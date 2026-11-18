"""Portal intake for Agent 2: turn the shared transaction CSV into Agent 2's input contract 1.1.0 and walk it through
Agent 2's own import API (upload, preview, commit) with the operator's Portal session.

Only cash movements are sent: rows paid through the bank (receipts, vendor payments, rent, payroll). Journal-only
entries (sales invoices, depreciation, VAT offsets) are not money moving and stay with Agents 1, 3 and 4.
Standard library only, like the rest of the portal.
"""
import csv
import io
import json
import uuid
from hashlib import sha256
from urllib.parse import quote

CONTRACT = '1.1.0'
SYSTEM = 'portal-intake'
KIND = {'customer_receipt': 'receipt', 'vendor_payment': 'payment', 'rent': 'payment', 'payroll': 'payroll'}
MAX_BYTES = 9 * 1024 * 1024         # Agent 2 refuses files above 10 MB


class IntakeError(ValueError):
    pass


def _source(record_id):
    return {'system': SYSTEM, 'record_id': record_id, 'is_simulated': True}


def _base(tenant, company, record_id, observed, effective):
    return {'tenant_id': tenant, 'company_id': company, 'record_id': record_id, 'revision': 1,
            'observed_at': observed, 'effective_at': effective, 'source': _source(record_id)}


def build_contract(raw, tenant, company, company_name):
    """Return (json bytes, summary) for the transaction CSV `raw`."""
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline='')))
    if not rows:
        raise IntakeError('Tệp giao dịch không có dòng nào.')
    transactions, vendors, employees, skipped = [], {}, {}, 0
    first = last = None
    for row in rows:
        kind = KIND.get(row.get('txn_type', ''))
        if kind is None or row.get('payment_channel') != 'bank':
            skipped += 1
            continue
        rid = row['transaction_id'].strip()
        posted = row['posted_at']
        observed = row.get('approved_at') or row.get('created_at') or posted
        item = _base(tenant, company, rid, observed, posted)
        item.update(amount_vnd=int(row['amount_vnd']), currency='VND', kind=kind,
                    description=(row.get('business_purpose') or row.get('accounting_purpose') or kind)[:2000],
                    payment_channel='bank')
        vendor = (row.get('vendor_id') or '').strip()
        employee = (row.get('employee_id') or '').strip()
        creator = (row.get('creator_id') or '').strip()
        if vendor:
            vendors[vendor] = True
            item['vendor_ref'] = {'record_id': vendor, 'revision': 1}
        if employee:
            employees[employee] = True
            item['employee_ref'] = {'record_id': employee, 'revision': 1}
        if creator:
            employees[creator] = True
            item['created_by_ref'] = {'record_id': creator, 'revision': 1}
        transactions.append(item)
        first = posted if first is None or posted < first else first
        last = posted if last is None or posted > last else last
    if not transactions:
        raise IntakeError('Không có dòng chuyển tiền qua ngân hàng nào trong tệp giao dịch.')
    stamp = first
    doc = {'contract_version': CONTRACT, 'tenant_id': tenant,
           'companies': [dict(_base(tenant, company, company, stamp, stamp), name=company_name or company)],
           'transactions': transactions,
           'vendors': [dict(_base(tenant, company, v, stamp, stamp), name=v) for v in sorted(vendors)],
           'invoices': [], 'payment_allocations': [],
           'employees': [dict(_base(tenant, company, e, stamp, stamp), name=e) for e in sorted(employees)],
           'approvals': [], 'supporting_documents': [], 'vendor_bank_history': [], 'payment_history_coverage': []}
    body = json.dumps(doc, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(body) > MAX_BYTES:
        raise IntakeError('Tệp sau khi chuyển đổi vượt 9 MB; chia nhỏ theo kỳ rồi nạp lại.')
    return body, dict(rows=len(transactions), skipped=skipped, first=first, last=last, vendors=len(vendors),
                      employees=len(employees))


def _headers(token, extra=None):
    head = {'Authorization': 'Bearer ' + token}
    head.update(extra or {})
    return head


def preview(call, agent_url, token, tenant, company, company_name, name, raw):
    """Upload and preview. `call(method, url, body, headers, timeout)` is the portal's own HTTP helper."""
    body, summary = build_contract(raw, tenant, company, company_name)
    base = f'/api/v1/companies/{quote(company)}/'
    key = 'portal-' + sha256(body).hexdigest()[:40]
    st, draft = call('POST', agent_url(base + 'imports/upload'), body,
                     _headers(token, {'Content-Type': 'application/octet-stream', 'X-File-Name': quote(name.rsplit('.', 1)[0] + '.json'),
                                      'Idempotency-Key': key}), 600)
    if st not in (200, 201):
        raise IntakeError(_message(draft, st))
    st, prev = call('POST', agent_url(base + 'imports/' + draft['import_id'] + '/preview'), {'expected_revision': draft['revision']},
                    _headers(token), 600)
    if st not in (200, 201):
        raise IntakeError(_message(prev, st))
    return dict(import_id=draft['import_id'], preview={k: prev.get(k) for k in
                ('revision', 'preview_id', 'source_hash', 'mapping_hash', 'report_hash', 'context_hash', 'expires_at')},
                key=key, summary=summary, warnings=prev.get('warnings') or [])


def commit(call, agent_url, token, company, pending):
    base = f'/api/v1/companies/{quote(company)}/'
    request = {'expected_revision': pending['preview']['revision'], 'acknowledge': True}
    for name in ('preview_id', 'source_hash', 'mapping_hash', 'report_hash', 'context_hash'):
        request[name] = pending['preview'][name]
    st, res = call('POST', agent_url(base + 'imports/' + pending['import_id'] + '/commit'), request,
                   _headers(token, {'Idempotency-Key': pending['key'] + '-commit'}), 600)
    if st not in (200, 201):
        raise IntakeError(_message(res, st))
    return res.get('snapshot') or {}


def _message(res, status):
    if isinstance(res, dict):
        text = res.get('error') or res.get('message') or res.get('detail')
        if isinstance(text, dict):
            text = text.get('message') or json.dumps(text, ensure_ascii=False)[:300]
        if text:
            return str(text)[:400]
    return f'Agent 2 trả lỗi {status}.'


def new_key():
    return uuid.uuid4().hex
