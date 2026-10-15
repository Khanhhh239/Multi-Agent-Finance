"""World v4: process-based SME world with case-based internal fraud (see DATA_V4.md).

Changes against v3 (answers to the review in the user's message of 2026-10-14):
* 48 companies by default, each with its own drawn policies (domain randomisation): size, industry, pay calendar,
  vendor/customer payment terms, customer payment behaviour, document habits, self-approval limit, cash intensity.
* Background is generated from business processes instead of independent random rows: monthly payroll for every
  active employee on the company's pay day(s); rent, VAT and depreciation on fixed days; sales invoices linked to
  customer receipts through `applied_invoice_id` with delays calibrated to Atradius Vietnam 2025 (58 percent on time,
  39 percent late, about 3 percent never); purchases paid after vendor terms on the company's payment-run weekday;
  employees leave and are replaced; petty-cash withdrawals; legitimate returns, write-offs and bonus runs.
* Fraud is injected as *cases* (perpetrator, level, collusion, concealment, start/end inside one split) over ~30
  schemes mapped to the ACFE fraud tree and to Vietnamese court/news cases; a truth table `truth_cases.csv`.
* Only filler rows are replaced by fraud rows; structured rows are mutated in place when the scheme alters a real
  business record (lapping, padded payroll), so linked processes are never silently broken.
* Fixes: every generated time is clamped and asserted inside its split; schemes that cannot be placed raise
  instead of silently consuming budget.
"""
from __future__ import annotations

import calendar
import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from sme_fraud.generate import HOLIDAYS, TZ, WINDOWS, parse, save_dataset, stamp

from . import accounting_ext  # noqa: F401  (installs templates for the new kinds)
from .accounting_ext import MONEY_KINDS, NEW_KINDS
from .world_v3 import CITIES, WorldV3, company_name
from .world_v4_schemes import SchemesMixin

START, END = WINDOWS["train"][0], WINDOWS["test"][1]
INDUSTRIES = (("trading", .30), ("retail", .20), ("manufacturing", .20), ("services", .20), ("logistics", .10))
ROW_DEFAULTS = dict(applied_invoice_id="", payer_account="", collector_id="")
TRUTH_EXTRA = dict(scheme_group="", perpetrator_level="", collusion="", concealment="")
SALARY_M = {"director": (25, 60), "chief_accountant": (15, 30), "cashier": (8, 12), "accountant": (9, 16), "sales": (7, 15),
            "purchasing": (9, 15), "warehouse": (7, 11), "operations": (6.5, 11), "hr": (9, 14)}
DEPARTMENT = {"director": "office", "chief_accountant": "office", "cashier": "office", "accountant": "office", "sales": "sales",
              "purchasing": "office", "warehouse": "warehouse", "operations": "operations", "hr": "office"}
FILLER_KINDS = (("vendor_payment", 30), ("stock_purchase", 14), ("material_purchase", 7), ("cash_expense", 14),
                ("selling_expense", 8), ("tools_purchase", 3), ("equipment_purchase", 1), ("adjustment", 3))


def split_of(at):
    for name, (a, b) in WINDOWS.items():
        if a <= at < b:
            return name
    raise ValueError(f"time outside simulation window: {at}")


def months():
    y, m = START.year, START.month
    while datetime(y, m, 1, tzinfo=TZ) < END:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def working_day(at, backward=True):
    step = timedelta(days=-1 if backward else 1)
    while at.weekday() >= 5 or at.date().isoformat() in HOLIDAYS:
        at += step
    return at


def poisson(rng, lam):
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


class WorldV4(SchemesMixin, WorldV3):
    def __init__(self, n=200_000, rate=.004, seed=1, companies=48, fraud_company_share=.55,
                 difficulty_weights=(.15, .45, .40), structured_share=.86):
        self.fraud_company_share, self.structured_share = fraud_company_share, structured_share
        self.profile, self.cases, self.vcat = {}, [], {}
        self.customer_prof, self.receipts, self.sales = {}, [], []
        self.payroll_rows = defaultdict(list)
        self.filler = set()
        super().__init__(n, rate, seed, companies, difficulty_weights)

    # ------------------------------------------------------------------ masters
    def employee(self, cid, at, role="operations", mode="onsite", bank=None, attendance=None, append_to_background=True):
        e = super().employee(cid, at, role if role in ("director", "chief_accountant", "accountant") else "operations",
                             mode, bank, attendance, append_to_background)
        prof = self.profile.get(cid)
        lo, hi = SALARY_M.get(role, SALARY_M["operations"])
        scale = (prof["scale"] if prof else 1.0) ** .3
        e.update(role=role, department=DEPARTMENT.get(role, "operations"),
                 monthly_salary_vnd=int(round(self.rng.uniform(lo, hi) * scale * 10)) * 100_000,
                 terminated_at="", termination_recorded_at="")
        if prof and role != "director":
            e["self_approval_limit_vnd"] = prof["self_limit"]
        return e

    def make_masters(self, count):
        rng = self.rng
        initial = datetime(2023, 1, 1, tzinfo=TZ)
        for i in range(count):
            cid = f"C{i+1:03}"
            industry = rng.choices([x for x, _ in INDUSTRIES], [w for _, w in INDUSTRIES])[0]
            size = rng.choices(["micro", "small", "medium"], [.40, .45, .15])[0]
            n_staff = {"micro": rng.randint(10, 19), "small": rng.randint(20, 45), "medium": rng.randint(46, 80)}[size]
            scale = math.exp(rng.gauss(0, .45)) * {"micro": .6, "small": 1.0, "medium": 1.8}[size]
            on_time = rng.uniform(.45, .72)
            bad = rng.uniform(.01, .05)
            prof = dict(industry=industry, size=size, scale=scale, n_staff=n_staff,
                        pay_days=rng.choice([[5], [10], [10], [15], [25], ["last"], ["last"], [15, "last"]]),
                        run_weekday=rng.choice([None, 0, 1, 2, 3, 3, 4]), vendor_terms=rng.choice([15, 30, 30, 45, 60]),
                        customer_terms=rng.choice([30, 30, 45, 45, 60]), on_time=on_time, bad=bad,
                        doc_mean=rng.uniform(1.3, 3.0), self_limit=rng.choice([1, 2, 2, 3, 5]) * 1_000_000,
                        cash_heavy=industry in ("retail", "services") and rng.random() < .7,
                        rent_day=rng.randint(1, 10), tax_day=rng.randint(15, 20),
                        fraud_mu=0.0 if rng.random() > self.fraud_company_share else rng.uniform(1.0, 4.0))
            self.profile[cid] = prof
            self.company_scale[cid] = scale
            self.tables["companies"].append(dict(
                company_id=cid, name=f"SME tổng hợp {i+1}", industry=industry, city=CITIES[i % len(CITIES)],
                amount_scale=round(scale, 3), saturday_operations=int(rng.random() < .7), currency="VND", timezone="Asia/Ho_Chi_Minh",
                size_class=size, pay_days="|".join(map(str, prof["pay_days"])), vendor_terms_days=prof["vendor_terms"],
                customer_terms_days=prof["customer_terms"], self_approval_limit_vnd=prof["self_limit"]))
            self.company_staff[cid], self.company_vendors[cid], self.company_customers[cid] = [], [], []
            roles = ["director", "chief_accountant", "cashier", "accountant", "accountant", "accountant", "sales", "purchasing", "warehouse"]
            roles += [rng.choices(["sales", "purchasing", "warehouse", "operations", "hr"], [.28, .08, .12, .49, .03])[0]
                      for _ in range(n_staff - len(roles))]
            for j, role in enumerate(roles):
                hired = initial if j < 6 else datetime(2018, 1, 1, tzinfo=TZ) + timedelta(days=rng.randrange(0, 5 * 365))
                self.employee(cid, hired, role, "remote" if j % 13 == 12 else "onsite")
            self.plan_turnover(cid)
            self.make_vendors(cid, n_staff, scale, initial)
            self.make_customers(cid, industry, initial)
        self.tables["calendar"] = [dict(date=d, is_holiday=1, source="illustrative_simulation_calendar") for d in sorted(HOLIDAYS)]

    def plan_turnover(self, cid):
        rng = self.rng
        for eid in list(self.company_staff[cid][9:]):
            if rng.random() < .18:
                e = self.employees[eid]
                left = working_day(datetime(2024, 2, 1, 17, tzinfo=TZ) + timedelta(days=rng.randrange(0, 640)))
                e["terminated_at"] = stamp(left)
                e["termination_recorded_at"] = stamp(left + timedelta(days=rng.randint(0, 10)))
                for a in self.tables["attendance"]:
                    if a["employee_id"] == eid and a["observed_at"] > e["terminated_at"]:
                        a["days_worked_observed"] = 0
                hire = working_day(left + timedelta(days=rng.randint(7, 40)), backward=False).replace(hour=9)
                if hire < END - timedelta(days=40):
                    self.employee(cid, hire, e["role"])

    def make_vendors(self, cid, n_staff, scale, initial):
        rng = self.rng
        n_vendors = int(n_staff * rng.uniform(1.5, 3.5)) + 20
        office = self.identifier("ADDRESS_SYN_")
        base = 8_000_000 * scale
        for j in range(n_vendors):
            onboard = (datetime(2018, 1, 1, tzinfo=TZ) + timedelta(days=rng.randrange(0, 5 * 365))) if rng.random() < .55 \
                else (initial + timedelta(days=rng.randrange(0, 33 * 30)))
            if j == 0:
                onboard = initial - timedelta(days=400)
            e = self.employees[self.company_staff[cid][j % n_staff]]
            v = self.vendor(cid, onboard, address=office if 0 < j < 4 else None, phone=e["phone"] if j in (5, 6) else None, disclosed=j in (5, 6))
            v["name"] = company_name(rng)
            self.vcat[v["vendor_id"]] = "landlord" if j == 0 else rng.choices(
                ["goods", "materials", "services", "utilities", "retail"], [.40, .20, .25, .05, .10])[0]
            prof = dict(mu=math.log(base) + rng.gauss(0, .9), sigma=rng.uniform(.18, .35), weight=1.0 / (1 + j) ** .9 * rng.uniform(.6, 1.4),
                        step_at=None, step=1.0, price=rng.lognormvariate(math.log(250_000), 1.0))
            if rng.random() < .12:
                prof.update(step_at=datetime(2024, 9, 1, tzinfo=TZ) + timedelta(days=rng.randrange(0, 330)), step=rng.uniform(1.15, 1.30))
            self.vprof[v["vendor_id"]] = prof
        vids = self.company_vendors[cid]
        for _ in range(max(1, n_vendors // 25)):
            a, b = rng.sample(vids[1:], 2)
            self.vendors[b]["name"] = self.vendors[a]["name"] + f" - Chi nhánh {rng.choice(CITIES)}"
        self.rent_vendor[cid] = (vids[0], rng.choice([5, 8, 10, 15, 20, 30, 45]) * 1_000_000)

    def make_customers(self, cid, industry, initial):
        rng = self.rng
        prof = self.profile[cid]
        sales_staff = [e for e in self.company_staff[cid] if self.employees[e]["role"] == "sales"
                       and parse(self.employees[e]["hired_at"]) <= START and not self.employees[e]["terminated_at"]]
        n = rng.randint(8, 20) if industry == "retail" else rng.randint(15, 45)
        for j in range(n):
            behavior = rng.choices(["good", "late", "bad"], [prof["on_time"], 1 - prof["on_time"] - prof["bad"], prof["bad"]])[0]
            cu = dict(customer_id=self.identifier("CU"), company_id=cid, name=f"Khách hàng {company_name(rng)[9:]}",
                      tax_code=self.identifier("MST_SYN_"), bank_account=self.identifier("BANK_SYN_"), recorded_at=stamp(initial),
                      credit_terms_days=prof["customer_terms"])
            self.customers[cu["customer_id"]] = cu
            self.company_customers[cid].append(cu["customer_id"])
            self.tables["customers"].append(cu)
            self.customer_prof[cu["customer_id"]] = dict(
                behavior=behavior, weight=1.0 / (1 + j) ** .8, mu=math.log(15_000_000 * prof["scale"]) + rng.gauss(0, .7),
                manager=rng.choice(sales_staff), affiliate=None)
        cus = self.company_customers[cid]
        for _ in range(max(1, len(cus) // 12)):
            a, b = rng.sample(cus, 2)
            self.customer_prof[b]["affiliate"] = a

    # ------------------------------------------------------------------ helpers
    def active(self, e, at):
        return parse(e["hired_at"]) <= at and (not e["terminated_at"] or at < parse(e["terminated_at"]))

    def staff_with(self, cid, *roles, at=None):
        out = [x for x in self.company_staff[cid] if self.employees[x]["role"] in roles]
        if at is not None:
            out = [x for x in out if self.active(self.employees[x], at)]
        return out

    def day_time(self, at, odd=False):
        if odd:
            return at.replace(hour=self.rng.choice([20, 21, 22, 23, 6]), minute=self.rng.randrange(60), second=self.rng.randrange(60))
        return at.replace(hour=self.rng.randint(8, 17), minute=self.rng.randrange(60), second=self.rng.randrange(60))

    def random_day(self, y, m):
        last = calendar.monthrange(y, m)[1]
        while True:
            d = datetime(y, m, self.rng.randint(1, last), tzinfo=TZ)
            if d.weekday() >= 5 and self.rng.random() > .25:
                continue
            if self.rng.random() < self.day_weight(d.date()) / self.MAX_WEIGHT:
                return self.day_time(d)

    def clamp(self, at, split):
        a, b = WINDOWS[split]
        return min(max(at, a + timedelta(hours=1)), b - timedelta(hours=2))

    EMPLOYEE_KINDS = ("payroll", "advance_issue", "advance_settlement", "advance_writeoff", "advance_review")

    def transaction(self, cid, split, at=None, kind=None, vendor=None, employee=None, amount=None, creator=None,
                    approver=None, delay_hours=None, price_markup=1.0):
        at = at or self.random_time(split)
        if kind is None:
            from sme_fraud.generate import NORMAL_TYPES, NORMAL_WEIGHTS
            kind = self.rng.choices(NORMAL_TYPES, NORMAL_WEIGHTS)[0]
        if employee is None and kind in self.EMPLOYEE_KINDS:
            pool = [x for x in self.company_staff[cid] if self.active(self.employees[x], at)]
            employee = self.employees[self.rng.choice(pool)]
        row = super().transaction(cid, split, at, kind, vendor, employee, amount, creator, approver, delay_hours, price_markup)
        for k, v in ROW_DEFAULTS.items():
            row.setdefault(k, v)
        return row

    def new_kind_row(self, cid, at, kind, amount, creator, approver, customer_id="", recipient="", purpose="", docs=None):
        split = split_of(at)
        r = self.transaction(cid, split, at, "cash_expense", amount=amount, creator=creator, approver=approver, delay_hours=self.rng.uniform(.2, 30))
        debit, credit = NEW_KINDS[kind]
        r.update(txn_type=kind, debit_account=debit, credit_account=credit, vendor_id="", customer_id=customer_id, employee_id="",
                 recipient_account=recipient if kind in MONEY_KINDS and kind != "cash_withdrawal" else "",
                 payment_channel="bank" if kind in MONEY_KINDS else "journal", business_purpose=purpose or kind,
                 invoice_id="", invoice_number="", invoice_issued_at="", invoice_gross_vnd=0, goods_receipt_verified=0,
                 unit_price_vnd="", quantity="")
        if approver:
            r["approver_id"] = approver
        if docs is not None:
            r["support_doc_count"] = docs
        return r

    def emit(self, row, filler=False, hard=""):
        i = len(self.rows)
        self.rows.append(row)
        self.truth.append(dict(transaction_id="", is_fraud=0, fraud_type="", variant="", case_id="", case_role="hard_negative" if hard else "background",
                               hard_negative_type=hard, difficulty="", observability="", **TRUTH_EXTRA))
        if filler:
            self.filler.add(i)
        return i

    # ------------------------------------------------------------------ background processes
    def make_background(self):
        rng = self.rng
        weights = {c: self.profile[c]["n_staff"] * self.profile[c]["scale"] ** .5 for c in self.company_staff}
        deterministic = sum(len(self.company_staff[c]) * 24 * len(self.profile[c]["pay_days"]) * .93 + 24 * 3 for c in weights)
        stochastic = max(0.0, self.structured_share * self.n - deterministic)
        total_w = sum(weights.values())
        for cid in self.company_staff:
            self.company_processes(cid, stochastic * weights[cid] / total_w / 24)
        need = self.n - len(self.rows)
        if need < .08 * self.n:
            raise ValueError(f"structured rows {len(self.rows)} leave only {need} filler rows; lower volumes")
        kinds, kw = zip(*FILLER_KINDS)
        cids, cw = zip(*weights.items())
        for _ in range(need):
            cid = rng.choices(cids, cw)[0]
            split = rng.choices(list(WINDOWS), [.5, .25, .25])[0]
            r = self.transaction(cid, split, kind=rng.choices(kinds, kw)[0])
            hidden = r.pop("_hn", "")
            self.emit(r, filler=True, hard=hidden)
        ids = list(range(1, len(self.rows) + 1))
        rng.shuffle(ids)
        self.pools = {s: [] for s in WINDOWS}
        for i, r in enumerate(self.rows):
            r["transaction_id"] = f"T{ids[i]:09d}"
            self.truth[i]["transaction_id"] = r["transaction_id"]
            hidden = r.pop("_hn", "")
            if hidden and not self.truth[i]["hard_negative_type"]:
                self.truth[i].update(hard_negative_type=hidden, case_role="hard_negative")
            if i in self.filler:
                self.pools[split_of(parse(r["posted_at"]))].append(i)
            if r["txn_type"] == "payroll" and self.truth[i]["case_role"] == "background":
                self.payroll_index[(r["employee_id"], r["payroll_period"])] = i
        for pool in self.pools.values():
            rng.shuffle(pool)

    def company_processes(self, cid, per_month):
        rng, prof = self.rng, self.profile[cid]
        retail_like = prof["industry"] in ("trading", "retail")
        rows_per_sale = 1.0 + .97 + (1.0 if retail_like else 0.0)
        share = dict(sales=.30, purchase=.30, accrual=.12, cash=.16, selling=.07)
        lam_sales = per_month * share["sales"] / rows_per_sale * (1.3 if retail_like else 1.0)
        payroll_staff = self.staff_with(cid, "chief_accountant", "accountant")
        director, chief, cashier = self.company_staff[cid][0], self.company_staff[cid][1], self.company_staff[cid][2]
        accountants = self.company_staff[cid][3:6]
        for y, m in months():
            last = calendar.monthrange(y, m)[1]
            for pd in prof["pay_days"]:
                day = last if pd == "last" else pd
                at = working_day(datetime(y, m, day, rng.randint(9, 16), rng.randrange(60), tzinfo=TZ))
                if not (START <= at < END):
                    continue
                for eid in list(self.company_staff[cid]):
                    e = self.employees[eid]
                    if not self.active(e, at):
                        continue
                    salary = e["monthly_salary_vnd"] * (1.0 if y == 2024 else 1 + (int(eid[1:]) % 9) / 100)
                    amount = salary / len(prof["pay_days"])
                    if e["role"] in ("operations", "warehouse") and rng.random() < .3:
                        amount *= 1 + rng.uniform(0, .15)
                    r = self.transaction(cid, split_of(at), at, "payroll", employee=e, creator=rng.choice(payroll_staff),
                                         approver=director, delay_hours=rng.uniform(1, 48))
                    r["amount_vnd"] = int(round(amount / 1000)) * 1000
                    r["support_doc_count"] = rng.choice([2, 3, 3, 4])
                    self.payroll_rows[(cid, eid)].append(self.emit(r))
            for eid in self.company_staff[cid]:
                e = self.employees[eid]
                if e["terminated_at"] and parse(e["terminated_at"]).year == y and parse(e["terminated_at"]).month == m:
                    at = working_day(parse(e["terminated_at"]) + timedelta(days=rng.randint(10, 28)))
                    if at < END:
                        r = self.transaction(cid, split_of(at), self.day_time(at), "payroll", employee=e, creator=chief, approver=director)
                        r["amount_vnd"] = int(e["monthly_salary_vnd"] * rng.uniform(.4, 1.3) / 1000) * 1000
                        r["support_doc_count"] = rng.choice([3, 4])
                        self.emit(r, hard="legit_final_settlement")
            for kind, day in (("rent", prof["rent_day"]), ("tax_payment", prof["tax_day"]), ("depreciation", last)):
                at = working_day(datetime(y, m, day, rng.randint(9, 16), rng.randrange(60), tzinfo=TZ))
                if START <= at < END:
                    amount = None if kind == "rent" else int(max(.3, rng.gauss(1, .15)) * (6_000_000 if kind == "tax_payment" else 3_000_000) * prof["scale"] / 1000) * 1000
                    self.emit(self.transaction(cid, split_of(at), at, kind, amount=amount, creator=rng.choice(accountants), approver=chief))
            self.month_sales(cid, y, m, poisson(rng, lam_sales), retail_like, accountants, chief)
            self.month_purchases(cid, y, m, poisson(rng, per_month * share["purchase"]), accountants, chief, director)
            for kind, lam in (("stock_purchase", per_month * share["accrual"] * .7), ("material_purchase", per_month * share["accrual"] * .3),
                              ("selling_expense", per_month * share["selling"])):
                for _ in range(poisson(rng, lam)):
                    at = self.random_day(y, m)
                    self.emit(self.transaction(cid, split_of(at), at, kind, creator=rng.choice(accountants)))
            self.month_cash(cid, y, m, poisson(rng, per_month * share["cash"]), accountants, cashier, chief)
            if prof["industry"] in ("trading", "retail", "manufacturing") and m in (3, 6, 9, 12):
                at = working_day(datetime(y, m, last, 16, tzinfo=TZ))
                if START <= at < END:
                    wh = self.staff_with(cid, "warehouse", at=at) or [chief]
                    r = self.new_kind_row(cid, at, "inventory_writeoff", int(rng.uniform(.5, 4) * 1_000_000 * prof["scale"] / 1000) * 1000,
                                          rng.choice(wh), director, purpose="Hao hụt kiểm kê định kỳ có biên bản", docs=rng.choice([3, 4]))
                    self.emit(r, hard="legit_inventory_writeoff")
            if m in (1, 12) and rng.random() < .5:
                self.bonus_run(cid, y, m, chief, director)

    def month_sales(self, cid, y, m, count, retail_like, accountants, chief):
        rng, prof = self.rng, self.profile[cid]
        cus = self.company_customers[cid]
        w = [self.customer_prof[c]["weight"] for c in cus]
        for _ in range(count):
            at = self.random_day(y, m)
            cu = rng.choices(cus, w)[0]
            cp = self.customer_prof[cu]
            gross = max(100_000, int(rng.lognormvariate(cp["mu"], .5) / 1000) * 1000)
            creator = cp["manager"] if rng.random() < .6 else rng.choice(accountants)
            r = self.transaction(cid, split_of(at), at, "sales_invoice", amount=gross, creator=creator)
            inv = self.identifier("I")
            r.update(customer_id=cu, recipient_account=self.customers[cu]["bank_account"], invoice_id=inv,
                     invoice_number=f"HDB{rng.randrange(1, 10**7):07d}", invoice_issued_at=r["posted_at"], invoice_gross_vnd=gross)
            si = self.emit(r)
            sale = dict(cid=cid, row=si, customer=cu, invoice_id=inv, gross=gross, at=at, due=at + timedelta(days=prof["customer_terms"]),
                        receipt=None, manager=cp["manager"])
            self.sales.append(sale)
            if retail_like:
                c = self.transaction(cid, split_of(at), at, "cogs", amount=max(50_000, int(gross / 1.1 * rng.uniform(.7, .85) / 1000) * 1000),
                                     creator=rng.choice(accountants))
                self.emit(c)
            if rng.random() < .02:
                ret_at = at + timedelta(days=rng.randint(3, 20))
                if ret_at < END:
                    rr = self.new_kind_row(cid, self.day_time(ret_at), "sales_return", max(50_000, int(gross * rng.uniform(.05, .4) / 1000) * 1000),
                                           creator, chief, customer_id=cu, purpose="Hàng bán bị trả lại có biên bản", docs=rng.choice([2, 3, 4]))
                    self.emit(rr, hard="legit_sales_return")
            behavior = cp["behavior"]
            if behavior == "bad" or rng.random() < .01:
                self.maybe_bad_debt(sale, chief)
                continue
            pay_at = sale["due"] - timedelta(days=rng.randint(0, 10)) if behavior == "good" else sale["due"] + timedelta(days=rng.randint(5, 60))
            pay_at = working_day(self.day_time(max(pay_at, at + timedelta(days=1))), backward=False)
            if pay_at >= END:
                continue
            payer, hard = cu, ""
            if cp["affiliate"] and rng.random() < .3:
                payer, hard = cp["affiliate"], "legit_affiliate_payment"
            rc = self.transaction(cid, split_of(pay_at), pay_at, "customer_receipt", amount=gross, creator=rng.choice(accountants))
            rc.update(customer_id=cu, recipient_account=self.customers[cu]["bank_account"], applied_invoice_id=inv,
                      payer_account=self.customers[payer]["bank_account"], collector_id=sale["manager"],
                      support_doc_count=rng.choice([1, 1, 2]))
            sale["receipt"] = self.emit(rc, hard=hard)
            self.receipts.append(sale)

    def maybe_bad_debt(self, sale, chief):
        at = working_day(sale["due"] + timedelta(days=self.rng.randint(180, 260)))
        if at < END:
            r = self.new_kind_row(sale["cid"], self.day_time(at), "bad_debt_writeoff", sale["gross"], chief, self.company_staff[sale["cid"]][0],
                                  customer_id=sale["customer"], purpose="Xóa nợ khó đòi có hồ sơ đối chiếu", docs=self.rng.choice([3, 4]))
            self.emit(r, hard="legit_bad_debt_writeoff")

    def month_purchases(self, cid, y, m, count, accountants, chief, director):
        rng, prof = self.rng, self.profile[cid]
        for _ in range(count):
            inv_at = self.random_day(y, m)
            pay_at = inv_at + timedelta(days=prof["vendor_terms"] + rng.randint(-5, 10))
            if prof["run_weekday"] is not None:
                pay_at += timedelta(days=(prof["run_weekday"] - pay_at.weekday()) % 7)
            pay_at = working_day(self.day_time(pay_at), backward=False)
            if pay_at >= END:
                continue
            v = self.pick_vendor(cid, inv_at)
            if self.vcat.get(v["vendor_id"]) in ("landlord", "retail"):
                continue
            amount = max(25_000, int(self.vendor_amount(v, inv_at) / 1000) * 1000)
            r = self.transaction(cid, split_of(pay_at), pay_at, "vendor_payment", vendor=v, amount=amount,
                                 creator=rng.choice(accountants), approver=chief if amount <= 50_000_000 else director)
            r.update(invoice_issued_at=stamp(inv_at), invoice_gross_vnd=amount)
            self.emit(r)

    def month_cash(self, cid, y, m, count, accountants, cashier, chief):
        rng, prof = self.rng, self.profile[cid]
        spent = 0
        for _ in range(count):
            at = self.random_day(y, m)
            amount = max(20_000, int(rng.lognormvariate(math.log(600_000 * prof["scale"] ** .3), .8) / 1000) * 1000)
            creator = rng.choice(accountants + [cashier])
            approver = creator if amount <= prof["self_limit"] and rng.random() < .4 else chief
            r = self.transaction(cid, split_of(at), at, "cash_expense", amount=amount, creator=creator, approver=approver)
            r["support_doc_count"] = min(4, max(0, int(round(rng.gauss(prof["doc_mean"], 1)))))
            self.emit(r)
            spent += amount
        if prof["cash_heavy"] or spent > 5_000_000:
            for half in (8, 22):
                at = working_day(datetime(y, m, half, 10, tzinfo=TZ))
                if START <= at < END:
                    amt = max(5_000_000, int(round(spent / 2 / 5_000_000 + .5)) * 5_000_000)
                    self.emit(self.new_kind_row(cid, at, "cash_withdrawal", amt, cashier, chief, purpose="Rút tiền về quỹ", docs=1))

    def bonus_run(self, cid, y, m, chief, director):
        rng = self.rng
        day = working_day(datetime(y, m, 30 if m == 12 else 20, 15, tzinfo=TZ))
        if not (START <= day < END):
            return
        for eid in self.company_staff[cid]:
            e = self.employees[eid]
            if self.active(e, day) and e["role"] != "director":
                r = self.transaction(cid, split_of(day), self.day_time(day), "payroll", employee=e, creator=chief, approver=director)
                r["amount_vnd"] = int(e["monthly_salary_vnd"] * rng.uniform(.5, 1.5) / 100_000) * 100_000
                r["support_doc_count"] = rng.choice([2, 3])
                self.emit(r, hard="legit_bonus_run")

    # ------------------------------------------------------------------ placement primitives
    def put(self, split, row, family="", variant="", case="", hard="", support=False, observable="available", difficulty="", extra=None):
        at = parse(row["posted_at"])
        a, b = WINDOWS[split]
        assert a <= at < b, f"{family or hard or 'support'} row outside split {split}: {row['posted_at']}"
        assert parse(row["created_at"]) <= parse(row["approved_at"]) <= at, "created <= approved <= posted"
        for k, v in ROW_DEFAULTS.items():
            row.setdefault(k, v)
        while True:
            if not self.pools[split]:
                raise RuntimeError(f"filler pool exhausted in {split}")
            i = self.pools[split].pop()
            if i not in self.used:
                break
        self.used.add(i)
        hidden = row.pop("_hn", "")
        hard = hard or ("" if family or support else hidden)
        row["transaction_id"] = self.rows[i]["transaction_id"]
        self.rows[i] = row
        self.truth[i].update(is_fraud=int(bool(family)), fraud_type=family, variant=variant, case_id=case,
                             case_role="support" if support else "fraud" if family else "hard_negative" if hard else "background",
                             hard_negative_type=hard, difficulty=difficulty, observability=observable if family else "", **(extra or {}))
        return row["transaction_id"]

    def mutate(self, i, family="", variant="", case="", hard="", difficulty="", extra=None, **updates):
        self.rows[i].update(updates)
        self.used.add(i)
        at = parse(self.rows[i]["posted_at"])
        split_of(at)
        self.truth[i].update(is_fraud=int(bool(family)), fraud_type=family, variant=variant, case_id=case,
                             case_role="fraud" if family else "hard_negative", hard_negative_type=hard, difficulty=difficulty,
                             observability="available" if family else "", **(extra or {}))

    # friend's advance helpers, copied with one change: the employee must be on staff for the whole advance
    def advance(self, cid, split, at, creator, valid=True, mode="review", hard=""):
        issued = WINDOWS[split][0] + timedelta(days=self.rng.randint(4, 15), hours=10)
        pool = [x for x in self.company_staff[cid][6:] if self.active(self.employees[x], issued) and self.active(self.employees[x], at)]
        if not pool:
            pool = [x for x in self.company_staff[cid][3:6]]
        keep = self.company_staff[cid]
        self.company_staff[cid] = keep[:6] + pool
        try:
            super().advance(cid, split, at, creator, valid, mode, hard)
        finally:
            self.company_staff[cid] = keep

    def inject_normal_advances(self):
        rng = self.rng
        for split in WINDOWS:
            count = max(3, int(self.n * .006 * (.5 if split == "train" else .25)))
            for _ in range(count):
                cid, at, creator = self.context(split, 45)
                settle_at = at + timedelta(days=rng.randint(5, 40))
                pool = [x for x in self.company_staff[cid][6:] if self.active(self.employees[x], at) and self.active(self.employees[x], settle_at)]
                if not pool:
                    continue
                e = self.employees[rng.choice(pool)]
                aid, case = self.identifier("A"), self.identifier("CASE")
                amount = rng.choice([1, 2, 3, 5, 8, 10]) * 1_000_000
                issue = self.transaction(cid, split, at, "advance_issue", employee=e, amount=amount, creator=creator)
                issue["advance_id"] = aid
                tid = self.put(split, issue, case=case, support=True)
                self.tables["advances"].append(dict(advance_id=aid, company_id=cid, employee_id=e["employee_id"], issue_transaction_id=tid,
                    issued_at=stamp(at), recorded_at=stamp(at), original_due_at=stamp(at + timedelta(days=30)), original_amount_vnd=amount))
                r = self.transaction(cid, split, settle_at, "advance_settlement", employee=e, amount=amount, creator=creator)
                r["advance_id"] = aid
                tid = self.put(split, r, case=case, support=True)
                self.tables["advance_events"].append(dict(event_id=self.identifier("AE"), advance_id=aid, company_id=cid, event_type="settlement",
                    observed_at=stamp(settle_at), new_due_at="", amount_vnd=amount, transaction_id=tid, evidence_on_file=1))

    def context(self, split, margin=5):
        cid = self.rng.choice(list(self.company_staff))
        at = self.random_time(split, margin)
        creator = self.rng.choice(self.company_staff[cid][1:6])
        return cid, at, creator

    def finalize(self):
        tables = super().finalize()
        tables["truth_cases"] = self.cases
        return tables


def generate_v4(output, n=200_000, rate=.004, seed=1, companies=48):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty dataset: {output}")
    g = WorldV4(n, rate, seed, companies)
    tables = g.finalize()
    return save_dataset(output, tables, n, rate, seed, companies)


def main():
    import argparse
    import json
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--rows", type=int, default=200_000)
    p.add_argument("--fraud-rate", type=float, default=.004)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--companies", type=int, default=48)
    a = p.parse_args()
    m = generate_v4(a.output, a.rows, a.fraud_rate, a.seed, a.companies)
    print(json.dumps({"output": str(a.output), "fraud_rows": m["actual_fraud_rows"], "variants": len(m["fraud_variants"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
