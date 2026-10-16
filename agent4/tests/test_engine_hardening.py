from concurrent.futures import ThreadPoolExecutor
from datetime import date
import pytest
from agent4.engine.engine import EngineError,FilterError,ScopeNotSupported,ViewNotAllowedError
from agent4.engine.metrics import REGISTRY
from agent4.engine.scope import SAFE_CUSTOM
from eval.oracle import oracle

@pytest.mark.parametrize('metric',REGISTRY)
def test_scope_is_enforced_or_explicitly_rejected(engine,metric):
    md = REGISTRY[metric]
    if md.kind=='custom' and metric not in SAFE_CUSTOM:
        with pytest.raises(ScopeNotSupported) as error:
            engine.query(metric,'2026-Q3',scope={'branch':['HCM']})
        assert error.value.code=='SCOPE_NOT_SUPPORTED'
    else:
        result = engine.query(metric,'2026-Q3',scope={'branch':['HCM']})
        expected = engine.query(metric,'2026-Q3',filters={'branch':['HCM']})
        assert result['value']==expected['value']
        assert result.get('rows')==expected.get('rows')
        # Independent empty predicate must produce no non-zero financial values.
        empty = engine.query(metric,'2026-Q3',scope={'branch':[]})
        assert empty['value'] in (0,None)

def test_scope_and_user_filters_intersect(engine):
    result = engine.query('net_revenue','2026-Q3',filters={'branch':['HN']},scope={'branch':['HCM']})
    assert result['value']==0
    assert engine.query('net_revenue','2026-Q3',filters={'branch':['HN','HCM']},scope={'branch':['HCM']})['value']==engine.query('net_revenue','2026-Q3',filters={'branch':['HCM']})['value']

def test_scope_filters_explain_entries(engine):
    detail = engine.explain('net_revenue','2026-Q3',scope={'branch':['HCM']},limit=1000)
    keys = [r['journal_id'] for r in detail['top_entries']]
    assert keys
    for journal in keys:
        branches = engine.q("SELECT DISTINCT branch_code FROM v_gl WHERE journal_id=? AND account_code LIKE '511%'",[journal])
        assert branches==[('HCM',)]

@pytest.mark.parametrize('scope',[{'branch':['Ho Chi Minh']},{'unknown':['HCM']},{'branch':'HCM'},{'branch':None}])
def test_scope_requires_exact_codes(engine,scope):
    with pytest.raises(FilterError):
        engine.query('net_revenue','2026-Q3',scope=scope)

def test_exclusion_resolves_only_scoped_top_customer(engine):
    result = engine.query('ar_balance','2026-Q3',filters={'exclude_top_customers':1},scope={'branch':['HCM']})
    expected = engine.q("""SELECT partner_code FROM v_gl WHERE account_code LIKE '131%' AND posting_date<='2026-09-30'
    AND branch_code='HCM' AND partner_code IS NOT NULL GROUP BY 1 ORDER BY SUM(net_debit) DESC LIMIT 1""")[0][0]
    assert result['filters']['exclude_top_customers'][0]['code']==expected

@pytest.mark.parametrize('metric',['dso','dpo','dio','cash_conversion_cycle','cash_coverage_days','dso_actual'])
def test_custom_comparison(engine,metric):
    result = engine.query(metric,'2026-Q3',compare_to='previous_period')
    expected = engine.query(metric,'2026-Q2')['value']
    assert result['comparison']['value']==expected
    assert result['comparison']['delta']==pytest.approx(result['value']-expected)

def test_partial_custom_comparison(engine):
    result = engine.query('dso','this_month',compare_to='previous_period')
    assert result['comparison']['period']['end_date']=='2026-09-14'
    expected = engine.query('dso',{'start':'2026-09-01','end':'2026-09-14'})['value']
    assert result['comparison']['value']==expected

@pytest.mark.parametrize('basis,column',[('receipt','receipt_date'),('bank','bank_txn_date')])
def test_dso_actual_date_basis_matches_raw_sql(engine,basis,column):
    actual = engine.query('dso_actual','2026-Q3',params={'date_basis':basis})['value']
    expected = engine.q(f"""SELECT SUM(r.amount*date_diff('day',i.issue_date,r.{column}))/SUM(r.amount)
    FROM ar_receipt r JOIN ar_invoice i USING(invoice_id) JOIN dim_partner p ON p.partner_code=r.customer_code
    WHERE r.{column} BETWEEN '2026-07-01' AND '2026-09-30' AND p.segment<>'RET'""")[0][0]
    assert actual==pytest.approx(float(expected),abs=1e-9,rel=0)

def test_date_basis_is_whitelisted_and_affects_lineage(engine):
    with pytest.raises(EngineError):
        engine.query('dso_actual','2026-Q3',params={'date_basis':'injected'})
    receipt = engine.query('dso_actual','2026-Q3')
    bank = engine.query('dso_actual','2026-Q3',params={'date_basis':'bank'})
    assert receipt['audit_trail']['lineage_id']!=bank['audit_trail']['lineage_id']

def test_version_and_scope_change_lineage(engine):
    original = engine.query('net_revenue','2026-Q3')['audit_trail']['lineage_id']
    assert engine.query('net_revenue','2026-Q3',scope={'branch':['HCM']})['audit_trail']['lineage_id']!=original
    with engine.cursor() as child:
        child.info = {**child.info,'data_version':'test-version'}
        assert child.query('net_revenue','2026-Q3')['audit_trail']['lineage_id']!=original

def test_request_cursors_are_independent(engine):
    def query(i):
        with engine.cursor() as child:
            return child.query('net_revenue','2026-Q3')['value']
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(query,range(12)))
    assert values==[engine.query('net_revenue','2026-Q3')['value']]*12

def test_explain_cannot_bypass_view_rules(engine):
    with pytest.raises(ViewNotAllowedError):
        engine.explain('taxable_income','2026-Q3',view='mgmt')

@pytest.mark.parametrize('kwargs',[{'top_k':-1},{'top_k':True},{'params':{'min_days':'not-a-number'}},
                                 {'view':23},{'compare_to':'bad-mode'},{'filters':{'exclude_top_customers':'not-a-number'}}])
def test_invalid_requests_return_domain_errors(engine,kwargs):
    with pytest.raises(EngineError) as error:
        engine.query('overdue_receivables','2026-Q3',**kwargs)
    assert error.value.code

@pytest.mark.parametrize('metric',['net_revenue','dso','dpo','dio','expense_spikes'])
def test_scoped_result_against_independent_sql(engine,metric):
    expected = oracle(engine.con,metric,date(2026,7,1),date(2026,9,30),'mgmt',{'branch':['HCM']})
    assert engine.query(metric,'2026-Q3',scope={'branch':['HCM']})['value']==pytest.approx(expected,abs=.5,rel=0)
