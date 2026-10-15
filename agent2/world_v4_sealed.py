"""Sealed world v4: new seeds, a shifted population and seven schemes never used while developing detectors.

Written on 2026-10-14 before any detector was run on these worlds; evaluated exactly once with the configuration frozen
in AGENT2_WORKLOG.md section 14. During that evaluation the labels of the seven new schemes are hidden from training
(the rows stay, labelled 0, as undiscovered fraud in the firm's history) and counted as fraud only in the test period.

New schemes (ACFE fraud-tree branch; source):
  phantom_sales_real_dealers  financial statements / sales: invoices to the salesperson's real dealers for goods never
                              shipped, never collected (Sebang Battery Vina case, Tuoi Tre / PLO 2023: 58 fake invoices
                              to 18 real dealers, 6.9 billion VND); closed later by a return or a write-off
  underpriced_sales_kickback  corruption, conflict of interest, sales scheme: repeated invoices to one customer far below
                              that customer's usual amounts (same case: goods sold to dealers 8-10 percent below list;
                              ACFE fraud tree "sales schemes")
  cash_withdrawal_skim        cash larceny: extra bank-to-cash withdrawals off the cash plan, kept by the cashier
                              (Bao Dinh cashier case, PLO: cash book balances altered, 442 million VND)
  advance_kiting              expense / advances: each new advance settles the previous one, amounts grow, last one open
  overtime_inflation_group    payroll, falsified wages: several workers' pay raised at once by the payroll preparer
                              (near variant of payroll_padding, reported separately)
  fake_lease_vendor           billing: a new "landlord" paid a fixed monthly rent for a warehouse that does not exist
  fake_tax_payment            payment tampering: extra tax payments routed to an account that is not the treasury
Population shift: 35 percent of firms get new pay calendars (1st, 20th, or 7th and 22nd); 40 firms instead of 48.
New legitimate look-alikes: legit_volume_discount, legit_extra_withdrawal, legit_overtime_peak, legit_new_lease,
legit_tax_installment.
"""
from __future__ import annotations

import calendar
import math
from datetime import datetime, timedelta
from pathlib import Path

from sme_fraud.generate import TZ, WINDOWS, parse, save_dataset, stamp

from .world_v4 import WorldV4, working_day
from .world_v4_schemes import SCHEMES, SPLIT_WEIGHTS, NotApplicable, _workday

NOVEL = {
    "phantom_sales_real_dealers": ("financial_statement", .15, ("sales",), "hóa đơn bán khống cho đại lý thật (vụ Sebang Battery Vina 6,9 tỷ)"),
    "underpriced_sales_kickback": ("corruption", .15, ("sales",), "bán giá thấp cho một khách để nhận lại quả; ACFE sales schemes"),
    "cash_withdrawal_skim": ("cash_larceny", .14, ("cashier",), "rút tiền ngân hàng về quỹ ngoài kế hoạch rồi giữ lại (vụ thủ quỹ Bảo Định)"),
    "advance_kiting": ("expense", .14, ("sales", "operations", "purchasing", "warehouse"), "tạm ứng sau hoàn tạm ứng trước"),
    "overtime_inflation_group": ("payroll", .14, ("chief_accountant", "accountant", "hr"), "nâng lương làm thêm cho cả nhóm công nhân"),
    "fake_lease_vendor": ("billing", .14, ("chief_accountant", "director", "accountant"), "hợp đồng thuê kho khống, trả tiền thuê hằng tháng"),
    "fake_tax_payment": ("payment_tampering", .14, ("accountant", "chief_accountant"), "lập ủy nhiệm chi nộp thuế khống sang tài khoản khác"),
}
NOVEL_SHARE = .40


class WorldV4Sealed(WorldV4):
    catalog = {**SCHEMES, **NOVEL}

    def make_masters(self, count):
        super().make_masters(count)
        rows = {r["company_id"]: r for r in self.tables["companies"]}
        for cid, prof in self.profile.items():
            if self.rng.random() < .35:
                prof["pay_days"] = self.rng.choice([[1], [20], [7, 22]])
                rows[cid]["pay_days"] = "|".join(map(str, prof["pay_days"]))

    # ------------------------------------------------------------------ driver
    def inject_fraud(self):
        rng = self.rng
        target = round(self.n * self.rate)
        comps = [c for c, p in self.profile.items() if p["fraud_mu"] > 0]
        weights = [self.profile[c]["fraud_mu"] * self.profile[c]["n_staff"] ** .5 for c in comps]
        created = 0
        for scheme in NOVEL:
            for split in SPLIT_WEIGHTS:
                created += self.try_case(scheme, comps, weights, split)
        for scheme in SCHEMES:
            created += self.try_case(scheme, comps, weights, "test")
        known, novel = list(SCHEMES), list(NOVEL)
        attempts = 0
        while created < target and attempts < 20_000:
            attempts += 1
            if rng.random() < NOVEL_SHARE:
                scheme = rng.choices(novel, [NOVEL[s][1] for s in novel])[0]
            else:
                scheme = rng.choices(known, [SCHEMES[s][1] for s in known])[0]
            created += self.try_case(scheme, comps, weights)

    # ------------------------------------------------------------------ helpers
    def my_customers(self, case):
        cus = [c for c in self.company_customers[case["company_id"]] if self.customer_prof[c]["manager"] == case["perpetrator_id"]]
        if not cus:
            raise NotApplicable
        return cus

    def invoice_row(self, case, at, cu, gross, creator, approver):
        r = self.tx(case, at, "sales_invoice", amount=gross, creator=creator, approver=approver)
        r.update(customer_id=cu, recipient_account=self.customers[cu]["bank_account"], invoice_id=self.identifier("I"),
                 invoice_number=f"HDB{self.rng.randrange(1, 10**7):07d}", invoice_issued_at=r["posted_at"], invoice_gross_vnd=gross)
        return r

    def receipt_row(self, cid, split, inv, cu, collector, after_days):
        at = working_day(self.day_time(parse(inv["posted_at"]) + timedelta(days=after_days)), backward=False)
        at = self.clamp(at, split)
        if at <= parse(inv["posted_at"]):
            return None
        rc = self.transaction(cid, split, at, "customer_receipt", amount=inv["amount_vnd"], creator=self.rng.choice(self.company_staff[cid][3:6]))
        rc.update(customer_id=cu, recipient_account=self.customers[cu]["bank_account"], applied_invoice_id=inv["invoice_id"],
                  payer_account=self.customers[cu]["bank_account"], collector_id=collector, support_doc_count=self.rng.choice([1, 1, 2]))
        return rc

    def months_in(self, a, b, day):
        out, d = [], a.replace(day=1)
        while d <= b:
            last = calendar.monthrange(d.year, d.month)[1]
            at = _workday(datetime(d.year, d.month, min(day, last), self.rng.randint(9, 16), self.rng.randrange(60), tzinfo=TZ))
            if a <= at <= b:
                out.append(at)
            d = (d + timedelta(days=32)).replace(day=1)
        return out

    # ------------------------------------------------------------------ new schemes
    def scheme_phantom_sales_real_dealers(self, case):
        rng, cid, c = self.rng, case["company_id"], case["concealment"]
        cus = self.my_customers(case)
        for at in self.times(case, rng.randint(3, 8)):
            cu = rng.choice(cus)
            mu = self.customer_prof[cu]["mu"]
            gross = math.exp(mu) * rng.uniform(2, 4) if c == "L0" else rng.lognormvariate(mu, .5) * (rng.uniform(1.2, 2) if c == "L1" else 1)
            gross = max(500_000, int(gross / 1000) * 1000)
            inv = self.invoice_row(case, at, cu, gross, case["perpetrator_id"], self.approver_for(case, gross))
            inv["support_doc_count"] = self.docs(case)
            self.fraud_put(case, inv, "invoice_for_goods_never_shipped")
            if c == "L0":
                continue
            delay = rng.randint(20, 60) if c == "L1" else rng.randint(150, 220)
            when = working_day(self.day_time(at + timedelta(days=delay)), backward=False)
            if when >= WINDOWS[case["split"]][1] - timedelta(days=1):
                continue
            kind = "sales_return" if c == "L1" else "bad_debt_writeoff"
            close = self.new_kind_row(cid, when, kind, gross, self.creator_for(case), self.approver_for(case, gross), customer_id=cu,
                                      purpose="Hàng bán bị trả lại" if kind == "sales_return" else "Xóa nợ khó đòi", docs=self.docs(case))
            close["applied_invoice_id"] = inv["invoice_id"]
            self.fraud_put(case, close, "phantom_invoice_closed_by_" + kind)

    def scheme_underpriced_sales_kickback(self, case):
        rng, cid, c = self.rng, case["company_id"], case["concealment"]
        cu = rng.choice(self.my_customers(case))
        lo, hi = {"L0": (.35, .5), "L1": (.2, .35), "L2": (.1, .2)}[c]
        retail_like = self.profile[cid]["industry"] in ("trading", "retail")
        for at in self.times(case, rng.randint(4, 10)):
            normal = rng.lognormvariate(self.customer_prof[cu]["mu"], .5)
            gross = max(200_000, int(normal * (1 - rng.uniform(lo, hi)) / 1000) * 1000)
            inv = self.invoice_row(case, at, cu, gross, case["perpetrator_id"], self.approver_for(case, gross))
            inv["support_doc_count"] = self.docs(case)
            self.fraud_put(case, inv, "invoice_far_below_customer_usual_price")
            if retail_like:
                cogs = self.tx(case, at, "cogs", amount=max(50_000, int(normal / 1.1 * rng.uniform(.7, .85) / 1000) * 1000),
                               creator=rng.choice(self.company_staff[cid][3:6]))
                self.support_put(case, cogs)
            rc = self.receipt_row(cid, case["split"], inv, cu, case["perpetrator_id"], self.profile[cid]["customer_terms"] - rng.randint(0, 10))
            if rc is not None:
                self.support_put(case, rc)

    def scheme_cash_withdrawal_skim(self, case):
        rng, cid, c = self.rng, case["company_id"], case["concealment"]
        scale = self.profile[cid]["scale"]
        months = max(1, (case["_end"] - case["_start"]).days // 30)
        for at in self.times(case, months * rng.randint(1, 2), odd=c == "L0"):
            if c == "L2":
                anchor = rng.choice([8, 22])
                at = self.clamp(_workday(at.replace(day=anchor, hour=10) + timedelta(days=rng.choice([-3, -2, 2, 3]))), case["split"])
                if not (case["_start"] <= at <= case["_end"]):
                    continue
            amt = max(1, int(round(rng.uniform(1, 5) * scale))) * 5_000_000
            approver = case["perpetrator_id"] if c == "L0" else self.approver_for(case, amt)
            r = self.new_kind_row(cid, at, "cash_withdrawal", amt, case["perpetrator_id"], approver, purpose="Rút tiền về quỹ",
                                  docs=0 if c == "L0" else 1)
            self.fraud_put(case, r, "unplanned_withdrawal_kept_by_cashier")

    def scheme_advance_kiting(self, case):
        rng, cid, c = self.rng, case["company_id"], case["concealment"]
        e = self.employees[case["perpetrator_id"]]
        span = max(10, (case["_end"] - case["_start"]).days)
        k = rng.randint(3, 6)
        gap = max(6, span // k)
        amount = rng.choice([3, 5, 8, 10]) * 1_000_000
        at = case["_start"]
        accountants = self.company_staff[cid][3:6]
        for j in range(k):
            if at > case["_end"]:
                break
            aid = self.identifier("A")
            issue = self.tx(case, at, "advance_issue", employee=e, amount=amount, creator=rng.choice(accountants),
                            approver=self.approver_for(case, amount))
            issue.update(advance_id=aid, support_doc_count=self.docs(case), business_purpose="Tạm ứng công tác / mua hàng")
            if j == 0:
                tid = self.put(case["split"], issue, case=case["case_id"], support=True)
            else:
                self.fraud_put(case, issue, "new_advance_settles_previous_one")
                tid = issue["transaction_id"]
            self.tables["advances"].append(dict(advance_id=aid, company_id=cid, employee_id=e["employee_id"], issue_transaction_id=tid,
                                                issued_at=stamp(at), recorded_at=stamp(at), original_due_at=stamp(at + timedelta(days=30)),
                                                original_amount_vnd=amount))
            nxt = self.clamp(at + timedelta(days=gap + rng.randint(-2, 3)), case["split"])
            settle = nxt + timedelta(days=rng.randint(1, 3), hours=rng.randint(0, 3))
            if j < k - 1 and settle < WINDOWS[case["split"]][1] - timedelta(days=1) and nxt <= case["_end"]:
                s = self.tx(case, settle, "advance_settlement", employee=e, amount=amount, creator=rng.choice(accountants))
                s.update(advance_id=aid, support_doc_count=self.docs(case))
                stid = self.put(case["split"], s, case=case["case_id"], support=True)
                self.tables["advance_events"].append(dict(event_id=self.identifier("AE"), advance_id=aid, company_id=cid, event_type="settlement",
                                                          observed_at=stamp(settle), new_due_at="", amount_vnd=amount, transaction_id=stid,
                                                          evidence_on_file=int(c == "L2")))
            amount = int(amount * rng.uniform(1.1, 1.3) / 1_000_000 + .5) * 1_000_000
            at = nxt

    def scheme_overtime_inflation_group(self, case):
        rng, cid, c = self.rng, case["company_id"], case["concealment"]
        crew = [x for x in self.company_staff[cid][9:] if self.employees[x]["role"] in ("operations", "warehouse")
                and self.active(self.employees[x], case["_start"]) and self.active(self.employees[x], case["_end"])]
        if len(crew) < 3:
            raise NotApplicable
        lo, hi = {"L0": (1.25, 1.45), "L1": (1.12, 1.25), "L2": (1.06, 1.12)}[c]
        for eid in rng.sample(crew, min(len(crew), rng.randint(3, 6))):
            factor = rng.uniform(lo, hi)
            for i in self.payroll_rows.get((cid, eid), []):
                if i in self.used or not (case["_start"] <= parse(self.rows[i]["posted_at"]) <= case["_end"]):
                    continue
                self.fraud_mutate(case, i, "crew_pay_raised_by_preparer", amount_vnd=int(round(self.rows[i]["amount_vnd"] * factor / 1000)) * 1000,
                                  creator_id=case["perpetrator_id"])

    def scheme_fake_lease_vendor(self, case):
        rng, cid, c = self.rng, case["company_id"], case["concealment"]
        p = self.employees[case["perpetrator_id"]]
        onboard = case["_start"] - timedelta(days=rng.randint(10, 60))
        v = self.shell(case, onboard, bank=p["bank_account"] if c == "L0" else None, address=p["address"] if c == "L1" else None)
        self.vcat[v["vendor_id"]] = "landlord"
        rent = max(3, int(rng.uniform(5, 30) * self.profile[cid]["scale"] ** .5)) * 1_000_000
        dates = self.months_in(case["_start"], case["_end"], rng.randint(1, 10))
        if len(dates) < 2:
            raise NotApplicable
        for at in dates:
            r = self.tx(case, at, "rent", vendor=v, amount=rent, creator=self.creator_for(case), approver=self.approver_for(case, rent))
            r.update(support_doc_count=self.docs(case), business_purpose="Thanh toán tiền thuê kho", goods_receipt_verified=0)
            self.fraud_put(case, r, "monthly_rent_for_nonexistent_warehouse")

    def scheme_fake_tax_payment(self, case):
        rng, cid, c = self.rng, case["company_id"], case["concealment"]
        p = self.employees[case["perpetrator_id"]]
        tax_day = self.profile[cid]["tax_day"]
        for at in self.times(case, rng.randint(2, 5), odd=c == "L0"):
            if c == "L2":
                at = self.clamp(_workday(at.replace(day=min(28, tax_day + rng.choice([-2, -1, 1, 2])), hour=rng.randint(9, 16))), case["split"])
                if not (case["_start"] <= at <= case["_end"]):
                    continue
            amt = int(max(.3, rng.gauss(1, .15)) * 6_000_000 * self.profile[cid]["scale"] / 1000) * 1000
            if c == "L0":
                amt = int(amt * rng.uniform(2, 3) / 1_000_000 + .5) * 1_000_000
            r = self.tx(case, at, "tax_payment", amount=amt, creator=self.creator_for(case), approver=self.approver_for(case, amt))
            dest = p["bank_account"] if c == "L0" else self.identifier("BANK_SYN_") if c == "L1" else ""
            r.update(recipient_account=dest, payment_channel="bank" if dest else r["payment_channel"], support_doc_count=self.docs(case),
                     business_purpose="Nộp thuế")
            self.fraud_put(case, r, "tax_payment_to_non_treasury_account")

    # ------------------------------------------------------------------ new legitimate look-alikes
    def inject_hard_negatives(self):
        super().inject_hard_negatives()
        rng = self.rng
        for cid in self.company_staff:
            staff = self.company_staff[cid]
            director, chief, cashier = staff[0], staff[1], staff[2]
            scale = self.profile[cid]["scale"]
            for split in WINDOWS:
                a, b = WINDOWS[split]
                for _ in range(rng.randint(0, 2)):                       # volume discount for the largest customer
                    cu = self.company_customers[cid][0]
                    at = self.clamp(self.random_time(split, 20).replace(hour=rng.randint(9, 16)), split)
                    gross = max(500_000, int(rng.lognormvariate(self.customer_prof[cu]["mu"], .5) * rng.uniform(.65, .85) / 1000) * 1000)
                    r = self.transaction(cid, split, at, "sales_invoice", amount=gross, creator=chief, approver=director)
                    r.update(customer_id=cu, recipient_account=self.customers[cu]["bank_account"], invoice_id=self.identifier("I"),
                             invoice_number=f"HDB{rng.randrange(1, 10**7):07d}", invoice_issued_at=r["posted_at"], invoice_gross_vnd=gross,
                             support_doc_count=rng.choice([3, 4]), business_purpose="Chiết khấu thương mại theo hợp đồng khung")
                    self.put(split, r, hard="legit_volume_discount")
                    rc = self.receipt_row(cid, split, r, cu, self.customer_prof[cu]["manager"], self.profile[cid]["customer_terms"])
                    if rc is not None:
                        self.put(split, rc)
                for _ in range(rng.randint(0, 2)):                       # extra withdrawal for a documented cash purchase
                    at = self.clamp(_workday(self.random_time(split, 5)).replace(hour=rng.randint(9, 15)), split)
                    amt = max(1, int(round(rng.uniform(1, 6) * scale))) * 5_000_000
                    r = self.new_kind_row(cid, at, "cash_withdrawal", amt, cashier, director, purpose="Rút tiền mặt thanh toán hàng nông sản",
                                          docs=rng.choice([2, 3]))
                    self.put(split, r, hard="legit_extra_withdrawal")
                if rng.random() < .5:                                    # peak-season overtime for a crew, approved by the director
                    month_start = self.clamp(self.random_time(split, 40), split).replace(day=1)
                    month_end = (month_start + timedelta(days=32)).replace(day=1)
                    crew = [x for x in staff[9:] if self.employees[x]["role"] in ("operations", "warehouse")]
                    for eid in rng.sample(crew, min(len(crew), rng.randint(4, 8))):
                        for i in self.payroll_rows.get((cid, eid), []):
                            if i not in self.used and month_start <= parse(self.rows[i]["posted_at"]) < month_end and a <= parse(self.rows[i]["posted_at"]) < b:
                                self.mutate(i, hard="legit_overtime_peak", amount_vnd=int(round(self.rows[i]["amount_vnd"] * rng.uniform(1.1, 1.3) / 1000)) * 1000,
                                            support_doc_count=4)
                if rng.random() < .3:                                    # a genuine new warehouse lease
                    start = self.clamp(self.random_time(split, 60), split)
                    v = self.new_shell_vendor(cid, start - timedelta(days=rng.randint(5, 30)))
                    self.vcat[v["vendor_id"]] = "landlord"
                    rent = max(3, int(rng.uniform(5, 30) * scale ** .5)) * 1_000_000
                    for at in self.months_in(start, b - timedelta(days=3), rng.randint(1, 10))[: rng.randint(2, 6)]:
                        r = self.transaction(cid, split, at, "rent", vendor=v, amount=rent, creator=rng.choice(staff[3:6]), approver=director)
                        r["support_doc_count"] = 3
                        self.put(split, r, hard="legit_new_lease")
                if rng.random() < .5:                                    # tax paid in an extra instalment
                    at = self.clamp(_workday(self.random_time(split, 10)).replace(hour=rng.randint(9, 16)), split)
                    amt = int(max(.3, rng.gauss(1, .2)) * 6_000_000 * scale / 1000) * 1000
                    r = self.transaction(cid, split, at, "tax_payment", amount=amt, creator=rng.choice(staff[3:6]), approver=chief)
                    r["support_doc_count"] = 3
                    self.put(split, r, hard="legit_tax_installment")


def generate_v4_sealed(output, n=200_000, rate=.004, seed=931, companies=40):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty dataset: {output}")
    g = WorldV4Sealed(n, rate, seed, companies)
    tables = g.finalize()
    return save_dataset(output, tables, n, rate, seed, companies)
