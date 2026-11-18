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
from .matching import (
    index_invoice_number,
    normalize,
    reference_lookup_keys,
    within_fee_tolerance,
)


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
    party_index, refs_index, prefixed_refs_index, widths = (
        defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(set)
    )
    for k, i in sorted(inv.items()):
        party_index[(i["tenant_id"], i["currency"], i["side"], i["party_id"])].append(k)
        number, aliases = index_invoice_number(i["invoice_number"])
        if number:
            refs_index[(i["tenant_id"], number)].append(k)
            widths[i["tenant_id"]].add(len(number.split()))
            for alias in aliases:
                prefixed_refs_index[(i["tenant_id"], alias)].append(k)
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
            fee_tol = config.fee_tolerance_vnd if p["currency"] == "VND" else 0
            words, prefixed_keys = reference_lookup_keys(p["reference"])
            known = set()
            for width in widths[p["tenant_id"]]:
                for start in range(len(words) - width + 1):
                    known.update(refs_index.get((p["tenant_id"], " ".join(words[start:start + width])), ()))
            for token in prefixed_keys:
                known.update(refs_index.get((p["tenant_id"], token), ()))
                known.update(prefixed_refs_index.get((p["tenant_id"], token), ()))
            remittance = p.get("remittance")
            if remittance is not None:
                if not isinstance(remittance, list) or not remittance:
                    raise ValueError("remittance must be a nonempty observed breakdown")
                exact = {}
                for row in remittance:
                    number, aliases = index_invoice_number(text(row["invoice_number"]))
                    matches = refs_index.get((p["tenant_id"], number), [])
                    if not matches:
                        alias_hits = {k for alias in aliases for k in prefixed_refs_index.get((p["tenant_id"], alias), ())}
                        matches = sorted(alias_hits)
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
                    decisions[pk] = {"status": "review", "reason": "reference_conflict", "fee_minor": 0}
                    continue
                # Disambiguate equal-amount invoices from distinct billing dates/periods
                # (e.g. monthly retainers) when the bank narrative names a specific invoice_no.
                # Only hold for review when strict_same_day_equal_amount is enabled and two
                # identical same-day twin obligations share issued_on, due_on, and balance.
                if remittance is None and len(valid) == 1 and config.strict_same_day_equal_amount:
                    resolved_pool = party_index[(p["tenant_id"], p["currency"], p["side"], inv[valid[0]]["party_id"])]
                    alternatives = [
                        k for k in resolved_pool
                        if k != valid[0]
                        and eligible(p, k)
                        and remaining[k] == remaining[valid[0]]
                        and inv[k]["issued_on"] == inv[valid[0]]["issued_on"]
                        and inv[k].get("due_on") == inv[valid[0]].get("due_on")
                    ]
                    if alternatives:
                        valid += alternatives
                        risks.add(pk)
                by_p[pk] = sorted(set(valid))
            elif remittance is not None:
                decisions[pk] = {"status": "review", "reason": "remittance_conflict", "fee_minor": 0}
            elif not p["party_id"]:
                decisions[pk] = {"status": "review", "reason": "unknown_party", "fee_minor": 0}
            else:
                all_eligible = [k for k in pool if eligible(p, k)]
                candidates.update((pk[0], pk[1], k[1]) for k in all_eligible)
                candidate_pool = [k for k in all_eligible if remaining[k] <= p["amount_minor"] + fee_tol]
                if len(candidate_pool) > config.max_group_pool:
                    decisions[pk] = {"status": "review", "reason": "group_pool_overflow", "fee_minor": 0}
                    continue
                exact_pool = [k for k in candidate_pool if remaining[k] <= p["amount_minor"]]
                subsets = []
                for size in range(1, config.max_group_size + 1):
                    for subset in combinations(exact_pool, size):
                        if sum(remaining[k] for k in subset) == p["amount_minor"]:
                            subsets.append(subset)
                            if len(subsets) == 2:
                                break
                    if len(subsets) == 2:
                        break
                if not subsets and fee_tol > 0:
                    for size in range(1, config.max_group_size + 1):
                        for subset in combinations(candidate_pool, size):
                            sub_total = sum(remaining[k] for k in subset)
                            fee_gap = sub_total - p["amount_minor"]
                            if within_fee_tolerance(fee_gap, sub_total, fee_tol):
                                ordered_sub = tuple(sorted(subset, key=lambda ik: (inv[ik]["issued_on"], inv[ik]["id"])))
                                if remaining[ordered_sub[-1]] > fee_gap:
                                    subsets.append(ordered_sub)
                                    if len(subsets) == 2:
                                        break
                        if len(subsets) == 2:
                            break
                if len(subsets) == 1:
                    by_p[pk] = list(subsets[0])
                else:
                    decisions[pk] = {"status": "review" if all_eligible else "unmatched",
                                     "reason": "ambiguous_subset" if subsets else "no_exact_subset",
                                     "fee_minor": 0}
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
            reason, flow, edge_fees = None, {}, {}
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
            elif len(ps) == 1 and ps[0] not in fixed and len(ii) > 1:
                pk0 = ps[0]
                fee_tol = config.fee_tolerance_vnd if pmap[pk0]["currency"] == "VND" else 0
                total_cap = sum(remaining[ik] for ik in ii)
                fee_gap = total_cap - pmap[pk0]["amount_minor"]
                ordered_ii = sorted(ii, key=lambda ik: (inv[ik]["issued_on"], inv[ik]["id"]))
                if within_fee_tolerance(fee_gap, total_cap, fee_tol) and remaining[ordered_ii[-1]] > fee_gap:
                    for ik in ordered_ii[:-1]:
                        flow[pk0, ik] = remaining[ik]
                    flow[pk0, ordered_ii[-1]] = remaining[ordered_ii[-1]] - fee_gap
                    edge_fees[pk0, ordered_ii[-1]] = fee_gap
                else:
                    supplies = [pmap[pk0]["amount_minor"]]
                    capacities = [remaining[ik] for ik in ii]
                    edges = [(0, i) for i, ik in enumerate(ii) if ik in by_p[pk0]]
                    status, solved = unique_transport(supplies, capacities, edges)
                    if status != "unique":
                        reason = "flow_" + status
                    else:
                        flow = {(ps[p], ii[i]): amount for (p, i), amount in solved.items()}
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
                    for (p_idx, i_idx), amount in solved.items():
                        pk_e, ik_e = ps[p_idx], ii[i_idx]
                        fee_tol = config.fee_tolerance_vnd if pmap[pk_e]["currency"] == "VND" else 0
                        if (len(by_p[pk_e]) == 1 and len(by_i[ik_e]) == 1
                                and amount == pmap[pk_e]["amount_minor"]):
                            fee_gap = remaining[ik_e] - amount
                            if within_fee_tolerance(fee_gap, remaining[ik_e], fee_tol):
                                edge_fees[pk_e, ik_e] = fee_gap
            if reason:
                for pk in ps:
                    decisions[pk] = {"status": "review", "reason": reason, "fee_minor": 0}
                continue
            for (pk, ik), amount in sorted(flow.items()):
                remaining[ik] -= amount
                result.append({"tenant_id": pk[0], "payment_id": pk[1], "invoice_id": ik[1],
                               "side": pmap[pk]["side"], "currency": pmap[pk]["currency"],
                               "amount_minor": amount, "fee_minor": edge_fees.get((pk, ik), 0),
                               "reason": "observed_remittance" if pk in fixed else "unique_transport"})
            for pk in ps:
                pk_fee = sum(fee for (p_key, _), fee in edge_fees.items() if p_key == pk)
                decisions[pk] = {"status": "auto" if any(k[0] == pk for k in flow) else "review",
                                 "reason": "unique_transport" if any(k[0] == pk for k in flow) else "no_cash_flow",
                                 "fee_minor": pk_fee}
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
