from agent4.metric_selection.catalog import (
    MetricCatalogAdapter,
    MetricDocumentBuilder,
    RelationshipRegistry,
)
from agent4.metric_selection.expansion import MetricExpander
from agent4.metric_selection.reranking import CandidateReranker, MetadataRanker
from agent4.metric_selection.schemas import MetricCandidate


def dependencies():
    catalog = MetricCatalogAdapter()
    relationships = RelationshipRegistry.from_yaml(
        "config/metric_relationships.yaml", catalog
    )
    return catalog, relationships


def test_one_hop_expansion_is_bounded_and_records_source():
    _, relationships = dependencies()
    expander = MetricExpander(relationships, max_candidates=2)
    expanded = expander.expand(
        "Khách hàng nào nợ nhiều nhất?",
        [MetricCandidate(metric_id="ar_balance", fusion_score=0.1)],
    )
    assert len(expanded) == 2
    assert expanded[1].metric_id == "ar_by_customer"
    assert expanded[1].expansion_source == "ar_balance:specialization"


def test_metadata_ranker_prefers_ratio_for_percentage_question():
    catalog, _ = dependencies()
    reranker = CandidateReranker(
        MetricDocumentBuilder(catalog), MetadataRanker(catalog), final_top_k=2
    )
    ranked = reranker.rerank(
        "Biên lãi gộp bao nhiêu phần trăm?",
        [MetricCandidate(metric_id="gross_profit"), MetricCandidate(metric_id="gross_margin_pct")],
    )
    assert ranked[0].metric_id == "gross_margin_pct"
    assert ranked[0].score_components["unit_ratio"] > 0


def test_metadata_ranker_prefers_snapshot_for_current_cash():
    catalog, _ = dependencies()
    reranker = CandidateReranker(
        MetricDocumentBuilder(catalog), MetadataRanker(catalog), final_top_k=2
    )
    ranked = reranker.rerank(
        "Hiện tại công ty còn bao nhiêu tiền?",
        [MetricCandidate(metric_id="net_cash_flow"), MetricCandidate(metric_id="cash_and_equivalents")],
    )
    assert ranked[0].metric_id == "cash_and_equivalents"
