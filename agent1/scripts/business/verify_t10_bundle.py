"""Generate a reviewable T10 engineering fixture, never a company-quality gate."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent1.adaptive.methods import forecast  # noqa: E402
from agent1.adaptive.t1_catalog import GlobalCatalog  # noqa: E402
from agent1.adaptive.t10_explanations import freeze_replay, replay_scenario  # noqa: E402
from agent1_service.workspace.forecast_export import workbook_bytes  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"outputs/implementation/t10_bundle_20261113/example")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cutoff = "2026-02-10"
    data = dict(invoices=[dict(invoice_id=f"I{i}", customer_id=c, amount=100_000_000,
                issue_date="2026-01-01", due_date="2026-02-01", known_at="2026-01-01")
                for i, c in enumerate(("A", "B", "A"))],
                payments=[dict(payment_id="P", invoice_id="I0", amount=40_000_000,
                    payment_date="2026-02-01", known_at="2026-02-01")],
                outflows=[dict(expense_id="RENT", amount=120_000_000, date="2026-02-12",
                               known_at=cutoff, category="rent")])
    kwargs = dict(cutoff=cutoff, balance=20_000_000, cash_floor=5_000_000,
                  horizon_weeks=13, simulation_paths=2000, simulation_seed=261113710,
                  shap_limit=3, confirmed_weeks=list(range(1, 14)))
    bundle = GlobalCatalog().default_bundle(cutoff)
    plan = forecast(data, bundle=bundle, **kwargs)
    plan.update(id="T10-ENGINE-FIXTURE", synthetic=True, real_company_acceptance=False)
    snapshot = freeze_replay(plan, data, bundle, kwargs)
    noop = replay_scenario(plan, snapshot)
    delayed = replay_scenario(plan, snapshot, customer_id="A", customer_delay_weeks=2)
    expense = replay_scenario(plan, snapshot, expense_id="RENT", expense_delay_weeks=1)
    assert all(w["baseline"] == w["scenario"] for w in noop["weeks"])
    assert delayed["delta_any_shortfall_probability"] >= 0
    assert expense["delta_any_shortfall_probability"] <= 0
    assert all(w["delta"]["expected_balance"] <= 1e-6 for w in delayed["weeks"])
    for row in plan["cash_decomposition"]["invoices"]:
        for week, expected in zip(row["receipt_explanation"]["weeks"], row["expected_by_week"], strict=True):
            assert np.isclose(week["expected_from_settlement"] + week["expected_from_partial"], expected,
                              atol=1e-6, rtol=1e-12)
    for name, value in (("forecast", plan), ("noop", noop), ("customer_delay", delayed), ("expense_deferral", expense)):
        (args.output/(name+".json")).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
    (args.output/"forecast.xlsx").write_bytes(workbook_bytes(plan, "T10-ENGINE-FIXTURE"))
    verification = dict(engine_fixture=True, real_company_acceptance=False, cash_band_acceptance=False,
        identity=plan["t10"]["identity"], invoice_count=plan["open_invoices"],
        full_shap_targets=[r["payment_explanation"]["target"] for r in plan["collections"]],
        adapter_components_reconcile=True, noop_exact=True, paired_random_numbers=True,
        baseline_any_shortfall_probability=plan["any_below_floor_probability"],
        delayed_any_shortfall_probability=delayed["scenario_any_shortfall_probability"],
        expense_deferred_any_shortfall_probability=expense["scenario_any_shortfall_probability"])
    (args.output/"verification.json").write_text(json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(verification, ensure_ascii=False))


if __name__ == "__main__":
    main()
