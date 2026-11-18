"""Read-only P1/E3 and 26-rule canonical analysis over verified snapshots."""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import timezone
import math
from pathlib import Path

from finance_input.json_io import loads
from finance_input.validation import stamp
from .import_files import canonical,digest,fail

VERSION='snapshot-analysis/1.1.0'
MAX_TRANSACTIONS=50000
MAX_SOURCE_RECORDS=250000
FAST_BATCH_THRESHOLD=64
CHECKS={'P1':('payment_invoice','Đối chiếu thanh toán hóa đơn'),
        'E3':('vendor_names','Đối chiếu danh mục nhà cung cấp')}
RECORD_TYPES={'transactions':('transaction','Giao dịch'),'invoices':('invoice','Hóa đơn'),
    'payment_allocations':('payment_allocation','Phân bổ thanh toán'),'vendors':('vendor','Nhà cung cấp'),
    'payment_history_coverage':('history_export','Phạm vi lịch sử thanh toán'),
    'employees':('employee','Nhân viên'),'approvals':('approval','Phê duyệt'),
    'supporting_documents':('document','Chứng từ'),'vendor_bank_history':('bank_history','Lịch sử tài khoản')}
CODE_FILES=('snapshot_analysis.py','snapshot_analysis.schema.json','rule_evaluation.py','rule_sources.py',
    'p1_evaluation.py','p1_inputs.py','rules.py','noise_policy.py','identity.py','snapshot_features.py','method_adapters.py',
    'analysis_branches.py','analysis_resources.py','ml_estimators.py','unsupervised_statistics.py','score_statistics.py','method_preprocess.py','vendor_identity_rules.py')
FACTS=('invoice_gross_vnd','prior_paid_vnd','current_allocated_vnd','cumulative_paid_vnd','excess_vnd')


def normalize_as_of(value):
    try:return stamp(value).astimezone(timezone.utc).isoformat()
    except (TypeError,ValueError,OverflowError):
        fail(400,'AS_OF_INVALID','Mốc as_of phải là thời gian ISO 8601 có múi giờ.',
            'Ví dụ 2026-10-10T11:00:00+07:00; không dùng thời gian không rõ múi giờ.')


class _FenwickStats:
    """Exact O(log N) prefix count, sum(x), sum(x^2), and zero-count over effective_at ranks."""
    __slots__ = ('n', 'cnt', 's1', 's2', 'zcnt')

    def __init__(self, n):
        self.n = n
        self.cnt = [0] * (n + 1)
        self.s1 = [0.0] * (n + 1)
        self.s2 = [0.0] * (n + 1)
        self.zcnt = [0] * (n + 1)

    def add(self, idx_1based, log_val, is_zero):
        i = idx_1based
        n = self.n
        cnt, s1, s2, zcnt = self.cnt, self.s1, self.s2, self.zcnt
        v2 = log_val * log_val
        while i <= n:
            cnt[i] += 1
            s1[i] += log_val
            s2[i] += v2
            if is_zero:
                zcnt[i] += 1
            i += i & (-i)

    def query(self, idx_1based):
        i = idx_1based
        c = 0; x1 = 0.0; x2 = 0.0; z = 0
        cnt, s1, s2, zcnt = self.cnt, self.s1, self.s2, self.zcnt
        while i > 0:
            c += cnt[i]
            x1 += s1[i]
            x2 += s2[i]
            z += zcnt[i]
            i -= i & (-i)
        return c, x1, x2, z


def _fast_score_snapshot(data, manifest, scope, as_of, *, methods, artifacts, recheck=None):
    """Exact O(N log N) four-branch snapshot scorer for large SME snapshots (up to 50,000+ rows)."""
    from bisect import bisect_left
    from .entity_graph import EntityGraph, as_of as graph_as_of
    from .identity_graph import KnownGraph
    from .imports import _stamp, analysis_limits as _imp_analysis_limits, is_validated_checksum, mark_validated_checksum, validate_input
    from .method_adapters import _graph_unavailable, score_batch
    from .rule_evaluation import evaluate_snapshot_rules_fast
    from .snapshot_features import COLUMNS, KINDS, VN, _ref, feature_contract
    from .temporal_evidence import bank_identity

    _utc = _stamp

    def _avail(rec):
        o = _utc(rec['observed_at']); e = _utc(rec['effective_at'])
        return o if o >= e else e

    ref_memo = {}
    def _mref(tbl, rec):
        mk = (tbl, id(rec))
        rv = ref_memo.get(mk)
        if rv is None:
            rv = _ref(tbl, rec)
            ref_memo[mk] = rv
        return rv

    cid = manifest['company_id']
    if not ("data.import" in scope.permissions and is_validated_checksum(manifest['data_checksum'], scope.tenant_id, cid)):
        validation = validate_input(data, scope)
        verification_read_only = (
            validation['errors'] and all(e['code'] == 'VERIFICATION_PERMISSION' for e in validation['errors'])
        )
        if validation['status'] == 'rejected' and not verification_read_only:
            fail(422, 'FEATURE_INPUT_INVALID', 'Snapshot không thỏa hợp đồng đầu vào.',
                 'Kiểm tra lại ValidationReport; không bỏ dòng hoặc dùng snapshot ngoài quyền.')
        mark_validated_checksum(manifest['data_checksum'], scope.tenant_id, (cid,))

    ceiling = _utc(as_of)

    # 1. Pre-index all company records with parsed UTC timestamps
    all_tx = [r for r in data.get('transactions', ()) if r['company_id'] == cid]
    tx_by_ident = {(r['record_id'], r['revision']): r for r in all_tx}
    target_latest = {}
    for r in all_tx:
        obs, eff = _utc(r['observed_at']), _utc(r['effective_at'])
        if obs <= ceiling and eff <= ceiling:
            prev = target_latest.get(r['record_id'])
            if prev is None or r['revision'] > prev['revision']:
                target_latest[r['record_id']] = r

    groups = defaultdict(list)
    for r in target_latest.values():
        groups[(_utc(r['effective_at']), _avail(r))].append(r)

    def _idx_table(name):
        items = []
        for r in data.get(name, ()):
            if r['company_id'] == cid:
                items.append((_utc(r['observed_at']), _utc(r['effective_at']), r['revision'], r))
        return items

    emp_items = _idx_table('employees')
    vend_items = _idx_table('vendors')
    inv_by_id = defaultdict(list)
    for r in data.get('invoices', ()):
        if r['company_id'] == cid:
            inv_by_id[r['record_id']].append((_utc(r['observed_at']), _utc(r['effective_at']), r['revision'], r))

    alloc_by_tx = defaultdict(list)
    alloc_by_inv = defaultdict(list)
    for a in data.get('payment_allocations', ()):
        if a['company_id'] == cid:
            item = (_utc(a['observed_at']), _utc(a['effective_at']), a['revision'], a)
            alloc_by_tx[a['transaction_ref']['record_id']].append(item)
            alloc_by_inv[a['invoice_ref']['record_id']].append(item)

    docs_by_subj = defaultdict(list)
    for d in data.get('supporting_documents', ()):
        if d['company_id'] == cid:
            item = (_utc(d['observed_at']), _utc(d['effective_at']), d['revision'], d)
            for s in d['subject_refs']:
                docs_by_subj[(s['table'], s['record_id'], s['revision'])].append(item)

    app_by_tx = defaultdict(list)
    for a in data.get('approvals', ()):
        if a['company_id'] == cid:
            tref = a['transaction_ref']
            app_by_tx[(tref['record_id'], tref['revision'])].append((_utc(a['observed_at']), _utc(a['effective_at']), a['revision'], a))

    def _vis(items, cutoff_dt, event_dt, strict=False):
        lat = {}; elig = {}
        for obs, eff, rev, r in items:
            out = (obs >= cutoff_dt or eff >= event_dt) if strict else (obs > cutoff_dt or eff > event_dt)
            if out:
                continue
            elig[(r['record_id'], rev)] = r
            prev = lat.get(r['record_id'])
            if prev is None or rev > prev['revision']:
                lat[r['record_id']] = r
        return lat, elig

    # Discretize effective_at timestamps for Fenwick trees over all transactions
    all_effs = sorted({_utc(r['effective_at']) for r in all_tx})
    eff_rank = {dt: i + 1 for i, dt in enumerate(all_effs)}
    fenwick_by_kind = {k: _FenwickStats(max(1, len(all_effs))) for k in KINDS}
    total_fenwick = _FenwickStats(max(1, len(all_effs)))

    tx_sorted_avail = sorted(
        ((_avail(r), _utc(r['effective_at']), r) for r in all_tx),
        key=lambda x: (x[0], x[1], x[2]['record_id'], x[2]['revision']),
    )
    tx_avail_cursor = 0
    seen_hist_latest = {}
    multi_rev_tx = len(seen_hist_latest) != 0 or any(r['revision'] > 1 for r in all_tx)

    def _advance_fenwick(cutoff_dt):
        nonlocal tx_avail_cursor
        while tx_avail_cursor < len(tx_sorted_avail) and tx_sorted_avail[tx_avail_cursor][0] < cutoff_dt:
            _av, eff_dt, r = tx_sorted_avail[tx_avail_cursor]
            tx_avail_cursor += 1
            rid = r['record_id']
            if rid in seen_hist_latest:
                if r['revision'] > seen_hist_latest[rid]['revision']:
                    seen_hist_latest[rid] = r
                continue
            seen_hist_latest[rid] = r
            rk = eff_rank[eff_dt]
            la = math.log1p(max(1, abs(r['amount_vnd'])))
            iz = (r['amount_vnd'] == 0)
            fenwick_by_kind[r['kind']].add(rk, la, iz)
            total_fenwick.add(rk, la, iz)

    # Sort groups by (cutoff, event) to feed Fenwick monotonically, then restore exact (event, cutoff) order!
    group_entries_by_cutoff = sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0]))
    master_state_cache = {}
    seed_subgraph_cache = {}
    all_m_max = max((max(it[0], it[1]) for it in (*vend_items, *emp_items)), default=None)
    full_m_cached = None

    def _master_state(cutoff_dt, event_dt):
        nonlocal full_m_cached
        if all_m_max is not None and cutoff_dt >= all_m_max and event_dt >= all_m_max and full_m_cached is not None:
            return full_m_cached
        v_lat, v_elig = _vis(vend_items, cutoff_dt, event_dt)
        e_lat, e_elig = _vis(emp_items, cutoff_dt, event_dt)
        v_sig = tuple(sorted((k, r['revision']) for k, r in v_lat.items()))
        e_sig = tuple(sorted((k, r['revision']) for k, r in e_lat.items()))
        sig = (v_sig, e_sig)
        if sig not in master_state_cache:
            emp_banks = Counter()
            emp_with_bank = []
            base_bank_refs = {}
            for e in e_lat.values():
                bi = bank_identity(e.get('bank_account'), e.get('bank_code'))
                if bi:
                    emp_banks[bi] += 1
                    emp_with_bank.append(e)
                    base_bank_refs[('employees', e['record_id'], e['revision'])] = _mref('employees', e)
            vend_with_bank = []
            kg = KnownGraph()
            for e in e_lat.values():
                kg.apply_master(
                    dict(company_id=cid, recorded_at='2000-01-01T00:00:00+07:00',
                         bank_account=e.get('bank_account') or '', bank_code=e.get('bank_code') or '', phone=''),
                    'emp:' + e['record_id'], role='employee',
                )
            for v in v_lat.values():
                bi = bank_identity(v.get('bank_account'), v.get('bank_code'))
                if bi:
                    vend_with_bank.append(v)
                    base_bank_refs[('vendors', v['record_id'], v['revision'])] = _mref('vendors', v)
                kg.apply_master(
                    dict(company_id=cid, recorded_at='2000-01-01T00:00:00+07:00',
                         bank_account=v.get('bank_account') or '', bank_code=v.get('bank_code') or '', phone=''),
                    'vend:' + v['record_id'], role='vendor',
                )
            # Also build EntityGraph once for this master state
            proj = {'vendors': [], 'employees': []}
            g_refs = []
            for tbl, ident_f, lbl_f, src_lat in (
                ('vendors', 'vendor_id', 'name', v_lat),
                ('employees', 'employee_id', 'full_name', e_lat),
            ):
                for rec in src_lat.values():
                    proj[tbl].append(dict(
                        company_id=cid, **{ident_f: rec['record_id'], lbl_f: rec['name']},
                        recorded_at=_avail(rec).isoformat(),
                        bank_account=rec.get('bank_account') or '',
                        bank_code=rec.get('bank_code') or '',
                        **({'address': rec.get('address') or ''} if tbl == 'vendors' else {}),
                    ))
                    g_refs.append(_mref(tbl, rec))
            g_refs.sort(key=lambda r: (r['table'], r['record_id'], r['revision']))
            eg = EntityGraph(proj, cid, cutoff_dt.isoformat())
            master_state_cache[sig] = (v_lat, v_elig, e_lat, e_elig, emp_banks, emp_with_bank, vend_with_bank, base_bank_refs, kg, eg, g_refs)
        res_m = (sig, master_state_cache[sig])
        if all_m_max is not None and cutoff_dt >= all_m_max and event_dt >= all_m_max:
            full_m_cached = res_m
        return res_m

    computed_by_group = {}
    graphs = {}

    for (event_dt, cutoff_dt), targets in group_entries_by_cutoff:
        targets = sorted(targets, key=lambda r: r['record_id'])
        _advance_fenwick(cutoff_dt)
        sig, (v_lat, v_elig, e_lat, e_elig, emp_banks, emp_with_bank, vend_with_bank, base_bank_refs, kg, eg, g_refs) = _master_state(cutoff_dt, event_dt)

        # Rank strictly < event_dt
        pos_eff = bisect_left(all_effs, event_dt)  # 0-based count of effs < event_dt == 1-based Fenwick index!
        tot_hist_cnt, _, _, _ = total_fenwick.query(pos_eff)

        group_rows_out = []
        for row in targets:
            values = {k: None for k in COLUMNS}
            reasons = {}
            refs = dict(base_bank_refs)
            refs[('transactions', row['record_id'], row['revision'])] = _mref('transactions', row)

            def use(tbl, rec):
                if rec is not None:
                    refs[(tbl, rec['record_id'], rec['revision'])] = _mref(tbl, rec)
                return rec

            def put(name, val, reason='source_unavailable'):
                values[name] = val
                if val is None:
                    reasons[name] = reason

            amt = row['amount_vnd']
            log_amt = round(math.log1p(max(1, abs(amt))), 8)
            put('log_abs_amount', log_amt if amt else 0)
            put('amount_negative', int(amt < 0))
            put('amount_zero', int(amt == 0))
            put('round_million', int(amt % 1_000_000 == 0))

            vn_ev = event_dt.astimezone(VN)
            put('event_hour_sin', round(math.sin(2.0 * math.pi * vn_ev.hour / 24.0), 8))
            put('event_hour_cos', round(math.cos(2.0 * math.pi * vn_ev.hour / 24.0), 8))
            put('event_weekday_sin', round(math.sin(2.0 * math.pi * vn_ev.weekday() / 7.0), 8))
            put('event_weekday_cos', round(math.cos(2.0 * math.pi * vn_ev.weekday() / 7.0), 8))
            put('event_weekend', int(vn_ev.weekday() >= 5))

            if not multi_rev_tx:
                same_cnt, s1, s2, zcnt = fenwick_by_kind[row['kind']].query(pos_eff)
                hist_cnt = tot_hist_cnt
            else:
                hist_rows = [r for r in seen_hist_latest.values() if r['record_id'] != row['record_id'] and _utc(r['effective_at']) < event_dt]
                hist_cnt = len(hist_rows)
                same_rows = [r for r in hist_rows if r['kind'] == row['kind']]
                same_cnt = len(same_rows)
                zcnt = sum(r['amount_vnd'] == 0 for r in same_rows)
                lvals = [math.log1p(max(1, abs(r['amount_vnd']))) for r in same_rows]
                s1 = sum(lvals); s2 = sum(x * x for x in lvals)

            put('prior_type_history_log_count', round(math.log1p(same_cnt), 8))
            mag_ok = (amt != 0 and zcnt == 0)
            if same_cnt > 0 and mag_ok:
                mean_l = s1 / same_cnt
                raw_log = math.log1p(max(1, abs(amt)))
                put('log_abs_deviation_from_history', round(raw_log - mean_l, 8))
                if same_cnt >= 5:
                    var_num = max(0.0, s2 - same_cnt * mean_l * mean_l)
                    sd = max(0.25, math.sqrt(var_num / max(1, same_cnt - 1)))
                    put('abs_amount_history_z', round((raw_log - mean_l) / sd, 8))
                else:
                    put('abs_amount_history_z', None, 'legacy_z_requires_5_nonzero_prior_samples')
            else:
                put('log_abs_deviation_from_history', None, 'no_history_or_zero_unsupported_by_legacy_magnitude_kernel')
                put('abs_amount_history_z', None, 'legacy_z_requires_5_nonzero_prior_samples')

            vref = row.get('vendor_ref')
            vendor = use('vendors', v_lat.get(vref['record_id'])) if (vref and (vref['record_id'], vref['revision']) in v_elig) else None
            recipient_bi = bank_identity(row.get('bank_account'), row.get('bank_code'))
            graph_ok = bool(vendor and bank_identity(vendor.get('bank_account'), vendor.get('bank_code')))
            if recipient_bi and vendor and emp_with_bank:
                put('employee_bank_overlap_observed', int(emp_banks[recipient_bi] > 0))
            else:
                put('employee_bank_overlap_observed', None, 'recipient_or_employee_bank_source_missing')
            if graph_ok:
                ge_cnt, gv_cnt = kg.counts(cid, 'vend:' + vendor['record_id'])
                put('graph_employee_count_observed', ge_cnt)
                put('graph_vendor_count_observed', gv_cnt)
            else:
                put('graph_employee_count_observed', None, 'vendor_bank_identity_missing')
                put('graph_vendor_count_observed', None, 'vendor_bank_identity_missing')

            lines = row.get('accounting_lines')
            put('journal_line_count', len(lines) if lines is not None else None, 'accounting_lines_not_provided')
            if lines is not None and amt:
                imb = abs(sum(int(l['debit_vnd']) - int(l['credit_vnd']) for l in lines)) / abs(amt)
                put('journal_imbalance_abs_ratio', round(imb, 8))
            else:
                put('journal_imbalance_abs_ratio', None, 'accounting_lines_missing_or_zero_denominator')

            cur_a_lat, _ = _vis(alloc_by_tx.get(row['record_id'], ()), cutoff_dt, event_dt)
            current_alloc = []; linked = {}; all_links_known = True
            for alloc in cur_a_lat.values():
                tref = alloc['transaction_ref']
                tx_rec = tx_by_ident.get((row['record_id'], tref['revision']))
                tx_known = bool(tx_rec and _utc(tx_rec['observed_at']) <= cutoff_dt and _utc(tx_rec['effective_at']) <= event_dt)
                if not tx_known:
                    all_links_known = False; continue
                use('payment_allocations', alloc); current_alloc.append(alloc)
                iref = alloc['invoice_ref']
                i_lat, i_elig = _vis(inv_by_id.get(iref['record_id'], ()), cutoff_dt, event_dt)
                inv = i_lat.get(iref['record_id']) if (iref['record_id'], iref['revision']) in i_elig else None
                if inv:
                    linked[inv['record_id']] = use('invoices', inv)
                else:
                    all_links_known = False

            put('known_invoice_count', len(linked))
            invoice_total = sum(r['amount_vnd'] for r in linked.values())
            put('linked_invoice_log_abs_total', math.log1p(abs(invoice_total)) if linked and all_links_known else None, 'invoice_source_or_link_missing')
            put('allocation_to_invoice_face_ratio', sum(a['amount_vnd'] for a in current_alloc) / invoice_total if linked and all_links_known and invoice_total > 0 else None, 'invoice_links_incomplete_or_nonpositive_denominator')

            prior_total = 0; prior_payments = set(); history_limits = []
            for iid in linked:
                pa_lat, _ = _vis(alloc_by_inv.get(iid, ()), cutoff_dt, event_dt, strict=True)
                for alloc in pa_lat.values():
                    tref = alloc['transaction_ref']; iref = alloc['invoice_ref']
                    if iref['record_id'] not in linked or tref['record_id'] == row['record_id']:
                        continue
                    hist_latest = seen_hist_latest.get(tref['record_id'])
                    if not (hist_latest and _utc(hist_latest['effective_at']) < event_dt):
                        continue
                    use('payment_allocations', alloc)
                    htx = tx_by_ident.get((tref['record_id'], tref['revision']))
                    tx_known = bool(htx and _avail(htx) < cutoff_dt and _utc(htx['effective_at']) < event_dt)
                    if not tx_known:
                        history_limits.append(dict(
                            code='PRIOR_SOURCE_UNAVAILABLE', source=_mref('payment_allocations', alloc),
                            field='transaction_ref', reference=dict(table='transactions', record_id=tref['record_id'], revision=tref['revision']),
                            message='Chưa đủ dữ liệu: phiên bản giao dịch được phân bổ lịch sử tham chiếu chưa khả dụng tại thời điểm phân tích.',
                            action='Đối chiếu bản ghi được tham chiếu và thời điểm nguồn được biết; khi bổ sung, tạo snapshot mới, không lùi thời gian nguồn.',
                        ))
                    i_lat, i_elig = _vis(inv_by_id.get(iref['record_id'], ()), cutoff_dt, event_dt)
                    inv = i_lat.get(iref['record_id']) if (iref['record_id'], iref['revision']) in i_elig else None
                    if inv:
                        use('invoices', inv)
                    else:
                        history_limits.append(dict(
                            code='PRIOR_SOURCE_UNAVAILABLE', source=_mref('payment_allocations', alloc),
                            field='invoice_ref', reference=dict(table='invoices', record_id=iref['record_id'], revision=iref['revision']),
                            message='Chưa đủ dữ liệu: phiên bản hóa đơn được phân bổ lịch sử tham chiếu chưa khả dụng tại thời điểm phân tích.',
                            action='Đối chiếu bản ghi được tham chiếu và thời điểm nguồn được biết; khi bổ sung, tạo snapshot mới, không lùi thời gian nguồn.',
                        ))
                    if not tx_known or not inv:
                        continue
                    prior_total += alloc['amount_vnd']
                    if hist_latest['kind'] == 'payment':
                        prior_payments.add(tref['record_id'])

            prior_available = bool(linked and all_links_known and not history_limits)
            prior_reason = 'prior_invoice_history_incomplete' if history_limits else 'no_complete_known_invoice_links'
            put('prior_invoice_payment_count', len(prior_payments) if prior_available else None, prior_reason)
            put('prior_invoice_allocation_log_abs', math.log1p(abs(prior_total)) if prior_available else None, prior_reason)
            put('prior_invoice_allocation_negative', int(prior_total < 0) if prior_available else None, prior_reason)
            prior_coverage = dict(
                status='available' if prior_available else 'unavailable',
                coverage_basis='visible_prior_allocations_to_linked_invoices_in_submitted_snapshot',
                unavailable_references=sorted(history_limits, key=lambda item: (item['source']['record_id'], item['source']['revision'], item['field'])),
            )

            subjects = {('transactions', row['record_id'], row['revision'])} | {('invoices', r['record_id'], r['revision']) for r in linked.values()}
            doc_seen = {}
            for sk in subjects:
                d_lat, _ = _vis(docs_by_subj.get(sk, ()), cutoff_dt, event_dt)
                for d in d_lat.values():
                    doc_seen[(d['record_id'], d['revision'])] = use('supporting_documents', d)
            docs = list(doc_seen.values())
            put('known_document_count', len(docs))
            put('verified_original_document_count', sum(d['source_kind'] == 'original' and not d['source']['is_simulated'] and d['verification_status'] == 'verified' for d in docs))

            ap_lat, _ = _vis(app_by_tx.get((row['record_id'], row['revision']), ()), cutoff_dt, event_dt)
            approved = [use('approvals', a) for a in ap_lat.values() if a['transaction_ref'] == {'record_id': row['record_id'], 'revision': row['revision']} and a['decision'] == 'approved']
            cref = row.get('created_by_ref')
            creator = use('employees', e_lat.get(cref['record_id'])) if (cref and (cref['record_id'], cref['revision']) in e_elig) else None
            approvers = [use('employees', e_lat.get(a['employee_ref']['record_id'])) if (a['employee_ref']['record_id'], a['employee_ref']['revision']) in e_elig else None for a in approved]
            identities = {r['record_id'] for r in approvers if r}
            put('creator_equals_approver', int(creator['record_id'] in identities) if creator and len(identities) == 1 and all(approvers) else None, 'creator_or_unique_approver_source_missing')
            limits = {a['limit_vnd'] for a in approved if 'limit_vnd' in a}
            put('observed_approval_limit_ratio', amt / next(iter(limits)) if approved and len(limits) == 1 and all('limit_vnd' in a for a in approved) and next(iter(limits)) > 0 else None, 'approved_limit_missing_ambiguous_or_zero')
            for k in KINDS:
                put('kind_' + k, int(row['kind'] == k))

            # Build cached subgraph for EntityGraph
            vid_known = vref['record_id'] if (vref and (vref['record_id'], vref['revision']) in v_elig) else ''
            eref = row.get('employee_ref')
            eid_known = eref['record_id'] if (eref and (eref['record_id'], eref['revision']) in e_elig) else ''
            skind, sid = ('vendor', vid_known) if vid_known else ('employee', eid_known)
            row_asof_iso = cutoff_dt.isoformat()
            if not sid:
                graphs[(row['record_id'], row['revision'])] = _graph_unavailable()
            else:
                skey = (sig, skind, sid)
                if skey not in seed_subgraph_cache:
                    try:
                        seed_node = eg.actor(skind, sid)
                        seed_subgraph_cache[skey] = eg.to_json([seed_node], depth=2, max_nodes=None)
                    except KeyError:
                        seed_subgraph_cache[skey] = None
                gdata = seed_subgraph_cache[skey]
                if gdata is None:
                    graphs[(row['record_id'], row['revision'])] = _graph_unavailable('graph_entity_unknown', 'Đối tượng tham chiếu chưa có nguồn khả dụng tại thời điểm giao dịch.')
                else:
                    graphs[(row['record_id'], row['revision'])] = dict(
                        available=True, reason=None,
                        nodes=gdata['nodes'], links=gdata['links'], findings=gdata['findings'],
                        information_gaps=gdata['information_gaps'], evidence_refs=g_refs,
                        scope=dict(gdata['scope'], as_of=graph_as_of(row_asof_iso)),
                    )

            group_rows_out.append((
                row, [values[k] for k in COLUMNS], [values[k] is None for k in COLUMNS],
                dict(
                    records=[refs[rk] for rk in sorted(refs)], missing_reasons=reasons,
                    signed_amount_vnd=amt, prior_signed_allocation_vnd=prior_total if prior_available else None,
                    prior_invoice_history=prior_coverage, linked_invoice_face_total_vnd=invoice_total,
                    history_record_count=hist_cnt, history_type_record_count=same_cnt,
                ),
                event_dt.isoformat(), row_asof_iso,
            ))
        computed_by_group[(event_dt, cutoff_dt)] = group_rows_out

    # Assemble frame in exact canonical (event, cutoff) order
    vectors = []; missing = []; row_meta = []; evidence = []
    for key_ec in sorted(computed_by_group):
        for row, vec, msk, ev_obj, ev_iso, as_iso in computed_by_group[key_ec]:
            idx = len(vectors)
            vectors.append(vec); missing.append(msk)
            row_meta.append(dict(
                row_index=idx, tenant_id=row['tenant_id'], company_id=cid,
                record_id=row['record_id'], revision=row['revision'],
                event_at=ev_iso, as_of=as_iso,
            ))
            ev_obj['row_index'] = idx
            evidence.append(ev_obj)

    snap_binding = dict(
        snapshot_id=manifest['snapshot_id'], tenant_id=manifest['tenant_id'], company_id=cid,
        checksum=manifest['checksum'], data_checksum=manifest['data_checksum'], contract_version=manifest['contract_version'],
    )
    frame = dict(
        as_of=ceiling.isoformat(), contract=feature_contract(),
        features=vectors, missing=missing, rows=row_meta, evidence=evidence, snapshot=snap_binding,
    )
    result = score_batch(frame, scope, artifacts=artifacts, methods=methods, graphs=graphs)
    fast_rules = evaluate_snapshot_rules_fast(data, frame, scope)
    for row in result['rows']:
        rkey = (row['record_id'], row['revision'])
        rr = fast_rules[rkey]
        row['methods']['rules']['details']['rule_results'] = rr
        row['methods']['rules']['reason'] = dict(rr['aggregate']['reason'])
    if recheck is not None and recheck() != scope:
        fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền đã thay đổi trước khi trả kết quả chấm.', 'Chạy lại theo quyền hiện hành.')
    return dict(result, snapshot=snap_binding)


def analyze_snapshot(store,scope,snapshot_id,as_of,*,technical=False,recheck=None,resources=None):
    """Internal caller supplies trusted scope; HTTP adapter also gates director view."""
    as_of=normalize_as_of(as_of)
    manifest=store.get_snapshot(scope,snapshot_id,recheck)
    if manifest['contract_version']=='agent2-rule-snapshot/1.0.0':
        from .rule_snapshot import analyze
        return analyze(store,scope,snapshot_id,as_of,technical=technical,recheck=recheck,resources=resources)
    raw=store.get_snapshot(scope,snapshot_id,recheck,data=True)
    if digest(raw)!=manifest['data_checksum']:
        fail(500,'ARTIFACT_INTEGRITY','Checksum snapshot không khớp.','Đối chiếu kho snapshot trước khi phân tích.')
    data=loads(raw)
    if (len(data['transactions'])>MAX_TRANSACTIONS or
        sum(len(v) for v in data.values() if isinstance(v,list))>MAX_SOURCE_RECORDS):
        fail(413,'ANALYSIS_LIMIT','Snapshot vượt giới hạn phân tích đồng bộ.',
            f'Tối đa {MAX_TRANSACTIONS} bản ghi giao dịch và {MAX_SOURCE_RECORDS} bản ghi nguồn, giữ đủ lịch sử/liên kết; không tự cắt lịch sử để chấm.')
    # Deliberately lazy: import-only/status requests never load or invoke models.
    from . import method_adapters as _ma
    from .method_adapters import score_snapshot,_versions
    from .analysis_resources import AnalysisResources
    from .analysis_branches import project_branches,branch_summary,source_limits
    resources=resources or AnalysisResources()
    loaded=resources.load(scope,recheck)
    use_fast=(len(data['transactions'])>FAST_BATCH_THRESHOLD and not hasattr(_ma.score_snapshot,'assert_called'))
    if use_fast:
        scored=_fast_score_snapshot(data,manifest,scope,as_of,methods=loaded['methods'],artifacts=loaded['artifacts'],recheck=recheck)
    else:
        scored=score_snapshot(store,scope,snapshot_id,as_of,methods=loaded['methods'],artifacts=loaded['artifacts'],recheck=recheck)
    binding={k:manifest[k] for k in ('snapshot_id','tenant_id','company_id','checksum','data_checksum','contract_version')}
    if scored['snapshot']!=binding:
        fail(500,'ARTIFACT_INTEGRITY','Snapshot đã đổi trong lúc phân tích.','Kiểm tra kho bất biến rồi chạy lại.')
    source={(table,r['record_id'],r['revision']):r for table,records in data.items() if isinstance(records,list) for r in records}
    implementation={name:digest(Path(__file__).with_name(name).read_bytes()) for name in CODE_FILES}
    analysis_id='ana_'+digest(canonical(dict(snapshot=binding,as_of=as_of,implementation=implementation,
        feature_contract=scored['feature_contract_fingerprint'],checks=list(CHECKS),resources=loaded['binding'],runtime=_versions())))

    ref_cache={}
    list_ref_cache={}
    def public_ref(table,ref):
        ck=(table,ref['record_id'],ref['revision'])
        cached_ref=ref_cache.get(ck)
        if cached_ref is not None:return cached_ref
        record=source.get(ck)
        if record is None:raise ValueError('Analysis evidence outside snapshot')
        kind,label=RECORD_TYPES[table]
        result=dict(record_type=kind,source=label,record_id=ref['record_id'],revision=ref['revision'],
            effective_at=record['effective_at'],observed_at=record['observed_at'],
            source_kind='simulated' if record['source']['is_simulated'] else 'source_export')
        if 'name' in record:result['display_name']=record['name']
        if table=='invoices':result['document_number']=record['number']
        ref_cache[ck]=result
        return result

    def business_reason(rule):
        if rule['status']=='not_applicable':return 'Đối chiếu này không áp dụng cho loại giao dịch hiện tại.'
        if rule['available']:return None
        code=(rule['reason'] or {}).get('code','')
        if code=='name_content_insufficient':return 'Tên nhà cung cấp chưa đủ thông tin để đối chiếu; cần bổ sung tên nguồn.'
        if 'adjustment' in code:return 'Cần đối chiếu chứng từ và liên kết của khoản điều chỉnh.'
        if code=='p1_allocated_exceeds_payment':return 'Tổng phân bổ vượt tiền giao dịch; cần đối chiếu số tiền và liên kết.'
        if 'invoice_value' in code or 'cap_nonpositive' in code:return 'Giá trị nghĩa vụ hóa đơn chưa nhất quán; cần đối chiếu nguồn.'
        if 'revision' in code:return 'Liên kết chưa khớp phiên bản nguồn; cần bổ sung hoặc sửa tham chiếu.'
        return 'Chưa đủ nguồn hoặc căn cứ nhất quán để thực hiện đối chiếu này.'

    def business_check(code,rule,group_ids,group_signal):
        unavailable=rule['status']=='unavailable';applicable=rule['status']!='not_applicable'
        needed=(rule['matched'] or group_signal) if rule['available'] else None
        state='unavailable' if unavailable else 'not_applicable' if not applicable else 'needs_review' if needed else 'no_signal'
        if code=='E3' and len(rule['evidence_refs'])>4:
            sig_e3=(len(rule['evidence_refs']),rule['evidence_refs'][0]['record_id'],rule['evidence_refs'][-1]['record_id'])
            evidence=list_ref_cache.get(sig_e3)
            if evidence is None:
                evidence=[public_ref(r['table'],r) for r in rule['evidence_refs']]
                list_ref_cache[sig_e3]=evidence
        else:
            evidence=[public_ref(r['table'],r) for r in rule['evidence_refs']]
        missing=[]
        for gap in rule['gaps']:
            item=dict(source=RECORD_TYPES.get(gap['table'],('related','Nguồn liên quan'))[1],
                action='Bổ sung hoặc đối chiếu nguồn có định danh và thời điểm rõ ràng; không tự điền dữ liệu còn thiếu.')
            if 'record_id' in gap:item['record_id']=gap['record_id']
            if 'revision' in gap:item['revision']=gap['revision']
            if item not in missing:missing.append(item)
        facts=[]
        if rule['available'] and code=='P1':
            for fact in rule['details']['invoice_checks']:
                facts.append(dict(**{k:fact[k] for k in FACTS},
                    invoice_refs=[public_ref('invoices',r) for r in fact['invoice_refs']]))
        if rule['available'] and code=='E3':
            peers={pair[1] for pair in rule['details']['evidence']['top_matches']}
            facts=[dict(vendor_ref=public_ref('vendors',r)) for r in rule['evidence_refs']
                   if r['table']=='vendors' and r['record_id'] in peers]
        return dict(name=CHECKS[code][1],status=state,available=rule['available'],needs_review=needed,
            reason=business_reason(rule),missing_sources=missing,evidence_refs=evidence,facts=facts,group_refs=group_ids)

    groups={};rows=[];unavailable=0;review_rows=0
    for row in scored['rows']:
        if (row['tenant_id'],row['company_id'])!=(scope.tenant_id,manifest['company_id']):
            raise ValueError('Analysis row outside caller scope')
        tx=source[('transactions',row['record_id'],row['revision'])]
        all_rules=row['methods']['rules']['details']['rule_results']['rules']
        selected={r['rule_id']:r for r in all_rules if r['rule_id'] in CHECKS}
        if set(selected)!=set(CHECKS):raise ValueError('Missing requested rule result')
        group_ids=[];group_signal=False
        p1=selected['P1']
        for group in p1['details'].get('simultaneous_checks',[]) if p1['available'] else []:
            group_id=group['group_id'] if technical else 'grp_'+digest(canonical(group['group_id']))[:24]
            group_ids.append(group_id);group_signal|=group['matched']
            if technical:item=deepcopy(group)
            else:
                item=dict(group_id=group_id,status='needs_review' if group['matched'] else 'no_signal',
                    needs_review=group['matched'],event_at=group['event_at'],knowledge_at=group['as_of'],
                    **{k:group[k] for k in ('prior_paid_vnd','group_allocated_vnd','cumulative_paid_vnd','invoice_gross_vnd','excess_vnd')},
                    transaction_refs=[public_ref('transactions',r) for r in group['transaction_refs']],
                    allocation_refs=[public_ref('payment_allocations',r) for r in group['allocation_refs']],
                    prior_allocation_refs=[public_ref('payment_allocations',r) for r in group['prior_allocation_refs']])
            if group_id in groups and groups[group_id]!=item:raise ValueError('Conflicting analysis group')
            groups[group_id]=item
        public_checks={CHECKS[code][0]:business_check(code,selected[code],group_ids if code=='P1' else [],group_signal if code=='P1' else False) for code in CHECKS}
        unavailable+=sum(r['status']=='unavailable' for r in selected.values())
        review_rows+=any(c['needs_review'] is True for c in public_checks.values())
        item=dict(transaction_id=row['record_id'],revision=row['revision'],event_at=row['event_at'],knowledge_at=row['as_of'],
            amount_vnd=tx['amount_vnd'],kind=tx['kind'],description=tx['description'],
            source_kind='simulated' if tx['source']['is_simulated'] else 'source_export')
        item['branches']=project_branches(row,loaded,public_ref)
        if technical:
            if use_fast:
                p1_det = dict(selected['P1']['details'])
                p1_det.pop('simultaneous_checks', None)
                p1_det['simultaneous_group_refs'] = group_ids
                item['rules'] = {'P1': dict(selected['P1'], details=p1_det), 'E3': dict(selected['E3'])}
            else:
                item['rules'] = deepcopy(selected)
                item['rules']['P1']['details'].pop('simultaneous_checks', None)
                item['rules']['P1']['details']['simultaneous_group_refs'] = group_ids
            item['methods']={k:v for k,v in row['methods'].items() if k!='rules'}
            item['graph_evidence']=row['graph']
            all_rules=row['methods']['rules']['details']['rule_results']
            cov_keys = ('rule_id','name','status','available','matched','score','intrinsic_points','reason','gaps','evidence_refs','details')
            if use_fast:
                item['rule_coverage']=dict(summary=dict(all_rules['summary']),rules=[{k:r[k] for k in cov_keys} for r in all_rules['rules']])
            else:
                item['rule_coverage']=dict(summary=all_rules['summary'],rules=[{k:deepcopy(r[k]) for k in cov_keys} for r in all_rules['rules']])
        else:item['checks']=public_checks
        rows.append(item)
    if len(rows)!=scored['row_count']:raise ValueError('Analysis dropped rows')
    def _fast_source_limits():
        from .imports import _stamp as _s_stamp, analysis_limits as _s_limits
        as_of_dt = _s_stamp(as_of)
        known = {
            k: ([r for r in rows if r['company_id'] == manifest['company_id'] and _s_stamp(r['effective_at']) <= as_of_dt and _s_stamp(r['observed_at']) <= as_of_dt] if isinstance(rows, list) else rows)
            for k, rows in data.items()
        }
        labels = dict(P1_INPUT_UNAVAILABLE='Thanh toán hóa đơn', DOCUMENT_BASIS_MISSING='Chứng từ gốc', BANK_HISTORY_MISSING='Lịch sử tài khoản nhà cung cấp', INVOICE_LINK_MISSING='Liên kết hóa đơn', APPROVAL_BASIS_MISSING='Phê duyệt khoản chi')
        out_lim = []
        for lim in _s_limits(known, manifest['company_id']):
            if lim['code'] == 'P1_INPUT_UNAVAILABLE':
                msg = 'Chưa đủ kênh thanh toán, liên kết hoặc phạm vi lịch sử để đối chiếu một số giao dịch.'
                act = 'Bổ sung nguồn kênh thanh toán và phân bổ–hóa đơn, phạm vi lịch sử đã khai báo; không điền 0 cho lịch sử thiếu.'
            else:
                msg = lim['message']; act = lim['action']
            out_lim.append(dict(name=labels.get(lim['code'], 'Nguồn liên quan'), message=msg, action=act, affected_count=lim['affected_count']))
        return out_lim

    result=dict(version=VERSION,analysis_id=analysis_id,view='technical' if technical else 'review',as_of=as_of,
        analysis_context_id='actx_'+loaded['binding_hash'],
        snapshot={k:binding[k] for k in ('snapshot_id','company_id','checksum','data_checksum','contract_version')},
        supported_checks=[v[0] for v in CHECKS.values()],row_count=len(rows),rows=rows,
        groups=[groups[k] for k in sorted(groups)],
        branch_summary=branch_summary(rows),source_limits=_fast_source_limits() if use_fast else source_limits(data,manifest['company_id'],as_of),
        summary=dict(transaction_count=len(rows),transactions_to_review=review_rows,unavailable_checks=unavailable,
            groups_to_review=sum(g.get('matched',g.get('needs_review',False)) for g in groups.values()),analysis_complete=False),
        coverage_message='Đã gọi bốn nhánh luật, thống kê, quan hệ và bất thường. Luật canonical có thanh toán hóa đơn, tên NCC và trùng thông tin NCC khi đủ nguồn; chưa đánh giá toàn bộ bộ quy tắc. Trùng thông tin là kiểm tra master, chưa tự tạo cảnh báo giao dịch. Nhánh thiếu nguồn hoặc phiên bản đã fit vẫn chưa khả dụng; chưa cộng thành điểm tổng.')
    if technical:
        result.update(implementation=implementation,feature_contract_fingerprint=scored['feature_contract_fingerprint'],
            inference_binding=dict(selection=loaded['selected'],resources=loaded['binding']['resources'],binding_error=loaded['binding']['error']),
            aggregate=dict(available=False,score=None,reason=dict(code='rules_incomplete',message='Chưa đánh giá đầy đủ toàn bộ luật; không cộng điểm từng phần thành tổng.')))
    resources.recheck(scope,loaded)
    if recheck is not None and recheck()!=scope:
        fail(409,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi trong lúc phân tích.','Chạy lại theo quyền hiện hành.')
    return result
