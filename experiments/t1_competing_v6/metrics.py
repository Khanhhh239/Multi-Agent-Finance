"""Invoice, amount-weighted and company-clustered diagnostics."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .core import PAID, WRITEOFF, observed_state


def reliability(probability, truth):
    probability = np.asarray(probability, float)
    truth = np.asarray(truth, float)
    if not len(probability) or not np.isfinite(probability).all():
        raise ValueError("Invalid reliability inputs")
    if np.ptp(probability) < 1e-12:
        bins = np.zeros(len(probability), dtype=int)
    else:
        bins = np.asarray(pd.qcut(probability, q=10, labels=False, duplicates="drop"))
    rows = []
    for group in np.unique(bins):
        keep = bins == group
        rows.append({"bin": int(group), "n": int(keep.sum()), "predicted": float(probability[keep].mean()), "observed": float(truth[keep].mean())})
    ece = sum(r["n"] * abs(r["predicted"]-r["observed"]) for r in rows) / len(probability)
    return float(ece), rows


def score(frame, probability, day):
    probability = np.asarray(probability, float)
    if probability.shape != (len(frame), 4) or not np.isfinite(probability).all() or (probability < -1e-8).any() or not np.allclose(probability.sum(axis=1), 1, atol=3e-6):
        raise ValueError("Incoherent evaluation probabilities")
    state = observed_state(frame, day)
    truth = np.eye(4)[state]
    squared = (probability - truth) ** 2
    weights = frame.amount_open.to_numpy(float).clip(0)
    weights = weights if weights.sum() else np.ones(len(frame))
    result = {"n": len(frame), "amount_open": float(weights.sum()),
              "four_state_brier": float(squared.sum(axis=1).mean()),
              "amount_weighted_brier": float(np.average(squared.sum(axis=1), weights=weights))}
    for label, cause in (("paid", PAID), ("writeoff", WRITEOFF), ("credit_note", 3)):
        result.update({f"actual_{label}": float(truth[:, cause].mean()),
                       f"pred_{label}": float(probability[:, cause].mean()),
                       f"{label}_gap": float((probability[:, cause]-truth[:, cause]).mean()),
                       f"{label}_brier": float(squared[:, cause].mean()),
                       f"{label}_ece": reliability(probability[:, cause], truth[:, cause])[0]})
    return result


def paired_company_bootstrap(frame, probability, baseline, day, replicates=400, seed=17):
    truth = np.eye(4)[observed_state(frame, day)]
    difference = np.sum((probability-truth)**2, axis=1) - np.sum((baseline-truth)**2, axis=1)
    values = pd.DataFrame({"firm": frame.firm_id.to_numpy(), "difference": difference})
    groups = values.groupby("firm").difference.agg(["sum", "count"])
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(groups), size=(replicates, len(groups)))
    boot = groups["sum"].to_numpy()[draws].sum(axis=1) / groups["count"].to_numpy()[draws].sum(axis=1)
    low, high = np.quantile(boot, [.025, .975])
    return {"firms": len(groups), "delta_brier_vs_v5": float(difference.mean()), "ci_low": float(low), "ci_high": float(high), "replicates": replicates, "resampling_unit": "firm within World; does not establish uncertainty across unseen Worlds"}


def subgroup_masks(frame, high_amount):
    age = frame.age_days.to_numpy()
    frac = frame.paid_frac_so_far.fillna(0).to_numpy()
    yield "all", np.ones(len(frame), dtype=bool)
    for low, high in ((0, 30), (31, 90), (91, 180), (181, 100000)):
        yield f"age_{low}_{high}", (age >= low) & (age <= high)
    yield "no_receipts", frac == 0
    yield "partial_receipts", (frac > 0) & (frac < 1)
    yield "high_amount_train_p90", frame.amount_open.to_numpy() >= high_amount
    yield "known_customer_writeoff", frame.c_writeoff_n_asof.to_numpy() > 0


def cash_score(frame, actual, predicted):
    if not np.isfinite(predicted).all() or np.any(predicted < 0):
        raise ValueError("Invalid cash forecast")
    error = np.asarray(predicted)-np.asarray(actual)
    by_firm = pd.DataFrame({"firm": frame.firm_id.to_numpy(), "actual": actual, "predicted": predicted}).groupby("firm").sum()
    denominator = float(np.sum(actual))
    return {"n": len(frame), "actual_cash": denominator, "predicted_cash": float(np.sum(predicted)),
            "invoice_mae_vnd": float(np.mean(np.abs(error))),
            "invoice_wape": float(np.sum(np.abs(error))/denominator) if denominator else None,
            "firm_aggregate_wape": float(np.sum(np.abs(by_firm.predicted-by_firm.actual))/denominator) if denominator else None,
            "aggregate_bias": float(np.sum(error)/denominator) if denominator else None}
