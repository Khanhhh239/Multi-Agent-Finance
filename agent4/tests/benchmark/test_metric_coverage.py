from decimal import Decimal

import duckdb

from agent4.core.catalog import MetricCatalog, _amount
from agent4.engine.metrics import REGISTRY
from scripts.check_revenue_candidates import METRIC_IDS, AccountTotal, reconcile
from scripts.metric_coverage import REPORT, render_coverage


def test_committed_coverage_report_matches_registry_and_sources():
    assert REPORT.read_text(encoding="utf-8") == render_coverage()


def test_revenue_candidate_expressions_distinguish_credit_debit_and_521_reversal():
    # Hand-calculated fixture: gross 140, deductions 10 + (7 - 2),
    # goods 100 - 10 and services 40. The 632 line contributes to none of them.
    accounts = [
        AccountTotal("51111", Decimal(10), Decimal(100)),
        AccountTotal("5113", Decimal(0), Decimal(40)),
        AccountTotal("521", Decimal(7), Decimal(2)),
        AccountTotal("632", Decimal(70), Decimal(0)),
    ]
    expected = (Decimal(140), Decimal(15), Decimal(90), Decimal(40))
    assert tuple(reconcile(accounts)[metric_id] for metric_id in METRIC_IDS) == expected
    expressions = ", ".join(_amount(REGISTRY[metric_id].terms) for metric_id in METRIC_IDS)
    with duckdb.connect() as db:
        result = db.execute(
            f"""SELECT {expressions}
            FROM (VALUES (?, ?, ?), (?, ?, ?), (?, ?, ?), (?, ?, ?))
            AS ledger(account_code, debit_amount, credit_amount)""",
            [value for row in accounts for value in row],
        ).fetchone()
    assert result == expected


def test_ledger_bindings_cover_nonzero_amounts_for_accounts_absent_from_mpx10():
    catalog = MetricCatalog(canonical=True)
    metrics = ("term_deposits", "finance_income", "other_income")
    expressions = ", ".join(catalog.get(metric)["sql_expr"] for metric in metrics)
    with duckdb.connect() as db:
        row = db.execute(
            f"""SELECT {expressions}
            FROM (VALUES ('1281', 150, 20), ('515', 3, 40), ('711', 8, 60), ('511', 0, 500))
            AS ledger(account_code, debit_amount, credit_amount)"""
        ).fetchone()
    assert row == (Decimal("130.00"), Decimal("37.00"), Decimal("52.00"))
