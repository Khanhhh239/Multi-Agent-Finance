import json
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent4.text2sql.catalog import CUSTOM_IDS, SYNTHETIC_CUSTOM_HANDLERS
from agent4.text2sql.models import (
    QueryRequest,
    QueryResponse,
    SemanticPlanDraft,
    TimeDraft,
    make_query_request,
)


def test_l0_catalog_has_verified_inventory(catalog):
    public = catalog.public_metrics()
    assert len(public) == 66
    assert Counter(item["kind"] for item in public) == {
        "flow": 26,
        "snapshot": 15,
        "ratio": 5,
        "custom": 20,
    }
    assert len(CUSTOM_IDS) == 20
    assert len(catalog.hash) == 16


def test_all_custom_metrics_have_explicit_capability(catalog):
    for metric_id in CUSTOM_IDS:
        capability = catalog.capability(metric_id)
        assert capability.handler == f"custom:{metric_id}"
        assert capability.synthetic_status in {"SUPPORTED", "BLOCKED"}
        assert capability.real_data_status == "BLOCKED"
    assert SYNTHETIC_CUSTOM_HANDLERS < CUSTOM_IDS


def test_query_contract_forbids_unknown_fields():
    with pytest.raises(ValidationError):
        QueryRequest(**make_query_request("Doanh thu?").model_dump(), secret="bad")


def test_plan_contract_rejects_contradictory_status():
    with pytest.raises(ValidationError):
        SemanticPlanDraft(
            plan_version="1.0",
            status="ready",
            metric_ids=[],
            time=TimeDraft.none(),
            dimensions=[],
            filters=[],
            view=None,
            operation=None,
            sort=None,
            top_k=None,
            comparison=None,
            question_for_user=None,
            unresolved_slots=[],
            reason_code=None,
        )


@pytest.mark.parametrize(
    ("filename", "model"),
    [
        ("query_request.schema.json", QueryRequest),
        ("query_response.schema.json", QueryResponse),
        ("semantic_plan.schema.json", SemanticPlanDraft),
    ],
)
def test_checked_schemas_match_runtime_models(filename, model):
    checked = json.loads((Path("schemas") / filename).read_text(encoding="utf-8"))
    assert checked == model.model_json_schema()
