"""Historical MoneyVis source audit, outside the current T0 development path.

Run from the repo root with python -m scripts.archive.t0.audit_t0_moneyvis.
"""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import urllib.request

from t0.data import write_json

ROOT = Path(__file__).resolve().parents[3]

COMMIT = "9fdd14e397ea309f0f52c5ff9d0a99c7ab4ff124"
CSV_URL = f"https://raw.githubusercontent.com/thevisgroup/MoneyVis/{COMMIT}/data/data.csv"
SOURCE_PAGE = "https://data.mendeley.com/datasets/dnxtg6n4rv/1"
PAPER = "https://doi.org/10.2312/evs.20231052"
HEADERS = ["Transaction Date", "Transaction Type", "Sort Code", "Account Number",
           "Transaction Description", "Debit Amount", "Credit Amount", "Balance"]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def download_moneyvis(destination):
    """Preserve a pinned author snapshot only for inspection, not benchmark use."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    raw, manifest_path = destination / "moneyvis.csv", destination / "source_manifest.json"
    if raw.exists() or manifest_path.exists():
        if not (raw.exists() and manifest_path.exists()):
            raise ValueError("Incomplete existing snapshot; use a new output directory")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("csv_url") != CSV_URL or manifest.get("sha256") != sha256(raw.read_bytes()):
            raise ValueError("Existing snapshot differs; refusing to overwrite raw")
        return manifest
    req = urllib.request.Request(CSV_URL, headers={"User-Agent": "FinanceProject-T0-Audit/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = response.read(2_000_001)
        if len(payload) > 2_000_000:
            raise ValueError("CSV exceeds 2 MB audit download limit")
        if next(csv.reader(io.StringIO(payload.decode("utf-8-sig"))), None) != HEADERS:
            raise ValueError("Unexpected MoneyVis CSV schema; raw not saved")
        manifest = {
            "source_id": "moneyvis-author-csv", "kind": "real_source_candidate",
            "source_page": SOURCE_PAGE, "paper": PAPER, "csv_url": CSV_URL,
            "commit": COMMIT, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "final_url": response.url, "bytes": len(payload), "sha256": sha256(payload),
            "reality_basis": "Authors describe anonymized real retail banking data; not independently verified",
            "license": "Mendeley v1 declares CC BY 4.0; transfer to this GitHub snapshot unverified",
            "use_policy": "inspection_only_excluded_from_matching",
            "limitations": ["retail banking, not SME receivables", "no invoices or allocation labels",
                            "no explicit currency, availability history or transaction identifier"],
        }
    # Exclusive creation prevents accidentally replacing a concurrently created snapshot.
    with raw.open("xb") as handle:
        handle.write(payload)
    with manifest_path.open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return manifest


def decimal_money(text):
    """Exact source decimal units; no inference of currency or ISO minor units."""
    try:
        value = Decimal(text)
        if not value.is_finite() or value.as_tuple().exponent < -2:
            raise ValueError("Expected finite decimal with at most two fractional places")
        return value
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal amount") from exc


def audit_moneyvis(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "source_manifest.json").read_text(encoding="utf-8"))
    payload = (directory / "moneyvis.csv").read_bytes()
    if (manifest.get("source_id") != "moneyvis-author-csv"
            or manifest.get("sha256") != sha256(payload)
            or manifest.get("bytes") != len(payload)):
        raise ValueError("Raw source identity/hash/size does not match manifest")
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    if reader.fieldnames != HEADERS:
        raise ValueError("Unexpected MoneyVis CSV schema")
    rows = list(reader)
    dates, parsed, errors, types, accounts = [], [], [], Counter(), set()
    tokens = Counter()
    credits = debits = Decimal(0)
    for number, row in enumerate(rows, 2):
        try:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Malformed CSV row")
            tokens[tuple(row[h] for h in HEADERS)] += 1
            day = datetime.strptime(row[HEADERS[0]], "%d/%m/%Y").date().isoformat()
            debit = decimal_money(row["Debit Amount"]) if row["Debit Amount"] else Decimal(0)
            credit = decimal_money(row["Credit Amount"]) if row["Credit Amount"] else Decimal(0)
            balance = decimal_money(row["Balance"])
            if debit < 0 or credit < 0 or (debit > 0 and credit > 0) or debit + credit == 0:
                raise ValueError("Expected exactly one positive debit or credit")
            dates.append(day)
            parsed.append((day, credit - debit, balance))
            credits += credit
            debits += debit
            types[row["Transaction Type"]] += 1
            accounts.add((row["Sort Code"], row["Account Number"]))
        except (TypeError, ValueError) as exc:
            # Preserve positions; never bridge invalid rows in a balance equation.
            parsed.append(None)
            errors.append({"csv_line": number, "reason": str(exc)})
    transitions = {"checked": 0, "reverse_storage_balance_equation_pass": 0,
                   "forward_storage_balance_equation_pass": 0,
                   "reverse_mismatch_csv_lines": []}
    for index, (left, right) in enumerate(zip(parsed, parsed[1:]), 2):
        if left is None or right is None:
            continue
        transitions["checked"] += 1
        reverse_ok = left[2] - right[2] == left[1]
        transitions["reverse_storage_balance_equation_pass"] += int(reverse_ok)
        transitions["forward_storage_balance_equation_pass"] += int(right[2] - left[2] == right[1])
        if not reverse_ok:
            transitions["reverse_mismatch_csv_lines"].append([index, index + 1])
    return {
        "audit_version": 1, "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": manifest, "audit_code_sha256": sha256(Path(__file__).read_bytes()),
        "scope": "Full pinned CSV; offline source-quality and task-fit audit only",
        "profile": {
            "columns": HEADERS, "rows": len(rows), "valid_rows": len(dates), "errors": errors,
            "date_min": min(dates) if dates else None, "date_max": max(dates) if dates else None,
            "dates_nondecreasing_in_file": all(a <= b for a, b in zip(dates, dates[1:])),
            "dates_nonincreasing_in_file": all(a >= b for a, b in zip(dates, dates[1:])),
            "account_count": len(accounts), "transaction_type_counts": dict(sorted(types.items())),
            "identical_row_occurrences_beyond_first": sum(n - 1 for n in tokens.values()),
            "duplicate_interpretation": "No transaction ID: identical rows not automatically removed",
            "credit_total_source_decimal_units": str(credits),
            "debit_total_source_decimal_units": str(debits), "currency": None,
            "balance_transitions": transitions,
        },
        "matching_gate": {"accepted": False, "status": "excluded",
            "reasons": ["missing_invoice_table", "missing_independent_allocation_truth",
                        "retail_domain_differs_from_SME_AR", "missing_explicit_currency",
                        "missing_transaction_id_and_availability_history",
                        "reuse_license_for_this_snapshot_unverified"],
            "action": "Do not normalize into matcher inputs, train, tune or rank methods on this source"},
        "matcher_runs": 0, "precision": None, "recall": None,
        "limitations": ["Balance equations inspect adjacent source rows; no sorting, fixes or deduplication",
                        "No opening balance supplied: first chronological transaction not checked",
                        "Passing balance equations does not establish statement completeness or matching accuracy",
                        "No raw account identifiers or descriptions included in this report"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/T0/raw/source_candidates/moneyvis")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--download", action="store_true", help="Explicitly allow download if raw is absent")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Output exists; choose a new --output")
    if args.download:
        download_moneyvis(args.input)
    report = audit_moneyvis(args.input)
    write_json(args.output, report)
    print(f"Historical MoneyVis audit: rows={report['profile']['rows']}; matcher_runs=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
