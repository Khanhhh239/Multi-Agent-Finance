"""Tầng 1 — nạp dữ liệu THẬT tương tự về lược đồ chuẩn, có cache parquet ở data/interim/.

Mỗi hàm ghi rõ vai trò (nhiệm vụ T nào) và giới hạn (không phải SME Việt Nam).
"""
from __future__ import annotations

import zipfile
from xml.etree.ElementTree import iterparse

import numpy as np
import pandas as pd

from ..paths import INTERIM, RAW


def _cache(name):
    return INTERIM / f"{name}.parquet"


# ------------------------------------------------------------------ T1: AR giống ERP (độ tin cậy C)
def customer_invoices(force=False) -> pd.DataFrame:
    """Customer Invoices (HighRadius/pradumn203 bản sao GitHub) -> lược đồ AR chuẩn.
    Ngày trả = clear_date (ngày ghi sổ ERP, có thể là nhiễu lô — không có sao kê để kiểm)."""
    p = _cache("real_customer_invoices")
    if p.exists() and not force:
        return pd.read_parquet(p)
    df = pd.read_csv(RAW / "customer_invoices" / "Dataset.csv", low_memory=False)

    def d(s):
        s = pd.to_numeric(s, errors="coerce")
        return pd.to_datetime(s.dropna().astype("int64").astype(str), format="%Y%m%d", errors="coerce").reindex(s.index)

    fx = df["invoice_currency"].map({"USD": 1.0, "CAD": 0.75}).fillna(1.0)
    out = pd.DataFrame({
        "invoice_id": "HR-" + df["invoice_id"].astype("Int64").astype(str) + "-" + df.index.astype(str),
        "firm_id": "HR-" + df["business_code"].astype(str),
        "customer_id": "HR-" + df["cust_number"].astype(str),
        "issue_date": d(df["baseline_create_date"]),
        "due_date": d(df["due_in_date"]),
        "paid_date_true": pd.to_datetime(df["clear_date"], errors="coerce"),
        "amount_gross": pd.to_numeric(df["total_open_amount"], errors="coerce") * fx,
        "terms_code": df["cust_payment_terms"].astype(str),
    })
    out["term_days"] = (out["due_date"] - out["issue_date"]).dt.days.clip(lower=0)
    out = out.dropna(subset=["issue_date", "due_date"]).drop_duplicates("invoice_id")
    out["is_bad_debt"] = False
    out["domain"] = "real_highradius"
    out.to_parquet(p, index=False)
    return out


# ------------------------------------------------------------------ T1/T9: BPI Challenge 2019 (thật)
def bpi2019(force=False) -> pd.DataFrame:
    """Mỗi dòng hàng PO -> 'hoá đơn' phía phải trả: invoice_date = lần đầu 'Record Invoice Receipt'
    (hoặc 'Vendor creates invoice'), paid = 'Clear Invoice' đầu tiên sau đó. Không có hạn thanh toán.
    Hoá đơn chưa clear khi log kết thúc = kiểm duyệt phải (right-censored)."""
    p = _cache("real_bpi2019")
    if p.exists() and not force:
        return pd.read_parquet(p)
    path = RAW / "bpi2019" / "BPI_Challenge_2019.xes"
    rows = []
    trace_attr, events = {}, []
    in_trace = in_event = False
    ev = {}
    for event, el in iterparse(str(path), events=("start", "end")):
        tag = el.tag.split("}")[-1]
        if event == "start":
            if tag == "trace":
                in_trace, trace_attr, events = True, {}, []
            elif tag == "event":
                in_event, ev = True, {}
            continue
        if tag in ("string", "date", "float", "boolean") and in_trace:
            k, v = el.get("key"), el.get("value")
            (ev if in_event else trace_attr)[k] = v
        elif tag == "event":
            events.append(ev)
            in_event = False
            el.clear()
        elif tag == "trace":
            inv_t = clr_t = None
            amt = None
            clr_user = None
            for e in events:
                nmv = e.get("concept:name")
                ts = e.get("time:timestamp")
                if nmv in ("Record Invoice Receipt", "Vendor creates invoice") and inv_t is None:
                    inv_t, amt = ts, e.get("Cumulative net worth (EUR)")
                elif nmv == "Clear Invoice" and inv_t is not None and clr_t is None and ts >= inv_t:
                    clr_t, clr_user = ts, e.get("User")
            if inv_t is not None:
                rows.append((trace_attr.get("concept:name"), trace_attr.get("Company"), trace_attr.get("Vendor"),
                             trace_attr.get("Item Category"), trace_attr.get("Spend area text"),
                             trace_attr.get("Document Type"), trace_attr.get("GR-Based Inv. Verif."),
                             inv_t, clr_t, clr_user, amt))
            in_trace = False
            el.clear()
    df = pd.DataFrame(rows, columns=["invoice_id", "firm_id", "customer_id", "item_category", "spend_area", "doc_type",
                                     "gr_based", "issue_date", "paid_date_true", "clear_user", "amount_gross"])
    for c in ("issue_date", "paid_date_true"):
        df[c] = pd.to_datetime(df[c], errors="coerce", utc=True).dt.tz_localize(None).dt.normalize()
    df["amount_gross"] = pd.to_numeric(df["amount_gross"], errors="coerce")
    df = df[(df["issue_date"] >= "2018-01-01") & (df["issue_date"] <= "2019-01-31")]
    df["domain"] = "real_bpi2019"
    df["is_bad_debt"] = False
    df.to_parquet(p, index=False)
    return df


# ------------------------------------------------------------------ T4: Online Retail II (thật)
def online_retail_weekly(force=False) -> pd.DataFrame:
    """Doanh thu tuần (đã trừ trả hàng) theo quốc gia và theo nhóm khách bán buôn lớn -> chuỗi cho T4."""
    p = _cache("real_online_retail_weekly")
    if p.exists() and not force:
        return pd.read_parquet(p)
    raw_p = _cache("real_online_retail_raw")
    if raw_p.exists():
        df = pd.read_parquet(raw_p)
    else:
        with zipfile.ZipFile(RAW / "online_retail_ii" / "online_retail_ii.zip") as z:
            with z.open("online_retail_II.xlsx") as f:
                sheets = pd.read_excel(f, sheet_name=None, engine="openpyxl")
        df = pd.concat(sheets.values(), ignore_index=True)
        df["Customer ID"] = df["Customer ID"].astype("Int64").astype(str)
        df["Invoice"] = df["Invoice"].astype(str)
        df["StockCode"] = df["StockCode"].astype(str)
        df["Description"] = df["Description"].astype(str)
        df.to_parquet(raw_p, index=False)
    df["rev"] = df["Quantity"] * df["Price"]
    df["week"] = pd.to_datetime(df["InvoiceDate"]).dt.to_period("W-SUN").dt.start_time
    top_c = df.groupby("Country")["rev"].sum().nlargest(12).index
    a = df[df["Country"].isin(top_c)].groupby(["Country", "week"])["rev"].sum().reset_index()
    a["series_id"] = "country:" + a["Country"].astype(str)
    cust = df[df["Customer ID"] != "<NA>"]
    top_k = cust.groupby("Customer ID")["rev"].sum().nlargest(60).index
    b = cust[cust["Customer ID"].isin(top_k)].groupby(["Customer ID", "week"])["rev"].sum().reset_index()
    b["series_id"] = "cust:" + b["Customer ID"].astype(str)
    allw = df.groupby("week")["rev"].sum().reset_index()
    allw["series_id"] = "total"
    out = pd.concat([a[["series_id", "week", "rev"]], b[["series_id", "week", "rev"]], allw[["series_id", "week", "rev"]]])
    weeks = pd.date_range(out["week"].min(), out["week"].max(), freq="7D")
    full = []
    for sid, g in out.groupby("series_id"):
        s = g.set_index("week")["rev"].reindex(weeks, fill_value=0.0)
        full.append(pd.DataFrame({"series_id": sid, "week": weeks, "y": s.values}))
    out = pd.concat(full, ignore_index=True)
    out["domain"] = "real_online_retail"
    out.to_parquet(p, index=False)
    return out


# ------------------------------------------------------------------ T6/T7: Berka (thật)
def berka_weekly(force=False) -> pd.DataFrame:
    """Dòng tiền ròng tuần + số dư cuối tuần cho từng tài khoản ngân hàng thật (1993–1998)."""
    p = _cache("real_berka_weekly")
    if p.exists() and not force:
        return pd.read_parquet(p)
    t = pd.read_csv(RAW / "berka" / "trans.asc", sep=";", low_memory=False)
    t["date"] = pd.to_datetime(t["date"].astype(str), format="%y%m%d")
    t["signed"] = np.where(t["type"] == "PRIJEM", t["amount"], -t["amount"])
    t["week"] = t["date"].dt.to_period("W-SUN").dt.start_time
    g = t.groupby(["account_id", "week"]).agg(inflow=("signed", lambda s: s[s > 0].sum()),
                                             outflow=("signed", lambda s: -s[s < 0].sum()),
                                             net=("signed", "sum"), n=("signed", "size")).reset_index()
    last_bal = t.sort_values(["account_id", "date", "trans_id"]).groupby(["account_id", "week"])["balance"].last()
    g = g.merge(last_bal.rename("balance").reset_index(), on=["account_id", "week"])
    # chỉ giữ tài khoản có lịch sử dài, đầy tuần
    cnt = g.groupby("account_id")["week"].nunique()
    keep = cnt[cnt >= 150].index
    g = g[g["account_id"].isin(keep)]
    full = []
    for aid, s in g.groupby("account_id"):
        w = pd.date_range(s["week"].min(), s["week"].max(), freq="7D")
        s = s.set_index("week").reindex(w)
        s[["inflow", "outflow", "net", "n"]] = s[["inflow", "outflow", "net", "n"]].fillna(0)
        s["balance"] = s["balance"].ffill()
        s["account_id"] = aid
        full.append(s.rename_axis("week").reset_index())
    out = pd.concat(full, ignore_index=True)
    out["domain"] = "real_berka"
    out.to_parquet(p, index=False)
    return out


def berka_loans() -> pd.DataFrame:
    df = pd.read_csv(RAW / "berka" / "loan.asc", sep=";")
    df["date"] = pd.to_datetime(df["date"].astype(str), format="%y%m%d")
    df["default"] = df["status"].isin(["B", "D"]).astype(int)
    return df


# ------------------------------------------------------------------ T2: SBA 7(a) (thật)
SBA_COLS = ["GrossApproval", "SBAGuaranteedApproval", "ApprovalDate", "ApprovalFY", "InitialInterestRate",
            "FixedorVariableInterestInd", "TermInMonths", "NaicsCode", "ProjectState", "BusinessType", "BusinessAge",
            "LoanStatus", "PaidInFullDate", "ChargeOffDate", "GrossChargeOffAmount", "RevolverStatus", "JobsSupported",
            "CollateralInd", "ProcessingMethod", "SoldSecMrktInd", "FranchiseCode", "BankState", "BorrState"]


def label_sba(df, *, horizon_years=3, exempt='drop', asof='2026-06-30'):
    """Nhãn cố định chân trời; EXEMPT thiếu kết quả không được gán âm trong chế độ censor."""
    if exempt not in {'drop', 'keep', 'censor'}:
        raise ValueError('exempt phải là drop, keep hoặc censor')
    df = df.copy()
    for c in ('ApprovalDate', 'PaidInFullDate', 'ChargeOffDate'):
        df[c] = pd.to_datetime(df[c], errors='coerce')
    df['LoanStatus'] = df['LoanStatus'].astype(str).str.replace(' ', '').str.upper()
    asof = pd.Timestamp(asof)
    df = df[~df['LoanStatus'].isin(['CANCLD', 'COMMIT']) &
            (df['ApprovalDate'] <= asof - pd.DateOffset(years=horizon_years))].copy()
    is_exempt = df['LoanStatus'].eq('EXEMPT')
    if exempt == 'drop':
        df = df[~is_exempt].copy()
    end = df['ApprovalDate'] + pd.DateOffset(years=horizon_years)
    co = df['ChargeOffDate'].notna() & (df['ChargeOffDate'] <= end) & (df['ChargeOffDate'] <= asof)
    df['y'] = co.astype('Int64')
    df['label_observed'] = True
    if exempt == 'censor':
        unknown = df['LoanStatus'].eq('EXEMPT') & ~co
        df.loc[unknown, 'y'] = pd.NA
        df.loc[unknown, 'label_observed'] = False
    df['exempt_policy'] = exempt
    df['time_to_chargeoff_days'] = (df['ChargeOffDate'] - df['ApprovalDate']).dt.days
    return df


def sba_7a(force=False, horizon_years=3, exempt='drop', asof='2026-06-30') -> pd.DataFrame:
    """Khoản vay DN nhỏ Mỹ: nhãn = bị xoá nợ (charge-off) trong `horizon_years` năm kể từ phê duyệt.
    Nhãn theo chân trời cố định -> không bị thiên lệch do khoản vay còn đang chạy, nếu cohort đủ già."""
    p = _cache(f"real_sba7a_v2_h{horizon_years}_{exempt}_{asof}")
    if p.exists() and not force:
        return pd.read_parquet(p)
    parts = []
    for f in ("FOIA_7a_FY2010_FY2019.csv", "FOIA_7a_FY2020_Present.csv"):
        parts.append(pd.read_csv(RAW / "sba" / f, usecols=lambda c: c in SBA_COLS, low_memory=False))
    df = pd.concat(parts, ignore_index=True)
    df = label_sba(df, horizon_years=horizon_years, exempt=exempt, asof=asof)
    df["naics2"] = df["NaicsCode"].astype("Int64").astype(str).str[:2]
    df["guarantee_ratio"] = df["SBAGuaranteedApproval"] / df["GrossApproval"]
    df["log_amount"] = np.log1p(df["GrossApproval"])
    df["approval_month"] = df["ApprovalDate"].dt.month
    df["domain"] = "real_sba7a"
    df.to_parquet(p, index=False)
    return df


# ------------------------------------------------------------------ T12/T3: UK Payment Practices (thật)
def home_credit_installments(path=None):
    """Chuẩn hoá file đã tải hợp lệ; ngày tương đối dùng epoch kỹ thuật 2000-01-01.

    Trả (invoices, payments); không tự đăng nhập/chấp nhận điều khoản Kaggle.
    Epoch không mang ý nghĩa lịch kinh tế hoặc luật Việt Nam.
    """
    path = path or RAW / 'home_credit/installments_payments.csv'
    raw = pd.read_csv(path)
    keys = ['SK_ID_CURR', 'SK_ID_PREV', 'NUM_INSTALMENT_VERSION', 'NUM_INSTALMENT_NUMBER']
    required = keys + ['DAYS_INSTALMENT', 'DAYS_ENTRY_PAYMENT', 'AMT_INSTALMENT', 'AMT_PAYMENT']
    if not set(required) <= set(raw):
        raise ValueError('Thiếu cột Home Credit')
    raw['invoice_id'] = 'HC-' + raw[keys].astype(str).agg('-'.join, axis=1)
    epoch = pd.Timestamp('2000-01-01')
    raw['due_date'] = epoch + pd.to_timedelta(raw.DAYS_INSTALMENT, unit='D')
    raw['pay_date_true'] = epoch + pd.to_timedelta(raw.DAYS_ENTRY_PAYMENT, unit='D')
    inv = raw.groupby('invoice_id', sort=False).agg(customer=('SK_ID_CURR', 'first'),
        due_date=('due_date', 'first'), amount_gross=('AMT_INSTALMENT', 'first')).reset_index()
    inv['customer_id'] = 'HC-' + inv.pop('customer').astype(str)
    inv['firm_id'] = 'HC-lender'
    # Chưa có ngày phát hành trong nguồn; chỉ dùng cho T3 theo lịch kỳ trả.
    inv['issue_date'] = inv.due_date
    inv['term_days'] = 0
    pay = raw.dropna(subset=['pay_date_true', 'AMT_PAYMENT']).copy()
    pay = pay[pay.AMT_PAYMENT > 0].sort_values(['pay_date_true', 'invoice_id'])
    pay['amount'] = pay.AMT_PAYMENT
    pay['cumulative'] = pay.groupby('invoice_id').amount.cumsum()
    gross = inv.set_index('invoice_id').amount_gross
    settled = pay[pay.cumulative >= .995 * pay.invoice_id.map(gross)]
    inv['paid_date_true'] = inv.invoice_id.map(settled.groupby('invoice_id').pay_date_true.min())
    inv['paid_amount'] = inv.invoice_id.map(pay.groupby('invoice_id').amount.sum()).fillna(0.)
    inv['paid_ratio'] = inv.paid_amount / inv.amount_gross
    inv['partial'] = inv.paid_ratio < .995
    inv['writeoff_date'] = pd.NaT
    inv['domain'] = 'home_credit_relative_dates'
    pay['kind'] = np.where(pay.cumulative + 1e-6 >= .995 * pay.invoice_id.map(gross), 'final', 'partial')
    pay['payment_id'] = 'HC-P-' + pay.index.astype(str)
    return inv, pay[['payment_id', 'invoice_id', 'pay_date_true', 'amount', 'kind']]


def uk_ppr_stats() -> dict:
    df = pd.read_csv(RAW / "uk_ppr" / "payment_practices.csv", low_memory=False)
    num = lambda c: pd.to_numeric(df[c], errors="coerce")  # noqa: E731
    out = {
        "n_reports": int(len(df)),
        "avg_time_to_pay_median": float(num("Average time to pay").median()),
        "pct_within_30_median": float(num("% Invoices paid within 30 days").median()),
        "pct_31_60_median": float(num("% Invoices paid between 31 and 60 days").median()),
        "pct_over_60_median": float(num("% Invoices paid later than 60 days").median()),
        "pct_not_within_terms_median": float(num("% Invoices not paid within agreed terms").median()),
        "pct_dispute_median": float(num("% Invoices not paid due to dispute").median()),
        "pct_dispute_p90": float(num("% Invoices not paid due to dispute").quantile(0.9)),
    }
    return out
