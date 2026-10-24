"""Encoding of the independent author's ten scenarios and their twenty look-alikes (registration v6.2).

Source prose: docs/05_ke_hoach_giao_viec/independent_scenarios/scenarios_v5.md (SHA-256 3723fb9d...02cc). Rules:
no new tables or columns (v6.2); cases are cut inside the test window; nothing is tuned to a detector; every field a
scenario fills is also filled by a legitimate look-alike at a natural rate (V13 on the dry-run world checks this).
`applied_invoice_id` and `collector_id` are never set on fraud rows (the R1 v1.3 shortcut). A scheme method decides
whether it is applicable BEFORE it writes its first row, so an abandoned attempt leaves no orphan rows. Adaptations
forced by the current schema are listed in independent_scenarios/encoding_notes_v5.md. All data are dữ liệu tổng hợp.
"""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta

from sme_fraud.generate import TZ, WINDOWS, parse, stamp

from .world_v4_schemes import NotApplicable, _workday

# name: (ACFE branch, weight, perpetrator roles, reference). Branch names are the ten used by the generator.
NOVEL_V5 = {
    "ar_skim_writedown": ("skimming", .10, ("sales",), "V5-KB01 thu tiền công nợ ngoài sổ, che bằng giảm giá, chiết khấu, xóa nợ"),
    "vendor_refund_diverted": ("skimming", .10, ("purchasing",), "V5-KB02 chặn tiền hoàn cọc của nhà cung cấp"),
    "inflated_trip_settlement": ("expense", .10, ("sales",), "V5-KB03 kê tăng ngày và quãng đường công tác phí"),
    "severance_inflation": ("payroll", .10, ("hr", "chief_accountant"), "V5-KB04 kê tăng trợ cấp thôi việc"),
    "fake_referral_commission": ("corruption", .10, ("sales",), "V5-KB05 hoa hồng giới thiệu cho cộng tác viên không có thật"),
    "related_asset_disposal": ("noncash", .10, ("chief_accountant", "director"), "V5-KB06 thanh lý tài sản cho người mua có quan hệ"),
    "truck_outside_hauling": ("noncash", .10, ("operations", "warehouse"), "V5-KB07 dùng xe tải công ty chở hàng thuê"),
    "payment_priority_bribe": ("corruption", .10, ("accountant", "chief_accountant"), "V5-KB08 đòi phí để thanh toán đúng hạn"),
    "period_end_cutoff_shift": ("financial_statement", .10, ("chief_accountant", "accountant"), "V5-KB09 dời ghi nhận chi phí cuối kỳ"),
    "related_dealer_credit": ("corruption", .10, ("director", "chief_accountant"), "V5-KB10 nới hạn nợ cho khách có quan hệ"),
}
NEW_DECOYS_V5 = (
    "dissolved_customer_writeoff", "supplier_defect_discount", "contract_deposit_forfeit", "deposit_settled_by_invoice",
    "trip_extended_incident", "seasonal_peak_trips", "severance_formula_paid", "layoff_wave_severance",
    "registered_referrer_commission", "reactivated_customer_commission", "scrap_asset_disposal", "depreciation_group_change",
    "hauling_service_invoiced", "urgent_sunday_delivery", "uniform_slow_payment", "early_payment_discount",
    "periodic_utility_lag", "post_period_bonus_decision", "seasonal_credit_policy", "structured_debt_extension",
)

FUEL_PRICE = 22_000


class ScenarioMixin:
    # ------------------------------------------------------------------ shared helpers
    def _index(self):
        if not hasattr(self, "_kind_rows"):
            self._kind_rows = {}
            for i, r in enumerate(self.rows):
                self._kind_rows.setdefault((r["company_id"], r["txn_type"]), []).append(i)
        return self._kind_rows

    def _accountants(self, cid):
        return self.company_staff[cid][3:6]

    def _scale(self, cid):
        return self.profile[cid]["scale"]

    def _money(self, cid, lo, hi, unit=1_000_000):
        return max(1, int(self.rng.uniform(lo, hi) * self._scale(cid) ** .5)) * unit

    def _after(self, case, base, lo, hi):
        """`base` plus a random lag in days, or None when it would leave the split window (cases are cut, v6.2)."""
        when = _workday(base + timedelta(days=self.rng.randint(lo, hi))).replace(hour=self.rng.randint(9, 16))
        return when if when < WINDOWS[case["split"]][1] - timedelta(days=2) else None

    def _workday_time(self, split, margin=20):
        return self.clamp(_workday(self.random_time(split, margin)).replace(hour=self.rng.randint(9, 16)), split)

    def _sunday(self, at, split):
        return self.clamp((at + timedelta(days=(6 - at.weekday()) % 7)).replace(hour=self.rng.randint(8, 11)), split)

    def _opposite(self, case, kind, at, amount, cu, purpose, docs, variant):
        """Adjustment-type row tied to a customer (no applied_invoice_id, no collector_id)."""
        if kind in ("sales_return", "bad_debt_writeoff", "inventory_writeoff", "customer_refund", "cash_withdrawal"):
            row = self.new_kind_row(case["company_id"], at, kind, amount, self.creator_for(case), self.approver_for(case, amount),
                                    customer_id=cu, purpose=purpose, docs=docs)
        else:
            row = self.tx(case, at, kind, amount=amount, creator=self.creator_for(case), approver=self.approver_for(case, amount))
            row.update(customer_id=cu, business_purpose=purpose, support_doc_count=docs)
        self.fraud_put(case, row, variant)

    def _advance_pair(self, case, at, amount, qty, unit, fraud, employee):
        """Advance issued (support) then settled with quantity and unit price on the settlement (fraud when asked)."""
        rng, cid = self.rng, case["company_id"]
        settle = self._after(case, at, 2, 5)
        if settle is None:
            return False
        aid, accountants = self.identifier("A"), self._accountants(cid)
        issue = self.tx(case, at, "advance_issue", employee=employee, amount=amount, creator=rng.choice(accountants),
                        approver=self.approver_for(case, amount))
        issue.update(advance_id=aid, support_doc_count=self.docs(case), business_purpose="Tạm ứng công tác")
        tid = self.put(case["split"], issue, case=case["case_id"], support=True)
        self.tables["advances"].append(dict(advance_id=aid, company_id=cid, employee_id=employee["employee_id"], issue_transaction_id=tid,
                                            issued_at=stamp(at), recorded_at=stamp(at), original_due_at=stamp(at + timedelta(days=30)),
                                            original_amount_vnd=amount))
        s = self.tx(case, settle, "advance_settlement", employee=employee, amount=amount, creator=rng.choice(accountants))
        s.update(advance_id=aid, support_doc_count=self.docs(case), unit_price_vnd=int(unit), quantity=qty,
                 business_purpose="Quyết toán công tác phí")
        if fraud:
            self.fraud_put(case, s, "per_diem_days_or_distance_overstated")
            stid = s["transaction_id"]
        else:
            stid = self.put(case["split"], s, case=case["case_id"], support=True)
        self.tables["advance_events"].append(dict(event_id=self.identifier("AE"), advance_id=aid, company_id=cid, event_type="settlement",
                                                  observed_at=stamp(settle), new_due_at="", amount_vnd=amount, transaction_id=stid,
                                                  evidence_on_file=int(case["concealment"] == "L2")))
        return True

    # ------------------------------------------------------------------ KB01 receivables skimmed, covered by write-downs
    def scheme_ar_skim_writedown(self, case):
        rng, c = self.rng, case["concealment"]
        cus = self.my_customers(case)
        chosen = rng.sample(cus, min(len(cus), {"L0": 1, "L1": rng.randint(3, 5), "L2": rng.randint(5, 8)}[c]))
        for cu in chosen:
            for at in self.times(case, rng.randint(1, 2)):
                when = self._after(case, at, 20, 120) if c != "L0" else self._after(case, at, 150, 260)
                if when is None:
                    continue
                gross = max(500_000, int(rng.lognormvariate(self.customer_prof[cu]["mu"], .5) / 1000) * 1000)
                inv = self.invoice_row(case, at, cu, gross, case["perpetrator_id"], self.approver_for(case, gross))
                inv["support_doc_count"] = self.docs(case)
                self.support_put(case, inv)                      # the customer paid the salesperson: no receipt row exists
                if c == "L0":                                    # unprovided write-off, no dissolution record
                    self._opposite(case, "bad_debt_writeoff", when, gross, cu, "Xóa nợ cửa hàng đã đóng cửa", rng.choice([0, 1]),
                                   "writeoff_without_provision_or_dissolution")
                elif c == "L1":                                  # quality discount signed by the customer
                    self._opposite(case, "adjustment", when, int(gross * rng.uniform(.05, .12) / 1000) * 1000, cu,
                                   "Giảm giá hàng bán do lỗi chất lượng", rng.choice([2, 3]), "quality_discount_on_skimmed_invoice")
                else:                                            # payment discount at policy rate, then documented write-off
                    self._opposite(case, "adjustment", when, int(gross * rng.uniform(.01, .02) / 1000) * 1000, cu,
                                   "Chiết khấu thanh toán", rng.choice([3, 4]), "policy_rate_payment_discount")
                    later = self._after(case, when, 30, 90)
                    if later is not None:
                        self._opposite(case, "bad_debt_writeoff", later, int(gross * .8 / 1000) * 1000, cu,
                                       "Xóa nợ khách ngừng kinh doanh, có hồ sơ", rng.choice([3, 4]), "documented_writeoff_of_skimmed_balance")

    # ------------------------------------------------------------------ KB02 vendor deposit refund diverted
    def scheme_vendor_refund_diverted(self, case):
        rng, cid, c = self.rng, case["company_id"], case["concealment"]
        plan = []
        for _ in range({"L0": 1, "L1": rng.randint(2, 3), "L2": rng.randint(1, 2)}[c]):
            at = self.times(case, 1)[0]
            when = self._after(case, at, 30, 120)
            if when is not None:
                plan.append((at, when, self.real_vendor(case, at)))
        if not plan:
            raise NotApplicable
        for at, when, v in plan:
            deposit = self._money(cid, 40, 350)
            dep = self.tx(case, at, "vendor_payment", vendor=v, amount=deposit, creator=rng.choice(self._accountants(cid)),
                          approver=self.approver_for(case, deposit))
            dep.update(goods_receipt_verified=0, support_doc_count=self.docs(case), business_purpose="Đặt cọc đơn hàng")
            self.support_put(case, dep)
            if c == "L2":                                        # partial cancellation: fee row looks like a normal change fee
                amount, purpose, docs = int(deposit * rng.uniform(.18, .3) / 1000) * 1000, "Phí giảm số lượng theo phụ lục", rng.choice([3, 4])
            else:
                amount, purpose, docs = deposit, "Mất cọc, phí hủy đơn", rng.choice([0, 1]) if c == "L0" else rng.choice([2, 2, 3])
            r = self.tx(case, when, "adjustment", vendor=v, amount=amount, creator=self.creator_for(case), approver=self.approver_for(case, amount))
            r.update(business_purpose=purpose, support_doc_count=docs)
            self.fraud_put(case, r, "deposit_booked_as_lost_refund_diverted")

    # ------------------------------------------------------------------ KB03 per-diem days or distance overstated
    def scheme_inflated_trip_settlement(self, case):
        rng, cid, c = self.rng, case["company_id"], case["concealment"]
        people = [case["perpetrator_id"]]
        if c == "L2":
            others = [x for x in self.company_staff[cid] if self.employees[x]["role"] == "sales" and x != people[0]
                      and self.active(self.employees[x], case["_start"]) and self.active(self.employees[x], case["_end"])]
            people += rng.sample(others, min(2, len(others)))
        unit = rng.choice([300_000, 400_000, 500_000]) * max(1, int(round(self._scale(cid) ** .5)))
        for pid in people:
            for at in self.times(case, {"L0": rng.randint(3, 5), "L1": rng.randint(4, 8), "L2": rng.randint(5, 9)}[c]):
                honest = rng.randint(2, 3)
                if c == "L0":
                    at, extra = self._sunday(at, case["split"]), rng.randint(1, 2)
                elif c == "L1":
                    extra = 1
                else:
                    extra = 1 if rng.random() < .4 else 0
                days = honest + extra
                self._advance_pair(case, at, unit * days, days, unit, extra > 0, self.employees[pid])

    # ------------------------------------------------------------------ KB04 severance inflated on an existing final settlement
    def scheme_severance_inflation(self, case):
        rng, cid, c = self.rng, case["company_id"], case["concealment"]
        low, high = case["_start"], case["_end"]
        pool = [i for i in self._index().get((cid, "payroll"), []) if i not in self.used
                and self.truth[i]["hard_negative_type"] == "legit_final_settlement"
                and low <= parse(self.rows[i]["posted_at"]) <= high]
        if not pool:
            raise NotApplicable
        picked = rng.sample(pool, min(len(pool), {"L0": 1, "L1": rng.randint(1, 2), "L2": rng.randint(1, 3)}[c]))
        factor = {"L0": (2.5, 4.0), "L1": (1.35, 1.5), "L2": (1.0, 1.08)}[c]
        for i in picked:
            self.fraud_mutate(case, i, "severance_inflated_or_reason_misstated",
                              amount_vnd=int(self.rows[i]["amount_vnd"] * rng.uniform(*factor) / 1000) * 1000,
                              creator_id=case["perpetrator_id"] if c != "L2" else self.rows[i]["creator_id"],
                              support_doc_count=rng.choice([1, 2]) if c == "L0" else rng.choice([3, 4]))

    # ------------------------------------------------------------------ KB05 referral commission to a fabricated collaborator
    def scheme_fake_referral_commission(self, case):
        rng, cid, c = self.rng, case["company_id"], case["concealment"]
        dates = self.months_in(case["_start"], case["_end"], rng.randint(3, 28))
        if len(dates) < 2:
            raise NotApplicable
        v = self.shell(case, case["_start"] - timedelta(days=rng.randint(5, 40)))
        base = self._money(cid, 4, 20)
        for j, at in enumerate(dates):
            amount = int(base * rng.uniform(.8, 1.2) * (1 + (.25 * j if c == "L0" else .04 * j)) / 1000) * 1000
            r = self.tx(case, at, "vendor_payment", vendor=v, amount=amount, creator=self.creator_for(case), approver=self.approver_for(case, amount))
            r.update(support_doc_count=self.docs(case), business_purpose="Hoa hồng giới thiệu khách hàng", goods_receipt_verified=0)
            self.fraud_put(case, r, "commission_to_collaborator_for_customers_not_referred")

    # ------------------------------------------------------------------ KB06 disposal to a related buyer
    def scheme_related_asset_disposal(self, case):
        rng, cid, c = self.rng, case["company_id"], case["concealment"]
        at = self.times(case, 1)[0]
        depreciation = []
        if c == "L1":                                            # depreciation raised on the asset group beforehand
            depreciation = [i for i in self._index().get((cid, "depreciation"), []) if i not in self.used
                            and max(WINDOWS[case["split"]][0], case["_start"] - timedelta(days=270)) <= parse(self.rows[i]["posted_at"]) <= at]
            if len(depreciation) < 2:
                raise NotApplicable
        cu = rng.choice(self.company_customers[cid])
        book = self._money(cid, 300, 1800)
        price = {"L0": rng.uniform(.18, .28), "L1": rng.uniform(.9, 1.3), "L2": rng.uniform(.5, .7)}[c] * book
        for i in (depreciation[-rng.randint(2, min(6, len(depreciation))):] if depreciation else []):
            self.fraud_mutate(case, i, "depreciation_accelerated_before_related_sale",
                              amount_vnd=int(self.rows[i]["amount_vnd"] * rng.uniform(4, 6) / 1000) * 1000)
        gross = int(price / 1000) * 1000
        inv = self.invoice_row(case, at, cu, gross, self.creator_for(case), self.approver_for(case, gross))
        inv.update(business_purpose="Thanh lý tài sản cố định", support_doc_count=rng.choice([1, 2]) if c == "L0" else rng.choice([3, 4]))
        self.fraud_put(case, inv, "asset_sold_far_below_value_to_related_buyer")
        rc = self.receipt_row(cid, case["split"], inv, cu, case["perpetrator_id"], rng.randint(1, 10))
        if rc is not None:
            self.support_put(case, rc)
        loss = max(1_000_000, int((book - price) / 1000) * 1000)
        r = self.tx(case, at + timedelta(hours=1), "adjustment", amount=loss, creator=self.creator_for(case), approver=self.approver_for(case, loss))
        r.update(business_purpose="Ghi giảm tài sản cố định, lỗ thanh lý", support_doc_count=inv["support_doc_count"])
        self.fraud_put(case, r, "disposal_loss_booked")

    # ------------------------------------------------------------------ KB07 company truck used for outside hauling
    def scheme_truck_outside_hauling(self, case):
        rng, c = self.rng, case["concealment"]
        plan = []
        for at in self.times(case, {"L0": rng.randint(3, 8), "L1": rng.randint(5, 10), "L2": rng.randint(4, 8)}[c]):
            if c == "L0":
                at = self._sunday(at, case["split"])
            plan.append((at, self.real_vendor(case, at, min_age=60)))
        for at, v in plan:
            liters = {"L0": rng.uniform(80, 150), "L1": rng.uniform(90, 130), "L2": rng.uniform(62, 78) * rng.uniform(1.02, 1.04)}[c]
            price = FUEL_PRICE * rng.uniform(.96, 1.04)
            amount = int(liters * price / 1000) * 1000
            r = self.tx(case, at, "vendor_payment", vendor=v, amount=amount, creator=self.creator_for(case), approver=self.approver_for(case, amount))
            r.update(unit_price_vnd=int(price), quantity=round(liters, 3), support_doc_count=rng.choice([0, 1]) if c == "L0" else self.docs(case),
                     business_purpose="Đổ nhiên liệu xe tải", goods_receipt_verified=0)
            self.fraud_put(case, r, "fuel_for_trip_not_on_company_books")
            if c == "L2":                                        # internal transfer pair covers the trip
                qty = int(amount * 3 / 1000) * 1000
                for when, purpose in ((at + timedelta(hours=2), "Điều chuyển hàng từ kho 1 sang kho 2"),
                                      (self._after(case, at, 2, 5), "Điều chuyển hàng từ kho 2 về kho 1")):
                    if when is None:
                        continue
                    t = self.tx(case, when, "adjustment", amount=qty, creator=self.creator_for(case), approver=self.approver_for(case, qty))
                    t.update(business_purpose=purpose, support_doc_count=rng.choice([3, 4]))
                    self.fraud_put(case, t, "transfer_pair_covering_outside_trip")

    # ------------------------------------------------------------------ KB08 payment order sold for a fee
    def scheme_payment_priority_bribe(self, case):
        rng, cid, c = self.rng, case["company_id"], case["concealment"]
        terms = self.profile[cid]["vendor_terms"]
        plan = []
        for _ in range(rng.randint(3, 4)):
            at = self.times(case, 1)[0]
            plan.append((at, self.real_vendor(case, at, min_age=60)))
        for at, v in plan:
            if c == "L2":                                        # favoured vendor paid early, price edges up
                issued, markup, label = at - timedelta(days=max(1, terms - rng.randint(10, 20))), rng.uniform(1.02, 1.03), "paid_early_without_discount"
            else:                                                # refusing vendor held back
                late = rng.randint(60, 120) if c == "L0" else rng.randint(40, 75)
                issued, markup, label = at - timedelta(days=terms + late), 1.0, "paid_late_while_cash_available"
            amount = self.amount(case, 0)
            r = self.tx(case, at, "vendor_payment", vendor=v, amount=amount, creator=self.creator_for(case), approver=self.approver_for(case, amount),
                        price_markup=markup)
            r.update(invoice_issued_at=stamp(issued), support_doc_count=self.docs(case))
            if c == "L1":
                r["business_purpose"] = "Hóa đơn thay thế"
            self.fraud_put(case, r, label)
            if c == "L0":
                fee = self.tx(case, at + timedelta(minutes=30), "adjustment", vendor=v,
                              amount=max(100_000, int(amount * rng.uniform(.01, .03) / 1000) * 1000),
                              creator=self.creator_for(case), approver=self.approver_for(case, amount))
                fee.update(business_purpose="Lãi chậm trả", support_doc_count=rng.choice([1, 2]))
                self.fraud_put(case, fee, "late_payment_interest_booked")

    # ------------------------------------------------------------------ KB09 expenses of the closing period booked after it
    def _period_end(self, split, clearance=14):
        a, b = WINDOWS[split]
        options = []
        for y in sorted({a.year, b.year}):
            for m in (3, 6, 9, 12):
                qe = datetime(y, m, calendar.monthrange(y, m)[1], 17, tzinfo=TZ)
                if a + timedelta(days=20) <= qe <= b - timedelta(days=clearance):
                    options.append(qe)
        if not options:
            raise NotApplicable
        return self.rng.choice(options)

    def scheme_period_end_cutoff_shift(self, case):
        rng, cid, c = self.rng, case["company_id"], case["concealment"]
        qe = self._period_end(case["split"])
        count = {"L0": rng.randint(6, 12), "L1": rng.randint(6, 12), "L2": rng.randint(2, 4)}[c]
        vendors = [self.real_vendor(case, qe, min_age=60) for _ in range(count)]
        for j, v in enumerate(vendors):
            posted = self.clamp(_workday(qe + timedelta(days=rng.randint(5, 10))).replace(hour=rng.randint(9, 16)), case["split"])
            issued = qe + timedelta(days=rng.randint(0, 2)) if c == "L2" else qe - timedelta(days=rng.randint(1, 12))
            amount = self.amount(case, j)
            r = self.tx(case, posted, "vendor_payment", vendor=v, amount=amount, creator=self.creator_for(case), approver=self.approver_for(case, amount))
            r.update(invoice_issued_at=stamp(issued), support_doc_count=rng.choice([3, 4]) if c == "L2" else self.docs(case))
            self.fraud_put(case, r, "current_period_expense_booked_after_period_end")
        if c == "L1":                                            # payroll accrual and interest for the closing month skipped
            amount = self._money(cid, 30, 90)
            r = self.tx(case, self.clamp(qe + timedelta(days=rng.randint(4, 9)), case["split"]), "adjustment", amount=amount,
                        creator=self.creator_for(case), approver=self.approver_for(case, amount))
            r.update(business_purpose="Chi phí lương và lãi vay cuối kỳ ghi sổ sau kỳ", support_doc_count=2)
            self.fraud_put(case, r, "closing_accrual_skipped_and_booked_later")

    # ------------------------------------------------------------------ KB10 credit extended to a related dealer
    def scheme_related_dealer_credit(self, case):
        rng, cid, c = self.rng, case["company_id"], case["concealment"]
        cu = rng.choice(self.company_customers[cid])
        self.customers[cu]["credit_terms_days"] = str({"L0": 120, "L1": 30, "L2": 90}[c])
        terms, first = int(self.customers[cu]["credit_terms_days"]), True
        for at in self.times(case, rng.randint(3, 6)):
            gross = max(1_000_000, int(rng.lognormvariate(self.customer_prof[cu]["mu"], .5) * rng.uniform(1.5, 3) / 1000) * 1000)
            inv = self.invoice_row(case, at, cu, gross, rng.choice(self._accountants(cid)), case["perpetrator_id"])
            inv["support_doc_count"] = self.docs(case)
            if first:
                self.support_put(case, inv)
                first = False
            else:
                self.fraud_put(case, inv, "credit_sale_while_related_dealer_overdue" if c != "L2" else "credit_sale_to_related_dealer_on_programme_terms")
            rc = self.receipt_row(cid, case["split"], inv, cu, case["perpetrator_id"], terms + (rng.randint(30, 60) if c == "L0" else rng.randint(0, 5)))
            if rc is not None:
                if c == "L0":
                    rc["amount_vnd"] = int(rc["amount_vnd"] * rng.uniform(.2, .3) / 1000) * 1000
                self.support_put(case, rc)

    # ================================================================== look-alikes (legitimate)
    def _legit(self, split, row, name):
        return self.put(split, row, hard=name)

    def _legit_invoice(self, cid, split, at, cu, name, purpose=None, docs=None):
        gross = max(500_000, int(self.rng.lognormvariate(self.customer_prof[cu]["mu"], .5) / 1000) * 1000)
        staff = self.company_staff[cid]
        inv = self.invoice_row({"company_id": cid, "split": split}, at, cu, gross, staff[1], staff[0])
        inv["support_doc_count"] = docs if docs is not None else self.rng.choice([2, 3, 4])
        if purpose:
            inv["business_purpose"] = purpose
        self._legit(split, inv, name)
        return inv, gross

    def decoy_dissolved_customer_writeoff(self, cid, split):
        cu = self.rng.choice(self.company_customers[cid])
        at = self.clamp(_workday(WINDOWS[split][0] + timedelta(days=self.rng.randint(8, 40))).replace(hour=10), split)
        when = at + timedelta(days=self.rng.randint(120, 200))
        if when >= WINDOWS[split][1] - timedelta(days=2):
            raise NotApplicable
        _, gross = self._legit_invoice(cid, split, at, cu, "dissolved_customer_writeoff")
        staff = self.company_staff[cid]
        r = self.new_kind_row(cid, _workday(when), "bad_debt_writeoff", gross, staff[1], staff[0], customer_id=cu,
                              purpose="Xóa nợ khách giải thể, có dự phòng và hồ sơ", docs=4)
        r["writeoff_provision_vnd"] = gross
        self._legit(split, r, "dissolved_customer_writeoff")

    def decoy_supplier_defect_discount(self, cid, split):
        cus = self.company_customers[cid]
        if len(cus) < 3:
            raise NotApplicable
        rate, staff = self.rng.uniform(.04, .08), self.company_staff[cid]
        start = self._workday_time(split, 60)
        for cu in self.rng.sample(cus, min(len(cus), self.rng.randint(3, 5))):
            at = self.clamp(start + timedelta(days=self.rng.randint(0, 35)), split)
            amount = max(100_000, int(self.rng.lognormvariate(self.customer_prof[cu]["mu"], .5) * rate / 1000) * 1000)
            r = self.transaction(cid, split, at, "adjustment", amount=amount, creator=staff[3], approver=staff[1])
            r.update(customer_id=cu, business_purpose="Giảm giá do lô hàng lỗi của nhà cung cấp", support_doc_count=3)
            self._legit(split, r, "supplier_defect_discount")

    def decoy_contract_deposit_forfeit(self, cid, split):
        self._deposit(cid, split, "contract_deposit_forfeit", settle=False)

    def decoy_deposit_settled_by_invoice(self, cid, split):
        self._deposit(cid, split, "deposit_settled_by_invoice", settle=True)

    def _deposit(self, cid, split, name, settle):
        rng, staff = self.rng, self.company_staff[cid]
        at = self._workday_time(split, 70)
        when = at + timedelta(days=rng.randint(40, 120))
        ids = [x for x in self.company_vendors[cid] if parse(self.vendors[x]["onboarded_at"]) < at - timedelta(days=90)]
        if not ids or when >= WINDOWS[split][1] - timedelta(days=2):
            raise NotApplicable
        v, deposit = self.vendors[rng.choice(ids)], self._money(cid, 40, 300)
        dep = self.transaction(cid, split, at, "vendor_payment", vendor=v, amount=deposit, creator=staff[3], approver=staff[1])
        dep.update(goods_receipt_verified=0, support_doc_count=3, business_purpose="Đặt cọc đơn hàng")
        self._legit(split, dep, name)
        if settle:
            r = self.transaction(cid, split, _workday(when), "vendor_payment", vendor=v, amount=int(deposit * rng.uniform(1.0, 1.4) / 1000) * 1000,
                                 creator=staff[3], approver=staff[1])
            r["business_purpose"] = "Đối trừ cọc bằng hóa đơn mua"
        else:
            r = self.transaction(cid, split, _workday(when), "adjustment", vendor=v, amount=int(deposit * rng.uniform(.1, .3) / 1000) * 1000,
                                 creator=staff[3], approver=staff[0])
            r.update(business_purpose="Phạt hủy đơn theo hợp đồng, có biên bản thanh lý", support_doc_count=4)
        self._legit(split, r, name)

    def _legit_trip(self, cid, split, at, name, extra=0, docs=4):
        rng, staff = self.rng, self.company_staff[cid]
        sales = [x for x in staff if self.employees[x]["role"] == "sales" and self.active(self.employees[x], at)
                 and self.active(self.employees[x], at + timedelta(days=8))]
        days = rng.randint(2, 3) + extra
        when = at + timedelta(days=rng.randint(days + 1, days + 4))
        if not sales or when >= WINDOWS[split][1] - timedelta(days=2):
            raise NotApplicable
        e = self.employees[rng.choice(sales)]
        unit = rng.choice([300_000, 400_000, 500_000]) * max(1, int(round(self._scale(cid) ** .5)))
        aid = self.identifier("A")
        issue = self.transaction(cid, split, at, "advance_issue", employee=e, amount=unit * days, creator=staff[3], approver=staff[1])
        issue.update(advance_id=aid, support_doc_count=3, business_purpose="Tạm ứng công tác")
        tid = self._legit(split, issue, name)
        self.tables["advances"].append(dict(advance_id=aid, company_id=cid, employee_id=e["employee_id"], issue_transaction_id=tid,
                                            issued_at=stamp(at), recorded_at=stamp(at), original_due_at=stamp(at + timedelta(days=30)),
                                            original_amount_vnd=unit * days))
        s = self.transaction(cid, split, _workday(when), "advance_settlement", employee=e, amount=unit * days, creator=staff[3])
        s.update(advance_id=aid, support_doc_count=docs, unit_price_vnd=int(unit), quantity=days, business_purpose="Quyết toán công tác phí")
        stid = self._legit(split, s, name)
        self.tables["advance_events"].append(dict(event_id=self.identifier("AE"), advance_id=aid, company_id=cid, event_type="settlement",
                                                  observed_at=stamp(when), new_due_at="", amount_vnd=unit * days, transaction_id=stid, evidence_on_file=1))

    def decoy_trip_extended_incident(self, cid, split):
        self._legit_trip(cid, split, self._workday_time(split, 30), "trip_extended_incident", extra=1, docs=4)

    def decoy_seasonal_peak_trips(self, cid, split):
        base = self._workday_time(split, 40)
        for _ in range(self.rng.randint(3, 5)):
            try:
                self._legit_trip(cid, split, self.clamp(base + timedelta(days=self.rng.randint(0, 12)), split), "seasonal_peak_trips", extra=1, docs=3)
            except NotApplicable:
                break

    def _staff_at(self, cid, at):
        people = [x for x in self.company_staff[cid][6:] if self.active(self.employees[x], at) and self.active(self.employees[x], at + timedelta(days=1))]
        if not people:
            raise NotApplicable
        return people

    def decoy_severance_formula_paid(self, cid, split):
        at = self._workday_time(split, 20)
        e, staff = self.employees[self.rng.choice(self._staff_at(cid, at))], self.company_staff[cid]
        r = self.transaction(cid, split, at, "payroll", employee=e, amount=int(e["monthly_salary_vnd"] * self.rng.uniform(.5, 1.5) / 1000) * 1000,
                             creator=staff[1], approver=staff[0])
        r.update(support_doc_count=4, business_purpose="Trợ cấp thôi việc theo công thức, thời gian chưa đóng BHTN")
        self._legit(split, r, "severance_formula_paid")

    def decoy_layoff_wave_severance(self, cid, split):
        at, staff = self._workday_time(split, 20), self.company_staff[cid]
        crew = self._staff_at(cid, at)
        if len(crew) < 4:
            raise NotApplicable
        for eid in self.rng.sample(crew, min(len(crew), self.rng.randint(4, 6))):
            e = self.employees[eid]
            r = self.transaction(cid, split, at, "payroll", employee=e, amount=int(e["monthly_salary_vnd"] * 2 / 1000) * 1000,
                                 creator=staff[1], approver=staff[0])
            r.update(support_doc_count=4, business_purpose="Trợ cấp mất việc làm đợt cắt giảm, thông báo cơ quan lao động")
            self._legit(split, r, "layoff_wave_severance")

    def _referrer(self, cid):
        if not hasattr(self, "_referrers"):
            self._referrers = {}
        if cid not in self._referrers:
            v = self.new_shell_vendor(cid, WINDOWS["train"][0] - timedelta(days=self.rng.randint(40, 160)))
            self.vcat[v["vendor_id"]] = "services"
            self._referrers[cid] = v
        return self._referrers[cid]

    def _commission(self, cid, split, at, name, amount):
        staff = self.company_staff[cid]
        r = self.transaction(cid, split, at, "vendor_payment", vendor=self._referrer(cid), amount=amount, creator=staff[3], approver=staff[1])
        r.update(support_doc_count=3, business_purpose="Hoa hồng giới thiệu khách hàng", goods_receipt_verified=0)
        self._legit(split, r, name)

    def decoy_registered_referrer_commission(self, cid, split):
        base = self._money(cid, 4, 15)
        for _ in range(self.rng.randint(2, 4)):
            self._commission(cid, split, self._workday_time(split, 20), "registered_referrer_commission",
                             int(base * self.rng.uniform(.8, 1.2) / 1000) * 1000)

    def decoy_reactivated_customer_commission(self, cid, split):
        self._commission(cid, split, self._workday_time(split, 20), "reactivated_customer_commission", self._money(cid, 6, 25))

    def decoy_scrap_asset_disposal(self, cid, split):
        rng, staff = self.rng, self.company_staff[cid]
        cu, at, gross = rng.choice(self.company_customers[cid]), self._workday_time(split, 20), self._money(cid, 5, 40)
        inv = self.invoice_row({"company_id": cid, "split": split}, at, cu, gross, staff[1], staff[0])
        inv.update(business_purpose="Thanh lý tài sản đã khấu hao hết, ba báo giá, kiểm định độc lập", support_doc_count=4)
        self._legit(split, inv, "scrap_asset_disposal")
        r = self.transaction(cid, split, at + timedelta(hours=1), "adjustment", amount=int(gross * rng.uniform(.9, 1.1) / 1000) * 1000,
                             creator=staff[3], approver=staff[1])
        r.update(business_purpose="Ghi giảm tài sản đã khấu hao hết", support_doc_count=4)
        self._legit(split, r, "scrap_asset_disposal")

    def decoy_depreciation_group_change(self, cid, split):
        a, b = WINDOWS[split]
        idx = [i for i in self._index().get((cid, "depreciation"), []) if i not in self.used and a <= parse(self.rows[i]["posted_at"]) < b]
        if len(idx) < 3:
            raise NotApplicable
        start = self.rng.randint(0, len(idx) - 3)
        factor = self.rng.uniform(1.4, 1.8)               # three-shift use raises the rate for the whole group, assets stay in use
        for i in idx[start:start + self.rng.randint(3, min(6, len(idx) - start))]:
            self.mutate(i, hard="depreciation_group_change", amount_vnd=int(self.rows[i]["amount_vnd"] * factor / 1000) * 1000, support_doc_count=4)

    def _fuel_row(self, cid, split, at, name, liters):
        staff = self.company_staff[cid]
        ids = [x for x in self.company_vendors[cid] if parse(self.vendors[x]["onboarded_at"]) < at - timedelta(days=60)
               and self.vcat.get(x) in ("goods", "materials", "services")]
        if not ids:
            raise NotApplicable
        price = FUEL_PRICE * self.rng.uniform(.96, 1.04)
        r = self.transaction(cid, split, at, "vendor_payment", vendor=self.vendors[self.rng.choice(ids)], amount=int(liters * price / 1000) * 1000,
                             creator=staff[3], approver=staff[1])
        r.update(unit_price_vnd=int(price), quantity=round(liters, 3), support_doc_count=3, business_purpose="Đổ nhiên liệu xe tải",
                 goods_receipt_verified=0)
        self._legit(split, r, name)

    def decoy_hauling_service_invoiced(self, cid, split):
        at = self._workday_time(split, 20)
        self._fuel_row(cid, split, at, "hauling_service_invoiced", self.rng.uniform(70, 110))
        self._legit_invoice(cid, split, at, self.rng.choice(self.company_customers[cid]), "hauling_service_invoiced",
                            purpose="Dịch vụ vận chuyển chiều về", docs=3)

    def decoy_urgent_sunday_delivery(self, cid, split):
        at = self._sunday(self._workday_time(split, 20), split)
        for _ in range(self.rng.randint(2, 3)):
            self._fuel_row(cid, split, at, "urgent_sunday_delivery", self.rng.uniform(70, 120))
            self._legit_invoice(cid, split, at, self.rng.choice(self.company_customers[cid]), "urgent_sunday_delivery",
                                purpose="Giao hàng gấp ngày nghỉ", docs=3)

    def _vendor_payment_with_issue(self, cid, split, at, name, issued, purpose=None):
        rng, staff = self.rng, self.company_staff[cid]
        ids = [x for x in self.company_vendors[cid] if parse(self.vendors[x]["onboarded_at"]) < at - timedelta(days=90)]
        if not ids:
            raise NotApplicable
        r = self.transaction(cid, split, at, "vendor_payment", vendor=self.vendors[rng.choice(ids)], creator=staff[3], approver=staff[1])
        r.update(invoice_issued_at=stamp(issued), support_doc_count=3)
        if purpose:
            r["business_purpose"] = purpose
        self._legit(split, r, name)
        return r

    def decoy_uniform_slow_payment(self, cid, split):
        at, terms = self._workday_time(split, 40), self.profile[cid]["vendor_terms"]
        delay = self.rng.randint(20, 40)               # cash is short for everyone, decided in writing
        for k in range(self.rng.randint(3, 5)):
            self._vendor_payment_with_issue(cid, split, self.clamp(at + timedelta(days=k * 2), split), "uniform_slow_payment",
                                            at - timedelta(days=terms + delay), purpose="Giãn thanh toán theo quyết định ưu tiên")

    def decoy_early_payment_discount(self, cid, split):
        at, terms = self._workday_time(split, 40), self.profile[cid]["vendor_terms"]
        staff = self.company_staff[cid]
        for _ in range(self.rng.randint(1, 3)):
            r = self._vendor_payment_with_issue(cid, split, self.clamp(at + timedelta(days=self.rng.randint(0, 6)), split), "early_payment_discount",
                                                at - timedelta(days=max(1, terms - self.rng.randint(10, 20))),
                                                purpose="Thanh toán sớm hưởng chiết khấu theo hợp đồng")
            d = self.transaction(cid, split, parse(r["posted_at"]) + timedelta(minutes=30), "adjustment", vendor=self.vendors[r["vendor_id"]],
                                 amount=max(100_000, int(float(r["amount_vnd"]) * .02 / 1000) * 1000), creator=staff[3], approver=staff[1])
            d.update(business_purpose="Chiết khấu thanh toán được hưởng", support_doc_count=3)
            self._legit(split, d, "early_payment_discount")

    def decoy_periodic_utility_lag(self, cid, split):
        a, b = WINDOWS[split]
        lag, at, k = self.rng.randint(5, 12), a + timedelta(days=self.rng.randint(15, 40)), 0
        while at < b - timedelta(days=25) and k < 6:
            issued = at - timedelta(days=lag + self.rng.randint(0, 2))
            self._vendor_payment_with_issue(cid, split, self.clamp(_workday(at).replace(hour=self.rng.randint(9, 16)), split),
                                            "periodic_utility_lag", issued, purpose="Điện, viễn thông, thuê bao phát hành sau kỳ")
            at += timedelta(days=30)
            k += 1

    def decoy_post_period_bonus_decision(self, cid, split):
        staff, qe = self.company_staff[cid], self._period_end(split)
        r = self.transaction(cid, split, self.clamp(_workday(qe + timedelta(days=self.rng.randint(4, 9))).replace(hour=10), split), "adjustment",
                             amount=self._money(cid, 20, 80), creator=staff[3], approver=staff[0])
        r.update(business_purpose="Thưởng theo kết quả kỳ, quyết định sau kỳ theo thông lệ nhiều năm", support_doc_count=4)
        self._legit(split, r, "post_period_bonus_decision")

    def decoy_seasonal_credit_policy(self, cid, split):
        cus, rng = self.company_customers[cid], self.rng
        if len(cus) < 4:
            raise NotApplicable
        for cu in rng.sample(cus, min(len(cus), rng.randint(3, 5))):
            self.customers[cu]["credit_terms_days"] = "90"
            inv, _ = self._legit_invoice(cid, split, self._workday_time(split, 40), cu, "seasonal_credit_policy",
                                         purpose="Bán chịu theo chính sách mùa vụ 90 ngày", docs=3)
            rc = self.receipt_row(cid, split, inv, cu, self.customer_prof[cu]["manager"], 90 - rng.randint(0, 6))
            if rc is not None:
                self._legit(split, rc, "seasonal_credit_policy")

    def decoy_structured_debt_extension(self, cid, split):
        rng, staff = self.rng, self.company_staff[cid]
        cu, at = rng.choice(self.company_customers[cid]), self._workday_time(split, 70)
        when = at + timedelta(days=rng.randint(60, 120))
        if when >= WINDOWS[split][1] - timedelta(days=2):
            raise NotApplicable
        inv, gross = self._legit_invoice(cid, split, at, cu, "structured_debt_extension", docs=3)
        rc = self.receipt_row(cid, split, inv, cu, self.customer_prof[cu]["manager"], (when - at).days)
        if rc is not None:
            rc["amount_vnd"] = int(gross * rng.uniform(.4, .6) / 1000) * 1000
            self._legit(split, rc, "structured_debt_extension")
        r = self.transaction(cid, split, _workday(when), "adjustment", amount=max(100_000, int(gross * .02 / 1000) * 1000), creator=staff[3], approver=staff[1])
        r.update(customer_id=cu, business_purpose="Lãi trả chậm theo biên bản giãn nợ", support_doc_count=4)
        self._legit(split, r, "structured_debt_extension")
