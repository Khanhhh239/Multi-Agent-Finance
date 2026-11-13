"""As-of receipt features, full-cohort SHAP, and cash/survival evaluation contracts."""

import json

import numpy as np
import pandas as pd
import pytest
from agent1.adaptive.compact_t1 import (
    CompactT1,
    Ledger,
    explain_compact,
    workspace_context,
)
from agent1.adaptive.landmark_features import (
    FEATURES,
    GROUPS,
    LandmarkEnsemble,
    LandmarkHazard,
    LandmarkRule,
    prepare_features,
)
from experiments.t1_compact.landmark_data import CASH_COLUMNS, OVERRIDE_COLUMNS
from experiments.t1_compact.train_landmark import (
    context_for,
    score_prediction,
    summarize_prediction,
)
from sklearn.linear_model import LogisticRegression


def book():
    invoices, payments = [], []
    for index in range(90):
        issued = pd.Timestamp("2024-01-01") + pd.Timedelta(days=index)
        invoices.append(
            {
                "invoice_id": f"I{index}",
                "customer_id": f"C{index % 5}",
                "amount": 100_000 * (index % 4 + 1),
                "issue_date": str(issued.date()),
                "due_date": str((issued + pd.Timedelta(days=21)).date()),
                "known_at": str(issued.date()),
            }
        )
        if index < 60:
            paid = issued + pd.Timedelta(days=14 + 7 * (index % 4))
            payments.append(
                {
                    "payment_id": f"P{index}",
                    "invoice_id": f"I{index}",
                    "amount": invoices[-1]["amount"],
                    "payment_date": str(paid.date()),
                    "known_at": str(paid.date()),
                }
            )
    payments.extend(
        [
            {
                "payment_id": "PART1",
                "invoice_id": "I70",
                "amount": 50000,
                "payment_date": "2024-03-15",
                "known_at": "2024-03-16",
            },
            {
                "payment_id": "PART2",
                "invoice_id": "I70",
                "amount": 25000,
                "payment_date": "2024-03-25",
                "known_at": "2024-03-26",
            },
        ]
    )
    return {"invoices": invoices, "payments": payments, "outflows": []}


def ledger(data):
    return Ledger(
        pd.DataFrame(data["invoices"]),
        pd.DataFrame(data["payments"]).rename(columns={"payment_date": "date"}),
    )


def opened_state(data):
    history = ledger(data).snapshot("2024-03-31")
    opened = history[
        (history.remaining_amount > 0.01) & history.written_off_at.isna()
    ].copy()
    opened.attrs["compact_context"] = history
    return opened, history


def test_requested_eighteen_features_match_world_and_workspace_and_exclude_future():
    data = book()
    opened, history = opened_state(data)
    x = prepare_features(opened, history, "2024-03-31")
    assert len(FEATURES) == 18 and [len(columns) for _, _, columns in GROUPS] == [
        2,
        1,
        4,
        4,
        2,
        5,
    ]
    workspace = workspace_context(data, "2024-03-31")
    targets = workspace.set_index("invoice_id").loc[opened.invoice_id].reset_index()
    np.testing.assert_allclose(
        x, prepare_features(targets, workspace, "2024-03-31"), atol=1e-12, rtol=0
    )
    position = opened.invoice_id.tolist().index("I70")
    assert np.expm1(x[position, 5]) == pytest.approx(2)
    assert x[position, 3] == pytest.approx(75000 / 300000)
    assert x[position, 6] == pytest.approx(75000 / 300000)
    assert x[position, 4] == 6
    assert (x[:, 13] >= x[:, 14]).all() and (x[:, 15] >= x[:, 16]).all()
    assert ((x[:, 17] >= 0) & (x[:, 17] <= 1)).all()
    changed = book()
    changed["payments"].append(
        {
            "payment_id": "LATE",
            "invoice_id": "I71",
            "amount": 100000,
            "payment_date": "2024-03-20",
            "known_at": "2024-04-02",
        }
    )
    other, context = opened_state(changed)
    np.testing.assert_array_equal(x, prepare_features(other, context, "2024-03-31"))


def test_feature_scale_invariance_and_census_shap_roundtrip(tmp_path):
    data = book()
    opened, history = opened_state(data)
    x = prepare_features(opened, history, "2024-03-31")
    for kind in ("invoices", "payments"):
        for row in data[kind]:
            row["amount"] *= 11
    scaled, scaled_history = opened_state(data)
    np.testing.assert_allclose(
        x, prepare_features(scaled, scaled_history, "2024-03-31"), atol=1e-12, rtol=0
    )
    rng = np.random.default_rng(34)
    design = rng.normal(size=(100, 19))
    labels = (design[:, 0] + design[:, 3] > 0).astype(int)
    model = LandmarkEnsemble(
        [LandmarkHazard(LogisticRegression().fit(design, labels), "fixture")], [1.0]
    )
    model.save(
        tmp_path,
        {
            "available_asof": "2024-07-01",
            "data_fingerprint": "fixture",
            "source_sha256": "fixture",
        },
    )
    restored = CompactT1.load(tmp_path)
    np.testing.assert_allclose(
        restored.distribution(opened), model.distribution(opened), atol=1e-12
    )
    probabilities = model.distribution(opened)[:, :4].sum(1)
    rows = [
        {
            "invoice_id": str(row.invoice_id),
            "customer_id": str(row.customer_id),
            "payment_probability_4w": float(probabilities[index]),
        }
        for index, row in enumerate(opened.iloc[:3].itertuples())
    ]
    reference = explain_compact(rows, opened, [(1.0, model)], "2024-03-31")
    assert reference["selection"] == "census" and reference["count"] == len(opened)
    assert reference["audit_sample_count"] == 3
    for row in rows:
        explanation = row["payment_explanation"]
        assert explanation["coalition_count"] == 64
        assert explanation["stability"]["checked"]
        assert explanation["additivity_error"] < 1e-10
    metadata = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert len(metadata["features"]) == 18


def cash_frame():
    frame = pd.DataFrame(
        {
            "world": ["W"] * 4,
            "firm": ["F"] * 4,
            "origin": pd.to_datetime(["2024-01-01"] * 4),
            "invoice_id": [f"I{i}" for i in range(4)],
            "paid_days": [7.0] * 4,
            "amount_open": [100.0, 100.0, 100.0, 700.0],
            "partial_override": [False] * 4,
        }
    )
    for index, column in enumerate(CASH_COLUMNS):
        frame[column] = 1.0 if index == 0 else 0.0
    for index, column in enumerate(OVERRIDE_COLUMNS):
        frame[column] = 1.0 if index == 13 else 0.0
    return frame


def test_cash_selection_detects_weekly_error_hidden_by_brier4_and13():
    frame = cash_frame()
    context = context_for(frame)
    early = np.zeros((4, 14))
    early[:, 0] = 1.0
    late = np.zeros((4, 14))
    late[:, 3] = 1.0
    a = score_prediction(summarize_prediction(early, context), context)
    b = score_prediction(summarize_prediction(late, context), context)
    assert a["brier4"] == b["brier4"] == a["brier13"] == b["brier13"] == 0.0
    assert a["score"] == 0.0 and b["score"] > 0.0
    assert b["integrated_brier13"] > a["integrated_brier13"]
    frame["partial_override"] = True
    context = context_for(frame)
    assert (
        score_prediction(summarize_prediction(early, context), context)["score"]
        == score_prediction(summarize_prediction(late, context), context)["score"]
    )


def test_survival_and_learned_models_share_cash_paid_and_unpaid_labels():
    from experiments.t1_compact.train import risk_rows

    data = book()
    source = ledger(data)
    source.invoices.loc[source.invoices.invoice_id == "I70", "written_off_at"] = (
        pd.Timestamp("2024-04-01")
    )
    history = source.snapshot("2024-03-31")
    opened = history[history.invoice_id == "I70"].copy()
    days, valid = source.labels(opened, "2024-03-31", "2024-07-01")
    assert valid.all() and np.isinf(days).all()
    frame = pd.DataFrame(
        prepare_features(opened, history, "2024-03-31"), columns=FEATURES
    )
    (
        frame["paid_days"],
        frame["invoice_id"],
        frame["world"],
        frame["firm"],
        frame["origin"],
    ) = np.inf, "I70", "W", "F", pd.Timestamp("2024-03-31")
    x, y, weights = risk_rows(frame, tuple(range(18)), FEATURES)
    assert len(x) == 13 and y.sum() == 0 and (weights > 0).all()
    survival = LandmarkRule("survival", np.full((5, 13), 0.02))
    assert survival.active == (2,)
    p = survival.distribution_from_features(frame[list(FEATURES)].to_numpy(float))
    assert p.shape == (1, 14)
    np.testing.assert_allclose(p.sum(1), 1.0, atol=1e-12)
