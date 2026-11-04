import argparse
import asyncio
import json

from agent4.metric_selection.config import load_config
from agent4.metric_selection.evaluation import evaluate_pipeline, load_evaluation_cases
from agent4.metric_selection.factory import build_pipeline


async def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strategy",
        choices=["all", "zero", "static", "similarity", "coverage", "adaptive"],
        default="all",
    )
    parser.add_argument("--dataset", default="data/eval/dev.jsonl")
    args = parser.parse_args()
    base = load_config()
    strategies = (
        ["zero", "static", "similarity", "coverage", "adaptive"]
        if args.strategy == "all"
        else [args.strategy]
    )
    summaries = {}
    for strategy in strategies:
        config = base.model_copy(
            update={"fewshot": base.fewshot.model_copy(update={"strategy": strategy})}
        )
        pipeline = build_pipeline(config)
        cases = load_evaluation_cases(args.dataset, pipeline.catalog)
        summaries[strategy] = (
            await evaluate_pipeline(cases, pipeline)
        ).model_dump(mode="json")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(run())
