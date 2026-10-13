from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.benchmark_suite import run_benchmark_suite
from src.environment_setup import REQUIREMENTS, setup_model_environment
from src.evaluator import evaluate_run
from src.prepare.common import benchmark_config
from src.prepare.inventory import build_inventory
from src.prepare.pipeline import prepare_all
from src.prepare.validate_data import validate_prepared_data
from src.reporting.render_report import render_report
from src.runner import run_model
from src.smoke_test import run_smoke


def print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OCR end-to-end benchmark")
    parser.add_argument("--config", default="configs/benchmark.yaml")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inventory")
    subparsers.add_parser("prepare")
    subparsers.add_parser("validate-data")
    subparsers.add_parser("list-models")
    setup = subparsers.add_parser("setup-env")
    setup.add_argument("--model", required=True, choices=sorted(REQUIREMENTS))
    smoke = subparsers.add_parser("smoke-test")
    group = smoke.add_mutually_exclusive_group(required=True)
    group.add_argument("--model", action="append")
    group.add_argument("--all-models", action="store_true")
    run = subparsers.add_parser("run")
    run.add_argument("--model", required=True)
    run.add_argument("--split", choices=["dev", "test"], required=True)
    run.add_argument("--limit", type=int)
    run.add_argument("--run-id")
    run.add_argument("--allow-current-python", action="store_true")
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--run-id", required=True)
    suite = subparsers.add_parser("benchmark-suite")
    suite.add_argument("--split", choices=["dev", "test"], default="dev")
    suite.add_argument("--limit", type=int, default=100)
    suite.add_argument("--suite-id")
    suite.add_argument("--model", action="append", choices=sorted(REQUIREMENTS))
    subparsers.add_parser("report")
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    config = benchmark_config(args.config)
    if args.command == "inventory":
        print_json(build_inventory(config))
    elif args.command == "prepare":
        print_json(prepare_all(config))
    elif args.command == "validate-data":
        report = validate_prepared_data(config)
        print_json(report)
        return 0 if report["valid"] else 2
    elif args.command == "list-models":
        print_json(sorted(REQUIREMENTS))
    elif args.command == "setup-env":
        print(setup_model_environment(args.model))
    elif args.command == "smoke-test":
        models = sorted(REQUIREMENTS) if args.all_models else args.model
        print_json(run_smoke(models, int(config["evaluation"].get("blank_fixture_count", 3))))
    elif args.command == "run":
        print(
            run_model(
                config,
                args.model,
                args.split,
                limit=args.limit,
                run_id=args.run_id,
                allow_current_python=args.allow_current_python,
            )
        )
    elif args.command == "evaluate":
        print(evaluate_run(config, args.run_id))
    elif args.command == "benchmark-suite":
        print_json(
            run_benchmark_suite(
                config,
                split=args.split,
                limit=args.limit,
                suite_id=args.suite_id,
                models=args.model,
            )
        )
    elif args.command == "report":
        print(render_report(config))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print(
            "\nBenchmark interrupted. Progress was saved; rerun the same command to resume.",
            file=sys.stderr,
        )
        raise SystemExit(130)
