"""Profile locally downloaded T1 research samples; never treats them as random samples.

Inputs: data/T1/raw/source_samples/ (see the URLs and hashes in
research/references/data-checks/t1/t1_dataset_deep_checks.json). Uses only the standard library.
Outputs aggregate diagnostics, never supplier names or individual invoice records.
"""

from collections import Counter
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/T1/raw/source_samples"


def date(value):
    if value is None or str(value).strip() in ("", "0000-00-00"):
        return None
    if isinstance(value, (float, int)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date()
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def number(value):
    try:
        return Decimal(str(value)) if value is not None else None
    except InvalidOperation:
        return None


def profile(rows, fields):
    result = {"rows": len(rows), "dates": {}}
    for name in fields:
        values = [date(row.get(name)) for row in rows]
        present = [v for v in values if v is not None]
        result["dates"][name] = {
            "missing_or_invalid": len(values) - len(present),
            "min": str(min(present)) if present else None,
            "max": str(max(present)) if present else None,
        }
    return result


def health_profile(rows):
    result = profile(rows, ["datum_vystaveni", "datum_prijeti", "datum_splatnosti", "datum_uhrady"])
    result["distinct_buyer_ids"] = len({r["odberatel"]["id_company"] for r in rows if r.get("odberatel")})
    result["distinct_supplier_ids"] = len({r["dodavatel"]["id_company"] for r in rows if r.get("dodavatel")})
    result["duplicate_invoice_ids"] = len(rows) - len({r["id_invoice"] for r in rows})
    result["import_ids"] = sorted({r["import_id"] for r in rows})
    result["document_types"] = dict(Counter(r.get("typ_dokladu") for r in rows))
    result["paid_amount_zero"] = sum(number(r.get("castka_uhrazena")) == 0 for r in rows)
    result["gross_amount_nonpositive"] = sum(number(r.get("castka_s_dph")) is not None and number(r["castka_s_dph"]) <= 0 for r in rows)
    result["paid_amount_below_gross_same_currency"] = sum(
        number(r.get("castka_uhrazena")) is not None and number(r.get("castka_s_dph")) is not None
        and r.get("castka_s_dph_mena") == r.get("castka_uhrazena_mena")
        and number(r["castka_uhrazena"]) < number(r["castka_s_dph"]) for r in rows)
    result["paid_before_received"] = sum(
        date(r.get("datum_prijeti")) is not None and date(r.get("datum_uhrady")) is not None
        and date(r["datum_uhrady"]) < date(r["datum_prijeti"]) for r in rows)
    result["paid_late_with_valid_dates"] = sum(
        date(r.get("datum_splatnosti")) is not None and date(r.get("datum_uhrady")) is not None
        and date(r["datum_uhrady"]) > date(r["datum_splatnosti"]) for r in rows)
    result["paid_date_in_1970"] = sum(
        bool(date(r.get("datum_uhrady"))) and date(r["datum_uhrady"]).year == 1970 for r in rows)
    result["missing_paid_and_due_dates"] = sum(
        not date(r.get("datum_uhrady")) and not date(r.get("datum_splatnosti")) for r in rows)
    # Diagnostic gate, not an automatic cleaning policy or proof of bank receipt.
    complete = []
    for row in rows:
        dates = [date(row.get(k)) for k in ("datum_vystaveni", "datum_splatnosti", "datum_uhrady")]
        amount = number(row.get("castka_s_dph"))
        if all(d is not None and d.year >= 2000 for d in dates) and dates[2] >= dates[0] and amount is not None and amount > 0:
            complete.append(row)
    result["positive_rows_with_issue_due_paid_dates_ordered"] = len(complete)
    result["complete_rows_by_buyer_code"] = dict(Counter(str(r["odberatel"]["id_company"]) for r in complete))
    # Different imports may republish invoices; matching identifiers are candidates,
    # not proof of duplicate invoices. Blank supplier references are excluded.
    keys = [(r.get("odberatel", {}).get("id_company"), r.get("dodavatel", {}).get("id_company"),
             r.get("identifikator_dodavatele")) for r in rows if r.get("identifikator_dodavatele")]
    result["repeated_buyer_supplier_supplier_reference_rows"] = len(keys) - len(set(keys))
    return result


def main():
    report = {"scope": "Non-random prefixes / selected pages / first OBJECTID rows in selected fiscal years. Counts describe these samples only.", "sources": {}}
    health = []
    health_paths = [RAW / "cz_health_sample.json", *sorted(RAW.glob("cz_health_page_*.json"))]
    for path in health_paths:
        if path.exists():
            rows = json.loads(path.read_bytes())
            health.extend(rows)
            report["sources"][path.stem] = health_profile(rows)
    if health:
        report["sources"]["cz_health_combined"] = health_profile(health)
    imports_path = RAW / "cz_health_imports_all.json"
    if imports_path.exists():
        rows = json.loads(imports_path.read_bytes())
        report["sources"]["cz_health_imports"] = {
            "rows": len(rows), "organization_ids": len({r["organization_id"] for r in rows}),
            "imported_at_min": min(r["imported_at"] for r in rows),
            "imported_at_max": max(r["imported_at"] for r in rows),
        }
    for path in sorted(RAW.glob("dc_sample_*.json")):
        rows = [f["attributes"] for f in json.loads(path.read_bytes())["features"]]
        result = profile(rows, ["INVOICEDATE", "PAYMENTDATE", "ESTPAYMENTDATE", "RECORDCREATED", "RECORDUPDATEDDATE"])
        result["payment_before_invoice"] = sum(date(r.get("PAYMENTDATE")) is not None and date(r.get("INVOICEDATE")) is not None and date(r["PAYMENTDATE"]) < date(r["INVOICEDATE"]) for r in rows)
        result["estimated_date_equals_payment_date"] = sum(r.get("PAYMENTDATE") is not None and r.get("ESTPAYMENTDATE") == r["PAYMENTDATE"] for r in rows)
        for columns in [("AGENCYCODE", "SUPPLIERNAME", "INVOICENUMBER"), ("AGENCYCODE", "SUPPLIERNAME", "INVOICENUMBER", "VOUCHERNUMBER", "PAYMENTNUMBER")]:
            counts = Counter(tuple(r.get(c) for c in columns) for r in rows)
            result["repeated_rows_on_" + "+".join(columns)] = len(rows) - len(counts)
        result["payment_amount_differs_from_voucher"] = sum(r.get("PAYMENTAMOUNT") != r.get("VOUCHERAMOUNT") for r in rows)
        result["nonpositive_payment_amount"] = sum(number(r.get("PAYMENTAMOUNT")) is not None and number(r["PAYMENTAMOUNT"]) <= 0 for r in rows)
        report["sources"][path.stem] = result
    path = RAW / "cz_mf_prefix.csv"
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        result = profile(rows, ["datum_vystavení", "datum_přijetí", "datum_splatnosti", "datum_úhrady"])
        result["record_types"] = dict(Counter(r["typ_záznamu"] for r in rows))
        result["unique_iri"] = len({r["iri"] for r in rows})
        summary = [r for r in rows if r["typ_záznamu"] == "souhrnný"]
        result["summary_rows"] = profile(summary, ["datum_vystavení", "datum_přijetí", "datum_splatnosti", "datum_úhrady"])
        report["sources"]["cz_mf_prefix"] = result
    path = RAW / "bpi_prefix.xml.part"
    if path.exists():
        traces = [ET.fromstring(t) for t in re.findall(rb"<trace>.*?</trace>", path.read_bytes(), flags=re.S)]
        case_keys, event_keys, activity_counts, receipt_counts, clear_counts = set(), set(), Counter(), Counter(), Counter()
        for trace in traces:
            case_keys.update(c.attrib.get("key") for c in trace if c.tag != "event")
            acts = []
            for event in trace.findall("event"):
                attrs = {c.attrib.get("key"): c.attrib.get("value") for c in event}
                event_keys.update(attrs)
                acts.append(attrs.get("concept:name"))
            activity_counts.update(acts)
            receipt_counts[acts.count("Record Invoice Receipt")] += 1
            clear_counts[acts.count("Clear Invoice")] += 1
        report["sources"]["bpi_prefix"] = {"complete_cases": len(traces), "case_keys": sorted(k for k in case_keys if k), "event_keys": sorted(k for k in event_keys if k), "activity_counts": dict(activity_counts), "invoice_receipt_events_per_case": dict(receipt_counts), "clear_events_per_case": dict(clear_counts)}
    target = ROOT / "research/references/data-checks/t1/t1_dataset_sample_profiles.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
