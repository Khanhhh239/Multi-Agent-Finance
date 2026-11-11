"""Exercise the core catalog's trusted SQL against the configured DuckDB."""

from collections.abc import Collection
from pathlib import Path
from time import perf_counter

import duckdb

from agent4.core.catalog import MetricCatalog
from agent4.core.config import AppConfig


def main() -> None:
    db_path = AppConfig().db_path
    with open_warehouse(db_path) as db:
        info = dict(db.execute("SELECT key, value FROM company_info").fetchall())
        start = perf_counter()
        print(
            f"{db_path} | version {info['data_version']} | as of {info['as_of_date']}", flush=True
        )
        results = catalog_results(db, info)
        for key, value in results.items():
            print(f"{key} = {value}")
        print(f"{len(results)} metric/view pairs executed in {perf_counter() - start:.2f}s")


def open_warehouse(db_path: Path) -> duckdb.DuckDBPyConnection:
    if not db_path.is_file():
        raise SystemExit(f"Warehouse not found: {db_path}. See the setup steps in README.md.")

    return duckdb.connect(
        str(db_path),
        read_only=True,
        config={"enable_external_access": "false", "threads": 2, "memory_limit": "1GB"},
    )


def catalog_results(
    db: duckdb.DuckDBPyConnection,
    info: dict[str, str],
    *,
    metric_ids: Collection[str] | None = None,
) -> dict[str, str | None]:
    results = {}
    for metric in MetricCatalog(canonical=True).list_metrics(
        approved_only=True, allowed_metrics=metric_ids
    ):
        if not metric["verified_handler"]:
            continue
        for view in metric["supported_views"]:
            if metric["base_relation"] == "budget":
                relation = "budget"
                period = "printf('%04d-%02d', year_no, month_no) = ?"
                params = [info["last_closed_month"]]
            elif metric["period_type"] == "snapshot":
                relation = f"v_{view}"
                period = "posting_date <= CAST(? AS DATE)"
                params = [info["as_of_date"]]
            else:
                relation = f"v_{view}"
                period = (
                    "year_month = ? AND NOT is_closing AND source_module IS DISTINCT FROM 'OPENING'"
                )
                params = [info["last_closed_month"]]

            rows, result = db.execute(
                f"SELECT count(*), {metric['sql_expr']} FROM {relation} WHERE {period}",
                params,
            ).fetchone()
            key = f"{metric['metric_id']} [{relation}]"
            if rows == 0:
                raise SystemExit(f"No source rows for {key}")
            results[key] = None if result is None else str(result)
    return results


if __name__ == "__main__":
    main()
