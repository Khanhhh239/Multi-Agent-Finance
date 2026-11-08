"""Bounded, unique integer transport for observed AP/AR remittance evidence.

Maximal feasible cash is not proof of identity. Economically interchangeable
single-reference invoices, conflicting references, nonunique flows and budget
overflows require review. No cost learned from labels, FIFO or arbitrary tie break.
"""

from collections import Counter, defaultdict, deque
from dataclasses import asdict
from datetime import date
from itertools import combinations

from .allocation import Config, invariant_errors, validate
from .data import fingerprint
from .ledger import positive, text
from .matching import normalize


def unique_transport(supplies, capacities, edges):
    """Edmonds-Karp plus a uniqueness certificate for a bounded bipartite flow.

    Saturate the smaller total, or abstain. Any different flow of the same
    total must decrease at least one positive edge. Reducing each such edge's
    capacity by one and resolving therefore detects every alternative integer
    allocation, including alternatives that leave different unapplied cash.
    """
    if any(type(v) is not int or v < 0 for v in [*supplies, *capacities]):
        raise ValueError("transport capacities must be nonnegative integers")
    if max(len(supplies), len(capacities)) > 16:
        raise ValueError("transport vertex budget exceeded")
    edges = sorted(set(edges))
    n, m = len(supplies), len(capacities)
    if any(type(p) is not int or type(i) is not int or not 0 <= p < n or not 0 <= i < m for p, i in edges):
        raise ValueError("transport edge outside universe")
    target = min(sum(supplies), sum(capacities))

    def solve(limit=None):
        size, source, sink = n + m + 2, n + m, n + m + 1
        cap = [[0] * size for _ in range(size)]
        for p, amount in enumerate(supplies):
            cap[source][p] = amount
        for i, amount in enumerate(capacities):
            cap[n + i][sink] = amount
        for p, i in edges:
            cap[p][n + i] = min(supplies[p], capacities[i])
        if limit is not None:
            p, i, amount = limit
            cap[p][n + i] = amount
        residual, total = [row[:] for row in cap], 0
        while total < target:
            parents, queue = {source: None}, deque([source])
            while queue and sink not in parents:
                u = queue.popleft()
                for v, amount in enumerate(residual[u]):
                    if amount > 0 and v not in parents:
                        parents[v] = u
                        queue.append(v)
            if sink not in parents:
                break
            delta, v = target - total, sink
            while v != source:
                u = parents[v]
                delta = min(delta, residual[u][v])
                v = u
            v = sink
            while v != source:
                u = parents[v]
                residual[u][v] -= delta
                residual[v][u] += delta
                v = u
            total += delta
        return total, {(p, i): cap[p][n + i] - residual[p][n + i] for p, i in edges
                       if cap[p][n + i] > residual[p][n + i]}

    total, flow = solve()
    if total != target:
        return "infeasible", {}
    for (p, i), amount in flow.items():
        if solve((p, i, amount - 1))[0] == target:
            return "nonunique", {}
    return "unique", flow


def allocate(invoices, payments, config=None):
    config = config or Config()
    validate(invoices, "invoice")
    validate(payments, "payment")
    key = lambda r: (r["tenant_id"], r["id"])
    inv = {key(i): i for i in invoices}
    remaining = {k: i["amount_minor"] for k, i in inv.items()}
    party_index, refs_index, widths = defaultdict(list), defaultdict(list), defaultdict(set)
    for k, i in sorted(inv.items()):
        party_index[(i["tenant_id"], i["currency"], i["side"], i["party_id"])].append(k)
        number = normalize(i["invoice_number"])
        if number:
            refs_index[(i["tenant_id"], number)].append(k)
            widths[i["tenant_id"]].add(len(number.split()))
    # Solve the whole visible snapshot jointly. Chronological greedy batches
    # can commit an early ambiguous split before a later observed payment
    # supplies the constraint that makes the component unique. Eligibility
    # still uses each payment's own business date, never a future invoice.
    batches = [sorted(payments, key=lambda p: (p["payment_on"], *key(p)))]
    result, decisions, candidates = [], {}, set()

    def eligible(p, k):
        i = inv[k]
        age = (date.fromisoformat(p["payment_on"]) - date.fromisoformat(i["issued_on"])).days
        return (k[0] == p["tenant_id"] and i["currency"] == p["currency"] and i["side"] == p["side"]
                and (not p["party_id"] or p["party_id"] == i["party_id"])
                and 0 <= age <= config.max_age_days and remaining[k] > 0)

    for visible_payments in batches:
        by_p, fixed, risks = {}, {}, set()
        pmap = {key(p): p for p in visible_payments}
        for pk, p in pmap.items():
            words, known = normalize(p["reference"]).split(), set()
            for width in widths[p["tenant_id"]]:
                for start in range(len(words) - width + 1):
                    known.update(refs_index.get((p["tenant_id"], " ".join(words[start:start + width])), ()))
            remittance = p.get("remittance")
            if remittance is not None:
                if not isinstance(remittance, list) or not remittance:
                    raise ValueError("remittance must be a nonempty observed breakdown")
                exact = {}
                for row in remittance:
                    number = normalize(text(row["invoice_number"]))
                    matches = refs_index.get((p["tenant_id"], number), [])
                    positive(row["amount_minor"])
                    if len(matches) != 1 or not eligible(p, matches[0]) or matches[0] in exact:
                        risks.add(pk)
                        continue
                    exact[matches[0]] = row["amount_minor"]
                if (not exact or len({inv[k]["party_id"] for k in exact}) != 1
                        or known and known != set(exact)
                        or sum(exact.values()) > p["amount_minor"]):
                    risks.add(pk)
                known.update(exact)
                fixed[pk] = exact
            pool = party_index[(p["tenant_id"], p["currency"], p["side"], p["party_id"])]
            if known:
                valid = sorted(k for k in known if eligible(p, k))
                if (len(valid) != len(known) or len({inv[k]["party_id"] for k in valid}) != 1
                        or len({normalize(inv[k]["invoice_number"]) for k in valid}) != len(valid)):
                    decisions[pk] = {"status": "review", "reason": "reference_conflict"}
                    continue
                # A valid reference alone cannot distinguish equal obligations
                # when remittance may name the wrong existing invoice.
                if remittance is None and len(valid) == 1:
                    resolved_pool = party_index[(p["tenant_id"], p["currency"], p["side"], inv[valid[0]]["party_id"])]
                    alternatives = [k for k in resolved_pool if k != valid[0] and eligible(p, k)
                                    and remaining[k] == remaining[valid[0]]]
                    if alternatives:
                        valid += alternatives
                        risks.add(pk)
                by_p[pk] = sorted(set(valid))
            elif remittance is not None:
                decisions[pk] = {"status": "review", "reason": "remittance_conflict"}
            elif not p["party_id"]:
                decisions[pk] = {"status": "review", "reason": "unknown_party"}
            else:
                pool = [k for k in pool if eligible(p, k) and remaining[k] <= p["amount_minor"]]
                candidates.update((pk[0], pk[1], k[1]) for k in pool)
                if len(pool) > config.max_group_pool:
                    decisions[pk] = {"status": "review", "reason": "group_pool_overflow"}
                    continue
                subsets = []
                for size in range(1, config.max_group_size + 1):
                    for subset in combinations(pool, size):
                        if sum(remaining[k] for k in subset) == p["amount_minor"]:
                            subsets.append(subset)
                            if len(subsets) == 2:
                                break
                    if len(subsets) == 2:
                        break
                if len(subsets) == 1:
                    by_p[pk] = list(subsets[0])
                else:
                    decisions[pk] = {"status": "review" if pool else "unmatched",
                                     "reason": "ambiguous_subset" if subsets else "no_exact_subset"}
        by_i = defaultdict(set)
        for pk, iks in by_p.items():
            for ik in iks:
                by_i[ik].add(pk)
                candidates.add((pk[0], pk[1], ik[1]))
        unseen = set(by_p)
        while unseen:
            ps, ii, queue = set(), set(), [min(unseen)]
            while queue:
                pk = queue.pop()
                if pk in ps:
                    continue
                ps.add(pk)
                for ik in by_p[pk]:
                    ii.add(ik)
                    queue.extend(by_i[ik] - ps)
            unseen -= ps
            ps, ii = sorted(ps), sorted(ii)
            reason, flow = None, {}
            fixed_i, fixed_edges = Counter(), {}
            for pk in ps:
                for ik, amount in fixed.get(pk, {}).items():
                    fixed_i[ik] += amount
                    fixed_edges[pk, ik] = amount
            if any(pk in risks for pk in ps):
                reason = "reference_or_remittance_risk"
            elif max(len(ps), len(ii)) > config.max_group_pool:
                reason = "flow_component_overflow"
            elif any(fixed_i[ik] > remaining[ik] for ik in ii):
                reason = "remittance_overflow"
            else:
                supplies = [0 if pk in fixed else pmap[pk]["amount_minor"] for pk in ps]
                capacities = [remaining[ik] - fixed_i[ik] for ik in ii]
                edges = [(p, i) for p, pk in enumerate(ps) for i, ik in enumerate(ii)
                         if pk not in fixed and ik in by_p[pk]]
                status, solved = unique_transport(supplies, capacities, edges)
                if status != "unique":
                    reason = "flow_" + status
                else:
                    flow = {**fixed_edges, **{(ps[p], ii[i]): amount for (p, i), amount in solved.items()}}
            if reason:
                for pk in ps:
                    decisions[pk] = {"status": "review", "reason": reason}
                continue
            for (pk, ik), amount in sorted(flow.items()):
                remaining[ik] -= amount
                result.append({"tenant_id": pk[0], "payment_id": pk[1], "invoice_id": ik[1],
                               "side": pmap[pk]["side"], "currency": pmap[pk]["currency"],
                               "amount_minor": amount, "reason": "observed_remittance" if pk in fixed else "unique_transport"})
            for pk in ps:
                decisions[pk] = {"status": "auto" if any(k[0] == pk for k in flow) else "review",
                                 "reason": "unique_transport" if any(k[0] == pk for k in flow) else "no_cash_flow"}
    result.sort(key=lambda a: (a["tenant_id"], a["payment_id"], a["invoice_id"]))
    errors = invariant_errors(invoices, payments, result)
    if errors:
        raise ValueError(f"invalid transport allocation: {errors}")
    spent = Counter()
    for a in result:
        spent[a["tenant_id"], a["payment_id"]] += a["amount_minor"]
    return {"method": "constrained_flow", "allocations": result, "candidate_edges": sorted(candidates),
            "decisions": [{"tenant_id": p["tenant_id"], "payment_id": p["id"], **decisions[key(p)],
                           "unallocated_minor": p["amount_minor"] - spent[key(p)]}
                          for p in sorted(payments, key=lambda p: (p["payment_on"], *key(p)))],
            "invariant_errors": errors, "allocation_hash": fingerprint(result), "config": asdict(config)}
