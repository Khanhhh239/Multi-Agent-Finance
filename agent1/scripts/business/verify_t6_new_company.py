"""Fresh synthetic integration evidence; never a real-company quality gate."""

import argparse
import calendar
from datetime import date, timedelta
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent1.adaptive.data import fingerprint, validate_dataset
from agent1.adaptive.t1_catalog import GlobalCatalog
from agent1.adaptive.t1_update import UpdatePolicy
from experiments.t6_backtest.new_company import freeze_predictions, lock_protocol, score_frozen, write_once

SEED = 261113605
CUTOFF = "2025-12-31"
TRUTH = "2026-04-30"


def synthetic_company(index):
    rng = np.random.default_rng(SEED+index)
    first, cutoff, last = date(2024, 1, 1), date.fromisoformat(CUTOFF), date.fromisoformat(TRUTH)
    data = dict(invoices=[], payments=[], bank=[], statements=[], outflows=[], payment_coverage=[])
    for week in range((cutoff-first).days//7):
        issued = first+timedelta(weeks=week)
        for j in range(3):
            iid = f"FRESH{index}-{week}-{j}"
            amount = int(rng.integers(15, 36))*100000
            data["invoices"].append(dict(invoice_id=iid, customer_id=f"FRESH{index}-C{week%8}",
                issue_date=str(issued), due_date=str(issued+timedelta(days=30)), known_at=str(issued), amount=amount))
            slow = rng.random() < (.25 if index == 0 else .5)
            # Both a tail-only partial case and an eventual cash-full case.
            receipts = [(7+7*(week%3), amount//4)]
            if not slow:
                receipts += [(28, amount//4), (49+7*(week%4), amount-2*(amount//4))]
            elif week%3 == 0:
                receipts += [(140, amount-amount//4)]
            for part, (delay, value) in enumerate(receipts):
                paid = issued+timedelta(days=delay)
                if paid > last:
                    continue
                pid = f"{iid}-{part}"
                data["payments"].append(dict(payment_id=pid, invoice_id=iid, amount=value,
                    payment_date=str(paid), known_at=str(paid), bank_id=pid))
                data["bank"].append(dict(bank_id=pid, account="Q", amount=value, direction="in",
                    date=str(paid), known_at=str(paid), component="other"))
    day, week = first, 0
    while day <= last:
        value = 3600000+index*1000000
        eid = f"COST-{week}"
        data["outflows"].append(dict(expense_id=eid, date=str(day), known_at=str(min(day, cutoff)),
                                    amount=value, category="rent"))
        data["bank"].append(dict(bank_id=eid, account="Q", date=str(day), known_at=str(day),
                                 amount=value, direction="out", component="other"))
        week += 1; day += timedelta(weeks=1)
    # Explicit bank allocations make cash-scope error attribution testable.
    data["expense_payments"] = [dict(settlement_id=r["bank_id"], expense_id=r["bank_id"],
        bank_id=r["bank_id"], amount=r["amount"], payment_date=r["date"], known_at=r["known_at"])
        for r in data["bank"] if r["direction"] == "out"]
    opening, month = 100000000, first
    while month <= last:
        end = min(last, date(month.year, month.month, calendar.monthrange(month.year, month.month)[1]))
        closing = opening+sum((1 if r["direction"] == "in" else -1)*r["amount"]
                              for r in data["bank"] if str(month) <= r["date"] <= str(end))
        data["statements"].append(dict(statement_id=str(month), account="Q", start_date=str(month),
            end_date=str(end), known_at=str(end), opening_balance=opening, closing_balance=closing))
        data["payment_coverage"].append(dict(complete=True, start_date=str(month), end_date=str(end), known_at=str(end)))
        opening = closing
        month = end+timedelta(days=1)
    validate_dataset(data)
    opening = next(r["closing_balance"] for r in data["statements"] if r["end_date"] == CUTOFF)
    return data, opening


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"outputs/implementation/t6_partial_paths_20261113/fresh_synthetic_final")
    parser.add_argument("--catalog", type=Path)
    args = parser.parse_args()
    catalog = GlobalCatalog(args.catalog)
    companies, datasets = [], []
    for i in range(2):
        data, opening = synthetic_company(i)
        source = args.output/f"synthetic_company_{i}.json"
        write_once(source, data)
        datasets.append(data)
        companies.append(dict(firm_id=f"T6_FRESH_{SEED}_{i}", dataset=str(source.resolve()),
            cutoff=CUTOFF, truth_asof=TRUTH, opening_balance=opening, accounts=["Q"],
            synthetic=True, generator_seed=SEED+i, dataset_sha256=fingerprint(data),
            heldout_from_global_and_policy_selection=True))
    policy = UpdatePolicy(stride_days=56, risk_cap=3000)
    protocol = args.output/"protocol.json"
    lock_protocol(protocol, companies, catalog, policy=policy, cash_floor=0, simulation_paths=1000)
    # Freeze every company's predictions before opening any company's outcomes.
    for case, data in zip(companies, datasets):
        freeze_predictions(protocol, case["firm_id"], data, catalog)
        print(case["firm_id"]+": predictions frozen", flush=True)
    results = [score_frozen(protocol, case["firm_id"], data) for case, data in zip(companies, datasets)]
    write_once(args.output/"verification.json", dict(
        status="synthetic_integration_only", companies=len(companies), seed=SEED,
        all_predictions_frozen_before_scoring=True, results=results,
        limitation="Fresh toy ledgers from this script, not real companies or evidence of generalization; no tenant activation"))
    print(json.dumps(dict(status="synthetic_integration_only", companies=len(companies)), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
