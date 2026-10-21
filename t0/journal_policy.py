"""Explicit observed accounting facts to balanced postings, with no policy guess.

Policy and facts are caller-supplied inputs, never extracted from expected_*.
This engine does not decide tax eligibility, revenue timing or an exchange rate.
"""

from .data import fingerprint, iso_date
from .fx import convert
from .ledger import positive, scope, text


class UnsupportedPolicy(ValueError):
    """Insufficient policy/evidence is unknown, not proof of inconsistency."""


INVOICES = {"customer_invoice", "vendor_invoice", "expense_receipt",
            "customer_credit_note", "vendor_credit_note"}
SETTLEMENTS = {"customer_payment", "vendor_payment", "customer_refund", "vendor_refund"}


def observed_identity(doc):
    """Shared identity for deliveries/dependencies, excluding evaluation labels."""
    fields = ("schema", "party_id", "currency", "subtotal_minor", "tax_minor", "discount_minor", "total_minor",
              "revenue_recognition", "tax_treatment", "expense_account", "reference_doc_id", "amount_minor",
              "carrying_functional_minor")
    facts = doc.get("accounting_facts", {})
    projected = {k: facts[k] for k in fields if k in facts}
    if "fx" in facts:
        projected["fx"] = {k: facts["fx"].get(k) for k in ("source_currency", "target_currency", "rate_num", "rate_den",
                            "rounding", "source_ref", "quoted_on", "available_on")}
    return fingerprint({**{k: doc.get(k) for k in ("ocr_text", "doc_type", "date", "role", "available_on")},
                        "accounting_facts": projected,
                        "metadata": {k: doc.get("metadata", {}).get(k) for k in ("currency_code", "issuer_name", "counterparty_name")}})


def nonnegative(value):
    if type(value) is not int or value < 0:
        raise ValueError("journal amounts must be nonnegative integer minor units")
    return value


def validate_policy(policy, cutoff):
    iso_date(cutoff)
    text(policy["policy_id"])
    text(policy["functional_currency"])
    scope({"tenant_id": "policy", "currency": policy["functional_currency"]})
    if not isinstance(policy["accounts"], dict) or not policy["accounts"]:
        raise ValueError("explicit policy accounts are required")
    names = [text(v) for v in policy["accounts"].values()]
    if len(names) != len(set(names)):
        raise ValueError("policy account aliases must have distinct names")
    iso_date(policy["available_on"])
    iso_date(policy["effective_on"])
    if not policy["effective_on"] <= policy["available_on"] <= cutoff:
        raise ValueError("accounting policy unavailable at cutoff")
    return policy


def postings(doc, policy, documents, cutoff):
    """Return balanced functional-currency debit/credit lines for one document."""
    validate_policy(policy, cutoff)
    facts = doc["accounting_facts"]
    if facts["schema"] != "t0-journal-facts-v1":
        raise UnsupportedPolicy("unknown observed journal facts schema")
    iso_date(doc["date"]); iso_date(doc["available_on"])
    day, available = doc["date"], doc["available_on"]
    if not day <= available <= cutoff:
        raise ValueError("document not effective or available at cutoff")
    if day < policy["effective_on"]:
        raise UnsupportedPolicy("document predates the supplied accounting policy")
    kind, currency = doc["doc_type"], facts["currency"]
    functional, accounts = policy["functional_currency"], policy["accounts"]
    scope({"tenant_id": "facts", "currency": currency})
    text(facts["party_id"])
    lines = []

    def account(alias):
        if alias not in accounts:
            raise UnsupportedPolicy("policy account missing: " + alias)
        return text(accounts[alias])

    def add(alias, debit=0, credit=0, actual=None):
        nonnegative(debit); nonnegative(credit)
        if debit and credit:
            raise ValueError("posting line cannot have both debit and credit")
        if debit or credit:
            name = text(actual) if actual is not None else account(alias)
            if name not in accounts.values():
                raise ValueError("posting account is not in the explicit policy chart")
            lines.append({"account": name, "debit_minor": debit, "credit_minor": credit})

    def translated(amount):
        return (amount if currency == functional else convert(amount, facts["fx"], currency, functional, day, available)) if amount else 0

    if kind in INVOICES:
        subtotal, tax = positive(facts["subtotal_minor"]), nonnegative(facts["tax_minor"])
        discount, total = nonnegative(facts.get("discount_minor", 0)), positive(facts["total_minor"])
        if discount >= subtotal or subtotal - discount + tax != total:
            raise ValueError("subtotal/discount/tax/total mismatch")
        if kind.startswith("customer") and facts["revenue_recognition"] != "immediate":
            raise UnsupportedPolicy("revenue recognition policy requires separate schedule")
        net_f, tax_f, total_f = translated(subtotal - discount), translated(tax), translated(total)
        # Rounding each component may differ from rounding the total. Do not
        # silently balance the difference into tax/revenue.
        if net_f + tax_f != total_f:
            raise UnsupportedPolicy("FX component rounding needs an explicit rounding policy")
        sale = kind.startswith("customer")
        if sale:
            add("receivable", debit=total_f)
            add("revenue", credit=net_f)
            add("output_tax", credit=tax_f)
        else:
            treatment = facts["tax_treatment"]
            if treatment not in ("recoverable", "expensed"):
                raise UnsupportedPolicy("purchase requires explicit tax treatment")
            add("expense", debit=net_f + (tax_f if treatment == "expensed" else 0), actual=facts["expense_account"])
            if treatment == "recoverable":
                add("input_tax", debit=tax_f)
            add("cash" if kind == "expense_receipt" else "payable", credit=total_f)
        if kind.endswith("credit_note"):
            source = _dependency(doc, facts, documents, cutoff,
                                 "customer_invoice" if sale else "vendor_invoice", total, currency)
            postings(source, policy, documents, cutoff)
            original = source["accounting_facts"]
            if (tax > original["tax_minor"] or subtotal - discount > original["subtotal_minor"] - original.get("discount_minor", 0)):
                raise ValueError("credit component exceeds referenced invoice component")
            if not sale and any(facts[field] != original[field] for field in ("tax_treatment", "expense_account")):
                raise ValueError("credit note must reverse the original expense and tax policy")
            if total_f != carrying_value(source, total, functional):
                raise ValueError("credit note must reverse the referenced booking carrying value")
            lines = [{"account": r["account"], "debit_minor": r["credit_minor"], "credit_minor": r["debit_minor"]} for r in lines]
    elif kind in SETTLEMENTS:
        amount = positive(facts["amount_minor"])
        source_kind = {"customer_payment": "customer_invoice", "vendor_payment": "vendor_invoice",
                       "customer_refund": "customer_credit_note", "vendor_refund": "vendor_credit_note"}[kind]
        source = _dependency(doc, facts, documents, cutoff, source_kind, amount, currency)
        postings(source, policy, documents, cutoff)
        actual, carrying = translated(amount), positive(facts["carrying_functional_minor"])
        if carrying != carrying_value(source, amount, functional):
            raise ValueError("settlement carrying value differs from referenced document booking")
        if currency == functional and carrying != actual:
            raise ValueError("same-currency carrying value mismatch")
        inflow = kind in ("customer_payment", "vendor_refund")
        control = "receivable" if kind.startswith("customer") else "payable"
        add("cash", debit=actual if inflow else 0, credit=0 if inflow else actual)
        add(control, debit=0 if inflow else carrying, credit=carrying if inflow else 0)
        gain = (actual - carrying) * (1 if inflow else -1)
        if gain > 0:
            add("fx_gain", credit=gain)
        elif gain < 0:
            add("fx_loss", debit=-gain)
    else:
        raise UnsupportedPolicy("unsupported structured journal document type")
    if sum(r["debit_minor"] - r["credit_minor"] for r in lines) != 0 or not lines:
        raise ValueError("unbalanced journal")
    return {"doc_id": doc["doc_id"], "posting_date": day, "currency": functional,
            "policy_id": policy["policy_id"], "lines": lines}


def carrying_value(source, amount, functional):
    facts = source["accounting_facts"]
    total = positive(facts["total_minor"])
    carrying = total if facts["currency"] == functional else convert(total, facts["fx"], facts["currency"],
                functional, source["date"], source["available_on"])
    quotient, remainder = divmod(carrying * amount, total)
    return quotient + int(2 * remainder > total or 2 * remainder == total and quotient % 2 == 1)


def _dependency(doc, facts, documents, cutoff, expected_kind, amount, currency):
    ref = text(facts["reference_doc_id"])
    matches = list({observed_identity(d): d for d in documents
                    if d["doc_id"] == ref and d["role"] in ("posting_doc", "support_doc")}.values())
    if len(matches) != 1 or ref == doc["doc_id"]:
        raise UnsupportedPolicy("missing or ambiguous journal dependency")
    other = matches[0]
    of = other["accounting_facts"]
    if (other["doc_type"] != expected_kind or of["currency"] != currency
            or of["party_id"] != facts["party_id"]):
        raise ValueError("journal dependency type/currency/party mismatch")
    iso_date(other["date"]); iso_date(other["available_on"])
    if other["date"] > doc["date"] or other["available_on"] > cutoff:
        raise ValueError("journal dependency is not visible/effective")
    if amount > positive(of["total_minor"]):
        raise ValueError("journal dependency amount overflow")
    return other


def pair_entries(posting):
    """Lossless debit-credit pairing for the existing entry evaluator schema."""
    iso_date(posting["posting_date"])
    if not posting["lines"]:
        raise ValueError("empty journal posting")
    for row in posting["lines"]:
        text(row["account"])
        debit, credit = nonnegative(row["debit_minor"]), nonnegative(row["credit_minor"])
        if bool(debit) == bool(credit):
            raise ValueError("posting line must have exactly one positive side")
    if sum(r["debit_minor"] - r["credit_minor"] for r in posting["lines"]) != 0:
        raise ValueError("unbalanced journal posting")
    debits = [[r["account"], r["debit_minor"]] for r in posting["lines"] if r["debit_minor"]]
    credits = [[r["account"], r["credit_minor"]] for r in posting["lines"] if r["credit_minor"]]
    entries, i, j = [], 0, 0
    while i < len(debits) and j < len(credits):
        amount = min(debits[i][1], credits[j][1])
        if debits[i][0] == credits[j][0]:
            raise ValueError("journal debit/credit account must differ")
        entries.append({"doc_refs": [posting["doc_id"]], "debit_account": debits[i][0],
                        "credit_account": credits[j][0], "amount_minor": amount,
                        "posting_date": posting["posting_date"]})
        debits[i][1] -= amount; credits[j][1] -= amount
        if not debits[i][1]:
            i += 1
        if not credits[j][1]:
            j += 1
    return entries


def replay_trial_balance(opening, postings, policy, cutoff):
    """Signed-debit trial balance in one explicit functional currency.

    Positive means debit, negative means credit. No inferred account classes,
    balance-sheet presentation, opening amounts or retained-earnings closure.
    """
    validate_policy(policy, cutoff)
    iso_date(opening["as_of"]); iso_date(opening["available_on"])
    if not opening["as_of"] <= opening["available_on"] <= cutoff:
        raise ValueError("opening trial balance unavailable at cutoff")
    if opening["currency"] != policy["functional_currency"]:
        raise ValueError("opening functional currency mismatch")
    balances = dict(opening["balances"])
    if any(type(v) is not int for v in balances.values()) or sum(balances.values()) != 0:
        raise ValueError("opening trial balance must balance in signed integer minor units")
    allowed = set(policy["accounts"].values())
    if not set(balances) <= allowed:
        raise ValueError("opening account outside explicit policy chart")
    for posting in postings:
        iso_date(posting["posting_date"])
        if (posting["currency"] != opening["currency"] or not opening["as_of"] < posting["posting_date"] <= cutoff
                or posting["policy_id"] != policy["policy_id"]):
            raise ValueError("posting currency/policy/period incompatible with opening")
        if sum(r["debit_minor"] - r["credit_minor"] for r in posting["lines"]) != 0:
            raise ValueError("unbalanced posting in trial balance replay")
        for row in posting["lines"]:
            if row["account"] not in allowed:
                raise ValueError("posting account outside explicit policy chart")
            debit, credit = nonnegative(row["debit_minor"]), nonnegative(row["credit_minor"])
            if debit and credit:
                raise ValueError("trial balance line has both debit and credit")
            balances[row["account"]] = balances.get(row["account"], 0) + debit - credit
    return {"currency": opening["currency"], "cutoff": cutoff, "balances": dict(sorted(balances.items())),
            "balanced": sum(balances.values()) == 0,
            "scope": "Only supplied opening and predicted structured postings; not a completeness assertion"}
