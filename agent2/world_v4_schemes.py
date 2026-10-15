"""Case-based internal-fraud scheme catalogue for world v4 (mixin used by WorldV4).

Every scheme opens a *case*: one perpetrator chosen by role (ACFE 2024: 37 percent employees, 41 percent managers,
19 percent owners/executives), collusion with probability .54 (two people .18, three or more .36), a concealment
level (L0 none .15 / L1 documents present .45 / L2 documents and behaviour mimic normal .40; ACFE: 11 percent of
cases had no concealment), and a start/end inside one chronological split. Weights follow ACFE 2024 scheme shares
for organisations under 100 staff, split across the concrete schemes below; Vietnamese references are listed in
DATA_V4.md. Rows are labelled fraud only where the record itself is the dishonest act; support rows (a genuine
invoice that is later duplicated, a re-payment to the real vendor) keep is_fraud = 0 and case_role = support.
"""
from __future__ import annotations

import calendar
import math
from datetime import datetime, timedelta

from sme_fraud.generate import HOLIDAYS, TZ, WINDOWS, parse, stamp

SPLIT_WEIGHTS = {"train": .5, "validation": .25, "test": .25}
ACFE_LEVEL = {"employee": .37, "manager": .41, "owner_executive": .19}
FINANCE = ("chief_accountant", "accountant", "cashier")

# name: (ACFE branch, weight, perpetrator roles, short Vietnamese/ACFE reference)
SCHEMES = {
    "shell_vendor": ("billing", .10, ("accountant", "chief_accountant", "purchasing"), "NCC ma nhận tiền; ACFE billing"),
    "invoice_mill": ("billing", .06, ("chief_accountant", "director"), "mua hóa đơn khống của doanh nghiệp ma rồi rút tiền"),
    "overbilling_excess_payment": ("billing", .05, ("accountant", "chief_accountant"), "sửa số tiền đề nghị sau khi ký duyệt (vụ DTC)"),
    "personal_purchase": ("billing", .04, ("director", "chief_accountant", "purchasing"), "mua đồ cá nhân bằng tiền công ty"),
    "duplicate_payment": ("payment_tampering", .04, ("accountant", "chief_accountant"), "tái sử dụng hóa đơn đã thanh toán (vụ Khải Đệ)"),
    "altered_payee": ("payment_tampering", .07, ("accountant", "cashier", "chief_accountant"), "sửa người thụ hưởng trên ủy nhiệm chi"),
    "bank_detail_switch": ("payment_tampering", .05, ("accountant", "chief_accountant"), "đổi tài khoản NCC sang tài khoản người quen rồi đổi lại"),
    "split_payments": ("billing", .05, ("accountant", "chief_accountant", "purchasing"), "chia nhỏ thanh toán né hạn mức"),
    "ghost_employee": ("payroll", .04, ("chief_accountant", "hr", "accountant"), "lập khống danh sách nhận lương (vụ trường học 7,5 tỷ)"),
    "payroll_padding": ("payroll", .04, ("chief_accountant", "hr", "accountant"), "nâng khống hệ số/tiền lương"),
    "terminated_still_paid": ("payroll", .03, ("hr", "chief_accountant", "accountant"), "nhân viên nghỉ việc vẫn có lương"),
    "fake_bonus_list": ("payroll", .03, ("hr", "chief_accountant"), "lập khống danh sách chi thưởng (vụ 770 triệu)"),
    "off_cycle_payroll": ("payroll", .02, ("accountant", "chief_accountant"), "chi lương ngoài kỳ cho người quen"),
    "expense_fictitious": ("expense", .07, ("sales", "operations", "purchasing"), "lập khống chứng từ suất ăn/tiếp khách (vụ Bắc Ninh 1,1 tỷ)"),
    "expense_padding": ("expense", .05, ("accountant", "cashier"), "chi tiền mặt sát hạn mức tự duyệt"),
    "expense_duplicate_claim": ("expense", .04, ("sales", "operations", "purchasing"), "nộp trùng chứng từ thanh toán"),
    "advance_unsettled": ("expense", .04, ("sales", "operations", "purchasing", "warehouse"), "tạm ứng không hoàn"),
    "receivable_lapping": ("skimming", .08, ("sales",), "nhân viên kinh doanh giữ tiền thu công nợ, xoay vòng (vụ Lê Huy 1,5 tỷ)"),
    "unrecorded_sales_skimming": ("skimming", .05, ("sales", "warehouse"), "bán hàng không ghi doanh thu, khai hàng hỏng"),
    "false_refund": ("skimming", .05, ("sales", "accountant"), "giảm giá/hoàn tiền khống cho khách"),
    "cash_larceny": ("cash_larceny", .10, ("cashier",), "thủ quỹ rút tiền quỹ, chứng từ chi khống"),
    "inventory_theft": ("noncash", .10, ("warehouse",), "thủ kho lập phiếu xuất khống (vụ VINACO, Massan)"),
    "kickback_overpricing": ("corruption", .09, ("purchasing", "chief_accountant"), "nâng giá mua để nhận lại quả"),
    "price_creep": ("corruption", .05, ("purchasing",), "tăng đơn giá dần theo thỏa thuận ngầm"),
    "bid_rotation": ("corruption", .05, ("purchasing", "director"), "nhóm NCC quân xanh quân đỏ thay phiên trúng"),
    "undisclosed_related_vendor": ("corruption", .06, ("purchasing", "director", "chief_accountant"), "NCC sân sau không công bố"),
    "period_end_adjustment": ("financial_statement", .03, ("chief_accountant", "director"), "bút toán tay cuối kỳ"),
    "fictitious_revenue_cutoff": ("financial_statement", .03, ("director", "chief_accountant"), "doanh thu khống cuối quý rồi giảm trừ"),
    "owner_override_transfer": ("owner_override", .03, ("director",), "giám đốc tự duyệt tạm ứng lớn không hoàn"),
    "vendor_burst": ("billing", .02, ("accountant",), "loạt chi nhiều NCC trong một buổi tối"),
}


class NotApplicable(Exception):
    pass


def _workday(at, forward=True):
    step = timedelta(days=1 if forward else -1)
    while at.weekday() >= 5 or at.date().isoformat() in HOLIDAYS:
        at += step
    return at


class SchemesMixin:
    catalog = SCHEMES          # the sealed world extends this with schemes never used in development

    # ------------------------------------------------------------------ case machinery
    def level_of(self, cid, eid):
        idx = self.company_staff[cid].index(eid) if eid in self.company_staff[cid] else 99
        return "owner_executive" if idx == 0 else "manager" if idx in (1, 6, 7, 8) else "employee"

    def open_case(self, scheme, cid, split=None):
        rng = self.rng
        branch, _, roles, ref = self.catalog[scheme]
        split = split or rng.choices(list(SPLIT_WEIGHTS), list(SPLIT_WEIGHTS.values()))[0]
        a, b = WINDOWS[split]
        span = (b - a).days
        candidates = self.staff_with(cid, *roles)
        if not candidates:
            raise NotApplicable
        by_level = {}
        for e in candidates:
            by_level.setdefault(self.level_of(cid, e), []).append(e)
        levels = list(by_level)
        level = rng.choices(levels, [ACFE_LEVEL[x] for x in levels])[0]   # ACFE 2024: 37 / 41 / 19 percent
        perp = rng.choice(by_level[level])
        duration = {"employee": rng.randint(30, 110), "manager": rng.randint(45, 150), "owner_executive": rng.randint(60, 170)}[level]
        duration = min(duration, span - 20)
        start = (a + timedelta(days=rng.randint(5, max(6, span - duration - 10)))).replace(hour=9)
        end = min(start + timedelta(days=duration), b - timedelta(days=3))
        if not (self.active(self.employees[perp], start) and self.active(self.employees[perp], end)):
            raise NotApplicable
        x = rng.random()
        collusion = 1 if x >= .54 else 2 if x < .18 else 3
        pool = [e for e in self.company_staff[cid] if e != perp and self.active(self.employees[e], start)]
        accomplices = rng.sample(pool, min(len(pool), collusion - 1))
        concealment = rng.choices(["L0", "L1", "L2"], [.15, .45, .40])[0]
        case = dict(case_id=self.identifier("CASE"), company_id=cid, scheme=scheme, acfe_branch=branch, reference_vi=ref,
                    perpetrator_id=perp, perpetrator_role=self.employees[perp]["role"], perpetrator_level=level,
                    accomplice_ids="|".join(accomplices), collusion=str(collusion) if collusion < 3 else "3+",
                    concealment=concealment, split=split, start_at=stamp(start), end_at=stamp(end), fraud_rows=0, loss_vnd=0)
        case["_start"], case["_end"], case["_acc"] = start, end, accomplices
        return case

    def extra(self, case):
        return dict(scheme_group=case["acfe_branch"], perpetrator_level=case["perpetrator_level"], collusion=case["collusion"],
                    concealment=case["concealment"])

    def approver_for(self, case, amount=0):
        cid = case["company_id"]
        if case["_acc"]:
            return case["_acc"][0]
        if case["concealment"] == "L0" and case["perpetrator_role"] in FINANCE + ("director",):
            return case["perpetrator_id"]
        return self.company_staff[cid][1] if amount <= 50_000_000 else self.company_staff[cid][0]

    def creator_for(self, case):
        p = case["perpetrator_id"]
        return p if self.employees[p]["role"] in FINANCE + ("director",) else self.rng.choice(self.company_staff[case["company_id"]][3:6])

    def docs(self, case):
        c = case["concealment"]
        if c == "L0":
            return self.rng.choice([0, 0, 1])
        if c == "L1":
            return self.rng.choice([1, 2, 2, 3])
        return min(4, max(1, int(round(self.rng.gauss(self.profile[case["company_id"]]["doc_mean"], .8)))))

    def times(self, case, k, odd=None):
        rng = self.rng
        start, end = case["_start"], case["_end"]
        span = max(1, (end - start).days)
        odd = case["concealment"] == "L0" if odd is None else odd
        out = []
        for j in range(k):
            day = start + timedelta(days=int(span * (j + rng.random()) / k))
            day = _workday(day) if not odd or rng.random() < .5 else day
            out.append(self.clamp(self.day_time(min(day, end), odd=odd and rng.random() < .6), case["split"]))
        return sorted(out)

    def velocity(self, case):
        mult = {"employee": 1.0, "manager": 2.2, "owner_executive": 4.5}[case["perpetrator_level"]]
        return 8_000_000 * self.profile[case["company_id"]]["scale"] * mult * self.rng.uniform(.6, 1.6)

    def amount(self, case, j=0, base=None, rnd=False):
        base = base or self.velocity(case)
        x = base * (1 + self.rng.uniform(0, .12)) ** j * self.rng.uniform(.75, 1.25)
        return max(100_000, int(round(x / 1_000_000)) * 1_000_000 if rnd else int(x / 1000) * 1000)

    def fraud_put(self, case, row, variant, observable="available"):
        if parse(row["approved_at"]) > parse(row["posted_at"]):
            row["approved_at"] = row["posted_at"]
        if parse(row["created_at"]) > parse(row["approved_at"]):
            row["created_at"] = row["approved_at"]
        self.put(case["split"], row, case["scheme"], variant, case["case_id"], observable=observable,
                 difficulty=case["concealment"], extra=self.extra(case))
        case["fraud_rows"] += 1
        case["loss_vnd"] += int(row["amount_vnd"])

    def support_put(self, case, row):
        self.put(case["split"], row, case=case["case_id"], support=True)

    def fraud_mutate(self, case, i, variant, **updates):
        self.mutate(i, case["scheme"], variant, case["case_id"], difficulty=case["concealment"], extra=self.extra(case), **updates)
        case["fraud_rows"] += 1
        case["loss_vnd"] += int(self.rows[i]["amount_vnd"])

    def tx(self, case, at, kind, **kw):
        return self.transaction(case["company_id"], case["split"], at, kind, **kw)

    def shell(self, case, onboard, **kw):
        v = self.new_shell_vendor(case["company_id"], onboard, **kw)
        self.vcat[v["vendor_id"]] = "services"
        return v

    def real_vendor(self, case, at, min_age=120):
        cid = case["company_id"]
        ids = [x for x in self.company_vendors[cid] if parse(self.vendors[x]["onboarded_at"]) < at - timedelta(days=min_age)
               and self.vcat.get(x) in ("goods", "materials", "services")]
        if not ids:
            raise NotApplicable
        return self.vendors[self.rng.choices(ids, [self.vprof[x]["weight"] for x in ids])[0]]

    # ------------------------------------------------------------------ driver
    def inject_fraud(self):
        rng = self.rng
        target = round(self.n * self.rate)
        comps = [c for c, p in self.profile.items() if p["fraud_mu"] > 0]
        weights = [self.profile[c]["fraud_mu"] * self.profile[c]["n_staff"] ** .5 for c in comps]
        names = list(SCHEMES)
        created = 0
        for scheme in names:                       # coverage: every scheme in every split
            for split in SPLIT_WEIGHTS:
                created += self.try_case(scheme, comps, weights, split)
        attempts = 0
        while created < target and attempts < 20_000:
            attempts += 1
            scheme = rng.choices(names, [SCHEMES[s][1] for s in names])[0]
            created += self.try_case(scheme, comps, weights)

    def try_case(self, scheme, comps, weights, split=None, tries=25):
        for _ in range(tries):
            cid = self.rng.choices(comps, weights)[0]
            try:
                case = self.open_case(scheme, cid, split)
                getattr(self, f"scheme_{scheme}")(case)
            except NotApplicable:
                continue
            if case["fraud_rows"]:
                self.cases.append({k: v for k, v in case.items() if not k.startswith("_")})
                return case["fraud_rows"]
        return 0

    # ------------------------------------------------------------------ billing / payment tampering
    def scheme_shell_vendor(self, case):
        rng, p, c = self.rng, self.employees[case["perpetrator_id"]], case["concealment"]
        if c == "L0":
            v = self.shell(case, case["_start"] - timedelta(days=rng.randint(2, 20)), bank=p["bank_account"])
            variant = "vendor_bank_is_employee_account"
        elif c == "L1":
            v = self.shell(case, case["_start"] - timedelta(days=rng.randint(5, 40)), address=p["address"], representative_phone=p["phone"])
            variant = "vendor_contact_linked_to_employee"
        else:
            v = self.shell(case, case["_start"] - timedelta(days=rng.randint(200, 700)), registered=case["_start"] - timedelta(days=rng.randint(900, 2500)))
            variant = "aged_vendor_no_master_overlap"
        months = max(1, (case["_end"] - case["_start"]).days // 30)
        for j, at in enumerate(self.times(case, months * rng.randint(1, 2))):
            amt = self.amount(case, j, rnd=c != "L2")
            r = self.tx(case, at, "vendor_payment", vendor=v, amount=amt, creator=self.creator_for(case), approver=self.approver_for(case, amt))
            r.update(goods_receipt_verified=int(c == "L2" and rng.random() < .6), support_doc_count=self.docs(case))
            self.fraud_put(case, r, variant)

    def scheme_invoice_mill(self, case):
        rng = self.rng
        first = case["_start"]
        v = self.shell(case, first - timedelta(days=rng.randint(1, 10)), registered=first - timedelta(days=rng.randint(10, 60)))
        latent = case["concealment"] != "L0"
        for j, at in enumerate(self.times(case, rng.randint(2, 6))):
            amt = self.amount(case, j, rnd=True)
            r = self.tx(case, at, "vendor_payment", vendor=v, amount=amt, creator=self.creator_for(case), approver=self.approver_for(case, amt))
            r.update(goods_receipt_verified=0, support_doc_count=self.docs(case), business_purpose="Thanh toán dịch vụ tư vấn")
            self.fraud_put(case, r, "service_invoice_from_young_vendor", observable="registry_reported_later" if latent else "available")
        if latent:
            eff = case["_end"] + timedelta(days=rng.randint(10, 40))
            self.status(v, "abandoned", eff, eff + timedelta(days=20))
        else:
            self.status(v, "abandoned", first - timedelta(days=3), first - timedelta(days=2))

    def scheme_overbilling_excess_payment(self, case):
        rng, p = self.rng, self.employees[case["perpetrator_id"]]
        for at in self.times(case, rng.randint(2, 5)):
            v = self.real_vendor(case, at)
            gross = max(1_000_000, int(self.vendor_amount(v, at) / 1000) * 1000)
            legit = self.tx(case, at, "vendor_payment", vendor=v, amount=gross, creator=self.creator_for(case), approver=self.approver_for(case, gross))
            r = dict(legit)
            self.support_put(case, legit)
            later = min(at + timedelta(hours=rng.randint(1, 72)), case["_end"])
            r.update(posted_at=stamp(later), approved_at=stamp(later), created_at=stamp(later - timedelta(minutes=30)),
                     amount_vnd=int(gross * rng.uniform(.08, .35) / 1000) * 1000, support_doc_count=self.docs(case),
                     recipient_account=p["bank_account"] if case["concealment"] == "L0" else self.identifier("BANK_SYN_"))
            self.fraud_put(case, r, "excess_payment_on_same_invoice")

    def scheme_personal_purchase(self, case):
        rng, cid = self.rng, case["company_id"]
        shops = [x for x in self.company_vendors[cid] if self.vcat.get(x) == "retail" and parse(self.vendors[x]["onboarded_at"]) < case["_start"]]
        if not shops:
            raise NotApplicable
        perp = case["perpetrator_id"]
        creator = perp if self.employees[perp]["role"] in FINANCE + ("director",) else self.creator_for(case)
        for j, at in enumerate(self.times(case, rng.randint(3, 8), odd=case["concealment"] != "L2")):
            if case["concealment"] != "L2" and rng.random() < .6:
                at = self.clamp(at + timedelta(days=(5 - at.weekday()) % 7), case["split"])
            amt = max(1_500_000, self.amount(case, j, base=6_000_000))
            r = self.tx(case, at, rng.choice(["tools_purchase", "selling_expense"]), vendor=self.vendors[rng.choice(shops)], amount=amt,
                        creator=creator, approver=self.approver_for(case, amt))
            r.update(goods_receipt_verified=0, support_doc_count=self.docs(case))
            self.fraud_put(case, r, "personal_items_paid_as_business")

    def scheme_duplicate_payment(self, case):
        rng, c = self.rng, case["concealment"]
        for at in self.times(case, rng.randint(1, 3)):
            v = self.real_vendor(case, at)
            gross = max(500_000, int(self.vendor_amount(v, at) / 1000) * 1000)
            r = self.tx(case, at, "vendor_payment", vendor=v, amount=gross, creator=self.creator_for(case))
            self.support_put(case, dict(r))
            later = min(at + timedelta(hours=rng.randint(2, 72) if c == "L0" else rng.randint(72, 24 * 25)), case["_end"])
            r.update(posted_at=stamp(later), approved_at=stamp(later), created_at=stamp(later - timedelta(hours=1)),
                     approver_id=self.approver_for(case, gross), support_doc_count=self.docs(case))
            if c != "L0":
                r.update(invoice_id=self.identifier("I"), invoice_number=f"HD{rng.randrange(1, 10**8):08}")
            if c == "L2":
                r["amount_vnd"] = r["invoice_gross_vnd"] = int(round(gross * rng.uniform(.97, 1.03) / 1000) * 1000)
            self.fraud_put(case, r, {"L0": "same_invoice_repeated", "L1": "new_invoice_number", "L2": "new_number_amount_jitter"}[c])

    def scheme_altered_payee(self, case):
        rng, p = self.rng, self.employees[case["perpetrator_id"]]
        for at in self.times(case, rng.randint(1, 4)):
            v = self.real_vendor(case, at)
            gross = max(1_000_000, int(self.vendor_amount(v, at) / 1000) * 1000)
            r = self.tx(case, at, "vendor_payment", vendor=v, amount=gross, creator=self.creator_for(case), approver=self.approver_for(case, gross))
            r.update(recipient_account=p["bank_account"] if case["concealment"] == "L0" else self.identifier("BANK_SYN_"), support_doc_count=self.docs(case))
            self.fraud_put(case, r, "payee_changed_on_transfer_order")
            repay = at + timedelta(days=rng.randint(10, 35))
            if repay < WINDOWS[case["split"]][1] - timedelta(days=1):
                again = self.tx(case, repay, "vendor_payment", vendor=v, amount=gross, creator=self.creator_for(case))
                again.update(invoice_id=r["invoice_id"], invoice_number=r["invoice_number"], invoice_issued_at=r["invoice_issued_at"], invoice_gross_vnd=gross)
                self.support_put(case, again)

    def scheme_bank_detail_switch(self, case):
        rng, cid = self.rng, case["company_id"]
        v = self.real_vendor(case, case["_start"])
        new = self.identifier("BANK_SYN_")
        at0 = case["_start"]
        self.tables["bank_account_changes"].append(dict(change_id=self.identifier("BC"), company_id=cid, vendor_id=v["vendor_id"],
            old_account=v["bank_account"], new_account=new, effective_at=stamp(at0), observed_at=stamp(at0), verified_at="",
            callback_verified=0, approver_id=case["perpetrator_id"]))
        self.link(cid, v["vendor_id"], new, "bank_account", at0)
        stamps = self.times(case, rng.randint(1, 3))
        for at in stamps:
            gross = max(1_000_000, int(self.vendor_amount(v, at) * rng.uniform(1, 1.6) / 1000) * 1000)
            r = self.tx(case, at, "vendor_payment", vendor=v, amount=gross, creator=self.creator_for(case), approver=self.approver_for(case, gross))
            r.update(recipient_account=new, support_doc_count=self.docs(case))
            self.fraud_put(case, r, "temporary_unverified_bank_change")
        back = min(stamps[-1] + timedelta(days=rng.randint(1, 10)), WINDOWS[case["split"]][1] - timedelta(days=1))
        self.tables["bank_account_changes"].append(dict(change_id=self.identifier("BC"), company_id=cid, vendor_id=v["vendor_id"],
            old_account=new, new_account=v["bank_account"], effective_at=stamp(back), observed_at=stamp(back), verified_at="",
            callback_verified=0, approver_id=case["perpetrator_id"]))

    def scheme_split_payments(self, case):
        rng, c = self.rng, case["concealment"]
        creator = self.creator_for(case)
        limit = self.employees[creator]["approval_limit_vnd"]
        at0 = self.times(case, 1)[0]
        v = self.real_vendor(case, at0) if c == "L2" else self.shell(case, at0 - timedelta(days=rng.randint(20, 90)))
        size = rng.randint(2, 3) if c == "L2" else rng.randint(3, 5)
        span = rng.choice([1, 3, 7, 12])
        for j in range(size):
            at = self.clamp(at0 + timedelta(days=span * j / max(1, size - 1), minutes=17 * j), case["split"])
            ratio = rng.uniform(.9, .995) if c == "L0" else rng.uniform(.55, .85)
            r = self.tx(case, at, "vendor_payment", vendor=v, amount=int(limit * ratio / 1000) * 1000, creator=creator,
                        approver=creator if c == "L0" else self.approver_for(case), delay_hours=rng.uniform(.1, 6))
            r["support_doc_count"] = self.docs(case)
            self.fraud_put(case, r, "split_below_approval_limit")

    def scheme_vendor_burst(self, case):
        rng, cid = self.rng, case["company_id"]
        at = self.clamp(self.times(case, 1, odd=True)[0].replace(hour=rng.randint(19, 21), minute=0), case["split"])
        ids = [x for x in self.company_vendors[cid] if parse(self.vendors[x]["onboarded_at"]) < at - timedelta(days=30) and self.vcat.get(x) != "landlord"]
        for j, vid in enumerate(rng.sample(ids, min(len(ids), rng.randint(4, 6)))):
            r = self.tx(case, self.clamp(at + timedelta(minutes=12 * j), case["split"]), "vendor_payment", vendor=self.vendors[vid],
                        creator=self.creator_for(case), delay_hours=rng.uniform(.1, 3))
            if case["concealment"] != "L2":
                r["recipient_account"] = self.identifier("BANK_SYN_")
            self.fraud_put(case, r, "late_evening_multi_vendor_burst")

    # ------------------------------------------------------------------ payroll
    def pay_dates(self, case, limit):
        cid = case["company_id"]
        pd = self.profile[cid]["pay_days"][-1]
        out, day = [], case["_start"].replace(day=1)
        while day <= case["_end"] and len(out) < limit:
            last = calendar.monthrange(day.year, day.month)[1]
            d = _workday(datetime(day.year, day.month, last if pd == "last" else pd, self.rng.randint(9, 16), self.rng.randrange(60), tzinfo=TZ), forward=False)
            if case["_start"] <= d <= case["_end"]:
                out.append(d)
            day = (day + timedelta(days=32)).replace(day=1)
        if not out:
            raise NotApplicable
        return out

    def scheme_ghost_employee(self, case):
        rng, cid, p, c = self.rng, case["company_id"], self.employees[case["perpetrator_id"]], case["concealment"]
        dates = self.pay_dates(case, 12)
        ghost = self.employee(cid, case["_start"].replace(day=1, hour=8), "operations", bank=p["bank_account"] if c == "L0" else None,
                              attendance=rng.randint(18, 22) if c == "L2" else 0, append_to_background=False)
        for at in dates:
            r = self.tx(case, at, "payroll", employee=ghost, creator=self.creator_for(case), approver=self.approver_for(case))
            r["amount_vnd"] = ghost["monthly_salary_vnd"]
            r["support_doc_count"] = self.docs(case)
            self.fraud_put(case, r, {"L0": "ghost_paid_to_employee_account", "L1": "ghost_no_attendance", "L2": "ghost_with_fabricated_timesheet"}[c])

    def scheme_payroll_padding(self, case):
        rng, cid = self.rng, case["company_id"]
        target = case["perpetrator_id"] if rng.random() < .5 or not case["_acc"] else case["_acc"][0]
        rows = [i for i in self.payroll_rows.get((cid, target), []) if i not in self.used and
                case["_start"] <= parse(self.rows[i]["posted_at"]) <= case["_end"]]
        if not rows:
            raise NotApplicable
        lo, hi = {"L0": (1.3, 2.0), "L1": (1.15, 1.35), "L2": (1.06, 1.15)}[case["concealment"]]
        factor = rng.uniform(lo, hi)
        for i in rows:
            self.fraud_mutate(case, i, "inflated_pay_one_employee", amount_vnd=int(round(self.rows[i]["amount_vnd"] * factor / 1000)) * 1000)

    def scheme_terminated_still_paid(self, case):
        rng, cid = self.rng, case["company_id"]
        left = [e for e in self.company_staff[cid] if self.employees[e]["terminated_at"]
                and case["_start"] - timedelta(days=120) < parse(self.employees[e]["terminated_at"]) < case["_start"] - timedelta(days=20)]
        if not left:
            raise NotApplicable
        dates = self.pay_dates(case, rng.randint(2, 5))
        e, p = self.employees[rng.choice(left)], self.employees[case["perpetrator_id"]]
        for at in dates:
            r = self.tx(case, at, "payroll", employee=e, creator=self.creator_for(case), approver=self.approver_for(case))
            r["amount_vnd"] = e["monthly_salary_vnd"]
            if case["concealment"] == "L0":
                r["recipient_account"] = p["bank_account"]
            r["support_doc_count"] = self.docs(case)
            self.fraud_put(case, r, "salary_after_termination")

    def scheme_fake_bonus_list(self, case):
        rng, cid = self.rng, case["company_id"]
        at = self.times(case, 1, odd=False)[0]
        for k in range(rng.randint(1, 3)):
            ghost = self.employee(cid, at - timedelta(days=rng.randint(1, 20)), "operations", attendance=0, append_to_background=False)
            r = self.tx(case, self.clamp(at + timedelta(minutes=5 * k), case["split"]), "payroll", employee=ghost,
                        creator=self.creator_for(case), approver=self.approver_for(case))
            r["amount_vnd"] = int(rng.uniform(3, 15) * 10) * 100_000
            r["support_doc_count"] = self.docs(case)
            self.fraud_put(case, r, "bonus_to_person_not_on_staff")
        p = self.employees[case["perpetrator_id"]]
        r = self.tx(case, self.clamp(at + timedelta(minutes=30), case["split"]), "payroll", employee=p, creator=self.creator_for(case),
                    approver=self.approver_for(case))
        r["amount_vnd"] = int(p["monthly_salary_vnd"] * rng.uniform(2, 4) / 100_000) * 100_000
        self.fraud_put(case, r, "self_bonus_above_policy")

    def scheme_off_cycle_payroll(self, case):
        rng, cid = self.rng, case["company_id"]
        target = self.employees[case["_acc"][0] if case["_acc"] else rng.choice(self.company_staff[cid][6:])]
        if not self.active(target, case["_start"]) or not self.active(target, case["_end"]):
            raise NotApplicable
        for at in self.times(case, rng.randint(2, 3)):
            at = self.clamp(at.replace(day=min(28, max(8, at.day))), case["split"])
            r = self.tx(case, at, "payroll", employee=target, creator=self.creator_for(case), approver=self.approver_for(case))
            r["amount_vnd"] = int(round(target["monthly_salary_vnd"] * rng.uniform(.6, 1.2) / 1000) * 1000)
            r["support_doc_count"] = self.docs(case)
            self.fraud_put(case, r, "extra_payment_outside_pay_date")

    # ------------------------------------------------------------------ expenses and advances
    def scheme_expense_fictitious(self, case):
        rng = self.rng
        base = rng.uniform(1.5, 6) * 1_000_000 * self.profile[case["company_id"]]["scale"] ** .3
        months = max(1, (case["_end"] - case["_start"]).days // 30)
        for j, at in enumerate(self.times(case, months * rng.randint(2, 4))):
            amt = int(base * rng.uniform(.9, 1.1) * (1 + .03 * j) / 1000) * 1000
            r = self.tx(case, at, "cash_expense", amount=amt, creator=self.creator_for(case), approver=self.approver_for(case, amt))
            r.update(support_doc_count=self.docs(case), business_purpose="Chi tiếp khách / suất ăn")
            self.fraud_put(case, r, "fabricated_meal_or_entertainment_receipts")

    def scheme_expense_padding(self, case):
        rng, cid = self.rng, case["company_id"]
        e, limit = case["perpetrator_id"], self.profile[case["company_id"]]["self_limit"]
        for at in self.times(case, rng.randint(4, 9)):
            amt = int(limit * rng.uniform(.82 if case["concealment"] == "L0" else .6, .995) / 1000) * 1000
            r = self.tx(case, at, "cash_expense", amount=amt, creator=e, approver=e, delay_hours=rng.uniform(.1, 6))
            r["support_doc_count"] = 0 if case["concealment"] != "L2" else rng.choice([0, 1])
            self.fraud_put(case, r, "just_below_self_approval_limit")

    def scheme_expense_duplicate_claim(self, case):
        rng = self.rng
        chief = self.company_staff[case["company_id"]][1]
        for at in self.times(case, rng.randint(2, 4)):
            amt = int(rng.uniform(.8, 5) * 1_000_000 / 1000) * 1000
            first = self.tx(case, at, "cash_expense", amount=amt, creator=self.creator_for(case), approver=chief)
            first["support_doc_count"] = rng.choice([1, 2])
            self.support_put(case, first)
            later = self.clamp(at + timedelta(days=rng.randint(7, 40)), case["split"])
            dup = self.tx(case, later, "cash_expense", amount=amt if case["concealment"] != "L2" else int(amt * rng.uniform(.97, 1.03) / 1000) * 1000,
                          creator=self.creator_for(case), approver=self.approver_for(case, amt))
            dup["support_doc_count"] = first["support_doc_count"]
            self.fraud_put(case, dup, "same_receipt_claimed_twice")

    def scheme_advance_unsettled(self, case):
        a, b = WINDOWS[case["split"]]
        hi = 300 if (b - a).days > 300 else 160
        at = a + timedelta(days=self.rng.randint(105, hi), hours=self.rng.randint(9, 17))
        self.advance(case["company_id"], case["split"], at, self.creator_for(case), False, "review" if self.rng.random() < .5 else "writeoff")
        for t in self.truth:
            if t["fraud_type"] == "long_outstanding_advance" and not t["scheme_group"]:
                t.update(fraud_type=case["scheme"], case_id=case["case_id"], difficulty=case["concealment"], **self.extra(case))
                case["fraud_rows"] += 1

    # ------------------------------------------------------------------ receipts (skimming)
    def scheme_receivable_lapping(self, case):
        perp = case["perpetrator_id"]
        mine = sorted((s for s in self.receipts if s["manager"] == perp and s["receipt"] is not None and s["receipt"] not in self.used
                       and case["_start"] <= parse(self.rows[s["receipt"]]["posted_at"]) <= case["_end"]),
                      key=lambda s: self.rows[s["receipt"]]["posted_at"])
        if len(mine) < 3:
            raise NotApplicable
        chain = mine[: self.rng.randint(3, min(8, len(mine)))]
        for prev, cur in zip(chain, chain[1:]):
            self.fraud_mutate(case, cur["receipt"], "later_customer_payment_applied_to_earlier_invoice",
                              customer_id=prev["customer"], applied_invoice_id=prev["invoice_id"], amount_vnd=prev["gross"],
                              recipient_account=self.customers[prev["customer"]]["bank_account"],
                              payer_account=self.customers[cur["customer"]]["bank_account"])
        last = chain[-1]
        when = self.clamp(parse(self.rows[last["receipt"]]["posted_at"]) + timedelta(days=self.rng.randint(1, 15)), case["split"])
        conceal = "sales_return" if case["concealment"] == "L2" else "bad_debt_writeoff"
        debit, credit = ("511", "131") if conceal == "sales_return" else ("642", "131")
        self.fraud_mutate(case, chain[0]["receipt"], "final_gap_closed_by_" + conceal, txn_type=conceal, debit_account=debit, credit_account=credit,
                          customer_id=last["customer"], applied_invoice_id=last["invoice_id"], amount_vnd=last["gross"], payer_account="",
                          recipient_account="", payment_channel="journal", employee_id="", vendor_id="", collector_id=perp,
                          posted_at=stamp(when), approved_at=stamp(when), created_at=stamp(when - timedelta(hours=2)),
                          effective_date=when.date().isoformat(), support_doc_count=self.docs(case), business_purpose="Điều chỉnh công nợ khách hàng")

    def scheme_unrecorded_sales_skimming(self, case):
        rng, cid = self.rng, case["company_id"]
        if self.profile[cid]["industry"] not in ("trading", "retail", "manufacturing"):
            raise NotApplicable
        for j, at in enumerate(self.times(case, rng.randint(3, 8))):
            amt = self.amount(case, j, base=self.velocity(case) * .6)
            r = self.new_kind_row(cid, at, "inventory_writeoff", amt, case["perpetrator_id"], self.approver_for(case, amt),
                                  purpose="Hàng hỏng, hết hạn", docs=self.docs(case))
            self.fraud_put(case, r, "goods_sold_off_book_written_off_as_spoilage")

    def scheme_false_refund(self, case):
        rng, cid, p = self.rng, case["company_id"], self.employees[case["perpetrator_id"]]
        cus = self.company_customers[cid]
        for j, at in enumerate(self.times(case, rng.randint(2, 6))):
            cu = rng.choice(cus)
            amt = self.amount(case, j, base=self.velocity(case) * .5)
            ret = self.new_kind_row(cid, at, "sales_return", amt, case["perpetrator_id"], self.approver_for(case, amt), customer_id=cu,
                                    purpose="Giảm giá / hàng bán bị trả lại", docs=self.docs(case))
            self.fraud_put(case, ret, "fictitious_return")
            later = self.clamp(at + timedelta(days=rng.randint(1, 5)), case["split"])
            dest = p["bank_account"] if case["concealment"] == "L0" else self.identifier("BANK_SYN_")
            ref = self.new_kind_row(cid, later, "customer_refund", amt, self.creator_for(case), self.approver_for(case, amt), customer_id=cu,
                                    recipient=dest, purpose="Hoàn tiền khách hàng", docs=self.docs(case))
            self.fraud_put(case, ref, "refund_to_account_not_on_customer_master")

    def scheme_cash_larceny(self, case):
        rng = self.rng
        months = max(1, (case["_end"] - case["_start"]).days // 30)
        for j, at in enumerate(self.times(case, months * rng.randint(2, 4))):
            amt = self.amount(case, j, base=self.velocity(case) * .4, rnd=case["concealment"] != "L2")
            r = self.tx(case, at, "cash_expense", amount=amt, creator=case["perpetrator_id"], approver=self.approver_for(case, amt))
            r.update(support_doc_count=self.docs(case), business_purpose="Chi khác")
            self.fraud_put(case, r, "cash_removed_with_fabricated_voucher")

    def scheme_inventory_theft(self, case):
        rng, cid = self.rng, case["company_id"]
        if self.profile[cid]["industry"] not in ("trading", "retail", "manufacturing", "logistics"):
            raise NotApplicable
        months = max(1, (case["_end"] - case["_start"]).days // 30)
        for j, at in enumerate(self.times(case, months * rng.randint(1, 3))):
            if case["concealment"] == "L2" and rng.random() < .5:
                at = self.clamp(_workday(datetime(at.year, at.month, 28, 16, tzinfo=TZ), forward=False), case["split"])
            amt = self.amount(case, j, base=self.velocity(case) * .7)
            r = self.new_kind_row(cid, at, "inventory_writeoff", amt, case["perpetrator_id"], self.approver_for(case, amt),
                                  purpose="Xuất kho hàng hỏng / hao hụt", docs=self.docs(case))
            self.fraud_put(case, r, "fake_issue_or_shrinkage_note")

    # ------------------------------------------------------------------ corruption
    def scheme_kickback_overpricing(self, case):
        rng = self.rng
        v = self.real_vendor(case, case["_start"], 200)
        lo, hi = {"L0": (1.25, 1.7), "L1": (1.18, 1.35), "L2": (1.10, 1.22)}[case["concealment"]]
        for at in self.times(case, rng.randint(3, 6)):
            markup = rng.uniform(lo, hi)
            amt = int(self.vendor_amount(v, at) * markup / 1000) * 1000
            r = self.tx(case, at, "vendor_payment", vendor=v, amount=amt, creator=self.creator_for(case), approver=self.approver_for(case, amt), price_markup=markup)
            self.fraud_put(case, r, "inflated_unit_price_colluding_pair")

    def scheme_price_creep(self, case):
        rng = self.rng
        v = self.real_vendor(case, case["_start"], 200)
        hard = case["concealment"] == "L2"
        growth = rng.uniform(.012, .02) if hard else rng.uniform(.02, .04)
        markup = 1.0
        for at in self.times(case, rng.randint(9, 12) if hard else rng.randint(6, 12)):
            amt = int(self.vendor_amount(v, at) * markup / 1000) * 1000
            r = self.tx(case, at, "vendor_payment", vendor=v, amount=amt, creator=self.creator_for(case), approver=self.approver_for(case, amt), price_markup=markup)
            if markup >= 1.08:
                self.fraud_put(case, r, "gradual_unit_price_increase")
            else:
                self.support_put(case, r)
            markup *= 1 + growth

    def scheme_bid_rotation(self, case):
        rng = self.rng
        legacy = self.real_vendor(case, case["_start"], 200)
        rep = self.identifier("PHONE_SYN_")
        ring = [self.shell(case, case["_start"] - timedelta(days=rng.randint(30, 400)),
                           representative_phone=rep if case["concealment"] != "L2" else None) for _ in range(rng.randint(2, 3))]
        markup = rng.uniform(1.15, 1.35)
        for v in ring:
            self.vprof[v["vendor_id"]].update(price=self.vprof[legacy["vendor_id"]]["price"] * markup, mu=self.vprof[legacy["vendor_id"]]["mu"], sigma=.25)
        for j, at in enumerate(self.times(case, rng.randint(4, 9))):
            v = ring[j % len(ring)]
            amt = int(self.vendor_amount(v, at) / 1000) * 1000
            r = self.tx(case, at, "vendor_payment", vendor=v, amount=amt, creator=self.creator_for(case), approver=self.approver_for(case, amt))
            r.update(goods_receipt_verified=1, support_doc_count=self.docs(case))
            self.fraud_put(case, r, "rotating_related_bidders_above_market")

    def scheme_undisclosed_related_vendor(self, case):
        rng, p, c = self.rng, self.employees[case["perpetrator_id"]], case["concealment"]
        base_vendor = self.real_vendor(case, case["_start"], 120)
        v = self.shell(case, case["_start"] - timedelta(days=rng.randint(10, 120)),
                       address=p["address"] if c != "L2" else None, phone=p["phone"] if c == "L0" else None)
        self.vprof[v["vendor_id"]].update(price=self.vprof[base_vendor["vendor_id"]]["price"] * rng.uniform(1.03, 1.15), mu=self.vprof[base_vendor["vendor_id"]]["mu"])
        for j, at in enumerate(self.times(case, rng.randint(4, 10))):
            amt = int(self.vendor_amount(v, at) * (1 + .08 * j) / 1000) * 1000
            r = self.tx(case, at, "vendor_payment", vendor=v, amount=amt, creator=self.creator_for(case), approver=self.approver_for(case, amt))
            r.update(goods_receipt_verified=1, support_doc_count=self.docs(case))
            self.fraud_put(case, r, "growing_volume_to_employee_linked_vendor")

    # ------------------------------------------------------------------ financial statements / owner
    def scheme_period_end_adjustment(self, case):
        rng = self.rng
        ends, d = [], case["_start"]
        while d <= case["_end"]:
            last = (d.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            if case["_start"] <= last <= case["_end"]:
                ends.append(last)
            d = last + timedelta(days=1)
        if not ends:
            raise NotApplicable
        for last in rng.sample(ends, min(len(ends), rng.randint(1, 3))):
            at = (last - timedelta(days=rng.randint(0, 4))).replace(hour=22 if case["concealment"] == "L0" else 19, minute=rng.randrange(60), second=0)
            at = self.clamp(at, case["split"])
            amt = self.amount(case, 0, base=self.velocity(case) * 2)
            r = self.tx(case, at, "adjustment", amount=amt, creator=self.creator_for(case), approver=self.approver_for(case, amt), delay_hours=rng.choice([.05, .5, 4]))
            r.update(approver_id=self.approver_for(case, amt), support_doc_count=self.docs(case), goods_receipt_verified=0)
            if rng.random() < .5:
                r.update(debit_account="131", credit_account="511")
            self.fraud_put(case, r, "manual_entry_near_close")

    def scheme_fictitious_revenue_cutoff(self, case):
        rng, cid = self.rng, case["company_id"]
        qends = [datetime(y, m, 31 if m in (3, 12) else 30, 15, tzinfo=TZ) for y in (2024, 2025) for m in (3, 6, 9, 12)]
        qends = [q for q in qends if case["_start"] <= q <= case["_end"] - timedelta(days=20)]
        if not qends:
            raise NotApplicable
        q = rng.choice(qends)
        cu = rng.choice(self.company_customers[cid])
        gross = int(math.exp(self.customer_prof[cu]["mu"]) * rng.uniform(2, 5) / 1000) * 1000
        at = self.clamp(_workday(q - timedelta(days=rng.randint(0, 2)), forward=False), case["split"])
        r = self.tx(case, at, "sales_invoice", amount=gross, creator=self.creator_for(case), approver=self.approver_for(case, gross))
        r.update(customer_id=cu, recipient_account=self.customers[cu]["bank_account"], invoice_id=self.identifier("I"),
                 invoice_number=f"HDB{rng.randrange(1, 10**7):07d}", invoice_issued_at=r["posted_at"], invoice_gross_vnd=gross)
        self.fraud_put(case, r, "revenue_booked_at_quarter_end")
        back = self.clamp(at + timedelta(days=rng.randint(5, 25)), case["split"])
        kind = "sales_return" if case["concealment"] != "L0" else "bad_debt_writeoff"
        rev = self.new_kind_row(cid, back, kind, gross, self.creator_for(case), self.approver_for(case, gross), customer_id=cu,
                                purpose="Điều chỉnh doanh thu", docs=self.docs(case))
        rev["applied_invoice_id"] = r["invoice_id"]
        self.fraud_put(case, rev, "reversed_next_period")

    def scheme_owner_override_transfer(self, case):
        rng, cid = self.rng, case["company_id"]
        d = self.employees[self.company_staff[cid][0]]
        for at in self.times(case, rng.randint(1, 3)):
            amt = max(10, int(rng.uniform(40, 250) * self.profile[cid]["scale"])) * 1_000_000
            r = self.tx(case, at, "advance_issue", employee=d, amount=amt, creator=d["employee_id"], approver=d["employee_id"])
            r.update(approver_id=d["employee_id"], support_doc_count=self.docs(case), business_purpose="Tạm ứng công tác")
            self.fraud_put(case, r, "director_self_approved_advance_never_settled")

    # ------------------------------------------------------------------ extra legitimate look-alikes
    def inject_hard_negatives(self):
        super().inject_hard_negatives()
        rng = self.rng
        for cid in self.company_staff:
            d = self.employees[self.company_staff[cid][0]]
            chief = self.company_staff[cid][1]
            for split in WINDOWS:
                for _ in range(rng.randint(0, 2)):
                    at = self.clamp(self.random_time(split, 30), split)
                    amt = max(10, int(rng.uniform(20, 150) * self.profile[cid]["scale"])) * 1_000_000
                    r = self.transaction(cid, split, at, "advance_issue", employee=d, amount=amt, creator=chief, approver=d["employee_id"])
                    r["support_doc_count"] = 3
                    self.put(split, r, hard="legit_director_advance")
                    back = self.clamp(at + timedelta(days=rng.randint(7, 25)), split)
                    s = self.transaction(cid, split, back, "advance_settlement", employee=d, amount=amt, creator=chief)
                    s["support_doc_count"] = 3
                    self.put(split, s, hard="legit_director_advance")
                if rng.random() < .4:
                    at = self.clamp(self.random_time(split, 20), split)
                    at = self.clamp(at.replace(day=min(18, max(8, at.day))), split)
                    e = self.employees[rng.choice(self.company_staff[cid][6:])]
                    if self.active(e, at):
                        r = self.transaction(cid, split, at, "payroll", employee=e, creator=chief, approver=self.company_staff[cid][0])
                        r["amount_vnd"] = int(e["monthly_salary_vnd"] * rng.uniform(.3, .6) / 1000) * 1000
                        r["support_doc_count"] = rng.choice([3, 4])
                        self.put(split, r, hard="legit_offcycle_payroll")
