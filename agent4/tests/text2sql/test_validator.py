from datetime import date

import pytest

from agent4.text2sql.errors import Forbidden, PlanRejected
from agent4.text2sql.models import (
    AuthContext,
    FilterDraft,
    SemanticPlanDraft,
    SortDraft,
    TimeDraft,
)
from agent4.text2sql.validation import SemanticValidator


def draft(metric="net_revenue", *, dimensions=None, view="mgmt", time=None, operation="aggregate", filters=None, top_k=None, sort=None):
    return SemanticPlanDraft(
        plan_version="1.0", status="ready", metric_ids=[metric],
        time=time or TimeDraft.range(date(2026, 10, 1), date(2026, 10, 31)),
        dimensions=dimensions or [], filters=filters or [], view=view, operation=operation,
        sort=sort, top_k=top_k, comparison=None, question_for_user=None,
        unresolved_slots=[], reason_code=None,
    )


def test_v01_unknown_metric(catalog, auth):
    validator = SemanticValidator(catalog)
    with pytest.raises(PlanRejected, match="Chỉ số"):
        validator.validate(draft("invented"), auth)


def test_v05_wrong_view(catalog, auth):
    with pytest.raises(PlanRejected) as caught:
        SemanticValidator(catalog).validate(
            draft(
                "cash_and_equivalents", view="tax",
                time=TimeDraft.as_of_date(date(2026, 10, 31)),
            ),
            auth,
        )
    assert caught.value.code == "unsupported_view"


def test_v06_view_permission(catalog):
    auth = AuthContext(user_id="u", tenant_id="t", roles=frozenset(), allowed_views=frozenset({"mgmt"}))
    with pytest.raises(Forbidden):
        SemanticValidator(catalog).validate(draft("taxable_income", view="tax"), auth)


def test_v07_unsupported_group(catalog, auth):
    with pytest.raises(PlanRejected) as caught:
        SemanticValidator(catalog).validate(
            draft(
                "total_assets", dimensions=["branch"],
                time=TimeDraft.as_of_date(date(2026, 10, 31)),
            ), auth
        )
    assert caught.value.code == "unsupported_grouping"


def test_catalog_grouping_without_reconciliation_fixture_fails_closed(catalog, auth):
    with pytest.raises(PlanRejected) as caught:
        SemanticValidator(catalog).validate(draft("net_revenue", dimensions=["branch"]), auth)
    assert caught.value.code == "unsupported_grouping"


def test_v09_rank_is_bounded_by_contract():
    with pytest.raises(ValueError):
        draft("ar_by_customer", dimensions=["customer"], operation="rank", top_k=101)


def test_v10_sort_metric_must_be_selected(catalog, auth):
    with pytest.raises(PlanRejected) as caught:
        SemanticValidator(catalog).validate(
            draft("net_revenue", dimensions=["month"], operation="rank", top_k=5,
                  sort=SortDraft(metric_id="gross_profit", direction="desc")), auth
        )
    assert caught.value.code == "invalid_sort"


def test_v12_invalid_filter_field(catalog, auth):
    with pytest.raises(PlanRejected) as caught:
        SemanticValidator(catalog).validate(
            draft(filters=[FilterDraft(field="tenant_id", operator="eq", values=["other"])]), auth
        )
    assert caught.value.code == "unsupported_filter"


def test_v14_blocked_custom_source(catalog, auth):
    with pytest.raises(PlanRejected) as caught:
        SemanticValidator(catalog).validate(draft("cash_flow_breakdown"), auth)
    assert caught.value.code == "unsupported_data_source"


def test_snapshot_requires_as_of(catalog, auth):
    with pytest.raises(PlanRejected) as caught:
        SemanticValidator(catalog).validate(draft("cash_and_equivalents"), auth)
    assert caught.value.code == "unsupported_time"


def test_filter_value_is_preserved_as_data(catalog, auth):
    value = "HN' OR 1=1 --"
    plan = SemanticValidator(catalog).validate(
        draft(filters=[FilterDraft(field="branch", operator="eq", values=[value])]), auth
    )
    assert plan.filters[0].values == [value]
