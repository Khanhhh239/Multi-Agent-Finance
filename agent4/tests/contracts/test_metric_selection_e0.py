"""Production-path checks for the canonical catalog and E0 adapter."""

from __future__ import annotations

import json

import httpx
import pytest

from agent4.core.catalog import DEFAULT_METRICS_DEFINITIONS, MetricCatalog
from agent4.core.errors import ContractError
from agent4.engine.metrics import REGISTRY
from agent4.metric_selection import (
    LLMMetricSelector,
    validate_llm_selection_draft,
    validate_metrics,
)
from agent4.metric_selection.catalog_adapter import (
    build_canonical_catalog,
    build_full_catalog_retrieval_result,
)
from agent4.metric_selection.config import LLMSelectionConfig
from agent4.metric_selection.eval_adapter import predict, predict_e0
from vals.run_eval import Prediction


def _draft(status="resolved", ids=None, clarification=None, reason=None):
    return {
        "status": status,
        "metric_ids": ["net_revenue"] if ids is None else ids,
        "clarification_question": clarification,
        "unsupported_reason": reason,
    }


def test_canonical_catalog_maps_every_registry_metric():
    catalog = build_canonical_catalog()
    visible = catalog.list_visible_metrics({"allowed_views": ["mgmt", "tax", "gl"]})
    assert len(visible) == len(REGISTRY) == 66
    assert len(DEFAULT_METRICS_DEFINITIONS) == 15
    for metric_id, definition in REGISTRY.items():
        metric = catalog.get(metric_id)
        assert metric is not None
        assert metric["label"] == definition.label
        assert metric["description"] == definition.description
        assert metric["period_type"] == definition.period_type
        assert metric["supported_views"] == list(definition.views)
        assert metric["supported_dimensions"] == list(definition.group_bys)
        assert metric["aliases"] == list(definition.synonyms)
        assert metric["default_view"] == definition.default_view
        assert metric["kind"] == definition.kind
        assert metric["unit"] == definition.unit
        assert metric["status"] == "approved"
        assert metric["verified_handler"] is True
        operations = {"aggregate", "compare", "comparison"}
        if {"month", "quarter", "year"}.intersection(definition.group_bys):
            operations.add("timeseries")
        if definition.group_bys:
            operations.update(("breakdown", "rank", "ranking"))
        assert set(metric["supported_operations"]) == operations
        assert "formula" not in metric
    assert catalog.get_catalog_hash() == build_canonical_catalog().get_catalog_hash()


def test_full_catalog_retrieval_filters_governance_and_handles_empty():
    catalog = MetricCatalog()
    auth = {
        "allowed_views": ["mgmt"],
        "allowed_metrics": ["net_revenue", "experimental_cash_burn", "unverified_custom_kpi"],
    }
    result = build_full_catalog_retrieval_result("Doanh thu thuần?", catalog, auth)
    assert result["status"] == "candidates_found"
    assert result["catalog_hash"] == catalog.get_catalog_hash()
    assert [c["metric_id"] for c in result["candidates"]] == ["net_revenue"]
    assert result["candidates"][0]["retrieval_sources"] == ["catalog_full"]
    empty = build_full_catalog_retrieval_result(
        "Doanh thu thuần?", catalog, {**auth, "allowed_views": []}
    )
    assert empty["status"] == "empty_candidates"
    assert empty["candidates"] == []


@pytest.mark.parametrize(
    "draft",
    [
        _draft(ids=[{"metric_id": "net_revenue"}]),
        _draft(ids=["net_revenue", "net_revenue"]),
        _draft("ambiguous", clarification="Which metric?"),
        _draft("ambiguous", ids=[], clarification="Use v_tax."),
        _draft("unsupported", ids=[], reason="SUM (gross_amount)"),
        _draft("unsupported", ids=[], reason="511-521"),
        _draft("unsupported", ids=[], reason="net_revenue / cogs"),
        _draft("unsupported", ids=[], reason="From gl_wide"),
        {**_draft(), "tenant_id": "different"},
    ],
)
def test_rejects_unsafe_or_malformed_drafts(draft):
    with pytest.raises(ContractError, match=".+") as error:
        validate_llm_selection_draft(draft)
    assert error.value.code == "invalid_request"


def test_validator_checks_clarification_empty_selection_and_capabilities():
    auth = {"allowed_views": ["mgmt"]}
    catalog = MetricCatalog()
    result = build_full_catalog_retrieval_result("Doanh thu thuần?", catalog, auth)
    ambiguous = _draft("ambiguous", ids=[], clarification="Bạn muốn doanh thu nào?")
    checked = validate_metrics(ambiguous, result, catalog, auth)
    assert checked["status"] == "needs_clarification"
    assert checked["clarification_question"] == ambiguous["clarification_question"]
    for draft, context in (
        (_draft(ids=[]), {}),
        (_draft("unsupported", ids=[]), {}),
        (_draft(), {"requested_dimensions": ["missing_dimension"]}),
        (_draft(), {"requested_operation": "missing_operation"}),
    ):
        with pytest.raises(ContractError) as error:
            validate_metrics(draft, result, catalog, auth, context)
        assert error.value.code == "unsupported_metric"
        assert error.value.final_status == "unsupported"


@pytest.mark.asyncio
async def test_mock_selector_is_deterministic():
    selector = LLMMetricSelector(LLMSelectionConfig(provider="mock"))
    assert await selector.select("Any question", [{"metric_id": "net_revenue"}]) == (_draft(), None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("draft", "status", "ids", "warning"),
    [
        (_draft(), "resolved", ["net_revenue"], None),
        (_draft(ids=["invented_metric"]), "unsupported", [], "unknown_metric"),
        (_draft(ids=["gross_profit"]), "unsupported", [], "metric_outside_candidates"),
        (
            _draft("ambiguous", ids=[], clarification="Bạn muốn doanh thu nào?"),
            "ambiguous",
            [],
            None,
        ),
        (
            _draft("unsupported", ids=[], reason="Chỉ tiêu chưa có."),
            "unsupported",
            [],
            "unsupported_metric",
        ),
    ],
)
async def test_e0_uses_only_authorized_candidates_and_scores_validated_output(
    monkeypatch, draft, status, ids, warning
):
    client = httpx.AsyncClient

    def ollama(request):
        body = json.loads(request.content)
        assert request.url.path == "/api/chat"
        assert body["model"] == "qwen3:4b"
        assert body["format"] == "json"
        assert body["think"] is False
        assert body["options"]["temperature"] == 0
        assert body["options"]["seed"] == 1234
        prompt = json.loads(body["messages"][1]["content"])
        assert prompt["question"] == "Doanh thu thuần?"
        assert prompt["dynamic_fewshot"] == {"examples": []}
        assert list(prompt.keys()) == ["candidates", "dynamic_fewshot", "question"]
        fields = prompt["candidates"]["fields"]
        [row] = prompt["candidates"]["rows"]
        candidate = dict(zip(fields, row, strict=True))
        assert candidate["metric_id"] == "net_revenue"
        assert candidate["supported_views"] == ["mgmt"]
        assert set(candidate) == {
            "metric_id",
            "label",
            "description",
            "unit",
            "period_type",
            "supported_views",
            "supported_dimensions",
        }
        return httpx.Response(
            200,
            json={
                "message": {"content": json.dumps(draft)},
                "done_reason": "stop",
                "prompt_eval_count": 100,
                "eval_count": 20,
            },
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(ollama), **kwargs),
    )
    assert predict is predict_e0
    prediction = Prediction.model_validate(
        await predict(
            {
                "id": "BM-999",
                "user_query": "Doanh thu thuần?",
                "auth_context": {"allowed_views": ["mgmt"], "allowed_metrics": ["net_revenue"]},
                "query_context": {},
                "seed": 1234,
            }
        )
    )
    assert prediction.retrieved_metric_ids == ["net_revenue"]
    assert prediction.selection.status == status
    assert prediction.selection.metric_ids == ids
    if status == "resolved":
        assert prediction.final_status is None
    assert prediction.usage.input_tokens == 100
    assert prediction.warning_codes == ([warning] if warning else [])
