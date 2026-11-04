"""Composition root for the default metric-selection implementation."""
from __future__ import annotations

from .catalog import (
    MetricCatalogAdapter,
    MetricDocumentBuilder,
    RelationshipRegistry,
)
from .catalog.index_builder import MetricIndexBuilder
from .config import MetricSelectionConfig, config_fingerprint, load_config
from .errors import ConfigurationError
from .expansion import MetricExpander
from .fewshot import (
    AdaptiveFewshotPolicy,
    ExampleBank,
    FewshotSelector,
    PromptBuilder,
)
from .llm import LLMMetricSelector, LLMProvider, OllamaLLMProvider
from .pipeline import MetricSelectionPipeline
from .reranking import CandidateReranker, CrossEncoder, MetadataRanker
from .retrieval import (
    CandidateGenerator,
    DenseRetriever,
    HashingEmbeddingProvider,
    LexicalRetriever,
)
from .retrieval.mentions import MentionExtractor
from .validation import SelectionValidator


def build_pipeline(
    config: MetricSelectionConfig | None = None,
    *,
    llm_provider: LLMProvider | None = None,
    cross_encoder: CrossEncoder | None = None,
) -> MetricSelectionPipeline:
    config = config or load_config()
    catalog = MetricCatalogAdapter()
    documents = MetricDocumentBuilder(catalog)
    embedding = HashingEmbeddingProvider(
        config.embedding.dimensions,
        config.embedding.model,
    )
    index_builder = MetricIndexBuilder(documents, embedding)
    cache_path = config.embedding.cache_path if config.embedding.cache_enabled else None
    index = index_builder.load_or_build(cache_path)

    dense = DenseRetriever(index, embedding) if config.retrieval.dense_enabled else None
    lexical = LexicalRetriever(catalog) if config.retrieval.lexical_enabled else None
    mentions = (
        MentionExtractor(catalog) if config.retrieval.mention_retrieval_enabled else None
    )
    candidate_generator = CandidateGenerator(
        dense,
        lexical,
        mentions,
        dense_top_k=config.retrieval.dense_top_k,
        lexical_top_k=config.retrieval.lexical_top_k,
        fusion_top_k=config.retrieval.fusion_top_k,
        rrf_k=config.retrieval.rrf_k,
    )

    relationships = RelationshipRegistry.from_yaml(
        config.expansion.relationship_path,
        catalog,
    )
    expander = (
        MetricExpander(
            relationships,
            max_candidates=config.expansion.max_candidates,
            max_hops=config.expansion.max_hops,
        )
        if config.expansion.enabled
        else None
    )
    metadata_ranker = MetadataRanker(catalog) if config.reranking.metadata_enabled else None
    if config.reranking.cross_encoder_enabled and cross_encoder is None:
        raise ConfigurationError("cross_encoder_enabled requires an injected CrossEncoder")
    reranker = CandidateReranker(
        documents,
        metadata_ranker,
        cross_encoder if config.reranking.cross_encoder_enabled else None,
        final_top_k=config.reranking.final_top_k,
        metadata_weight=config.reranking.metadata_weight,
        cross_encoder_weight=config.reranking.cross_encoder_weight,
    )

    fewshot_selector = None
    example_bank_version = "disabled"
    if config.fewshot.enabled and config.fewshot.strategy != "zero":
        bank = ExampleBank.from_jsonl(config.fewshot.example_bank_path, catalog)
        example_bank_version = bank.version
        policy = AdaptiveFewshotPolicy(
            config.fewshot.min_examples,
            config.fewshot.max_examples,
        )
        fewshot_selector = FewshotSelector(
            bank,
            catalog,
            relationships,
            policy,
            strategy=config.fewshot.strategy,
            initial_pool_size=config.fewshot.initial_pool_size,
            alpha=config.fewshot.alpha,
            beta=config.fewshot.beta,
            gamma=config.fewshot.gamma,
            delta=config.fewshot.delta,
        )

    if llm_provider is None:
        if config.llm.provider != "ollama":
            raise ConfigurationError("The mock provider must be explicitly injected")
        llm_provider = OllamaLLMProvider(
            config.llm.base_url,
            config.llm.model,
            temperature=config.llm.temperature,
            timeout_s=config.llm.timeout_s,
            max_retries=config.llm.max_retries,
        )
    validator = SelectionValidator(catalog)
    prompt_builder = PromptBuilder(documents, config.prompt_version)
    llm_selector = LLMMetricSelector(
        llm_provider,
        prompt_builder,
        validator,
        max_validation_retries=config.llm.max_retries,
    )
    return MetricSelectionPipeline(
        catalog,
        documents,
        candidate_generator,
        reranker,
        llm_selector,
        expander=expander,
        fewshot_selector=fewshot_selector,
        versions={
            "config": config.version,
            "config_fingerprint": config_fingerprint(config),
            "catalog": catalog.version,
            "documents": documents.version,
            "embedding": embedding.model_id,
            "relationships": relationships.version,
            "example_bank": example_bank_version,
            "prompt": config.prompt_version,
        },
    )
