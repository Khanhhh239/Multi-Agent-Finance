import pytest

from agent4.metric_selection.catalog import MetricCatalogAdapter, RelationshipRegistry
from agent4.metric_selection.errors import OutputValidationError
from agent4.metric_selection.fewshot import (
    AdaptiveFewshotPolicy,
    ExampleBank,
    FewshotSelector,
)
from agent4.metric_selection.schemas import (
    MetricCandidate,
    MetricSelectionRequest,
    MetricSelectionResult,
)
from agent4.metric_selection.validation import SelectionValidator


def selector(strategy="adaptive"):
    catalog = MetricCatalogAdapter()
    relationships = RelationshipRegistry.from_yaml(
        "config/metric_relationships.yaml", catalog
    )
    bank = ExampleBank.from_jsonl("data/example_bank.jsonl", catalog)
    return FewshotSelector(
        bank,
        catalog,
        relationships,
        AdaptiveFewshotPolicy(0, 4),
        strategy=strategy,
    )


def test_example_bank_is_validated():
    catalog = MetricCatalogAdapter()
    bank = ExampleBank.from_jsonl("data/example_bank.jsonl", catalog)
    assert len(bank) >= 10


def test_coverage_selector_uses_amount_ratio_boundary():
    chosen = selector("coverage").select(
        "Biên lãi gộp?",
        [
            MetricCandidate(metric_id="gross_profit", rerank_score=1.0),
            MetricCandidate(metric_id="gross_margin_pct", rerank_score=0.99),
        ],
    )
    assert chosen
    assert "amount_vs_ratio" in chosen[0].decision_tags


@pytest.mark.parametrize("strategy", ["static", "similarity", "coverage", "adaptive"])
def test_supported_fewshot_modes_are_bounded(strategy):
    chosen = selector(strategy).select(
        "Nợ vay đang bằng mấy lần vốn chủ sở hữu?",
        [
            MetricCandidate(metric_id="debt_to_equity", rerank_score=1.0),
            MetricCandidate(metric_id="debt_balance", rerank_score=0.99),
        ],
    )
    assert 0 < len(chosen) <= 4


def test_zero_shot_returns_no_examples():
    assert selector("zero").select("Doanh thu?", []) == []


def test_empty_example_bank_is_supported():
    catalog = MetricCatalogAdapter()
    bank = ExampleBank([], catalog)
    relationships = RelationshipRegistry([], catalog)
    empty_selector = FewshotSelector(
        bank,
        catalog,
        relationships,
        AdaptiveFewshotPolicy(0, 4),
    )
    assert empty_selector.select("Doanh thu?", []) == []


def test_empty_question_is_rejected():
    with pytest.raises(ValueError, match="empty"):
        MetricSelectionRequest(question="   ")


def test_selection_schema_rejects_contradictory_status():
    with pytest.raises(ValueError):
        MetricSelectionResult(status="unsupported", metric_ids=["net_revenue"], unsupported_reason="x")


def test_validator_rejects_unknown_and_outside_candidate_ids():
    validator = SelectionValidator(MetricCatalogAdapter())
    candidates = [MetricCandidate(metric_id="net_revenue")]
    with pytest.raises(OutputValidationError, match="Unknown"):
        validator.validate(
            MetricSelectionResult(status="resolved", metric_ids=["invented"]), candidates
        )
    with pytest.raises(OutputValidationError, match="outside"):
        validator.validate(
            MetricSelectionResult(status="resolved", metric_ids=["net_profit"]), candidates
        )


def test_validator_rejects_duplicate_candidate_ids():
    validator = SelectionValidator(MetricCatalogAdapter())
    duplicate = [
        MetricCandidate(metric_id="net_revenue"),
        MetricCandidate(metric_id="net_revenue"),
    ]
    with pytest.raises(OutputValidationError, match="duplicate"):
        validator.validate(
            MetricSelectionResult(status="resolved", metric_ids=["net_revenue"]),
            duplicate,
        )
