"""Đối soát tuần tự: quy tắc rõ trước, ML sau; giao dịch mơ hồ phải vào hàng chờ."""
from __future__ import annotations
from functools import lru_cache
import itertools
import numpy as np
import pandas as pd
from .t9_recon import TOL, memo_numbers

LINK_COLUMNS = ['txn_id', 'invoice_id', 'est_pay_date', 'kind', 'amount', 'method', 'confidence']


@lru_cache(maxsize=16)
def _subsets(n, max_size=6):
    combinations = [c for size in range(1, min(max_size, n) + 1) for c in itertools.combinations(range(n), size)]
    matrix = np.zeros((len(combinations), n), dtype=float)
    for row, combo in enumerate(combinations):
        matrix[row, list(combo)] = 1
    return matrix


def choose_subset(open_invoices, amount, probabilities=None):
    """Chọn tối đa 6/15 HĐ bằng liệt kê vector hoá; báo rõ số nghiệm khả thi."""
    op = open_invoices.head(15)
    if op.empty:
        return [], 0
    matrix = _subsets(len(op))
    totals = matrix @ op['remaining_amount'].to_numpy()
    feasible = np.flatnonzero(np.abs(totals - amount) <= TOL)
    if not len(feasible):
        return [], 0
    prob = np.full(len(op), .5) if probabilities is None else np.clip(np.asarray(probabilities)[:len(op)], 1e-6, 1 - 1e-6)
    # Xác suất được cung cấp từ T1 nếu có; ưu tiên FIFO nhẹ khi chi phí bằng nhau.
    costs = -np.log(prob) + np.arange(len(op)) * .01
    objective = matrix[feasible] @ costs
    pick = feasible[np.argmin(objective)]
    return op.index[matrix[pick].astype(bool)].tolist(), len(feasible)


def reconcile(rec, bank, invoices, customers, tau_auto=.9, assignments=None, rules_first=True,
              rule_mode='both', ledger_policy='asof'):
    """Chỉ cập nhật công nợ từ liên kết tự động; không lấy nhãn thật để ra quyết định."""
    if not 0 <= tau_auto <= 1:
        raise ValueError('tau_auto trong [0,1]')
    if rule_mode not in {'both', 'amount', 'memo'} or ledger_policy not in {'asof', 'opening_only'}:
        raise ValueError('Chính sách quy tắc/sổ cái không hợp lệ')
    inv = invoices.copy().sort_values(['due_date', 'invoice_id']).set_index('invoice_id', drop=False)
    inv['remaining_amount'] = inv['amount_gross'].astype(float)
    inv['_credit_applied'] = 0.
    if len(bank) and 'ledger_clear_date' in inv:
        inv.loc[inv.ledger_clear_date < bank.value_date.min(), 'remaining_amount'] = 0.
    if assignments is None and rec.model is not None and len(bank):
        cand = rec.candidates(bank, invoices, customers)
        assignments = rec.assign_customers(cand, thr=tau_auto) if len(cand) else pd.DataFrame()
    assigned = assignments.set_index('txn_id') if assignments is not None and len(assignments) else pd.DataFrame()
    links, reviews = [], []
    for t in bank.sort_values(['value_date', 'txn_id']).itertuples(index=False):
        if getattr(t, 'direction', 'in') != 'in' or t.amount <= 0:
            reviews.append(dict(txn_id=t.txn_id, reason='not_positive_inflow', amount=t.amount))
            continue
        # Nhìn sổ cái/điều chỉnh tới đúng ngày giao dịch, không chỉ đầu kỳ sao kê.
        if ledger_policy == 'asof' and 'ledger_clear_date' in inv:
            cleared = (inv.firm_id == t.firm_id) & (inv.ledger_clear_date < t.value_date)
            inv.loc[cleared, 'remaining_amount'] = 0.
        if 'credit_note_date' in inv and 'credit_note' in inv:
            known = (inv.firm_id == t.firm_id) & (inv.credit_note_date <= t.value_date)
            delta = (inv.loc[known, 'credit_note'] - inv.loc[known, '_credit_applied']).clip(lower=0.)
            inv.loc[known, 'remaining_amount'] = (inv.loc[known, 'remaining_amount'] - delta).clip(lower=0.)
            inv.loc[known, '_credit_applied'] = inv.loc[known, 'credit_note']
        op = inv[(inv.firm_id == t.firm_id) & (inv.issue_date <= t.value_date) & (inv.remaining_amount > TOL)]
        nums = set(memo_numbers(t.memo))
        matches = op[op.invoice_no.astype(int).isin(nums)]
        chosen, method, confidence = [], '', 0.
        if rules_first and rule_mode != 'amount' and len(matches) and matches.invoice_no.astype(int).nunique() == len(matches) and matches.customer_id.nunique() == 1:
            if abs(matches.remaining_amount.sum() - t.amount) <= TOL:
                chosen, method, confidence = matches.index.tolist(), 'R2_memo', 1.
        if rules_first and rule_mode != 'memo' and not chosen:
            exact = op[np.abs(op.remaining_amount - t.amount) <= TOL]
            if len(exact) == 1:
                chosen, method, confidence = exact.index.tolist(), 'R1_unique_amount', 1.
        reason = 'no_unambiguous_rule'
        if not chosen and len(assigned) and t.txn_id in assigned.index:
            a = assigned.loc[t.txn_id]
            confidence = float(a.get('confidence', a.get('p', 0)))
            if confidence >= tau_auto:
                pool = op[op.customer_id == a.customer_id]
                chosen, solutions = choose_subset(pool, t.amount)
                method = 'ML_subset'
                if solutions > 1:
                    chosen, reason = [], 'ambiguous_allocation'
                elif not chosen:
                    reason = 'no_amount_allocation'
            else:
                reason = 'low_customer_confidence'
        if not chosen:
            reviews.append(dict(txn_id=t.txn_id, reason=reason, amount=t.amount, confidence=confidence))
            continue
        remaining_cash = float(t.amount)
        for iid in chosen:
            paid = min(float(inv.loc[iid, 'remaining_amount']), remaining_cash)
            remaining_cash -= paid
            inv.loc[iid, 'remaining_amount'] -= paid
            links.append(dict(txn_id=t.txn_id, invoice_id=iid, est_pay_date=t.value_date,
                              kind='full' if inv.loc[iid, 'remaining_amount'] <= TOL else 'partial',
                              amount=paid, method=method, confidence=confidence))
    return pd.DataFrame(links, columns=LINK_COLUMNS), pd.DataFrame(reviews, columns=['txn_id', 'reason', 'amount', 'confidence'])


def build_bank_labels(invoices, links):
    """Ngày tất toán ước lượng chỉ khi tổng phân bổ đạt công nợ; không dùng paid_date_true."""
    out = invoices.copy()
    out['paid_date_est'] = pd.NaT
    if links.empty:
        return out
    if 'amount' not in links:
        raise ValueError('Nhãn ngân hàng cần liên kết có số tiền phân bổ')
    ordered = links.sort_values(['est_pay_date', 'txn_id']).copy()
    gross = out.set_index('invoice_id')['amount_gross']
    ordered['cumulative_amount'] = ordered.groupby('invoice_id').amount.cumsum()
    target = ordered.invoice_id.map(gross)
    if 'credit_note_date' in out and 'credit_note' in out:
        metadata = out.set_index('invoice_id')
        known = ordered.invoice_id.map(metadata.credit_note_date) <= ordered.est_pay_date
        target = target - ordered.invoice_id.map(metadata.credit_note).where(known, 0.)
    settled = ordered[ordered.cumulative_amount + TOL >= target]
    if settled.empty:
        return out
    dates = settled.groupby('invoice_id').est_pay_date.min()
    out['paid_date_est'] = out.invoice_id.map(dates)
    return out
