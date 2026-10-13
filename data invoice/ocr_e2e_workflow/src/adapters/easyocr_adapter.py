from __future__ import annotations

from pathlib import Path
from typing import Any

from src.adapters.base import BaseAdapter, flatten_document_text
from src.utils import resolve_path


class EasyOCRAdapter(BaseAdapter):
    location_support = True

    def load_model(self) -> None:
        import easyocr
        import torch

        gpu_setting = self.config.get("gpu", "auto")
        gpu = torch.cuda.is_available() if gpu_setting == "auto" else bool(gpu_setting)
        model_dir = resolve_path(self.config.get("model_storage_directory", "artifacts/models/easyocr"))
        model_dir.mkdir(parents=True, exist_ok=True)
        self.reader = easyocr.Reader(
            self.config.get("languages", ["vi", "en"]),
            gpu=gpu,
            model_storage_directory=str(model_dir),
            download_enabled=bool(self.config.get("download_enabled", True)),
        )

    def infer(self, image_path: Path) -> dict[str, Any]:
        results = self.reader.readtext(str(image_path), detail=1, paragraph=False)
        detections = [
            {
                "polygon": [[float(x), float(y)] for x, y in polygon],
                "text_raw": str(text),
                "confidence": float(confidence),
                "source_id": str(index),
            }
            for index, (polygon, text, confidence) in enumerate(results)
        ]
        return {"detections": detections, "document_text_raw": flatten_document_text(detections)}

