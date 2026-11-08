"""Natural-frequency joint classifier and source-only probability calibration."""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize
from scipy.special import softmax


def validate_probabilities(p):
    p = np.asarray(p, float)
    if p.ndim != 2 or not np.isfinite(p).all() or (p < 0).any() or not np.allclose(p.sum(1), 1, atol=2e-6):
        raise ValueError("Invalid transition probabilities")
    return p


def transform(p, calibration=None):
    p = validate_probabilities(p)
    if calibration is None or calibration["selected"] == "identity":
        return p
    a = np.asarray(calibration["parameters"])
    return softmax(np.log(np.clip(p, 1e-12, 1))/np.exp(a[0]) + np.r_[a[1:], 0.], axis=1)


def log_loss(p, y):
    if (y < 0).any():
        return None
    return float(-np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1)).mean())


def fit_calibration(fit_p, fit_y, select_p, select_y, protocol):
    """An unseen source outcome is disclosed and prevents calibration selection."""
    result = {"selected": "identity", "parameters": [0.]*fit_p.shape[1],
              "fit_unknown_rows": int((fit_y < 0).sum()), "select_unknown_rows": int((select_y < 0).sum())}
    if (fit_y < 0).any() or (select_y < 0).any():
        result["reason"] = "source calibration contains outcomes unsupported by training vocabulary"
        return result
    logits = np.log(np.clip(validate_probabilities(fit_p), 1e-12, 1))
    def objective(a):
        scaled = logits/np.exp(a[0])
        p = softmax(scaled+np.r_[a[1:], 0.], axis=1)
        loss = log_loss(p, fit_y)+protocol["penalty"]*np.mean(a*a)
        residual = p.copy()
        residual[np.arange(len(p)), fit_y] -= 1
        gradient = np.r_[-np.mean(np.sum(residual*scaled, axis=1)), residual[:, :-1].mean(0)]
        gradient += 2*protocol["penalty"]*a/len(a)
        return loss, gradient
    optimum = minimize(objective, np.zeros(fit_p.shape[1]), jac=True, method="L-BFGS-B",
                       bounds=[(-1, 1)]+[(-2, 2)]*(fit_p.shape[1]-1),
                       options={"maxiter": protocol["max_iterations"]})
    candidate = {"selected": "calibrated", "parameters": optimum.x.tolist()}
    raw = log_loss(select_p, select_y)
    adjusted = log_loss(transform(select_p, candidate), select_y)
    if optimum.success and adjusted < raw:
        result.update(candidate)
    result.update(converged=bool(optimum.success), selection_raw_logloss=raw,
                  selection_candidate_logloss=adjusted, candidate_parameters=optimum.x.tolist())
    return result
