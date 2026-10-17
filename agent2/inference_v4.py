"""Build operational features from an explicit raw-table allowlist, without labels.

Unlike the research loader, this never opens labels, truth_cases, splits, cached
feature files or a synthetic-world manifest. Snapshot tables are bounded by the
requested week before feature extraction and rule execution.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from sme_fraud.features import build_features
from sme_fraud.rules import INPUT_TABLES, OPTIONAL_INPUT_TABLES, RULE_NAMES, score_rules

from . import accounting_ext  # noqa: F401; use the same v4 templates as the generator
from .feats import engineered_features
from .feats_v4 import v4_features
from .schema import validate_input
from .input_values import normalize

TABLES = (*INPUT_TABLES, *OPTIONAL_INPUT_TABLES, "journal_lines")
REQUIRED_TABLES = set(INPUT_TABLES) | {"journal_lines"}


class ReducedInput(ValueError):
    def __init__(self, report):
        self.report = report
        super().__init__("insufficient evidence for the full frozen v4 model; see input_report")


def week_bounds(week):
    if not re.fullmatch(r"\d{4}-W\d{2}", week):
        raise ValueError("week must use YYYY-Www")
    year, number = int(week[:4]), int(week[6:])
    day = dt.date.fromisocalendar(year, number, 1)
    start = pd.Timestamp(day).tz_localize("Asia/Ho_Chi_Minh")
    return start, start + pd.Timedelta(days=7)


def snapshot_input(data, out, company_id, week, require_full=True):
    data, out = Path(data), Path(out)
    _, end = week_bounds(week)
    frames, hashes = {}, {}
    for name in TABLES:
        path = data / f"{name}.csv"
        if not path.exists():
            continue
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        if "company_id" in frame:
            frame = frame[frame.company_id == str(company_id)].copy()
        frame = normalize(frame)
        observed = next((c for c in ("observed_at", "recorded_at") if c in frame), None)
        if name == "transactions":
            observed = "posted_at"
        if observed:
            dates = pd.to_datetime(frame[observed], utc=True, errors="coerce", format="mixed")
            if dates.isna().any():
                raise ValueError(f"invalid observation timestamp in {name}.{observed}")
            frame = frame[dates < end].copy()
        frames[name] = frame
    if "transactions" not in frames:
        raise ValueError("transactions.csv is required")
    tx = frames["transactions"]
    if "journal_lines" in frames and "transaction_id" in frames["journal_lines"]:
        frames["journal_lines"] = frames["journal_lines"][frames["journal_lines"].transaction_id.isin(tx.transaction_id)].copy()
    report = validate_input(frames)
    if report["errors"]:
        raise ValueError(f"input contract errors: {report['errors']}")
    missing = sorted(REQUIRED_TABLES - set(frames))
    contract = Path(__file__).resolve().parents[1] / 'configs' / 'v4_input_columns.json'
    columns = json.loads(contract.read_text(encoding='utf-8'))
    missing_columns = {name: sorted(set(required) - set(frames[name]))
                       for name, required in columns.items() if name in frames and set(required) - set(frames[name])}
    if missing or missing_columns or report["disabled_capabilities"]:
        report["missing_full_model_tables"] = missing
        report["missing_full_model_columns"] = missing_columns
        report["status"] = "reduced"
        if require_full:
            raise ReducedInput(report)
    out.mkdir(parents=True, exist_ok=True)
    for name, frame in frames.items():
        target = out / f"{name}.csv"
        frame.to_csv(target, index=False, encoding="utf-8-sig")
        hashes[target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
    return frames, report, hashes


def build(data, snapshot, company_id, week):
    frames, report, hashes = snapshot_input(data, snapshot, company_id, week)
    tables = {name: frame.to_dict("records") for name, frame in frames.items()}
    for name in OPTIONAL_INPUT_TABLES:
        tables.setdefault(name, [])
    features = build_features(tables)
    if not features:
        raise ValueError("no transactions before the requested week end")
    graph = score_rules(tables, config=None, features=features)
    direct = score_rules(tables, config={"enable_graph": False}, features=features)
    rule = pd.DataFrame({"transaction_id": [r["transaction_id"] for r in graph["scores"]],
                         "rule_graph": [float(r["rule_score"]) for r in graph["scores"]],
                         "rule_hard": [float(r["hard_trigger"]) for r in graph["scores"]],
                         "rule_ids": [r["rule_ids"] for r in graph["scores"]],
                         "explanation_vi": [r["explanation_vi"] for r in graph["scores"]]})
    rule = rule.merge(pd.DataFrame({"transaction_id": [r["transaction_id"] for r in direct["scores"]],
                                   "rule_direct": [float(r["rule_score"]) for r in direct["scores"]]}), on="transaction_id", validate="one_to_one")
    hits = {f"hit_{rid}": np.zeros(len(rule)) for rid in sorted(RULE_NAMES)}
    evidence = {tid: {} for tid in rule.transaction_id}
    position = {tid: i for i, tid in enumerate(rule.transaction_id)}
    for hit in graph["hits"]:
        if not hit["suppressed_reason"]:
            col, index = f"hit_{hit['rule_id']}", position[hit["transaction_id"]]
            hits[col][index] = max(hits[col][index], hit["points"])
            evidence[hit["transaction_id"]][hit["rule_id"]] = hit["evidence"]
    rule = pd.concat([rule, pd.DataFrame(hits)], axis=1)
    rule["rule_evidence_json"] = rule.transaction_id.map(lambda tid: json.dumps(evidence[tid], ensure_ascii=False))
    keep = ["transaction_id", "company_id", "posted_at", "txn_type", "vendor_id", "employee_id", "creator_id", "approver_id",
            "amount_vnd", "invoice_number", "accounting_framework", "customer_id", "collector_id"]
    df = frames["transactions"][keep].copy()
    for feature in (pd.DataFrame(features), engineered_features(snapshot), v4_features(snapshot), rule):
        df = df.merge(feature, on="transaction_id", validate="one_to_one")
    df["t"] = pd.to_datetime(df.posted_at, utc=True).dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None)
    df = df.sort_values(["t", "transaction_id"], kind="stable").reset_index(drop=True)
    df["week"] = (df.t - pd.Timestamp("2024-01-01")).dt.days // 7
    return df, report, hashes
