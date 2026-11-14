"""Read-only parity checks over existing native rule fixtures, not new rules."""
from collections import Counter
from copy import deepcopy

from finance_input import AccessScope
from sme_fraud.import_files import canonical,digest
from sme_fraud.method_adapters import native_inputs,score_batch
from sme_fraud.rules import score_rules


def company_tables(tables,company='C001'):
    return {name:deepcopy([r for r in rows if r.get('company_id',company)==company]
                          if isinstance(rows,list) else rows)
            for name,rows in tables.items() if name not in {'labels','splits'}}


def compare_native(tables,config=None,company='C001'):
    """Evaluate both paths independently on exactly the same scoped sources."""
    scope=AccessScope('parity-demo',frozenset({company}),'parity-review',frozenset({'data.import'}))
    tables=company_tables(tables,company);before=digest(canonical(tables))
    baseline_input=deepcopy(tables);native_input=deepcopy(tables)
    baseline=score_rules(baseline_input,config=config)
    frame,raw,graphs=native_inputs(native_input,scope,config=config)
    raw_before=digest(canonical(raw))
    adapted=score_batch(frame,scope,methods=(),rule_output=raw,graphs=graphs)
    expected={(r['company_id'],r['transaction_id']):r for r in baseline['scores']}
    expected_ids=Counter((r['company_id'],r['transaction_id']) for r in tables['transactions'])
    actual_ids=Counter((r['company_id'],r['record_id']) for r in adapted['rows'])
    point_equal=all(r['methods']['rules']['available'] and
                    r['methods']['rules']['raw_score']==r['methods']['rules']['score']==expected[(r['company_id'],r['record_id'])]['rule_score']
                    for r in adapted['rows'])
    scores=[r['methods']['rules']['details']['native_score'] for r in adapted['rows']]
    hits=[h for r in adapted['rows'] for h in r['methods']['rules']['details']['hits']]
    diagnostics={k:v for k,v in baseline.items() if k not in {'scores','hits'}}
    observed=adapted.get('native_rule_diagnostics',{})
    checks=dict(all_transactions_retained=actual_ids==expected_ids and adapted['row_count']==len(tables['transactions']),
        points_equal=point_equal,native_score_and_alert_fields_equal=canonical(scores)==canonical(baseline['scores']),
        hits_and_exceptions_equal=canonical(hits)==canonical(baseline['hits']),
        native_diagnostics_equal=canonical(observed.get('output'))==canonical(diagnostics),
        diagnostic_binding_equal=observed.get('input_checksum')==before and observed.get('implementation_sha256')==raw['implementation_sha256'],
        coverage_equal=all(r['methods']['rules']['details']['coverage']==baseline['coverage'] for r in adapted['rows']),
        input_and_engine_output_unchanged=before==digest(canonical(tables))==digest(canonical(baseline_input))==digest(canonical(native_input))
                                         and raw_before==digest(canonical(raw)))
    counts=dict(input_rows=len(tables['transactions']),output_rows=adapted['row_count'],hits=len(baseline['hits']),
        operational_alerts=sum(r['operational_alert'] for r in baseline['scores']),
        zero_score_rows=sum(r['rule_score']==0 for r in baseline['scores']),
        suppressed_hits=sum(bool(h['suppressed_reason']) for h in baseline['hits']),
        suppressed_by_rule=dict(sorted(Counter(h['rule_id'] for h in baseline['hits'] if h['suppressed_reason']).items())),
        batch_events=len(baseline['batch_events']),
        batch_exceptions=sum(bool(e['suppressed_reason']) for e in baseline['batch_events']),
        batch_positive_events=sum(e['signal'] is True for e in baseline['batch_events']))
    result=dict(checks=checks,counts=counts,source_checksum=before,config=deepcopy(config),
                baseline_sha256=digest(canonical(baseline)),adapted_sha256=digest(canonical(adapted)))
    return result,adapted,baseline,raw,frame


def prepared_case(kind):
    """Reuse raw business fixtures and their real source helpers."""
    from datetime import timedelta
    from sme_fraud.rule_audit_cases import Case
    from sme_fraud.rules import DEFAULT_CONFIG
    from sme_fraud.generate import stamp
    from test_payment_evidence import PaymentEvidenceTest
    from test_authority_and_dormancy import AuthorityAndDormancyTest
    case=Case();case.config=dict(DEFAULT_CONFIG)
    if kind in ('five_default','five_legacy','self_approval'):
        case.vendor['name']='Orchid marine instruments'
        if kind=='five_legacy':case.config={}
        for index in range(5):
            at=case.at+timedelta(days=7*index)
            values=dict(created_at=stamp(at),approved_at=stamp(at+timedelta(minutes=5)))
            amount=500003+137*index
            if kind=='self_approval' and index<2:
                amount=int(case.maker['self_approval_limit_vnd'])+index
                values['approver_id']=case.maker['employee_id']
            case.pay(at,amount,**values)
    elif kind in ('installments','batch_installment_exception'):
        helper=PaymentEvidenceTest()
        count,days=(3,1) if kind=='installments' else (2,0)
        rows=[case.pay(case.at+timedelta(days=days*i),invoice_number='PARITY_BOUND_INVOICE',invoice_gross_vnd=27_000_000)
              for i in range(count)]
        helper.bind_request_rows(case,rows,total=9_000_000*count)
    elif kind=='bank_callback_revision':
        case.change()
        case.pay(case.at+timedelta(days=1),50_000_000,recipient_account='AUDIT_NEW_BANK',recipient_bank_code='AUDIT_BANK')
        original=case.tables['bank_account_changes'][0]
        case.tables['bank_account_changes'].append(dict(original,callback_verified=1,
            verified_at=stamp(case.at+timedelta(hours=1)),observed_at=stamp(case.at+timedelta(hours=2)),
            approver_id=case.director['employee_id']))
    elif kind=='paid_leave':case.attendance(leave=22)
    elif kind=='authority_matrix':
        helper=AuthorityAndDormancyTest();helper.coverage(case)
        helper.authority(case,case.maker['employee_id'],'self_approve',maximum=100_000_000,self_allowed=1)
        case.pay(amount=int(case.maker['self_approval_limit_vnd'])+1,approver_id=case.maker['employee_id'])
    elif kind=='batch_overpayment':
        for _ in range(2):
            case.pay(amount=9_000_000,invoice_number='PARITY_BATCH_INVOICE',invoice_gross_vnd=10_000_000,
                     support_doc_count=0,goods_receipt_verified=0)
    else:raise ValueError('Unknown parity fixture')
    case.score()
    return case
