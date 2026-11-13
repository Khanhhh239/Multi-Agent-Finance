"""Temporal, accounting and served-probability contracts of compact T1."""
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agent1.adaptive.compact_t1 import (
    CompactT1, FEATURES, Ledger, explain_compact, load_workspace_bundle,
    prepare_features, workspace_context,
)
from agent1.adaptive.methods import forecast


def book():
    invoices, payments = [], []
    for i in range(90):
        day = pd.Timestamp("2024-01-01")+pd.Timedelta(days=i)
        invoices.append(dict(invoice_id=f"I{i}", customer_id=f"C{i%5}", amount=100_000*(i%4+1),
                             issue_date=str(day.date()), due_date=str((day+pd.Timedelta(days=21)).date()), known_at=str(day.date())))
        if i < 60:
            pay = day+pd.Timedelta(days=14+i%4*7)
            payments.append(dict(payment_id=f"P{i}", invoice_id=f"I{i}", amount=invoices[-1]["amount"], payment_date=str(pay.date()), known_at=str(pay.date())))
    payments.append(dict(payment_id="PART", invoice_id="I70", amount=50_000, payment_date="2024-03-20", known_at="2024-03-21"))
    return dict(invoices=invoices, payments=payments, outflows=[])


def ledger(data=None):
    data = data or book()
    return Ledger(pd.DataFrame(data["invoices"]), pd.DataFrame(data["payments"]).rename(columns={"payment_date":"date"}))


class ToyBooster:
    """A state-dependent hazard lets faithfulness tests detect ignored columns."""
    def predict(self, x, **kwargs):
        x = np.asarray(x)
        return 1/(1+np.exp(-(-3.+.3*x[:, 0]+.01*x[:, 2]+x[:, 3]-.01*x[:, 5]-.5*x[:, 8]+.02*x[:, -1])))


def test_snapshot_excludes_future_and_late_known_receipts():
    data = book()
    first, x = ledger(data).snapshot_features("2024-03-31")
    altered = deepcopy(data)
    altered["payments"].append(dict(payment_id="LATE", invoice_id="I71", amount=200_000, payment_date="2024-03-15", known_at="2024-04-02"))
    second, y = ledger(altered).snapshot_features("2024-03-31")
    pd.testing.assert_frame_equal(first, second)
    np.testing.assert_array_equal(x, y)
    assert len(FEATURES) == 10
    row = first.invoice_id.tolist().index("I70")
    assert x[row, 3] == pytest.approx(50_000/300_000)
    assert x[row, 4] == 11


def test_landmark_state_refreshes_at_current_origin():
    source = ledger()
    a = source.snapshot("2024-03-19")
    b = source.snapshot("2024-03-31")
    row_a = a[a.invoice_id == "I70"]
    row_b = b[b.invoice_id == "I70"]
    xa = prepare_features(row_a, a, "2024-03-19")
    xb = prepare_features(row_b, b, "2024-03-31")
    assert xa[0, 3] == 0 and xb[0, 3] > 0
    assert xb[0, 2]-xa[0, 2] == 12
    with pytest.raises(ValueError, match="origin"):
        prepare_features(row_a, b, "2024-03-19")


def test_label_maturity_and_noncash_closure_exclusion():
    source = ledger()
    opened, _ = source.snapshot_features("2024-03-31")
    with pytest.raises(ValueError, match="91"):
        source.labels(opened, "2024-03-31", "2024-04-30")
    source.credits = pd.DataFrame([dict(invoice_id="I70", date=pd.Timestamp("2024-04-03"), known_at=pd.Timestamp("2024-04-03"), available=pd.Timestamp("2024-04-03"), amount=250_000.)])
    days, valid = source.labels(opened, "2024-03-31", "2024-07-01")
    assert not valid[opened.invoice_id.tolist().index("I70")]
    assert np.isinf(days[opened.invoice_id.tolist().index("I70")])


def test_tenants_cannot_share_a_history_pool():
    invoices = pd.DataFrame(book()["invoices"])
    invoices["firm_id"] = ["A", "B"]*45
    with pytest.raises(ValueError, match="tenant"):
        Ledger(invoices, pd.DataFrame(book()["payments"]).rename(columns={"payment_date":"date"}))


def test_grouped_shap_reconstructs_served_probability_and_scenario():
    history = ledger().snapshot("2024-03-31")
    opened = history[(history.remaining_amount > 0) & history.written_off_at.isna()].copy()
    opened.attrs["compact_context"] = history
    model = CompactT1(ToyBooster())
    probability = model.distribution(opened)[:, :2].sum(1)
    rows = [dict(invoice_id=str(r.invoice_id), customer_id=str(r.customer_id), payment_probability_4w=float(probability[i])) for i, r in enumerate(opened.iloc[:3].itertuples())]
    snapshot = explain_compact(rows, opened, [(1., model)], pd.Timestamp("2024-03-31"), delay_days=14, background_policy="legacy24")
    assert snapshot["count"] <= 24
    for row in rows:
        explanation = row["payment_explanation"]
        assert explanation["group_count"] == 6
        assert explanation["coalition_count"] == 64
        assert explanation["additivity_error"] < 1e-10
        assert sum(f["contribution"] for f in explanation["factors"])+explanation["baseline_probability"] == pytest.approx(row["payment_probability_4w"], abs=1e-10)
        assert not explanation["stability"]["checked"]
    p = model.distribution(opened, horizon=26)
    np.testing.assert_allclose(p.sum(1), 1)
    assert np.all(p[:, 13:26] == 0)


def test_workspace_forecast_uses_observed_context_and_keeps_future_invariant():
    data = book()
    model = CompactT1(ToyBooster())
    from agent1.adaptive.cash_adapter import fit_partial
    bundle = dict(model=model, anchor=model, weight=1., asof="2024-03-01", selected_method="compact_world", partial=fit_partial(pd.DataFrame(), "2024-01-01", prior=None))
    result = forecast(data, "2024-03-31", 0, bundle)
    assert result["collections"]
    assert all(r["payment_explanation"]["method"] == "exact_grouped_interventional_shapley" for r in result["collections"])
    altered = deepcopy(data)
    altered["payments"].append(dict(payment_id="FUT", invoice_id="I89", amount=200_000, payment_date="2024-04-15", known_at="2024-04-15"))
    again = forecast(altered, "2024-03-31", 0, bundle)
    assert result["weeks"] == again["weeks"]
    assert [r["payment_probability_4w"] for r in result["collections"]] == [r["payment_probability_4w"] for r in again["collections"]]


def test_workspace_and_world_builder_share_feature_semantics():
    data = book()
    one = workspace_context(data, "2024-03-31")
    two = ledger(data).snapshot("2024-03-31")
    opened = one[one.remaining_amount > 0].copy()
    x = prepare_features(opened, one, "2024-03-31")
    aligned = two.set_index("invoice_id").loc[opened.invoice_id].reset_index()
    y = prepare_features(aligned, two, "2024-03-31")
    np.testing.assert_allclose(x, y, atol=1e-12)


def test_native_artifact_roundtrip_hash_and_temporal_guard(tmp_path):
    import lightgbm as lgb
    from agent1.adaptive.compact_t1 import sha256

    rng = np.random.default_rng(17)
    x = rng.normal(size=(80, 11))
    y = (x[:, 0] > 0).astype(int)
    booster = lgb.train(dict(objective="binary", verbosity=-1, num_threads=1, min_data_in_leaf=5), lgb.Dataset(x, label=y), num_boost_round=3)
    model = CompactT1(booster)
    model.save(tmp_path, dict(available_asof="2024-07-01", data_fingerprint="fixture", source_sha256="fixture"))
    restored = CompactT1.load(tmp_path)
    np.testing.assert_allclose(model.distribution_from_features(x[:, :10]), restored.distribution_from_features(x[:, :10]), atol=1e-12)
    with pytest.raises(ValueError, match="after"):
        load_workspace_bundle(tmp_path, "2024-06-30")
    assert load_workspace_bundle(tmp_path, "2024-07-01")["weight"] == 1
    (tmp_path/"model.txt").write_bytes((tmp_path/"model.txt").read_bytes()+b"\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        CompactT1.load(tmp_path)
