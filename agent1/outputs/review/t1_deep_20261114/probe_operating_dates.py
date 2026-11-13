"""Real operating learners: a retained T1 does not gate newer cash parameters."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from copy import deepcopy
import pandas as pd
from agent1.adaptive.data import validate_dataset
from agent1.adaptive.methods import train, forecast
from agent1.adaptive.operating import select_operating
from agent1.adaptive.t1_catalog import GlobalCatalog


def main():
    data = dict(invoices=[dict(invoice_id="I", customer_id="C", amount=100,
                    issue_date="2024-12-01", due_date="2024-12-31", known_at="2024-12-01")],
                payments=[], outflows=[], bank=[], statements=[], bank_scope=dict(accounts=["Q"]))
    balance = 0
    for i, end in enumerate(pd.date_range("2020-01-07", "2025-12-30", freq="7D")):
        amount = 1_000_000 + i*100_000
        day = str(end.date())
        data["bank"].append(dict(bank_id=f"B{i}", account="Q", date=day, known_at=day,
                                 amount=amount, direction="in", component="cash_sale"))
        data["statements"].append(dict(statement_id=f"S{i}", account="Q",
                                       start_date=str((end-pd.Timedelta(days=6)).date()), end_date=day,
                                       known_at=day, opening_balance=balance, closing_balance=balance+amount))
        balance += amount
    validate_dataset(data)
    cutoff, update = "2024-12-31", "2025-12-30"
    bundle = train(data, update, catalog=GlobalCatalog())
    # This is the same assignment performed in workspace/api.py's fit callback.
    bundle["operating"] = select_operating(data, update, False, include_new_credit=False)
    assert bundle["promotion_status"] == "kept_incumbent"
    assert bundle["operating"] is not None
    historical = deepcopy(bundle)
    historical["operating"] = select_operating(data, cutoff, False, include_new_credit=False)
    assert historical["operating"] is not None
    common = dict(cutoff=cutoff, balance=0, include_operating=True, shap_limit=0)
    new = forecast(data, bundle=bundle, **common)
    old = forecast(data, bundle=historical, **common)
    result = dict(update_asof=bundle["update_asof"], t1_ready_on=bundle["asof"], forecast_cutoff=cutoff,
                  fresh_operating=bundle["operating"]["name"], historical_operating=historical["operating"]["name"],
                  accepted_backdated_forecast=True,
                  fresh_model_cash_in=[w["cash_in"] for w in new["weeks"]],
                  historical_model_cash_in=[w["cash_in"] for w in old["weeks"]],
                  maximum_cash_difference=max(abs(a["cash_in"]-b["cash_in"]) for a,b in zip(new["weeks"],old["weeks"])),
                  mock_models_used=False)
    Path(__file__).with_name("operating_dates_evidence.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
