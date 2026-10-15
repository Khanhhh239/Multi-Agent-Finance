"""World v3: a more realistic synthetic SME world on top of the friend's generator.

What it fixes in v2 (all verified by probing the v2 data, see AGENT2_WORKLOG.md):
* every background vendor was onboarded on 2023-01-01, so vendor tenure alone separated fraud;
* vendors were drawn uniformly, amounts ignored the vendor, no seasonality, no Tet effects;
* all 2,043 vendor names shared one prefix (rule E3 fired on 100 percent of rows);
* only 5 near-identical companies, fraud always at one difficulty level, only six families
  that the rule library was written for (circular evaluation).

What it adds:
* graded difficulty (easy / medium / hard) for the six original families;
* three held-out families that no rule was written for: kickback_overpricing, expense_padding,
  payroll_padding (detectable mainly with per-entity baselines);
* legitimate decoys that look like fraud: Tet and year-end bonus payroll, legitimate vendor price
  increases, bulk restocking.

Everything reuses the friend's table schema so the friend's accounting, features and rule engine run
unchanged. Fraud labels stay in labels.csv only.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path

from sme_fraud.generate import (Generator, HOLIDAYS, NORMAL_TYPES, NORMAL_WEIGHTS,
                                TZ, WINDOWS, allocate, parse, save_dataset, stamp)

ORIGINAL_FAMILIES = ["ghost_vendor", "split_payments", "duplicate_payment",
                     "period_end_adjustment", "risky_invoice", "long_outstanding_advance"]
HELD_OUT_FAMILIES = ["kickback_overpricing", "expense_padding", "payroll_padding"]
FAMILIES_V3 = ORIGINAL_FAMILIES + HELD_OUT_FAMILIES
DECOYS_V3 = ["tet_bonus_payroll", "year_end_bonus_payroll", "legit_price_increase", "legit_bulk_purchase"]
DIFFICULTIES = ("easy", "medium", "hard")
TET_DATES = [datetime(2024, 2, 10, tzinfo=TZ), datetime(2025, 1, 29, tzinfo=TZ)]
VENDOR_KINDS = ("vendor_payment", "stock_purchase", "material_purchase", "rent",
                "equipment_purchase", "selling_expense")

FORMS = ["TNHH", "TNHH", "TNHH", "Cổ phần", "TNHH Thương mại", "TNHH Sản xuất", "TNHH Dịch vụ",
         "TNHH MTV", "Cổ phần Đầu tư", "TNHH Thương mại Dịch vụ"]
WORDS = ["An Phát", "Hòa Bình", "Minh Long", "Thái Dương", "Phú Gia", "Đại Nam", "Việt Tiến", "Hưng Thịnh",
         "Kim Ngân", "Bảo Châu", "Tân Á", "Trường Sơn", "Đông Phương", "Gia Huy", "Nam Cường", "Hải Âu",
         "Sao Mai", "Thành Công", "Lộc Phát", "Quang Minh", "Hoàng Long", "Tín Nghĩa", "Phương Nam",
         "Đức Thành", "Vạn Xuân", "Hiệp Lực", "Ngọc Lan", "Thiên Phú", "Trí Đạt", "Mai Linh", "Á Châu",
         "Tây Hồ", "Cửu Long", "Sông Hồng", "Bình Minh", "Vĩnh Phát", "Toàn Cầu", "Hà Thành", "Xuân Bách"]
TRADES = ["Vật liệu xây dựng", "Thực phẩm", "Bao bì", "Vận tải", "Điện máy", "In ấn", "Nhựa", "Cơ khí",
          "Nông sản", "Thiết bị văn phòng", "Dệt may", "Hóa chất", "Logistics", "Quảng cáo", "Nội thất"]
CITIES = ["TP.HCM", "Hà Nội", "Đà Nẵng", "Cần Thơ", "Hải Phòng", "Bình Dương", "Đồng Nai", "Nha Trang"]


def company_name(rng) -> str:
    return f"Công ty {rng.choice(FORMS)} {rng.choice(TRADES)} {rng.choice(WORDS)}"


class WorldV3(Generator):
    """Subclass of the v2 generator. Construct with the same arguments plus optional knobs."""

    def __init__(self, n, rate, seed, companies=8, difficulty_weights=(.40, .35, .25)):
        self.difficulty_weights = difficulty_weights
        self.vprof, self.used, self.payroll_index = {}, set(), {}
        self.rent_vendor, self.company_scale = {}, {}
        super().__init__(n, rate, seed, companies)

    # ------------------------------------------------------------------ masters
    def default_profile(self, cid):
        return dict(mu=math.log(8_000_000 * self.company_scale[cid]), sigma=.3, weight=1., step_at=None, step=1.,
                    price=self.rng.lognormvariate(math.log(250_000), 1.0))

    def make_masters(self, count):
        rng = self.rng
        initial = datetime(2023, 1, 1, tzinfo=TZ)
        industries = ["trading", "manufacturing", "services", "retail", "logistics"]
        for i in range(count):
            cid = f"C{i+1:03}"
            scale = rng.choice([.5, .7, .9, 1.1, 1.5, 2.0])
            self.company_scale[cid] = scale
            self.tables["companies"].append(dict(
                company_id=cid, name=f"SME tổng hợp {i+1}", industry=industries[i % 5],
                city=CITIES[i % len(CITIES)], amount_scale=scale,
                saturday_operations=int(rng.random() < .7), currency="VND", timezone="Asia/Ho_Chi_Minh"))
            self.company_staff[cid], self.company_vendors[cid], self.company_customers[cid] = [], [], []
            n_staff, n_vendors, n_customers = rng.choice([16, 20, 26, 34, 44]), rng.choice([45, 70, 100, 140]), rng.choice([30, 50, 80])
            for j in range(n_staff):
                role = "director" if j == 0 else "chief_accountant" if j == 1 else "accountant" if j < 6 else "operations"
                hired = initial if j < 6 else datetime(2018, 1, 1, tzinfo=TZ) + timedelta(days=rng.randrange(0, 5 * 365))
                self.employee(cid, hired, role, "remote" if j % 13 == 8 else "onsite")
            office = self.identifier("ADDRESS_SYN_")
            base = 8_000_000 * scale
            for j in range(n_vendors):
                if rng.random() < .55:
                    onboard = datetime(2018, 1, 1, tzinfo=TZ) + timedelta(days=rng.randrange(0, 5 * 365))
                else:
                    onboard = datetime(2023, 1, 1, tzinfo=TZ) + timedelta(days=rng.randrange(0, 33 * 30))
                e = self.employees[self.company_staff[cid][j % n_staff]]
                v = self.vendor(cid, onboard, address=office if j < 5 else None,
                                phone=e["phone"] if j in (6, 7) else None, disclosed=j in (6, 7))
                v["name"] = company_name(rng)
                prof = dict(mu=math.log(base) + rng.gauss(0, .9), sigma=rng.uniform(.18, .35),
                            weight=1.0 / (1 + j) ** .9 * rng.uniform(.6, 1.4), step_at=None, step=1.0,
                            price=rng.lognormvariate(math.log(250_000), 1.0))
                if rng.random() < .12:
                    prof.update(step_at=datetime(2024, 9, 1, tzinfo=TZ) + timedelta(days=rng.randrange(0, 330)),
                                step=rng.uniform(1.15, 1.30))
                self.vprof[v["vendor_id"]] = prof
            # a few legitimate branch-style near-duplicate names (real-world source of fuzzy-match noise)
            vids = self.company_vendors[cid]
            for _ in range(max(1, n_vendors // 25)):
                a, b = rng.sample(vids, 2)
                self.vendors[b]["name"] = self.vendors[a]["name"] + f" - Chi nhánh {rng.choice(CITIES)}"
            legacy = [v for v in vids if parse(self.vendors[v]["onboarded_at"]) < initial]
            self.rent_vendor[cid] = (rng.choice(legacy), rng.choice([5, 8, 10, 15, 20, 30]) * 1_000_000)
            for j in range(n_customers):
                customer = dict(customer_id=self.identifier("CU"), company_id=cid, name=f"Khách hàng {company_name(rng)[9:]}",
                                tax_code=self.identifier("MST_SYN_"), bank_account=self.identifier("BANK_SYN_"),
                                recorded_at=stamp(initial), credit_terms_days=rng.choice([15, 30, 45, 60]))
                self.customers[customer["customer_id"]] = customer
                self.company_customers[cid].append(customer["customer_id"])
                self.tables["customers"].append(customer)
        self.tables["calendar"] = [dict(date=d, is_holiday=1, source="illustrative_simulation_calendar")
                                    for d in sorted(HOLIDAYS)]

    # ------------------------------------------------------------------ time
    @staticmethod
    def day_weight(d):
        w = 1.0
        if d.isoformat() in HOLIDAYS:
            w *= .12
        for tet in TET_DATES:
            if 0 < (tet.date() - d).days <= 14:
                w *= 1.6
        if d.day >= 26:
            w *= 1.3
        if d.month in (11, 12):
            w *= 1.12
        return w

    MAX_WEIGHT = 1.6 * 1.3 * 1.12

    def random_time(self, split, margin=0, weekend=False):
        start, end = WINDOWS[split]
        rng = self.rng
        while True:
            at = start + timedelta(days=rng.randrange(margin, (end - start).days - margin),
                hours=rng.choices([rng.randint(8, 18), rng.randint(19, 23), rng.randint(0, 7)], [86, 10, 4])[0],
                minutes=rng.randrange(60), seconds=rng.randrange(60))
            if weekend and at.weekday() < 5:
                continue
            if not weekend and rng.random() >= (1 if at.weekday() < 5 else .58 if at.weekday() == 5 else .28):
                continue
            if rng.random() < self.day_weight(at.date()) / self.MAX_WEIGHT:
                return at

    # ------------------------------------------------------------------ transactions
    def pick_vendor(self, cid, at):
        ids = [v for v in self.company_vendors[cid] if parse(self.vendors[v]["onboarded_at"]) <= at]
        weights = [self.vprof[v]["weight"] for v in ids]
        return self.vendors[self.rng.choices(ids, weights)[0]]

    def vendor_amount(self, v, at):
        prof = self.vprof.get(v["vendor_id"]) or self.vprof.setdefault(v["vendor_id"], self.default_profile(v["company_id"]))
        amount = self.rng.lognormvariate(prof["mu"], prof["sigma"])
        if prof["step_at"] and at >= prof["step_at"]:
            amount *= prof["step"]
        return amount

    def new_shell_vendor(self, cid, onboard, **kwargs):
        v = self.vendor(cid, onboard, background=False, **kwargs)
        v["name"] = company_name(self.rng)
        self.vprof[v["vendor_id"]] = self.default_profile(cid)
        return v

    def transaction(self, cid, split, at=None, kind=None, vendor=None, employee=None,
                    amount=None, creator=None, approver=None, delay_hours=None, price_markup=1.0):
        at = at or self.random_time(split)
        kind = kind or self.rng.choices(NORMAL_TYPES, NORMAL_WEIGHTS)[0]
        hidden = ""
        if vendor is None and kind in VENDOR_KINDS:
            vendor = self.vendors[self.rent_vendor[cid][0]] if kind == "rent" else self.pick_vendor(cid, at)
        if amount is None and kind in VENDOR_KINDS:
            if kind == "rent":
                amount = self.rent_vendor[cid][1]
            else:
                amount = max(25_000, int(self.vendor_amount(vendor, at) / 1000) * 1000)
                prof = self.vprof[vendor["vendor_id"]]
                if prof["step_at"] and prof["step_at"] <= at < prof["step_at"] + timedelta(days=75):
                    hidden = "legit_price_increase"
                if self.rng.random() < .007:
                    amount *= self.rng.randint(5, 12)
                    hidden = "legit_bulk_purchase"
                if self.rng.random() < .2 and amount > 1_500_000:
                    amount = max(100_000, round(amount / 1_000_000) * 1_000_000)
        row = super().transaction(cid, split, at, kind, vendor, employee, amount, creator, approver, delay_hours)
        row["unit_price_vnd"], row["quantity"] = "", ""
        if kind in VENDOR_KINDS and vendor is not None:
            if kind == "rent":
                price = float(row["amount_vnd"])
            else:
                prof = self.vprof.get(vendor["vendor_id"]) or self.vprof.setdefault(vendor["vendor_id"], self.default_profile(cid))
                price = prof["price"] * self.rng.uniform(.985, 1.015) * price_markup
                if prof["step_at"] and at >= prof["step_at"]:
                    price *= prof["step"]
            row["unit_price_vnd"] = int(round(price))
            row["quantity"] = round(int(row["amount_vnd"]) / max(1.0, float(row["unit_price_vnd"])), 3)
        if hidden:
            row["_hn"] = hidden
        return row

    def make_background(self):
        super().make_background()
        for i, r in enumerate(self.rows):
            if r["txn_type"] == "payroll":
                self.payroll_index[(r["employee_id"], r["payroll_period"])] = i
            hidden = r.pop("_hn", "")
            if hidden:
                self.truth[i].update(hard_negative_type=hidden, case_role="hard_negative")

    def put(self, split, row, family="", variant="", case="", hard="", support=False, observable="available", difficulty=""):
        while True:
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
            hard_negative_type=hard, difficulty=difficulty or ("subtle" if observable != "available" else "mixed" if family else ""),
            observability=observable if family else "")
        return row["transaction_id"]

    def mutate(self, i, family="", variant="", case="", hard="", difficulty="", **updates):
        """Edit an existing background row in place (padding / bonus decoys)."""
        self.rows[i].update(updates)
        self.used.add(i)
        self.truth[i].update(is_fraud=int(bool(family)), fraud_type=family, variant=variant, case_id=case,
            case_role="fraud" if family else "hard_negative", hard_negative_type=hard, difficulty=difficulty,
            observability="available" if family else "")

    def pick_difficulty(self):
        return self.rng.choices(DIFFICULTIES, self.difficulty_weights)[0]

    def context(self, split, margin=5):
        cid = self.rng.choice(list(self.company_staff))
        at = self.random_time(split, margin)
        creator = self.rng.choice(self.company_staff[cid][1:12])
        return cid, at, creator

    # ------------------------------------------------------------------ fraud
    def inject_fraud(self):
        total = round(self.n * self.rate)
        counts = allocate(total, [len(self.pools[s]) for s in WINDOWS])
        for split, count in zip(WINDOWS, counts):
            budgets = allocate(count, [1] * len(FAMILIES_V3))
            for family, budget in zip(FAMILIES_V3, budgets):
                getattr(self, f"fraud_{family}")(split, budget)

    @staticmethod
    def _loop(budget, build):
        done, k = 0, 0
        while done < budget:
            done += build(k, budget - done)
            k += 1

    def fraud_ghost_vendor(self, split, budget):
        def build(k, remaining):
            cid, at, creator = self.context(split, 8)
            case, d = self.identifier("CASE"), self.pick_difficulty()
            e = self.employees[self.rng.choice(self.company_staff[cid][2:])]
            variant = ["employee_vendor_overlap", "new_shell_two_hop", "ghost_employee_payroll"][k % 3]
            if variant == "ghost_employee_payroll":
                at = at.replace(day=28, hour=16)
                ghost = self.employee(cid, at.replace(day=1), bank=e["bank_account"], attendance=0, append_to_background=False)
                r = self.transaction(cid, split, at, "payroll", employee=ghost, creator=creator)
                r["support_doc_count"] = self.rng.choice([0, 1, 2]) if d != "hard" else self.rng.choice([1, 2, 3])
                self.put(split, r, "ghost_vendor", variant, case, difficulty=d)
                return 1
            before = at - timedelta(days=self.rng.randint(1, 20) if d == "easy" else self.rng.randint(60, 400))
            old = d != "easy"
            registered = before - timedelta(days=self.rng.randint(150, 2500)) if old else (
                before - timedelta(days=self.rng.randint(1, 45)) if variant == "new_shell_two_hop" else None)
            by_bank = variant == "employee_vendor_overlap" and k % 2 == 0 and d != "hard"
            v = self.new_shell_vendor(cid, before, registered=registered,
                bank=e["bank_account"] if by_bank else None,
                phone=e["phone"] if variant == "employee_vendor_overlap" and k % 2 and d == "easy" else None,
                address=e["address"] if (k % 2 or d == "medium") else None,
                representative_phone=e["phone"] if variant == "new_shell_two_hop" or d == "hard" else None)
            rows = 1 if d == "easy" else min(remaining, self.rng.randint(1, 3))
            for j in range(rows):
                when = min(at + timedelta(days=9 * j), WINDOWS[split][1] - timedelta(days=1))
                r = self.transaction(cid, split, when, "vendor_payment", vendor=v, creator=creator)
                r["goods_receipt_verified"] = int(self.rng.random() < (.35 if d == "easy" else .6))
                self.put(split, r, "ghost_vendor", variant, case, difficulty=d)
            return rows
        self._loop(budget, build)

    def fraud_split_payments(self, split, budget):
        def build(k, remaining):
            cid, at, creator = self.context(split, 8)
            case, d = self.identifier("CASE"), self.pick_difficulty()
            size = min(remaining, self.rng.randint(3, 6) if d != "hard" else self.rng.randint(2, 3))
            if remaining - size == 1 and size > 2:
                size += 1
            mode = (k + list(WINDOWS).index(split)) % 3
            variant = ["near_limit_same_recipient", "distributed_days", "multiple_recipients"][mode]
            span = [1, 12, 5][mode] if d != "hard" else 9
            at = min(at, WINDOWS[split][1] - timedelta(days=span + 2))
            phone = self.identifier("PHONE_SYN_")
            n_v = 3 if variant == "multiple_recipients" else 2 if d == "hard" else 1
            age = 30 if d == "easy" else self.rng.randint(40, 300)
            vendors = [self.new_shell_vendor(cid, at - timedelta(days=age), phone=None if d == "hard" else phone,
                                             representative_phone=phone) for _ in range(n_v)]
            limit = self.employees[creator]["approval_limit_vnd"]
            for j in range(size):
                ratio = self.rng.uniform(.90, .995) if (variant == "near_limit_same_recipient" and d == "easy") else (
                    self.rng.uniform(.55, .8) if d == "hard" else self.rng.uniform(.42, .88))
                if size == 2:
                    ratio = max(.62, ratio)
                r = self.transaction(cid, split, at + timedelta(days=span * j / max(1, size - 1), minutes=j * 17),
                    "vendor_payment", vendor=vendors[j % len(vendors)], amount=int(limit * ratio / 1000) * 1000,
                    creator=creator, delay_hours=self.rng.uniform(.1, 8))
                r["project_id"] = f"PR{self.rng.randrange(1, 31):03}" if variant == "multiple_recipients" else "PR001"
                self.put(split, r, "split_payments", variant, case, difficulty=d)
            return size
        self._loop(budget, build)

    def fraud_duplicate_payment(self, split, budget):
        def build(k, remaining):
            cid, at, creator = self.context(split, 30)
            case, d = self.identifier("CASE"), self.pick_difficulty()
            r = self.transaction(cid, split, at, "vendor_payment", creator=creator)
            self.put(split, dict(r), case=case, support=True)
            gap_hours = self.rng.randint(2, 72) if d == "easy" else self.rng.randint(72, 24 * 20)
            r.update(posted_at=stamp(at + timedelta(hours=gap_hours)),
                     approved_at=stamp(at + timedelta(hours=min(gap_hours, 2))),
                     created_at=stamp(at + timedelta(minutes=30)))
            if d == "easy":
                if k % 2:
                    r["invoice_id"] = self.identifier("I")
            else:
                r["invoice_id"] = self.identifier("I")
                r["invoice_number"] = f"HD{self.rng.randrange(1, 10**8):08}"
                if d == "hard":
                    r["amount_vnd"] = int(round(r["amount_vnd"] * self.rng.uniform(.97, 1.03) / 1000) * 1000)
                    r["invoice_gross_vnd"] = r["amount_vnd"]
            self.put(split, r, "duplicate_payment", "repeated_full_invoice" if d == "easy" else "repeated_new_invoice", case, difficulty=d)
            return 1
        self._loop(budget, build)

    def fraud_period_end_adjustment(self, split, budget):
        def build(k, remaining):
            cid, _, creator = self.context(split, 8)
            case, d = self.identifier("CASE"), self.pick_difficulty()
            start, end = WINDOWS[split]
            want_weekend = d == "easy"
            days = [start + timedelta(days=x) for x in range((end - start).days)]
            days = [x for x in days if x.day >= 25 and ((x.weekday() >= 5) if want_weekend else (x.weekday() < 5))]
            at = self.rng.choice(days).replace(hour=22 if want_weekend else 20, minute=self.rng.randrange(60))
            colluder = self.rng.choice([s for s in self.company_staff[cid][:6] if s != creator])
            approver = creator if d != "hard" else colluder
            r = self.transaction(cid, split, at, "adjustment", creator=creator, approver=approver,
                                 delay_hours=self.rng.choice([.01, .2, 3, 12]))
            r.update(approver_id=approver, support_doc_count=self.rng.choice([0, 1, 2]) if d != "hard" else 2,
                     goods_receipt_verified=0)
            if d == "hard":
                r["amount_vnd"] = int(r["amount_vnd"] * self.rng.uniform(2.5, 5))
            if k % 2:
                r.update(debit_account="131", credit_account="511")
            self.put(split, r, "period_end_adjustment", "self_approved_weekend_close" if d == "easy" else "collusive_period_close", case, difficulty=d)
            return 1
        self._loop(budget, build)

    def fraud_risky_invoice(self, split, budget):
        def build(k, remaining):
            cid, at, creator = self.context(split, 8)
            case, d = self.identifier("CASE"), self.pick_difficulty()
            v = self.new_shell_vendor(cid, at - timedelta(days=90))
            effective = at - timedelta(days=self.rng.randint(20, 60))
            latent = (k % 4 == 3) if d == "easy" else (self.rng.random() < (.4 if d == "medium" else .7))
            self.status(v, "ceased" if k % 2 else "abandoned", effective,
                        at + timedelta(days=7) if latent else effective + timedelta(days=2))
            r = self.transaction(cid, split, at, "vendor_payment", vendor=v, creator=creator)
            r["invoice_issued_at"] = stamp(at - timedelta(days=5))
            self.put(split, r, "risky_invoice", "inactive_issuer", case,
                     observable="registry_reported_later" if latent else "available", difficulty=d)
            return 1
        self._loop(budget, build)

    def fraud_long_outstanding_advance(self, split, budget):
        def build(k, remaining):
            cid, _, creator = self.context(split, 8)
            at = WINDOWS[split][0] + timedelta(days=self.rng.randint(105, 160), hours=self.rng.randint(9, 19))
            self.advance(cid, split, at, creator, False, "review" if k % 2 == 0 else "writeoff")
            return 1
        self._loop(budget, build)

    # --- held-out families (no rule was written for these) ---
    def fraud_kickback_overpricing(self, split, budget):
        def build(k, remaining):
            cid, at, _ = self.context(split, 60)
            case, d = self.identifier("CASE"), self.pick_difficulty()
            staff = self.company_staff[cid]
            creator, approver = self.rng.sample(staff[1:6], 2)
            legacy = [v for v in self.company_vendors[cid] if parse(self.vendors[v]["onboarded_at"]) < at - timedelta(days=200)]
            v = self.vendors[self.rng.choice(legacy)]
            n_rows = min(remaining, self.rng.randint(3, 5))
            lo, hi = (1.25, 1.7) if d == "easy" else (1.18, 1.35) if d == "medium" else (1.10, 1.22)
            for j in range(n_rows):
                when = at + timedelta(days=int(j * self.rng.uniform(7, 12)), hours=self.rng.randint(0, 6))
                markup = self.rng.uniform(lo, hi)
                amount = int(self.vendor_amount(v, when) * markup / 1000) * 1000
                r = self.transaction(cid, split, when, "vendor_payment", vendor=v, amount=amount, creator=creator,
                                     approver=approver, price_markup=markup)
                self.put(split, r, "kickback_overpricing", "inflated_price_colluding_pair", case, difficulty=d)
            return n_rows
        self._loop(budget, build)

    def fraud_expense_padding(self, split, budget):
        def build(k, remaining):
            cid, at, _ = self.context(split, 60)
            case, d = self.identifier("CASE"), self.pick_difficulty()
            e = self.rng.choice(self.company_staff[cid][2:6])
            n_rows = min(remaining, self.rng.randint(5, 8) if d == "easy" else self.rng.randint(3, 5))
            for j in range(n_rows):
                gap = self.rng.uniform(3, 7) if d == "easy" else self.rng.uniform(4, 12)
                when = at + timedelta(days=int(j * gap))
                lo = 1_700_000 if d == "easy" else 1_200_000
                r = self.transaction(cid, split, when, "cash_expense", amount=self.rng.randint(lo // 1000, 1_990_000 // 1000) * 1000,
                                     creator=e, approver=e, delay_hours=self.rng.uniform(.1, 6))
                r["support_doc_count"] = 0 if d != "hard" else self.rng.choice([0, 1])
                self.put(split, r, "expense_padding", "just_below_self_approval_limit", case, difficulty=d)
            return n_rows
        self._loop(budget, build)

    def fraud_payroll_padding(self, split, budget):
        start, end = WINDOWS[split]
        def build(k, remaining):
            case, d = self.identifier("CASE"), self.pick_difficulty()
            by_employee = {}
            for (eid, period), i in self.payroll_index.items():
                if i not in self.used and start <= parse(self.rows[i]["posted_at"]) < end and self.employees[eid]["role"] != "director":
                    by_employee.setdefault(eid, []).append((period, i))
            if not by_employee:
                return remaining
            eid = self.rng.choice(sorted(by_employee))
            mine = sorted(by_employee[eid])
            n_rows = min(remaining, self.rng.randint(2, 4), len(mine))
            lo, hi = (1.3, 2.0) if d == "easy" else (1.15, 1.35) if d == "medium" else (1.08, 1.18)
            first = self.rng.randrange(0, len(mine) - n_rows + 1)
            factor = self.rng.uniform(lo, hi)
            for _, i in mine[first:first + n_rows]:
                self.mutate(i, "payroll_padding", "inflated_pay_one_employee", case, difficulty=d,
                            amount_vnd=int(round(self.rows[i]["amount_vnd"] * factor / 1000) * 1000),
                            support_doc_count=self.rng.choice([0, 1, 2]))
            return n_rows
        self._loop(budget, build)

    # ------------------------------------------------------------------ decoys
    def inject_hard_negatives(self):
        super().inject_hard_negatives()
        for (eid, period), i in sorted(self.payroll_index.items()):
            if i in self.used or self.employees[eid]["role"] == "director":
                continue
            month = period[-2:]
            if month in ("01", "12") and self.rng.random() < .3:
                factor = self.rng.uniform(1.4, 2.4)
                self.mutate(i, hard="tet_bonus_payroll" if month == "01" else "year_end_bonus_payroll",
                            amount_vnd=int(round(self.rows[i]["amount_vnd"] * factor / 1000) * 1000),
                            support_doc_count=self.rng.choice([2, 3, 4]))


def generate_v3(output, n=100_000, rate=.003, seed=20261012, companies=8):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty dataset: {output}")
    generator = WorldV3(n, rate, seed, companies)
    tables = generator.finalize()
    return save_dataset(output, tables, n, rate, seed, companies)


def main():
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--fraud-rate", type=float, default=.003)
    parser.add_argument("--seed", type=int, default=20261012)
    parser.add_argument("--companies", type=int, default=8)
    args = parser.parse_args()
    manifest = generate_v3(args.output, args.rows, args.fraud_rate, args.seed, args.companies)
    print(json.dumps({"output": str(args.output), "fraud_rows": manifest["actual_fraud_rows"],
                      "fraud_variants": manifest["fraud_variants"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
