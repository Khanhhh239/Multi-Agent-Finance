"""RecBench payout-bank task only; no invented ledger/settlement unbundling."""

from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
import re
from time import perf_counter

from .adapters import csv_rows, verified_source
from .data import fingerprint, iso_date, prepare_experiment_output, write_json


def signed_minor(value):
    if type(value) is int:
        amount = value
    elif isinstance(value, str) and re.fullmatch(r"[+-]?[0-9]+", value):
        amount = int(value)
    else:
        raise ValueError("signed amount must be an exact integer or integer string")
    if amount == 0:
        raise ValueError("zero settlement amount unsupported")
    return amount


def match(payouts, banks, max_lag_days=7):
    if type(max_lag_days) is not int or not 0 <= max_lag_days <= 31:
        raise ValueError("max_lag_days must be an integer in [0,31]")
    pool, ref_index = defaultdict(list), defaultdict(list)
    seen = set()
    for p in payouts:
        if p["payout_id"] in seen:
            raise ValueError("duplicate payout")
        seen.add(p["payout_id"])
        iso_date(p["expected_arrival_date"])
        amount = signed_minor(p["amount_minor"])
        pool[(p["settle_currency"], amount)].append(p)
        ref_index[p["payout_ref"].casefold()].append(p["payout_id"])
    proposals, decisions, seen_bank = {}, {}, set()
    for b in sorted(banks, key=lambda r: r["stmt_line_id"]):
        bid = b["stmt_line_id"]
        if bid in seen_bank:
            raise ValueError("duplicate bank ID")
        seen_bank.add(bid)
        iso_date(b["value_date"])
        amount = signed_minor(b["amount_minor"])
        if b["direction"] not in ("credit", "debit"):
            raise ValueError("invalid bank direction/amount")
        if (amount > 0) != (b["direction"] == "credit"):
            raise ValueError("bank sign disagrees with direction")
        candidates = [p for p in pool[(b["currency"], amount)]
                      if abs((date.fromisoformat(b["value_date"]) - date.fromisoformat(p["expected_arrival_date"])).days) <= max_lag_days]
        known = {pid for token in re.findall(r"[a-z0-9_-]+", b["reference"].casefold())
                 for pid in ref_index.get(token, ())}
        refs = [p for p in candidates if p["payout_id"] in known]
        if known and (len(refs) != len(known) or not refs):
            decisions[bid] = "review"
            continue
        selected = refs if known else candidates
        if len(selected) == 1:
            proposals[bid] = selected[0]["payout_id"]
        else:
            decisions[bid] = "review" if candidates else "unmatched"
    claims = Counter(proposals.values())
    predictions = {b: p for b, p in proposals.items() if claims[p] == 1}
    decisions.update({b: "auto" if b in predictions else "review" for b in proposals})
    return {"predictions": predictions, "decisions": decisions, "prediction_hash": fingerprint(predictions)}


def score(payouts, banks, truth, labels, predictions):
    pids = {p["payout_id"] for p in payouts}
    bids = {b["stmt_line_id"] for b in banks}
    if len(pids) != len(payouts) or len(bids) != len(banks):
        raise ValueError("duplicate input IDs")
    expected, absent = defaultdict(set), set()
    seen = set()
    for r in truth:
        pair = r["stmt_line_id"], r["payout_id"]
        if pair in seen:
            raise ValueError("duplicate truth edge")
        seen.add(pair)
        if pair[0] not in bids or pair[1] not in pids:
            absent.add(pair[0])
        expected[pair[0]].add(pair[1])
    by_label = {r["stmt_line_id"]: r for r in labels}
    if len(by_label) != len(labels) or set(by_label) != bids:
        raise ValueError("bank labels do not cover observed bank IDs exactly")
    if any(not isinstance(r["is_matchable"], str) or r["is_matchable"].lower() not in ("true", "false") for r in labels):
        raise ValueError("matchable labels must be explicit true/false strings")
    # Only explicit non-matchable labels are negatives; no truth is not enough.
    negatives = {bid for bid, r in by_label.items() if r["is_matchable"].lower() == "false" and bid not in expected}
    complete = {bid for bid in expected if bid in bids and bid not in absent}
    universe = complete | negatives
    unknown = bids - universe
    if any(b not in bids or p not in pids for b, p in predictions.items()):
        raise ValueError("prediction endpoint absent")
    eligible = {b: p for b, p in predictions.items() if b in universe}
    correct = sum(expected.get(b) == {p} for b, p in eligible.items())
    return {"truth_edges_total": len(truth), "truth_groups_complete": len(complete),
            "truth_groups_missing_endpoints": len(absent), "explicit_negative_bank_rows": len(negatives),
            "unknown_bank_rows": len(unknown), "predictions_on_unknown_bank_rows": sum(b in unknown for b in predictions),
            "nonmatchable_labels_with_truth": sum(bid in expected and r["is_matchable"].lower() == "false" for bid, r in by_label.items()),
            "predictions_on_nonmatchable_labels": sum(by_label[b]["is_matchable"].lower() == "false" for b in predictions),
            "scored_predictions": len(eligible), "correct_links": correct,
            "exact_link_precision": correct / len(eligible) if eligible else None,
            "exact_link_recall": correct / len(complete) if complete else None,
            "observed_truth_group_coverage": len(complete) / len(expected) if expected else None,
            "by_currency": {c: {"bank_rows": sum(b["currency"] == c for b in banks),
                                 "scored_bank_rows": sum(b["currency"] == c and b["stmt_line_id"] in universe for b in banks)}
                            for c in sorted({b["currency"] for b in banks})}}


def run(folder, output):
    names = [f"small/csv/{n}.csv" for n in ("payouts", "bank_statements", "truth_payout_bank", "labels_bank")]
    provenance = verified_source(folder, names)
    output = prepare_experiment_output(output)
    tables = {n: csv_rows(Path(folder) / f"small/csv/{n}.csv") for n in ("payouts", "bank_statements")}
    start = perf_counter()
    result = match(tables["payouts"], tables["bank_statements"])
    runtime = perf_counter() - start
    write_json(output / "predictions.json", result)  # Saved before label loading.
    truth = csv_rows(Path(folder) / "small/csv/truth_payout_bank.csv")
    labels = csv_rows(Path(folder) / "small/csv/labels_bank.csv")
    measured = score(tables["payouts"], tables["bank_statements"], truth, labels, result["predictions"])
    measured["runtime_seconds"] = runtime
    measured["order_stable"] = result["prediction_hash"] == match(tables["payouts"][::-1], tables["bank_statements"][::-1])["prediction_hash"]
    report = {"task": "synthetic_payout_bank", "provenance": provenance, "metrics": measured,
              "limits": ["Development snapshot already inspected, not blind",
                         "Missing endpoints remain unknown, never negatives", "No ledger/settlement unbundling",
                         "CSV hashes verified; release Parquet hashes not verified"],
              "config": {"max_lag_days": 7, "feature_allowlist": ["currency", "amount_minor", "date", "payout_ref", "bank_reference", "direction"]}}
    write_json(output / "report.json", report)
    return report
