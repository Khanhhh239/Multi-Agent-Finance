import argparse
import asyncio
import json

from agent4.metric_selection.config import load_config
from agent4.metric_selection.evaluation import evaluate_pipeline, load_evaluation_cases
from agent4.metric_selection.factory import build_pipeline
from agent4.metric_selection.reranking import CandidateReranker
from agent4.metric_selection.retrieval import FullCatalogCandidateGenerator


async def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", nargs="?", default="data/eval/test.jsonl")
    args = parser.parse_args()
    base = load_config()
    variants = {
        "dense": {
            "retrieval": {"dense_enabled": True, "lexical_enabled": False},
            "expansion": False,
            "metadata": False,
            "fewshot": "zero",
        },
        "hybrid": {
            "retrieval": {"dense_enabled": True, "lexical_enabled": True},
            "expansion": False,
            "metadata": False,
            "fewshot": "zero",
        },
        "hybrid_expansion": {
            "retrieval": {"dense_enabled": True, "lexical_enabled": True},
            "expansion": True,
            "metadata": False,
            "fewshot": "zero",
        },
        "hybrid_expansion_reranking": {
            "retrieval": {"dense_enabled": True, "lexical_enabled": True},
            "expansion": True,
            "metadata": True,
            "fewshot": "zero",
        },
        "full_pipeline_adaptive": {
            "retrieval": {"dense_enabled": True, "lexical_enabled": True},
            "expansion": True,
            "metadata": True,
            "fewshot": "adaptive",
        },
    }
    summaries = {}
    for name, options in variants.items():
        retrieval = base.retrieval.model_copy(update=options["retrieval"])
        expansion = base.expansion.model_copy(update={"enabled": options["expansion"]})
        reranking = base.reranking.model_copy(update={"metadata_enabled": options["metadata"]})
        fewshot = base.fewshot.model_copy(update={"strategy": options["fewshot"]})
        config = base.model_copy(
            update={
                "retrieval": retrieval,
                "expansion": expansion,
                "reranking": reranking,
                "fewshot": fewshot,
            }
        )
        pipeline = build_pipeline(config)
        cases = load_evaluation_cases(args.dataset, pipeline.catalog)
        summaries[name] = (
            await evaluate_pipeline(cases, pipeline)
        ).model_dump(mode="json")

    full_catalog_pipeline = build_pipeline(
        base.model_copy(
            update={
                "expansion": base.expansion.model_copy(update={"enabled": False}),
                "fewshot": base.fewshot.model_copy(update={"strategy": "zero"}),
            }
        )
    )
    full_catalog_pipeline.candidate_generator = FullCatalogCandidateGenerator(
        full_catalog_pipeline.catalog
    )
    full_catalog_pipeline.reranker = CandidateReranker(
        full_catalog_pipeline.documents,
        metadata_ranker=None,
        final_top_k=len(full_catalog_pipeline.catalog),
    )
    cases = load_evaluation_cases(args.dataset, full_catalog_pipeline.catalog)
    summaries["full_catalog"] = (
        await evaluate_pipeline(cases, full_catalog_pipeline)
    ).model_dump(mode="json")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(run())
