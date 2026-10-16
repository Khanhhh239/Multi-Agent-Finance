import pandas as pd
import pytest

from agent2.inference_v4 import ReducedInput, snapshot_input, week_bounds


def test_iso_week_bounds_handle_year_boundary():
    start, end = week_bounds("2025-W01")
    assert start.isoformat() == "2024-12-30T00:00:00+07:00"
    assert (end - start).days == 7
    with pytest.raises(ValueError):
        week_bounds("2025-W54")


def test_raw_loader_ignores_truth_files_and_requires_reduced_mode(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    # If these are accidentally opened as CSV, they would fail decoding.
    for name in ("labels", "splits", "truth_cases", "features"):
        (source / f"{name}.csv").write_bytes(b"\xff\x00bad")
    pd.DataFrame([{"company_id": "a", "transaction_id": "t", "posted_at": "2025-01-01T12:00:00+07:00",
                   "created_at": "2025-01-01T10:00:00+07:00", "approved_at": "2025-01-01T11:00:00+07:00",
                   "txn_type": "cash_expense", "amount_vnd": "100"}]).to_csv(source / "transactions.csv", index=False)
    with pytest.raises(ReducedInput) as failure:
        snapshot_input(source, tmp_path / "snapshot", "a", "2025-W01")
    assert failure.value.report["rows"] == 1
    assert failure.value.report["missing_full_model_tables"]
    assert not (tmp_path / "snapshot").exists()
