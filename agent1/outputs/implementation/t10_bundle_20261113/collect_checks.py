"""Combine the broad run and affected rerun without hiding historical failures."""

import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
cases = {}
for name in ("tests.xml", "recheck.xml"):
    for case in ET.parse(ROOT/name).iter("testcase"):
        status = ("failed" if case.find("failure") is not None or case.find("error") is not None
                  else "skipped" if case.find("skipped") is not None else "passed")
        cases[(case.get("classname"), case.get("name"))] = status
ui = list(ET.parse(ROOT/"ui.xml").iter("testcase"))
lint = json.loads((ROOT/"ruff.json").read_text(encoding="utf-8"))
example = json.loads((ROOT/"example/verification.json").read_text(encoding="utf-8"))
result = dict(python_unique_cases=len(cases),
    python_passed=sum(s == "passed" for s in cases.values()),
    python_failed=sum(s == "failed" for s in cases.values()),
    python_skipped=sum(s == "skipped" for s in cases.values()),
    ui_passed=sum(c.find("failure") is None and c.find("error") is None for c in ui),
    ui_failed=sum(c.find("failure") is not None or c.find("error") is not None for c in ui),
    lint_issues=len(lint), noop_exact=example["noop_exact"],
    adapter_components_reconcile=example["adapter_components_reconcile"],
    paired_random_numbers=example["paired_random_numbers"],
    real_company_acceptance=False, cash_band_acceptance=False,
    aggregation="Latest result per classname/name from broad tests.xml then affected recheck.xml; not a second fresh full-suite run",
    finalized_on="2026-11-14")
(ROOT/"checks_summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
assert not result["python_failed"] and not result["ui_failed"] and not result["lint_issues"]
