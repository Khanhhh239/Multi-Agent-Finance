"""Double-entry ledger used by the simulator.

Every business event goes through :meth:`Ledger.post`, which refuses an
unbalanced journal unless the caller explicitly injects a data-quality defect
(``allow_unbalanced=True``).  Running balances are kept per account and per
(account, partner) so the simulator can make cash-management decisions and
derive VAT offsets, payroll payable, etc. exactly as an accountant would.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time


@dataclass
class Line:
    account: str
    debit: int = 0
    credit: int = 0
    partner: str | None = None
    item: str | None = None
    branch: str | None = None
    department: str | None = None
    employee: str | None = None
    product_line: str | None = None
    cost_category: str | None = None
    tax_deductible: bool = True
    tax_note: str | None = None
    description: str | None = None


def dr(account: str, amount: int, **kw) -> Line:
    return Line(account, debit=int(amount), **kw)


def cr(account: str, amount: int, **kw) -> Line:
    return Line(account, credit=int(amount), **kw)


class Ledger:
    def __init__(self) -> None:
        self.rows: list[tuple] = []
        self.journals: list[tuple] = []
        self.balance: dict[str, int] = defaultdict(int)  # debit-positive
        self.partner_balance: dict[tuple[str, str], int] = defaultdict(int)
        self.month_movement: dict[tuple[str, str], int] = defaultdict(int)  # (yyyy-mm, account) excl. closing
        self._entry_id = 0
        self._seq: dict[str, int] = defaultdict(int)

    def next_doc(self, prefix: str, on: date) -> str:
        key = f"{prefix}{on:%Y%m}"
        self._seq[key] += 1
        return f"{prefix}{on:%y%m}/{self._seq[key]:04d}"

    def post(
        self,
        on: date,
        doc_type: str,
        description: str,
        lines: list[Line],
        *,
        prefix: str,
        module: str,
        doc_no: str | None = None,
        branch: str | None = None,
        is_closing: bool = False,
        created_by: str = "ketoan.tonghop",
        created_at: datetime | None = None,
        allow_unbalanced: bool = False,
        hour: int = 10,
    ) -> str:
        lines = [ln for ln in lines if ln.debit or ln.credit]
        if not lines:
            return ""
        total_dr = sum(ln.debit for ln in lines)
        total_cr = sum(ln.credit for ln in lines)
        if total_dr != total_cr and not allow_unbalanced:
            raise ValueError(f"unbalanced journal {description}: {total_dr} != {total_cr}")
        for ln in lines:
            if ln.debit < 0 or ln.credit < 0 or (ln.debit and ln.credit):
                raise ValueError(f"bad line in {description}: {ln}")
        journal_id = self.next_doc(prefix, on)
        created_at = created_at or datetime.combine(on, time(hour, (self._entry_id * 7) % 60))
        self.journals.append((journal_id, on, doc_type, doc_no or journal_id, description, module, is_closing, created_by, created_at))
        ym = f"{on:%Y-%m}"
        for n, ln in enumerate(lines, start=1):
            self._entry_id += 1
            net = ln.debit - ln.credit
            self.balance[ln.account] += net
            if ln.partner:
                self.partner_balance[(ln.account, ln.partner)] += net
            if not is_closing:
                self.month_movement[(ym, ln.account)] += net
            self.rows.append((
                self._entry_id, journal_id, n, on, ln.account, ln.partner, ln.item,
                ln.branch or branch, ln.department, ln.employee, ln.product_line, ln.cost_category,
                ln.description or description, ln.debit, ln.credit, doc_type, doc_no or journal_id, module,
                is_closing, ln.tax_deductible, ln.tax_note, created_by, created_at,
            ))
        return journal_id

    def bal(self, *prefixes: str) -> int:
        return sum(v for k, v in self.balance.items() if k.startswith(prefixes))
