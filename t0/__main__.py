"""T0 offline v0.4 commands; frozen receipt and v2 benchmark remain explicit."""

import argparse
from dataclasses import asdict
from pathlib import Path
import sys

from . import allocation, offline
from .adapters import adapt_finrca
from .data import (fingerprint, guard_matching_source, iso_date, prepare_experiment_output,
                   read_json, read_jsonl, snapshot, write_json, write_jsonl)
from .evaluation import evaluate
from .ledger import EventStore
from .matching import Config, METHODS, reconcile


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "data/T0/raw/fixture_research/2026-10-20"


def load_allocation_input(directory, cutoff=None):
    guard_matching_source(directory)
    manifest = read_json(directory / "manifest.json")
    if manifest.get("schema") != "t0-invoice-payment-v2":
        raise ValueError("allocate requires a derived t0-invoice-payment-v2 dataset, never raw research")
    invoices, payments = read_jsonl(directory / "invoices.jsonl"), read_jsonl(directory / "payments.jsonl")
    if manifest["availability"] == "simulated":
        cutoff = cutoff or manifest["cutoff"]
        iso_date(cutoff)
        # Validate before comparison: lexical filtering is valid only for ISO dates.
        for rows, business_date in ((invoices, "issued_on"), (payments, "payment_on")):
            for row in rows:
                iso_date(row["available_on"])
                iso_date(row[business_date])
        invoices = [r for r in invoices if r["available_on"] <= cutoff and r["issued_on"] <= cutoff]
        payments = [r for r in payments if r["available_on"] <= cutoff and r["payment_on"] <= cutoff]
    elif manifest["availability"] == "static_retrospective":
        if cutoff:
            raise ValueError("static pool has no historical availability; cannot claim an as-of snapshot")
    else:
        raise ValueError("unknown availability policy")
    return invoices, payments, manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description="T0 offline v0.4: AP/AR/FX allocation, versioned ledger and journal")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="Create typed v2 AR capability input and independent event intent/truth")
    gen.add_argument("--seed", type=int, default=2101)
    gen.add_argument("--blocks", type=int, default=4)
    gen.add_argument("--profile", choices=("clean", "masked"), default="clean")
    gen.add_argument("--output", type=Path, required=True)
    bench = sub.add_parser("benchmark", help="Frozen v2 plan: old four baselines and three ablations")
    bench.add_argument("--output", type=Path, required=True)
    robust = sub.add_parser("benchmark-robustness", help="Compare v2 and unique constrained flow on new failure/capability cases")
    robust.add_argument("--output", type=Path, required=True)
    all_run = sub.add_parser("run-offline", help="Run AR, FinRCA, RecBench, FinBalance, FISCUS and Gold separately")
    all_run.add_argument("--sources", type=Path, default=SOURCES)
    all_run.add_argument("--output", type=Path, required=True)
    all_run.add_argument("--gate", choices=("execution", "technical", "quality"), default="technical")
    ap = sub.add_parser("adapt-finrca", help="Audit typed AP, preserving corrupted allocations and lineage")
    ap.add_argument("--input", type=Path, default=SOURCES / "finrca")
    ap.add_argument("--output", type=Path, required=True)
    allocate = sub.add_parser("allocate", help="Propose invoice-payment allocations; never reads truth")
    allocate.add_argument("--input", type=Path, required=True)
    allocate.add_argument("--cutoff")
    allocate.add_argument("--output", type=Path, required=True)
    allocate.add_argument("--method", choices=("constrained_flow", "v2"), default="constrained_flow")
    fx = sub.add_parser("allocate-fx", help="Observed FX remittance proposals; no inferred exchange rates")
    fx.add_argument("--input", type=Path, required=True)
    fx.add_argument("--cutoff", required=True)
    fx.add_argument("--output", type=Path, required=True)
    jp = sub.add_parser("journal-predict", help="Predict journal from observed JSON records with optional explicit accounting policy")
    jp.add_argument("--input", type=Path, required=True)
    jp.add_argument("--output", type=Path, required=True)
    for name, help_text in (("settlement", "RecBench payout-bank with missing endpoints reported"),
                            ("journal", "FinBalance narrow document-text journal baseline"),
                            ("fiscus", "Four bank reconciliation workflow fixtures")):
        cmd = sub.add_parser(name, help=help_text)
        source = {"settlement": "recbench", "journal": "finbalance", "fiscus": "fiscus"}[name]
        cmd.add_argument("--input", type=Path, default=SOURCES / source)
        cmd.add_argument("--output", type=Path, required=True)
    ledger = sub.add_parser("ledger", help="Submit JSONL idempotency_key/command to local transactional ledger")
    ledger.add_argument("--input", type=Path, required=True)
    ledger.add_argument("--store", type=Path, required=True)
    gold = sub.add_parser("gold", help="Replay committed ledger and bank movements at cutoff")
    gold.add_argument("--store", type=Path, required=True)
    gold.add_argument("--cutoff", required=True)
    gold.add_argument("--output", type=Path, required=True)
    demo = sub.add_parser("ledger-demo", help="Approval/unknown/verify/reversal/refund/credit/fee examples")
    demo.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("reconcile", help="Frozen v0.1 positive AR bank-receipt matcher (BenchRec/AP excluded)")
    score = sub.add_parser("evaluate", help="Frozen v0.1 receipt evaluator; exhaustive truth required")
    for command in (run, score):
        command.add_argument("--input", type=Path, required=True)
        command.add_argument("--cutoff", required=True)
        command.add_argument("--method", choices=METHODS, default="reference_then_global")
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--score-threshold", type=float, default=0.72)
        command.add_argument("--ambiguity-margin", type=float, default=0.08)
        command.add_argument("--max-age-days", type=int, default=120)
        command.add_argument("--due-window-days", type=int, default=14)
    score.add_argument("--truth-exhaustive", action="store_true", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            invoices, payments, truth, manifest = offline.generate(args.seed, args.blocks, args.profile)
            prepare_experiment_output(args.output)
            write_jsonl(args.output / "invoices.jsonl", invoices)
            write_jsonl(args.output / "payments.jsonl", payments)
            write_jsonl(args.output / "truth.jsonl", truth)
            write_json(args.output / "manifest.json", {**manifest, "schema": "t0-invoice-payment-v2", "availability": "simulated"})
        elif args.command == "benchmark":
            report = offline.benchmark(args.output)
            print(f"AR benchmark: {args.output / 'report.json'}")
            return int(any(not r["all_invariants_pass"] or not r["all_order_stable"] for r in report["summary"]))
        elif args.command == "benchmark-robustness":
            from .robustness import benchmark
            return int(not benchmark(args.output)["all_pass"])
        elif args.command == "run-offline":
            report = offline.run_all(args.output, args.sources)
            print(f"Offline evidence: {args.output / 'evidence.json'}")
            print(f"Assessment: {report['assessment']['status']}; production_ready=False")
            from .gates import exit_code
            return exit_code(report["assessment"], args.gate)
        elif args.command == "adapt-finrca":
            adapt_finrca(args.input, args.output)
        elif args.command == "allocate-fx":
            from .fx import allocate as propose_fx
            invoices, payments, manifest = load_allocation_input(args.input, args.cutoff)
            if manifest["availability"] != "simulated":
                raise ValueError("FX as-of proposals require explicit availability")
            result = propose_fx(invoices, payments, args.cutoff)
            prepare_experiment_output(args.output)
            write_json(args.output / "predictions.json", result)
        elif args.command == "journal-predict":
            from .journal import predict
            records = read_jsonl(args.input)
            result = [predict({k: r[k] for k in ("record_id", "industry", "documents", "allowed_accounts", "cutoff", "accounting_policy", "opening_balances") if k in r}) for r in records]
            prepare_experiment_output(args.output)
            write_json(args.output / "predictions.json", result)
        elif args.command == "allocate":
            invoices, payments, manifest = load_allocation_input(args.input, args.cutoff)
            if args.method == "constrained_flow":
                from .constrained import allocate as propose
            else:
                propose = allocation.allocate
            result = propose(invoices, payments)
            prepare_experiment_output(args.output)
            write_json(args.output / "predictions.json", {**result, "input_hash": fingerprint([invoices, payments]),
                                                          "availability": manifest["availability"]})
        elif args.command in ("settlement", "journal", "fiscus"):
            if args.command == "settlement":
                from .settlement import run as operation
            elif args.command == "journal":
                from .journal import run as operation
            else:
                operation = offline.fiscus
            operation(args.input, args.output)
        elif args.command == "ledger-demo":
            offline.ledger_demo(args.output)
        elif args.command == "ledger":
            commands = read_jsonl(args.input)
            with EventStore(args.store) as store:
                for row in commands:
                    store.submit(row["idempotency_key"], row["command"])
            print(f"Accepted {len(commands)} deliveries (existing keys replayed)")
        elif args.command == "gold":
            if not args.store.is_file():
                raise ValueError("ledger store does not exist")
            if args.output.exists():
                raise ValueError("output exists; choose a new Gold output")
            with EventStore(args.store) as store:
                write_json(args.output, store.gold(args.cutoff))
        else:
            guard_matching_source(args.input)
            if (args.input / "manifest.json").is_file():
                manifest = read_json(args.input / "manifest.json")
                if manifest.get("schema") == "t0-invoice-payment-v2":
                    raise ValueError("typed AP/AR dataset requires allocate, not v0.1 reconcile/evaluate")
            config = Config(args.max_age_days, args.due_window_days, args.score_threshold, args.ambiguity_margin)
            raw_i, raw_b = read_jsonl(args.input / "invoices.jsonl"), read_jsonl(args.input / "bank.jsonl")
            if args.command == "evaluate":
                if args.output.exists():
                    raise ValueError("evaluation output already exists")
                measured = evaluate(raw_i, raw_b, read_jsonl(args.input / "truth.jsonl"), args.cutoff, args.method, config)
                write_json(args.output, {"cutoff": args.cutoff, "method": args.method, "config": asdict(config), "metrics": measured,
                                         "input_hashes": {"invoices": fingerprint(raw_i), "bank": fingerprint(raw_b)}})
                return int(not measured["order_and_replay_stable"] or bool(measured["invariant_errors"]))
            inv, iq = snapshot(raw_i, "invoices", args.cutoff)
            bank, bq = snapshot(raw_b, "bank", args.cutoff)
            result = reconcile(inv, bank, args.method, config)
            prepare_experiment_output(args.output)
            write_jsonl(args.output / "allocations.jsonl", result["allocations"])
            write_jsonl(args.output / "decisions.jsonl", result["decisions"])
            write_json(args.output / "audit.json", {**result, "cutoff": args.cutoff, "quality": {"invoices": iq, "bank": bq}})
        print(f"T0 {args.command}: complete")
        return 0
    except (KeyError, TypeError, ValueError, OSError) as exc:
        print(f"T0 error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
