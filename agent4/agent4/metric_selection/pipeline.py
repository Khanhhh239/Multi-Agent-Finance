"""Orchestrator for the independently replaceable metric-selection stages."""
from __future__ import annotations

import time
from typing import Any

from .catalog import MetricCatalogAdapter, MetricDocumentBuilder
from .errors import EmptyCandidateError
from .expansion import MetricExpander
from .fewshot import FewshotSelector
from .llm import LLMMetricSelector
from .reranking import CandidateReranker
from .retrieval import CandidateGenerator
from .schemas import MetricSelectionRequest, MetricSelectionResult, PipelineDebugTrace


class MetricSelectionPipeline:
    def __init__(
        self,
        catalog: MetricCatalogAdapter,
        documents: MetricDocumentBuilder,
        candidate_generator: CandidateGenerator,
        reranker: CandidateReranker,
        llm_selector: LLMMetricSelector,
        *,
        expander: MetricExpander | None = None,
        fewshot_selector: FewshotSelector | None = None,
        versions: dict[str, str] | None = None,
    ) -> None:
        self.catalog = catalog
        self.documents = documents
        self.candidate_generator = candidate_generator
        self.expander = expander
        self.reranker = reranker
        self.fewshot_selector = fewshot_selector
        self.llm_selector = llm_selector
        self.versions = versions or {}

    @staticmethod
    def _elapsed(started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 3)

    async def select(self, request: MetricSelectionRequest) -> MetricSelectionResult:
        trace = PipelineDebugTrace(versions=self.versions)

        started = time.perf_counter()
        retrieval = self.candidate_generator.retrieve(request.question)
        trace.latency_ms["retrieval"] = self._elapsed(started)
        if not retrieval.fused:
            raise EmptyCandidateError("Retrieval produced no metric candidates")

        started = time.perf_counter()
        expanded = (
            self.expander.expand(request.question, retrieval.fused)
            if self.expander
            else [candidate.model_copy(deep=True) for candidate in retrieval.fused]
        )
        trace.latency_ms["expansion"] = self._elapsed(started)

        started = time.perf_counter()
        ranked = self.reranker.rerank(request.question, expanded, request.context)
        trace.latency_ms["reranking"] = self._elapsed(started)
        if not ranked:
            raise EmptyCandidateError("Reranking produced no metric candidates")

        started = time.perf_counter()
        examples = (
            self.fewshot_selector.select(
                request.question,
                ranked,
                dense_top_id=retrieval.dense[0].metric_id if retrieval.dense else None,
                lexical_top_id=retrieval.lexical[0].metric_id if retrieval.lexical else None,
            )
            if self.fewshot_selector
            else []
        )
        trace.latency_ms["fewshot"] = self._elapsed(started)

        started = time.perf_counter()
        outcome = await self.llm_selector.select(
            request.question,
            ranked,
            examples,
            request.context,
        )
        trace.latency_ms["llm"] = self._elapsed(started)
        trace.latency_ms["total"] = round(sum(trace.latency_ms.values()), 3)

        if request.debug:
            trace.initial_dense_candidates = retrieval.dense
            trace.initial_lexical_candidates = retrieval.lexical
            trace.fused_candidates = retrieval.fused
            trace.expanded_candidates = expanded
            trace.final_ranked_candidates = ranked
            trace.selected_fewshot_ids = [example.id for example in examples]
            trace.prompt_token_estimate = outcome.prompt_token_estimate
            trace.llm_output = outcome.result.model_dump(exclude={"debug_trace"})
            trace.validation_errors = list(outcome.validation_errors)
            trace.token_usage = {
                "prompt_tokens": outcome.usage.prompt_tokens,
                "completion_tokens": outcome.usage.completion_tokens,
            }
            trace.versions["llm_model"] = self.llm_selector.provider.model_id
            outcome.result.debug_trace = trace
        return outcome.result


def safe_context(context: dict[str, Any]) -> dict[str, Any]:
    """Return only context fields permitted in operational logs."""
    return {key: context[key] for key in ("view", "reference_date") if key in context}
