"""Weekly direct sales and variable expenses on reconciled statements only."""

import os
from datetime import date, timedelta
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from .cash_history import weekly_cash
from .data import account_scope


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


def fit_candidate(name, y):
    if name.startswith("pool:"):
        return [(n, fit_candidate(n, y)) for n in name[5:].split(",")]
    if name == "seasonal":
        return None
    if name == "chronos":
        from pathlib import Path

        path = os.environ.get("AGENT1_CHRONOS_DIR", "")
        if not path or not Path(path).is_dir():
            raise ValueError("Cần thư mục Chronos local đã kiểm tra")
        return path
    if name == "gbm":
        models = []
        for series in y.T:
            X = np.array([series[t - 8 : t] for t in range(8, len(series))])
            models.append(
                HistGradientBoostingRegressor(
                    max_iter=40, max_leaf_nodes=7, min_samples_leaf=8, random_state=7
                ).fit(X, series[8:])
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
        return y[-52:][gap:horizon].copy()
    if name == "chronos":
        from agent1.models.t4_revenue import chronos_predict

        estimates = chronos_predict(list(y.T), horizon=horizon, model_id=model)
        if estimates is None:
            raise ValueError("Thiếu runtime Chronos")
        return np.stack([r[gap:, 1] for r in estimates], axis=1)
    if name == "gbm":
        points = []
        for estimator, series in zip(model, y.T):
            window = list(series[-8:])
            for _ in range(horizon):
                window.append(max(0, float(estimator.predict([window[-8:]])[0])))
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
            loc = head(last)[:, 0].clamp(0, 12)
            out.append(np.expm1(loc.numpy()) * scale)
            hidden, state = gru(loc[:, None, None], state)
            last = hidden[:, 0]
    return np.asarray(out)[gap:]


def select_operating(data, asof, try_deep=False):
    accounts = account_scope(data, asof)
    if not accounts:
        return None
    y, gap = available_history(data, asof, accounts)
    asof = str(date.fromisoformat(asof) - timedelta(weeks=gap))
    if len(y) < 104 or not np.any(y):
        return None
    names = ["seasonal", "gbm"]
    if try_deep and len(y) >= 156 and (np.count_nonzero(y, axis=0) >= 32).all():
        names.extend(["gaussian_gru", "gaussian_gru_wide", "gaussian_lstm"])
    if try_deep and os.environ.get("AGENT1_CHRONOS_DIR"):
        names.append("chronos")
    losses = {}
    unavailable = {}
    residuals = {}
    audit_origin = str(date.fromisoformat(asof) - timedelta(weeks=13))
    eligible = []
    # Only labels already certified before the locked audit may choose the model.
    for end in range(len(y) - 26, 51, -1):
        if eligible and eligible[-1] - end < 13:
            continue
        origin = date.fromisoformat(asof) - timedelta(weeks=len(y) - end)
        target = weekly_cash(
            data, str(origin + timedelta(days=1)), 13, audit_origin, accounts
        )[:, 2:]
        past, gap = available_history(data, str(origin), accounts)
        if np.isfinite(target).all() and len(past) >= 52:
            eligible.append(end)
        if len(eligible) == 3:
            break
    if len(eligible) < 3:
        return None
    for name in names:
        folds = []
        try:
            for end in reversed(eligible):
                origin = str(date.fromisoformat(asof) - timedelta(weeks=len(y) - end))
                past, gap = available_history(data, origin, accounts)
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
                folds.append(target - predict_candidate(name, model, past, gap))
        except (ImportError, RuntimeError, ValueError) as exc:
            unavailable[name] = type(exc).__name__
            continue
        residuals[name] = np.asarray(folds)
        losses[name] = float(np.abs(folds).mean())
    ranked = sorted(losses, key=losses.get)[:3]
    if len(ranked) > 1:
        pooled = "pool:" + ",".join(ranked)
        residuals[pooled] = np.mean([residuals[n] for n in ranked], axis=0)
        losses[pooled] = float(np.abs(residuals[pooled]).mean())
    name = min(losses, key=losses.get)
    past, gap = available_history(data, audit_origin, accounts)
    if len(past) < 52:
        return None
    candidate = predict_candidate(name, fit_candidate(name, past), past, gap)
    baseline = predict_candidate("seasonal", None, past, gap)
    audit = float(np.abs(candidate - y[-13:]).mean())
    reference = float(np.abs(baseline - y[-13:]).mean())
    if audit >= reference:
        name = "seasonal"
    from .new_credit import select_credit

    return dict(
        name=name,
        model=fit_candidate(name, y),
        accounts=accounts,
        residuals=residuals[name],
        audit_mae=audit,
        reference_mae=reference,
        validation=losses,
        unavailable=unavailable,
        credit=select_credit(data, asof, accounts),
    )
