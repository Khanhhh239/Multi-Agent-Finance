"""Inspect observed payment timing, T1 survival and 13-week/tail hazards.

Uses one earliest validation/test snapshot per invoice with 365 days of complete
follow-up. This analysis is outside the locked training source hash.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent1.data.world_manifest import code_provenance, load_cohort, sha256_file  # noqa: E402
from agent1.models import t1  # noqa: E402
from agent1.paths import OUT, SYNTH  # noqa: E402
from scripts.train_manifest import _rows  # noqa: E402

COHORT = SYNTH / "v4_shortpay_4shock_20261028_cohort.json"
MODEL_DIR = OUT / "data/v4_shortpay_4shock_20261028"
OUTPUT = MODEL_DIR / "survival_diagnostic_20261028"
HORIZONS = (28, 91, 120, 180, 270, 365)
BUCKETS = (("1-28", 0, 28), ("29-91", 28, 91), ("92-120", 91, 120),
           ("121-180", 120, 180), ("181-270", 180, 270),
           ("271-365", 270, 365))


def predicted_cdf(hazards: np.ndarray, days: int) -> np.ndarray:
    """Exact T1 week-end CDF or its published geometric tail beyond day 91."""
    if days < 1 or (days <= 91 and days % 7):
        raise ValueError("Use week ends through day 91, or a later day")
    _, survival = t1.pmf_from_hazard(hazards)
    if days <= 91:
        return 1 - survival[:, days // 7 - 1]
    tail = np.clip(hazards[:, -4:].mean(axis=1), .02, .6)
    return 1 - survival[:, -1] * np.power(1 - tail, (days - 91) / 7)


def summarize_timing(remaining: np.ndarray, writeoff_days: np.ndarray) -> dict:
    """All members have 365-day follow-up; no right-censored row is paid by fiat."""
    rem = np.asarray(remaining, dtype=float)
    wo = np.asarray(writeoff_days, dtype=float)
    if len(rem) == 0 or len(rem) != len(wo) or np.isnan(rem).any() or np.isnan(wo).any():
        raise ValueError("Invalid timing data")
    paid365 = rem <= 365
    written365 = wo <= 365
    if np.any(paid365 & written365):
        raise ValueError("Paid and written off within 365 days")
    buckets = {name: int(((rem > left) & (rem <= right)).sum())
               for name, left, right in BUCKETS}
    sorted_rem = np.sort(rem)

    def identifiable_quantile(level: float) -> float | None:
        value = sorted_rem[int(np.ceil(level * len(rem))) - 1]
        return float(value) if value <= 365 else None

    return {
        "n": int(len(rem)), "paid_by_120": int((rem <= 120).sum()),
        "paid_day_121_to_365": int(((rem > 120) & paid365).sum()),
        "not_paid_by_365": int((~paid365).sum()),
        "written_off_by_365": int(written365.sum()),
        "not_paid_or_written_off_by_365": int((~paid365 & ~written365).sum()),
        "paid_after_365_observed_by_world_end": int(((rem > 365) & np.isfinite(rem)).sum()),
        "payment_buckets": buckets,
        "median_days_among_paid_by_365": float(np.median(rem[paid365])) if paid365.any() else None,
        "observed_q50_all_if_by_365": identifiable_quantile(.5),
        "observed_q90_all_if_by_365": identifiable_quantile(.9),
    }


def week_hazards(hazards: np.ndarray, remaining: np.ndarray,
                 writeoff_days: np.ndarray, max_week=52) -> list[dict]:
    rem = np.asarray(remaining, dtype=float)
    wo = np.asarray(writeoff_days, dtype=float)
    tail = np.clip(hazards[:, -4:].mean(axis=1), .02, .6)
    rows = []
    for week in range(1, max_week + 1):
        left, right = 7 * (week - 1), 7 * week
        risk = rem > left
        active = risk & (wo > left)
        n = int(risk.sum())
        events = int(((rem > left) & (rem <= right)).sum())
        predicted = hazards[risk, week - 1] if week <= 13 else tail[risk]
        predicted_active = hazards[active, week - 1] if week <= 13 else tail[active]
        rows.append({"week": week, "start_day_exclusive": left, "end_day_inclusive": right,
                     "phase": "direct" if week <= 13 else "geometric_tail",
                     "at_risk": n, "paid_in_week": events,
                     "observed_hazard": events / n if n else None,
                     "predicted_hazard_on_observed_risk_set": float(predicted.mean()) if n else None,
                     "already_written_off_at_week_start": int((risk & (wo <= left)).sum()),
                     "active_at_risk_excluding_writeoff": int(active.sum()),
                     "observed_hazard_active": events / active.sum() if active.any() else None,
                     "predicted_hazard_active": float(predicted_active.mean())
                     if active.any() else None})
    return rows


def load_anchor_frame(entry: dict, cohort: dict) -> pd.DataFrame:
    world = entry["name"]
    frame = _rows(SYNTH / world, cohort["split_protocol"]["origin"],
                  role=entry["role"], protocol=cohort["split_protocol"])
    frame = frame.loc[frame.obs_window >= 365].sort_values(["cutoff", "invoice_id"])
    frame = frame.drop_duplicates("invoice_id", keep="first").reset_index(drop=True)
    if frame.empty or frame.invoice_id.duplicated().any() or (frame.obs_window < 365).any():
        raise ValueError(f"{world}: invalid 365-day anchor cohort")
    return frame


def analyze(cohort_path: Path, model_dir: Path, output_dir: Path) -> dict:
    cohort_path, model_dir, output_dir = map(Path, (cohort_path, model_dir, output_dir))
    cohort = load_cohort(cohort_path)
    metadata = json.loads((model_dir / "train.json").read_text(encoding="utf-8"))
    model_path = model_dir / "model.txt"
    if metadata["cohort_sha256"] != sha256_file(cohort_path) or \
            metadata["model_sha256"] != sha256_file(model_path):
        raise ValueError("Cohort/model hash differs from locked training")
    current = code_provenance()
    if current["commit"] != metadata["commit"] or \
            current["source_code_sha256"] != metadata["source_code_sha256"]:
        raise ValueError("Training code changed; restore saved source snapshot")
    model = t1.HazardGBM(feats=metadata["features"])
    model.booster = lgb.Booster(model_file=str(model_path))
    if model.booster.feature_name() != model.feats + t1.WEEK_FEATS:
        raise ValueError("Model feature order differs")
    curve_rows, weekly_curve_rows, hazard_rows, distributions = [], [], [], []
    for entry in cohort["worlds"]:
        if entry["role"] == "train":
            continue
        world, role = entry["name"], entry["role"]
        frame = load_anchor_frame(entry, cohort)
        rem = frame.remaining.to_numpy(dtype=float)
        writeoff_days = (pd.to_datetime(frame.writeoff_date) - frame.cutoff).dt.days
        wo = writeoff_days.fillna(np.inf).to_numpy(dtype=float)
        H = model.hazards(frame)
        timing = summarize_timing(rem, wo)
        distributions.append({"world": world, "role": role,
                              "first_cutoff": str(frame.cutoff.min().date()),
                              "last_cutoff": str(frame.cutoff.max().date()),
                              "min_followup_days": float(frame.obs_window.min()), **timing})
        for day in HORIZONS:
            forecast = predicted_cdf(H, day)
            actual = rem <= day
            curve_rows.append({"world": world, "role": role, "day": day,
                               "n": len(frame), "paid_by_day": int(actual.sum()),
                               "observed_cdf": float(actual.mean()),
                               "predicted_cdf": float(forecast.mean()),
                               "cdf_gap_pred_minus_observed": float(forecast.mean() - actual.mean()),
                               "prediction_phase": "direct" if day <= 91 else "geometric_tail"})
        for week in range(53):
            day = week * 7
            forecast = np.zeros(len(frame)) if week == 0 else predicted_cdf(H, day)
            actual = rem <= day
            weekly_curve_rows.append({"world": world, "role": role, "week": week,
                                      "day": day, "n": len(frame),
                                      "observed_survival": float(1 - actual.mean()),
                                      "predicted_survival": float(1 - forecast.mean())})
        for row in week_hazards(H, rem, wo):
            hazard_rows.append({"world": world, "role": role, **row})
        print(f"{world}: {len(frame):,} unique invoices", flush=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(curve_rows).to_csv(output_dir / "survival_curves.csv", index=False)
    weekly_curves = pd.DataFrame(weekly_curve_rows)
    weekly_curves.to_csv(output_dir / "weekly_survival_curves.csv", index=False)
    pd.DataFrame(hazard_rows).to_csv(output_dir / "weekly_hazards.csv", index=False)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(11, 7), sharex=True, sharey=True)
    for ax, entry in zip(axes.flat, (e for e in cohort["worlds"] if e["role"] != "train")):
        world = entry["name"]
        data = weekly_curves[weekly_curves.world == world]
        ax.plot(data.day, data.observed_survival, label="Observed full-payment survival", lw=2)
        ax.plot(data.day, data.predicted_survival, label="T1 prediction", lw=2, ls="--")
        ax.axvline(91, color="gray", lw=1, ls=":")
        ax.set_title(f"{entry['role']} {world.rsplit('_', 1)[-1]} (n={int(data.n.iloc[0]):,})")
        ax.grid(alpha=.25)
        ax.set_xlim(0, 365)
        ax.set_ylim(0, 1)
    for ax in axes[-1]:
        ax.set_xlabel("Days after snapshot")
    for ax in axes[:, 0]:
        ax.set_ylabel("Not fully paid by day")
    fig.legend(*axes.flat[0].get_legend_handles_labels(), loc="lower center", ncol=2)
    fig.suptitle("T1 v4: observed vs predicted survival; dotted line = day 91 tail start")
    fig.tight_layout(rect=(0, .05, 1, .96))
    fig.savefig(output_dir / "survival_curves.png", dpi=160)
    plt.close(fig)
    report = {
        "cohort_sha256": metadata["cohort_sha256"],
        "model_sha256": metadata["model_sha256"],
        "training_source_code_sha256": metadata["source_code_sha256"],
        "analysis_code_sha256": sha256_file(Path(__file__)),
        "protocol": "Earliest eligible 28-day-stride snapshot per invoice in locked validation/test Worlds; at least 365 days of complete follow-up; full payment is the event; write-off is a competing nonpayment state; no model fitting",
        "horizons_days": list(HORIZONS),
        "distributions": distributions,
        "limitations": ["Synthetic outcomes only", "Anchor cohorts stop by late 2024 and do not represent the 2025-12-31 batch",
                        "Payment after day 365 is unresolved for 365-day comparisons",
                        "The tail is a model assumption, not trained weekly hazard after week 13"],
    }
    (output_dir / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, default=COHORT)
    parser.add_argument("--model-dir", type=Path, default=MODEL_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = analyze(args.cohort, args.model_dir, args.output_dir)
    print(json.dumps({"worlds": len(report["distributions"]),
                      "output": str(args.output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
