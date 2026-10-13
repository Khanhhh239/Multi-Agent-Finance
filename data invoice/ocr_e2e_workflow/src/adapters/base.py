from __future__ import annotations

import time
import traceback
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from PIL import Image

from src.contracts import Detection, OCRResult


class BaseAdapter(ABC):
    location_support = False

    def __init__(self, config: dict[str, Any], run_id: str):
        self.config = config
        self.run_id = run_id
        self.model_id = str(config["model_id"])
        started = time.perf_counter()
        self.load_model()
        self.load_time_ms = (time.perf_counter() - started) * 1000

    @abstractmethod
    def load_model(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def infer(self, image_path: Path) -> dict[str, Any]:
        raise NotImplementedError

    def predict(self, image_path: str | Path) -> OCRResult:
        path = Path(image_path).resolve()
        with Image.open(path) as image:
            width, height = image.size
        started = time.perf_counter()
        try:
            payload = self.infer(path)
            elapsed = (time.perf_counter() - started) * 1000
            detections = [
                item if isinstance(item, Detection) else Detection(**item)
                for item in payload.get("detections", [])
            ]
            return OCRResult(
                schema_version="1.1",
                run_id=self.run_id,
                model_id=self.model_id,
                output_mode=self.config.get("output_mode", "boxes_and_text"),
                image_id=path.name,
                image_width=width,
                image_height=height,
                load_time_ms=self.load_time_ms,
                inference_time_ms=elapsed,
                document_text_raw=payload.get("document_text_raw", ""),
                structured_blocks=payload.get("structured_blocks", []),
                detections=detections,
                error=None,
                metadata={**payload.get("metadata", {}), "location_support": self.location_support},
            )
        except Exception as exc:  # adapters must preserve failed samples
            elapsed = (time.perf_counter() - started) * 1000
            return OCRResult(
                schema_version="1.1",
                run_id=self.run_id,
                model_id=self.model_id,
                output_mode=self.config.get("output_mode", "full_page_text"),
                image_id=path.name,
                image_width=width,
                image_height=height,
                load_time_ms=self.load_time_ms,
                inference_time_ms=elapsed,
                error=f"{type(exc).__name__}: {exc}",
                metadata={
                    "location_support": self.location_support,
                    "traceback": traceback.format_exc(limit=8),
                },
            )


def rectangle_to_polygon(left: float, top: float, width: float, height: float) -> list[list[float]]:
    return [[left, top], [left + width, top], [left + width, top + height], [left, top + height]]


def flatten_document_text(detections: list[dict[str, Any]]) -> str:
    return "\n".join(item.get("text_raw", "") for item in detections if item.get("text_raw"))

