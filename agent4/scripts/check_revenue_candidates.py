"""Reconcile proposed revenue bindings on the frozen MPX10 snapshot."""

import json
from decimal import Decimal
from typing import NamedTuple

from agent4.core.catalog import _amount
from agent4.core.config import AppConfig
from agent4.engine.metrics import REGISTRY
from scripts.check_mpx10 import REFERENCE, SNAPSHOT
from scripts.check_warehouse import open_warehouse

METRIC_IDS = ("gross_revenue", "revenue_deductions", "goods_revenue", "service_revenue")


class AccountTotal(NamedTuple):
    code: str
    debit: Decimal
    credit: Decimal


def reconcile(accounts: list[AccountTotal]) -> dict[str, Decimal]:
    """Calculate reference totals from account subtotals independently of registry terms."""
    zero = Decimal(0)
    revenue = [row for row in accounts if row.code.startswith("511")]
    return {
        "gross_revenue": sum((row.credit for row in revenue), zero),
        "revenue_deductions": sum((row.debit for row in revenue), zero)
        + sum((row.debit - row.credit for row in accounts if row.code.startswith("521")), zero),
        "goods_revenue": sum(
            (row.credit - row.debit for row in revenue if row.code.startswith("5111")), zero
        ),
        "service_revenue": sum(
            (row.credit - row.debit for row in revenue if row.code.startswith("5113")), zero
        ),
    }


def main() -> None:
    with open_warehouse(AppConfig().db_path) as db:
        info = dict(db.execute("SELECT key, value FROM company_info").fetchall())
        if any(info.get(key) != value for key, value in SNAPSHOT.items()):
            raise SystemExit("Revenue reconciliation requires the frozen MPX10 v3 snapshot")

        reference = json.loads(REFERENCE.read_text(encoding="utf-8"))["catalog_baseline"]
        month = SNAPSHOT["last_closed_month"]
        for view in ("mgmt", "tax"):
            relation = f"v_{view}"
            accounts = [
                AccountTotal(*row)
                for row in db.execute(
                    f"""SELECT account_code, SUM(debit_amount), SUM(credit_amount)
                    FROM {relation}
                    WHERE year_month = ? AND NOT is_closing
                      AND source_module IS DISTINCT FROM 'OPENING'
                      AND (starts_with(account_code, '511') OR starts_with(account_code, '521'))
                    GROUP BY account_code ORDER BY account_code""",
                    [month],
                ).fetchall()
            ]
            if not accounts:
                raise SystemExit(f"No revenue postings in {view} for {month}")
            expected = reconcile(accounts)
            supported = [metric for metric in METRIC_IDS if view in REGISTRY[metric].views]
            expressions = ", ".join(_amount(REGISTRY[metric].terms) for metric in supported)
            actual = db.execute(
                f"""SELECT {expressions} FROM {relation}
                WHERE posting_date >= CAST(? AS DATE)
                  AND posting_date < CAST(? AS DATE) + INTERVAL 1 MONTH
                  AND NOT is_closing AND source_module IS DISTINCT FROM 'OPENING'""",
                [f"{month}-01", f"{month}-01"],
            ).fetchone()
            for metric_id, result in zip(supported, actual, strict=True):
                if result != expected[metric_id]:
                    raise SystemExit(
                        f"Candidate differs from account reconciliation: {view}/{metric_id}"
                    )
            if expected["gross_revenue"] - expected["revenue_deductions"] != Decimal(
                reference[f"net_revenue [{relation}]"]
            ):
                raise SystemExit(f"Revenue bridge differs from frozen net revenue: {view}")
            print(f"{view} {month}: " + ", ".join(f"{m}={expected[m]}" for m in supported))


if __name__ == "__main__":
    main()
