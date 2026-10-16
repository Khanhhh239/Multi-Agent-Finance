"""Development-only BM25 smoke recall and per-question latency benchmark."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from time import perf_counter

from agent4.agent.retriever import MetricRetriever

NOTICE = "công thức chưa được kế toán duyệt (G0.7 mở)"
DEFAULT_DATA = Path(__file__).resolve().parents[1] / "tests/data/retriever_smoke.jsonl"


def benchmark(path=DEFAULT_DATA, *, k=8, repeats=3):
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows or repeats < 1 or k < 1:
        raise ValueError("Cần dữ liệu và số lần lặp/k dương")
    start = perf_counter()
    retriever = MetricRetriever()
    initialization_ms = (perf_counter() - start) * 1000
    latencies, misses, hits = [], [], 0
    for row in rows:
        cands = []
        for _ in range(repeats):
            start = perf_counter()
            cands = retriever.topk(row["question"], k=k, hints=row.get("hints"))
            latencies.append((perf_counter() - start) * 1000)
        gold = row["gold"]
        gold = [gold] if isinstance(gold, str) else gold
        correct = set(gold).issubset(c.metric for c in cands)
        hits += int(correct)
        if not correct:
            misses.append({"question": row["question"], "gold": gold,
                           "retrieved": [c.metric for c in cands]})
    ordered = sorted(latencies)
    return {
        "notice": NOTICE, "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": str(Path(path).resolve()), "dataset_role": "handwritten development smoke (used for tuning; not held out)",
        "method": "BM25 with registry phrase and capability boosts; embeddings not implemented",
        "questions": len(rows), "unique_gold_metrics": len({g for r in rows for g in ([r['gold']] if isinstance(r['gold'], str) else r['gold'])}),
        "k": k, "hits": hits, "recall_at_k": hits / len(rows), "repeats": repeats,
        "initialization_ms": initialization_ms,
        "latency_ms": {"mean": mean(latencies), "p95": ordered[min(len(ordered)-1, int(len(ordered)*.95))], "max": max(latencies)},
        "acceptance": {"recall_at_least_0_99": hits / len(rows) >= .99,
                       "every_query_under_30_ms": max(latencies) < 30},
        "misses": misses,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--k", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    result = benchmark(args.data, k=args.k, repeats=args.repeats)
    report = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
