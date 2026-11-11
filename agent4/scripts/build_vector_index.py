"""Build and verify the dense index used by the governed pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agent4.core.catalog import MetricCatalog
from agent4.core.errors import ContractError
from agent4.metric_selection.config import load_config
from agent4.metric_selection.embedding import EmbeddingProvider
from agent4.metric_selection.errors import ConfigurationError
from agent4.metric_selection.index import build_index, load_index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="Metric-selection YAML preset")
    args = parser.parse_args()

    try:
        provider = EmbeddingProvider(load_config(args.config).embedding)
        catalog = MetricCatalog(canonical=True)
        path = provider.config.cache_path
        if not provider.normalize:
            parser.error("Dense retrieval requires normalized embeddings.")
        build_index(catalog, provider, path)
        index = load_index(
            path,
            catalog_hash=catalog.get_catalog_hash(),
            embedding_provider=provider,
            cache_enabled=False,
        )
    except (ConfigurationError, ContractError, OSError) as exc:
        print(f"Index build failed: {exc}", file=sys.stderr)
        return 1

    print(f"Verified {len(index.metric_ids)} vectors × {provider.dimension} in {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
