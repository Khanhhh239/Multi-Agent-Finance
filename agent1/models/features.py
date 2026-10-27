"""Snapshot "as-of" (landmarking) cho hoá đơn còn mở + đặc trưng chống rò rỉ — dùng chung T1/T2/T3/T8/T10.

Tại mỗi điểm cắt T, chỉ dùng thông tin biết được tại T:
  - hoá đơn đã lập <= T và chưa tất toán theo ngày nhãn (ngày tiền về NH, hoặc ngày ghi sổ nếu label_col=ledger);
  - lịch sử khách = các hoá đơn đã tất toán <= T (ngày nhãn <= T); có thể giới hạn "cửa sổ nhìn thấy"
    (visible_from) để mô phỏng doanh nghiệp mới onboard chỉ có M tháng lịch sử (domain adaptation);
  - thanh toán một phần đã nhận <= T; lời hứa đã ghi nhận <= T, độ tin cậy lời hứa từ các lời hứa đã đến hạn <= T.
Đặc trưng thiết kế bất biến miền: số ngày tương đối hạn, số tiền tương đối trung vị của chính công ty (không phụ
thuộc đơn vị VND/USD/EUR), thống kê khách co về trung bình công ty (empirical Bayes).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import calendar_vn as cal

BASELINE_QUANTILES = ['hist_q10', 'hist_q50', 'hist_q90']


class StationaryFeatures:
    """Tuỳ chọn P4; kẹp học chỉ từ train, tháng lịch bị ẩn khi lịch sử DN <24 tháng."""
    def fit(self,train):
        values=pd.to_numeric(train['f_n_hist'],errors='coerce').dropna()
        if values.empty or (values<0).any():raise ValueError('Cần f_n_hist train không âm')
        self.count_cap=float(values.quantile(.99))
        return self

    def transform(self,frame,history_days=None):
        if not hasattr(self,'count_cap'):raise ValueError('Phải fit phân vị 99 trên train trước')
        result=frame.copy()
        result['f_n_hist']=np.log1p(result.f_n_hist.clip(lower=0,upper=self.count_cap))
        result['c_tenure_days']=np.log1p(result.c_tenure_days.clip(lower=0))
        if history_days is None:
            if 'firm_history_days' not in result:raise ValueError('Thiếu tuổi lịch sử DN as-of')
            history_days=result.firm_history_days
        # 24 tháng tính theo lịch tại từng cutoff, không suy từ công ty trong test.
        elapsed=pd.to_numeric(pd.Series(np.asarray(history_days),index=result.index),errors='coerce')
        threshold=(result.cutoff-result.cutoff.map(lambda day:day-pd.DateOffset(months=24))).dt.days
        short=elapsed.isna() | (elapsed<threshold)
        result.loc[short,['issue_month','cut_month']]=np.nan
        return result

APPROVED_T1_FEATURES = (
    # hoá đơn
    "log_amount_rel", "term_days", "age_days", "days_to_due", "days_past_due", "is_overdue", "issue_month",
    "due_dom", "due_dow", "paid_frac_so_far", "has_due",
    # khách: lịch sử
    "c_n_hist", "c_delay_mean", "c_delay_med", "c_delay_std", "c_delay_eb", "c_delay_ewm", "c_late_share",
    "c_late30_share", "c_last_delay", "c_trend", "c_days_since_last_pay", "c_tenure_days", "c_life_med",
    "c_payrun_strength", "c_days_due_to_payrun", "c_dow_strength", "c_amount_rel_med",
    # khách: công nợ hiện tại
    "c_open_n", "c_open_share", "c_open_overdue_n", "c_max_dpd", "c_pay_30d",
    # lời hứa (T8)
    "has_promise", "days_to_promised", "promise_overdue", "c_promise_rel", "c_promise_n",
    # công ty / sốc chung
    "f_n_hist", "f_delay_mean", "f_resid_28d", "f_resid_trend", "f_open_n",
    # lịch
    "days_to_tet", "cut_month", "due_near_tet",
)
FEATURES = list(APPROVED_T1_FEATURES)

# These are the only T1 columns that may enter an estimator. Research ablations
# must be registered here before they can be used; arbitrary extra columns in a
# synthetic world are never automatically promoted to model features.
OPTIONAL_FEATURES = ("f_resid_7d", "no_due", "c_disp_eb")
ALLOWED_MODEL_FEATURES = frozenset((*APPROVED_T1_FEATURES, *OPTIONAL_FEATURES))
MODEL_CONTEXT = ("invoice_id", "firm_id", "customer_id", "cutoff", "issue_date",
                 "due_date", "amount_gross", "amount_open", "top1", "top2")
MODEL_VISIBLE_COLUMNS = (*MODEL_CONTEXT, *FEATURES, *BASELINE_QUANTILES)


def validate_feature_columns(columns):
    """Fail closed: a new raw/latent/outcome column needs an explicit policy review."""
    names = list(columns)
    unknown = set(names) - ALLOWED_MODEL_FEATURES
    if unknown:
        raise ValueError(f'Đặc trưng cấm hoặc chưa được duyệt: {sorted(unknown)}')
    if len(names) != len(set(names)):
        raise ValueError('Danh sách đặc trưng có cột trùng')


def model_snapshot_view(snapshot: pd.DataFrame, cutoff) -> pd.DataFrame:
    """Only information available at cutoff; drops every unregistered raw column."""
    validate_feature_columns(FEATURES)
    T = pd.Timestamp(cutoff)
    if pd.isna(T):
        raise ValueError('Ngày dự báo cutoff không hợp lệ')
    if snapshot.empty:
        return pd.DataFrame(columns=MODEL_VISIBLE_COLUMNS)
    if 'cutoff' not in snapshot:
        raise ValueError('Thiếu ngày dự báo cutoff')
    dates = pd.to_datetime(snapshot['cutoff'], errors='coerce')
    if dates.isna().any() or not dates.eq(T).all():
        raise ValueError('Snapshot chứa ngày dự báo khác cutoff')
    required = set(MODEL_CONTEXT[:8]) | set(FEATURES)
    missing = required - set(snapshot)
    if missing:
        raise ValueError(f'Snapshot thiếu cột được phép: {sorted(missing)}')
    issued = pd.to_datetime(snapshot['issue_date'], errors='coerce')
    if issued.isna().any() or (issued > T).any():
        raise ValueError('Snapshot chứa hóa đơn chưa phát hành tại cutoff')
    return snapshot.loc[:, [name for name in MODEL_VISIBLE_COLUMNS if name in snapshot]].copy()


def published_macro_as_of(macro: pd.DataFrame, cutoff) -> pd.DataFrame:
    """Latest published public indicator; generator-only macro state stays hidden."""
    required = {'week', 'published_date', 'covid_source', 'covid_stress'}
    if required - set(macro):
        raise ValueError(f'Macro thiếu cột công bố: {sorted(required - set(macro))}')
    T = pd.Timestamp(cutoff)
    weeks = pd.to_datetime(macro['week'], errors='coerce')
    published = pd.to_datetime(macro['published_date'], errors='coerce')
    if pd.isna(T) or weeks.isna().any() or published.isna().any() or (published < weeks + pd.Timedelta(days=7)).any():
        raise ValueError('Ngày công bố macro không hợp lệ')
    visible = macro.loc[(published <= T) & (weeks <= T) & macro['covid_source'].eq('oxcgrt'),
                        ['week', 'published_date', 'covid_stress']]
    return visible.sort_values(['published_date', 'week']).tail(1).copy()


def _dom_next(dom_from: np.ndarray, targets: np.ndarray) -> np.ndarray:
    """Khoảng cách (ngày) từ ngày-trong-tháng dom_from tới target dom gần nhất phía sau (vòng 30 ngày)."""
    d = (targets - dom_from) % 30
    return d


class SnapshotBuilder:
    def __init__(self, invoices: pd.DataFrame, payments: pd.DataFrame | None = None,
                 promises: pd.DataFrame | None = None, label_col: str = "paid_date_true", ewm_halflife: float = 90.0,
                 eb_k: float = 4.0,stationary_features: bool = False,stationary_state=None):
        self.stationary_features=stationary_features
        self.stationary_state=stationary_state
        if stationary_features and stationary_state is None:raise ValueError('stationary_features cần trạng thái đã fit từ train')
        inv = invoices.copy()
        due = inv['due_date'] if 'due_date' in inv else pd.Series(pd.NaT, index=inv.index, dtype='datetime64[ns]')
        inv["has_due"] = due.notna().astype(int)
        inv["due_date"] = due.fillna(inv["issue_date"])
        inv["label_date"] = inv[label_col]
        if "writeoff_date" not in inv:
            inv["writeoff_date"] = pd.NaT
        inv["delay"] = (inv["label_date"] - inv["due_date"]).dt.days
        inv["life"] = (inv["label_date"] - inv["issue_date"]).dt.days
        self.inv = inv.reset_index(drop=True)
        self.pay = None
        if payments is not None and len(payments):
            pdate = ('pay_date_true' if label_col == 'paid_date_true' else
                     'ledger_post_date' if label_col == 'ledger_clear_date' else 'est_pay_date')
            if pdate not in payments:
                raise ValueError(f'Thiếu cột ngày quan sát {pdate} cho {label_col}')
            invoice_key = 'ledger_invoice_id' if label_col == 'ledger_clear_date' and 'ledger_invoice_id' in payments else 'invoice_id'
            columns = [invoice_key, pdate, 'amount']
            if 'fx_adjustment' in payments:
                columns.append('fx_adjustment')
            p = payments[columns].rename(columns={invoice_key: 'invoice_id', pdate: 'pdate'})
            p['face_amount'] = p['amount'] - p['fx_adjustment'] if 'fx_adjustment' in p else p['amount']
            self.pay = p.merge(inv[["invoice_id", "amount_gross"]], on="invoice_id")
        self.prom = promises.copy() if promises is not None and len(promises) else None
        self.hl = ewm_halflife
        self.eb_k = eb_k

    # --------------------------------------------------------------------------------------------
    def model_snapshot(self, T, visible_from=None, firms=None) -> pd.DataFrame:
        """Forecast-facing view; outcomes remain available only to label builders."""
        return model_snapshot_view(self.snapshot(T, visible_from=visible_from, firms=firms), T)

    # --------------------------------------------------------------------------------------------
    def snapshot(self, T, visible_from=None, firms=None) -> pd.DataFrame:
        T = pd.Timestamp(T)
        inv = self.inv if firms is None else self.inv[self.inv["firm_id"].isin(firms)]
        vis = inv if visible_from is None else inv[inv["issue_date"] >= pd.Timestamp(visible_from)]
        vis = vis[vis["issue_date"] <= T].copy()
        # Mẫu chuẩn hoá chỉ gồm hoá đơn đã thấy tại T, kể cả khi giới hạn onboarding.
        firm_med = vis.groupby("firm_id")["amount_gross"].transform("median")
        vis["amount_rel"] = vis["amount_gross"] / firm_med.clip(lower=1e-9)
        issued = vis["issue_date"] <= T
        settled = vis["label_date"].notna() & (vis["label_date"] <= T)
        written = vis["writeoff_date"].notna() & (vis["writeoff_date"] <= T)
        if {'credit_note', 'credit_note_date'} <= set(vis.columns):
            credit_known = pd.to_datetime(vis['credit_note_date']) <= T
            credited_out = credit_known & vis['credit_note'].ge(vis['amount_gross'] - 1.)
        else:
            credited_out = pd.Series(False, index=vis.index)
        op = vis[issued & ~settled & ~written & ~credited_out].copy()
        if op.empty:
            return op
        hist = vis[settled].copy()
        # Phân vị mốc tính đúng tại từng cutoff; không lấy lịch sử ở ngày bắt đầu test
        # để chấm ngược cửa sổ hiệu chỉnh.
        for a, col in zip((.1, .5, .9), BASELINE_QUANTILES):
            cq = hist.groupby('customer_id')['delay'].quantile(a)
            fq = hist.groupby('firm_id')['delay'].quantile(a)
            op[col] = op['customer_id'].map(cq).fillna(op['firm_id'].map(fq)).fillna(0.)
        op["cutoff"] = T
        # ---------------- hoá đơn
        op["log_amount_rel"] = np.log(op["amount_rel"].clip(1e-6))
        op["age_days"] = (T - op["issue_date"]).dt.days
        op["days_to_due"] = (op["due_date"] - T).dt.days
        op["days_past_due"] = (-op["days_to_due"]).clip(lower=0)
        op["is_overdue"] = (op["days_to_due"] < 0).astype(int)
        op["issue_month"] = op["issue_date"].dt.month
        op["due_dom"] = op["due_date"].dt.day
        op["due_dow"] = op["due_date"].dt.dayofweek
        if self.pay is not None:
            pp = self.pay[(self.pay["pdate"] <= T) & self.pay["invoice_id"].isin(op["invoice_id"])]
            paid = op['invoice_id'].map(pp.groupby('invoice_id')['face_amount'].sum()).fillna(0.)
            op["paid_frac_so_far"] = (paid / op['amount_gross']).clip(0, 1)
        else:
            paid = pd.Series(0., index=op.index)
            op["paid_frac_so_far"] = np.nan
        if {'credit_note', 'credit_note_date'} <= set(op.columns):
            credit = op['credit_note'].where(pd.to_datetime(op['credit_note_date']) <= T, 0.).fillna(0.)
        else:
            credit = pd.Series(0., index=op.index)
        op['amount_open'] = (op['amount_gross'] - paid - credit).clip(lower=0.)
        # ---------------- công ty
        f = hist.assign(delay_clipped=hist['delay'].clip(-60, 180)).groupby("firm_id").agg(
            f_n_hist=("delay", "size"), f_delay_mean=("delay_clipped", 'mean'))
        op = op.merge(f, left_on="firm_id", right_index=True, how="left")
        # ---------------- khách
        if len(hist):
            h = hist
            h = h.assign(dl=h["delay"].clip(-60, 240), age_pay=(T - h["label_date"]).dt.days)
            h["w"] = np.power(0.5, h["age_pay"] / self.hl)
            h["dw"] = h["dl"] * h["w"]
            h['late_flag'], h['late30_flag'] = h['dl'] > 0, h['dl'] > 30
            g = h.groupby("customer_id")
            c = pd.DataFrame({
                "c_n_hist": g.size(), "c_delay_mean": g["dl"].mean(), "c_delay_med": g["dl"].median(),
                "c_delay_std": g["dl"].std(), "c_late_share": g['late_flag'].mean(),
                "c_late30_share": g['late30_flag'].mean(),
                "c_delay_ewm": g["dw"].sum() / g["w"].sum(), "c_life_med": g["life"].median(),
                "c_last_pay": g["label_date"].max(), "c_first_issue": g["issue_date"].min(),
                "c_amount_med": g["amount_rel"].median(),
            })
            hs = h.sort_values("label_date")
            last = hs.groupby("customer_id").tail(3).groupby("customer_id")["dl"]
            c["c_last_delay"] = hs.groupby("customer_id")["dl"].last()
            c["c_trend"] = last.mean() - c["c_delay_mean"]
            # nhịp ngày trả: tỷ trọng ngày-trong-tháng phổ biến nhất (top-2) và thứ phổ biến nhất
            h["dom"] = h["label_date"].dt.day.clip(upper=30)
            h["dow"] = h["label_date"].dt.dayofweek
            vc = h.groupby(["customer_id", "dom"]).size().rename("k").reset_index().sort_values(["customer_id", "k"],
                                                                                              ascending=[True, False])
            top = vc.groupby("customer_id").head(2)
            c["c_payrun_strength"] = top.groupby("customer_id")["k"].sum() / c["c_n_hist"]
            top1 = vc.groupby("customer_id").head(1).set_index("customer_id")["dom"]
            top2 = vc.groupby("customer_id").nth(1).set_index("customer_id")["dom"] if len(vc) else top1
            c["top1"], c["top2"] = top1, top2
            vd = h.groupby(["customer_id", "dow"]).size().groupby("customer_id").max()
            c["c_dow_strength"] = vd / c["c_n_hist"]
            fm = op.groupby("firm_id")["f_delay_mean"].first()
            op = op.merge(c, left_on="customer_id", right_index=True, how="left")
            prior = op["f_delay_mean"].fillna(0.0)
            n = op["c_n_hist"].fillna(0)
            op["c_delay_eb"] = (n * op["c_delay_mean"].fillna(0) + self.eb_k * prior) / (n + self.eb_k)
            op["c_days_since_last_pay"] = (T - op["c_last_pay"]).dt.days
            op["c_tenure_days"] = (T - op["c_first_issue"]).dt.days
            op["c_amount_rel_med"] = op["amount_rel"] / op["c_amount_med"]
            dd = op["due_date"].dt.day.clip(upper=30).values
            t1 = op["top1"].values
            t2 = op["top2"].values
            d1 = np.where(np.isnan(t1.astype(float)), np.nan, _dom_next(dd, np.nan_to_num(t1.astype(float))))
            d2 = np.where(np.isnan(t2.astype(float)), np.nan, _dom_next(dd, np.nan_to_num(t2.astype(float))))
            op["c_days_due_to_payrun"] = np.fmin(d1, d2)
            # residual sốc chung (công ty): trễ gần đây so với kỳ vọng theo khách
            hh = h.merge(c[["c_delay_mean"]], left_on="customer_id", right_index=True)
            hh["res"] = hh["dl"] - hh["c_delay_mean"]
            r28 = hh[hh["age_pay"] <= 28].groupby("firm_id")["res"].mean()
            r90 = hh[(hh["age_pay"] > 28) & (hh["age_pay"] <= 120)].groupby("firm_id")["res"].mean()
            op["f_resid_28d"] = op["firm_id"].map(r28)
            op["f_resid_trend"] = op["f_resid_28d"] - op["firm_id"].map(r90)
            pay30 = h[h["age_pay"] <= 30].groupby("customer_id").size()
            op["c_pay_30d"] = op["customer_id"].map(pay30).fillna(0)
        else:
            for col in ["c_n_hist", "c_delay_mean", "c_delay_med", "c_delay_std", "c_delay_eb", "c_delay_ewm",
                        "c_late_share", "c_late30_share", "c_last_delay", "c_trend", "c_days_since_last_pay",
                        "c_tenure_days", "c_life_med", "c_payrun_strength", "c_days_due_to_payrun", "c_dow_strength",
                        "c_amount_rel_med", "f_resid_28d", "f_resid_trend", "c_pay_30d"]:
                op[col] = np.nan
        # ---------------- công nợ mở của khách
        g = op.groupby("customer_id")
        op["c_open_n"] = g["invoice_id"].transform("size")
        op["c_open_share"] = g["amount_gross"].transform("sum") / op.groupby("firm_id")["amount_gross"].transform("sum")
        op["c_open_overdue_n"] = g["is_overdue"].transform("sum")
        op["c_max_dpd"] = g["days_past_due"].transform("max")
        op["f_open_n"] = op.groupby("firm_id")["invoice_id"].transform("size")
        # ---------------- lời hứa
        if self.prom is not None and (self.prom['made_date'] <= T).any():
            pr = self.prom[self.prom["made_date"] <= T]
            last_p = pr.sort_values("made_date").groupby("invoice_id").tail(1).set_index("invoice_id")
            op["has_promise"] = op["invoice_id"].isin(last_p.index).astype(int)
            op["days_to_promised"] = (op["invoice_id"].map(last_p["promised_date"]) - T).dt.days
            op["promise_overdue"] = (op["days_to_promised"] < -3).astype(float).where(op["has_promise"] == 1)
            resolved = pr[(pr["promised_date"] + pd.Timedelta(days=3) <= T) & pr['kept'].notna()]
            kc = resolved.groupby("customer_id")["kept"].agg(["sum", "size"])
            a, b = 4.0, 2.0  # tiền nghiệm Beta (co về mức trung bình khi ít quan sát) — T8
            rel = (kc["sum"] + a) / (kc["size"] + a + b)
            op["c_promise_rel"] = op["customer_id"].map(rel).fillna(a / (a + b))
            op["c_promise_n"] = op["customer_id"].map(kc["size"]).fillna(0)
        else:
            for col in ["has_promise", "days_to_promised", "promise_overdue", "c_promise_rel", "c_promise_n"]:
                op[col] = np.nan
        # ---------------- lịch
        op["days_to_tet"] = cal.days_to_tet(T)
        op["cut_month"] = T.month
        dt = cal.days_to_tet_np(op["due_date"].values.astype("datetime64[D]"))
        op["due_near_tet"] = ((dt >= -10) & (dt <= 20)).astype(int)
        for col in FEATURES:
            if col not in op:
                op[col] = np.nan
        if self.stationary_features:
            first=self.inv.groupby('firm_id').issue_date.min()
            beginning=op.firm_id.map(first)
            if visible_from is not None:beginning=beginning.clip(lower=pd.Timestamp(visible_from))
            op=self.stationary_state.transform(op,history_days=(T-beginning).dt.days)
        return op

    # --------------------------------------------------------------------------------------------
    def build(self, cutoffs, label_end=None, visible_from=None, firms=None, verbose=False) -> pd.DataFrame:
        """Ghép nhiều snapshot + nhãn. label_end: nhãn bị kiểm duyệt tại ngày này (chống nhìn tương lai)."""
        out = []
        for T in cutoffs:
            s = self.snapshot(T, visible_from=visible_from, firms=firms)
            if s is None or s.empty:
                continue
            out.append(s)
            if verbose:
                print("  snapshot", pd.Timestamp(T).date(), len(s), flush=True)
        if not out:
            return pd.DataFrame()
        df = pd.concat(out, ignore_index=True)
        return add_labels(df, label_end)


def add_labels(df: pd.DataFrame, label_end=None) -> pd.DataFrame:
    """remaining = ngày tới khi tất toán (vô hạn nếu nợ xấu); event/obs tới label_end."""
    T = df["cutoff"]
    rem = (df["label_date"] - T).dt.days.astype(float)
    rem = rem.where(df["label_date"].notna(), np.inf)
    df["remaining"] = rem
    end = pd.Timestamp(label_end) if label_end is not None else pd.Timestamp.max.normalize()
    if (T > end).any():
        raise ValueError('label_end phải không trước cutoff')
    obs = (end - T).dt.days.astype(float)
    df["obs_window"] = obs
    df["event"] = (rem <= obs).astype(int)
    df["time_obs"] = np.minimum(rem, obs)
    # nợ xấu đã biết tại label_end (đã xoá sổ) -> 'cured' (không bao giờ trả)
    wo = df["writeoff_date"].notna() & (df["writeoff_date"] <= end)
    df["bad_known"] = (wo & df["label_date"].isna()).astype(int)
    return df
