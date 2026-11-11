"""Compare cold and warm production metric selection in one process."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from agent4.metric_selection.config import load_config
from vals.run_eval import main as evaluate
from vals.run_eval import read_jsonl

_MEASUREMENTS = {"latency_ms", "stage_latency_ms", "usage"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model-version", required=True)
    args = parser.parse_args()
    config = load_config(args.config)
    if config.llm.provider != "ollama" or not config.cache_enabled:
        parser.error("Choose a real Ollama preset with cache enabled.")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    os.environ["AGENT4_METRIC_SELECTION_CONFIG"] = str(args.config)
    common = [
        "--mode",
        "selection",
        "--split",
        "dev",
        "--adapter",
        "agent4.metric_selection.eval_adapter:predict_e5",
        "--config",
        str(args.config),
        "--model-version",
        args.model_version,
        "--prompt-version",
        config.prompt_version,
        "--ks",
        "5",
        "10",
        "12",
        "15",
    ]
    cold = args.output_dir / "cold"
    warm = args.output_dir / "warm"
    cold_exit = evaluate([*common, "--output-dir", str(cold)])
    if not (cold / "predictions.jsonl").is_file():
        return cold_exit
    warm_exit = evaluate(
        [
            *common,
            "--output-dir",
            str(warm),
            "--baseline",
            str(cold / "summary.json"),
        ]
    )
    if not (warm / "predictions.jsonl").is_file():
        return warm_exit
    cold_predictions = {p["id"]: p for p in read_jsonl(cold / "predictions.jsonl")}
    warm_predictions = {p["id"]: p for p in read_jsonl(warm / "predictions.jsonl")}
    diffs = sorted(
        case_id
        for case_id in cold_predictions.keys() | warm_predictions.keys()
        if _prediction_fields(cold_predictions.get(case_id, {}))
        != _prediction_fields(warm_predictions.get(case_id, {}))
    )
    warm_hits = [
        case_id
        for case_id, prediction in warm_predictions.items()
        if prediction["usage"] == {"input_tokens": 0, "output_tokens": 0}
        and (cold_predictions.get(case_id, {}).get("usage") or {}).get("output_tokens", 0) > 0
    ]
    report = {
        "cold_exit": cold_exit,
        "warm_exit": warm_exit,
        "cold_count": len(cold_predictions),
        "warm_count": len(warm_predictions),
        "different_case_ids": diffs,
        "observed_selection_hit_ids": warm_hits,
    }
    (args.output_dir / "comparison.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return int(bool(cold_exit or warm_exit or diffs or not warm_hits))


def _prediction_fields(prediction: dict) -> dict:
    return {key: value for key, value in prediction.items() if key not in _MEASUREMENTS}


if __name__ == "__main__":
    raise SystemExit(main())
