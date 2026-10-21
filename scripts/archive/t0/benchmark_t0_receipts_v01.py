"""Archived initial synthetic benchmark; current CLI uses t0.offline."""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import platform
import subprocess

from t0.data import fingerprint, prepare_experiment_output, save_receipt_dataset, write_json
from t0.evaluation import describe, evaluate, paired_interval
from t0.matching import Config, METHODS
from .generate_t0_receipts_v01 import generate

__version__ = "0.1.0"

def benchmark(output, blocks=8, config=None, validation_seeds=(11, 12, 13),
              test_seeds=(101, 102, 103, 104, 105), profiles=("clean", "noisy", "stress")):
    if (not validation_seeds or not test_seeds or not profiles
            or len(set(validation_seeds)) != len(validation_seeds)
            or len(set(test_seeds)) != len(test_seeds) or len(set(profiles)) != len(profiles)):
        raise ValueError("seeds/profiles must be nonempty and unique within each list")
    if set(validation_seeds) & set(test_seeds):
        raise ValueError("validation and test seeds must be disjoint")
    config = config or Config()
    output = prepare_experiment_output(output)
    runs, datasets = [], []
    for split, seeds in (("validation", validation_seeds), ("test", test_seeds)):
        for profile in profiles:
            for seed in seeds:
                generated = generate(seed, blocks, profile)
                directory = output / "datasets" / split / f"{profile}-{seed}"
                save_receipt_dataset(directory, generated)
                raw_i, raw_b, truth, manifest = generated
                datasets.append({"split": split, "profile": profile, "seed": seed,
                                 "manifest": manifest})
                for method in METHODS:
                    measured = evaluate(raw_i, raw_b, truth, manifest["cutoff"], method, config)
                    runs.append({"split": split, "profile": profile, "seed": seed,
                                 "method": method, "metrics": measured})
    summary, comparisons = [], []
    for split in ("validation", "test"):
        for profile in profiles:
            for method in METHODS:
                group = [r["metrics"] for r in runs if (r["split"], r["profile"], r["method"])
                         == (split, profile, method)]
                summary.append({"split": split, "profile": profile, "method": method,
                                "metrics": {k: describe([r[k] for r in group]) for k in (
                                    "precision", "recall", "candidate_recall", "auto_receipt_rate",
                                    "manual_review_rate", "runtime_seconds")},
                                "money_by_currency": {
                                    currency: {key: describe([r["money_by_currency"].get(currency, {}).get(key, 0)
                                                             for r in group])
                                               for key in ("wrongly_allocated_minor", "missing_truth_minor",
                                                           "unallocated_minor")}
                                    for currency in sorted({c for r in group for c in r["money_by_currency"]})},
                                "quality": {table: {"selected": describe([r["quality"][table]["selected"] for r in group]),
                                                    "quarantined_groups_or_rows": describe([
                                                        len(r["quality"][table]["quarantined"]) for r in group])}
                                            for table in ("invoices", "bank")},
                                "all_order_and_replay_stable": all(r["order_and_replay_stable"] for r in group),
                                "all_invariants_pass": all(not r["invariant_errors"] for r in group)})
            for method in METHODS[1:]:
                a = {r["seed"]: r["metrics"] for r in runs if (r["split"], r["profile"], r["method"])
                     == (split, profile, method)}
                b = {r["seed"]: r["metrics"] for r in runs if (r["split"], r["profile"], r["method"])
                     == (split, profile, METHODS[0])}
                comparisons.append({"split": split, "profile": profile, "method": method,
                                    "baseline": METHODS[0], "recall": paired_interval([
                                        a[s]["recall"] - b[s]["recall"] for s in sorted(a.keys() & b.keys())
                                        if a[s]["recall"] is not None and b[s]["recall"] is not None])})
    root = Path(__file__).resolve().parents[3]
    code_hashes = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in [Path(__file__), Path(__file__).with_name("generate_t0_receipts_v01.py"),
                             *sorted((root / "t0").glob("*.py"))]}
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
                                text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    report = {"version": __version__, "kind": "synthetic_benchmark",
              "run_at_utc": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
              "platform": platform.platform(), "git_head": commit, "source_sha256": code_hashes,
              "config": asdict(config), "config_hash": fingerprint(asdict(config)), "blocks": blocks,
              "validation_seeds": list(validation_seeds), "test_seeds": list(test_seeds),
              "thresholds_tuned": False,
              "limitations": ["Synthetic cases only; no estimate of production accuracy",
                              "Default test seeds have been used during development; not a blind holdout",
                              "Thresholds are fixed engineering defaults, not probabilities",
                              "Seed intervals do not measure real-world uncertainty",
                              "Payment date MAE tests propagation of bank booked_on only"],
              "datasets": datasets, "summary": summary, "paired_comparisons": comparisons,
              "runs": runs}
    write_json(output / "benchmark.json", report)
    return report
