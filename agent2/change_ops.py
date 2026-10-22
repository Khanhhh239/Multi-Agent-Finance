"""Operational wrapper for v5 change features on a real company's snapshot (explanations only).

Real exports may lack some columns (`unit_price_vnd`, `applied_invoice_id`, `collector_id`, `advance_id`) or the
company table. Missing columns are treated as empty and missing customer terms default to 30 days; the core
`change_detect` code is untouched. Used to ADD evidence-checked Vietnamese observations to alerts; it never changes
which rows are alerted. The invoice-link features excluded by R1 v1.3 are not used for explanations either.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from .change_detect import EntityDeviation2, change_features
from .screen_v5 import LINK_SHORTCUT

NEEDED = ["transaction_id", "company_id", "posted_at", "txn_type", "amount_vnd", "unit_price_vnd", "vendor_id",
          "customer_id", "employee_id", "creator_id", "invoice_id", "applied_invoice_id", "collector_id", "advance_id"]


def lenient_change_features(snapshot: Path) -> pd.DataFrame:
    snapshot = Path(snapshot)
    tx = pd.read_csv(snapshot / "transactions.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    for column in NEEDED:
        if column not in tx:
            tx[column] = ""
    companies = snapshot / "companies.csv"
    comp = pd.read_csv(companies, dtype=str, keep_default_na=False, encoding="utf-8-sig") if companies.exists() else pd.DataFrame()
    if "customer_terms_days" not in comp or "company_id" not in comp:
        comp = pd.DataFrame({"company_id": tx.company_id.unique(), "customer_terms_days": "30"})
    comp["customer_terms_days"] = pd.to_numeric(comp.customer_terms_days, errors="coerce").fillna(30).astype(int).astype(str)
    with tempfile.TemporaryDirectory() as tmp:
        tx[NEEDED].to_csv(Path(tmp) / "transactions.csv", index=False)
        comp[["company_id", "customer_terms_days"]].to_csv(Path(tmp) / "companies.csv", index=False)
        return change_features(tmp)


class ChangeExplainer:
    """Fit EntityDeviation2 on the company's own history (no labels); give detector tails for alerted rows."""

    def fit(self, history: pd.DataFrame):
        self.model = EntityDeviation2().fit(history, history.txn_type.to_numpy())
        return self

    def parts(self, frame: pd.DataFrame) -> dict:
        parts = self.model.parts(frame, frame.txn_type.to_numpy())
        return {name: values for name, values in parts.items() if name not in LINK_SHORTCUT}
