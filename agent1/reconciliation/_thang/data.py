"""Versioned input contracts, as-of selection, and allocation invariants."""

from collections import defaultdict
import csv
from datetime import date
import hashlib
import json
import math
from pathlib import Path


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def iso_date(value):
    if not isinstance(value, str):
        raise ValueError("dates must be YYYY-MM-DD strings")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("dates must use YYYY-MM-DD")
    return parsed


def json_object(pairs):
    """Do not silently discard repeated fields, including in nested objects."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError(f"nonfinite JSON number: {value}")


def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        invalid_constant(value)
    return number


def loads_json(value, *, parse_float=finite_float):
    return json.loads(value, object_pairs_hook=json_object, parse_constant=invalid_constant,
                      parse_float=parse_float)


def read_json(path):
    try:
        return loads_json(Path(path).read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from exc


def read_jsonl(path, *, parse_float=finite_float):
    with Path(path).open(encoding="utf-8-sig") as handle:
        rows = []
        for index, line in enumerate(handle, 1):
            if line.strip():
                try:
                    row = loads_json(line, parse_float=parse_float)
                    if not isinstance(row, dict):
                        raise ValueError("expected a JSON object")
                except ValueError as exc:
                    raise ValueError(f"{path}:{index}: {exc}") from exc
                rows.append(row)
        return rows


def read_csv_rows(path):
    """Yield lossless CSV objects; ambiguous headers/row widths fail closed."""
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        fields = reader.fieldnames
        if not fields or any(not f.strip() for f in fields) or len(fields) != len(set(fields)):
            raise ValueError(f"{path}: missing/empty/duplicate CSV header")
        try:
            for row in reader:
                if None in row or any(v is None for v in row.values()) or list(row.values()) == fields:
                    raise ValueError(f"{path}:{reader.line_num}: malformed CSV row or repeated header")
                yield row
        except csv.Error as exc:
            raise ValueError(f"{path}:{reader.line_num}: {exc}") from exc


def guard_matching_source(directory):
    """Keep inspection-only snapshots out of the invoice matching CLI."""
    path = Path(directory) / "source_manifest.json"
    if path.exists():
        manifest = read_json(path)
        if manifest.get("use_policy") == "inspection_only_excluded_from_matching":
            raise ValueError("Source excluded from matching; see the source manifest and T0 source-audit results")


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(canonical(row) + "\n" for row in rows), encoding="utf-8")


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
                    + "\n", encoding="utf-8")


def prepare_experiment_output(path):
    """Never reuse a complete or interrupted experiment directory."""
    path = Path(path)
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError("Experiment output is not empty; choose a new --output")
    path.mkdir(parents=True, exist_ok=True)
    return path


def snapshot(rows, kind, cutoff):
    """Fail closed on conflicting visible versions; keep errors out of matching.

    Availability is checked before business validation so future revisions cannot
    alter an older snapshot. Duplicate identical deliveries are idempotent.
    Currency amounts are integers in each currency's minor unit, never floats.
    """
    iso_date(cutoff)
    id_field = {"invoices": "invoice_id", "bank": "transaction_id"}[kind]
    grouped = defaultdict(lambda: defaultdict(list))
    errors, duplicates, future, blocked = [], 0, 0, set()
    seen = set()
    for index, raw in enumerate(rows):
        identity = None
        try:
            available = raw["available_on"]
            iso_date(available)
            if available > cutoff:
                future += 1
                continue
            for field in ("tenant_id", id_field):
                if not isinstance(raw[field], str) or not raw[field].strip():
                    raise ValueError(f"invalid {field}")
            identity = (raw["tenant_id"], raw[id_field])
            if type(raw["version"]) is not int or raw["version"] < 1:
                raise ValueError("version must be a positive integer")
            token = canonical(raw)
            if token in seen:
                duplicates += 1
                continue
            seen.add(token)
            grouped[(raw["tenant_id"], raw[id_field])][raw["version"]].append(raw)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append({"row": index, "key": list(identity) if identity else None, "reason": str(exc)})
            if identity:
                blocked.add(identity)

    selected = []
    for key, versions in sorted(grouped.items()):
        if key in blocked:
            continue
        try:
            if any(len(values) != 1 for values in versions.values()):
                raise ValueError("conflicting payloads for one record/version")
            ordered = [versions[v][0] for v in sorted(versions)]
            if any(a["available_on"] > b["available_on"]
                   for a, b in zip(ordered, ordered[1:])):
                raise ValueError("version availability goes backwards")
            # Validate all visible revisions; a malformed newest revision must
            # not silently resurrect the previous one.
            for row in ordered:
                for field in ("effective_on", "issued_on", "due_on") if kind == "invoices" else ("effective_on", "booked_on"):
                    iso_date(row[field])
                if type(row["amount_minor"]) is not int or row["amount_minor"] <= 0:
                    raise ValueError("only positive integer receipt/invoice amounts supported")
                if (not isinstance(row["currency"], str) or len(row["currency"]) != 3
                        or not row["currency"].isascii() or not row["currency"].isupper()
                        or not row["currency"].isalpha()):
                    raise ValueError("currency must be a three-letter uppercase code")
                for field in (("customer_id", "customer_name") if kind == "invoices"
                              else ("customer_id", "counterparty", "reference")):
                    if not isinstance(row[field], str):
                        raise ValueError(f"{field} must be a string")
                if kind == "invoices" and not row["customer_id"]:
                    raise ValueError("invoice customer_id is required")
                if kind == "invoices" and row["due_on"] < row["issued_on"]:
                    raise ValueError("due_on precedes issued_on")
            active = [row for row in ordered if row["effective_on"] <= cutoff]
            if active:
                row = active[-1]
                business_date = row["issued_on"] if kind == "invoices" else row["booked_on"]
                if business_date <= cutoff:
                    selected.append(dict(row))
                else:
                    future += 1
            else:
                future += 1
        except (KeyError, TypeError, ValueError) as exc:
            errors.append({"key": list(key), "reason": str(exc)})
    return selected, {"input_rows": len(rows), "selected": len(selected),
                      "duplicate_deliveries": duplicates, "future_rows": future,
                      "quarantined": errors}


def allocation_errors(invoices, bank, allocations):
    inv = {(r["tenant_id"], r["invoice_id"]): r for r in invoices}
    tx = {(r["tenant_id"], r["transaction_id"]): r for r in bank}
    invoice_used, bank_used = defaultdict(int), defaultdict(int)
    errors, seen = [], set()
    for a in allocations:
        ik = (a["tenant_id"], a["invoice_id"])
        bk = (a["tenant_id"], a["transaction_id"])
        edge = (*bk, a["invoice_id"])
        if edge in seen:
            errors.append("duplicate allocation edge")
        seen.add(edge)
        if ik not in inv or bk not in tx:
            errors.append("unknown or cross-tenant endpoint")
            continue
        if type(a["amount_minor"]) is not int or a["amount_minor"] <= 0:
            errors.append("non-positive/non-integer allocation")
            continue
        if not (a["currency"] == inv[ik]["currency"] == tx[bk]["currency"]):
            errors.append("cross-currency allocation")
        if tx[bk]["booked_on"] < inv[ik]["issued_on"]:
            errors.append("allocation before invoice issued")
        if a.get("payment_on") != tx[bk]["booked_on"]:
            errors.append("payment_on differs from bank booked_on")
        invoice_used[ik] += a["amount_minor"]
        bank_used[bk] += a["amount_minor"]
    if any(value > inv[key]["amount_minor"] for key, value in invoice_used.items()):
        errors.append("invoice over-allocated")
    if any(value > tx[key]["amount_minor"] for key, value in bank_used.items()):
        errors.append("receipt over-allocated")
    return errors


def save_receipt_dataset(directory, generated):
    """Create an immutable instance; identical replays do not rewrite raw files."""
    directory = Path(directory)
    invoices, bank, truth, manifest = generated
    expected = {"invoices.jsonl": invoices, "bank.jsonl": bank, "truth.jsonl": truth,
                "manifest.json": manifest}
    for name, value in expected.items():
        path = directory / name
        if path.exists():
            existing = (read_json(path) if name == "manifest.json"
                        else read_jsonl(path))
            if existing != value:
                raise ValueError(f"dataset already exists with different contents: {path}; choose a new --output")
    for name, rows in (("invoices", invoices), ("bank", bank), ("truth", truth)):
        path = directory / f"{name}.jsonl"
        if not path.exists():
            write_jsonl(path, rows)
    if not (directory / "manifest.json").exists():
        write_json(directory / "manifest.json", manifest)
