"""Anonymised export of reviewer-confirmed LEGITIMATE cases for a shared feedback corpus (v6 condition).

The v6 model learns from confirmed legitimate look-alikes of OTHER clients. This module prepares that corpus from the
review store (read-only) with an allowlist: pseudonymous company, ISO week, priority, rule codes, signal family,
the numeric feedback vector, the conclusion and a bucketed review time. It never exports names, ids, reviewer ids,
transaction ids, free-text reasons or amounts. It refuses to run without a reference to a written legal approval and a
secret salt, because sharing client data across clients needs that approval first (Pha E1). Nothing here is legal advice.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

MIN_REFERENCE_LENGTH = 8


def pseudonym(company_id, salt):
    return hashlib.sha256(f"{salt}|{company_id}".encode("utf-8")).hexdigest()[:12]


def minutes_bucket(minutes):
    return "up_to_5" if minutes <= 5 else "up_to_15" if minutes <= 15 else "over_15"


def export_confirmed_legitimate(db_path, salt, approval_reference):
    if len(str(approval_reference).strip()) < MIN_REFERENCE_LENGTH:
        raise ValueError("a reference to the written legal approval is required before any export")
    if len(str(salt)) < 16:
        raise ValueError("a secret salt of at least 16 characters is required")
    db = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    latest = {}
    for r in db.execute("SELECT * FROM decisions ORDER BY id"):
        latest[(r["company_id"], r["case_id"])] = r
    rows = []
    for r in db.execute("SELECT company_id,id,payload,created_at FROM cases"):
        decision = latest.get((r["company_id"], r["id"]))
        if decision is None or decision["conclusion"] != "legitimate":
            continue
        payload = json.loads(r["payload"])
        vector = payload.get("feedback_vector")
        rows.append({"pseudo_company": pseudonym(r["company_id"], salt), "iso_week": payload.get("iso_week"),
                     "priority": payload.get("priority"), "rule_ids": payload.get("rule_ids", ""),
                     "signal_family": (payload.get("top_signal") or "") or None,
                     "feedback_vector": [float(x) for x in vector] if isinstance(vector, list) else None,
                     "conclusion": "legitimate", "worth_review": decision["worth_review"],
                     "review_time": minutes_bucket(float(decision["review_minutes"]))})
    return {"approval_reference": str(approval_reference), "records": rows, "count": len(rows),
            "fields_excluded": ["company_id", "case_id", "transaction_ids", "reviewer_id", "reason", "amounts", "names"]}
