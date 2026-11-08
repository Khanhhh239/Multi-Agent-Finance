import numpy as np
import pandas as pd
import pytest

from experiments.t1_v6_practical.ledger import PracticalFeatureBuilder, BEHAVIOR_FEATURES
from experiments.t1_v6_practical.model import ARMS, expand_weekly, week_matrix
from experiments.t1_competing_v6.core import expand_weekly as original_expand
from experiments.t1_competing_v6.features import V6_FEATURES


def fixture():
    inv = pd.DataFrame({"firm_id": ["f"] * 3, "customer_id": ["c"] * 3,
                        "invoice_id": ["old", "partial", "new"],
                        "issue_date": ["2024-01-01", "2024-01-01", "2024-03-10"],
                        "known_at": ["2024-01-02", "2024-01-02", "2024-03-11"],
                        "due_date": ["2024-01-31", "2024-02-01", "2024-04-10"], "amount_gross": [100., 200., 100.]})
    ent = pd.DataFrame({"firm_id": ["f", "f"], "invoice_id": ["old", "partial"],
                        "entry_id": ["r1", "r2"], "event_date": ["2024-03-01", "2024-03-05"],
                        "known_at": ["2024-03-02", "2024-03-06"], "entry_type": ["receipt", "receipt"], "amount": [100., 50.]})
    dates = pd.date_range("2024-01-01", "2024-06-01")
    cov = pd.DataFrame({"firm_id": "f", "history_start": pd.Timestamp("2024-01-01"),
                        "through_date": dates, "known_at": dates + pd.Timedelta(days=1)})
    keys = pd.DataFrame({"firm_id": ["f"], "customer_id": ["c"], "invoice_id": ["partial"], "cutoff": ["2024-03-20"]})
    return inv, ent, cov, keys


def build(inv, ent, cov):
    return PracticalFeatureBuilder(inv, ent, cov, authorized_firms={"f"})


def test_values_use_observed_receipts_partial_balance_and_reporting_lag():
    inv, ent, cov, keys = fixture()
    row = build(inv, ent, cov).transform(keys).iloc[0]
    assert row.b_c_delay_mean_28d == 31  # recognized March 2 vs Jan 31
    assert row.b_c_settled_n_28d == 1
    assert row.b_i_receipt_frac_28d == .25
    assert row.b_c_partial_share == .6  # remaining 150 / remaining total 250
    assert row.b_c_overdue_share == .6
    assert row.b_c_days_since_receipt == 14
    assert row.b_ledger_report_age_days == 1
    assert row.b_c_collection_ratio_28d == pytest.approx(150 / 400)
    assert row.b_ledger_missing == 0


def test_late_allocation_is_not_visible_on_its_backdated_event_date():
    inv, ent, cov, keys = fixture()
    later = ent.iloc[[1]].assign(entry_id="late", event_date="2024-02-01", known_at="2024-04-01", amount=150.)
    baseline = build(inv, ent, cov).transform(keys)
    changed = build(inv, pd.concat([ent, later], ignore_index=True), cov).transform(keys)
    pd.testing.assert_frame_equal(baseline, changed)


def test_newly_learned_backdated_receipt_does_not_rewrite_starting_balance():
    inv, ent, cov, keys = fixture()
    late = ent.iloc[[1]].assign(entry_id="late", event_date="2024-02-01", known_at="2024-03-15", amount=50.)
    row = build(inv, pd.concat([ent, late], ignore_index=True), cov).transform(keys).iloc[0]
    assert row.b_c_collection_ratio_28d == pytest.approx(200 / 400)


def test_stale_complete_export_does_not_imply_current_zero_receipts():
    inv, ent, cov, keys = fixture()
    stale = cov[cov.through_date.le("2024-02-29")]
    row = build(inv, ent, stale).transform(keys).iloc[0]
    assert row.b_ledger_missing == 1
    assert np.isnan(row.b_i_receipt_frac_28d)


def test_future_receipt_and_future_invoice_do_not_change_past_features():
    inv, ent, cov, keys = fixture()
    future = inv.iloc[[2]].assign(invoice_id="future", issue_date="2024-05-01", known_at="2024-05-02")
    receipt = ent.iloc[[0]].assign(entry_id="future", invoice_id="future", event_date="2024-05-03", known_at="2024-05-04")
    baseline = build(inv, ent, cov).transform(keys)
    changed = build(pd.concat([inv, future], ignore_index=True), pd.concat([ent, receipt], ignore_index=True), cov).transform(keys)
    pd.testing.assert_frame_equal(baseline, changed)


def test_reversal_is_append_only_and_can_reopen_ledger_balance():
    inv, ent, cov, keys = fixture()
    reversal = ent.iloc[[0]].assign(entry_id="reverse", event_date="2024-03-10", known_at="2024-03-11", amount=-100.)
    row = build(inv, pd.concat([ent, reversal], ignore_index=True), cov).transform(keys).iloc[0]
    assert row.b_c_settled_n_28d == 0
    assert np.isnan(row.b_c_delay_mean_28d)
    assert row.b_c_collection_ratio_28d == pytest.approx(50 / 400)


def test_missing_coverage_is_missing_not_zero_payment():
    inv, ent, cov, keys = fixture()
    row = build(inv, ent, cov.iloc[:0]).transform(keys).iloc[0]
    assert row.b_ledger_missing == 1
    assert row[BEHAVIOR_FEATURES[:-1]].isna().all()


def test_short_history_cannot_create_fictitious_previous_window():
    inv, ent, cov, keys = fixture()
    cov["history_start"] = pd.Timestamp("2024-03-01")
    cov = cov[cov.through_date.ge("2024-03-01")]
    # Imported invoices from before history_start are not guaranteed covered.
    inv.loc[:, "issue_date"] = "2024-03-01"
    inv.loc[:, "known_at"] = "2024-03-02"
    row = build(inv, ent, cov).transform(keys).iloc[0]
    assert row.b_ledger_missing == 0
    assert np.isnan(row.b_c_delay_delta_28d)
    assert np.isnan(row.b_c_collection_ratio_28d)


def test_customer_with_uncovered_older_invoices_is_missing_even_for_new_invoice():
    inv, ent, cov, keys = fixture()
    cov = cov[cov.through_date.ge("2024-03-01")].copy()
    cov["history_start"] = pd.Timestamp("2024-03-01")
    keys["invoice_id"] = "new"
    row = build(inv, ent, cov).transform(keys).iloc[0]
    assert row.b_ledger_missing == 1
    assert np.isnan(row.b_c_overdue_share)


def test_missing_due_date_is_not_assumed_to_mean_not_overdue():
    inv, ent, cov, keys = fixture()
    inv.loc[inv.invoice_id.eq("partial"), "due_date"] = None
    row = build(inv, ent, cov).transform(keys).iloc[0]
    assert row.b_ledger_missing == 0
    assert np.isnan(row.b_c_overdue_share)
    assert np.isnan(row.b_c_overdue_share_delta_28d)
    assert row.b_c_partial_share == .6


def test_same_customer_and_invoice_identifiers_at_other_tenant_do_not_join():
    inv, ent, cov, keys = fixture()
    inv2, ent2, cov2 = inv.assign(firm_id="other"), ent.assign(firm_id="other", amount=999.), cov.assign(firm_id="other")
    baseline = build(inv, ent, cov).transform(keys)
    builder = PracticalFeatureBuilder(pd.concat([inv, inv2]), pd.concat([ent, ent2]), pd.concat([cov, cov2]), authorized_firms={"f", "other"})
    pd.testing.assert_frame_equal(baseline, builder.transform(keys))
    with pytest.raises(ValueError, match="authorized"):
        build(pd.concat([inv, inv2]), ent, cov)
    with pytest.raises(ValueError, match="authorized"):
        build(inv, ent, cov).transform(keys.assign(firm_id="other"))


@pytest.mark.parametrize("kind", ["true_link", "missing_known_at", "duplicate", "early_known"])
def test_unregistered_or_invalid_events_fail_closed(kind):
    inv, ent, cov, _ = fixture()
    if kind == "true_link":
        ent["paid_date_true"] = "2024-01-01"
    elif kind == "missing_known_at":
        ent["known_at"] = None
    elif kind == "duplicate":
        ent = pd.concat([ent, ent.iloc[[0]]])
    else:
        ent["known_at"] = "2020-01-01"
    with pytest.raises(ValueError):
        build(inv, ent, cov)


def test_original_risk_rows_and_matrix_are_identical_and_extras_stay_frozen():
    n = 4
    frame = pd.DataFrame(0., index=range(n), columns=ARMS["both"])
    frame["cutoff"] = pd.Timestamp("2024-01-01")
    frame["top1"], frame["top2"] = np.nan, np.nan
    frame["days_to_due"] = 30
    frame["time_days"] = [7, 14, 371, 10]
    frame["obs_days"] = [371, 371, 371, 10]
    frame["cause"] = [1, 2, 0, 0]
    frame["b_c_collection_ratio_28d"] = [.1, .2, .3, .4]
    a, ay = original_expand(frame, V6_FEATURES)
    b, by = expand_weekly(frame, ARMS["v6"])
    np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(ay, by)
    _, ey = expand_weekly(frame, ARMS["both"])
    np.testing.assert_array_equal(ay, ey)
    column = ARMS["behavior"].index("b_c_collection_ratio_28d")
    np.testing.assert_array_equal(week_matrix(frame, 1, ARMS["behavior"])[:, column], week_matrix(frame, 53, ARMS["behavior"])[:, column])
    with pytest.raises(ValueError):
        week_matrix(frame, 1, V6_FEATURES + ["shock_truth"])


def test_source_selection_rejects_fresh_and_requires_short_paid_safety():
    from experiments.t1_v6_practical.run import choose
    rows = []
    for name in ("v6", "industry", "behavior"):
        for day in (28, 91, 365):
            rows.append(dict(split="source", world="v4_shortpay_4shock_20261028_train_000", model=name,
                             day=day, four_state_brier=.2 if name == "v6" else .18,
                             writeoff_brier=.1 if name == "v6" else .08,
                             paid_brier=.1 if name != "behavior" else .11))
    assert choose(rows)["selected"] == "industry"
    rows[0]["split"] = "fresh"
    with pytest.raises(ValueError, match="source"):
        choose(rows)


def test_sidecar_measurement_design_has_no_macro_and_is_locked_before_models():
    from experiments.t1_v6_practical.design import protocol
    p = protocol()
    assert p["fresh_generation"] == "only after final source selection freeze"
    assert len(p["fresh_worlds"]) == 4
    seeds = [w["seed"] for w in p["augment_worlds"] + p["fresh_worlds"]]
    assert len(seeds) == len(set(seeds))
    assert all(w["start"] >= "2019-01-01" for w in p["augment_worlds"] + p["fresh_worlds"])
    assert len(ARMS["industry"]) - len(V6_FEATURES) == 14
    assert not any("macro_credit" in c for columns in ARMS.values() for c in columns)


def test_extended_model_prediction_has_four_coherent_states():
    import lightgbm as lgb
    from experiments.t1_v6_practical.model import predict_hazards
    from agent1.models import t1
    frame = pd.DataFrame(0., index=range(12), columns=ARMS["behavior"])
    frame["cutoff"] = pd.Timestamp("2024-01-01")
    frame["days_to_due"] = 30
    model = lgb.train(dict(objective="multiclass", num_class=3, min_data_in_leaf=1, verbosity=-1, num_threads=1),
                      lgb.Dataset(week_matrix(frame, 1, ARMS["behavior"]), label=np.tile([0, 1, 2], 4),
                                  feature_name=ARMS["behavior"] + t1.WEEK_FEATS), num_boost_round=2)
    h = predict_hazards(model, frame, ARMS["behavior"], [0, 1, 2])
    assert h.shape == (12, 53, 4)
    np.testing.assert_allclose(h.sum(axis=2), 1., atol=1e-6)
    assert not h[:, :, 3].any()


def test_cached_score_precision_and_integrity_are_preserved(tmp_path):
    from experiments.t1_v6_practical.run import save_frame, csv_once, json_once, digest, evaluate
    path = tmp_path / "predictions/source/tiny.parquet"
    save_frame(path, pd.DataFrame({"x": [1.]}))
    scores = path.parent / "tiny_scores.csv"
    rows = [{"number": .08874324783576451, "n": 17}]
    csv_once(scores, rows)
    json_once(scores.with_suffix(".sha256.json"), {"sha256": digest(scores)})
    _, actual = evaluate(tmp_path, "tiny", "v6", None, None, None, "source")
    assert actual == rows
    scores.write_text("number,n\n0.5,17\n", encoding="utf-8")
    with pytest.raises(ValueError, match="scores changed"):
        evaluate(tmp_path, "tiny", "v6", None, None, None, "source")
