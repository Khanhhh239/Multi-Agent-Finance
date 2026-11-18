"""Automated accounting & double-entry reconciliation tests for dual views (v_mgmt / v_tax).

Verifies that ``agent4.datagen.build`` produces a ``v_tax`` view that simultaneously satisfies:
1. Strict double-entry balance (``SUM(debit_amount) == SUM(credit_amount)`` per journal; 0 false-positive
   unbalanced journals on clean books).
2. Statutory Vietnamese CIT B4 & VAT adjustments (TT133/200 & Tờ khai 03/TNDN Chỉ tiêu B4):
   non-deductible expenses (6xx/811) and non-creditable input VAT (1331) are reclassified out of
   tax-deductible P&L / VAT accounts into equity adjustment account 4219, while whole-journal
   ``mgmt_only`` internal accruals (all legs ``tax_deductible = FALSE``) are excluded intact.
3. Real Cash/Bank (111, 112), AR (131), AP (331), Loan (341), and Tax Payable (333) balances on
   ``v_tax`` match ``v_mgmt`` without phantom missing legs.
4. Balance Sheet accounting equation (``Assets == Liabilities + Equity``) and closed-period P&L
   zeroing hold to exact 0.00 VND across closed and open periods on both ``v_mgmt`` and ``v_tax``.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from agent4.datagen import company as C
from agent4.datagen.build import SCHEMA_SQL, VIEWS_SQL, build


@pytest.fixture(scope="module")
def built_warehouse(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    out_dir = tmp_path_factory.mktemp("v_tax_warehouse")
    db_path = out_dir / "cfo_warehouse.duckdb"
    stats = build(
        db_path,
        seed=20251,
        as_of=date(2026, 10, 14),
        last_closed="2026-08",
        quiet=True,
    )
    return db_path, stats


@pytest.fixture()
def warehouse_conn(built_warehouse: tuple[Path, dict]):
    db_path, _ = built_warehouse
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        yield con
    finally:
        con.close()


def _unbalanced_journal_id(con: duckdb.DuckDBPyConnection) -> str:
    payload_str = con.execute(
        "SELECT payload FROM ground_truth WHERE id = 'A4_UNBALANCED_JOURNAL'"
    ).fetchone()[0]
    return json.loads(payload_str)["journal_id"]


def test_schema_parity_and_account_catalog(
    warehouse_conn: duckdb.DuckDBPyConnection, built_warehouse: tuple[Path, dict]
) -> None:
    _, stats = built_warehouse
    cols_gl = warehouse_conn.execute("DESCRIBE v_gl").fetchall()
    cols_mgmt = warehouse_conn.execute("DESCRIBE v_mgmt").fetchall()
    cols_tax = warehouse_conn.execute("DESCRIBE v_tax").fetchall()
    assert [c[0] for c in cols_gl] == [c[0] for c in cols_mgmt] == [c[0] for c in cols_tax]
    assert len(cols_tax) == 36

    b4_acc = warehouse_conn.execute(
        "SELECT account_key, account_code, account_type, normal_balance, parent_account_code "
        "FROM dim_account WHERE account_code = '4219'"
    ).fetchone()
    assert b4_acc == (len(C.ACCOUNTS), "4219", "EQUITY", "C", "421")

    assert stats["unbalanced_journals"] == 1
    assert stats["unbalanced_journals_v_mgmt"] == 1
    assert stats["unbalanced_journals_v_tax"] == 1


def test_double_entry_balance_on_v_mgmt_and_v_tax(
    warehouse_conn: duckdb.DuckDBPyConnection,
) -> None:
    seeded_dq_jid = _unbalanced_journal_id(warehouse_conn)

    for view in ("v_mgmt", "v_tax"):
        clean_unbalanced = warehouse_conn.execute(
            f"""
            SELECT journal_id, SUM(debit_amount) AS dr, SUM(credit_amount) AS cr
            FROM {view}
            WHERE journal_id <> ?
            GROUP BY journal_id
            HAVING SUM(debit_amount) <> SUM(credit_amount)
            """,
            [seeded_dq_jid],
        ).fetchall()
        assert clean_unbalanced == [], (
            f"Unexpected unbalanced journals in {view}: {clean_unbalanced}"
        )

        dq_gap = warehouse_conn.execute(
            f"SELECT SUM(debit_amount - credit_amount) FROM {view} WHERE journal_id = ?",
            [seeded_dq_jid],
        ).fetchone()[0]
        assert dq_gap == Decimal("500000.00")

        bad_signs = warehouse_conn.execute(
            f"""
            SELECT COUNT(*) FROM {view}
            WHERE debit_amount < 0 OR credit_amount < 0
               OR NOT ((debit_amount > 0 AND credit_amount = 0)
                    OR (debit_amount = 0 AND credit_amount > 0))
               OR net_debit <> debit_amount - credit_amount
            """
        ).fetchone()[0]
        assert bad_signs == 0


@pytest.mark.parametrize(
    ("start_date", "end_date"),
    [
        ("2025-01-01", "2025-12-31"),
        ("2026-01-01", "2026-10-14"),
        ("2026-08-01", "2026-08-31"),
        ("2026-09-01", "2026-09-30"),
    ],
)
def test_statutory_b4_pnl_reconciliation_total_and_dimensional(
    warehouse_conn: duckdb.DuckDBPyConnection, start_date: str, end_date: str
) -> None:
    pbt_sql = """
        SELECT COALESCE(SUM(
            CASE
                WHEN regexp_matches(account_code, '^(511|515|711)') THEN credit_amount - debit_amount
                WHEN regexp_matches(account_code, '^(521|632|635|641|642|811)') THEN -(debit_amount - credit_amount)
                ELSE 0
            END
        ), 0)
        FROM {view}
        WHERE posting_date BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
          AND NOT is_closing AND source_module IS DISTINCT FROM 'OPENING'
    """
    pbt_mgmt = warehouse_conn.execute(
        pbt_sql.format(view="v_mgmt"), [start_date, end_date]
    ).fetchone()[0]
    pbt_tax = warehouse_conn.execute(
        pbt_sql.format(view="v_tax"), [start_date, end_date]
    ).fetchone()[0]

    b4_gap = warehouse_conn.execute(
        """
        SELECT COALESCE(SUM(net_debit), 0)
        FROM v_mgmt
        WHERE posting_date BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
          AND NOT is_closing AND source_module IS DISTINCT FROM 'OPENING'
          AND tax_deductible IS FALSE
          AND left(account_code, 3) IN ('632', '635', '641', '642', '811')
        """,
        [start_date, end_date],
    ).fetchone()[0]

    assert b4_gap > Decimal("0.00")
    assert pbt_tax > pbt_mgmt
    assert pbt_tax - pbt_mgmt == b4_gap

    # Branch-level and department-level B4 reconciliation
    for dim in ("branch_code", "department_code"):
        by_mgmt = dict(
            warehouse_conn.execute(
                f"""
                SELECT {dim}, COALESCE(SUM(
                    CASE
                        WHEN regexp_matches(account_code, '^(511|515|711)') THEN credit_amount - debit_amount
                        WHEN regexp_matches(account_code, '^(521|632|635|641|642|811)') THEN -(debit_amount - credit_amount)
                        ELSE 0
                    END
                ), 0)
                FROM v_mgmt
                WHERE posting_date BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
                  AND NOT is_closing AND source_module IS DISTINCT FROM 'OPENING'
                GROUP BY 1
                """,
                [start_date, end_date],
            ).fetchall()
        )
        by_tax = dict(
            warehouse_conn.execute(
                f"""
                SELECT {dim}, COALESCE(SUM(
                    CASE
                        WHEN regexp_matches(account_code, '^(511|515|711)') THEN credit_amount - debit_amount
                        WHEN regexp_matches(account_code, '^(521|632|635|641|642|811)') THEN -(debit_amount - credit_amount)
                        ELSE 0
                    END
                ), 0)
                FROM v_tax
                WHERE posting_date BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
                  AND NOT is_closing AND source_module IS DISTINCT FROM 'OPENING'
                GROUP BY 1
                """,
                [start_date, end_date],
            ).fetchall()
        )
        by_gap = dict(
            warehouse_conn.execute(
                f"""
                SELECT {dim}, COALESCE(SUM(net_debit), 0)
                FROM v_mgmt
                WHERE posting_date BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
                  AND NOT is_closing AND source_module IS DISTINCT FROM 'OPENING'
                  AND tax_deductible IS FALSE
                  AND left(account_code, 3) IN ('632', '635', '641', '642', '811')
                GROUP BY 1
                """,
                [start_date, end_date],
            ).fetchall()
        )
        assert set(by_mgmt.keys()) == set(by_tax.keys())
        for key, mgmt_val in by_mgmt.items():
            assert by_tax[key] - mgmt_val == by_gap.get(key, Decimal("0.00"))


def test_non_creditable_vat_disallowed_while_preserving_journal_balance(
    warehouse_conn: duckdb.DuckDBPyConnection,
) -> None:
    # September 2026 contains A5_THRESHOLD_HUGGING (cash >= threshold, non-deductible 6421 + 1331)
    vat_sql = """
        SELECT COALESCE(SUM(CASE WHEN starts_with(account_code, '33311') THEN -net_debit ELSE 0 END), 0) AS out_vat,
               COALESCE(SUM(CASE WHEN starts_with(account_code, '1331') THEN net_debit ELSE 0 END), 0) AS in_vat
        FROM {view}
        WHERE posting_date BETWEEN DATE '2026-09-01' AND DATE '2026-09-30'
          AND NOT is_closing AND source_module IS DISTINCT FROM 'OPENING'
          AND COALESCE(source_document_type, '') NOT IN ('VAT_OFFSET', 'VAT_PAYMENT', 'TAX_PAYMENT')
    """
    out_mgmt, in_mgmt = warehouse_conn.execute(vat_sql.format(view="v_mgmt")).fetchone()
    out_tax, in_tax = warehouse_conn.execute(vat_sql.format(view="v_tax")).fetchone()

    disallowed_vat = warehouse_conn.execute(
        """
        SELECT COALESCE(SUM(net_debit), 0)
        FROM v_mgmt
        WHERE posting_date BETWEEN DATE '2026-09-01' AND DATE '2026-09-30'
          AND NOT is_closing AND source_module IS DISTINCT FROM 'OPENING'
          AND tax_deductible IS FALSE AND starts_with(account_code, '1331')
        """
    ).fetchone()[0]

    assert disallowed_vat > Decimal("0.00")
    assert out_tax == out_mgmt
    assert in_mgmt - in_tax == disallowed_vat


@pytest.mark.parametrize(
    "as_of_date",
    ["2025-12-31", "2026-06-30", "2026-08-31", "2026-09-30", "2026-10-14"],
)
def test_cash_ar_ap_loan_and_balance_sheet_equation(
    warehouse_conn: duckdb.DuckDBPyConnection, as_of_date: str
) -> None:
    seeded_dq_jid = _unbalanced_journal_id(warehouse_conn)

    # Real Cash/Bank (111, 112), AR (131), AP (331), Loan (341), Tax Payable (333) are identical
    for prefix in ("111", "112", "131", "331", "333", "341"):
        bal_mgmt = warehouse_conn.execute(
            "SELECT COALESCE(SUM(net_debit), 0) FROM v_mgmt WHERE posting_date <= CAST(? AS DATE) AND starts_with(account_code, ?)",
            [as_of_date, prefix],
        ).fetchone()[0]
        bal_tax = warehouse_conn.execute(
            "SELECT COALESCE(SUM(net_debit), 0) FROM v_tax WHERE posting_date <= CAST(? AS DATE) AND starts_with(account_code, ?)",
            [as_of_date, prefix],
        ).fetchone()[0]
        assert bal_tax == bal_mgmt, f"Mismatch on prefix {prefix} as of {as_of_date}"

    # Accounting Equation: Assets (1..2) == Liabilities (3) + Equity (4..9) on clean books
    for view in ("v_mgmt", "v_tax"):
        assets, liabilities, equity_all = warehouse_conn.execute(
            f"""
            SELECT COALESCE(SUM(CASE WHEN regexp_matches(account_code, '^[12]') THEN net_debit ELSE 0 END), 0) AS assets,
                   COALESCE(SUM(CASE WHEN starts_with(account_code, '3') THEN -net_debit ELSE 0 END), 0) AS liabilities,
                   COALESCE(SUM(CASE WHEN regexp_matches(account_code, '^[4-9]') THEN -net_debit ELSE 0 END), 0) AS equity
            FROM {view}
            WHERE posting_date <= CAST(? AS DATE) AND journal_id <> ?
            """,
            [as_of_date, seeded_dq_jid],
        ).fetchone()
        assert assets == liabilities + equity_all, (
            f"Balance sheet mismatch in {view} on {as_of_date}: "
            f"assets={assets}, liabilities={liabilities}, equity={equity_all}"
        )


def test_closed_periods_zero_out_pnl_and_b4_bridge_on_v_tax(
    warehouse_conn: duckdb.DuckDBPyConnection,
) -> None:
    unclosed_pnl_tax = warehouse_conn.execute(
        """
        SELECT year_month, account_code, SUM(net_debit) AS bal
        FROM v_tax
        WHERE year_month <= '2026-08'
          AND regexp_matches(account_code, '^[5-9]')
        GROUP BY 1, 2
        HAVING SUM(net_debit) <> 0
        """
    ).fetchall()
    assert unclosed_pnl_tax == []

    closed_b4_bridge_bal = warehouse_conn.execute(
        """
        SELECT COALESCE(SUM(net_debit), 0)
        FROM v_tax
        WHERE year_month <= '2026-08' AND account_code = '4219'
        """
    ).fetchone()[0]
    assert closed_b4_bridge_bal == Decimal("0.00")


def test_benchmark_tax_view_golden_values_preserved(
    warehouse_conn: duckdb.DuckDBPyConnection,
) -> None:
    # BM-061 vs BM-062 (2026-08 operating_expense)
    opex_mgmt = warehouse_conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN account_code LIKE '642%' THEN debit_amount - credit_amount ELSE 0 END), 0) "
        "FROM v_mgmt WHERE posting_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31' AND NOT is_closing"
    ).fetchone()[0]
    opex_tax = warehouse_conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN account_code LIKE '642%' THEN debit_amount - credit_amount ELSE 0 END), 0) "
        "FROM v_tax WHERE posting_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31' AND NOT is_closing"
    ).fetchone()[0]
    assert opex_mgmt == Decimal("3028615501.00")
    assert opex_tax == Decimal("2928697501.00")

    # BM-063 (2026-08 net_profit on v_tax)
    net_profit_tax = warehouse_conn.execute(
        """
        SELECT COALESCE(SUM(
            CASE
                WHEN account_type = 'REVENUE' THEN credit_amount - debit_amount
                WHEN account_type = 'EXPENSE' THEN -(debit_amount - credit_amount)
                ELSE 0
            END
        ), 0)
        FROM v_tax
        WHERE posting_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31' AND NOT is_closing
        """
    ).fetchone()[0]
    assert net_profit_tax == Decimal("198911518.00")

    # BM-065 (2026-08 operating_expense grouped by cost_category on v_tax: exact 18 rows, no phantom categories)
    bm065_rows = warehouse_conn.execute(
        """
        SELECT cost_category,
               COALESCE(SUM(CASE WHEN account_code LIKE '642%' THEN debit_amount - credit_amount ELSE 0 END), 0)
        FROM v_tax
        WHERE posting_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31' AND NOT is_closing
        GROUP BY cost_category
        ORDER BY cost_category ASC
        """
    ).fetchall()
    assert len(bm065_rows) == 18

    # BM-074 (Q3 2026 operating_expense on v_tax) & BM-075 (2026-08 branch HN net_profit on v_tax)
    bm074 = warehouse_conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN account_code LIKE '642%' THEN debit_amount - credit_amount ELSE 0 END), 0) "
        "FROM v_tax WHERE posting_date BETWEEN DATE '2026-07-01' AND DATE '2026-09-30' AND NOT is_closing"
    ).fetchone()[0]
    assert bm074 == Decimal("9930329982.00")

    bm075 = warehouse_conn.execute(
        """
        SELECT COALESCE(SUM(
            CASE
                WHEN account_type = 'REVENUE' THEN credit_amount - debit_amount
                WHEN account_type = 'EXPENSE' THEN -(debit_amount - credit_amount)
                ELSE 0
            END
        ), 0)
        FROM v_tax
        WHERE posting_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31'
          AND NOT is_closing AND branch_code = 'HN'
        """
    ).fetchone()[0]
    assert bm075 == Decimal("130124564.00")


def test_core_catalog_sql_executes_on_both_views(
    warehouse_conn: duckdb.DuckDBPyConnection,
) -> None:
    from scripts.check_warehouse import catalog_results

    info = dict(warehouse_conn.execute("SELECT key, value FROM company_info").fetchall())
    results = catalog_results(warehouse_conn, info)
    assert Decimal(results["profit_before_tax [v_tax]"]) > Decimal(
        results["profit_before_tax [v_mgmt]"]
    )
    assert Decimal(results["operating_expenses [v_tax]"]) < Decimal(
        results["operating_expenses [v_mgmt]"]
    )
    assert Decimal(results["net_revenue [v_tax]"]) == Decimal(results["net_revenue [v_mgmt]"])
    assert Decimal(results["tax_payable [v_tax]"]) == Decimal(results["tax_payable [v_mgmt]"])


def _fmt_cell(v: object) -> str | None:
    if v is None:
        return None
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def test_all_v1_benchmark_golden_queries_match_exact_rows(
    warehouse_conn: duckdb.DuckDBPyConnection,
) -> None:
    bench_file = (
        Path(__file__).resolve().parents[1] / "data/eval/contract_benchmark_questions.v1.jsonl"
    )
    with bench_file.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            case = json.loads(line)
            if not case.get("golden_sql"):
                continue
            cur = warehouse_conn.execute(case["golden_sql"], case["golden_params"])
            cols = [d[0] for d in cur.description]
            actual = [
                dict(zip(cols, (_fmt_cell(v) for v in row), strict=True)) for row in cur.fetchall()
            ]
            assert actual == case["golden_rows"], f"Mismatch on {case['benchmark_id']}"


def test_governed_catalog_execution_across_all_registry_metrics(
    built_warehouse: tuple[Path, dict],
) -> None:
    from scripts.check_catalog_execution import run as run_catalog_execution

    db_path, _ = built_warehouse
    assert asyncio.run(run_catalog_execution(db_path, None)) is True


def test_whole_journal_mgmt_only_and_b4_synthetic_edge_cases() -> None:
    with duckdb.connect() as con:
        con.execute(SCHEMA_SQL)
        for k, (code, name, typ, nb, parent) in enumerate(C.ACCOUNTS, start=1):
            has_child = any(a[4] == code for a in C.ACCOUNTS)
            con.execute(
                "INSERT INTO dim_account VALUES (?, ?, ?, ?, ?, ?, ?, ?, DATE '2020-01-01', NULL)",
                [k, code, name, typ, nb, parent, 1 if parent is None else 2, not has_child],
            )
        acc_key = dict(con.execute("SELECT account_code, account_key FROM dim_account").fetchall())
        con.execute(
            """
            INSERT INTO dim_period VALUES
                (20260815, DATE '2026-08-15', 15, 6, FALSE, 33, 8, 3, 2026, '2026-08', DATE '2026-08-01', DATE '2026-08-31', TRUE),
                (20260831, DATE '2026-08-31', 31, 1, TRUE,  36, 8, 3, 2026, '2026-08', DATE '2026-08-01', DATE '2026-08-31', TRUE),
                (20260910, DATE '2026-09-10', 10, 4, TRUE,  37, 9, 3, 2026, '2026-09', DATE '2026-09-01', DATE '2026-09-30', FALSE)
            """
        )
        entries = [
            # 1. Opening capital: Dr 11211 = 100M, Cr 4111 = 100M
            (
                1,
                "J-OPEN",
                1,
                "2026-08-15",
                20260815,
                acc_key["11211"],
                100_000_000,
                0,
                "OPENING",
                False,
                True,
                None,
            ),
            (
                2,
                "J-OPEN",
                2,
                "2026-08-15",
                20260815,
                acc_key["4111"],
                0,
                100_000_000,
                "OPENING",
                False,
                True,
                None,
            ),
            # 2. Revenue in closed month: Dr 11211 = 50M, Cr 5111 = 50M
            (
                3,
                "J-REV",
                1,
                "2026-08-15",
                20260815,
                acc_key["11211"],
                50_000_000,
                0,
                "AR",
                False,
                True,
                None,
            ),
            (
                4,
                "J-REV",
                2,
                "2026-08-15",
                20260815,
                acc_key["5111"],
                0,
                50_000_000,
                "AR",
                False,
                True,
                None,
            ),
            # 3. Statutory CIT B4 cash expense in closed month: Dr 6422 (False) = 10M, Cr 11211 (True) = 10M
            (
                5,
                "J-B4-CLOSED",
                1,
                "2026-08-15",
                20260815,
                acc_key["6422"],
                10_000_000,
                0,
                "GL",
                False,
                False,
                "NO_VALID_INVOICE",
            ),
            (
                6,
                "J-B4-CLOSED",
                2,
                "2026-08-15",
                20260815,
                acc_key["11211"],
                0,
                10_000_000,
                "GL",
                False,
                True,
                None,
            ),
            # 4. Pure mgmt_only internal accrual in closed month (BOTH legs tax_deductible = False): Dr 6421 = 7M, Cr 335 = 7M
            (
                7,
                "J-MGMT-ONLY",
                1,
                "2026-08-15",
                20260815,
                acc_key["6421"],
                7_000_000,
                0,
                "GL",
                False,
                False,
                "MGMT_ACCRUAL",
            ),
            (
                8,
                "J-MGMT-ONLY",
                2,
                "2026-08-15",
                20260815,
                acc_key["335"],
                0,
                7_000_000,
                "GL",
                False,
                False,
                "MGMT_ACCRUAL",
            ),
            # 5. Management closing for 2026-08 (net profit = 50M - 10M - 7M = 33M)
            (
                9,
                "J-KC",
                1,
                "2026-08-31",
                20260831,
                acc_key["5111"],
                50_000_000,
                0,
                "CLOSING",
                True,
                True,
                None,
            ),
            (
                10,
                "J-KC",
                2,
                "2026-08-31",
                20260831,
                acc_key["6422"],
                0,
                10_000_000,
                "CLOSING",
                True,
                True,
                None,
            ),
            (
                11,
                "J-KC",
                3,
                "2026-08-31",
                20260831,
                acc_key["6421"],
                0,
                7_000_000,
                "CLOSING",
                True,
                True,
                None,
            ),
            (
                12,
                "J-KC",
                4,
                "2026-08-31",
                20260831,
                acc_key["4212"],
                0,
                33_000_000,
                "CLOSING",
                True,
                True,
                None,
            ),
            # 6. Open-month statutory B4 expense: Dr 811 (False) = 4M, Cr 11211 (True) = 4M
            (
                13,
                "J-B4-OPEN",
                1,
                "2026-09-10",
                20260910,
                acc_key["811"],
                4_000_000,
                0,
                "GL",
                False,
                False,
                "ADMIN_PENALTY",
            ),
            (
                14,
                "J-B4-OPEN",
                2,
                "2026-09-10",
                20260910,
                acc_key["11211"],
                0,
                4_000_000,
                "GL",
                False,
                True,
                None,
            ),
        ]
        con.executemany(
            """
            INSERT INTO gl_entry (
                entry_id, journal_id, entry_no, posting_date, period_key, account_key,
                debit_amount, credit_amount, source_module, is_closing, tax_deductible, tax_note,
                created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'test', TIMESTAMP '2026-08-31 18:00:00')
            """,
            entries,
        )
        con.execute(VIEWS_SQL)

        # 0 unbalanced journals on both views
        for view in ("v_mgmt", "v_tax"):
            unbal = con.execute(
                f"SELECT COUNT(*) FROM (SELECT journal_id FROM {view} GROUP BY 1 HAVING SUM(debit_amount) <> SUM(credit_amount))"
            ).fetchone()[0]
            assert unbal == 0

        # Whole-journal mgmt_only is excluded from v_tax, so 335 liability is 0 on v_tax (vs 7M on v_mgmt)
        liab_335_mgmt = con.execute(
            "SELECT COALESCE(SUM(-net_debit), 0) FROM v_mgmt WHERE account_code = '335'"
        ).fetchone()[0]
        liab_335_tax = con.execute(
            "SELECT COALESCE(SUM(-net_debit), 0) FROM v_tax WHERE account_code = '335'"
        ).fetchone()[0]
        assert liab_335_mgmt == Decimal("7000000.00")
        assert liab_335_tax == Decimal("0.00")

        # Real bank cash (11211) is 100M + 50M - 10M - 4M = 136M on BOTH views
        for view in ("v_mgmt", "v_tax"):
            bank_bal = con.execute(
                f"SELECT SUM(net_debit) FROM {view} WHERE account_code = '11211'"
            ).fetchone()[0]
            assert bank_bal == Decimal("136000000.00")

        # Closed-month P&L accounts in 2026-08 all net to 0 on v_tax
        unclosed = con.execute(
            "SELECT account_code, SUM(net_debit) FROM v_tax WHERE year_month = '2026-08' AND regexp_matches(account_code, '^[5-9]') GROUP BY 1 HAVING SUM(net_debit) <> 0"
        ).fetchall()
        assert unclosed == []

        # Accounting Equation Assets == Liabilities + Equity holds on both 2026-08-31 and 2026-09-30
        for check_date in ("2026-08-31", "2026-09-30"):
            assets, liab, eq = con.execute(
                """
                SELECT COALESCE(SUM(CASE WHEN regexp_matches(account_code, '^[12]') THEN net_debit ELSE 0 END), 0),
                       COALESCE(SUM(CASE WHEN starts_with(account_code, '3') THEN -net_debit ELSE 0 END), 0),
                       COALESCE(SUM(CASE WHEN regexp_matches(account_code, '^[4-9]') THEN -net_debit ELSE 0 END), 0)
                FROM v_tax
                WHERE posting_date <= CAST(? AS DATE)
                """,
                [check_date],
            ).fetchone()
            assert assets == liab + eq
