from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..errors import OutputParseError

ModelT = TypeVar("ModelT", bound=BaseModel)
FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", flags=re.IGNORECASE)


def parse_structured_output(content: str | dict, response_model: type[ModelT]) -> ModelT:
    try:
        if isinstance(content, dict):
            return response_model.model_validate(content)
        cleaned = FENCE_RE.sub("", content.strip())
        return response_model.model_validate(json.loads(cleaned))
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise OutputParseError(f"LLM returned invalid structured output: {exc}") from exc
