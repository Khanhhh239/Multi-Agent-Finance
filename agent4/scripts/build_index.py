from agent4.metric_selection.catalog import MetricCatalogAdapter, MetricDocumentBuilder
from agent4.metric_selection.catalog.index_builder import MetricIndexBuilder
from agent4.metric_selection.config import load_config
from agent4.metric_selection.retrieval import HashingEmbeddingProvider


def main() -> None:
    config = load_config()
    catalog = MetricCatalogAdapter()
    documents = MetricDocumentBuilder(catalog)
    provider = HashingEmbeddingProvider(config.embedding.dimensions, config.embedding.model)
    builder = MetricIndexBuilder(documents, provider)
    index = builder.build()
    builder.save(index, config.embedding.cache_path)
    print(
        f"Built {len(index.metric_ids)} metrics at {config.embedding.cache_path} "
        f"(catalog={index.catalog_version}, embedding={index.embedding_model})"
    )


if __name__ == "__main__":
    main()
