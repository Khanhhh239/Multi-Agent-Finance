"""35-rule baseline vs 35-rule + ML selection comparison on full rule snapshots."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from .import_files import canonical, digest, fail
from .review_api import display_record
from .rule_snapshot import SCOPE_RULES
from .rules import RULE_NAMES
from .selection_comparison import BUDGET, POLICY, arm_metrics, identity, score, select_records
from .snapshot_features import utc

VERSION = 'rule35-selection-comparison/1.0.0'
ANALYSIS_VERSION = 'snapshot-rule-analysis/1.0.0'
MASTER_QUALITY_RULES = frozenset({'B5', 'E4', 'E3'})
B5_E4_OVERLAP_PAIR = frozenset({'B5', 'E4'})


def _verify_source_scope(snapshot_data, scope, snapshot_manifest):
    company = next(iter(scope.company_ids))
    if not isinstance(snapshot_data, dict) or snapshot_data.get('contract_version') != 'agent2-rule-snapshot/1.0.0':
        fail(422, 'COMPARISON_SOURCE_CONTRACT', 'Dữ liệu phải đúng profile agent2-rule-snapshot/1.0.0.',
             'Dùng snapshot nguồn đầy đủ đã xác nhận lưu.')
    if snapshot_data.get('tenant_id') != scope.tenant_id or snapshot_data.get('company_id') != company:
        fail(403, 'ACCESS_DENIED', 'Snapshot ngoài phạm vi doanh nghiệp được phép.', 'Chọn đúng doanh nghiệp.')
    if snapshot_manifest.get('company_id') != company or (
        snapshot_manifest.get('tenant_id') is not None and snapshot_manifest.get('tenant_id') != scope.tenant_id
    ):
        fail(403, 'ACCESS_DENIED', 'Manifest ngoài phạm vi doanh nghiệp được phép.', 'Chọn đúng doanh nghiệp.')
    source = snapshot_data.get('source') or {}
    if source.get('company_id') != company or source.get('tenant_id') != scope.tenant_id:
        fail(403, 'ACCESS_DENIED', 'Nguồn ngoài phạm vi doanh nghiệp được phép.', 'Chọn đúng doanh nghiệp.')
    return company, source


def _resolved_evidence_item(rec, table, simulated):
    verified_doc = (
        table == 'transaction_documents'
        and not simulated
        and rec.get('status') == 'verified'
    )
    return dict(
        evidence_id='ev_' + digest(canonical(rec)),
        table=table,
        record=display_record(rec),
        simulated=simulated,
        original_verified=bool(verified_doc),
    )


def rule35_cases_for(snapshot_store, scope, analysis, review_store, recheck=None, *, raw_data=None):
    """Build deterministic enterprise review packets pinned to snapshot/analysis point-in-time sources."""
    if analysis.get('version') != ANALYSIS_VERSION:
        fail(409, 'COMPARISON_ANALYSIS_VERSION', 'Lần phân tích chưa đúng định dạng 35 luật đầy đủ.',
             'Chạy lại analyze snapshot agent2-rule-snapshot/1.0.0.')
    sid = analysis['snapshot']['snapshot_id']
    if raw_data is None:
        from finance_input.json_io import loads
        raw_data = loads(snapshot_store.get_snapshot(scope, sid, recheck, data=True))
    manifest = dict(analysis['snapshot'])
    _verify_source_scope(raw_data, scope, manifest)
    source = raw_data['source']
    tables = source['tables']
    simulated = bool(source.get('is_simulated'))
    as_of_dt = utc(analysis['as_of'])

    by_sha = {}
    tx_by_id = {}
    for table, recs in tables.items():
        if not isinstance(recs, list):
            continue
        for rec in recs:
            if isinstance(rec, dict):
                by_sha[(table, digest(canonical(rec)))] = rec
                if table == 'transactions':
                    tx_by_id[rec['transaction_id']] = rec

    cases = []
    for row in analysis['rows']:
        tid = row['transaction_id']
        rev = int(row['revision'])
        tx = tx_by_id.get(tid)
        if tx is None:
            fail(503, 'REVIEW_EVIDENCE_BINDING', 'Không tìm thấy giao dịch trong snapshot đã khóa.',
                 'Kiểm tra đúng snapshot của lần phân tích.')
        tx_visible = row.get('availability', {}).get('available', True) is not False
        event_dt = utc(row['event_at'])
        refs_by_sha = {}

        if tx_visible:
            if utc(tx['observed_at']) > as_of_dt or utc(tx['posted_at']) > as_of_dt:
                fail(503, 'REVIEW_EVIDENCE_TIME', 'Giao dịch vượt quá mốc as_of của lần phân tích.',
                     'Không dùng chứng từ tương lai.')
            refs_by_sha[('transactions', digest(canonical(tx)))] = tx

            for ref in row.get('feature_evidence', {}).get('records', []):
                table = ref.get('table')
                sha = ref.get('source_sha256')
                rec = by_sha.get((table, sha)) if sha else None
                if rec is None:
                    fail(503, 'REVIEW_EVIDENCE_BINDING', 'Căn cứ feature không khớp snapshot đã khóa.',
                         'Kiểm tra bản nguồn và phiên bản phân tích.')
                obs = rec.get('observed_at')
                eff = ref.get('effective_at') or rec.get('posted_at') or rec.get('recorded_at') or rec.get('verified_at') or obs
                if utc(obs) > as_of_dt or utc(eff) > event_dt:
                    fail(503, 'REVIEW_EVIDENCE_TIME', 'Căn cứ chưa khả dụng tại thời điểm giao dịch đang rà.',
                         'Không dùng chứng từ đến muộn để kết luận cho quá khứ.')
                refs_by_sha[(table, sha)] = rec

        items = [
            _resolved_evidence_item(rec, table, simulated)
            for (table, _), rec in sorted(refs_by_sha.items(), key=lambda item: (item[0][0], item[0][1]))
        ]
        case_id = review_store.case_id(scope, analysis['analysis_id'], tid, rev)
        hit_rules = []
        missing_sources = []
        if 'rule_coverage' in row:
            for r in row['rule_coverage']['rules']:
                if r['rule_id'] in SCOPE_RULES | MASTER_QUALITY_RULES:
                    continue
                if r['status'] == 'evaluated_hit' and any(
                    not h.get('suppressed_reason') and (h.get('points', 0) > 0 or h.get('hard_trigger'))
                    for h in r.get('hits', [])
                ):
                    hit_rules.append(r['rule_id'])
                elif r['status'] == 'unavailable':
                    missing_sources.append(r['rule_id'])
        why = (
            '35 luật ghi nhận tín hiệu nghiệp vụ cần đối chiếu chứng từ gốc.'
            if hit_rules else
            'Một số luật chưa đủ nguồn tại thời điểm phân tích; cần kiểm tra nguồn thiếu và hồ sơ giao dịch.'
            if missing_sources and tx_visible else
            'Các luật áp dụng đã đối chiếu chưa thấy tín hiệu; giữ đối chiếu mẫu hoặc điểm bất thường tương đối nếu được chọn.'
            if tx_visible else
            'Giao dịch chưa khả dụng tại mốc phân tích.'
        )
        cases.append(dict(
            case_id=case_id,
            record_id=tid,
            revision=rev,
            amount_vnd=str(tx['amount_vnd']),
            currency=tx['currency'],
            event_at=row['event_at'],
            as_of=analysis['as_of'],
            question='Khoản tiền này có đúng đối tượng, nghĩa vụ, số tiền và thời điểm được phép không?',
            why=why,
            next_step='Đối chiếu hóa đơn, phê duyệt và chứng từ gốc; thiếu nguồn thì chọn Chưa đủ căn cứ.',
            evidence=items,
            analysis_limits=dict(row.get('feature_missing_reasons', {})),
            review=review_store.get(scope, case_id),
        ))
    return cases


def _resolve_ml_method(analysis, ml_method):
    pins = dict(analysis.get('bridge_provenance', {}).get('model_pins') or {})
    candidates = sorted(m for m in pins if m != 'robust_z' and pins[m] is not None)
    if ml_method is not None:
        return ml_method, pins.get(ml_method)
    if len(candidates) == 1:
        return candidates[0], pins[candidates[0]]
    if len(candidates) > 1:
        raise ValueError(f'Multiple ML methods pinned ({candidates}); specify ml_method explicitly')
    # Fallback inspection when no ML artifact was pinned: check methods on first row.
    rows = analysis.get('rows') or []
    row_methods = sorted(m for m in (rows[0].get('methods') or {}) if m not in ('rules', 'robust_z')) if rows else []
    if len(row_methods) == 1:
        return row_methods[0], pins.get(row_methods[0])
    return None, None


def _master_dedup_key(rule_id, hit):
    ev = hit.get('evidence') or {}
    if rule_id in B5_E4_OVERLAP_PAIR:
        vendors = tuple(sorted(set(ev.get('vendor_ids') or [])))
        if vendors:
            return ('B5_E4_SHARED_VENDOR', vendors)
        eid = hit.get('evidence_id') or ev.get('evidence_id')
        if eid:
            return ('B5_E4_SHARED_VENDOR', eid)
    eid = hit.get('evidence_id') or ev.get('evidence_id')
    return (rule_id, eid or digest(canonical(ev)))


def _extract_batch_groups(analysis, key_by_id):
    """Collect active simultaneous rule groups from catalogue_results and top-level groups."""
    groups = {}
    member_hits = {}

    for entry in analysis.get('catalogue_results') or []:
        rid = entry.get('rule_id')
        if rid in SCOPE_RULES or rid in MASTER_QUALITY_RULES:
            continue
        for ev in entry.get('groups') or []:
            if ev.get('status') != 'evaluated' or ev.get('signal') is not True or ev.get('suppressed_reason'):
                continue
            if not (ev.get('points', 0) > 0 or ev.get('hard_trigger')):
                continue
            cands = sorted(
                {key_by_id[tid] for tid in ev.get('transaction_ids', []) if tid in key_by_id},
                key=lambda k: (k[0], k[1]),
            )
            if not cands:
                continue
            eid = ev.get('event_id') or digest(canonical([rid, cands]))
            for key in cands:
                member_hits.setdefault(key, []).append((rid, eid))
            if len(cands) >= 2:
                groups[eid] = set(cands)

    for g in analysis.get('groups') or []:
        ids = g.get('transaction_ids') or []
        cands = sorted({key_by_id[tid] for tid in ids if tid in key_by_id}, key=lambda k: (k[0], k[1]))
        if len(cands) >= 2:
            gid = g.get('group_id') or digest(canonical(cands))
            groups[gid] = set(cands)

    return groups, member_hits


def extract_rule35_records(analysis, cases_by_key, *, ml_method=None):
    """Extract normalized per-transaction 35-rule + ML records and simultaneous groups."""
    if analysis.get('version') != ANALYSIS_VERSION or analysis.get('view') != 'technical':
        fail(409, 'COMPARISON_TECHNICAL_ANALYSIS_REQUIRED',
             'Cần kết quả phân tích 35 luật mức kỹ thuật (technical) để tạo kế hoạch so sánh.',
             'Chạy analyze với view=technical.')
    rows = analysis.get('rows') or []
    key_by_id = {r['transaction_id']: (r['transaction_id'], int(r['revision'])) for r in rows}
    if len(key_by_id) != len(rows) or set(key_by_id.values()) != set(cases_by_key):
        fail(503, 'COMPARISON_ROW_BINDING', 'Kết quả phân tích và danh sách phiếu chưa khớp đủ giao dịch.',
             'Kiểm tra nguồn và lần phân tích trước khi so sánh.')

    resolved_ml, expected_pin = _resolve_ml_method(analysis, ml_method)
    groups, batch_member_hits = _extract_batch_groups(analysis, key_by_id)

    expected_fp = (analysis.get('feature_contract') or {}).get('fingerprint')
    pinned_artifact_id = (expected_pin or {}).get('artifact_id') if isinstance(expected_pin, dict) else None

    records = []
    for row in rows:
        key = (row['transaction_id'], int(row['revision']))
        tx_visible = row.get('availability', {}).get('available', True) is not False
        cov = row.get('rule_coverage') or {}
        rule_entries = cov.get('rules') or []
        if len(rule_entries) != len(RULE_NAMES) or {e['rule_id'] for e in rule_entries} != set(RULE_NAMES):
            raise ValueError('Analysis row does not cover all 35 rules')

        actionable_hit_rules = []
        context_hits = []
        master_quality_hits = []
        master_quality_dedup = set()
        no_hit_actionable = []
        unavailable_actionable = []
        not_applicable_actionable = []
        scope_refs = []
        missing_source_details = {}

        for entry in rule_entries:
            rid = entry['rule_id']
            status = entry['status']
            hits = [h for h in entry.get('hits') or [] if not h.get('suppressed_reason')]

            if rid in SCOPE_RULES:
                if status != 'not_applicable' and tx_visible:
                    raise ValueError(f'Scope rule {rid} must stay in dataset/scope diagnostics, never row alert')
                if entry.get('scope_result_ref'):
                    scope_refs.append(entry['scope_result_ref'])
                continue

            if rid in MASTER_QUALITY_RULES:
                if any(h.get('points', 0) > 0 or h.get('hard_trigger') for h in hits) or (entry.get('score') or 0) > 0:
                    raise ValueError(f'Master quality rule {rid} cannot carry positive transaction score')
                if status == 'evaluated_hit':
                    master_quality_hits.append(rid)
                    for h in hits:
                        master_quality_dedup.add(_master_dedup_key(rid, h))
                continue

            if status == 'not_applicable':
                not_applicable_actionable.append(rid)
            elif status == 'unavailable':
                unavailable_actionable.append(rid)
                missing_source_details[rid] = [
                    dict(table=g.get('table'), reason=g.get('reason')) for g in entry.get('gaps') or []
                ]
            elif status == 'evaluated_no_hit':
                no_hit_actionable.append(rid)
            elif status == 'evaluated_hit':
                if any(h.get('points', 0) > 0 or h.get('hard_trigger') for h in hits):
                    actionable_hit_rules.append(rid)
                else:
                    context_hits.append(rid)

        batch_events = batch_member_hits.get(key, [])
        for rid, _eid in batch_events:
            if rid not in actionable_hit_rules:
                actionable_hit_rules.append(rid)

        actionable_hit_rules.sort()
        context_hits.sort()
        master_quality_hits.sort()
        unavailable_actionable.sort()
        applicable_count = len(RULE_NAMES) - len(SCOPE_RULES) - len(MASTER_QUALITY_RULES) - len(not_applicable_actionable)

        if not tx_visible:
            rule_state = 'unavailable'
            rule_completeness = 'tx_not_visible'
        elif actionable_hit_rules:
            rule_state = 'alert'
            rule_completeness = 'all_applicable_evaluated' if not unavailable_actionable else 'partial_rule_source_gap'
        elif applicable_count > 0 and len(unavailable_actionable) == applicable_count:
            rule_state = 'unavailable'
            rule_completeness = 'all_applicable_unavailable'
        elif unavailable_actionable:
            rule_state = 'partial_unavailable'
            rule_completeness = 'partial_rule_source_gap'
        elif applicable_count == 0:
            rule_state = 'not_applicable'
            rule_completeness = 'all_not_applicable'
        else:
            rule_state = 'no_signal'
            rule_completeness = 'all_applicable_evaluated'

        ml_branch = (row.get('methods') or {}).get(resolved_ml) if resolved_ml else None
        ml_val = score(ml_branch) if (ml_branch and tx_visible) else None
        if ml_val is not None:
            if pinned_artifact_id and ml_branch.get('artifact_id') != pinned_artifact_id:
                raise ValueError('ML artifact mismatch against analysis binding')
            if expected_fp and ml_branch.get('feature_contract_fingerprint') != expected_fp:
                raise ValueError('Feature contract mismatch against analysis provenance')

        records.append(dict(
            record_id=key[0],
            revision=key[1],
            case_id=cases_by_key[key]['case_id'],
            event_at=row['event_at'],
            amount_vnd=int(row['amount_vnd']),
            kind=row['kind'],
            tx_visible=tx_visible,
            rule_state=rule_state,
            rule_eval_completeness=rule_completeness,
            actionable_hit_rules=actionable_hit_rules,
            batch_event_ids=sorted({eid for _, eid in batch_events}),
            context_hits=context_hits,
            master_quality_hits=master_quality_hits,
            master_quality_dedup_keys=sorted(digest(canonical(list(k))) for k in master_quality_dedup),
            master_quality_dedup_count=len(master_quality_dedup),
            evaluated_no_hit_count=len(no_hit_actionable),
            unavailable_rule_ids=unavailable_actionable,
            not_applicable_rule_ids=sorted(not_applicable_actionable),
            missing_source_details=missing_source_details,
            scope_result_refs=sorted(set(scope_refs)),
            ml_method=resolved_ml,
            ml_available=ml_val is not None,
            ml_score=ml_val,
            ml_reason=(ml_branch or {}).get('reason') if resolved_ml else dict(code='ml_not_configured'),
        ))

    return records, groups, resolved_ml, expected_pin


def _validate_candidate_isolation(analysis, raw_data):
    if raw_data is None:
        return dict(candidate_count=len(analysis['rows']), history_excluded_from_candidates=None)
    raw_cands = raw_data.get('candidate_transaction_ids') or []
    row_ids = [r['transaction_id'] for r in analysis['rows']]
    if row_ids != raw_cands:
        raise ValueError('Analysis rows do not match snapshot candidate_transaction_ids')
    txs = raw_data.get('source', {}).get('tables', {}).get('transactions', [])
    history_only_ids = {t['transaction_id'] for t in txs} - set(raw_cands)
    if history_only_ids & set(row_ids):
        raise ValueError('history_only transactions leaked into comparison candidates')
    return dict(
        total_snapshot_transactions=len(txs),
        candidate_count=len(raw_cands),
        history_only_count=len(history_only_ids),
        history_excluded_from_candidates=True,
    )


def make_rule35_plan(
    analysis,
    cases,
    snapshot_manifest,
    model_pin=None,
    *,
    ml_method=None,
    raw_data=None,
    budget=BUDGET,
):
    """Build deterministic immutable plan comparing 35-rule baseline vs 35-rule + ML."""
    if budget != BUDGET:
        raise ValueError(f'Locked comparison policy fixes budget={BUDGET}')
    cases_by_key = {identity(c): c for c in cases}
    candidate_check = _validate_candidate_isolation(analysis, raw_data)
    records, groups, resolved_ml, analyzed_pin = extract_rule35_records(
        analysis, cases_by_key, ml_method=ml_method
    )
    if snapshot_manifest.get('checksum') != analysis['snapshot'].get('checksum'):
        fail(409, 'COMPARISON_SNAPSHOT_MISMATCH', 'Checksum snapshot không khớp kết quả phân tích.',
             'Chạy lại trên đúng snapshot đã khóa.')

    baseline, deferred, additions, components = select_records(records, groups, budget=budget)
    by_key = {identity(r): r for r in records}
    remaining_slots = budget - len(baseline)

    if remaining_slots == 0:
        ml_status = 'budget_full_no_slots'
        ml_note = 'Không còn chỗ trong ngân sách tối đa 5 giao dịch; giữ nguyên danh sách 35 luật.'
    elif not additions:
        ml_status = 'ml_unavailable'
        ml_note = 'ML không khả dụng tại lần phân tích này; giữ nguyên danh sách của 35 luật.'
    elif len(additions) < remaining_slots:
        ml_status = 'partial_ml_fill'
        ml_note = f'ML bổ sung {len(additions)}/{remaining_slots} chỗ còn trống từ các ứng viên có điểm ML hợp lệ.'
    else:
        ml_status = 'ml_filled_remaining_slots'
        ml_note = f'ML bổ sung đủ {len(additions)} chỗ trống còn lại (tổng {len(baseline) + len(additions)}/{budget}).'

    addition_classifications = {}
    for k in additions:
        rec = by_key[k]
        addition_classifications[f'{k[0]}#{k[1]}'] = (
            'partial_rule_source_gap'
            if rec['rule_eval_completeness'] == 'partial_rule_source_gap'
            else 'all_applicable_rules_evaluated_no_hit'
        )

    scope_diagnostics = [
        dict(
            rule_id=s['rule_id'],
            name=s['name'],
            status=s['status'],
            matched=s['matched'],
            scope_result_ref=s['rule_id'],
            reason=s.get('reason'),
        )
        for s in analysis.get('scope_results') or []
    ]
    start = min((utc(r['event_at']) for r in records), default=None)
    end = max((utc(r['event_at']) for r in records), default=None)
    simulated = any(e['simulated'] for c in cases for e in c['evidence'])
    effective_pin = deepcopy(model_pin) if model_pin is not None else deepcopy(analyzed_pin)

    return dict(
        version=VERSION,
        plan_kind='rule35_snapshot_comparison',
        policy=POLICY,
        budget=budget,
        run_id=analysis['analysis_id'],
        analysis_id=analysis['analysis_id'],
        analysis_context_id=analysis['analysis_context_id'],
        company_id=analysis['snapshot']['company_id'],
        tenant_id=analysis['snapshot'].get('tenant_id'),
        snapshot_id=analysis['snapshot']['snapshot_id'],
        snapshot_checksum=snapshot_manifest['checksum'],
        data_checksum=analysis['snapshot'].get('data_checksum'),
        as_of=analysis['as_of'],
        result_sha256=digest(canonical(analysis)),
        native_reference_sha256=analysis.get('native_reference_sha256'),
        feature_contract_fingerprint=(analysis.get('feature_contract') or {}).get('fingerprint'),
        ml_method=resolved_ml,
        model_pin=effective_pin,
        bridge_provenance=deepcopy(analysis.get('bridge_provenance') or {}),
        baseline_rule_scope='35_rules_full_snapshot_adapter',
        implemented_rule_count=35,
        he_execution=bool(analysis.get('he_execution', False)),
        period_start=start.isoformat() if start else None,
        period_end=end.isoformat() if end else None,
        created_at=datetime.now(timezone.utc).isoformat(),
        prospective=False,
        design='retrospective_full_snapshot_comparison',
        simulated_data=simulated,
        unit='transaction',
        reviews_present_before_lock=sum(c['review']['feedback'] is not None for c in cases),
        baseline=[list(k) for k in baseline],
        combined=[list(k) for k in baseline + additions],
        added=[list(k) for k in additions],
        removed=[],
        deferred_rule_alerts=[list(k) for k in deferred],
        rule_groups=[[list(k) for k in comp] for comp in components],
        ml_addition_status=ml_status,
        ml_addition_note=ml_note,
        ml_addition_classifications=addition_classifications,
        remaining_budget_after_rules=remaining_slots,
        candidate_isolation=candidate_check,
        scope_diagnostics=scope_diagnostics,
        records=records,
        ordering='35-rule alert groups by event UTC then record ID/revision; ML descending score then event UTC and ID/revision; simultaneous groups kept atomic',
        selection_uses_feedback=False,
        mandatory_routing_approved=False,
        operational_queue_changed=False,
    )


def _ml_basis_label(record):
    if record['rule_eval_completeness'] == 'partial_rule_source_gap':
        return 'partial_rule_source_gap'
    if record['rule_eval_completeness'] == 'all_applicable_evaluated':
        return 'all_applicable_rules_evaluated_no_hit'
    return record['rule_eval_completeness']


def rule35_report_for(plan, cases, *, redaction='technical'):
    """Render technical or Portal-redacted evaluation report from a locked 35-rule plan."""
    if redaction not in ('technical', 'review'):
        raise ValueError("redaction must be 'technical' or 'review'")
    lookup = {identity(c): c for c in cases}
    records = {identity(r): r for r in plan['records']}
    if set(lookup) != set(records):
        fail(503, 'COMPARISON_CASE_BINDING', 'Nguồn phiếu không còn khớp kế hoạch 35 luật đã khóa.',
             'Mở đúng bản dữ liệu và lần phân tích đã khóa.')

    def entries(keys, arm_name):
        output = []
        for rank, key in enumerate(keys, start=1):
            r = records[tuple(key)]
            c = lookup[tuple(key)]
            review = c['review']
            f = review['feedback'] or {}
            is_rule = r['rule_state'] == 'alert'
            item = dict(
                rank=rank,
                record_id=r['record_id'],
                revision=r['revision'],
                case_id=c['case_id'],
                amount_vnd=c['amount_vnd'],
                kind=r['kind'],
                event_at=r['event_at'],
                rule_state=r['rule_state'],
                rule_eval_completeness=r['rule_eval_completeness'],
                selection_source='rule35_baseline' if is_rule else 'ml_backfill',
                reason='rule35_alert' if is_rule else _ml_basis_label(r),
                unavailable_rule_ids=list(r['unavailable_rule_ids']),
                not_applicable_rule_ids=list(r['not_applicable_rule_ids']),
                master_quality_hits=list(r['master_quality_hits']),
                master_quality_dedup_count=r['master_quality_dedup_count'],
                context_hits=list(r['context_hits']),
                review_revision=review['revision'],
                outcome=f.get('outcome'),
                usefulness=f.get('usefulness'),
                active_seconds=review['active_seconds'] if review['feedback'] is not None else None,
            )
            if arm_name in ('added', 'combined') and not is_rule:
                item['ml_addition_basis'] = _ml_basis_label(r)
            if redaction == 'technical':
                item['actionable_hit_rules'] = list(r['actionable_hit_rules'])
                item['batch_event_ids'] = list(r['batch_event_ids'])
                item['ml_method'] = r['ml_method']
                item['ml_score'] = r['ml_score']
            output.append(item)
        return output

    baseline = arm_metrics(plan['baseline'], lookup)
    combined = arm_metrics(plan['combined'], lookup)
    added = arm_metrics(plan['added'], lookup)
    removed = arm_metrics(plan['removed'], lookup)

    delta_known = added['resolved'] == added['selected'] and removed['resolved'] == removed['selected']
    usefulness_known = added['usefulness_assessed'] == added['selected'] and removed['usefulness_assessed'] == removed['selected']
    added_items = entries(plan['added'], 'added')
    ml_added_clean_no_hit = sum(i.get('ml_addition_basis') == 'all_applicable_rules_evaluated_no_hit' for i in added_items)
    ml_added_source_gap = sum(i.get('ml_addition_basis') == 'partial_rule_source_gap' for i in added_items)

    # Deduplicate shared B5/E4 evidence keys across candidate dataset level.
    b5_e4_master_count = sum(1 for r in records.values() if r['master_quality_hits'])
    b5_e4_dedup_total = len({dk for r in records.values() for dk in r.get('master_quality_dedup_keys', [])})

    clean_rule_eval_count = sum(r['rule_eval_completeness'] == 'all_applicable_evaluated' for r in records.values())
    partial_gap_count = sum(r['rule_eval_completeness'] == 'partial_rule_source_gap' for r in records.values())
    full_unavail_count = sum(r['rule_state'] == 'unavailable' for r in records.values())
    ml_avail_count = sum(r['ml_available'] for r in records.values())
    ml_unavail_count = sum(not r['ml_available'] for r in records.values())
    both_clean = {k for k, r in records.items() if r['ml_available'] and r['rule_eval_completeness'] == 'all_applicable_evaluated'}
    both_evaluable_or_alert = {
        k for k, r in records.items()
        if r['ml_available'] and (r['rule_state'] == 'alert' or r['rule_eval_completeness'] == 'all_applicable_evaluated')
    }

    pins = dict(
        version=plan['version'],
        policy=plan['policy'],
        budget=plan['budget'],
        run_id=plan['run_id'],
        analysis_id=plan['analysis_id'],
        analysis_context_id=plan['analysis_context_id'],
        company_id=plan['company_id'],
        tenant_id=plan.get('tenant_id'),
        snapshot_id=plan['snapshot_id'],
        snapshot_checksum=plan['snapshot_checksum'],
        result_sha256=plan['result_sha256'],
        feature_contract_fingerprint=plan.get('feature_contract_fingerprint'),
        baseline_rule_scope=plan['baseline_rule_scope'],
        implemented_rule_count=plan['implemented_rule_count'],
        ml_method=plan.get('ml_method'),
        he_execution=plan['he_execution'],
        as_of=plan['as_of'],
        period_start=plan['period_start'],
        period_end=plan['period_end'],
        created_at=plan['created_at'],
        simulated_data=plan['simulated_data'],
        design=plan['design'],
        reviews_present_before_lock=plan['reviews_present_before_lock'],
        prospective=False,
        unit='transaction',
        operational_queue_changed=False,
    )
    if redaction == 'technical':
        pins['model_pin'] = deepcopy(plan.get('model_pin'))
        pins['candidate_isolation'] = deepcopy(plan.get('candidate_isolation'))

    value = dict(
        version=VERSION,
        status='technical_only' if redaction == 'technical' else 'review_summary',
        label_status='insufficient_verified_labels' if combined['resolved'] == 0 else 'human_declared_feedback_only',
        plan=pins,
        baseline=dict(metrics=baseline, transactions=entries(plan['baseline'], 'baseline')),
        combined=dict(metrics=combined, transactions=entries(plan['combined'], 'combined')),
        added=added_items,
        removed=entries(plan['removed'], 'removed'),
        deferred_rule_alerts=entries(plan['deferred_rule_alerts'], 'deferred'),
        ml_addition_summary=dict(
            status=plan['ml_addition_status'],
            note=plan['ml_addition_note'],
            remaining_slots_after_rules=plan['remaining_budget_after_rules'],
            added_count=len(added_items),
            added_after_all_applicable_rules_no_hit=ml_added_clean_no_hit,
            added_with_partial_rule_source_gap=ml_added_source_gap,
        ),
        delta=dict(
            added_transactions=len(added_items),
            declared_problem_transactions=(added['declared_problem_transactions'] or 0) - (removed['declared_problem_transactions'] or 0) if delta_known else None,
            declared_useful_transactions=(added['declared_useful_transactions'] or 0) - (removed['declared_useful_transactions'] or 0) if usefulness_known else None,
            attributed_connected_seconds=(
                round((combined['saved_connected_seconds'] or 0.0) - (baseline['saved_connected_seconds'] or 0.0), 3)
                if baseline['effort_complete'] and combined['effort_complete'] else None
            ),
            timing_measurement_basis='shared_transaction_review_attribution_not_independent_arms',
        ),
        coverage=dict(
            total_candidates=len(records),
            rules_all_applicable_evaluated=clean_rule_eval_count,
            rules_partial_source_gap=partial_gap_count,
            rules_unavailable=full_unavail_count,
            rules_actionable_alerts=sum(r['rule_state'] == 'alert' for r in records.values()),
            ml_available=ml_avail_count,
            ml_unavailable=ml_unavail_count,
            both_clean_available=len(both_clean),
            both_evaluable_or_alert=len(both_evaluable_or_alert),
            master_quality_candidate_rows=b5_e4_master_count,
            master_quality_dedup_groups=b5_e4_dedup_total,
            scope_diagnostics=deepcopy(plan.get('scope_diagnostics', [])),
        ),
        common_coverage=dict(
            cohort_size=len(both_evaluable_or_alert),
            selection_recomputed=False,
            baseline=arm_metrics([k for k in plan['baseline'] if tuple(k) in both_evaluable_or_alert], lookup),
            combined=arm_metrics([k for k in plan['combined'] if tuple(k) in both_evaluable_or_alert], lookup),
        ),
        overlap=dict(
            shared=len(set(map(tuple, plan['baseline'])) & set(map(tuple, plan['combined']))),
            added=len(plan['added']),
            removed=len(plan['removed']),
            known_simultaneous_alert_groups=sum(1 for g in plan['rule_groups'] if len(g) >= 2),
            deferred_alert_count=len(plan['deferred_rule_alerts']),
        ),
        feedback_revisions=[dict(case_id=c['case_id'], revision=c['review']['revision']) for c in cases],
        generated_at=datetime.now(timezone.utc).isoformat(),
        new_scoring_performed=False,
        model_fit_performed=False,
        limitations=[
            'Synthetic/offline-fit evaluation without ground-truth fraud labels; review outcomes remain unverified until human completion.',
            'Full-snapshot 35-rule + 33-feature ML bridge runs in enterprise-local mode (he_execution=False); not end-to-end HE.',
            'Budget is capped at 5 transaction slots; rules-only keeps <5 unused rather than randomly padding.',
            'Simultaneous batch alert groups (P1/A1/A2/A3/A4) stay indivisible; components exceeding remaining slots are deferred as a whole.',
            'Scope diagnostics (D1-D6, F4) and master-quality links (B5/E4/E3, deduplicated) stay separate and never auto-promote to row alerts.',
            'Shared transactions reuse one ReviewStore record; connected active time delta attributes effort and is not a blinded timing trial.',
        ],
    )
    value['report_sha256'] = digest(canonical(value))
    return value
