"""Explicit statement-to-bank reconciliation; completeness is never inferred."""

from datetime import timedelta

from .data import iso_date
from .ledger import scope, text


def validate_statement(row, effective_on):
    scope(row)
    text(row["id"])
    text(row["account_id"])
    start, end = iso_date(row["start_on"]), iso_date(row["end_on"])
    if start > end or end > iso_date(effective_on):
        raise ValueError("statement period invalid or not yet effective")
    for field in ("opening_minor", "closing_minor", "credits_minor", "debits_minor"):
        if type(row[field]) is not int:
            raise ValueError("statement amounts must be integer minor units")
    if min(row["credits_minor"], row["debits_minor"]) < 0:
        raise ValueError("statement credit/debit totals must be nonnegative")
    if type(row["transactions_complete"]) is not bool:
        raise ValueError("statement requires explicit transactions_complete boolean")


def reconcile_statements(statements, banks):
    results, previous = [], {}
    for s in sorted(statements, key=lambda r: (r["tenant_id"], r["currency"], r["account_id"], r["start_on"], r["id"])):
        k = (*scope(s), s["account_id"])
        prev = previous.get(k)
        if prev and s["start_on"] <= prev["end_on"]:
            raise ValueError("overlapping statement periods for the same account")
        observed = [b for b in banks if (*scope(b), b.get("account_id")) == k
                    and s["start_on"] <= b["effective_on"] <= s["end_on"]]
        credits = sum(b["amount_minor"] for b in observed if b["direction"] == "credit")
        debits = sum(b["amount_minor"] for b in observed if b["direction"] == "debit")
        equation = s["opening_minor"] + s["credits_minor"] - s["debits_minor"] == s["closing_minor"]
        totals = credits == s["credits_minor"] and debits == s["debits_minor"]
        adjacent = prev is not None and iso_date(prev["end_on"]) + timedelta(days=1) == iso_date(s["start_on"])
        continuity = s["opening_minor"] == prev["closing_minor"] if adjacent else None
        # A gap or missing opening period is reported, never invented.
        status = ("mismatch" if not equation or not totals or continuity is False else
                  "matched_declared_complete" if s["transactions_complete"] else "unknown_completeness")
        results.append({"tenant_id": s["tenant_id"], "currency": s["currency"], "account_id": s["account_id"],
                        "statement_id": s["id"], "start_on": s["start_on"], "end_on": s["end_on"],
                        "status": status, "statement_equation_pass": equation, "transaction_totals_pass": totals,
                        "previous_period_adjacent": adjacent, "continuity_pass": continuity,
                        "transactions_complete_declared": s["transactions_complete"],
                        "observed_credits_minor": credits, "observed_debits_minor": debits,
                        "closing_difference_minor": s["opening_minor"] + credits - debits - s["closing_minor"],
                        "bank_ids": sorted(b["id"] for b in observed)})
        previous[k] = s
    return results
