"""Conservative reference rules and scored 1:1 assignment; no ground-truth access."""

from dataclasses import asdict, dataclass
from datetime import date
from difflib import SequenceMatcher
import re
import math
import unicodedata

from .data import allocation_errors, fingerprint


METHODS = ("exact_reference", "amount_date", "scored_global", "reference_then_global")


@dataclass(frozen=True)
class Config:
    max_age_days: int = 120
    due_window_days: int = 14
    score_threshold: float = 0.72
    ambiguity_margin: float = 0.08

    def __post_init__(self):
        if (type(self.max_age_days) is not int or type(self.due_window_days) is not int
                or self.max_age_days < 0 or self.due_window_days < 0):
            raise ValueError("date windows must be nonnegative")
        if (any(type(v) not in (int, float) or not math.isfinite(v)
                for v in (self.score_threshold, self.ambiguity_margin))
                or not 0 <= self.score_threshold <= 1 or not 0 <= self.ambiguity_margin <= 1):
            raise ValueError("threshold/margin must be in [0, 1]")


def normalize(text):
    text = unicodedata.normalize("NFKD", text.casefold().replace("đ", "d"))
    return " ".join(re.findall(r"[a-z0-9]+", "".join(
        char for char in text if not unicodedata.combining(char))))


def references(bank, invoice):
    # Token boundaries prevent INV-1 matching INV-10. Punctuation is normalized.
    needle = normalize(invoice["invoice_id"])
    return bool(needle) and f" {needle} " in f" {normalize(bank['reference'])} "


def eligible(bank, invoice, config):
    age = (date.fromisoformat(bank["booked_on"])
           - date.fromisoformat(invoice["issued_on"])).days
    return (bank["tenant_id"] == invoice["tenant_id"]
            and bank["currency"] == invoice["currency"]
            and (not bank["customer_id"] or bank["customer_id"] == invoice["customer_id"])
            and 0 <= age <= config.max_age_days)


def score(bank, invoice, config):
    if references(bank, invoice):
        return 1.0
    bank_name, invoice_name = normalize(bank["counterparty"]), normalize(invoice["customer_name"])
    name = (SequenceMatcher(None, bank_name, invoice_name, autojunk=False).ratio()
            if bank_name and invoice_name else 0.0)
    identity = 1.0 if bank["customer_id"] else name
    lag = abs((date.fromisoformat(bank["booked_on"])
               - date.fromisoformat(invoice["due_on"])).days)
    proximity = max(0.0, 1 - lag / max(1, config.due_window_days))
    return round(0.65 * identity + 0.25 * name + 0.10 * proximity, 8)


def maximum_weight_assignment(weights):
    """Hungarian assignment with one dummy unmatched column per bank row.

    Forbidden edges are negative; dummy edges have zero weight. Returns real,
    positive edges only. Deterministic when rows/columns have stable ordering.
    """
    n = len(weights)
    m_real = len(weights[0]) if n else 0
    if any(len(row) != m_real for row in weights):
        raise ValueError("ragged weight matrix")
    if any(type(value) not in (int, float) or not math.isfinite(value)
           for row in weights for value in row):
        raise ValueError("assignment weights must be finite numbers")
    if not n or not m_real:
        return []
    costs = [[-v for v in row] + [0.0] * n for row in weights]
    m = m_real + n
    u, v, p, way = [0.0] * (n + 1), [0.0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0, used, minimum = 0, [False] * (m + 1), [float("inf")] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], float("inf"), 0
            for j in range(1, m + 1):
                if not used[j]:
                    current = costs[i0 - 1][j - 1] - u[i0] - v[j]
                    if current < minimum[j]:
                        minimum[j], way[j] = current, j0
                    if minimum[j] < delta:
                        delta, j1 = minimum[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    return [(p[j] - 1, j - 1) for j in range(1, m_real + 1)
            if p[j] and weights[p[j] - 1][j - 1] > 0]


def reconcile(invoices, bank, method="reference_then_global", config=None):
    if method not in METHODS:
        raise ValueError(f"unknown method: {method}")
    config = config or Config()
    invoices = sorted(invoices, key=lambda r: (r["tenant_id"], r["invoice_id"]))
    bank = sorted(bank, key=lambda r: (r["booked_on"], r["tenant_id"], r["transaction_id"]))
    remaining = {(r["tenant_id"], r["invoice_id"]): r["amount_minor"] for r in invoices}
    allocations, used, candidate_edges = [], set(), set()

    def add(b, i, amount, confidence, reason):
        allocations.append({"tenant_id": b["tenant_id"], "transaction_id": b["transaction_id"],
                            "invoice_id": i["invoice_id"], "currency": b["currency"],
                            "amount_minor": amount, "payment_on": b["booked_on"],
                            "score": confidence, "reason": reason})
        remaining[(i["tenant_id"], i["invoice_id"])] -= amount

    if method in ("exact_reference", "reference_then_global"):
        for bi, b in enumerate(bank):
            candidates = [i for i in invoices if eligible(b, i, config) and references(b, i)]
            for i in candidates:
                candidate_edges.add((b["tenant_id"], b["transaction_id"], i["invoice_id"]))
            # Repeated invoice numbers belonging to several buyers are ambiguous.
            if len({normalize(i["invoice_id"]) for i in candidates}) != len(candidates):
                continue
            if len({i["customer_id"] for i in candidates}) > 1:
                continue
            balances = [remaining[(i["tenant_id"], i["invoice_id"])] for i in candidates]
            amount = b["amount_minor"]
            if len(candidates) == 1 and ((method == "exact_reference" and amount == balances[0])
                                         or (method == "reference_then_global" and amount <= balances[0])):
                add(b, candidates[0], amount, 1.0, "reference")
                used.add(bi)
            elif (method == "reference_then_global" and candidates and all(v > 0 for v in balances)
                  and sum(balances) == amount):
                for i, balance in zip(candidates, balances):
                    add(b, i, balance, 1.0, "reference_group")
                used.add(bi)

    if method != "exact_reference":
        pending = [(j, b) for j, b in enumerate(bank) if j not in used]
        open_invoices = [i for i in invoices if remaining[(i["tenant_id"], i["invoice_id"])] > 0]
        weights = []
        for _, b in pending:
            known_references = {i["invoice_id"] for i in invoices
                                if i["tenant_id"] == b["tenant_id"] and references(b, i)}
            row = []
            for i in open_invoices:
                full_amount = remaining[(i["tenant_id"], i["invoice_id"])] == b["amount_minor"]
                due_gap = abs((date.fromisoformat(b["booked_on"])
                               - date.fromisoformat(i["due_on"])).days)
                valid = eligible(b, i, config) and full_amount
                if method != "amount_date" and known_references:
                    valid = valid and i["invoice_id"] in known_references
                if method == "amount_date":
                    valid = valid and due_gap <= config.due_window_days
                if valid:
                    candidate_edges.add((b["tenant_id"], b["transaction_id"], i["invoice_id"]))
                row.append((1.0 if method == "amount_date" else score(b, i, config)) if valid else -1.0)
            weights.append(row)
        # Abstain when a bank row or an invoice has nearly tied alternatives.
        # Score thresholds are engineering defaults, not calibrated probabilities.
        safe = [[-1.0] * len(open_invoices) for _ in pending]
        threshold = 0.5 if method == "amount_date" else config.score_threshold
        for bi, row in enumerate(weights):
            for ii, weight in enumerate(row):
                if weight < threshold:
                    continue
                alternatives = [v for j, v in enumerate(row) if j != ii and v >= threshold]
                alternatives += [r[ii] for j, r in enumerate(weights) if j != bi and r[ii] >= threshold]
                if alternatives and weight - max(alternatives) <= config.ambiguity_margin:
                    continue
                safe[bi][ii] = weight
        for bi, ii in maximum_weight_assignment(safe):
            original, b = pending[bi]
            i = open_invoices[ii]
            add(b, i, b["amount_minor"], safe[bi][ii], method)
            used.add(original)

    errors = allocation_errors(invoices, bank, allocations)
    if errors:
        raise ValueError(f"allocation invariant failure: {errors}")
    allocations.sort(key=lambda a: (a["tenant_id"], a["transaction_id"], a["invoice_id"]))
    statuses = [{"tenant_id": b["tenant_id"], "transaction_id": b["transaction_id"],
                 "status": "auto" if j in used else (
                     "review" if any(e[:2] == (b["tenant_id"], b["transaction_id"]) for e in candidate_edges)
                     else "unmatched")}
                for j, b in enumerate(bank)]
    return {"method": method, "config": asdict(config), "allocations": allocations,
            "decisions": statuses, "candidate_edges": sorted(candidate_edges),
            "allocation_hash": fingerprint(allocations), "invariant_errors": errors}
