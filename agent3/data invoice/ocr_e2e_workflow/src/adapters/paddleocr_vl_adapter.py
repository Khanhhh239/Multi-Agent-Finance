from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.adapters.base import BaseAdapter, rectangle_to_polygon
from src.adapters.paddle_common import _as_dict, paddle_result_to_detections


def _find_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("markdown", "text", "content", "rec_text", "parsing_res_list"):
            if key in value:
                candidate = _find_text(value[key])
                if candidate:
                    return candidate
        return "\n".join(filter(None, (_find_text(item) for item in value.values())))
    if isinstance(value, list):
        return "\n".join(filter(None, (_find_text(item) for item in value)))
    return ""


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        return _json_safe(value.tolist())
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def paddle_vl_blocks_to_detections(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    detections: list[dict[str, Any]] = []
    for value in values:
        payload = value.get("res", value)
        for block in payload.get("parsing_res_list", []):
            bbox = block.get("block_bbox")
            if bbox is None:
                continue
            bbox = _json_safe(bbox)
            if len(bbox) == 4 and not isinstance(bbox[0], list):
                x1, y1, x2, y2 = [float(item) for item in bbox]
                polygon = rectangle_to_polygon(x1, y1, x2 - x1, y2 - y1)
            elif len(bbox) >= 3:
                polygon = [[float(point[0]), float(point[1])] for point in bbox]
            else:
                continue
            detections.append(
                {
                    "polygon": polygon,
                    "text_raw": str(block.get("block_content") or ""),
                    "confidence": None,
                    "block_type": block.get("block_label"),
                    "source_id": str(block.get("block_id", len(detections))),
                }
            )
    return detections


class PaddleOCRVLAdapter(BaseAdapter):
    # Returned boxes are layout regions, not line-level OCR polygons.
    location_support = False

    def load_model(self) -> None:
        try:
            from paddleocr import PaddleOCRVL

            cls = PaddleOCRVL
        except ImportError:
            from paddlex import create_pipeline

            self.pipeline = create_pipeline(pipeline="PaddleOCR-VL")
            return
        kwargs: dict[str, Any] = {"pipeline_version": self.config.get("pipeline_version", "v1.6")}
        for option in (
            "vl_rec_backend",
            "vl_rec_server_url",
            "vl_rec_api_model_name",
            "vl_rec_api_key",
            "use_doc_orientation_classify",
            "use_doc_unwarping",
            "use_layout_detection",
            "device",
            "enable_mkldnn",
        ):
            if self.config.get(option) is not None:
                kwargs[option] = self.config[option]
        self.pipeline = cls(**kwargs)

    def infer(self, image_path: Path) -> dict[str, Any]:
        results = list(self.pipeline.predict(str(image_path)))
        values = [_json_safe(_as_dict(item)) for item in results]
        detections = paddle_vl_blocks_to_detections(values) or paddle_result_to_detections(results)
        text = _find_text(values)
        return {
            "detections": detections,
            "document_text_raw": text,
            "structured_blocks": values,
            "metadata": {"raw_result_count": len(values)},
        }
