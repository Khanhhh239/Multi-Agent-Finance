"""Exercise every canonical metric through the governed pipeline on a sample warehouse."""

import argparse
import asyncio
from collections import Counter
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from time import perf_counter

from agent4.core.catalog import MetricCatalog
from agent4.core.config import AppConfig
from agent4.engine.metrics import REGISTRY
from agent4.metric_selection.config import LLMSelectionConfig, MetricSelectionConfig, load_config
from agent4.pipeline import PipelineTrace, run_governed_pipeline
from scripts.check_warehouse import open_warehouse

CLAIMS = {
    "tenant_id": "minh-phat",
    "user_id": "metric-audit",
    "roles": ["finance_analyst", "payroll_viewer"],
}
VIEWS = ["mgmt", "tax"]


async def run(path: Path, config_path: str | None) -> bool:
    catalog = MetricCatalog(canonical=True)
    app = replace(AppConfig(), db_path=path, query_timeout_ms=15000)
    config = (
        load_config(config_path)
        if config_path
        else MetricSelectionConfig(llm=LLMSelectionConfig(provider="mock"))
    )
    if config_path and config.llm.provider == "mock":
        raise SystemExit("A real model is required with --llm-config")
    statuses: Counter[str] = Counter()
    latencies = []
    totals: dict[str, Decimal] = {}
    truncated = set()
    for metric_id in REGISTRY:
        metric = catalog.get(metric_id)
        view = metric["default_view"]
        date_phrase = (
            "as of August 31, 2026" if metric["period_type"] == "snapshot" else "for August 2026"
        )
        label = metric["label_en"] if config_path else f"metric_id: {metric_id}"
        question = f"{label} {date_phrase} in the {'tax' if view == 'tax' else 'management'} view?"
        trace = PipelineTrace()
        started = perf_counter()
        response = await run_governed_pipeline(
            {"api_version": "v1", "question": question, "locale": "en-US"},
            CLAIMS,
            {
                "policy_version": "catalog-execution-audit",
                "allowed_views": VIEWS,
                "allowed_metrics": None,
            },
            warehouses={CLAIMS["tenant_id"]: path},
            app_config=app,
            catalog=catalog,
            selection_config=config,
            trace=trace,
        )
        latencies.append(perf_counter() - started)
        selected = (trace.selected_metrics or {}).get("metric_ids")
        status = response["status"]
        execution = trace.execution or {}
        if selected != [metric_id]:
            status = "wrong_selection"
        elif status in ("ready", "no_data") and (
            not execution.get("succeeded") or trace.answer_validation_passed is not True
        ):
            status = "missing_execution"
        statuses[status] += 1
        if status == "ready":
            if response["data"]["truncated"]:
                truncated.add(metric_id)
            values = [row[metric_id] for row in response["data"]["rows"]]
            if all(value is not None for value in values):
                totals[metric_id] = sum(map(Decimal, values))
        print(metric_id, status, response["error"], flush=True)
    passed = statuses["ready"] + statuses["no_data"]
    print(f"{passed}/{len(REGISTRY)} executed and grounded: {dict(statuses)}")
    print(f"p95 {sorted(latencies)[int((len(latencies) - 1) * 0.95)]:.3f}s")
    if not config_path and passed == len(REGISTRY):
        assert totals["gross_revenue"] - totals["revenue_deductions"] == totals["net_revenue"]
        assert totals["cash_flow_breakdown"] == totals["net_cash_flow"]
        if {"ar_by_customer", "ar_by_salesperson"} & truncated:
            print("Receivables exceed the query cap. Comparing returned groups with source totals.")
            with open_warehouse(path) as db:
                for metric_id, group in (
                    ("ar_by_customer", "g.partner_code"),
                    ("ar_by_salesperson", "COALESCE(p.salesperson_code, 'unassigned')"),
                ):
                    expected = db.execute(
                        f"""SELECT SUM(balance) FROM (
                            SELECT SUM(g.debit_amount - g.credit_amount) AS balance
                            FROM v_mgmt g LEFT JOIN dim_partner p ON p.partner_code = g.partner_code
                                AND p.partner_type = 'CUSTOMER'
                            WHERE g.posting_date <= DATE '2026-08-31'
                                AND starts_with(g.account_code, '131')
                                AND g.partner_type = 'CUSTOMER' AND g.partner_code IS NOT NULL
                            GROUP BY {group} ORDER BY balance DESC LIMIT 1000
                        ) groups"""
                    ).fetchone()[0]
                    assert totals[metric_id] == expected, metric_id
        else:
            assert totals["ar_by_customer"] == totals["ar_by_salesperson"]
        print("3 cross-metric reconciliations passed")
    return passed == len(REGISTRY)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=AppConfig().db_path)
    parser.add_argument("--llm-config")
    args = parser.parse_args()
    raise SystemExit(0 if asyncio.run(run(args.db, args.llm_config)) else 1)
