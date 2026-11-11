"""Check drafts against the deterministic rendering of verified result cells."""

from agent4.core.catalog import MetricCatalog
from agent4.core.errors import ContractError
from agent4.planning.validator import ValidatedPlan

from .generator import generate_grounded_answer


def validate_answer(
    draft: dict,
    validated_result: dict,
    plan: ValidatedPlan,
    catalog: MetricCatalog,
    *,
    locale: str = "vi-VN",
    fallback_on_failure: bool = True,
) -> dict:
    expected = generate_grounded_answer(plan, validated_result, catalog, locale=locale)
    mismatch = draft != expected
    if mismatch and not fallback_on_failure:
        raise ContractError("ungrounded_answer", "answer_validation", "Answer failed grounding.")
    return {
        "status": "valid",
        "answer": expected["summary"],
        "warnings": expected["warnings"],
        "validated_claims": [{**claim, "verified": True} for claim in expected["claims"]],
        "used_fallback": mismatch,
    }
