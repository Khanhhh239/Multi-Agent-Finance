"""Truth is isolated here, never passed to a reconciliation method."""

from collections import defaultdict
from datetime import date
import random
import statistics
from time import perf_counter

from .data import allocation_errors, snapshot
from .matching import reconcile


def edge(row):
    return row["tenant_id"], row["transaction_id"], row["invoice_id"]


def metrics(invoices, bank, truth, result):
    """Requires independently reviewed, exhaustive truth for the input universe.

    Zero predicted positives => precision is null, not a misleading perfect score.
    Money is reported separately per currency, with no implicit FX conversion.
    """
    inv = {(r["tenant_id"], r["invoice_id"]) for r in invoices}
    tx = {(r["tenant_id"], r["transaction_id"]) for r in bank}
    labels = [r for r in truth if (r["tenant_id"], r["invoice_id"]) in inv
              and (r["tenant_id"], r["transaction_id"]) in tx]
    errors = allocation_errors(invoices, bank, labels)
    if errors:
        raise ValueError(f"invalid truth: {errors}")
    prediction_errors = allocation_errors(invoices, bank, result["allocations"])
    if prediction_errors:
        raise ValueError(f"invalid predictions: {prediction_errors}")
    actual = {edge(r): r for r in labels}
    predicted = {edge(r): r for r in result["allocations"]}
    correct = {k for k, r in predicted.items() if k in actual
               and r["amount_minor"] == actual[k]["amount_minor"]
               and r["currency"] == actual[k]["currency"]}
    candidates = {tuple(row) for row in result["candidate_edges"]}
    money = defaultdict(lambda: {"receipt_minor": 0, "allocated_minor": 0,
                                 "wrongly_allocated_minor": 0, "truth_minor": 0,
                                 "unallocated_minor": 0, "missing_truth_minor": 0})
    for r in bank:
        money[r["currency"]]["receipt_minor"] += r["amount_minor"]
    for r in labels:
        money[r["currency"]]["truth_minor"] += r["amount_minor"]
    for key, r in predicted.items():
        amount = r["amount_minor"]
        money[r["currency"]]["allocated_minor"] += amount
        expected = actual.get(key, {}).get("amount_minor", 0)
        money[r["currency"]]["wrongly_allocated_minor"] += max(0, amount - expected)
    for key, r in actual.items():
        assigned = predicted.get(key, {}).get("amount_minor", 0)
        money[r["currency"]]["missing_truth_minor"] += max(0, r["amount_minor"] - assigned)
    for row in money.values():
        row["unallocated_minor"] = row["receipt_minor"] - row["allocated_minor"]
    dates = [abs((date.fromisoformat(predicted[k]["payment_on"])
                  - date.fromisoformat(actual[k]["payment_on"])).days)
             for k in correct]
    scenarios = defaultdict(lambda: {"truth_edges": 0, "correct_edges": 0})
    for key, row in actual.items():
        scenarios[row.get("scenario", "unspecified")]["truth_edges"] += 1
        scenarios[row.get("scenario", "unspecified")]["correct_edges"] += int(key in correct)
    counts = {state: sum(d["status"] == state for d in result["decisions"])
              for state in ("auto", "review", "unmatched")}
    return {"precision": len(correct) / len(predicted) if predicted else None,
            "recall": len(correct) / len(actual) if actual else None,
            "candidate_recall": len(candidates & actual.keys()) / len(actual) if actual else None,
            "truth_edges": len(actual), "excluded_truth_edges": len(truth) - len(labels),
            "predicted_edges": len(predicted), "correct_edges": len(correct),
            "auto_receipt_rate": counts["auto"] / len(bank) if bank else None,
            "manual_review_rate": counts["review"] / len(bank) if bank else None,
            "unmatched_rate": counts["unmatched"] / len(bank) if bank else None,
            "decision_counts": counts, "money_by_currency": dict(money),
            "payment_date_mae_days_on_correct_links": statistics.mean(dates) if dates else None,
            "invariant_errors": allocation_errors(invoices, bank, result["allocations"]),
            "by_scenario": dict(scenarios)}


def evaluate(raw_invoices, raw_bank, truth, cutoff, method, config=None):
    known_i = {(r.get("tenant_id"), r.get("invoice_id")) for r in raw_invoices}
    known_b = {(r.get("tenant_id"), r.get("transaction_id")) for r in raw_bank}
    if any((r["tenant_id"], r["invoice_id"]) not in known_i
           or (r["tenant_id"], r["transaction_id"]) not in known_b for r in truth):
        raise ValueError("truth refers to an endpoint absent from raw inputs")
    invoices, iq = snapshot(raw_invoices, "invoices", cutoff)
    bank, bq = snapshot(raw_bank, "bank", cutoff)
    start = perf_counter()
    result = reconcile(invoices, bank, method, config)
    elapsed = perf_counter() - start
    measured = metrics(invoices, bank, truth, result)
    rng = random.Random(2026)
    shuffled_i, shuffled_b = list(raw_invoices), list(raw_bank)
    rng.shuffle(shuffled_i)
    rng.shuffle(shuffled_b)
    # Re-ingestion of the same raw deliveries must leave the result unchanged.
    replay_i, _ = snapshot(shuffled_i + raw_invoices, "invoices", cutoff)
    replay_b, _ = snapshot(shuffled_b + raw_bank, "bank", cutoff)
    replay = reconcile(replay_i, replay_b, method, config)
    measured.update({"runtime_seconds": elapsed,
                     "order_and_replay_stable": result["allocation_hash"] == replay["allocation_hash"],
                     "allocation_hash": result["allocation_hash"],
                     "quality": {"invoices": iq, "bank": bq}})
    return measured


def describe(values):
    values = [v for v in values if v is not None]
    return {"n": len(values), "mean": statistics.mean(values) if values else None,
            "std": statistics.stdev(values) if len(values) > 1 else None,
            "min": min(values) if values else None, "max": max(values) if values else None}


def paired_interval(differences):
    """Paired seed bootstrap interval; descriptive generator variability only."""
    if not differences:
        return None
    rng = random.Random(803)
    samples = sorted(statistics.mean(rng.choices(differences, k=len(differences)))
                     for _ in range(1000))
    return {"mean_difference": statistics.mean(differences),
            "bootstrap_95_percent": [samples[24], samples[974]], "n_seeds": len(differences)}
