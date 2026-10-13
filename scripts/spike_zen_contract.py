"""Read-only probe of the installed ZEN Python binding. No financial data/API calls."""
import importlib.metadata
import json
from decimal import Decimal
from pathlib import Path

import zen


def main():
    results = {"zen_engine_version": importlib.metadata.version("zen-engine"), "probes": []}
    probes = [
        ("decimal_context", "amount >= 5000000", {"amount": Decimal("5000000.00")}),
        ("decimal_string_add", "amount + 0.01", {"amount": "5000000.01"}),
        ("small_fraction_add", "0.1 + 0.2", {}),
        ("large_integer_add", "amount + 1", {"amount": 9007199254740992}),
    ]
    for name, expression, context in probes:
        try:
            value = zen.evaluate_expression(expression, context)
            results["probes"].append({"name": name, "value": value, "python_type": type(value).__name__})
        except (TypeError, RuntimeError) as exc:
            results["probes"].append({"name": name, "error_type": type(exc).__name__, "message": str(exc)})

    root = Path(__file__).resolve().parents[1]
    model = json.loads((root / "agent3_tax_compliance/config/zen/LUAT67_ARTICLE9_v1.json").read_text(encoding="utf-8"))
    # Match the existing adapter's 0.53 normalization, without changing the source JDM.
    for node in model["nodes"]:
        if node["type"] != "decisionTableNode":
            continue
        ids = [column["id"] for column in node["content"]["inputs"]]
        for row in node["content"]["rules"]:
            for column_id in ids:
                row.setdefault(column_id, "")
                if row[column_id] in ("true", "false"):
                    row[column_id] = "== " + row[column_id]
    decision = zen.ZenEngine().create_decision(json.dumps(model))
    response = decision.evaluate({"checks": {"input_complete": False}}, {"trace": True})
    table_trace = response["trace"]["table-article9"]
    results["trace_probe"] = {
        "verdict": response["result"][0]["verdict"],
        "table_trace_keys": sorted(table_trace),
        "matched_row_keys": sorted(table_trace["traceData"][0]),
        "matched_row_id": table_trace["traceData"][0]["rule"]["_id"],
        "condition_boolean_array_provided": "conditions" in table_trace["traceData"][0],
    }
    print(json.dumps(results, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
