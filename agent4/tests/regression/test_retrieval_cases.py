import json
from pathlib import Path

import pytest

from agent4.metric_selection.config import load_config
from agent4.metric_selection.factory import build_pipeline
from agent4.metric_selection.llm import MockLLMProvider


@pytest.fixture(scope="module")
def pipeline():
    config = load_config()
    config = config.model_copy(
        update={
            "embedding": config.embedding.model_copy(update={"cache_enabled": False}),
            "llm": config.llm.model_copy(update={"provider": "mock"}),
        }
    )
    return build_pipeline(
        config,
        llm_provider=MockLLMProvider(
            {"status": "unsupported", "metric_ids": [], "unsupported_reason": "test"}
        ),
    )


def test_required_resolved_cases_survive_final_candidate_budget(pipeline):
    lines = Path("data/eval/test.jsonl").read_text(encoding="utf-8").splitlines()
    cases = [json.loads(line) for line in lines if line.strip()]
    for case in cases:
        if case["gold_status"] != "resolved":
            continue
        retrieval = pipeline.candidate_generator.retrieve(case["question"])
        expanded = pipeline.expander.expand(case["question"], retrieval.fused)
        ranked = pipeline.reranker.rerank(case["question"], expanded)
        candidate_ids = {candidate.metric_id for candidate in ranked}
        assert set(case["gold_metric_ids"]).issubset(candidate_ids), case["id"]
