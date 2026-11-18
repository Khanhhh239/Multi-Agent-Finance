"""Unified multi-group FHE coordinator helpers for `agent2-rule-snapshot/1.0.0`.

Supports staged Concrete execution across the verified rule-snapshot slices:
  1. `P1` (`rules` circuit)
  2. `C3` (`c3` circuit)
  3. `B1` and unified `B5`/`E4` (`graph` circuit)

Unencrypted statistical/ML branches (`statistics`, `ml` 33-feature bridge) and
the remaining 30 local rules explicitly report `unavailable` on HE runs rather
than running incompatible canonical circuits or falling back to plaintext.
"""
from copy import deepcopy
from sme_fraud.authority_policy import ApprovalAuthority
from sme_fraud.import_files import canonical, digest, fail
from sme_fraud.native_rule_node import validate_bundle
from sme_fraud.rule_snapshot import CONTRACT as RULE_SNAPSHOT_CONTRACT, validate as validate_rule_snapshot
from sme_fraud.snapshot_features import utc
from .rule_snapshot_adapter import decode_p1_plan_results, plan_p1_from_rule_snapshot
from .rule_snapshot_c3_adapter import (
    _metadata_authority_candidates,
    decode_c3_plan_results,
    plan_c3_from_rule_snapshot,
)
from .rule_snapshot_identity_adapter import (
    decode_b1_plan_results,
    decode_b5_e4_plan_results,
    plan_b1_from_rule_snapshot,
    plan_b5_e4_from_rule_snapshot,
)
from .rule_snapshot_extended_adapter import (
    decode_a6_plan_results,
    decode_c2_plan_results,
    decode_statistics_plan_results,
    plan_a6_from_rule_snapshot,
    plan_c2_from_rule_snapshot,
    plan_statistics_from_rule_snapshot,
)

RULE_SNAPSHOT_RESULT_VERSION = 'he-rule-snapshot-groups-result/1.0.0'
COVERED_RULES = ('P1', 'C3', 'B1', 'B5', 'E4')
EXTENDED_COVERED_RULES = ('P1', 'A6', 'C2', 'C3', 'B1', 'B5', 'E4')
TOTAL_RULE_COUNT = 35

_GROUP_LABELS = {
    'p1': 'P1 - Thanh toán vượt giá trị hóa đơn',
    'a6': 'A6 - Thanh toán làm tròn vượt hóa đơn gốc',
    'c2': 'C2 - Tự duyệt vượt quyền được cấp',
    'c3': 'C3 - Phê duyệt nhanh dưới 60 giây',
    'b1': 'B1 - Tài khoản/định danh NCC trùng nhân viên',
    'b5_e4': 'B5/E4 - Nhà cung cấp dùng chung định danh',
}

_REASON_TEXT = {
    'transaction_not_known_at_cutoff': 'Giao dịch chưa được ghi nhận/hạch toán tại thời điểm cắt dữ liệu.',
    'rule_not_applicable_to_source_kinds': 'Luật không áp dụng cho loại giao dịch này.',
    'source_not_supplied': 'Thiếu bảng nguồn bắt buộc.',
    'source_coverage_missing': 'Thiếu khai báo phạm vi/độ đầy đủ của nguồn.',
    'source_coverage_incomplete': 'Nguồn dữ liệu chưa đầy đủ (coverage incomplete).',
    'history_before_window_unknown': 'Chưa đủ lịch sử giao dịch từ đầu kỳ (since_inception).',
    'invoice_value_unavailable': 'Thiếu giá trị hóa đơn trên giao dịch thanh toán NCC.',
    'invoice_identity_not_provided': 'Thiếu số hóa đơn định danh.',
    'invoice_not_available_at_cutoff': 'Hóa đơn chưa phát hành tại thời điểm giao dịch.',
    'invoice_history_not_available_at_cutoff': 'Lịch sử thanh toán trước đó chưa khả dụng tại thời điểm giao dịch.',
    'simultaneous_invoice_gross_gap': 'Các giao dịch cùng thời điểm trên cùng hóa đơn có giá trị hóa đơn mâu thuẫn.',
    'signed_amount_policy_not_supported': 'Giao dịch âm (điều chỉnh/hoàn) không thuộc miền áp dụng của luật này.',
    'he_p1_source_limit': 'Số giao dịch trước đó hoặc cùng thời điểm vượt giới hạn 4 dòng của mạch HE P1.',
    'he_p1_nonpositive_prior_unsupported': 'Tồn tại thanh toán trước đó <= 0 không thuộc miền hỗ trợ mạch HE P1.',
    'he_a6_domain_limit': 'Số tiền hoặc hóa đơn vượt miền số nguyên an toàn của mạch HE A6.',
    'approved_authority_source_missing': 'Thiếu bảng thẩm quyền hoặc phạm vi hiệu lực phê duyệt.',
    'authority_not_covered_or_ambiguous_at_action': 'Không có phạm vi thẩm quyền rõ ràng hoặc nhiều quy tắc xung đột tại thời điểm duyệt.',
    'actor_role_not_known_for_authority_scope': 'Chưa rõ vai trò người duyệt và chưa có quy tắc thẩm quyền khớp.',
    'he_c2_authority_limit': 'Số quy tắc thẩm quyền tự duyệt ứng viên vượt giới hạn 4 dòng của mạch HE C2.',
    'he_c2_domain_limit': 'Số tiền vượt miền số nguyên an toàn của mạch HE C2.',
    'he_c3_authority_limit': 'Số quy tắc thẩm quyền ứng viên vượt giới hạn 4 dòng của mạch HE C3.',
    'he_c3_domain_limit': 'Thời gian hoặc số tiền vượt miền số nguyên an toàn của mạch HE C3.',
    'recipient_bank_identity_incomplete': 'Có tài khoản nhận tiền nhưng thiếu mã ngân hàng để định danh.',
    'he_graph_node_limit': 'Số thực thể (nhân viên/NCC) vượt giới hạn 4 nút của mạch HE đồ thị.',
    'identity_field_unknown': 'Trường định danh liên hệ của NCC bị thiếu hoặc chưa chuẩn hóa được.',
    'he4_key_not_provisioned': 'Chưa cấp khóa HE cho doanh nghiệp và mạch xử lý tương ứng.',
    'artifact_not_pinned': 'Doanh nghiệp chưa ghim artifact thống kê RobustZ tương thích.',
    'he_statistics_column_count_unsupported': 'Mạch HE thống kê hiện hỗ trợ model RobustZ 2 biến; không cắt cột từ model nhiều biến.',
    'rule_snapshot_he_unsupported': 'Nhánh này hiện chạy local trên dữ liệu gốc; chưa có mạch HE tương ứng cho profile 35 luật.',
}


def _explain(group_key: str, entry: dict) -> str:
    label = _GROUP_LABELS[group_key]
    status = entry.get('status')
    reason = entry.get('reason')
    if status == 'not_applicable':
        return f'{label}: {_REASON_TEXT.get(reason, "Không áp dụng cho loại giao dịch này.")}'
    if not entry.get('available'):
        return f'{label}: Chưa thể kết luận ({_REASON_TEXT.get(reason, reason or "thiếu nguồn hoặc vượt miền HE")}).'
    if status == 'evaluated_hit':
        if group_key == 'p1':
            row_check = entry.get('row_check') or {}
            if row_check.get('matched'):
                return f"{label}: Cần đối chiếu — lũy kế {row_check.get('cumulative_paid_vnd')} VND vượt hóa đơn {row_check.get('invoice_gross_vnd')} VND."
            return f'{label}: Cần đối chiếu nhóm thanh toán đồng thời vượt giá trị hóa đơn.'
        if group_key == 'a6':
            det = entry.get('details') or {}
            return f"{label}: Cần đối chiếu — khoản thanh toán tròn nghìn {det.get('payment_vnd')} VND vượt hóa đơn lẻ {det.get('invoice_gross_vnd')} VND (+{det.get('difference_vnd')} VND)."
        if group_key == 'c2':
            return f'{label}: Cần đối chiếu — người lập đồng thời tự duyệt vượt quyền/hạn mức được cấp.'
        if group_key == 'c3':
            det = entry.get('details') or {}
            sec = round((det.get('approval_delta_us') or 0) / 1_000_000, 3)
            return f'{label}: Cần đối chiếu — thời gian duyệt {sec} giây (< 60 giây) với thẩm quyền cao/trọng yếu.'
        if group_key == 'b1':
            if entry.get('matched_employee_ids'):
                return f"{label}: Cần đối chiếu — trùng định danh với nhân viên {', '.join(entry['matched_employee_ids'])}."
            return f"{label}: Bổ sung ngữ cảnh — nghi vấn trùng tài khoản thiếu mã ngân hàng với nhân viên {', '.join(entry.get('ambiguous_employee_ids') or [])}."
        fields = sorted((entry.get('shared_fields') or {}).keys())
        return f"{label}: Cần đối chiếu thông tin dùng chung giữa các NCC theo trường: {', '.join(fields)}."
    return f'{label}: Đã kiểm tra qua FHE, chưa thấy tín hiệu bất thường.'


def _row_evidence_refs(tx: dict | None, visible_txs: dict[str, dict], tables: dict, as_of: str) -> list[dict]:
    if tx is None:
        return []
    cutoff = tx['posted_at']
    cid = tx['company_id']
    refs: list[tuple[str, str, str]] = [('transactions', tx['transaction_id'], tx['observed_at'])]
    seen = set(refs)

    def add(table: str, record_id: str, observed_at: str) -> None:
        key = (table, record_id, observed_at)
        if key not in seen and observed_at <= as_of:
            seen.add(key)
            refs.append(key)

    inv = str(tx.get('invoice_number') or '').strip()
    if inv and tx.get('vendor_id'):
        for other in visible_txs.values():
            if (
                other.get('company_id') == cid
                and other.get('vendor_id') == tx.get('vendor_id')
                and str(other.get('invoice_number') or '').strip() == inv
                and other['posted_at'] <= cutoff
            ):
                add('transactions', other['transaction_id'], other['observed_at'])

    for doc in tables.get('transaction_documents', []):
        if doc.get('transaction_id') == tx['transaction_id'] and doc.get('observed_at', '') <= cutoff:
            doc_id = str(doc.get('document_id') or doc.get('record_id') or digest(canonical(doc)))
            add('transaction_documents', doc_id, doc['observed_at'])

    visible_vendors = sorted(
        (
            r
            for r in tables.get('vendors', [])
            if r.get('company_id') == cid and r.get('observed_at', '') <= cutoff
        ),
        key=lambda r: (r['observed_at'], r['vendor_id']),
    )
    latest_vendors: dict[str, dict] = {}
    for rec in visible_vendors:
        latest_vendors[rec['vendor_id']] = rec
    for rec in sorted(latest_vendors.values(), key=lambda r: r['vendor_id']):
        if len(latest_vendors) <= 4 or rec['vendor_id'] == tx.get('vendor_id'):
            add('vendors', rec['vendor_id'], rec['observed_at'])

    visible_staff = sorted(
        (
            r
            for r in tables.get('employees', [])
            if r.get('company_id') == cid and r.get('observed_at', '') <= cutoff
        ),
        key=lambda r: (r['observed_at'], r['employee_id']),
    )
    latest_staff: dict[str, dict] = {}
    for rec in visible_staff:
        latest_staff[rec['employee_id']] = rec
    relevant_emp = {tx.get('creator_id'), tx.get('approver_id'), tx.get('employee_id')}
    for rec in sorted(latest_staff.values(), key=lambda r: r['employee_id']):
        if len(latest_staff) <= 4 or rec['employee_id'] in relevant_emp:
            add('employees', rec['employee_id'], rec['observed_at'])

    auth_time = tx.get('approved_at') or cutoff
    if auth_time <= as_of:
        authority = ApprovalAuthority(
            dict(
                employees=[r for r in tables.get('employees', []) if r.get('observed_at', '') <= auth_time],
                approval_authorities=[r for r in tables.get('approval_authorities', []) if r.get('observed_at', '') <= auth_time],
                approval_authority_coverage=[
                    r for r in tables.get('approval_authority_coverage', []) if r.get('observed_at', '') <= auth_time
                ],
            )
        )
        cov = authority.covered(tx, 'approve', auth_time)
        if cov and cov.get('coverage_id') and not cov.get('ambiguous'):
            add('approval_authority_coverage', cov['coverage_id'], cov['observed_at'])
        elif not cov:
            for cov_row in tables.get('approval_authority_coverage', []):
                if cov_row.get('company_id') == cid and cov_row.get('observed_at', '') <= auth_time:
                    cid_ref = str(cov_row.get('coverage_id') or cov_row.get('record_id') or digest(canonical(cov_row)))
                    add('approval_authority_coverage', cid_ref, cov_row['observed_at'])
        approver = latest_staff.get(tx.get('approver_id', ''))
        if approver:
            for _, rule_rec in _metadata_authority_candidates(authority, tx, tx.get('approver_id', ''), approver, auth_time):
                aid_ref = str(rule_rec.get('authority_id') or rule_rec.get('record_id') or digest(canonical(rule_rec)))
                add('approval_authorities', aid_ref, rule_rec['observed_at'])

    return [dict(table=t, record_id=rid, observed_at=obs) for t, rid, obs in refs]


def prepare_rule_snapshot_he_plan(
    store,
    scope,
    snapshot_id: str,
    as_of: str,
    programs: dict,
    *,
    extended: bool = False,
    model_db=None,
    statistics_artifact: str | None = None,
    recheck=None,
) -> dict:
    """Plan staged multi-group HE execution from a locked rule snapshot."""
    manifest = store.get_snapshot(scope, snapshot_id, recheck)
    raw = store.get_snapshot(scope, snapshot_id, recheck, data=True)
    if digest(raw) != manifest['data_checksum']:
        fail(500, 'ARTIFACT_INTEGRITY', 'Checksum snapshot không khớp.', 'Đối chiếu kho nguồn.')
    from finance_input.json_io import loads

    data = loads(raw)
    if not isinstance(data, dict) or data.get('contract_version') != RULE_SNAPSHOT_CONTRACT:
        fail(422, 'RULE_SNAPSHOT_INVALID', 'Yêu cầu profile agent2-rule-snapshot/1.0.0.', 'Xuất lại đúng profile.')
    if data.get('tenant_id') != scope.tenant_id or data.get('company_id') != next(iter(scope.company_ids)):
        fail(403, 'ACCESS_DENIED', 'Snapshot ngoài phạm vi doanh nghiệp.', 'Chọn đúng doanh nghiệp.')
    if utc(as_of) != utc(data['source']['as_of']):
        fail(409, 'HE_AS_OF_MISMATCH', 'Mốc thời điểm không khớp as_of đã khóa trong snapshot.', 'Dùng đúng as_of của snapshot.')

    report = validate_rule_snapshot(data, scope, committed=True)
    if report['status'] == 'rejected':
        fail(422, 'RULE_SNAPSHOT_INVALID', 'Snapshot nguồn luật không hợp lệ.', 'Kiểm tra lại schema và coverage.')
    checked = validate_bundle(data['source'], scope)
    if checked['status'] != 'accepted':
        fail(422, 'NATIVE_RULE_SOURCE_INVALID', 'Bundle nguồn luật không hợp lệ.', 'Sửa lỗi nguồn.')

    for required_profile in ('rules', 'c3', 'graph'):
        if required_profile not in programs:
            fail(503, 'HE4_BUILD_MISSING', f'Thiếu mạch HE đã biên dịch cho profile {required_profile}.', 'Cấu hình đủ mạch rules, c3, graph.')

    candidate_ids = list(data['candidate_transaction_ids'])
    if extended:
        stage_order = ['p1', 'a6', 'c2', 'c3', 'b1', 'b5_e4']
        subplans = dict(
            p1=plan_p1_from_rule_snapshot(deepcopy(data), scope),
            a6=plan_a6_from_rule_snapshot(deepcopy(data), scope),
            c2=plan_c2_from_rule_snapshot(deepcopy(data), scope),
            c3=plan_c3_from_rule_snapshot(deepcopy(data), scope),
            b1=plan_b1_from_rule_snapshot(deepcopy(data), scope),
            b5_e4=plan_b5_e4_from_rule_snapshot(deepcopy(data), scope),
        )
        if 'statistics' in programs:
            subplans['statistics'] = plan_statistics_from_rule_snapshot(
                store,
                scope,
                snapshot_id,
                as_of,
                candidate_ids,
                model_db=model_db,
                statistics_artifact=statistics_artifact,
                recheck=recheck,
            )
            stage_order.append('statistics')
    else:
        stage_order = ['p1', 'c3', 'b1', 'b5_e4']
        subplans = dict(
            p1=plan_p1_from_rule_snapshot(deepcopy(data), scope),
            c3=plan_c3_from_rule_snapshot(deepcopy(data), scope),
            b1=plan_b1_from_rule_snapshot(deepcopy(data), scope),
            b5_e4=plan_b5_e4_from_rule_snapshot(deepcopy(data), scope),
        )

    for name, sp in subplans.items():
        if [r['transaction_id'] for r in sp['rows']] != candidate_ids:
            raise ValueError(f'subplan row alignment mismatch for {name}')

    tasks: list[dict] = []
    dedup: dict[str, int] = {}
    for stage_name in stage_order:
        sp = subplans[stage_name]
        for entry in sp['rows']:
            task_indexes: list[int] = []
            for req in entry.get('requests', []):
                profile = req['profile']
                signature = digest(canonical(dict(profile=profile, program=programs[profile], values=req['values'])))
                if signature not in dedup:
                    dedup[signature] = len(tasks)
                    tasks.append(
                        dict(
                            profile=profile,
                            rule_group=stage_name,
                            values=req['values'],
                            context=None,
                            packet=None,
                            response=None,
                            result=None,
                        )
                    )
                task_indexes.append(dedup[signature])
            entry['task_indexes'] = task_indexes

    source = data['source']
    cutoff = source['as_of']
    tables = source['tables']
    visible_txs = {
        r['transaction_id']: r
        for r in tables.get('transactions', [])
        if r.get('observed_at', '') <= cutoff and r.get('posted_at', '') <= cutoff
    }
    rows_meta = []
    for cid in candidate_ids:
        tx = visible_txs.get(cid)
        if tx is not None:
            rows_meta.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    revision=1,
                    known_at_cutoff=True,
                    txn_type=tx.get('txn_type'),
                    posted_at=tx.get('posted_at'),
                    observed_at=tx.get('observed_at'),
                    amount_vnd=int(tx['amount_vnd']),
                    currency=tx.get('currency', 'VND'),
                    vendor_id=tx.get('vendor_id') or '',
                    employee_id=tx.get('employee_id') or '',
                    evidence_refs=_row_evidence_refs(tx, visible_txs, tables, cutoff),
                )
            )
        else:
            rows_meta.append(
                dict(
                    record_id=cid,
                    transaction_id=cid,
                    revision=1,
                    known_at_cutoff=False,
                    txn_type=None,
                    posted_at=None,
                    observed_at=None,
                    amount_vnd=None,
                    currency='VND',
                    vendor_id='',
                    employee_id='',
                    evidence_refs=[],
                )
            )

    plan = dict(
        version='he4-rule-snapshot-multi-plan/1.0.0',
        contract_version=RULE_SNAPSHOT_CONTRACT,
        company_id=data['company_id'],
        tenant_id=data['tenant_id'],
        snapshot_id=snapshot_id,
        snapshot_checksum=manifest['checksum'],
        data_checksum=manifest['data_checksum'],
        as_of=cutoff,
        source_sha256=digest(canonical(source)),
        rows=rows_meta,
        subplans=subplans,
    )
    if extended:
        plan['extended'] = True
    plan['plan_sha256'] = digest(canonical(plan))
    return dict(plan=plan, tasks=tasks)


def _decode_subplan(group_key: str, subplan: dict, tasks: list[dict]) -> list[dict]:
    decoders = dict(
        p1=decode_p1_plan_results,
        a6=decode_a6_plan_results,
        c2=decode_c2_plan_results,
        c3=decode_c3_plan_results,
        b1=decode_b1_plan_results,
        b5_e4=decode_b5_e4_plan_results,
        statistics=decode_statistics_plan_results,
    )
    decoder = decoders[group_key]
    ready_entries = []
    ready_outputs = []
    ready_positions = []
    unavailable_override: dict[int, str] = {}

    for pos, entry in enumerate(subplan['rows']):
        t_idxs = entry.get('task_indexes', [])
        executed = [tasks[i] for i in t_idxs]
        missing = next((t['unavailable'] for t in executed if t.get('unavailable')), None)
        if missing:
            unavailable_override[pos] = missing
        else:
            ready_entries.append({k: v for k, v in entry.items() if k != 'task_indexes'})
            for t in executed:
                ready_outputs.append(t['result'])
            ready_positions.append(pos)

    decoded_ready = decoder(dict(subplan, rows=ready_entries), ready_outputs)['rows'] if ready_entries else []
    mapped = [None] * len(subplan['rows'])
    for pos, res in zip(ready_positions, decoded_ready):
        mapped[pos] = res
    for pos, missing in unavailable_override.items():
        if group_key == 'statistics':
            mapped[pos] = dict(
                transaction_id=subplan['rows'][pos]['transaction_id'],
                method_id='robust_z',
                available=False,
                status='unavailable',
                raw_score=None,
                score=None,
                score_kind='empirical_midrank',
                reason=missing,
            )
        else:
            mapped[pos] = dict(
                transaction_id=subplan['rows'][pos]['transaction_id'],
                available=False,
                status='unavailable',
                matched=None,
                score=None,
                reason=missing,
            )
    return mapped


def assemble_rule_snapshot_he_result(job: str, request: dict, pending: dict, context: dict) -> dict:
    """Assemble final multi-group HE result + provenance + unsupported-branch disclosures."""
    plan = pending['plan']
    tasks = pending['tasks']
    subplans = plan['subplans']
    extended = bool(plan.get('extended'))
    rule_group_keys = ('p1', 'a6', 'c2', 'c3', 'b1', 'b5_e4') if extended else ('p1', 'c3', 'b1', 'b5_e4')
    covered_rules = EXTENDED_COVERED_RULES if extended else COVERED_RULES

    decoded_by_group = {
        group_key: _decode_subplan(group_key, subplans[group_key], tasks)
        for group_key in rule_group_keys
    }
    decoded_stats = (
        _decode_subplan('statistics', subplans['statistics'], tasks)
        if extended and 'statistics' in subplans
        else None
    )

    eval_key_hashes: dict[str, str] = {}
    key_epochs: dict[str, str] = {}
    for task in tasks:
        ctx = task.get('context') or {}
        prof = task['profile']
        if ctx.get('evaluation_keys_sha256'):
            eval_key_hashes[prof] = ctx['evaluation_keys_sha256']
        if ctx.get('key_epoch'):
            key_epochs[prof] = ctx['key_epoch']

    rows_out = []
    for idx, meta in enumerate(plan['rows']):
        groups_out = {}
        for group_key in rule_group_keys:
            plan_entry = subplans[group_key]['rows'][idx]
            dec = deepcopy(decoded_by_group[group_key][idx])
            applicable = dec.get('status') != 'not_applicable'
            dec.setdefault('rule_id', 'B5/E4' if group_key == 'b5_e4' else group_key.upper())
            dec['applicable'] = applicable
            dec['profile'] = (
                'rules'
                if group_key == 'p1'
                else 'rules+c3'
                if group_key == 'a6'
                else 'c3'
                if group_key in ('c2', 'c3')
                else 'graph'
            )
            dec['gaps'] = deepcopy(plan_entry.get('gaps', []))
            dec['explanation'] = _explain(group_key, dec)
            if group_key == 'p1' and 'simultaneous_checks' in dec:
                dec['simultaneous_checks'] = deepcopy(dec['simultaneous_checks'])
            groups_out[group_key] = dec

        any_available = any(g.get('available') for g in groups_out.values())
        any_hit = any(g.get('available') and g.get('matched') for g in groups_out.values())
        all_not_applicable = all(g.get('status') == 'not_applicable' for g in groups_out.values())
        if not meta['known_at_cutoff']:
            row_status = 'unavailable'
            row_matched = None
            row_reason = 'transaction_not_known_at_cutoff'
        elif any_hit:
            row_status = 'evaluated_hit'
            row_matched = True
            row_reason = None
        elif any_available:
            row_status = 'evaluated_no_hit'
            row_matched = False
            row_reason = None
        elif all_not_applicable:
            row_status = 'not_applicable'
            row_matched = None
            row_reason = 'rule_not_applicable_to_source_kinds'
        else:
            row_status = 'unavailable'
            row_matched = None
            row_reason = next((g.get('reason') for g in groups_out.values() if g.get('reason')), 'rule_sources_unavailable')

        if decoded_stats is not None:
            stat_entry = deepcopy(decoded_stats[idx])
            if not stat_entry.get('available'):
                rc = stat_entry.get('reason') or 'rule_snapshot_he_unsupported'
                stat_entry['message'] = _REASON_TEXT.get(rc, str(rc))
            stat_branch = stat_entry
        else:
            stat_branch = dict(
                available=False,
                status='unavailable',
                reason='rule_snapshot_he_unsupported',
                message=_REASON_TEXT['rule_snapshot_he_unsupported'],
            )

        branches_out = {
            'p1': dict(groups_out['p1'], evidence_refs=deepcopy(meta['evidence_refs'])),
            **({k: deepcopy(groups_out[k]) for k in ('a6', 'c2')} if extended else {}),
            'c3': deepcopy(groups_out['c3']),
            'b1': deepcopy(groups_out['b1']),
            'b5_e4': deepcopy(groups_out['b5_e4']),
            'statistics': stat_branch,
            'ml': dict(
                available=False,
                status='unavailable',
                reason='rule_snapshot_he_unsupported',
                model=None,
                raw_score=None,
                probability=False,
                message=_REASON_TEXT['rule_snapshot_he_unsupported'],
            ),
        }

        rows_out.append(
            dict(
                record_id=meta['record_id'],
                transaction_id=meta['transaction_id'],
                revision=meta['revision'],
                known_at_cutoff=meta['known_at_cutoff'],
                txn_type=meta['txn_type'],
                posted_at=meta['posted_at'],
                observed_at=meta['observed_at'],
                amount_vnd=meta['amount_vnd'],
                currency=meta['currency'],
                available=any_available,
                status=row_status,
                matched=row_matched,
                reason=row_reason,
                score=max((int(g.get('score') or 0) for g in groups_out.values() if g.get('available')), default=None),
                raw_score=stat_branch.get('raw_score') if stat_branch.get('available') else None,
                groups=groups_out,
                branches=branches_out,
                unsupported_summary=dict(
                    covered_he_rules=list(covered_rules),
                    covered_rule_count=len(covered_rules),
                    total_rule_count=TOTAL_RULE_COUNT,
                    unencrypted_rule_count=TOTAL_RULE_COUNT - len(covered_rules),
                    ml_bridge_he_supported=False,
                    statistics_he_supported=bool(decoded_stats is not None),
                    reason='rule_snapshot_he_unsupported',
                ),
            )
        )

    provenance = dict(
        snapshot_id=request['snapshot_id'],
        snapshot_checksum=plan['snapshot_checksum'],
        data_checksum=plan['data_checksum'],
        as_of=plan['as_of'],
        source_sha256=plan['source_sha256'],
        plan_sha256=plan['plan_sha256'],
        implementation_sha256=context['implementation_sha256'],
        builds={
            profile: dict(circuit_sha256=info['circuit_sha256'], specs_sha256=info['specs_sha256'])
            for profile, info in sorted(context['programs'].items())
        },
        evaluation_keys_sha256_by_profile=eval_key_hashes,
        key_epochs_by_profile=key_epochs,
        covered_he_rules=list(covered_rules),
        covered_rule_count=len(covered_rules),
        total_rule_count=TOTAL_RULE_COUNT,
    )

    return dict(
        version=RULE_SNAPSHOT_RESULT_VERSION,
        contract_version=RULE_SNAPSHOT_CONTRACT,
        run_id=job,
        company_id=plan['company_id'],
        tenant_id=plan['tenant_id'],
        snapshot_id=request['snapshot_id'],
        snapshot_checksum=plan['snapshot_checksum'],
        data_checksum=plan['data_checksum'],
        as_of=plan['as_of'],
        status='completed',
        row_count=len(rows_out),
        rows=rows_out,
        plan_sha256=plan['plan_sha256'],
        source_sha256=plan['source_sha256'],
        provenance=provenance,
        aggregation=dict(
            available=False,
            score=None,
            reason='No approved ensemble weights or mandatory routing; encrypted rule groups, remaining local rules, and 33-feature ML stay separate.',
        ),
    )
