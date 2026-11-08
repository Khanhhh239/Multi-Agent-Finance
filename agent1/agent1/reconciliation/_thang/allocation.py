"""Bounded invoice-payment allocation, explicit direction, no labels or bank oracle.

References can justify partial payment/overpayment. Amount-only groups need a
known party, a unique exact subset and no competing payment. No forced FIFO.
"""

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from itertools import combinations

from .data import fingerprint, iso_date
from .ledger import compatible, positive, scope, text
from .matching import normalize


@dataclass(frozen=True)
class Config:
    max_age_days: int = 120
    max_group_size: int = 3
    max_group_pool: int = 12

    def __post_init__(self):
        if any(type(v) is not int or v < 1 for v in asdict(self).values()):
            raise ValueError("allocation budgets must be positive integers")
        if self.max_group_size > self.max_group_pool or self.max_group_pool > 16:
            raise ValueError("group_size <= group_pool <= 16 required")


def validate(rows, kind):
    seen = set()
    for r in rows:
        scope(r)
        positive(r["amount_minor"])
        key = r["tenant_id"], text(r["id"])
        if key in seen:
            raise ValueError(f"duplicate {kind} identity")
        seen.add(key)
        if r["side"] not in ("AP", "AR") or not isinstance(r["party_id"], str):
            raise ValueError("explicit AP/AR and string party_id required")
        iso_date(r["issued_on"] if kind == "invoice" else r["payment_on"])
        if kind == "invoice":
            text(r["party_id"])
            text(r["invoice_number"])
        elif not isinstance(r["reference"], str):
            raise ValueError("reference must be a string")


def invariant_errors(invoices, payments, allocations):
    inv = {(r["tenant_id"], r["id"]): r for r in invoices}
    pay = {(r["tenant_id"], r["id"]): r for r in payments}
    by_i, by_p, seen, errors = Counter(), Counter(), set(), []
    for a in allocations:
        try:
            positive(a["amount_minor"])
            t, i, p = a["tenant_id"], a["invoice_id"], a["payment_id"]
            if (t, i, p) in seen:
                raise ValueError("duplicate edge")
            seen.add((t, i, p))
            ir, pr = inv[(t, i)], pay[(t, p)]
            # Unknown payment party may be resolved only from observed evidence.
            compatible(ir, {**pr, "party_id": pr["party_id"] or ir["party_id"]})
            if a["currency"] != ir["currency"] or a["side"] != ir["side"]:
                raise ValueError("allocation currency/side mismatch")
            if pr["payment_on"] < ir["issued_on"]:
                raise ValueError("payment before invoice issue")
            by_i[(t, i)] += a["amount_minor"]
            by_p[(t, p)] += a["amount_minor"]
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(str(exc))
    if any(v > inv[k]["amount_minor"] for k, v in by_i.items()):
        errors.append("invoice overflow")
    if any(v > pay[k]["amount_minor"] for k, v in by_p.items()):
        errors.append("payment overflow")
    return errors


def allocate(invoices, payments, config=None, *, groups=True, overpayment=True):
    config = config or Config()
    validate(invoices, "invoice")
    validate(payments, "payment")
    inv = sorted(invoices, key=lambda r: (r["tenant_id"], r["id"]))
    pay = sorted(payments, key=lambda r: (r["payment_on"], r["tenant_id"], r["id"]))
    remaining = {(r["tenant_id"], r["id"]): r["amount_minor"] for r in inv}
    party_blocks = defaultdict(list)
    ref_index, ref_lengths = defaultdict(list), defaultdict(set)
    for i in inv:
        party_blocks[(i["tenant_id"], i["currency"], i["side"], i["party_id"])].append(i)
        needle = normalize(i["invoice_number"])
        if needle:
            ref_index[(i["tenant_id"], needle)].append(i)
            ref_lengths[i["tenant_id"]].add(len(needle.split()))
    allocations, decisions, candidates = [], {}, set()

    def key(r):
        return r["tenant_id"], r["id"]

    def eligible(p, i):
        age = (date.fromisoformat(p["payment_on"]) - date.fromisoformat(i["issued_on"])).days
        return (0 <= age <= config.max_age_days
                and (not p["party_id"] or p["party_id"] == i["party_id"]))

    def add(p, proposal, reason):
        for i, amount in proposal:
            remaining[key(i)] -= amount
            allocations.append({"tenant_id": p["tenant_id"], "payment_id": p["id"],
                                "invoice_id": i["id"], "currency": p["currency"],
                                "side": p["side"], "amount_minor": amount, "reason": reason})
        decisions[key(p)] = {"status": "auto", "reason": reason}

    # Same-day conflicting reference requests are reviewed together. Ordering IDs
    # must not decide which receipt owns a limited remaining invoice balance.
    days = defaultdict(list)
    for p in pay:
        days[p["payment_on"]].append(p)
    for day_payments in days.values():
        proposed, no_reference = [], []
        for p in day_payments:
            words = normalize(p["reference"]).split()
            known_ids = {}
            for width in ref_lengths[p["tenant_id"]]:
                for start in range(len(words) - width + 1):
                    token = " ".join(words[start:start + width])
                    for i in ref_index.get((p["tenant_id"], token), ()):
                        known_ids[key(i)] = i
            known = list(known_ids.values())
            refs = [i for i in known if i["currency"] == p["currency"] and i["side"] == p["side"]
                    and eligible(p, i) and remaining[key(i)] > 0]
            for i in refs:
                candidates.add((p["tenant_id"], p["id"], i["id"]))
            if known:
                # A conflicting, paid, or stale explicit reference blocks fallback.
                if (len(refs) != len(known) or len({i["party_id"] for i in refs}) != 1
                        or len({normalize(i["invoice_number"]) for i in known}) != len(known)):
                    decisions[key(p)] = {"status": "review", "reason": "reference_conflict"}
                    continue
                total = sum(remaining[key(i)] for i in refs)
                if len(refs) == 1 and (p["amount_minor"] <= total or overpayment):
                    proposed.append((p, [(refs[0], min(total, p["amount_minor"]))], "reference"))
                elif len(refs) > 1 and (p["amount_minor"] == total or
                                      overpayment and p["amount_minor"] > total):
                    proposed.append((p, [(i, remaining[key(i)]) for i in refs], "reference_group"))
                else:
                    decisions[key(p)] = {"status": "review", "reason": "underdetermined_reference_amount"}
            else:
                no_reference.append(p)
        sums = Counter()
        for _, proposal, _ in proposed:
            for i, amount in proposal:
                sums[key(i)] += amount
        conflicts = {k for k, amount in sums.items() if amount > remaining[k]}
        for p, proposal, reason in proposed:
            if any(key(i) in conflicts for i, _ in proposal):
                decisions[key(p)] = {"status": "review", "reason": "competing_references"}
            else:
                add(p, proposal, reason)
        amount_proposals = []
        for p in no_reference:
            if not p["party_id"]:
                decisions[key(p)] = {"status": "review", "reason": "unknown_party"}
                continue
            pool = [i for i in party_blocks[(p["tenant_id"], p["currency"], p["side"], p["party_id"])]
                    if eligible(p, i) and 0 < remaining[key(i)] <= p["amount_minor"]]
            for i in pool:
                candidates.add((p["tenant_id"], p["id"], i["id"]))
            if len(pool) > config.max_group_pool:
                decisions[key(p)] = {"status": "review", "reason": "group_pool_overflow"}
                continue
            solutions = []
            for size in range(1, (config.max_group_size if groups else 1) + 1):
                for subset in combinations(pool, size):
                    if sum(remaining[key(i)] for i in subset) == p["amount_minor"]:
                        solutions.append(subset)
                        if len(solutions) == 2:
                            break
                if len(solutions) == 2:
                    break
            if len(solutions) == 1:
                amount_proposals.append((p, solutions[0]))
            else:
                decisions[key(p)] = {"status": "review" if pool else "unmatched",
                                     "reason": "ambiguous_subset" if solutions else "no_exact_subset"}
        claims = Counter(key(i) for _, subset in amount_proposals for i in subset)
        for p, subset in amount_proposals:
            if any(claims[key(i)] > 1 for i in subset):
                decisions[key(p)] = {"status": "review", "reason": "competing_subsets"}
            else:
                add(p, [(i, remaining[key(i)]) for i in subset], "unique_amount_group")
    allocations.sort(key=lambda a: (a["tenant_id"], a["payment_id"], a["invoice_id"]))
    errors = invariant_errors(invoices, payments, allocations)
    if errors:
        raise ValueError(f"invalid allocation: {errors}")
    spent = Counter()
    for a in allocations:
        spent[(a["tenant_id"], a["payment_id"])] += a["amount_minor"]
    return {"allocations": allocations,
            "decisions": [{"tenant_id": p["tenant_id"], "payment_id": p["id"], **decisions[key(p)],
                           "unallocated_minor": p["amount_minor"] - spent[key(p)]} for p in pay],
            "candidate_edges": sorted(candidates), "invariant_errors": errors,
            "allocation_hash": fingerprint(allocations), "config": asdict(config)}
