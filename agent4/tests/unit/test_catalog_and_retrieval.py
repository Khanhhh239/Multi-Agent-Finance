import pytest

from agent4.engine.metrics import M
from agent4.metric_selection.catalog import (
    MetricCatalogAdapter,
    MetricDocumentBuilder,
    RelationshipRegistry,
)
from agent4.metric_selection.catalog.index_builder import MetricIndexBuilder
from agent4.metric_selection.errors import (
    CatalogError,
    ConfigurationError,
    EmbeddingProviderError,
)
from agent4.metric_selection.retrieval import HashingEmbeddingProvider, LexicalRetriever
from agent4.metric_selection.retrieval.dense import DenseRetriever
from agent4.metric_selection.retrieval.fusion import reciprocal_rank_fusion
from agent4.metric_selection.schemas import MetricCandidate


def test_catalog_loads_all_66_metrics_in_stable_order():
    catalog = MetricCatalogAdapter()
    assert len(catalog) == 66
    assert catalog.metric_ids == tuple(sorted(catalog.metric_ids))
    assert len(catalog.version) == 16


def test_catalog_detects_duplicate_definitions():
    metric = M[0]
    with pytest.raises(CatalogError, match="Duplicate"):
        MetricCatalogAdapter({metric.id: metric}, [metric, metric])


def test_documents_are_stable_and_exclude_formula_text():
    catalog = MetricCatalogAdapter()
    builder = MetricDocumentBuilder(catalog)
    first = builder.build("net_revenue")
    second = builder.build("net_revenue")
    assert first == second
    assert "Có 511 − Nợ 511" not in first.text
    assert first.metadata["period_type"] == "flow"


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Doanh thu trước giảm trừ?", "gross_revenue"),
        ("Biên lãi gộp bao nhiêu phần trăm?", "gross_margin_pct"),
        ("Khách hàng nào nợ nhiều nhất?", "ar_by_customer"),
        ("Công ty còn bao nhiêu tiền trong tài khoản?", "cash_and_equivalents"),
    ],
)
def test_lexical_retrieval_handles_vietnamese(question, expected):
    results = LexicalRetriever(MetricCatalogAdapter()).retrieve(question, 5)
    assert results[0].metric_id == expected


def test_hashing_dense_index_is_reproducible(tmp_path):
    catalog = MetricCatalogAdapter()
    documents = MetricDocumentBuilder(catalog)
    provider = HashingEmbeddingProvider(128)
    builder = MetricIndexBuilder(documents, provider)
    first = builder.build()
    path = tmp_path / "index.npz"
    builder.save(first, path)
    second = builder.load(path)
    assert second is not None
    assert first.metric_ids == second.metric_ids
    assert first.matrix.shape == (66, 128)
    results = DenseRetriever(second, provider).retrieve("lợi nhuận sau thuế", 5)
    assert "net_profit" in {item.metric_id for item in results}


def test_index_cache_is_invalidated_when_embedding_config_changes(tmp_path):
    catalog = MetricCatalogAdapter()
    documents = MetricDocumentBuilder(catalog)
    first = MetricIndexBuilder(documents, HashingEmbeddingProvider(128, "first"))
    path = tmp_path / "index.npz"
    first.save(first.build(), path)
    second = MetricIndexBuilder(documents, HashingEmbeddingProvider(128, "second"))
    assert second.load(path) is None


def test_embedding_provider_failure_is_typed():
    catalog = MetricCatalogAdapter()
    documents = MetricDocumentBuilder(catalog)
    good = HashingEmbeddingProvider(128)
    index = MetricIndexBuilder(documents, good).build()

    class BrokenProvider:
        model_id = "broken"

        def embed_query(self, text):
            raise TimeoutError("service timeout")

        def embed_documents(self, texts):
            raise TimeoutError("service timeout")

    with pytest.raises(EmbeddingProviderError, match="service timeout"):
        DenseRetriever(index, BrokenProvider()).retrieve("doanh thu", 5)


def test_rrf_preserves_provenance_and_tie_breaks():
    dense = [MetricCandidate(metric_id="b"), MetricCandidate(metric_id="a")]
    lexical = [MetricCandidate(metric_id="a"), MetricCandidate(metric_id="b")]
    fused = reciprocal_rank_fusion([("dense", dense), ("lexical", lexical)], 2)
    assert [item.metric_id for item in fused] == ["a", "b"]
    assert fused[0].retrieval_sources == ["dense", "lexical"]


def test_relationship_registry_rejects_unknown_metric(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        "relationships:\n  - source: net_revenue\n    target: invented\n    type: related_concept\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="unknown metric"):
        RelationshipRegistry.from_yaml(path, MetricCatalogAdapter())
