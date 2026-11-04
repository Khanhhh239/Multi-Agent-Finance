from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MetricSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    context: dict[str, Any] = Field(default_factory=dict)
    debug: bool = False

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be empty")
        if len(value) > 10_000:
            raise ValueError("question is too long")
        return value
