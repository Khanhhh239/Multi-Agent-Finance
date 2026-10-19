import calendar
import hashlib
from datetime import date
import duckdb
import pytest
from agent4.engine.metrics import REGISTRY
from agent4.datagen.build import build

LINEAR = [m for m in REGISTRY.values() if m.kind in ('flow','snapshot')]

@pytest.mark.parametrize('metric,group',[(m.id,g) for m in LINEAR for g in m.group_bys if not(m.kind=='snapshot' and g=='month')])
def test_sum_groups_equals_total(engine,metric,group):
    result = engine.query(metric,'2026-Q3',group_by=group,top_k=100000)
    assert sum(r['value'] for r in result['rows']) == pytest.approx(result['value'],abs=.5,rel=0)

@pytest.mark.parametrize('metric',[m.id for m in LINEAR if m.kind=='flow'])
def test_flow_additivity(engine,metric):
    q3 = engine.query(metric,'2026-Q3')['value']
    assert q3 == pytest.approx(sum(engine.query(metric,f'2026-{m:02}')['value'] for m in (7,8,9)),abs=.5,rel=0)
    year = engine.query(metric,'2025')['value']
    assert year == pytest.approx(sum(engine.query(metric,f'2025-{m:02}')['value'] for m in range(1,13)),abs=.5,rel=0)

@pytest.mark.parametrize('metric',[m.id for m in LINEAR if m.kind=='snapshot' and 'month' in m.group_bys])
def test_snapshot_months_are_balances_not_additive_flows(engine,metric):
    result = engine.query(metric,'2026-Q3',group_by='month')
    assert result['rows'][-1]['value']==result['value']
    for row in result['rows']:
        assert row['value']==engine.query(metric,row['key'])['value']

@pytest.mark.parametrize('month',range(1,13))
def test_accounting_equation_with_explicit_a4_exception(engine,month):
    on = date(2026,month,calendar.monthrange(2026,month)[1])
    imbalance = engine.q("""SELECT COALESCE(SUM(debit_amount-credit_amount),0) FROM gl_entry WHERE posting_date<=?""",[on])[0][0]
    # A4 is intentional, never erase it or silently declare raw balance zero.
    expected = 500000 if on>=date(2026,7,31) else 0
    assert float(imbalance) == expected
    a = engine.query('total_assets',str(on))['value']
    l = engine.query('total_liabilities',str(on))['value']
    e = engine.query('equity',str(on))['value']
    assert a-l-e == pytest.approx(expected,abs=.5,rel=0)

@pytest.mark.parametrize('month',range(1,9))
def test_closed_profit_equals_retained_earnings(engine,month):
    # January includes a transfer of prior-year earnings 4212 -> 4211.
    delta = engine.q("""SELECT SUM(credit_amount-debit_amount) FROM v_gl WHERE account_code='4212' AND year_month=?
    AND journal_id NOT IN (SELECT journal_id FROM v_gl WHERE account_code='4211')""",[f'2026-{month:02}'])[0][0]
    assert engine.query('net_profit',f'2026-{month:02}')['value'] == pytest.approx(float(delta or 0),abs=.5,rel=0)

def test_january_transfer_is_prior_year_profit(engine):
    transfer = engine.q("""SELECT SUM(debit_amount-credit_amount) FROM v_gl WHERE account_code='4212' AND year_month='2026-01'
    AND journal_id IN (SELECT journal_id FROM v_gl WHERE account_code='4211')""")[0][0]
    assert float(transfer) == engine.query('net_profit','2025')['value']

@pytest.mark.parametrize('month',range(1,10))
def test_subledger_reconciliation(engine,month):
    on = date(2026,month,calendar.monthrange(2026,month)[1])
    assert engine.query('ar_balance',str(on))['value'] == pytest.approx(engine.query('ar_aging',str(on))['value'],abs=.5,rel=0)
    ap = engine.query('ap_by_vendor',str(on),top_k=100000)
    assert sum(r['value'] for r in ap['rows']) == pytest.approx(engine.query('ap_balance',str(on))['value'],abs=.5,rel=0)
    inv = engine.q('SELECT SUM(value) FROM inventory_txn WHERE txn_date<=?',[on])[0][0]
    # Generator currently stocks only account 156; assert rather than assume.
    assert engine.query('inventory_value',str(on))['value'] == pytest.approx(float(inv or 0),abs=.5,rel=0)

@pytest.mark.parametrize('metric',REGISTRY)
def test_query_idempotent(engine,metric):
    assert engine.query(metric,'2026-Q3') == engine.query(metric,'2026-Q3')

def ledger_hash(path):
    con = duckdb.connect(str(path),read_only=True)
    digest = hashlib.sha256()
    for row in con.execute('SELECT * FROM gl_entry ORDER BY entry_id').fetchall():
        digest.update((repr(row)+'\n').encode('utf-8'))
    con.close()
    return digest.hexdigest()

@pytest.mark.slow
def test_same_seed_reproduces_ledger(tmp_path,warehouse):
    other = tmp_path/'same_seed.duckdb'
    build(other,seed=20251,quiet=True)
    assert ledger_hash(other) == ledger_hash(warehouse)
    con = duckdb.connect(str(other),read_only=True)
    assert dict(con.execute('SELECT key,value FROM company_info').fetchall())['data_version']=='v2.1'
    original=duckdb.connect(str(warehouse),read_only=True)
    sql='SELECT * FROM budget ORDER BY ALL'
    assert con.execute(sql).fetchall()==original.execute(sql).fetchall()
    original.close()
    con.close()
