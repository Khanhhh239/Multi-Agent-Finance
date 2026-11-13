"""Merge the broad run with subsequent targeted fixes by pytest case identity."""

import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
FILES = ("tests.xml", "recheck.xml", "periodic_and_joint.xml", "final_cash.xml")
cases = {}
for name in FILES:
    for case in ET.parse(ROOT/name).iter("testcase"):
        key = (case.get("classname"), case.get("name"))
        status = "failed" if case.find("failure") is not None or case.find("error") is not None else (
            "skipped" if case.find("skipped") is not None else "passed")
        cases[key] = dict(status=status, evidence=name)
result = dict(python_unique_cases=len(cases),
              python_passed=sum(v["status"] == "passed" for v in cases.values()),
              python_failed=sum(v["status"] == "failed" for v in cases.values()),
              python_skipped=sum(v["status"] == "skipped" for v in cases.values()),
              evidence=list(FILES),
              interpretation="Latest outcome per pytest case; broad run plus affected-case reruns, not another full run")
node_cases = list(ET.parse(ROOT/"ui.xml").iter("testcase"))
result["ui_passed"] = sum(c.find("failure") is None and c.find("error") is None for c in node_cases)
result["ui_failed"] = len(node_cases)-result["ui_passed"]
result["lint_issues"] = len(json.loads((ROOT/"ruff.json").read_text(encoding="utf-8-sig")))
verification = json.loads((ROOT/"fresh_synthetic_final/verification.json").read_text(encoding="utf-8"))
result["synthetic_integration"] = dict(status=verification["status"], companies=verification["companies"],
    all_predictions_frozen_before_scoring=verification["all_predictions_frozen_before_scoring"],
    real_company_acceptance=False, cash_band_acceptance=False)
(ROOT/"checks_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
if result["python_failed"] or result["ui_failed"] or result["lint_issues"]:
    raise SystemExit(1)
