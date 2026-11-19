"""Build an Agent 2 rule snapshot (agent2-rule-snapshot/1.0.0, native-rule-source/1.0.0) from a transaction CSV/XLSX.

Every column the file really has is kept. Fields the file does not carry stay empty, and tables the file cannot provide
are left out (rules that need them report the missing source instead of inventing data). Coverage claims are 'partial'
with a bounded period: the file is one export, not a full ledger since inception.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json

CONTRACT = 'agent2-rule-snapshot/1.0.0'
SOURCE_VERSION = 'native-rule-source/1.0.0'
MAX_CANDIDATES = 200

INT_FIELDS = {'is_financial_entry', 'support_doc_count', 'goods_receipt_verified', 'evidence_on_file'}
TX_FIELDS = ('company_id', 'transaction_id', 'posted_at', 'created_at', 'approved_at', 'amount_vnd', 'txn_type', 'currency', 'vendor_id', 'employee_id',
             'customer_id', 'creator_id', 'approver_id', 'approval_limit_vnd', 'payment_channel', 'is_financial_entry', 'recipient_account', 'invoice_number',
             'invoice_issued_at', 'invoice_gross_vnd', 'support_doc_count', 'goods_receipt_verified', 'payroll_period', 'advance_id', 'debit_account',
             'credit_account')
TX_OPTIONAL = ('journal_signature', 'accounting_purpose', 'business_purpose', 'recognised_input_vat_vnd', 'recognised_output_vat_vnd', 'writeoff_provision_vnd',
               'production_cost_vnd', 'evidence_on_file', 'journal_document_id', 'linked_document_id', 'account_pair', 'department', 'project_id',
               'counterparty_account', 'counterparty_type', 'invoice_id', 'invoice_net_vnd', 'invoice_vat_vnd', 'linked_input_vat_vnd', 'vat_rate',
               'recipient_bank_code', 'effective_date', 'self_approval_exception_id', 'bank_change_id', 'accounting_framework')


def _ts(value):
    """ISO with seconds and +07:00 (the native profile rejects anything else)."""
    text = str(value or '').strip()
    if not text:
        return ''
    d = datetime.fromisoformat(text.replace('Z', '+00:00').replace(' ', 'T'))
    if d.tzinfo is None:
        from datetime import timezone, timedelta
        d = d.replace(tzinfo=timezone(timedelta(hours=7)))
    from datetime import timezone, timedelta
    return d.astimezone(timezone(timedelta(hours=7))).replace(microsecond=0).isoformat()


def _int(value):
    text = str(value if value is not None else '').strip().replace(',', '')
    if text == '':
        return ''
    return int(round(float(text)))


def _digest(records):
    raw = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def build(rows, tenant, company, company_name, purpose='intake'):
    """rows: list of dict (header -> cell). Returns (json bytes, summary)."""
    txs, vendors, employees, customers = {}, set(), set(), set()
    for raw in rows:
        r = {str(k).strip(): ('' if v is None else v) for k, v in raw.items() if k is not None}
        rid = str(r.get('transaction_id') or '').strip()
        if not rid:
            continue
        posted = _ts(r.get('posted_at'))
        tx = {}
        for f in TX_FIELDS + TX_OPTIONAL:
            if f not in r and f not in TX_FIELDS:
                continue
            v = r.get(f, '')
            if f.endswith('_vnd'):
                v = _int(v)
                v = 0 if v == '' else v  # amount not in the export (e.g. no invoice attached): 0, never a guessed value
            elif f.endswith('_at'):
                v = _ts(v)
            elif f in INT_FIELDS:
                v = _int(v)
                v = 0 if v == '' else v
            elif f == 'vat_rate':
                v = float(v) if str(v).strip() else ''
            else:
                v = str(v).strip()
            tx[f] = v
        tx['company_id'] = company
        tx['currency'] = 'VND'
        tx['observed_at'] = tx.get('approved_at') or tx.get('created_at') or posted
        txs[rid] = tx
        for key, bucket in (('vendor_id', vendors), ('customer_id', customers)):
            if tx.get(key):
                bucket.add(tx[key])
        for key in ('employee_id', 'creator_id', 'approver_id'):
            if tx.get(key):
                employees.add(tx[key])
    if not txs:
        raise ValueError('Tệp không có giao dịch hợp lệ (thiếu transaction_id).')
    ordered = sorted(txs.values(), key=lambda t: (t['posted_at'], t['transaction_id']))
    as_of = max(t['observed_at'] for t in ordered if t['observed_at'])
    as_of = max(as_of, max(t['posted_at'] for t in ordered))
    start = min(t['posted_at'] for t in ordered)
    master_at = min(v for t in ordered for k, v in t.items() if k.endswith('_at') and v)
    company_row = dict(company_id=company, name=company_name or company, accounting_framework='TT200',
                       saturday_operations=int(any(datetime.fromisoformat(t['posted_at']).weekday() == 5 for t in ordered)), currency='VND',
                       observed_at=master_at, recorded_at=master_at)
    limits = [t['approval_limit_vnd'] for t in ordered if isinstance(t.get('approval_limit_vnd'), int)]
    company_limit = max(limits) if limits else 0
    # The export carries the approval limit on each transaction; employees inherit it. Self-approval is not permitted by default.
    emp_rows = [dict(company_id=company, employee_id=e, full_name=e, role='', approval_limit_vnd=company_limit, self_approval_limit_vnd=0, bank_account='', phone='',
                     address='', contract_on_file=1, observed_at=master_at, recorded_at=master_at) for e in sorted(employees)]
    # Vendor master dates are not in the export: use the start of the first year in the file so a missing master never
    # looks like a brand-new vendor paid the same day.
    year_start = master_at[:4] + '-01-01T00:00:00+07:00'
    ven_rows = [dict(company_id=company, vendor_id=v, name=v, registered_at=year_start, onboarded_at=year_start, bank_account='', phone='', address='',
                     related_party_disclosed_at='', observed_at=master_at, recorded_at=master_at) for v in sorted(vendors)]
    cus_rows = [dict(company_id=company, customer_id=c, name=c, observed_at=master_at, recorded_at=master_at) for c in sorted(customers)]
    tables = dict(companies=[company_row], employees=emp_rows, transactions=ordered)
    if ven_rows:
        tables['vendors'] = ven_rows
    if cus_rows:
        tables['customers'] = cus_rows
    coverage = {name: dict(status='complete', observed_at=as_of, covered_from=master_at, covered_through=as_of, history_basis='bounded_period',
                           record_count=len(recs), records_sha256=_digest(recs)) for name, recs in tables.items()}
    candidates = [t['transaction_id'] for t in ordered[-MAX_CANDIDATES:]]
    doc = dict(contract_version=CONTRACT, tenant_id=tenant, company_id=company, candidate_transaction_ids=candidates,
               source=dict(version=SOURCE_VERSION, tenant_id=tenant, company_id=company, as_of=as_of, source_id=f'{"training" if purpose == "training" else "portal-intake"}-{company}-{as_of[:10]}',
                           is_simulated=True, tables=tables, coverage=coverage))
    body = json.dumps(doc, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return body, dict(rows=len(ordered), skipped=0, first=start, last=as_of, vendors=len(ven_rows), employees=len(emp_rows), native_json=True)
