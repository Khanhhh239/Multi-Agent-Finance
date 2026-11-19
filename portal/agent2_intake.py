"""Portal intake for Agent 2: turn the shared transaction CSV/XLSX (or native Agent 2 JSON contract)
into Agent 2's input contract and walk it through Agent 2's import API (upload, preview, commit)
with the operator's Portal session.

For shared transaction tables, only cash movements paid through the bank (receipts, vendor payments,
rent, payroll) are sent; journal-only entries stay with Agents 1, 3 and 4.
Standard library only, like the rest of the portal.
"""
import csv
import io
import json
import re
import uuid
from decimal import InvalidOperation
from hashlib import sha256
from urllib.parse import quote

if __package__:
    from . import bank_intake
else:
    import bank_intake

CONTRACT = '1.1.0'
SYSTEM = 'portal-intake'
KIND = {'customer_receipt': 'receipt', 'vendor_payment': 'payment', 'rent': 'payment', 'payroll': 'payroll'}
MAX_BYTES = 9 * 1024 * 1024         # Agent 2 refuses files above 10 MB
MAX_RECORDS = 50000                 # Agent 2 import_files.py MAX_ROWS limit
_ISO_TZ_RE = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$')
_DATETIME_NO_TZ_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?)$')


class IntakeError(ValueError):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = list(details or [])


class AlreadyCommitted(IntakeError):
    """The same bytes were already saved as an immutable Agent 2 snapshot; nothing to write again."""


def _is_committed(res):
    try:
        return 'IMPORT_COMMITTED' in json.dumps(res, ensure_ascii=False)
    except (TypeError, ValueError):
        return False


def _source(record_id):
    return {'system': SYSTEM, 'record_id': record_id, 'is_simulated': True}


def _base(tenant, company, record_id, observed, effective):
    return {'tenant_id': tenant, 'company_id': company, 'record_id': record_id, 'revision': 1,
            'observed_at': observed, 'effective_at': effective, 'source': _source(record_id)}


def _iso_timestamp(value: str) -> str:
    s = str(value or '').strip()
    if not s:
        return ''
    if _ISO_TZ_RE.fullmatch(s):
        return s
    if m := _DATETIME_NO_TZ_RE.fullmatch(s):
        return f'{m.group(1)}T{m.group(2)}+07:00'
    try:
        return bank_intake.day(s) + 'T00:00:00+07:00'
    except ValueError:
        return s


def _iter_raw_rows(name, raw, xlsx_reader=None):
    """Stream (header, row_iterator) without materializing hundreds of thousands of dicts in RAM."""
    if name.lower().endswith('.xlsx'):
        if xlsx_reader is None:
            raise IntakeError('Chưa hỗ trợ đọc XLSX trực tiếp khi thiếu bộ đọc bảng.')
        it = xlsx_reader(raw)
        header = [str(c).strip() for c in next(it, [])]
        return header, it
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise IntakeError('Tệp CSV cần mã hóa UTF-8.') from exc
    buf = io.StringIO(text, newline='')
    first = ''
    while line := buf.readline():
        if line.strip():
            first = line
            break
    if not first:
        return [], iter(())
    buf.seek(0)
    delimiter = max((',', ';', '\t'), key=first.count)
    reader = csv.reader(buf, delimiter=delimiter)
    header = [str(c).strip() for c in next(reader, [])]
    return header, reader


def _read_table_rows(name, raw, xlsx_reader=None):
    header, it = _iter_raw_rows(name, raw, xlsx_reader=xlsx_reader)
    if not header:
        return []
    out = []
    for values in it:
        row = {header[i]: (str(values[i]).strip() if i < len(values) and values[i] is not None else '')
               for i in range(len(header)) if header[i]}
        if any(row.values()):
            out.append(row)
    return out


def build_contract(raw, tenant, company, company_name, *, name='transactions.csv', xlsx_reader=None):
    """Return (json bytes, summary) for a transaction CSV/XLSX or native Agent 2 JSON package."""
    if name.lower().endswith('.json'):
        if len(raw) > MAX_BYTES:
            raise IntakeError('Tệp JSON vượt giới hạn 9 MB của Agent 2.')
        try:
            doc = json.loads(raw.decode('utf-8-sig'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IntakeError(f'Tệp JSON không hợp lệ: {exc}') from exc
        if not isinstance(doc, dict) or not isinstance(doc.get('transactions'), list):
            raise IntakeError('Tệp JSON không chứa danh sách transactions hợp lệ của Agent 2.')
        txs = doc['transactions']
        if not txs:
            raise IntakeError('Tệp JSON không có giao dịch nào.')
        dates = [str(t.get('effective_at') or t.get('posted_at') or '') for t in txs if isinstance(t, dict)]
        dates = [d for d in dates if d]
        first = min(dates) if dates else ''
        last = max(dates) if dates else ''
        return raw, dict(rows=len(txs), skipped=0, first=first, last=last,
                         vendors=len(doc.get('vendors') or []), employees=len(doc.get('employees') or []),
                         native_json=True)

    header, row_iter = _iter_raw_rows(name, raw, xlsx_reader=xlsx_reader)
    if not header:
        raise IntakeError('Tệp giao dịch không có dòng nào.')
    if 'transaction_id' in [str(h).strip() for h in header] and 'approver_id' in [str(h).strip() for h in header]:
        # Full A2 export: keep every column and build the rule snapshot the investigation queue runs on.
        try:
            from . import agent2_rule_source as rule_source
        except ImportError:
            import agent2_rule_source as rule_source
        keys = [str(h).strip() for h in header]
        rows = [dict(zip(keys, values)) for values in row_iter if values and any(str(v).strip() for v in values if v is not None)]
        try:
            body, summary = rule_source.build(rows, tenant, company, company_name)
        except (ValueError, TypeError) as exc:
            raise IntakeError(f'Tệp giao dịch không hợp lệ: {exc}') from exc
        if len(body) > MAX_BYTES:
            raise IntakeError('Tệp sau khi chuyển đổi vượt 9 MB; chia nhỏ theo kỳ rồi nạp lại.')
        return body, summary
    col_idx = {}
    for idx, col in enumerate(header):
        key = col.strip()
        if key and key not in col_idx:
            col_idx[key] = idx
            low = key.lower()
            if low not in col_idx:
                col_idx[low] = idx

    def cell(values, col_name):
        i = col_idx.get(col_name)
        if i is None or i >= len(values) or values[i] is None:
            return ''
        return values[i]

    transactions, vendors, employees, seen_tx, skipped, total_rows = [], {}, {}, {}, 0, 0
    first = last = earliest_stamp = None
    for values in row_iter:
        if not values or not any(str(v).strip() for v in values if v is not None):
            continue
        total_rows += 1
        kind = KIND.get(str(cell(values, 'txn_type')).strip())
        if kind is None or str(cell(values, 'payment_channel')).strip() != 'bank':
            skipped += 1
            continue
        rid = str(cell(values, 'transaction_id')).strip()
        if not rid:
            raise IntakeError(f'Thiếu transaction_id tại dòng {total_rows + 1}.')
        posted = _iso_timestamp(cell(values, 'posted_at'))
        observed = _iso_timestamp(cell(values, 'approved_at') or cell(values, 'created_at') or posted)
        raw_amount = cell(values, 'amount_vnd')
        try:
            amount_vnd = Decimal_or_int(raw_amount)
        except (ValueError, TypeError, InvalidOperation) as exc:
            raise IntakeError(f'Số tiền không hợp lệ tại giao dịch {rid}: {raw_amount}') from exc
        if kind in ('payment', 'payroll') and amount_vnd < 0:
            amount_vnd = -amount_vnd
        elif kind == 'receipt' and amount_vnd < 0:
            raise IntakeError(f'Khoản thu qua ngân hàng không được có số tiền âm tại giao dịch {rid}: {raw_amount}')
        desc = str(cell(values, 'business_purpose') or cell(values, 'accounting_purpose') or kind).strip()[:2000]
        item = _base(tenant, company, rid, observed, posted)
        item.update(amount_vnd=amount_vnd, currency='VND', kind=kind, description=desc, payment_channel='bank')
        vendor = str(cell(values, 'vendor_id')).strip()
        employee = str(cell(values, 'employee_id')).strip()
        creator = str(cell(values, 'creator_id')).strip()
        if vendor:
            vendors[vendor] = True
            item['vendor_ref'] = {'record_id': vendor, 'revision': 1}
        if employee:
            employees[employee] = True
            item['employee_ref'] = {'record_id': employee, 'revision': 1}
        if creator:
            employees[creator] = True
            item['created_by_ref'] = {'record_id': creator, 'revision': 1}
        if rid in seen_tx:
            if seen_tx[rid] != item:
                raise IntakeError(f'Mã giao dịch {rid} bị trùng nhưng nội dung khác nhau.')
            continue
        seen_tx[rid] = item
        transactions.append(item)
        first = posted if first is None or posted < first else first
        last = posted if last is None or posted > last else last
        for ts in (posted, observed):
            if ts and (earliest_stamp is None or ts < earliest_stamp):
                earliest_stamp = ts
        if 1 + len(transactions) + len(vendors) + len(employees) > MAX_RECORDS:
            raise IntakeError('Tệp vượt giới hạn 50.000 bản ghi của Agent 2; chia nhỏ theo kỳ rồi nạp lại.')
    if total_rows == 0:
        raise IntakeError('Tệp giao dịch không có dòng nào.')
    if not transactions:
        raise IntakeError('Không có dòng chuyển tiền qua ngân hàng nào trong tệp giao dịch.')
    stamp = earliest_stamp or first
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
                      employees=len(employees), native_json=False)


def Decimal_or_int(val):
    """Parse VND transaction amounts accurately using shared domestic VND money() rules."""
    if val is None or isinstance(val, bool) or (isinstance(val, str) and not val.strip()):
        raise ValueError('Thiếu số tiền VND')
    return int(bank_intake.money(val))


def _headers(token, extra=None):
    head = {'Authorization': 'Bearer ' + token}
    head.update(extra or {})
    return head


def preview(call, agent_url, token, tenant, company, company_name, name, raw, *, xlsx_reader=None):
    """Upload and preview. `call(method, url, body, headers, timeout)` is the portal's own HTTP helper."""
    body, summary = build_contract(raw, tenant, company, company_name, name=name, xlsx_reader=xlsx_reader)
    base = f'/api/v1/companies/{quote(company)}/'
    key = 'portal-' + sha256(body).hexdigest()[:40]
    upload_name = name if name.lower().endswith('.json') else (name.rsplit('.', 1)[0] + '.json')
    st, draft = call('POST', agent_url(base + 'imports/upload'), body,
                     _headers(token, {'Content-Type': 'application/octet-stream', 'X-File-Name': quote(upload_name),
                                      'Idempotency-Key': key}), 600)
    if st not in (200, 201):
        if _is_committed(draft):
            raise AlreadyCommitted('Agent 2 đã lưu snapshot cho đúng nội dung này trước đó; không ghi đè.')
        raise IntakeError(_message(draft, st))
    st, prev = call('POST', agent_url(base + 'imports/' + draft['import_id'] + '/preview'), {'expected_revision': draft['revision']},
                    _headers(token), 600)
    if st not in (200, 201):
        if _is_committed(prev):
            raise AlreadyCommitted('Agent 2 đã lưu snapshot cho đúng nội dung này trước đó; không ghi đè.')
        raise IntakeError(_message(prev, st))
    if isinstance(prev, dict) and prev.get('status') == 'rejected':
        if _is_committed(prev):
            raise AlreadyCommitted('Agent 2 đã lưu snapshot cho đúng nội dung này trước đó; không ghi đè.')
        errs = prev.get('errors') or []
        details = [f'{e.get("path") or "$"}: {e.get("message", "")}' for e in errs[:5] if isinstance(e, dict)]
        first_msg = errs[0].get('message') if errs and isinstance(errs[0], dict) else 'Tệp bị từ chối khi kiểm tra cấu trúc Agent 2.'
        raise IntakeError(first_msg, details=details)
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
        errs = res.get('errors')
        if isinstance(errs, list) and errs and isinstance(errs[0], dict) and errs[0].get('message'):
            return str(errs[0]['message'])[:400]
        text = res.get('error') or res.get('message') or res.get('detail')
        if isinstance(text, dict):
            text = text.get('message') or json.dumps(text, ensure_ascii=False)[:300]
        if text:
            return str(text)[:400]
    return f'Agent 2 trả lỗi {status}.'


def new_key():
    return uuid.uuid4().hex
