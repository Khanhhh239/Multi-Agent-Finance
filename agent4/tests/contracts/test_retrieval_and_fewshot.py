"""Tests for Contracts 5 through 13 of contracts.md:
- metric.embedding-provider.v1
- metric.document-builder.v1
- metric.retrieval.dense.v1
- metric.retrieval.lexical.v1
- metric.retrieval.fusion.v1
- metric.retrieval.rerank.v1
- metric.retrieval.orchestrator.v1
- fewshot.example-bank.v1
- fewshot.retrieval.dynamic.v1
"""

from __future__ import annotations

import pytest

from tests.contract_harness import (
    DEFAULT_FEWSHOT_BANK,
    ContractError,
    EmbeddingProvider,
    MetricCatalog,
    build_metric_documents,
    dense_retrieve,
    fuse_candidates,
    lexical_retrieve,
    orchestrate_retrieval,
    query_intake,
    rerank_candidates,
    retrieve_dynamic_fewshot,
)


class TestEmbeddingAndDocumentBuilderContracts:
    """Contracts 5 & 6: metric.embedding-provider.v1 & metric.document-builder.v1."""

    def test_embedding_dimension_and_version_match(self, embedding_provider: EmbeddingProvider) -> None:
        res = embedding_provider.embed(
            {
                "texts": ["biên lợi nhuận ròng tháng này là bao nhiêu?"],
                "model_id": "multilingual-embedding-v1",
                "model_version": "2026.10",
                "normalize": True,
            }
        )
        assert res["model_id"] == "multilingual-embedding-v1"
        assert res["dimension"] == 16
        assert len(res["vectors"]) == 1
        assert res["vectors"][0]["normalized"] is True
        assert len(res["vectors"][0]["values"]) == 16

        # Model version mismatch must fail
        with pytest.raises(ContractError) as exc_info:
            embedding_provider.embed(
                {
                    "texts": ["test"],
                    "model_id": "multilingual-embedding-v1",
                    "model_version": "1999.01",
                    "normalize": True,
                }
            )
        assert exc_info.value.code == "invalid_request"

    def test_embedding_provider_outage_is_unavailable_not_unsupported(self) -> None:
        down_provider = EmbeddingProvider(available=False)
        with pytest.raises(ContractError) as exc_info:
            down_provider.embed(
                {
                    "texts": ["doanh thu tháng 8"],
                    "model_id": "multilingual-embedding-v1",
                    "model_version": "2026.10",
                    "normalize": True,
                }
            )
        assert exc_info.value.code == "retrieval_unavailable"
        assert exc_info.value.final_status == "temporarily_unavailable"
        assert exc_info.value.retryable is True

    def test_metric_document_no_sql_or_raw_data(self, catalog: MetricCatalog) -> None:
        docs = build_metric_documents(catalog, locale="vi-VN")
        assert len(docs) > 0
        for doc in docs:
            assert doc["catalog_hash"] == catalog.get_catalog_hash()
            assert doc["document_version"] == "metric-doc-v2"
            assert "SELECT " not in doc["document_text"]
            assert "credit_amount" not in doc["document_text"]
            assert doc["metric_id"] != "experimental_cash_burn"


class TestMetricRetrievalPipelineContracts:
    """Contracts 7, 8, 9, 10, 11: Dense, Lexical, Fusion, Reranking, Orchestrator."""

    def test_retrievers_only_return_approved_catalog_metrics(
        self, catalog: MetricCatalog, embedding_provider: EmbeddingProvider
    ) -> None:
        emb = embedding_provider.embed(
            {
                "texts": ["biên lợi nhuận ròng tháng 8"],
                "model_id": embedding_provider.model_id,
                "model_version": embedding_provider.model_version,
                "normalize": True,
            }
        )["vectors"][0]

        dense_out = dense_retrieve(
            {
                "query": "biên lợi nhuận ròng tháng 8",
                "query_embedding": emb,
                "top_k": 15,
                "catalog_hash": catalog.get_catalog_hash(),
                "index_version": "metric-dense-index-v3",
            },
            catalog=catalog,
            expected_dim=embedding_provider.dimension,
        )
        assert dense_out["source"] == "dense"
        for hit in dense_out["hits"]:
            assert catalog.contains(hit["metric_id"])
            assert catalog.get(hit["metric_id"])["status"] == "approved"

        lex_out = lexical_retrieve(
            {
                "query": "biên lợi nhuận ròng tháng 8",
                "top_k": 15,
                "index_version": "metric-lexical-index-v2",
            },
            catalog=catalog,
        )
        assert lex_out["source"] == "lexical"
        assert lex_out["hits"][0]["metric_id"] == "net_profit_margin"
        assert "biên lợi nhuận ròng" in lex_out["hits"][0]["matched_terms"]

    def test_rrf_fusion_deduplication_and_provenance(self) -> None:
        dense_out = {
            "source": "dense",
            "hits": [
                {"metric_id": "net_profit_margin", "rank": 1, "score": 0.912, "index_version": "v3"},
                {"metric_id": "gross_margin", "rank": 2, "score": 0.801, "index_version": "v3"},
            ],
        }
        lexical_out = {
            "source": "lexical",
            "hits": [
                {"metric_id": "net_profit_margin", "rank": 1, "score": 8.42, "matched_terms": ["biên lợi nhuận ròng"]},
            ],
        }
        fused = fuse_candidates(dense_out, lexical_out)
        assert fused["status"] == "candidates_found"
        assert fused["fusion_method"] == "rrf"
        assert len(fused["candidates"]) == 2

        top = fused["candidates"][0]
        assert top["metric_id"] == "net_profit_margin"
        assert top["retrieval_sources"] == ["dense", "lexical"]
        assert top["dense_score"] == 0.912
        assert top["lexical_score"] == 8.42
        assert top["fusion_score"] > fused["candidates"][1]["fusion_score"]

    def test_fusion_empty_candidates(self) -> None:
        fused = fuse_candidates({"source": "dense", "hits": []}, {"source": "lexical", "hits": []})
        assert fused["status"] == "empty_candidates"
        assert fused["candidates"] == []

    def test_reranker_preserves_candidate_set(self, catalog: MetricCatalog) -> None:
        norm_q = query_intake(
            {
                "api_version": "v1",
                "question": "Biên lợi nhuận ròng tháng này là bao nhiêu?",
                "locale": "vi-VN",
            }
        )
        fused = {
            "status": "candidates_found",
            "candidates": [
                {
                    "metric_id": "gross_margin",
                    "rank": 1,
                    "retrieval_sources": ["dense"],
                    "dense_score": 0.88,
                    "lexical_score": None,
                    "fusion_score": 0.0163,
                },
                {
                    "metric_id": "net_profit_margin",
                    "rank": 2,
                    "retrieval_sources": ["dense", "lexical"],
                    "dense_score": 0.85,
                    "lexical_score": 8.4,
                    "fusion_score": 0.0325,
                },
            ],
        }
        reranked = rerank_candidates(norm_q, fused, catalog, requested_view="mgmt")
        out_ids = {c["metric_id"] for c in reranked["ranked_candidates"]}
        assert out_ids == {"gross_margin", "net_profit_margin"}
        assert reranked["ranked_candidates"][0]["metric_id"] == "net_profit_margin"
        assert reranked["reranker_version"] == "metadata-reranker-v2"

    def test_orchestrator_three_statuses(
        self, catalog: MetricCatalog, embedding_provider: EmbeddingProvider
    ) -> None:
        # 1. candidates_found
        q_ok = query_intake({"api_version": "v1", "question": "Doanh thu thuần tháng 8/2026?", "locale": "vi-VN"})
        res_ok = orchestrate_retrieval(q_ok, catalog, embedding_provider)
        assert res_ok["status"] == "candidates_found"
        assert res_ok["candidates"][0]["metric_id"] == "net_revenue"

        # 2. empty_candidates
        q_empty = query_intake({"api_version": "v1", "question": "xyz123 qwerty987", "locale": "vi-VN"})
        res_empty = orchestrate_retrieval(q_empty, catalog, embedding_provider)
        assert res_empty["status"] == "empty_candidates"
        assert res_empty["candidates"] == []

        # 3. retrieval_unavailable
        down_emb = EmbeddingProvider(available=False)
        res_unavail = orchestrate_retrieval(q_ok, catalog, down_emb)
        assert res_unavail["status"] == "retrieval_unavailable"


class TestDynamicFewShotContracts:
    """Contracts 12 & 13: fewshot.example-bank.v1 & fewshot.retrieval.dynamic.v1."""

    def test_fewshot_compatible_only_constraint(self) -> None:
        # Candidate set only has ['net_profit_margin'], so examples for 'net_revenue' or 'operating_expense' must be excluded
        res = retrieve_dynamic_fewshot(
            {
                "question": "Biên lợi nhuận ròng tháng này là bao nhiêu?",
                "locale": "vi-VN",
                "candidate_metric_ids": ["net_profit_margin", "gross_margin"],
                "context": {"view": "mgmt"},
                "max_examples": 3,
                "token_budget": 2500,
                "selection_strategy": "hybrid",
                "example_bank_version": "fewshot-v4",
                "compatible_only": True,
            }
        )
        assert res["status"] == "examples_found"
        for ex in res["examples"]:
            assert set(ex["expected_selection"]["metric_ids"]).issubset({"net_profit_margin", "gross_margin"})
            assert ex["example_id"] != "fs-unapproved-999"

    def test_fewshot_token_budget_and_exclude_self(self) -> None:
        # Exact match with fs-margin-001 question must not return fs-margin-001 itself
        res_self = retrieve_dynamic_fewshot(
            {
                "question": "Tỷ suất lợi nhuận ròng quý trước là bao nhiêu?",
                "locale": "vi-VN",
                "candidate_metric_ids": ["net_profit_margin"],
                "context": {"view": "mgmt"},
                "max_examples": 3,
                "token_budget": 2500,
                "selection_strategy": "hybrid",
                "example_bank_version": "fewshot-v4",
                "compatible_only": True,
            }
        )
        assert all(
            ex["question"] != "Tỷ suất lợi nhuận ròng quý trước là bao nhiêu?" for ex in res_self["examples"]
        )

        # Very tight token budget (100 tokens) should prevent exceeding budget
        res_budget = retrieve_dynamic_fewshot(
            {
                "question": "Biên lợi nhuận ròng tháng 9/2026?",
                "locale": "vi-VN",
                "candidate_metric_ids": ["net_profit_margin", "net_revenue"],
                "context": {"view": "mgmt"},
                "max_examples": 3,
                "token_budget": 100,
                "selection_strategy": "hybrid",
                "example_bank_version": "fewshot-v4",
                "compatible_only": True,
            }
        )
        assert res_budget["total_token_count"] <= 100
        assert res_budget["status"] == "no_compatible_examples"

    def test_fewshot_unavailable_status(self) -> None:
        res = retrieve_dynamic_fewshot(
            {
                "question": "Doanh thu tháng 8?",
                "locale": "vi-VN",
                "candidate_metric_ids": ["net_revenue"],
                "context": {"view": "mgmt"},
                "max_examples": 3,
                "token_budget": 2500,
                "selection_strategy": "hybrid",
                "example_bank_version": "fewshot-v4",
                "compatible_only": True,
            },
            available=False,
        )
        assert res["status"] == "fewshot_unavailable"
        assert res["examples"] == []
