# Evaluation report

The repository's existing retrieval evaluation contains 12 test, 4 dev and 3
train cases plus 15 few-shot examples. These are small engineering seeds, not
the 300–500 expert-reviewed sealed benchmark proposed by the pack.

`scripts/benchmark_retrieval.py` evaluates dense, lexical, hybrid,
hybrid+expansion and hybrid+expansion+reranking with candidate recall metrics.
The external-LLM E0/E1/E2/E6 plan ablation is BLOCKED because no approved
provider/model/credentials were supplied. The deterministic offline selector
is for reproducible demo and negative/security behavior; it is not represented
as an LLM accuracy result.

Raw outputs are saved under `reports/eval/` by the final verification run.
Claims must include dataset size and mode.

Observed seed result (`reports/eval/retrieval_metrics.json`): 11 supported
queries were eligible. Dense, lexical and hybrid each reached Recall@5 = 1.0,
All-Gold-Covered@5 = 1.0 and MRR = 1.0. Hybrid+expansion retained coverage.
Hybrid+expansion+metadata-reranking retained Recall@5 = 1.0 but reduced MRR to
0.893939. On this tiny seed there is no evidence that the more complex reranker
improves ranking; it should not be selected on that claim.
