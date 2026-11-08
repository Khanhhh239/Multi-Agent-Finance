from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MetricCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_id: str
    dense_score: float | None = None
    lexical_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None
    retrieval_sources: list[str] = Field(default_factory=list)
    expansion_source: str | None = None
    score_components: dict[str, float] = Field(default_factory=dict)


class PipelineDebugTrace(BaseModel):
    initial_dense_candidates: list[MetricCandidate] = Field(default_factory=list)
    initial_lexical_candidates: list[MetricCandidate] = Field(default_factory=list)
    fused_candidates: list[MetricCandidate] = Field(default_factory=list)
    expanded_candidates: list[MetricCandidate] = Field(default_factory=list)
    final_ranked_candidates: list[MetricCandidate] = Field(default_factory=list)
    selected_fewshot_ids: list[str] = Field(default_factory=list)
    prompt_token_estimate: int = 0
    llm_output: dict[str, Any] | None = None
    validation_errors: list[str] = Field(default_factory=list)
    token_usage: dict[str, int] = Field(default_factory=dict)
    latency_ms: dict[str, float] = Field(default_factory=dict)
    versions: dict[str, str] = Field(default_factory=dict)
