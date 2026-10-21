"""Offline adapters for pinned research snapshots; raw policy is never changed."""

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path

from .constrained import allocate
from .data import (fingerprint, iso_date, prepare_experiment_output, read_csv_rows,
                   read_json, write_json, write_jsonl)


SCALES = {"VND": 0, "JPY": 0, "USD": 2, "EUR": 2, "GBP": 2, "CAD": 2, "INR": 2}


def minor(value, currency):
    """No implicit FX, rounding, NaN, binary floats, or guessed scale."""
    if isinstance(value, (float, bool)) or currency not in SCALES:
        raise ValueError("explicit supported scale and decimal string required")
    try:
        n = Decimal(value)
        if not n.is_finite():
            raise ValueError("amount must be finite")
        # Multiplication under Decimal's process context can round large values
        # before the integrality test. Work with the exact coefficient instead.
        sign, digits, exponent = n.as_tuple()
        coefficient = int("".join(map(str, digits)))
        shift = exponent + SCALES[currency]
        if shift >= 0:
            coefficient *= 10 ** shift
        else:
            coefficient, remainder = divmod(coefficient, 10 ** -shift)
            if remainder:
                raise ValueError("amount is not exact at currency scale")
        return -coefficient if sign else coefficient
    except InvalidOperation as exc:
        raise ValueError("invalid decimal money") from exc


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verified_source(folder, names):
    folder = Path(folder)
    manifest = read_json(folder / "source_manifest.json")
    files = {}
    for entry in manifest["files"]:
        name = entry["file"]
        if name in files:
            raise ValueError(f"duplicate source manifest entry: {name}")
        files[name] = entry
    hashes = {}
    for name in names:
        path = folder / name
        entry = files.get(name)
        if (not entry or entry.get("status") != 200 or not path.is_file()
                or digest(path) != entry["sha256"] or path.stat().st_size != entry["bytes"]):
            raise ValueError(f"raw snapshot hash/size mismatch: {name}")
        hashes[name] = entry["sha256"]
    return {"source_id": manifest["source_id"], "source": manifest["source"],
            "source_manifest_sha256": digest(folder / "source_manifest.json"), "raw_sha256": hashes}


def csv_rows(path):
    return list(read_csv_rows(path))


def normalize_finrca(tables, stage, hashes):
    """Every source row has lineage; invalid rows remain in quarantine."""
    result = {n: [] for n in ("invoices", "payments", "bank", "allocations", "quarantine")}
    for name, id_field in (("invoices", "invoice_id"), ("payments", "payment_id"),
                           ("bank_transactions", "bank_transaction_id")):
        counts = Counter(r[id_field] for r in tables[name])
        for number, r in enumerate(tables[name], 2):
            lineage = {"file": f"data/{stage}/{name}.csv", "row": number,
                       "sha256": hashes[f"data/{stage}/{name}.csv"]}
            try:
                if not r[id_field].strip() or counts[r[id_field]] != 1:
                    raise ValueError("missing or duplicate source ID")
                currency = r["payment_currency"] if name == "payments" else r["currency"]
                amount = minor(r[{"invoices": "invoice_total", "payments": "payment_amount",
                                  "bank_transactions": "amount"}[name]], currency)
                if amount <= 0:
                    raise ValueError("nonpositive amount unsupported")
                row = {"tenant_id": "FINRCA", "id": r[id_field], "currency": currency,
                       "amount_minor": amount, "lineage": lineage}
                if name in ("invoices", "payments"):
                    row.update(side="AP", party_id=r["vendor_id"])
                    if not r["vendor_id"].strip():
                        raise ValueError("missing vendor")
                if name == "invoices":
                    iso_date(r["invoice_date"])
                    iso_date(r["due_date"])
                    if r["due_date"] < r["invoice_date"] or not r["invoice_number"].strip():
                        raise ValueError("invalid due date/invoice number")
                    row.update(invoice_number=r["invoice_number"], issued_on=r["invoice_date"], due_on=r["due_date"])
                elif name == "payments":
                    iso_date(r["payment_date"])
                    row.update(payment_on=r["payment_date"], reference=r["reference_number"])
                else:
                    iso_date(r["transaction_date"])
                    iso_date(r["posted_date"])
                    if r["direction"] not in ("credit", "debit"):
                        raise ValueError("invalid bank direction")
                    row.update(direction=r["direction"], account_id=r["bank_account_id"],
                               transaction_on=r["transaction_date"], posted_on=r["posted_date"],
                               reference=r["payment_reference"])
                result["bank" if name == "bank_transactions" else name].append(row)
            except (KeyError, TypeError, ValueError) as exc:
                result["quarantine"].append({"table": name, "source_id": r.get(id_field),
                                             "lineage": lineage, "raw": r, "reasons": [str(exc)]})
    inv = {r["id"]: r for r in result["invoices"]}
    pay = {r["id"]: r for r in result["payments"]}
    valid, seen, by_i, by_p = [], Counter(), Counter(), Counter()
    for number, r in enumerate(tables["payment_allocations"], 2):
        lineage = {"file": f"data/{stage}/payment_allocations.csv", "row": number,
                   "sha256": hashes[f"data/{stage}/payment_allocations.csv"]}
        reasons = []
        try:
            i, p = inv[r["invoice_id"]], pay[r["payment_id"]]
            amount = minor(r["allocated_amount"], i["currency"])
            if amount <= 0:
                reasons.append("nonpositive_allocation")
            if i["currency"] != p["currency"]:
                reasons.append("cross_currency_unsupported")
            if i["party_id"] != p["party_id"]:
                reasons.append("cross_vendor")
            iso_date(r["allocation_date"])
            if r["allocation_date"] < max(i["issued_on"], p["payment_on"]):
                reasons.append("allocation_predates_endpoint")
            row = {"tenant_id": "FINRCA", "invoice_id": i["id"], "payment_id": p["id"],
                   "currency": i["currency"], "side": "AP", "amount_minor": amount,
                   "allocation_on": r["allocation_date"], "lineage": lineage, "reasons": reasons}
            valid.append(row)
            seen[(i["id"], p["id"])] += 1
            if i["currency"] == p["currency"] and amount > 0:
                by_i[i["id"]] += amount
                by_p[p["id"]] += amount
        except (KeyError, TypeError, ValueError) as exc:
            result["quarantine"].append({"table": "payment_allocations", "raw": r,
                                         "lineage": lineage, "reasons": [f"invalid_endpoint_or_money: {exc}"]})
    for r in valid:
        if seen[(r["invoice_id"], r["payment_id"])] > 1:
            r["reasons"].append("duplicate_allocation_pair")
        if by_i[r["invoice_id"]] > inv[r["invoice_id"]]["amount_minor"]:
            r["reasons"].append("invoice_overallocated")
        if by_p[r["payment_id"]] > pay[r["payment_id"]]["amount_minor"]:
            r["reasons"].append("payment_overallocated")
        # Observed ERP allocations are data under audit, never matcher truth.
        result["allocations"].append(r)
    raw_sums = defaultdict(Decimal)
    raw_inv = {r["invoice_id"]: r for r in tables["invoices"]}
    raw_pay = {r["payment_id"]: r for r in tables["payments"]}
    for r in tables["payment_allocations"]:
        if r["invoice_id"] in raw_inv and r["payment_id"] in raw_pay and raw_inv[r["invoice_id"]]["currency"] == raw_pay[r["payment_id"]]["payment_currency"]:
            raw_sums[r["invoice_id"]] += Decimal(r["allocated_amount"])
    result["audit"] = {
        "source_counts": {n: len(r) for n, r in tables.items()},
        "normalized_counts": {n: len(result[n]) for n in ("invoices", "payments", "bank", "allocations")},
        "quarantined_rows": len(result["quarantine"]),
        "allocation_reason_counts": dict(Counter(c for r in valid for c in r["reasons"])),
        "invoices_overallocated": sum(v > inv[k]["amount_minor"] for k, v in by_i.items()),
        "invoices_partial": sum(0 < by_i[k] < r["amount_minor"] for k, r in inv.items()),
        "raw_decimal_invoice_overallocated_comparisons": sum(raw_sums[k] > Decimal(r["invoice_total"]) for k, r in raw_inv.items()),
        "raw_nonpositive_invoice_totals": sum(Decimal(r["invoice_total"]) <= 0 for r in raw_inv.values()),
        "raw_comparison_limit": "Negative invoice totals are quarantined, not silently treated as positive invoices or inferred credit notes",
        "statement_reconciliation": statement_checks(tables["bank_statements"], tables["bank_transactions"]),
        "matching_quality": None, "bank_link_oracle_verified": False,
        "availability": "absent; static retrospective pool only"}
    return result


def statement_checks(statements, transactions):
    """Check both bank date conventions without choosing the better result."""
    currencies = defaultdict(set)
    totals = {field: defaultdict(lambda: {"debit": Decimal(0), "credit": Decimal(0)})
              for field in ("posted_date", "transaction_date")}
    for r in transactions:
        currencies[r["bank_account_id"]].add(r["currency"])
        for field in totals:
            iso_date(r[field])
            totals[field][(r["bank_account_id"], r[field][:7])][r["direction"]] += Decimal(r["amount"])
    results, prior = [], {}
    for s in sorted(statements, key=lambda r: (r["bank_account_id"], r["statement_date"])):
        account, month = s["bank_account_id"], s["statement_date"][:7]
        opening, closing = Decimal(s["opening_balance"]), Decimal(s["closing_balance"])
        row = {"statement_id": s["bank_statement_id"], "account_id": account,
               "equation_pass": opening + Decimal(s["total_credits"]) - Decimal(s["total_debits"]) == closing,
               "currency_unambiguous": len(currencies[account]) == 1,
               "opening_matches_previous_observed_close": opening == prior[account] if account in prior else None}
        for field, grouped in totals.items():
            observed = grouped[(account, month)]
            row[field + "_totals_pass"] = (len(currencies[account]) == 1 and
                observed["debit"] == Decimal(s["total_debits"]) and observed["credit"] == Decimal(s["total_credits"]))
        prior[account] = closing
        results.append(row)
    return {"statements": len(results), "equation_failures": sum(not r["equation_pass"] for r in results),
            "posted_date_total_failures": sum(not r["posted_date_totals_pass"] for r in results),
            "transaction_date_total_failures": sum(not r["transaction_date_totals_pass"] for r in results),
            "rows": results, "complete_bank_scope_verified": False}


def component_splits(stages):
    """Union all clean/corrupted allocation relations before splitting worlds."""
    parent = {}

    def root(k):
        parent.setdefault(k, k)
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for data in stages.values():
        for name, prefix in (("invoices", "I:"), ("payments", "P:")):
            for r in data[name]:
                root(prefix + r["id"])
        for r in data["allocations"]:
            a, b = root("I:" + r["invoice_id"]), root("P:" + r["payment_id"])
            parent[max(a, b)] = min(a, b)
    groups = defaultdict(list)
    for k in parent:
        groups[root(k)].append(k)
    mapping = {}
    for members in groups.values():
        group = fingerprint(sorted(members))
        split = "development" if int(group[:8], 16) % 10 < 8 else "validation"
        for member in members:
            mapping[member] = {"world_id": group, "split": split}
    return mapping


def adapt_finrca(folder, output):
    stages = ("raw_clean", "benchmark/full")
    names = [f"data/{stage}/{n}.csv" for stage in stages for n in
             ("invoices", "payments", "payment_allocations", "bank_transactions", "bank_statements")]
    provenance = verified_source(folder, names)
    data = {stage: normalize_finrca({n: csv_rows(Path(folder) / f"data/{stage}/{n}.csv") for n in
                                   ("invoices", "payments", "payment_allocations", "bank_transactions", "bank_statements")},
                                  stage, provenance["raw_sha256"]) for stage in stages}
    splits = component_splits(data)
    output = prepare_experiment_output(output)
    for stage, normalized in data.items():
        directory = output / ("clean" if stage == "raw_clean" else "corrupted")
        for name, prefix in (("invoices", "I:"), ("payments", "P:")):
            for r in normalized[name]:
                r.update(splits[prefix + r["id"]])
        for name in ("invoices", "payments", "bank", "allocations", "quarantine"):
            write_jsonl(directory / ("observed_allocations.jsonl" if name == "allocations" else name + ".jsonl"), normalized[name])
        write_json(directory / "manifest.json", {"schema": "t0-invoice-payment-v2", "side": "AP",
                   "availability": "static_retrospective", "cutoff": None,
                   "truth_exhaustive": False, "parent_source_manifest_sha256": provenance["source_manifest_sha256"]})
        proposals = allocate(normalized["invoices"], normalized["payments"])
        write_json(directory / "predictions.json", proposals)
        normalized["audit"]["proposal_counts"] = dict(Counter(r["status"] for r in proposals["decisions"]))
        normalized["audit"]["proposal_method"] = "constrained_flow"
        normalized["audit"]["proposal_invariant_errors"] = proposals["invariant_errors"]
        write_json(directory / "audit.json", normalized["audit"])
    manifest = {"schema": "t0-ap-static-v2", **provenance, "scales": SCALES,
                "use_policy": "ap_audit_and_proposals_no_verified_matching_truth",
                "feature_allowlist": {"invoices": ["id", "tenant_id", "side", "party_id", "currency", "amount_minor", "invoice_number", "issued_on"],
                                      "payments": ["id", "tenant_id", "side", "party_id", "currency", "amount_minor", "reference", "payment_on"]},
                "split_policy": "union allocation components across clean/corrupted; internal development/validation, not blind",
                "normalized_hashes": {stage: {name: fingerprint(rows) for name, rows in values.items()
                                              if isinstance(rows, list)} for stage, values in data.items()},
                "limitations": ["No confirmed bank-link oracle", "No historical pipeline availability",
                                "Observed allocations are not repair truth", "Dataset redistribution license unresolved"]}
    write_json(output / "manifest.json", manifest)
    return {"manifest": manifest, "stages": {k: v["audit"] for k, v in data.items()}}
