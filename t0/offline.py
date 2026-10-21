"""Reproducible T0 v2 capability benchmark and local decision/Gold exercise."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import platform
import random
from time import perf_counter

from . import allocation
from .data import fingerprint, prepare_experiment_output, read_json, read_jsonl, write_json, write_jsonl
from .evaluation import describe
from .ledger import EventStore
from .matching import METHODS, reconcile


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "research/references/data-checks/t0/ar-benchmark-plan-v2.json"
V2_METHODS = ("v2_no_amount_groups", "v2_no_overpayment", "v2_full")


def generate(seed, blocks=4, profile="clean"):
    if type(seed) is not int or type(blocks) is not int or blocks < 1 or profile not in ("clean", "masked"):
        raise ValueError("invalid generator configuration")
    rng = random.Random(seed)
    invoices, payments, truth, intents = [], [], [], []
    serial = Counter()

    def identifier(kind):
        serial[kind] += 1
        return f"S{seed}-{kind}-{rng.getrandbits(64):016x}"

    def invoice(party, amount, scenario, currency="VND", tenant="SYNTH"):
        r = {"tenant_id": tenant, "id": identifier("I"), "invoice_number": identifier("INV"),
             "side": "AR", "party_id": party, "party_name": "Cong ty Mau", "currency": currency,
             "amount_minor": amount, "issued_on": "2025-01-01", "due_on": "2025-01-31",
             "available_on": "2025-01-01"}
        invoices.append(r)
        return r

    def payment(targets, amounts, scenario, gross=None, reference=True, day="2025-01-31", party=None):
        i = targets[0]
        r = {"tenant_id": i["tenant_id"], "id": identifier("P"), "side": "AR",
             "party_id": i["party_id"] if party is None else party, "currency": i["currency"],
             "amount_minor": sum(amounts) if gross is None else gross, "payment_on": day,
             "available_on": day, "reference": " + ".join(t["invoice_number"] for t in targets) if reference else "Thanh toan"}
        payments.append(r)
        intent = {"payment_id": r["id"], "scenario": scenario,
                  "instructions": [{"invoice_id": t["id"], "amount_minor": a} for t, a in zip(targets, amounts)]}
        intents.append(intent)
        for t, a in zip(targets, amounts):
            if a:
                truth.append({"tenant_id": t["tenant_id"], "payment_id": r["id"], "invoice_id": t["id"],
                              "side": "AR", "currency": t["currency"], "amount_minor": a, "scenario": scenario})
        return r

    for block in range(blocks):
        for currency in ("VND", "USD"):
            unit = 100 if currency == "USD" else 100_000
            amount = rng.randint(20, 500) * unit
            # Separate parties isolate mechanisms; frequencies are deliberately balanced.
            party = lambda name: f"S{seed}-{block}-{currency}-{name}"
            i = invoice(party("single"), amount, "single", currency)
            payment([i], [amount], "single")
            i = invoice(party("partial"), amount, "partial", currency)
            part = amount // 3
            payment([i], [part], "partial", day="2025-01-30")
            payment([i], [amount - part], "partial")
            i = invoice(party("overpayment"), amount, "overpayment", currency)
            payment([i], [amount], "overpayment", gross=amount + unit)
            pair = [invoice(party("group"), n * unit, "group", currency) for n in (7, 13)]
            payment(pair, [r["amount_minor"] for r in pair], "group")
            pair = [invoice(party("amount_group"), n * unit, "amount_group", currency) for n in (9, 17)]
            payment(pair, [r["amount_minor"] for r in pair], "amount_group", reference=False)
            pair = [invoice(party("partial_group"), n * unit, "partial_group", currency) for n in (11, 19)]
            payment(pair, [5 * unit, 8 * unit], "partial_group")
            i = invoice(party("ambiguous"), amount, "ambiguous", currency)
            invoice(i["party_id"], amount, "ambiguous", currency)
            payment([i], [amount], "ambiguous", reference=False)
            invoice(party("unpaid"), amount, "unpaid", currency)
            i = invoice(party("bank_only"), amount, "bank_only", currency)
            payment([i], [0], "bank_only", gross=amount, reference=False, party="UNKNOWN")
            i = invoice(party("credit_note"), amount - unit, "credit_note", currency)
            # A disclosed credit reduces open obligation; it is never a bank receipt.
            intents.append({"scenario": "credit_note", "invoice_id": i["id"], "noncash_minor": unit,
                            "face_minor": amount, "known_on": "2025-01-20"})
            payment([i], [amount - unit], "credit_note")
            i = invoice(party("fee_net"), amount, "fee_net", currency)
            p = payment([i], [amount], "fee_net")
            intents.append({"scenario": "fee_net", "payment_id": p["id"], "gross_minor": amount,
                            "net_bank_minor": amount - unit, "fee_minor": unit})
            i = invoice(party("late_arrival"), amount, "late_arrival", currency)
            i["available_on"] = "2025-03-01"
            payment([i], [amount], "late_arrival")
    # Observation channel follows intent creation; it cannot change truth.
    if profile == "masked":
        for p in payments:
            if rng.random() < 0.5:
                p["reference"] = "Thanh toan"
    return invoices, payments, truth, {"seed": seed, "profile": profile, "blocks": blocks,
        "cutoff": "2025-02-01", "intents": intents, "truth_exhaustive": True,
        "task": "synthetic_AR_invoice_payment", "limitations": "capability cases, not SME distribution"}


def legacy_inputs(invoices, payments):
    inv = [{"tenant_id": i["tenant_id"], "invoice_id": i["invoice_number"], "customer_id": i["party_id"],
            "customer_name": i.get("party_name", ""), "currency": i["currency"], "amount_minor": i["amount_minor"],
            "issued_on": i["issued_on"], "due_on": i["due_on"]} for i in invoices]
    bank = [{"tenant_id": p["tenant_id"], "transaction_id": p["id"], "customer_id": p["party_id"],
             "counterparty": "Cong ty Mau", "currency": p["currency"], "amount_minor": p["amount_minor"],
             "booked_on": p["payment_on"], "reference": p["reference"]} for p in payments]
    return inv, bank


def predict(invoices, payments, method, config):
    if method in V2_METHODS:
        return allocation.allocate(invoices, payments, config,
                                   groups=method != "v2_no_amount_groups", overpayment=method != "v2_no_overpayment")
    inv, bank = legacy_inputs(invoices, payments)
    result = reconcile(inv, bank, method)
    ids = {(i["tenant_id"], i["invoice_number"]): i["id"] for i in invoices}
    result["allocations"] = [{"tenant_id": a["tenant_id"], "payment_id": a["transaction_id"],
                              "invoice_id": ids[(a["tenant_id"], a["invoice_id"])], "currency": a["currency"],
                              "side": "AR", "amount_minor": a["amount_minor"]} for a in result["allocations"]]
    result["candidate_edges"] = [(t, p, ids[(t, i)]) for t, p, i in result["candidate_edges"]]
    result["decisions"] = [{**d, "payment_id": d["transaction_id"]} for d in result["decisions"]]
    result["allocation_hash"] = fingerprint(result["allocations"])
    return result


def metrics(invoices, payments, truth, result, source_universe=None):
    errors = allocation.invariant_errors(invoices, payments, result["allocations"])
    if errors:
        raise ValueError(f"invalid prediction: {errors}")
    inv = {(i["tenant_id"], i["id"]) for i in invoices}
    pay = {(p["tenant_id"], p["id"]) for p in payments}
    known_i, known_p = source_universe or (inv, pay)
    if any((r["tenant_id"], r["invoice_id"]) not in known_i or
           (r["tenant_id"], r["payment_id"]) not in known_p for r in truth):
        raise ValueError("truth endpoint absent from raw universe, not a future observation")
    labels = [r for r in truth if (r["tenant_id"], r["invoice_id"]) in inv and (r["tenant_id"], r["payment_id"]) in pay]
    if allocation.invariant_errors(invoices, payments, labels):
        raise ValueError("invalid exhaustive truth")
    edge = lambda a: (a["tenant_id"], a["payment_id"], a["invoice_id"])
    actual, predicted = {edge(a): a for a in labels}, {edge(a): a for a in result["allocations"]}
    correct = {k for k, a in predicted.items() if k in actual and a["amount_minor"] == actual[k]["amount_minor"]}
    money = defaultdict(lambda: Counter(receipt_minor=0, allocated_minor=0, wrong_minor=0, missing_minor=0))
    for p in payments:
        money[p["currency"]]["receipt_minor"] += p["amount_minor"]
    for k, a in predicted.items():
        money[a["currency"]]["allocated_minor"] += a["amount_minor"]
        money[a["currency"]]["wrong_minor"] += max(0, a["amount_minor"] - actual.get(k, {}).get("amount_minor", 0))
    for k, a in actual.items():
        money[a["currency"]]["missing_minor"] += max(0, a["amount_minor"] - predicted.get(k, {}).get("amount_minor", 0))
    for values in money.values():
        values["unallocated_minor"] = values["receipt_minor"] - values["allocated_minor"]
    scenarios = defaultdict(lambda: Counter(truth_edges=0, correct_edges=0))
    for k, a in actual.items():
        scenarios[a["scenario"]]["truth_edges"] += 1
        scenarios[a["scenario"]]["correct_edges"] += k in correct
    return {"precision": len(correct) / len(predicted) if predicted else None,
            "recall": len(correct) / len(actual) if actual else None,
            "candidate_recall": len(set(map(tuple, result["candidate_edges"])) & actual.keys()) / len(actual) if actual else None,
            "truth_edges": len(actual), "excluded_future_truth_edges": len(truth) - len(labels),
            "predicted_edges": len(predicted), "correct_edges": len(correct),
            "money_by_currency": {k: dict(v) for k, v in money.items()},
            "by_scenario": {k: dict(v) for k, v in scenarios.items()},
            "by_currency": {c: {"truth_edges": sum(a["currency"] == c for a in actual.values()),
                                 "predicted_edges": sum(a["currency"] == c for a in predicted.values()),
                                 "correct_edges": sum(predicted[k]["currency"] == c for k in correct)}
                            for c in sorted({p["currency"] for p in payments})},
            "decision_counts": dict(Counter(d["status"] for d in result["decisions"])),
            "overflow_payments": sum(d.get("reason") == "group_pool_overflow" for d in result["decisions"]),
            "invariant_errors": errors}


def benchmark(output, plan=None):
    plan = read_json(PLAN) if plan is None else plan
    seeds = plan["seeds"]
    if set(seeds) != {"validation", "test"} or any(not isinstance(v, list) or not v or
        any(type(n) is not int for n in v) or len(set(v)) != len(v) for v in seeds.values()):
        raise ValueError("nonempty unique validation/test integer seeds required")
    if set(seeds["validation"]) & set(seeds["test"]):
        raise ValueError("validation/test world seeds overlap")
    if plan["methods"] != list(METHODS + V2_METHODS) or plan["profiles"] != ["clean", "masked"]:
        raise ValueError("plan methods/profiles differ from frozen implementation")
    if type(plan["blocks"]) is not int or plan["blocks"] < 1:
        raise ValueError("blocks must be positive")
    config = allocation.Config(**plan["allocation_config"])
    output = prepare_experiment_output(output)
    code_hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted((ROOT / "t0").glob("*.py"))}
    experiment = {"plan": plan, "plan_hash": fingerprint(plan), "code_hashes": code_hashes,
                  "python": platform.python_version(), "platform": platform.platform(),
                  "created_at_utc": datetime.now(timezone.utc).isoformat(),
                  "split_policy": "world seed; masked and clean stay in same split; synthetic test is not domain holdout"}
    write_json(output / "experiment.json", experiment)
    runs = []
    for split in ("validation", "test"):
        for seed in seeds[split]:
            for profile in plan["profiles"]:
                invoices, payments, truth, manifest = generate(seed, plan["blocks"], profile)
                directory = output / "datasets" / split / f"{profile}-{seed}"
                write_jsonl(directory / "invoices.jsonl", invoices)
                write_jsonl(directory / "payments.jsonl", payments)
                write_jsonl(directory / "truth.jsonl", truth)
                write_json(directory / "manifest.json", {**manifest, "input_hash": fingerprint([invoices, payments]), "truth_hash": fingerprint(truth)})
                source_universe = ({(i["tenant_id"], i["id"]) for i in invoices},
                                   {(p["tenant_id"], p["id"]) for p in payments})
                invoices = [i for i in invoices if i["available_on"] <= manifest["cutoff"]]
                payments = [p for p in payments if p["available_on"] <= manifest["cutoff"]]
                for method in plan["methods"]:
                    start = perf_counter()
                    result = predict(invoices, payments, method, config)
                    elapsed = perf_counter() - start
                    write_json(directory / f"predictions-{method}.json", result)
                    # Evaluation reads the persisted oracle after predictions exist.
                    measured = metrics(invoices, payments, read_jsonl(directory / "truth.jsonl"), result, source_universe)
                    again = predict(list(reversed(invoices)), list(reversed(payments)), method, config)
                    measured.update(runtime_seconds=elapsed, order_stable=result["allocation_hash"] == again["allocation_hash"])
                    runs.append({"split": split, "seed": seed, "profile": profile, "method": method, "metrics": measured})
    summary = []
    for split in seeds:
        for profile in plan["profiles"]:
            for method in plan["methods"]:
                values = [r["metrics"] for r in runs if (r["split"], r["profile"], r["method"]) == (split, profile, method)]
                summary.append({"split": split, "profile": profile, "method": method,
                                "metrics": {k: describe([r[k] for r in values]) for k in ("precision", "recall", "candidate_recall", "runtime_seconds")},
                                "all_order_stable": all(r["order_stable"] for r in values),
                                "all_invariants_pass": all(not r["invariant_errors"] for r in values),
                                "money_by_currency": {c: {k: describe([r["money_by_currency"][c][k] for r in values]) for k in values[0]["money_by_currency"][c]}
                                                      for c in values[0]["money_by_currency"]}})
    report = {"task": "synthetic_AR_invoice_payment_v2", "experiment": experiment, "runs": runs, "summary": summary,
              "selection": "No parameter selection on test; all baselines/ablations retained",
              "limits": ["Balanced capability cases, not market frequencies", "No SME or T1 efficacy claims"]}
    write_json(output / "report.json", report)
    return report


def record(kind, identifier, amount, day="2025-01-01", **fields):
    return {"tenant_id": "DEMO", "effective_on": day, "available_on": day,
            "action": "record", "kind": kind,
            "data": {"tenant_id": "DEMO", "id": identifier, "currency": "VND", "amount_minor": amount, **fields}}


def decision(action, day="2025-01-31", identifier="D1", **fields):
    return {"tenant_id": "DEMO", "effective_on": day, "available_on": day,
            "action": action, "decision_id": identifier, **fields}


def ledger_demo(output):
    output = prepare_experiment_output(output)
    commands = [record("invoice", "I1", 1000, side="AR", party_id="C", invoice_number="INV-001"),
                record("credit_note", "CN1", 100, invoice_id="I1"),
                record("payment", "P1", 1100, side="AR", party_id="C"),
                record("bank", "B1", 1080, direction="credit", account_id="DEMO-BANK"),
                record("bank_link", "L1", 0, payment_id="P1", bank_id="B1", fee_minor=20),
                decision("suggest", allocations=[{"invoice_id": "I1", "payment_id": "P1", "amount_minor": 900}]),
                decision("approve"), decision("commit", external_result="unknown"),
                decision("verify", day="2025-02-01", external_result="committed"),
                decision("reverse", day="2025-02-02"),
                record("refund", "R1", 200, day="2025-02-03", payment_id="P1"),
                record("bank", "B-REFUND", 200, day="2025-02-03", direction="debit", account_id="DEMO-BANK"),
                record("refund_bank_link", "RL1", 0, day="2025-02-03", refund_id="R1", bank_id="B-REFUND",
                       refund_amount_minor=200, bank_amount_minor=200, fee_minor=0),
                record("bank_statement", "ST1", 0, day="2025-02-03", account_id="DEMO-BANK",
                       start_on="2025-01-01", end_on="2025-02-03", opening_minor=500,
                       closing_minor=1380, credits_minor=1080, debits_minor=200, transactions_complete=True)]
    write_jsonl(output / "commands.jsonl", [{"idempotency_key": f"demo-{n}", "command": e} for n, e in enumerate(commands)])
    with EventStore(output / "ledger.sqlite") as store:
        for n, e in enumerate(commands):
            store.submit(f"demo-{n}", e)
        # Exact retry survives store reopening too (covered by regression tests).
        repeated = store.submit("demo-8", commands[8])
        snapshots = {d: store.gold(d) for d in ("2025-01-30", "2025-01-31", "2025-02-01", "2025-02-02", "2025-02-03")}
    for day, gold in snapshots.items():
        write_json(output / f"gold-{day}.json", gold)
    report = {"commands": len(commands), "idempotent_retry": repeated,
              "snapshots": {d: {"outstanding_minor": g["invoices"][0]["outstanding_minor"],
                                 "unallocated_minor": g["payments"][0]["unallocated_minor"],
                                 "cash_movements": g["bank_movements"], "snapshot_hash": g["snapshot_hash"]} for d, g in snapshots.items()},
              "limits": ["Local simulation; external verification is supplied explicitly", "Cash is bank movement, not opening-to-closing balance",
                         "Refund consumes unapplied credit after reversal; explicit refund-bank link does not post cash twice"],
              "bank_reconciliation": snapshots["2025-02-03"]["bank_reconciliation"],
              "refund_bank_links": snapshots["2025-02-03"]["refund_bank_links"]}
    write_json(output / "report.json", report)
    return report


def fiscus(folder, output):
    from .adapters import verified_source
    name = "data/financial_workflow_state_fixtures.jsonl"
    provenance = verified_source(folder, [name])
    output = prepare_experiment_output(output)
    cases = read_jsonl(Path(folder) / name)
    rows = []
    for case in cases:
        if case["domain"] != "bank_reconciliation":
            continue
        with EventStore(output / (case["case_id"] + ".sqlite")) as store:
            setup = [record("invoice", "I1", 100, side="AR", party_id="C", invoice_number="INV1"),
                     record("payment", "P1", 100, side="AR", party_id="C"),
                     decision("suggest", allocations=[{"invoice_id": "I1", "payment_id": "P1", "amount_minor": 100}])]
            if case["initial_status"] in ("approved", "committed"):
                setup.append(decision("approve"))
            if case["initial_status"] == "committed":
                setup.append(decision("commit", external_result="verified"))
            for n, command in enumerate(setup):
                store.submit(f"setup-{n}", command)
            before = store.gold("2025-02-01")
            if case["event"] == "user_approves_match":
                store.submit("action", decision("approve"))
            elif case["event"] == "commit_match":
                store.submit("action", decision("commit", external_result="verified" if case["external_result"] == "verified" else "unknown"))
            elif case["event"] == "retry_same_match":
                store.submit(f"setup-{len(setup)-1}", setup[-1])
            else:
                raise ValueError("unsupported FISCUS bank event")
            after = store.gold("2025-02-01")
            status = after["decisions"][0]["status"]
            change = before["invoices"][0]["outstanding_minor"] - after["invoices"][0]["outstanding_minor"]
            effect = ("unknown_do_not_duplicate" if status == "review_required" else
                      "none_until_commit" if status == "approved" else "created_once" if change else "no_new_effect")
            rows.append({"case_id": case["case_id"], "status": status, "financial_effect": effect,
                         "status_pass": status == case["expected_status"], "effect_pass": effect == case["financial_effect"],
                         "audit_events": len(store.events())})
    report = {"provenance": provenance, "bank_cases": rows, "unsupported_domains_cases": len(cases) - len(rows),
              "all_pass": all(r["status_pass"] and r["effect_pass"] for r in rows) and bool(rows),
              "limits": "Bank workflow fixture simulation only; no external API/concurrency certification"}
    write_json(output / "report.json", report)
    return report


def run_all(output, sources, plan=None):
    from .adapters import adapt_finrca
    from .journal import run as journal
    from .settlement import run as settlement
    from .robustness import benchmark as robustness
    output, sources = prepare_experiment_output(output), Path(sources)
    results = {"ar": benchmark(output / "ar", plan), "ledger": ledger_demo(output / "ledger")}
    results["robustness"] = robustness(output / "robustness")
    for source, operation in (("finrca", adapt_finrca), ("recbench", settlement), ("finbalance", journal), ("fiscus", fiscus)):
        if not (sources / source / "source_manifest.json").is_file():
            results[source] = {"status": "unavailable", "quality": None, "reason": "local raw snapshot absent"}
        else:
            results[source] = operation(sources / source, output / source)
    checks = {"ar_invariants": all(r["all_invariants_pass"] for r in results["ar"]["summary"]),
              "ar_order_stability": all(r["all_order_stable"] for r in results["ar"]["summary"]),
              "fiscus": results.get("fiscus", {}).get("all_pass"),
              "recbench_order_stability": results["recbench"].get("metrics", {}).get("order_stable"),
              "recbench_unknown_predictions": (results["recbench"]["metrics"]["predictions_on_unknown_bank_rows"] == 0
                                               if "metrics" in results["recbench"] else None),
              "ledger_retry": results["ledger"]["idempotent_retry"]["replayed"],
              "ledger_statements": all(r["status"] == "matched_declared_complete" for r in results["ledger"]["bank_reconciliation"]),
              "ledger_refund_bank": len(results["ledger"]["refund_bank_links"]) == 1,
              "robustness": results["robustness"]["all_pass"]}
    from .gates import assess
    assessment = assess(results, checks)
    artifacts = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(output.rglob("*")) if p.is_file()}
    end_hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted((ROOT / "t0").glob("*.py"))}
    if end_hashes != results["ar"]["experiment"]["code_hashes"]:
        raise ValueError("T0 code changed during offline run; keep partial output and rerun into a new folder")
    report = {"schema": "t0-offline-evidence-v4", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "code_hashes": results["ar"]["experiment"]["code_hashes"],
              "plan_hash": results["ar"]["experiment"]["plan_hash"], "checks": checks,
              "assessment": assessment,
              "ar_summary": results["ar"]["summary"], "ledger": results["ledger"],
              "robustness_summary": results["robustness"]["summary"],
              "finrca": results["finrca"].get("stages", results["finrca"]),
              "recbench": results["recbench"].get("metrics", results["recbench"]),
              "finbalance": results["finbalance"].get("metrics", {}).get("summary", results["finbalance"]),
              "inconsistency_quality": results["finbalance"].get("inconsistency_quality"),
              "fiscus": results["fiscus"], "artifact_sha256": artifacts,
              "missing": ["SME AR independent labels/availability/approval logs", "Verified FinRCA bank-link oracle",
                          "RecBench ledger/settlement and missing payout endpoints", "FinBalance main/PDF and broad journal policies",
                          "Live ERP/bank connector and T1 efficacy backtest"]}
    write_json(output / "evidence.json", report)
    return report
