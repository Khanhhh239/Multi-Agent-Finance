import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest

from experiments.t1_competing_v6 import calibration
from experiments.t1_competing_v6.core import (
    CREDIT, PAID, WRITEOFF, cumulative_states, expand_weekly, label_events,
    observed_state, paid_quantiles, predict_hazards, state_at_day,
)
from experiments.t1_competing_v6.features import (
    ReceiptIndex, V6_FEATURES, V6SnapshotBuilder, model_view, validate_features,
)
from experiments.t1_competing_v6.metrics import paired_company_bootstrap, score
from experiments.t1_competing_v6.run import balanced_sample, firm_partition, write_bytes_once


def invoice_fixture():
    inv = pd.DataFrame({
        "invoice_id": ["past_paid", "past_writeoff", "current"],
        "firm_id": ["F0"] * 3, "customer_id": ["C0"] * 3,
        "issue_date": pd.to_datetime(["2020-01-01", "2020-02-01", "2020-05-01"]),
        "due_date": pd.to_datetime(["2020-01-31", "2020-03-02", "2020-06-01"]),
        "term_days": [30, 30, 31], "amount_gross": [100., 100., 100.],
        "paid_date_true": pd.to_datetime(["2020-02-03", None, "2020-08-03"]),
        "writeoff_date": pd.to_datetime([None, "2020-04-01", None]),
        "credit_note": [0., 0., 10.],
        "credit_note_date": pd.to_datetime([None, None, "2020-07-01"]),
        "closure_type": ["paid", "writeoff", "paid_after_credit_note"],
    })
    pay = pd.DataFrame({"invoice_id": ["past_paid", "current", "current"],
                        "pay_date_true": pd.to_datetime(["2020-02-03", "2020-05-15", "2020-08-03"]),
                        "amount": [100., 20., 70.]})
    return inv, pay


def matrix_frame(n=80):
    rng = np.random.default_rng(7)
    frame = pd.DataFrame(rng.normal(size=(n, len(V6_FEATURES))), columns=V6_FEATURES)
    frame["cutoff"] = pd.Timestamp("2024-01-01")
    frame["top1"] = np.nan
    frame["top2"] = np.nan
    frame["days_to_due"] = 30
    return frame


def test_asof_writeoff_and_receipt_features_do_not_read_future_outcomes():
    inv, pay = invoice_fixture()
    cutoff = pd.Timestamp("2020-06-01")
    first = model_view(V6SnapshotBuilder(inv, pay).snapshot(cutoff), cutoff)
    assert first.invoice_id.tolist() == ["current"]
    assert first.c_writeoff_n_asof.iloc[0] == 1
    assert first.i_payment_count_asof.iloc[0] == 1
    assert first.i_remaining_frac.iloc[0] == pytest.approx(.8)
    assert first.i_credit_frac_known.iloc[0] == 0
    changed = inv.copy()
    changed.loc[2, "paid_date_true"] = pd.Timestamp("2022-01-01")
    changed.loc[2, "writeoff_date"] = pd.Timestamp("2021-01-01")
    changed.loc[2, "credit_note"] = 90
    changed["is_bad_debt"] = True
    changed["writeoff_amount"] = 999999
    changed["n_payments"] = 100
    changed["remaining_amount"] = 0
    changed_pay = pd.concat([pay, pd.DataFrame({"invoice_id": ["current"], "pay_date_true": [pd.Timestamp("2021-01-01")], "amount": [999999.]})], ignore_index=True)
    second = model_view(V6SnapshotBuilder(changed, changed_pay).snapshot(cutoff), cutoff)
    pd.testing.assert_frame_equal(first[V6_FEATURES], second[V6_FEATURES])
    with pytest.raises(ValueError, match="Unregistered"):
        validate_features(["is_bad_debt"])


def test_credit_only_has_a_separate_terminal_label_and_admin_censoring():
    frame = pd.DataFrame({"cutoff": pd.to_datetime(["2024-01-01"] * 3),
                          "label_date": pd.to_datetime([None, "2024-02-01", None]),
                          "writeoff_date": pd.to_datetime([None, None, "2025-01-01"]),
                          "credit_note_date": pd.to_datetime(["2024-01-15", None, None]),
                          "closure_type": ["credit_note", "paid", "writeoff"]})
    labeled = label_events(frame, "2024-12-31")
    assert labeled.cause.tolist() == [CREDIT, PAID, 0]
    assert observed_state(labeled, 28).tolist() == [CREDIT, 0, 0]
    frame.loc[1, "writeoff_date"] = pd.Timestamp("2024-03-01")
    with pytest.raises(ValueError, match="Conflicting"):
        label_events(frame, "2024-12-31")


def test_risk_rows_stop_at_all_three_terminal_causes_and_skip_partial_week():
    frame = matrix_frame(4)
    frame["time_days"] = [8, 14, 21, 10]
    frame["obs_days"] = [30, 30, 30, 10]
    frame["cause"] = [PAID, WRITEOFF, CREDIT, 0]
    x, y = expand_weekly(frame, V6_FEATURES)
    assert len(x) == 8
    assert y.tolist() == [0, 0, 0, 0, PAID, WRITEOFF, 0, CREDIT]


def test_four_state_probability_mass_and_day_boundaries():
    hazards = np.tile([.7, .15, .1, .05], (2, 53, 1))
    states = cumulative_states(hazards)
    assert np.allclose(states.sum(axis=2), 1)
    assert np.all(np.diff(states[:, :, 1:], axis=1) >= 0)
    assert np.allclose(state_at_day(hazards, 0), [[1, 0, 0, 0]] * 2)
    assert np.allclose(state_at_day(hazards, 7), states[:, 0])
    day = state_at_day(hazards, 365)
    assert np.allclose(day.sum(axis=1), 1)
    assert np.all(day[:, PAID] >= states[:, 51, PAID])
    with pytest.raises(ValueError, match="horizon"):
        state_at_day(hazards, 372)


def test_unreached_quantiles_are_null_and_reached_quantile_inverts_cif():
    hazards = np.tile([.9, .09, .01, 0], (1, 53, 1))
    result = paid_quantiles(hazards)
    assert np.isnan(result["q90_days"][0])
    assert result["q90_status"][0] == "not_reached_by_365"
    days = result["q50_days"][0]
    assert 0 < days < 365
    left = state_at_day(hazards, int(days))[:, PAID][0]
    right = state_at_day(hazards, int(np.ceil(days)))[:, PAID][0]
    assert left <= .5 <= right


def test_cash_labels_exclude_payments_at_or_before_cutoff():
    _, payments = invoice_fixture()
    frame = pd.DataFrame({"invoice_id": ["current"], "cutoff": pd.to_datetime(["2020-05-15"])})
    cash = ReceiptIndex(payments).targets(frame, [28, 91], "2020-12-31")
    assert cash.tolist() == [[0, 70]]
    with pytest.raises(ValueError, match="follow-up"):
        ReceiptIndex(payments).targets(frame, [365], "2020-12-31")


def test_calibration_identity_and_protection_against_holdout_fit():
    hazards = np.tile([.8, .15, .05, 0], (4, 53, 1))
    identity = calibration.identity([0, 1, 2], [4, 13, 26, 53])
    assert np.allclose(calibration.transform(hazards, identity), hazards)
    frame = pd.DataFrame({"partition": ["test"] * 4})
    with pytest.raises(ValueError, match="dedicated source"):
        calibration.fit(frame, hazards, [0, 1, 2], {})
    with pytest.raises(ValueError, match="dedicated source"):
        calibration.select_on_source_firms(frame, hazards, identity, {})


def test_calibration_selection_can_reject_a_harmful_candidate():
    hazards = np.tile([.99, .009, .001, 0], (10, 53, 1))
    frame = pd.DataFrame({"partition": ["calibration_select"] * 10, "world": ["train_0"] * 10,
                          "obs_days": [400] * 10, "time_days": [400] * 10, "cause": [0] * 10})
    candidate = calibration.identity([0, 1, 2], [4, 13, 26, 53])
    candidate["selected"] = "candidate"
    candidate["parameters"] = [[0., -2., 2.]] * 4
    selected = calibration.select_on_source_firms(frame, hazards, candidate, {"calibration_short_paid_brier_tolerance": .02})
    assert selected["selected"] == "identity"


def test_multiclass_calibration_optimizer_reduces_held_source_objective():
    hazards = np.tile([.95, .04, .01, 0], (100, 53, 1))
    frame = pd.DataFrame({"partition": ["calibration_fit"] * 100,
                          "time_days": [7] * 60 + [400] * 40, "obs_days": [400] * 100,
                          "cause": [PAID] * 40 + [WRITEOFF] * 20 + [0] * 40})
    protocol = {"calibration_bands": [4, 13, 26, 53], "calibration_penalty": .002, "calibration_max_iterations": 40}
    result = calibration.fit(frame, hazards, [0, 1, 2], protocol)
    assert all(d["objective"] <= d["initial_objective"] + 1e-8 for d in result["fit_diagnostics"])
    calibrated = calibration.transform(hazards, result)
    assert np.allclose(calibrated.sum(axis=2), 1)
    assert np.all(calibrated[:, :, CREDIT] == 0)


def test_firm_partition_is_disjoint_and_sampling_does_not_use_outcomes():
    protocol = {"seed": 17, "calibration_firms_per_world": 8}
    split = firm_partition("world", [f"F{i:03}" for i in range(40)], protocol)
    assert len(split["fit"]) == 32
    assert not set(split["fit"]) & set(split["calibration_fit"] + split["calibration_select"])
    frame = pd.DataFrame({"firm_id": np.repeat(["A", "B"], 100), "row_id": np.arange(200), "cause": np.arange(200) % 3})
    sample = balanced_sample(frame, 20, 17)
    changed = frame.copy()
    changed["cause"] = 0
    assert sample.row_id.tolist() == balanced_sample(changed, 20, 17).row_id.tolist()
    assert sample.groupby("firm_id").size().tolist() == [10, 10]


def test_artifact_writer_refuses_to_overwrite_existing_different_content(tmp_path):
    path = tmp_path / "model.txt"
    write_bytes_once(path, b"locked model")
    write_bytes_once(path, b"locked model")
    with pytest.raises(ValueError, match="overwrite"):
        write_bytes_once(path, b"new model")
    assert path.read_bytes() == b"locked model"


def test_lightgbm_roundtrip_respects_active_causes_and_unknown_credit_class(tmp_path):
    frame = matrix_frame()
    matrix, _ = expand_weekly(frame.assign(time_days=7, obs_days=400, cause=np.arange(len(frame)) % 3), V6_FEATURES)
    y = np.arange(len(frame)) % 3
    model = lgb.train({"objective": "multiclass", "num_class": 3, "num_leaves": 3,
                       "min_data_in_leaf": 3, "num_threads": 1, "verbose": -1},
                      lgb.Dataset(matrix, y, feature_name=V6_FEATURES + ["k", "dtd_k", "due_in_k", "bd_in_k", "tet_in_k", "payrun_in_k", "promised_in_k"]), num_boost_round=3)
    path = tmp_path / "model.txt"
    model.save_model(str(path))
    restored = lgb.Booster(model_file=str(path))
    hazards = predict_hazards(restored, frame, V6_FEATURES, [0, 1, 2])
    assert hazards.shape == (len(frame), 53, 4)
    assert np.allclose(hazards.sum(axis=2), 1)
    assert np.all(hazards[:, :, CREDIT] == 0)


def test_metrics_reject_invalid_probabilities_and_cluster_whole_firms():
    frame = pd.DataFrame({"firm_id": ["A", "A", "B", "B"], "obs_days": [400] * 4,
                          "time_days": [10, 20, 400, 400], "cause": [PAID, WRITEOFF, 0, 0], "amount_open": [1., 100., 1., 100.]})
    p = np.tile([.5, .3, .2, 0], (4, 1))
    result = paired_company_bootstrap(frame, p, p, 28, replicates=20)
    assert result["firms"] == 2
    assert result["ci_low"] == result["ci_high"] == 0
    assert "amount_weighted_brier" in score(frame, p, 28)
    with pytest.raises(ValueError, match="Incoherent"):
        score(frame, p * 2, 28)
