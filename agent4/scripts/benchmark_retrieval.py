import argparse
import json
from pathlib import Path

from agent4.metric_selection.evaluation import evaluate_retrieval, load_evaluation_cases
from agent4.metric_selection.factory import build_pipeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", nargs="?", default="data/eval/test.jsonl")
    parser.add_argument("--output")
    args = parser.parse_args()
    pipeline = build_pipeline()
    cases = load_evaluation_cases(args.dataset, pipeline.catalog)

    def dense(question):
        return pipeline.candidate_generator.dense.retrieve(question, 20)

    def lexical(question):
        return pipeline.candidate_generator.lexical.retrieve(question, 20)

    def hybrid(question):
        return pipeline.candidate_generator.retrieve(question).fused

    def expanded(question):
        initial = pipeline.candidate_generator.retrieve(question).fused
        return pipeline.expander.expand(question, initial) if pipeline.expander else initial

    def reranked(question):
        candidates = expanded(question)
        return pipeline.reranker.rerank(question, candidates)

    variants = {
        "dense": dense,
        "lexical": lexical,
        "hybrid": hybrid,
        "hybrid_expansion": expanded,
        "hybrid_expansion_reranking": reranked,
    }
    summaries = {
        name: evaluate_retrieval(cases, retrieve).model_dump(mode="json")
        for name, retrieve in variants.items()
    }
    payload = json.dumps(summaries, ensure_ascii=False, indent=2)
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
