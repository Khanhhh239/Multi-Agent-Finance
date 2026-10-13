from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from src.metrics.recognition import evaluate_pairs
from src.postprocess.text_normalizer import normalize_text
from src.runner import _run_worker, model_config_path
from src.utils import (
    WORKFLOW_ROOT,
    load_yaml,
    read_jsonl,
    resolve_python_executable,
    sha256_file,
    write_json,
    write_jsonl,
)


CHARSET_TEXT = (
    "ă â ê ô ơ ư – Ă Â Ê Ô Ơ Ư\n"
    "ấ ầ ẩ ẫ ậ – ớ ờ ở ỡ ợ – ứ ừ ử ữ ự\n"
    "Tổng tiền: 1.234.567đ – Thời gian: 15/08/2020 10:44"
)


def _font(size: int = 34) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/times.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def create_fixtures(blank_count: int = 3) -> list[dict[str, Any]]:
    fixture_dir = WORKFLOW_ROOT / "tests" / "fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    charset_path = fixture_dir / "vietnamese_charset.png"
    image = Image.new("RGB", (1500, 260), "white")
    draw = ImageDraw.Draw(image)
    draw.multiline_text((30, 25), CHARSET_TEXT, fill="black", font=_font(), spacing=14)
    image.save(charset_path)
    records = [{"image_id": charset_path.name, "image_path": str(charset_path), "fixture_type": "charset"}]
    for index in range(blank_count):
        path = fixture_dir / f"blank_{index + 1}.png"
        shade = 255 - index * 3
        Image.new("RGB", (768, 1024), (shade, shade, shade)).save(path)
        records.append({"image_id": path.name, "image_path": str(path), "fixture_type": "blank"})
    return records


def run_smoke(models: list[str], blank_count: int = 3) -> dict[str, Any]:
    records = create_fixtures(blank_count)
    smoke_root = WORKFLOW_ROOT / "reports" / "smoke"
    smoke_root.mkdir(parents=True, exist_ok=True)
    manifest = smoke_root / "fixtures.jsonl"
    write_jsonl(manifest, records)
    summary_path = smoke_root / "summary.json"
    if summary_path.is_file():
        report = json.loads(summary_path.read_text(encoding="utf-8"))
        report["charset_text"] = CHARSET_TEXT
        report.setdefault("models", {})
    else:
        report = {"charset_text": CHARSET_TEXT, "models": {}}
    for model_id in models:
        config_path = model_config_path(model_id)
        config = load_yaml(config_path)
        python = resolve_python_executable(config.get("python", sys.executable))
        if not python.is_file():
            report["models"][model_id] = {"status": "missing_environment", "python": str(python)}
            continue
        config_json = smoke_root / f"{model_id}.config.json"
        write_json(config_json, config)
        output = smoke_root / f"{model_id}.jsonl"
        try:
            _run_worker(python, config_json, manifest, output, f"smoke_{model_id}", smoke_root / "logs" / model_id)
            predictions = list(read_jsonl(output))
            charset = predictions[0]
            recognized = charset.get("document_text_raw", "") or " ".join(
                item.get("text_raw", "") for item in charset.get("detections", [])
            )
            metric = evaluate_pairs([(CHARSET_TEXT, recognized)], normalized=True)
            blank_text = []
            for prediction in predictions[1:]:
                text = prediction.get("document_text_raw", "") or " ".join(
                    item.get("text_raw", "") for item in prediction.get("detections", [])
                )
                blank_text.append(bool(normalize_text(text)))
            model_report: dict[str, Any] = {
                "status": "ok" if not charset.get("error") else "failed",
                "error": charset.get("error"),
                "charset_cer": metric["cer_micro"],
                "charset_exact_match": metric["exact_match"],
                "blank_image_text_rate": sum(blank_text) / max(1, len(blank_text)),
            }
            dictionary_path = config.get("dictionary_path")
            if dictionary_path and resolve_path(dictionary_path).is_file():
                model_report["dictionary_sha256"] = sha256_file(dictionary_path)
            report["models"][model_id] = model_report
        except Exception as exc:
            report["models"][model_id] = {"status": "worker_failed", "error": f"{type(exc).__name__}: {exc}"}
    write_json(summary_path, report)
    return report
