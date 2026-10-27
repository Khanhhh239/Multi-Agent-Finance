"""Run T0 quality checks on the locked v3_final_20261027 synthetic cohort.

The full-cohort check maps Parquet invoice rows to the ERP input schema. A
deterministic 200-invoice sample also exercises XML serialization and parsing,
then the existing labelled error-injection benchmark.
"""
from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.data.schema import inject_errors, quality_gate
from agent1.synth.einvoice import invoice_to_xml, parse_xml


ROOT = Path(__file__).resolve().parents[1]
COHORT = ROOT / "data/synthetic/v3_final_20261027_cohort.json"
WORLD_DIR = ROOT / "data/synthetic"
OUT = ROOT / "outputs/wp0/t0_final_20261027"
ERROR_COLUMNS = [
    "missing_seller_mst", "missing_buyer_mst", "missing_symbol",
    "missing_invoice_no", "missing_issue_date", "missing_amount_net",
    "missing_vat", "missing_amount_gross", "missing_currency",
    "bad_seller_mst", "bad_buyer_mst", "bad_issue_date",
    "due_before_issue", "sum_mismatch", "bad_vat_rate",
    "negative_amount", "duplicate_key", "bad_currency", "any_error",
]


def run(cohort_path: Path, output_dir: Path, sample_per_world: int) -> None:
    cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
    if sample_per_world < 1:
        raise ValueError("sample_per_world must be positive")
    rows = []
    xml_rows = []
    for world in cohort["worlds"]:
        name = world["name"]
        directory = WORLD_DIR / name
        manifest_path = directory / "manifest.json"
        manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        if manifest_hash != world["manifest_sha256"]:
            raise ValueError(f"Cohort manifest hash mismatch: {name}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for table in ("invoices.parquet", "firms.parquet", "customers.parquet"):
            table_hash = hashlib.sha256((directory / table).read_bytes()).hexdigest()
            if table_hash != manifest["tables_sha256"][table]:
                raise ValueError(f"Table hash mismatch: {name}/{table}")
        inv = pd.read_parquet(directory / "invoices.parquet")
        firms = pd.read_parquet(directory / "firms.parquet")
        customers = pd.read_parquet(directory / "customers.parquet")
        d = inv.merge(firms[["firm_id", "mst"]].rename(columns={"mst": "seller_mst"}),
                      on="firm_id", how="left", validate="many_to_one")
        d = d.merge(customers[["customer_id", "mst"]].rename(columns={"mst": "buyer_mst"}),
                    on="customer_id", how="left", validate="many_to_one")
        d["vat"] = np.rint(d["amount_net"] * d["vat_rate"])
        errors = quality_gate(d, today="2026-10-27")
        counts = errors[ERROR_COLUMNS].sum().astype(int).to_dict()
        rows.append({"world": name, "role": world["role"], "n": len(d), **counts})
        print(f"{name}: {len(d):,} invoices, {counts['any_error']:,} flagged", flush=True)

        sample_indices = np.linspace(0, len(inv) - 1, min(sample_per_world, len(inv)), dtype=int)
        firm_lookup = firms.set_index("firm_id")
        customer_lookup = customers.set_index("customer_id")
        for i in sample_indices:
            r = inv.iloc[i]
            parsed = parse_xml(BytesIO(invoice_to_xml(
                r, firm_lookup.loc[r["firm_id"]], customer_lookup.loc[r["customer_id"]]
            )))
            if (parsed["invoice_key"] != r["invoice_id"] or
                    parsed["symbol"] != r["symbol"] or
                    parsed["invoice_no"] != r["invoice_no"] or
                    parsed["seller_mst"] != firm_lookup.loc[r["firm_id"], "mst"] or
                    parsed["buyer_mst"] != customer_lookup.loc[r["customer_id"], "mst"] or
                    parsed["issue_date"] != r["issue_date"].strftime("%Y-%m-%d") or
                    parsed["due_date"] != r["due_date"].strftime("%Y-%m-%d") or
                    parsed["currency"] != r["currency"] or
                    abs(parsed["amount_gross"] - r["amount_gross"]) > 1 or
                    abs(parsed["amount_net"] - r["amount_net"]) > 1):
                raise AssertionError(f"XML roundtrip mismatch: {name}/{r['invoice_id']}")
            xml_rows.append(parsed)

    summary = pd.DataFrame(rows)
    total = {c: int(summary[c].sum()) for c in ERROR_COLUMNS}
    clean_xml = pd.DataFrame(xml_rows)
    clean_errors = quality_gate(clean_xml, today="2026-10-27")
    dirty, truth = inject_errors(clean_xml, rate=0.3, seed=1)
    predicted = quality_gate(dirty, today="2026-10-27")["any_error"]
    tp = int((predicted & truth).sum())
    fp = int((predicted & ~truth).sum())
    fn = int((~predicted & truth).sum())
    result = {
        "cohort": cohort_path.name,
        "cohort_sha256": hashlib.sha256(cohort_path.read_bytes()).hexdigest(),
        "source_code_sha256_in_cohort": cohort["source_code_sha256"],
        "verified_manifest_hashes": len(rows),
        "verified_table_hashes": len(rows) * 3,
        "as_of": "2026-10-27",
        "worlds": len(rows),
        "n_invoices": int(summary["n"].sum()),
        "full_cohort_flags": total,
        "xml_sample_n": len(clean_xml),
        "xml_clean_flagged": int(clean_errors["any_error"].sum()),
        "xml_injected_n": int(truth.sum()),
        "xml_injection_tp": tp,
        "xml_injection_fp": fp,
        "xml_injection_fn": fn,
        "xml_injection_precision": tp / max(tp + fp, 1),
        "xml_injection_recall": tp / max(tp + fn, 1),
        "xml_sample_per_world": sample_per_world,
        "xml_injection_seed": 1,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output_dir / "world_quality.csv", index=False)
    (output_dir / "summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", type=Path, default=COHORT)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--sample-per-world", type=int, default=25)
    args = parser.parse_args()
    run(args.cohort, args.out, args.sample_per_world)
