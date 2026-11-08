"""Read-only firm/time and supplier-payable diagnostics for existing worlds.

This script never opens test-world invoices or payments. Its inputs are named
train/control worlds; all outputs are aggregate diagnostics for review.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.data.world_manifest import verify_world_manifest
from agent1.paths import SYNTH


def audit_world(name: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    path = SYNTH / name
    verify_world_manifest(path, validate=True)
    inv = pd.read_parquet(path / "invoices.parquet", columns=[
        "firm_id", "customer_id", "issue_date", "due_date", "amount_net", "remaining_amount",
    ])
    firms = pd.read_parquet(path / "firms.parquet")
    macro = pd.read_parquet(path / "macro.parquet", columns=[
        "week", "common_factor", "covid_stress", "credit_crunch",
    ])
    inventory = pd.read_parquet(path / "inventory_weekly.parquet")
    inv["year"] = inv.issue_date.dt.year
    inv["month"] = inv.issue_date.dt.to_period("M").astype(str)
    annual = inv.groupby(["firm_id", "year"], as_index=False).agg(
        revenue_vnd=("amount_net", "sum"), invoices=("amount_net", "size"),
        active_customers=("customer_id", "nunique"),
    )
    annual = annual.merge(firms, on="firm_id", validate="many_to_one")
    annual.insert(0, "world", name)
    monthly = inv.groupby(["firm_id", "month"], as_index=False).agg(
        revenue_vnd=("amount_net", "sum"), invoices=("amount_net", "size"),
        active_customers=("customer_id", "nunique"),
    )
    monthly.insert(0, "world", name)
    annual["ratio_2025_2019"] = annual.revenue_vnd / annual.firm_id.map(
        annual[annual.year.eq(2019)].set_index("firm_id").revenue_vnd)
    annual["ratio_2025_2024"] = annual.revenue_vnd / annual.firm_id.map(
        annual[annual.year.eq(2024)].set_index("firm_id").revenue_vnd)
    macro["year"] = macro.week.dt.year
    macro = macro.groupby("year", as_index=False)[[
        "common_factor", "covid_stress", "credit_crunch",
    ]].mean()
    macro.insert(0, "world", name)

    purchases = inventory[inventory.purchase_gross.gt(0)].copy()
    purchases["year"] = purchases.purchase_date.dt.year
    purchases["payment_lag_days"] = (
        purchases.supplier_pay_date - purchases.purchase_date).dt.days
    ap_rows = []
    for year in range(2019, 2026):
        cutoff = pd.Timestamp(year, 12, 31)
        issued = purchases[purchases.purchase_date.dt.year.eq(year)]
        outstanding = purchases[purchases.purchase_date.le(cutoff) &
                                purchases.supplier_pay_date.gt(cutoff)]
        overdue = (outstanding[outstanding.supplier_due_date.lt(cutoff)]
                   if 'supplier_due_date' in outstanding else outstanding.iloc[0:0])
        ap_rows.append({
            "world": name, "year": year,
            "supplier_purchase_gross_vnd": float(issued.purchase_gross.sum()),
            "year_end_open_ap_vnd": float(outstanding.purchase_gross.sum()),
            "year_end_overdue_ap_vnd": float(overdue.purchase_gross.sum()),
            "supplier_payment_lag_weighted_days": float(np.average(
                issued.payment_lag_days, weights=issued.purchase_gross)) if len(issued) else np.nan,
            "open_ap_to_year_purchase": float(outstanding.purchase_gross.sum() /
                                              issued.purchase_gross.sum()) if len(issued) else np.nan,
            "supplier_purchases": int(len(issued)),
        })
    ap = pd.DataFrame(ap_rows)
    end = pd.Timestamp(2025, 12, 31)
    ar = inv.groupby("firm_id", as_index=False).agg(open_ar_vnd=("remaining_amount", "sum"))
    late = inv[inv.due_date.lt(end)].groupby("firm_id").remaining_amount.sum()
    ar["overdue_ar_vnd"] = ar.firm_id.map(late).fillna(0)
    ap_2025 = purchases[purchases.purchase_date.le(end) &
                        purchases.supplier_pay_date.gt(end)].groupby("firm_id").purchase_gross.sum()
    ar["open_ap_vnd"] = ar.firm_id.map(ap_2025).fillna(0)
    ar = ar.merge(firms, on="firm_id", validate="one_to_one")
    ar = ar.merge(annual[annual.year.eq(2025)][["firm_id", "revenue_vnd"]],
                  on="firm_id", validate="one_to_one")
    ar.insert(0, "world", name)
    ar["overdue_ar_share"] = ar.overdue_ar_vnd / ar.open_ar_vnd.replace(0, np.nan)
    ar["ap_to_revenue"] = ar.open_ap_vnd / ar.revenue_vnd.replace(0, np.nan)
    ar["ar_to_revenue"] = ar.open_ar_vnd / ar.revenue_vnd.replace(0, np.nan)
    return annual, monthly, macro.merge(ap, on=["world", "year"], validate="one_to_one"), ar


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("worlds", nargs="+", help="Only train/validation or historical control worlds")
    args = p.parse_args()
    if any("_test_" in name for name in args.worlds):
        raise ValueError("Test outcome seal: do not pass a test World")
    outputs = [audit_world(name) for name in args.worlds]
    args.output.mkdir(parents=True, exist_ok=True)
    for filename, frames in (
        ("firm_year.csv", [item[0] for item in outputs]),
        ("firm_month.csv", [item[1] for item in outputs]),
        ("macro_ap_year.csv", [item[2] for item in outputs]),
        ("firm_2025_ar_ap.csv", [item[3] for item in outputs]),
    ):
        pd.concat(frames, ignore_index=True).to_csv(args.output / filename, index=False)
    print(f"Audited {len(outputs)} worlds -> {args.output}")


if __name__ == "__main__":
    main()
