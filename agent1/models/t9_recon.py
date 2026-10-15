"""T9 — Khớp sao kê ngân hàng với hoá đơn để lấy NGÀY TIỀN VỀ THẬT (chống nhiễu ghi sổ theo lô).

Ba bước (Phần 7, T9):
  1. Sinh ứng viên khách hàng cho mỗi giao dịch có: tên đối tác mờ (RapidFuzz trên tên đã bỏ dấu, bỏ tiền tố
     pháp lý), số hoá đơn trích từ nội dung chuyển khoản, khớp số tiền với công nợ mở.
  2. Chấm điểm ứng viên bằng LightGBM (học trên miền nguồn, áp dụng cho miền đích) — kèm lớp "không khớp"
     (lãi, nộp tiền mặt, chuyển nội bộ...).
  3. Phân bổ lệnh chuyển vào hoá đơn: số HĐ trong nội dung -> subset-sum trên công nợ mở (<= 4 HĐ, dung sai phí
     chuyển tiền) -> trả một phần cho HĐ cũ nhất.
Đầu ra: liên kết (txn, invoice) + ngày trả ước lượng; so với mốc quy tắc (khớp đúng số tiền; chỉ regex).
"""
from __future__ import annotations

import itertools
import re

import numpy as np

from ..threads import NT
import pandas as pd
import lightgbm as lgb
from rapidfuzz import fuzz, process

from ..synth.names import ascii_upper

LEGAL_RE = re.compile(r"\b(CONG TY|CTY|CT|TNHH|CP|CO PHAN|TRACH NHIEM HUU HAN|DNTN|HKD|DOANH NGHIEP TU NHAN|HO KINH DOANH|MTV)\b")
NUM_RE = re.compile(r"(?<!\d)(\d{3,8})(?!\d)")
BANKPFX_RE = re.compile(r"^(MB[A-Z]+\.\d+\.\d+\.|FT\d+[A-Z]+\s)")
TOL = 25_000.0


def norm_name(s: str) -> str:
    s = ascii_upper(s or "")
    s = LEGAL_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def memo_numbers(memo: str) -> list[int]:
    m = BANKPFX_RE.sub("", memo or "")
    return [int(x) for x in NUM_RE.findall(m)]


FEATS = ["name_score", "memo_name_score", "n_no_hit", "amt_exact_single", "amt_subset_hit", "amt_rel_gap",
         "cust_open_n", "days_from_oldest_due", "is_rank1_name", "cust_hist_txn_share"]


class Reconciler:
    def __init__(self, top_k=4):
        self.top_k = top_k
        self.model = None

    # ------------------------------------------------------------------ ứng viên + đặc trưng
    def candidates(self, bank: pd.DataFrame, inv: pd.DataFrame, cust: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for fid, b in bank.groupby("firm_id"):
            c = cust[cust["firm_id"] == fid]
            names = {cid: norm_name(sh) for cid, sh in zip(c["customer_id"], c["short"])}
            keys = list(names.values())
            ids = list(names.keys())
            fi = inv[inv["firm_id"] == fid].sort_values("due_date")
            fi_no = fi.assign(no=fi["invoice_no"].astype(int))
            by_cust = {k: g for k, g in fi_no.groupby("customer_id")}
            no_rows = {number: g[['customer_id', 'issue_date']].values for number, g in fi_no.groupby('no')}
            share = (b["true_customer_id"].value_counts(normalize=True) if False else None)
            for t in b.itertuples(index=False):
                cp = norm_name(t.counterparty)
                memo_n = norm_name(t.memo)
                nums = memo_numbers(t.memo)
                cand = {}
                if cp:
                    for _, sc, j in process.extract(cp, keys, scorer=fuzz.token_set_ratio, limit=self.top_k):
                        cand[ids[j]] = max(cand.get(ids[j], 0), sc)
                for _, sc, j in process.extract(memo_n, keys, scorer=fuzz.partial_ratio, limit=2):
                    cand.setdefault(ids[j], 0)
                for n in nums:
                    for cid, issued in no_rows.get(n, []):
                        if issued <= t.value_date:
                            cand.setdefault(cid, 0)
                ranked = sorted(cand.items(), key=lambda kv: -kv[1])
                for rank, (cid, sc) in enumerate(ranked):
                    g = by_cust.get(cid)
                    op = g[(g["issue_date"] <= t.value_date)] if g is not None else None
                    feats = self._amount_feats(op, t.amount, t.value_date)
                    hit = sum(1 for n in nums if any(c == cid and d <= t.value_date for c, d in no_rows.get(n, [])))
                    rows.append(dict(txn_id=t.txn_id, firm_id=fid, customer_id=cid, name_score=sc,
                                     memo_name_score=fuzz.partial_ratio(names[cid], memo_n), n_no_hit=hit,
                                     is_rank1_name=int(rank == 0), cust_hist_txn_share=np.nan, **feats,
                                     y=int(getattr(t, "true_customer_id", None) == cid)))
        return pd.DataFrame(rows)

    @staticmethod
    def _amount_feats(op, amt, date):
        if op is None or op.empty:
            return dict(amt_exact_single=0, amt_subset_hit=0, amt_rel_gap=1.0, cust_open_n=0, days_from_oldest_due=np.nan)
        # chỉ xét HĐ chưa tất toán theo ngày tiền về ở thời điểm giao dịch (công nợ mở nhìn từ phía DN)
        # Ngày NH thật là nhãn để chấm, không phải dữ liệu vận hành.
        known_clear = op['ledger_clear_date'] if 'ledger_clear_date' in op else pd.Series(pd.NaT, index=op.index)
        o = op[known_clear.isna() | (known_clear >= date)].head(12)
        if o.empty:
            o = op.tail(6)
        a = o["amount_gross"].values - o["credit_note"].values
        exact = int(np.any(np.abs(a - amt) <= TOL))
        best = np.min(np.abs(a - amt)) if len(a) else amt
        sub = 0
        for r in (2, 3):
            if sub or len(a) < r:
                break
            for comb in itertools.combinations(range(min(len(a), 10)), r):
                if abs(a[list(comb)].sum() - amt) <= TOL:
                    sub, best = 1, 0.0
                    break
        return dict(amt_exact_single=exact, amt_subset_hit=sub, amt_rel_gap=float(min(best / max(amt, 1), 1.0)),
                    cust_open_n=len(o), days_from_oldest_due=float((date - o["due_date"].iloc[0]).days))

    # ------------------------------------------------------------------ học + dự đoán
    def fit(self, cand: pd.DataFrame):
        p = dict(objective="binary", learning_rate=0.05, num_leaves=31, min_data_in_leaf=50, verbose=-1, seed=1, num_threads=NT)
        self.model = lgb.train(p, lgb.Dataset(cand[FEATS].astype(float).values, cand["y"].values), 300)
        return self

    def assign_customers(self, cand: pd.DataFrame, thr=0.5) -> pd.DataFrame:
        c = cand.copy()
        c["p"] = self.model.predict(c[FEATS].astype(float).values)
        if getattr(self, 'calibrator', None) is not None:
            c['p'] = self.calibrator.predict(c['p'])
        best = c.sort_values("p", ascending=False).groupby("txn_id").head(1)
        best["matched"] = best["p"] >= thr
        best['confidence'] = best['p']
        return best

    def calibrate(self, candidates):
        from sklearn.isotonic import IsotonicRegression
        p = self.model.predict(candidates[FEATS].astype(float).values)
        self.calibrator = IsotonicRegression(out_of_bounds='clip').fit(p, candidates['y'])
        return self

    def reconcile(self, bank, inv, cust, tau_auto=.9):
        from .reconciliation_pipeline import reconcile
        return reconcile(self, bank, inv, cust, tau_auto=tau_auto)

    # ------------------------------------------------------------------ phân bổ vào hoá đơn
    @staticmethod
    def allocate(best: pd.DataFrame, bank: pd.DataFrame, inv: pd.DataFrame) -> pd.DataFrame:
        """Phân bổ theo thời gian, giữ số dư còn lại từng HĐ: số HĐ trong nội dung -> khớp đúng số dư một HĐ
        -> subset-sum 2..4 HĐ -> trả một phần cho HĐ cũ nhất. Ngày trả ước lượng = ngày giao dịch tất toán HĐ."""
        b = bank.set_index("txn_id")
        inv = inv.sort_values("due_date")
        remain = dict(zip(inv["invoice_id"], (inv["amount_gross"] - inv["credit_note"]).astype(float)))
        by_cust = {k: g[["invoice_id", "invoice_no", "issue_date"]].values for k, g in inv.groupby("customer_id")}
        links = []
        m = best[best["matched"]].copy()
        m["vd"] = m["txn_id"].map(b["value_date"])
        for r in m.sort_values(["vd", "txn_id"]).itertuples():
            t = b.loc[r.txn_id]
            g = by_cust.get(r.customer_id)
            if g is None:
                continue
            op = [(iid, int(no)) for iid, no, d in g if d <= t.value_date and remain[iid] > TOL]
            if not op:
                continue
            amt = float(t.amount)
            nums = set(memo_numbers(t.memo))
            chosen = [iid for iid, no in op if no in nums]
            if not chosen:
                one = [iid for iid, _ in op if abs(remain[iid] - amt) <= TOL]
                chosen = one[:1]
            if not chosen:
                cand = [iid for iid, _ in op[:12]]
                a = np.array([remain[c] for c in cand])
                for rr in (2, 3, 4):
                    if chosen or len(a) < rr:
                        break
                    for comb in itertools.combinations(range(len(a)), rr):
                        if abs(a[list(comb)].sum() - amt) <= TOL:
                            chosen = [cand[c] for c in comb]
                            break
            if not chosen:
                chosen = [op[0][0]]
            left = amt + TOL
            for iid in chosen:
                pay = min(remain[iid], left)
                if pay <= 0:
                    break
                remain[iid] -= pay
                left -= pay
                links.append((r.txn_id, iid, t.value_date, "full" if remain[iid] <= TOL else "partial"))
        return pd.DataFrame(links, columns=["txn_id", "invoice_id", "est_pay_date", "kind"])


def rule_exact_amount(bank: pd.DataFrame, inv: pd.DataFrame) -> pd.DataFrame:
    """Mốc R1: khớp giao dịch với hoá đơn mở DUY NHẤT trong công ty có đúng số tiền."""
    out = []
    for fid, b in bank.groupby("firm_id"):
        fi = inv[inv["firm_id"] == fid].copy()
        fi["a"] = (fi["amount_gross"] - fi["credit_note"]).round(-3)
        idx = fi.groupby("a")["invoice_id"].apply(list).to_dict()
        for t in b.itertuples():
            c = idx.get(round(t.amount, -3), [])
            if len(c) == 1:
                out.append((t.txn_id, c[0], t.value_date, "full"))
    return pd.DataFrame(out, columns=["txn_id", "invoice_id", "est_pay_date", "kind"])


def rule_memo_regex(bank: pd.DataFrame, inv: pd.DataFrame) -> pd.DataFrame:
    """Mốc R2: chỉ dùng số hoá đơn trong nội dung chuyển khoản."""
    out = []
    for fid, b in bank.groupby("firm_id"):
        fi = inv[inv["firm_id"] == fid]
        no = {}
        for iid, n, d in zip(fi["invoice_id"], fi["invoice_no"].astype(int), fi["issue_date"]):
            no.setdefault(n, []).append((d, iid))
        for t in b.itertuples():
            for n in memo_numbers(t.memo):
                c = [iid for d, iid in no.get(n, []) if d <= t.value_date]
                if c:
                    out.append((t.txn_id, c[-1], t.value_date, "full"))
    return pd.DataFrame(out, columns=["txn_id", "invoice_id", "est_pay_date", "kind"])


def score_links(pred: pd.DataFrame, truth: pd.DataFrame) -> dict:
    """truth: payments (txn_id, invoice_id) thật. Precision/recall trên cặp liên kết."""
    t = set(zip(truth["txn_id"], truth["invoice_id"]))
    p = set(zip(pred["txn_id"], pred["invoice_id"]))
    tp = len(t & p)
    prec = tp / max(len(p), 1)
    rec = tp / max(len(t), 1)
    return dict(link_precision=prec, link_recall=rec, link_f1=2 * prec * rec / max(prec + rec, 1e-9),
                n_pred=len(p), n_true=len(t))
