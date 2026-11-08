"""Validate demo imports, deliberate failures and scenario differences."""

import json, csv, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent1.adaptive.data import parse_rows, suggested_mapping, validate_dataset

folder = ROOT / "pilot/demo_dai_phat"
data = {}
results = []
for path in sorted(folder.glob("*.csv")):
    kind = path.stem.split("_", 1)[1]
    raw = pd.read_csv(path, dtype=str)
    rows, errors, _ = parse_rows(
        raw,
        kind,
        suggested_mapping(raw.columns, kind),
        date_format="%Y-%m-%d",
        number_format="plain",
    )
    assert not errors, (kind, errors[:2])
    data[kind] = rows
    results.append(dict(check="import_" + kind, status="passed", count=len(rows)))
validate_dataset(data)
results.append(
    dict(
        check="cross_table_reconciliation",
        status="passed",
        count=len(data["statements"]),
    )
)
for path in (folder / "invalid_cases").glob("*.csv"):
    raw = pd.read_csv(path, dtype=str)
    _, errors, _ = parse_rows(
        raw,
        "invoices",
        suggested_mapping(raw.columns, "invoices"),
        date_format="%Y-%m-%d",
        number_format="plain",
    )
    assert errors, path
    results.append(
        dict(check="reject_" + path.stem, status="passed", count=len(errors))
    )
payload = json.loads(
    (ROOT / "agent1_service/ui/workspace/dai-phat-data.json").read_text(
        encoding="utf-8"
    )
)
plans = payload["plans"]
assert len(plans["base"]["weeks"]) == 13
assert plans["cost"]["minimum_balance"] < plans["base"]["minimum_balance"]
assert sum(r["cash_in"] for r in plans["delay"]["weeks"]) <= sum(
    r["cash_in"] for r in plans["base"]["weeks"]
)
assert plans["base"]["minimum_balance"] > 200000000
assert plans["delay"]["minimum_balance"] < 0
results.append(dict(check="forecast_scenarios", status="passed", count=4))
output = ROOT / "outputs/business/demo_dai_phat_checks.csv"
output.parent.mkdir(parents=True, exist_ok=True)
with output.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["check", "status", "count"])
    w.writeheader()
    w.writerows(results)
print(f"{len(results)} demo checks passed")
