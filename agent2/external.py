"""External validity checks on public accounting-fraud data (not Vietnamese, not SME-specific).

* DFKI synthetic general ledger (Gronewald et al., Data in Brief 2026, Zenodo 10.5281/zenodo.22014653, CC BY 4.0):
  102,429 postings, 850 injected anomalies (0.83 percent) inside journal-entry-test lists.
* Wuerzburg ERP Fraud Data (Tritscher et al. 2022; ERPsim on SAP): line-level labels, 12 fraud scenarios.

Purpose: see whether the generic methods (IF, ECOD, HBOS, autoencoder, supervised trees) behave on someone
else's data the way they do on our world, and measure how much a journal-entry-test list is worth on its own.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from . import methods as M
from .metrics import evaluate_scores

warnings.filterwarnings("ignore")


# ------------------------------------------------------------------ DFKI general ledger
def load_dfki(path="external/dfki_gl/journal_entries_4203.csv") -> pd.DataFrame:
    d = pd.read_csv(path, sep=";")
    d["entered"] = pd.to_datetime(d["entered_date"])
    d["doc"] = pd.to_datetime(d["document_date"])
    d["debit"] = np.where(d["cd_flag"] == "D", d["amount"], 0.0)
    d["credit"] = np.where(d["cd_flag"] == "C", d["amount"], 0.0)
    g = d.groupby("posting_id", sort=False)
    doc = g.agg(entered=("entered", "first"), doc=("doc", "first"), user=("user", "first"), lines=("amount", "size"),
                debit=("debit", "sum"), tax=("tax_rate", "max"), label=("label", "max"), marking=("marking", "max"),
                top_n=("top_n", "max"), weekend=("weekend", "max"), nwh=("nwh", "max"), promptly=("promptly", "max"),
                high_cash=("high_cash", "max"), maxline=("amount", "max"))
    sig = d.assign(s=d["cd_flag"] + d["gl_account"].astype(str)).groupby("posting_id", sort=False)["s"].apply(lambda s: "|".join(sorted(s)))
    doc["signature"] = sig
    accounts = sorted(d["gl_account"].unique())
    for side in ("D", "C"):
        flag = d[d["cd_flag"] == side].assign(v=1).pivot_table(index="posting_id", columns="gl_account", values="v", aggfunc="max", fill_value=0)
        flag = flag.reindex(columns=accounts, fill_value=0).add_prefix(f"{side.lower()}_")
        doc = doc.join(flag, how="left").fillna(0)
    for u in sorted(doc["user"].unique()):
        doc[f"user_{u}"] = (doc["user"] == u).astype(int)
    doc = doc.sort_values("entered", kind="stable").reset_index()
    doc["log_amount"] = np.log1p(doc["debit"])
    doc["log_max_line"] = np.log1p(doc["maxline"])
    doc["hour"] = doc["entered"].dt.hour + doc["entered"].dt.minute / 60
    doc["dow"] = doc["entered"].dt.dayofweek
    doc["entry_weekend"] = (doc["dow"] >= 5).astype(int)
    doc["delay_days"] = (doc["entered"].dt.normalize() - doc["doc"]).dt.days.clip(lower=0)
    # past-only behaviour baselines: signature rarity and user-specific amount deviation
    seen_sig, seen_user_sig, hist = {}, {}, {}
    sig_freq, user_sig_freq, amt_z = [], [], []
    n = 0
    for r in doc.itertuples(index=False):
        n += 1
        sig_freq.append(seen_sig.get(r.signature, 0) / max(1, n - 1))
        user_sig_freq.append(seen_user_sig.get((r.user, r.signature), 0) / max(1, hist.get(("n", r.user), 0)))
        key = (r.user, r.signature)
        m, s, k = hist.get(key, (0.0, 0.0, 0))
        amt_z.append((r.log_amount - m) / max(.25, s) if k >= 5 else 0.0)
        k += 1
        delta = r.log_amount - m
        m2 = m + delta / k
        hist[key] = (m2, (s * (k - 1) + abs(r.log_amount - m2)) / k, k)
        seen_sig[r.signature] = seen_sig.get(r.signature, 0) + 1
        seen_user_sig[key] = seen_user_sig.get(key, 0) + 1
        hist[("n", r.user)] = hist.get(("n", r.user), 0) + 1
    doc["sig_rarity"] = -np.log(np.array(sig_freq) + 1e-4)
    doc["user_sig_rarity"] = -np.log(np.array(user_sig_freq) + 1e-4)
    doc["amt_z_user_sig"] = np.abs(amt_z)
    doc["jet_count"] = (doc[["top_n", "high_cash", "nwh"]].sum(axis=1) + (doc["weekend"] > 0) + (doc["promptly"] > 1)).astype(float)
    doc["is_fraud"] = doc["label"].astype(int)
    doc["company_id"] = "DFKI"
    doc["vendor_id"], doc["employee_id"], doc["creator_id"] = "", "", doc["user"]
    doc["t"] = doc["entered"]
    doc["week"] = (doc["t"] - pd.Timestamp("2023-01-01")).dt.days // 7
    doc["case_id"] = np.where(doc["is_fraud"] == 1, doc["posting_id"], "")
    doc["hard_negative_type"] = ""
    doc["fraud_type"] = np.where(doc["is_fraud"] == 1, "marking_" + doc["marking"].astype(str), "")
    doc["difficulty"] = ""
    doc["split"] = np.where(doc["t"] < "2024-01-01", "train", np.where(doc["t"] < "2024-07-01", "validation", "test"))
    return doc


DFKI_BASE = ["log_amount", "log_max_line", "lines", "tax", "hour", "dow", "entry_weekend", "delay_days", "sig_rarity",
             "user_sig_rarity", "amt_z_user_sig"]
DFKI_JET = ["top_n", "weekend", "nwh", "promptly", "high_cash", "jet_count"]


def dfki_columns(doc, jet=False):
    cols = DFKI_BASE + [c for c in doc.columns if c[:2] in ("d_", "c_") and c[2:].isdigit()] + [c for c in doc.columns if c.startswith("user_") and c not in ("user_sig_rarity",)]
    return cols + (DFKI_JET if jet else [])


def run_dfki(out: Path | None = None):
    doc = load_dfki()
    tr, va, te = (doc[doc.split == s] for s in ("train", "validation", "test"))
    base, with_jet = (lambda d: dfki_columns(d)), (lambda d: dfki_columns(d, True))
    ms = [
        M.RuleScore("jet_count", "JET count (rule lists only)"),
        M.IForest(base, name="IF[ledger]"), M.ECOD(base, name="ECOD[ledger]"), M.HBOS(base, name="HBOS[ledger]"),
        M.Autoencoder(base, name="AE[ledger]"),
        M.IForest(with_jet, name="IF[ledger+JET flags]"),
        M.Supervised(base, "LGBM[ledger]"), M.Supervised(with_jet, "LGBM[ledger+JET flags]"),
    ]
    res = {}
    for m in ms:
        m.fit(tr, va)
        r = evaluate_scores(te, m.score(te), budgets=(1, 3))
        res[m.name] = dict(regime=m.regime, ap=r["ap"], r_precision=r["r_precision"], roc_auc=r["roc_auc"], positives=r["positives"],
                           B1_precision=r["B1"]["precision"], B1_recall=r["B1"]["recall"], B3_precision=r["B3"]["precision"],
                           B3_recall=r["B3"]["recall"], jet_flagged_share=float((te["jet_count"] > 0).mean()))
        print(f"  DFKI {m.name:30s} AP={r['ap']:.3f} Rprec={r['r_precision']:.3f} AUC={r['roc_auc']:.3f} B3 P={r['B3']['precision']:.2f} R={r['B3']['recall']:.2f}", flush=True)
    if out:
        Path(out).write_text(json.dumps(dict(rows=len(doc), test_rows=len(te), test_positives=int(te.is_fraud.sum()), results=res), indent=1), encoding="utf-8")
    return res


# ------------------------------------------------------------------ Wuerzburg ERP fraud data
def load_erp(root="external/erp_fraud/joint") -> pd.DataFrame:
    root = Path(root)
    info = pd.read_csv(root / "column_information.csv", header=None, skiprows=1, index_col=0)
    names = list(info.columns)
    parts = []
    for run in ("normal_1", "normal_2", "fraud_1", "fraud_2", "fraud_3"):
        d = pd.read_csv(root / f"{run}.csv", low_memory=False)
        d["run"] = run
        parts.append(d)
    d = pd.concat(parts, ignore_index=True)
    meta = ["Label", "Belegnummer", "Position", "Transaktionsart", "Erfassungsuhrzeit", "run"]
    feat = [c for c in d.columns if c not in meta]
    cat = [c for c in feat if d[c].dtype == object or d[c].map(type).eq(str).any()]
    num = [c for c in feat if c not in cat]
    out = pd.DataFrame(index=d.index)
    for c in num:
        out[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)
    for c in cat:
        codes, _ = pd.factorize(d[c].astype(str))
        out[c] = codes
    out = out.loc[:, out.std() > 0]
    out["is_fraud"] = (d["Label"].astype(str) != "NonFraud").astype(int)
    out["scenario"] = np.where(out["is_fraud"] == 1, d["Label"].astype(str), "")
    out["run"] = d["run"].values
    out["doc"] = d["Belegnummer"].astype(str).values
    out["ttype"] = d["Transaktionsart"].astype(str).values
    return out


def run_erp(out: Path | None = None):
    d = load_erp()
    feats = [c for c in d.columns if c not in ("is_fraud", "scenario", "run", "doc", "ttype")]
    d["company_id"], d["week"], d["case_id"], d["hard_negative_type"], d["fraud_type"] = "ERP", 0, d["doc"].where(d.is_fraud == 1, ""), "", d["scenario"]
    d["t"] = pd.Timestamp("2024-01-01")
    d["vendor_id"], d["employee_id"], d["creator_id"] = "", "", d["run"]
    res = {}
    clean = d[d.run.isin(["normal_1", "normal_2"])]
    cols = lambda _d: feats
    for target in ("fraud_1", "fraud_2", "fraud_3"):
        te = d[d.run == target]
        row = {}
        unsup = [M.IForest(cols, name="IF"), M.ECOD(cols, name="ECOD"), M.HBOS(cols, name="HBOS"), M.Autoencoder(cols, name="AE")]
        for m in unsup:
            m.fit(clean, None)
            r = evaluate_scores(te, m.score(te), budgets=())
            row[m.name] = dict(ap=r["ap"], r_precision=r["r_precision"], roc_auc=r["roc_auc"], regime="U (fit on clean runs)")
        # supervised: train on the other two fraud runs plus normal runs (same scenarios may repeat, so also leave-scenario-out)
        others = d[(d.run.isin(["fraud_1", "fraud_2", "fraud_3"])) & (d.run != target)]
        tr = pd.concat([others, clean])
        m = M.Supervised(cols, "LGBM", grid=((7, .05),)).fit(tr, None)
        r = evaluate_scores(te, m.score(te), budgets=())
        row["LGBM (other runs)"] = dict(ap=r["ap"], r_precision=r["r_precision"], roc_auc=r["roc_auc"], regime="S (other fraud runs)")
        scenarios = sorted(s for s in te.scenario.unique() if s)
        loso = {}
        for s in scenarios:
            tr2 = pd.concat([others[others.scenario != s], clean])
            te2 = te[(te.scenario == s) | (te.is_fraud == 0)]
            if te2.is_fraud.sum() < 3:
                continue
            m2 = M.Supervised(cols, "LGBM", grid=((7, .05),)).fit(tr2.assign(), None)
            rr = evaluate_scores(te2, m2.score(te2), budgets=())
            loso[s] = dict(positives=int(te2.is_fraud.sum()), ap=rr["ap"], r_precision=rr["r_precision"])
        row["LGBM leave-scenario-out"] = loso
        res[target] = dict(rows=len(te), fraud_lines=int(te.is_fraud.sum()), methods=row)
        print(f"  ERP {target}: fraud lines {int(te.is_fraud.sum())}/{len(te)}; " +
              ", ".join(f"{k}={v['ap']:.3f}" for k, v in row.items() if isinstance(v, dict) and "ap" in v), flush=True)
    if out:
        Path(out).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return res
