"""Point-in-time 33-feature bridge for agent2-rule-snapshot/1.0.0 sources.

Preserves canonical snapshot-point-in-time/1.1.0 column ordering and missing
semantics where native-rule-source/1.0.0 supplies equivalent tables/clocks,
and emits explicit null values + missing_reasons where native lacks required
source structures (e.g. invoices, payment_allocations, approver-confirmed
transaction limits, or per-document source_kind). Never alters source data,
never invents 0 or bank codes, and never touches snapshot_features.py or
method_adapters.py hashes.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path

from finance_input.json_io import loads
from .entity_graph import EntityGraph
from .import_files import canonical, digest, fail
from .method_adapters import _scope
from .native_rule_node import validate_bundle
from .snapshot_features import COLUMNS, utc
from .spec_policy import bank_identity

VERSION = 'rule-snapshot-point-in-time/1.0.0'
SOURCE_CONTRACT = 'agent2-rule-snapshot/1.0.0'
NATIVE_PROFILE = 'native-rule-source/1.0.0'
BASE_CONTRACT_VERSION = 'snapshot-point-in-time/1.1.0'
VN = timezone(timedelta(hours=7))

# Explicit, 1-to-1 documented mapping from native txn_type to canonical KINDS.
# Other native txn_types keep 0 on all six canonical one-hot indicators and
# preserve their native group key when computing prior_type_history features.
NATIVE_KIND_MAP = {
    'payment': 'payment',
    'vendor_payment': 'payment',
    'receipt': 'receipt',
    'customer_receipt': 'receipt',
    'payroll': 'payroll',
    'transfer': 'transfer',
    'adjustment': 'adjustment',
    'reversal': 'reversal',
}

CANONICAL_KINDS = ('payment', 'receipt', 'payroll', 'transfer', 'adjustment', 'reversal')

UNMAPPED_COLUMNS = {
    'verified_original_document_count': 'document_source_kind_absent_in_native_profile',
    'known_invoice_count': 'invoice_allocation_tables_absent_in_native_profile',
    'linked_invoice_log_abs_total': 'invoice_allocation_tables_absent_in_native_profile',
    'allocation_to_invoice_face_ratio': 'invoice_allocation_tables_absent_in_native_profile',
    'prior_invoice_payment_count': 'invoice_allocation_tables_absent_in_native_profile',
    'prior_invoice_allocation_log_abs': 'invoice_allocation_tables_absent_in_native_profile',
    'prior_invoice_allocation_negative': 'invoice_allocation_tables_absent_in_native_profile',
    'observed_approval_limit_ratio': 'approver_confirmed_limit_absent_in_native_profile',
}

COLUMN_SPECS = {
    'log_abs_amount': 'log1p(abs(transactions.amount_vnd)); signed VND kept separate in evidence',
    'amount_negative': '1 if transactions.amount_vnd < 0 else 0; signed source amount retained in evidence',
    'amount_zero': '1 if transactions.amount_vnd == 0 else 0',
    'round_million': '1 if transactions.amount_vnd % 1_000_000 == 0 else 0',
    'event_hour_sin': 'sin(2pi * vn_hour / 24) from transactions.posted_at (+07:00)',
    'event_hour_cos': 'cos(2pi * vn_hour / 24) from transactions.posted_at (+07:00)',
    'event_weekday_sin': 'sin(2pi * vn_weekday / 7) from transactions.posted_at (+07:00)',
    'event_weekday_cos': 'cos(2pi * vn_weekday / 7) from transactions.posted_at (+07:00)',
    'event_weekend': '1 if vn_weekday in (5, 6) else 0 from transactions.posted_at (+07:00)',
    'prior_type_history_log_count': 'log1p(count) of strictly prior same-group txs on both clocks; requires transactions coverage=complete and since_inception',
    'log_abs_deviation_from_history': 'log1p(abs(amount)) - mean(prior nonzero same-group log_abs); null if <1 prior or zero amount or incomplete coverage',
    'abs_amount_history_z': '(log_abs - mean) / max(0.25, sd_ddof1); null if <5 nonzero prior or zero amount or incomplete coverage',
    'employee_bank_overlap_observed': '1 if vendor bank_identity(account,code) matches active observed employee at cutoff; null if missing code/coverage',
    'graph_employee_count_observed': 'Distinct active observed employees at cutoff sharing vendor bank_identity; null if missing bank_code/coverage',
    'graph_vendor_count_observed': 'Distinct active observed vendors at cutoff sharing vendor bank_identity incl self; null if missing bank_code/coverage',
    'journal_line_count': 'Count of journal_lines joined by transaction_id with observed_at<=cutoff and posted_at<=event_at; null if absent/incomplete',
    'journal_imbalance_abs_ratio': 'abs(debit - credit) / abs(amount_vnd) across joined journal_lines; null if absent or amount_vnd==0',
    'known_document_count': 'Count of transaction_documents joined by transaction_id with observed_at<=cutoff; never reads tx.support_doc_count',
    'verified_original_document_count': 'Always null: native transaction_documents lacks source_kind=original metadata',
    'known_invoice_count': 'Always null: native-rule-source/1.0.0 has no invoices/payment_allocations relational tables',
    'linked_invoice_log_abs_total': 'Always null: native-rule-source/1.0.0 has no invoices/payment_allocations relational tables',
    'allocation_to_invoice_face_ratio': 'Always null: native-rule-source/1.0.0 has no invoices/payment_allocations relational tables',
    'prior_invoice_payment_count': 'Always null: native-rule-source/1.0.0 has no invoices/payment_allocations relational tables',
    'prior_invoice_allocation_log_abs': 'Always null: native-rule-source/1.0.0 has no invoices/payment_allocations relational tables',
    'prior_invoice_allocation_negative': 'Always null: native-rule-source/1.0.0 has no invoices/payment_allocations relational tables',
    'creator_equals_approver': '1 if non-empty creator_id == approver_id with observed approved_at<=cutoff else 0; null if unobserved',
    'observed_approval_limit_ratio': 'Always null: native has no per-transaction approver-attested limit table; tx.approval_limit_vnd is maker limit',
    **{f'kind_{kind}': f'One-hot indicator for NATIVE_KIND_MAP[txn_type] == {kind}; unmapped native types receive 0' for kind in CANONICAL_KINDS},
}


def feature_contract():
    """Return immutable 33-column contract bound to this bridge implementation."""
    contract = dict(
        version=VERSION,
        source_contract=SOURCE_CONTRACT,
        native_profile=NATIVE_PROFILE,
        base_contract_version=BASE_CONTRACT_VERSION,
        columns=list(COLUMNS),
        descriptions=dict(COLUMN_SPECS),
        dtype='float64',
        nullable=True,
        missing='parallel boolean matrix; null never implicitly imputed',
        timezone='Asia/Ho_Chi_Minh (+07:00) for calendar; aware UTC comparisons',
        timestamp_clock='transactions.posted_at as event_at; transactions.observed_at and master recorded_at as knowledge clock',
        unmapped_columns=dict(UNMAPPED_COLUMNS),
        native_kind_map=dict(NATIVE_KIND_MAP),
        predictor_exclusions=[
            'tenant_id', 'company_id', 'transaction_id', 'revision', 'snapshot_id', 'as_of',
            'rule_hits', 'rule_scores', 'labels', 'document IDs/hashes', 'support_doc_count',
            'invoice_number', 'invoice_gross_vnd', 'approval_limit_vnd', 'source_id', 'seed', 'template',
        ],
        bridge_sha256=digest(Path(__file__).read_bytes()),
    )
    contract['fingerprint'] = digest(canonical(contract))
    return contract


def _cov_status(coverage, table):
    claim = coverage.get(table)
    return isinstance(claim, dict) and claim.get('status') == 'complete'


def _history_complete(coverage):
    claim = coverage.get('transactions')
    return isinstance(claim, dict) and claim.get('status') == 'complete' and claim.get('history_basis') == 'since_inception'


def _latest_masters(rows, id_field, company, row_cutoff):
    """Select latest observed master record per entity ID at cutoff, order-invariantly."""
    best = {}
    for row in rows:
        if row.get('company_id') != company:
            continue
        rec_dt = utc(row['recorded_at'])
        obs_dt = utc(row['observed_at'])
        if rec_dt > row_cutoff or obs_dt > row_cutoff:
            continue
        eid = row.get(id_field)
        if not eid:
            continue
        rank = (rec_dt, obs_dt, digest(canonical(row)))
        prev = best.get(eid)
        if prev is None or rank > prev[0]:
            best[eid] = (rank, row)
    return {eid: item[1] for eid, item in best.items()}


def _tx_revision(tx):
    if 'revision' not in tx:
        return 1, 'native_singleton_default_1'
    rev = tx['revision']
    if type(rev) is not int or rev < 1:
        fail(422, 'RULE_SNAPSHOT_INVALID', 'Revision giao dịch không hợp lệ.', 'Dùng số nguyên revision >= 1 từ nguồn.')
    return rev, 'source_field'


def _history_group(txn_type):
    mapped = NATIVE_KIND_MAP.get(txn_type)
    return mapped if mapped is not None else 'native:' + str(txn_type)


def _select_prior(cur, all_txs):
    """Return strictly prior same-group transactions across both clocks."""
    cur_id, cur_event, cur_cutoff, cur_group = cur['id'], cur['event_dt'], cur['cutoff_dt'], cur['group']
    prior = []
    for cand in all_txs:
        if cand['id'] == cur_id or cand['group'] != cur_group:
            continue
        if cand['event_dt'] < cur_event and cand['observed_dt'] < cur_cutoff:
            prior.append(cand)
    return prior


def _compute_row(item, all_txs, tables, coverage, tenant, company, cutoff_iso, *,
                 vendors_by_cutoff, employees_by_cutoff, jl_by_tx, docs_by_tx):
    tx = item['tx']
    tx_id = item['id']
    event_dt = item['event_dt']
    obs_dt = item['observed_dt']
    row_cutoff = item['cutoff_dt']
    amount = tx['amount_vnd']
    tx_complete = _cov_status(coverage, 'transactions')
    hist_complete = _history_complete(coverage)
    vendor_complete = _cov_status(coverage, 'vendors')
    emp_complete = _cov_status(coverage, 'employees')
    journal_complete = _cov_status(coverage, 'journal_lines')
    doc_complete = _cov_status(coverage, 'transaction_documents')

    values = {}
    reasons = {}
    records = [dict(
        table='transactions', record_id=tx_id, revision=item['revision'],
        revision_in_source='revision' in tx, revision_origin=item['revision_origin'],
        effective_at=tx['posted_at'], observed_at=tx['observed_at'],
        clock='posted_at', source_sha256=item['sha256'],
    )]

    def missing(col, reason):
        values[col] = None
        reasons[col] = reason

    if not tx_complete:
        for col in ('log_abs_amount', 'amount_negative', 'amount_zero', 'round_million',
                    'event_hour_sin', 'event_hour_cos', 'event_weekday_sin', 'event_weekday_cos', 'event_weekend',
                    'creator_equals_approver', *(f'kind_{k}' for k in CANONICAL_KINDS)):
            missing(col, 'transactions_coverage_missing_or_incomplete')
    else:
        values['log_abs_amount'] = round(math.log1p(abs(amount)), 8)
        values['amount_negative'] = 1 if amount < 0 else 0
        values['amount_zero'] = 1 if amount == 0 else 0
        values['round_million'] = 1 if amount % 1_000_000 == 0 else 0

        vn_event = event_dt.astimezone(VN)
        hour_rad = 2.0 * math.pi * (vn_event.hour / 24.0)
        wday_rad = 2.0 * math.pi * (vn_event.weekday() / 7.0)
        values['event_hour_sin'] = round(math.sin(hour_rad), 8)
        values['event_hour_cos'] = round(math.cos(hour_rad), 8)
        values['event_weekday_sin'] = round(math.sin(wday_rad), 8)
        values['event_weekday_cos'] = round(math.cos(wday_rad), 8)
        values['event_weekend'] = 1 if vn_event.weekday() in (5, 6) else 0

        mapped_kind = NATIVE_KIND_MAP.get(tx.get('txn_type'))
        for k in CANONICAL_KINDS:
            values[f'kind_{k}'] = 1 if mapped_kind == k else 0

        creator_id = tx.get('creator_id') or ''
        approver_id = tx.get('approver_id') or ''
        approved_at = tx.get('approved_at') or ''
        if creator_id and approver_id and approved_at and utc(approved_at) <= row_cutoff:
            values['creator_equals_approver'] = 1 if creator_id == approver_id else 0
        else:
            missing('creator_equals_approver', 'creator_or_unique_approver_source_missing')

    # History magnitude features (require complete + since_inception coverage).
    prior = _select_prior(item, all_txs) if hist_complete else []
    if not hist_complete:
        missing('prior_type_history_log_count', 'history_coverage_incomplete')
        missing('log_abs_deviation_from_history', 'history_coverage_incomplete')
        missing('abs_amount_history_z', 'history_coverage_incomplete')
    else:
        values['prior_type_history_log_count'] = round(math.log1p(len(prior)), 8)
        nonzero_logs = [math.log1p(abs(p['amount'])) for p in prior if p['amount'] != 0]
        if amount == 0 or not nonzero_logs:
            missing('log_abs_deviation_from_history', 'no_history_or_zero_unsupported_by_legacy_magnitude_kernel')
            missing('abs_amount_history_z', 'legacy_z_requires_5_nonzero_prior_samples')
        else:
            mu = sum(nonzero_logs) / len(nonzero_logs)
            cur_log = math.log1p(abs(amount))
            values['log_abs_deviation_from_history'] = round(cur_log - mu, 8)
            if len(nonzero_logs) >= 5:
                sd = math.sqrt(sum((x - mu) ** 2 for x in nonzero_logs) / (len(nonzero_logs) - 1))
                values['abs_amount_history_z'] = round((cur_log - mu) / max(0.25, sd), 8)
            else:
                missing('abs_amount_history_z', 'legacy_z_requires_5_nonzero_prior_samples')

    # Observed vendor/employee bank graph features (never default empty bank_code).
    vendor_id = tx.get('vendor_id') or ''
    if row_cutoff not in vendors_by_cutoff:
        vendors_by_cutoff[row_cutoff] = _latest_masters(tables.get('vendors', []), 'vendor_id', company, row_cutoff) if vendor_complete else {}
    if row_cutoff not in employees_by_cutoff:
        employees_by_cutoff[row_cutoff] = _latest_masters(tables.get('employees', []), 'employee_id', company, row_cutoff) if emp_complete else {}
    obs_vendors = vendors_by_cutoff[row_cutoff]
    obs_emps = employees_by_cutoff[row_cutoff]

    vendor_rec = obs_vendors.get(vendor_id) if (vendor_complete and vendor_id) else None
    if vendor_rec is not None:
        records.append(dict(
            table='vendors', record_id=vendor_id, revision=1,
            effective_at=vendor_rec['recorded_at'], observed_at=vendor_rec['observed_at'],
            source_sha256=digest(canonical(vendor_rec)),
        ))

    v_bank = bank_identity(vendor_rec.get('bank_account', ''), vendor_rec.get('bank_code', '')) if vendor_rec else ''
    tx_bank = bank_identity(tx.get('recipient_account', ''), tx.get('recipient_bank_code', '')) if tx_complete else ''
    # Strict: empty bank_code yields '' unless BANKSYN*; never fabricate bank match.
    if not (vendor_complete and emp_complete):
        missing('employee_bank_overlap_observed', 'vendor_or_employee_coverage_incomplete')
        missing('graph_employee_count_observed', 'vendor_or_employee_coverage_incomplete')
    elif not (v_bank or tx_bank):
        missing('employee_bank_overlap_observed', 'recipient_or_employee_bank_source_missing')
        missing('graph_employee_count_observed', 'vendor_bank_identity_missing')
    else:
        active_emp_banks = [
            (eid, e, bank_identity(e.get('bank_account', ''), e.get('bank_code', '')))
            for eid, e in sorted(obs_emps.items())
        ]
        overlap_target = v_bank or tx_bank
        emp_matches = [e for _, e, b in active_emp_banks if b and b == overlap_target]
        values['employee_bank_overlap_observed'] = 1 if emp_matches else 0
        for e in emp_matches:
            records.append(dict(
                table='employees', record_id=e['employee_id'], revision=1,
                effective_at=e['recorded_at'], observed_at=e['observed_at'],
                source_sha256=digest(canonical(e)),
            ))
        if not v_bank:
            missing('graph_employee_count_observed', 'vendor_bank_identity_missing')
        else:
            values['graph_employee_count_observed'] = len([1 for _, _, b in active_emp_banks if b == v_bank])

    if not vendor_complete:
        missing('graph_vendor_count_observed', 'vendors_coverage_incomplete')
    elif not v_bank:
        missing('graph_vendor_count_observed', 'vendor_bank_identity_missing')
    else:
        values['graph_vendor_count_observed'] = len([
            1 for v in obs_vendors.values()
            if bank_identity(v.get('bank_account', ''), v.get('bank_code', '')) == v_bank
        ])

    # Accounting lines (journal_lines joined by transaction_id).
    if not journal_complete:
        missing('journal_line_count', 'journal_lines_coverage_incomplete')
        missing('journal_imbalance_abs_ratio', 'journal_lines_coverage_incomplete')
    else:
        jlines = [
            r for r in jl_by_tx.get(tx_id, ())
            if r.get('company_id') == company and utc(r['observed_at']) <= row_cutoff and utc(r['posted_at']) <= event_dt
        ]
        if not jlines:
            missing('journal_line_count', 'accounting_lines_not_provided')
            missing('journal_imbalance_abs_ratio', 'accounting_lines_missing_or_zero_denominator')
        else:
            values['journal_line_count'] = len(jlines)
            if amount == 0:
                missing('journal_imbalance_abs_ratio', 'accounting_lines_missing_or_zero_denominator')
            else:
                debit = sum(int(r['debit_vnd']) for r in jlines)
                credit = sum(int(r['credit_vnd']) for r in jlines)
                values['journal_imbalance_abs_ratio'] = round(abs(debit - credit) / abs(amount), 8)
            for jl in jlines:
                records.append(dict(
                    table='journal_lines', record_id=str(jl.get('line_id') or jl.get('document_id') or digest(canonical(jl))[:16]),
                    revision=1, effective_at=jl['posted_at'], observed_at=jl['observed_at'],
                    source_sha256=digest(canonical(jl)),
                ))

    # Supporting documents (transaction_documents only; never support_doc_count).
    if not doc_complete:
        missing('known_document_count', 'transaction_documents_coverage_incomplete')
    else:
        seen_docs = {}
        for doc in docs_by_tx.get(tx_id, ()):
            if doc.get('company_id') == company and utc(doc['observed_at']) <= row_cutoff:
                key = doc.get('document_id') or doc.get('record_id') or doc.get('evidence_id') or digest(canonical(doc))
                seen_docs[key] = doc
        values['known_document_count'] = len(seen_docs)
        for doc_key in sorted(seen_docs):
            doc = seen_docs[doc_key]
            records.append(dict(
                table='transaction_documents', record_id=str(doc_key), revision=1,
                effective_at=doc.get('verified_at') or doc['observed_at'], observed_at=doc['observed_at'],
                source_sha256=digest(canonical(doc)),
            ))

    # Structurally absent canonical sources in native-rule-source/1.0.0 -> explicit null + reason.
    for col, reason in UNMAPPED_COLUMNS.items():
        missing(col, reason)

    feature_vec = [values[col] for col in COLUMNS]
    missing_vec = [v is None for v in feature_vec]
    records.sort(key=lambda r: (r['table'], r['record_id'], r['revision'], r['observed_at']))
    row_meta = dict(
        tenant_id=tenant, company_id=company, record_id=tx_id, revision=item['revision'],
        event_at=event_dt.astimezone(timezone.utc).isoformat(),
        as_of=row_cutoff.astimezone(timezone.utc).isoformat(),
    )
    evidence_meta = dict(
        records=records,
        missing_reasons=reasons,
        signed_amount_vnd=amount,
        history_group=item['group'],
        history_type_record_count=len(prior) if hist_complete else None,
        cutoff_as_of=cutoff_iso,
    )
    return feature_vec, missing_vec, row_meta, evidence_meta


def build_rule_feature_rows(bundle, scope, as_of, *, snapshot=None, candidate_transaction_ids=None,
                            candidates_only=True, require_exact_source_cutoff=False):
    """Build 33-column point-in-time feature frame from agent2-rule-snapshot/1.0.0 payload."""
    tenant, company = _scope(scope)
    if not isinstance(bundle, dict) or bundle.get('contract_version') != SOURCE_CONTRACT:
        fail(422, 'RULE_SNAPSHOT_INVALID', 'Snapshot không đúng profile nguồn 35 luật.', 'Dùng snapshot agent2-rule-snapshot/1.0.0.')
    if bundle.get('tenant_id') != tenant or bundle.get('company_id') != company:
        fail(403, 'ACCESS_DENIED', 'Snapshot không thuộc phạm vi doanh nghiệp được phép.', 'Chọn đúng snapshot của doanh nghiệp hiện tại.')
    source = bundle.get('source')
    if not isinstance(source, dict):
        fail(422, 'RULE_SNAPSHOT_INVALID', 'Thiếu payload source của snapshot.', 'Lưu lại snapshot nguồn hợp lệ.')
    report = validate_bundle(source, scope)
    if report['status'] == 'rejected':
        first = (report.get('errors') or [{}])[0]
        fail(422, first.get('code') or 'RULE_SNAPSHOT_INVALID',
             first.get('message') or 'Nguồn không hợp lệ để tạo feature.',
             first.get('action') or 'Kiểm tra lại dữ liệu nguồn trước khi phân tích.')

    cutoff_dt = utc(as_of)
    source_cutoff = utc(source['as_of'])
    if require_exact_source_cutoff and cutoff_dt != source_cutoff:
        fail(400, 'RULE_SOURCE_CUTOFF', 'Phải chấm đúng as_of đã khóa trong gói nguồn 35 luật.', 'Chọn đúng mốc as_of của gói dữ liệu đã lưu.')
    if cutoff_dt > source_cutoff:
        fail(400, 'RULE_SOURCE_CUTOFF', 'Thời điểm as_of vượt quá mốc nguồn đã khóa.', 'Không chấm hoặc replay vượt quá source.as_of.')

    tables = source['tables']
    coverage = source['coverage']
    raw_txs = tables.get('transactions', [])

    all_txs = []
    by_id = {}
    for tx in raw_txs:
        tx_id = tx['transaction_id']
        event_dt = utc(tx['posted_at'])
        obs_dt = utc(tx['observed_at'])
        row_cutoff = max(event_dt, obs_dt)
        if row_cutoff > cutoff_dt:
            continue
        rev, rev_origin = _tx_revision(tx)
        item = dict(
            tx=tx, id=tx_id, revision=rev, revision_origin=rev_origin,
            event_dt=event_dt, observed_dt=obs_dt, cutoff_dt=row_cutoff,
            amount=tx['amount_vnd'], group=_history_group(tx.get('txn_type')),
            sha256=digest(canonical(tx)),
        )
        all_txs.append(item)
        by_id[tx_id] = item
    # Order-invariant internal timeline for deterministic history replay.
    all_txs.sort(key=lambda r: (r['event_dt'], r['observed_dt'], r['id']))

    candidates = candidate_transaction_ids if candidate_transaction_ids is not None else bundle.get('candidate_transaction_ids', [])
    if candidates_only:
        if not isinstance(candidates, list) or not candidates or len(candidates) > 200 or len(set(candidates)) != len(candidates):
            fail(422, 'RULE_CANDIDATES_INVALID', 'Danh sách candidate_transaction_ids không hợp lệ.', 'Chọn 1..200 mã giao dịch duy nhất từ bảng transactions.')
        missing_cands = [cid for cid in candidates if cid not in by_id]
        if missing_cands:
            fail(400, 'RULE_CANDIDATE_MISSING', 'Có giao dịch ứng viên chưa tồn tại tại thời điểm as_of.', 'Chọn ứng viên có hiệu lực và đã quan sát tại cutoff.')
        selected_items = [by_id[cid] for cid in candidates]
    else:
        selected_items = list(all_txs)

    jl_by_tx = defaultdict(list)
    for jl in tables.get('journal_lines', []):
        tid = jl.get('transaction_id')
        if tid:
            jl_by_tx[tid].append(jl)

    docs_by_tx = defaultdict(list)
    for doc in tables.get('transaction_documents', []):
        tid = doc.get('transaction_id')
        if tid:
            docs_by_tx[tid].append(doc)

    cutoff_iso = cutoff_dt.astimezone(timezone.utc).isoformat()
    vendors_cache = {}
    employees_cache = {}

    features, missing_rows, rows, evidence = [], [], [], []
    for index, item in enumerate(selected_items):
        f_vec, m_vec, r_meta, e_meta = _compute_row(
            item, all_txs, tables, coverage, tenant, company, cutoff_iso,
            vendors_by_cutoff=vendors_cache, employees_by_cutoff=employees_cache,
            jl_by_tx=jl_by_tx, docs_by_tx=docs_by_tx,
        )
        r_meta['row_index'] = index
        e_meta['row_index'] = index
        features.append(f_vec)
        missing_rows.append(m_vec)
        rows.append(r_meta)
        evidence.append(e_meta)

    contract = feature_contract()
    manifest = dict(
        version=VERSION,
        source_contract=SOURCE_CONTRACT,
        native_profile=NATIVE_PROFILE,
        as_of=cutoff_iso,
        snapshot_id=(snapshot or {}).get('snapshot_id'),
        tenant_id=tenant,
        company_id=company,
        data_checksum=(snapshot or {}).get('data_checksum'),
        source_sha256=source.get('source_sha256'),
        candidate_transaction_ids=list(candidates) if candidates_only else [r['record_id'] for r in rows],
        row_count=len(rows),
        candidates_only=bool(candidates_only),
        bridge_sha256=contract['bridge_sha256'],
        feature_contract_fingerprint=contract['fingerprint'],
        coverage_status={t: dict(status=coverage[t].get('status'), history_basis=coverage[t].get('history_basis'))
                         for t in sorted(coverage) if isinstance(coverage.get(t), dict)},
    )
    manifest['manifest_sha256'] = digest(canonical(manifest))

    result = dict(
        version=VERSION,
        as_of=cutoff_iso,
        contract=contract,
        features=features,
        missing=missing_rows,
        rows=rows,
        evidence=evidence,
        manifest=manifest,
    )
    if snapshot is not None:
        result['snapshot'] = {
            k: snapshot[k] for k in ('snapshot_id', 'tenant_id', 'company_id', 'checksum', 'data_checksum', 'contract_version')
        }
    return result


def build_from_rule_snapshot(store, scope, snapshot_id, as_of, recheck=None, *,
                             candidates_only=True, require_exact_source_cutoff=False):
    """Load an immutable committed agent2-rule-snapshot/1.0.0 snapshot and build 33-feature channels."""
    _scope(scope)
    manifest = store.get_snapshot(scope, snapshot_id, recheck)
    if manifest['contract_version'] != SOURCE_CONTRACT:
        fail(422, 'RULE_SNAPSHOT_CONTRACT', 'Snapshot không phải profile nguồn 35 luật.', 'Chọn snapshot agent2-rule-snapshot/1.0.0.')
    data = loads(store.get_snapshot(scope, snapshot_id, recheck, data=True))
    frame = build_rule_feature_rows(
        data, scope, as_of, snapshot=manifest,
        candidates_only=candidates_only,
        require_exact_source_cutoff=require_exact_source_cutoff,
    )
    if recheck is not None and recheck() != scope:
        fail(409, 'AUTH_CONTEXT_CHANGED', 'Quyền đã thay đổi khi tạo feature từ snapshot.', 'Chạy lại thao tác theo quyền hiện hành.')
    return frame


def build_rule_entity_graphs(bundle, scope, as_of, candidate_transaction_ids=None):
    """Build point-in-time EntityGraph subgraphs keyed by (record_id, revision)."""
    tenant, company = _scope(scope)
    source = bundle['source']
    tables = source['tables']
    coverage = source['coverage']
    vendor_ok = _cov_status(coverage, 'vendors')
    emp_ok = _cov_status(coverage, 'employees')
    links_present = bool(tables.get('entity_links'))
    links_ok = (not links_present) or _cov_status(coverage, 'entity_links')

    candidates = set(candidate_transaction_ids if candidate_transaction_ids is not None else bundle.get('candidate_transaction_ids', []))
    tx_by_id = {tx['transaction_id']: tx for tx in tables.get('transactions', []) if tx['transaction_id'] in candidates}
    graphs = {}

    if not (vendor_ok and emp_ok and links_ok):
        for tx_id, tx in tx_by_id.items():
            rev, _ = _tx_revision(tx)
            graphs[(tx_id, rev)] = dict(
                available=False,
                reason=dict(code='graph_sources_incomplete', message='Chưa đủ coverage vendors/employees/entity_links để dựng đồ thị quan hệ tại cutoff.'),
            )
        return graphs

    cutoff_dt = utc(as_of)
    vendors_cache = {}
    employees_cache = {}
    links_by_key = {}
    for row in tables.get('entity_links', []):
        lid = row.get('link_id') or digest(canonical(row))
        links_by_key[lid] = row

    graph_cache = {}
    for tx_id, tx in tx_by_id.items():
        rev, _ = _tx_revision(tx)
        event_dt = utc(tx['posted_at'])
        row_cutoff = max(event_dt, utc(tx['observed_at']))
        if row_cutoff > cutoff_dt:
            continue
        row_cutoff_iso = row_cutoff.astimezone(timezone.utc).isoformat()
        # _checked_graph validates effective_at <= event_at and observed_at <= row_cutoff.
        # For native masters/links (recorded_at == observed_at), event_dt <= row_cutoff_iso.
        master_cutoff = min(event_dt, row_cutoff).astimezone(timezone.utc).isoformat()
        if master_cutoff not in graph_cache:
            graph_cache[master_cutoff] = EntityGraph(tables, company, master_cutoff)
            vendors_cache[master_cutoff] = _latest_masters(tables.get('vendors', []), 'vendor_id', company, utc(master_cutoff))
            employees_cache[master_cutoff] = _latest_masters(tables.get('employees', []), 'employee_id', company, utc(master_cutoff))

        eg = graph_cache[master_cutoff]
        obs_v = vendors_cache[master_cutoff]
        obs_e = employees_cache[master_cutoff]
        seeds = []
        vid = tx.get('vendor_id')
        if vid and ('vendor', vid) in eg.entities:
            seeds.append(eg.actor('vendor', vid))
        for eid_key in ('employee_id', 'creator_id'):
            eid = tx.get(eid_key)
            if eid and ('employee', eid) in eg.entities:
                seeds.append(eg.actor('employee', eid))

        if not seeds:
            graphs[(tx_id, rev)] = dict(
                available=False,
                reason=dict(code='graph_entities_unobserved', message='Chưa có bản ghi đối tượng liên quan được quan sát tại thời điểm giao dịch.'),
            )
            continue

        payload = eg.to_json(seeds, depth=2, max_nodes=None)
        refs = {}
        for link in payload['links']:
            ev = link['evidence']
            src_tbl, src_id = ev['source_table'], ev['source_id']
            if (src_tbl, src_id) in refs:
                continue
            if src_tbl == 'vendors' and src_id in obs_v:
                rec = obs_v[src_id]
                refs[(src_tbl, src_id)] = dict(
                    table='vendors', record_id=src_id, revision=1,
                    effective_at=rec['recorded_at'], observed_at=rec['observed_at'],
                    name=rec.get('name'),
                )
            elif src_tbl == 'employees' and src_id in obs_e:
                rec = obs_e[src_id]
                refs[(src_tbl, src_id)] = dict(
                    table='employees', record_id=src_id, revision=1,
                    effective_at=rec['recorded_at'], observed_at=rec['observed_at'],
                    full_name=rec.get('full_name'),
                )
            elif src_tbl == 'entity_links' and src_id in links_by_key:
                rec = links_by_key[src_id]
                refs[(src_tbl, src_id)] = dict(
                    table='entity_links', record_id=src_id, revision=1,
                    effective_at=rec['observed_at'], observed_at=rec['observed_at'],
                )
        payload['available'] = True
        payload['scope']['as_of'] = row_cutoff_iso
        payload['evidence_refs'] = list(refs.values())
        graphs[(tx_id, rev)] = payload
    return graphs
