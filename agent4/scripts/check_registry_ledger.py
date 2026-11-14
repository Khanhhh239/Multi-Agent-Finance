"""Compare newly bound ledger metrics with independent MPX10 account totals."""

import argparse
import asyncio
from collections import defaultdict
from decimal import Decimal

from agent4.core.catalog import MetricCatalog
from agent4.core.config import AppConfig
from agent4.metric_selection.config import LLMSelectionConfig, MetricSelectionConfig, load_config
from agent4.pipeline import PipelineTrace, run_governed_pipeline
from scripts.check_mpx10 import SNAPSHOT
from scripts.check_warehouse import open_warehouse

FLOW_PERIOD = "2026-08"
SNAPSHOT_DATE = "2026-08-31"
CLAIMS = {"tenant_id": "minh-phat", "user_id": "metric-audit", "roles": ["finance_analyst"]}


def reference_totals(rows):
    """Apply financial signs and account families to grouped debit/credit balances."""
    debits = defaultdict(Decimal)
    credits = defaultdict(Decimal)
    for account, debit, credit in rows:
        debits[account] += debit
        credits[account] += credit

    def net(*prefixes):
        return sum(
            (
                debits[account] - credits[account]
                for account in debits
                if account.startswith(prefixes)
            ),
            Decimal(0),
        )

    gross = sum(
        (value for account, value in credits.items() if account.startswith("511")), Decimal(0)
    )
    return {
        "gross_revenue": gross,
        "revenue_deductions": gross + net("511", "521"),
        "goods_revenue": -net("5111"),
        "service_revenue": -net("5113"),
        "finance_income": -net("515"),
        "finance_cost": net("635"),
        "other_income": -net("711"),
        "other_expenses": net("811"),
        "term_deposits": net("128"),
        "inventory_value": net("151", "152", "153", "154", "155", "156", "157"),
        "tax_payable": -net("333"),
        "fixed_assets_net": net("211", "214"),
        "total_assets": net("1", "2"),
        "total_liabilities": -net("3"),
        "net_cash_flow": net("111", "112"),
        "taxable_income": -net("511", "521", "515", "711", "632", "641", "642", "635", "811"),
        "deductible_expenses": net("632", "641", "642", "635", "811"),
    }


def collect_expected(app: AppConfig, catalog: MetricCatalog):
    cases = []
    with open_warehouse(app.db_path) as db:
        info = dict(db.execute("SELECT key, value FROM company_info").fetchall())
        if any(info.get(key) != value for key, value in SNAPSHOT.items()):
            raise SystemExit("Ledger verification requires MPX10 v3")
        for view in ("mgmt", "tax"):
            for snapshot in (False, True):
                if snapshot:
                    predicate, period = "posting_date <= CAST(? AS DATE)", SNAPSHOT_DATE
                else:
                    predicate = "year_month = ? AND NOT is_closing AND source_module IS DISTINCT FROM 'OPENING'"
                    period = FLOW_PERIOD
                for branch_mode in (False,) if snapshot else (False, True):
                    group = (
                        "branch_code, account_code"
                        if branch_mode
                        else "NULL::VARCHAR, account_code"
                    )
                    rows = db.execute(
                        f"""SELECT {group}, SUM(debit_amount), SUM(credit_amount)
                            FROM v_{view} WHERE {predicate} GROUP BY 1, 2""",
                        [period],
                    ).fetchall()
                    accounts = defaultdict(list)
                    for branch, account, debit, credit in rows:
                        accounts[branch].append((account, debit, credit))
                    if not accounts or any(not value for value in accounts.values()):
                        raise SystemExit(f"Missing source rows in {view}/{period}")
                    expected = {
                        branch: reference_totals(totals) for branch, totals in accounts.items()
                    }
                    if not snapshot and not branch_mode and view == "mgmt":
                        expected[None]["depreciation_expense"] = db.execute(
                            """SELECT COALESCE(SUM(credit_amount), 0) FROM v_mgmt
                            WHERE year_month = ? AND NOT is_closing
                              AND source_module IS DISTINCT FROM 'OPENING'
                              AND source_document_type = 'DEPRECIATION'
                              AND starts_with(account_code, '214')""",
                            [period],
                        ).fetchone()[0]
                    for metric_id in next(iter(expected.values())):
                        capability = catalog.get_capability(metric_id)
                        if (capability["period_type"] == "snapshot") != snapshot:
                            continue
                        if view not in capability["supported_views"]:
                            continue
                        if branch_mode and "branch_code" not in capability["supported_dimensions"]:
                            continue
                        values = {branch: totals[metric_id] for branch, totals in expected.items()}
                        cases.append((metric_id, view, snapshot, branch_mode, values))
    return cases


async def check_cases(app: AppConfig, catalog: MetricCatalog, config_path: str | None) -> bool:
    config = (
        load_config(config_path)
        if config_path
        else MetricSelectionConfig(llm=LLMSelectionConfig(provider="mock"))
    )
    if config_path and config.llm.provider == "mock":
        raise SystemExit("The supplied configuration must use a real selector")
    cases = collect_expected(app, catalog)
    passed = 0
    tokens = 0
    usage_samples = 0
    for metric_id, view, snapshot, branch_mode, expected in cases:
        label = catalog.get(metric_id)["label_en"]
        when = "as of August 31, 2026" if snapshot else "for August 2026"
        grouping = " by branch" if branch_mode else ""
        trace = PipelineTrace()
        response = await run_governed_pipeline(
            {
                "api_version": "v1",
                "question": f"{label}{grouping} {when} in the {'tax' if view == 'tax' else 'management'} view?",
                "locale": "en-US",
            },
            CLAIMS,
            {
                "policy_version": "registry-ledger-audit",
                "allowed_views": ["mgmt", "tax"] if config_path else [view],
                "allowed_metrics": None if config_path else [metric_id],
            },
            warehouses={CLAIMS["tenant_id"]: app.db_path},
            app_config=app,
            catalog=catalog,
            selection_config=config,
            trace=trace,
        )
        if trace.selection.usage is not None:
            usage_samples += 1
            tokens += sum(trace.selection.usage.values())
        selected = (trace.selected_metrics or {}).get("metric_ids", [])
        actual = {}
        if (
            response["status"] == "ready"
            and trace.answer_validation_passed is True
            and selected == [metric_id]
        ):
            actual = {
                row.get("branch_code"): Decimal(row[metric_id]) for row in response["data"]["rows"]
            }
        if actual == expected:
            passed += 1
            print(f"{metric_id}/{view}/{branch_mode}: {len(expected)} result rows matched")
        else:
            error = (response["error"] or {}).get("code")
            print(f"{metric_id}/{view}/{branch_mode}: {response['status']}, {selected}, {error}")
    print(f"{passed}/{len(cases)} governed ledger cases matched independent MPX10 totals")
    if config_path:
        print(f"{tokens} tokens across {usage_samples}/{len(cases)} cases with usage")
    return passed == len(cases)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm-config", help="Run unrestricted catalog selection with a real model")
    args = parser.parse_args()
    if not asyncio.run(check_cases(AppConfig(), MetricCatalog(canonical=True), args.llm_config)):
        raise SystemExit(1)
