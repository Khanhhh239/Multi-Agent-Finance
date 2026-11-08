"""Paired company-level scores; weekly marginals and whole-path events differ."""
from __future__ import annotations

import numpy as np
import pandas as pd


def crps(samples, truth):
    x = np.sort(np.asarray(samples, float), axis=0)
    n = len(x)
    weights = (2*np.arange(1, n+1)-n-1)[:, None]
    return np.abs(x-np.asarray(truth)).mean(0) - (weights*x).sum(0)/(n*n)


def score_paths(samples, truth, scale):
    samples, truth = np.asarray(samples), np.asarray(truth)
    if samples.ndim != 2 or samples.shape[1] != 13 or truth.shape != (13,) or scale <= 0:
        raise ValueError("Invalid T6 score inputs")
    lo, mid, hi = np.quantile(samples, [.1, .5, .9], axis=0)
    interval = hi-lo+10*np.maximum(lo-truth, 0)+10*np.maximum(truth-hi, 0)
    result = {"crps_normalized": float(crps(samples, truth).mean()/scale),
              "coverage_80": float(((lo <= truth) & (truth <= hi)).mean()),
              "width_normalized": float((hi-lo).mean()/scale),
              "interval_score_normalized": float(interval.mean()/scale),
              "p50_mae_normalized": float(np.abs(mid-truth).mean()/scale)}
    for k in (4, 13):
        event = bool((truth[:k] < 0).any())
        probability = float((samples[:, :k] < 0).any(1).mean())
        result.update({f"shortfall_y{k}": int(event), f"shortfall_p{k}": probability,
                       f"brier_{k}": float((probability-event)**2)})
    return result


def paired_summary(frame, protocol):
    metrics = ["crps_normalized", "brier_4", "brier_13", "coverage_80", "width_normalized", "interval_score_normalized"]
    rows, cis = [], []
    rng = np.random.default_rng(protocol["seed"])
    for world, part in frame.groupby("world", sort=True):
        for name, group in part.groupby("model", sort=True):
            rows.append({"world": world, "model": name, "firms": group.firm_id.nunique(),
                         "origins": group.cutoff.nunique(), **{m: float(group[m].mean()) for m in metrics}})
        for metric in metrics:
            pivot = part.pivot(index=["firm_id", "cutoff"], columns="model", values=metric)
            delta = (pivot.unified-pivot.v6).groupby(level="firm_id").mean().to_numpy()
            bootstrap = delta[rng.integers(0, len(delta), (protocol["bootstrap_replicates"], len(delta)))].mean(1)
            cis.append({"world": world, "metric": metric, "unified_minus_v6": float(delta.mean()),
                        "ci_low": float(np.quantile(bootstrap, .025)), "ci_high": float(np.quantile(bootstrap, .975)),
                        "clusters": len(delta), "scope": "company variation within this World, not economic-world uncertainty"})
    return pd.DataFrame(rows), pd.DataFrame(cis)


def research_decision(summary, protocol, latency_ok, accounting_ok):
    a = protocol["acceptance"]
    checks = []
    for world, part in summary.groupby("world"):
        old = part[part.model.eq("v6")].iloc[0]
        new = part[part.model.eq("unified")].iloc[0]
        checks.append({"world": world, "criterion": "crps_5pct", "passed": bool(new.crps_normalized <= old.crps_normalized*(1-a["minimum_relative_crps_improvement"]))})
        for k in (4, 13):
            b = old[f"brier_{k}"]
            limit = b*(1+a["max_relative_brier_worsening"]) if b >= a["near_zero_brier"] else b+a["absolute_brier_tolerance"]
            checks.append({"world": world, "criterion": f"brier_{k}", "passed": bool(new[f"brier_{k}"] <= limit)})
        checks += [{"world": world, "criterion": "coverage", "passed": bool(a["coverage_min"] <= new.coverage_80 <= a["coverage_max"])},
                   {"world": world, "criterion": "interval_score", "passed": bool(new.interval_score_normalized <= old.interval_score_normalized*(1+a["max_relative_interval_score_worsening"]))}]
    passed = bool(checks) and all(c["passed"] for c in checks) and latency_ok and accounting_ok
    return {"research_passed": passed, "decision": "eligible_for_further_research" if passed else "insufficient_evidence_to_replace_v6",
            "latency_passed": bool(latency_ok), "accounting_passed": bool(accounting_ok), "checks": checks,
            "service_changed": False, "product_gates_changed": False}
