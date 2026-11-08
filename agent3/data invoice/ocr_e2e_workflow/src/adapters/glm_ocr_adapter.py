from __future__ import annotations

from pathlib import Path
from typing import Any

from src.adapters.base import BaseAdapter


class GLMOCRAdapter(BaseAdapter):
    location_support = False

    def load_model(self) -> None:
        from glmocr import GlmOcr

        kwargs: dict[str, Any] = {"mode": self.config.get("mode", "selfhosted")}
        if self.config.get("model_name"):
            kwargs["model"] = self.config["model_name"]
        self.parser = GlmOcr(**kwargs)

    def infer(self, image_path: Path) -> dict[str, Any]:
        result = self.parser.parse(str(image_path))
        value = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        markdown = getattr(result, "markdown_result", None) or value.get("markdown_result") or value.get("markdown") or ""
        blocks = value.get("blocks") or value.get("layout") or [value]
        detections = value.get("detections") or []
        if detections:
            self.location_support = True
        return {"document_text_raw": markdown, "structured_blocks": blocks, "detections": detections}
