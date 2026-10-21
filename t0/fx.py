"""Observed minor-unit FX quotes; exact rational arithmetic, explicit rounding.

No rate lookup, currency-scale guess, or implied quote from matching amounts.
The ratio is target MINOR units per source MINOR unit, not a major-unit rate.
"""

from .data import iso_date


def convert(amount, quote, source_currency, target_currency, effective_on, available_on):
    if type(amount) is not int or amount <= 0:
        raise ValueError("FX source amount must be a positive integer")
    if (quote["source_currency"] != source_currency or quote["target_currency"] != target_currency
            or source_currency == target_currency):
        raise ValueError("FX quote currency pair mismatch")
    n, d = quote["rate_num"], quote["rate_den"]
    if type(n) is not int or type(d) is not int or n <= 0 or d <= 0:
        raise ValueError("FX ratio must use positive integers")
    if quote["rounding"] != "half_even" or not isinstance(quote["source_ref"], str) or not quote["source_ref"].strip():
        raise ValueError("FX requires half_even rounding and observed source_ref")
    for field in ("quoted_on", "available_on"):
        iso_date(quote[field])
    iso_date(effective_on)
    iso_date(available_on)
    if (quote["quoted_on"] > effective_on or quote["available_on"] > available_on
            or quote["quoted_on"] > quote["available_on"]):
        raise ValueError("FX quote not known/effective at command cutoff")
    whole, remainder = divmod(amount * n, d)
    if 2 * remainder > d or 2 * remainder == d and whole % 2:
        whole += 1
    if whole <= 0:
        raise ValueError("FX conversion rounds to zero")
    return whole


def allocate(invoices, payments, cutoff):
    """Propose only explicitly observed cross-currency remittance breakdowns.

    No fuzzy reference/amount search or rate implied by endpoint amounts. These
    are separate proposals; the ledger checks combined consumption at commit.
    """
    from collections import Counter, defaultdict
    from .allocation import validate
    from .data import fingerprint
    from .ledger import positive, text
    from .matching import normalize
    validate(invoices, "invoice"); validate(payments, "payment")
    iso_date(cutoff)
    for rows, field in ((invoices, "issued_on"), (payments, "payment_on")):
        for row in rows:
            iso_date(row["available_on"])
            if row["available_on"] > cutoff or row[field] > cutoff:
                raise ValueError("FX allocator requires a visible input snapshot")
    index, proposed, decisions = defaultdict(list), {}, {}
    for i in invoices:
        index[i["tenant_id"], normalize(i["invoice_number"])].append(i)
    for p in payments:
        pk, edges, seen = (p["tenant_id"], p["id"]), [], set()
        try:
            breakdown = p.get("fx_remittance")
            if not isinstance(breakdown, list) or not breakdown or len(breakdown) > 16:
                raise ValueError("explicit FX remittance required; at most 16 rows")
            for row in breakdown:
                matches = index[p["tenant_id"], normalize(text(row["invoice_number"]))]
                if len(matches) != 1:
                    raise ValueError("FX invoice reference missing or ambiguous")
                i = matches[0]
                if (i["id"] in seen or not p["party_id"] or p["party_id"] != i["party_id"]
                        or p["side"] != i["side"] or i["currency"] == p["currency"]
                        or p["payment_on"] < i["issued_on"]):
                    raise ValueError("FX remittance endpoint/date/scope conflict")
                seen.add(i["id"])
                source, target = positive(row["invoice_amount_minor"]), positive(row["payment_amount_minor"])
                if target != convert(source, row["fx"], i["currency"], p["currency"], p["payment_on"], cutoff):
                    raise ValueError("FX remittance conversion mismatch")
                edges.append({"tenant_id": p["tenant_id"], "invoice_id": i["id"], "payment_id": p["id"],
                              "currency": i["currency"], "payment_currency": p["currency"], "side": p["side"],
                              "amount_minor": source, "payment_amount_minor": target, "fx": row["fx"]})
            words, known = normalize(p["reference"]).split(), set()
            for (tenant, number), matches in index.items():
                if tenant != p["tenant_id"] or not number:
                    continue
                width = len(number.split())
                if any(" ".join(words[start:start + width]) == number for start in range(len(words) - width + 1)):
                    known.update(i["id"] for i in matches)
            if known and known != seen:
                raise ValueError("FX reference conflicts with observed remittance")
            if sum(a["payment_amount_minor"] for a in edges) > p["amount_minor"]:
                raise ValueError("FX remittance payment overflow")
            proposed[pk] = edges
        except (KeyError, TypeError, ValueError) as exc:
            decisions[pk] = {"status": "review", "reason": str(exc)}
    spent, owners = Counter(), defaultdict(set)
    for pk, edges in proposed.items():
        for a in edges:
            ik = a["tenant_id"], a["invoice_id"]
            spent[ik] += a["amount_minor"]
            owners[ik].add(pk)
    bad = set()
    for i in invoices:
        ik = i["tenant_id"], i["id"]
        if spent[ik] > i["amount_minor"]:
            bad.update(owners[ik])
    result = []
    for pk, edges in sorted(proposed.items()):
        if pk in bad:
            decisions[pk] = {"status": "review", "reason": "FX competing invoice overflow"}
        else:
            result.extend(edges)
            decisions[pk] = {"status": "auto", "reason": "observed_fx_remittance"}
    result.sort(key=lambda a: (a["tenant_id"], a["payment_id"], a["invoice_id"]))
    return {"method": "observed_fx_remittance", "cutoff": cutoff, "allocations": result,
            "decisions": [{"tenant_id": t, "payment_id": p, **d} for (t, p), d in sorted(decisions.items())],
            "allocation_hash": fingerprint(result),
            "limits": "Separate observed FX proposals; combined same/foreign-currency consumption enforced by ledger commit"}
