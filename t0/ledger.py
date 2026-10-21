"""Offline subledger with atomic, idempotent decisions and bitemporal replay.

This is a local ledger, not an ERP connector. Money is always positive minor
units with explicit AR/AP and bank direction. Approval never posts money.
"""

from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import sqlite3

from .data import canonical, fingerprint, iso_date, loads_json
from .fx import convert


def positive(value):
    if type(value) is not int or value <= 0:
        raise ValueError("amount must be a positive integer in minor units")
    return value


def text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("identity must be a nonempty string")
    return value


def scope(row):
    text(row["tenant_id"])
    currency = row["currency"]
    if (not isinstance(currency, str) or len(currency) != 3 or not currency.isascii()
            or not currency.isalpha() or not currency.isupper()):
        raise ValueError("currency must be three uppercase ASCII letters")
    return row["tenant_id"], currency


def compatible(a, b):
    if scope(a) != scope(b) or a["side"] != b["side"] or a["party_id"] != b["party_id"]:
        raise ValueError("tenant/currency/side/party mismatch")


def replay(events, cutoff):
    """Replay immutable commands in ingestion sequence, visible as of cutoff.

    Return movements, not a bank balance: opening bank balances/complete
    statements are not assumed. All endpoint references are tenant scoped.
    """
    iso_date(cutoff)
    invoices, payments, banks, decisions = {}, {}, {}, {}
    credits, refunds, links, statements, refund_links = {}, {}, {}, {}, {}
    applied, lineage, versions = {}, [], []
    prior_available = "0001-01-01"

    def lookup(table, tenant, identifier):
        try:
            return table[(tenant, identifier)]
        except KeyError as exc:
            raise ValueError(f"missing visible endpoint: {tenant}/{identifier}") from exc

    def balances():
        paid, spent = defaultdict(int), defaultdict(int)
        for allocations in applied.values():
            for a in allocations:
                paid[(a["tenant_id"], a["invoice_id"])] += a["amount_minor"]
                spent[(a["tenant_id"], a["payment_id"])] += a.get("payment_amount_minor", a["amount_minor"])
        reduced, returned = defaultdict(int), defaultdict(int)
        for r in credits.values():
            reduced[(r["tenant_id"], r["invoice_id"])] += r["amount_minor"]
        for r in refunds.values():
            returned[(r["tenant_id"], r["payment_id"])] += r["amount_minor"]
        inv_balance = {k: r["amount_minor"] - paid[k] - reduced[k] for k, r in invoices.items()}
        pay_balance = {k: r["amount_minor"] - spent[k] - returned[k] for k, r in payments.items()}
        if any(v < 0 for v in (*inv_balance.values(), *pay_balance.values())):
            raise ValueError("allocation/credit/refund exceeds available invoice or payment")
        for k, p in payments.items():
            if sum(v["payment_amount_minor"] for v in links.values()
                   if (v["tenant_id"], v["payment_id"]) == k) > p["amount_minor"]:
                raise ValueError("revision exceeds bank-linked payment")
        return inv_balance, pay_balance, paid, reduced, returned

    def allocation_amount(a, i, p, e):
        positive(a["amount_minor"])
        for field, expected in (("tenant_id", e["tenant_id"]), ("currency", i["currency"]),
                                ("payment_currency", p["currency"]), ("side", i["side"])):
            if field in a and a[field] != expected:
                raise ValueError(f"allocation {field} disagrees with its endpoints")
        if (i["tenant_id"] != p["tenant_id"] or i["side"] != p["side"]
                or i["party_id"] != p["party_id"]):
            raise ValueError("allocation tenant/side/party mismatch")
        if i["currency"] == p["currency"]:
            if "fx" in a or positive(a.get("payment_amount_minor", a["amount_minor"])) != a["amount_minor"]:
                raise ValueError("same-currency allocation amounts must agree")
        else:
            if "fx" not in a or "payment_amount_minor" not in a:
                raise ValueError("cross-currency allocation requires observed FX and payment amount")
            if positive(a["payment_amount_minor"]) != convert(a["amount_minor"], a["fx"], i["currency"],
                    p["currency"], e["effective_on"], e["available_on"]):
                raise ValueError("FX allocation amount mismatch")

    for sequence, original in enumerate(events, 1):
        e = deepcopy(original)
        iso_date(e["available_on"])
        if e["available_on"] < prior_available:
            raise ValueError("ingestion availability must not move backwards")
        prior_available = e["available_on"]
        if e["available_on"] > cutoff:
            continue
        iso_date(e["effective_on"])
        if e["effective_on"] > e["available_on"]:
            raise ValueError("scheduled future-effective ledger commands are unsupported")
        tenant = text(e["tenant_id"])
        action = e["action"]
        if action in ("record", "revise"):
            r = e["data"]
            if r["tenant_id"] != tenant:
                raise ValueError("command and row tenant mismatch")
            scope(r)
            key = (tenant, text(r["id"]))
            kind = e["kind"]
            tables = {"invoice": invoices, "payment": payments, "bank": banks,
                      "credit_note": credits, "refund": refunds, "bank_link": links,
                      "bank_statement": statements, "refund_bank_link": refund_links}
            if kind not in tables:
                raise ValueError(f"unsupported record kind: {kind}")
            table = tables[kind]
            old = table.get(key)
            if action == "revise":
                if kind not in ("invoice", "payment") or old is None:
                    raise ValueError("revision requires an existing invoice/payment")
                if type(e["expected_version"]) is not int or e["expected_version"] != old["version"]:
                    raise ValueError("stale document version")
                if any(r[field] != old[field] for field in ("tenant_id", "id", "currency", "side", "party_id")):
                    raise ValueError("revision cannot change document scope/identity")
                # Revisions change values known now, not the original issue or
                # payment date. A correction of those dates needs a reversal.
                if e["effective_on"] != old["effective_on"]:
                    raise ValueError("revision must preserve original document effective date")
                field = "invoice_id" if kind == "invoice" else "payment_id"
                if any(d["tenant_id"] == tenant and d["status"] == "review_required" and
                       any(a[field] == r["id"] for a in d["allocations"]) for d in decisions.values()):
                    raise ValueError("external result unknown; verify before revision")
            elif old is not None:
                raise ValueError("record already exists; use the original idempotency key")
            if kind not in ("bank_link", "refund_bank_link", "bank_statement"):
                positive(r["amount_minor"])
            if kind == "bank_statement":
                from .balances import validate_statement
                validate_statement(r, e["effective_on"])
            if kind in ("invoice", "payment"):
                if r["side"] not in ("AR", "AP"):
                    raise ValueError("side must be AR or AP")
                text(r["party_id"])
            if kind == "bank" and r["direction"] not in ("credit", "debit"):
                raise ValueError("bank direction must be credit or debit")
            if kind == "invoice":
                text(r["invoice_number"])
            if kind in ("credit_note", "refund"):
                field = "invoice_id" if kind == "credit_note" else "payment_id"
                endpoint = lookup(invoices if kind == "credit_note" else payments, tenant,
                                  r[field])
                if scope(endpoint) != scope(r):
                    raise ValueError("adjustment scope mismatch; FX is unsupported")
                if e["effective_on"] < endpoint["effective_on"]:
                    raise ValueError("adjustment predates its endpoint")
                if any(d["tenant_id"] == tenant and d["status"] == "review_required" and
                       any(a[field] == r[field] for a in d["allocations"]) for d in decisions.values()):
                    raise ValueError("external result unknown; verify before credit/refund")
            if kind in ("bank_link", "refund_bank_link"):
                is_refund = kind == "refund_bank_link"
                adjustment = lookup(refunds, tenant, r["refund_id"]) if is_refund else None
                payment_id = adjustment["payment_id"] if is_refund else r["payment_id"]
                p = lookup(payments, tenant, payment_id)
                b = lookup(banks, tenant, r["bank_id"])
                if scope(p) != scope(r) or b["tenant_id"] != tenant:
                    raise ValueError("bank link source scope mismatch")
                if e["effective_on"] < max(p["effective_on"], b["effective_on"],
                                           adjustment["effective_on"] if is_refund else p["effective_on"]):
                    raise ValueError("bank link predates its endpoints")
                fee = r["fee_minor"]
                if type(fee) is not int or fee < 0:
                    raise ValueError("fee must be a nonnegative integer")
                direction = "credit" if p["side"] == "AR" else "debit"
                if is_refund:
                    direction = "debit" if direction == "credit" else "credit"
                amount_field = "refund_amount_minor" if is_refund else "payment_amount_minor"
                gross = positive(r.get(amount_field, adjustment["amount_minor"] if is_refund else p["amount_minor"]))
                net = positive(r.get("bank_amount_minor", b["amount_minor"]))
                converted = gross
                if p["currency"] != b["currency"]:
                    if "fx" not in r:
                        raise ValueError("bank link currency mismatch requires an observed FX quote")
                    converted = convert(gross, r["fx"], p["currency"], b["currency"], e["effective_on"], e["available_on"])
                elif "fx" in r:
                    raise ValueError("same-currency bank link cannot carry FX")
                expected = converted - fee if direction == "credit" else converted + fee
                if b["direction"] != direction or net != expected:
                    raise ValueError("gross/net/fee or direction mismatch")
                source_table = refund_links if is_refund else links
                identity_field = "refund_id" if is_refund else "payment_id"
                used_gross = sum(v[amount_field] for v in source_table.values()
                                 if v["tenant_id"] == tenant and v[identity_field] == r[identity_field])
                used_net = sum(v["bank_amount_minor"] for v in (*links.values(), *refund_links.values())
                               if v["tenant_id"] == tenant and v["bank_id"] == r["bank_id"])
                if (used_gross + gross > (adjustment["amount_minor"] if is_refund else p["amount_minor"])
                        or used_net + net > b["amount_minor"]):
                    raise ValueError("bank/payment link exceeds remaining amount")
                r = {**r, amount_field: gross, "bank_amount_minor": net, "bank_currency": b["currency"]}
                if "realized_fx_minor" in r and "carrying_bank_minor" not in r:
                    raise ValueError("realized FX requires an explicit carrying value")
                if is_refund:
                    r["payment_id"] = payment_id
                if "carrying_bank_minor" in r:
                    carrying = positive(r["carrying_bank_minor"])
                    if p["currency"] == b["currency"]:
                        raise ValueError("carrying value requires an FX link")
                    r["realized_fx_minor"] = (converted - carrying) * (1 if direction == "credit" else -1)
            if kind in ("invoice", "payment"):
                for field in ("issued_on", "payment_on", "due_on"):
                    if field in r:
                        iso_date(r[field])
                business_field = "issued_on" if kind == "invoice" else "payment_on"
                if business_field in r and r[business_field] != e["effective_on"]:
                    raise ValueError("document business date must agree with ledger effective date")
                if kind == "invoice" and r.get("due_on", e["effective_on"]) < e["effective_on"]:
                    raise ValueError("invoice due date precedes issue date")
                r = {**r, "version": old["version"] + 1 if old else 1}
            table[key] = {**r, "effective_on": e["effective_on"], "available_on": e["available_on"]}
            if kind in ("invoice", "payment"):
                versions.append({**table[key], "kind": kind, "sequence": sequence,
                                 "supersedes_version": old["version"] if old else None})
        else:
            key = tenant, text(e["decision_id"])
            if action == "suggest":
                if key in decisions:
                    raise ValueError("decision already exists")
                allocations = e["allocations"]
                if not isinstance(allocations, list) or not allocations:
                    raise ValueError("decision needs nonempty allocations")
                seen = set()
                for a in allocations:
                    pair = (text(a["invoice_id"]), text(a["payment_id"]))
                    if pair in seen:
                        raise ValueError("duplicate allocation edge")
                    seen.add(pair)
                    i, p = lookup(invoices, tenant, pair[0]), lookup(payments, tenant, pair[1])
                    allocation_amount(a, i, p, e)
                    if max(i["effective_on"], p["effective_on"]) > e["effective_on"]:
                        raise ValueError("decision predates its endpoints")
                decisions[key] = {"tenant_id": tenant, "decision_id": e["decision_id"],
                                  "status": "suggested", "allocations": allocations,
                                  "endpoint_versions": [[invoices[(tenant, a["invoice_id"])]["version"],
                                                         payments[(tenant, a["payment_id"])]["version"]] for a in allocations],
                                  "last_effective_on": e["effective_on"]}
            else:
                d = lookup(decisions, tenant, e["decision_id"])
                state = d["status"]
                if e["effective_on"] < d["last_effective_on"]:
                    raise ValueError("decision transition predates its preceding transition")
                if action in ("approve", "commit", "verify"):
                    current = [[invoices[(tenant, a["invoice_id"])]["version"],
                                payments[(tenant, a["payment_id"])]["version"]] for a in d["allocations"]]
                    if current != d["endpoint_versions"]:
                        raise ValueError("stale decision; document revised, cancel and suggest again")
                if action in ("commit", "verify"):
                    endpoints = {(a["invoice_id"], a["payment_id"]) for a in d["allocations"]}
                    for other_key, other in decisions.items():
                        if other_key == key or other["tenant_id"] != tenant or other["status"] != "review_required":
                            continue
                        if any(any(i == a["invoice_id"] or p == a["payment_id"] for i, p in endpoints)
                               for a in other["allocations"]):
                            raise ValueError("overlapping external result unknown; verify source before new commit")
                if action == "approve" and state == "suggested":
                    d["status"] = "approved"
                elif action == "commit" and state == "approved":
                    if e["external_result"] == "unknown":
                        d["status"] = "review_required"
                    elif e["external_result"] == "verified":
                        d["status"] = "committed"
                    else:
                        raise ValueError("external_result must be verified or unknown")
                elif action == "verify" and state == "review_required":
                    if e["external_result"] not in ("committed", "not_committed"):
                        raise ValueError("verification requires a confirmed outcome")
                    d["status"] = "committed" if e["external_result"] == "committed" else "approved"
                elif action == "reverse" and state == "committed":
                    d["status"] = "reversed"
                    del applied[key]
                elif action == "cancel" and state in ("suggested", "approved"):
                    d["status"] = "cancelled"
                else:
                    raise ValueError(f"invalid transition: {state} -> {action}")
                d["last_effective_on"] = e["effective_on"]
                if d["status"] == "committed":
                    applied[key] = [{**a, "tenant_id": tenant} for a in d["allocations"]]
        balances()  # Fail atomically before an invalid command enters the store.
        lineage.append({"sequence": sequence, "command_hash": fingerprint(original)})

    inv_balance, pay_balance, paid, reduced, returned = balances()
    cash = defaultdict(int)
    for b in banks.values():
        cash[(b["tenant_id"], b["currency"])] += b["amount_minor"] * (1 if b["direction"] == "credit" else -1)
    from .balances import reconcile_statements
    statement_report = reconcile_statements(statements.values(), banks.values())
    return {"cutoff": cutoff,
            "invoices": [{**r, "allocated_minor": paid[k], "credit_minor": reduced[k],
                          "outstanding_minor": inv_balance[k]} for k, r in sorted(invoices.items())],
            "payments": [{**r, "refunded_minor": returned[k], "unallocated_minor": pay_balance[k]}
                         for k, r in sorted(payments.items())],
            "bank_movements": [{"tenant_id": t, "currency": c, "net_minor": v}
                               for (t, c), v in sorted(cash.items())],
            "bank_links": [r for _, r in sorted(links.items())],
            "refund_bank_links": [r for _, r in sorted(refund_links.items())],
            "refunds": [{**r, "bank_unlinked_minor": r["amount_minor"] - sum(v["refund_amount_minor"]
                         for v in refund_links.values() if v["tenant_id"] == r["tenant_id"] and v["refund_id"] == r["id"])}
                        for _, r in sorted(refunds.items())],
            "document_versions": versions,
            "bank_reconciliation": statement_report,
            "bank_unlinked": [{"tenant_id": t, "bank_id": bid, "currency": b["currency"],
                               "unlinked_minor": b["amount_minor"] - sum(link["bank_amount_minor"] for link in (*links.values(), *refund_links.values())
                                   if link["tenant_id"] == t and link["bank_id"] == bid)}
                              for (t, bid), b in sorted(banks.items())],
            "decisions": [r for _, r in sorted(decisions.items())],
            "lineage": lineage, "invariant_errors": []}


class EventStore:
    """SQLite transaction encloses key lookup, validation and immutable insert."""

    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=10)
        self.connection.execute("CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY, "
                                "key TEXT NOT NULL UNIQUE, payload TEXT NOT NULL)")
        self.connection.commit()

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def events(self):
        return [loads_json(row[0]) for row in self.connection.execute("SELECT payload FROM events ORDER BY sequence")]

    def submit(self, idempotency_key, command):
        text(idempotency_key)
        payload = canonical(command)
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            old = self.connection.execute("SELECT sequence, payload FROM events WHERE key=?",
                                          (idempotency_key,)).fetchone()
            if old:
                if old[1] != payload:
                    raise ValueError("idempotency key reused with different payload")
                return {"sequence": old[0], "command_hash": fingerprint(command), "replayed": True}
            replay(self.events() + [command], "9999-12-31")
            cursor = self.connection.execute("INSERT INTO events(key,payload) VALUES (?,?)", (idempotency_key, payload))
            return {"sequence": cursor.lastrowid, "command_hash": fingerprint(command), "replayed": False}

    def gold(self, cutoff):
        result = replay(self.events(), cutoff)
        result["snapshot_hash"] = fingerprint(result)
        return result
