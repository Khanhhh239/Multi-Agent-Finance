"""Independent accounting identities and temporal boundaries for T6 backtests."""
from copy import deepcopy
from datetime import date, timedelta

import numpy as np
import pytest
from threadpoolctl import threadpool_limits

from agent1.adaptive.data import as_of, validate_dataset
from experiments.t6_backtest.evaluation import measure, score, ar_score, event_score, knowledge_snapshot
from experiments.t6_backtest.stress import make_stress


@pytest.fixture
def cash_case():
    cutoff = "2026-01-31"
    first, end = "2026-02-07", "2026-05-02"
    bank = [dict(bank_id=k, account="Q", date=first, known_at=first, amount=a, direction=d, component=c)
            for k, a, d, c in (("AR", 100, "in", "other"), ("NEW", 20, "in", "other"),
                               ("SALE", 30, "in", "cash_sale"), ("FIX", 40, "out", "other"),
                               ("VAR", 10, "out", "variable_cost"), ("OTHERIN", 5, "in", "other"),
                               ("OTHEROUT", 15, "out", "other"))]
    data = dict(invoices=[dict(invoice_id="OLD", customer_id="C", issue_date="2026-01-01", due_date=first,
                               amount=100, known_at="2026-01-01"),
                          dict(invoice_id="NEW", customer_id="C", issue_date="2026-02-01", due_date=first,
                               amount=20, known_at="2026-02-01")],
                payments=[dict(payment_id=k, invoice_id=i, payment_date=first, known_at=first, amount=a, bank_id=k)
                          for k, i, a in (("AR", "OLD", 100), ("NEW", "NEW", 20))],
                bank=bank, actions=[],
                outflows=[dict(expense_id="FIXED", date=first, known_at=cutoff, amount=40, category="supplier_contract")],
                expense_payments=[dict(settlement_id="EP", expense_id="FIXED", bank_id="FIX", payment_date=first,
                                       known_at=first, amount=40)],
                statements=[dict(statement_id="PAST", account="Q", start_date="2026-01-01", end_date=cutoff,
                                  known_at=cutoff, opening_balance=100, closing_balance=100),
                            dict(statement_id="OUTCOME", account="Q", start_date="2026-02-01", end_date=end,
                                  known_at=end, opening_balance=100, closing_balance=190)])
    weeks, parts = [], []
    for i in range(13):
        weeks.append(dict(week=i+1, date=str(date.fromisoformat(cutoff)+timedelta(weeks=i+1)),
            cash_in=115 if i == 0 else 0, cash_out=43 if i == 0 else 0, balance=172,
            low=160, high=200, below_floor_probability=.7, outflow_status="scheduled"))
        parts.append(dict(ar_in=90 if i == 0 else 0, cash_sale_in=25 if i == 0 else 0,
                          variable_cost_topup=8 if i == 0 else 0, scheduled_out=35 if i == 0 else 0,
                          obligation_in=0))
    plan = dict(cutoff=cutoff, opening_balance=100, weeks=weeks, cash_floor=180,
        alerts=[dict(week=i+1) for i in range(13)], new_credit_included=False,
        cash_decomposition=dict(invoices=[dict(invoice_id="OLD")], weeks=parts,
                                outflows=[dict(week=1, amount=35, category="supplier_contract")]))
    validate_dataset(data)
    return data, plan, end


def test_bank_bridge_keeps_excluded_new_invoice_receipts_and_each_cost(cash_case):
    data, plan, end = cash_case
    rows = measure(data, plan, end, ["Q"])
    first = rows[0]
    assert first["actual_balance"] == 190
    assert first["actual_excluded_new_invoice_in"] == 20
    assert first["actual_scheduled_out"] == 40 and first["actual_variable_out"] == 10
    assert first["cumulative_scope_effect"] == -10
    assert first["cumulative_ar_error"] == -10
    assert first["cumulative_sale_effect"] == -5
    assert first["cumulative_variable_effect"] == 2
    assert first["cumulative_scheduled_effect"] == 5
    assert first["balance_error"] == -18
    assert all(abs(r["error_bridge_residual"]) < 1e-10 for r in rows)
    metrics = score(rows)
    assert metrics["mae_balance_vnd"] == 18
    assert metrics["coverage80"] == 1 and metrics["false_alert_weeks"] == 13
    assert metrics["recall_weekly"] is None and metrics["precision_weekly"] == 0


def test_scope_scoring_refuses_missing_bank_coverage_and_new_credit(cash_case):
    data, plan, end = cash_case
    data["statements"][-1]["end_date"] = "2026-05-01"
    with pytest.raises(ValueError, match="coverage"):
        measure(data, plan, end, ["Q"])
    data["statements"][-1]["end_date"] = end
    plan["new_credit_included"] = True
    with pytest.raises(ValueError, match="excluded"):
        measure(data, plan, end, ["Q"])


def test_ar_late_horizon_keeps_cash_received_in_first_four_weeks(cash_case):
    data, plan, end = cash_case
    rows = measure(data, plan, end, ["Q"])
    for r in rows:
        r.update(predicted_balance=190, p10=180, p90=200)
    result = ar_score(rows[4:])
    assert result["mae_balance_vnd"] == 10
    assert result["coverage80"] == 1


def test_weekly_and_context_alerts_do_not_multiply_marginal_probabilities(cash_case):
    data, plan, end = cash_case
    rows = measure(data, plan, end, ["Q"])
    for r in rows:
        r.update(dataset="original", profile="raw")
    result = event_score(rows)
    assert result["contexts"] == result["false_alert_contexts"] == 1
    assert result["recall_context"] is None and result["precision_context"] == 0
    rows[0]["below_floor_probability"] = 1.1
    with pytest.raises(ValueError, match="Invalid"):
        score(rows)


def test_stress_closes_future_issuance_without_mutating_original(cash_case):
    data, _, _ = cash_case
    # The original demo has no historical schedules at the selected origins.
    data["outflows"], data["expense_payments"] = [], []
    before = deepcopy(data)
    fixture, design = make_stress(data, "2026-01-31", "payment_pressure", ["Q"])
    assert data == before
    assert {r["invoice_id"] for r in fixture["invoices"]} == {"OLD"}
    assert {r["invoice_id"] for r in fixture["payments"]} == {"OLD"}
    assert all(r["known_at"] == "2026-01-31" for r in fixture["outflows"])
    assert design["confirmed_weeks"] == list(range(1, 14))
    assert fixture == make_stress(data, "2026-01-31", "payment_pressure", ["Q"])[0]


def test_schedule_gap_does_not_reveal_future_documents(cash_case):
    data, _, _ = cash_case
    data["outflows"], data["expense_payments"] = [], []
    fixture, design = make_stress(data, "2026-01-31", "schedule_gap", ["Q"])
    past = knowledge_snapshot(fixture, "2026-01-31")
    assert len(past["outflows"]) == 7
    assert not past["expense_payments"]
    assert design["confirmed_weeks"] == []


def test_knowledge_snapshot_physically_removes_flat_and_versioned_future_rows(cash_case):
    data, _, _ = cash_case
    data["record_history"] = {"invoices": deepcopy(data["invoices"])}
    past = knowledge_snapshot(data, "2026-01-31")
    assert {r["invoice_id"] for r in past["invoices"]} == {"OLD"}
    assert not past["payments"] and not past["bank"]
    assert len(past["statements"]) == 1
    assert len(past["record_history"]["invoices"]) == 1


def test_operating_opt_out_does_not_fit_new_invoice_branch(monkeypatch):
    from agent1.adaptive import new_credit, operating
    end = date(2026, 1, 31)
    data = dict(invoices=[], payments=[], bank=[], statements=[])
    for i in range(156):
        last = str(end-timedelta(weeks=155-i))
        first = str(date.fromisoformat(last)-timedelta(days=6))
        for label, amount, direction, component in (("S", 100, "in", "cash_sale"), ("V", 80, "out", "variable_cost")):
            data["bank"].append(dict(bank_id=f"{i}{label}", account="Q", date=last, known_at=last,
                                     amount=amount, direction=direction, component=component))
        data["statements"].append(dict(statement_id=str(i), account="Q", start_date=first, end_date=last,
            known_at=last, opening_balance=100+20*i, closing_balance=120+20*i))
    def forbidden(*args):
        pytest.fail("new-invoice learner must not run")
    monkeypatch.setattr(new_credit, "select_credit", forbidden)
    with threadpool_limits(limits=1):
        selected = operating.select_operating(data, str(end), include_new_credit=False)
    assert selected is not None and selected["credit"] is None
