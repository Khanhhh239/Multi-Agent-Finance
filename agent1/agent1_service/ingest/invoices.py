"""T0 invoice admission, cross-source reconciliation and as-of lifecycle view.

Only fully specified invoices enter the canonical table. ERP rows with fewer
fields must be completed from the export before admission; guessing VAT or a
seller identity from an unrelated record would defeat the quality gate.
"""
from __future__ import annotations

import re
from datetime import date
from itertools import groupby

import pandas as pd

from agent1.data.schema import REQUIRED, quality_gate
from .dates import local_dates, normalize_date_fields
from .money import SCALES, major, minor

BUSINESS_KEY = ('seller_mst', 'symbol', 'invoice_no')
LIFECYCLE = {'replacement', 'adjustment'}
TRANSPORT_FIELDS = {
    'id', 'source', 'sources', 'source_ids', 'source_versions', 'source_payloads',
    'source_lineage', 'source_file', 'source_row', 'source_sha256', 'revision',
    'available_on', 'known_at', 'known_at_time', 'ingested_on',
}


def _business_payload(row):
    """Source-specific facts, before XML/ERP merging or reference resolution."""
    payload = {k: v for k, v in row.items() if k not in TRANSPORT_FIELDS and v is not None}
    if row.get('due_date') and row.get('issue_date'):
        payload['term_days'] = (pd.Timestamp(row['due_date']) - pd.Timestamp(row['issue_date'])).days
    return payload


_ISO_DAY = re.compile(r'\d{4}-\d{2}-\d{2}')


def _date(value):
    if value is None:
        return None
    # A plain YYYY-MM-DD needs no pandas: building a Series per call made one preview of a 50,000-invoice store take minutes.
    if isinstance(value, str) and _ISO_DAY.fullmatch(value):
        try:
            day = date.fromisoformat(value)
        except ValueError:
            return None
        if 1700 <= day.year <= 2200:
            return day.isoformat()
    result = local_dates(pd.Series([value]), dayfirst=False).iloc[0]
    return None if pd.isna(result) else result.date().isoformat()


def _available_on(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('available_on phải là ngày YYYY-MM-DD')
    parsed = _date(value)
    if parsed != value:
        raise ValueError('available_on phải là ngày YYYY-MM-DD hợp lệ')
    return parsed


def validate_invoices(rows, *, source, today=None):
    """Normalize input and run the same quality gate for XML, ERP and JSON."""
    if not rows:
        return []
    required = set(REQUIRED) | {'invoice_id', 'customer_id'}
    prepared = []
    for index, row in enumerate(rows, 1):
        location = f'{row.get("source_file", "JSON")}: dòng {row.get("source_row", index)}'
        missing = sorted(k for k in required if k not in row or row[k] is None or str(row[k]).strip() == '')
        if missing:
            raise ValueError(f'{location}: hóa đơn thiếu trường chuẩn: {missing}')
        try:
            d = normalize_date_fields(row, required=('issue_date', 'available_on'))
            d['available_on'] = _available_on(d.get('available_on'))
            version = d.get('record_version', 1)
            if type(version) is not int or version < 1:
                raise ValueError('record_version phải là số nguyên dương')
            d['record_version'] = version
        except (ValueError, TypeError) as exc:
            raise ValueError(f'{location}: {exc}') from exc
        kind = d.get('adjustment_type') or None
        if kind not in (None, *LIFECYCLE):
            raise ValueError(f'{location}: loại hóa đơn điều chỉnh/thay thế không được hỗ trợ')
        d['currency'] = str(d['currency']).upper()
        if d['currency'] not in SCALES:
            raise ValueError(f'{location}: tiền tệ không hỗ trợ: {d["currency"]}')
        for col in ('amount_net', 'vat', 'amount_gross'):
            try:
                d[col + '_minor'] = minor(d[col], d['currency'])
            except (TypeError, ValueError) as exc:
                raise ValueError(f'{location}: {col}: {exc}') from exc
            d[col] = major(d[col + '_minor'], d['currency'])
        if abs(d['amount_net_minor'] + d['vat_minor'] - d['amount_gross_minor']) > (1000 if d['currency']=='VND' else 0):
            raise ValueError(f'{location}: tổng tiền không bằng tiền trước thuế cộng VAT')
        if kind == 'adjustment':
            signs = {1 if d[c+'_minor'] > 0 else -1 for c in ('amount_net', 'vat', 'amount_gross') if d[c+'_minor'] != 0}
            if len(signs) != 1 or d['amount_gross_minor'] == 0:
                raise ValueError(f'{location}: hóa đơn điều chỉnh cần chênh lệch có dấu nhất quán')
        elif d['amount_net_minor'] <= 0 or d['amount_gross_minor'] <= 0 or d['vat_minor'] < 0:
            raise ValueError(f'{location}: giá trị hóa đơn không hợp lệ')
        d['issue_date'] = _date(d['issue_date'])
        d['due_date'] = _date(d.get('due_date'))
        if d['due_date']:
            d['term_days'] = (pd.Timestamp(d['due_date']) - pd.Timestamp(d['issue_date'])).days
        if not d['issue_date']:
            raise ValueError(f'{location}: ngày lập hóa đơn không hợp lệ')
        if d['available_on'] < d['issue_date']:
            raise ValueError(f'{location}: available_on trước ngày lập hóa đơn')
        for col in ('invoice_id', 'customer_id', 'seller_mst', 'buyer_mst', 'symbol', 'invoice_no'):
            d[col] = str(d[col]).strip()
        d['adjustment_type'] = kind
        d['source'] = source
        d['sources'] = [source]
        d['source_ids'] = {source: d['invoice_id']}
        d['source_lineage'] = {source: {'file': d.get('source_file'),
                                        'row': d.get('source_row', index),
                                        'sha256': d.get('source_sha256')}}
        prepared.append(d)
    # The original gate expects positive amounts. For signed adjustment deltas,
    # inspect their magnitudes with the same rules and separately check the sign.
    gate_rows = []
    for d in prepared:
        checked = dict(d)
        for col in ('amount_net', 'vat', 'amount_gross'):
            amount = d[col + '_minor'] / (10 ** SCALES[d['currency']])
            checked[col] = abs(amount) if d['adjustment_type'] == 'adjustment' else amount
        gate_rows.append(checked)
    flags = quality_gate(pd.DataFrame(gate_rows), today=today)
    bad = flags[flags.any_error]
    if len(bad):
        index = int(bad.index[0])
        reasons = flags.columns[flags.iloc[index] & flags.columns.to_series().ne('any_error')].tolist()
        row = prepared[index]
        raise ValueError(f'{row.get("source_file", "JSON")}: dòng {row.get("source_row", index + 1)}: '
                         f'hóa đơn {row["invoice_id"]} không đạt T0: {reasons}')
    ids = [r['invoice_id'] for r in prepared]
    if len(ids) != len(set(ids)):
        raise ValueError('Trùng invoice_id trong lô nhập')
    return prepared


def _key(row):
    return tuple(row.get(c) for c in BUSINESS_KEY) if all(row.get(c) for c in BUSINESS_KEY) else None


def _same_date(left, right):
    return _date(left) == _date(right)


def _known_on(row):
    dates = [_date(row.get(field)) for field in ('available_on', 'known_at')]
    return max((value for value in dates if value is not None), default=None)


def _kind(row):
    value = row.get('adjustment_type')
    return None if value is None or pd.isna(value) else value


def _minor_of(row,col):
    if col+'_minor' in row:return row[col+'_minor']
    return minor(str(row[col]),row['currency'])


def _aliases(rows):
    aliases = {}
    for row in rows:
        canonical = row['invoice_id']
        for alias in (canonical, *row.get('source_ids', {}).values()):
            if alias in aliases and aliases[alias] != canonical:
                raise ValueError(f'Mã hóa đơn nguồn {alias} chỉ hai hóa đơn khác nhau')
            aliases[alias] = canonical
    return aliases


def reconcile_invoices(existing, incoming):
    """Return the complete canonical set and rows to upsert, without writing."""
    all_rows = {str(r['invoice_id']): dict(r) for r in existing}
    keys = {_key(r): str(r['invoice_id']) for r in existing if _key(r)}
    if len(all_rows) != len(existing) or len(keys) != sum(_key(r) is not None for r in existing):
        raise ValueError('Kho hóa đơn hiện có chứa khóa trùng; cần đối chiếu trước khi nhập tiếp')
    updates = []
    for row in incoming:
        row = dict(row)
        key = _key(row)
        by_id = all_rows.get(row['invoice_id'])
        by_key = all_rows.get(keys[key]) if key in keys else None
        if by_id is not None and by_key is not None and by_id['invoice_id'] != by_key['invoice_id']:
            raise ValueError('invoice_id và bộ MST/ký hiệu/số chỉ hai hóa đơn khác nhau')
        old = by_id or by_key
        if old is None:
            row['id'] = row['invoice_id']
            row['source_versions'] = {row['source']: row['record_version']}
            row['source_payloads'] = {row['source']: _business_payload(row)}
            row['revision'] = 1
            all_rows[row['invoice_id']] = row
            keys[key] = row['invoice_id']
            updates.append(row)
            continue
        if by_key is not None and by_id is None and {old.get('source'), row['source']} != {'xml', 'erp'}:
            raise ValueError('Trùng MST/ký hiệu/số với invoice_id khác')
        if _key(old) and key != _key(old):
            raise ValueError('Cùng invoice_id nhưng khác MST/ký hiệu/số hóa đơn')
        versions = old.get('source_versions', {old.get('source'): old.get('record_version', 1)})
        previous_version = versions.get(row['source'])
        if previous_version is not None and row['record_version'] < previous_version:
            raise ValueError('Phiên bản chứng từ đi lùi')
        same_source_revision = previous_version is not None and row['record_version'] > previous_version
        if previous_version == row['record_version'] and row['source'] in old.get('sources', [old.get('source')]):
            prior_payload = old.get('source_payloads', {}).get(row['source'])
            if prior_payload is None and len(versions) == 1:
                # A legacy single-source row can still be compared faithfully.
                prior_payload = _business_payload(normalize_date_fields(old))
            if prior_payload is not None and prior_payload == _business_payload(row):
                continue
            raise ValueError('Không xác nhận được nội dung giống nhau cho cùng nguồn và record_version; '
                             'cần tăng record_version khi sửa hóa đơn')
        if row['available_on'] < old.get('available_on', old['issue_date']):
            raise ValueError('Ngày hệ thống nhận của phiên bản đi lùi')
        if old.get('currency') != row['currency']:
            raise ValueError(f'Hóa đơn {row["invoice_id"]} khác tiền tệ giữa các nguồn')
        for col in ('amount_gross', 'amount_net', 'vat'):
            old_minor = _minor_of(old,col)
            if not (same_source_revision and len(versions) == 1) and old_minor != row[col+'_minor']:
                raise ValueError(f'Hóa đơn {row["invoice_id"]} lệch {col} giữa các nguồn')
        for col in ('issue_date', 'due_date'):
            if old.get(col) and row.get(col) and not (same_source_revision and len(versions) == 1) and not _same_date(old[col], row[col]):
                raise ValueError(f'Hóa đơn {row["invoice_id"]} lệch {col} giữa các nguồn')
        for col in ('buyer_mst', 'currency', 'adjustment_type'):
            if old.get(col) and row.get(col) and not (same_source_revision and len(versions) == 1) and old[col] != row[col]:
                raise ValueError(f'Hóa đơn {row["invoice_id"]} lệch {col} giữa các nguồn')
        merged = dict(old)
        # XML is authoritative for invoice fields; ERP contributes its customer
        # code and ledger outcome after all shared facts have been checked.
        if row['source'] == 'xml':
            merged.update(row)
            if 'erp' in old.get('sources', [old.get('source')]):
                merged['customer_id'] = old['customer_id']
                if not row.get('due_date'):
                    merged['due_date'] = old.get('due_date')
                if old.get('ledger_clear_date'):
                    merged['ledger_clear_date'] = old['ledger_clear_date']
        elif row['source'] == 'erp' and old.get('source') == 'xml':
            merged['customer_id'] = row['customer_id']
            if not old.get('due_date'):
                merged['due_date'] = row.get('due_date')
            if row.get('ledger_clear_date'):
                merged['ledger_clear_date'] = row['ledger_clear_date']
        else:
            merged.update({k: v for k, v in row.items() if k not in ('id', 'invoice_id', 'source', 'sources')})
        merged['invoice_id'] = old['invoice_id']
        merged['id'] = old['invoice_id']
        if merged.get('due_date'):
            merged['term_days'] = (pd.Timestamp(merged['due_date']) - pd.Timestamp(merged['issue_date'])).days
        merged['source'] = merged.get('source') or row['source']
        merged['sources'] = sorted(set(old.get('sources', [old.get('source', 'legacy')])) | {row['source']})
        merged['source_ids'] = {**old.get('source_ids', {}), row['source']: row['invoice_id']}
        merged['source_lineage'] = {**old.get('source_lineage', {}), **row['source_lineage']}
        merged['source_versions'] = {**versions, row['source']: row['record_version']}
        merged['source_payloads'] = {**old.get('source_payloads', {}), row['source']: _business_payload(row)}
        merged['revision'] = old.get('revision', 1) + 1
        merged['available_on'] = row['available_on']
        merged['ingested_on'] = row.get('ingested_on')
        all_rows[merged['invoice_id']] = merged
        updates.append(merged)
    return list(all_rows.values()), updates


def resolve_references(rows):
    """Resolve XML related invoice number to the canonical ID; reject ambiguity."""
    by_id = {r['invoice_id']: r for r in rows}
    aliases = _aliases(rows)
    related = {}
    for row in rows:
        key = (row.get('seller_mst'), row.get('symbol'), row.get('invoice_no'), _date(row.get('issue_date')))
        related.setdefault(key, []).append(row)
    for row in rows:
        kind = _kind(row)
        if kind not in LIFECYCLE:
            continue
        target_id = row.get('adjusts_invoice_id')
        if target_id in aliases:
            target_id = aliases[target_id]
            row['adjusts_invoice_id'] = target_id
        if not target_id:
            number = row.get('adjusts_invoice_no')
            symbol = row.get('adjusts_symbol')
            issued = row.get('adjusts_issue_date')
            matches = related.get((row.get('seller_mst'), symbol, number, _date(issued)), [])
            if len(matches) != 1:
                raise ValueError(f'Hóa đơn {row["invoice_id"]} không tìm được duy nhất hóa đơn liên quan')
            target_id = matches[0]['invoice_id']
            row['adjusts_invoice_id'] = target_id
        if target_id not in by_id or target_id == row['invoice_id']:
            raise ValueError(f'Hóa đơn {row["invoice_id"]} có tham chiếu không hợp lệ')
        target = by_id[target_id]
        if target.get('seller_mst') != row.get('seller_mst') or target.get('currency') != row.get('currency'):
            raise ValueError('Hóa đơn liên quan khác người bán hoặc tiền tệ')
        if _date(target['issue_date']) > _date(row['issue_date']):
            raise ValueError('Hóa đơn điều chỉnh/thay thế lập trước hóa đơn gốc')
    return rows


def validate_cancellations(existing, incoming, invoices):
    by_id = {r['invoice_id']: r for r in invoices}
    aliases = _aliases(invoices)
    seen = {r['event_id'] for r in existing}
    result = list(existing)
    for event in incoming:
        e = normalize_date_fields(event, required=('event_date', 'available_on'))
        if e.get('event_type') != 'cancel' or not e.get('event_id') or not e.get('invoice_id'):
            raise ValueError('Sự kiện hủy cần event_id, invoice_id và event_type=cancel')
        e['invoice_id'] = aliases.get(e['invoice_id'], e['invoice_id'])
        e['event_date'] = _date(e.get('event_date'))
        e['available_on'] = _available_on(e.get('available_on'))
        if e['available_on'] < e['event_date']:
            raise ValueError('Sự kiện hủy cần available_on không trước event_date')
        if not e['event_date'] or e['invoice_id'] not in by_id:
            raise ValueError('Ngày hoặc hóa đơn được hủy không hợp lệ')
        if e['event_id'] in seen:
            old = next(r for r in result if r['event_id'] == e['event_id'])
            ignored = {'id', 'ingested_on'}
            if ({k: v for k, v in old.items() if k not in ignored} !=
                    {k: v for k, v in e.items() if k not in ignored}):
                raise ValueError('Trùng event_id với nội dung khác')
            continue
        if e['event_date'] < _date(by_id[e['invoice_id']]['issue_date']):
            raise ValueError('Sự kiện hủy lập trước hóa đơn')
        e['id'] = e['event_id']
        result.append(e)
        seen.add(e['event_id'])
    return result


def effective_invoices(invoices, events=(), cutoff=None):
    """Apply replacements, signed adjustment deltas and cancellations as of cutoff."""
    limit = _date(cutoff) if cutoff is not None else None
    selected = {}
    for row in invoices:
        known = _known_on(row)
        if limit is not None and known is not None and known > limit:
            continue
        key = row['invoice_id']
        if key not in selected or row.get('revision', 1) > selected[key].get('revision', 1):
            selected[key] = dict(row)
    records = list(selected.values())
    events = [e for e in events if limit is None or _known_on(e) is None or _known_on(e) <= limit]
    if not records:
        return pd.DataFrame(records)
    if not any(_kind(r) for r in records) and not events:
        frame = pd.DataFrame(records)
        if cutoff is not None:
            frame = frame[pd.to_datetime(frame.issue_date) <= pd.Timestamp(cutoff)]
        return _model_frame(frame.reset_index(drop=True))
    timeline = [(str(_date(r['issue_date'])), r) for r in records]
    timeline += [(str(_date(e['event_date'])), e) for e in events]
    active = {}
    for date, group in groupby(sorted(timeline, key=lambda item: item[0]), key=lambda item: item[0]):
        if cutoff is not None and date > _date(cutoff):
            break
        today = [row for _, row in group]
        for row in today:
            if row.get('event_type') or _kind(row):
                continue
            active[row['invoice_id']] = dict(row)
        pending = [row for row in today if _kind(row)]
        while pending:
            ready = [row for row in pending if row.get('adjusts_invoice_id') in active]
            if not ready:
                raise ValueError('Chuỗi điều chỉnh/thay thế thiếu gốc hoặc tham chiếu vòng')
            for row in ready:
                target = row['adjusts_invoice_id']
                if target not in active:
                    raise ValueError(f'Hóa đơn liên quan đã hết hiệu lực: {target}')
                if _kind(row) == 'replacement':
                    del active[target]
                    active[row['invoice_id']] = dict(row)
                else:
                    adjusted = active[target]
                    for col in ('amount_net', 'vat', 'amount_gross'):
                        amount = _minor_of(adjusted,col)
                        delta = _minor_of(row,col)
                        adjusted[col+'_minor'] = amount + delta
                        adjusted[col] = major(adjusted[col+'_minor'],adjusted['currency'])
                    if adjusted['amount_gross_minor'] <= 0:
                        raise ValueError(f'Điều chỉnh làm công nợ không dương: {target}')
                pending.remove(row)
        for row in today:
            if row.get('event_type') != 'cancel':
                continue
            target = row['invoice_id']
            if target not in active:
                raise ValueError(f'Hủy hóa đơn không còn hiệu lực: {target}')
            del active[target]
    return _model_frame(pd.DataFrame(active.values()).reset_index(drop=True))


def _model_frame(frame):
    """Keep exact minor units in T0; convert only the model's numeric view."""
    for col in ('amount_net', 'vat', 'amount_gross'):
        if col in frame and col+'_minor' in frame:
            frame[col] = frame.apply(lambda row: row[col+'_minor'] / (10 ** SCALES[row['currency']]), axis=1)
    return frame
