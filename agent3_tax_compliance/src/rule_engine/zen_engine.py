"""GoRules ZEN adapter for versioned Vietnamese tax decision models."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import zen


class ZenTaxRuleEngine:
    """Load and evaluate a JDM decision while enforcing its effective dates."""

    def __init__(self, decision_path: str | Path):
        self.decision_path = Path(decision_path)
        content = self.decision_path.read_text(encoding="utf-8")
        self.model = json.loads(content)
        self.meta = self.model.get("meta", {})
        # In a JDM input cell, a bare boolean is evaluated as the row result.
        # ``false`` would therefore never match. Normalize the readable boolean
        # cells in our checked-in model to unary comparisons understood by ZEN.
        for node in self.model.get("nodes", []):
            if node.get("type") != "decisionTableNode":
                continue
            input_ids = {
                column["id"] for column in node.get("content", {}).get("inputs", [])
            }
            for rule in node.get("content", {}).get("rules", []):
                for input_id in input_ids:
                    # ZEN 0.53 treats a missing cell differently from an
                    # explicitly blank cell. Blank cells mean "always true".
                    rule.setdefault(input_id, "")
                    if rule.get(input_id) in {"true", "false"}:
                        rule[input_id] = f"== {rule[input_id]}"
        self.decision = zen.ZenEngine().create_decision(
            json.dumps(self.model, ensure_ascii=False)
        )

    @staticmethod
    def _parse_date(value: str | date | datetime) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return datetime.strptime(value.split("T", 1)[0], "%Y-%m-%d").date()

    def is_active(self, transaction_date: str | date | datetime) -> bool:
        checked_date = self._parse_date(transaction_date)
        effective_from = self.meta.get("effectiveFrom")
        effective_to = self.meta.get("effectiveTo")
        if effective_from and checked_date < self._parse_date(effective_from):
            return False
        if effective_to and checked_date > self._parse_date(effective_to):
            return False
        return True

    def evaluate(self, context: dict[str, Any], transaction_date: str) -> dict[str, Any]:
        if not self.is_active(transaction_date):
            return {
                "verdict": "NOT_APPLICABLE",
                "hits": [],
                "ruleset": self.meta.get("ruleSetId"),
                "version": self.meta.get("version"),
            }

        response = self.decision.evaluate(context)
        raw_result = response.get("result", [])
        hits = raw_result if isinstance(raw_result, list) else ([raw_result] if raw_result else [])
        verdicts = {hit.get("verdict") for hit in hits}
        verdict = "FAIL" if "FAIL" in verdicts else "REVIEW" if "REVIEW" in verdicts else "PASS"
        return {
            "verdict": verdict,
            "hits": hits,
            "ruleset": self.meta.get("ruleSetId"),
            "version": self.meta.get("version"),
            "performance": response.get("performance"),
        }
