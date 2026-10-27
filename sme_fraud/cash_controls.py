"""Cash purchase screening; a review flag is not a VAT deduction decision."""
from datetime import datetime, timedelta, timezone
from .cash_limit_priority import POLICY as LIMIT_PRIORITY_POLICY, LEGACY_POLICY as LEGACY_LIMIT_PRIORITY, limit_priority


VN = timezone(timedelta(hours=7))
CASH_POLICY = 'vn_vat_v1'
REVIEW_POLICY = 'evidence_v2'
LEGACY_REVIEW_POLICY = 'legacy_v1'
PURCHASE_TYPES = frozenset({'vendor_payment', 'cash_expense', 'rent', 'selling_expense',
                            'stock_purchase', 'material_purchase', 'equipment_purchase', 'tools_purchase'})
VAT_CHANGE = '2025-07-01'
VAT_OLD_SOURCE = 'TT219/2013/TT-BTC_D15_amended'
VAT_NEW_SOURCE = 'ND181/2025/ND-CP_D26'


def local_day(timestamp):
    value = datetime.fromisoformat(timestamp)
    if value.utcoffset() is None:
        raise ValueError('Cash controls require timezone-aware timestamps')
    return value.astimezone(VN).date().isoformat()


def vat_policy(day):
    return ((20_000_000, VAT_OLD_SOURCE) if day < VAT_CHANGE else (5_000_000, VAT_NEW_SOURCE))


def _cash_payment_evidence(row, config):
    """Screen a cash purchase against its invoice and any internal cash limit.

    Use inclusive VAT boundaries, gross invoice value for partial payments, and
    Vietnam dates. Cross-regime invoices require a tax review. Missing invoice
    evidence never becomes an assertion that VAT was claimed or disallowed.
    """
    if (config['cash_payment_policy'] == 'disabled' or not int(row['is_financial_entry'])
            or row['payment_channel'] != 'cash' or row['txn_type'] not in PURCHASE_TYPES):
        return None
    # Imported refund/reversal rows may retain the original expense type.
    # A known debit to cash with no cash credit is a receipt, not a new purchase.
    if str(row.get('debit_account', '')).startswith('111') and not str(row.get('credit_account', '')).startswith('111'):
        return None
    amount = int(row['amount_vnd'])
    if amount <= 0:
        return None
    if row.get('currency', 'VND') != 'VND':
        return dict(evidence_status='information_gap', missing_fields=['verified_vnd_amount'],
                    amount=amount, currency=row.get('currency'), payment_at=row['posted_at'])
    paid_day = local_day(row['posted_at'])
    invoice_at = row.get('invoice_issued_at', '')
    future_invoice = bool(invoice_at and datetime.fromisoformat(invoice_at) > datetime.fromisoformat(row['posted_at']))
    invoice_day = local_day(invoice_at) if invoice_at and not future_invoice else paid_day
    invoice_limit, invoice_source = vat_policy(invoice_day)
    payment_limit, payment_source = vat_policy(paid_day)
    # A transition is flagged for review, rather than silently granting the old
    # exemption or presenting a full legal decision about transitional contracts.
    threshold = min(invoice_limit, payment_limit)
    gross = 0 if future_invoice else int(row.get('invoice_gross_vnd') or 0)
    internal = config['cash_limit_vnd_by_company'].get(row['company_id'])
    reasons = []
    if amount >= threshold:
        reasons.append('cash_amount_at_or_above_vat_threshold')
    if gross >= threshold and (row.get('invoice_id') or row.get('invoice_number')):
        reasons.append('cash_payment_on_invoice_at_or_above_vat_threshold')
    if internal is not None and amount > internal:
        reasons.append('internal_cash_limit_exceeded')
    if not reasons:
        if future_invoice:
            return dict(evidence_status='information_gap', missing_fields=['invoice_issued_at_not_in_future'],
                        cash_amount_vnd=amount, payment_at=row['posted_at'])
        return None
    complete = bool(invoice_at and (row.get('invoice_id') or row.get('invoice_number')) and gross > 0)
    return dict(evidence_status='cash_purchase_invalid_invoice_date' if future_invoice else
                'transition_review_required' if invoice_limit != payment_limit else
                'cash_purchase_review' if complete else 'cash_purchase_missing_invoice',
                cash_amount_vnd=amount, invoice_gross_vnd=gross,
                invoice_id=row.get('invoice_id', ''), invoice_number=row.get('invoice_number', ''),
                invoice_issued_at=invoice_at, payment_at=row['posted_at'],
                vat_non_cash_threshold_vnd=threshold, threshold_inclusive=True,
                invoice_policy=invoice_source, payment_policy=payment_source,
                internal_cash_limit_vnd=internal, reasons=reasons,
                policy=CASH_POLICY, requires_tax_review=True,
                conclusion='Rà soát chứng từ thanh toán/điều kiện VAT; chưa kết luận gian lận hoặc loại khấu trừ.')


def validate_review_config(config):
    if config.get('cash_limit_priority_policy', LIMIT_PRIORITY_POLICY) not in {LIMIT_PRIORITY_POLICY, LEGACY_LIMIT_PRIORITY}:
        raise ValueError('Invalid cash limit priority policy')
    if config['cash_review_policy'] not in {REVIEW_POLICY, LEGACY_REVIEW_POLICY}:
        raise ValueError('Invalid cash evidence review policy')
    evidence = config['cash_limit_evidence_by_company']
    if not isinstance(evidence, dict):
        raise ValueError('Cash limit evidence must be company-scoped')
    for company, record in evidence.items():
        required = {'limit_vnd', 'source_ref', 'verified_by', 'verified_at', 'effective_from'}
        if (company not in config['cash_limit_vnd_by_company'] or not isinstance(record, dict)
                or required-set(record) or set(record)-required-{'effective_to'}):
            raise ValueError('Cash limit evidence requires a configured company, source and validity')
        if (type(record['limit_vnd']) is not int or record['limit_vnd'] != config['cash_limit_vnd_by_company'][company]
                or any(not isinstance(record[k], str) or not record[k].strip() for k in ('source_ref', 'verified_by'))):
            raise ValueError('Cash limit evidence must bind the exact limit and verification source')
        for field in ('verified_at', 'effective_from', 'effective_to'):
            if field == 'effective_to' and not record.get(field):
                continue
            try:
                local_day(record[field])
            except (TypeError, ValueError) as error:
                raise ValueError('Cash limit evidence dates must be timezone-aware ISO timestamps') from error
        if record.get('effective_to') and datetime.fromisoformat(record['effective_to']) <= datetime.fromisoformat(record['effective_from']):
            raise ValueError('Cash limit validity must be a nonempty interval')


def cash_payment_check(row, config):
    proof = _cash_payment_evidence(row, config)
    if proof is None or config.get('cash_review_policy', REVIEW_POLICY) == LEGACY_REVIEW_POLICY:
        return proof
    paid_at = datetime.fromisoformat(row['posted_at'])
    internal = config['cash_limit_vnd_by_company'].get(row['company_id'])
    record = config.get('cash_limit_evidence_by_company', {}).get(row['company_id'])
    exceeded = 'internal_cash_limit_exceeded' in proof.get('reasons', [])
    internal_status = 'not_configured' if internal is None else 'not_exceeded'
    if internal is not None and 'verified_vnd_amount' in proof.get('missing_fields', []):
        internal_status = 'not_evaluable'
    if exceeded:
        internal_status = ('unverified_limit' if not record else
            'not_known_at_payment' if datetime.fromisoformat(record['verified_at']) > paid_at else
            'outside_effective_period' if not (datetime.fromisoformat(record['effective_from']) <= paid_at and
                (not record.get('effective_to') or paid_at < datetime.fromisoformat(record['effective_to']))) else 'verified_breach')
    missing = list(proof.get('missing_fields', []))
    if proof.get('evidence_status') != 'information_gap':
        if not (row.get('invoice_id') or row.get('invoice_number')):
            missing.append('invoice_identity')
        if not row.get('invoice_issued_at'):
            missing.append('invoice_issued_at')
        elif datetime.fromisoformat(row['invoice_issued_at']) > paid_at:
            missing.append('invoice_issued_at_not_in_future')
        if int(row.get('invoice_gross_vnd') or 0) <= 0:
            missing.append('invoice_gross_vnd')
    vat_reasons = [r for r in proof.get('reasons', []) if r != 'internal_cash_limit_exceeded']
    invoice_ready = not any(field.startswith('invoice_') for field in missing)
    if internal_status == 'verified_breach':
        category, points, priority = 'verified_internal_breach', 14, 'cao'
        if config.get('cash_limit_priority_policy', LIMIT_PRIORITY_POLICY) == LIMIT_PRIORITY_POLICY:
            tier = limit_priority(proof['cash_amount_vnd'], internal)
            priority = tier['tier_priority']
            # The independent VAT/document branch keeps its medium handling floor.
            # Its eight points are not stacked on top of the breach's 14 points.
            vat_floor = bool(vat_reasons and invoice_ready and proof.get('evidence_status') != 'information_gap')
            if vat_floor and priority == 'thap':
                priority = 'trung_binh'
            proof.update(limit_priority=tier, vat_document_priority_floor='trung_binh' if vat_floor else '')
        summary = 'Chi tiền mặt vượt hạn mức nội bộ có nguồn và xác minh tại thời điểm chi'
        action = 'Đối chiếu quyết định hạn mức, phê duyệt ngoại lệ và chứng từ chi.'
    elif vat_reasons and invoice_ready and proof.get('evidence_status') != 'information_gap':
        category, points, priority = 'vat_document_review', 8, 'trung_binh'
        summary = 'Khoản chi tiền mặt có thông tin hóa đơn cần đối chiếu chứng từ thanh toán/VAT'
        action = 'Đối chiếu hóa đơn gốc, chứng từ thanh toán và điều kiện áp dụng; ghi rõ giải trình.'
    else:
        category, points, priority = 'information_request', 0, 'thap'
        if exceeded and internal_status != 'verified_breach':
            missing.append('internal_limit_verification')
        summary = 'Cần bổ sung bằng chứng cho khoản chi tiền mặt'
        action = 'Bổ sung các trường còn thiếu và nguồn xác minh, sau đó chạy lại đối chiếu.'
    proof.update(review_policy=REVIEW_POLICY, review_category=category, review_points=points,
                 review_priority=priority, review_route='evidence_request' if not points else 'operational_review',
                 internal_limit_status=internal_status,
                 internal_limit_evidence=dict(record) if record and datetime.fromisoformat(record['verified_at']) <= paid_at else None,
                 missing_fields=sorted(set(missing)), summary_vi=summary, next_action_vi=action,
                 requires_tax_review=bool(vat_reasons), conclusion=summary+'; chưa kết luận gian lận hoặc loại khấu trừ.')
    return proof
