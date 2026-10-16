"""Input contract for read-only ingestion; never accepts truth as model input."""
from __future__ import annotations

import numpy as np
import pandas as pd


REQUIRED = {"transactions": ("company_id", "transaction_id", "posted_at", "created_at", "approved_at", "txn_type", "amount_vnd")}
MASTER_KEYS = {"employees": "employee_id", "vendors": "vendor_id", "customers": "customer_id"}
REFERENCES = {"employee_id": "employees", "creator_id": "employees", "approver_id": "employees",
              "collector_id": "employees", "vendor_id": "vendors", "customer_id": "customers"}
# These capabilities must stay disabled until all listed evidence is available.
CAPABILITIES = {
    "payroll_after_leave": {"transactions": ("employee_id",), "employees": ("terminated_at", "termination_recorded_at")},
    "payee_not_on_master": {"transactions": ("vendor_id", "recipient_account"), "vendors": ("bank_account",),
                            "bank_account_changes": ("vendor_id", "new_account", "observed_at")},
    "receipt_payer_mismatch": {"transactions": ("customer_id", "payer_account"), "customers": ("bank_account",)},
    "refund_to_foreign_account": {"transactions": ("customer_id", "recipient_account"), "customers": ("bank_account",)},
    "payroll_off_calendar": {"transactions": ("employee_id",), "companies": ("company_id", "pay_days")},
    "invoice_checks": {"transactions": ("invoice_id", "invoice_number", "invoice_gross_vnd")},
    "approval_checks": {"transactions": ("creator_id", "approver_id", "approval_limit_vnd")},
    "support_document_checks": {"transactions": ("support_doc_count",)},
}
TRUTH = {"is_fraud", "fraud_type", "case_id", "case_role", "hard_negative_type", "difficulty", "concealment", "loss_vnd"}


def validate_input(tables) -> dict:
    """Return errors, warnings and disabled capabilities; do not mutate inputs.

    Tables may be DataFrames or lists of dictionaries. Absent optional evidence
    produces an explicit reduced-mode report. A caller must honor this report;
    the legacy synthetic-data loader does not implement reduced-mode scoring.
    """
    frames = {k: v.copy() if isinstance(v, pd.DataFrame) else pd.DataFrame(v) for k, v in tables.items()}
    errors, warnings = [], []

    def issue(issues, code, table, count=1, **details):
        issues.append(dict(code=code, table=table, count=int(count), **details))

    for name, cols in REQUIRED.items():
        if name not in frames:
            issue(errors, "missing_table", name)
        else:
            missing = sorted(set(cols) - set(frames[name].columns))
            if missing:
                issue(errors, "missing_columns", name, columns=missing)
    for name in ("transactions", *MASTER_KEYS):
        if name not in frames:
            continue
        f = frames[name]
        key = "transaction_id" if name == "transactions" else MASTER_KEYS[name]
        for col in ("company_id", key):
            if col not in f:
                if name != "transactions":
                    issue(errors, "missing_columns", name, columns=[col])
                continue
            bad = f[col].isna() | f[col].astype(str).str.strip().eq("")
            if bad.any():
                issue(errors, "empty_key", name, bad.sum(), column=col)
        if {"company_id", key} <= set(f):
            bad = f.duplicated(["company_id", key], keep=False)
            if bad.any():
                issue(errors, "duplicate_key", name, bad.sum(), column=key)
        if name == "transactions" and TRUTH.intersection(f.columns):
            issue(errors, "truth_in_input", name, columns=sorted(TRUTH.intersection(f.columns)))
    tx = frames.get("transactions")
    if tx is not None:
        if tx.empty:
            issue(errors, "empty_transactions", "transactions")
        if "amount_vnd" in tx:
            amount = pd.to_numeric(tx.amount_vnd, errors="coerce")
            bad = amount.isna() | ~np.isfinite(amount) | amount.mod(1).ne(0)
            if bad.any():
                issue(errors, "invalid_amount", "transactions", bad.sum())
        dates = {}
        for col in ("created_at", "approved_at", "posted_at"):
            if col not in tx:
                continue
            dates[col] = pd.to_datetime(tx[col], utc=True, errors="coerce", format="mixed")
            bad = dates[col].isna()
            if bad.any():
                issue(errors, "invalid_datetime", "transactions", bad.sum(), column=col)
        if len(dates) == 3:
            bad = (dates["created_at"] > dates["approved_at"]) | (dates["approved_at"] > dates["posted_at"])
            if bad.any():
                issue(errors, "invalid_chronology", "transactions", bad.sum())
        for col, target in REFERENCES.items():
            if col not in tx or "company_id" not in tx:
                continue
            populated = tx[col].notna() & tx[col].astype(str).ne("")
            if not populated.any():
                continue
            master = frames.get(target)
            key = MASTER_KEYS[target]
            if master is None:
                issue(warnings, "missing_master", target, populated.sum(), reference=col)
                continue
            if not {"company_id", key} <= set(master):
                continue
            known = pd.MultiIndex.from_frame(master[["company_id", key]].astype(str))
            observed = pd.MultiIndex.from_frame(tx.loc[populated, ["company_id", col]].astype(str))
            bad = ~observed.isin(known)
            if bad.any():
                issue(errors, "invalid_foreign_key", "transactions", bad.sum(), column=col, target=target)
    disabled = {}
    for capability, deps in CAPABILITIES.items():
        missing = [f"{name}.{col}" for name, cols in deps.items() for col in cols
                   if name not in frames or col not in frames[name]]
        if missing:
            disabled[capability] = missing
    if disabled:
        issue(warnings, "reduced_mode_required", "transactions", capabilities=sorted(disabled))
    return {"status": "error" if errors else ("reduced" if warnings else "passed"),
            "errors": errors, "warnings": warnings, "disabled_capabilities": disabled,
            "rows": 0 if tx is None else len(tx)}
