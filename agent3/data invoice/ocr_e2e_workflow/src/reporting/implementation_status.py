from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from src.adapters import IMPLEMENTED_ADAPTERS
from src.environment_setup import REQUIREMENTS
from src.prepare.common import output_path
from src.runner import model_config_path
from src.utils import load_yaml, read_json, resolve_path, resolve_python_executable


def _runtime_state(model_id: str, config: dict[str, Any], python_exists: bool) -> str:
    if not python_exists:
        return "Chưa cài môi trường"
    if model_id == "tesseract" and not (
        (config.get("tesseract_cmd") and resolve_path(config["tesseract_cmd"]).is_file())
        or shutil.which("tesseract")
    ):
        return "Thiếu Tesseract executable"
    if model_id == "surya_ocr_2" and not (
        shutil.which("llama-server") or os.environ.get("SURYA_INFERENCE_URL")
    ):
        return "Thiếu llama-server/SURYA_INFERENCE_URL"
    if config.get("requires_gpu") and not shutil.which("nvidia-smi"):
        return "Thiếu NVIDIA GPU runtime"
    return "Sẵn sàng smoke test"


def render_implementation_status(config: dict[str, Any]) -> Path:
    smoke_path = output_path(config, "reports") / "smoke" / "summary.json"
    smoke = read_json(smoke_path).get("models", {}) if smoke_path.is_file() else {}
    tesseract_config = load_yaml(model_config_path("tesseract"))
    configured_tesseract = tesseract_config.get("tesseract_cmd")
    tesseract_exists = bool(
        (configured_tesseract and resolve_path(configured_tesseract).is_file())
        or shutil.which("tesseract")
    )
    rows: list[list[str]] = []
    for model_id in sorted(REQUIREMENTS):
        model_config = load_yaml(model_config_path(model_id))
        python = resolve_python_executable(model_config["python"])
        smoke_status = smoke.get(model_id, {}).get("status", "chưa chạy")
        rows.append(
            [
                model_id,
                "có" if model_config["adapter"] in IMPLEMENTED_ADAPTERS else "thiếu",
                "đã cài" if python.is_file() else "chưa cài",
                smoke_status,
                _runtime_state(model_id, model_config, python.is_file()),
            ]
        )
    lines = [
        "# Trạng thái triển khai model OCR",
        "",
        "Bảng này tách trạng thái adapter, môi trường và khả năng chạy trên máy hiện tại. Adapter có mã nguồn không đồng nghĩa model đã được tải hoặc máy đủ phần cứng để suy luận.",
        "",
        "| Model | Adapter | Môi trường | Smoke test | Runtime hiện tại |",
        "|---|---:|---:|---|---|",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    lines.extend(
        [
            "",
            "## Ghi chú phần cứng",
            "",
            f"- NVIDIA runtime: {'có' if shutil.which('nvidia-smi') else 'không phát hiện'}.",
            f"- Tesseract executable: {'có' if tesseract_exists else 'không phát hiện'}.",
            f"- llama-server: {'có' if shutil.which('llama-server') else 'không phát hiện'}.",
            "- Các VLM lớn được giữ thành môi trường riêng và chỉ nên cài/chạy trên máy GPU phù hợp hoặc Kaggle.",
        ]
    )
    target = output_path(config, "reports") / "IMPLEMENTATION_STATUS.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
