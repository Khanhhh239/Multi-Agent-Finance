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
from .matching import (
    DEFAULT_FEE_TOLERANCE_VND,
    index_invoice_number,
    normalize,
    reference_lookup_keys,
    within_fee_tolerance,
)


@dataclass(frozen=True)
class Config:
    max_age_days: int = 120
    max_group_size: int = 3
    max_group_pool: int = 12
    fee_tolerance_vnd: int = DEFAULT_FEE_TOLERANCE_VND
    strict_same_day_equal_amount: bool = True

    def __post_init__(self):
        for v in (self.max_age_days, self.max_group_size, self.max_group_pool):
            if type(v) is not int or v < 1:
                raise ValueError("allocation budgets must be positive integers")
        if type(self.fee_tolerance_vnd) is not int or self.fee_tolerance_vnd < 0:
            raise ValueError("fee_tolerance_vnd must be a nonnegative integer")
        if type(self.strict_same_day_equal_amount) is not bool:
            raise ValueError("strict_same_day_equal_amount must be a boolean")
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
    ref_index, prefixed_ref_index, ref_lengths = defaultdict(list), defaultdict(list), defaultdict(set)
    for i in inv:
        party_blocks[(i["tenant_id"], i["currency"], i["side"], i["party_id"])].append(i)
        needle, aliases = index_invoice_number(i["invoice_number"])
        if needle:
            ref_index[(i["tenant_id"], needle)].append(i)
            ref_lengths[i["tenant_id"]].add(len(needle.split()))
            for alias in aliases:
                prefixed_ref_index[(i["tenant_id"], alias)].append(i)
    allocations, decisions, candidates = [], {}, set()

    def key(r):
        return r["tenant_id"], r["id"]

    def eligible(p, i):
        age = (date.fromisoformat(p["payment_on"]) - date.fromisoformat(i["issued_on"])).days
        return (0 <= age <= config.max_age_days
                and (not p["party_id"] or p["party_id"] == i["party_id"]))

    def add(p, proposal, reason):
        total_fee = 0
        for item in proposal:
            i, amount = item[0], item[1]
            fee_minor = item[2] if len(item) > 2 else 0
            total_fee += fee_minor
            remaining[key(i)] -= amount
            allocations.append({"tenant_id": p["tenant_id"], "payment_id": p["id"],
                                "invoice_id": i["id"], "currency": p["currency"],
                                "side": p["side"], "amount_minor": amount,
                                "fee_minor": fee_minor, "reason": reason})
        decisions[key(p)] = {"status": "auto", "reason": reason, "fee_minor": total_fee}

    # Same-day conflicting reference requests are reviewed together. Ordering IDs
    # must not decide which receipt owns a limited remaining invoice balance.
    days = defaultdict(list)
    for p in pay:
        days[p["payment_on"]].append(p)
    for day_payments in days.values():
        proposed, no_reference = [], []
        for p in day_payments:
            fee_tol = config.fee_tolerance_vnd if p["currency"] == "VND" else 0
            words, prefixed_keys = reference_lookup_keys(p["reference"])
            known_ids = {}
            for width in ref_lengths[p["tenant_id"]]:
                for start in range(len(words) - width + 1):
                    token = " ".join(words[start:start + width])
                    for i in ref_index.get((p["tenant_id"], token), ()):
                        known_ids[key(i)] = i
            for token in prefixed_keys:
                for i in ref_index.get((p["tenant_id"], token), ()):
                    known_ids[key(i)] = i
                for i in prefixed_ref_index.get((p["tenant_id"], token), ()):
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
                    decisions[key(p)] = {"status": "review", "reason": "reference_conflict", "fee_minor": 0}
                    continue
                total = sum(remaining[key(i)] for i in refs)
                if len(refs) == 1 and (p["amount_minor"] <= total or overpayment):
                    allocated_amt = min(total, p["amount_minor"])
                    fee_gap = total - allocated_amt
                    fee_val = fee_gap if within_fee_tolerance(fee_gap, total, fee_tol) else 0
                    proposed.append((p, [(refs[0], allocated_amt, fee_val)], "reference"))
                elif len(refs) > 1 and (p["amount_minor"] == total or
                                      overpayment and p["amount_minor"] > total):
                    proposed.append((p, [(i, remaining[key(i)], 0) for i in refs], "reference_group"))
                elif len(refs) > 1 and within_fee_tolerance(total - p["amount_minor"], total, fee_tol):
                    ordered_refs = sorted(refs, key=lambda r: (r["issued_on"], r["id"]))
                    fee_gap = total - p["amount_minor"]
                    if remaining[key(ordered_refs[-1])] > fee_gap:
                        items = [(i, remaining[key(i)], 0) for i in ordered_refs[:-1]]
                        items.append((ordered_refs[-1], remaining[key(ordered_refs[-1])] - fee_gap, fee_gap))
                        proposed.append((p, items, "reference_group"))
                    else:
                        decisions[key(p)] = {"status": "review", "reason": "underdetermined_reference_amount", "fee_minor": 0}
                else:
                    decisions[key(p)] = {"status": "review", "reason": "underdetermined_reference_amount", "fee_minor": 0}
            else:
                no_reference.append(p)
        sums = Counter()
        for _, proposal, _ in proposed:
            for item in proposal:
                sums[key(item[0])] += item[1]
        conflicts = {k for k, amount in sums.items() if amount > remaining[k]}
        for p, proposal, reason in proposed:
            if any(key(item[0]) in conflicts for item in proposal):
                decisions[key(p)] = {"status": "review", "reason": "competing_references", "fee_minor": 0}
            else:
                add(p, proposal, reason)
        amount_proposals = []
        for p in no_reference:
            if not p["party_id"]:
                decisions[key(p)] = {"status": "review", "reason": "unknown_party", "fee_minor": 0}
                continue
            fee_tol = config.fee_tolerance_vnd if p["currency"] == "VND" else 0
            all_eligible = [i for i in party_blocks[(p["tenant_id"], p["currency"], p["side"], p["party_id"])]
                            if eligible(p, i) and remaining[key(i)] > 0]
            for i in all_eligible:
                candidates.add((p["tenant_id"], p["id"], i["id"]))
            pool = [i for i in all_eligible if remaining[key(i)] <= p["amount_minor"] + fee_tol]
            if len(pool) > config.max_group_pool:
                decisions[key(p)] = {"status": "review", "reason": "group_pool_overflow", "fee_minor": 0}
                continue
            exact_pool = [i for i in pool if remaining[key(i)] <= p["amount_minor"]]
            solutions = []
            for size in range(1, (config.max_group_size if groups else 1) + 1):
                for subset in combinations(exact_pool, size):
                    if sum(remaining[key(i)] for i in subset) == p["amount_minor"]:
                        solutions.append((subset, 0))
                        if len(solutions) == 2:
                            break
                if len(solutions) == 2:
                    break
            if not solutions and fee_tol > 0:
                for size in range(1, (config.max_group_size if groups else 1) + 1):
                    for subset in combinations(pool, size):
                        sub_total = sum(remaining[key(i)] for i in subset)
                        fee_gap = sub_total - p["amount_minor"]
                        if within_fee_tolerance(fee_gap, sub_total, fee_tol):
                            ordered_sub = tuple(sorted(subset, key=lambda r: (r["issued_on"], r["id"])))
                            if remaining[key(ordered_sub[-1])] > fee_gap:
                                solutions.append((ordered_sub, fee_gap))
                                if len(solutions) == 2:
                                    break
                    if len(solutions) == 2:
                        break
            if len(solutions) == 1:
                amount_proposals.append((p, solutions[0][0], solutions[0][1]))
            else:
                decisions[key(p)] = {"status": "review" if all_eligible else "unmatched",
                                     "reason": "ambiguous_subset" if solutions else "no_exact_subset",
                                     "fee_minor": 0}
        claims = Counter(key(i) for _, subset, _ in amount_proposals for i in subset)
        for p, subset, fee_gap in amount_proposals:
            if any(claims[key(i)] > 1 for i in subset):
                decisions[key(p)] = {"status": "review", "reason": "competing_subsets", "fee_minor": 0}
            elif fee_gap > 0:
                items = [(i, remaining[key(i)], 0) for i in subset[:-1]]
                items.append((subset[-1], remaining[key(subset[-1])] - fee_gap, fee_gap))
                add(p, items, "unique_amount_group")
            else:
                add(p, [(i, remaining[key(i)], 0) for i in subset], "unique_amount_group")
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
