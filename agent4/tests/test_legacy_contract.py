"""v0 contract tests (ported from the original test_engine.py) — run against the toy v0 generator.

The tests intentionally exercise the public contract described in
``plan_test.md``.  They use a temporary DuckDB database so that the suite is
isolated from a developer's local database.

Expected engine API::

    from engine import ExecutionEngine
    engine = ExecutionEngine(database_path)
    engine.get_metric(metric_id, start_date="YYYY-MM-DD", end_date="YYYY-MM-DD")

The engine may expose ``Engine`` or ``FinancialEngine`` instead; the fixture
accepts those names as a small convenience while the implementation is being
built.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root: the original v0 generator
from generate_data import main as generate_data_main  # noqa: E402


START = "2026-05-01"
END = "2026-05-31"


def _generate_database(path: Path) -> None:
    """Generate the six-month fixture used by the test suite."""
    # generate_data.main is CLI-shaped, so invoke it with a temporary argv.
    import sys

    import generate_data as gd

    class _FrozenDate(date):
        """The v0 generator builds the six months ending at date.today(); the
        expected values below were written in May 2026 (window Dec–May), so freeze 'today'."""

        @classmethod
        def today(cls):
            return cls(2026, 5, 15)

    original_argv, original_date = sys.argv, gd.date
    try:
        sys.argv = ["generate_data.py", "--output", str(path), "--months", "6"]
        gd.date = _FrozenDate
        generate_data_main()
    finally:
        sys.argv, gd.date = original_argv, original_date


@pytest.fixture()
def execution_engine(tmp_path: Path):
    """Return an engine connected to a fresh generated DuckDB database."""
    database_path = tmp_path / "fixture.duckdb"
    _generate_database(database_path)

    import agent4.engine.engine as engine_module

    engine_class = next(
        (
            getattr(engine_module, name, None)
            for name in ("ExecutionEngine", "FinancialEngine", "Engine")
            if getattr(engine_module, name, None) is not None
        ),
        None,
    )
    if engine_class is None:
        pytest.fail(
            "engine.py must expose ExecutionEngine, FinancialEngine, or Engine"
        )
    return engine_class(database_path)


def metric(execution_engine, metric_id: str, *, start: str = START, end: str = END):
    return execution_engine.get_metric(metric_id, start_date=start, end_date=end)


def assert_common_schema(result: dict, metric_id: str, period_type: str) -> None:
    assert isinstance(result, dict)
    assert result["metric_id"] == metric_id
    assert isinstance(result["metric_name"], str)
    assert isinstance(result["value"], (int, float, Decimal))
    assert result["unit"] == "VND"
    assert result["period"]["type"] == period_type
    assert result["period"]["start_date"] == START
    assert result["period"]["end_date"] == END

    audit = result["audit_trail"]
    assert isinstance(audit["accounts_involved"], list)
    assert isinstance(audit["entry_count"], int)
    assert audit["entry_count"] >= 0
    assert audit["as_of_date"] == END


def test_net_revenue_is_flow_and_auditable(execution_engine):
    result = metric(execution_engine, "net_revenue")

    assert_common_schema(result, "net_revenue", "flow")
    assert result["value"] == pytest.approx(129_600_000.0)  # 120m × season 1.08 (May = 6th month); the original 110.4m was inconsistent with the 720m AR assertion
    assert result["value"] > 0
    assert "511" in result["audit_trail"]["accounts_involved"]
    assert "521" in result["audit_trail"]["accounts_involved"]
    assert result["audit_trail"]["entry_count"] > 0


def test_cogs_is_debit_632_flow(execution_engine):
    result = metric(execution_engine, "cogs")

    assert_common_schema(result, "cogs", "flow")
    assert result["value"] == pytest.approx(77_760_000.0)  # 129.6m × 60%
    assert result["value"] > 0
    assert result["audit_trail"]["accounts_involved"] == ["632"]


def test_gross_profit_equals_net_revenue_minus_cogs(execution_engine):
    revenue = metric(execution_engine, "net_revenue")
    cogs = metric(execution_engine, "cogs")
    gross_profit = metric(execution_engine, "gross_profit")

    assert_common_schema(gross_profit, "gross_profit", "flow")
    assert gross_profit["value"] == pytest.approx(
        revenue["value"] - cogs["value"], abs=0.01
    )


def test_salary_and_operating_expenses(execution_engine):
    salary = metric(execution_engine, "salary_expense")
    operating = metric(execution_engine, "operating_expenses")

    assert_common_schema(salary, "salary_expense", "flow")
    assert_common_schema(operating, "operating_expenses", "flow")
    assert salary["value"] == pytest.approx(18_000_000.0)
    # metrics-v0.md defines operating_expenses = 641 + 642, i.e. salary (18m, Nợ 642/Có 334)
    # + management expense (12m).  The original assertion (12m) contradicted that spec.
    assert operating["value"] == pytest.approx(30_000_000.0)
    assert "642" in salary["audit_trail"]["accounts_involved"]
    assert "642" in operating["audit_trail"]["accounts_involved"]


def test_cash_balance_is_snapshot_not_period_flow(execution_engine):
    result = metric(execution_engine, "cash_and_equivalents")

    assert_common_schema(result, "cash_and_equivalents", "snapshot")
    # Fixture contains six monthly 12m credits to 112 and no cash receipts.
    assert result["value"] == pytest.approx(-72_000_000.0)
    assert set(result["audit_trail"]["accounts_involved"]) == {"111", "112"}
    assert result["audit_trail"]["as_of_date"] == END


def test_net_cash_flow_is_flow(execution_engine):
    result = metric(execution_engine, "net_cash_flow")

    assert_common_schema(result, "net_cash_flow", "flow")
    # Only the May 112 management-expense posting is in this period.
    assert result["value"] == pytest.approx(-12_000_000.0)


def test_ar_balance_is_snapshot(execution_engine):
    result = metric(execution_engine, "ar_balance")

    assert_common_schema(result, "ar_balance", "snapshot")
    assert result["value"] == pytest.approx(720_000_000.0)
    assert result["audit_trail"]["accounts_involved"] == ["131"]


def test_ar_by_customer_reconciles_to_ar_balance(execution_engine):
    total = metric(execution_engine, "ar_balance")
    by_customer = metric(execution_engine, "ar_by_customer")

    assert by_customer["metric_id"] == "ar_by_customer"
    assert isinstance(by_customer["value"], dict)
    assert sum(by_customer["value"].values()) == pytest.approx(total["value"])
    assert set(by_customer["value"]) == {"C001", "C002"}
    assert by_customer["value"]["C001"] == pytest.approx(720_000_000.0)
    assert by_customer["value"]["C002"] == pytest.approx(0.0)


def test_ap_balance_is_safe_when_fixture_has_no_payables(execution_engine):
    result = metric(execution_engine, "ap_balance")

    assert_common_schema(result, "ap_balance", "snapshot")
    assert result["value"] == pytest.approx(0.0)
    assert result["audit_trail"]["entry_count"] == 0
    assert result["audit_trail"]["accounts_involved"] == ["331"]


def test_unknown_metric_raises_helpful_error(execution_engine):
    import agent4.engine.engine as engine

    error_type = getattr(engine, "MetricNotFoundError", KeyError)
    with pytest.raises(error_type) as exc_info:
        metric(execution_engine, "metric_khong_ton_tai")

    message = str(exc_info.value)
    assert "metric_khong_ton_tai" in message
    assert "net_revenue" in message


def test_reversed_date_range_raises_error(execution_engine):
    import agent4.engine.engine as engine

    error_type = getattr(engine, "InvalidDateRangeError", ValueError)
    with pytest.raises(error_type):
        metric(execution_engine, "net_revenue", start=END, end=START)


def test_empty_future_period_returns_zero_without_crashing(execution_engine):
    result = metric(
        execution_engine,
        "net_revenue",
        start="2030-01-01",
        end="2030-01-31",
    )

    assert result["value"] == pytest.approx(0.0)
    assert result["audit_trail"]["entry_count"] == 0
    assert result["period"] == {
        "type": "flow",
        "start_date": "2030-01-01",
        "end_date": "2030-01-31",
    }

