"""Verify retrospective measurement and scope attribution independently of forecasting."""

from datetime import date, timedelta
from copy import deepcopy
import importlib.util
import json
import pickle
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/business/backtest_t6_baseline.py"
SPEC = importlib.util.spec_from_file_location("t6_baseline_runner", SCRIPT)
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


@pytest.fixture
def measured_case():
    cutoff, end = "2026-01-31", "2026-05-02"
    data = dict(
        invoices=[
            dict(invoice_id="OLD", customer_id="C", issue_date="2026-01-10", due_date="2026-01-20", known_at="2026-01-10", amount=100, currency="VND"),
            dict(invoice_id="NEW", customer_id="C", issue_date="2026-02-01", due_date="2026-02-02", known_at="2026-02-01", amount=20, currency="VND"),
        ],
        bank=[dict(bank_id=key, account="Q", date=day, known_at=day, amount=amount, direction=direction, component=component)
              for key, day, amount, direction, component in (
                  ("A", "2026-02-01", 100, "in", "other"),
                  ("N", "2026-02-02", 20, "in", "other"),
                  ("C", "2026-02-03", 10, "in", "cash_sale"),
                  ("O", "2026-02-04", 50, "out", "other"),
              )],
        payments=[dict(payment_id=key, invoice_id=iid, bank_id=bank, payment_date=day, known_at=day, amount=amount)
                  for key, iid, bank, day, amount in (("P1", "OLD", "A", "2026-02-01", 100), ("P2", "NEW", "N", "2026-02-02", 20))],
        statements=[
            dict(statement_id="S0", account="Q", start_date="2026-01-01", end_date=cutoff, known_at=cutoff, opening_balance=100, closing_balance=100),
            dict(statement_id="S1", account="Q", start_date="2026-02-01", end_date=end, known_at=end, opening_balance=100, closing_balance=180),
        ], outflows=[], actions=[],
    )
    plan = dict(cutoff=cutoff, opening_balance=100, cash_floor=90,
        operating_included=False, new_credit_included=False,
        cash_decomposition={"invoices": [{"invoice_id": "OLD"}]}, alerts=[],
        weeks=[dict(week=i, date=str(date.fromisoformat(cutoff) + timedelta(weeks=i)),
                    cash_in=90 if i == 1 else 0, cash_out=0, balance=190,
                    low=170, high=200, below_floor_probability=0, outflow_status="unknown")
               for i in range(1, 14)])
    return data, plan, end


def test_origins_reject_overlap_and_incomplete_followup():
    RUNNER.validate_origins(RUNNER.CUTOFFS, "2026-10-31")
    with pytest.raises(ValueError, match="overlap"):
        RUNNER.validate_origins(["2026-01-31", "2026-02-28"], "2026-10-31")
    with pytest.raises(ValueError, match="Immature"):
        RUNNER.validate_origins(["2026-08-31"], "2026-10-31")


def test_origin_balance_requires_a_statement_already_known(measured_case):
    data, plan, _ = measured_case
    past = RUNNER.knowledge_snapshot(data, plan["cutoff"])
    assert len(past["invoices"]) == 1 and not past["bank"] and not past["payments"]
    assert RUNNER.opening_balance(past, plan["cutoff"], ["Q"]) == 100
    data["statements"][0]["known_at"] = "2026-02-01"
    with pytest.raises(ValueError, match="certified"):
        RUNNER.opening_balance(data, plan["cutoff"], ["Q"])


def test_bank_error_is_partitioned_into_ar_and_missing_scope(measured_case):
    data, plan, end = measured_case
    rows = RUNNER.measured_rows(data, plan, end, ["Q"])
    first = rows[0]
    assert len(rows) == 13 and first["actual_balance"] == 180
    assert first["actual_opening_ar_in"] == 100
    assert first["actual_new_invoice_in"] == 20 and first["actual_cash_sales_in"] == 10
    assert first["actual_other_unmodelled_in"] == 0
    assert first["cumulative_ar_error"] == -10
    assert first["cumulative_scope_effect"] == 20
    assert first["balance_error"] == 10
    metrics = RUNNER.score_rows(rows)
    assert metrics["mae_balance_vnd"] == metrics["mae_cumulative_opening_ar_vnd"] == 10
    assert metrics["coverage80"] == 1 and metrics["brier_weekly_shortfall"] == 0
    assert metrics["recall_weekly"] is None and metrics["precision_weekly"] is None


def test_missing_last_day_is_not_scored_as_zero_cash(measured_case):
    data, plan, end = measured_case
    data["statements"][-1]["end_date"] = "2026-05-01"
    with pytest.raises(ValueError, match="coverage"):
        RUNNER.measured_rows(data, plan, end, ["Q"])


def test_false_alerts_are_counted_as_weeks_and_invalid_bounds_rejected(measured_case):
    data, plan, end = measured_case
    plan["alerts"] = [{"week": 2}]
    plan["weeks"][1]["below_floor_probability"] = 0.4
    rows = RUNNER.measured_rows(data, plan, end, ["Q"])
    metrics = RUNNER.score_rows(rows)
    assert metrics["false_alert_weeks"] == 1 and metrics["alert_weeks"] == 1
    assert metrics["precision_weekly"] == 0 and metrics["recall_weekly"] is None
    assert metrics["brier_weekly_shortfall"] == pytest.approx(0.16 / 13)
    rows[0]["p10"] = 201
    with pytest.raises(ValueError, match="Invalid forecast"):
        RUNNER.score_rows(rows)


def test_scope_bridge_refuses_an_operating_forecast(measured_case):
    data, plan, end = measured_case
    plan["operating_included"] = True
    with pytest.raises(ValueError, match="scope bridge"):
        RUNNER.measured_rows(data, plan, end, ["Q"])


def test_frozen_run_keeps_the_captured_code_after_live_edits(tmp_path, monkeypatch):
    project = tmp_path / "project"
    script = project / "scripts/business/backtest_t6_baseline.py"
    module = project / "agent1/adaptive/example.py"
    service = project / "agent1_service/__init__.py"
    calendar = project / "agent1/rules/rules_history.json"
    inputs = project / "pilot/demo"
    for path in (script, module, service):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("version = 1\n", encoding="utf-8")
    calendar.parent.mkdir(parents=True)
    calendar.write_text("[]", encoding="utf-8")
    inputs.mkdir(parents=True)
    for i, kind in enumerate(RUNNER.KINDS, 1):
        (inputs / f"{i:02}_{kind}.csv").write_text("header\n", encoding="utf-8")
    (inputs / "manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(RUNNER, "ROOT", project)
    monkeypatch.setattr(RUNNER, "__file__", str(script))
    output = tmp_path / "measurement"
    frozen_script, frozen_inputs = RUNNER.freeze_runtime(output, inputs)
    module.write_text("version = 2\n", encoding="utf-8")
    assert frozen_script.read_text(encoding="utf-8") == "version = 1\n"
    assert (output / "runtime_source/agent1/adaptive/example.py").read_text(encoding="utf-8") == "version = 1\n"
    assert (frozen_inputs / "manifest.json").read_text(encoding="utf-8") == "{}"
    assert (output / "runtime_source/agent1/rules/rules_history.json").read_text(encoding="utf-8") == "[]"


def test_trained_t1_bundle_reaches_both_forecasts(measured_case, monkeypatch):
    data, _, _ = measured_case
    cutoff = "2026-01-31"
    past = RUNNER.knowledge_snapshot(data, cutoff)
    bundle = {"asof": cutoff}
    calls = []

    def fake_train(given, asof, progress):
        assert given is past and asof == cutoff
        return bundle

    def fake_forecast(given, asof, balance, **kwargs):
        assert kwargs["bundle"] is bundle
        calls.append(given)
        return {"mode": "company_trained"}

    monkeypatch.setattr(RUNNER, "train", fake_train)
    monkeypatch.setattr(RUNNER, "forecast", fake_forecast)
    trained = RUNNER.fit_origin_t1(past, cutoff, "workspace", lambda message: None)
    RUNNER.forecast_pair(data, past, cutoff, 100, trained, "workspace", 90)
    assert calls == [data, past]


def test_workspace_mode_cannot_silently_use_fallback(measured_case):
    data, _, _ = measured_case
    with pytest.raises(ValueError, match="requires a trained bundle"):
        RUNNER.forecast_pair(data, data, "2026-01-31", 100, None, "workspace", 90)


def test_t1_trained_after_origin_is_rejected(monkeypatch):
    monkeypatch.setattr(RUNNER, "train", lambda *args, **kwargs: {"asof": "2026-02-01"})
    with pytest.raises(ValueError, match="historical cutoff"):
        RUNNER.fit_origin_t1({}, "2026-01-31", "workspace", lambda message: None)


def test_cash_check_tolerates_roundoff_but_rejects_one_dong_and_probability_leaks(measured_case):
    _, plan, _ = measured_case
    plan["cash_decomposition"]["invoices"][0]["expected_by_week"] = [90] + [0] * 12
    plan["collections"] = [dict(invoice_id="OLD", payment_probability_4w=0.5)]
    replay = deepcopy(plan)
    replay["weeks"][0]["balance"] += 1e-7
    replay["collections"][0]["payment_probability_4w"] += 1e-15
    replay["unrelated_shap_hash"] = "presentation-roundoff"
    assert RUNNER.cash_equivalent(plan, replay)
    replay["weeks"][0]["balance"] += 1
    assert not RUNNER.cash_equivalent(plan, replay)
    replay = deepcopy(plan)
    replay["collections"][0]["payment_probability_4w"] += 0.001
    assert not RUNNER.cash_equivalent(plan, replay)


def test_t1_checkpoint_requires_identical_data_code_and_training_settings(tmp_path, monkeypatch):
    cutoff, data = "2026-01-31", {"invoices": []}
    path = tmp_path / "models" / f"{cutoff}.pkl"
    path.parent.mkdir()
    bundle = dict(asof=cutoff, dataset_hash=RUNNER.fingerprint(data), code_hash="same-code", dependencies={})
    path.write_bytes(pickle.dumps(bundle))
    metadata = dict(training_config=RUNNER.training_config(), artifact_sha256=RUNNER.sha256(path))
    path.with_suffix(".json").write_text(json.dumps(metadata), encoding="utf-8")
    monkeypatch.setattr(RUNNER, "training_code_hash", lambda: "same-code")
    assert RUNNER.cached_t1(tmp_path, cutoff, data) == bundle
    assert RUNNER.cached_t1(tmp_path, cutoff, {"invoices": ["changed"]}) is None
    monkeypatch.setattr(RUNNER, "training_code_hash", lambda: "changed-code")
    assert RUNNER.cached_t1(tmp_path, cutoff, data) is None
