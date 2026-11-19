"""Exercise the real demo API, sealed row scopes and opt-in evidence."""

import logging
from pathlib import Path
from shutil import copyfile

import httpx
import pytest
from fastapi.testclient import TestClient

from agent4.api import create_app, create_demo_app
from agent4.core.context import build_auth_context
from agent4.core.errors import ContractError
from agent4.engine.metrics import REGISTRY
from agent4.metric_selection.config import MetricSelectionConfig
from agent4.metric_selection.errors import ConfigurationError
from agent4.metric_selection.validator import validate_metrics

_WAREHOUSE = Path(__file__).resolve().parents[2] / "data/cfo_warehouse.duckdb"
_BRANCH = {"X-Demo-Persona": "branch_viewer"}
_CLAIMS = {"tenant_id": "demo-enterprise", "user_id": "injected", "roles": ["finance_analyst"]}


@pytest.fixture(scope="module")
def demo_warehouse(tmp_path_factory):
    target = tmp_path_factory.mktemp("governed-demo") / "warehouse.duckdb"
    copyfile(_WAREHOUSE, target)
    return target


@pytest.fixture
def demo_app(monkeypatch, tmp_path, demo_warehouse):
    preset = tmp_path / "selection.yaml"
    preset.write_text("llm: {provider: mock, model: demo-contract-model}\n", encoding="utf-8")
    monkeypatch.setenv("AGENT4_DB_PATH", str(demo_warehouse))
    monkeypatch.setenv("AGENT4_SELECTION_CONFIG", str(preset))
    return create_demo_app(allow_test_providers=True)


@pytest.fixture
def demo(demo_app):
    with TestClient(demo_app) as client:
        yield client


def _query(client, question, *, headers=None, locale="vi-VN", **fields):
    return client.post(
        "/v1/query",
        headers=headers,
        json={"api_version": "v1", "question": question, "locale": locale, **fields},
    )


def test_demo_factory_publishes_ui_health_and_reference_data(demo, demo_warehouse):
    health = demo.get("/health").json()
    assert health == {
        "status": "ok",
        "demo_mode": True,
        "db_path": str(demo_warehouse),
        "verified_metrics_count": 67,
        "llm_model": "demo-contract-model",
        "llm_provider": "mock",
        "embedding_model": "hashing-v1",
        "embedding_provider": "hashing",
        "retrieval_mode": "full_catalog",
    }
    ui = demo.get("/")
    assert ui.status_code == 200
    assert "X-Demo-Persona" in ui.text
    assert "unsafe-inline" not in ui.headers["Content-Security-Policy"]
    assert ui.headers["Cache-Control"] == "no-store"
    metrics = demo.get("/v1/metrics").json()
    assert len(metrics) == 67
    assert {tuple(sorted(metric)) for metric in metrics} == {
        tuple(
            sorted(
                [
                    "metric_id",
                    "name_vi",
                    "name_en",
                    "unit",
                    "period_type",
                    "supported_dimensions",
                    "allowed_views",
                ]
            )
        )
    }
    ids = {metric["metric_id"] for metric in metrics}
    assert ids == {*REGISTRY, "budget_amount"}
    examples = demo.get("/v1/demo-questions").json()
    assert [example["id"] for example in examples] == [f"D-{n:02d}" for n in range(1, 13)]
    assert examples[10]["persona"] == "branch_viewer"
    assert examples[8]["locale"] == "en-US"


def test_production_demo_requires_both_api_keys(monkeypatch, tmp_path):
    preset = tmp_path / "cloud-selection.yaml"
    preset.write_text("embedding: {provider: openai}\nllm: {provider: openai}\n", encoding="utf-8")
    monkeypatch.setenv("AGENT4_SELECTION_CONFIG", str(preset))
    monkeypatch.delenv("AGENT4_LLM_API_KEY", raising=False)
    monkeypatch.delenv("AGENT4_EMBED_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="both|API key"):
        create_demo_app()


def test_non_demo_ignores_persona_and_requires_auth(monkeypatch):
    monkeypatch.delenv("AGENT4_DEMO_MODE", raising=False)
    with TestClient(create_app(selection_config=MetricSelectionConfig())) as client:
        response = _query(client, "Doanh thu thuần tháng 08/2026?", headers=_BRANCH)
        assert response.status_code == 403
        assert "demo_evidence" not in response.json()
        assert client.get("/").status_code == 404
        assert client.get("/v1/metrics").status_code == 404
        assert client.get("/health").json() == {"status": "ok", "demo_mode": False}
        assert client.get("/healthz").json() == {"status": "live"}


def test_explicit_demo_metric_runs_its_own_query_and_keeps_scope(demo):
    response = _query(
        demo, "metric_id: payroll_summary tháng 08/2026", options={"include_evidence_preview": True}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    rows = {row["component"]: row for row in body["data"]["rows"]}
    assert rows["headcount"]["component_unit"] == "count"
    assert rows["gross_salary"]["component_unit"] == "VND"
    assert (
        _query(demo, "metric_id: payroll_summary tháng 08/2026", headers=_BRANCH).status_code == 403
    )


@pytest.mark.parametrize(
    ("question", "view"),
    [
        ("payroll_summary for August 2026 in the management view", "mgmt"),
        ("mgmt_vs_tax_gap for August 2026 in the tax view", "tax"),
    ],
)
def test_custom_metrics_require_authorization_for_all_their_sources(
    monkeypatch, demo_warehouse, question, view
):
    monkeypatch.delenv("AGENT4_DEMO_MODE", raising=False)
    app = create_app(
        warehouses={"demo-enterprise": demo_warehouse},
        selection_config=MetricSelectionConfig(),
    )

    @app.middleware("http")
    async def inject_claims(request, call_next):
        request.state.idp_claims = _CLAIMS
        request.state.server_policy = {"allowed_views": [view], "policy_version": "test-custom"}
        return await call_next(request)

    with TestClient(app) as client:
        result = _query(client, question, locale="en-US").json()
    assert result["status"] == "forbidden"
    assert result["data"] is None


def test_environment_can_enable_demo(monkeypatch):
    monkeypatch.setenv("AGENT4_DEMO_MODE", "1")
    with TestClient(create_app(selection_config=MetricSelectionConfig())) as client:
        assert client.get("/health").json()["demo_mode"]
        assert client.get("/").status_code == 200


def test_branch_aggregate_is_scoped_in_sql_and_cache(demo):
    question = "Doanh thu thuần tháng 08/2026?"
    company = _query(demo, question).json()
    restricted = _query(demo, question, headers=_BRANCH, options={"include_evidence_preview": True})
    assert company["status"] == "ready"
    assert restricted.status_code == 200
    body = restricted.json()
    hcm = _query(demo, "Doanh thu thuần chi nhánh HCM tháng 08/2026?").json()
    assert body["data"] == hcm["data"]
    assert body["data"]["rows"] != company["data"]["rows"]
    assert body["provenance"]["query_fingerprint"] != company["provenance"]["query_fingerprint"]
    assert body["evidence"]["preview_table"]["sample_row_count"] == 1
    evidence = body["demo_evidence"]
    assert evidence["semantic_plan"]["filters"] == [
        {"field": "branch_code", "op": "=", "value": "HCM"}
    ]
    assert "branch_code = ?" in evidence["sql"]
    assert "HCM" not in evidence["sql"]
    assert "params" not in evidence


@pytest.mark.parametrize(
    "question",
    [
        "Chi phí nhân sự (labor cost) tháng 08/2026 là bao nhiêu?",
        "Show labor_cost in August 2026?",
        "Doanh thu thuần tháng 08/2026 view=tax?",
        "Doanh thu thuần chi nhánh HN tháng 08/2026?",
        "Doanh thu thuần chi nhánh HCM và HN tháng 08/2026?",
    ],
)
def test_branch_viewer_denials_stop_before_model_and_sql(demo, caplog, question):
    with caplog.at_level(logging.INFO, logger="agent4.pipeline"):
        response = _query(demo, question, headers=_BRANCH)
    assert response.status_code == 403
    body = response.json()
    assert body["data"] is None
    assert set(body["demo_evidence"]) == {"trace_id"}
    event = next(record.query_event for record in caplog.records if hasattr(record, "query_event"))
    assert "retrieval_ms" not in event["stage_latencies_ms"]
    assert "sql_execution" not in event["stage_latencies_ms"]


def test_clarification_preserves_persona_and_mandatory_filter(demo):
    ask = _query(
        demo,
        "Doanh thu thuần là bao nhiêu?",
        headers=_BRANCH,
        options={"clarification_mode": "guided"},
    ).json()
    assert ask["status"] == "needs_clarification"
    sid = ask["clarification"]["session_id"]
    assert _query(demo, "Tháng 08/2026", session_id=sid).status_code == 400
    result = _query(demo, "Tháng 08/2026", headers=_BRANCH, session_id=sid).json()
    assert result["status"] == "ready"
    assert result["demo_evidence"]["semantic_plan"]["filters"][0]["value"] == "HCM"


@pytest.mark.asyncio
async def test_invalid_filter_clarification_answer_is_rejected_at_clarification_boundary(demo_app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=demo_app), base_url="http://test"
    ) as client:
        ask = await client.post(
            "/v1/query",
            json={
                "api_version": "v1",
                "question": "metric_id: net_revenue tại chi nhánh XYZ trong tháng 08/2026",
                "locale": "vi-VN",
                "options": {"clarification_mode": "guided"},
            },
        )
        assert ask.status_code == 200
        clarification = ask.json()["clarification"]
        response = await client.post(
            "/v1/query",
            json={
                "api_version": "v1",
                "question": "Lãi gộp quý 3/2026 tăng hay giảm so với quý 2? Chênh bao nhiêu tiền?",
                "locale": "vi-VN",
                "session_id": clarification["session_id"],
            },
        )
    assert clarification["unresolved_slots"] == ["filters"]
    assert clarification["slot_prompts"][0]["choices"] == []
    assert response.status_code == 400
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "invalid_request"
    assert body["error"]["stage"] == "clarification"
    assert body["data"] is None
    assert set(body["demo_evidence"]) == {"trace_id"}


@pytest.mark.asyncio
async def test_demo_reports_unsupported_period_comparison_without_starting_a_session():
    app = create_app(
        demo_mode=True, selection_config=MetricSelectionConfig(llm={"provider": "mock"})
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/query",
            json={
                "api_version": "v1",
                "question": "Lãi gộp quý 3/2026 tăng hay giảm so với quý 2? Chênh bao nhiêu tiền?",
                "locale": "vi-VN",
                "options": {"clarification_mode": "guided"},
            },
        )

    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "unsupported"
    assert body["error"]["code"] == "unsupported_comparison"
    assert "chênh lệch giữa hai kỳ" in body["answer"]
    assert "clarification" not in body
    assert body["data"] is None
    assert set(body["demo_evidence"]) == {"trace_id"}


@pytest.mark.asyncio
async def test_guided_clarification_continues_original_question(monkeypatch, tmp_path):
    preset = tmp_path / "selection.yaml"
    preset.write_text("llm: {provider: mock, model: demo-contract-model}\n", encoding="utf-8")
    monkeypatch.setenv("AGENT4_DB_PATH", str(_WAREHOUSE))
    monkeypatch.setenv("AGENT4_SELECTION_CONFIG", str(preset))
    monkeypatch.setenv("AGENT4_REPORTING_LAST_CLOSED_MONTH", "2026-08")
    demo_app = create_demo_app(allow_test_providers=True)

    async def ambiguous_selection(query, catalog, *, auth_context, query_context, **_kwargs):
        return validate_metrics(
            {
                "status": "ambiguous",
                "metric_ids": [],
                "clarification_question": None,
                "unsupported_reason": None,
            },
            {"candidates": []},
            catalog,
            auth_context,
            query_context,
        )

    monkeypatch.setattr("agent4.pipeline.select_metrics_with_recovery", ambiguous_selection)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=demo_app), base_url="http://test"
    ) as client:
        ask = await client.post(
            "/v1/query",
            json={
                "api_version": "v1",
                "question": "Lợi nhuận tại HCM?",
                "locale": "vi-VN",
                "options": {"clarification_mode": "guided"},
            },
        )
        assert ask.status_code == 200
        body = ask.json()
        assert body["status"] == "needs_clarification"
        clarification = body["clarification"]
        assert clarification["slot_prompts"][0]["slot"] == "metric"
        assert {choice["value"] for choice in clarification["slot_prompts"][0]["choices"]} == {
            "gross_profit",
            "net_profit",
        }
        metric_choice = next(
            choice
            for choice in clarification["slot_prompts"][0]["choices"]
            if choice["value"] == "gross_profit"
        )
        assert clarification["partial_interpretation"]["filters"][0]["value"] == "HCM"

        follow_up = await client.post(
            "/v1/query",
            json={
                "api_version": "v1",
                "question": metric_choice["value"],
                "locale": "vi-VN",
                "session_id": clarification["session_id"],
            },
        )
    assert follow_up.status_code == 200
    result = follow_up.json()
    assert result["status"] == "needs_clarification"
    next_clarification = result["clarification"]
    assert next_clarification["session_id"] == clarification["session_id"]
    assert next_clarification["unresolved_slots"] == ["time"]
    assert next_clarification["slot_prompts"][0]["slot"] == "time"
    assert next_clarification["partial_interpretation"]["metric_ids"] == ["gross_profit"]
    assert next_clarification["partial_interpretation"]["filters"][0]["value"] == "HCM"
    assert {choice["value"] for choice in next_clarification["slot_prompts"][0]["choices"]} == {
        "2026-08",
        "Q2 2026",
    }


@pytest.mark.parametrize("metric", ["experimental_cash_burn", "altman_z_score"])
def test_non_executable_metric_returns_422(demo, metric):
    response = _query(demo, f"Chỉ số {metric} trong tháng 08/2026 là bao nhiêu?")
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "unsupported"
    assert body["data"] is None
    assert set(body["demo_evidence"]) == {"trace_id"}
    if metric == "altman_z_score":
        assert body["error"]["code"] == "unsupported_metric"


def test_unknown_persona_and_client_policy_forgery_are_rejected(demo):
    assert _query(demo, "Doanh thu?", headers={"X-Demo-Persona": "superuser"}).status_code == 403
    assert _query(demo, "Doanh thu?", headers=_BRANCH, allowed_branches=["*"]).status_code == 400


def test_injected_middleware_policy_takes_precedence_and_vendor_evidence_is_redacted(demo_app):
    @demo_app.middleware("http")
    async def host_policy(request, call_next):
        request.state.idp_claims = _CLAIMS
        request.state.server_policy = {
            "allowed_metrics": ["operating_expenses"],
            "allowed_views": ["mgmt"],
            "policy_version": "host-policy",
        }
        return await call_next(request)

    with TestClient(demo_app) as client:
        example = client.get("/v1/demo-questions").json()[7]
        response = _query(client, example["question"], headers=_BRANCH)
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert "partial_data_watermark" in body["warnings"]
        evidence = body["demo_evidence"]
        assert "partner_code = ?" in evidence["sql"]
        assert evidence["semantic_plan"]["filters"] == [
            {"field": "partner_code", "op": "=", "value": "[REDACTED]"}
        ]
        assert "NCC-MK-DG" not in response.text


def test_partially_injected_identity_is_not_upgraded(demo_app):
    @demo_app.middleware("http")
    async def partial_identity(request, call_next):
        request.state.idp_claims = _CLAIMS
        return await call_next(request)

    with TestClient(demo_app) as client:
        assert _query(client, "Doanh thu thuần tháng 08/2026?").status_code == 403


def test_row_policy_is_validated_and_included_in_scope_hash():
    policy = {"allowed_views": ["mgmt"], "policy_version": "demo-test"}
    hcm = build_auth_context(_CLAIMS, {**policy, "allowed_branches": ["HCM"]})
    hn = build_auth_context(_CLAIMS, {**policy, "allowed_branches": ["HN"]})
    assert hcm["policy_hash"] != hn["policy_hash"]
    with pytest.raises(ContractError):
        build_auth_context(_CLAIMS, {**policy, "allowed_branches": ["*", "HCM"]})
