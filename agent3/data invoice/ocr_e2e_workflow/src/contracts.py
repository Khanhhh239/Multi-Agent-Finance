from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


Point = list[float]
Polygon = list[Point]
OutputMode = Literal["boxes_and_text", "full_page_text", "structured_document"]


@dataclass
class Detection:
    polygon: Polygon
    text_raw: str = ""
    confidence: float | None = None
    block_type: str | None = None
    source_id: str | None = None

    def validate(self) -> None:
        if len(self.polygon) < 3:
            raise ValueError("Detection polygon must contain at least three points")
        if any(len(point) != 2 for point in self.polygon):
            raise ValueError("Each polygon point must contain x and y")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("Detection confidence must be in [0, 1]")


@dataclass
class OCRResult:
    schema_version: str
    run_id: str
    model_id: str
    output_mode: OutputMode
    image_id: str
    image_width: int
    image_height: int
    load_time_ms: float
    inference_time_ms: float
    document_text_raw: str = ""
    structured_blocks: list[dict[str, Any]] = field(default_factory=list)
    detections: list[Detection] = field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if self.schema_version != "1.1":
            raise ValueError(f"Unsupported OCR schema: {self.schema_version}")
        if self.image_width <= 0 or self.image_height <= 0:
            raise ValueError("Image dimensions must be positive")
        for detection in self.detections:
            detection.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "OCRResult":
        payload = dict(value)
        payload["detections"] = [Detection(**item) for item in payload.get("detections", [])]
        result = cls(**payload)
        result.validate()
        return result

