"""Read-only company records and links back to imports and reconciliation."""

from collections import Counter

from unidecode import unidecode

from agent1.adaptive.data import IDS, SCHEMAS, vnd
from agent1.reconciliation.pipeline import NON_AR, today


def outstanding(source):
    if not source.data.get("invoices"):
        return 0
    return sum(r["amount_open_minor"] for r in source.view(today())["invoices"].to_dict("records"))


def import_counts(before, after, kind, accepted):
    old = {r[IDS[kind]]: r for r in before.get(kind, [])}
    new = {r[IDS[kind]]: r for r in after.get(kind, [])}
    added = len(new.keys() - old.keys())
    updated = sum(old[key] != new[key] for key in old.keys() & new.keys())
    return dict(new=added, changed=updated, unchanged=max(0, accepted - added - updated))


def public_record(row, kind):
    fields = set(SCHEMAS[kind]) | {"source_file", "source_row", "source_sha256", "t9_decision_id",
                                      "known_at_time", "correction_id", "_deleted"}
    return {key: value for key, value in row.items() if key in fields}


def record_rows(source, kind):
    data = source.data
    paid, used = Counter(), Counter()
    for row in data.get("payments", []):
        if row["known_at"] <= today() and row["payment_date"] <= today():
            paid[row["invoice_id"]] += vnd(row["amount"])
            used[row.get("bank_id", "")] += vnd(row["amount"])
    effective = {}
    if kind == "invoices" and data.get("invoices"):
        effective = {r["invoice_id"]: r for r in source.view(today())["invoices"].to_dict("records")}
    result = []
    for raw in data.get(kind, []):
        row = public_record(raw, kind)
        row["identifier"] = raw[IDS[kind]]
        row["status"] = "recorded"
        if kind == "invoices":
            current = effective.get(row["identifier"])
            if current is None:
                row["status"] = "inactive"
            else:
                remaining = current["amount_open_minor"]
                row["remaining_amount"] = remaining
                row["allocated_amount"] = paid[row["identifier"]]
                row["status"] = "paid" if remaining == 0 else "partial" if row["allocated_amount"] else "open"
                if current["closure_type"] == "writeoff":
                    row["status"] = "written_off"
        elif kind == "bank":
            row["allocated_amount"] = used[row["identifier"]]
            row["remaining_amount"] = vnd(row["amount"]) - used[row["identifier"]]
            row["status"] = ("outgoing" if row["direction"] == "out" else
                             "non_ar" if row.get("component") == "cash_sale" or row.get("cash_flow_class") in NON_AR else
                             "allocated" if row["remaining_amount"] == 0 else
                             "partial" if row["allocated_amount"] else "pending")
        elif kind == "payments":
            row["status"] = "linked" if row.get("bank_id") else "unlinked"
        if row.get("known_at", "") > today():
            row["status"] = "future"
        result.append(row)
    return sorted(result, key=lambda row: row["identifier"])


def search_rows(rows, query, status, start, end, kind):
    date_field = dict(invoices="issue_date", payments="payment_date", statements="end_date",
                      invoice_events="event_date").get(kind, "date")
    query = unidecode(query).casefold().strip()
    return [row for row in rows if
            (not query or query in unidecode(" ".join(str(value) for value in row.values())).casefold())
            and (not status or row["status"] == status)
            and (not start or row.get(date_field, "") >= start)
            and (not end or row.get(date_field, "") <= end)]


def record_detail(source, kind, identifier, imports):
    data = source.data
    raw = next((r for r in data.get(kind, []) if r[IDS[kind]] == identifier), None)
    versions = [r for r in data.get("record_history", {}).get(kind, []) if r[IDS[kind]] == identifier]
    if raw is None and not versions:
        raise KeyError(identifier)
    # A deletion marker records when a receipt was reversed; it has no invoice
    # or bank identity. Keep the last real row available for audit navigation.
    seed = raw or next((row for row in reversed(versions) if not row.get("_deleted")), versions[-1])
    invoice_ids = {identifier} if kind == "invoices" else {seed["invoice_id"]} if seed.get("invoice_id") else set()
    bank_ids = {identifier} if kind == "bank" else {seed["bank_id"]} if seed.get("bank_id") else set()
    payment_ids = {identifier} if kind == "payments" else set()
    all_receipts = list(data.get("payments", []))
    # Reversed allocations remain navigable through their historical payment rows.
    seen = {r["payment_id"] for r in all_receipts}
    for row in reversed(data.get("record_history", {}).get("payments", [])):
        if row["payment_id"] not in seen and not row.get("_deleted"):
            all_receipts.append(row)
            seen.add(row["payment_id"])
    receipts = [r for r in all_receipts if r["payment_id"] in payment_ids
                or r["invoice_id"] in invoice_ids or r.get("bank_id") in bank_ids]
    invoice_ids.update(r["invoice_id"] for r in receipts)
    bank_ids.update(r["bank_id"] for r in receipts if r.get("bank_id"))
    payment_ids.update(r["payment_id"] for r in receipts)
    decisions = [r for r in source.history() if r.get("bank_id") in bank_ids
                 or any(a["invoice_id"] in invoice_ids or a["payment_id"] in bank_ids for a in r.get("allocations", []))
                 or any(c.get("kind") == kind and c.get("identifier") == identifier for c in r.get("changes", []))]
    linked = []
    for target, ids in (("invoices", invoice_ids), ("bank", bank_ids), ("payments", payment_ids)):
        rows = all_receipts if target == "payments" else data.get(target, [])
        linked.extend(dict(kind=target, identifier=r[IDS[target]], record=public_record(r, target))
                      for r in rows if r[IDS[target]] in ids and (target, r[IDS[target]]) != (kind, identifier))
    return dict(kind=kind, identifier=identifier, record=public_record(seed, kind), deleted=raw is None,
                versions=[public_record(r, kind) for r in versions], related=linked,
                decisions=decisions,
                imports=[{k: v for k, v in batch.items() if k != "record_ids"} for batch in imports
                         if batch["kind"] == kind and identifier in batch.get("record_ids", [])])
