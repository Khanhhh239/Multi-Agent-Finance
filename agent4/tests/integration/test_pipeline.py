import pytest

from agent4.metric_selection.config import load_config
from agent4.metric_selection.errors import OutputValidationError
from agent4.metric_selection.factory import build_pipeline
from agent4.metric_selection.llm import MockLLMProvider
from agent4.metric_selection.schemas import MetricSelectionRequest


def make_test_config():
    config = load_config()
    return config.model_copy(
        update={
            "embedding": config.embedding.model_copy(update={"cache_enabled": False}),
            "llm": config.llm.model_copy(update={"provider": "mock", "max_retries": 1}),
        }
    )


@pytest.mark.asyncio
async def test_pipeline_returns_validated_selection_and_debug_trace():
    provider = MockLLMProvider(
        {"status": "resolved", "metric_ids": ["net_revenue"]}
    )
    pipeline = build_pipeline(make_test_config(), llm_provider=provider)
    result = await pipeline.select(
        MetricSelectionRequest(question="Doanh thu thuần tháng này?", debug=True)
    )
    assert result.metric_ids == ["net_revenue"]
    assert result.debug_trace is not None
    assert result.debug_trace.final_ranked_candidates
    assert result.debug_trace.versions["catalog"] == pipeline.catalog.version
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_invalid_first_selection_is_retried_with_feedback():
    provider = MockLLMProvider(
        [
            {"status": "resolved", "metric_ids": ["invented_metric"]},
            {"status": "resolved", "metric_ids": ["gross_profit"]},
        ]
    )
    pipeline = build_pipeline(make_test_config(), llm_provider=provider)
    result = await pipeline.select(MetricSelectionRequest(question="Lãi gộp?"))
    assert result.metric_ids == ["gross_profit"]
    assert provider.calls == 2
    assert "validation_feedback" in provider.messages[1][1]["content"]


@pytest.mark.asyncio
async def test_pipeline_supports_unsupported_result_without_fabricating_id():
    provider = MockLLMProvider(
        {
            "status": "unsupported",
            "metric_ids": [],
            "unsupported_reason": "Danh mục không hỗ trợ giá cổ phiếu.",
        }
    )
    pipeline = build_pipeline(make_test_config(), llm_provider=provider)
    result = await pipeline.select(MetricSelectionRequest(question="Giá cổ phiếu hôm nay?"))
    assert result.status == "unsupported"
    assert result.metric_ids == []


@pytest.mark.asyncio
async def test_pipeline_supports_ambiguous_result():
    provider = MockLLMProvider(
        {
            "status": "ambiguous",
            "metric_ids": [],
            "clarification_question": "Bạn muốn lợi nhuận gộp hay sau thuế?",
        }
    )
    pipeline = build_pipeline(make_test_config(), llm_provider=provider)
    result = await pipeline.select(MetricSelectionRequest(question="Lợi nhuận?"))
    assert result.status == "ambiguous"
    assert result.clarification_question


@pytest.mark.asyncio
async def test_malformed_structured_output_fails_explicitly_after_retry():
    provider = MockLLMProvider(
        {"status": "resolved", "metric_ids": []}
    )
    pipeline = build_pipeline(make_test_config(), llm_provider=provider)
    with pytest.raises(OutputValidationError, match="No valid"):
        await pipeline.select(MetricSelectionRequest(question="Doanh thu?"))
    assert provider.calls == 2
