"""Weekly direct sales and variable expenses on reconciled statements only."""

import hashlib
import os
import pickle
from datetime import date, timedelta
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from .cash_history import weekly_cash
from .data import account_scope


def operating_identity(component):
    """Persisted fit identity survives estimator serialization and alias changes."""
    if not component:
        return None
    return dict(
        version=component.get("version"),
        name=component.get("name"),
        accounts=sorted(component.get("accounts", [])),
        fitted_through=component.get("fitted_through"),
        ready_on=component.get("ready_on"),
    )


def available_history(data, clock, accounts):
    """Keep the weekly grid fixed; bridge up to six unreconciled weeks at the origin."""
    end = date.fromisoformat(clock)
    panel = weekly_cash(
        data, str(end - timedelta(weeks=260) + timedelta(days=1)), 260, clock, accounts
    )[:, 2:]
    covered = np.flatnonzero(np.isfinite(panel).all(1))
    if not len(covered):
        return panel[:0], 0
    last = covered[-1] + 1
    gap = len(panel) - last
    if gap > 6:
        return panel[:0], gap
    holes = np.flatnonzero(~np.isfinite(panel[:last]).all(1))
    return panel[(holes[-1] + 1 if len(holes) else 0) : last], int(gap)


def _fit_local_seasonal(y: np.ndarray):
    """EWMA level + 4-week monthly phase ratios for short SME histories (8-52w)."""
    n, cols = y.shape
    alpha = 0.25
    levels = np.zeros(cols)
    phases = np.ones((4, cols))
    for j in range(cols):
        s = y[:, j].astype(float)
        lvl = float(s[0])
        for v in s[1:]:
            lvl = alpha * float(v) + (1.0 - alpha) * lvl
        levels[j] = max(lvl, 0.0)
        mean_all = float(s.mean())
        if mean_all > 1e-8 and n >= 8:
            for p in range(4):
                idx = np.arange(p, n, 4)
                raw_ratio = float(s[idx].mean()) / mean_all if len(idx) else 1.0
                # Empirical Bayes shrinkage toward 1.0 when sample count is small
                k = len(idx)
                phases[p, j] = (k * raw_ratio + 2.0) / (k + 2.0)
            phases[:, j] /= max(phases[:, j].mean(), 1e-8)
    return dict(levels=levels, phases=phases, last_phase=n % 4)


def _predict_local_seasonal(model, horizon: int, gap: int = 0) -> np.ndarray:
    levels = model["levels"]
    phases = model["phases"]
    start_phase = model["last_phase"]
    out = np.zeros((horizon, len(levels)))
    for h in range(horizon):
        p = (start_phase + h) % 4
        out[h] = np.maximum(0.0, levels * phases[p])
    return out[gap:]


def _fit_lognormal(y: np.ndarray):
    """Parametric log-normal model on log1p(y/scale) with Jensen + Duan smearing."""
    scale = np.maximum(y.mean(axis=0), 1.0)
    z = np.log1p(np.maximum(y, 0.0) / scale)
    n = len(z)
    weights = np.exp2(-np.arange(n - 1, -1, -1, dtype=float) / max(8.0, n / 2.0))
    weights /= weights.sum()
    mu = (z * weights[:, None]).sum(axis=0)
    var = (weights[:, None] * (z - mu[None, :]) ** 2).sum(axis=0)
    # Unbiased effective-sample Bessel correction
    ess = 1.0 / np.sum(weights**2)
    if ess > 1.5:
        var = var * (ess / (ess - 1.0))
    sigma2 = np.clip(var, 0.0, 4.0)
    # Hybrid Jensen exp(mu + 0.5*sigma^2) blended with Duan smearing for robustness
    jensen = np.expm1(np.clip(mu + 0.5 * sigma2, 0.0, 14.0)) * scale
    smearing = np.maximum(0.0, (np.exp(mu[None, :] + (z - mu[None, :])).mean(axis=0) - 1.0) * scale)
    point = np.maximum(0.0, 0.5 * jensen + 0.5 * smearing)
    return dict(scale=scale, mu=mu, sigma2=sigma2, point=point)


def _predict_lognormal(model, horizon: int, gap: int = 0) -> np.ndarray:
    return np.tile(model["point"], (horizon, 1))[gap:]


def fit_candidate(name, y):
    if name.startswith("pool:"):
        return [(n, fit_candidate(n, y)) for n in name[5:].split(",")]
    if name == "seasonal":
        return None
    if name == "local_seasonal":
        return _fit_local_seasonal(y)
    if name == "lognormal":
        return _fit_lognormal(y)
    if name == "chronos":
        from pathlib import Path

        path = os.environ.get("AGENT1_CHRONOS_DIR", "")
        if not path or not Path(path).is_dir():
            raise ValueError("Cần thư mục Chronos local đã kiểm tra")
        return path
    if name == "gbm":
        lag = min(8, max(2, len(y) // 3))
        if len(y) <= lag + 1:
            raise ValueError("Chuỗi quá ngắn cho GBM")
        min_leaf = min(8, max(2, (len(y) - lag) // 4))
        models = []
        for series in y.T:
            X = np.array([series[t - lag : t] for t in range(lag, len(series))])
            models.append(
                HistGradientBoostingRegressor(
                    max_iter=40,
                    max_leaf_nodes=7,
                    min_samples_leaf=min_leaf,
                    random_state=7,
                ).fit(X, series[lag:])
            )
        return models
    import torch

    torch.manual_seed(7)
    torch.set_num_threads(2)
    device = os.environ.get("AGENT1_DL_DEVICE", "cpu")
    scale = np.maximum(y.mean(axis=0), 1.0)
    values = torch.tensor(np.log1p(y / scale).T, dtype=torch.float32, device=device)
    width = 24 if name == "gaussian_gru_wide" else 12
    cell = torch.nn.LSTM if name == "gaussian_lstm" else torch.nn.GRU
    gru = cell(1, width, batch_first=True).to(device)
    head = torch.nn.Linear(width, 2).to(device)
    opt = torch.optim.Adam([*gru.parameters(), *head.parameters()], lr=0.012)
    for _ in range(60):
        hidden, _ = gru(values[:, :-1, None])
        mu, raw = head(hidden).unbind(-1)
        std = torch.nn.functional.softplus(raw) + 0.05
        loss = (std.log() + 0.5 * ((values[:, 1:] - mu) / std).square()).mean()
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(gru.parameters(), 2.0)
        opt.step()
    return (gru.cpu().eval(), head.cpu().eval(), scale)


def predict_candidate(name, model, y, gap=0):
    if name.startswith("pool:"):
        return np.mean([predict_candidate(n, m, y, gap) for n, m in model], axis=0)
    horizon = 13 + gap
    if name == "seasonal":
        base = y[-52:]
        if len(base) >= horizon:
            return base[gap:horizon].copy()
        idx = np.arange(gap, horizon) % len(base)
        return base[idx].copy()
    if name == "local_seasonal":
        return _predict_local_seasonal(model, horizon, gap)
    if name == "lognormal":
        return _predict_lognormal(model, horizon, gap)
    if name == "chronos":
        from agent1.models.t4_revenue import chronos_predict

        estimates = chronos_predict(list(y.T), horizon=horizon, model_id=model)
        if estimates is None:
            raise ValueError("Thiếu runtime Chronos")
        return np.stack([r[gap:, 1] for r in estimates], axis=1)
    if name == "gbm":
        points = []
        for estimator, series in zip(model, y.T):
            lag = int(getattr(estimator, "n_features_in_", 8))
            window = list(series[-lag:])
            for _ in range(horizon):
                window.append(max(0.0, float(estimator.predict([window[-lag:]])[0])))
            points.append(window[-13:])
        return np.asarray(points).T
    import torch

    gru, head, scale = model
    with torch.no_grad():
        series = torch.tensor(np.log1p(y / scale).T, dtype=torch.float32)
        hidden, state = gru(series[:, :, None])
        last = hidden[:, -1]
        out = []
        for _ in range(horizon):
            mu, raw = head(last).unbind(-1)
            loc = mu.clamp(0, 12)
            std = (torch.nn.functional.softplus(raw) + 0.05).clamp(max=2.5)
            # Exact log-normal Jensen correction: E[expm1(Z)] = expm1(mu + 0.5 * sigma^2)
            mean_log = (loc + 0.5 * std.square()).clamp(0, 14)
            out.append(np.maximum(0.0, np.expm1(mean_log.numpy()) * scale))
            hidden, state = gru(loc[:, None, None], state)
            last = hidden[:, 0]
    return np.asarray(out)[gap:]


def _expand_residual_trajectories(folds: np.ndarray, *, target_count: int = 64, seed: int = 17) -> np.ndarray:
    """Prevent 3-fold bootstrap collapse while preserving exact residual mean.

    Uses conformal finite-sample dispersion scaling sqrt((M + 1) / max(M - 1, 1))
    and stationary block/convex combinations when M < target_count so P10/P50/P90
    achieve calibrated ~80% coverage without altering expected cash.
    """
    folds = np.asarray(folds, float)
    m = len(folds)
    if m == 0 or not np.any(np.ptp(folds, axis=0) > 1e-9):
        return folds
    if m >= target_count:
        return folds
    mean = folds.mean(axis=0, keepdims=True)
    centered = folds - mean
    # Finite-sample Jackknife+/conformal inflation factor
    conformal_scale = float(np.sqrt((m + 1.0) / max(m - 1.0, 1.0)))
    conformal_scale = min(conformal_scale, 1.65)
    scaled = centered * conformal_scale
    rng = np.random.default_rng(seed)
    extra_n = target_count - m
    synth = np.empty((extra_n, folds.shape[1], folds.shape[2]), dtype=float)
    block_len = 4
    for k in range(extra_n):
        # Stationary block-bootstrap across folds + standardized Gaussian jitter
        traj = np.empty_like(folds[0])
        pos = 0
        while pos < folds.shape[1]:
            f_idx = int(rng.integers(0, m))
            end_pos = min(folds.shape[1], pos + block_len)
            traj[pos:end_pos] = scaled[f_idx, pos:end_pos]
            pos = end_pos
        # Add small variance-preserving orthogonal innovation from cross-fold std
        if m >= 2:
            fold_std = scaled.std(axis=0, ddof=1)
            z = rng.standard_normal(traj.shape)
            traj = np.sqrt(0.85) * traj + np.sqrt(0.15) * fold_std * z
        synth[k] = traj
    # Re-center synthetic trajectories to zero mean so overall mean == folds.mean(0) exactly
    synth -= synth.mean(axis=0, keepdims=True)
    combined = np.concatenate([mean + scaled, mean + synth], axis=0)
    # Exact mean conservation
    combined += mean - combined.mean(axis=0, keepdims=True)
    return combined


def _select_short_history_operating(data, y: np.ndarray, asof: str, ready_on: str, accounts: list[str], try_deep: bool, include_new_credit: bool):
    """Adaptive Jackknife+ / rolling-origin selection & calibration for 8-103 week SME series."""
    n = len(y)
    h_audit = min(13, max(2, n // 5))
    dev = y[:-h_audit]
    audit_target = y[-h_audit:]
    min_train = max(4, min(12, len(dev) // 2))
    if len(dev) <= min_train:
        return None

    names = ["local_seasonal", "lognormal"]
    if len(dev) >= 8:
        names.append("gbm")
    if try_deep and len(dev) >= 24 and (np.count_nonzero(dev, axis=0) >= 8).all():
        names.append("gaussian_gru")
    if try_deep and os.environ.get("AGENT1_CHRONOS_DIR"):
        names.append("chronos")

    losses = {}
    unavailable = {}
    residuals = {}
    origins = list(range(min_train, len(dev)))

    for name in names:
        one_step_errors = []
        multi_step_trajs = []
        try:
            for t in origins:
                past = dev[:t]
                model = fit_candidate(name, past)
                pred13 = predict_candidate(name, model, past, 0)
                avail_steps = min(13, len(dev) - t)
                err = dev[t : t + avail_steps] - pred13[:avail_steps]
                one_step_errors.append(err[0])
                if avail_steps == 13:
                    multi_step_trajs.append(err)
        except (ImportError, RuntimeError, ValueError) as exc:
            unavailable[name] = type(exc).__name__
            continue

        if not one_step_errors:
            continue
        one_step_arr = np.asarray(one_step_errors, float)  # (M, 2)
        losses[name] = float(np.abs(one_step_arr).mean())

        if len(multi_step_trajs) >= 4:
            base_folds = np.asarray(multi_step_trajs, float)
            residuals[name] = _expand_residual_trajectories(base_folds, target_count=64)
        else:
            # Jackknife+ stationary block bootstrap over OOS 1-step innovations
            m = len(one_step_arr)
            mean_e = one_step_arr.mean(axis=0, keepdims=True)
            centered = one_step_arr - mean_e
            conformal_factor = min(float(np.sqrt((m + 1.0) / max(m - 1.0, 1.0))), 1.75)
            scaled_e = centered * conformal_factor
            rng = np.random.default_rng(23)
            b_count = 64
            trajs = np.empty((b_count, 13, 2), dtype=float)
            block = min(4, max(1, m // 2))
            horizon_scale = np.sqrt(1.0 + 0.08 * np.minimum(np.arange(13), 6))[:, None]
            for b in range(b_count):
                seq = np.empty((13, 2), dtype=float)
                pos = 0
                while pos < 13:
                    start_i = int(rng.integers(0, m))
                    take_len = min(block, 13 - pos)
                    idx = (start_i + np.arange(take_len)) % m
                    seq[pos : pos + take_len] = scaled_e[idx]
                    pos += take_len
                trajs[b] = seq * horizon_scale
            trajs -= trajs.mean(axis=0, keepdims=True)
            residuals[name] = trajs + mean_e[:, None, :]

    if not losses:
        return None

    ranked = sorted(losses, key=losses.get)[:3]
    if len(ranked) > 1:
        shapes = {residuals[nm].shape for nm in ranked}
        if len(shapes) == 1:
            pooled = "pool:" + ",".join(ranked)
            residuals[pooled] = np.mean([residuals[nm] for nm in ranked], axis=0)
            losses[pooled] = float(np.abs(residuals[pooled][:, 0, :]).mean())

    name = min(losses, key=losses.get)
    candidate_pred = predict_candidate(name, fit_candidate(name, dev), dev, 0)[:h_audit]
    baseline_pred = predict_candidate("local_seasonal", fit_candidate("local_seasonal", dev), dev, 0)[:h_audit]
    audit = float(np.abs(candidate_pred - audit_target).mean())
    reference = float(np.abs(baseline_pred - audit_target).mean())
    if audit > reference and "local_seasonal" in residuals:
        name = "local_seasonal"
        audit = reference

    from .new_credit import select_credit

    result = dict(
        fitted_through=asof,
        ready_on=ready_on,
        name=name,
        model=fit_candidate(name, y),
        accounts=accounts,
        residuals=residuals[name],
        audit_mae=audit,
        reference_mae=reference,
        validation=losses,
        unavailable=unavailable,
        adaptive_short=True,
        min_history_weeks=8,
        credit=select_credit(data, asof, accounts) if include_new_credit else None,
    )
    result["version"] = (
        "operating:"
        + hashlib.sha256(pickle.dumps(result, protocol=4)).hexdigest()
    )
    return result


def select_operating(data, asof, try_deep=False, *, include_new_credit=True):
    ready_on = str(date.fromisoformat(asof))
    accounts = account_scope(data, asof)
    if not accounts:
        return None
    y, gap = available_history(data, asof, accounts)
    asof = str(date.fromisoformat(asof) - timedelta(weeks=gap))
    if len(y) < 8 or not np.any(y):
        return None
    if len(y) < 104:
        # Degenerate zero-variance short series (< 2 annual cycles) cannot verify seasonality
        if not np.any(np.ptp(y, axis=0) > 0):
            return None
        return _select_short_history_operating(
            data, y, asof, ready_on, accounts, try_deep, include_new_credit
        )
    names = ["seasonal", "gbm"]
    if try_deep and len(y) >= 156 and (np.count_nonzero(y, axis=0) >= 32).all():
        names.extend(["gaussian_gru", "gaussian_gru_wide", "gaussian_lstm"])
    if try_deep and os.environ.get("AGENT1_CHRONOS_DIR"):
        names.append("chronos")
    losses = {}
    unavailable = {}
    residuals = {}
    audit_origin = str(date.fromisoformat(asof) - timedelta(weeks=13))
    # Collect rolling OOS 13-week folds (stride 4 weeks, up to 16 origins) instead
    # of stopping at 3 discrete points, while retaining non-overlapping fallback.
    eligible = []
    for end in range(len(y) - 26, 51, -1):
        if eligible and eligible[-1] - end < 4:
            continue
        origin = date.fromisoformat(asof) - timedelta(weeks=len(y) - end)
        target = weekly_cash(
            data, str(origin + timedelta(days=1)), 13, audit_origin, accounts
        )[:, 2:]
        past, fold_gap = available_history(data, str(origin), accounts)
        if np.isfinite(target).all() and len(past) >= 52:
            eligible.append(end)
        if len(eligible) == 16:
            break
    if len(eligible) < 3:
        return None
    raw_by_name = {}
    for name in names:
        folds = []
        try:
            for end in reversed(eligible):
                origin = str(date.fromisoformat(asof) - timedelta(weeks=len(y) - end))
                past, fold_gap = available_history(data, origin, accounts)
                if len(past) < 52:
                    return None
                model = fit_candidate(name, past)
                target = weekly_cash(
                    data,
                    str(date.fromisoformat(origin) + timedelta(days=1)),
                    13,
                    audit_origin,
                    accounts,
                )[:, 2:]
                folds.append(target - predict_candidate(name, model, past, fold_gap))
        except (ImportError, RuntimeError, ValueError) as exc:
            unavailable[name] = type(exc).__name__
            continue
        raw_folds = np.asarray(folds)
        raw_by_name[name] = raw_folds
        losses[name] = float(np.abs(raw_folds).mean())
        residuals[name] = _expand_residual_trajectories(raw_folds, target_count=64)
    ranked = sorted(losses, key=losses.get)[:3]
    if len(ranked) > 1:
        pooled = "pool:" + ",".join(ranked)
        pooled_raw = np.mean([raw_by_name[n] for n in ranked], axis=0)
        losses[pooled] = float(np.abs(pooled_raw).mean())
        residuals[pooled] = _expand_residual_trajectories(pooled_raw, target_count=64)
    name = min(losses, key=losses.get)
    past, audit_gap = available_history(data, audit_origin, accounts)
    if len(past) < 52:
        return None
    candidate = predict_candidate(name, fit_candidate(name, past), past, audit_gap)
    baseline = predict_candidate("seasonal", None, past, audit_gap)
    audit = float(np.abs(candidate - y[-13:]).mean())
    reference = float(np.abs(baseline - y[-13:]).mean())
    if audit >= reference:
        name = "seasonal"
    from .new_credit import select_credit

    result = dict(
        fitted_through=asof,
        ready_on=ready_on,
        name=name,
        model=fit_candidate(name, y),
        accounts=accounts,
        residuals=residuals[name],
        audit_mae=audit,
        reference_mae=reference,
        validation=losses,
        unavailable=unavailable,
        min_history_weeks=52,
        credit=select_credit(data, asof, accounts) if include_new_credit else None,
    )
    # Hash once at fit time, then retain the ID with the artifact. Re-pickling a
    # loaded sklearn estimator can change bytes despite identical parameters.
    # This fit ID covers model, residual law, scope and the optional credit head.
    result["version"] = (
        "operating:" + hashlib.sha256(pickle.dumps(result, protocol=4)).hexdigest()
    )
    return result
