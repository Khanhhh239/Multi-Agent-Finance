from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

from src.adapters.command_adapter import CommandAdapter


_HTML_TAG = re.compile(r"<[^>]+>")


def _plain_text(value: str) -> str:
    return html.unescape(_HTML_TAG.sub(" ", value or "")).strip()


def surya_result_to_output(value: Any) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(value, dict):
        return str(value), [], []
    pages: list[dict[str, Any]] = []
    for item in value.values():
        if isinstance(item, list):
            pages.extend(page for page in item if isinstance(page, dict))
        elif isinstance(item, dict) and "blocks" in item:
            pages.append(item)
    structured: list[dict[str, Any]] = []
    detections: list[dict[str, Any]] = []
    texts: list[str] = []
    for page in pages:
        for block in page.get("blocks", []):
            if not isinstance(block, dict) or block.get("skipped"):
                continue
            structured.append(block)
            text = _plain_text(str(block.get("html") or block.get("text") or ""))
            if text:
                texts.append(text)
            polygon = block.get("polygon")
            if polygon and len(polygon) >= 3:
                detections.append(
                    {
                        "polygon": [[float(point[0]), float(point[1])] for point in polygon],
                        "text_raw": text,
                        "confidence": block.get("confidence"),
                        "block_type": block.get("label") or block.get("raw_label"),
                        "source_id": str(block.get("reading_order", len(detections))),
                    }
                )
    return "\n".join(texts), structured, detections


class SuryaAdapter(CommandAdapter):
    # Surya 2 returns layout-block polygons rather than line-level text polygons.
    location_support = False

    def load_model(self) -> None:
        self.command = list(
            self.config.get("command")
            or ["surya_ocr", "{input}", "--output_dir", "{output_dir}"]
        )

    def _load_output(
        self, output_dir: Path, stdout: str
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        json_files = sorted(output_dir.rglob("*.json"), key=lambda path: path.stat().st_mtime)
        if not json_files:
            return super()._load_output(output_dir, stdout)
        value = json.loads(json_files[-1].read_text(encoding="utf-8"))
        return surya_result_to_output(value)
