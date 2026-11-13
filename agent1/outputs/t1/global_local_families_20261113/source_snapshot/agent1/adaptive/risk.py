"""Finite-horizon recorded write-off risk. Unpaid alone is never a positive label."""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from .data import observed


def design(frame):
    # Issuance-time attributes, no outcome or customer identifier.
    return np.column_stack(
        [np.log1p(frame.amount), (frame.due_date - frame.issue_date).dt.days]
    )


def train_risk(data, asof):
    frame = observed(data, asof).sort_values("issue_date")
    frame = frame[
        (frame.issue_date <= pd.Timestamp(asof) - pd.Timedelta(days=365))
        & (frame.known_at <= frame.issue_date)
    ]
    unavailable = dict(
        status="insufficient_labels",
        horizon_days=365,
        definition="recorded_write_off_within_365_days",
        n=len(frame),
    )
    if len(frame) < 150:
        return unavailable
    # Date boundaries and maturity embargo: no future labels train an earlier origin.
    dates = frame.issue_date.sort_values()
    audit_start = dates.iloc[int(len(dates) * 0.8)]
    val_start = dates.iloc[int(len(dates) * 0.6)]
    train = frame[frame.issue_date + pd.Timedelta(days=365) < val_start]
    val = frame[
        (frame.issue_date >= val_start)
        & (frame.issue_date + pd.Timedelta(days=365) < audit_start)
    ]
    audit = frame[frame.issue_date >= audit_start]

    def label(f):
        return (
            ((f.written_off_at - f.issue_date).dt.days.between(0, 365))
            .astype(int)
            .to_numpy()
        )

    if (
        min(map(len, (train, val, audit))) < 20
        or min(np.bincount(label(train), minlength=2)) < 10
    ):
        return unavailable
    train = (
        observed(data, val_start - pd.Timedelta(days=1))
        .set_index("invoice_id")
        .loc[train.invoice_id]
        .reset_index()
    )
    val = (
        observed(data, audit_start - pd.Timedelta(days=1))
        .set_index("invoice_id")
        .loc[val.invoice_id]
        .reset_index()
    )
    y = label(train)
    if min(np.bincount(y, minlength=2)) < 10:
        return unavailable
    prior = float((y.sum() + 1) / (len(y) + 2))
    candidates = {
        "prior": None,
        "logistic": make_pipeline(
            StandardScaler(), LogisticRegression(C=0.1, max_iter=300)
        ),
        "logistic_flexible": make_pipeline(
            StandardScaler(), LogisticRegression(C=1, max_iter=300)
        ),
        "boosting": HistGradientBoostingClassifier(
            max_leaf_nodes=7, l2_regularization=10, random_state=7
        ),
    }
    if len(train) >= 1000 and min(np.bincount(y)) >= 50:
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
            np.full(len(val), prior)
            if model is None
            else model.predict_proba(design(val))[:, 1]
        )
        validation[name] = float(np.mean((p - label(val)) ** 2))
    chosen = min(validation, key=validation.get)
    model = candidates[chosen]
    p = (
        np.full(len(audit), prior)
        if model is None
        else model.predict_proba(design(audit))[:, 1]
    )
    baseline = float(np.mean((prior - label(audit)) ** 2))
    loss = float(np.mean((p - label(audit)) ** 2))
    accepted = loss <= baseline
    if not accepted:
        model = None
    # Refit only after the audit gate has been recorded.
    if model is not None:
        model.fit(design(frame), label(frame))
    return dict(
        status="evaluated",
        model=model,
        prior=float((label(frame).sum() + 1) / (len(frame) + 2)),
        validation=validation,
        audit_brier=loss,
        baseline_brier=baseline,
        accepted=accepted,
        n=len(frame),
        audit_n=len(audit),
        horizon_days=365,
        definition="recorded_write_off_within_365_days",
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
