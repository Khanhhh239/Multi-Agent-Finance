"""Historical public-source survey; inspection never becomes matching labels.

Run from the repo root with python -m scripts.archive.t0.audit_t0_source_survey.
"""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
from decimal import Decimal
import io
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

from t0.data import fingerprint, write_json
from .audit_t0_moneyvis import decimal_money, sha256

ROOT = Path(__file__).resolve().parents[3]


DC = "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Government_Operations/MapServer/17"
DC_WHERE = "FISCALYEAR='2025'"


def dc_query(**params):
    return DC + "/query?" + urllib.parse.urlencode({"where": DC_WHERE, "f": "json", **params})


SOURCES = {
    "cityvizor-cernosice-2025": {
        "provider": "CityVizor / Cernosice", "format": "cityvizor", "profile_id": 3,
        "source_page": "https://www.mestocernosice.cz/samosprava/rozpocet/",
        "documentation": "https://cityvizor.cz/landing/dokumentace",
        "scope": "Entire payments export for profile 3, accounting year 2025; not all bank activity",
        "license": "Data reuse terms not verified; software AGPL does not license municipal records",
        "files": {"payments.json": "https://cityvizor.cz/api/exports/profiles/3/payments/2025",
                  "years.json": "https://cityvizor.cz/api/exports/profiles/3/years"},
    },
    "cityvizor-nmnm-2025": {
        "provider": "CityVizor / Nove Mesto na Morave", "format": "cityvizor", "profile_id": 1,
        "source_page": "https://cityvizor.cz/nmnm/prehled",
        "documentation": "https://cityvizor.cz/landing/dokumentace",
        "scope": "Entire payments export for profile 1, accounting year 2025; not all bank activity",
        "license": "Data reuse terms not verified; software AGPL does not license municipal records",
        "files": {"payments.json": "https://cityvizor.cz/api/exports/profiles/1/payments/2025",
                  "years.json": "https://cityvizor.cz/api/exports/profiles/1/years"},
    },
    "national-archives-2025-12": {
        "provider": "The National Archives, UK", "format": "tna",
        "source_page": "https://www.nationalarchives.gov.uk/about-us/how-we-work/transparency/how-we-spend-public-money/",
        "documentation": "https://www.nationalarchives.gov.uk/legal/copyright/",
        "scope": "Entire December 2025 over-GBP-25000 supplier payment CSV; thresholded disclosure",
        "license": "Check source copyright/OGL exceptions; no raw redistribution in this repository",
        "files": {"payments.csv": "https://www.nationalarchives.gov.uk/wagtail-documents/107/payments-over-25k-december-2025.csv"},
    },
    "dc-pass-fy2025-prefix": {
        "provider": "District of Columbia / DC GIS", "format": "dc",
        "source_page": DC, "documentation": DC,
        "scope": "First up to 1000 FY2025 rows ordered by OBJECTID, deterministic nonrandom prefix only",
        "license": "Endpoint copyright is null; public access does not establish reuse permission",
        "files": {"schema.json": DC + "?f=pjson",
                  "count.json": dc_query(returnCountOnly="true"),
                  "payments.json": dc_query(outFields="*", returnGeometry="false",
                                             resultRecordCount=1000, orderByFields="OBJECTID ASC")},
    },
    "wigan-fy2025-26": {
        "provider": "Wigan Council, UK", "format": "unavailable",
        "source_page": "https://www.wigan.gov.uk/Council/DataProtection-FOI-Stats/Spending-and-Finance-data.aspx",
        "documentation": "https://www.wigan.gov.uk/Docs/PDF/Council/Data-Protection-FOI/Open-Data/FinancialSpendsMetadata.pdf",
        "scope": "Attempted FY2025-26 creditor payment CSV; not treated as downloaded if request fails",
        "license": "Source page and metadata explicitly state Open Government Licence",
        "files": {"payments.csv": "https://www.wigan.gov.uk/Docs/PDF/Council/Data-Protection-FOI/Open-Data/Open-Data-2025-26/Open-Data-M12-March-2026-Creditor-Payments-CSV.csv"},
    },
    "opencollective-webpack": {
        "provider": "Open Collective / webpack", "format": "unavailable",
        "source_page": "https://opencollective.com/webpack/transactions",
        "documentation": "https://documentation.opencollective.com/advanced/ledger",
        "scope": "Public GraphQL transaction request, limit 100; ledger is not an independent bank statement",
        "license": "Data reuse not verified; private attachments not requested",
        "files": {"transactions.json": "https://api.opencollective.com/graphql/v2?" + urllib.parse.urlencode({
            "query": '{account(slug:"webpack"){slug currency transactions(limit:100){totalCount nodes{id createdAt type kind amount{valueInCents currency}}}}}'})},
    },
    "berka-original": {
        "provider": "PKDD99 / original VSE archive", "format": "unavailable",
        "source_page": "https://relational.fel.cvut.cz/dataset/Financial",
        "documentation": "https://relational.fel.cvut.cz/dataset/Financial",
        "scope": "Attempt original archived bank dataset URL; no invoice allocation truth established",
        "license": "Reuse conditions not verified",
        "files": {"data_berka.zip": "https://lisp.vse.cz/pkdd99/DATA/data_berka.zip"},
    },
    "benchrec": {
        "provider": "Operartis", "format": "access_gated",
        "source_page": "https://www.operartis.com/benchrec",
        "documentation": "https://sites.google.com/view/fintranmatch-competition-icaif",
        "scope": "Participation page only; no dataset download, registration or contact submission",
        "license": "Dataset terms unavailable until access granted; GL is not necessarily an invoice",
        "files": {"participation.html": "https://www.operartis.com/benchrec"},
    },
}


def now():
    return datetime.now(timezone.utc).isoformat()


def download_source(base, source_id):
    spec = SOURCES[source_id]
    folder = Path(base) / source_id
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / "source_manifest.json"
    if manifest_path.exists():
        manifest = verify_source(folder, source_id)
        return manifest
    if any(folder.iterdir()):
        raise ValueError(f"{source_id}: incomplete existing snapshot; use a new --output")
    manifest = {"source_id": source_id, "spec_hash": fingerprint(spec),
                "retrieved_at_utc": now(), "source": spec,
                "use_policy": "inspection_only_excluded_from_matching", "files": [], "errors": []}
    for filename, url in spec["files"].items():
        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": "FinanceProject-T0-Audit/1.0",
                "Accept": "application/json" if filename.endswith(".json") else "*/*"})
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = response.read(30_000_001)
                if len(payload) > 30_000_000:
                    raise ValueError("Response exceeds 30 MB source-inspection limit")
                if filename.endswith(".json"):
                    data = json.loads(payload)
                    if isinstance(data, dict) and (data.get("error") or data.get("errors")):
                        raise ValueError("API returned an error envelope")
                elif filename.endswith(".csv") and b"<html" in payload[:1000].lower():
                    raise ValueError("CSV endpoint returned HTML")
                with (folder / filename).open("xb") as handle:
                    handle.write(payload)
                manifest["files"].append({"file": filename, "url": url, "final_url": response.url,
                    "status": response.status, "retrieved_at_utc": now(),
                    "content_type": response.headers.get("Content-Type"),
                    "bytes": len(payload), "sha256": sha256(payload)})
        except (OSError, ValueError) as exc:
            manifest["errors"].append({"file": filename, "url": url,
                "error_type": type(exc).__name__, "http_status": getattr(exc, "code", None),
                "reason": str(exc), "checked_at_utc": now()})
            break
    manifest["download_status"] = "failed" if manifest["errors"] else "downloaded"
    write_json(manifest_path, manifest)
    return manifest


def verify_source(folder, source_id):
    folder = Path(folder)
    manifest = json.loads((folder / "source_manifest.json").read_text(encoding="utf-8"))
    spec = SOURCES[source_id]
    if manifest.get("source_id") != source_id or manifest.get("spec_hash") != fingerprint(spec):
        raise ValueError(f"{source_id}: source specification does not match snapshot")
    if (manifest.get("download_status") not in ("downloaded", "failed")
            or manifest.get("use_policy") != "inspection_only_excluded_from_matching"):
        raise ValueError("Invalid download state or inspection policy")
    expected = set(spec["files"])
    actual = [item["file"] for item in manifest["files"]]
    if len(actual) != len(set(actual)) or not set(actual).issubset(expected):
        raise ValueError("Unexpected or duplicate raw file entries")
    if manifest["download_status"] == "downloaded" and set(actual) != expected:
        raise ValueError("Incomplete downloaded snapshot")
    for item in manifest["files"]:
        if item["url"] != spec["files"][item["file"]]:
            raise ValueError("Raw file URL differs from registered source")
        payload = (folder / item["file"]).read_bytes()
        if len(payload) != item["bytes"] or sha256(payload) != item["sha256"]:
            raise ValueError(f"{source_id}: raw hash/size mismatch: {item['file']}")
    return manifest


def download_survey(base):
    # Each worker owns a separate source folder. Failed access is persisted as evidence.
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda source_id: download_source(base, source_id), SOURCES))


def load_json(path):
    return json.loads(Path(path).read_bytes(), parse_float=Decimal)


def columns(rows, required):
    if not rows:
        raise ValueError("Empty source data; cannot claim successful row audit")
    if not all(isinstance(row, dict) and required <= row.keys() for row in rows):
        raise ValueError("Source schema changed or row malformed")


def amount(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("Missing/invalid amount")
    return decimal_money(str(value))


def date_text(value):
    if not isinstance(value, str):
        raise ValueError("Missing/invalid date")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()


def duplicates(rows):
    # JSON Decimal values retain exact lexical money, without float conversion.
    counts = Counter(json.dumps(row, sort_keys=True, default=str, ensure_ascii=False) for row in rows)
    return sum(n - 1 for n in counts.values())


def audit_cityvizor(folder, profile_id):
    rows = load_json(folder / "payments.json")
    required = {"profileId", "year", "date", "incomeAmount", "expenditureAmount",
                "counterpartyId", "counterpartyName", "description", "paragraph", "item", "event"}
    columns(rows, required)
    dates, errors = [], []
    income = expenditure = Decimal(0)
    signs = Counter()
    missing_cp = missing_name = wrong_scope = 0
    for number, row in enumerate(rows, 1):
        try:
            day = date_text(row["date"])
            inc, out = amount(row["incomeAmount"]), amount(row["expenditureAmount"])
            dates.append(day)
            income += inc
            expenditure += out
            signs["negative_rows"] += int(inc < 0 or out < 0)
            signs["zero_both_rows"] += int(inc == out == 0)
            signs["both_nonzero_rows"] += int(inc != 0 and out != 0)
            signs["income_nonzero_rows"] += int(inc != 0)
            signs["expenditure_nonzero_rows"] += int(out != 0)
            wrong_scope += int(row["profileId"] != profile_id or row["year"] != 2025)
            missing_cp += int(not row["counterpartyId"])
            missing_name += int(not row["counterpartyName"])
        except (ValueError, TypeError) as exc:
            errors.append({"row": number, "reason": str(exc)})
    year_rows = load_json(folder / "years.json")
    year_metadata = next((row for row in year_rows if row.get("year") == 2025), None)
    return {"rows": len(rows), "columns": sorted(rows[0]), "valid_rows": len(dates),
        "date_min": min(dates) if dates else None, "date_max": max(dates) if dates else None,
        "errors": errors, "wrong_profile_or_year_rows": wrong_scope,
        "missing_counterparty_id_rows": missing_cp, "missing_counterparty_name_rows": missing_name,
        "identical_row_occurrences_beyond_first": duplicates(rows), "amount_signs": dict(signs),
        "income_total_source_decimal_units": str(income), "expenditure_total_source_decimal_units": str(expenditure),
        "currency": None, "year_metadata_present": year_metadata is not None,
        "year_metadata_validity": year_metadata.get("validity") if year_metadata else None,
        "grain": "Budget-coded accounting/payment lines; invoice can split across item/paragraph/event",
        "absent_invoice_id_and_bank_transaction_id": True,
        "duplicate_policy": "Count only; identical accounting lines may be legitimate, no removal"}


TNA_COLUMNS = {"Operational Transaction Number", "Last Invoice Payment Date", "Supplier",
               "Supplier's Invoice Number", "Line Amount Spend", "Invoice Amount Spend"}


def uk_amount(value):
    value = value.strip()
    # Explicit UK grouping only; no guessing commas as decimal separators.
    if not re.fullmatch(r"-?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]{1,2})?", value):
        raise ValueError("Invalid UK monetary text")
    return decimal_money(value.replace(",", ""))


def audit_tna(folder):
    reader = csv.DictReader(io.StringIO((folder / "payments.csv").read_text(encoding="utf-8-sig")))
    rows = list(reader)
    columns(rows, TNA_COLUMNS)
    groups, dates, errors = defaultdict(list), [], []
    line_total = Decimal(0)
    missing = Counter()
    for number, row in enumerate(rows, 2):
        try:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Malformed CSV row")
            text = row["Last Invoice Payment Date"]
            day = datetime.strptime(text, "%d/%m/%Y").date().isoformat()
            line = uk_amount(row["Line Amount Spend"])
            invoice = uk_amount(row["Invoice Amount Spend"])
            key = tuple(row[field].strip() for field in ("Supplier", "Supplier's Invoice Number", "Operational Transaction Number"))
            dates.append(day)
            line_total += line
            missing["negative_line_rows"] += int(line < 0)
            missing["missing_supplier_rows"] += int(not key[0])
            missing["missing_invoice_number_rows"] += int(not key[1])
            missing["missing_operational_transaction_rows"] += int(not key[2])
            groups[key].append((line, invoice))
        except (ValueError, TypeError) as exc:
            errors.append({"csv_line": number, "reason": str(exc)})
    comparable = consistent = conflicts = 0
    max_lines = 0
    for values in groups.values():
        max_lines = max(max_lines, len(values))
        totals = {v[1] for v in values}
        if len(totals) != 1:
            conflicts += 1
            continue
        comparable += 1
        consistent += int(sum((v[0] for v in values), Decimal(0)) == next(iter(totals)))
    return {"rows": len(rows), "columns": reader.fieldnames, "valid_rows": len(dates), "errors": errors,
        "date_min": min(dates) if dates else None, "date_max": max(dates) if dates else None,
        "identical_row_occurrences_beyond_first": duplicates(rows), **missing,
        "line_total_source_decimal_units": str(line_total), "currency": "GBP (source page threshold, not CSV column)",
        "candidate_invoice_transaction_groups": len(groups), "max_lines_per_candidate_group": max_lines,
        "groups_with_conflicting_repeated_invoice_amounts": conflicts,
        "groups_with_consistent_invoice_amount": comparable,
        "groups_where_sum_lines_equals_invoice_amount": consistent,
        "grain": "Spend lines; repeated Invoice Amount Spend must not be summed as separate invoices",
        "grouping_limit": "Exploratory supplier + invoice number + operational transaction grouping, not verified invoice identity",
        "bank_statement_and_independent_allocation_truth": False}


def epoch_date(value):
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise ValueError("Expected epoch milliseconds")
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).date().isoformat()


def audit_dc(folder):
    envelope = load_json(folder / "payments.json")
    rows = [item["attributes"] for item in envelope["features"]]
    required = {"OBJECTID", "AGENCYCODE", "SUPPLIERNAME", "INVOICENUMBER", "PAYMENTNUMBER",
                "PAYMENTDATE", "INVOICEDATE", "ESTPAYMENTDATE", "PAYMENTAMOUNT", "VOUCHERAMOUNT", "FISCALYEAR"}
    columns(rows, required)
    count = load_json(folder / "count.json")["count"]
    schema = load_json(folder / "schema.json")
    stats, errors, dates, groups, payment_groups = Counter(), [], [], Counter(), Counter()
    amount_total = Decimal(0)
    for number, row in enumerate(rows, 1):
        try:
            stats["wrong_fiscal_year_rows"] += int(row["FISCALYEAR"] != "2025")
            money = amount(row["PAYMENTAMOUNT"])
            amount_total += money
            stats["negative_payment_rows"] += int(money < 0)
            stats["zero_payment_rows"] += int(money == 0)
            for field in ("PAYMENTDATE", "ESTPAYMENTDATE", "INVOICEDATE", "PAYMENTNUMBER", "INVOICENUMBER"):
                stats["missing_" + field] += int(row[field] is None or row[field] == "")
            actual = epoch_date(row["PAYMENTDATE"]) if row["PAYMENTDATE"] is not None else None
            issued = epoch_date(row["INVOICEDATE"]) if row["INVOICEDATE"] is not None else None
            estimate = epoch_date(row["ESTPAYMENTDATE"]) if row["ESTPAYMENTDATE"] is not None else None
            if actual:
                dates.append(actual)
            if actual and issued:
                stats["actual_before_invoice_rows"] += int(actual < issued)
            if actual and estimate:
                stats["actual_differs_from_estimate_rows"] += int(actual != estimate)
            if row["INVOICENUMBER"]:
                groups[(row["AGENCYCODE"], row["SUPPLIERNAME"], row["INVOICENUMBER"])] += 1
            if row["PAYMENTNUMBER"]:
                payment_groups[(row["AGENCYCODE"], row["PAYMENTNUMBER"])] += 1
        except (ValueError, TypeError, OverflowError, OSError) as exc:
            errors.append({"row": number, "reason": str(exc)})
    ids = [row["OBJECTID"] for row in rows]
    return {"rows": len(rows), "columns": sorted(rows[0]), "errors": errors,
        "query_total_rows_at_download": count, "sample_is_full_query": len(rows) == count,
        "exceeded_transfer_limit": envelope.get("exceededTransferLimit", False),
        "sample_selection": "Nonrandom OBJECTID ascending prefix, no population accuracy inference",
        "unique_object_ids": len(set(ids)), "object_ids_sorted": ids == sorted(ids),
        "payment_date_min": min(dates) if dates else None, "payment_date_max": max(dates) if dates else None,
        "schema_has_actual_and_estimated_payment_date": {"PAYMENTDATE", "ESTPAYMENTDATE"} <= {f["name"] for f in schema["fields"]},
        **stats, "candidate_invoice_groups_with_multiple_rows": sum(n > 1 for n in groups.values()),
        "candidate_payment_groups_with_multiple_rows": sum(n > 1 for n in payment_groups.values()),
        "sum_PAYMENTAMOUNT_source_decimal_units_unverified_grain": str(amount_total),
        "amount_total_limit": "Not a verified cash total: row grain/payment repetition not established",
        "currency": None, "independent_bank_statement_and_allocation_truth": False,
        "grain": "Invoice/voucher/payment disclosure rows; OBJECTID is row ID, not invoice ID"}


def audit_source(base, source_id):
    folder = Path(base) / source_id
    manifest = verify_source(folder, source_id)
    spec = SOURCES[source_id]
    report = {"source_id": source_id, "manifest": manifest, "audited_at_utc": now(),
              "audit_code_sha256": sha256(Path(__file__).read_bytes()), "profile": None,
              "matcher_runs": 0, "precision": None, "recall": None}
    if manifest["download_status"] != "downloaded":
        report["status"] = "access_failed"
        reasons = ["no_downloaded_dataset"]
    elif spec["format"] == "access_gated":
        report["status"] = "access_gated"
        reasons = ["only_participation_page_downloaded", "dataset_and_terms_require_access"]
    elif spec["format"] == "unavailable":
        report["status"] = "needs_schema_audit"
        reasons = ["access_now_succeeds_but_adapter_not_implemented", "not_approved_for_matching"]
    else:
        try:
            report["profile"] = (audit_cityvizor(folder, spec["profile_id"]) if spec["format"] == "cityvizor"
                                 else audit_tna(folder) if spec["format"] == "tna" else audit_dc(folder))
            report["status"] = "audited_excluded"
            reasons = ["no_independent_invoice_bank_allocation_truth", "public_sector_differs_from_SME_AR",
                       "no_historical_availability_for_asof_matching", "no_separate_bank_statement"]
            if spec["format"] == "cityvizor":
                reasons += ["no_explicit_invoice_or_bank_transaction_identifier", "budget_split_line_grain", "data_reuse_terms_unverified"]
            elif spec["format"] == "dc":
                reasons += ["nonrandom_prefix_only", "payment_and_invoice_row_grain_unverified", "data_reuse_terms_unverified"]
        except (ValueError, KeyError, TypeError) as exc:
            report["status"] = "audit_failed"
            report["audit_error"] = str(exc)
            reasons = ["source_parse_or_schema_failure"]
    report["matching_gate"] = {"accepted": False, "reasons": reasons,
        "action": "Inspection only; no matcher inputs, pseudo-labels, training, tuning or method ranking"}
    return report


def audit_survey(base, output):
    reports = [audit_source(base, key) for key in SOURCES]
    summary = {"audited_at_utc": now(), "sources": reports,
        "code_hashes": {path.relative_to(ROOT).as_posix(): sha256(path.read_bytes())
                        for path in (Path(__file__), Path(__file__).with_name("audit_t0_moneyvis.py"),
                                     ROOT / "t0/data.py")},
        "summary": {"candidate_snapshots": len(reports),
            "audited_data_snapshots": sum(r["status"] == "audited_excluded" for r in reports),
            "rows_inspected": sum(r["profile"]["rows"] for r in reports if r["profile"]),
            "accepted_for_matching": 0, "matcher_runs": 0},
        "limits": ["CityVizor profiles share a provider/schema, not independent data formats",
                   "Failed access is session-specific, not proof a source is permanently unavailable",
                   "Only the DC prefix is sampled; entire selected export files audited for other accessible sources",
                   "Public-source authenticity follows publisher provenance, not independent real-world verification",
                   "Source audit success is not matching acceptance; no raw names/descriptions copied to report"]}
    write_json(output, summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/T0/raw/source_survey/2026-10-19")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--download", action="store_true", help="Explicitly allow source requests if cache is absent")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Output exists; choose a new --output")
    if args.download:
        download_survey(args.input)
    report = audit_survey(args.input, args.output)
    print(f"Historical source survey: {report['summary']}")
    return int(any(row["status"] == "audit_failed" for row in report["sources"]))


if __name__ == "__main__":
    raise SystemExit(main())
