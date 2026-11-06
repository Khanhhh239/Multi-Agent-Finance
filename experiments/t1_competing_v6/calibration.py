"""Regularized multiclass hazard calibration on held-out source firms only."""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize
from scipy.special import softmax

from .core import OPEN, PAID, observed_state, state_at_day, validate_hazards


def identity(active_causes, bands):
    return {"active_causes": list(active_causes), "bands": list(bands), "parameters": [[0.0] * len(active_causes) for _ in bands], "selected": "identity"}


def transform(hazards, calibration):
    h = validate_hazards(hazards)
    out = np.zeros_like(h)
    active = calibration["active_causes"]
    start = 0
    for end, parameters in zip(calibration["bands"], calibration["parameters"]):
        p = h[:, start:end, :][:, :, active]
        logits = np.log(np.clip(p, 1e-12, 1)) / np.exp(parameters[0])
        bias = np.r_[parameters[1:], 0.0]
        q = softmax(logits + bias, axis=2)
        for column, cause in enumerate(active):
            out[:, start:end, cause] = q[:, :, column]
        start = end
    validate_hazards(out)
    return out


def fit(frame, hazards, active_causes, protocol):
    if "partition" not in frame or not frame.partition.eq("calibration_fit").all():
        raise ValueError("Calibration fitting requires dedicated source calibration-fit firms")
    result = identity(active_causes, protocol["calibration_bands"])
    result["selected"] = "candidate"
    times, obs, causes = (frame[c].to_numpy(int) for c in ("time_days", "obs_days", "cause"))
    mapping = {cause: i for i, cause in enumerate(active_causes)}
    penalty = protocol["calibration_penalty"]
    start = 0
    diagnostics = []
    for band, end in enumerate(result["bands"]):
        matrices, labels = [], []
        for week in range(start + 1, end + 1):
            keep = (times > 7 * (week - 1)) & (obs >= 7 * week)
            y = np.where(times[keep] <= week * 7, causes[keep], OPEN)
            if set(y) - set(active_causes):
                raise ValueError("Calibration contains a cause absent from training")
            matrices.append(np.log(np.clip(hazards[keep, week - 1, :][:, active_causes], 1e-12, 1)))
            labels.append(np.array([mapping[c] for c in y], dtype=int))
        logits = np.vstack(matrices)
        y = np.concatenate(labels)
        if not len(y):
            start = end
            continue
        def objective(parameters):
            temperature = np.exp(parameters[0])
            scaled = logits / temperature
            probability = softmax(scaled + np.r_[parameters[1:], 0.0], axis=1)
            loss = -np.log(np.clip(probability[np.arange(len(y)), y], 1e-12, 1)).mean() + penalty * np.mean(parameters ** 2)
            residual = probability.copy()
            residual[np.arange(len(y)), y] -= 1
            gradient = np.r_[-np.mean(np.sum(residual * scaled, axis=1)), residual[:, :-1].mean(axis=0)]
            gradient += 2 * penalty * parameters / len(parameters)
            return loss, gradient
        optimum = minimize(objective, np.zeros(len(active_causes)), jac=True, method="L-BFGS-B", bounds=[(-1, 1)] + [(-2, 2)] * (len(active_causes) - 1), options={"maxiter": protocol["calibration_max_iterations"]})
        result["parameters"][band] = optimum.x.tolist()
        diagnostics.append({"end_week": end, "risk_rows": len(y), "converged": bool(optimum.success), "objective": float(optimum.fun), "initial_objective": float(objective(np.zeros(len(active_causes)))[0])})
        start = end
    result["fit_diagnostics"] = diagnostics
    return result


def select_on_source_firms(frame, raw_hazards, candidate, protocol):
    """Use disjoint calibration-selection firms, never a holdout World."""
    if "partition" not in frame or not frame.partition.eq("calibration_select").all():
        raise ValueError("Calibration selection requires dedicated source selection firms")
    calibrated = transform(raw_hazards, candidate)
    baseline = identity(candidate["active_causes"], candidate["bands"])
    scores, guards = [], []
    for world in sorted(frame.world.unique()):
        keep = frame.world.eq(world).to_numpy()
        part = frame.loc[keep]
        for day in (28, 91, 180, 365):
            truth = np.eye(4)[observed_state(part, day)]
            p0 = state_at_day(raw_hazards[keep], day)
            p1 = state_at_day(calibrated[keep], day)
            b0, b1 = np.mean(np.sum((p0-truth)**2, axis=1)), np.mean(np.sum((p1-truth)**2, axis=1))
            scores.append({"world": world, "day": day, "raw_brier": float(b0), "calibrated_brier": float(b1)})
            if day in (28, 91):
                old = np.mean((p0[:, PAID]-truth[:, PAID])**2)
                new = np.mean((p1[:, PAID]-truth[:, PAID])**2)
                guards.append(bool(new <= old * (1 + protocol["calibration_short_paid_brier_tolerance"])))
    improved = np.mean([s["calibrated_brier"]-s["raw_brier"] for s in scores]) < -1e-6
    selected = candidate if improved and all(guards) else baseline
    selected = dict(selected)
    selected["selection_audit"] = {"role": "source_train_calibration_selection_firms", "improved_joint_brier": bool(improved), "all_short_paid_guards_passed": all(guards), "scores": scores}
    return selected
