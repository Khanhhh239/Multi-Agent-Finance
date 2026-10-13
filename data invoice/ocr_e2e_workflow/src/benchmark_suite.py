from __future__ import annotations

import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.environment_setup import REQUIREMENTS
from src.evaluator import evaluate_run
from src.prepare.common import output_path
from src.prepare.validate_data import validate_prepared_data
from src.reporting.aggregate import flatten
from src.reporting.render_report import render_report
from src.reporting.suite_dashboard import render_suite_dashboard
from src.runner import model_config_path, run_model
from src.utils import load_yaml, read_json, read_jsonl, resolve_python_executable, write_json


def _safe_id(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("._")
    if not safe:
        raise ValueError("suite_id must contain at least one letter or number")
    return safe


def _line_count(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _run_is_complete(run_dir: Path) -> bool:
    pairs = [
        (run_dir / "inputs" / "full_images.jsonl", run_dir / "predictions" / "raw.jsonl"),
        (
            run_dir / "inputs" / "recognition_crops.jsonl",
            run_dir / "predictions" / "recognition_raw.jsonl",
        ),
    ]
    for source, prediction in pairs:
        if _line_count(source) == 0 or _line_count(source) != _line_count(prediction):
            return False
        if any(
            row.get("metadata", {}).get("recovery_action") == "sample_marked_failed"
            for row in read_jsonl(prediction)
        ):
            return False
    return True


def _preflight(model_id: str) -> str | None:
    model_config = load_yaml(model_config_path(model_id))
    python = resolve_python_executable(model_config["python"])
    if not python.is_file():
        return f"missing environment: {python}"
    if model_config.get("requires_gpu") and not shutil.which("nvidia-smi"):
        return "NVIDIA GPU runtime is unavailable"
    return None


def run_benchmark_suite(
    config: dict[str, Any],
    split: str,
    limit: int,
    suite_id: str | None = None,
    models: list[str] | None = None,
) -> dict[str, Any]:
    if split not in {"dev", "test"}:
        raise ValueError("split must be dev or test")
    if limit <= 0:
        raise ValueError("limit must be positive")
    validation = validate_prepared_data(config)
    if not validation["valid"]:
        raise RuntimeError("Prepared data is invalid; run validate-data for details")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suite_id = _safe_id(suite_id or f"{split}_{limit}_all_{stamp}")
    selected_models = models or sorted(REQUIREMENTS)
    unknown = sorted(set(selected_models) - set(REQUIREMENTS))
    if unknown:
        raise ValueError(f"Unknown models: {', '.join(unknown)}")

    suite_dir = output_path(config, "reports") / "suites" / suite_id
    state_path = suite_dir / "status.json"
    suite_dir.mkdir(parents=True, exist_ok=True)
    statuses: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []

    def save_state() -> None:
        write_json(
            state_path,
            {
                "suite_id": suite_id,
                "split": split,
                "limit": limit,
                "models": selected_models,
                "statuses": statuses,
            },
        )

    for index, model_id in enumerate(selected_models, 1):
        run_id = f"{suite_id}_{model_id}"
        print(f"\n=== [{index}/{len(selected_models)}] {model_id} ===", flush=True)
        reason = _preflight(model_id)
        if reason:
            statuses.append(
                {"model_id": model_id, "run_id": run_id, "status": "skipped", "error": reason}
            )
            print(f"SKIP: {reason}", flush=True)
            save_state()
            continue
        started = time.perf_counter()
        run_dir = output_path(config, "runs") / run_id
        try:
            existed = run_dir.is_dir()
            already_complete = existed and _run_is_complete(run_dir)
            if not existed:
                run_dir = run_model(
                    config,
                    model_id,
                    split,
                    limit=limit,
                    run_id=run_id,
                    recover_native_crash=True,
                )
            elif not already_complete:
                print("RESUME: continuing incomplete prediction files", flush=True)
                run_dir = run_model(
                    config,
                    model_id,
                    split,
                    limit=limit,
                    run_id=run_id,
                    resume=True,
                    recover_native_crash=True,
                )
            summary_path = evaluate_run(config, run_id)
            summary = read_json(summary_path)
            row = flatten(summary)
            rows.append(row)
            statuses.append(
                {
                    "model_id": model_id,
                    "run_id": run_id,
                    "status": (
                        "reused" if already_complete else "resumed" if existed else "completed"
                    ),
                    "elapsed_seconds": time.perf_counter() - started,
                    "summary": str(summary_path),
                }
            )
        except KeyboardInterrupt:
            statuses.append(
                {"model_id": model_id, "run_id": run_id, "status": "interrupted"}
            )
            save_state()
            raise
        except Exception as exc:
            statuses.append(
                {
                    "model_id": model_id,
                    "run_id": run_id,
                    "status": "failed",
                    "elapsed_seconds": time.perf_counter() - started,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            print(f"FAILED: {type(exc).__name__}: {exc}", flush=True)
        save_state()

    final_report = render_report(config)
    suite_report = render_suite_dashboard(config, suite_id, statuses, rows)
    save_state()
    return {
        "suite_id": suite_id,
        "split": split,
        "limit": limit,
        "completed": sum(
            item["status"] in {"completed", "resumed", "reused"} for item in statuses
        ),
        "skipped": sum(item["status"] == "skipped" for item in statuses),
        "failed": sum(item["status"] == "failed" for item in statuses),
        "suite_report": str(suite_report),
        "leaderboard": str(suite_report.parent / "leaderboard.csv"),
        "final_report": str(final_report),
        "status": str(state_path),
    }
