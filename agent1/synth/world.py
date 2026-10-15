"""T12 — Máy phát "thế giới" SME Việt Nam có nhãn, hiệu chỉnh theo Phần 5 (calibration_vn.json).

Một thế giới = nhiều công ty (người dùng Agent 1), mỗi công ty có khách hàng, hoá đơn điện tử đầu ra,
thanh toán (ngày tiền về thật trên ngân hàng), sao kê ngân hàng (tên đối tác + nội dung chuyển khoản),
sổ cái (ngày ghi sổ có nhiễu lô, phân bổ FIFO sai), lời hứa trả, nhà cung cấp, lương/BHXH/thuế theo luật VN,
và đường số dư tiền mặt "không can thiệp" (ground truth cho T6).

Cơ chế sinh dữ liệu (không phải trọng số cố định -> tránh các dấu hiệu tổng hợp mà realism_audit bắt được):
  * Nhân tố thanh khoản chung F_w: AR(1), nhiễu Student-t (đuôi dày) + chỉ số sốc COVID lấy từ OxCGRT Việt Nam
    (dữ liệu thật đã crawl) + cú sốc "đóng băng trái phiếu" 10/2022–06/2023 theo ngành.
  * Thanh khoản riêng từng khách L_c,w = AR(1) + beta_c * F_w - gamma_ngành * stress_w.
  * Kỳ hạn rời rạc theo ngành (Atradius 43/41/~49 ngày), xác suất đúng hạn phụ thuộc kỷ luật + thanh khoản.
  * Trễ = lognormal theo khách (trung tâm "khoảng một tháng"), đuôi cực dài kiểu Coface (tham số nhạy cảm),
    tranh chấp (UK PPR), sốc riêng khách (điểm gãy), suy giảm trước vỡ nợ.
  * Thói quen "ngày chạy thanh toán" của khách (thứ cố định / ngày 10-25 / cuối tháng), không trả cuối tuần,
    Tết: dồn trả trước Tết, đóng băng trong kỳ nghỉ, chậm khởi động sau Tết.
  * Vỡ nợ cấp khách (hazard phụ thuộc thanh khoản + sốc) -> nợ xấu tương quan, thu hồi một phần.
  * Trả một phần, giảm trừ do tranh chấp, phí chuyển tiền bị trừ, gộp nhiều hoá đơn trong một lệnh chuyển.
  * Kế toán ghi sổ theo ngày / tuần / cuối tháng (nhiễu lô W1), phân bổ FIFO khi nội dung không ghi số HĐ.
  * Lời hứa trả với độ tin cậy riêng từng khách (Beta), nhất quán với ngày trả thật.
  * Đệm tiền mặt ban đầu theo JPMorgan Chase Institute (trung vị 27 ngày chi, 1/4 dưới 13 ngày).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np
import pandas as pd

from .. import calendar_vn as cal
from ..paths import CALIBRATION, RAW, SYNTH
from . import names as nm

INDUSTRY = {
    # credit, terms {days: p}, bad_debt (value), overdue (value)  <- Atradius VN 2025 (by_industry);
    # wholesale/food/services: dùng số toàn mẫu (65%, 45 ngày, 39%, 3%) làm tiền nghiệm.
    "steel_metals": dict(credit=0.61, terms={15: .06, 30: .38, 45: .30, 60: .20, 90: .06}, bad=0.02, overdue=0.35,
                         season=[1.15, .7, 1.05, 1.0, .95, .85, .8, .85, .95, 1.05, 1.2, 1.4], crunch=1.0, covid=.45,
                         ticket=180e6, rev_per_emp=3.0e9),
    "textile_clothing": dict(credit=0.66, terms={15: .05, 30: .45, 45: .30, 60: .15, 90: .05}, bad=0.04, overdue=0.34,
                             season=[.95, .7, .95, 1.0, 1.0, 1.0, 1.05, 1.1, 1.15, 1.15, 1.05, 1.0], crunch=.6, covid=.55,
                             ticket=95e6, rev_per_emp=0.9e9),
    "plastic_rubber": dict(credit=0.69, terms={15: .03, 30: .25, 45: .30, 60: .30, 90: .12}, bad=0.04, overdue=0.47,
                           season=[1.05, .75, 1.0, 1.0, 1.0, .95, .95, 1.0, 1.0, 1.05, 1.1, 1.2], crunch=.5, covid=.4,
                           ticket=70e6, rev_per_emp=1.6e9),
    "wholesale": dict(credit=0.65, terms={0: .05, 15: .10, 30: .40, 45: .25, 60: .15, 90: .05}, bad=0.03, overdue=0.39,
                      season=[1.2, .65, .95, .95, 1.0, .95, .95, 1.0, 1.0, 1.05, 1.1, 1.3], crunch=.5, covid=.5,
                      ticket=45e6, rev_per_emp=4.0e9),
    "food_processing": dict(credit=0.60, terms={0: .05, 15: .15, 30: .45, 45: .25, 60: .10}, bad=0.03, overdue=0.37,
                            season=[1.35, .7, .9, .9, .95, .95, .95, 1.0, 1.05, 1.0, 1.05, 1.3], crunch=.3, covid=.35,
                            ticket=35e6, rev_per_emp=1.8e9),
    "services": dict(credit=0.65, terms={0: .05, 15: .15, 30: .45, 45: .20, 60: .15}, bad=0.03, overdue=0.40,
                     season=[1.0, .7, .95, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.05, 1.05, 1.25], crunch=.4, covid=.6,
                     ticket=60e6, rev_per_emp=1.2e9),
}
TAILS = {  # độ dài trễ phần quá hạn — chạy như khoảng nhạy cảm (Phần 5, mục 3.3)
    "atradius": dict(late_med=(18.0, 36.0), late_sig=(0.35, 0.7), ultra=0.006),
    "uk": dict(late_med=(8.0, 20.0), late_sig=(0.45, 0.8), ultra=0.003),
    "coface": dict(late_med=(30.0, 60.0), late_sig=(0.5, 0.9), ultra=0.03),
}
PAYRUNS = ["adhoc", "dow1", "dow2", "dow3", "dow4", "dom_10_25", "dom_5_20", "dom_15_eom", "dom_eom", "dom_25"]


@dataclass
class WorldConfig:
    name: str = "src"
    seed: int = 1
    start: str = "2019-01-01"
    end: str = "2025-12-31"
    n_firms: int = 40
    tail: str = "atradius"
    industry_mix: dict = field(default_factory=lambda: {"steel_metals": .2, "textile_clothing": .2, "plastic_rubber": .2,
                                                         "wholesale": .2, "food_processing": .1, "services": .1})
    posting_mode_p: tuple = (0.45, 0.30, 0.25)   # daily, weekly, monthly
    payrun_p: tuple = (0.34, .07, .07, .06, .06, .12, .08, .08, .07, .05)
    late_scale: float = 1.0
    dispute_scale: float = 1.0
    n_cust_median: float = 60.0
    revenue_median: float = 40e9
    memo_invoice_no_p: tuple = (2.0, 2.0)      # Beta(a,b) xác suất khách ghi số HĐ trong nội dung CK
    ontime_shift: dict = field(default_factory=dict)   # logit shift theo ngành (từ vòng hiệu chỉnh)
    pd_mult: dict = field(default_factory=dict)        # hệ số PD theo ngành (từ vòng hiệu chỉnh)
    write_xml: int = 200
    cod_mult: float = 1.8
    cash_cap_days: float = 60.0   # rút lợi nhuận/chia cổ tức khi số dư vượt ngưỡng (ngày chi bình quân)


# ---------------------------------------------------------------------------- calendar arrays
class Cal:
    def __init__(self, start, end):
        self.d0 = np.datetime64((pd.Timestamp(start) - pd.Timedelta(days=430)).date(), "D")
        self.d1 = np.datetime64((pd.Timestamp(end) + pd.Timedelta(days=1100)).date(), "D")
        days = np.arange(self.d0, self.d1)
        self.days = days
        n = len(days)
        ts = pd.DatetimeIndex(days)
        self.wd = ts.weekday.values
        self.dom = ts.day.values
        self.month = ts.month.values
        self.year = ts.year.values
        self.eom = (ts + pd.Timedelta(days=1)).day.values == 1
        hs = cal.holiday_set()
        self.hol = np.array([d.date() in hs for d in ts])
        self.bd = (self.wd < 5) & ~self.hol
        self.next_bd = self._next(self.bd)
        prv = np.empty(n, dtype=np.int64)
        j = 0
        for i in range(n):
            if self.bd[i]:
                j = i
            prv[i] = j
        self.prev_bd = prv
        self.next_ptn, self.prev_ptn = {}, {}
        for p in PAYRUNS:
            if p == "adhoc":
                ok = np.ones(n, bool)
            elif p.startswith("dow"):
                ok = self.wd == int(p[3])
            else:
                ok = np.zeros(n, bool)
                for q in p.split("_")[1:]:
                    ok |= self.eom if q == "eom" else (self.dom == int(q))
            self.next_ptn[p] = self._next(ok)
            self.prev_ptn[p] = self._prev(ok)
        self.tet_break = [(int((np.datetime64(a) - self.d0).astype(int)), int((np.datetime64(b) - self.d0).astype(int)))
                          for a, b in cal.TET_BREAK.values()]
        self.n = n

    @staticmethod
    def _next(ok):
        n = len(ok)
        arr = np.empty(n, dtype=np.int64)
        j = n - 1
        for i in range(n - 1, -1, -1):
            if ok[i]:
                j = i
            arr[i] = j
        return arr

    @staticmethod
    def _prev(ok):
        n = len(ok)
        arr = np.empty(n, dtype=np.int64)
        j = 0
        for i in range(n):
            if ok[i]:
                j = i
            arr[i] = j
        return arr

    def idx(self, d):
        return (np.asarray(d, dtype="datetime64[D]") - self.d0).astype(np.int64)

    def date(self, i):
        return self.d0 + np.asarray(i, dtype=np.int64)

    def clip(self, i):
        return np.clip(i, 0, self.n - 1)

    def snap_bd(self, i):
        return self.next_bd[self.clip(i)]

    def tet_break_of(self, i):
        st = np.array([a for a, _ in self.tet_break])
        en = np.array([b for _, b in self.tet_break])
        k = np.clip(np.searchsorted(en, i, side="left"), 0, len(st) - 1)
        return st[k], en[k]


# ---------------------------------------------------------------------------- macro
def load_oxcgrt_vn_weekly(weeks: pd.DatetimeIndex) -> np.ndarray:
    p = RAW / "oxcgrt" / "OxCGRT_compact_national_v1.csv"
    s = pd.Series(0.0, index=weeks)
    if p.exists():
        df = pd.read_csv(p, usecols=["CountryName", "Date", "StringencyIndex_Average", "C2M_Workplace closing"],
                         low_memory=False)
        df = df[df["CountryName"] == "Vietnam"].copy()
        df["Date"] = pd.to_datetime(df["Date"].astype(str), format="%Y%m%d")
        df = df.set_index("Date")
        si = df["StringencyIndex_Average"].resample("W-MON").mean().fillna(0)
        c6 = pd.read_csv(p, usecols=["CountryName", "Date", "C6M_Stay at home requirements"], low_memory=False)
        c6 = c6[c6["CountryName"] == "Vietnam"]
        c6 = pd.Series(c6["C6M_Stay at home requirements"].values,
                       index=pd.to_datetime(c6["Date"].astype(str), format="%Y%m%d")).resample("W-MON").mean().fillna(0)
        # sốc kinh tế = phần vượt ngưỡng 55 của chỉ số nghiêm ngặt, nhân với mức yêu cầu ở nhà (C6M)
        comb = ((si - 55.0) / 35.0).clip(0, 1) * (0.5 + 0.25 * c6.reindex(si.index).fillna(0))
        s = comb.reindex(weeks).fillna(0.0).clip(0, 1)
    else:  # dự phòng khi chưa crawl: các đợt giãn cách chính
        for a, b, v in (("2020-04-01", "2020-04-22", .8), ("2020-07-28", "2020-09-05", .35),
                        ("2021-05-01", "2021-07-08", .45), ("2021-07-09", "2021-10-01", .9),
                        ("2021-10-02", "2021-12-31", .4)):
            s[(s.index >= a) & (s.index <= b)] = v
    return np.asarray(s.values, dtype=float)


def load_lending_rate() -> dict:
    p = RAW / "wdi_vn" / "wdi_vietnam.csv"
    out = {}
    if p.exists():
        df = pd.read_csv(p)
        r = df[df["indicator"] == "FR.INR.LEND"].dropna(subset=["value"])
        out = {int(y): float(v) / 100 for y, v in zip(r["year"], r["value"])}
    return out


def crunch_curve(weeks: pd.DatetimeIndex) -> np.ndarray:
    """Cú sốc thanh khoản 2022Q4–2023Q2 (đóng băng TPDN/BĐS): tăng dần rồi giảm."""
    t = (weeks - pd.Timestamp("2022-10-01")).days.values / 7.0
    return np.where((t >= 0) & (t <= 40), np.exp(-0.5 * ((t - 16.0) / 9.0) ** 2), 0.0)


# ---------------------------------------------------------------------------- generator
class World:
    def __init__(self, cfg: WorldConfig):
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg.seed)
        self.cal = Cal(cfg.start, cfg.end)
        self.start = pd.Timestamp(cfg.start)
        self.end = pd.Timestamp(cfg.end)
        self.base = np.datetime64(self.start.date(), "D")
        self.base_i = int(self.cal.idx(self.base))
        self.weeks = pd.date_range(self.start - pd.Timedelta(days=self.start.weekday()), self.end, freq="W-MON")
        self.W = len(self.weeks)
        self.week0_i = int(self.cal.idx(np.datetime64(self.weeks[0].date(), "D")))
        self.lend = load_lending_rate()
        self.used_names = set()

    def macro(self):
        r = self.rng
        nu = 4.0
        eps = r.standard_t(nu, self.W) / math.sqrt(nu / (nu - 2))
        F = np.zeros(self.W)
        for t in range(1, self.W):
            F[t] = 0.93 * F[t - 1] + 0.22 * eps[t]
        self.F, self.covid, self.crunch = F, load_oxcgrt_vn_weekly(self.weeks), crunch_curve(self.weeks)
        return pd.DataFrame({"week": self.weeks, "common_factor": F, "covid_stress": self.covid,
                             "credit_crunch": self.crunch})

    def week_of(self, day_idx):
        return np.clip((np.asarray(day_idx) - self.week0_i) // 7, 0, self.W - 1)

    # ---------------- one firm
    def make_firm(self, fid):
        r, cfg = self.rng, self.cfg
        inds = list(cfg.industry_mix)
        pr = np.array(list(cfg.industry_mix.values()), float)
        ind = str(r.choice(inds, p=pr / pr.sum()))
        I = INDUSTRY[ind]
        rev = float(np.clip(np.exp(r.normal(np.log(cfg.revenue_median), 0.8)), 3e9, 600e9))
        name, short, core = nm.make_company_name(r, ind, self.used_names)
        head = max(5, int(rev / (I["rev_per_emp"] * np.exp(r.normal(0, .3)))))
        return dict(firm_id=f"F{fid:03d}", name=name, short=short, core=core, mst=nm.make_mst(r), industry=ind,
                    region=int(r.choice([1, 2, 3, 4], p=[.45, .3, .15, .1])), revenue_annual=rev, headcount=head,
                    wage_mult=float(r.uniform(1.5, 2.6)), margin=float(np.clip(r.normal(0.045, 0.025), -0.01, 0.12)),
                    growth=float(r.normal(0.07, 0.08)), credit_share=I["credit"],
                    posting_mode=["daily", "weekly", "monthly"][int(r.choice(3, p=cfg.posting_mode_p))],
                    collect_intensity=float(r.uniform(0.25, 0.8)),
                    payday=[5, 10, "eom", 15][int(r.choice(4, p=[.25, .45, .2, .1]))],
                    payroll_lag_month=int(r.random() < 0.8),
                    supplier_payrun=["dom_10_25", "dom_5_20", "dom_15_eom", "dom_eom"][int(r.integers(4))],
                    rent=float(rev * r.uniform(0.004, 0.012) / 12), rent_day=int(r.choice([1, 5, 10])),
                    loan_principal=float(rev * r.uniform(0.0, 0.25)), loan_day=int(r.choice([5, 15, 25])),
                    charter_capital=float(rev * r.uniform(0.1, 0.5)),
                    buffer_days=float(np.exp(r.normal(np.log(27.0), 1.08))),
                    covid_sens=float(I["covid"] * r.uniform(.6, 1.4)), crunch_sens=float(I["crunch"] * r.uniform(.6, 1.4)),
                    bank=str(r.choice(nm.BANKS)))

    def make_customers(self, firm):
        r, cfg = self.rng, self.cfg
        I = INDUSTRY[firm["industry"]]
        T = TAILS[cfg.tail]
        n = int(np.clip(np.exp(r.normal(np.log(cfg.n_cust_median), 0.6)), 8, 400))
        w = r.pareto(1.5, n) + 1.0
        w = w / w.sum()
        span = (self.end - self.start).days
        start_days = np.where(r.random(n) < 0.55, 0, r.integers(0, span - 120, n))
        end_days = np.minimum(start_days + r.exponential(365 * 6, n) + 180, span + 2000)
        tk = np.array(list(I["terms"]))
        tp = np.array(list(I["terms"].values()))
        terms = r.choice(tk, n, p=tp / tp.sum())
        cod = r.random(n) < np.clip((1 - I["credit"]) * self.cfg.cod_mult * (1 - w / w.max()) ** 2, 0, 0.9)
        terms = np.where(cod, 0, terms)
        ontime_base = np.clip(r.beta(2.4, 1.5, n), 0.02, 0.995)
        a_logit = np.log(ontime_base / (1 - ontime_base)) + cfg.ontime_shift.get(firm["industry"], 0.0)
        late_med = np.exp(r.normal(np.log(np.sqrt(T["late_med"][0] * T["late_med"][1])), 0.55, n)) * cfg.late_scale
        payrun = r.choice(PAYRUNS, n, p=np.array(cfg.payrun_p) / sum(cfg.payrun_p))
        rows = []
        for i in range(n):
            name, short, _ = nm.make_company_name(r, str(r.choice(list(INDUSTRY))), self.used_names)
            rows.append(dict(
                customer_id=f"{firm['firm_id']}-C{i:04d}", firm_id=firm["firm_id"], name=name, short=short,
                mst=nm.make_mst(r), weight=float(w[i]), start_day=int(start_days[i]), end_day=int(end_days[i]),
                term_days=int(terms[i]), ontime_logit=float(a_logit[i]), early_p=float(r.beta(1.2, 6)),
                late_med=float(late_med[i]), late_sig=float(r.uniform(*T["late_sig"])),
                ultra_p=float(T["ultra"] * r.lognormal(0, .8)), payrun=str(payrun[i]),
                beta_F=float(r.uniform(0.3, 1.6)), rho=float(r.uniform(0.85, 0.97)), idio_sd=float(r.uniform(0.08, 0.25)),
                pd_frailty=float(r.lognormal(-0.4, 0.9)),
                dispute_p=float(np.clip(r.lognormal(np.log(0.012), 0.7) * cfg.dispute_scale, 0, 0.2)),
                partial_p=float(r.beta(1.0, 12.0)), batch_pay=bool(r.random() < 0.55),
                memo_no_p=float(r.beta(*cfg.memo_invoice_no_p)), reliability=float(r.beta(4.0, 2.0)),
                tet_settle_p=float(r.beta(3, 3)), monthly_consolidate=bool(r.random() < 0.12 and terms[i] > 0),
                ticket=float(I["ticket"] * (w[i] * n) ** 0.35 * r.lognormal(0, 0.4) * (firm["revenue_annual"] / 40e9) ** 0.5),
                bank=str(r.choice(nm.BANKS)), fifo_alloc=bool(r.random() < 0.5),
                break_day=int(r.integers(200, span)) if r.random() < 0.10 else -1,
                break_shift=float(r.uniform(8, 25)),
            ))
        cust = pd.DataFrame(rows)
        cust["ticket"] = cust["ticket"].clip(3e6, None)
        return cust

    def customer_paths(self, firm, cust):
        r = self.rng
        n, W = len(cust), self.W
        sec_stress = firm["covid_sens"] * self.covid + firm["crunch_sens"] * self.crunch
        rho, bF = cust["rho"].values, cust["beta_F"].values
        z = r.standard_normal((n, W))
        idio = np.zeros((n, W))
        idio[:, 0] = z[:, 0]
        a = np.sqrt(1 - rho ** 2)
        for t in range(1, W):
            idio[:, t] = rho * idio[:, t - 1] + a * z[:, t]          # AR(1) phương sai 1
        Fz = self.F / (self.F.std() + 1e-9)
        # thanh khoản chuẩn hoá ~N(0,1) trong thời bình, trừ sốc ngành khi khủng hoảng
        L = (idio + bF[:, None] * Fz[None, :]) / np.sqrt(1 + bF[:, None] ** 2) - 1.2 * sec_stress[None, :] * bF[:, None]
        base_annual = 0.06 * self.cfg.pd_mult.get(firm["industry"], 1.0) * INDUSTRY[firm["industry"]]["bad"] / 0.03
        h0 = 1 - (1 - base_annual) ** (1 / 52)
        h = h0 * cust["pd_frailty"].values[:, None] * np.exp(0.7 * np.clip(-L, 0, None) + 1.0 * sec_stress[None, :])
        hit = r.random((n, W)) < np.clip(h, 0, 0.2)
        start_w = np.clip((cust["start_day"].values + self.base_i - self.week0_i) // 7 + 26, 0, W)
        for i in range(n):
            hit[i, : start_w[i]] = False
        default_w = np.where(hit.any(axis=1), hit.argmax(axis=1), -1)
        # khách vỡ nợ ngừng phát sinh hoá đơn mới (doanh nghiệp ngừng bán chịu ~2 tuần trước khi khách sụp)
        dday = self.week0_i + default_w * 7 - self.base_i - 14
        cust["end_day"] = np.where(default_w >= 0, np.minimum(cust["end_day"].values, dday), cust["end_day"].values)
        return L, default_w, sec_stress

    def make_invoices(self, firm, cust):
        r, C = self.rng, self.cal
        I = INDUSTRY[firm["industry"]]
        W = self.W
        season = np.array(I["season"])[self.weeks.month.values - 1]
        tet = np.ones(W)
        for a, b in cal.TET_BREAK.values():
            wa = (pd.Timestamp(a) - self.weeks[0]).days // 7
            wb = (pd.Timestamp(b) - self.weeks[0]).days // 7
            for k, f in ((wa - 2, 1.15), (wa - 1, 1.25), (wa, .35), (wb, .45), (wb + 1, .7)):
                if 0 <= k < W:
                    tet[k] *= f
        noise = np.zeros(W)
        e = r.normal(0, 0.10, W)
        for t in range(1, W):
            noise[t] = 0.6 * noise[t - 1] + e[t]
        R = (firm["revenue_annual"] / 52) * np.exp(firm["growth"] * np.arange(W) / 52.0) * season * tet * np.exp(noise) \
            * (1 - 0.6 * firm["covid_sens"] * self.covid) * (1 - 0.35 * firm["crunch_sens"] * self.crunch)
        R = np.clip(R, 0, None)
        firm["weekly_revenue_plan"] = R
        cw, tick = cust["weight"].values, cust["ticket"].values
        sd, ed = cust["start_day"].values, cust["end_day"].values
        ci_l, day_l, amt_l = [], [], []
        for t in range(W):
            day0 = (self.weeks[t] - self.start).days
            active = (sd <= day0) & (ed > day0)
            if not active.any():
                continue
            share = np.where(active, cw, 0)
            lam = share / share.sum() * R[t] / tick
            k = r.poisson(lam)
            nz = np.nonzero(k)[0]
            if len(nz) == 0:
                continue
            cis = np.repeat(nz, k[nz])
            ci_l.append(cis)
            day_l.append(day0 + r.choice(6, len(cis), p=[.19, .19, .19, .19, .19, .05]))
            amt_l.append(tick[cis] * r.lognormal(0, 0.75, len(cis)))
        inv = pd.DataFrame({"ci": np.concatenate(ci_l), "day": np.concatenate(day_l), "net": np.concatenate(amt_l)})
        mc = cust["monthly_consolidate"].values[inv["ci"].values]
        if mc.any():
            d = self.start + pd.to_timedelta(inv.loc[mc, "day"], unit="D")
            eom = (d + pd.offsets.MonthEnd(0)).values.astype("datetime64[D]")
            eom_i = C.prev_bd[C.clip(C.idx(eom))]
            inv.loc[mc, "day"] = eom_i - self.base_i
            g = inv[mc].groupby(["ci", "day"], as_index=False)["net"].sum()
            inv = pd.concat([inv[~mc], g], ignore_index=True)
        inv = inv[(inv["day"] >= 0) & (inv["day"] <= (self.end - self.start).days)].copy()
        di = C.clip(inv["day"].values.astype(np.int64) + self.base_i)
        keep_sat = (C.wd[di] == 5) & (r.random(len(di)) < 0.6) & ~C.hol[di]
        inv["issue_i"] = np.where(keep_sat, di, C.next_bd[di])
        inv["net"] = (np.round(inv["net"].values / 1000) * 1000).clip(1e6, None)
        return inv.sort_values(["issue_i", "ci"]).reset_index(drop=True)

    def settle(self, firm, cust, inv, L, default_w, sec_stress):
        r, C = self.rng, self.cal
        n = len(inv)
        ci = inv["ci"].values
        term = cust["term_days"].values[ci]
        issue = inv["issue_i"].values
        due = issue + term
        wdue = self.week_of(due)
        lat = L[ci, wdue]
        stress = sec_stress[wdue]
        logit = cust["ontime_logit"].values[ci] + 0.6 * lat - 1.2 * stress
        on = r.random(n) < 1 / (1 + np.exp(-logit))
        early = on & (r.random(n) < cust["early_p"].values[ci])
        delay = np.where(early, -np.round(r.uniform(0.2, 0.9, n) * np.minimum(term, 40)), -r.integers(0, 4, n))
        med = cust["late_med"].values[ci] * np.exp(-0.25 * lat) * (1 + 0.8 * stress)
        late_d = np.exp(np.log(med) + cust["late_sig"].values[ci] * r.standard_normal(n)) + 1
        ultra = r.random(n) < cust["ultra_p"].values[ci] * (1 + 2 * stress + np.clip(-lat, 0, None))
        late_d = late_d + np.where(ultra, 90 + 60 * r.pareto(2.2, n), 0)
        delay = np.where(on, delay, late_d)
        bday = cust["break_day"].values[ci]
        after = (bday >= 0) & ((issue - self.base_i) >= bday)
        delay = delay + np.where(after, cust["break_shift"].values[ci] * r.uniform(.6, 1.4, n), 0)
        disp = r.random(n) < cust["dispute_p"].values[ci]
        delay = delay + np.where(disp, r.uniform(15, 75, n), 0)
        credit_note = np.where(disp & (r.random(n) < 0.6), inv["net"].values * r.uniform(0.05, 0.3, n), 0.0)
        cod = term == 0
        delay = np.where(cod, r.integers(0, 4, n), delay)
        dw = default_w[ci]
        dday = np.where(dw >= 0, self.week0_i + dw * 7 + 3, 10 ** 9)
        pre = (dw >= 0) & (due > dday - 120) & (due <= dday)
        delay = delay + np.where(pre, r.uniform(10, 40, n), 0)
        target = np.maximum(due + np.round(delay).astype(np.int64), issue)
        pr = cust["payrun"].values[ci]
        tc = C.clip(target)
        pay = tc.copy()
        for p in PAYRUNS:
            m = pr == p
            if m.any():
                nx = C.next_ptn[p][tc[m]]
                pv = C.prev_ptn[p][tc[m]]
                # khách định trả đúng hạn dùng kỳ chạy thanh toán gần nhất TRƯỚC hạn (nếu còn sau ngày lập)
                use_prev = on[m] & (pv >= issue[m]) & (tc[m] - pv <= 16)
                pay[m] = np.where(use_prev, pv, nx)
        pay = np.where(cod, tc, pay)
        bd_prev = C.prev_bd[C.clip(pay)]
        pay = np.where(on & (bd_prev >= issue), bd_prev, C.snap_bd(pay))
        ts, te = C.tet_break_of(pay)
        near = (pay >= ts - 25) & (pay <= te + 12) & (issue < ts - 15) & ~cod
        settle = near & (r.random(n) < cust["tet_settle_p"].values[ci] * np.clip(1 + lat, 0.2, 1.5) * 0.6) & (due <= te + 10)
        pre_tet = C.prev_bd[C.clip(ts - 1 - r.integers(0, 6, n))]
        pay = np.where(settle, np.maximum(pre_tet, issue), pay)
        post = near & ~settle & (pay > te) & (pay <= te + 12)
        pay = np.where(post, C.snap_bd(pay + r.integers(0, 6, n)), pay)
        sat = (r.random(n) < 0.012) & (C.wd[C.clip(pay - 2)] == 5) & ~C.hol[C.clip(pay - 2)] & (pay - 2 >= issue)
        pay = np.where(sat, pay - 2, pay)
        bad = (dw >= 0) & (pay > dday)
        bad |= disp & (r.random(n) < 0.12)
        recov = bad & (r.random(n) < 0.25)
        recov_frac = np.where(recov, r.uniform(0.2, 0.5, n), 0)
        recov_day = C.snap_bd(np.maximum(np.minimum(dday, pay), due) + r.integers(120, 360, n))
        writeoff_day = C.snap_bd(np.maximum(np.minimum(dday, pay), due) + r.integers(180, 400, n))
        part_p = np.clip(cust["partial_p"].values[ci] * (1 + 1.5 * np.clip(-lat, 0, None)), 0, 0.6)
        part = ~bad & ~cod & (r.random(n) < part_p)
        frac1 = r.uniform(0.3, 0.7, n)
        pay2 = C.snap_bd(pay + r.integers(10, 46, n))
        idates = pd.DatetimeIndex(C.date(issue))
        vat = np.full(n, 0.10)
        if firm["industry"] != "steel_metals":
            for a, b in cal.VAT_REDUCTION:
                vat[(idates >= a) & (idates <= b)] = 0.08
        net = inv["net"].values
        gross = np.round((net - credit_note) * (1 + vat) / 1000) * 1000
        amount_inv = np.round(net * (1 + vat) / 1000) * 1000
        short_pay = part & (r.random(n) < 0.15)
        a1 = np.round(gross * frac1, -6)
        a1 = np.where(a1 <= 0, np.round(gross * frac1, -3), a1)
        a2 = np.where(short_pay, np.round((gross - a1) * r.uniform(0.9, 0.99, n), -3), gross - a1)
        k = np.arange(n)
        full = ~bad & ~part
        pays = pd.concat([
            pd.DataFrame({"k": k[full], "day_i": pay[full], "amount": gross[full], "kind": "full"}),
            pd.DataFrame({"k": k[part], "day_i": pay[part], "amount": a1[part], "kind": "partial"}),
            pd.DataFrame({"k": k[part], "day_i": pay2[part], "amount": a2[part], "kind": "final"}),
            pd.DataFrame({"k": k[recov], "day_i": recov_day[recov], "amount": np.round(gross * recov_frac, -3)[recov],
                          "kind": "recovery"}),
        ], ignore_index=True).sort_values(["day_i", "k"]).reset_index(drop=True)
        inv = inv.assign(term_days=term, due_i=due, target_i=target, vat_rate=vat, amount_gross=amount_inv,
                         credit_note=np.round(credit_note * (1 + vat), -3), dispute=disp, is_bad_debt=bad,
                         writeoff_i=np.where(bad, writeoff_day, -1), ultra_late=ultra & ~on,
                         liquidity_at_due=lat, stress_at_due=stress, partial=part)
        return inv, pays

    def bank_ledger(self, firm, cust, inv, pays):
        r, C = self.rng, self.cal
        p = pays.copy()
        p["ci"] = inv["ci"].values[p["k"].values]
        p["invoice_no"] = inv["invoice_no"].values[p["k"].values]
        batch = cust["batch_pay"].values[p["ci"].values]
        p["grp"] = np.where(batch, p["ci"].astype(str) + "_" + p["day_i"].astype(str), "s" + p.index.astype(str))
        txns = []
        tx_of = np.empty(len(p), dtype=object)
        for g, sub in p.groupby("grp", sort=False):
            c = cust.iloc[int(sub["ci"].iloc[0])]
            fee = float(r.choice([11000, 22000])) if r.random() < 0.05 else 0.0
            dt = pd.Timestamp(C.date(int(sub["day_i"].iloc[0])))
            tid = f"{firm['firm_id']}-T{len(txns):06d}"
            txns.append(dict(txn_id=tid, firm_id=firm["firm_id"], value_date=dt, amount=float(sub["amount"].sum()) - fee,
                             direction="in", counterparty=nm.counterparty_variant(r, c["name"], c["short"]),
                             memo=nm.transfer_memo(r, c["short"], firm["core"], sub["invoice_no"].tolist(), dt.month,
                                                   c["memo_no_p"]),
                             txn_type="customer_payment", true_customer_id=c["customer_id"], fee_deducted=fee))
            tx_of[sub.index.values] = tid
        p["txn_id"] = tx_of
        span = (self.end - self.start).days
        k_noise = int(len(txns) * 0.12) + 24
        nd = C.snap_bd(self.base_i + r.integers(0, span, k_noise))
        kinds = r.choice(["interest", "cash_deposit", "internal", "refund", "loan_disbursement", "unknown"], k_noise,
                         p=[.25, .25, .2, .12, .03, .15])
        memo = {"interest": "TRA LAI TIEN GUI", "cash_deposit": "NOP TIEN MAT", "internal": "CHUYEN TIEN NOI BO",
                "refund": "HOAN TIEN DAT COC", "loan_disbursement": "GIAI NGAN KHOAN VAY HDTD", "unknown": "CK"}
        rng_amt = {"interest": (1e5, 5e6), "cash_deposit": (5e6, 2e8), "internal": (1e7, 2e9), "refund": (1e6, 5e7),
                   "loan_disbursement": (5e8, 5e9), "unknown": (1e6, 3e8)}
        for d, kd in zip(nd, kinds):
            cp = ""
            if kd == "unknown":
                cp = nm.ascii_upper(cust["short"].iloc[int(r.integers(len(cust)))])[:50]
            txns.append(dict(txn_id=f"{firm['firm_id']}-T{len(txns):06d}", firm_id=firm["firm_id"],
                             value_date=pd.Timestamp(C.date(d)), amount=float(round(r.uniform(*rng_amt[kd]), -3)),
                             direction="in", counterparty=cp, memo=memo[kd], txn_type=kd, true_customer_id=None,
                             fee_deducted=0.0))
        bank = pd.DataFrame(txns)
        mode = firm["posting_mode"]
        di = p["day_i"].values
        m = len(di)
        if mode == "daily":
            post = C.snap_bd(di + np.where(r.random(m) < 0.9, r.integers(0, 2, m), r.integers(2, 6, m)))
        elif mode == "weekly":
            post = C.snap_bd(C.next_ptn["dow4"][C.clip(di)])
        else:
            me = C.prev_bd[C.next_ptn["dom_eom"][C.clip(di)]]
            me = np.where(me < di, C.prev_bd[C.next_ptn["dom_eom"][C.clip(di + 5)]], me)
            nxt = C.snap_bd(me + 1)
            post = np.where(r.random(m) < 0.3, C.snap_bd(nxt + r.integers(0, 4, m)), me)
            post = np.maximum(post, di)
        p["post_i"] = post
        p["ledger_k"] = p["k"]
        if mode != "daily":
            fifo_c = cust["fifo_alloc"].values
            fin = p[p["kind"].isin(["full", "final"])]
            for c_i, sub in fin.groupby("ci"):
                if not fifo_c[c_i] or len(sub) < 2:
                    continue
                # kế toán gạch nợ theo thứ tự HĐ cũ nhất trước: ngày ghi sổ (đã sắp) gán cho HĐ theo thứ tự lập
                s = sub.sort_values("k")
                p.loc[s.index, "post_i"] = np.sort(s["post_i"].values)
        return bank, p

    def promises(self, firm, cust, inv, pays):
        r, C = self.rng, self.cal
        last = pays[pays["kind"].isin(["full", "final", "recovery"])].groupby("k")["day_i"].max()
        actual = np.full(len(inv), 10 ** 9, dtype=np.int64)
        actual[last.index.values] = last.values
        due = inv["due_i"].values
        rel = cust["reliability"].values[inv["ci"].values]
        rows = []
        done = np.zeros(len(inv), bool)
        for chk in (7, 21, 45, 75):
            t0 = due + chk
            cand = np.nonzero((actual > t0) & (inv["term_days"].values > 0) & ~done &
                              (r.random(len(inv)) < firm["collect_intensity"]))[0]
            for k in cand:
                tk = int(t0[k])
                horizon = actual[k] - tk
                if r.random() < rel[k] and horizon <= 60:
                    prom = int(C.snap_bd(actual[k] + int(round(r.normal(0, 1.5)))))
                else:
                    prom = int(C.snap_bd(tk + int(r.integers(3, 15))))
                    if horizon < 10 ** 8 and prom >= actual[k] - 3:
                        prom = int(C.snap_bd(max(tk + 1, int(actual[k]) - int(r.integers(5, 20)))))
                kept = abs(int(actual[k]) - prom) <= 3
                rows.append(dict(invoice_k=int(k), made_i=int(C.snap_bd(tk)), promised_i=prom, kept=bool(kept)))
                if kept:
                    done[k] = True
        return pd.DataFrame(rows)

    def outflows(self, firm, inv):
        r, C = self.rng, self.cal
        R = firm["weekly_revenue_plan"]
        payroll_share = firm["headcount"] * cal.min_wage(self.start, firm["region"]) * firm["wage_mult"] * 13 / firm["revenue_annual"]
        opex_share = 0.02 + firm["rent"] * 12 / firm["revenue_annual"]
        cogs = float(np.clip(1 - firm["margin"] - payroll_share * 1.3 - opex_share, 0.35, 0.92))
        firm["cogs_ratio"] = cogs
        sup_terms = int(r.choice([0, 15, 30, 45, 60], p=[.1, .15, .4, .2, .15]))
        rows = []
        for t in range(self.W):
            amt = R[min(self.W - 1, t + 2)] * cogs * r.lognormal(0, 0.15)
            if amt <= 0:
                continue
            d_i = int(C.snap_bd(self.week0_i + t * 7 + int(r.integers(0, 5))))
            vr = cal.vat_rate(pd.Timestamp(C.date(d_i)), firm["industry"])
            due = d_i + int(r.choice([sup_terms, 30, 45], p=[.6, .25, .15]))
            pay = int(C.snap_bd(C.next_ptn[firm["supplier_payrun"]][C.clip(due)]))
            rows.append((pay, "supplier", float(round(amt * (1 + vr), -3)), d_i, float(amt * vr)))
        ap = pd.DataFrame(rows, columns=["day_i", "category", "amount", "incurred_i", "input_vat"])
        inv_d = pd.DatetimeIndex(C.date(inv["issue_i"].values))
        out_vat = pd.Series((inv["amount_gross"] - inv["amount_gross"] / (1 + inv["vat_rate"])).values, index=inv_d)
        in_vat = pd.Series(ap["input_vat"].values, index=pd.DatetimeIndex(C.date(ap["incurred_i"].values)))
        monthly = firm["revenue_annual"] > cal.MONTHLY_VAT_THRESHOLD
        freq = "ME" if monthly else "QE"
        ov = out_vat.resample(freq).sum()
        iv = in_vat.resample(freq).sum().reindex(ov.index).fillna(0)
        carry, vat_by = 0.0, {}
        for pe in ov.index:
            v = ov[pe] - iv[pe] + carry
            carry = min(0.0, v)
            vat_by[pd.Timestamp(pe).normalize()] = max(0.0, v)
        rev_q = pd.Series((inv["amount_gross"] / (1 + inv["vat_rate"])).values, index=inv_d).resample("QE").sum()
        cit_by = {pd.Timestamp(q).normalize(): max(0.0, 0.2 * firm["margin"] * v) for q, v in rev_q.items()}
        pay_by = {}
        for pm in pd.period_range(self.start - pd.offsets.MonthBegin(2), self.end, freq="M"):
            mw = cal.min_wage(pm.to_timestamp(), firm["region"])
            pay_by[(pm.year, pm.month)] = firm["headcount"] * mw * firm["wage_mult"] * (1 + 0.03 * max(0, pm.year - self.start.year))
        ann_rate = self.lend.get(self.start.year) or 0.08
        fsched = dict(revenue_prev_year=firm["revenue_annual"], payday=firm["payday"],
                      payroll_lag_month=firm["payroll_lag_month"], rent=firm["rent"], rent_day=firm["rent_day"],
                      loan_payment=firm["loan_principal"] * ann_rate / 12, loan_day=firm["loan_day"],
                      charter_capital=firm["charter_capital"])
        sch = cal.obligation_schedule(fsched, self.start, self.end, pay_by, vat_by, cit_by).dropna(subset=["amount"])
        extra = []
        for y, (a, b) in cal.TET_BREAK.items():
            d = pd.Timestamp(a) - pd.Timedelta(days=3)
            if self.start <= d <= self.end:
                g = pay_by.get((d.year, d.month), next(iter(pay_by.values())))
                extra.append((cal.prev_business_day(d), "tet_bonus", g * r.uniform(0.6, 1.2), (y, 0)))
        for pm in pd.period_range(self.start, self.end, freq="M"):
            extra.append((cal.next_business_day(pd.Timestamp(pm.year, pm.month, 15)), "utilities",
                          firm["revenue_annual"] / 12 * r.uniform(0.006, 0.012), (pm.year, pm.month)))
        for _ in range(int(r.poisson(1.5 * (self.end.year - self.start.year + 1)))):
            d = cal.next_business_day(self.start + pd.Timedelta(days=int(r.integers(0, (self.end - self.start).days))))
            extra.append((d, "capex", firm["revenue_annual"] * r.uniform(0.01, 0.05), (d.year, d.month)))
        sch = pd.concat([sch, pd.DataFrame(extra, columns=sch.columns)], ignore_index=True)
        sch["day_i"] = C.idx(pd.DatetimeIndex(sch["date"]).values.astype("datetime64[D]"))
        sch["known_in_advance"] = sch["category"] != "capex"
        ap["known_in_advance"] = True
        out = pd.concat([ap[["day_i", "category", "amount", "known_in_advance"]],
                         sch[["day_i", "category", "amount", "known_in_advance"]]], ignore_index=True)
        out["firm_id"] = firm["firm_id"]
        return out

    # ---------------- run
    def run(self, out_dir: Path | None = None, verbose=True):
        cfg, C = self.cfg, self.cal
        out_dir = Path(out_dir or (SYNTH / cfg.name))
        out_dir.mkdir(parents=True, exist_ok=True)
        macro = self.macro()
        firms, custs, invs, pays_all, banks, proms, outs, events = [], [], [], [], [], [], [], []
        for f in range(cfg.n_firms):
            firm = self.make_firm(f)
            cust = self.make_customers(firm)
            L, default_w, sec = self.customer_paths(firm, cust)
            inv = self.make_invoices(firm, cust)
            yrs = pd.DatetimeIndex(C.date(inv["issue_i"].values)).year
            sym = {y: nm.einvoice_symbol(y, self.rng) for y in sorted(set(yrs))}
            inv["symbol"] = [sym[y] for y in yrs]
            inv["invoice_no"] = (inv.groupby("symbol").cumcount() + 1).map(lambda x: f"{x:08d}")
            inv, pays = self.settle(firm, cust, inv, L, default_w, sec)
            bank, pays = self.bank_ledger(firm, cust, inv, pays)
            prom = self.promises(firm, cust, inv, pays)
            out = self.outflows(firm, inv)
            fid = firm["firm_id"]
            inv["firm_id"] = fid
            inv["invoice_id"] = fid + "-" + inv["symbol"] + "-" + inv["invoice_no"]
            inv["customer_id"] = cust["customer_id"].values[inv["ci"].values]
            pays["invoice_id"] = inv["invoice_id"].values[pays["k"].values]
            pays["ledger_invoice_id"] = inv["invoice_id"].values[pays["ledger_k"].values]
            if len(prom):
                prom["invoice_id"] = inv["invoice_id"].values[prom["invoice_k"].values]
                prom["customer_id"] = inv["customer_id"].values[prom["invoice_k"].values]
                prom["firm_id"] = fid
                proms.append(prom)
            cust["default_week"] = default_w
            cust["default_date"] = [self.weeks[w] + pd.Timedelta(days=3) if w >= 0 else pd.NaT for w in default_w]
            for _, c in cust[cust["break_day"] >= 0].iterrows():
                events.append(dict(firm_id=fid, customer_id=c["customer_id"], type="customer_delay_shift",
                                   date=self.start + pd.Timedelta(days=int(c["break_day"])), magnitude=c["break_shift"]))
            for _, c in cust[cust["default_week"] >= 0].iterrows():
                events.append(dict(firm_id=fid, customer_id=c["customer_id"], type="customer_default",
                                   date=c["default_date"], magnitude=np.nan))
            firm.pop("weekly_revenue_plan")
            firms.append(firm)
            custs.append(cust)
            invs.append(inv)
            pays_all.append(pays)
            banks.append(bank)
            outs.append(out)
            if verbose:
                print(f"  {fid} {firm['industry']:<17} cust={len(cust):4d} inv={len(inv):6d} "
                      f"bad={inv['is_bad_debt'].mean():.3f} posting={firm['posting_mode']}", flush=True)
        firms = pd.DataFrame(firms)
        firms["payday"] = firms["payday"].astype(str)
        cust = pd.concat(custs, ignore_index=True)
        inv = pd.concat(invs, ignore_index=True)
        pays = pd.concat(pays_all, ignore_index=True)
        bank = pd.concat(banks, ignore_index=True)
        prom = pd.concat(proms, ignore_index=True) if proms else pd.DataFrame()
        out = pd.concat(outs, ignore_index=True)

        def D(i):
            i = np.asarray(i, dtype=np.int64)
            res = pd.to_datetime(C.date(np.clip(i, 0, C.n - 1)))
            return pd.Series(res).where(i >= 0).values

        fin = pays[pays["kind"].isin(["full", "final"])]
        settle = fin.groupby("invoice_id")["day_i"].max()
        led = fin.groupby("ledger_invoice_id")["post_i"].max()
        first = pays.groupby("invoice_id")["day_i"].min()
        paid_amt = pays.groupby("invoice_id")["amount"].sum()
        npay = pays.groupby("invoice_id").size()
        ids = inv["invoice_id"]
        I = pd.DataFrame({
            "invoice_id": ids, "firm_id": inv["firm_id"], "customer_id": inv["customer_id"],
            "symbol": inv["symbol"], "invoice_no": inv["invoice_no"],
            "issue_date": D(inv["issue_i"]), "due_date": D(inv["due_i"]), "term_days": inv["term_days"].values,
            "amount_net": inv["net"].values, "vat_rate": inv["vat_rate"].values, "amount_gross": inv["amount_gross"].values,
            "credit_note": inv["credit_note"].values, "currency": "VND", "dispute": inv["dispute"].values,
            "partial": inv["partial"].values, "is_bad_debt": inv["is_bad_debt"].values,
            "writeoff_date": D(inv["writeoff_i"]), "ultra_late": inv["ultra_late"].values,
            "liquidity_at_due": inv["liquidity_at_due"].values, "stress_at_due": inv["stress_at_due"].values,
        })
        I["paid_date_true"] = D(settle.reindex(ids).fillna(-1).astype(np.int64).values)
        I["first_payment_date"] = D(first.reindex(ids).fillna(-1).astype(np.int64).values)
        I["ledger_clear_date"] = D(led.reindex(ids).fillna(-1).astype(np.int64).values)
        I["paid_amount"] = paid_amt.reindex(ids).fillna(0).values
        I["n_payments"] = npay.reindex(ids).fillna(0).astype(int).values
        I["days_late_true"] = (I["paid_date_true"] - I["due_date"]).dt.days
        P = pd.DataFrame({"payment_id": [f"P{i:08d}" for i in range(len(pays))], "firm_id": pays["invoice_id"].str[:4],
                          "invoice_id": pays["invoice_id"], "ledger_invoice_id": pays["ledger_invoice_id"],
                          "txn_id": pays["txn_id"], "pay_date_true": D(pays["day_i"]),
                          "ledger_post_date": D(pays["post_i"]), "amount": pays["amount"].values,
                          "kind": pays["kind"].values})
        if len(prom):
            prom = pd.DataFrame({"firm_id": prom["firm_id"], "invoice_id": prom["invoice_id"],
                                 "customer_id": prom["customer_id"], "made_date": D(prom["made_i"]),
                                 "promised_date": D(prom["promised_i"]), "kept": prom["kept"].values})
        out["date"] = D(out["day_i"])
        out = out.drop(columns="day_i")
        daily = self.cash_paths(firms, bank, out)
        I.to_parquet(out_dir / "invoices.parquet", index=False)
        P.to_parquet(out_dir / "payments.parquet", index=False)
        bank.to_parquet(out_dir / "bank_txns.parquet", index=False)
        if not len(prom):
            prom = pd.DataFrame({'firm_id': pd.Series(dtype='str'), 'invoice_id': pd.Series(dtype='str'),
                                 'customer_id': pd.Series(dtype='str'), 'made_date': pd.Series(dtype='datetime64[ns]'),
                                 'promised_date': pd.Series(dtype='datetime64[ns]'), 'kept': pd.Series(dtype='bool')})
        prom.to_parquet(out_dir / "promises.parquet", index=False)
        out.to_parquet(out_dir / "outflows.parquet", index=False)
        firms.to_parquet(out_dir / "firms.parquet", index=False)
        cust.to_parquet(out_dir / "customers.parquet", index=False)
        event_table = pd.DataFrame(events, columns=['firm_id', 'customer_id', 'type', 'date', 'magnitude'])
        event_table['date'] = pd.to_datetime(event_table['date'])
        event_table.to_parquet(out_dir / "events.parquet", index=False)
        macro.to_parquet(out_dir / "macro.parquet", index=False)
        daily.to_parquet(out_dir / "daily_cash.parquet", index=False)
        from ..data.contracts import validate_world
        validate_world(out_dir)
        (out_dir / "config.json").write_text(json.dumps(asdict(cfg), indent=2, default=str), encoding="utf-8")
        if cfg.write_xml:
            from .einvoice import write_xml_samples
            write_xml_samples(I.head(cfg.write_xml), firms, cust, out_dir / "einvoice_xml")
        if verbose:
            print(f"[{cfg.name}] firms={len(firms)} invoices={len(I)} payments={len(P)} bank={len(bank)} "
                  f"promises={len(prom)} outflows={len(out)} -> {out_dir}", flush=True)
        return out_dir

    def cash_paths(self, firms, bank, out):
        rows = []
        days = pd.date_range(self.start, self.end)
        for _, f in firms.iterrows():
            fid = f["firm_id"]
            b = bank[bank["firm_id"] == fid]
            inflow = b[b["txn_type"] == "customer_payment"].groupby("value_date")["amount"].sum().reindex(days, fill_value=0.0)
            other = b[b["txn_type"].isin(["interest", "refund"])].groupby("value_date")["amount"].sum().reindex(days, fill_value=0.0)
            o = out[out["firm_id"] == fid].groupby("date")["amount"].sum().reindex(days, fill_value=0.0)
            daily_out = o.mean()
            opening = f["buffer_days"] * daily_out
            cap = max(self.cfg.cash_cap_days, f["buffer_days"] * 1.5) * daily_out
            net = (inflow + other - o).values
            draw = np.zeros(len(days))
            bal = np.empty(len(days))
            b = opening
            qend = set(pd.date_range(self.start, self.end, freq="QE").normalize())
            for i, d in enumerate(days):
                b += net[i]
                if d in qend and b > cap:      # chủ DN rút lợi nhuận về mức đệm mục tiêu
                    draw[i] = b - f["buffer_days"] * daily_out
                    b -= draw[i]
                bal[i] = b
            rows.append(pd.DataFrame({"firm_id": fid, "date": days, "inflow_ar": inflow.values, "inflow_other": other.values,
                                      "outflow": o.values, "owner_draw": draw, "balance": bal,
                                      "opening_balance": opening}))
        return pd.concat(rows, ignore_index=True)


def generate(cfg: WorldConfig, verbose=True):
    return World(cfg).run(verbose=verbose)
