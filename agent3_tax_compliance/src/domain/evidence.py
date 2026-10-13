import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .base import Contract, Identifier

Unit = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class Evidence(Contract):
    source_id: Identifier
    document_id: Identifier
    page_index: Annotated[int, Field(strict=True, ge=0)]
    coordinate_system: Literal['NORMALIZED_TOP_LEFT'] = 'NORMALIZED_TOP_LEFT'
    bbox: tuple[Unit, Unit, Unit, Unit]
    block_id: Identifier | None = None
    span: tuple[Annotated[int, Field(strict=True, ge=0)], Annotated[int, Field(strict=True, ge=0)]] | None = None
    transform_id: Identifier | None = None

    @model_validator(mode='after')
    def geometry(self):
        x0, y0, x1, y1 = self.bbox
        if x0 >= x1 or y0 >= y1:
            raise ValueError('bbox must have positive area')
        if self.span is not None and self.span[0] >= self.span[1]:
            raise ValueError('span must be nonempty and ordered')
        return self


class PageTransform(Contract):
    transform_id: Identifier
    source_id: Identifier
    page_index: Annotated[int, Field(strict=True, ge=0)]
    from_space: Literal['PDF_POINTS', 'IMAGE_PIXELS']
    to_space: Literal['NORMALIZED_TOP_LEFT'] = 'NORMALIZED_TOP_LEFT'
    source_width: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    source_height: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    matrix: tuple[float, float, float, float, float, float]

    @model_validator(mode='after')
    def invertible(self):
        import math
        a, b, c, d, e, f = self.matrix
        if not all(math.isfinite(v) for v in self.matrix) or a*d-b*c == 0:
            raise ValueError('finite invertible affine transform required')
        return self


class Provenance(Contract):
    method: Identifier
    adapter_version: Identifier
    evidence: tuple[Evidence, ...] = ()
    calibration_version: Identifier | None = None
    deterministic_policy_version: Identifier | None = None
    review_event_id: Identifier | None = None
    derived_from: tuple[str, ...] = ()


def stable_candidate_id(field_path: str, raw_value: str, evidence: tuple[Evidence, ...]) -> str:
    payload = [field_path, raw_value, [e.model_dump(mode='json') for e in evidence]]
    return 'candidate-' + hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]
