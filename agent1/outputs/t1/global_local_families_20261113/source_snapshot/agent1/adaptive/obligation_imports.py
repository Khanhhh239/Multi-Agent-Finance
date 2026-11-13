"""Business identity and a reviewable import plan for individual T5 due items."""

from copy import deepcopy
import re


IDENTITY_FIELDS = ('obligation_ref', 'payment_period', 'installment_no')
PAYLOAD_FIELDS = ('date', 'amount', 'category', 'status', 'forecast_date', 'source',
                  'verified', 'refund_approved_at', 'business_day',
                  'replaces_expense_id', 'currency', *IDENTITY_FIELDS)


def normalize_identity(row):
    row = dict(row)
    supplied = [str(row[field]).strip() if row.get(field) is not None else '' for field in IDENTITY_FIELDS]
    if not any(supplied):
        return row
    if not all(supplied):
        raise ValueError('Cần đủ mã hợp đồng/khoản cố định, kỳ thanh toán và đợt đến hạn')
    reference, period, installment = supplied
    period = period.upper()
    if not re.fullmatch(r'[1-9]\d{3}(?:-(?:0[1-9]|1[0-2]|Q[1-4]))?', period):
        raise ValueError('Kỳ thanh toán dùng YYYY-MM, YYYY-Q1 đến YYYY-Q4 hoặc YYYY; không suy từ ngày trả')
    if not re.fullmatch(r'[1-9]\d*', installment):
        raise ValueError('Đợt đến hạn phải là số nguyên dương; không phải số lần thực trả')
    row.update(zip(IDENTITY_FIELDS, (reference, period, installment)))
    return row


def identity_key(row):
    row = normalize_identity(row)
    if not row.get('obligation_ref'):
        return None
    return (row['obligation_ref'].casefold(), row['category'].strip().casefold(),
            row['payment_period'], row['installment_no'])


def identity_status(row):
    return 'identified' if identity_key(row) else 'missing'


def _content(row):
    values = {key: row[key] for key in PAYLOAD_FIELDS if row.get(key) not in (None, '')}
    values.update(status=row.get('status', 'open'), currency=row.get('currency', 'VND'),
                  business_day=row.get('business_day', 'none'))
    if identity_key(row):
        values.update(zip(IDENTITY_FIELDS, (row['obligation_ref'].casefold(),
                                            row['payment_period'], row['installment_no'])))
    return values


def validate_identities(data):
    """Also protect source corrections, which do not go through CSV merging."""
    keys, identities = {}, {}
    for row in [*data.get('record_history', {}).get('outflows', []), *data.get('outflows', [])]:
        if row.get('_deleted'):
            continue
        key = identity_key(row)
        identifier = row['expense_id']
        if key and identifier in identities and identities[identifier] != key:
            raise ValueError('Mã lần đến hạn T5 đã dùng cho hợp đồng, loại, kỳ hoặc đợt khác: ' + identifier)
        if not key and identifier in identities:
            raise ValueError('Không được bỏ định danh nghiệp vụ T5 đã ghi nhận: ' + identifier)
        if key:
            identities[identifier] = key
    for row in data.get('outflows', []):
        key = identity_key(row)
        if key in keys and key is not None:
            raise ValueError('Trùng hợp đồng/khoản cố định, loại, kỳ và đợt đến hạn T5: ' + keys[key])
        if key:
            keys[key] = row['expense_id']


def plan_obligation_import(data, incoming, row_numbers=None):
    """Resolve business matches to stable IDs without altering data or history.

    Alternate input IDs are shown in the preview, not installed as new payment
    identities. Bank allocations must keep using the retained expense_id.
    """
    existing = {row['expense_id']: normalize_identity(row) for row in data.get('outflows', [])}
    by_key = {identity_key(row): identifier for identifier, row in existing.items() if identity_key(row)}
    seen, records, results, errors, warnings = {}, [], [], [], []
    counts = dict(new=0, changed=0, unchanged=0, review=0)
    for index, raw in enumerate(incoming):
        number = row_numbers[index] if row_numbers is not None else index + 2
        result = dict(row=number, input_expense_id=raw['expense_id'], expense_id=raw['expense_id'])
        try:
            row = normalize_identity(raw)
            result['identity_status'] = identity_status(row)
            old = existing.get(row['expense_id'])
            key = identity_key(row)
            if old and identity_key(old) and not key:
                row.update({field: old[field] for field in IDENTITY_FIELDS})
                key = identity_key(row)
            if old and identity_key(old) and key != identity_key(old):
                raise ValueError('Mã đã thuộc hợp đồng, loại, kỳ hoặc đợt khác; dùng mã mới cho lần đến hạn mới')
            matched = by_key.get(key) if key else None
            if matched and old and matched != row['expense_id']:
                raise ValueError('Định danh nghiệp vụ đã thuộc mã ' + matched + '; đối chiếu hai khoản trước khi sửa')
            if matched:
                old = existing[matched]
                row['expense_id'] = matched
                # Retain the spelling of the established business reference.
                row['obligation_ref'] = old['obligation_ref']
            result.update(expense_id=row['expense_id'], identity_status=identity_status(row))
            identifier = row['expense_id']
            if identifier in seen and _content(seen[identifier]) != _content(row):
                raise ValueError('Cùng lần đến hạn xuất hiện nhiều nội dung trong file; chỉ giữ một bản đã đối chiếu')
            if old and _content(old) == _content(row):
                classification, row = 'unchanged', deepcopy(old)
            else:
                classification = 'changed' if old else 'new'
                if old and row['known_at'] <= old['known_at']:
                    raise ValueError('Bản sửa cần ngày ghi nhận mới hơn bản trước; không ghi đè lịch sử')
            result.update(classification=classification, before=deepcopy(old), after=deepcopy(row))
            messages = []
            if raw['expense_id'] != identifier:
                messages.append('Giữ mã ' + identifier + '; dùng mã này khi nạp thanh toán và tham chiếu thay thế')
            if not key:
                messages.append('Chưa đủ định danh nghiệp vụ; bổ sung theo cùng mã để kiểm tra nạp trùng giữa các mã')
                warnings.append('Lịch T5 chưa đủ định danh: bổ sung mã hợp đồng/khoản cố định, kỳ và đợt theo cùng mã lần đến hạn. Không tự suy kỳ từ ngày trả.')
            result['message'] = '. '.join(messages)
            counts[classification] += 1
            records.append(row)
            seen[identifier] = row
            existing[identifier] = row
            if key:
                by_key[key] = identifier
        except ValueError as exc:
            result.update(classification='review', message=str(exc), after=deepcopy(raw))
            counts['review'] += 1
            errors.append(dict(row=number, column='expense_id', message=str(exc)))
        results.append(result)
    missing = sum(identity_key(row) is None for row in existing.values())
    if missing:
        warnings.append(f'Còn {missing} khoản T5 chưa đủ định danh nghiệp vụ; các khoản này chỉ chống trùng theo mã lần đến hạn. Bổ sung định danh theo cùng mã trước khi đổi mã nạp.')
    return dict(records=records, rows=results, counts=counts, errors=errors,
                warnings=list(dict.fromkeys(warnings)))
