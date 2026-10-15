"""End-to-end Agent 2 pipeline.

    ingest (friend-format tables) -> causal features -> evidence rules (31 + relationship graph)
      -> entity-baseline deviations (price, payroll, creator, near-duplicates, self-approved cash)
      -> [pretrained voice: CES stack or L3 ranker]  -> alert selection with exploit/explore slots
      -> entity cases with Vietnamese reasons, priority and action  -> cases.csv, case_queue.csv, report.json

Profiles
  cold       nothing pretrained: only the label-free 'novelty' voice (rules + entity deviations, max of ranks)
  precision  default for SMEs: CES (13 pretrained weights + bias, inspectable) fills 2/3 of the slots, novelty the rest
  wide       L3 (LightGBM, pretrained) fills 2/3 of the slots: more recall, more false alerts on look-alike events

Budget B = alerts per company per week (default 3). exploit = ceil(2B/3), explore = B - exploit.

Run:  python -m agent2.pipeline --data work/data/w3_s205 --out work/runs/s205 --profile precision --pretrained models/pretrained_v1.joblib
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from . import methods as M
from .alerting import Confidence, build_cases, reasons_for_row, select_alerts, select_mixed
from .data import load
from .metrics import evaluate_scores, operating_point, weekly_alerts, tie_break

PROFILES = ("cold", "precision", "wide")


def slots(budget: int) -> tuple[int, int]:
    exploit = math.ceil(2 * budget / 3)
    return exploit, budget - exploit


class Agent2Detector:
    def __init__(self, profile="precision", pretrained: dict | None = None):
        if profile != "cold" and not pretrained:
            raise ValueError(f"profile '{profile}' needs --pretrained (train one with agent2.train_pretrained)")
        self.profile, self.pretrained = profile, pretrained
        self.entity = M.EntityDeviation()

    def fit(self, train: pd.DataFrame, valid: pd.DataFrame):
        self.entity.fit(train, valid)
        self.rules_ref = valid["rule_graph"].to_numpy(dtype=float)
        self.entity_ref = self.entity.score(valid)
        return self

    def score(self, df: pd.DataFrame) -> dict[str, np.ndarray]:
        rr = M.empirical_rank(self.rules_ref, df["rule_graph"].to_numpy(dtype=float))
        ee = M.empirical_rank(self.entity_ref, self.entity.score(df))
        out = {"rules": rr, "entity": ee, "novelty": np.maximum(rr, ee) + 1e-3 * (rr + ee) / 2}
        if self.profile == "precision":
            out["exploit"] = self.pretrained["ces"].score(df, self.entity)
        elif self.profile == "wide":
            out["exploit"] = self.pretrained["l3"].score(df)
        return out

    def alerts(self, df: pd.DataFrame, s: dict, budget: int) -> tuple[np.ndarray, np.ndarray]:
        if "exploit" not in s:
            final = s["novelty"]
            return weekly_alerts(df, final + tie_break(len(df), 5), budget), final
        a, b = slots(budget)
        flags = select_mixed(df, s["exploit"], s["novelty"], a, b)
        e = s["exploit"]
        final = 1 / (1 + np.exp(-e)) if self.profile == "precision" else e      # stack logit -> probability-like; L3 is already a probability
        return flags, final


def rule_weight_map(detector: Agent2Detector) -> dict[str, float] | None:
    ces = (detector.pretrained or {}).get("ces")
    if ces is None:
        return None
    model = ces.rule_model
    return {c.replace("hit_", ""): float(w) for c, w in zip(model.cols, model.model.coef_[0])}


def vietnamese_reasons(df: pd.DataFrame, detector: Agent2Detector, alerts: np.ndarray) -> pd.Series:
    weights = rule_weight_map(detector)
    idx = np.where(alerts)[0]
    sub = df.iloc[idx]
    ent_parts = detector.entity.parts(sub)
    texts = []
    for k, (_, row) in enumerate(sub.iterrows()):
        found = reasons_for_row(row, {n: float(v[k]) for n, v in ent_parts.items()}, weights)
        texts.append(" | ".join(dict.fromkeys(found)) or "Điểm bất thường tổng hợp cao so với lịch sử của chính doanh nghiệp")
    out = pd.Series("", index=df.index)
    out.iloc[idx] = texts
    return out


def to_case_queue(cases: pd.DataFrame) -> pd.DataFrame:
    """Columns of the friend's case_queue.csv so their review tooling can ingest the file."""
    sla = {"cao_nhat": 24, "cao": 48, "trung_binh": 168}
    fmt = lambda s: s.dt.strftime("%Y-%m-%dT%H:%M:%S+07:00")
    return pd.DataFrame({
        "case_id": cases["case_id"], "company_id": cases["company_id"], "entity": "entity:" + cases["entity"].str.split(":").str[-1],
        "opened_at": fmt(cases["opened_at"]), "last_seen_at": fmt(cases["opened_at"]), "priority": cases["priority"],
        "max_score": cases["case_score"].round(4), "owner_id": "", "status": "new", "conclusion": "", "reviewer_note": "",
        "transaction_ids": cases["transaction_ids"].map(json.dumps), "rule_ids": "", "explanation_vi": cases["reason"],
        "sla_due_at": fmt(cases["opened_at"] + pd.to_timedelta(cases["priority"].map(sla), unit="h")),
        "sla_basis": "mo_phong_theo_muc_uu_tien", "observation_count": cases["rows"]})


def run(data: Path, out: Path, profile="precision", budget=3, pretrained_path: Path | None = None, fdr: float | None = None):
    out.mkdir(parents=True, exist_ok=True)
    pretrained = joblib.load(pretrained_path) if pretrained_path else None
    df = load(data, need_text=True)
    train, valid = df[df.split == "train"], df[df.split == "validation"]
    det = Agent2Detector(profile, pretrained).fit(train, valid)
    deploy = df[df.split != "train"].reset_index(drop=True)
    s = det.score(deploy)
    flags, score = det.alerts(deploy, s, budget)
    if fdr:
        from .alerting import benjamini_hochberg, conformal_pvalues
        cal = det.alerts(valid.reset_index(drop=True), det.score(valid), budget)[1]
        flags &= benjamini_hochberg(conformal_pvalues(cal, score), fdr)
    deploy["explanation_vi"] = vietnamese_reasons(deploy, det, flags)
    conf = None
    if deploy["is_fraud"].sum():
        vs = det.score(valid)
        vscore = det.alerts(valid.reset_index(drop=True), vs, budget)[1]
        conf = Confidence().fit(vscore, valid["is_fraud"].to_numpy())
    cases = build_cases(deploy, flags, score, {k: v for k, v in s.items() if k in ("rules", "entity")}, conf)
    cases.assign(transaction_ids=cases["transaction_ids"].map(json.dumps)).to_csv(out / "cases.csv", index=False, encoding="utf-8-sig")
    to_case_queue(cases).to_csv(out / "case_queue.csv", index=False, encoding="utf-8-sig")
    report = dict(data=str(data), profile=profile, budget_per_company_week=budget, slots_exploit_explore=slots(budget) if profile != "cold" else (0, budget),
                  fdr=fdr, rows_deployment=len(deploy), alert_rows=int(flags.sum()), cases=len(cases), alerts_per_1000=1000 * float(flags.sum()) / len(deploy),
                  ces_weights=pretrained["ces"].weights() if pretrained and profile == "precision" else None)
    test = deploy[deploy.split == "test"]
    if test["is_fraud"].sum():
        m = (deploy.split == "test").to_numpy()
        op = operating_point(test.reset_index(drop=True), flags[m])
        report["test_operating_point"] = {k: op[k] for k in ("alerts", "tp", "precision", "recall", "case_recall", "hard_neg_alert_rate",
                                                              "entity_alerts", "entity_precision", "median_delay_days")}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    joblib.dump(dict(entity=det.entity, rules_ref=det.rules_ref, entity_ref=det.entity_ref, profile=profile), out / "detector.joblib")
    return report, cases


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--profile", choices=PROFILES, default="precision")
    p.add_argument("--budget", type=int, default=3)
    p.add_argument("--pretrained", type=Path)
    p.add_argument("--fdr", type=float)
    a = p.parse_args()
    report, cases = run(a.data, a.out, a.profile, a.budget, a.pretrained, a.fdr)
    print(json.dumps(report, ensure_ascii=False, indent=1, default=float))
    print(cases[["case_id", "company_id", "entity", "priority", "case_score", "reason"]].head(6).to_string())


if __name__ == "__main__":
    main()
