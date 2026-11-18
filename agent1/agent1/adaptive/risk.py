"""Finite-horizon recorded write-off risk. Unpaid alone is never a positive label."""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .data import observed
from .payment_coverage import reconciled_bounds


def design(frame):
    # Issuance-time attributes, no outcome or customer identifier.
    return np.column_stack(
        [np.log1p(frame.amount), (frame.due_date - frame.issue_date).dt.days]
    )


def _eligible_issuance_mask(frame: pd.DataFrame, data: dict, cutoff: pd.Timestamp) -> pd.Series:
    """Admit invoices recorded promptly or covered by confirmed historical books."""
    prompt = frame.known_at <= (frame.issue_date + pd.Timedelta(days=31))
    bounds = reconciled_bounds(data, cutoff)
    if not bounds:
        return frame.known_at <= frame.issue_date if (frame.known_at <= frame.issue_date).sum() >= 24 else prompt
    in_reconciled = pd.Series(False, index=frame.index)
    issue_iso = frame.issue_date.dt.strftime("%Y-%m-%d")
    for start, end in bounds:
        in_reconciled |= (issue_iso >= start) & (issue_iso <= end)
    return (frame.known_at <= frame.issue_date) | in_reconciled | prompt


def train_risk(data, asof):
    cutoff = pd.Timestamp(asof)
    bounds = reconciled_bounds(data, cutoff)
    if bounds:
        from .t1_data import _project_confirmed_historical

        working_data = _project_confirmed_historical(
            data, cutoff.normalize(), max(end for _, end in bounds)
        )
    else:
        working_data = data
    all_obs = observed(working_data, cutoff).sort_values("issue_date")
    if all_obs.empty:
        return dict(
            fitted_through=str(cutoff.date()),
            ready_on=str(cutoff.date()),
            status="insufficient_labels",
            horizon_days=365,
            definition="recorded_write_off_within_365_days",
            n=0,
        )

    eligible_mask = _eligible_issuance_mask(all_obs, data, cutoff)
    frame_365 = all_obs[
        (all_obs.issue_date <= cutoff - pd.Timedelta(days=365)) & eligible_mask
    ].copy()

    # Adaptive SME horizon: use 365d when >=60 mature annual invoices exist;
    # otherwise fall back to 180d (6-12 months SME history) when >=24 exist.
    if len(frame_365) >= 60:
        frame = frame_365
        horizon_days = 365
    else:
        frame_180 = all_obs[
            (all_obs.issue_date <= cutoff - pd.Timedelta(days=180)) & eligible_mask
        ].copy()
        if len(frame_180) >= 24:
            frame = frame_180
            horizon_days = 180
        else:
            return dict(
                fitted_through=str(cutoff.date()),
                ready_on=str(cutoff.date()),
                status="insufficient_labels",
                horizon_days=365,
                definition="recorded_write_off_within_365_days",
                n=len(frame_365),
            )

    definition = f"recorded_write_off_within_{horizon_days}_days"
    unavailable = dict(
        fitted_through=str(cutoff.date()),
        ready_on=str(cutoff.date()),
        status="insufficient_labels",
        horizon_days=horizon_days,
        definition=definition,
        n=len(frame),
    )

    dates = frame.issue_date.sort_values().reset_index(drop=True)
    audit_idx = int(len(dates) * 0.8)
    val_idx = int(len(dates) * 0.6)
    audit_start = dates.iloc[audit_idx]
    val_start = dates.iloc[val_idx]

    # Prefer strict full-horizon embargo when multi-year history exists;
    # otherwise use resolved chronological cohorts capped at each split's maturity.
    strict_train = frame[frame.issue_date + pd.Timedelta(days=horizon_days) < val_start]
    strict_val = frame[
        (frame.issue_date >= val_start)
        & (frame.issue_date + pd.Timedelta(days=horizon_days) < audit_start)
    ]
    strict_audit = frame[frame.issue_date >= audit_start]

    if min(map(len, (strict_train, strict_val, strict_audit))) >= 20:
        train = (
            observed(working_data, val_start - pd.Timedelta(days=1))
            .set_index("invoice_id")
            .loc[strict_train.invoice_id]
            .reset_index()
        )
        val = (
            observed(working_data, audit_start - pd.Timedelta(days=1))
            .set_index("invoice_id")
            .loc[strict_val.invoice_id]
            .reset_index()
        )
        audit = strict_audit
    else:
        train_raw = frame.iloc[:val_idx].copy()
        val_raw = frame.iloc[val_idx:audit_idx].copy()
        audit = frame.iloc[audit_idx:].copy()
        if min(len(train_raw), len(val_raw), len(audit)) < 4:
            return unavailable
        train_clock = min(
            cutoff, train_raw.issue_date.max() + pd.Timedelta(days=horizon_days)
        )
        val_clock = min(
            cutoff, val_raw.issue_date.max() + pd.Timedelta(days=horizon_days)
        )
        train = (
            observed(working_data, train_clock)
            .set_index("invoice_id")
            .loc[train_raw.invoice_id]
            .reset_index()
        )
        val = (
            observed(working_data, val_clock)
            .set_index("invoice_id")
            .loc[val_raw.invoice_id]
            .reset_index()
        )

    def label(f):
        return (
            ((f.written_off_at - f.issue_date).dt.days.between(0, horizon_days))
            .astype(int)
            .to_numpy()
        )

    y = label(train)
    prior_train = float((y.sum() + 1) / (len(y) + 2))
    full_prior = float((label(frame).sum() + 1) / (len(frame) + 2))

    # Graceful Empirical Bayes Beta-Binomial fallback when write-off events are rare
    min_class = int(min(np.bincount(y, minlength=2)))
    if min_class < 4 or len(train) < 20:
        val_brier = float(np.mean((prior_train - label(val)) ** 2))
        audit_brier = float(np.mean((prior_train - label(audit)) ** 2))
        return dict(
            fitted_through=str(cutoff.date()),
            ready_on=str(cutoff.date()),
            status="evaluated",
            model=None,
            prior=full_prior,
            validation={"prior": val_brier},
            audit_brier=audit_brier,
            baseline_brier=audit_brier,
            accepted=True,
            fallback="empirical_bayes_prior",
            n=len(frame),
            audit_n=len(audit),
            horizon_days=horizon_days,
            definition=definition,
        )

    candidates = {
        "prior": None,
        "logistic": make_pipeline(
            StandardScaler(), LogisticRegression(C=0.1, max_iter=300)
        ),
        "logistic_flexible": make_pipeline(
            StandardScaler(), LogisticRegression(C=1, max_iter=300)
        ),
        "boosting": HistGradientBoostingClassifier(
            max_leaf_nodes=7,
            min_samples_leaf=min(20, max(3, len(train) // 5)),
            l2_regularization=10,
            random_state=7,
        ),
    }
    if len(train) >= 1000 and min_class >= 50:
        candidates["neural"] = make_pipeline(
            StandardScaler(),
            MLPClassifier(
                hidden_layer_sizes=(32, 16), alpha=0.1, max_iter=100, random_state=7
            ),
        )
    validation = {}
    for name, model in candidates.items():
        if model is not None:
            model.fit(design(train), y)
        p = (
            np.full(len(val), prior_train)
            if model is None
            else model.predict_proba(design(val))[:, 1]
        )
        validation[name] = float(np.mean((p - label(val)) ** 2))
    chosen = min(validation, key=validation.get)
    model = candidates[chosen]
    p = (
        np.full(len(audit), prior_train)
        if model is None
        else model.predict_proba(design(audit))[:, 1]
    )
    baseline = float(np.mean((prior_train - label(audit)) ** 2))
    loss = float(np.mean((p - label(audit)) ** 2))
    accepted = loss <= baseline
    if not accepted:
        model = None
    # Refit only after the audit gate has been recorded.
    if model is not None:
        model.fit(design(frame), label(frame))
    return dict(
        fitted_through=str(cutoff.date()),
        ready_on=str(cutoff.date()),
        status="evaluated",
        model=model,
        prior=full_prior,
        validation=validation,
        audit_brier=loss,
        baseline_brier=baseline,
        accepted=accepted,
        n=len(frame),
        audit_n=len(audit),
        horizon_days=horizon_days,
        definition=definition,
    )


def predict_risk(bundle, frame):
    if not bundle or bundle.get("status") != "evaluated":
        return [None] * len(frame)
    model = bundle["model"]
    p = (
        np.full(len(frame), bundle["prior"])
        if model is None or not len(frame)
        else model.predict_proba(design(frame))[:, 1]
    )
    # This is issuance-time risk, not conditional lifetime default probability.
    return [float(v) for v in p]
