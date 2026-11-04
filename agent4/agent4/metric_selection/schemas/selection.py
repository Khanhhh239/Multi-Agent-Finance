from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .retrieval import PipelineDebugTrace


class StructuredMetricSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["resolved", "ambiguous", "unsupported"]
    metric_ids: list[str] = Field(default_factory=list)
    clarification_question: str | None = None
    unsupported_reason: str | None = None
    @model_validator(mode="after")
    def validate_status(self) -> "StructuredMetricSelection":
        if len(self.metric_ids) != len(set(self.metric_ids)):
            raise ValueError("metric_ids must not contain duplicates")
        if self.status == "resolved" and not self.metric_ids:
            raise ValueError("resolved results require at least one metric")
        if self.status != "resolved" and self.metric_ids:
            raise ValueError(f"{self.status} results must not contain metric_ids")
        if self.status == "ambiguous" and not self.clarification_question:
            raise ValueError("ambiguous results require clarification_question")
        if self.status == "unsupported" and not self.unsupported_reason:
            raise ValueError("unsupported results require unsupported_reason")
        return self


class MetricSelectionResult(StructuredMetricSelection):
    debug_trace: PipelineDebugTrace | None = None
