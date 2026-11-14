"""Connect full 35-rule source profile (`agent2-rule-snapshot/1.0.0`) to verified HE circuits.

Priority 1 (Slice 1): connect `P1` (both row-level and simultaneous timestamp
batches) from `native-rule-source/1.0.0` to the existing bounded Concrete `p1`
circuit without altering retained logic, trimming >4 rows, or pre-summing
amounts in plaintext to dodge circuit bounds.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from itertools import groupby

from . import inputs as p
from . import circuits as c
from sme_fraud.import_files import canonical, digest, fail
from sme_fraud.native_rule_node import REQUIRED, _gaps, validate_bundle
from sme_fraud.p1_timing import unavailable_fields as p1_unavailable_fields
from sme_fraud.rule_snapshot import CONTRACT, validate as validate_rule_snapshot
from sme_fraud.rules import invoice_payment_key
from sme_fraud.snapshot_features import utc


DOMAIN_LIMIT_MIN = -(2**63)
DOMAIN_LIMIT_MAX = (2**63) - 1


def _in_signed_int64(value: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and DOMAIN_LIMIT_MIN <= value <= DOMAIN_LIMIT_MAX


def _p1_source_gap_reasons(data: dict, scope) -> list[dict]:
    """Collect snapshot-wide P1 gaps matching `native_rule_node` + `source_guards`."""
    source = data['source']
    tables = source['tables']
    candidates = set(data['candidate_transaction_ids'])
    gaps = list(_gaps(source, 'P1'))
    for tx in tables.get('transactions', []):
        if tx.get('transaction_id') not in candidates:
            continue
        if tx.get('txn_type') == 'vendor_payment':
            inv = tx.get('invoice_number')
            if not isinstance(inv, str) or not inv.strip():
                gaps.append(
                    dict(
                        table='transactions',
                        record_id=tx['transaction_id'],
                        field='invoice_number',
                        reason='invoice_identity_not_provided',
                    )
                )
    return gaps


def _build_p1_payment_request(
    *,
    role: str,
    prior_rows: list[dict],
    current_rows: list[dict],
    gross: int,
    group_mode: bool,
    extra: dict | None = None,
) -> tuple[dict | None, str | None]:
    """Pack raw payment inputs into `p1` contract or fail closed with an explicit reason."""
    if len(prior_rows) > 4 or len(current_rows) > 4:
        return None, 'he_p1_source_limit'
    if not group_mode and prior_rows and all(int(r['amount_vnd']) <= 0 for r in prior_rows):
        # Concrete `p1` requires at least one strictly positive prior payment for `previous=1`,
        # whereas `rules.py:557` treats any non-empty `previous_invoice` as having prior rows.
        return None, 'he_p1_nonpositive_prior_unsupported'

    prior_amounts = [int(r['amount_vnd']) for r in prior_rows]
    current_amounts = [int(r['amount_vnd']) for r in current_rows]
    if not _in_signed_int64(gross) or gross <= 0:
        return None, 'he_p1_domain_limit'
    if any(not _in_signed_int64(v) for v in (*prior_amounts, *current_amounts)):
        return None, 'he_p1_domain_limit'

    try:
        values = p.payment(
            prior_amounts,
            current_amounts,
            [gross],
            ['payment' for _ in prior_amounts],
            tolerance=1,
            group=group_mode,
        )
    except p.InputUnavailable as exc:
        return None, str(exc)

    request = dict(
        profile='rules',
        rule_id='P1',
        role=role,
        values=[v.tolist() if hasattr(v, 'tolist') else v for v in values],
        source_refs=dict(
            prior=[
                dict(
                    record_type='transaction',
                    transaction_id=r['transaction_id'],
                    posted_at=r['posted_at'],
                    observed_at=r['observed_at'],
                    amount_vnd=int(r['amount_vnd']),
                )
                for r in prior_rows
            ],
            current=[
                dict(
                    record_type='transaction',
                    transaction_id=r['transaction_id'],
                    posted_at=r['posted_at'],
                    observed_at=r['observed_at'],
                    amount_vnd=int(r['amount_vnd']),
                )
                for r in current_rows
            ],
            invoice_gross_vnd=gross,
        ),
    )
    if extra:
        request.update(extra)
    return request, None


def plan_p1_from_rule_snapshot(data: dict, scope) -> dict:
    """Build deterministic Concrete `p1` evaluation requests for an `agent2-rule-snapshot/1.0.0` payload.

    No plaintext pre-summing or row slicing occurs here. Every obligation whose
    history, clock, coverage, or >4-row bound fails becomes `unavailable`.
    """
    if data.get('contract_version') != CONTRACT:
        fail(422, 'RULE_SNAPSHOT_INVALID', 'Yêu cầu profile agent2-rule-snapshot/1.0.0.', 'Xuất lại đúng profile.')
    report = validate_rule_snapshot(data, scope, committed=True)
    if report['status'] == 'rejected':
        fail(422, 'RULE_SNAPSHOT_INVALID', 'Snapshot nguồn luật không hợp lệ.', 'Kiểm tra lại schema và coverage.')

    source = data['source']
    as_of = source['as_of']
    checked = validate_bundle(source, scope)
    if checked['status'] != 'accepted':
        fail(422, 'NATIVE_RULE_SOURCE_INVALID', 'Bundle nguồn luật không hợp lệ.', 'Sửa lỗi validation trước khi chạy HE.')

    tables = source['tables']
    visible_txs = [
        deepcopy(r)
        for r in tables.get('transactions', [])
        if r.get('observed_at', '') <= as_of and r.get('posted_at', '') <= as_of
    ]
    visible_by_id = {r['transaction_id']: r for r in visible_txs}

    has_vendor_payment = any(t.get('txn_type') == 'vendor_payment' for t in visible_txs)
    rule_gaps = _p1_source_gap_reasons(data, scope) if has_vendor_payment else []

    invoice_payments: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    invoice_batches: dict[tuple[str, str, str], list[dict]] = defaultdict(list)

    per_tx_plan: dict[str, dict] = {}
    candidate_ids = list(data['candidate_transaction_ids'])
    candidate_set = set(candidate_ids)

    visible_txs.sort(key=lambda r: r['posted_at'])
    for now, batch_iter in groupby(visible_txs, key=lambda r: r['posted_at']):
        batch = list(batch_iter)
        # Pre-index eligible simultaneous same-timestamp vendor payments for batch_controls equivalence
        same_ts_by_key: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
        for r in batch:
            k = invoice_payment_key(r)
            if k is not None and not p1_unavailable_fields(r, now):
                same_ts_by_key[k].append(r)

        batch_group_cache: dict[tuple[str, str, str], dict] = {}
        for k, group_rows in sorted(same_ts_by_key.items()):
            if len(group_rows) < 2:
                continue
            history_rows = list(invoice_batches[k])
            blocked_history = [r for r in history_rows if p1_unavailable_fields(r, now)]
            if blocked_history:
                batch_group_cache[k] = dict(
                    available=False,
                    status='unavailable',
                    reason='invoice_history_not_available_at_cutoff',
                    request=None,
                )
                continue
            pool = [*history_rows, *group_rows]
            gross_values = sorted({int(r['invoice_gross_vnd']) for r in pool})
            if len(gross_values) != 1 or gross_values[0] <= 0:
                batch_group_cache[k] = dict(
                    available=False,
                    status='unavailable',
                    reason='simultaneous_invoice_gross_gap',
                    request=None,
                )
                continue
            req, err = _build_p1_payment_request(
                role='simultaneous_group',
                prior_rows=history_rows,
                current_rows=group_rows,
                gross=gross_values[0],
                group_mode=True,
                extra=dict(
                    group_scope=dict(
                        company_id=k[0],
                        vendor_id=k[1],
                        invoice_number_norm=k[2],
                        posted_at=now,
                        transaction_ids=sorted(r['transaction_id'] for r in group_rows),
                    )
                ),
            )
            if err is not None:
                batch_group_cache[k] = dict(available=False, status='unavailable', reason=err, request=None)
            else:
                batch_group_cache[k] = dict(available=True, status='ready', reason=None, request=req)

        for row in batch:
            tid = row['transaction_id']
            if tid in candidate_set:
                if not has_vendor_payment or row.get('txn_type') != 'vendor_payment':
                    per_tx_plan[tid] = dict(
                        record_id=tid,
                        transaction_id=tid,
                        txn_type=row.get('txn_type'),
                        posted_at=row.get('posted_at'),
                        observed_at=row.get('observed_at'),
                        applicable=False,
                        available=False,
                        status='not_applicable',
                        reason='rule_not_applicable_to_source_kinds',
                        requests=[],
                    )
                elif rule_gaps:
                    per_tx_plan[tid] = dict(
                        record_id=tid,
                        transaction_id=tid,
                        txn_type=row.get('txn_type'),
                        posted_at=row.get('posted_at'),
                        observed_at=row.get('observed_at'),
                        applicable=True,
                        available=False,
                        status='unavailable',
                        reason=rule_gaps[0].get('reason', 'rule_sources_unavailable'),
                        gaps=deepcopy(rule_gaps),
                        requests=[],
                    )
                else:
                    financial = int(row.get('is_financial_entry', 0)) == 1
                    channel_ok = row.get('payment_channel') in {'bank', 'cash'}
                    if not financial or not channel_ok:
                        per_tx_plan[tid] = dict(
                            record_id=tid,
                            transaction_id=tid,
                            txn_type=row.get('txn_type'),
                            posted_at=row.get('posted_at'),
                            observed_at=row.get('observed_at'),
                            applicable=True,
                            available=True,
                            status='evaluated_no_hit',
                            reason=None,
                            requests=[],
                        )
                    else:
                        k = invoice_payment_key(row)
                        gross = int(row.get('invoice_gross_vnd') or 0)
                        prior_rows = list(invoice_payments.get(k, [])) if k is not None else []
                        unavailable = p1_unavailable_fields(row, now)
                        blocked_prior = [r for r in prior_rows if p1_unavailable_fields(r, now)]
                        group_entry = batch_group_cache.get(k) if k is not None else None

                        if unavailable or (gross > 0 and blocked_prior):
                            per_tx_plan[tid] = dict(
                                record_id=tid,
                                transaction_id=tid,
                                txn_type=row.get('txn_type'),
                                posted_at=row.get('posted_at'),
                                observed_at=row.get('observed_at'),
                                applicable=True,
                                available=False,
                                status='unavailable',
                                reason='invoice_not_available_at_cutoff' if unavailable else 'invoice_history_not_available_at_cutoff',
                                requests=[],
                            )
                        elif gross <= 0 or k is None:
                            per_tx_plan[tid] = dict(
                                record_id=tid,
                                transaction_id=tid,
                                txn_type=row.get('txn_type'),
                                posted_at=row.get('posted_at'),
                                observed_at=row.get('observed_at'),
                                applicable=True,
                                available=False,
                                status='unavailable',
                                reason='invoice_value_or_identity_unavailable',
                                requests=[],
                            )
                        elif group_entry is not None and not group_entry['available']:
                            per_tx_plan[tid] = dict(
                                record_id=tid,
                                transaction_id=tid,
                                txn_type=row.get('txn_type'),
                                posted_at=row.get('posted_at'),
                                observed_at=row.get('observed_at'),
                                applicable=True,
                                available=False,
                                status='unavailable',
                                reason=group_entry['reason'],
                                requests=[],
                            )
                        else:
                            row_req, row_err = _build_p1_payment_request(
                                role='row',
                                prior_rows=prior_rows,
                                current_rows=[row],
                                gross=gross,
                                group_mode=False,
                                extra=dict(invoice_number=row.get('invoice_number')),
                            )
                            if row_err is not None:
                                per_tx_plan[tid] = dict(
                                    record_id=tid,
                                    transaction_id=tid,
                                    txn_type=row.get('txn_type'),
                                    posted_at=row.get('posted_at'),
                                    observed_at=row.get('observed_at'),
                                    applicable=True,
                                    available=False,
                                    status='unavailable',
                                    reason=row_err,
                                    requests=[],
                                )
                            else:
                                reqs = [row_req]
                                if group_entry is not None and group_entry['request'] is not None:
                                    reqs.append(deepcopy(group_entry['request']))
                                per_tx_plan[tid] = dict(
                                    record_id=tid,
                                    transaction_id=tid,
                                    txn_type=row.get('txn_type'),
                                    posted_at=row.get('posted_at'),
                                    observed_at=row.get('observed_at'),
                                    applicable=True,
                                    available=True,
                                    status='ready',
                                    reason=None,
                                    requests=reqs,
                                )

        # Commit chronological invoice history ONLY AFTER closing the entire timestamp batch
        for row in batch:
            if row.get('txn_type') == 'vendor_payment':
                k = invoice_payment_key(row)
                if k is not None:
                    invoice_payments[k].append(row)
                    invoice_batches[k].append(row)

    # Handle candidate rows whose posted_at/observed_at exceed as_of
    ordered_rows = []
    for cid in candidate_ids:
        if cid in per_tx_plan:
            ordered_rows.append(per_tx_plan[cid])
        else:
            raw_tx = next((r for r in tables.get('transactions', []) if r.get('transaction_id') == cid), {})
            ordered_rows.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    txn_type=raw_tx.get('txn_type'),
                    posted_at=raw_tx.get('posted_at'),
                    observed_at=raw_tx.get('observed_at'),
                    applicable=raw_tx.get('txn_type') == 'vendor_payment',
                    available=False,
                    status='unavailable' if has_vendor_payment else 'not_applicable',
                    reason='transaction_not_known_at_cutoff' if has_vendor_payment else 'rule_not_applicable_to_source_kinds',
                    requests=[],
                )
            )

    return dict(
        version='he4-rule-snapshot-p1-plan/1.0.0',
        contract_version=CONTRACT,
        company_id=data['company_id'],
        tenant_id=data['tenant_id'],
        as_of=as_of,
        rule_id='P1',
        profile='rules',
        source_sha256=digest(canonical(source)),
        rows=ordered_rows,
    )


def prepare_p1_rule_snapshot(store, scope, snapshot_id: str, as_of: str, *, recheck=None) -> dict:
    """Load an immutable committed `agent2-rule-snapshot/1.0.0` bundle under `scope` and build its HE P1 plan."""
    from finance_input.json_io import loads

    manifest = store.get_snapshot(scope, snapshot_id, recheck)
    raw = store.get_snapshot(scope, snapshot_id, recheck, data=True)
    if digest(raw) != manifest['data_checksum']:
        fail(500, 'ARTIFACT_INTEGRITY', 'Checksum snapshot không khớp.', 'Đối chiếu kho nguồn.')
    data = loads(raw)
    if utc(as_of) != utc(data['source']['as_of']):
        fail(422, 'RULE_CUTOFF_MISMATCH', 'Mốc phân tích phải khớp phạm vi nguồn đã khóa.', 'Dùng đúng as_of trong nguồn.')
    if recheck is not None and recheck() != scope:
        fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền đã thay đổi.', 'Đăng nhập lại.')
    plan = plan_p1_from_rule_snapshot(data, scope)
    plan['snapshot'] = {k: manifest[k] for k in ('snapshot_id', 'company_id', 'checksum', 'data_checksum', 'contract_version')}
    return plan


def decode_p1_plan_results(plan: dict, decrypted_outputs: list[list[int]]) -> dict:
    """Decode decrypted Concrete `p1` outputs paired with `plan` requests into structured P1 outcomes."""
    idx = 0
    rows_out = []
    for entry in plan['rows']:
        reqs = entry.get('requests', [])
        count = len(reqs)
        outputs = decrypted_outputs[idx : idx + count]
        idx += count
        if len(outputs) != count:
            raise ValueError('decrypted output count mismatch for P1 plan')

        if entry['status'] == 'not_applicable':
            rows_out.append(
                dict(
                    transaction_id=entry['transaction_id'],
                    available=False,
                    status='not_applicable',
                    matched=None,
                    score=None,
                    reason=entry['reason'],
                    row_check=None,
                    simultaneous_checks=[],
                )
            )
            continue
        if not entry['available']:
            rows_out.append(
                dict(
                    transaction_id=entry['transaction_id'],
                    available=False,
                    status='unavailable',
                    matched=None,
                    score=None,
                    reason=entry['reason'],
                    row_check=None,
                    simultaneous_checks=[],
                )
            )
            continue

        if not reqs:
            # Eligible row_kind (`vendor_payment`) that is non-financial or outside bank/cash channel
            rows_out.append(
                dict(
                    transaction_id=entry['transaction_id'],
                    available=True,
                    status='evaluated_no_hit',
                    matched=False,
                    score=0,
                    reason=None,
                    row_check=None,
                    simultaneous_checks=[],
                )
            )
            continue

        row_check = None
        group_checks = []
        for req, raw_out in zip(reqs, outputs):
            decoded = p.decode_payment(raw_out)
            decoded['role'] = req['role']
            if req['role'] == 'row':
                decoded['invoice_number'] = req.get('invoice_number')
                row_check = decoded
            else:
                decoded['group_scope'] = req.get('group_scope')
                group_checks.append(decoded)

        row_hit = bool(row_check and row_check['matched'])
        rows_out.append(
            dict(
                transaction_id=entry['transaction_id'],
                available=True,
                status='evaluated_hit' if row_hit else 'evaluated_no_hit',
                matched=row_hit,
                score=20 if row_hit else 0,
                reason=None,
                row_check=row_check,
                simultaneous_checks=group_checks,
            )
        )

    if idx != len(decrypted_outputs):
        raise ValueError('unused decrypted outputs left over after decoding P1 plan')
    return dict(
        version='he4-rule-snapshot-p1-result/1.0.0',
        company_id=plan['company_id'],
        as_of=plan['as_of'],
        rule_id='P1',
        rows=rows_out,
    )

