"""Sealed holdout worlds: three fraud families that were NOT used while developing detectors.

Written before looking at any detector output on them; evaluated exactly once at the end.
  price_creep        a colluding pair raises one vendor's unit price 2-4 percent per payment (no single jump)
  off_cycle_payroll  extra payroll payments to a real employee outside the normal pay date, small team of two
  vendor_burst       one user posts 4-6 payments to different existing vendors in one late evening
Decoys added: legit_offcycle_payroll (director-approved advance on salary, well documented).
"""
from __future__ import annotations

import math
from datetime import timedelta
from pathlib import Path

from sme_fraud.generate import WINDOWS, parse, save_dataset

from .world_v3 import FAMILIES_V3, WorldV3

SEALED_FAMILIES = ["price_creep", "off_cycle_payroll", "vendor_burst"]
ALL_SEALED = FAMILIES_V3 + SEALED_FAMILIES
DECOYS_SEALED = ["legit_offcycle_payroll"]


class WorldSealed(WorldV3):
    def inject_fraud(self):
        from sme_fraud.generate import allocate
        total = round(self.n * self.rate)
        counts = allocate(total, [len(self.pools[s]) for s in WINDOWS])
        for split, count in zip(WINDOWS, counts):
            for family, budget in zip(ALL_SEALED, allocate(count, [1] * len(ALL_SEALED))):
                getattr(self, f"fraud_{family}")(split, budget)

    def fraud_price_creep(self, split, budget):
        def build(k, remaining):
            cid, _, _ = self.context(split, 10)
            case, d = self.identifier("CASE"), self.pick_difficulty()
            staff = self.company_staff[cid]
            creator, approver = self.rng.sample(staff[1:6], 2)
            start = WINDOWS[split][0] + timedelta(days=self.rng.randint(8, 25))
            legacy = [v for v in self.company_vendors[cid] if parse(self.vendors[v]["onboarded_at"]) < start - timedelta(days=200)]
            v = self.vendors[self.rng.choice(legacy)]
            growth = self.rng.uniform(.02, .04) if d != "hard" else self.rng.uniform(.012, .02)
            labelled, markup, n = 0, 1.0, 0
            when = start
            while labelled < remaining and when < WINDOWS[split][1] - timedelta(days=2) and n < 14:
                amount = int(self.vendor_amount(v, when) * markup / 1000) * 1000
                r = self.transaction(cid, split, when, "vendor_payment", vendor=v, amount=amount, creator=creator,
                                     approver=approver, price_markup=markup)
                if markup >= 1.08:
                    self.put(split, r, "price_creep", "gradual_unit_price_increase", case, difficulty=d)
                    labelled += 1
                else:
                    self.put(split, r, case=case, support=True)
                markup *= 1 + growth
                n += 1
                when += timedelta(days=self.rng.randint(11, 17), hours=self.rng.randint(0, 5))
            return max(1, labelled)
        self._loop(budget, build)

    def fraud_off_cycle_payroll(self, split, budget):
        def build(k, remaining):
            cid, at, creator = self.context(split, 30)
            case, d = self.identifier("CASE"), self.pick_difficulty()
            staff = self.company_staff[cid]
            e = self.employees[self.rng.choice(staff[6:])]
            n_rows = min(remaining, self.rng.randint(2, 3))
            for j in range(n_rows):
                when = (at + timedelta(days=40 * j)).replace(day=self.rng.randint(8, 18), hour=self.rng.randint(9, 17))
                when = min(max(when, WINDOWS[split][0] + timedelta(days=1)), WINDOWS[split][1] - timedelta(days=1))
                r = self.transaction(cid, split, when, "payroll", employee=e, creator=creator)
                r["amount_vnd"] = int(round(e["monthly_salary_vnd"] * self.rng.uniform(.6, 1.2) / 1000) * 1000)
                r["support_doc_count"] = self.rng.choice([0, 1]) if d != "hard" else self.rng.choice([1, 2])
                self.put(split, r, "off_cycle_payroll", "extra_payment_outside_pay_date", case, difficulty=d)
            return n_rows
        self._loop(budget, build)

    def fraud_vendor_burst(self, split, budget):
        def build(k, remaining):
            cid, at, creator = self.context(split, 12)
            case, d = self.identifier("CASE"), self.pick_difficulty()
            at = at.replace(hour=self.rng.randint(19, 21), minute=0)
            n_rows = min(remaining, self.rng.randint(4, 6))
            ids = [v for v in self.company_vendors[cid] if parse(self.vendors[v]["onboarded_at"]) < at - timedelta(days=30)]
            for j, vid in enumerate(self.rng.sample(ids, min(n_rows, len(ids)))):
                r = self.transaction(cid, split, at + timedelta(minutes=12 * j), "vendor_payment", vendor=self.vendors[vid],
                                     creator=creator, delay_hours=self.rng.uniform(.1, 3))
                self.put(split, r, "vendor_burst", "late_evening_multi_vendor_burst", case, difficulty=d)
            return min(n_rows, len(ids))
        self._loop(budget, build)

    def inject_hard_negatives(self):
        super().inject_hard_negatives()
        done = 0
        for split in WINDOWS:
            for _ in range(int(self.n * .004 * (.5 if split == "train" else .25))):
                cid, at, creator = self.context(split, 12)
                e = self.employees[self.rng.choice(self.company_staff[cid][6:])]
                r = self.transaction(cid, split, at.replace(day=self.rng.randint(8, 18)), "payroll", employee=e, creator=creator,
                                     approver=self.company_staff[cid][0])
                r["amount_vnd"] = int(round(e["monthly_salary_vnd"] * self.rng.uniform(.3, .6) / 1000) * 1000)
                r["support_doc_count"] = self.rng.choice([3, 4])
                self.put(split, r, hard="legit_offcycle_payroll")
                done += 1


def generate_sealed(output, n=100_000, rate=.0036, seed=901, companies=8):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty dataset: {output}")
    g = WorldSealed(n, rate, seed, companies)
    tables = g.finalize()
    return save_dataset(output, tables, n, rate, seed, companies)
