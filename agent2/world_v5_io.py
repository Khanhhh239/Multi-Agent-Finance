"""Legacy-compatible dataset writer with bounded streaming checksums.

CSV generation and manifest semantics are unchanged. All generated observations
are dữ liệu tổng hợp. Keep the legacy writer unmodified for parity checks.
"""
from collections import Counter
import json

from sme_fraud.generate import WINDOWS, write_csv
from .runtime_v5 import sha256


def save_dataset_streamed(output,tables,n,rate,seed,companies):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty dataset: {output}")
    output.mkdir(parents=True,exist_ok=True)
    from sme_fraud.features import build_features, FEATURE_DESCRIPTIONS
    tables["features"] = build_features(tables)
    for name, rows in tables.items():
        # Optional event tables can be empty on very small configurations; retain a schema.
        fields = None
        if not rows:
            fields = {"advance_events": ["event_id", "advance_id", "company_id", "event_type", "observed_at",
                       "new_due_at", "amount_vnd", "transaction_id", "evidence_on_file"]}.get(name, [])
        write_csv(output/f"{name}.csv", rows, fields)
    splits = {r["transaction_id"]:r["split"] for r in tables["splits"]}
    split_stats = {}
    for split in WINDOWS:
        ground = [r for r in tables["labels"] if splits[r["transaction_id"]]==split]
        positives = sum(r["is_fraud"] for r in ground)
        split_stats[split] = dict(rows=len(ground), fraud_rows=positives, fraud_rate=positives/len(ground),
            fraud_types=dict(Counter(r["fraud_type"] for r in ground if r["is_fraud"])))
    manifest = dict(version="2.0", seed=seed, requested_rows=n, requested_fraud_rate=rate,
        actual_fraud_rows=sum(r["is_fraud"] for r in tables["labels"]), companies=companies,
        timezone="Asia/Ho_Chi_Minh", currency="VND", observation_unit="posted transaction or nonfinancial advance review",
        financial_rows=sum(r["is_financial_entry"] for r in tables["transactions"]),
        hard_negative_rows=sum(bool(r["hard_negative_type"]) for r in tables["labels"]),
        splits=split_stats, fraud_variants=dict(Counter(r["variant"] for r in tables["labels"] if r["is_fraud"])),
        assumptions={"prevalence": "User-selected synthetic scenarios, not an estimate of Vietnam's measured fraud incidence",
            "holidays": "Illustrative fixed dates, not a complete statutory calendar",
            "journal": "TT133/TT200 scenario templates, balanced multi-line VAT and linked auxiliary documents; not a full opening/closing balance reconciliation",
            "accounting_scope": "Historical 2024-2025; TT99 is not implemented for financial years starting from 2026",
            "vat": "Credit method assumed, illustrative invoice rate 10%; not a legal tax eligibility determination",
            "expense_features": "Raw TT200 641/642 and TT133 6421/6422 retained; ML combines them into group 642",
            "auxiliary_documents": "Supporting accounting documents have no additional scored labels and do not change observation prevalence",
            "ids": "Synthetic non-usable contact/account/tax tokens; transaction IDs random and excluded from X",
            "training": "Unsupervised mixed train; labels only for evaluation; known SMEs observed over time",
            "advance_review": "Nonfinancial observation; excluded from journal lines and cash-flow totals"},
        accounting_frameworks={r['company_id']:r['accounting_framework'] for r in tables['companies']},
        journal_documents=len(tables['journal_documents']),journal_lines=len(tables['journal_lines']),
        feature_columns=list(FEATURE_DESCRIPTIONS), files={})
    for name in tables:
        path = output/f"{name}.csv"
        manifest["files"][path.name] = dict(rows=len(tables[name]), sha256=sha256(path))
    (output/"manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    dictionary = {name: {field: {"example": rows[0].get(field),
                    "kind": "integer" if isinstance(rows[0].get(field), int) else "number" if isinstance(rows[0].get(field), float) else "text"}
                for field in rows[0]} for name, rows in tables.items() if rows}
    dictionary["features"] = FEATURE_DESCRIPTIONS
    (output/"data_dictionary.json").write_text(json.dumps(dictionary, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
