"""Append-only scoped reviewer events. Legacy files remain untouched on first write."""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _load(ws):
    path = Path(ws) / 'decisions_v2.json'
    if path.exists():
        value = json.loads(path.read_text(encoding='utf-8'))
        if value.get('schema_version') != 2:
            raise ValueError('Phiên bản kho quyết định không được hỗ trợ')
        return value
    legacy = Path(ws) / 'decisions.json'
    rows = json.loads(legacy.read_text(encoding='utf-8')) if legacy.exists() else []
    events = []
    for n, row in enumerate(rows):
        # Preserve existing meaning, including invoice-wide legacy confirmations.
        scope = {'NOT_CLAIMED': 'deduction', 'PAYMENT_EVIDENCE_ATTACHED': 'payment'}.get(row['action'], 'legacy')
        events.append(dict(row, id='legacy-' + _hash([n, row])[:24], scope=scope,
                           subject=row['invoice_key'], legacy=True, supersedes=None))
    return dict(schema_version=2, events=events, requests={})


def history(ws):
    return _load(ws)['events']


def effective(ws):
    out = {}
    for event in history(ws):
        out.setdefault(event['subject'], {})[event['scope']] = event
    return out


def projection(ws):
    """Compatibility view for matching and historical callers; scopes are never collapsed on disk."""
    out = {}
    for key, scopes in effective(ws).items():
        selected = scopes.get('deduction') or scopes.get('payment') or scopes.get('legacy') or next(iter(scopes.values()))
        out[key] = dict(selected, _scopes=scopes)
    return out


def applicable(records, invoices, transactions):
    """A recorded confirmation cannot silently approve changed source evidence."""
    invs = {i.key: i for i in invoices}
    txns = {t.txn_id: __import__('dataclasses').asdict(t) for t in transactions}
    out = {}
    for subject, record in records.items():
        if '_scopes' not in record:
            out[subject] = record  # Legacy and explicit what-if records retain existing semantics.
            continue
        valid = {}
        for scope, event in record['_scopes'].items():
            if any(k not in invs or invs[k].source_sha256 != value for k, value in event.get('invoice_fingerprints', {}).items()):
                continue
            if any(k not in txns or _hash(txns[k]) != value for k, value in event.get('txn_fingerprints', {}).items()):
                continue
            valid[scope] = event
        if valid:
            selected = valid.get('deduction') or valid.get('payment') or valid.get('legacy') or next(iter(valid.values()))
            out[subject] = dict(selected, _scopes=valid)
    return out


def etag(ws):
    return '"' + _hash(_load(ws)) + '"'


def request_hash(body):
    return _hash({k: v for k, v in body.items() if k not in ('request_id', 'report_revision')})


def retry(ws, body):
    previous = _load(ws)['requests'].get(body.get('request_id', ''))
    if previous:
        if previous['payload_hash'] != request_hash(body):
            raise HTTPException(409, 'Mã yêu cầu đã được dùng với nội dung khác.')
        return previous
    return None


def append(ws, body, events):
    """Caller holds the workspace write boundary and has validated every event before entering here."""
    journal = _load(ws)
    current = effective(ws)
    ids = []
    for record in events:
        previous = current.get(record['subject'], {}).get(record['scope'])
        event = dict(record, id=uuid.uuid4().hex, at=datetime.now(timezone.utc).isoformat(),
                     supersedes=previous['id'] if previous else None, legacy=False)
        journal['events'].append(event)
        current.setdefault(event['subject'], {})[event['scope']] = event
        ids.append(event['id'])
    receipt = dict(payload_hash=request_hash(body), event_ids=ids, decisions=len(events))
    journal['requests'][body['request_id']] = receipt
    target = Path(ws) / 'decisions_v2.json'
    tmp = target.with_suffix('.tmp')
    tmp.write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(target)
    return receipt


def validate(body, report, ws):
    """Produce the complete event batch or reject it without writing anything."""
    from pydantic import BaseModel, Field, ValidationError

    class Required(BaseModel):
        action: str
        evidence: str = Field(min_length=1, max_length=4000)
        by: str = Field(min_length=1, max_length=200)

    try:
        required = Required(**{k: body.get(k) for k in ('action', 'evidence', 'by')})
    except ValidationError:
        raise HTTPException(422, 'Cần hành động, bằng chứng và người duyệt hợp lệ.')
    action, evidence, by = required.action, required.evidence.strip(), required.by.strip()
    if not evidence or not by:
        raise HTTPException(422, 'Bằng chứng và người duyệt không được để trống.')
    invs = {i['key']: i for i in report['invoices']}
    findings = {i['finding_id']: i for i in report['items']}
    txns = {t['txn_id']: t for t in report['transactions']}
    keys = body.get('invoice_keys') if 'invoice_keys' in body else [body.get('invoice_key')]
    if not isinstance(keys, list) or any(not isinstance(k, str) for k in keys if k is not None):
        raise HTTPException(422, 'Danh sách hóa đơn không hợp lệ.')
    keys = list(dict.fromkeys(k for k in keys if k))
    ids = body.get('finding_ids') if 'finding_ids' in body else [body.get('finding_id')]
    if not isinstance(ids, list) or any(not isinstance(k, str) for k in ids if k is not None):
        raise HTTPException(422, 'Danh sách cảnh báo không hợp lệ.')
    ids = list(dict.fromkeys(k for k in ids if k))
    records = []
    common = dict(action=action, evidence=evidence, by=by)
    if action in ('NOT_CLAIMED', 'PAYMENT_EVIDENCE_ATTACHED'):
        if not keys or any(k not in invs or invs[k]['role'] != 'PURCHASE' for k in keys):
            raise HTTPException(422, 'Cần hóa đơn mua vào tồn tại trong doanh nghiệp hiện tại.')
        scope = 'deduction' if action == 'NOT_CLAIMED' else 'payment'
        tids = body.get('txn_ids') or []
        if not isinstance(tids, list) or any(not isinstance(t, str) for t in tids) or len(set(tids)) != len(tids):
            raise HTTPException(422, 'Danh sách giao dịch không hợp lệ.')
        if tids:
            from decimal import Decimal
            if len(keys) != 1 or any(t not in txns or txns[t]['direction'] != 'OUT' for t in tids):
                raise HTTPException(422, 'Chứng từ thanh toán phải là giao dịch chi của doanh nghiệp.')
            if abs(sum(Decimal(str(txns[t]['amount'])) for t in tids) - Decimal(str(invs[keys[0]]['gross']))) > 1:
                raise HTTPException(422, 'Số tiền giao dịch không khớp hóa đơn.')
            used = {t for m in report['matches'] if m['status'] == 'MATCHED' and keys[0] not in m['invoice_keys'] for t in m['txn_ids']}
            if used & set(tids):
                raise HTTPException(409, 'Giao dịch đã ghép cho hóa đơn khác.')
        for k in keys:
            records.append(dict(common, subject=k, scope=scope, invoice_key=k, txn_ids=tids))
    elif action == 'CONFIRMED_OK':
        if not ids or any(k not in findings or findings[k]['status'] != 'REVIEW' or not findings[k]['invoice_keys'] for k in ids):
            raise HTTPException(422, 'Cần chọn đúng cảnh báo chờ xem xét của hóa đơn.')
        for k in ids:
            records.append(dict(common, subject=k, scope='finding', finding_id=k, invoice_key=findings[k]['invoice_keys'][0]))
    elif action in ('CONFIRMED_NON_REVENUE', 'SALES_EVIDENCE_ATTACHED'):
        if len(ids) != 1 or ids[0] not in findings or not findings[ids[0]]['code'].startswith('R14'):
            raise HTTPException(422, 'Cần cảnh báo khoản thu R14 đang tồn tại.')
        item = findings[ids[0]]
        tids = item['txn_ids']
        if not tids or any(t not in txns for t in tids):
            raise HTTPException(422, 'Không tìm thấy giao dịch của cảnh báo.')
        if action == 'CONFIRMED_NON_REVENUE' and body.get('category') not in ('LOAN', 'INTERNAL_TRANSFER', 'CAPITAL', 'REFUND', 'OTHER'):
            raise HTTPException(422, 'Cần chọn loại khoản thu và ghi bằng chứng.')
        if action == 'SALES_EVIDENCE_ATTACHED' and (not keys or any(k not in invs or invs[k]['role'] != 'SALE' for k in keys)):
            raise HTTPException(422, 'Cần chọn hóa đơn bán ra đã nạp.')
        records.append(dict(common, subject=ids[0], scope='finding', finding_id=ids[0], txn_ids=tids,
                            category=body.get('category'), sales_invoice_keys=keys))
    elif action == 'REJECT_BANK_PROPOSAL':
        if len(keys) != 1 or keys[0] not in invs or body.get('txn_id') not in txns:
            raise HTTPException(422, 'Đề xuất không thuộc dữ liệu hiện tại.')
        records.append(dict(common, subject=body['txn_id'] + '|' + keys[0], scope='bank_rejection',
                            invoice_key=keys[0], txn_id=body['txn_id']))
    else:
        raise HTTPException(422, 'Hành động không được hỗ trợ.')
    for record in records:
        related = [record.get('invoice_key')] + record.get('sales_invoice_keys', [])
        record['invoice_fingerprints'] = {k: invs[k].get('source_sha256', '') for k in related if k in invs}
        record['txn_fingerprints'] = {k: _hash(txns[k]) for k in record.get('txn_ids', []) if k in txns}
    return records
