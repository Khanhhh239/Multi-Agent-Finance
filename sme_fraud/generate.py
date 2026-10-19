"""Generate relational, reproducible SME observations and separate audit truth.

Amounts are VND integers. Times are local Asia/Ho_Chi_Minh (+07:00).
The calendar and policies are simulation assumptions, not legal rules.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=7))
WINDOWS = {
    "train": (datetime(2024, 1, 1, tzinfo=TZ), datetime(2025, 1, 1, tzinfo=TZ)),
    "validation": (datetime(2025, 1, 1, tzinfo=TZ), datetime(2025, 7, 1, tzinfo=TZ)),
    "test": (datetime(2025, 7, 1, tzinfo=TZ), datetime(2026, 1, 1, tzinfo=TZ)),
}
FAMILIES = ["ghost_vendor", "split_payments", "duplicate_payment",
            "period_end_adjustment", "risky_invoice", "long_outstanding_advance"]
HARD_NEGATIVES = ["verified_bank_change", "legitimate_self_approval", "weekend_operations",
                  "round_recurring_payment", "legitimate_installments", "new_legitimate_vendor",
                  "declared_related_party", "long_approval_delay", "remote_employee_payroll",
                  "approved_advance_extension", "historical_valid_invoice", "approved_advance_writeoff",
                  "legitimate_period_close"]
# Fixed illustrative holidays. No substitute days or full statutory calendar.
HOLIDAYS = {"2024-01-01", "2024-02-09", "2024-02-10", "2024-02-11", "2024-02-12",
            "2024-02-13", "2024-02-14", "2024-04-30", "2024-05-01", "2024-09-02",
            "2025-01-01", "2025-01-28", "2025-01-29", "2025-01-30", "2025-01-31",
            "2025-02-01", "2025-04-30", "2025-05-01", "2025-09-02"}
# Initial pair summaries. accounting.enrich_accounting produces framework-specific
# multi-line VAT/production/receivable documents before features are built.
PAIRS = {
    "vendor_payment": ("331", "112"), "stock_purchase": ("156", "331"),
    "material_purchase": ("152", "331"), "sales_invoice": ("131", "511"),
    "customer_receipt": ("112", "131"), "cash_expense": ("642", "111"),
    "payroll": ("334", "112"), "cogs": ("632", "156"), "adjustment": ("642", "338"),
    "rent": ("642", "112"), "advance_issue": ("141", "112"),
    "advance_settlement": ("642", "141"), "advance_writeoff": ("138", "141"),
    "advance_review": ("", ""), "depreciation": ("642", "214"),
    "equipment_purchase": ("211", "331"), "tax_payment": ("3331", "112"),
    "selling_expense": ("641", "112"),
    "material_issue": ("154", "152"), "production_completion": ("155", "154"),
    "vat_offset": ("3331", "1331"),
    "tools_purchase": ("153", "331"),
}
NORMAL_TYPES = ["vendor_payment", "stock_purchase", "material_purchase", "sales_invoice",
                "customer_receipt", "cash_expense", "payroll", "cogs", "adjustment", "rent",
                "depreciation", "equipment_purchase", "tax_payment", "selling_expense"]
NORMAL_WEIGHTS = [29, 11, 6, 13, 12, 7, 5, 6, 3, 2, 1, 1, 1, 3]


def stamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None):
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def allocate(total: int, weights: list[float]) -> list[int]:
    exact = [total * weight / sum(weights) for weight in weights]
    counts = [math.floor(x) for x in exact]
    for i in sorted(range(len(weights)), key=lambda i: exact[i] - counts[i], reverse=True)[:total-sum(counts)]:
        counts[i] += 1
    return counts


class Generator:
    def __init__(self, n: int, rate: float, seed: int, companies: int = 5):
        self.rng = random.Random(seed)
        self.n, self.rate, self.seed = n, rate, seed
        self.tables = defaultdict(list)
        self.employees, self.vendors, self.customers = {}, {}, {}
        self.company_staff, self.company_vendors, self.company_customers = {}, {}, {}
        self.serials = Counter()
        self.rows, self.truth, self.pools = [], [], {}
        self.payroll_keys = set()
        self.make_masters(companies)
        self.make_background()

    def identifier(self, kind: str) -> str:
        self.serials[kind] += 1
        return f"{kind}{self.serials[kind]:07d}"

    def company(self, cid: str) -> dict:
        return self.tables["companies"][int(cid[1:])-1]

    def link(self, cid: str, source: str, target: str, kind: str, at: datetime):
        self.tables["entity_links"].append(dict(company_id=cid, source_id=source,
            target_id=target, link_type=kind, observed_at=stamp(at)))

    def employee(self, cid: str, at: datetime, role="operations", mode="onsite", bank=None,
                 attendance=None, append_to_background=True):
        eid = self.identifier("E")
        limit = {"director": 100_000_000, "chief_accountant": 50_000_000,
                 "accountant": 20_000_000}.get(role, 5_000_000)
        e = dict(employee_id=eid, company_id=cid, full_name=f"Nhân sự mô phỏng {self.serials['E']}",
            role=role, department=self.rng.choice(["office", "sales", "warehouse", "operations"]),
            bank_account=bank or self.identifier("BANK_SYN_"), phone=self.identifier("PHONE_SYN_"),
            address=self.identifier("ADDRESS_SYN_"), hired_at=stamp(at), recorded_at=stamp(at),
            work_mode=mode, monthly_salary_vnd=self.rng.choice([8, 10, 12, 15, 18, 22])*1_000_000,
            approval_limit_vnd=limit, self_approval_limit_vnd=limit if role=="director" else 2_000_000,
            contract_on_file=int(self.rng.random() > .015))
        self.employees[eid] = e
        self.tables["employees"].append(e)
        if append_to_background:
            self.company_staff[cid].append(eid)
        self.link(cid, eid, e["bank_account"], "bank_account", at)
        self.link(cid, eid, e["phone"], "phone", at)
        for year in (2024, 2025):
            for month in range(1, 13):
                observed = datetime(year, month, 25, 8, tzinfo=TZ)
                if observed < at:
                    continue
                days = attendance if attendance is not None else (0 if mode=="remote" else self.rng.randint(14, 22))
                self.tables["attendance"].append(dict(employee_id=eid, company_id=cid,
                    payroll_period=f"{year}-{month:02}", observed_at=stamp(observed),
                    days_worked_observed=days, approved_leave_days=0,
                    alternative_work_evidence=int(mode=="remote")))
        return e

    def vendor(self, cid: str, onboard: datetime, registered=None, bank=None, phone=None,
               address=None, representative_phone=None, disclosed=False, background=True):
        vid = self.identifier("V")
        v = dict(vendor_id=vid, company_id=cid, name=f"Công ty mô phỏng đối tác {self.serials['V']}",
            tax_code=self.identifier("MST_SYN_"), bank_account=bank or self.identifier("BANK_SYN_"),
            phone=phone or self.identifier("PHONE_SYN_"), address=address or self.identifier("ADDRESS_SYN_"),
            registered_at=stamp(registered or onboard-timedelta(days=self.rng.randint(180, 3600))),
            onboarded_at=stamp(onboard), recorded_at=stamp(onboard),
            representative_id=self.identifier("P"), related_party_disclosed_at=stamp(onboard) if disclosed else "")
        self.vendors[vid] = v
        self.tables["vendors"].append(v)
        if background:
            self.company_vendors[cid].append(vid)
        for key in ("bank_account", "phone"):
            self.link(cid, vid, v[key], key, onboard)
        self.link(cid, vid, v["representative_id"], "representative", onboard)
        self.link(cid, v["representative_id"], representative_phone or self.identifier("PHONE_SYN_"), "phone", onboard)
        self.tables["vendor_status_history"].append(dict(vendor_id=vid, company_id=cid,
            status="active", effective_at=stamp(onboard), observed_at=stamp(onboard)))
        return v

    def make_masters(self, count):
        initial = datetime(2023, 1, 1, tzinfo=TZ)
        industries = ["trading", "manufacturing", "services", "retail", "logistics"]
        for i in range(count):
            cid = f"C{i+1:03}"
            self.tables["companies"].append(dict(company_id=cid, name=f"SME tổng hợp {i+1}",
                industry=industries[i%5], city=["TP.HCM", "Hà Nội", "Đà Nẵng", "Cần Thơ", "Hải Phòng"][i%5],
                amount_scale=[1.0, 1.6, .7, .8, 1.2][i%5], saturday_operations=int(i%5 in (0, 1, 3, 4)),
                currency="VND", timezone="Asia/Ho_Chi_Minh"))
            self.company_staff[cid], self.company_vendors[cid], self.company_customers[cid] = [], [], []
            for j in range(40):
                role = "director" if j==0 else "chief_accountant" if j==1 else "accountant" if j<6 else "operations"
                self.employee(cid, initial, role, "remote" if j%13==8 else "onsite")
            office = self.identifier("ADDRESS_SYN_")
            for j in range(80):
                # Co-working addresses and declared relationships are legitimate background overlaps.
                e = self.employees[self.company_staff[cid][j%40]]
                self.vendor(cid, initial, address=office if j<5 else None,
                    phone=e["phone"] if j in (6, 7) else None, disclosed=j in (6, 7))
            for j in range(60):
                customer = dict(customer_id=self.identifier("CU"), company_id=cid,
                    name=f"Khách hàng mô phỏng {j+1}", tax_code=self.identifier("MST_SYN_"),
                    bank_account=self.identifier("BANK_SYN_"), recorded_at=stamp(initial),
                    credit_terms_days=self.rng.choice([15, 30, 45, 60]))
                self.customers[customer["customer_id"]] = customer
                self.company_customers[cid].append(customer["customer_id"])
                self.tables["customers"].append(customer)
        self.tables["calendar"] = [dict(date=date, is_holiday=1, source="illustrative_simulation_calendar")
                                    for date in sorted(HOLIDAYS)]

    def random_time(self, split, margin=0, weekend=False):
        start, end = WINDOWS[split]
        while True:
            at = start + timedelta(days=self.rng.randrange(margin, (end-start).days-margin),
                hours=self.rng.choices([self.rng.randint(8, 18), self.rng.randint(19, 23), self.rng.randint(0, 7)],
                                      [86, 10, 4])[0], minutes=self.rng.randrange(60), seconds=self.rng.randrange(60))
            if weekend and at.weekday()<5:
                continue
            if weekend or self.rng.random() < (1 if at.weekday()<5 else .58 if at.weekday()==5 else .28):
                return at

    def transaction(self, cid, split, at=None, kind=None, vendor=None, employee=None,
                    amount=None, creator=None, approver=None, delay_hours=None):
        at = at or self.random_time(split)
        kind = kind or self.rng.choices(NORMAL_TYPES, NORMAL_WEIGHTS)[0]
        staff = self.company_staff[cid]
        creator = creator or self.rng.choice(staff[:6])
        approver = approver or (creator if self.rng.random()<.06 else self.rng.choice(staff[:2]))
        delay = delay_hours if delay_hours is not None else (
            self.rng.uniform(72, 504) if self.rng.random()<.04 else min(72, self.rng.lognormvariate(.35, 1.5)))
        created = max(WINDOWS[split][0], at-timedelta(hours=delay))
        if amount is None:
            base = 8_000_000 * float(self.company(cid)["amount_scale"])
            amount = max(25_000, int(self.rng.lognormvariate(math.log(base), 1.05)/1000)*1000)
            if self.rng.random()<.007:
                amount *= self.rng.randint(5, 12)
            if self.rng.random()<.25:
                amount = max(100_000, round(amount/1_000_000)*1_000_000)
        vid, eid, cuid, recipient = "", "", "", ""
        if kind in ("vendor_payment", "stock_purchase", "material_purchase", "rent", "equipment_purchase", "selling_expense"):
            v = vendor or self.vendors[self.rng.choice(self.company_vendors[cid])]
            vid, recipient = v["vendor_id"], v["bank_account"]
        if kind in ("sales_invoice", "customer_receipt"):
            customer = self.customers[self.rng.choice(self.company_customers[cid])]
            cuid, recipient = customer["customer_id"], customer["bank_account"]
        if kind in ("payroll", "advance_issue", "advance_settlement", "advance_writeoff", "advance_review"):
            e = employee or self.employees[self.rng.choice(staff)]
            eid, recipient = e["employee_id"], e["bank_account"]
            if kind=="payroll":
                amount = e["monthly_salary_vnd"] + self.rng.choice([0, 0, 200_000, -100_000])
        if creator==approver and amount>self.employees[creator]["self_approval_limit_vnd"]:
            approver = next(x for x in staff[:2] if x!=creator)
        debit, credit = PAIRS[kind]
        invoice = self.identifier("I") if vid else ""
        return dict(company_id=cid, posted_at=stamp(at), created_at=stamp(created), approved_at=stamp(at),
            effective_date=at.date().isoformat(), txn_type=kind, amount_vnd=int(amount), currency="VND",
            debit_account=debit, credit_account=credit, vendor_id=vid, customer_id=cuid, employee_id=eid,
            recipient_account=recipient, invoice_id=invoice, invoice_number=f"HD{self.rng.randrange(1, 10**8):08}" if invoice else "",
            invoice_issued_at=stamp(max(parse(v["onboarded_at"]), at-timedelta(days=self.rng.randint(0, 30)))) if invoice else "",
            invoice_gross_vnd=int(amount) if invoice else 0, project_id=f"PR{self.rng.randrange(1, 31):03}",
            business_purpose="Thanh toán hoạt động", creator_id=creator, approver_id=approver,
            approval_limit_vnd=self.employees[creator]["approval_limit_vnd"],
            department=self.employees[creator]["department"],
            payment_channel="cash" if kind=="cash_expense" else "bank" if recipient else "journal",
            support_doc_count=self.rng.choices([0, 1, 2, 3, 4], [3, 15, 35, 32, 15])[0],
            goods_receipt_verified=int(self.rng.random()<.85) if vid else 0,
            self_approval_exception_id="", bank_change_id="", advance_id="",
            payroll_period=at.strftime("%Y-%m") if kind=="payroll" else "",
            is_financial_entry=int(kind!="advance_review"))

    def make_background(self):
        ids = list(range(1, self.n+1))
        self.rng.shuffle(ids)
        counts = allocate(self.n, [.5, .25, .25])
        for split, count in zip(WINDOWS, counts):
            indices = []
            for _ in range(count):
                cid = self.rng.choice(list(self.company_staff))
                r = self.transaction(cid, split)
                if r["txn_type"]=="payroll":
                    r = self.transaction(cid, split, parse(r["posted_at"]).replace(day=28), "payroll",
                                         employee=self.employees[r["employee_id"]])
                    key = (r["employee_id"], r["payroll_period"])
                    if key in self.payroll_keys:
                        r = self.transaction(cid, split, parse(r["posted_at"]), "cash_expense")
                    else:
                        self.payroll_keys.add(key)
                i = len(self.rows)
                r["transaction_id"] = f"T{ids[i]:09d}"
                self.rows.append(r)
                self.truth.append(dict(transaction_id=r["transaction_id"], is_fraud=0, fraud_type="", variant="",
                    case_id="", case_role="background", hard_negative_type="", difficulty="", observability=""))
                indices.append(i)
            self.rng.shuffle(indices)
            self.pools[split] = indices

    def put(self, split, row, family="", variant="", case="", hard="", support=False, observable="available"):
        i = self.pools[split].pop()
        row["transaction_id"] = self.rows[i]["transaction_id"]
        self.rows[i] = row
        self.truth[i].update(is_fraud=int(bool(family)), fraud_type=family, variant=variant,
            case_id=case, case_role="support" if support else "fraud" if family else "hard_negative" if hard else "background",
            hard_negative_type=hard, difficulty="subtle" if observable!="available" else "mixed" if family else "",
            observability=observable if family else "")
        return row["transaction_id"]

    def context(self, split, margin=5):
        cid = self.rng.choice(list(self.company_staff))
        at = self.random_time(split, margin)
        creator = self.rng.choice(self.company_staff[cid][1:12])
        return cid, at, creator

    def status(self, v, status, effective, observed):
        self.tables["vendor_status_history"].append(dict(vendor_id=v["vendor_id"], company_id=v["company_id"],
            status=status, effective_at=stamp(effective), observed_at=stamp(observed)))

    def advance(self, cid, split, at, creator, valid=True, mode="review", hard=""):
        case = self.identifier("CASE")
        staff = self.employees[self.rng.choice(self.company_staff[cid][6:])]
        aid = self.identifier("A")
        issued = WINDOWS[split][0] + timedelta(days=self.rng.randint(4, 15), hours=10)
        amount = self.rng.choice([3, 5, 8, 12, 18, 25])*1_000_000
        due = issued+timedelta(days=self.rng.choice([15, 30, 45]))
        first = self.transaction(cid, split, issued, "advance_issue", employee=staff, amount=amount, creator=creator)
        first["advance_id"] = aid
        issue_id = self.put(split, first, case=case, support=True)
        self.tables["advances"].append(dict(advance_id=aid, company_id=cid, employee_id=staff["employee_id"],
            issue_transaction_id=issue_id, issued_at=stamp(issued), recorded_at=stamp(issued),
            original_due_at=stamp(due), original_amount_vnd=amount))
        if valid:
            extended = at+timedelta(days=10)
            self.tables["advance_events"].append(dict(event_id=self.identifier("AE"), advance_id=aid,
                company_id=cid, event_type="extension", observed_at=stamp(due-timedelta(days=1)),
                new_due_at=stamp(extended), amount_vnd=0, transaction_id="", evidence_on_file=1))
        kind = "advance_review" if mode=="review" else "advance_writeoff"
        row = self.transaction(cid, split, at, kind, employee=staff, amount=amount, creator=creator)
        row.update(advance_id=aid, support_doc_count=self.rng.randint(1, 3) if valid else self.rng.choice([0, 0, 1, 2]),
                   business_purpose="Đối chiếu tạm ứng")
        family = "" if valid else "long_outstanding_advance"
        variant = "overdue_unsettled" if mode=="review" else "opaque_writeoff"
        tid = self.put(split, row, family, variant if family else "", case, hard=hard)
        if mode!="review":
            self.tables["advance_events"].append(dict(event_id=self.identifier("AE"), advance_id=aid,
                company_id=cid, event_type="writeoff", observed_at=stamp(at), new_due_at="",
                amount_vnd=amount, transaction_id=tid, evidence_on_file=int(valid)))

    def inject_fraud(self):
        total = round(self.n*self.rate)
        counts = allocate(total, [len(self.pools[s]) for s in WINDOWS])
        for split, count in zip(WINDOWS, counts):
            budgets = allocate(count, [1]*6)
            for family, budget in zip(FAMILIES, budgets):
                done = 0
                case_index = 0
                while done<budget:
                    cid, at, creator = self.context(split, 8)
                    case = self.identifier("CASE")
                    e = self.employees[self.rng.choice(self.company_staff[cid][2:])]
                    if family=="ghost_vendor":
                        variant = ["employee_vendor_overlap", "new_shell_two_hop", "ghost_employee_payroll"][case_index%3]
                        if variant=="ghost_employee_payroll":
                            at = at.replace(day=28, hour=16)
                            ghost = self.employee(cid, at.replace(day=1), bank=e["bank_account"], attendance=0,
                                                  append_to_background=False)
                            r = self.transaction(cid, split, at, "payroll", employee=ghost, creator=creator)
                            r["support_doc_count"] = self.rng.choice([0, 1, 2])
                        else:
                            before = at-timedelta(days=self.rng.randint(1, 20))
                            v = self.vendor(cid, before, registered=before-timedelta(days=self.rng.randint(1, 45)) if variant=="new_shell_two_hop" else None,
                                bank=e["bank_account"] if variant=="employee_vendor_overlap" and case_index%2==0 else None,
                                phone=e["phone"] if variant=="employee_vendor_overlap" and case_index%2 else None,
                                address=e["address"] if case_index%2 else None,
                                representative_phone=e["phone"] if variant=="new_shell_two_hop" else None, background=False)
                            r = self.transaction(cid, split, at, "vendor_payment", vendor=v, creator=creator)
                            r["goods_receipt_verified"] = int(self.rng.random()<.35)
                        self.put(split, r, family, variant, case)
                        done += 1
                    elif family=="split_payments":
                        size = min(budget-done, self.rng.randint(3, 6))
                        # A final singleton gets preceding, labelled fraudulent context by being avoided when possible.
                        if budget-done-size==1 and size>2:
                            size += 1
                        mode = (case_index+list(WINDOWS).index(split))%3
                        variant = ["near_limit_same_recipient", "distributed_days", "multiple_recipients"][mode]
                        span = [1, 12, 5][mode]
                        at = min(at, WINDOWS[split][1]-timedelta(days=span+2))
                        phone = self.identifier("PHONE_SYN_")
                        vendors = [self.vendor(cid, at-timedelta(days=30), phone=phone, background=False)
                                   for _ in range(3 if variant=="multiple_recipients" else 1)]
                        limit = self.employees[creator]["approval_limit_vnd"]
                        for j in range(size):
                            ratio = self.rng.uniform(.90, .995) if variant=="near_limit_same_recipient" else self.rng.uniform(.42, .88)
                            if size==2:
                                ratio = max(.62, ratio)
                            r = self.transaction(cid, split, at+timedelta(days=span*j/max(1,size-1), minutes=j*17),
                                "vendor_payment", vendor=vendors[j%len(vendors)], amount=int(limit*ratio/1000)*1000,
                                creator=creator, delay_hours=self.rng.uniform(.1, 8))
                            r["project_id"] = f"PR{self.rng.randrange(1,31):03}" if variant=="multiple_recipients" else "PR001"
                            self.put(split, r, family, variant, case)
                        done += size
                    elif family=="duplicate_payment":
                        r = self.transaction(cid, split, at, "vendor_payment", creator=creator)
                        self.put(split, dict(r), case=case, support=True)
                        r.update(posted_at=stamp(at+timedelta(hours=self.rng.randint(2, 72))),
                            approved_at=stamp(at+timedelta(hours=self.rng.randint(1, 2))),
                            created_at=stamp(at+timedelta(minutes=30)))
                        # Same tax issuer + invoice number, sometimes a different ERP invoice ID.
                        if case_index%2:
                            r["invoice_id"] = self.identifier("I")
                        self.put(split, r, family, "repeated_full_invoice", case)
                        done += 1
                    elif family=="period_end_adjustment":
                        candidates = [WINDOWS[split][0]+timedelta(days=d, hours=22, minutes=self.rng.randrange(60))
                            for d in range((WINDOWS[split][1]-WINDOWS[split][0]).days)
                            if (WINDOWS[split][0]+timedelta(days=d)).day>=25
                            and (WINDOWS[split][0]+timedelta(days=d)).weekday()>=5]
                        at = self.rng.choice(candidates)
                        r = self.transaction(cid, split, at, "adjustment", creator=creator, approver=creator,
                                             delay_hours=self.rng.choice([.01, .2, 3, 12]))
                        r.update(approver_id=creator, support_doc_count=self.rng.choice([0, 1, 2]), goods_receipt_verified=0)
                        if case_index%2:
                            r.update(debit_account="131", credit_account="511")
                        self.put(split, r, family, "self_approved_weekend_close", case)
                        done += 1
                    elif family=="risky_invoice":
                        v = self.vendor(cid, at-timedelta(days=90), background=False)
                        effective = at-timedelta(days=self.rng.randint(20, 60))
                        latent = case_index%4==3
                        self.status(v, "ceased" if case_index%2 else "abandoned", effective,
                                    at+timedelta(days=7) if latent else effective+timedelta(days=2))
                        r = self.transaction(cid, split, at, "vendor_payment", vendor=v, creator=creator)
                        r["invoice_issued_at"] = stamp(at-timedelta(days=5))
                        self.put(split, r, family, "inactive_issuer", case, observable="registry_reported_later" if latent else "available")
                        done += 1
                    else:
                        at = WINDOWS[split][0]+timedelta(days=self.rng.randint(105, 160), hours=self.rng.randint(9, 19))
                        self.advance(cid, split, at, creator, False, "review" if case_index%2==0 else "writeoff")
                        done += 1
                    case_index += 1

    def inject_normal_advances(self):
        # Routine issues and settlements plus legitimate delayed settlements.
        for split in WINDOWS:
            count = max(3, int(self.n*.006*(.5 if split=="train" else .25)))
            for _ in range(count):
                cid, at, creator = self.context(split, 45)
                e = self.employees[self.rng.choice(self.company_staff[cid][6:])]
                aid, case = self.identifier("A"), self.identifier("CASE")
                amount = self.rng.choice([1, 2, 3, 5, 8, 10])*1_000_000
                issue = self.transaction(cid, split, at, "advance_issue", employee=e, amount=amount, creator=creator)
                issue["advance_id"] = aid
                tid = self.put(split, issue, case=case, support=True)
                due = at+timedelta(days=30)
                self.tables["advances"].append(dict(advance_id=aid, company_id=cid, employee_id=e["employee_id"],
                    issue_transaction_id=tid, issued_at=stamp(at), recorded_at=stamp(at),
                    original_due_at=stamp(due), original_amount_vnd=amount))
                settle_at = at+timedelta(days=self.rng.randint(5, 40))
                r = self.transaction(cid, split, settle_at, "advance_settlement", employee=e, amount=amount, creator=creator)
                r["advance_id"] = aid
                tid = self.put(split, r, case=case, support=True)
                self.tables["advance_events"].append(dict(event_id=self.identifier("AE"), advance_id=aid,
                    company_id=cid, event_type="settlement", observed_at=stamp(settle_at), new_due_at="",
                    amount_vnd=amount, transaction_id=tid, evidence_on_file=1))

    def inject_hard_negatives(self):
        for split in WINDOWS:
            count = int(self.n*.05*(.5 if split=="train" else .25))
            for j in range(count):
                hard = HARD_NEGATIVES[j%len(HARD_NEGATIVES)]
                cid, at, creator = self.context(split, 12)
                case = self.identifier("CASE")
                if hard=="verified_bank_change":
                    v = self.vendor(cid, at-timedelta(days=60), background=False)
                    new_account = self.identifier("BANK_SYN_")
                    change = dict(change_id=self.identifier("BC"), company_id=cid, vendor_id=v["vendor_id"],
                        old_account=v["bank_account"], new_account=new_account, effective_at=stamp(at-timedelta(days=2)),
                        observed_at=stamp(at-timedelta(days=2)), verified_at=stamp(at-timedelta(days=1)),
                        callback_verified=1, approver_id=self.company_staff[cid][0])
                    self.tables["bank_account_changes"].append(change)
                    self.link(cid, v["vendor_id"], new_account, "bank_account", parse(change["observed_at"]))
                    r = self.transaction(cid, split, at, "vendor_payment", vendor=v, creator=creator)
                    r.update(recipient_account=new_account, bank_change_id=change["change_id"])
                elif hard=="legitimate_self_approval":
                    creator = self.company_staff[cid][0] if j%2 else creator
                    r = self.transaction(cid, split, at, "cash_expense", amount=self.rng.randint(2, 18)*100_000,
                                         creator=creator, approver=creator)
                elif hard=="weekend_operations":
                    r = self.transaction(cid, split, self.random_time(split, 12, True), "vendor_payment", creator=creator)
                elif hard=="round_recurring_payment":
                    r = self.transaction(cid, split, at, "rent", amount=self.rng.choice([5, 10, 15, 20, 30])*1_000_000, creator=creator)
                elif hard=="legitimate_installments":
                    r = self.transaction(cid, split, at, "vendor_payment", creator=creator)
                    r["invoice_gross_vnd"] = r["amount_vnd"]*2
                    self.put(split, dict(r), case=case, support=True)
                    at += timedelta(days=2)
                    r.update(posted_at=stamp(at), approved_at=stamp(at), created_at=stamp(at-timedelta(hours=4)))
                elif hard in ("new_legitimate_vendor", "declared_related_party", "historical_valid_invoice"):
                    e = self.employees[self.rng.choice(self.company_staff[cid])]
                    v = self.vendor(cid, at-timedelta(days=10),
                        registered=at-timedelta(days=20) if hard=="new_legitimate_vendor" else None,
                        phone=e["phone"] if hard=="declared_related_party" else None,
                        disclosed=hard=="declared_related_party", background=False)
                    r = self.transaction(cid, split, at, "vendor_payment", vendor=v, creator=creator)
                    if hard=="historical_valid_invoice":
                        # Goods/invoice preceded closure; payment clears a genuine existing obligation.
                        self.status(v, "ceased", at-timedelta(days=2), at-timedelta(days=1))
                        r["invoice_issued_at"] = stamp(at-timedelta(days=5))
                        r["goods_receipt_verified"] = 1
                elif hard=="long_approval_delay":
                    r = self.transaction(cid, split, at, delay_hours=self.rng.uniform(120, 504), creator=creator)
                elif hard=="remote_employee_payroll":
                    e = self.employee(cid, at.replace(day=1), mode="remote", attendance=0, append_to_background=False)
                    r = self.transaction(cid, split, at.replace(day=28), "payroll", employee=e, creator=creator)
                elif hard=="legitimate_period_close":
                    while True:
                        at = self.random_time(split, 0, True).replace(hour=22)
                        if at.day>=25:
                            break
                    creator = self.company_staff[cid][0]
                    r = self.transaction(cid, split, at, "adjustment", creator=creator, approver=creator,
                                         amount=self.rng.choice([1, 2, 5, 10, 15])*1_000_000, delay_hours=.1)
                    r.update(support_doc_count=4, business_purpose="Đối chiếu cuối kỳ")
                else:
                    at = WINDOWS[split][0]+timedelta(days=self.rng.randint(105, 160), hours=10)
                    self.advance(cid, split, at, creator, True, "writeoff" if hard=="approved_advance_writeoff" else "review", hard)
                    continue
                self.put(split, r, case=case, hard=hard)

    def finalize(self):
        self.inject_fraud()
        self.inject_normal_advances()
        self.inject_hard_negatives()
        self.rows.sort(key=lambda r: (r["posted_at"], r["transaction_id"]))
        labels = {r["transaction_id"]: r for r in self.truth}
        self.truth = [labels[r["transaction_id"]] for r in self.rows]
        self.tables["transactions"] = self.rows
        self.tables["labels"] = self.truth
        self.tables["splits"] = [dict(transaction_id=r["transaction_id"],
            split=next(s for s,(start,end) in WINDOWS.items() if start<=parse(r["posted_at"])<end)) for r in self.rows]
        self.tables["invoices"] = []
        seen = set()
        for r in self.rows:
            if r["invoice_id"] and r["invoice_id"] not in seen:
                seen.add(r["invoice_id"])
                self.tables["invoices"].append(dict(invoice_id=r["invoice_id"], company_id=r["company_id"],
                    vendor_id=r["vendor_id"], invoice_number=r["invoice_number"],
                    issued_at=r["invoice_issued_at"], recorded_at=max(r["created_at"],r["invoice_issued_at"]),
                    gross_amount_vnd=r["invoice_gross_vnd"]))
            if r["is_financial_entry"]:
                for direction, account in (("debit",r["debit_account"]),("credit",r["credit_account"])):
                    self.tables["journal_lines"].append(dict(transaction_id=r["transaction_id"], company_id=r["company_id"],
                        posted_at=r["posted_at"], account_code=account,
                        debit_vnd=r["amount_vnd"] if direction=="debit" else 0,
                        credit_vnd=r["amount_vnd"] if direction=="credit" else 0))
        from .accounting import enrich_accounting
        return enrich_accounting(self.tables,self.seed)


def generate(output: Path, n=100_000, rate=.003, seed=20261012, companies=5):
    if n<10_000 or not .001<=rate<=.005 or companies<1 or round(n*rate)<48:
        raise ValueError("Require n >= 10000, rate in [0.001, 0.005], companies >= 1 and >=48 fraudulent rows for scenario coverage")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty dataset: {output}")
    generator = Generator(n, rate, seed, companies)
    tables = generator.finalize()
    return save_dataset(output,tables,n,rate,seed,companies)


def save_dataset(output,tables,n,rate,seed,companies):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty dataset: {output}")
    output.mkdir(parents=True,exist_ok=True)
    from .features import build_features, FEATURE_DESCRIPTIONS
    tables["features"] = build_features(tables)
    for name, rows in tables.items():
        # Optional event tables can be empty on very small configurations; retain a schema.
        fields = None
        if not rows:
            fields = {"advance_events": ["event_id", "advance_id", "company_id", "event_type", "observed_at",
                       "new_due_at", "amount_vnd", "transaction_id", "evidence_on_file"]}.get(name, [])
        write_csv(output/f"{name}.csv", rows, fields)
    splits = {r["transaction_id"]:r["split"] for r in tables["splits"]}
    split_stats = {}
    for split in WINDOWS:
        ground = [r for r in tables["labels"] if splits[r["transaction_id"]]==split]
        positives = sum(r["is_fraud"] for r in ground)
        split_stats[split] = dict(rows=len(ground), fraud_rows=positives, fraud_rate=positives/len(ground),
            fraud_types=dict(Counter(r["fraud_type"] for r in ground if r["is_fraud"])))
    manifest = dict(version="2.0", seed=seed, requested_rows=n, requested_fraud_rate=rate,
        actual_fraud_rows=sum(r["is_fraud"] for r in tables["labels"]), companies=companies,
        timezone="Asia/Ho_Chi_Minh", currency="VND", observation_unit="posted transaction or nonfinancial advance review",
        financial_rows=sum(r["is_financial_entry"] for r in tables["transactions"]),
        hard_negative_rows=sum(bool(r["hard_negative_type"]) for r in tables["labels"]),
        splits=split_stats, fraud_variants=dict(Counter(r["variant"] for r in tables["labels"] if r["is_fraud"])),
        assumptions={"prevalence": "User-selected synthetic scenarios, not an estimate of Vietnam's measured fraud incidence",
            "holidays": "Illustrative fixed dates, not a complete statutory calendar",
            "journal": "TT133/TT200 scenario templates, balanced multi-line VAT and linked auxiliary documents; not a full opening/closing balance reconciliation",
            "accounting_scope": "Historical 2024-2025; TT99 is not implemented for financial years starting from 2026",
            "vat": "Credit method assumed, illustrative invoice rate 10%; not a legal tax eligibility determination",
            "expense_features": "Raw TT200 641/642 and TT133 6421/6422 retained; ML combines them into group 642",
            "auxiliary_documents": "Supporting accounting documents have no additional scored labels and do not change observation prevalence",
            "ids": "Synthetic non-usable contact/account/tax tokens; transaction IDs random and excluded from X",
            "training": "Unsupervised mixed train; labels only for evaluation; known SMEs observed over time",
            "advance_review": "Nonfinancial observation; excluded from journal lines and cash-flow totals"},
        accounting_frameworks={r['company_id']:r['accounting_framework'] for r in tables['companies']},
        journal_documents=len(tables['journal_documents']),journal_lines=len(tables['journal_lines']),
        feature_columns=list(FEATURE_DESCRIPTIONS), files={})
    for name in tables:
        path = output/f"{name}.csv"
        manifest["files"][path.name] = dict(rows=len(tables[name]), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (output/"manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    dictionary = {name: {field: {"example": rows[0].get(field),
                    "kind": "integer" if isinstance(rows[0].get(field), int) else "number" if isinstance(rows[0].get(field), float) else "text"}
                for field in rows[0]} for name, rows in tables.items() if rows}
    dictionary["features"] = FEATURE_DESCRIPTIONS
    (output/"data_dictionary.json").write_text(json.dumps(dictionary, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/sme_fraud_003"))
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--fraud-rate", type=float, default=.003)
    parser.add_argument("--seed", type=int, default=20261012)
    parser.add_argument("--companies", type=int, default=5)
    args = parser.parse_args()
    manifest = generate(args.output, args.rows, args.fraud_rate, args.seed, args.companies)
    print(json.dumps({"output":str(args.output), "fraud_rows":manifest["actual_fraud_rows"], "splits":manifest["splits"]}, indent=2))


if __name__=="__main__":
    main()
