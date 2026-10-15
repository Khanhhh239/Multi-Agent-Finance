"""Load a friend-format dataset into one analysis frame, with cached engineered and rule features."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .feats import ENGINEERED, engineered_features

LABEL_COLUMNS = ["is_fraud", "fraud_type", "variant", "case_id", "case_role", "hard_negative_type", "difficulty"]


def rule_frame(dataset: Path, cache: Path | None = None) -> pd.DataFrame:
    """Run the friend's rule engine (graph on and off) and return per-transaction rule features."""
    cache = Path(cache) if cache else None
    if cache and cache.exists():
        return pd.read_pickle(cache)
    from sme_fraud.rules import load_inputs, score_rules
    tables, features, _ = load_inputs(Path(dataset))
    graph = score_rules(tables, config=None, features=features)
    direct = score_rules(tables, config={"enable_graph": False}, features=features)
    ids = [r["transaction_id"] for r in graph["scores"]]
    frame = pd.DataFrame({"transaction_id": ids,
                          "rule_graph": [float(r["rule_score"]) for r in graph["scores"]],
                          "rule_hard": [float(r["hard_trigger"]) for r in graph["scores"]],
                          "rule_ids": [r["rule_ids"] for r in graph["scores"]],
                          "explanation_vi": [r["explanation_vi"] for r in graph["scores"]]})
    d = pd.DataFrame({"transaction_id": [r["transaction_id"] for r in direct["scores"]],
                      "rule_direct": [float(r["rule_score"]) for r in direct["scores"]]})
    frame = frame.merge(d, on="transaction_id")
    from sme_fraud.rules import RULE_NAMES
    rule_ids = sorted(RULE_NAMES)
    mat = {f"hit_{rid}": np.zeros(len(frame)) for rid in rule_ids}
    index = {t: i for i, t in enumerate(frame["transaction_id"])}
    for h in graph["hits"]:
        if not h["suppressed_reason"]:
            mat[f"hit_{h['rule_id']}"][index[h["transaction_id"]]] = max(mat[f"hit_{h['rule_id']}"][index[h["transaction_id"]]], h["points"])
    frame = pd.concat([frame, pd.DataFrame(mat)], axis=1)
    if cache:
        frame.to_pickle(cache)
    return frame


def load(dataset: Path, use_rules=True, cache_dir: Path | None = None, need_text=False) -> pd.DataFrame:
    dataset = Path(dataset)
    cache_dir = Path(cache_dir) if cache_dir else dataset / "_cache"
    cache_dir.mkdir(exist_ok=True)
    feats = pd.read_csv(dataset / "features.csv")
    labels = pd.read_csv(dataset / "labels.csv", keep_default_na=False)[["transaction_id", *LABEL_COLUMNS]]
    splits = pd.read_csv(dataset / "splits.csv")
    header = pd.read_csv(dataset / "transactions.csv", nrows=0).columns
    optional = [c for c in ("customer_id", "collector_id") if c in header]
    tx = pd.read_csv(dataset / "transactions.csv", keep_default_na=False,
                     usecols=["transaction_id", "company_id", "posted_at", "txn_type", "vendor_id", "employee_id",
                              "creator_id", "approver_id", "amount_vnd", "invoice_number", "accounting_framework", *optional])
    eng_cache = cache_dir / "engineered.pkl"
    eng = pd.read_pickle(eng_cache) if eng_cache.exists() else engineered_features(dataset)
    if not eng_cache.exists():
        eng.to_pickle(eng_cache)
    df = tx.merge(splits, on="transaction_id").merge(labels, on="transaction_id").merge(feats, on="transaction_id").merge(eng, on="transaction_id")
    from .feats_v4 import is_v4, v4_features
    if is_v4(dataset):
        v4_cache = cache_dir / "v4feats.pkl"
        v4 = pd.read_pickle(v4_cache) if v4_cache.exists() else v4_features(dataset)
        if not v4_cache.exists():
            v4.to_pickle(v4_cache)
        df = df.merge(v4, on="transaction_id")
    if use_rules:
        new, old = cache_dir / "rules2.pkl", cache_dir / "rules.pkl"
        path = old if (old.exists() and not new.exists() and not need_text) else new
        df = df.merge(rule_frame(dataset, path), on="transaction_id", how="left")
    df["t"] = pd.to_datetime(df["posted_at"], utc=True).dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None)
    df = df.sort_values(["t", "transaction_id"], kind="stable").reset_index(drop=True)
    df["week"] = (df["t"] - pd.Timestamp("2024-01-01")).dt.days // 7
    return df


def friend_columns(df: pd.DataFrame) -> list[str]:
    from sme_fraud.features import FEATURE_DESCRIPTIONS
    return list(FEATURE_DESCRIPTIONS)


def rule_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.startswith("hit_")] + ["rule_graph", "rule_direct", "rule_hard"]


def engineered_columns(df=None) -> list[str]:
    from .feats_v4 import V4_FEATURES
    extra = [c for c in V4_FEATURES if df is not None and c in df.columns]
    return list(ENGINEERED) + extra

