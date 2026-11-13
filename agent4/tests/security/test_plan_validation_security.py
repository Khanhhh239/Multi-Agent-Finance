"""Production plan-gate regressions for tampered semantic drafts."""

import pytest

from agent4.core.context import query_intake
from agent4.core.errors import ContractError
from agent4.metric_selection.catalog_adapter import (
    build_canonical_catalog,
    build_full_catalog_retrieval_result,
)
from agent4.metric_selection.validator import validate_metrics
from agent4.planning.planner import build_semantic_plan_draft
from agent4.planning.validator import validate_semantic_plan_draft


@pytest.mark.parametrize(
    "overrides",
    [
        {"dimensions": ["branch_code; DROP TABLE ap_bill"]},
        {"dimensions": ["gl_entry"]},
        {"filters": [{"field": "v_mgmt", "op": "=", "value": "HN"}]},
        {"filters": [{"field": "partner_code", "op": "=", "value": "KH0001' OR 1=1 --"}]},
        {"filters": [{"field": "partner_code", "op": "IN", "value": ["KH0001", "NCC-DROP-TABLE"]}]},
        {"filters": [{"field": "partner_code", "op": "=", "value": "KH0001'"}]},
        {
            "status": "needs_clarification",
            "unresolved_slots": ["time"],
            "question_for_user": "ＳＥＬＥＣＴ * FROM gl_wide",
        },
        {
            "status": "needs_clarification",
            "unresolved_slots": ["time"],
            "question_for_user": "WITH x AS (VALUES (1))",
        },
        {"status": "unsupported", "reason_code": "ar_invoice_line"},
    ],
)
def test_production_sql_injection_rejected_before_plan_is_sealed(overrides, analyst_auth):
    catalog = build_canonical_catalog()
    question = "Doanh thu thuần tháng 08/2026?"
    metrics = validate_metrics(
        {
            "status": "resolved",
            "metric_ids": ["net_revenue"],
            "clarification_question": None,
            "unsupported_reason": None,
        },
        build_full_catalog_retrieval_result(question, catalog, analyst_auth),
        catalog,
        analyst_auth,
    )
    draft = build_semantic_plan_draft(
        query_intake({"api_version": "v1", "locale": "vi-VN", "question": question}),
        metrics,
        {},
    )
    draft.update(overrides)
    with pytest.raises(ContractError) as error:
        validate_semantic_plan_draft(draft, metrics, catalog, analyst_auth)
    assert (error.value.code, error.value.stage) == ("invalid_request", "semantic_plan_validation")
    assert error.value.details == {}
