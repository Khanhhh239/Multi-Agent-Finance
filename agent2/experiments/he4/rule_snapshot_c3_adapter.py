"""Slice 2 adapter: connect rule `C3` from `agent2-rule-snapshot/1.0.0` to Concrete `c3` circuit.

All timing (`0 <= approved_at - created_at < 60s`), amount threshold (`amount >= high_approval_vnd`),
authority band selection (`min_amount_vnd <= amount_vnd <= max_amount_vnd`), specificity tie-breaking,
and `ambiguous_authority` detection execute inside encrypted Concrete `c3` circuit.
"""
from __future__ import annotations

from copy import deepcopy

import numpy as np

from . import c3_circuit as c3m
from sme_fraud.authority_policy import ApprovalAuthority
from sme_fraud.identity import normalize
from sme_fraud.import_files import canonical, digest, fail
from sme_fraud.native_rule_node import _gaps, validate_bundle
from sme_fraud.rule_snapshot import CONTRACT, validate as validate_rule_snapshot
from sme_fraud.rules import DEFAULT_CONFIG
from sme_fraud.snapshot_features import utc
from sme_fraud.temporal_evidence import approved_evidence


def _metadata_authority_candidates(authority: ApprovalAuthority, row: dict, actor: str, employee: dict, at: str) -> list[dict]:
    """Select approved `approval_authorities` rows matching metadata ONLY (never amount_vnd)."""
    cid = row['company_id']
    candidates = []
    for record in authority.authorities.records_at(cid, at):
        if not authority._approved(record, cid, at, actor):
            continue
        if record['action'] not in {'approve', 'all'}:
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


def plan_c3_from_rule_snapshot(
    data: dict,
    scope,
    *,
    high_approval_vnd: int | None = None,
    enforce_source_guards: bool = True,
) -> dict:
    """Build Concrete `c3` evaluation plan for every candidate transaction in `data`."""
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
    threshold_vnd = int(DEFAULT_CONFIG['high_approval_vnd'] if high_approval_vnd is None else high_approval_vnd)

    source_gaps = list(_gaps(source, 'C3'))
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
                    actor_role_known=False,
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
                    actor_role_known=False,
                    requests=[],
                )
            )
            continue

        at = tx.get('approved_at', '')
        actor = tx.get('approver_id', '')
        company_id = tx['company_id']
        coverage = authority.covered(tx, 'approve', at)
        if coverage is not None and coverage.get('_ambiguous'):
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason='authority_not_covered_or_ambiguous_at_action',
                    actor_role_known=False,
                    requests=[],
                )
            )
            continue

        employee = authority.employee_at(company_id, actor, at) if coverage else None
        actor_role_known = bool(
            employee and isinstance(employee.get('role'), str) and normalize(employee['role']) not in {'', 'UNKNOWN', 'NONE', 'NULL'}
        )

        if coverage is None:
            if enforce_source_guards:
                rows_plan.append(
                    dict(
                        record_id=cid,
                        transaction_id=cid,
                        available=False,
                        status='unavailable',
                        reason='authority_not_covered_or_ambiguous_at_action',
                        actor_role_known=actor_role_known,
                        requests=[],
                    )
                )
                continue
            mode_legacy = 1
            candidates = []
        else:
            if not employee or employee.get('company_id') != company_id:
                rows_plan.append(
                    dict(
                        record_id=cid,
                        transaction_id=cid,
                        available=False,
                        status='unavailable',
                        reason='authority_not_covered_or_ambiguous_at_action',
                        actor_role_known=False,
                        requests=[],
                    )
                )
                continue
            mode_legacy = 0
            candidates = _metadata_authority_candidates(authority, tx, actor, employee, at)

        if len(candidates) > c3m.MAX_AUTHORITIES:
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason='he_c3_authority_limit',
                    actor_role_known=actor_role_known,
                    requests=[],
                )
            )
            continue

        try:
            created_us = c3m.timestamp_to_epoch_us(tx.get('created_at', ''))
            approved_us = c3m.timestamp_to_epoch_us(at)
            amount = int(tx['amount_vnd'])
            created_w = c3m.encode_word64(created_us)
            approved_w = c3m.encode_word64(approved_us)
            amount_w = c3m.encode_word64(amount)
            thr_w = c3m.encode_word64(threshold_vnd)

            rule_min = np.zeros((c3m.MAX_AUTHORITIES, c3m.C3_WORD_DIGITS), dtype=np.int64)
            rule_max = np.zeros((c3m.MAX_AUTHORITIES, c3m.C3_WORD_DIGITS), dtype=np.int64)
            rule_rank = np.zeros(c3m.MAX_AUTHORITIES, dtype=np.int64)
            rule_is_high = np.zeros(c3m.MAX_AUTHORITIES, dtype=np.int64)
            rule_outcome = np.zeros(c3m.MAX_AUTHORITIES, dtype=np.int64)

            distinct_specs = sorted({spec for spec, _ in candidates})
            spec_rank = {spec: idx + 1 for idx, spec in enumerate(distinct_specs)}
            distinct_outcomes = sorted({(int(r['self_approval_allowed'] == 1), str(r['authority_level'])) for _, r in candidates})
            outcome_code = {pair: idx + 1 for idx, pair in enumerate(distinct_outcomes)}

            for i, (spec, rec) in enumerate(candidates):
                rule_min[i] = c3m.encode_word64(int(rec['min_amount_vnd']))
                rule_max[i] = c3m.encode_word64(int(rec['max_amount_vnd']))
                rule_rank[i] = spec_rank[spec]
                rule_is_high[i] = int(rec['authority_level'] in {'high', 'executive'})
                rule_outcome[i] = outcome_code[(int(rec['self_approval_allowed'] == 1), str(rec['authority_level']))]
        except (KeyError, TypeError, ValueError):
            rows_plan.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    available=False,
                    status='unavailable',
                    reason='he_c3_domain_limit',
                    actor_role_known=actor_role_known,
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
        req = dict(
            profile='c3',
            rule_id='C3',
            role='row',
            values=values,
            enforce_source_guards=enforce_source_guards,
            actor_role_known=actor_role_known,
            mode_legacy=bool(mode_legacy),
            source_refs=dict(
                transaction_id=cid,
                approver_id=actor,
                coverage_id=coverage['coverage_id'] if coverage else None,
                candidate_authority_ids=[rec['authority_id'] for _, rec in candidates],
            ),
        )
        rows_plan.append(
            dict(
                record_id=cid,
                transaction_id=cid,
                txn_type=tx.get('txn_type'),
                posted_at=tx.get('posted_at'),
                observed_at=tx.get('observed_at'),
                available=True,
                status='ready',
                reason=None,
                actor_role_known=actor_role_known,
                requests=[req],
            )
        )

    return dict(
        version='he4-rule-snapshot-c3-plan/1.0.0',
        contract_version=CONTRACT,
        company_id=data['company_id'],
        tenant_id=data['tenant_id'],
        as_of=as_of,
        rule_id='C3',
        profile='c3',
        enforce_source_guards=enforce_source_guards,
        source_sha256=digest(canonical(source)),
        rows=rows_plan,
    )


def prepare_c3_rule_snapshot(
    store,
    scope,
    snapshot_id: str,
    as_of: str,
    *,
    high_approval_vnd: int | None = None,
    enforce_source_guards: bool = True,
    recheck=None,
) -> dict:
    """Load committed `agent2-rule-snapshot/1.0.0` bundle and build Concrete `c3` plan."""
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
    plan = plan_c3_from_rule_snapshot(
        data,
        scope,
        high_approval_vnd=high_approval_vnd,
        enforce_source_guards=enforce_source_guards,
    )
    plan['snapshot'] = {k: manifest[k] for k in ('snapshot_id', 'company_id', 'checksum', 'data_checksum', 'contract_version')}
    return plan


def decode_c3_plan_results(plan: dict, decrypted_outputs: list[list[int]]) -> dict:
    """Decode Concrete `c3` outputs, applying post-decryption authority-ambiguity/role checks."""
    idx = 0
    rows_out = []
    enforce_guards = bool(plan.get('enforce_source_guards', True))

    for entry in plan['rows']:
        reqs = entry.get('requests', [])
        outputs = decrypted_outputs[idx : idx + len(reqs)]
        idx += len(reqs)
        if len(outputs) != len(reqs):
            raise ValueError('decrypted output count mismatch for C3 plan')

        if not entry['available']:
            rows_out.append(
                dict(
                    transaction_id=entry['transaction_id'],
                    available=False,
                    status='unavailable',
                    matched=None,
                    score=None,
                    reason=entry['reason'],
                    details=None,
                )
            )
            continue

        req = reqs[0]
        decoded = c3m.decode_c3(outputs[0])
        if enforce_guards and not req['mode_legacy']:
            if decoded['ambiguous_authority']:
                rows_out.append(
                    dict(
                        transaction_id=entry['transaction_id'],
                        available=False,
                        status='unavailable',
                        matched=None,
                        score=None,
                        reason='authority_not_covered_or_ambiguous_at_action',
                        details=decoded,
                    )
                )
                continue
            if not decoded['has_matching_authority'] and not req['actor_role_known']:
                rows_out.append(
                    dict(
                        transaction_id=entry['transaction_id'],
                        available=False,
                        status='unavailable',
                        matched=None,
                        score=None,
                        reason='actor_role_not_known_for_authority_scope',
                        details=decoded,
                    )
                )
                continue

        matched = bool(decoded['matched'])
        rows_out.append(
            dict(
                transaction_id=entry['transaction_id'],
                available=True,
                status='evaluated_hit' if matched else 'evaluated_no_hit',
                matched=matched,
                score=8 if matched else 0,
                reason=None,
                details=decoded,
            )
        )

    if idx != len(decrypted_outputs):
        raise ValueError('unused decrypted outputs left over after decoding C3 plan')
    return dict(
        version='he4-rule-snapshot-c3-result/1.0.0',
        company_id=plan['company_id'],
        as_of=plan['as_of'],
        rule_id='C3',
        rows=rows_out,
    )

