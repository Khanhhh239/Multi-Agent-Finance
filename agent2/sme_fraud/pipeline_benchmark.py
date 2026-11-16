"""Read-only score matrix and same-budget trial; never an active ensemble.

Joins a saved, approved supervised shadow run with a fresh technical analysis
of the exact same immutable source/cutoff. Raw scales are kept separate. No
weights, calibration, thresholds, labels or operational delivery are invented.
"""
from copy import deepcopy
import math
from pathlib import Path

from finance_input.json_io import loads
from .import_files import canonical, digest, fail
from .snapshot_features import utc
from .snapshot_analysis import analyze_snapshot
from .rule35_comparison import extract_rule35_records, _validate_candidate_isolation
from .selection_comparison import BUDGET, POLICY, identity, select_records

VERSION = 'agent2-pipeline-benchmark/0.1.0'


def check(ok, code, message):
    if not ok:
        fail(409, code, message, 'Chọn đúng snapshot, cutoff và phiên model đã duyệt rồi chạy lại benchmark.')


def build_matrix(scope, analysis, shadow, manifest, raw, *, ml_method=None):
    """Internal DTO join. Public callers must use benchmark_shadow_run below."""
    company = next(iter(scope.company_ids))
    check(shadow['tenant_id'] == scope.tenant_id and shadow['company_id'] == company,
          'BENCHMARK_SCOPE', 'Kết quả shadow không thuộc doanh nghiệp này.')
    check(analysis.get('view') == 'technical' and analysis.get('version') == 'snapshot-rule-analysis/1.0.0',
          'BENCHMARK_PROFILE', 'Benchmark hiện cần snapshot nguồn đầy đủ 35 luật.')
    check(raw.get('tenant_id') == scope.tenant_id and raw.get('company_id') == company and
          manifest['tenant_id'] == scope.tenant_id and manifest['company_id'] == company,
          'BENCHMARK_SCOPE', 'Nguồn phân tích không thuộc doanh nghiệp này.')
    binding = shadow['snapshot']
    check(all(binding[k] == manifest[k] == analysis['snapshot'][k] for k in ('snapshot_id', 'checksum', 'data_checksum')),
          'BENCHMARK_SNAPSHOT_MISMATCH', 'Hai kết quả không dùng cùng snapshot/checksum.')
    check(utc(binding['as_of']) == utc(analysis['as_of']), 'BENCHMARK_CUTOFF_MISMATCH', 'Hai kết quả không dùng cùng cutoff.')
    check(shadow['model'].get('approved_for_shadow') is True and shadow['model'].get('approval_sha256'),
          'BENCHMARK_MODEL_NOT_APPROVED', 'Model shadow chưa có bản phê duyệt được ghim.')
    candidate_scope = _validate_candidate_isolation(analysis, raw)
    native = {(r['transaction_id'], r['revision']): r for r in analysis['rows']}
    shadow_rows = {(r['record_id'], r['revision']): r for r in shadow['rows']}
    check(len(shadow_rows) == len(shadow['rows']) and set(native) <= set(shadow_rows),
          'BENCHMARK_ROW_BINDING', 'Shadow thiếu hoặc trùng ID/revision so với danh sách ứng viên.')
    cases = {k: dict(case_id='bmcase_' + digest(canonical([scope.tenant_id, company, manifest['snapshot_id'], *k]))) for k in native}
    pins = analysis.get('bridge_provenance', {}).get('model_pins') or {}
    configured = [m for m, pin in pins.items() if m != 'robust_z' and pin is not None]
    check(ml_method is not None or len(configured) <= 1, 'BENCHMARK_METHOD_SELECTION_REQUIRED',
          'Có nhiều model không nhãn; chọn rõ ml_method để khóa phương án so sánh.')
    check(ml_method is None or ml_method in ('isolation_forest', 'autoencoder', 'ecod', 'lof'),
          'BENCHMARK_METHOD_SELECTION_REQUIRED', 'Phương pháp ML không nhãn chưa được hỗ trợ.')
    records, groups, ml_method, ml_pin = extract_rule35_records(analysis, cases, ml_method=ml_method)

    excluded = {}
    for r in records:
        key = identity(r)
        saved = shadow_rows[key]
        check(utc(saved['event_at']) == utc(r['event_at']), 'BENCHMARK_ROW_BINDING', 'Thời gian giao dịch không khớp giữa hai kết quả.')
        if not r['tx_visible']:
            excluded[key] = 'transaction_not_known_at_cutoff'
        elif not saved.get('is_new_transaction') or saved.get('history_status') != 'new_transaction':
            excluded[key] = 'seen_in_supervised_training_or_evaluation'
    # Never compare only one member of a linked component after excluding a
    # contaminated member. Propagate through overlapping obligation groups.
    changed = True
    while changed:
        changed = False
        for members in groups.values():
            if set(members) & set(excluded):
                for key in set(members) & set(native):
                    if key not in excluded:
                        excluded[key] = 'linked_group_contains_excluded_transaction'
                        changed = True

    matrix = []
    supervised_records = []
    for r in records:
        key = identity(r);saved = shadow_rows[key];row = native[key]
        value = saved.get('score')
        available = saved.get('available') is True and saved.get('status') == 'scored'
        check(not available or (type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1),
              'BENCHMARK_SHADOW_SCORE', 'Điểm shadow đã lưu không hợp lệ.')
        check(available or value is None, 'BENCHMARK_SHADOW_SCORE', 'Dòng shadow chưa khả dụng phải giữ điểm null.')
        methods = deepcopy(row.get('methods', {}))
        methods['supervised_shadow'] = dict(available=available, raw_score=value, percentile=None,
            score_kind='uncalibrated_supervised_score', model_pin=deepcopy(shadow['model']),
            reason=None if available else deepcopy(saved.get('issues', [])))
        matrix.append(dict(record_id=key[0], revision=key[1], event_at=r['event_at'],
            candidate=True, benchmark_eligible=key not in excluded, exclusion_reason=excluded.get(key),
            rule_state=r['rule_state'], rule_completeness=r['rule_eval_completeness'],
            actionable_hit_rules=r['actionable_hit_rules'], unavailable_rule_ids=r['unavailable_rule_ids'],
            context_hits=r['context_hits'], master_quality_hits=r['master_quality_hits'],
            rule_results=deepcopy(row['rule_coverage']['rules']), methods=methods,
            graph=deepcopy(row.get('graph')), graph_is_fraud_probability=False))
        supervised_records.append(dict(r, ml_method='supervised_shadow', ml_available=available,
            ml_score=value, ml_reason=None if available else deepcopy(saved.get('issues', []))))

    eligible = {identity(r) for r in records} - set(excluded)
    trial_groups = {g: set(v) for g, v in groups.items() if set(v) <= eligible}
    local_records = [r for r in records if identity(r) in eligible]
    shadow_records = [r for r in supervised_records if identity(r) in eligible]
    baseline, deferred, _, _ = select_records(local_records, trial_groups, budget=BUDGET)

    def arm(name, rows, with_ml):
        chosen, _, additions, _ = select_records(rows, trial_groups, budget=BUDGET)
        if not with_ml:
            additions = []
        keys = chosen + (additions if with_ml else [])
        return dict(name=name, selected=[list(k) for k in keys], added=[list(k) for k in additions] if with_ml else [],
            selected_count=len(keys), unused_slots=BUDGET-len(keys),
            additions_with_rule_source_gaps=[list(identity(r)) for r in rows if identity(r) in additions and r['rule_state'] in ('partial_unavailable', 'unavailable')],
            precision_resolved=None, recall=None, useful_cases=None, review_seconds=None,
            label_status='not_joined; no business effectiveness claimed')

    arms = [arm('rules_only', local_records, False), arm('rules_plus_unsupervised', local_records, True),
            arm('rules_plus_supervised_shadow', shadow_records, True)]
    check(all(a['selected'][:len(baseline)] == [list(k) for k in baseline] and a['selected_count'] <= BUDGET for a in arms),
          'BENCHMARK_POLICY', 'Các phương án không giữ cùng baseline/ngân sách.')
    coverage = {}
    method_ids = sorted({name for row in matrix for name in row['methods']})
    for name in method_ids:
        evaluated = [r['methods'].get(name, {}) for r in matrix]
        coverage[name] = dict(available=sum(m.get('available') is True for m in evaluated),
                              unavailable=sum(m.get('available') is not True for m in evaluated))
    result = dict(version=VERSION, status='technical_only', tenant_id=scope.tenant_id, company_id=company,
        implementation={name:digest(Path(__file__).with_name(name).read_bytes()) for name in
                        ('pipeline_benchmark.py','rule35_comparison.py','selection_comparison.py')},
        snapshot={k:manifest[k] for k in ('snapshot_id', 'checksum', 'data_checksum', 'contract_version')},
        as_of=analysis['as_of'], analysis_id=analysis['analysis_id'], analysis_sha256=digest(canonical(analysis)),
        shadow_run_id=shadow['shadow_run_id'], shadow_sha256=digest(canonical(shadow)),
        supervised_model_pin=deepcopy(shadow['model']), unsupervised_method=ml_method, unsupervised_model_pin=ml_pin,
        feature_contract=analysis.get('feature_contract'), candidate_scope=candidate_scope,
        candidate_rows=len(matrix), eligible_rows=len(eligible), excluded_rows=len(excluded),
        source_history_rows_not_candidates=len(shadow_rows)-len(native), coverage=coverage, rows=matrix,
        comparison=dict(policy=POLICY, budget=BUDGET, unit='transaction', design='retrospective_known_shadow_run',
            prospective=False, arms=arms, deferred_rule_alerts=[list(k) for k in deferred],
            raw_scores_mixed_across_methods=False, active_case_policy=False),
        limits=['No validated ensemble, percentile calibration, production threshold or active routing is created.',
                'Rule-source gaps are preserved; ML additions do not automatically prove a rule miss.',
                'Human review outcomes and verified labels are not inferred from model scores.',
                'Snapshot-source graph evidence is context, not a fraud probability.',
                'The fixed five-transaction trial is distinct from the unapproved production case budget.'],
        operational_queue_changed=False, fit_performed=False)
    result['report_sha256'] = digest(canonical(result))
    return result


def benchmark_shadow_run(snapshots, manager, scope, shadow_run_id, *, resources=None, recheck=None, ml_method=None):
    """Read only saved server results; never takes feature or score arrays from UI."""
    snapshots._scope(scope)
    if recheck is not None:
        check(recheck() == scope, 'AUTH_CONTEXT_CHANGED', 'Quyền đã thay đổi.')
    shadow = manager.get_shadow_run(scope, shadow_run_id, recheck)['shadow_run']
    binding = shadow['snapshot'];sid = binding['snapshot_id']
    manifest = snapshots.get_snapshot(scope, sid, recheck)
    raw = loads(snapshots.get_snapshot(scope, sid, recheck, data=True))
    check(digest(canonical(raw)) == manifest['data_checksum'], 'BENCHMARK_SNAPSHOT_MISMATCH', 'Checksum nguồn không khớp.')
    analysis = analyze_snapshot(snapshots, scope, sid, binding['as_of'], technical=True, resources=resources, recheck=recheck)
    result = build_matrix(scope, analysis, shadow, manifest, raw, ml_method=ml_method)
    if recheck is not None:
        check(recheck() == scope, 'AUTH_CONTEXT_CHANGED', 'Quyền đã thay đổi.')
    return result
