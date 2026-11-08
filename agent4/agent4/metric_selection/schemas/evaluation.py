from typing import Literal

from pydantic import BaseModel, Field


class EvaluationCase(BaseModel):
    id: str
    question: str
    gold_metric_ids: list[str] = Field(default_factory=list)
    gold_status: Literal["resolved", "ambiguous", "unsupported"] = "resolved"
    category: str
    group_id: str | None = None


class EvaluationSummary(BaseModel):
    count: int
    recall_at_k: dict[int, float] = Field(default_factory=dict)
    precision_at_k: dict[int, float] = Field(default_factory=dict)
    mean_reciprocal_rank: float = 0.0
    all_gold_covered_at_k: dict[int, float] = Field(default_factory=dict)
    average_candidate_count: float = 0.0
    average_latency_ms: float = 0.0
    exact_set_match: float | None = None
    metric_precision: float | None = None
    metric_recall: float | None = None
    metric_f1: float | None = None
    valid_output_rate: float | None = None
    status_accuracy: float | None = None
    per_category: dict[str, "EvaluationSummary"] = Field(default_factory=dict)
