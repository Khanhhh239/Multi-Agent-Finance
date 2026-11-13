"""Check the MPX10 v3 warehouse against its frozen numerical references."""

import argparse
import json
from decimal import Decimal
from pathlib import Path

import duckdb

from agent4.core.config import AppConfig
from scripts.check_warehouse import catalog_results, open_warehouse

EVAL_DIR = Path(__file__).resolve().parents[1] / "data/eval"
REFERENCE = EVAL_DIR / "mpx10-v3-reference.json"
SOURCE_CASES = EVAL_DIR / "contract_benchmark_questions.v1.jsonl"
SNAPSHOT = {
    "profile_id": "minh_phat_enterprise_x10",
    "data_version": "3.0.0",
    "seed": "20261108",
    "as_of_date": "2026-10-14",
    "last_closed_month": "2026-08",
}
GL_COUNT = 19_784_697

# These questions contain a v2.1 entity, event or zero-revenue assumption,
# or name a narrower list of branches/departments than their SQL selects.
V21_ONLY = {
    "BM-041",
    "BM-046",
    "BM-066",
    "BM-067",
    "BM-068",
    "BM-069",
    "BM-070",
    "BM-071",
    "BM-072",
    "BM-073",
    "BM-105",
    "BM-107",
    "BM-109",
    "BM-119",
    "BM-120",
}

# Fixed checks from the MPX10 generator. Database descriptions and stored SQL are data.
SCENARIOS = {
    "GT-DUPLICATE": (1, "SELECT count(*) FROM ap_payment WHERE journal_id = 'DUP-PAY'"),
    "GT-INJECTION": (
        1,
        (
            "SELECT count(*) FROM gl_journal WHERE journal_id = 'SALE-17' "
            "AND description LIKE '%UNTRUSTED%'"
        ),
    ),
    "GT-OFFHOURS": (
        1,
        "SELECT count(*) FROM gl_journal WHERE journal_id = 'SPLIT-1' AND hour(created_at) = 23",
    ),
    "GT-SPLIT": (3, "SELECT count(*) FROM gl_journal WHERE journal_id LIKE 'SPLIT-%'"),
    "GT-UNBALANCED": (
        1000,
        "SELECT sum(debit_amount-credit_amount) FROM gl_entry WHERE journal_id = 'TEST-UNBALANCED'",
    ),
}


def golden_rows(db: duckdb.DuckDBPyConnection) -> dict:
    results = {}
    with SOURCE_CASES.open(encoding="utf-8") as source:
        for line in source:
            case = json.loads(line)
            case_id = case["benchmark_id"]
            if not case["golden_sql"] or case_id in V21_ONLY:
                continue
            query = db.execute(case["golden_sql"], case["golden_params"])
            columns = [column[0] for column in query.description]
            results[case_id] = [
                dict(zip(columns, (None if value is None else str(value) for value in row)))
                for row in query.fetchall()
            ]
    return results


def check_ground_truth(db: duckdb.DuckDBPyConnection, path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"Ground truth not found: {path}. See README.md.")
    records = json.loads(path.read_text(encoding="utf-8"))
    recorded = {row["id"]: row for row in records}
    if recorded.keys() != SCENARIOS.keys() or len(records) != len(SCENARIOS):
        raise SystemExit("MPX10 ground truth scenario IDs differ")
    for case_id, (expected, sql) in SCENARIOS.items():
        row = recorded[case_id]
        actual = db.execute(sql).fetchone()[0]
        if actual != expected or (
            row["expected"] != expected
            or not row["passed"]
            or Decimal(str(row["actual"])) != expected
        ):
            raise SystemExit(f"{case_id}: expected {expected}, got {actual}, sidecar {row}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-reference", type=Path, help="Author a candidate at a new path")
    args = parser.parse_args()
    expected = None if args.write_reference else json.loads(REFERENCE.read_text(encoding="utf-8"))
    # The frozen reference covers the metric IDs shipped with MPX10 v3.
    metric_ids = (
        {key.rsplit(" [", 1)[0] for key in expected["catalog_baseline"]} if expected else None
    )
    config = AppConfig()
    with open_warehouse(config.db_path) as db:
        info = dict(db.execute("SELECT key, value FROM company_info").fetchall())
        identity = {key: info.get(key) for key in SNAPSHOT}
        count = db.execute("SELECT count(*) FROM gl_entry").fetchone()[0]
        if identity != SNAPSHOT or count != GL_COUNT:
            raise SystemExit(
                f"Expected the full MPX10 v3 snapshot, got {identity}, {count} GL rows"
            )
        check_ground_truth(db, config.ground_truth_path)
        results = {
            "snapshot": {**identity, "gl_rows": count},
            "catalog_baseline": catalog_results(db, info, metric_ids=metric_ids),
            "golden_rows": golden_rows(db),
        }

    if args.write_reference:
        with args.write_reference.open("x", encoding="utf-8") as output:
            json.dump(results, output, ensure_ascii=False, indent=2)
            output.write("\n")
        return

    if expected["snapshot"] != results["snapshot"]:
        raise SystemExit("Reference snapshot does not match the database")
    for name in ("catalog_baseline", "golden_rows"):
        actual, frozen = results[name], expected[name]
        mismatches = sorted(
            (actual.keys() ^ frozen.keys())
            | {key for key in actual.keys() & frozen.keys() if actual[key] != frozen[key]}
        )
        if mismatches:
            raise SystemExit(f"{name} differs for: {', '.join(mismatches)}")
    print(
        f"MPX10 {SNAPSHOT['data_version']}: {len(results['catalog_baseline'])} catalog results, "
        f"{len(results['golden_rows'])} golden cases and {len(SCENARIOS)} scenarios matched"
    )


if __name__ == "__main__":
    main()
