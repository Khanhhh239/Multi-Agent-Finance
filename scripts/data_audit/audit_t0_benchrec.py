"""Inspect a downloaded BenchRec Kaggle snapshot; never run an invoice matcher.

Verifies the source manifest and profiles all CSV rows. Allocation-key semantics,
group matching and source timing still require a separate GL-bank contract.
"""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from t0.data import read_json, write_json

FILES = {
    "train": "BenchRec_cash_v1.0_train.csv",
    "eval": "BenchRec_cash_v1.0_eval.csv",
    "solution": "BenchRec_cash_v1.0_solution.csv",
    "submission_example": "MatcherByChatGPT_submission.csv",
}


def profile_csv(path):
    counts, present, shapes, issues = Counter(), Counter(), Counter(), Counter()
    ids = {"A_id": set(), "B_id": set()}
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("Missing or repeated CSV header")
        for row in reader:
            counts["rows"] += 1
            if None in row or any(value is None for value in row.values()):
                issues["malformed_csv_rows"] += 1
                continue
            present.update(key for key, value in row.items() if value)
            if "A_transactionType" in row and "B_transactionType" in row:
                shapes[("A" if row.get("A_id") else "") + ("B" if row.get("B_id") else "") or "neither"] += 1
            for key in ids:
                value = row.get(key)
                if value:
                    counts[key + "_occurrences"] += 1
                    counts[key + "_duplicate_occurrences"] += int(value in ids[key])
                    ids[key].add(value)
            for key in ("A_amount", "B_amount"):
                value = row.get(key)
                if value:
                    try:
                        amount = Decimal(value)
                        if not amount.is_finite():
                            raise ValueError("Non-finite amount")
                        counts[key + "_negative"] += int(amount < 0)
                        counts[key + "_zero"] += int(amount == 0)
                    except (InvalidOperation, ValueError):
                        issues[key + "_parse_errors"] += 1
            for key in ("A_importDate", "A_valueDate", "B_importDate", "B_valueDate", "matchDate"):
                if row.get(key):
                    try:
                        date.fromisoformat(row[key])
                    except ValueError:
                        issues[key + "_non_iso_values"] += 1
            if row.get("B_id") and "B_transactionType" in row:
                counts["B_rows_with_target"] += bool(row.get("targetAllocation"))
                counts["B_rows_without_target"] += not row.get("targetAllocation")
    return {"columns": reader.fieldnames, **counts, "nonempty_counts": dict(present),
            "row_shapes_by_present_id": dict(shapes), "issues": dict(issues),
            "unique_id_counts": {key: len(values) for key, values in ids.items()}}, ids


def audit(directory):
    directory = Path(directory)
    manifest = read_json(directory / "source_manifest.json")
    if manifest.get("source_id") != "benchrec-kaggle-v3" or manifest.get("download_status") != "downloaded":
        raise ValueError("Expected a downloaded BenchRec Kaggle v3 manifest")
    if manifest.get("use_policy") != "inspection_only_excluded_from_matching":
        raise ValueError("Snapshot must remain inspection-only")
    entries = {item["file"]: item for item in manifest["files"]}
    if len(entries) != len(manifest["files"]) or set(entries) != set(FILES.values()):
        raise ValueError("Unexpected or duplicate source files")
    profiles, identities = {}, {}
    for role, name in FILES.items():
        payload = (directory / name).read_bytes()
        if len(payload) != entries[name]["bytes"] or hashlib.sha256(payload).hexdigest() != entries[name]["sha256"]:
            raise ValueError("Raw hash/size mismatch: " + name)
        profiles[role], identities[role] = profile_csv(directory / name)
    expected = set(profiles["train"]["columns"])
    if not {"A_id", "B_id", "A_allocation", "targetAllocation", "matchId"} <= expected:
        raise ValueError("Unexpected transaction schema")
    if set(profiles["eval"]["columns"]) != expected or set(profiles["solution"]["columns"]) != {"B_id", "targetAllocation", "Usage"}:
        raise ValueError("Unexpected evaluation or solution schema")
    solution_ids, eval_ids = identities["solution"]["B_id"], identities["eval"]["B_id"]
    return {"audited_at_utc": datetime.now(timezone.utc).isoformat(), "source": manifest,
            "audit_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "scope": "Full CSV structural preflight: hashes, row grain, ID overlap, field presence, decimal/ISO-date parsing only",
            "profiles": profiles,
            "identity_checks": {"eval_B_ids_missing_solution": len(eval_ids - solution_ids),
                "solution_B_ids_absent_from_eval": len(solution_ids - eval_ids),
                "train_eval_A_id_overlap": len(identities["train"]["A_id"] & identities["eval"]["A_id"]),
                "train_eval_B_id_overlap": len(identities["train"]["B_id"] & eval_ids)},
            "matcher_runs": 0, "accepted_for_current_invoice_matcher": False,
            "limits": ["Publisher describes real GL-bank data; origin not independently authenticated",
                "targetAllocation is an allocation-key target, not a verified invoice-bank amount edge",
                "No allocation-label correctness, group-money conservation or availability backtest verified",
                "Historical matchId/matchDate/matchRule/matchedBy, targetAllocation and solution need leakage controls",
                "Submission example is someone else's predictions, never ground truth",
                "No account, transaction reference, allocation value or transaction IDs copied to report"]}


def audit_train_semantics(directory):
    """Train-only diagnostics; discrepancies are counted, never repaired.

    matchId is privileged historical metadata used only in this audit, never
    supplied to the baselines. No conclusion about causes of discrepancies.
    """
    from t0.benchrec import csv_rows, parse_allocations, verified_path
    groups = defaultdict(lambda: {"A": [], "B": []})
    signs = Counter()
    for row in csv_rows(verified_path(directory, FILES["train"])):
        side = "A" if row["A_id"] else "B"
        groups[row["matchId"]][side].append(row)
        signs[(side, row[side + "_debitOrCredit"], "negative" if Decimal(row[side + "_amount"]) < 0 else "positive")] += 1
    counts, shape, discrepancy = Counter(), Counter(), defaultdict(Decimal)
    for group in groups.values():
        aa, bb = group["A"], group["B"]
        shape[f"A{min(3, len(aa))}_B{min(3, len(bb))}"] += 1
        if not aa or not bb:
            continue
        counts["groups_with_both_sides"] += 1
        a_keys = {row["A_allocation"] for row in aa}
        counts["groups_with_any_B_target_outside_A_group_keys"] += any(
            not parse_allocations(row["targetAllocation"]) <= a_keys for row in bb)
        scope = {(row["A_currencyCode"], row["A_account"]) for row in aa}
        scope.update((row["B_currencyCode"], row["B_account"]) for row in bb)
        counts["groups_crossing_currency_or_account"] += len(scope) != 1
        delta = sum(Decimal(row["A_amount"]) for row in aa) - sum(Decimal(row["B_amount"]) for row in bb)
        counts["equal_signed_sum_groups"] += delta == 0
        counts["different_signed_sum_groups"] += delta != 0
        if len(scope) == 1:
            currency, _ = next(iter(scope))
            discrepancy[currency] += abs(delta)
    return {"scope": "Historical train matchId groups only; no eval label tuning or raw repair",
            "counts": dict(counts), "group_shape_counts_capped_at_3": dict(shape),
            "side_dr_cr_signed_amount_counts": [{"side": side, "code": code, "sign": sign, "rows": n}
                for (side, code, sign), n in sorted(signs.items())],
            "absolute_group_sum_discrepancy_by_currency": {k: str(v) for k, v in discrepancy.items()},
            "limits": ["Unequal sums may involve adjustments or label issues; causes not identified from this audit",
                       "Allocation labels are business-characteristic sets, not verified transaction-ID allocation edges",
                       "Baseline money-conservation constraints can leave true labelled B rows unmatched; not evidence of bad matching labels alone"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/T0/raw/benchrec_kaggle/2026-10-19-v3")
    parser.add_argument("--output", type=Path, default=ROOT / "data/T0/processed/source-audits/benchrec-kaggle.json")
    parser.add_argument("--train-semantics", action="store_true", help="Also inspect train historical groups; never run matching")
    args = parser.parse_args()
    report = audit(args.input)
    if args.train_semantics:
        report["train_semantics"] = audit_train_semantics(args.input)
    write_json(args.output, report)
    for role, profile in report["profiles"].items():
        print(f"{role}: rows={profile['rows']}; issues={profile['issues']}")
    print(f"Structural preflight only; matcher_runs=0; report={args.output}")


if __name__ == "__main__":
    main()
