"""Observation-clock and common-cohort checks for the retrospective comparison."""

import numpy as np
import pandas as pd
import pytest

from agent1.adaptive.compact_t1 import Ledger
from agent1.adaptive.data import observed
from experiments.t1_compact import compare_workspace_worlds as comparison


def example_ledger():
    invoices = pd.DataFrame([
        dict(invoice_id="A", customer_id="C", amount=100_000,
             issue_date="2024-01-01", due_date="2024-01-31", known_at="2024-01-01",
             written_off_at=pd.NaT),
        dict(invoice_id="B", customer_id="C", amount=200_000,
             issue_date="2024-01-02", due_date="2024-02-01", known_at="2024-01-02",
             written_off_at="2024-04-01"),
    ])
    payments = pd.DataFrame([
        dict(invoice_id="A", date="2024-02-01", known_at="2024-02-02", amount=40_000),
        dict(invoice_id="A", date="2024-02-03", known_at="2024-03-01", amount=10_000),
    ])
    credits = pd.DataFrame([
        dict(invoice_id="A", date="2024-02-10", known_at="2024-02-12", amount=20_000),
        dict(invoice_id="A", date="2024-03-10", known_at="2024-03-10", amount=10_000),
    ])
    return Ledger(invoices, payments, credits)


@pytest.mark.parametrize("cutoff", ["2024-02-01", "2024-02-02", "2024-02-12", "2024-03-01", "2024-04-01"])
def test_adapter_preserves_dated_claims_receipts_and_writeoffs(cutoff):
    ledger = example_ledger()
    data = comparison.workspace_data(ledger)
    expected = ledger.snapshot(cutoff).set_index("invoice_id").sort_index()
    actual = observed(data, cutoff).set_index("invoice_id").sort_index()
    np.testing.assert_array_equal(actual.remaining_amount, expected.remaining_amount)
    np.testing.assert_array_equal(actual.received, expected.received)
    np.testing.assert_array_equal(actual.written_off_at, expected.written_off_at)
    truncated = observed(comparison.past_data(data, cutoff), cutoff).set_index("invoice_id").sort_index()
    pd.testing.assert_frame_equal(actual, truncated)


def test_adapter_keeps_noncash_revision_out_of_issuance_time_training():
    frame = observed(comparison.workspace_data(example_ledger()), "2024-02-12")
    revised = frame.set_index("invoice_id").loc["A"]
    assert revised.known_at > revised.issue_date
    assert revised.received == 40_000
    assert revised.remaining_amount == 40_000


def test_only_runtime_insufficient_history_is_a_fallback(monkeypatch):
    def missing(*args):
        raise ValueError("Chưa đủ lịch sử: cần thêm quan sát")

    monkeypatch.setattr(comparison, "train", missing)
    assert comparison.fit_local({}, "2024-01-01")[0] is None

    def broken(*args):
        raise ValueError("Estimator failed")

    monkeypatch.setattr(comparison, "train", broken)
    with pytest.raises(ValueError, match="Estimator failed"):
        comparison.fit_local({}, "2024-01-01")


def test_parallel_cache_worker_leaves_world_publication_to_main_runner(tmp_path, monkeypatch):
    from experiments.t1_compact.precompute_workspace_world_firms import run

    original_sha = comparison.sha256
    original_npz = comparison.np.savez_compressed

    def fake_world(output, world):
        checkpoint = output / "checkpoint.npz"
        comparison.np.savez_compressed(checkpoint, distribution=np.ones((1, 14))/14)
        comparison.write_json(output / "checkpoint.json", {"sha256": comparison.sha256(checkpoint)})
        comparison.np.savez_compressed(output / "predictions.npz", distribution=np.zeros((2, 14)))
        comparison.write_json(output / "receipt.json", {"sha256": comparison.sha256(output / "predictions.npz")})
        comparison.write_json(output / "fits.json", [])

    monkeypatch.setattr(comparison, "run_world", fake_world)
    run(tmp_path, "test", {"firm"})
    assert (tmp_path / "checkpoint.npz").exists()
    assert (tmp_path / "checkpoint.json").exists()
    assert not (tmp_path / "predictions.npz").exists()
    assert not (tmp_path / "receipt.json").exists()
    assert not (tmp_path / "fits.json").exists()
    assert comparison.sha256 is original_sha
    assert comparison.np.savez_compressed is original_npz


def test_float32_hazards_preserve_probability_mass_and_horizon_prefix():
    from experiments.t1_compact.historical_workspace import Method

    class Float32Estimator:
        def predict_proba(self, rows):
            hazard = np.asarray(.07 + .001 * rows[:, 5], dtype=np.float32)
            return np.column_stack((1-hazard, hazard))

    model = Method("xgboost")
    model.estimator = Float32Estimator()
    state = np.ones((20, 5))
    ages = np.arange(20)*7
    full = model.distribution_from_features(state, ages, horizon=13)
    short = model.distribution_from_features(state, ages, horizon=4)
    np.testing.assert_allclose(full.sum(1), 1., atol=1e-12, rtol=0)
    np.testing.assert_allclose(short.sum(1), 1., atol=1e-12, rtol=0)
    np.testing.assert_array_equal(short[:, :4], full[:, :4])
    assert full.dtype == np.float64
