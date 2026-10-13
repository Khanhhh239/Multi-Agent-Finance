from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.adapter_worker import (
    discard_recovered_native_failures,
    failed_result,
    prepare_resume,
)
from src.prepare.common import output_path
from src.utils import (
    WORKFLOW_ROOT,
    environment_metadata,
    load_yaml,
    read_jsonl,
    resolve_path,
    resolve_python_executable,
    sha256_file,
    utc_run_id,
    write_json,
    write_jsonl,
)


def model_config_path(model_id: str) -> Path:
    path = WORKFLOW_ROOT / "configs" / "models" / f"{model_id}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Unknown model config: {path}")
    return path


def _python_for(config: dict[str, Any], allow_current_python: bool) -> Path:
    configured = resolve_python_executable(config.get("python", sys.executable))
    if configured.is_file():
        return configured
    if allow_current_python:
        return Path(sys.executable)
    raise FileNotFoundError(
        f"Model environment is missing: {configured}. Create it from the matching requirements file."
    )


def _run_worker(
    python: Path,
    config_json: Path,
    manifest: Path,
    output: Path,
    run_id: str,
    log_prefix: Path,
    description: str = "OCR",
    resume: bool = False,
) -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(WORKFLOW_ROOT)
    environment["PYTHONUTF8"] = "1"
    environment.setdefault("HF_HOME", str(WORKFLOW_ROOT / "artifacts" / "cache" / "huggingface"))
    environment.setdefault("TORCH_HOME", str(WORKFLOW_ROOT / "artifacts" / "cache" / "torch"))
    environment.setdefault("PADDLE_PDX_CACHE_HOME", str(WORKFLOW_ROOT / "artifacts" / "cache" / "paddlex"))
    worker_config = json.loads(config_json.read_text(encoding="utf-8"))
    if worker_config.get("adapter") == "ppocrv6_vietocr":
        # Paddle and PyTorch share this CPU worker. Conservative thread pools avoid
        # oversubscription and native runtime instability on Windows.
        for name in (
            "OMP_NUM_THREADS",
            "MKL_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
        ):
            environment.setdefault(name, "1")
    for name, value in worker_config.get("environment", {}).items():
        environment[str(name)] = str(value)
    command = [
        str(python),
        "-m",
        "src.adapter_worker",
        "--config-json",
        str(config_json),
        "--manifest",
        str(manifest),
        "--output",
        str(output),
        "--run-id",
        run_id,
        "--description",
        description,
    ]
    if resume:
        command.append("--resume")
    worker_settings = worker_config.get("worker", {})
    max_samples = worker_settings.get("max_samples_per_process")
    if max_samples is None and worker_config.get("adapter") == "ppocrv6_vietocr":
        # Also protects snapshots created before the worker setting was introduced.
        max_samples = 10
    if max_samples is not None:
        max_samples = int(max_samples)
        if max_samples <= 0:
            raise ValueError("worker.max_samples_per_process must be positive")
        command.extend(["--max-samples-per-worker", str(max_samples)])
    log_prefix.parent.mkdir(parents=True, exist_ok=True)

    def tee(stream: Any, terminal: Any, log: Any) -> None:
        while True:
            chunk = stream.read(1)
            if not chunk:
                break
            terminal.write(chunk)
            terminal.flush()
            log.write(chunk)
            log.flush()

    log_mode = "a" if resume else "w"
    with (
        log_prefix.with_suffix(".stdout.log").open(log_mode, encoding="utf-8") as stdout_log,
        log_prefix.with_suffix(".stderr.log").open(log_mode, encoding="utf-8") as stderr_log,
    ):
        process = subprocess.Popen(
            command,
            cwd=WORKFLOW_ROOT,
            env=environment,
            stdout=stdout_log,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=0,
        )
        try:
            tee(process.stderr, sys.stderr, stderr_log)
            return_code = process.wait()
        except KeyboardInterrupt:
            print("\nINTERRUPT: stopping adapter worker; completed JSONL rows are preserved.", flush=True)
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise
    if return_code:
        raise RuntimeError(f"Adapter worker failed ({return_code}); see {log_prefix.parent}")


def _append_worker_crash_failure(
    config_json: Path,
    manifest: Path,
    output: Path,
    run_id: str,
    error: str,
) -> str | None:
    records = list(read_jsonl(manifest))
    remaining, _ = prepare_resume(output, records, True)
    if not remaining:
        return None
    row = remaining[0]
    image_path = Path(row.get("image_path") or row.get("crop_path"))
    config = json.loads(config_json.read_text(encoding="utf-8"))
    prediction = failed_result(config, run_id, image_path, error)
    prediction["metadata"] = {
        "location_support": False,
        "worker_native_crash": error,
        "recovery_action": "sample_marked_failed",
    }
    with output.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(prediction, ensure_ascii=False) + "\n")
    return str(prediction["image_id"])


def _run_worker_with_recovery(
    python: Path,
    config_json: Path,
    manifest: Path,
    output: Path,
    run_id: str,
    log_prefix: Path,
    description: str,
    resume: bool,
    recover_native_crash: bool,
    max_failed_samples: int = 10,
) -> None:
    records = list(read_jsonl(manifest))
    _, completed_before = prepare_resume(output, records, resume)
    failed_samples = 0
    while True:
        try:
            _run_worker(
                python,
                config_json,
                manifest,
                output,
                run_id,
                log_prefix,
                description,
                resume or completed_before > 0,
            )
            remaining_after, completed_after = prepare_resume(output, records, True)
            if not remaining_after:
                return
            if completed_after <= completed_before:
                raise RuntimeError("Adapter worker exited successfully without progress")
            print(
                f"RECYCLE: worker completed {completed_after}/{len(records)}; restarting cleanly",
                flush=True,
            )
            completed_before = completed_after
            resume = True
            continue
        except RuntimeError as exc:
            if not recover_native_crash:
                raise
            remaining, completed_after = prepare_resume(output, records, True)
            if completed_after > completed_before:
                print(
                    f"RECOVER: worker stopped after {completed_after}/{len(records)}; restarting",
                    flush=True,
                )
                completed_before = completed_after
                resume = True
                continue
            if not remaining or failed_samples >= max_failed_samples:
                raise
            failed_id = _append_worker_crash_failure(
                config_json,
                manifest,
                output,
                run_id,
                f"native worker crash: {exc}",
            )
            failed_samples += 1
            completed_before += 1
            resume = True
            print(
                f"RECOVER: marked {failed_id} as failed and continuing "
                f"({failed_samples}/{max_failed_samples} recovery failures)",
                flush=True,
            )


def run_model(
    benchmark_config: dict[str, Any],
    model_id: str,
    split: str,
    limit: int | None = None,
    run_id: str | None = None,
    allow_current_python: bool = False,
    resume: bool = False,
    recover_native_crash: bool = False,
) -> Path:
    if split not in {"dev", "test"}:
        raise ValueError("split must be dev or test")
    config_path = model_config_path(model_id)
    model_config = load_yaml(config_path)
    run_id = run_id or utc_run_id(model_id)
    runs_dir = output_path(benchmark_config, "runs")
    run_dir = runs_dir / run_id
    if run_dir.exists() and not resume:
        raise FileExistsError(f"Run already exists: {run_dir}")
    full_manifest = run_dir / "inputs" / "full_images.jsonl"
    recognition_manifest = run_dir / "inputs" / "recognition_crops.jsonl"
    if run_dir.exists():
        snapshot = json.loads((run_dir / "config.snapshot.json").read_text(encoding="utf-8"))
        if snapshot.get("model_id") != model_id or snapshot.get("split") != split:
            raise ValueError("Existing run does not match requested model/split")
        if snapshot.get("sample_limit") != limit:
            raise ValueError("Existing run does not match requested sample limit")
    else:
        for name in ("logs", "predictions", "metrics", "intermediate", "inputs"):
            (run_dir / name).mkdir(parents=True, exist_ok=True)

        manifest_dir = output_path(benchmark_config, "manifests")
        full_source = manifest_dir / f"full_image_{split}.jsonl"
        rec_source = manifest_dir / f"recognition_{'test' if split == 'test' else 'train'}.jsonl"
        full_records = list(read_jsonl(full_source))[:limit]
        recognition_records = list(read_jsonl(rec_source))[:limit]
        write_jsonl(full_manifest, full_records)
        write_jsonl(recognition_manifest, recognition_records)

        snapshot = {
            **model_config,
            "run_id": run_id,
            "split": split,
            "benchmark_seed": benchmark_config.get("seed"),
            "sample_limit": limit,
            "source_config": str(config_path),
        }
        write_json(run_dir / "config.snapshot.json", snapshot)
        write_json(run_dir / "environment.json", environment_metadata())
        write_json(
            run_dir / "manifest.sha256.json",
            {
                "full_images": sha256_file(full_source),
                "recognition": sha256_file(rec_source),
                "run_full_images": sha256_file(full_manifest),
                "run_recognition": sha256_file(recognition_manifest),
            },
        )
    python = _python_for(model_config, allow_current_python)
    if resume and recover_native_crash:
        for prediction_name in ("raw.jsonl", "recognition_raw.jsonl"):
            removed = discard_recovered_native_failures(
                run_dir / "predictions" / prediction_name
            )
            if removed:
                print(
                    f"RETRY: {removed} native-crash sample(s) from {prediction_name}",
                    flush=True,
                )
    _run_worker_with_recovery(
        python,
        run_dir / "config.snapshot.json",
        full_manifest,
        run_dir / "predictions" / "raw.jsonl",
        run_id,
        run_dir / "logs" / "full_images",
        "Full images",
        resume,
        recover_native_crash,
    )
    _run_worker_with_recovery(
        python,
        run_dir / "config.snapshot.json",
        recognition_manifest,
        run_dir / "predictions" / "recognition_raw.jsonl",
        run_id,
        run_dir / "logs" / "recognition",
        "Recognition crops",
        resume,
        recover_native_crash,
    )
    return run_dir
