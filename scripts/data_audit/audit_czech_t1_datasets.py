"""Audit the complete downloaded Czech sources and export invoice-level audit CSVs.

Requires pandas and numpy. Does not train models, impute dates, merge sources,
or silently deduplicate invoices. Audit gates are explicit diagnostic screens.
"""

import argparse
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATE_FIELDS = ["issue_date", "received_date", "due_date", "paid_date"]
MF_COLUMNS = {
    "iri": "source_record_id", "číslo_faktury": "invoice_reference",
    "dodavatel_ičo": "seller_id", "typ_dokladu": "document_type",
    "datum_vystavení": "issue_date_raw", "datum_přijetí": "received_date_raw",
    "datum_splatnosti": "due_date_raw", "datum_úhrady": "paid_date_raw",
    "částka": "amount_local_raw", "částka_v_měně": "amount_raw", "měna": "currency",
    "částka_k_úhradě_v_měně": "amount_to_pay_raw",
}
HEALTH_COLUMNS = {
    "id_invoice": "source_record_id", "import_id": "import_id",
    "identifikator_dodavatele": "invoice_reference",
    "identifikator_odberatele": "buyer_invoice_reference",
    "typ_dokladu": "document_type", "datum_vystaveni": "issue_date_raw",
    "datum_prijeti": "received_date_raw", "datum_splatnosti": "due_date_raw",
    "datum_uhrady": "paid_date_raw", "castka_s_dph": "amount_raw",
    "castka_s_dph_mena": "currency", "castka_uhrazena": "paid_amount_raw",
    "castka_uhrazena_mena": "paid_currency",
}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(4 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def clean(series):
    return series.fillna("").astype(str).str.strip()


def missing(series):
    return clean(series).str.lower().isin(["", "null", "none", "nan", "nat"])


def counts(series):
    return {str(k): int(v) for k, v in series.value_counts(dropna=False).items()}


def read_finance(raw):
    path = raw / "finance/faktury.csv"
    totals, selected, malformed = Counter(), [], 0
    for chunk in pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False, chunksize=50000):
        totals.update(chunk["typ_záznamu"])
        malformed += int(chunk.isna().any(axis=1).sum())
        selected.append(chunk.loc[chunk["typ_záznamu"] == "souhrnný", list(MF_COLUMNS)].rename(columns=MF_COLUMNS))
    frame = pd.concat(selected, ignore_index=True)
    frame["buyer_id"] = "CZ_MF"
    frame["paid_amount_raw"] = ""  # amount-to-pay is not verified actual cash paid
    frame["paid_currency"] = ""
    frame["import_id"] = ""
    return frame, {"raw_rows": int(sum(totals.values())), "raw_record_types": dict(totals),
                   "rows_with_missing_csv_cells": malformed, "invoice_summary_rows": len(frame),
                   "raw_file_bytes": path.stat().st_size, "raw_file_sha256": digest(path)}


def read_health(raw):
    manifest = json.loads((raw / "download_manifest.json").read_text(encoding="utf-8"))
    expected = manifest["sources"]["health"]
    imports = json.loads((raw / "health/imports_before.json").read_bytes())
    import_map = {r["id_import"]: r for r in imports}
    rows, schemas, mismatches, page_counts = [], Counter(), [], []
    for entry in expected["pages"]:
        path = raw / "health/pages" / f"page_{entry['page']:04d}.json"
        if digest(path) != entry["sha256"]:
            mismatches.append(entry["page"])
        batch = json.loads(path.read_bytes())
        page_counts.append(len(batch))
        for row in batch:
            schemas.update([tuple(sorted(row))])
            compact = {target: row.get(source) for source, target in HEALTH_COLUMNS.items()}
            compact["buyer_id"] = (row.get("odberatel") or {}).get("id_company")
            compact["seller_id"] = (row.get("dodavatel") or {}).get("id_company")
            imp = import_map.get(row.get("import_id"), {})
            compact["organization_id"] = imp.get("organization_id")
            compact["imported_at"] = imp.get("imported_at")
            compact["source_page"] = entry["page"]
            rows.append(compact)
    if mismatches:
        raise ValueError(f"Health response hash mismatch on pages {mismatches}")
    if len(rows) != expected["expected_records"]:
        raise ValueError("Health row count does not match API total")
    frame = pd.DataFrame(rows)
    return frame, {"raw_rows": len(rows), "pages": len(page_counts), "expected_records": expected["expected_records"],
                   "page_hashes_verified": True, "schema_variants": [{"columns": list(k), "rows": v} for k, v in schemas.items()],
                   "imports_unchanged_during_download": expected.get("imports_unchanged_during_download"),
                   "organizations_unchanged_during_download": expected.get("organizations_unchanged_during_download"),
                   "first_page_unchanged_during_download": expected.get("first_page_unchanged_during_download")}


def duplicate_stats(frame, key, eligible=None):
    selected = frame.loc[eligible] if eligible is not None else frame
    size = selected.groupby(key, dropna=False, sort=False).size()
    repeated = size[size > 1]
    return {"eligible_rows": len(selected), "unique_keys": len(size), "repeated_key_groups": len(repeated),
            "rows_in_repeated_groups": int(repeated.sum()), "excess_rows": int((repeated - 1).sum())}


def audit(frame, name, metadata, stamp, out):
    frame = frame.copy()
    report = {"dataset": name, **metadata, "invoice_level_rows_before_deduplication": len(frame),
              "gates_are_diagnostics_not_verified_cash_labels": True,
              "gates_use_plausible_dates_1990_to_snapshot_for_issue_and_payment": True}
    today = pd.Timestamp(stamp)
    due_upper_bound = today + pd.DateOffset(years=5)
    report["due_date_diagnostic_upper_bound"] = str(due_upper_bound.date())
    report["dates"] = {}
    for field in DATE_FIELDS:
        original = clean(frame[field + "_raw"])
        frame[field] = pd.to_datetime(original.str.slice(0, 10), format="%Y-%m-%d", errors="coerce")
        present = frame[field].notna()
        report["dates"][field] = {
            "missing_raw": int(missing(original).sum()),
            "unparseable_nonempty": int((~missing(original) & ~present).sum()),
            "parsed": int(present.sum()),
            "year_1970": int((frame[field].dt.year == 1970).sum()),
            "before_1990": int((frame[field] < "1990-01-01").sum()),
            "after_snapshot": int((frame[field] > today).sum()),
            "min": str(frame.loc[present, field].min().date()) if present.any() else None,
            "max": str(frame.loc[present, field].max().date()) if present.any() else None,
        }
        # Future due dates are allowed. Early/future dates remain in the audit CSV.
        frame[field + "_plausible"] = present & (frame[field] >= "1990-01-01")
        if field != "due_date":
            frame[field + "_plausible"] &= frame[field] <= today
        else:
            report["dates"][field]["beyond_five_year_diagnostic_bound"] = int((frame[field] > due_upper_bound).sum())
            frame[field + "_plausible"] &= frame[field] <= due_upper_bound
    for field in ["source_record_id", "invoice_reference", "buyer_id", "seller_id", "currency", "paid_currency", "document_type"]:
        frame[field] = clean(frame[field])
    frame["currency_code_shape_valid"] = frame["currency"].str.fullmatch(r"[A-Za-z]{3}")
    frame["amount"] = pd.to_numeric(frame["amount_raw"], errors="coerce")
    frame["paid_amount"] = pd.to_numeric(frame["paid_amount_raw"], errors="coerce")
    frame["days_to_payment"] = (frame["paid_date"] - frame["issue_date"]).dt.days
    frame["days_late"] = (frame["paid_date"] - frame["due_date"]).dt.days
    frame["derived_issue_to_due_days"] = (frame["due_date"] - frame["issue_date"]).dt.days
    frame["days_received_to_payment"] = (frame["paid_date"] - frame["received_date"]).dt.days
    frame["due_before_issue"] = frame["due_date"] < frame["issue_date"]
    frame["paid_before_issue"] = frame["paid_date"] < frame["issue_date"]
    frame["paid_before_received"] = frame["paid_date"] < frame["received_date"]
    frame["reference_usable"] = ~frame["invoice_reference"].str.upper().isin(["", "NULL", "NONE", "NAN", "?", "-", "N/A"])
    frame["gate_issue_due_paid"] = (
        frame["issue_date_plausible"] & frame["due_date_plausible"] & frame["paid_date_plausible"]
        & ~frame["due_before_issue"] & ~frame["paid_before_issue"] & (frame["amount"] > 0)
        & frame["currency_code_shape_valid"] & ~missing(frame["buyer_id"]) & ~missing(frame["seller_id"])
        & ~missing(frame["source_record_id"])
    )
    frame["gate_with_invoice_reference"] = frame["gate_issue_due_paid"] & frame["reference_usable"]
    frame["gate_received_due_paid"] = (
        frame["received_date_plausible"] & frame["due_date_plausible"] & frame["paid_date_plausible"]
        & ~frame["paid_before_received"] & (frame["amount"] > 0)
        & frame["currency_code_shape_valid"] & ~missing(frame["buyer_id"]) & ~missing(frame["seller_id"])
    )
    # A positive paid-date label is a proxy, not proof of full settlement or bank cash.
    frame["paid_amount_comparable"] = (frame["paid_amount"].notna() & frame["amount"].notna()
                                        & (frame["currency"] == frame["paid_currency"]) & ~missing(frame["currency"]))
    comparable = frame["paid_amount_comparable"]
    frame["paid_matches_gross_within_001"] = comparable & ((frame["paid_amount"] - frame["amount"]).abs() <= 0.01)
    frame["gate_with_amount_agreement"] = frame["gate_with_invoice_reference"] & frame["paid_matches_gross_within_001"]
    report["identifiers"] = {"distinct_buyers": frame.loc[~missing(frame["buyer_id"]), "buyer_id"].nunique(),
                             "distinct_sellers": frame.loc[~missing(frame["seller_id"]), "seller_id"].nunique(),
                             "missing_seller_id": int(missing(frame["seller_id"]).sum()),
                             "missing_or_placeholder_invoice_reference": int((~frame["reference_usable"]).sum())}
    report["amounts"] = {"missing_or_invalid": int(frame["amount"].isna().sum()),
                         "nonpositive": int((frame["amount"] <= 0).sum()),
                         "invalid_or_missing_currency_code_shape": int((~frame["currency_code_shape_valid"]).sum()),
                         "currencies": counts(frame["currency"]),
                         "paid_amount_missing": int(frame["paid_amount"].isna().sum()),
                         "paid_amount_zero": int((frame["paid_amount"] == 0).sum()),
                         "paid_amount_comparable": int(comparable.sum()),
                         "paid_matches_gross_within_001": int(frame["paid_matches_gross_within_001"].sum()),
                         "positive_paid_less_than_positive_gross": int((comparable & (frame["paid_amount"] > 0) & (frame["paid_amount"] < frame["amount"] - 0.01)).sum()),
                         "paid_exceeds_gross": int((comparable & (frame["paid_amount"] > frame["amount"] + 0.01)).sum())}
    report["quality_flags"] = {f: int(frame[f].sum()) for f in ["due_before_issue", "paid_before_issue", "paid_before_received"]}
    report["quality_flags"]["missing_paid_and_due_dates"] = int((frame["paid_date"].isna() & frame["due_date"].isna()).sum())
    report["quality_flags"]["missing_paid_positive_amount"] = int((frame["paid_date"].isna() & (frame["amount"] > 0)).sum())
    report["gates"] = {k: int(frame[k].sum()) for k in ["gate_issue_due_paid", "gate_with_invoice_reference", "gate_received_due_paid", "gate_with_amount_agreement"]}
    business_key = ["buyer_id", "seller_id", "invoice_reference"]
    strong_key = business_key + ["issue_date_raw", "received_date_raw", "due_date_raw", "paid_date_raw", "amount_raw", "currency", "paid_amount_raw", "paid_currency", "document_type"]
    report["duplicates"] = {
        "source_record_id": duplicate_stats(frame, ["source_record_id"]),
        "buyer_seller_reference_candidates": duplicate_stats(frame, business_key, frame["reference_usable"]),
        "same_reference_and_selected_financial_fields": duplicate_stats(frame, strong_key, frame["reference_usable"]),
    }
    signature = pd.util.hash_pandas_object(frame[strong_key], index=False)
    signature_groups = frame.assign(financial_signature=signature).groupby("source_record_id")["financial_signature"].nunique()
    conflict_ids = signature_groups[signature_groups > 1].index
    report["duplicates"]["source_ids_with_conflicting_selected_financial_fields"] = len(conflict_ids)
    frame["source_id_has_financial_conflict"] = frame["source_record_id"].isin(conflict_ids)
    clean_source = frame.loc[frame["gate_with_invoice_reference"] & ~frame["source_id_has_financial_conflict"]]
    report["gates"]["unique_source_ids_passing_gate_without_source_id_conflict"] = int(clean_source["source_record_id"].nunique())
    if name == "health":
        ordinary = frame["document_type"].isin(["Běžná faktura", "Faktura přijatá", "Faktury přijaté", "Přijatá faktura"])
        report["gates"]["ordinary_named_document_types_issue_gate"] = int((ordinary & frame["gate_with_invoice_reference"]).sum())
        report["gates"]["ordinary_named_document_types_amount_agreement_gate"] = int((ordinary & frame["gate_with_amount_agreement"]).sum())
        frame["ordinary_named_document_type"] = ordinary
    frame["same_financial_fields_repeat"] = False
    use = frame["reference_usable"]
    frame.loc[use, "same_financial_fields_repeat"] = frame.loc[use].duplicated(strong_key, keep=False)
    frame["candidate_unique_in_selected_fields"] = frame["gate_with_invoice_reference"] & ~frame["same_financial_fields_repeat"]
    report["gates"]["candidate_unique_in_selected_fields"] = int(frame["candidate_unique_in_selected_fields"].sum())
    # This count describes removing all ambiguous duplicate groups, not proving a
    # correct deduplication rule. The export keeps every row and its flags.
    report["gates"]["one_row_per_selected_fields_if_exact_replays_confirmed"] = int(
        frame.loc[frame["gate_with_invoice_reference"]].drop_duplicates(strong_key).shape[0])
    passed = frame.loc[frame["gate_issue_due_paid"]]
    report["timing_on_issue_gate"] = {
        "days_to_payment": {str(k): float(v) for k, v in passed["days_to_payment"].quantile([0, .5, .9, .99, 1]).items()} if len(passed) else {},
        "days_late": {str(k): float(v) for k, v in passed["days_late"].quantile([0, .5, .9, .99, 1]).items()} if len(passed) else {},
        "late_count": int((passed["days_late"] > 0).sum()),
        "same_day_payments": int((passed["days_to_payment"] == 0).sum()),
    }
    report["document_types"] = counts(frame["document_type"])
    report["issue_year_counts"] = counts(frame["issue_date"].dt.year.astype("Int64"))
    report["paid_year_counts"] = counts(frame["paid_date"].dt.year.astype("Int64"))
    by_type = frame.groupby("document_type", dropna=False).agg(rows=("source_record_id", "size"), passed=("gate_issue_due_paid", "sum"))
    report["gate_by_document_type"] = by_type.reset_index().to_dict("records")
    group = frame.groupby("buyer_id", dropna=False).agg(
        rows=("source_record_id", "size"), sellers=("seller_id", "nunique"),
        passed_issue=("gate_issue_due_paid", "sum"), passed_reference=("gate_with_invoice_reference", "sum"),
        passed_amount_agreement=("gate_with_amount_agreement", "sum"),
        passed_received=("gate_received_due_paid", "sum"))
    report["by_buyer"] = group.reset_index().to_dict("records")
    monthly = frame.assign(issue_month=frame["issue_date"].dt.strftime("%Y-%m").fillna("missing"))
    monthly = monthly.groupby(["buyer_id", "issue_month"], dropna=False).agg(
        rows=("source_record_id", "size"), passed=("gate_issue_due_paid", "sum"),
        passed_reference=("gate_with_invoice_reference", "sum"))
    monthly.to_csv(out / f"{name}_monthly_coverage.csv", encoding="utf-8-sig")
    report["issue_gate_months_by_buyer"] = {
        str(buyer): {"months": int(series.nunique()), "first_month": series.min(), "last_month": series.max()}
        for buyer, series in passed.assign(month=passed["issue_date"].dt.strftime("%Y-%m")).groupby("buyer_id")["month"]
    }
    if name == "health":
        frame["imported_at"] = pd.to_datetime(frame["imported_at"], errors="coerce")
        report["publication"] = {
            "missing_import_metadata": int(frame["imported_at"].isna().sum()),
            "imported_after_paid_date": int((frame["imported_at"].dt.normalize() > frame["paid_date"]).sum()),
        }
        frame.groupby("organization_id", dropna=False).agg(
            rows=("source_record_id", "size"), passed=("gate_issue_due_paid", "sum"),
            passed_reference=("gate_with_invoice_reference", "sum"),
            passed_received=("gate_received_due_paid", "sum")).to_csv(out / "health_by_organization.csv", encoding="utf-8-sig")
    frame.to_csv(out / f"{name}_invoice_audit.csv", index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")
    print(json.dumps({"dataset": name, "raw_rows": metadata["raw_rows"], "invoice_rows": len(frame), "gates": report["gates"]}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", default=date.today().isoformat())
    args = parser.parse_args()
    stamp = date.fromisoformat(args.snapshot).isoformat()
    raw = ROOT / "data/T1/raw/czech" / stamp
    manifest = json.loads((raw / "download_manifest.json").read_text(encoding="utf-8"))
    if not manifest["complete"]:
        raise ValueError("Finish the download first")
    out = ROOT / "data/T1/interim/czech" / stamp
    out.mkdir(parents=True, exist_ok=True)
    profiles = {"snapshot": stamp, "scope": "All downloaded Finance summary rows and all downloaded Health API invoice records; no model training.", "datasets": {}}
    for name, loader in [("finance", read_finance), ("health", read_health)]:
        frame, meta = loader(raw)
        if name == "finance" and meta["raw_file_sha256"] != manifest["sources"]["finance"]["sha256"]:
            raise ValueError("Finance file hash mismatch")
        profiles["datasets"][name] = audit(frame, name, meta, stamp, out)
        del frame
    target = ROOT / "research/references/data-checks/t1/czech_t1_full_audit.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(profiles, ensure_ascii=False, indent=2, default=lambda x: x.item() if isinstance(x, np.generic) else str(x)) + "\n", encoding="utf-8")
    print(f"Audit saved: {target.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
