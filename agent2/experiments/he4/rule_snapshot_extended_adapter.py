"""Extended Concrete FHE adapters for `agent2-rule-snapshot/1.0.0` in `BundleHE`.

Extends encrypted evaluation on existing compiled Concrete circuits without any
plaintext numerical comparisons or clear fallback:
  1. `A6` (Thanh toán làm tròn vượt hóa đơn gốc) via `rules` (`p1` 128-bit nibble
     `amount > gross + 1` + `excess_vnd`) and `c3` (`(gross % 1000 != 0)` &
     `(amount % 1000 == 0)`).
  2. `C2` (Tự duyệt vượt quyền được cấp) via `c3` (encrypted `self_approved`,
     64-bit authority band matching, specificity tie-breaking, ambiguity check,
     `self_approval_allowed`, and `amount > self_approval_limit_vnd`).
  3. `statistics` (`RobustZ` 2-column `abs/clip/sum` on `rule-snapshot-point-in-time/1.0.0`
     via `build-statistics-v1`, mapped to empirical midrank at enterprise node).
"""
from __future__ import annotations

from copy import deepcopy
import io
from pathlib import Path
import pickle

from finance_input.json_io import loads
import joblib
import numpy as np

from . import c3_circuit as c3m
from . import inputs as p
from sme_fraud.authority_policy import ApprovalAuthority
from sme_fraud.identity import normalize
from sme_fraud.import_files import ImportFailure, canonical, digest, fail
from sme_fraud.method_adapters import ARTIFACT_VERSION, _versions
from sme_fraud.method_jobs import validate_config
from sme_fraud.method_preprocess import VERSION as PREPROCESS, row_values, validate_preprocess
from sme_fraud.method_store import MethodStore
from sme_fraud.native_rule_node import _gaps, validate_bundle
from sme_fraud.rule_snapshot import CONTRACT, validate as validate_rule_snapshot
from sme_fraud.rule_snapshot_features import (
    build_from_rule_snapshot,
    feature_contract as rule_feature_contract,
)
from sme_fraud.score_statistics import empirical_rank
from sme_fraud.snapshot_features import utc
from sme_fraud.unsupervised_statistics import RobustZ

DOMAIN_LIMIT_MIN = -(2**63)
DOMAIN_LIMIT_MAX = (2**63) - 1


def _in_signed_int64(value: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and DOMAIN_LIMIT_MIN <= value <= DOMAIN_LIMIT_MAX


def _metadata_self_approval_candidates(
    authority: ApprovalAuthority,
    row: dict,
    actor: str,
    employee: dict,
    at: str,
) -> list[tuple[tuple[int, int, int, int, int], dict]]:
    """Select approved `approval_authorities` rows for `self_approve` using metadata ONLY (never amount_vnd)."""
    cid = row['company_id']
    candidates = []
    for record in authority.authorities.records_at(cid, at):
        if not authority._approved(record, cid, at, actor):
            continue
        if record['action'] not in {'self_approve', 'all'}:
            continue
        if record['txn_type'] not in {row['txn_type'], '*'}:
            continue
        if record['subject_employee_id']:
            if record['subject_employee_id'] != actor:
                continue
        elif record['subject_role'] != employee.get('role'):
            continue
        if record['department'] and record['department'] != row.get('department'):
            continue
        if record['project_id'] and record['project_id'] != row.get('project_id'):
            continue
        if not record['effective_from'][:10] <= at[:10] <= record['effective_to'][:10]:
            continue
        if record['authority_type'] == 'delegation' and (
            not record['delegated_by_id'] or record['delegated_by_id'] == actor
        ):
            continue
        specificity = (
            int(bool(record['subject_employee_id'])),
            int(record['action'] != 'all'),
            int(record['txn_type'] != '*'),
            int(bool(record['department'])),
            int(bool(record['project_id'])),
        )
        candidates.append((specificity, record))
    candidates.sort(key=lambda item: (item[0], item[1]['authority_id']))
    return candidates


def plan_a6_from_rule_snapshot(data: dict, scope) -> dict:
    """Plan encrypted `A6` evaluation (`rules` + `c3` circuits; zero plaintext amount comparisons)."""
    if data.get('contract_version') != CONTRACT:
        fail(422, 'RULE_SNAPSHOT_INVALID', 'Yêu cầu profile agent2-rule-snapshot/1.0.0.', 'Xuất lại đúng profile.')
    report = validate_rule_snapshot(data, scope, committed=True)
    if report['status'] == 'rejected':
        fail(422, 'RULE_SNAPSHOT_INVALID', 'Snapshot nguồn luật không hợp lệ.', 'Kiểm tra lại schema và coverage.')

    source = data['source']
    as_of = source['as_of']
    checked = validate_bundle(source, scope)
    if checked['status'] != 'accepted':
        fail(422, 'NATIVE_RULE_SOURCE_INVALID', 'Bundle nguồn luật không hợp lệ.', 'Sửa lỗi trước khi chạy HE.')

    tables = source['tables']
    visible_txs = [
        deepcopy(r)
        for r in tables.get('transactions', [])
        if r.get('observed_at', '') <= as_of and r.get('posted_at', '') <= as_of
    ]
    by_id = {r['transaction_id']: r for r in visible_txs}
    has_vendor_payment = any(t.get('txn_type') == 'vendor_payment' for t in visible_txs)
    source_gaps = list(_gaps(source, 'A6')) if has_vendor_payment else []

    rows_plan = []
    for cid in data['candidate_transaction_ids']:
        tx = by_id.get(cid)
        if tx is None:
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason='transaction_not_known_at_cutoff',
                    requests=[],
                )
            )
            continue

        if not has_vendor_payment or tx.get('txn_type') != 'vendor_payment':
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='not_applicable',
                    reason='rule_not_applicable_to_source_kinds',
                    requests=[],
                )
            )
            continue

        if source_gaps:
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason=source_gaps[0].get('reason', 'rule_sources_unavailable'),
                    gaps=deepcopy(source_gaps),
                    requests=[],
                )
            )
            continue

        amount = int(tx['amount_vnd'])
        gross = int(tx.get('invoice_gross_vnd') or 0)
        if amount < 0:
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason='signed_amount_policy_not_supported',
                    gaps=[dict(table='transactions', record_id=cid, reason='signed_amount_policy_not_supported')],
                    requests=[],
                )
            )
            continue
        if gross <= 0:
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason='invoice_value_unavailable',
                    gaps=[dict(table='transactions', record_id=cid, reason='invoice_value_unavailable')],
                    requests=[],
                )
            )
            continue
        if not _in_signed_int64(amount) or not _in_signed_int64(gross):
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason='he_a6_domain_limit',
                    requests=[],
                )
            )
            continue

        now = tx['posted_at']
        recipient = normalize(tx.get('recipient_account', ''), 'bank_account')
        invoice_at_cutoff = all(
            not tx.get(field) or tx[field] <= now
            for field in ('invoice_issued_at', 'invoice_observed_at')
        )
        if not recipient or not invoice_at_cutoff:
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=True,
                    status='ready',
                    eval_mode='metadata_no_hit',
                    reason=None,
                    requests=[],
                )
            )
            continue

        try:
            p1_vals = p.payment([], [amount], [gross], [], tolerance=1, group=True)
            created_w = c3m.encode_word64(1)
            approved_w = c3m.encode_word64(int(gross % 1000))
            amount_rem_w = c3m.encode_word64(int(amount % 1000))
            thr_w = c3m.encode_word64(0)
            rule_min = np.zeros((c3m.MAX_AUTHORITIES, c3m.C3_WORD_DIGITS), dtype=np.int64)
            rule_max = np.zeros((c3m.MAX_AUTHORITIES, c3m.C3_WORD_DIGITS), dtype=np.int64)
            rule_rank = np.array([1, 0, 0, 0], dtype=np.int64)
            rule_is_high = np.array([1, 0, 0, 0], dtype=np.int64)
            rule_outcome = np.array([1, 0, 0, 0], dtype=np.int64)
            c3_vals = [
                created_w.tolist(),
                approved_w.tolist(),
                amount_rem_w.tolist(),
                thr_w.tolist(),
                0,
                rule_min.tolist(),
                rule_max.tolist(),
                rule_rank.tolist(),
                rule_is_high.tolist(),
                rule_outcome.tolist(),
            ]
        except (p.InputUnavailable, TypeError, ValueError):
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason='he_a6_domain_limit',
                    requests=[],
                )
            )
            continue

        rows_plan.append(
            dict(
                record_id=cid,
                transaction_id=cid,
                available=True,
                status='ready',
                eval_mode='fhe',
                reason=None,
                payment_vnd=amount,
                invoice_gross_vnd=gross,
                requests=[
                    dict(
                        profile='rules',
                        rule_id='A6',
                        role='a6_over_cap',
                        values=[v.tolist() if hasattr(v, 'tolist') else v for v in p1_vals],
                    ),
                    dict(
                        profile='c3',
                        rule_id='A6',
                        role='a6_rounding',
                        values=c3_vals,
                    ),
                ],
            )
        )

    return dict(
        version='he4-rule-snapshot-a6-plan/1.0.0',
        rule_id='A6',
        rows=rows_plan,
    )


def decode_a6_plan_results(plan: dict, outputs: list) -> dict:
    """Decode encrypted `A6` evaluation results."""
    cursor = 0
    rows_out = []
    for entry in plan['rows']:
        tid = entry['transaction_id']
        if not entry['available']:
            rows_out.append(
                dict(
                    transaction_id=tid,
                    rule_id='A6',
                    available=False,
                    status=entry['status'],
                    matched=None,
                    score=None,
                    hard_trigger=False,
                    reason=entry['reason'],
                    gaps=deepcopy(entry.get('gaps', [])),
                )
            )
            continue
        if entry.get('eval_mode') == 'metadata_no_hit':
            rows_out.append(
                dict(
                    transaction_id=tid,
                    rule_id='A6',
                    available=True,
                    status='evaluated_no_hit',
                    matched=False,
                    score=0,
                    hard_trigger=False,
                    reason=None,
                    details=dict(basis='missing_recipient_or_invoice_after_payment'),
                )
            )
            continue
        dec_p1 = p.decode_payment(outputs[cursor])
        dec_c3 = c3m.decode_c3(outputs[cursor + 1])
        cursor += 2
        matched = bool(dec_p1['matched'] and dec_c3['matched'])
        rows_out.append(
            dict(
                transaction_id=tid,
                rule_id='A6',
                available=True,
                status='evaluated_hit' if matched else 'evaluated_no_hit',
                matched=matched,
                score=8 if matched else 0,
                hard_trigger=False,
                reason=None,
                details=dict(
                    payment_vnd=entry['payment_vnd'],
                    invoice_gross_vnd=entry['invoice_gross_vnd'],
                    difference_vnd=int(dec_p1['excess_vnd']) if matched else None,
                    over_cap=bool(dec_p1['matched']),
                    unrounded_invoice=bool(dec_c3['fast_60s']),
                    rounded_payment=bool(dec_c3['explicit_high']),
                ),
            )
        )
    if cursor != len(outputs):
        raise ValueError('A6 output count mismatch')
    return dict(rows=rows_out)


def plan_c2_from_rule_snapshot(
    data: dict,
    scope,
    *,
    enforce_source_guards: bool = True,
) -> dict:
    """Plan encrypted `C2` evaluation (`c3` circuit; zero plaintext amount comparisons)."""
    if data.get('contract_version') != CONTRACT:
        fail(422, 'RULE_SNAPSHOT_INVALID', 'Yêu cầu profile agent2-rule-snapshot/1.0.0.', 'Xuất lại đúng profile.')
    report = validate_rule_snapshot(data, scope, committed=True)
    if report['status'] == 'rejected':
        fail(422, 'RULE_SNAPSHOT_INVALID', 'Snapshot nguồn luật không hợp lệ.', 'Kiểm tra lại schema và coverage.')

    source = data['source']
    as_of = source['as_of']
    checked = validate_bundle(source, scope)
    if checked['status'] != 'accepted':
        fail(422, 'NATIVE_RULE_SOURCE_INVALID', 'Bundle nguồn luật không hợp lệ.', 'Sửa lỗi trước khi chạy HE.')

    tables = source['tables']
    visible_tables = {
        name: [
            deepcopy(r)
            for r in tables.get(name, [])
            if r.get('observed_at', '') <= as_of and (name != 'transactions' or r.get('posted_at', '') <= as_of)
        ]
        for name in tables
    }
    by_id = {r['transaction_id']: r for r in visible_tables.get('transactions', [])}
    authority = ApprovalAuthority(visible_tables)

    source_gaps = list(_gaps(source, 'C2'))
    if enforce_source_guards:
        for table_name in ('approval_authorities', 'approval_authority_coverage'):
            if not visible_tables.get(table_name):
                source_gaps.append(dict(table=table_name, reason='approved_authority_source_missing'))

    rows_plan = []
    for cid in data['candidate_transaction_ids']:
        tx = by_id.get(cid)
        if tx is None:
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason='transaction_not_known_at_cutoff',
                    requests=[],
                )
            )
            continue

        if source_gaps:
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason=source_gaps[0].get('reason', 'rule_sources_unavailable'),
                    gaps=deepcopy(source_gaps),
                    requests=[],
                )
            )
            continue

        amount = int(tx['amount_vnd'])
        if amount < 0:
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason='signed_amount_policy_not_supported',
                    gaps=[dict(table='transactions', record_id=cid, reason='signed_amount_policy_not_supported')],
                    requests=[],
                )
            )
            continue

        at = tx.get('approved_at', '')
        maker = tx.get('creator_id', '')
        approver = tx.get('approver_id', '')
        company_id = tx['company_id']
        coverage = authority.covered(tx, 'self_approve', at)
        if coverage is not None and coverage.get('_ambiguous'):
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason='authority_not_covered_or_ambiguous_at_action',
                    requests=[],
                )
            )
            continue

        employee = authority.employee_at(company_id, maker, at)
        if not employee or employee.get('company_id') != company_id:
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason='authority_not_covered_or_ambiguous_at_action',
                    requests=[],
                )
            )
            continue
        if coverage is None:
            mode_legacy = 1
            candidates = []
        else:
            mode_legacy = 0
            candidates = _metadata_self_approval_candidates(authority, tx, maker, employee, at)

        if len(candidates) > c3m.MAX_AUTHORITIES:
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason='he_c2_authority_limit',
                    requests=[],
                )
            )
            continue

        try:
            self_approved_flag = 1 if (maker and maker == approver) else c3m.LIMIT_DT_US
            created_w = c3m.encode_word64(0)
            approved_w = c3m.encode_word64(self_approved_flag)
            amount_w = c3m.encode_word64(amount)
            self_lim = (
                int(employee['self_approval_limit_vnd'])
                if (employee and employee.get('self_approval_limit_vnd') is not None)
                else None
            )
            thr_val = (
                c3m.INT64_MIN
                if self_lim is None
                else (c3m.INT64_MAX if self_lim >= c3m.INT64_MAX else self_lim + 1)
            )
            thr_w = c3m.encode_word64(thr_val)

            rule_min = np.zeros((c3m.MAX_AUTHORITIES, c3m.C3_WORD_DIGITS), dtype=np.int64)
            rule_max = np.zeros((c3m.MAX_AUTHORITIES, c3m.C3_WORD_DIGITS), dtype=np.int64)
            rule_rank = np.zeros(c3m.MAX_AUTHORITIES, dtype=np.int64)
            rule_is_high = np.zeros(c3m.MAX_AUTHORITIES, dtype=np.int64)
            rule_outcome = np.zeros(c3m.MAX_AUTHORITIES, dtype=np.int64)

            distinct_specs = sorted({spec for spec, _ in candidates})
            spec_rank = {spec: idx + 1 for idx, spec in enumerate(distinct_specs)}
            distinct_outcomes = sorted(
                {(int(r['self_approval_allowed'] == 1), str(r['authority_level'])) for _, r in candidates}
            )
            outcome_code = {pair: idx + 1 for idx, pair in enumerate(distinct_outcomes)}

            for i, (spec, rec) in enumerate(candidates):
                rule_min[i] = c3m.encode_word64(int(rec['min_amount_vnd']))
                rule_max[i] = c3m.encode_word64(int(rec['max_amount_vnd']))
                rule_rank[i] = spec_rank[spec]
                rule_is_high[i] = int(rec['self_approval_allowed'] == 1)
                rule_outcome[i] = outcome_code[(int(rec['self_approval_allowed'] == 1), str(rec['authority_level']))]
        except (KeyError, TypeError, ValueError):
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason='he_c2_domain_limit',
                    requests=[],
                )
            )
            continue

        values = [
            created_w.tolist(),
            approved_w.tolist(),
            amount_w.tolist(),
            thr_w.tolist(),
            int(mode_legacy),
            rule_min.tolist(),
            rule_max.tolist(),
            rule_rank.tolist(),
            rule_is_high.tolist(),
            rule_outcome.tolist(),
        ]
        rows_plan.append(
            dict(
                record_id=cid,
                transaction_id=cid,
                available=True,
                status='ready',
                reason=None,
                mode_legacy=mode_legacy,
                self_approval_limit_vnd=self_lim,
                coverage_id=coverage['coverage_id'] if coverage else None,
                requests=[dict(profile='c3', rule_id='C2', role='c2_self_approval', values=values)],
            )
        )

    return dict(
        version='he4-rule-snapshot-c2-plan/1.0.0',
        rule_id='C2',
        rows=rows_plan,
    )


def decode_c2_plan_results(plan: dict, outputs: list) -> dict:
    """Decode encrypted `C2` evaluation results."""
    cursor = 0
    rows_out = []
    for entry in plan['rows']:
        tid = entry['transaction_id']
        if not entry['available']:
            rows_out.append(
                dict(
                    transaction_id=tid,
                    rule_id='C2',
                    available=False,
                    status=entry['status'],
                    matched=None,
                    score=None,
                    hard_trigger=False,
                    reason=entry['reason'],
                    gaps=deepcopy(entry.get('gaps', [])),
                )
            )
            continue
        dec = c3m.decode_c3(outputs[cursor])
        cursor += 1
        self_approved = bool(dec['fast_60s'])
        if entry['mode_legacy'] == 0:
            permitted = bool(dec['has_matching_authority'] and not dec['ambiguous_authority'] and dec['explicit_high'])
        else:
            permitted = not bool(dec['legacy_high'])
        matched = bool(self_approved and not permitted)
        suppressed = (
            (
                'Trong quyền tự duyệt/ủy quyền đã được phê duyệt'
                if entry['mode_legacy'] == 0
                else 'Trong hạn mức tự duyệt đã biết'
            )
            if (self_approved and permitted)
            else ''
        )
        rows_out.append(
            dict(
                transaction_id=tid,
                rule_id='C2',
                available=True,
                status='evaluated_hit' if matched else 'evaluated_no_hit',
                matched=matched,
                score=20 if matched else 0,
                hard_trigger=matched,
                suppressed_reason=suppressed or None,
                reason=None,
                details=dict(
                    self_approved=self_approved,
                    permitted=permitted,
                    mode='legacy_fallback' if entry['mode_legacy'] == 1 else 'authority_matrix',
                    has_matching_authority=bool(dec['has_matching_authority']),
                    ambiguous_authority=bool(dec['ambiguous_authority']),
                    coverage_id=entry.get('coverage_id'),
                ),
            )
        )
    if cursor != len(outputs):
        raise ValueError('C2 output count mismatch')
    return dict(rows=rows_out)


def load_rule_snapshot_statistics(model_db, scope, artifact_id: str | None, recheck=None):
    """Load and verify a 2-column `RobustZ` artifact bound to `rule-snapshot-point-in-time/1.0.0`."""
    if artifact_id is None or model_db is None:
        return None, 'artifact_not_pinned'
    check = recheck or (lambda: scope)
    contract = rule_feature_contract()
    try:
        store = MethodStore(model_db, read_only=True)
        artifact = store.get_artifact(scope, artifact_id, check)
        m = loads(artifact.manifest)
        if (
            artifact.artifact_id != 'mth_' + digest(artifact.manifest)
            or m['payload_sha256'] != digest(artifact.payload)
            or m['model_version'] != 'mdl_' + digest(artifact.payload)
        ):
            raise ValueError('artifact digest')
        if (m['tenant_id'], m['company_id']) != (scope.tenant_id, next(iter(scope.company_ids))):
            raise ValueError('artifact scope')
        if (
            m['method_id'] != 'robust_z'
            or m['version'] != ARTIFACT_VERSION
            or m['feature_contract'] != contract
            or m['feature_contract_fingerprint'] != contract['fingerprint']
            or m['versions'] != _versions()
            or m['preprocess_version'] != PREPROCESS
        ):
            return None, 'artifact_incompatible'
        pre = m['preprocess']
        validate_preprocess(dict(contract=contract), pre)
        if pre['selected_columns'] != m['selected_columns'] or digest(canonical(pre)) != m['preprocess_sha256']:
            return None, 'artifact_incompatible'
        if len(pre['output_columns']) != 2:
            return None, 'he_statistics_column_count_unsupported'
        context = m['fit_context']
        config = validate_config(context['config'])
        from sme_fraud import method_jobs

        if (
            config['method_id'] != 'robust_z'
            or context['job_implementation_sha256'] != digest(Path(method_jobs.__file__).read_bytes())
        ):
            return None, 'artifact_incompatible'
        if (
            not utc(m['train_end']) < utc(m['reference_start']) <= utc(m['reference_end']) < utc(config['evaluation_start'])
            or m['history_rows'] < config['minimum_history']
            or m['reference_rows'] < 1
        ):
            raise ValueError('fit periods')
        if config['evaluation_mode'] == 'prospective' and utc(context['created_at']) >= utc(config['evaluation_start']):
            raise ValueError('publication period')
        with store._transaction(scope, check) as conn:
            job = store._job(conn, scope, context['job_id'])
            request = loads(job['request_json'])
            if (
                job['status'] != 'succeeded'
                or job['artifact_id'] != artifact_id
                or job['request_hash'] != context['request_hash']
                or request['config'] != config
                or request['versions'] != m['versions']
                or request['feature_contract'] != m['feature_contract']
                or request['snapshot'] != m['history_binding']
                or request['snapshot'] != m['reference_binding']
                or request['job_implementation_sha256'] != context['job_implementation_sha256']
            ):
                raise ValueError('fit receipt')
        if check() != scope:
            fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền đã thay đổi.', 'Mở lại từ Portal.')
        model, reference = joblib.load(io.BytesIO(artifact.payload))
        if (
            type(model) is not RobustZ
            or not reference
            or len(reference) != m['reference_rows']
            or sorted(reference) != list(reference)
            or not np.isfinite(reference).all()
            or digest(canonical(reference)) != m['reference_version']
        ):
            raise ValueError('model/reference')
        if (
            any(np.asarray(v).shape != (2,) or not np.isfinite(v).all() for v in (model.med_, model.scale_))
            or np.any(model.scale_ <= 0)
        ):
            raise ValueError('model domain')
        return dict(manifest=m, model=model, reference=[float(x) for x in reference], artifact_id=artifact_id), None
    except ImportFailure as error:
        if error.status in (403, 409):
            raise
        return None, 'artifact_missing' if error.status == 404 else 'artifact_invalid'
    except (ValueError, KeyError, TypeError, EOFError, OSError, pickle.UnpicklingError, AttributeError, ImportError):
        return None, 'artifact_invalid'


def plan_statistics_from_rule_snapshot(
    store,
    scope,
    snapshot_id: str,
    as_of: str,
    candidate_ids: list[str],
    *,
    model_db=None,
    statistics_artifact: str | None = None,
    recheck=None,
) -> dict:
    """Plan encrypted 2-column `RobustZ` (`statistics` circuit) on a 35-rule snapshot."""
    check = recheck or (lambda: scope)
    loaded, load_reason = load_rule_snapshot_statistics(model_db, scope, statistics_artifact, check)
    frame = None
    by_record: dict[str, int] = {}
    if loaded is not None:
        try:
            frame = build_from_rule_snapshot(store, scope, snapshot_id, as_of, check)
            by_record = {r['record_id']: idx for idx, r in enumerate(frame['rows'])}
        except ImportFailure as error:
            if error.status in (403, 409):
                raise
            loaded = None
            load_reason = error.code

    rows_plan = []
    for cid in candidate_ids:
        if loaded is None:
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason=load_reason,
                    requests=[],
                )
            )
            continue
        idx = by_record.get(cid)
        if idx is None:
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason='transaction_not_known_at_cutoff',
                    requests=[],
                )
            )
            continue
        m = loaded['manifest']
        row = frame['rows'][idx]
        context = m['fit_context']
        cutoff = min(utc(row['event_at']), utc(row['as_of']))
        if utc(m['reference_end']) >= cutoff:
            rows_plan.append(
                dict(record_id=cid, transaction_id=cid, available=False, status='unavailable', reason='artifact_from_future', requests=[])
            )
            continue
        if digest(canonical(row['record_id'])) in m['fitted_identity_hashes']:
            rows_plan.append(
                dict(record_id=cid, transaction_id=cid, available=False, status='unavailable', reason='artifact_training_overlap', requests=[])
            )
            continue
        if utc(context['evaluation_start']) > cutoff:
            rows_plan.append(
                dict(record_id=cid, transaction_id=cid, available=False, status='unavailable', reason='before_evaluation_period', requests=[])
            )
            continue
        if context['evaluation_mode'] == 'prospective' and utc(context['created_at']) >= cutoff:
            rows_plan.append(
                dict(record_id=cid, transaction_id=cid, available=False, status='unavailable', reason='artifact_not_yet_created', requests=[])
            )
            continue
        values, missing, unavail_reason = row_values(frame, frame['features'][idx], m['preprocess'])
        if unavail_reason:
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason=unavail_reason,
                    missing_features=list(missing),
                    requests=[],
                )
            )
            continue
        try:
            scale_eff = np.asarray(loaded['model'].scale_, dtype=float).copy()
            active_mask = getattr(loaded['model'], 'active_mask_', None)
            if active_mask is not None:
                scale_eff = np.where(np.asarray(active_mask, dtype=bool), scale_eff, 1e9)
            args = p.statistics(values, loaded['model'].med_, scale_eff)
        except p.InputUnavailable as error:
            rows_plan.append(
                dict(record_id=cid, transaction_id=cid, available=False, status='unavailable', reason=error.code, requests=[])
            )
            continue

        rows_plan.append(
            dict(
                record_id=cid,
                transaction_id=cid,
                available=True,
                status='ready',
                reason=None,
                missing_features=list(missing),
                requests=[
                    dict(
                        profile='statistics',
                        role='statistics',
                        values=[np.asarray(v).tolist() for v in args],
                    )
                ],
            )
        )

    meta = (
        dict(
            artifact_id=loaded['artifact_id'],
            model_version=loaded['manifest']['model_version'],
            preprocess_version=loaded['manifest']['preprocess_version'],
            reference_version=loaded['manifest']['reference_version'],
            feature_contract_fingerprint=loaded['manifest']['feature_contract_fingerprint'],
            selected_columns=list(loaded['manifest']['preprocess']['output_columns']),
            reference_values=loaded['reference'],
            quantization=1024,
            absolute_score_error_bound=1 / 1024,
        )
        if loaded is not None
        else None
    )
    return dict(
        version='he4-rule-snapshot-statistics-plan/1.0.0',
        artifact=meta,
        rows=rows_plan,
    )


def decode_statistics_plan_results(plan: dict, outputs: list) -> dict:
    """Decode encrypted `RobustZ` outputs and map to frozen empirical midranks."""
    cursor = 0
    meta = plan.get('artifact') or {}
    ref_arr = np.asarray(meta.get('reference_values') or [], dtype=float)
    raw_scores_avail = [float(v / 1024.0) for v in outputs]
    ranks_avail = (
        np.atleast_1d(empirical_rank(ref_arr, np.asarray(raw_scores_avail, dtype=float)))
        if raw_scores_avail
        else np.asarray([], dtype=float)
    )
    rows_out = []
    for entry in plan['rows']:
        tid = entry['transaction_id']
        if not entry['available']:
            rows_out.append(
                dict(
                    transaction_id=tid,
                    method_id='robust_z',
                    available=False,
                    status='unavailable',
                    raw_score=None,
                    score=None,
                    score_kind='empirical_midrank',
                    reason=entry['reason'],
                    missing_features=list(entry.get('missing_features', [])),
                    artifact_id=meta.get('artifact_id'),
                )
            )
            continue
        val = outputs[cursor]
        if isinstance(val, np.ndarray) and val.ndim == 0:
            val = int(val.item())
        if type(val) is not int or not 0 <= val <= 20480:
            raise ValueError('he4_statistics_output')
        raw_score = float(val / 1024.0)
        rank = float(ranks_avail[cursor])
        cursor += 1
        rows_out.append(
            dict(
                transaction_id=tid,
                method_id='robust_z',
                available=True,
                status='available',
                raw_score=raw_score,
                score=rank,
                score_kind='empirical_midrank',
                reason=None,
                missing_features=list(entry.get('missing_features', [])),
                artifact_id=meta['artifact_id'],
                model_version=meta['model_version'],
                preprocess_version=meta['preprocess_version'],
                reference_version=meta['reference_version'],
                feature_contract_fingerprint=meta['feature_contract_fingerprint'],
                quantization=meta['quantization'],
                absolute_score_error_bound=meta['absolute_score_error_bound'],
                selected_columns=list(meta['selected_columns']),
                probability=False,
            )
        )
    if cursor != len(outputs):
        raise ValueError('statistics output count mismatch')
    return dict(rows=rows_out)
