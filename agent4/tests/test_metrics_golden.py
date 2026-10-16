from datetime import date
import duckdb
import pytest
from eval.oracle import oracle
from agent4.engine.metrics import REGISTRY

# Development seed only. The held-out agent test set is not touched.
PERIODS = [
    ('closed-month',date(2026,8,1),date(2026,8,31)),
    ('partial-month',date(2026,10,1),date(2026,10,31)),
    ('quarter',date(2026,7,1),date(2026,9,30)),
    ('year',date(2025,1,1),date(2025,12,31)),
    ('ytd',date(2026,1,1),date(2026,10,14)),
    ('vat-transition',date(2025,6,15),date(2025,7,15)),
]

@pytest.fixture(scope='module')
def reference_con(warehouse):
    con = duckdb.connect(str(warehouse),read_only=True)
    yield con
    con.close()

@pytest.mark.parametrize('metric',REGISTRY)
@pytest.mark.parametrize('case,start,end',PERIODS,ids=[p[0] for p in PERIODS])
def test_independent_golden(engine,reference_con,metric,case,start,end):
    md = REGISTRY[metric]
    expected = oracle(reference_con,metric,start,end,md.default_view)
    actual = engine.query(metric,{'start_date':str(start),'end_date':str(end)})['value']
    if expected is None:
        assert actual is None
    else:
        assert actual == pytest.approx(expected,abs=0.5 if md.unit=='VND' else 1e-9,rel=0)

@pytest.mark.parametrize('metric',[m.id for m in REGISTRY.values() if 'tax' in m.views and m.default_view!='tax'])
def test_tax_view(engine,reference_con,metric):
    start,end = date(2026,7,1),date(2026,9,30)
    result = engine.query(metric,'2026-Q3',view='tax')['value']
    assert result == pytest.approx(oracle(reference_con,metric,start,end,'tax'),abs=0.5,rel=0)

def test_explain_from_base_tables(engine,reference_con):
    detail = engine.explain('net_profit','2026-Q3')
    expected = reference_con.execute("""SELECT a.account_code,SUM(g.debit_amount),SUM(g.credit_amount),COUNT(*)
    FROM gl_entry g JOIN dim_account a USING(account_key)
    WHERE posting_date BETWEEN '2026-07-01' AND '2026-09-30' AND NOT is_closing
    AND COALESCE(source_module,'')<>'OPENING' AND left(a.account_code,3) IN ('511','521','632','641','642','515','635','711','811','821')
    GROUP BY 1 ORDER BY 1""").fetchall()
    assert [(r['account_code'],r['debit'],r['credit'],r['lines']) for r in detail['accounts_summary']] == expected

def test_oracle_has_no_production_imports():
    import ast
    from pathlib import Path
    tree = ast.parse(Path('eval/oracle.py').read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node,ast.ImportFrom):
            assert not (node.module or '').startswith('agent4')
        elif isinstance(node,ast.Import):
            assert all(not name.name.startswith('agent4') for name in node.names)
