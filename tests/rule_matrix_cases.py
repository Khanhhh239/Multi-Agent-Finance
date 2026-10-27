"""Small raw-source business controls under the current default rule policy.

No saved dataset, label, split, oracle or model is opened by this module.
Expected routing is declared here, independently of the detector output.
"""
import copy
from datetime import timedelta

from sme_fraud.generate import stamp
from sme_fraud.rule_audit_cases import Case
from sme_fraud.rules import DEFAULT_CONFIG


def current_case():
    case = Case()
    case.config = copy.deepcopy(DEFAULT_CONFIG)
    return case


def advance_case(*, writeoff=False, evidence=0, overdue_days=1, grace=0):
    case = current_case()
    case.config['advance_grace_days'] = grace
    advance = dict(advance_id='MATRIX_ADV', company_id='C001',
                   employee_id=case.worker['employee_id'], issue_transaction_id='MATRIX_ISSUE',
                   issued_at=stamp(case.at - timedelta(days=60)),
                   recorded_at=stamp(case.at - timedelta(days=60)),
                   original_due_at=stamp(case.at - timedelta(days=overdue_days)),
                   original_amount_vnd=5_000_000)
    case.tables['advances'] = [advance]
    case.tables['advance_events'] = []
    row = case.pay(kind='advance_writeoff' if writeoff else 'advance_review',
                   amount=5_000_000, advance_id=advance['advance_id'], evidence_on_file=evidence,
                   support_doc_count=2 if evidence else 0)
    if writeoff:
        event = advance_event(case, row, 'writeoff', observed=case.at, amount=5_000_000, evidence=evidence)
        event['transaction_id'] = row['transaction_id']
    return case, row


def advance_event(case, row, kind, *, observed=None, amount=0, due=None, evidence=1):
    event = dict(event_id='MATRIX_EVENT_' + str(len(case.tables['advance_events'])),
                 advance_id=row['advance_id'], company_id=row['company_id'], event_type=kind,
                 observed_at=stamp(observed or case.at - timedelta(seconds=1)),
                 new_due_at=stamp(due) if due else '', amount_vnd=amount,
                 transaction_id='', evidence_on_file=evidence)
    case.tables['advance_events'].append(event)
    return event


def manual_close(case, row):
    approved = dict(company_id='C001', status='approved', evidence_on_file=1,
                    evidence_id='MATRIX_APPROVAL', approver_id=case.director['employee_id'],
                    approved_at=stamp(case.at - timedelta(days=7)),
                    observed_at=stamp(case.at - timedelta(days=6)))
    case.tables['journal_audit_log'] = [dict(audit_id='MATRIX_MANUAL', company_id='C001',
        employee_id=case.maker['employee_id'], transaction_id=row['transaction_id'], entry_origin='manual',
        entered_at=row['created_at'], observed_at=row['posted_at'], evidence_id='MATRIX_AUDIT')]
    case.tables['closing_periods'] = [dict(approved, closing_id='MATRIX_CLOSE',
        period_start='2025-08-01', period_end='2025-08-31', closing_at=stamp(case.at + timedelta(days=2)))]
    case.tables['materiality_policies'] = [dict(approved, policy_id='MATRIX_MATERIAL',
        effective_from='2025-01-01', effective_to='2025-12-31', materiality_vnd=2_000_000)]


# A positive context/master finding is expected to stay out of the risk queue.
# These constants are acceptance expectations, not copies of admission().
ROUTING = {
    'A1': ('trung_binh', 168), 'A2': ('trung_binh', 168),
    'A3': ('trung_binh', 168), 'A4': ('trung_binh', 168),
    'A5': (None, None), 'A6': ('trung_binh', 168),
    'B1': ('cao_nhat', 24), 'B2': ('trung_binh', 168), 'B3': (None, None),
    'B4': ('trung_binh', 168), 'B5': (None, None), 'B6': ('trung_binh', 168),
    'B7': ('cao_nhat', 24), 'C1': (None, None), 'C2': ('cao_nhat', 24),
    'C3': ('trung_binh', 168), 'C4': ('trung_binh', 168),
    'E1': ('cao_nhat', 24), 'E2': ('cao_nhat', 24), 'E3': (None, None), 'E4': (None, None),
    'F1': ('trung_binh', 168), 'F2': ('trung_binh', 168),
    'F3': ('trung_binh', 168), 'F4': ('trung_binh', 168),
    'P1': ('cao_nhat', 24), 'P2': ('thap', 720),
    'T1': ('trung_binh', 168), 'T2': ('cao_nhat', 24),
}


def positive_case(code):
    """Return case, target raw transaction and optional source-finding scope."""
    if code in {'C4', 'E2', 'F2', 'F3', 'F4'}:
        from sme_fraud.evidence_cases import prepare
        case, row, expected, scope = prepare(code, 'positive', 20261027)
        assert expected is True
        case.config = {**copy.deepcopy(DEFAULT_CONFIG), **case.config}
        return case, row, scope
    if code in {'T1', 'T2'}:
        case, row = advance_case(writeoff=code == 'T2')
        return case, row, 'transaction'
    if code == 'P2':
        from test_cash_controls import CashControlsTest
        helper = CashControlsTest()
        case = helper.case()
        helper.verified_limit(case)
        case.config = {**copy.deepcopy(DEFAULT_CONFIG), **case.config}
        row = helper.pay(case, 2_000_001)
        return case, row, 'transaction'
    case = current_case()
    if code == 'A1':
        row = case.sequence([9_000_000] * 2)
    elif code == 'A2':
        row = case.sequence([9_000_000] * 3, days=7)
    elif code == 'A3':
        row = case.sequence([9_000_000] * 2, vendors=case.shared_vendors()[:2])
    elif code == 'A4':
        row = case.sequence([17_000_000] * 3, kind='cash_expense')
    elif code == 'A5':
        case.sequence([1_000_000 + (i % 5 - 2) * 10_000 for i in range(25)],
                      kind='cash_expense', start=case.at - timedelta(days=30))
        row = case.pay(amount=3_000_000, kind='cash_expense')
    elif code == 'A6':
        row = case.pay(amount=2_001_000, invoice_gross_vnd=1_990_007)
    elif code == 'B1':
        row = case.pay(recipient_account=case.worker['bank_account'])
    elif code == 'B2':
        case.vendor['phone'] = case.worker['phone']
        row = case.pay()
    elif code == 'B3':
        case.new_vendor()
        row = case.pay(amount=50_000_000, support_doc_count=0, goods_receipt_verified=0)
    elif code == 'B4':
        case.g.status(case.vendor, 'ceased', case.at - timedelta(days=10), case.at - timedelta(days=9))
        row = case.pay(invoice_issued_at=stamp(case.at - timedelta(days=2)))
    elif code in {'B5', 'E4'}:
        row = case.pay(vendor=case.shared_vendors()[0])
    elif code == 'B6':
        case.sequence([1_000_000 + (i % 5) * 10_000 for i in range(20)],
                      start=case.at - timedelta(days=200))
        row = case.pay(amount=5_000_000)
    elif code == 'B7':
        row = case.change()
    elif code == 'C1':
        row = case.pay(at=case.at.replace(hour=23), created_at=stamp(case.at.replace(hour=23)))
    elif code == 'C2':
        row = case.pay(amount=int(case.maker['self_approval_limit_vnd']) + 1,
                       approver_id=case.maker['employee_id'])
    elif code == 'C3':
        row = case.pay(amount=50_000_000, approved_at=stamp(case.at),
                       created_at=stamp(case.at - timedelta(seconds=59)))
    elif code == 'E1':
        row = case.attendance()
    elif code == 'E3':
        case.tables['vendors'] = case.tables['vendors'][12:14]
        case.tables['vendors'][0]['name'] = 'ABC Co., Ltd'
        case.tables['vendors'][1]['name'] = 'A.B.C Co Ltd'
        row = case.pay()
    elif code == 'F1':
        row = case.pay(amount=5_000_000, kind='adjustment')
        manual_close(case, row)
    elif code == 'P1':
        row = case.sequence([9_000_000] * 2, invoice_number='MATRIX_ONE', invoice_gross_vnd=9_000_000)
    else:
        raise ValueError('No matrix fixture for ' + code)
    return case, row, 'transaction'


def target_hits(result, row, code):
    return [hit for hit in result['hits'] if hit['transaction_id'] == row['transaction_id']
            and (hit['rule_id'] == code or code in hit.get('aliases', []))]


def negative_case(code):
    if code in {'C4', 'E2', 'F2', 'F3', 'F4'}:
        from sme_fraud.evidence_cases import prepare
        variants = dict(C4='authorized', E2='final_payment', F2='completed', F3='cancelled_gap', F4='fully_paid')
        case, row, expected, scope = prepare(code, variants[code], 20261027)
        assert expected is False
        case.config = {**copy.deepcopy(DEFAULT_CONFIG), **case.config}
        return case, row, scope
    if code in {'T1', 'T2'}:
        case, row = advance_case(writeoff=code == 'T2', evidence=1, overdue_days=0)
        return case, row, 'transaction'
    if code == 'P2':
        from test_cash_controls import CashControlsTest
        helper = CashControlsTest()
        case = helper.case()
        helper.verified_limit(case)
        case.config = {**copy.deepcopy(DEFAULT_CONFIG), **case.config}
        row = helper.pay(case, 2_000_000)
        return case, row, 'transaction'
    case = current_case()
    if code == 'A5':
        case.sequence([1_000_000 + (i % 5 - 2) * 10_000 for i in range(25)],
                      kind='cash_expense', start=case.at - timedelta(days=30))
        row = case.pay(amount=1_000_000, kind='cash_expense')
    elif code == 'B6':
        case.sequence([1_000_000] * 20, start=case.at - timedelta(days=20))
        row = case.pay(amount=5_000_000)
    elif code == 'E1':
        row = case.attendance(alternative=1)
    elif code == 'E3':
        case.tables['vendors'] = case.tables['vendors'][12:14]
        case.tables['vendors'][0]['name'] = 'ALPHA INDUSTRIAL'
        case.tables['vendors'][1]['name'] = 'ZETA AGRICULTURE'
        row = case.pay()
    elif code == 'P1':
        row = case.sequence([4_000_000, 5_000_000], invoice_number='MATRIX_INSTALLMENTS', invoice_gross_vnd=9_000_000)
    elif code == 'A6':
        row = case.pay(amount=1_000_000, invoice_gross_vnd=1_990_007)
    else:
        row = case.pay()
    return case, row, 'transaction'
