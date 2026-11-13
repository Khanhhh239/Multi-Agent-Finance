"""Re-evaluate the v2 production selector on an existing synthetic company.

This is a reproducible integration audit on previously inspected synthetic
data, not evidence on a new company/holdout and never a tenant activation.
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent1.adaptive.cash_adapter import VERSION as ADAPTER_VERSION
from agent1.adaptive.ledger_bridge import workspace_data
from agent1.adaptive.methods import forecast
from agent1.adaptive.t1_catalog import GlobalCatalog
from agent1.adaptive.t1_update import UpdatePolicy, code_signature, train_update
from experiments.t1_compact.train import world_ledgers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--firm", default="F013")
    parser.add_argument("--world", type=Path, default=ROOT / "outputs/t1/aligned_refit_20261112/worlds/refit_04_fresh_test")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/implementation/t1_partial_bundle_v2_20261113")
    args = parser.parse_args()
    ledger = next(ledger for firm, ledger in world_ledgers(args.world) if firm == args.firm)
    data = workspace_data(ledger)
    # Simulator exports supply complete observed cash ledgers. Explicit dated
    # confirmations are fixture evidence, not inferred from absence of receipts.
    dates = {str(d.date()) for d in pd.date_range("2019-01-31", "2025-12-31", freq="ME")}
    dates.update(("2025-06-04", "2025-10-01", "2025-12-31"))
    data["payment_coverage"] = [dict(start_date="2019-01-01", end_date=d, known_at=d,
                                      complete=True, source="complete_synthetic_ledger") for d in sorted(dates)]
    catalog = GlobalCatalog()
    policy = UpdatePolicy(stride_days=56, risk_cap=2000, alphas=(0.0, 1.0))
    bundle = train_update(data, "2025-12-31", print, catalog=catalog, policy=policy,
                          grids={"neural": ((0.0001, 2),), "lightgbm": ((0.02, 4),),
                                 "xgboost": ((0.02, 4),)})
    plan = forecast(data, "2025-12-31", 0, bundle, shap_limit=0, simulation_paths=1000)
    report = dict(firm=args.firm, world=str(args.world), cutoff="2025-12-31",
                  code_sha256=code_signature(), catalog_sha256=catalog.digest,
                  adapter_version=ADAPTER_VERSION, algorithm_version=bundle["algorithm_version"],
                  promotion_status=bundle["promotion_status"], windows=bundle["windows"],
                  fit_data=bundle.get("fit_data"), locked_spec=bundle.get("locked_spec"),
                  partial_selection=bundle.get("partial_selection"), selection=bundle["selection"],
                  audit=bundle["audit"], forecast=dict(open_invoices=plan["open_invoices"],
                  outstanding=plan["outstanding"], partial_cash_supported=plan["partial_cash_supported"],
                  expected_receipts=sum(w["cash_in"] for w in plan["weeks"])),
                  limitation="Existing synthetic world and previously inspected origins; reduced fixed compute grid. No new holdout or real-company quality claim.")
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / f"{args.firm}_pipeline_audit.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
