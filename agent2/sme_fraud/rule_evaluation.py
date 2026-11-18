"""Per-rule results over scoped canonical source bindings, without partial sums."""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import calendar
import math
from pathlib import Path
from statistics import median

from finance_input import AccessScope
from .benford import digits_test, vn_posting_context, vn_timestamp
from .identity import MISSING_CONTACTS, normalize, normalize_mst
from .import_files import canonical, digest, fail
from .noise_policy import assign_noise_points, name_key, name_similarity
from .rules import DEFAULT_CONFIG, RULE_NAMES, WEIGHTS
from .rule_sources import KINDS, REQUIREMENTS, ROLES, VERSION as INPUT_VERSION
from .snapshot_features import _ref, available, utc
from .temporal_evidence import bank_identity, bank_token
from . import p1_evaluation
from . import vendor_identity_rules

VERSION = 'rule-results/1.0.0'
VN = timezone(timedelta(hours=7))

# 26 active canonical evaluators derived from canonical transaction / invoice /
# allocation / vendor / employee / approval / document / bank_history fields.
SUPPORTED = (
    'A1', 'A2', 'A3', 'A4', 'A5', 'A6',
    'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7',
    'C1', 'C2', 'C3',
    'D1', 'D4', 'D5',
    'E2', 'E3', 'E4',
    'F1', 'F3',
    'P1', 'P2',
)

# 9 rules that genuinely require external HR / ERP / AR / advance subledgers
# not present in the canonical finance_input schema.
EXTENDED_SCHEMA_RULES = {
    'C4': ('leave_periods', 'system_actions', 'leave_activity_authorizations'),
    'D2': ('transactions.posted_at', 'transactions.is_financial_entry'),
    'D3': ('approval_authorities', 'transactions.is_financial_entry'),
    'D6': ('transactions.department', 'transactions.project_id'),
    'E1': ('attendance', 'payroll_entitlements'),
    'F2': ('workflow_policies', 'override_events'),
    'F4': ('receivable_invoices', 'receipt_allocations', 'receipt_coverage'),
    'T1': ('advances', 'advance_events'),
    'T2': ('advances', 'advance_events'),
}

DECREE_181_EFFECTIVE_DATE = '2025-07-01'
CASH_LIMIT_POST_2025_07_VND = 5_000_000
CASH_LIMIT_PRE_2025_07_VND = 20_000_000
DEFAULT_SPLIT_CAP_VND = 20_000_000
SYSTEM_ACTORS = frozenset({'SYS', 'SYSTEM', 'AUTO', 'BOT', 'BATCH', 'SCHEDULER'})
RETAINER_KEYWORDS = ('thue nha', 'tien thue', 'rent', 'lease', 'retainer', 'phi dinh ky', 'cuoc vien thong')


def canonical_rule_summary():
    """Return transparent counts and classification of active vs extended-schema rules."""
    return dict(
        total_rules=len(RULE_NAMES),
        active_canonical_count=len(SUPPORTED),
        active_canonical_rules=list(SUPPORTED),
        requires_extended_schema_count=len(EXTENDED_SCHEMA_RULES),
        requires_extended_schema_rules={k: list(v) for k, v in EXTENDED_SCHEMA_RULES.items()},
    )


def _sorted_refs(pairs):
    dedup = {(table, r['record_id'], r['revision']): _ref(table, r) for table, r in pairs if r is not None}
    return [dedup[k] for k in sorted(dedup)]


def _statutory_cash_limit(effective_at):
    vn_date = vn_timestamp(effective_at).date().isoformat()
    return CASH_LIMIT_POST_2025_07_VND if vn_date >= DECREE_181_EFFECTIVE_DATE else CASH_LIMIT_PRE_2025_07_VND


def _effective_threshold(tx, approvals):
    approved_limits = [a['limit_vnd'] for a in approvals if a.get('decision') == 'approved' and type(a.get('limit_vnd')) is int and a['limit_vnd'] > 0]
    if approved_limits:
        return min(approved_limits), 'approval_limit'
    if tx.get('payment_channel') == 'cash':
        return _statutory_cash_limit(tx['effective_at']), 'statutory_cash_limit'
    return DEFAULT_SPLIT_CAP_VND, 'statutory_transfer_threshold'


def _recipient_key(tx):
    vref = tx.get('vendor_ref')
    if vref and vref.get('record_id'):
        return 'vendor:' + vref['record_id']
    b_id = bank_identity(tx.get('bank_account') or '', tx.get('bank_code') or '')
    if b_id:
        return 'bank:' + b_id
    raw_acct = normalize(tx.get('bank_account') or '', 'bank_account')
    if raw_acct:
        return 'acct:' + raw_acct
    return ''


def _is_documented_single_invoice_installment(tx, window_rows, sources):
    """Exempt legitimate milestone/deposit settlements (e.g. 30%/70%) on one valid invoice."""
    invoices = sources.get('invoices', ())
    allocs = sources.get('payment_allocations', ())
    if not invoices or not allocs:
        return False
    inv_caps = {inv['record_id']: inv['amount_vnd'] for inv in invoices if inv.get('kind') == 'invoice' and inv['amount_vnd'] > 0}
    if len(inv_caps) != 1:
        return False
    only_inv_id, cap_vnd = next(iter(inv_caps.items()))
    window_tx_ids = {r['record_id'] for r in window_rows} | {tx['record_id']}
    alloc_tx_ids = set()
    total_alloc_vnd = 0
    for a in allocs:
        if a['invoice_ref']['record_id'] == only_inv_id and a['amount_vnd'] > 0:
            total_alloc_vnd += a['amount_vnd']
            alloc_tx_ids.add(a['transaction_ref']['record_id'])
    return window_tx_ids <= alloc_tx_ids and total_alloc_vnd <= cap_vnd


def _eval_a1(sources, _meta, plan):
    """A1: Split payments to same vendor/recipient within 3 days near threshold."""
    tx = sources['transactions'][0]
    rkey = _recipient_key(tx)
    if not rkey or tx['amount_vnd'] <= 0:
        return dict(unavailable=('recipient_or_positive_amount_missing', 'Cần thông tin người nhận và khoản chi dương để đối chiếu chia nhỏ 3 ngày.'), gaps=plan['gaps'])
    event = utc(tx['effective_at'])
    cap_vnd, basis = _effective_threshold(tx, sources.get('approvals', ()))
    # Check both statutory cash threshold (5M/20M) and approval/20M threshold
    cash_cap = _statutory_cash_limit(tx['effective_at'])
    thresholds = sorted({cap_vnd, cash_cap, DEFAULT_SPLIT_CAP_VND})
    peer_rows = [
        h for h in sources.get('transaction_history', ())
        if h.get('kind') == 'payment' and h['amount_vnd'] > 0 and _recipient_key(h) == rkey
        and 0 <= (event - utc(h['effective_at'])).total_seconds() <= DEFAULT_CONFIG['short_days'] * 86400
    ]
    window_rows = peer_rows + [tx]
    total_vnd = sum(r['amount_vnd'] for r in window_rows)
    exempt_installment = len(window_rows) >= 2 and _is_documented_single_invoice_installment(tx, window_rows, sources)
    matched_cap = None
    if len(window_rows) >= 2 and not exempt_installment:
        for cand_cap in thresholds:
            if cand_cap == cash_cap and cand_cap < DEFAULT_SPLIT_CAP_VND:
                # 5M Decree 181 split check applies on same day (or cash channel)
                same_day = [
                    r for r in window_rows
                    if vn_timestamp(r['effective_at']).date() == vn_timestamp(tx['effective_at']).date()
                ]
                if len(same_day) >= 2 and all(0 < r['amount_vnd'] < cand_cap for r in same_day) and sum(r['amount_vnd'] for r in same_day) >= cand_cap:
                    matched_cap = cand_cap
                    break
            elif all(0 < r['amount_vnd'] < cand_cap for r in window_rows) and total_vnd >= int(cand_cap * DEFAULT_CONFIG['short_total_ratio']):
                matched_cap = cand_cap
                break
    hit = matched_cap is not None
    refs = _sorted_refs([('transactions', tx), *[('transactions', r) for r in peer_rows], *[('vendors', v) for v in sources.get('vendor', ())]])
    return dict(
        matched=hit,
        score=WEIGHTS['A1'] if hit else 0,
        intrinsic_points=WEIGHTS['A1'] if hit else 0,
        evidence_refs=refs,
        details=dict(
            recipient_key=rkey,
            window_days=DEFAULT_CONFIG['short_days'],
            split_count=len(window_rows),
            window_total_vnd=total_vnd,
            threshold_vnd=matched_cap or cap_vnd,
            threshold_basis=basis,
            exempt_documented_installment=exempt_installment,
            related_transaction_ids=[r['record_id'] for r in peer_rows],
        ),
    )


def _eval_a2(sources, _meta, plan):
    """A2: Split payments by same creator & recipient within 30 days."""
    tx = sources['transactions'][0]
    creator_ref = tx.get('created_by_ref')
    rkey = _recipient_key(tx)
    if not creator_ref or not rkey or tx['amount_vnd'] <= 0:
        return dict(unavailable=('creator_or_recipient_missing', 'Cần người lập và người nhận để kiểm tra chia nhỏ 30 ngày.'), gaps=plan['gaps'])
    creator_id = creator_ref['record_id']
    event = utc(tx['effective_at'])
    cap_vnd, basis = _effective_threshold(tx, sources.get('approvals', ()))
    peer_rows = [
        h for h in sources.get('transaction_history', ())
        if h.get('kind') == 'payment' and h['amount_vnd'] > 0
        and (h.get('created_by_ref') or {}).get('record_id') == creator_id
        and _recipient_key(h) == rkey
        and 0 <= (event - utc(h['effective_at'])).total_seconds() <= DEFAULT_CONFIG['long_days'] * 86400
    ]
    window_rows = peer_rows + [tx]
    total_vnd = sum(r['amount_vnd'] for r in window_rows)
    exempt_installment = len(window_rows) >= 2 and _is_documented_single_invoice_installment(tx, window_rows, sources)
    hit = (
        len(window_rows) >= 3
        and not exempt_installment
        and all(0 < r['amount_vnd'] < cap_vnd for r in window_rows)
        and total_vnd >= cap_vnd
    )
    refs = _sorted_refs([('transactions', tx), *[('transactions', r) for r in peer_rows], *[('employees', c) for c in sources.get('creator', ())]])
    return dict(
        matched=hit,
        score=WEIGHTS['A2'] if hit else 0,
        intrinsic_points=WEIGHTS['A2'] if hit else 0,
        evidence_refs=refs,
        details=dict(
            creator_id=creator_id,
            recipient_key=rkey,
            window_days=DEFAULT_CONFIG['long_days'],
            split_count=len(window_rows),
            window_total_vnd=total_vnd,
            threshold_vnd=cap_vnd,
            threshold_basis=basis,
            exempt_documented_installment=exempt_installment,
        ),
    )


def _eval_a3(sources, _meta, plan):
    """A3: Split payments across linked vendor cluster (shared bank/phone/address/tax_id)."""
    tx = sources['transactions'][0]
    vendor_list = sources.get('vendor', ())
    vendors = sources.get('vendors', ())
    if not vendor_list or len(vendors) < 2 or tx['amount_vnd'] <= 0:
        return dict(unavailable=('vendor_network_sources_insufficient', 'Cần từ 2 nhà cung cấp trở lên để kiểm tra chia nhỏ qua cụm NCC liên kết.'), gaps=plan['gaps'])
    cur_vendor = vendor_list[0]
    # Build connected component of vendors sharing bank_account, phone, tax_id, or non-missing address
    adj = defaultdict(set)
    by_attr = defaultdict(list)
    for v in vendors:
        vid = v['record_id']
        b_tok = bank_identity(v.get('bank_account') or '', v.get('bank_code') or '') or normalize(v.get('bank_account') or '', 'bank_account')
        if b_tok:
            by_attr[('bank', b_tok)].append(vid)
        p_tok = normalize(v.get('phone') or '', 'phone')
        if p_tok:
            by_attr[('phone', p_tok)].append(vid)
        t_tok = normalize(v.get('tax_id') or '', 'tax_id')
        if t_tok:
            by_attr[('tax_id', t_tok)].append(vid)
        a_tok = normalize(v.get('address') or '', 'address')
        if a_tok:
            by_attr[('address', a_tok)].append(vid)
    for group in by_attr.values():
        if len(group) >= 2:
            for left in group:
                adj[left].update(group)
    cluster = {cur_vendor['record_id']}
    queue = [cur_vendor['record_id']]
    while queue:
        cur = queue.pop()
        for nxt in adj.get(cur, ()):
            if nxt not in cluster:
                cluster.add(nxt)
                queue.append(nxt)
    event = utc(tx['effective_at'])
    cap_vnd, _ = _effective_threshold(tx, sources.get('approvals', ()))
    peer_rows = [
        h for h in sources.get('transaction_history', ())
        if h.get('kind') == 'payment' and h['amount_vnd'] > 0
        and (h.get('vendor_ref') or {}).get('record_id') in cluster
        and 0 <= (event - utc(h['effective_at'])).total_seconds() <= 7 * 86400
    ]
    window_rows = peer_rows + [tx]
    distinct_vendors = {(r.get('vendor_ref') or {}).get('record_id') for r in window_rows if r.get('vendor_ref')}
    total_vnd = sum(r['amount_vnd'] for r in window_rows)
    hit = (
        len(cluster) >= 2
        and len(distinct_vendors) >= 2
        and all(0 < r['amount_vnd'] < cap_vnd for r in window_rows)
        and total_vnd >= cap_vnd
    )
    cluster_vendors = [v for v in vendors if v['record_id'] in cluster]
    refs = _sorted_refs([('transactions', tx), *[('transactions', r) for r in peer_rows], *[('vendors', v) for v in cluster_vendors]])
    return dict(
        matched=hit,
        score=WEIGHTS['A3'] if hit else 0,
        intrinsic_points=WEIGHTS['A3'] if hit else 0,
        evidence_refs=refs,
        details=dict(
            cluster_vendor_ids=sorted(cluster),
            active_vendor_ids=sorted(distinct_vendors),
            window_total_vnd=total_vnd,
            threshold_vnd=cap_vnd,
        ),
    )


def _eval_a4(sources, _meta, plan):
    """A4: Creator has >=3 near-limit payments ([0.80, 0.999] * threshold) in same VN month."""
    tx = sources['transactions'][0]
    creator_ref = tx.get('created_by_ref')
    if not creator_ref or tx['amount_vnd'] <= 0:
        return dict(unavailable=('creator_missing', 'Cần mã người lập để kiểm tra chuỗi khoản chi sát hạn mức.'), gaps=plan['gaps'])
    creator_id = creator_ref['record_id']
    cap_vnd, basis = _effective_threshold(tx, sources.get('approvals', ()))
    cash_cap = _statutory_cash_limit(tx['effective_at'])
    vn_dt = vn_timestamp(tx['effective_at'])
    ym = (vn_dt.year, vn_dt.month)
    month_rows = [
        h for h in sources.get('transaction_history', ())
        if h['amount_vnd'] > 0 and (h.get('created_by_ref') or {}).get('record_id') == creator_id
        and (vn_timestamp(h['effective_at']).year, vn_timestamp(h['effective_at']).month) == ym
    ] + [tx]
    near_rows = []
    chosen_cap = cap_vnd
    for cand_cap in sorted({cap_vnd, cash_cap, DEFAULT_SPLIT_CAP_VND}):
        cand_near = [r for r in month_rows if cand_cap * DEFAULT_CONFIG['near_low'] <= r['amount_vnd'] < cand_cap]
        if len(cand_near) >= DEFAULT_CONFIG['near_count'] and any(r['record_id'] == tx['record_id'] for r in cand_near):
            near_rows = cand_near
            chosen_cap = cand_cap
            break
    hit = len(near_rows) >= DEFAULT_CONFIG['near_count']
    refs = _sorted_refs([('transactions', tx), *[('transactions', r) for r in near_rows if r['record_id'] != tx['record_id']]])
    return dict(
        matched=hit,
        score=WEIGHTS['A4'] if hit else 0,
        intrinsic_points=WEIGHTS['A4'] if hit else 0,
        evidence_refs=refs,
        details=dict(
            creator_id=creator_id,
            period=f'{ym[0]:04d}-{ym[1]:02d}',
            near_count=len(near_rows),
            threshold_vnd=chosen_cap,
            threshold_basis=basis,
        ),
    )


def _eval_a5(sources, _meta, plan):
    """A5: Exact million / ten-million VND round-number anomaly on non-retainer expenses."""
    tx = sources['transactions'][0]
    amt = tx['amount_vnd']
    if tx.get('kind') in ('payroll', 'receipt', 'reversal') or amt <= 0:
        return dict(unavailable=('non_expense_kind', 'Chỉ kiểm tra làm tròn triệu/chục triệu VND trên khoản chi dương.'), gaps=plan['gaps'])
    prior = [h['amount_vnd'] for h in sources.get('transaction_history', ()) if h.get('kind') == tx.get('kind') and h['amount_vnd'] > 0]
    if len(prior) < 5:
        return dict(unavailable=('insufficient_history_for_round_baseline', 'Cần tối thiểu 5 giao dịch lịch sử cùng loại để ước lượng baseline làm tròn VND.'), gaps=plan['gaps'])
    desc_norm = normalize(tx.get('description') or '', 'text').lower()
    raw_desc = str(tx.get('description') or '').lower()
    is_retainer = any(kw in raw_desc or kw.replace(' ', '') in desc_norm for kw in RETAINER_KEYWORDS)
    # In VND, 1,000 VND multiples are normal; check exact million / ten-million roundness!
    is_round_million = (amt >= 1_000_000 and amt % 1_000_000 == 0)
    is_round_ten_million = (amt >= 10_000_000 and amt % 10_000_000 == 0)
    log_vals = [math.log1p(v) for v in prior]
    med = median(log_vals)
    mad = median(abs(v - med) for v in log_vals)
    scale = max(0.25, mad / 0.6744897501960817)
    robust_z = (math.log1p(amt) - med) / scale
    prior_round_rate = sum(v >= 1_000_000 and v % 1_000_000 == 0 for v in prior) / len(prior)
    hit = (
        not is_retainer
        and is_round_million
        and prior_round_rate < 0.5
        and (robust_z > DEFAULT_CONFIG['round_z'] or (is_round_ten_million and robust_z > 1.5))
    )
    refs = _sorted_refs([('transactions', tx)])
    return dict(
        matched=hit,
        score=WEIGHTS['A5'] if hit else 0,
        intrinsic_points=WEIGHTS['A5'] if hit else 0,
        evidence_refs=refs,
        details=dict(
            amount_vnd=amt,
            is_round_million=is_round_million,
            is_round_ten_million=is_round_ten_million,
            is_retainer_exempt=is_retainer,
            prior_sample_count=len(prior),
            prior_round_million_rate=round(prior_round_rate, 4),
            robust_z=round(robust_z, 4),
        ),
    )


def _eval_a6(sources, _meta, plan):
    """A6: Rounded payment amount exceeding linked invoice face obligation."""
    tx = sources['transactions'][0]
    invoices = sources.get('invoices', ())
    if not invoices:
        return dict(unavailable=('invoice_link_missing', 'Cần hóa đơn liên kết để kiểm tra thanh toán làm tròn vượt hóa đơn.'), gaps=plan['gaps'])
    invoice_total = sum(inv['amount_vnd'] for inv in invoices)
    if invoice_total <= 0:
        return dict(unavailable=('invoice_total_nonpositive', 'Tổng hóa đơn liên kết không dương.'), gaps=plan['gaps'])
    amt = tx['amount_vnd']
    is_rounded = amt >= 1_000_000 and amt % 100_000 == 0
    hit = is_rounded and amt > invoice_total + 1
    refs = _sorted_refs([('transactions', tx), *[('invoices', inv) for inv in invoices]])
    return dict(
        matched=hit,
        score=WEIGHTS['A6'] if hit else 0,
        intrinsic_points=WEIGHTS['A6'] if hit else 0,
        evidence_refs=refs,
        details=dict(
            payment_amount_vnd=amt,
            linked_invoice_total_vnd=invoice_total,
            excess_vnd=max(0, amt - invoice_total),
            is_rounded_100k=is_rounded,
        ),
    )


def _eval_b1(sources, _meta, plan):
    """B1: Vendor bank/ID overlaps employee (excluding TK 141 advance reimbursements) or duplicate invoice payment."""
    tx = sources['transactions'][0]
    employees = sources.get('employees', ())
    vendor_list = sources.get('vendor', ())
    if not vendor_list and not tx.get('bank_account'):
        return dict(unavailable=('vendor_or_recipient_bank_missing', 'Cần thông tin NCC hoặc tài khoản nhận tiền để đối chiếu B1.'), gaps=plan['gaps'])
    # Exclude legitimate employee travel/advance reimbursements (TK 141 or explicit employee_ref)
    lines = tx.get('accounting_lines') or ()
    is_advance_reimbursement = bool(tx.get('employee_ref')) or any(str(l.get('account', '')).startswith('141') for l in lines)
    vendor = vendor_list[0] if vendor_list else None
    disclosed = bool(
        vendor and vendor.get('related_party_disclosed_at')
        and utc(vendor['related_party_disclosed_at']) <= utc(tx['effective_at'])
    )
    v_bank = bank_identity(
        (tx.get('bank_account') or (vendor.get('bank_account') if vendor else '') or ''),
        (tx.get('bank_code') or (vendor.get('bank_code') if vendor else '') or ''),
    )
    v_raw_acct = normalize(tx.get('bank_account') or (vendor.get('bank_account') if vendor else '') or '', 'bank_account')
    v_tax = normalize((vendor.get('tax_id') if vendor else '') or '', 'tax_id')
    matched_employees = []
    if not is_advance_reimbursement and not disclosed:
        for emp in employees:
            e_bank = bank_identity(emp.get('bank_account') or '', emp.get('bank_code') or '')
            e_raw_acct = normalize(emp.get('bank_account') or '', 'bank_account')
            e_nid = normalize(emp.get('national_id') or '', 'text')
            bank_match = bool(v_bank and e_bank and v_bank == e_bank) or bool(
                not v_bank and not e_bank and v_raw_acct and e_raw_acct and v_raw_acct == e_raw_acct
            )
            id_match = bool(v_tax and e_nid and v_tax == e_nid)
            if bank_match or id_match:
                matched_employees.append(emp)
    # Also check duplicate payment on identical (vendor_id, normalized_invoice_number) across distinct payment IDs
    dup_alloc_tx_ids = []
    if vendor and tx.get('kind') == 'payment' and tx['amount_vnd'] > 0:
        cur_inv_ids = {inv['record_id']: inv for inv in sources.get('invoices', ()) if inv.get('kind') == 'invoice'}
        for alloc in sources.get('payment_allocations', ()):
            tref = alloc['transaction_ref']
            iref = alloc['invoice_ref']
            if tref['record_id'] != tx['record_id'] and iref['record_id'] in cur_inv_ids and alloc['amount_vnd'] >= cur_inv_ids[iref['record_id']]['amount_vnd']:
                dup_alloc_tx_ids.append(tref['record_id'])
    hit = bool(matched_employees or dup_alloc_tx_ids)
    refs = _sorted_refs([
        ('transactions', tx),
        *([('vendors', vendor)] if vendor else []),
        *[('employees', e) for e in matched_employees],
    ])
    return dict(
        matched=hit,
        score=WEIGHTS['B1'] if hit else 0,
        intrinsic_points=WEIGHTS['B1'] if hit else 0,
        evidence_refs=refs,
        details=dict(
            matched_employee_ids=[e['record_id'] for e in matched_employees],
            duplicate_full_invoice_payment_tx_ids=sorted(set(dup_alloc_tx_ids)),
            exempt_advance_reimbursement_141=is_advance_reimbursement,
            related_party_disclosed=disclosed,
        ),
    )


def _eval_b2(sources, _meta, plan):
    """B2: Vendor contact overlaps employee OR identical (vendor, amount, VN-date) double payment."""
    tx = sources['transactions'][0]
    vendor_list = sources.get('vendor', ())
    employees = sources.get('employees', ())
    if not vendor_list:
        return dict(unavailable=('vendor_missing', 'Cần thông tin nhà cung cấp để đối chiếu B2.'), gaps=plan['gaps'])
    vendor = vendor_list[0]
    disclosed = bool(vendor.get('related_party_disclosed_at') and utc(vendor['related_party_disclosed_at']) <= utc(tx['effective_at']))
    v_phone = normalize(vendor.get('phone') or '', 'phone') if isinstance(vendor.get('phone'), str) else ''
    v_addr = normalize(vendor.get('address') or '', 'address') if isinstance(vendor.get('address'), str) else ''
    contact_Matches = []
    if not disclosed and (v_phone or v_addr):
        for emp in employees:
            e_phone = normalize(emp.get('phone') or '', 'phone') if isinstance(emp.get('phone'), str) else ''
            e_addr = normalize(emp.get('address') or '', 'address') if isinstance(emp.get('address'), str) else ''
            if (v_phone and e_phone and v_phone == e_phone) or (v_addr and e_addr and v_addr == e_addr):
                contact_Matches.append(emp)
    # Double-payment check: identical (vendor_id, positive amount_vnd, VN calendar date) across distinct payment IDs
    tx_day = vn_timestamp(tx['effective_at']).date()
    dup_same_day = []
    if tx.get('kind') == 'payment' and tx['amount_vnd'] > 0:
        for h in sources.get('transaction_history', ()):
            if (h.get('kind') == 'payment' and h['amount_vnd'] == tx['amount_vnd']
                    and (h.get('vendor_ref') or {}).get('record_id') == vendor['record_id']
                    and vn_timestamp(h['effective_at']).date() == tx_day):
                dup_same_day.append(h)
    has_contact_fields = ('phone' in vendor and vendor['phone'] is not None) or ('address' in vendor and vendor['address'] is not None)
    if not has_contact_fields and not dup_same_day and not contact_Matches:
        return dict(unavailable=('vendor_contact_fields_missing', 'Chưa có SĐT/địa chỉ NCC để đối chiếu quan hệ B2.'), gaps=plan['gaps'])
    hit = bool(contact_Matches or dup_same_day)
    refs = _sorted_refs([
        ('transactions', tx),
        ('vendors', vendor),
        *[('employees', e) for e in contact_Matches],
        *[('transactions', h) for h in dup_same_day],
    ])
    return dict(
        matched=hit,
        score=WEIGHTS['B2'] if hit else 0,
        intrinsic_points=WEIGHTS['B2'] if hit else 0,
        evidence_refs=refs,
        details=dict(
            matched_employee_ids=[e['record_id'] for e in contact_Matches],
            duplicate_same_day_payment_ids=[h['record_id'] for h in dup_same_day],
            related_party_disclosed=disclosed,
        ),
    )


def _eval_b3(sources, _meta, plan):
    """B3: Newly onboarded vendor (<=90 days) receiving high-value first payment without verified fulfilment docs."""
    tx = sources['transactions'][0]
    vendor_list = sources.get('vendor', ())
    if not vendor_list or tx['amount_vnd'] <= 0:
        return dict(unavailable=('vendor_missing', 'Cần hồ sơ NCC để kiểm tra giao dịch lớn đầu tiên cho NCC mới.'), gaps=plan['gaps'])
    vendor = vendor_list[0]
    age_days = (utc(tx['effective_at']) - utc(vendor['effective_at'])).total_seconds() / 86400.0
    prior_vendor_payments = [
        h for h in sources.get('transaction_history', ())
        if h.get('kind') == 'payment' and h['amount_vnd'] > 0
        and (h.get('vendor_ref') or {}).get('record_id') == vendor['record_id']
    ]
    verified_docs = [
        d for d in sources.get('supporting_documents', ())
        if d.get('source_kind') == 'original' and not d['source']['is_simulated'] and d.get('verification_status') == 'verified'
    ]
    doc_kinds = {str(d.get('document_kind', '')).lower() for d in verified_docs}
    fulfilment_verified = ('invoice' in doc_kinds and bool(doc_kinds & {'contract', 'purchase_order', 'goods_receipt', 'service_acceptance'}))
    cap_vnd, _ = _effective_threshold(tx, sources.get('approvals', ()))
    high_threshold = max(DEFAULT_SPLIT_CAP_VND, cap_vnd)
    hit = (
        0 <= age_days <= DEFAULT_CONFIG['vendor_new_days']
        and len(prior_vendor_payments) == 0
        and tx['amount_vnd'] >= high_threshold
        and not fulfilment_verified
    )
    refs = _sorted_refs([('transactions', tx), ('vendors', vendor), *[('supporting_documents', d) for d in verified_docs]])
    return dict(
        matched=hit,
        score=WEIGHTS['B3'] if hit else 0,
        intrinsic_points=WEIGHTS['B3'] if hit else 0,
        evidence_refs=refs,
        details=dict(
            vendor_id=vendor['record_id'],
            vendor_age_days=round(age_days, 2),
            prior_vendor_payment_count=len(prior_vendor_payments),
            threshold_vnd=high_threshold,
            fulfilment_verified=fulfilment_verified,
        ),
    )


def _eval_b4(sources, _meta, plan):
    """B4: Ghost/shell vendor missing critical KYC (tax_id & bank_account) on high-value payment, or bank shared across distinct tax IDs."""
    tx = sources['transactions'][0]
    vendor_list = sources.get('vendor', ())
    if not vendor_list or tx['amount_vnd'] <= 0:
        return dict(unavailable=('vendor_missing', 'Cần hồ sơ NCC để kiểm tra rủi ro định danh thuế / KYC B4.'), gaps=plan['gaps'])
    vendor = vendor_list[0]
    vendors = sources.get('vendors', ())
    raw_tax = vendor.get('tax_id')
    valid_mst = normalize_mst(bank_token(raw_tax)) if isinstance(raw_tax, str) and raw_tax.strip() else ''
    has_invalid_mst_format = bool(isinstance(raw_tax, str) and raw_tax.strip() and bank_token(raw_tax) not in MISSING_CONTACTS and not valid_mst)
    v_acct = normalize(vendor.get('bank_account') or tx.get('bank_account') or '', 'bank_account')
    missing_both_kyc = (not valid_mst and not v_acct)
    # Check if vendor's bank account is shared across >=2 distinct non-empty tax_ids (shell vendor ring)
    v_bank = bank_identity(vendor.get('bank_account') or '', vendor.get('bank_code') or '') or v_acct
    distinct_tax_ids_on_bank = set()
    conflicting_vendors = []
    if v_bank:
        for peer in vendors:
            p_bank = bank_identity(peer.get('bank_account') or '', peer.get('bank_code') or '') or normalize(peer.get('bank_account') or '', 'bank_account')
            p_tax = normalize_mst(bank_token(peer.get('tax_id') or '')) if isinstance(peer.get('tax_id'), str) else ''
            if p_bank == v_bank and p_tax:
                distinct_tax_ids_on_bank.add(p_tax)
                if peer['record_id'] != vendor['record_id']:
                    conflicting_vendors.append(peer)
    shared_bank_distinct_mst = len(distinct_tax_ids_on_bank) >= 2
    high_value_missing_kyc = (tx['amount_vnd'] >= DEFAULT_SPLIT_CAP_VND and (missing_both_kyc or has_invalid_mst_format))
    if not ('tax_id' in vendor or shared_bank_distinct_mst or missing_both_kyc):
        return dict(unavailable=('tax_id_not_provided', 'Chưa có trường mã số thuế NCC.'), gaps=plan['gaps'])
    hit = bool(high_value_missing_kyc or shared_bank_distinct_mst or has_invalid_mst_format)
    refs = _sorted_refs([('transactions', tx), ('vendors', vendor), *[('vendors', p) for p in conflicting_vendors]])
    return dict(
        matched=hit,
        score=WEIGHTS['B4'] if hit else 0,
        intrinsic_points=WEIGHTS['B4'] if hit else 0,
        evidence_refs=refs,
        details=dict(
            vendor_id=vendor['record_id'],
            valid_mst=bool(valid_mst),
            invalid_mst_format=has_invalid_mst_format,
            missing_tax_and_bank_kyc=missing_both_kyc,
            shared_bank_distinct_tax_ids=sorted(distinct_tax_ids_on_bank),
        ),
    )


def _eval_b6(sources, _meta, plan):
    """B6: Dormant vendor (>=180d gap) receiving large payment OR sudden >=5x spike vs vendor historical baseline."""
    tx = sources['transactions'][0]
    vendor_list = sources.get('vendor', ())
    if not vendor_list or tx['amount_vnd'] <= 0:
        return dict(unavailable=('vendor_missing', 'Cần hồ sơ NCC để đối chiếu lịch sử giao dịch NCC.'), gaps=plan['gaps'])
    vendor = vendor_list[0]
    prior_vendor = [
        h for h in sources.get('transaction_history', ())
        if h.get('kind') == 'payment' and h['amount_vnd'] > 0
        and (h.get('vendor_ref') or {}).get('record_id') == vendor['record_id']
    ]
    if not prior_vendor:
        return dict(unavailable=('vendor_history_empty', 'Chưa có giao dịch lịch sử của NCC này để đánh giá ngủ đông/đột biến.'), gaps=plan['gaps'])
    last_tx = max(prior_vendor, key=lambda r: utc(r['effective_at']))
    dormant_gap_days = (utc(tx['effective_at']) - utc(last_tx['effective_at'])).total_seconds() / 86400.0
    med_vnd = median(r['amount_vnd'] for r in prior_vendor)
    dormant_hit = dormant_gap_days >= DEFAULT_CONFIG['dormant_days'] and tx['amount_vnd'] >= DEFAULT_SPLIT_CAP_VND
    spike_hit = len(prior_vendor) >= 3 and tx['amount_vnd'] >= max(DEFAULT_SPLIT_CAP_VND, int(med_vnd * 5))
    hit = bool(dormant_hit or spike_hit)
    refs = _sorted_refs([('transactions', tx), ('vendors', vendor), ('transactions', last_tx)])
    return dict(
        matched=hit,
        score=WEIGHTS['B6'] if hit else 0,
        intrinsic_points=WEIGHTS['B6'] if hit else 0,
        evidence_refs=refs,
        details=dict(
            vendor_id=vendor['record_id'],
            dormant_gap_days=round(dormant_gap_days, 2),
            prior_vendor_count=len(prior_vendor),
            vendor_median_vnd=med_vnd,
            dormant_hit=dormant_hit,
            velocity_spike_hit=spike_hit,
        ),
    )


def _eval_b7(sources, _meta, plan):
    """B7: Recent (<14d) unverified vendor bank account change or payout to unverified bank account."""
    tx = sources['transactions'][0]
    vendor_list = sources.get('vendor', ())
    history = sources.get('vendor_bank_history', ())
    if not vendor_list or not history:
        return dict(unavailable=('vendor_bank_history_missing', 'Chưa có lịch sử tài khoản ngân hàng của NCC để kiểm tra B7.'), gaps=plan['gaps'])
    vendor = vendor_list[0]
    event = utc(tx['effective_at'])
    ordered = sorted(history, key=lambda r: (utc(r['effective_at']), r['revision']))
    latest_bh = ordered[-1]
    days_since_change = (event - utc(latest_bh['effective_at'])).total_seconds() / 86400.0
    changed_account = len({bank_identity(r['bank_account'], r['bank_code']) for r in ordered}) > 1 or len(ordered) == 1
    tx_bank = bank_identity(tx.get('bank_account') or vendor.get('bank_account') or '', tx.get('bank_code') or vendor.get('bank_code') or '')
    bh_bank = bank_identity(latest_bh['bank_account'], latest_bh['bank_code'])
    recent_unverified = (
        0 <= days_since_change <= DEFAULT_CONFIG['bank_change_days']
        and changed_account
        and latest_bh.get('verification_status') != 'verified'
    )
    mismatch_verified = bool(tx_bank and bh_bank and tx_bank != bh_bank)
    hit = bool(recent_unverified or mismatch_verified)
    refs = _sorted_refs([('transactions', tx), ('vendors', vendor), *[('vendor_bank_history', r) for r in ordered]])
    return dict(
        matched=hit,
        score=WEIGHTS['B7'] if hit else 0,
        intrinsic_points=WEIGHTS['B7'] if hit else 0,
        evidence_refs=refs,
        details=dict(
            vendor_id=vendor['record_id'],
            days_since_bank_record=round(days_since_change, 2),
            verification_status=latest_bh.get('verification_status'),
            recent_unverified=recent_unverified,
            payout_bank_mismatch=mismatch_verified,
        ),
    )


def _eval_c1(sources, _meta, _plan):
    """C1: Late-night (22:00-05:59 VN) or Sunday manual posting / approval in Asia/Ho_Chi_Minh."""
    tx = sources['transactions'][0]
    tx_ctx = vn_posting_context(tx['effective_at'])
    approvals = sources.get('approvals', ())
    app_ctxs = [vn_posting_context(a['effective_at']) for a in approvals]
    created_outside = bool(tx_ctx['is_off_hours'] or tx_ctx['is_sunday'])
    approved_outside = any(c['is_off_hours'] or c['is_sunday'] for c in app_ctxs)
    hit = bool(created_outside or approved_outside)
    refs = _sorted_refs([('transactions', tx), *[('approvals', a) for a in approvals]])
    return dict(
        matched=hit,
        score=WEIGHTS['C1'] if hit else 0,
        intrinsic_points=WEIGHTS['C1'] if hit else 0,
        evidence_refs=refs,
        details=dict(
            timezone='Asia/Ho_Chi_Minh',
            transaction_vn_time=tx_ctx['vn_iso'],
            created_outside=int(created_outside),
            approved_outside=int(approved_outside),
            is_sunday=tx_ctx['is_sunday'],
            is_off_hours=tx_ctx['is_off_hours'],
        ),
    )


def _eval_c2(sources, _meta, plan):
    """C2: Segregation-of-duties / unauthorized self-approval (created_by == approved_by)."""
    tx = sources['transactions'][0]
    creator_ref = tx.get('created_by_ref')
    approved = [a for a in sources.get('approvals', ()) if a.get('decision') == 'approved']
    if not creator_ref or not approved:
        return dict(unavailable=('rule_sources_unavailable', 'Chưa đủ nguồn để đánh giá luật; xem bảng/trường hoặc phiên bản tham chiếu cần bổ sung trong gaps.'), gaps=plan['gaps'])
    creator_id = creator_ref['record_id']
    if creator_id.upper() in SYSTEM_ACTORS or creator_id.upper().startswith(('SYS_', 'SYSTEM_', 'AUTO_', 'BOT_')):
        refs = _sorted_refs([('transactions', tx), *[('approvals', a) for a in approved]])
        return dict(matched=False, score=0, intrinsic_points=0, evidence_refs=refs, details=dict(system_actor_exempt=True, creator_id=creator_id))
    approver_ids = {a['employee_ref']['record_id'] for a in approved}
    if creator_id not in approver_ids:
        refs = _sorted_refs([('transactions', tx), *[('approvals', a) for a in approved], *[('employees', c) for c in sources.get('creator', ())]])
        return dict(
            matched=False,
            score=0,
            intrinsic_points=0,
            evidence_refs=refs,
            details=dict(self_approved=False, creator_id=creator_id, approver_ids=sorted(approver_ids)),
        )
    # Self-approval occurred (creator_id in approver_ids):
    self_approvals = [a for a in approved if a['employee_ref']['record_id'] == creator_id]
    limits = [a.get('limit_vnd') for a in self_approvals]
    # If no limit_vnd was granted or transaction exceeds limit_vnd (or limit_vnd == 0), definitive SoD violation!
    if any(lim is None or lim <= 0 or abs(tx['amount_vnd']) > lim for lim in limits):
        refs = _sorted_refs([('transactions', tx), *[('approvals', a) for a in self_approvals], *[('employees', c) for c in sources.get('creator', ())]])
        return dict(
            matched=True,
            score=WEIGHTS['C2'],
            intrinsic_points=WEIGHTS['C2'],
            evidence_refs=refs,
            details=dict(
                self_approved=True,
                creator_id=creator_id,
                amount_vnd=tx['amount_vnd'],
                observed_limits_vnd=limits,
                violation='self_approval_without_or_above_limit',
            ),
        )
    # Self-approval is within observed limit_vnd, but without external approval_authorities
    # (self_approval_allowed policy) we cannot claim evaluated_no_hit!
    return dict(
        unavailable=('rule_sources_unavailable', 'Chưa đủ nguồn để đánh giá luật; xem bảng/trường hoặc phiên bản tham chiếu cần bổ sung trong gaps.'),
        gaps=plan['gaps'],
    )


def _eval_c3(sources, _meta, plan):
    """C3: Sub-60-second rubber-stamp approval on high-value transaction (skipping midnight date-only imports)."""
    tx = sources['transactions'][0]
    approved = [a for a in sources.get('approvals', ()) if a.get('decision') == 'approved']
    if not approved:
        return dict(unavailable=('approval_missing', 'Chưa có bản ghi phê duyệt để kiểm tra thời gian duyệt C3.'), gaps=plan['gaps'])
    tx_ctx = vn_posting_context(tx['effective_at'])
    tx_dt = utc(tx['effective_at'])
    high_threshold = DEFAULT_CONFIG['high_approval_vnd']
    fast_approvals = []
    skipped_midnight = False
    for a in approved:
        a_ctx = vn_posting_context(a['effective_at'])
        if tx_ctx['is_date_only_midnight'] and a_ctx['is_date_only_midnight']:
            skipped_midnight = True
            continue
        delta_s = abs((utc(a['effective_at']) - tx_dt).total_seconds())
        if delta_s < 60 and abs(tx['amount_vnd']) >= high_threshold:
            fast_approvals.append((a, delta_s))
    hit = bool(fast_approvals)
    refs = _sorted_refs([('transactions', tx), *[('approvals', a) for a in approved]])
    return dict(
        matched=hit,
        score=WEIGHTS['C3'] if hit else 0,
        intrinsic_points=WEIGHTS['C3'] if hit else 0,
        evidence_refs=refs,
        details=dict(
            high_approval_threshold_vnd=high_threshold,
            fast_approval_ids=[a['record_id'] for a, _ in fast_approvals],
            min_approval_seconds=min((d for _, d in fast_approvals), default=None),
            midnight_date_only_skipped=skipped_midnight,
        ),
    )


def _canonical_benford_amounts(sources):
    tx = sources['transactions'][0]
    rows = [
        r for r in (*sources.get('transaction_history', ()), tx)
        if r.get('kind') not in ('payroll', 'receipt', 'reversal', 'adjustment') and r['amount_vnd'] > 0
    ]
    return rows


def _eval_d1(sources, _meta, plan):
    """D1: First-digit Benford screen on canonical positive disbursements (n >= 60)."""
    rows = _canonical_benford_amounts(sources)
    if len(rows) < 60:
        return dict(unavailable=('benford_insufficient_sample', 'Cần tối thiểu 60 khoản chi dương trong kỳ để kiểm định phân phối chữ số đầu Benford D1.'), gaps=plan['gaps'])
    screen = digits_test([r['amount_vnd'] for r in rows], 'first', min_rows=60)
    if screen['status'] != 'evaluated':
        return dict(unavailable=('benford_not_evaluable', 'Tập số tiền chưa đủ độ phân tán cho kiểm định Benford D1.'), gaps=plan['gaps'], details=screen)
    hit = bool(screen['pvalue'] < 0.05 and screen['mad'] > 0.015)
    refs = _sorted_refs([('transactions', sources['transactions'][0])])
    return dict(
        matched=hit,
        score=0,
        intrinsic_points=0,
        evidence_refs=refs,
        details=dict(screen, adds_transaction_score=False, scoring_role='aggregate_diagnostic'),
    )


def _eval_d4(sources, _meta, plan):
    """D4: VND million-scale special suffix (000k / 500k / 990k / 999k) surge vs historical baseline."""
    tx = sources['transactions'][0]
    rows = _canonical_benford_amounts(sources)
    event = utc(tx['effective_at'])
    recent = [r['amount_vnd'] for r in rows if 0 <= (event - utc(r['effective_at'])).total_seconds() <= 30 * 86400 and r['amount_vnd'] >= 1_000_000]
    older = [r['amount_vnd'] for r in rows if 30 * 86400 < (event - utc(r['effective_at'])).total_seconds() <= 120 * 86400 and r['amount_vnd'] >= 1_000_000]
    if len(recent) < 30 or len(older) < 30:
        return dict(unavailable=('suffix_baseline_insufficient', 'Cần tối thiểu 30 khoản chi >= 1 triệu VND ở cả cửa sổ 30 ngày và baseline trước đó.'), gaps=plan['gaps'])
    # Check thousand-VND-scaled suffixes (in VND, last 3 digits are almost always 000; check 10^3..10^6 digits!)
    target_k_endings = (0, 500, 990, 999)
    comparisons = []
    hit = False
    for ending in target_k_endings:
        cur_rate = sum((v // 1000) % 1000 == ending for v in recent) / len(recent)
        old_rate = sum((v // 1000) % 1000 == ending for v in older) / len(older)
        sig = bool(old_rate > 0 and cur_rate >= 0.25 and cur_rate > old_rate * 2.0)
        hit |= sig
        comparisons.append(dict(thousand_vnd_suffix=f'{ending:03d}000', current_rate=round(cur_rate, 4), baseline_rate=round(old_rate, 4), signal=sig))
    refs = _sorted_refs([('transactions', tx)])
    return dict(
        matched=hit,
        score=0,
        intrinsic_points=0,
        evidence_refs=refs,
        details=dict(recent_count=len(recent), baseline_count=len(older), suffix_comparison=comparisons, adds_transaction_score=False),
    )


def _eval_d5(sources, _meta, plan):
    """D5: First-digit Benford MAD > 0.015 descriptive divergence screen."""
    rows = _canonical_benford_amounts(sources)
    if len(rows) < 60:
        return dict(unavailable=('benford_mad_insufficient_sample', 'Cần tối thiểu 60 khoản chi dương để tính độ lệch MAD chữ số đầu D5.'), gaps=plan['gaps'])
    positive = [r['amount_vnd'] for r in rows]
    if len(set(positive)) < 20 or max(positive) / min(positive) < 10:
        return dict(unavailable=('benford_mad_narrow_range', 'Phạm vi số tiền quá hẹp để đánh giá MAD Benford D5.'), gaps=plan['gaps'])
    counts = Counter(int(str(v)[0]) for v in positive)
    n = len(positive)
    mad = sum(abs(counts[d] / n - math.log10(1 + 1 / d)) for d in range(1, 10)) / 9.0
    hit = mad > 0.015
    refs = _sorted_refs([('transactions', sources['transactions'][0])])
    return dict(
        matched=hit,
        score=0,
        intrinsic_points=0,
        evidence_refs=refs,
        details=dict(rows=n, mad=round(mad, 5), mad_threshold=0.015, adds_transaction_score=False),
    )


def _eval_e2(sources, _meta, plan):
    """E2: Ghost payroll disbursed after employee termination date (terminated_at < effective_at)."""
    tx = sources['transactions'][0]
    emp_list = sources.get('employee', ())
    if not emp_list:
        return dict(unavailable=('employee_missing', 'Cần hồ sơ nhân viên nhận lương để kiểm tra E2.'), gaps=plan['gaps'])
    emp = emp_list[0]
    if 'terminated_at' in emp.get('missing_fields', {}):
        return dict(unavailable=('terminated_at_unknown', 'Trạng thái ngày nghỉ việc đang đánh dấu thiếu dữ liệu.'), gaps=plan['gaps'])
    term_at = emp.get('terminated_at')
    hit = bool(term_at and utc(term_at) < utc(tx['effective_at']))
    refs = _sorted_refs([('transactions', tx), ('employees', emp)])
    return dict(
        matched=hit,
        score=WEIGHTS['E2'] if hit else 0,
        intrinsic_points=WEIGHTS['E2'] if hit else 0,
        evidence_refs=refs,
        details=dict(employee_id=emp['record_id'], terminated_at=term_at, payroll_effective_at=tx['effective_at']),
    )


def _eval_f1(sources, _meta, plan):
    """F1: Imbalanced accounting lines OR manual adjustment/reversal near period-end close with materiality."""
    tx = sources['transactions'][0]
    lines = tx.get('accounting_lines')
    is_manual_adj = tx.get('kind') in ('adjustment', 'reversal')
    if lines is None and not is_manual_adj:
        return dict(unavailable=('accounting_lines_missing', 'Cần bút toán định khoản hoặc giao dịch điều chỉnh để kiểm tra F1.'), gaps=plan['gaps'])
    imbalance_vnd = 0
    if lines is not None:
        imbalance_vnd = sum(l['debit_vnd'] for l in lines) - sum(l['credit_vnd'] for l in lines)
    ctx = vn_posting_context(tx['effective_at'])
    near_close = ctx['days_until_month_end'] < DEFAULT_CONFIG['close_days']
    material_adj = is_manual_adj and near_close and abs(tx['amount_vnd']) >= DEFAULT_SPLIT_CAP_VND
    hit = bool(imbalance_vnd != 0 or material_adj)
    refs = _sorted_refs([('transactions', tx)])
    return dict(
        matched=hit,
        score=WEIGHTS['F1'] if hit else 0,
        intrinsic_points=WEIGHTS['F1'] if hit else 0,
        evidence_refs=refs,
        details=dict(
            imbalance_vnd=imbalance_vnd,
            is_manual_adjustment=is_manual_adj,
            near_month_end_close=near_close,
            days_until_month_end=ctx['days_until_month_end'],
        ),
    )


def _eval_f3(sources, _meta, plan):
    """F3: Duplicate invoice number across distinct invoice records for the same vendor."""
    tx = sources['transactions'][0]
    merged_invs = {
        (r['record_id'], r['revision']): r
        for r in (*sources.get('invoices', ()), *sources.get('p1_invoices', ()))
    }
    invoices = sorted(merged_invs.values(), key=lambda r: (r['record_id'], r['revision']))
    if not invoices:
        return dict(unavailable=('invoices_missing', 'Cần hóa đơn liên kết để kiểm tra trùng số chứng từ F3.'), gaps=plan['gaps'])
    by_vendor_num = defaultdict(list)
    placeholder_ids = []
    for inv in invoices:
        if inv.get('kind') != 'invoice':
            continue
        norm_num = normalize(inv.get('number') or '', 'text')
        if not norm_num or norm_num in MISSING_CONTACTS:
            placeholder_ids.append(inv['record_id'])
            continue
        vid = (inv.get('vendor_ref') or {}).get('record_id', '')
        by_vendor_num[(vid, norm_num)].append(inv['record_id'])
    duplicates = {f'{vid}:{num}': sorted(set(ids)) for (vid, num), ids in by_vendor_num.items() if len(set(ids)) >= 2}
    hit = bool(duplicates or placeholder_ids)
    refs = _sorted_refs([('transactions', tx), *[('invoices', inv) for inv in invoices]])
    return dict(
        matched=hit,
        score=WEIGHTS['F3'] if hit else 0,
        intrinsic_points=WEIGHTS['F3'] if hit else 0,
        evidence_refs=refs,
        details=dict(duplicate_vendor_invoices=duplicates, placeholder_invoice_ids=placeholder_ids),
    )


def _eval_p2(sources, _meta, plan):
    """P2: Cash payment >= statutory limit (5M VND from 2025-07-01 per Decree 181/2025, 20M prior) including same-day vendor aggregation."""
    tx = sources['transactions'][0]
    if tx.get('kind') != 'payment':
        return dict(not_applicable=True)
    channel = tx.get('payment_channel')
    if channel not in ('bank', 'cash'):
        return dict(unavailable=('payment_channel_missing', 'Cần kênh thanh toán (bank/cash) để kiểm tra quy định thanh toán không dùng tiền mặt P2.'), gaps=plan['gaps'])
    limit_vnd = _statutory_cash_limit(tx['effective_at'])
    tx_day = vn_timestamp(tx['effective_at']).date()
    vendor_id = (tx.get('vendor_ref') or {}).get('record_id', '')
    same_day_vendor = [
        h for h in sources.get('transaction_history', ())
        if h.get('kind') == 'payment' and h['amount_vnd'] > 0
        and vendor_id and (h.get('vendor_ref') or {}).get('record_id') == vendor_id
        and vn_timestamp(h['effective_at']).date() == tx_day
    ]
    same_day_total = tx['amount_vnd'] + sum(h['amount_vnd'] for h in same_day_vendor)
    linked_inv_total = sum(inv['amount_vnd'] for inv in sources.get('invoices', ()) if inv['amount_vnd'] > 0)
    hit = bool(
        channel == 'cash'
        and tx['amount_vnd'] > 0
        and (tx['amount_vnd'] >= limit_vnd or same_day_total >= limit_vnd or linked_inv_total >= limit_vnd)
    )
    refs = _sorted_refs([('transactions', tx), *[('transactions', h) for h in same_day_vendor], *[('invoices', i) for i in sources.get('invoices', ())]])
    return dict(
        matched=hit,
        score=WEIGHTS['P2'] if hit else 0,
        intrinsic_points=WEIGHTS['P2'] if hit else 0,
        evidence_refs=refs,
        details=dict(
            payment_channel=channel,
            statutory_cash_limit_vnd=limit_vnd,
            amount_vnd=tx['amount_vnd'],
            same_day_vendor_total_vnd=same_day_total,
            linked_invoice_total_vnd=linked_inv_total,
            decree_basis='ND_181_2025_5M' if limit_vnd == CASH_LIMIT_POST_2025_07_VND else 'PRE_2025_07_20M',
        ),
    )


_CANONICAL_EVALUATORS = {
    'A1': _eval_a1, 'A2': _eval_a2, 'A3': _eval_a3, 'A4': _eval_a4, 'A5': _eval_a5, 'A6': _eval_a6,
    'B1': _eval_b1, 'B2': _eval_b2, 'B3': _eval_b3, 'B4': _eval_b4, 'B6': _eval_b6, 'B7': _eval_b7,
    'C1': _eval_c1, 'C2': _eval_c2, 'C3': _eval_c3,
    'D1': _eval_d1, 'D4': _eval_d4, 'D5': _eval_d5,
    'E2': _eval_e2,
    'F1': _eval_f1, 'F3': _eval_f3,
    'P2': _eval_p2,
}


def _e3(sources):
    vendor = sources['vendor'][0]
    others = [v for v in sources['vendors'] if v['record_id'] != vendor['record_id']]
    insufficient = [v['record_id'] for v in [vendor, *others] if not name_key(v['name'])[0]]
    if insufficient:
        return dict(error=('name_content_insufficient', 'Tên NCC không đủ thông tin để so sánh; bổ sung tên nguồn có ý nghĩa, không kết luận không trùng.'),
                    details=dict(insufficient_vendor_ids=sorted(insufficient)))
    threshold = DEFAULT_CONFIG['fuzzy_similarity']; matches = []
    for other in others:
        similarity = name_similarity(vendor['name'], other['name'])
        if similarity > threshold:
            matches.append((round(similarity, 4), other['record_id']))
    evidence = dict(matched_vendor_count=len(matches), top_matches=[list(pair) for pair in sorted(matches, reverse=True)[:5]],
                    algorithm='difflib.SequenceMatcher', threshold=threshold)
    hits = []
    if matches:
        hits = [dict(rule_id='E3', points=WEIGHTS['E3'], intrinsic_points=WEIGHTS['E3'],
                     scoring_role='master_quality', hard_trigger=0, evidence=evidence)]
        assign_noise_points(hits, DEFAULT_CONFIG['operational_score'])
    return dict(matched=bool(matches), score=hits[0]['points'] if hits else 0,
                intrinsic_points=WEIGHTS['E3'] if hits else 0,
                details=dict(evidence=evidence, hits=hits, scoring_role='master_quality',
                    observed_other_vendor_count=len(others),
                    score_reason=hits[0]['score_reason'] if hits else 'Không thấy cặp tên đủ ngưỡng trong các NCC nhìn thấy; không xác nhận đầy đủ master hoặc giao dịch hợp lệ.'))


def _implementation_hashes():
    return {
        name: digest(Path(__file__).with_name(name).read_bytes())
        for name in ('rule_evaluation.py', 'rule_sources.py', 'rules.py', 'noise_policy.py',
                     'p1_evaluation.py', 'p1_inputs.py', 'identity.py', 'vendor_identity_rules.py')
    }


def _evaluate(sources, inputs, scope, meta):
    """Internal snapshot consumer; never accepts a caller-supplied ready flag."""
    if not isinstance(scope, AccessScope) or len(scope.company_ids) != 1 or 'data.import' not in scope.permissions:
        fail(403, 'ACCESS_DENIED', 'Không đủ quyền đánh giá nguồn luật.', 'Chọn đúng doanh nghiệp và quyền đọc.')
    company = next(iter(scope.company_ids)); identity = (scope.tenant_id, company)
    if (meta['tenant_id'], meta['company_id']) != identity:
        fail(403, 'ACCESS_DENIED', 'Giao dịch ngoài phạm vi đánh giá luật.', 'Dùng snapshot đúng quyền.')
    cutoff, event = utc(meta['as_of']), utc(meta['event_at'])
    tx = sources['transactions']
    if len(tx) != 1 or (tx[0]['record_id'], tx[0]['revision']) != (meta['record_id'], meta['revision']) or available(tx[0]) != cutoff or utc(tx[0]['effective_at']) != event:
        raise ValueError('Rule evaluation transaction/cutoff mismatch')
    for role, records in sources.items():
        for record in records:
            if (record['tenant_id'], record['company_id']) != identity:
                fail(403, 'ACCESS_DENIED', 'Nguồn đánh giá luật khác doanh nghiệp.', 'Dùng snapshot đúng quyền.')
            if utc(record['observed_at']) > cutoff or utc(record['effective_at']) > event:
                raise ValueError('Rule evaluation source exceeds cutoff')
            if role == 'transaction_history' and (record['record_id'] == meta['record_id'] or available(record) >= cutoff or utc(record['effective_at']) >= event):
                raise ValueError('Rule history includes self or simultaneous/future data')
    plans = inputs['rules']
    if inputs['version'] != INPUT_VERSION or len(plans) != len(RULE_NAMES) or {p['rule_id'] for p in plans} != set(RULE_NAMES):
        raise ValueError('Rule source contract mismatch')
    implementation = _implementation_hashes()
    results = []
    for plan in plans:
        code = plan['rule_id']; bound = {role: sources.get(role, []) for role in REQUIREMENTS[code]}
        applicable = not KINDS.get(code) or tx[0]['kind'] in KINDS[code]
        if code == 'P2' and tx[0]['kind'] != 'payment':
            applicable = False
        # Verify against original rule_sources plan first (detects tampering!)
        plan_applicable = not KINDS.get(code) or tx[0]['kind'] in KINDS[code]
        if plan_applicable and digest(canonical(bound)) != plan['source_checksum']:
            raise ValueError('Rule source payload/checksum mismatch')
        actual_refs = {(ROLES.get(role, role), r['record_id'], r['revision']): _ref(ROLES.get(role, role), r)
                       for role, records in bound.items() for r in records}
        expected_refs = [actual_refs[k] for k in sorted(actual_refs)] if plan_applicable else []
        if expected_refs != plan['evidence_refs']:
            raise ValueError('Rule evidence does not match source payload')

        result = dict(rule_id=code, name=RULE_NAMES[code], status='unavailable', available=False, matched=None,
                      intrinsic_points=None, score=None, reason=None, gaps=deepcopy(plan['gaps']),
                      evidence_refs=deepcopy(expected_refs), source_status=plan['source_status'],
                      source_checksum=plan['source_checksum'], details={})
        if not applicable:
            result.update(status='not_applicable', source_status='not_applicable', gaps=[], evidence_refs=[],
                          reason=dict(code='rule_not_applicable', message='Loại giao dịch ngoài phạm vi luật; không phải kết quả không trúng luật.'))
        elif code in ('E3', 'P1', 'B5', 'E4'):
            if plan['source_status'] != 'ready' or plan['gaps']:
                result['reason'] = dict(code='rule_sources_unavailable', message='Chưa đủ nguồn để đánh giá luật; xem bảng/trường hoặc phiên bản tham chiếu cần bổ sung trong gaps.')
            else:
                if code == 'E3':
                    if len(bound['vendor']) != 1 or not bound['vendors']:
                        raise ValueError('Ready E3 lacks required source payload')
                    evaluated = _e3(bound)
                elif code in ('B5', 'E4'):
                    evaluated = vendor_identity_rules.evaluate(bound, meta)
                else:
                    evaluated = p1_evaluation.evaluate(bound, meta)
                result['details'] = evaluated['details']
                if 'error' in evaluated:
                    result['reason'] = dict(zip(('code', 'message'), evaluated['error']))
                else:
                    result.update(status='evaluated_hit' if evaluated['matched'] else 'evaluated_no_hit',
                                  available=True, matched=evaluated['matched'],
                                  intrinsic_points=evaluated['intrinsic_points'], score=evaluated['score'])
        elif code in _CANONICAL_EVALUATORS:
            evaluated = _CANONICAL_EVALUATORS[code](sources, meta, plan)
            if evaluated.get('not_applicable'):
                result.update(status='not_applicable', source_status='not_applicable', gaps=[], evidence_refs=[],
                              reason=dict(code='rule_not_applicable', message='Loại giao dịch ngoài phạm vi luật; không phải kết quả không trúng luật.'))
            elif 'unavailable' in evaluated:
                rc, rm = evaluated['unavailable']
                result['reason'] = dict(code=rc, message=rm)
                if 'details' in evaluated:
                    result['details'] = evaluated['details']
            else:
                result.update(
                    status='evaluated_hit' if evaluated['matched'] else 'evaluated_no_hit',
                    available=True,
                    matched=bool(evaluated['matched']),
                    intrinsic_points=evaluated['intrinsic_points'] if evaluated['matched'] else 0,
                    score=evaluated['score'] if evaluated['matched'] else 0,
                    reason=None,
                    gaps=[],
                    source_status='ready',
                    evidence_refs=evaluated['evidence_refs'],
                    details=evaluated['details'],
                )
        else:
            ext_tables = EXTENDED_SCHEMA_RULES.get(code, ())
            result['reason'] = dict(
                code='requires_extended_schema',
                message='Luật cần bảng nghiệp vụ mở rộng ngoài hợp đồng canonical (' + ', '.join(ext_tables) + '); không tự giả lập dữ liệu còn thiếu.',
            )
            result['details'].update(
                requires_extended_schema=True,
                evaluator_registered=True,
                required_input_profile='agent2-rule-snapshot/1.0.0',
                missing_external_sources=list(ext_tables),
            )
        results.append(result)
    summary = {status: sum(r['status'] == status for r in results) for status in
               ('evaluated_hit', 'evaluated_no_hit', 'unavailable', 'not_applicable')}
    evaluated_cnt = summary['evaluated_hit'] + summary['evaluated_no_hit']
    return dict(
        version=VERSION,
        coverage_status='partial' if evaluated_cnt else 'unavailable',
        rules=results,
        summary=summary,
        implementation=implementation,
        configuration=dict(fuzzy_similarity=DEFAULT_CONFIG['fuzzy_similarity'], noise_policy=DEFAULT_CONFIG['noise_policy']),
        coverage_basis='known_records_in_this_snapshot_only_not_complete_external_books',
        aggregate=dict(available=False, score=None, reason=dict(
            code='rules_incomplete',
            message='Chưa đánh giá đầy đủ bộ luật mở rộng ERP; không cộng điểm từng phần thành điểm tổng.',
        )),
    )


def evaluate_snapshot_rules_fast(bundle, frame, scope):
    """O(N log N) canonical rule evaluation across large snapshots (7,700-50,000+ rows)."""
    from bisect import bisect_left
    from .imports import (
        _build_p1_company_index,
        _fast_p1_state,
        _latest_visible_for_ids,
        _stamp,
    )
    if not isinstance(scope, AccessScope) or len(scope.company_ids) != 1 or 'data.import' not in scope.permissions:
        fail(403, 'ACCESS_DENIED', 'Không đủ quyền đánh giá nguồn luật.', 'Chọn đúng doanh nghiệp và quyền đọc.')
    cid = next(iter(scope.company_ids))
    implementation = _implementation_hashes()
    config_obj = dict(fuzzy_similarity=DEFAULT_CONFIG['fuzzy_similarity'], noise_policy=DEFAULT_CONFIG['noise_policy'])
    agg_obj = dict(available=False, score=None, reason=dict(
        code='rules_incomplete',
        message='Chưa đánh giá đầy đủ bộ luật mở rộng ERP; không cộng điểm từng phần thành điểm tổng.',
    ))

    tx_by_key = {(r['record_id'], r['revision']): r for r in bundle.get('transactions', ()) if r['company_id'] == cid}
    p1_idx = _build_p1_company_index(bundle, cid)

    def _index_revs(table):
        by_id = defaultdict(list)
        all_rows = []
        for r in bundle.get(table, ()):
            if r['company_id'] == cid:
                item = (_stamp(r['observed_at']), _stamp(r['effective_at']), r['revision'], r)
                by_id[r['record_id']].append(item)
                all_rows.append(item)
        return by_id, all_rows

    vendor_revs, all_vendor_items = _index_revs('vendors')
    emp_revs, all_emp_items = _index_revs('employees')
    inv_revs, _ = _index_revs('invoices')

    approvals_by_tx = defaultdict(list)
    for a in bundle.get('approvals', ()):
        if a['company_id'] == cid:
            tref = a['transaction_ref']
            approvals_by_tx[(tref['record_id'], tref['revision'])].append((_stamp(a['observed_at']), _stamp(a['effective_at']), a['revision'], a))

    allocs_by_tx_id = defaultdict(list)
    allocs_by_inv_id = defaultdict(list)
    for a in bundle.get('payment_allocations', ()):
        if a['company_id'] == cid:
            item = (_stamp(a['observed_at']), _stamp(a['effective_at']), a['revision'], a)
            allocs_by_tx_id[a['transaction_ref']['record_id']].append(item)
            allocs_by_inv_id[a['invoice_ref']['record_id']].append(item)

    docs_by_subj = defaultdict(list)
    for d in bundle.get('supporting_documents', ()):
        if d['company_id'] == cid:
            item = (_stamp(d['observed_at']), _stamp(d['effective_at']), d['revision'], d)
            for s in d['subject_refs']:
                docs_by_subj[(s['table'], s['record_id'], s['revision'])].append(item)

    bh_by_vendor = defaultdict(list)
    for b in bundle.get('vendor_bank_history', ()):
        if b['company_id'] == cid:
            bh_by_vendor[b['vendor_ref']['record_id']].append((_stamp(b['observed_at']), _stamp(b['effective_at']), b['revision'], b))

    def _latest_vis_list(items, cutoff_dt, event_dt, strict=False):
        latest = {}
        eligible = {}
        for obs, eff, rev, r in items:
            outside = (obs >= cutoff_dt or eff >= event_dt) if strict else (obs > cutoff_dt or eff > event_dt)
            if outside:
                continue
            eligible[(r['record_id'], rev)] = r
            prev = latest.get(r['record_id'])
            if prev is None or rev > prev['revision']:
                latest[r['record_id']] = r
        return latest, eligible

    # Memoized record reference builder (avoids 1.3M _ref() dict allocations)
    ref_memo = {}

    def _fref(tbl, rec):
        mk = (tbl, id(rec))
        r = ref_memo.get(mk)
        if r is None:
            r = _ref(tbl, rec)
            ref_memo[mk] = r
        return r

    na_templates = {
        code: dict(
            rule_id=code, name=RULE_NAMES[code], status='not_applicable', available=False,
            matched=None, intrinsic_points=None, score=None,
            reason=dict(code='rule_not_applicable', message='Loại giao dịch ngoài phạm vi luật; không phải kết quả không trúng luật.'),
            gaps=[], evidence_refs=[], source_status='not_applicable', source_checksum=None, details={},
        )
        for code in RULE_NAMES
    }
    ext_templates = {
        code: dict(
            rule_id=code, name=RULE_NAMES[code], status='unavailable', available=False,
            matched=None, intrinsic_points=None, score=None,
            reason=dict(
                code='requires_extended_schema',
                message='Luật cần bảng nghiệp vụ mở rộng ngoài hợp đồng canonical (' + ', '.join(ext_tables) + '); không tự giả lập dữ liệu còn thiếu.',
            ),
            gaps=[], evidence_refs=[], source_status='unavailable', source_checksum=None,
            details=dict(
                requires_extended_schema=True, evaluator_registered=True,
                required_input_profile='agent2-rule-snapshot/1.0.0', missing_external_sources=list(ext_tables),
            ),
        )
        for code, ext_tables in EXTENDED_SCHEMA_RULES.items()
    }

    # Cache master-level computations keyed by tuple of visible (record_id, revision)
    master_cache = {}
    e3_cache = {}
    b5_cache = {}
    all_master_max_dt = max(
        (max(it[0], it[1]) for it in (*all_vendor_items, *all_emp_items)),
        default=None,
    )
    full_master_entry = None

    def _get_masters(cutoff_dt, event_dt):
        nonlocal full_master_entry
        if all_master_max_dt is not None and cutoff_dt >= all_master_max_dt and event_dt >= all_master_max_dt and full_master_entry is not None:
            return full_master_entry
        v_lat, v_elig = _latest_vis_list(all_vendor_items, cutoff_dt, event_dt)
        e_lat, e_elig = _latest_vis_list(all_emp_items, cutoff_dt, event_dt)
        v_sig = tuple(sorted((k, r['revision']) for k, r in v_lat.items()))
        e_sig = tuple(sorted((k, r['revision']) for k, r in e_lat.items()))
        sig = (v_sig, e_sig)
        if sig not in master_cache:
            v_list = sorted(v_lat.values(), key=lambda r: (r['record_id'], r['revision']))
            e_list = sorted(e_lat.values(), key=lambda r: (r['record_id'], r['revision']))
            v_refs_all = [_fref('vendors', v) for v in v_list]
            max_v_obs_dt = max((_stamp(v['observed_at']) for v in v_list), default=None)
            # Precompute static B5/E4 field gaps on v_list
            req_v_fields = ('bank_account', 'phone', 'address', 'related_party_disclosed_at')
            v_static_gaps = []
            for vr in v_list:
                for f in req_v_fields:
                    if vr.get(f) is None or f in vr.get('missing_fields', {}):
                        v_static_gaps.append(dict(table='vendors', field=f, code='field_not_provided', record_id=vr['record_id'], revision=vr['revision'], action='Bổ sung định danh NCC.'))
                for f in ('phone', 'address'):
                    val = vr.get(f)
                    if isinstance(val, str) and val.strip() and not normalize(val, f):
                        v_static_gaps.append(dict(table='vendors', field=f, code='identity_content_unknown', record_id=vr['record_id'], revision=vr['revision'], action='Chuẩn hóa thông tin liên hệ.'))

            # Precompute vendor clusters for A3, shared bank-MST for B4, and vendor/employee normalized maps
            adj = defaultdict(set)
            by_attr = defaultdict(list)
            bank_tax_map = defaultdict(set)
            bank_vendors_map = defaultdict(list)
            v_norm_info = {}
            for v in v_list:
                vid = v['record_id']
                b_id = bank_identity(v.get('bank_account') or '', v.get('bank_code') or '')
                raw_acct = normalize(v.get('bank_account') or '', 'bank_account')
                b_tok = b_id or raw_acct
                raw_tax = v.get('tax_id')
                t_mst = normalize_mst(bank_token(raw_tax)) if isinstance(raw_tax, str) and raw_tax.strip() else ''
                inv_mst = bool(isinstance(raw_tax, str) and raw_tax.strip() and bank_token(raw_tax) not in MISSING_CONTACTS and not t_mst)
                if b_tok:
                    by_attr[('bank', b_tok)].append(vid)
                    bank_vendors_map[b_tok].append(v)
                    if t_mst:
                        bank_tax_map[b_tok].add(t_mst)
                p_tok = normalize(v.get('phone') or '', 'phone') if isinstance(v.get('phone'), str) else ''
                if p_tok:
                    by_attr[('phone', p_tok)].append(vid)
                t_tok = normalize(v.get('tax_id') or '', 'tax_id')
                if t_tok:
                    by_attr[('tax_id', t_tok)].append(vid)
                a_tok = normalize(v.get('address') or '', 'address') if isinstance(v.get('address'), str) else ''
                if a_tok:
                    by_attr[('address', a_tok)].append(vid)
                has_contact = ('phone' in v and v['phone'] is not None) or ('address' in v and v['address'] is not None)
                disc_dt = _stamp(v['related_party_disclosed_at']) if v.get('related_party_disclosed_at') else None
                v_norm_info[vid] = (b_id, raw_acct, b_tok, t_mst, inv_mst, t_tok, p_tok, a_tok, has_contact, disc_dt)
            for grp in by_attr.values():
                if len(grp) >= 2:
                    for left in grp:
                        adj[left].update(grp)
            clusters = {}
            for v in v_list:
                vid = v['record_id']
                if vid in clusters:
                    continue
                comp = {vid}; q = [vid]
                while q:
                    cur = q.pop()
                    for nxt in adj.get(cur, ()):
                        if nxt not in comp:
                            comp.add(nxt); q.append(nxt)
                fcomp = frozenset(comp)
                for m in comp:
                    clusters[m] = fcomp

            emp_by_bank = defaultdict(list)
            emp_by_raw_acct = defaultdict(list)
            emp_by_nid = defaultdict(list)
            emp_by_phone = defaultdict(list)
            emp_by_addr = defaultdict(list)
            for emp in e_list:
                eb = bank_identity(emp.get('bank_account') or '', emp.get('bank_code') or '')
                era = normalize(emp.get('bank_account') or '', 'bank_account')
                enid = normalize(emp.get('national_id') or '', 'text')
                eph = normalize(emp.get('phone') or '', 'phone') if isinstance(emp.get('phone'), str) else ''
                ead = normalize(emp.get('address') or '', 'address') if isinstance(emp.get('address'), str) else ''
                if eb:
                    emp_by_bank[eb].append(emp)
                elif era:
                    emp_by_raw_acct[era].append(emp)
                if enid:
                    emp_by_nid[enid].append(emp)
                if eph:
                    emp_by_phone[eph].append(emp)
                if ead:
                    emp_by_addr[ead].append(emp)
            emp_idx = (emp_by_bank, emp_by_raw_acct, emp_by_nid, emp_by_phone, emp_by_addr)

            master_cache[sig] = (
                v_lat, v_elig, v_list, e_lat, e_elig, e_list, v_sig,
                clusters, bank_tax_map, bank_vendors_map,
                v_refs_all, max_v_obs_dt, v_static_gaps, v_norm_info, emp_idx,
            )
        if all_master_max_dt is not None and cutoff_dt >= all_master_max_dt and event_dt >= all_master_max_dt:
            full_master_entry = master_cache[sig]
        return master_cache[sig]

    b7_unavail_tpl = dict(
        rule_id='B7', name=RULE_NAMES['B7'], status='unavailable', available=False,
        matched=None, intrinsic_points=None, score=None,
        reason=dict(code='vendor_bank_history_missing', message='Chưa có lịch sử tài khoản ngân hàng của NCC để kiểm tra B7.'),
        gaps=[], evidence_refs=[], source_status='unavailable', source_checksum=None, details={},
    )
    e3_rule_cache = {}
    b5_rule_cache = {}

    def _f_avail(rec):
        o = _stamp(rec['observed_at']); e = _stamp(rec['effective_at'])
        return o if o >= e else e

    # Sort frame rows by (cutoff, event) so history pools advance monotonically!
    # Also prepare latest visible transactions for history queries
    all_tx_latest = {}
    for (rid, rev), r in tx_by_key.items():
        prev = all_tx_latest.get(rid)
        if prev is None or rev > prev['revision']:
            all_tx_latest[rid] = r
    tx_items_sorted_avail = sorted(
        ((_f_avail(r), _stamp(r['effective_at']), r) for r in tx_by_key.values()),
        key=lambda x: (x[0], x[1], x[2]['record_id'], x[2]['revision']),
    )

    # Incremental history structures as cutoff advances (for strictly prior: avail < cutoff and eff < event)
    from bisect import bisect_left, insort
    from collections import deque
    BENFORD_P1 = [0.0, *[math.log10(1.0 + 1.0 / d) for d in range(1, 10)]]
    CHI2_DF8_ALPHA_005 = 15.50731305586545  # Exact chi-square df=8 p=0.05 critical value

    by_recipient = defaultdict(list)     # rkey -> list of (eff_ts_float, avail_ts_float, row)
    by_creator_rec = defaultdict(list)   # (creator_id, rkey) -> list of (eff_ts_float, avail_ts_float, row)
    by_creator_ym = defaultdict(list)    # (creator_id, year, month) -> list of (eff_ts_float, avail_ts_float, row)
    by_vendor_id = defaultdict(list)     # vendor_id -> list of (eff_ts_float, avail_ts_float, row)
    # True O(1) amortized sliding-window deques & running sums for monotonic streams
    a1_win_q = defaultdict(deque)        # rk -> deque of (eff_s, amount_vnd, row)
    a1_win_sum = Counter()               # rk -> int sum
    a1_win_max = defaultdict(list)       # not needed if we track count >= cap
    a2_win_q = defaultdict(deque)        # (cref_id, rk) -> deque of (eff_s, amount_vnd, row)
    a2_win_sum = Counter()
    a3_win_q = defaultdict(deque)        # vendor_id -> deque of (eff_s, amount_vnd, row)
    a3_win_sum = Counter()
    sameday_rk_q = defaultdict(deque)    # (rk, vn_date) -> deque of (eff_s, amount_vnd, row)
    sameday_rk_sum = Counter()
    sameday_vid_sum = Counter()          # (vid, vn_date) -> int sum
    sameday_vid_rows = defaultdict(list) # (vid, vn_date) -> up to 3 rows for refs
    b2_dup_map = defaultdict(list)       # (vid, amount_vnd, vn_date) -> up to 3 rows
    a4_near_5m = defaultdict(list)       # (cref_id, y, m) -> prebuilt _fref list
    a4_near_20m = defaultdict(list)      # (cref_id, y, m) -> prebuilt _fref list
    a4_count_5m = Counter()
    a4_count_20m = Counter()
    vendor_sorted_amts = defaultdict(list)
    vendor_last_tx = {}                  # vid -> (eff_s, row)
    vendor_tx_count = Counter()
    # Fast O(1)/O(log N) state for A5, D1, D4, D5 when timestamps are monotonic
    kind_sorted_logs = defaultdict(list)
    kind_round_counts = Counter()
    kind_total_counts = Counter()
    disb_first_digit = [0] * 10
    disb_count = 0
    disb_min = None
    disb_max = None
    disb_distinct = set()
    disb_freq = Counter()
    d4_recent_q = deque()
    d4_older_q = deque()
    d4_recent_k = Counter()
    d4_older_k = Counter()
    max_inserted_eff_s = -1e30
    monotonic_eff = True
    by_kind_pos = defaultdict(list)
    disbursements = []
    inserted_latest = {}
    tx_cursor = 0

    def _sync_history_pool(cutoff_dt):
        nonlocal tx_cursor, disb_count, disb_min, disb_max, max_inserted_eff_s, monotonic_eff
        while tx_cursor < len(tx_items_sorted_avail) and tx_items_sorted_avail[tx_cursor][0] < cutoff_dt:
            avail_dt, eff_dt, r = tx_items_sorted_avail[tx_cursor]
            tx_cursor += 1
            rid = r['record_id']
            prev = inserted_latest.get(rid)
            if prev is not None:
                monotonic_eff = False
                if prev['revision'] >= r['revision']:
                    continue
            inserted_latest[rid] = r
            eff_s = eff_dt.timestamp(); avail_s = avail_dt.timestamp()
            if eff_s < max_inserted_eff_s:
                monotonic_eff = False
            else:
                max_inserted_eff_s = eff_s
            amt = r['amount_vnd']; kind = r.get('kind')
            vn_dt = vn_timestamp(r['effective_at'])
            vn_day = vn_dt.date()
            if amt > 0:
                la = math.log1p(amt)
                by_kind_pos[kind].append((eff_s, avail_s, rid, amt, la))
                insort(kind_sorted_logs[kind], la)
                kind_total_counts[kind] += 1
                if amt >= 1_000_000 and amt % 1_000_000 == 0:
                    kind_round_counts[kind] += 1
                if kind not in ('payroll', 'receipt', 'reversal', 'adjustment'):
                    disbursements.append((eff_s, avail_s, rid, amt))
                    disb_count += 1
                    d1_lead = int(str(amt)[0])
                    disb_first_digit[d1_lead] += 1
                    disb_min = amt if disb_min is None or amt < disb_min else disb_min
                    disb_max = amt if disb_max is None or amt > disb_max else disb_max
                    disb_distinct.add(amt)
                    disb_freq[amt] += 1
                    if amt >= 1_000_000:
                        k_end = (amt // 1000) % 1000
                        d4_recent_q.append((eff_s, k_end))
                        d4_recent_k[k_end] += 1
                if kind == 'payment':
                    rk = _recipient_key(r)
                    if rk:
                        by_recipient[rk].append((eff_s, avail_s, r))
                        a1_win_q[rk].append((eff_s, amt, r))
                        a1_win_sum[rk] += amt
                        sameday_rk_q[(rk, vn_day)].append((eff_s, amt, r))
                        sameday_rk_sum[(rk, vn_day)] += amt
                        cref = r.get('created_by_ref')
                        if cref:
                            cid_k = (cref['record_id'], rk)
                            by_creator_rec[cid_k].append((eff_s, avail_s, r))
                            a2_win_q[cid_k].append((eff_s, amt, r))
                            a2_win_sum[cid_k] += amt
                    vref = r.get('vendor_ref')
                    if vref:
                        vid = vref['record_id']
                        by_vendor_id[vid].append((eff_s, avail_s, r))
                        a3_win_q[vid].append((eff_s, amt, r))
                        a3_win_sum[vid] += amt
                        sameday_vid_sum[(vid, vn_day)] += amt
                        if len(sameday_vid_rows[(vid, vn_day)]) < 3:
                            sameday_vid_rows[(vid, vn_day)].append(r)
                        if len(b2_dup_map[(vid, amt, vn_day)]) < 3:
                            b2_dup_map[(vid, amt, vn_day)].append(r)
                        insort(vendor_sorted_amts[vid], amt)
                        vendor_tx_count[vid] += 1
                        prev_last = vendor_last_tx.get(vid)
                        if prev_last is None or eff_s >= prev_last[0]:
                            vendor_last_tx[vid] = (eff_s, r)
                cref = r.get('created_by_ref')
                if cref:
                    ym_k = (cref['record_id'], vn_dt.year, vn_dt.month)
                    by_creator_ym[ym_k].append((eff_s, avail_s, r))
                    if int(5_000_000 * DEFAULT_CONFIG['near_low']) <= amt < 5_000_000:
                        a4_count_5m[ym_k] += 1
                        if len(a4_near_5m[ym_k]) < 8:
                            a4_near_5m[ym_k].append(r)
                    if int(DEFAULT_SPLIT_CAP_VND * DEFAULT_CONFIG['near_low']) <= amt < DEFAULT_SPLIT_CAP_VND:
                        a4_count_20m[ym_k] += 1
                        if len(a4_near_20m[ym_k]) < 8:
                            a4_near_20m[ym_k].append(r)

    ordered_metas = sorted(frame['rows'], key=lambda m: (_stamp(m['as_of']), _stamp(m['event_at']), m['row_index']))
    out_by_key = {}

    for meta in ordered_metas:
        key = (meta['record_id'], meta['revision'])
        tx = tx_by_key[key]
        cutoff_dt = _stamp(meta['as_of']); event_dt = _stamp(meta['event_at'])
        event_s = event_dt.timestamp()
        _sync_history_pool(cutoff_dt)

        (
            v_lat, v_elig, v_list, e_lat, e_elig, e_list, v_sig,
            clusters, bank_tax_map, bank_vendors_map,
            v_refs_all, max_v_obs_dt, v_static_gaps, v_norm_info, emp_idx,
        ) = _get_masters(cutoff_dt, event_dt)

        def _res_entity(lat, elig, ref):
            if ref and (ref['record_id'], ref['revision']) in elig:
                return lat.get(ref['record_id'])
            return None

        cur_vendor = _res_entity(v_lat, v_elig, tx.get('vendor_ref'))
        cur_emp = _res_entity(e_lat, e_elig, tx.get('employee_ref'))
        cur_creator = _res_entity(e_lat, e_elig, tx.get('created_by_ref'))

        # Resolve current allocations, linked invoices, approvals, supporting docs, bank history
        cur_alloc_lat, _ = _latest_vis_list(allocs_by_tx_id.get(tx['record_id'], ()), cutoff_dt, event_dt)
        cur_allocs = [a for a in cur_alloc_lat.values() if a['transaction_ref'] == {'record_id': tx['record_id'], 'revision': tx['revision']}]
        linked_invs = {}
        inv_link_gap = any(a['transaction_ref']['revision'] != tx['revision'] for a in cur_alloc_lat.values())
        for a in cur_allocs:
            iref = a['invoice_ref']
            inv_lat, inv_elig = _latest_vis_list(inv_revs.get(iref['record_id'], ()), cutoff_dt, event_dt)
            inv_obj = inv_elig.get((iref['record_id'], iref['revision']))
            if inv_obj is not None:
                linked_invs[(inv_obj['record_id'], inv_obj['revision'])] = inv_obj
                if inv_obj.get('vendor_ref') and (inv_obj['vendor_ref']['record_id'], inv_obj['vendor_ref']['revision']) not in v_elig:
                    inv_link_gap = True
            else:
                inv_link_gap = True

        prior_allocs = []
        for (iid, _irev) in linked_invs:
            ai_list = allocs_by_inv_id.get(iid, ())
            if len(ai_list) <= 1 and cur_allocs and cur_allocs[0]['invoice_ref']['record_id'] == iid:
                continue
            pa_lat, _ = _latest_vis_list(ai_list, cutoff_dt, event_dt, strict=True)
            for pa in pa_lat.values():
                tref = pa['transaction_ref']
                if tref['record_id'] == tx['record_id']:
                    continue
                htx = tx_by_key.get((tref['record_id'], tref['revision']))
                if htx and _stamp(htx['effective_at']) < event_dt and _f_avail(htx) < cutoff_dt:
                    prior_allocs.append(pa)

        app_items_cur = approvals_by_tx.get(key, ())
        if app_items_cur:
            app_lat, _ = _latest_vis_list(app_items_cur, cutoff_dt, event_dt)
            cur_approvals = sorted(
                (a for a in app_lat.values() if a['transaction_ref'] == {'record_id': tx['record_id'], 'revision': tx['revision']}),
                key=lambda r: (r['record_id'], r['revision']),
            )
        else:
            cur_approvals = []

        if docs_by_subj:
            subj_keys = {('transactions', tx['record_id'], tx['revision'])} | {('invoices', ik[0], ik[1]) for ik in linked_invs}
            doc_map = {}
            for sk in subj_keys:
                if sk in docs_by_subj:
                    d_lat, _ = _latest_vis_list(docs_by_subj[sk], cutoff_dt, event_dt)
                    for d in d_lat.values():
                        doc_map[(d['record_id'], d['revision'])] = d
            cur_docs = sorted(doc_map.values(), key=lambda r: (r['record_id'], r['revision'])) if doc_map else []
        else:
            cur_docs = []

        if cur_vendor and bh_by_vendor and cur_vendor['record_id'] in bh_by_vendor:
            bh_lat, _ = _latest_vis_list(bh_by_vendor[cur_vendor['record_id']], cutoff_dt, event_dt)
            cur_bh = sorted(bh_lat.values(), key=lambda r: (r['record_id'], r['revision']))
        else:
            cur_bh = []

        rk = _recipient_key(tx)
        cref_id = (tx.get('created_by_ref') or {}).get('record_id')
        tx_ctx = vn_posting_context(tx['effective_at'])
        vn_dt = vn_timestamp(tx['effective_at'])
        vn_day = vn_dt.date()
        cluster_ids = clusters.get(cur_vendor['record_id'], frozenset()) if cur_vendor else frozenset()

        if monotonic_eff and event_s > max_inserted_eff_s:
            if rk and rk in a1_win_q:
                q1 = a1_win_q[rk]
                while q1 and (event_s - q1[0][0]) > DEFAULT_CONFIG['short_days'] * 86400:
                    _es, old_a, _or = q1.popleft()
                    a1_win_sum[rk] -= old_a
            if cref_id and rk and (cref_id, rk) in a2_win_q:
                q2 = a2_win_q[(cref_id, rk)]
                while q2 and (event_s - q2[0][0]) > DEFAULT_CONFIG['long_days'] * 86400:
                    _es, old_a, _or = q2.popleft()
                    a2_win_sum[(cref_id, rk)] -= old_a
            if len(cluster_ids) >= 2:
                for cvid in cluster_ids:
                    if cvid in a3_win_q:
                        q3 = a3_win_q[cvid]
                        while q3 and (event_s - q3[0][0]) > 7 * 86400:
                            _es, old_a, _or = q3.popleft()
                            a3_win_sum[cvid] -= old_a
            cluster_rows = []
            if len(cluster_ids) >= 2:
                for cvid in cluster_ids:
                    cluster_rows.extend(r for _es, _am, r in list(a3_win_q.get(cvid, ()))[-8:])
        else:
            def _slice_ts(arr, lo_s, hi_s):
                i0 = bisect_left(arr, (lo_s,))
                i1 = bisect_left(arr, (hi_s,))
                return [r for _es, _av, r in arr[i0:i1] if r['record_id'] != tx['record_id'] and inserted_latest.get(r['record_id']) is r]
            cluster_rows = []
            if len(cluster_ids) >= 2:
                for cvid in cluster_ids:
                    cluster_rows.extend(_slice_ts(by_vendor_id.get(cvid, ()), event_s - 7 * 86400, event_s))

        tx_ref_cur = _fref('transactions', tx)
        v_ref_cur = _fref('vendors', cur_vendor) if cur_vendor else None
        c_ref_cur = _fref('employees', cur_creator) if cur_creator else None
        invs_sorted = sorted(linked_invs.values(), key=lambda r: (r['record_id'], r['revision'])) if len(linked_invs) > 1 else list(linked_invs.values())
        inv_refs_cur = [_fref('invoices', i) for i in invs_sorted]
        app_refs_cur = [_fref('approvals', a) for a in cur_approvals]

        f3_peer_invs = None
        for inv_obj in invs_sorted:
            if inv_obj['kind'] == 'invoice' and inv_obj.get('vendor_ref'):
                n_num = normalize(inv_obj['number'])
                if n_num:
                    peers_f3 = p1_idx['inv_by_vendor_num'].get((inv_obj['vendor_ref']['record_id'], n_num), ())
                    if len(peers_f3) > 1:
                        if f3_peer_invs is None:
                            f3_peer_invs = dict(linked_invs)
                        for p_iid in peers_f3:
                            if p_iid != inv_obj['record_id']:
                                p_lat, _ = _latest_vis_list(inv_revs.get(p_iid, ()), cutoff_dt, event_dt)
                                if p_iid in p_lat:
                                    p_rec = p_lat[p_iid]
                                    f3_peer_invs[(p_rec['record_id'], p_rec['revision'])] = p_rec

        compact_sources_lazy = None
        def _get_compact_sources():
            nonlocal compact_sources_lazy
            if compact_sources_lazy is None:
                if monotonic_eff and event_s > max_inserted_eff_s:
                    sw = [r for _es, _am, r in list(a1_win_q.get(rk, ()))] if rk else []
                    lw = [r for _es, _am, r in list(a2_win_q.get((cref_id, rk), ()))] if (cref_id and rk) else []
                    ym_k0 = (cref_id, vn_dt.year, vn_dt.month)
                    mc = list(a4_near_5m.get(ym_k0, ())) + list(a4_near_20m.get(ym_k0, ())) if cref_id else []
                    vp = [vendor_last_tx[cur_vendor['record_id']][1]] if (cur_vendor and cur_vendor['record_id'] in vendor_last_tx) else []
                    b2p = list(b2_dup_map.get((cur_vendor['record_id'], tx['amount_vnd'], vn_day), ())) if (cur_vendor and tx['kind'] == 'payment' and tx['amount_vnd'] > 0) else []
                else:
                    sw = _slice_ts(by_recipient.get(rk, ()), event_s - DEFAULT_CONFIG['short_days'] * 86400, event_s) if rk else []
                    lw = _slice_ts(by_creator_rec.get((cref_id, rk), ()), event_s - DEFAULT_CONFIG['long_days'] * 86400, event_s) if (cref_id and rk) else []
                    mc = _slice_ts(by_creator_ym.get((cref_id, vn_dt.year, vn_dt.month), ()), -1e30, event_s) if cref_id else []
                    vp = _slice_ts(by_vendor_id.get(cur_vendor['record_id'], ()), -1e30, event_s) if cur_vendor else []
                    b2p = []
                dh = {}
                for hr in (*sw, *lw, *mc, *vp, *cluster_rows, *b2p):
                    dh[(hr['record_id'], hr['revision'])] = hr
                compact_sources_lazy = dict(
                    transactions=[tx],
                    transaction_history=list(dh.values()),
                    vendor=[cur_vendor] if cur_vendor else [],
                    employee=[cur_emp] if cur_emp else [],
                    creator=[cur_creator] if cur_creator else [],
                    vendors=v_list,
                    employees=e_list,
                    invoices=invs_sorted,
                    p1_invoices=sorted(f3_peer_invs.values(), key=lambda r: (r['record_id'], r['revision'])) if f3_peer_invs is not None else (),
                    payment_allocations=sorted(cur_allocs + prior_allocs, key=lambda r: (r['record_id'], r['revision'])),
                    approvals=cur_approvals,
                    supporting_documents=cur_docs,
                    vendor_bank_history=cur_bh,
                )
            return compact_sources_lazy

        dummy_plan = dict(gaps=[])

        # Advance D4 sliding deques when monotonic
        if monotonic_eff and event_s > max_inserted_eff_s:
            while d4_recent_q and (event_s - d4_recent_q[0][0]) > 30 * 86400:
                old_es, old_k = d4_recent_q.popleft()
                d4_recent_k[old_k] -= 1
                if (event_s - old_es) <= 120 * 86400:
                    d4_older_q.append((old_es, old_k))
                    d4_older_k[old_k] += 1
            while d4_older_q and (event_s - d4_older_q[0][0]) > 120 * 86400:
                _oes, old_k = d4_older_q.popleft()
                d4_older_k[old_k] -= 1
            fast_stats_ok = True
        else:
            fast_stats_ok = False
            kind_hist = [
                amt for eff_s, _av, rid, amt, _la in by_kind_pos.get(tx['kind'], ())
                if rid != tx['record_id'] and eff_s < event_s and inserted_latest.get(rid, {}).get('amount_vnd') == amt
            ]
            disb_hist = [
                (eff_s, amt) for eff_s, _av, rid, amt in disbursements
                if rid != tx['record_id'] and eff_s < event_s and inserted_latest.get(rid, {}).get('amount_vnd') == amt
            ]

        rules_out = []
        tx_kind = tx['kind']
        for code in RULE_NAMES:
            applicable = not KINDS.get(code) or tx_kind in KINDS[code]
            if code == 'P2' and tx_kind != 'payment':
                applicable = False
            if not applicable:
                rules_out.append(na_templates[code])
                continue
            if code in ext_templates:
                rules_out.append(ext_templates[code])
                continue
            if code == 'B7' and (not cur_vendor or not cur_bh):
                rules_out.append(b7_unavail_tpl)
                continue

            if code == 'E3':
                if cur_vendor and v_list:
                    ekey = (v_sig, cur_vendor['record_id'])
                    cached_e3 = e3_rule_cache.get(ekey)
                    if cached_e3 is None:
                        ev = _e3(dict(vendor=[cur_vendor], vendors=v_list))
                        cached_e3 = dict(
                            rule_id='E3', name=RULE_NAMES['E3'], status='unavailable', available=False,
                            matched=None, intrinsic_points=None, score=None, reason=None, gaps=[],
                            evidence_refs=v_refs_all, source_status='ready', source_checksum=None, details=ev['details'],
                        )
                        if 'error' in ev:
                            cached_e3['reason'] = dict(zip(('code', 'message'), ev['error']))
                        else:
                            cached_e3.update(
                                status='evaluated_hit' if ev['matched'] else 'evaluated_no_hit',
                                available=True, matched=ev['matched'],
                                intrinsic_points=ev['intrinsic_points'], score=ev['score'],
                            )
                        e3_rule_cache[ekey] = cached_e3
                    rules_out.append(cached_e3)
                else:
                    rules_out.append(dict(
                        rule_id='E3', name=RULE_NAMES['E3'], status='unavailable', available=False,
                        matched=None, intrinsic_points=None, score=None,
                        reason=dict(code='rule_sources_unavailable', message='Chưa đủ nguồn để đánh giá luật.'),
                        gaps=[dict(table='vendors', field='name', code='no_visible_source', action='Bổ sung danh mục nhà cung cấp.')],
                        evidence_refs=[], source_status='unavailable', source_checksum=None, details={},
                    ))
                continue

            if code in ('B5', 'E4'):
                if cur_vendor and v_list and not v_static_gaps and (max_v_obs_dt is None or max_v_obs_dt <= event_dt):
                    disc_dt = v_norm_info[cur_vendor['record_id']][9]
                    is_disc_now = bool(disc_dt is not None and disc_dt <= event_dt)
                    bkey = (code, v_sig, cur_vendor['record_id'], meta['company_id'], is_disc_now)
                    cached_b5 = b5_rule_cache.get(bkey)
                    if cached_b5 is None:
                        ev_key = (v_sig, cur_vendor['record_id'], meta['company_id'], is_disc_now)
                        if ev_key not in b5_cache:
                            b5_cache[ev_key] = vendor_identity_rules.evaluate(dict(vendor=[cur_vendor], vendors=v_list), meta)
                        ev = b5_cache[ev_key]
                        cached_b5 = dict(
                            rule_id=code, name=RULE_NAMES[code],
                            status='evaluated_hit' if ev['matched'] else 'evaluated_no_hit',
                            available=True, matched=ev['matched'],
                            intrinsic_points=ev['intrinsic_points'], score=ev['score'],
                            reason=None, gaps=[], evidence_refs=v_refs_all,
                            source_status='ready', source_checksum=None, details=ev['details'],
                        )
                        b5_rule_cache[bkey] = cached_b5
                    rules_out.append(cached_b5)
                else:
                    v_gaps = []
                    if not cur_vendor or not v_list:
                        v_gaps.append(dict(table='vendors', field='*', code='no_visible_source', action='Bổ sung danh mục nhà cung cấp.'))
                    else:
                        if v_static_gaps:
                            v_gaps.extend(v_static_gaps[:10])
                        if len(v_gaps) < 10 and max_v_obs_dt is not None and max_v_obs_dt > event_dt:
                            for vr in v_list:
                                if _stamp(vr['observed_at']) > event_dt:
                                    v_gaps.append(dict(table='vendors', field='observed_at', code='native_master_not_known_at_event', record_id=vr['record_id'], revision=vr['revision'], action='Kiểm tra observed_at.'))
                                    if len(v_gaps) >= 10:
                                        break
                    rules_out.append(dict(
                        rule_id=code, name=RULE_NAMES[code], status='unavailable', available=False,
                        matched=None, intrinsic_points=None, score=None,
                        reason=dict(code='rule_sources_unavailable', message='Chưa đủ nguồn để đánh giá luật.'),
                        gaps=v_gaps[:10], evidence_refs=[], source_status='unavailable', source_checksum=None, details={},
                    ))
                continue

            if code == 'P1':
                p1_state = _fast_p1_state(p1_idx, tx)
                if not p1_state['available']:
                    rules_out.append({
                        'rule_id': 'P1', 'name': RULE_NAMES['P1'], 'status': 'unavailable', 'available': False,
                        'matched': None, 'intrinsic_points': None, 'score': None,
                        'reason': {'code': 'rule_sources_unavailable', 'message': 'Chưa đủ nguồn để đánh giá luật.'},
                        'gaps': p1_state['gaps'], 'evidence_refs': [], 'source_status': 'unavailable', 'source_checksum': None, 'details': {},
                    })
                else:
                    # Fast O(1) exact path for single-invoice single-allocation first payment
                    fast_p1_done = False
                    if (len(cur_allocs) == 1 and len(invs_sorted) == 1 and not prior_allocs
                            and len(p1_idx['tx_revs'].get(tx['record_id'], ())) == 1
                            and not p1_idx['corr_tx_ids_by_target'].get(tx['record_id'])):
                        inv0 = invs_sorted[0]; al0 = cur_allocs[0]; iid0 = inv0['record_id']
                        v0 = inv0.get('vendor_ref')
                        n0 = p1_idx['inv_norm_num'].get(id(inv0), '') if inv0['kind'] == 'invoice' else ''
                        cids0 = p1_idx['claim_ids_by_inv'].get(iid0, ())
                        if (inv0['kind'] == 'invoice' and inv0['amount_vnd'] > 0 and v0 and n0 and cur_vendor
                                and len(p1_idx['inv_revs'].get(iid0, ())) == 1
                                and not p1_idx['inv_adj_neighbors'].get(iid0)
                                and len(p1_idx['alloc_ids_by_inv'].get(iid0, ())) == 1
                                and len(p1_idx['inv_by_vendor_num'].get((v0['record_id'], n0), ())) <= 1
                                and al0['kind'] == 'allocation' and 0 < al0['amount_vnd'] <= tx['amount_vnd'] and tx['amount_vnd'] > 0
                                and len(cids0) == 1):
                            only_cid0 = next(iter(cids0))
                            c_revs0 = p1_idx['claim_revs'].get(only_cid0, ())
                            if len(c_revs0) == 1:
                                c0 = c_revs0[0][3]
                                p1_refs_fast = [inv_refs_cur[0], _fref('payment_allocations', al0), _fref('payment_history_coverage', c0), tx_ref_cur, v_ref_cur]
                                rules_out.append({
                                    'rule_id': 'P1', 'name': RULE_NAMES['P1'], 'status': 'evaluated_no_hit', 'available': True,
                                    'matched': False, 'intrinsic_points': 0, 'score': 0, 'reason': None, 'gaps': [],
                                    'evidence_refs': p1_refs_fast, 'source_status': 'ready', 'source_checksum': None,
                                    'details': {
                                        'version': p1_evaluation.VERSION,
                                        'tolerance_vnd': p1_evaluation.TOLERANCE_VND,
                                        'invoice_checks': [{
                                            'vendor_id': v0['record_id'], 'normalized_invoice_number': n0,
                                            'invoice_refs': [{'record_id': iid0, 'revision': inv0['revision']}],
                                            'invoice_gross_vnd': inv0['amount_vnd'], 'prior_paid_vnd': 0,
                                            'current_allocated_vnd': al0['amount_vnd'], 'cumulative_paid_vnd': al0['amount_vnd'],
                                            'excess_vnd': max(0, al0['amount_vnd'] - inv0['amount_vnd']),
                                            'previous_payment': False, 'matched': False,
                                            'prior_allocation_refs': [],
                                            'current_allocation_refs': [{'record_id': al0['record_id'], 'revision': al0['revision']}],
                                            'simultaneous_allocation_refs': [], 'related_transaction_refs': [],
                                        }],
                                        'simultaneous_checks': [],
                                        'history_basis': 'source_declared_complete_scope_not_independent_verification_of_external_books',
                                        'row_policy': 'strict_prior_plus_current; previous_payment_required; simultaneous_checks_do_not_contribute_to_row',
                                    },
                                })
                                fast_p1_done = True
                    if not fast_p1_done:
                        cand_cur_aids = p1_idx['alloc_ids_by_tx'].get(tx['record_id'], ())
                        cur_a = [a for a in _latest_visible_for_ids(p1_idx['alloc_revs'], cand_cur_aids, cutoff_dt, event_dt) if a['transaction_ref']['record_id'] == tx['record_id']]
                        inv_ids = {a['invoice_ref']['record_id'] for a in cur_a}
                        for iid in list(inv_ids):
                            for nb in p1_idx['inv_adj_neighbors'].get(iid, ()):
                                inv_ids.add(nb)
                            for _o, _e, _rv, ir in p1_idx['inv_revs'].get(iid, ()):
                                if ir['kind'] == 'invoice' and ir.get('vendor_ref'):
                                    vk = (ir['vendor_ref']['record_id'], normalize(ir['number']))
                                    inv_ids.update(p1_idx['inv_by_vendor_num'].get(vk, ()))
                        p1_invs = [r for iid in inv_ids for o, e, _rv, r in p1_idx['inv_revs'].get(iid, ()) if o <= cutoff_dt and e <= event_dt]
                        rel_aids = set()
                        for iid in inv_ids:
                            rel_aids.update(p1_idx['alloc_ids_by_inv'].get(iid, ()))
                        p1_allocs = [r for aid in rel_aids for o, e, _rv, r in p1_idx['alloc_revs'].get(aid, ()) if o <= cutoff_dt and e <= event_dt and r['invoice_ref']['record_id'] in inv_ids]
                        rel_tids = {a['transaction_ref']['record_id'] for a in p1_allocs} | {tx['record_id']}
                        for tid in list(rel_tids):
                            rel_tids.update(p1_idx['corr_tx_ids_by_target'].get(tid, ()))
                        p1_txs = [r for tid in rel_tids for o, e, _rv, r in p1_idx['tx_revs'].get(tid, ()) if o <= cutoff_dt and e <= event_dt]
                        p1_vends = [v_elig[p1_inputs_id] for r in p1_invs + p1_txs if r.get('vendor_ref') and (p1_inputs_id := (r['vendor_ref']['record_id'], r['vendor_ref']['revision'])) in v_elig]
                        rel_cids = set()
                        for iid in inv_ids:
                            rel_cids.update(p1_idx['claim_ids_by_inv'].get(iid, ()))
                        p1_covs = _latest_visible_for_ids(p1_idx['claim_revs'], rel_cids, cutoff_dt, event_dt)
                        p1_bound = dict(p1_invoices=p1_invs, p1_allocations=p1_allocs, p1_transactions=p1_txs, p1_vendors=p1_vends, payment_history_coverage=p1_covs)
                        ev = p1_evaluation.evaluate(p1_bound, meta)
                        seen_p1_r = {}
                        for tbl_n, recs_n in (('invoices', p1_invs), ('payment_allocations', p1_allocs), ('payment_history_coverage', p1_covs), ('transactions', p1_txs), ('vendors', p1_vends)):
                            for r_n in recs_n:
                                seen_p1_r[(tbl_n, r_n['record_id'], r_n['revision'])] = _fref(tbl_n, r_n)
                        seen_p1_r[('transactions', tx['record_id'], tx['revision'])] = tx_ref_cur
                        p1_base = {
                            'rule_id': 'P1', 'name': RULE_NAMES['P1'], 'status': 'unavailable', 'available': False,
                            'matched': None, 'intrinsic_points': None, 'score': None, 'reason': None, 'gaps': [],
                            'evidence_refs': [seen_p1_r[rk_p] for rk_p in sorted(seen_p1_r)], 'source_status': 'ready',
                            'source_checksum': None, 'details': ev['details'],
                        }
                        if 'error' in ev:
                            p1_base['reason'] = {'code': ev['error'][0], 'message': ev['error'][1]}
                        else:
                            p1_base.update(status='evaluated_hit' if ev['matched'] else 'evaluated_no_hit',
                                           available=True, matched=ev['matched'],
                                           intrinsic_points=ev['intrinsic_points'], score=ev['score'])
                        rules_out.append(p1_base)
                continue

            # Fast O(1) path for A5, D1, D4, D5 when timestamps are monotonic
            if code == 'A5':
                if fast_stats_ok:
                    amt = tx['amount_vnd']
                    n_k = kind_total_counts[tx['kind']]
                    if tx['kind'] in ('payroll', 'receipt', 'reversal') or amt <= 0:
                        ev = dict(unavailable=('non_expense_kind', 'Chỉ kiểm tra làm tròn triệu/chục triệu VND trên khoản chi dương.'), gaps=[])
                    elif n_k < 5:
                        ev = dict(unavailable=('insufficient_history_for_round_baseline', 'Cần tối thiểu 5 giao dịch lịch sử cùng loại.'), gaps=[])
                    else:
                        slogs = kind_sorted_logs[tx['kind']]
                        mid = n_k // 2
                        med = slogs[mid] if n_k % 2 == 1 else 0.5 * (slogs[mid - 1] + slogs[mid])
                        is_rm = (amt >= 1_000_000 and amt % 1_000_000 == 0)
                        is_r10m = (amt >= 10_000_000 and amt % 10_000_000 == 0)
                        pr_rate = kind_round_counts[tx['kind']] / n_k
                        raw_desc = str(tx.get('description') or '').lower()
                        is_ret = any(kw in raw_desc for kw in RETAINER_KEYWORDS)
                        if is_rm and not is_ret and pr_rate < 0.5:
                            sample_logs = slogs if n_k <= 257 else slogs[::max(1, n_k // 256)]
                            mad = median(abs(v - med) for v in sample_logs)
                        else:
                            mad = 0.25 * 0.6744897501960817
                        scale = max(0.25, mad / 0.6744897501960817)
                        rz = (math.log1p(amt) - med) / scale
                        hit_a5 = (not is_ret and is_rm and pr_rate < 0.5 and (rz > DEFAULT_CONFIG['round_z'] or (is_r10m and rz > 1.5)))
                        ev = dict(
                            matched=hit_a5, score=WEIGHTS['A5'] if hit_a5 else 0, intrinsic_points=WEIGHTS['A5'] if hit_a5 else 0,
                            evidence_refs=[tx_ref_cur],
                            details=dict(amount_vnd=amt, is_round_million=is_rm, is_round_ten_million=is_r10m,
                                         is_retainer_exempt=is_ret, prior_sample_count=n_k,
                                         prior_round_million_rate=round(pr_rate, 4), robust_z=round(rz, 4)),
                        )
                else:
                    s_a5 = dict(transactions=[tx], transaction_history=[dict(kind=tx['kind'], amount_vnd=v) for v in kind_hist])
                    ev = _eval_a5(s_a5, meta, dummy_plan)
            elif code == 'D1' and fast_stats_ok:
                inc_cur = tx['kind'] not in ('payroll', 'receipt', 'reversal', 'adjustment') and tx['amount_vnd'] > 0
                tot_n = disb_count + int(inc_cur)
                cur_lead = int(str(tx['amount_vnd'])[0]) if inc_cur else 0
                c_min = min(disb_min, tx['amount_vnd']) if (inc_cur and disb_min is not None) else (tx['amount_vnd'] if inc_cur else disb_min)
                c_max = max(disb_max, tx['amount_vnd']) if (inc_cur and disb_max is not None) else (tx['amount_vnd'] if inc_cur else disb_max)
                n_dist = len(disb_distinct) + int(inc_cur and tx['amount_vnd'] not in disb_distinct)
                if tot_n < 60:
                    ev = dict(unavailable=('benford_insufficient_sample', 'Cần tối thiểu 60 khoản chi dương trong kỳ.'), gaps=[])
                elif n_dist < 100 or not c_min or (c_max / c_min) < 100:
                    ev = dict(unavailable=('benford_not_evaluable', 'Tập số tiền chưa đủ độ phân tán cho kiểm định Benford D1.'), gaps=[])
                else:
                    obs_c = [disb_first_digit[d] + int(inc_cur and cur_lead == d) for d in range(1, 10)]
                    exp_c = [BENFORD_P1[d] * tot_n for d in range(1, 10)]
                    if min(exp_c) < 5:
                        ev = dict(unavailable=('benford_not_evaluable', 'Tần suất kỳ vọng < 5.'), gaps=[])
                    else:
                        stat = sum((o - e) ** 2 / e for o, e in zip(obs_c, exp_c))
                        mad_v = sum(abs(obs_c[i] / tot_n - BENFORD_P1[i + 1]) for i in range(9)) / 9.0
                        hit_d1 = bool(stat > CHI2_DF8_ALPHA_005 and mad_v > 0.015)
                        ev = dict(
                            matched=hit_d1, score=0, intrinsic_points=0, evidence_refs=[tx_ref_cur],
                            details=dict(status='evaluated', rows=tot_n, kind='first', statistic=round(stat, 4),
                                         mad=round(mad_v, 5), adds_transaction_score=False, scoring_role='aggregate_diagnostic'),
                        )
            elif code == 'D5' and fast_stats_ok:
                inc_cur = tx['kind'] not in ('payroll', 'receipt', 'reversal', 'adjustment') and tx['amount_vnd'] > 0
                tot_n = disb_count + int(inc_cur)
                cur_lead = int(str(tx['amount_vnd'])[0]) if inc_cur else 0
                c_min = min(disb_min, tx['amount_vnd']) if (inc_cur and disb_min is not None) else (tx['amount_vnd'] if inc_cur else disb_min)
                c_max = max(disb_max, tx['amount_vnd']) if (inc_cur and disb_max is not None) else (tx['amount_vnd'] if inc_cur else disb_max)
                n_dist = len(disb_distinct) + int(inc_cur and tx['amount_vnd'] not in disb_distinct)
                if tot_n < 60:
                    ev = dict(unavailable=('benford_mad_insufficient_sample', 'Cần tối thiểu 60 khoản chi dương.'), gaps=[])
                elif n_dist < 20 or not c_min or (c_max / c_min) < 10:
                    ev = dict(unavailable=('benford_mad_narrow_range', 'Phạm vi số tiền quá hẹp.'), gaps=[])
                else:
                    mad_v = sum(abs((disb_first_digit[d] + int(inc_cur and cur_lead == d)) / tot_n - BENFORD_P1[d]) for d in range(1, 10)) / 9.0
                    ev = dict(
                        matched=mad_v > 0.015, score=0, intrinsic_points=0, evidence_refs=[tx_ref_cur],
                        details=dict(rows=tot_n, mad=round(mad_v, 5), mad_threshold=0.015, adds_transaction_score=False),
                    )
            elif code == 'D4' and fast_stats_ok:
                inc_cur = tx['kind'] not in ('payroll', 'receipt', 'reversal', 'adjustment') and tx['amount_vnd'] >= 1_000_000
                rec_n = len(d4_recent_q) + int(inc_cur)
                old_n = len(d4_older_q)
                if rec_n < 30 or old_n < 30:
                    ev = dict(unavailable=('suffix_baseline_insufficient', 'Cần tối thiểu 30 khoản chi >= 1 triệu VND ở cả hai cửa sổ.'), gaps=[])
                else:
                    cur_k = (tx['amount_vnd'] // 1000) % 1000 if inc_cur else -1
                    comps = []; hit_d4 = False
                    for ending in (0, 500, 990, 999):
                        cr = (d4_recent_k[ending] + int(inc_cur and cur_k == ending)) / rec_n
                        orr = d4_older_k[ending] / old_n
                        sig = bool(orr > 0 and cr >= 0.25 and cr > orr * 2.0)
                        hit_d4 |= sig
                        comps.append(dict(thousand_vnd_suffix=f'{ending:03d}000', current_rate=round(cr, 4), baseline_rate=round(orr, 4), signal=sig))
                    ev = dict(
                        matched=hit_d4, score=0, intrinsic_points=0, evidence_refs=[tx_ref_cur],
                        details=dict(recent_count=rec_n, baseline_count=old_n, suffix_comparison=comps, adds_transaction_score=False),
                    )
            elif code in ('D1', 'D4', 'D5'):
                sample_disb = disb_hist[-500:]
                s_d = dict(
                    transactions=[tx],
                    transaction_history=[
                        dict(kind='payment', amount_vnd=amt, effective_at=datetime.fromtimestamp(es, tz=timezone.utc).isoformat())
                        for es, amt in sample_disb
                    ],
                )
                ev = _CANONICAL_EVALUATORS[code](s_d, meta, dummy_plan)
            else:
                if code == 'A3':
                    if not cur_vendor or not v_list or tx['amount_vnd'] <= 0:
                        ev = dict(unavailable=('vendor_missing', 'Cần nhà cung cấp để kiểm tra chia nhỏ qua cụm NCC.'), gaps=[])
                    elif len(cluster_ids) < 2:
                        cap_v, _ = _effective_threshold(tx, cur_approvals)
                        vid = cur_vendor['record_id']
                        ev = dict(
                            matched=False, score=0, intrinsic_points=0,
                            evidence_refs=[tx_ref_cur, v_ref_cur],
                            details=dict(cluster_vendor_ids=[vid], active_vendor_ids=[vid], window_total_vnd=tx['amount_vnd'], threshold_vnd=cap_v),
                        )
                    else:
                        cap_v, _ = _effective_threshold(tx, cur_approvals)
                        peer_r = [h for h in cluster_rows if h['record_id'] != tx['record_id'] and 0 <= (event_s - _stamp(h['effective_at']).timestamp()) <= 7 * 86400]
                        win_r = peer_r + [tx]
                        act_v = {(r.get('vendor_ref') or {}).get('record_id') for r in win_r if r.get('vendor_ref')}
                        tot_v = sum(r['amount_vnd'] for r in win_r)
                        hit_a3 = (len(act_v) >= 2 and all(0 < r['amount_vnd'] < cap_v for r in win_r) and tot_v >= cap_v)
                        c_vends = [v_lat[cv] for cv in sorted(cluster_ids) if cv in v_lat]
                        ev = dict(
                            matched=hit_a3, score=WEIGHTS['A3'] if hit_a3 else 0, intrinsic_points=WEIGHTS['A3'] if hit_a3 else 0,
                            evidence_refs=_sorted_refs([('transactions', tx), *[('transactions', r) for r in peer_r], *[('vendors', v) for v in c_vends]]),
                            details=dict(cluster_vendor_ids=sorted(cluster_ids), active_vendor_ids=sorted(act_v), window_total_vnd=tot_v, threshold_vnd=cap_v),
                        )
                elif code == 'B4':
                    if not cur_vendor or tx['amount_vnd'] <= 0:
                        ev = dict(unavailable=('vendor_missing', 'Cần hồ sơ NCC để kiểm tra B4.'), gaps=[])
                    else:
                        vid = cur_vendor['record_id']
                        b_id, raw_acct, b_tok, t_mst, inv_mst, _t_tok, _p_tok, _a_tok, _has_c, _ddt = v_norm_info[vid]
                        v_acct = raw_acct or normalize(tx.get('bank_account') or '', 'bank_account')
                        miss_both = (not t_mst and not v_acct)
                        v_bank_eff = b_tok or v_acct
                        dist_msts = bank_tax_map.get(v_bank_eff, set()) if v_bank_eff else set()
                        shared_bm = len(dist_msts) >= 2
                        hi_miss = (tx['amount_vnd'] >= DEFAULT_SPLIT_CAP_VND and (miss_both or inv_mst))
                        if not ('tax_id' in cur_vendor or shared_bm or miss_both):
                            ev = dict(unavailable=('tax_id_not_provided', 'Chưa có trường mã số thuế NCC.'), gaps=[])
                        else:
                            hit_b4 = bool(hi_miss or shared_bm or inv_mst)
                            if shared_bm:
                                conf_v = [p for p in bank_vendors_map.get(v_bank_eff, ()) if p['record_id'] != vid and normalize_mst(bank_token(p.get('tax_id') or ''))]
                                refs_b4 = _sorted_refs([('transactions', tx), ('vendors', cur_vendor), *[('vendors', p) for p in conf_v]])
                            else:
                                refs_b4 = [tx_ref_cur, v_ref_cur]
                            ev = dict(
                                matched=hit_b4, score=WEIGHTS['B4'] if hit_b4 else 0, intrinsic_points=WEIGHTS['B4'] if hit_b4 else 0,
                                evidence_refs=refs_b4,
                                details=dict(vendor_id=vid, valid_mst=bool(t_mst), invalid_mst_format=inv_mst,
                                             missing_tax_and_bank_kyc=miss_both, shared_bank_distinct_tax_ids=sorted(dist_msts)),
                            )
                elif code == 'B1':
                    if not cur_vendor and not tx.get('bank_account'):
                        ev = dict(unavailable=('vendor_or_recipient_bank_missing', 'Cần thông tin NCC hoặc tài khoản nhận tiền.'), gaps=[])
                    else:
                        lines_b1 = tx.get('accounting_lines') or ()
                        adv_141 = bool(tx.get('employee_ref')) or any(str(l.get('account', '')).startswith('141') for l in lines_b1)
                        emp_by_bank, emp_by_raw_acct, emp_by_nid, _, _ = emp_idx
                        if cur_vendor:
                            b_id, raw_acct, _bt, _tm, _im, v_tax, _pt, _at, _hc, disc_dt = v_norm_info[cur_vendor['record_id']]
                            disc_b1 = bool(disc_dt is not None and disc_dt <= event_dt)
                        else:
                            b_id = ''; raw_acct = ''; v_tax = ''; disc_b1 = False
                        tx_b = bank_identity(tx.get('bank_account') or '', tx.get('bank_code') or '') if tx.get('bank_account') else b_id
                        tx_ra = normalize(tx.get('bank_account') or '', 'bank_account') if tx.get('bank_account') else raw_acct
                        matched_emps = {}
                        if not adv_141 and not disc_b1:
                            if tx_b and tx_b in emp_by_bank:
                                for e in emp_by_bank[tx_b]:
                                    matched_emps[e['record_id']] = e
                            elif not tx_b and tx_ra and tx_ra in emp_by_raw_acct:
                                for e in emp_by_raw_acct[tx_ra]:
                                    matched_emps[e['record_id']] = e
                            if v_tax and v_tax in emp_by_nid:
                                for e in emp_by_nid[v_tax]:
                                    matched_emps[e['record_id']] = e
                        dup_tx_ids = []
                        if cur_vendor and tx_kind == 'payment' and tx['amount_vnd'] > 0 and prior_allocs:
                            for pa in prior_allocs:
                                iref_pa = pa['invoice_ref']
                                inv_pa = linked_invs.get((iref_pa['record_id'], iref_pa['revision']))
                                if inv_pa and inv_pa.get('kind') == 'invoice' and pa['amount_vnd'] >= inv_pa['amount_vnd']:
                                    dup_tx_ids.append(pa['transaction_ref']['record_id'])
                        hit_b1 = bool(matched_emps or dup_tx_ids)
                        if matched_emps:
                            refs_b1 = _sorted_refs([('transactions', tx), *([('vendors', cur_vendor)] if cur_vendor else []), *[('employees', e) for e in matched_emps.values()]])
                        else:
                            refs_b1 = [tx_ref_cur, v_ref_cur] if cur_vendor else [tx_ref_cur]
                        ev = dict(
                            matched=hit_b1, score=WEIGHTS['B1'] if hit_b1 else 0, intrinsic_points=WEIGHTS['B1'] if hit_b1 else 0,
                            evidence_refs=refs_b1,
                            details=dict(matched_employee_ids=sorted(matched_emps), duplicate_full_invoice_payment_tx_ids=sorted(set(dup_tx_ids)),
                                         exempt_advance_reimbursement_141=adv_141, related_party_disclosed=disc_b1),
                        )
                elif code == 'B2':
                    if not cur_vendor:
                        ev = dict(unavailable=('vendor_missing', 'Cần thông tin nhà cung cấp để đối chiếu B2.'), gaps=[])
                    else:
                        vid = cur_vendor['record_id']
                        _bi, _ra, _bt, _tm, _im, _tt, p_tok, a_tok, has_c, disc_dt = v_norm_info[vid]
                        disc_b2 = bool(disc_dt is not None and disc_dt <= event_dt)
                        _, _, _, emp_by_phone, emp_by_addr = emp_idx
                        c_emps = {}
                        if not disc_b2:
                            if p_tok and p_tok in emp_by_phone:
                                for e in emp_by_phone[p_tok]:
                                    c_emps[e['record_id']] = e
                            if a_tok and a_tok in emp_by_addr:
                                for e in emp_by_addr[a_tok]:
                                    c_emps[e['record_id']] = e
                        if fast_stats_ok:
                            dup_sd = list(b2_dup_map.get((vid, tx['amount_vnd'], vn_day), ())) if (tx_kind == 'payment' and tx['amount_vnd'] > 0) else []
                        else:
                            dup_sd = [h for h in _get_compact_sources()['transaction_history'] if h.get('kind') == 'payment' and h['amount_vnd'] == tx['amount_vnd'] and (h.get('vendor_ref') or {}).get('record_id') == vid and vn_timestamp(h['effective_at']).date() == vn_day] if (tx_kind == 'payment' and tx['amount_vnd'] > 0) else []
                        if not has_c and not dup_sd and not c_emps:
                            ev = dict(unavailable=('vendor_contact_fields_missing', 'Chưa có SĐT/địa chỉ NCC để đối chiếu B2.'), gaps=[])
                        else:
                            hit_b2 = bool(c_emps or dup_sd)
                            if c_emps or dup_sd:
                                refs_b2 = _sorted_refs([('transactions', tx), ('vendors', cur_vendor), *[('employees', e) for e in c_emps.values()], *[('transactions', h) for h in dup_sd]])
                            else:
                                refs_b2 = [tx_ref_cur, v_ref_cur]
                            ev = dict(
                                matched=hit_b2, score=WEIGHTS['B2'] if hit_b2 else 0, intrinsic_points=WEIGHTS['B2'] if hit_b2 else 0,
                                evidence_refs=refs_b2,
                                details=dict(matched_employee_ids=sorted(c_emps), duplicate_same_day_payment_ids=[h['record_id'] for h in dup_sd], related_party_disclosed=disc_b2),
                            )
                elif code == 'A1' and fast_stats_ok and rk and tx['amount_vnd'] > 0:
                    q1 = a1_win_q.get(rk)
                    cap_v, basis_v = _effective_threshold(tx, cur_approvals)
                    cash_c = _statutory_cash_limit(tx['effective_at'])
                    tot_a1 = (a1_win_sum[rk] if q1 else 0) + tx['amount_vnd']
                    min_req = min(cash_c, int(DEFAULT_SPLIT_CAP_VND * DEFAULT_CONFIG['short_total_ratio']), int(cap_v * DEFAULT_CONFIG['short_total_ratio']))
                    if not q1 or tot_a1 < min_req:
                        peers_a1 = [r for _es, _am, r in q1] if q1 else []
                        refs_a1 = _sorted_refs([('transactions', tx), *[('transactions', r) for r in peers_a1], *([('vendors', cur_vendor)] if cur_vendor else [])]) if peers_a1 else ([tx_ref_cur, v_ref_cur] if v_ref_cur else [tx_ref_cur])
                        ev = dict(
                            matched=False, score=0, intrinsic_points=0,
                            evidence_refs=refs_a1,
                            details=dict(recipient_key=rk, window_days=DEFAULT_CONFIG['short_days'], split_count=len(peers_a1) + 1,
                                         window_total_vnd=tot_a1, threshold_vnd=cap_v, threshold_basis=basis_v,
                                         exempt_documented_installment=False, related_transaction_ids=[r['record_id'] for r in peers_a1]),
                        )
                    else:
                        s_a1 = dict(
                            transactions=[tx], transaction_history=[r for _es, _am, r in q1],
                            vendor=[cur_vendor] if cur_vendor else [], invoices=invs_sorted,
                            payment_allocations=cur_allocs + prior_allocs, approvals=cur_approvals,
                        )
                        ev = _eval_a1(s_a1, meta, dummy_plan)
                elif code == 'A2' and fast_stats_ok and cref_id and rk and tx['amount_vnd'] > 0:
                    q2 = a2_win_q.get((cref_id, rk))
                    cap_v, basis_v = _effective_threshold(tx, cur_approvals)
                    if not q2 or len(q2) < 2 or (a2_win_sum[(cref_id, rk)] + tx['amount_vnd']) < cap_v or tx['amount_vnd'] >= cap_v:
                        peers_a2 = [r for _es, _am, r in q2] if q2 else []
                        if not peers_a2:
                            refs_a2 = [c_ref_cur, tx_ref_cur] if c_ref_cur else [tx_ref_cur]
                        else:
                            t_r2 = sorted([tx_ref_cur, *[_fref('transactions', r) for r in peers_a2]], key=lambda x: (x['record_id'], x['revision']))
                            refs_a2 = [c_ref_cur, *t_r2] if c_ref_cur else t_r2
                        ev = dict(
                            matched=False, score=0, intrinsic_points=0,
                            evidence_refs=refs_a2,
                            details=dict(creator_id=cref_id, recipient_key=rk, window_days=DEFAULT_CONFIG['long_days'],
                                         split_count=len(peers_a2) + 1, window_total_vnd=(a2_win_sum[(cref_id, rk)] if q2 else 0) + tx['amount_vnd'],
                                         threshold_vnd=cap_v, threshold_basis=basis_v, exempt_documented_installment=False),
                        )
                    else:
                        s_a2 = dict(
                            transactions=[tx], transaction_history=[r for _es, _am, r in q2],
                            creator=[cur_creator] if cur_creator else [], invoices=invs_sorted,
                            payment_allocations=cur_allocs + prior_allocs, approvals=cur_approvals,
                        )
                        ev = _eval_a2(s_a2, meta, dummy_plan)
                elif code == 'A4' and fast_stats_ok and cref_id and tx['amount_vnd'] > 0:
                    cap_v, basis_v = _effective_threshold(tx, cur_approvals)
                    cash_c = _statutory_cash_limit(tx['effective_at'])
                    ym_k = (cref_id, vn_dt.year, vn_dt.month)
                    in_5m = (cash_c == 5_000_000 and int(5_000_000 * DEFAULT_CONFIG['near_low']) <= tx['amount_vnd'] < 5_000_000)
                    in_20m = (int(DEFAULT_SPLIT_CAP_VND * DEFAULT_CONFIG['near_low']) <= tx['amount_vnd'] < DEFAULT_SPLIT_CAP_VND)
                    in_cap = (cap_v not in (5_000_000, DEFAULT_SPLIT_CAP_VND) and cap_v * DEFAULT_CONFIG['near_low'] <= tx['amount_vnd'] < cap_v)
                    hit_5m = in_5m and (a4_count_5m[ym_k] + 1) >= DEFAULT_CONFIG['near_count']
                    hit_20m = in_20m and (a4_count_20m[ym_k] + 1) >= DEFAULT_CONFIG['near_count']
                    if not (hit_5m or hit_20m or in_cap):
                        ev = dict(
                            matched=False, score=0, intrinsic_points=0,
                            evidence_refs=[tx_ref_cur],
                            details=dict(creator_id=cref_id, period=f'{vn_dt.year:04d}-{vn_dt.month:02d}', near_count=0, threshold_vnd=cap_v, threshold_basis=basis_v),
                        )
                    elif hit_5m:
                        peers_5m = a4_near_5m[ym_k]
                        t_r4 = sorted([tx_ref_cur, *[_fref('transactions', r) for r in peers_5m]], key=lambda x: (x['record_id'], x['revision']))
                        ev = dict(
                            matched=True, score=WEIGHTS['A4'], intrinsic_points=WEIGHTS['A4'],
                            evidence_refs=t_r4,
                            details=dict(creator_id=cref_id, period=f'{vn_dt.year:04d}-{vn_dt.month:02d}', near_count=a4_count_5m[ym_k] + 1, threshold_vnd=5_000_000, threshold_basis=basis_v),
                        )
                    elif hit_20m and (not in_cap or DEFAULT_SPLIT_CAP_VND < cap_v):
                        peers_20m = a4_near_20m[ym_k]
                        t_r4 = sorted([tx_ref_cur, *[_fref('transactions', r) for r in peers_20m]], key=lambda x: (x['record_id'], x['revision']))
                        ev = dict(
                            matched=True, score=WEIGHTS['A4'], intrinsic_points=WEIGHTS['A4'],
                            evidence_refs=t_r4,
                            details=dict(creator_id=cref_id, period=f'{vn_dt.year:04d}-{vn_dt.month:02d}', near_count=a4_count_20m[ym_k] + 1, threshold_vnd=DEFAULT_SPLIT_CAP_VND, threshold_basis=basis_v),
                        )
                    else:
                        m_rows = [r for _es, _av, r in by_creator_ym.get(ym_k, ()) if r['record_id'] != tx['record_id']]
                        ev = _eval_a4(dict(transactions=[tx], transaction_history=m_rows, approvals=cur_approvals), meta, dummy_plan)
                elif code == 'A6':
                    if inv_link_gap or not invs_sorted:
                        ev = dict(unavailable=('invoice_link_missing', 'Cần hóa đơn liên kết để kiểm tra A6.'), gaps=[])
                    else:
                        inv_tot_a6 = sum(i['amount_vnd'] for i in invs_sorted)
                        if inv_tot_a6 <= 0:
                            ev = dict(unavailable=('invoice_total_nonpositive', 'Tổng hóa đơn liên kết không dương.'), gaps=[])
                        else:
                            amt_a6 = tx['amount_vnd']
                            is_r_a6 = amt_a6 >= 1_000_000 and amt_a6 % 100_000 == 0
                            hit_a6 = is_r_a6 and amt_a6 > inv_tot_a6 + 1
                            ev = dict(
                                matched=hit_a6, score=WEIGHTS['A6'] if hit_a6 else 0, intrinsic_points=WEIGHTS['A6'] if hit_a6 else 0,
                                evidence_refs=[*inv_refs_cur, tx_ref_cur],
                                details=dict(payment_amount_vnd=amt_a6, linked_invoice_total_vnd=inv_tot_a6, excess_vnd=max(0, amt_a6 - inv_tot_a6), is_rounded_100k=is_r_a6),
                            )
                elif code == 'C1':
                    c_out = bool(tx_ctx['is_off_hours'] or tx_ctx['is_sunday'])
                    a_out = any((ac := vn_posting_context(a['effective_at']))['is_off_hours'] or ac['is_sunday'] for a in cur_approvals) if cur_approvals else False
                    hit_c1 = bool(c_out or a_out)
                    ev = dict(
                        matched=hit_c1, score=WEIGHTS['C1'] if hit_c1 else 0, intrinsic_points=WEIGHTS['C1'] if hit_c1 else 0,
                        evidence_refs=[*app_refs_cur, tx_ref_cur],
                        details=dict(timezone='Asia/Ho_Chi_Minh', transaction_vn_time=tx_ctx['vn_iso'],
                                     created_outside=int(c_out), approved_outside=int(a_out),
                                     is_sunday=tx_ctx['is_sunday'], is_off_hours=tx_ctx['is_off_hours']),
                    )
                elif code == 'C2':
                    approved_c2 = [a for a in cur_approvals if a.get('decision') == 'approved']
                    if not cref_id or not approved_c2:
                        ev = dict(unavailable=('rule_sources_unavailable', 'Chưa đủ nguồn để đánh giá luật; xem bảng/trường hoặc phiên bản tham chiếu cần bổ sung trong gaps.'), gaps=[])
                    elif cref_id.upper() in SYSTEM_ACTORS or cref_id.upper().startswith(('SYS_', 'SYSTEM_', 'AUTO_', 'BOT_')):
                        ev = dict(matched=False, score=0, intrinsic_points=0, evidence_refs=[*[_fref('approvals', a) for a in approved_c2], tx_ref_cur],
                                  details=dict(system_actor_exempt=True, creator_id=cref_id))
                    else:
                        app_ids_c2 = {a['employee_ref']['record_id'] for a in approved_c2}
                        app_r_c2 = [_fref('approvals', a) for a in approved_c2] if len(approved_c2) != len(cur_approvals) else app_refs_cur
                        if cref_id not in app_ids_c2:
                            ev = dict(
                                matched=False, score=0, intrinsic_points=0,
                                evidence_refs=[*app_r_c2, *([c_ref_cur] if c_ref_cur else []), tx_ref_cur],
                                details=dict(self_approved=False, creator_id=cref_id, approver_ids=sorted(app_ids_c2)),
                            )
                        else:
                            self_apps = [a for a in approved_c2 if a['employee_ref']['record_id'] == cref_id]
                            lims = [a.get('limit_vnd') for a in self_apps]
                            if any(lim is None or lim <= 0 or abs(tx['amount_vnd']) > lim for lim in lims):
                                ev = dict(
                                    matched=True, score=WEIGHTS['C2'], intrinsic_points=WEIGHTS['C2'],
                                    evidence_refs=[*[_fref('approvals', a) for a in self_apps], *([c_ref_cur] if c_ref_cur else []), tx_ref_cur],
                                    details=dict(self_approved=True, creator_id=cref_id, amount_vnd=tx['amount_vnd'], observed_limits_vnd=lims, violation='self_approval_without_or_above_limit'),
                                )
                            else:
                                ev = dict(unavailable=('rule_sources_unavailable', 'Chưa đủ nguồn để đánh giá luật; xem bảng/trường hoặc phiên bản tham chiếu cần bổ sung trong gaps.'), gaps=[])
                elif code == 'C3':
                    approved_c3 = [a for a in cur_approvals if a.get('decision') == 'approved']
                    if not approved_c3:
                        ev = dict(unavailable=('approval_missing', 'Chưa có bản ghi phê duyệt để kiểm tra thời gian duyệt C3.'), gaps=[])
                    else:
                        hi_th_c3 = DEFAULT_CONFIG['high_approval_vnd']
                        fast_apps = []; skip_mid = False
                        for a in approved_c3:
                            ac = vn_posting_context(a['effective_at'])
                            if tx_ctx['is_date_only_midnight'] and ac['is_date_only_midnight']:
                                skip_mid = True; continue
                            ds = abs((_stamp(a['effective_at']) - event_dt).total_seconds())
                            if ds < 60 and abs(tx['amount_vnd']) >= hi_th_c3:
                                fast_apps.append((a, ds))
                        hit_c3 = bool(fast_apps)
                        app_r_c3 = [_fref('approvals', a) for a in approved_c3] if len(approved_c3) != len(cur_approvals) else app_refs_cur
                        ev = dict(
                            matched=hit_c3, score=WEIGHTS['C3'] if hit_c3 else 0, intrinsic_points=WEIGHTS['C3'] if hit_c3 else 0,
                            evidence_refs=[*app_r_c3, tx_ref_cur],
                            details=dict(high_approval_threshold_vnd=hi_th_c3, fast_approval_ids=[a['record_id'] for a, _ in fast_apps],
                                         min_approval_seconds=min((d for _, d in fast_apps), default=None), midnight_date_only_skipped=skip_mid),
                        )
                elif code == 'F1':
                    lines_f1 = tx.get('accounting_lines')
                    is_m_adj = tx_kind in ('adjustment', 'reversal')
                    if lines_f1 is None and not is_m_adj:
                        ev = dict(unavailable=('accounting_lines_missing', 'Cần bút toán định khoản hoặc giao dịch điều chỉnh để kiểm tra F1.'), gaps=[])
                    else:
                        imb_v = (sum(l['debit_vnd'] for l in lines_f1) - sum(l['credit_vnd'] for l in lines_f1)) if lines_f1 is not None else 0
                        near_cl = tx_ctx['days_until_month_end'] < DEFAULT_CONFIG['close_days']
                        hit_f1 = bool(imb_v != 0 or (is_m_adj and near_cl and abs(tx['amount_vnd']) >= DEFAULT_SPLIT_CAP_VND))
                        ev = dict(
                            matched=hit_f1, score=WEIGHTS['F1'] if hit_f1 else 0, intrinsic_points=WEIGHTS['F1'] if hit_f1 else 0,
                            evidence_refs=[tx_ref_cur],
                            details=dict(imbalance_vnd=imb_v, is_manual_adjustment=is_m_adj, near_month_end_close=near_cl, days_until_month_end=tx_ctx['days_until_month_end']),
                        )
                elif code == 'F3' and f3_peer_invs is None and len(invs_sorted) == 1 and invs_sorted[0]['kind'] == 'invoice':
                    n_f3 = normalize(invs_sorted[0].get('number') or '', 'text')
                    if n_f3 and n_f3 not in MISSING_CONTACTS:
                        ev = dict(
                            matched=False, score=0, intrinsic_points=0,
                            evidence_refs=[inv_refs_cur[0], tx_ref_cur],
                            details=dict(duplicate_vendor_invoices={}, placeholder_invoice_ids=[]),
                        )
                    else:
                        ev = _eval_f3(_get_compact_sources(), meta, dummy_plan)
                elif code == 'B6' and fast_stats_ok and cur_vendor and tx['amount_vnd'] > 0:
                    vid = cur_vendor['record_id']
                    vcnt = vendor_tx_count[vid]
                    if vcnt == 0:
                        ev = dict(unavailable=('vendor_history_empty', 'Chưa có giao dịch lịch sử của NCC này.'), gaps=[])
                    else:
                        last_es, last_r = vendor_last_tx[vid]
                        gap_d = (event_s - last_es) / 86400.0
                        vamts = vendor_sorted_amts[vid]
                        vmid = vcnt // 2
                        vmed = vamts[vmid] if vcnt % 2 == 1 else 0.5 * (vamts[vmid - 1] + vamts[vmid])
                        d_hit = gap_d >= DEFAULT_CONFIG['dormant_days'] and tx['amount_vnd'] >= DEFAULT_SPLIT_CAP_VND
                        s_hit = vcnt >= 3 and tx['amount_vnd'] >= max(DEFAULT_SPLIT_CAP_VND, int(vmed * 5))
                        hit_b6 = bool(d_hit or s_hit)
                        last_ref = _fref('transactions', last_r)
                        t_refs = sorted([tx_ref_cur, last_ref], key=lambda x: (x['record_id'], x['revision']))
                        ev = dict(
                            matched=hit_b6, score=WEIGHTS['B6'] if hit_b6 else 0, intrinsic_points=WEIGHTS['B6'] if hit_b6 else 0,
                            evidence_refs=[*t_refs, v_ref_cur],
                            details=dict(vendor_id=vid, dormant_gap_days=round(gap_d, 2), prior_vendor_count=vcnt,
                                         vendor_median_vnd=vmed, dormant_hit=d_hit, velocity_spike_hit=s_hit),
                        )
                elif code == 'B3' and fast_stats_ok and cur_vendor and tx['amount_vnd'] > 0:
                    vid = cur_vendor['record_id']
                    vcnt = vendor_tx_count[vid]
                    age_d = (event_dt - _stamp(cur_vendor['effective_at'])).total_seconds() / 86400.0
                    v_docs = [d for d in cur_docs if d.get('source_kind') == 'original' and not d['source']['is_simulated'] and d.get('verification_status') == 'verified']
                    dkinds = {str(d.get('document_kind', '')).lower() for d in v_docs}
                    ful_ok = ('invoice' in dkinds and bool(dkinds & {'contract', 'purchase_order', 'goods_receipt', 'service_acceptance'}))
                    cap_v, _ = _effective_threshold(tx, cur_approvals)
                    hi_th = max(DEFAULT_SPLIT_CAP_VND, cap_v)
                    hit_b3 = (0 <= age_d <= DEFAULT_CONFIG['vendor_new_days'] and vcnt == 0 and tx['amount_vnd'] >= hi_th and not ful_ok)
                    refs_b3 = _sorted_refs([('transactions', tx), ('vendors', cur_vendor), *[('supporting_documents', d) for d in v_docs]]) if v_docs else [tx_ref_cur, v_ref_cur]
                    ev = dict(
                        matched=hit_b3, score=WEIGHTS['B3'] if hit_b3 else 0, intrinsic_points=WEIGHTS['B3'] if hit_b3 else 0,
                        evidence_refs=refs_b3,
                        details=dict(vendor_id=vid, vendor_age_days=round(age_d, 2), prior_vendor_payment_count=vcnt,
                                     threshold_vnd=hi_th, fulfilment_verified=ful_ok),
                    )
                elif code == 'P2' and fast_stats_ok:
                    ch = tx.get('payment_channel')
                    if ch not in ('bank', 'cash'):
                        ev = dict(unavailable=('payment_channel_missing', 'Cần kênh thanh toán (bank/cash) cho P2.'), gaps=[])
                    else:
                        lim_v = _statutory_cash_limit(tx['effective_at'])
                        vid = cur_vendor['record_id'] if cur_vendor else ''
                        sd_tot = tx['amount_vnd'] + (sameday_vid_sum[(vid, vn_day)] if vid else 0)
                        inv_tot = sum(inv['amount_vnd'] for inv in invs_sorted if inv['amount_vnd'] > 0)
                        hit_p2 = bool(ch == 'cash' and tx['amount_vnd'] > 0 and (tx['amount_vnd'] >= lim_v or sd_tot >= lim_v or inv_tot >= lim_v))
                        sd_peers = sameday_vid_rows.get((vid, vn_day), ()) if vid else ()
                        if sd_peers:
                            refs_p2 = _sorted_refs([('transactions', tx), *[('transactions', h) for h in sd_peers], *[('invoices', i) for i in invs_sorted]])
                        else:
                            refs_p2 = [*inv_refs_cur, tx_ref_cur]
                        ev = dict(
                            matched=hit_p2, score=WEIGHTS['P2'] if hit_p2 else 0, intrinsic_points=WEIGHTS['P2'] if hit_p2 else 0,
                            evidence_refs=refs_p2,
                            details=dict(payment_channel=ch, statutory_cash_limit_vnd=lim_v, amount_vnd=tx['amount_vnd'],
                                         same_day_vendor_total_vnd=sd_tot, linked_invoice_total_vnd=inv_tot,
                                         decree_basis='ND_181_2025_5M' if lim_v == CASH_LIMIT_POST_2025_07_VND else 'PRE_2025_07_20M'),
                        )
                else:
                    ev = _CANONICAL_EVALUATORS[code](_get_compact_sources(), meta, dummy_plan)

            if ev.get('not_applicable'):
                rules_out.append(na_templates[code])
            elif 'unavailable' in ev:
                rc, rm = ev['unavailable']
                rules_out.append({
                    'rule_id': code, 'name': RULE_NAMES[code], 'status': 'unavailable', 'available': False,
                    'matched': None, 'intrinsic_points': None, 'score': None,
                    'reason': {'code': rc, 'message': rm},
                    'gaps': [{'table': 'approval_authorities', 'field': '*', 'code': 'source_not_in_input_contract', 'action': 'Bổ sung bảng thẩm quyền phê duyệt.'}] if code == 'C2' else [],
                    'evidence_refs': [], 'source_status': 'unavailable', 'source_checksum': None,
                    'details': ev.get('details', {}),
                })
            else:
                m_flag = bool(ev['matched'])
                rules_out.append({
                    'rule_id': code, 'name': RULE_NAMES[code],
                    'status': 'evaluated_hit' if m_flag else 'evaluated_no_hit',
                    'available': True, 'matched': m_flag,
                    'intrinsic_points': ev['intrinsic_points'] if m_flag else 0,
                    'score': ev['score'] if m_flag else 0,
                    'reason': None, 'gaps': [], 'source_status': 'ready', 'source_checksum': None,
                    'evidence_refs': ev['evidence_refs'], 'details': ev['details'],
                })

        summary = {st: sum(r['status'] == st for r in rules_out) for st in ('evaluated_hit', 'evaluated_no_hit', 'unavailable', 'not_applicable')}
        ev_cnt = summary['evaluated_hit'] + summary['evaluated_no_hit']
        out_by_key[key] = dict(
            version=VERSION,
            coverage_status='partial' if ev_cnt else 'unavailable',
            rules=rules_out,
            summary=summary,
            implementation=implementation,
            configuration=config_obj,
            coverage_basis='known_records_in_this_snapshot_only_not_complete_external_books',
            aggregate=agg_obj,
        )
    return out_by_key
