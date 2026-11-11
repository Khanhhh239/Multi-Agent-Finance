import pytest

from agent4.core.context import query_intake
from agent4.core.errors import ContractError
from agent4.planning.clarification import ClarificationSessionStore, resolve_clarification_turn
from agent4.planning.planner import build_semantic_plan_draft
from agent4.planning.validator import ValidatedPlan


def start(store, catalog, auth, question, metric=None, locale="vi-VN", calendar=None):
    query = query_intake({"api_version": "v1", "question": question, "locale": locale})
    if calendar is not None:
        query["reporting_calendar"] = calendar
    metrics = {
        "status": "validated" if metric else "needs_clarification",
        "metric_ids": [metric] if metric else [],
        "catalog_hash": catalog.get_catalog_hash(),
        "validated_capabilities": {metric: catalog.get_capability(metric)} if metric else {},
    }
    draft = build_semantic_plan_draft(query, metrics, {})
    return store.start(draft, metrics, catalog, auth, query)


@pytest.mark.parametrize(
    ("question", "choices"),
    [
        ("Profit?", {"gross_profit", "net_profit"}),
        ("Profit margin?", {"gross_margin", "net_profit_margin"}),
        ("Debt?", {"ar_balance", "ap_balance", "loan_balance"}),
    ],
)
def test_metric_choices_are_localized(selection_catalog, analyst_auth, question, choices):
    payload = start(
        ClarificationSessionStore(), selection_catalog, analyst_auth, question, locale="en-US"
    )
    metric_prompt, time_prompt = payload["slot_prompts"]
    assert {choice["value"] for choice in metric_prompt["choices"]} == choices
    assert all(choice["label"].isascii() for choice in metric_prompt["choices"])
    assert ("as-of" in time_prompt["prompt"]) == (question == "Debt?")


def test_multiturn_preserves_filter_and_consumes_session(selection_catalog, analyst_auth):
    store = ClarificationSessionStore()
    payload = start(store, selection_catalog, analyst_auth, "Lợi nhuận tại HCM?")
    assert payload["partial_interpretation"]["filters"][0]["value"] == "HCM"
    sid = payload["session_id"]
    next_turn = resolve_clarification_turn(
        store, sid, {"metric": "gross_profit"}, selection_catalog, analyst_auth
    )
    assert next_turn["unresolved_slots"] == ["time"]
    plan = resolve_clarification_turn(store, sid, "Tháng 08/2026", selection_catalog, analyst_auth)
    assert isinstance(plan, ValidatedPlan)
    assert plan.metric_ids == ("gross_profit",)
    assert plan.filters[0].value == "HCM"
    assert plan.time.start.isoformat() == "2026-08-01"
    with pytest.raises(ContractError):
        resolve_clarification_turn(store, sid, "Tháng 08/2026", selection_catalog, analyst_auth)


def test_scope_policy_and_injection_are_rejected(selection_catalog, analyst_auth):
    store = ClarificationSessionStore(max_turns=1)
    auth = {**analyst_auth, "allowed_metrics": ["gross_profit"]}
    payload = start(store, selection_catalog, auth, "Lợi nhuận tháng 08/2026?")
    assert [choice["value"] for choice in payload["slot_prompts"][0]["choices"]] == ["gross_profit"]
    sid = payload["session_id"]
    for key in ("tenant_id", "user_id", "policy_hash"):
        with pytest.raises(ContractError):
            resolve_clarification_turn(
                store, sid, "gross_profit", selection_catalog, {**auth, key: "other"}
            )
    with pytest.raises(ContractError):
        resolve_clarification_turn(store, sid, "SELECT * FROM v_mgmt", selection_catalog, auth)
    with pytest.raises(ContractError):
        resolve_clarification_turn(store, sid, "gross_profit", selection_catalog, auth)


def test_conflicting_view_only_offers_authorized_choices(selection_catalog, analyst_auth):
    payload = start(
        ClarificationSessionStore(),
        selection_catalog,
        analyst_auth,
        "Doanh thu tháng 08/2026 theo quản trị hay sổ thuế?",
        "net_revenue",
    )
    assert payload["unresolved_slots"] == ["view"]
    assert payload["slot_prompts"][0]["choices"] == [{"value": "mgmt", "label": "Quản trị"}]


def test_calendar_choices_follow_server_metadata(selection_catalog, analyst_auth):
    store = ClarificationSessionStore()
    payload = start(
        store,
        selection_catalog,
        analyst_auth,
        "Doanh thu thuần?",
        "net_revenue",
        calendar={"last_closed_month": "2026-08"},
    )
    assert payload["slot_prompts"][0]["choices"] == [
        {"value": "2026-08", "label": "Tháng 2026-08"},
        {"value": "Q2 2026", "label": "Quý 2/2026"},
    ]
    plan = resolve_clarification_turn(
        store,
        payload["session_id"],
        "Tháng 2026-08",
        selection_catalog,
        analyst_auth,
    )
    assert plan.time.start.isoformat() == "2026-08-01"


def test_breakdown_grain_is_applied_after_time_clarification(selection_catalog, analyst_auth):
    store = ClarificationSessionStore()
    payload = start(
        store, selection_catalog, analyst_auth, "Doanh thu theo chi nhánh?", "net_revenue"
    )
    assert payload["unresolved_slots"] == ["time"]
    plan = resolve_clarification_turn(
        store,
        payload["session_id"],
        "Quý 2 năm 2026",
        selection_catalog,
        analyst_auth,
    )
    assert isinstance(plan, ValidatedPlan)
    assert plan.operation == "breakdown"
    assert plan.time.start.isoformat() == "2026-04-01"
    assert plan.time.end.isoformat() == "2026-06-30"
    assert plan.time.grain == "month"
