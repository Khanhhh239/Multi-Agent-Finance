"""Run the frozen research invoice suite and full BenchRec allocation-key benchmark."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import platform
import random
import statistics
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from t0 import benchrec, scenarios
from t0.data import fingerprint, prepare_experiment_output, read_json, read_jsonl, save_receipt_dataset, write_json
from t0.evaluation import describe, evaluate, paired_interval
from t0.matching import METHODS as INVOICE_METHODS

PLAN = ROOT / "research/references/data-checks/t0/reconciliation-benchmark-plan-v1.json"


def validate_plan(plan):
    """Reject leakage-prone splits and invalid noise before creating outputs."""
    def seeds(values):
        if (not isinstance(values, list) or not values or any(type(v) is not int for v in values)
                or len(values) != len(set(values))):
            raise ValueError("Seeds must be nonempty, unique integers")
    try:
        invoice, bank = plan["invoice_suite"], plan["benchrec"]
        for values in (invoice["validation_seeds"], invoice["test_seeds"], bank["seeds"]):
            seeds(values)
        if set(invoice["validation_seeds"]) & set(invoice["test_seeds"]):
            raise ValueError("Validation and test seeds must be disjoint")
        if type(invoice["blocks"]) is not int or invoice["blocks"] < 1:
            raise ValueError("blocks must be a positive integer")
        for spec, names in ((invoice, {"clean", "noisy", "stress"}), (bank, {"original", "noisy", "stress"})):
            if set(spec["profiles"]) != names:
                raise ValueError("Unexpected profile names")
            for noise in spec["profiles"].values():
                expected = {"mask_reference", "date_error_days"} | ({"typo_probability"} if spec is invoice else set())
                if set(noise) != expected:
                    raise ValueError("Unexpected noise parameters")
                for key in expected - {"date_error_days"}:
                    value = noise[key]
                    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                        raise ValueError("Noise probability must be finite and in [0, 1]")
                if type(noise["date_error_days"]) is not int or noise["date_error_days"] < 0:
                    raise ValueError("Date displacement must be a nonnegative integer")
        benchrec.Config(**{k: bank[k] for k in benchrec.Config.__dataclass_fields__})
        if bank["methods"] != list(benchrec.METHODS):
            raise ValueError("Plan and implemented methods disagree")
    except (KeyError, TypeError) as exc:
        raise ValueError("Incomplete or malformed benchmark plan") from exc


def summaries(runs, keys):
    groups = defaultdict(list)
    for run in runs:
        groups[(run["split"], run["profile"], run["method"])].append(run["metrics"])
    rows = []
    for (split, profile, method), values in sorted(groups.items()):
        times = sorted(v["runtime_seconds"] for v in values)
        rows.append({"split": split, "profile": profile, "method": method,
                     "metrics": {k: describe([v[k] for v in values]) for k in keys},
                     "runtime_median_seconds": statistics.median(times),
                     "runtime_max_seconds": max(times),
                     "all_order_and_replay_stable": all(v["order_and_replay_stable"] for v in values),
                     "all_invariants_pass": all(not v["invariant_errors"] for v in values)})
    return rows


def paired(runs, key, baseline):
    comparisons = []
    for split, profile in sorted({(r["split"], r["profile"]) for r in runs}):
        by_method = defaultdict(dict)
        for run in runs:
            if (run["split"], run["profile"]) == (split, profile):
                by_method[run["method"]][run["seed"]] = run["metrics"][key]
        for method in sorted(set(by_method) - {baseline}):
            diffs = [by_method[method][s] - by_method[baseline][s] for s in by_method[baseline]
                     if by_method[method][s] is not None and by_method[baseline][s] is not None]
            comparisons.append({"split": split, "profile": profile, "method": method,
                                "baseline": baseline, "metric": key, "paired_seed_interval": paired_interval(diffs)})
    return comparisons


def run_invoice(plan, output):
    spec = plan["invoice_suite"]
    runs, datasets = [], []
    for split in ("validation", "test"):
        for profile, noise in spec["profiles"].items():
            for seed in spec[split + "_seeds"]:
                generated = scenarios.generate(seed, spec["blocks"], profile, noise)
                save_receipt_dataset(output / "invoice-datasets" / split / f"{profile}-{seed}", generated)
                invoices, bank, truth, manifest = generated
                datasets.append({"split": split, "manifest": manifest})
                for method in INVOICE_METHODS:
                    metrics = evaluate(invoices, bank, truth, manifest["cutoff"], method)
                    runs.append({"split": split, "profile": profile, "seed": seed,
                                 "method": method, "metrics": metrics})
    return {"kind": "research_synthetic_invoice", "datasets": datasets, "runs": runs,
            "summary": summaries(runs, ("precision", "recall", "candidate_recall", "auto_receipt_rate",
                                        "manual_review_rate", "payment_date_mae_days_on_correct_links")),
            "paired_comparisons": paired(runs, "recall", INVOICE_METHODS[0])}


def run_benchrec(plan, directory, output):
    spec = plan["benchrec"]
    config = benchrec.Config(**{k: spec[k] for k in benchrec.Config.__dataclass_fields__})
    if spec["methods"] != list(benchrec.METHODS):
        raise ValueError("Plan and implemented methods disagree")
    ledger, bank = benchrec.load_features(directory, "eval")
    runs, prediction_paths = [], []
    # Generate and persist EVERY prediction before loading evaluation labels.
    # This cannot establish blindness against previous human access, but it
    # makes evaluator-to-matcher leakage structurally testable and reviewable.
    for profile, noise in spec["profiles"].items():
        for seed in spec["seeds"]:
            perturbed, changes = benchrec.perturb(bank, noise, seed)
            shuffled_a, shuffled_b = list(ledger), list(perturbed)
            rng = random.Random(seed)
            rng.shuffle(shuffled_a)
            rng.shuffle(shuffled_b)
            for method in benchrec.METHODS:
                start = perf_counter()
                result = benchrec.match(ledger, perturbed, method, config)
                seconds = perf_counter() - start
                replay = benchrec.match(shuffled_a, shuffled_b, method, config)
                path = output / "benchrec-predictions" / f"{profile}-{seed}-{method}.json"
                write_json(path, result["predictions"])
                prediction_paths.append(path)
                runs.append({"split": "published_eval", "profile": profile, "seed": seed, "method": method,
                             "noise_counts": changes, "prediction_hash": result["prediction_hash"],
                             "metrics": {"runtime_seconds": seconds,
                                 "order_and_replay_stable": result["prediction_hash"] == replay["prediction_hash"],
                                 "invariant_errors": result["invariant_errors"], "diagnostics": result["diagnostics"]}})
            print(f"BenchRec predictions: {profile}, seed={seed}", flush=True)
    truth, diagnostics = benchrec.load_truth(directory, "eval", {b["id"] for b in bank}, {a["allocation"] for a in ledger})
    for run, path in zip(runs, prediction_paths):
        predictions = read_json(path)
        if fingerprint(predictions) != run["prediction_hash"]:
            raise ValueError("Predictions changed before scoring")
        run["metrics"].update(benchrec.score(bank, truth, predictions))
    # Diagnostic only, after all predictions: never a parameter-selection input.
    buckets = defaultdict(list)
    for b in bank:
        buckets[b["account"]].append(b)
    return {"kind": "benchrec_static_GL_bank", "ledger_rows": len(ledger), "bank_rows": len(bank),
            "label_diagnostics": diagnostics, "account_B_counts": sorted(len(v) for v in buckets.values()),
            "runs": runs,
            "summary": summaries(runs, ("precision", "match_rate", "exact_set_precision", "exact_set_recall", "auto_rate", "review_rate")),
            "paired_comparisons": paired(runs, "match_rate", benchrec.METHODS[0]),
            "limits": ["Publisher labels; not re-annotated independently. Allocation correctness does not establish transaction-ID or invoice allocation correctness.",
                       "Static full candidate pool; no claim of availability-safe production backtest.",
                       "Same-sign 1:N group baseline capped at 3 and 12 candidates on same date; N:M and residual fees left for review.",
                       "No ML training or tuning. Seed variability measures noise/reordering, not independent datasets.",
                       "Nonempty subset metric follows dataset card, implemented locally; no official evaluator executable was available.",
                       "Original is unmodified obfuscated data, not a guaranteed clean financial dataset."]}


def verify_existing(directory, source):
    """Recheck saved inputs/predictions without rewriting the historical report."""
    directory = Path(directory)
    report = read_json(directory / "report.json")
    validate_plan(report["plan"])
    if not {"invoice", "benchrec"} & report.keys():
        raise ValueError("Historical report contains no benchmark runs")
    for task in ("invoice", "benchrec"):
        if task not in report:
            continue
        if task == "invoice":
            spec = report["plan"]["invoice_suite"]
            expected = {(split, profile, seed, method) for split in ("validation", "test")
                        for profile in spec["profiles"] for seed in spec[split + "_seeds"] for method in INVOICE_METHODS}
        else:
            spec = report["plan"]["benchrec"]
            expected = {("published_eval", profile, seed, method) for profile in spec["profiles"]
                        for seed in spec["seeds"] for method in benchrec.METHODS}
        identities = [(r["split"], r["profile"], r["seed"], r["method"]) for r in report[task]["runs"]]
        if len(identities) != len(expected) or set(identities) != expected:
            raise ValueError("Historical runs are missing, duplicated or outside the plan")
    counts = {"invoice_runs_verified": 0, "benchrec_predictions_verified": 0, "benchrec_matchers_replayed": 0}
    if "invoice" in report:
        for run in report["invoice"]["runs"]:
            location = directory / "invoice-datasets" / run["split"] / f"{run['profile']}-{run['seed']}"
            manifest = read_json(location / "manifest.json")
            recorded = [d["manifest"] for d in report["invoice"]["datasets"]
                        if d["split"] == run["split"] and d["manifest"]["profile"] == run["profile"]
                        and d["manifest"]["seed"] == run["seed"]]
            if len(recorded) != 1 or manifest != recorded[0]:
                raise ValueError("Historical synthetic manifest changed")
            invoices, bank, truth = [read_jsonl(location / (name + ".jsonl")) for name in ("invoices", "bank", "truth")]
            for name, rows in (("invoices", invoices), ("bank", bank), ("truth", truth)):
                if fingerprint(rows) != manifest["content_hashes"][name]:
                    raise ValueError("Saved synthetic input/truth changed")
            measured = evaluate(invoices, bank, truth, manifest["cutoff"], run["method"])
            if any(measured[k] != v for k, v in run["metrics"].items() if k != "runtime_seconds"):
                raise ValueError("Historical invoice metrics or replay changed")
            counts["invoice_runs_verified"] += 1
    if "benchrec" in report:
        source_manifest = read_json(Path(source) / "source_manifest.json")
        if source_manifest != report["benchrec_source_manifest"]:
            raise ValueError("Historical BenchRec source manifest changed")
        ledger, bank = benchrec.load_features(source, "eval")
        truth, _ = benchrec.load_truth(source, "eval", {b["id"] for b in bank}, {a["allocation"] for a in ledger})
        spec = report["plan"]["benchrec"]
        config = benchrec.Config(**{k: spec[k] for k in benchrec.Config.__dataclass_fields__})
        for run in report["benchrec"]["runs"]:
            location = directory / "benchrec-predictions" / f"{run['profile']}-{run['seed']}-{run['method']}.json"
            predictions = read_json(location)
            if fingerprint(predictions) != run["prediction_hash"] or benchrec.invariant_errors(ledger, bank, predictions):
                raise ValueError("Saved BenchRec predictions changed or violate invariants")
            measured = benchrec.score(bank, truth, predictions)
            if any(v != run["metrics"][k] for k, v in measured.items()):
                raise ValueError("Historical BenchRec metrics changed")
            counts["benchrec_predictions_verified"] += 1
            if run["profile"] == "original" and run["seed"] == spec["seeds"][0]:
                replay = benchrec.match(ledger, bank, run["method"], config)
                if replay["prediction_hash"] != run["prediction_hash"]:
                    raise ValueError("Historical BenchRec matcher output changed")
                counts["benchrec_matchers_replayed"] += 1
    return {"verified_at_utc": datetime.now(timezone.utc).isoformat(), **counts,
            "historical_report_content_hash": fingerprint(report), "plan_content_hash": fingerprint(report["plan"]),
            "historical_files_modified": False, "parameters_tuned": False,
            "verification_source_sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [Path(__file__), *sorted((ROOT / "t0").glob("*.py"))]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/T0/raw/benchrec_kaggle/2026-10-19-v3")
    parser.add_argument("--output", type=Path, default=ROOT / "data/T0/processed/reconciliation-v1")
    parser.add_argument("--only", choices=("invoice", "benchrec", "all"), default="all")
    parser.add_argument("--verify-existing", type=Path, help="Verify historical report/input/predictions; write verification to a fresh --output")
    args = parser.parse_args()
    if args.verify_existing:
        prepare_experiment_output(args.output)
        write_json(args.output / "verification.json", verify_existing(args.verify_existing, args.input))
        print(f"Historical verification passed: {args.output / 'verification.json'}", flush=True)
        return
    plan = read_json(PLAN)
    validate_plan(plan)
    prepare_experiment_output(args.output)
    hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in [PLAN, Path(__file__), *sorted((ROOT / "t0").glob("*.py"))]}
    report = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "plan": plan,
              "source_sha256": hashes, "python": platform.python_version(), "platform": platform.platform(),
              "thresholds_tuned": False, "test_used_for_selection": False}
    # Persist configuration before any predictions, even if this run interrupts.
    write_json(args.output / "experiment.json", report)
    if args.only in ("invoice", "all"):
        report["invoice"] = run_invoice(plan, args.output)
    if args.only in ("benchrec", "all"):
        report["benchrec_source_manifest"] = read_json(args.input / "source_manifest.json")
        report["benchrec"] = run_benchrec(plan, args.input, args.output)
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    if any(hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest for path, digest in hashes.items()):
        raise ValueError("Experiment sources changed during execution")
    write_json(args.output / "report.json", report)
    # Tracked evidence deliberately contains no raw IDs/text/predictions.
    compact = dict(report)
    compact["full_report_content_hash"] = fingerprint(report)
    for key in ("invoice", "benchrec"):
        if key in compact:
            compact[key] = {k: v for k, v in compact[key].items() if k not in ("runs", "datasets")}
    write_json(args.output / "evidence.json", compact)
    if any(not row["all_invariants_pass"] or not row["all_order_and_replay_stable"]
           for task in ("invoice", "benchrec") if task in report for row in report[task]["summary"]):
        raise ValueError("Benchmark financial invariants or replay stability failed; inspect report")
    print(f"Completed: {args.output / 'report.json'}", flush=True)


if __name__ == "__main__":
    main()
