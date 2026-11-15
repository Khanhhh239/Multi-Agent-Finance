# Vietnamese VND answer formatting

The governed answer now groups Vietnamese VND amounts by billions, millions,
thousands and đồng. It preserves the exact amount, including negative values
and nonzero decimal digits. Preview tables and citations retain the warehouse
decimal string. A regression test uses `1010000001.00` and checks for
`1 tỉ 10 triệu lẻ 1 đồng` in both the summary and its verified claim.

## Checks

- Before implementation, the focused currency regression command below exited
  1 with six Vietnamese cases failing and the English case passing.
  `python -m pytest -q tests/contracts/test_evidence_preview.py -k currency_answer`
- `timeout 22s make test-answer` exited 124 in the sandbox at the API cases.
  The rerun `timeout 45s make test-answer` outside the sandbox exited 0 with
  31 passed.
- `python -m pytest -o addopts='' -q tests/contracts/test_result_answer_response.py tests/contracts/test_evidence_preview.py tests/security` exited 0 with 34 passed, including 12 security cases.
- `make typecheck` and `make format-check lint CHECK_PATHS='agent4/answer/generator.py tests/contracts/test_evidence_preview.py'` exited 0.
- `git diff --check` exited 0.

## Development comparison

Ran `make eval` twice outside the sandbox. Both runs used the production
adapter `agent4.eval_adapter:predict`, `data/eval/contract_benchmark_questions.jsonl`
at SHA-256 `094fb090bff62ee8c83045eed3780c371ec3f4cf38095f274237c02a6b5b88d5`,
dev category `single_metric_aggregate`, seed `20261101`, the synthetic
`data/cfo_warehouse.duckdb`, tenant `minh-phat`, and mock metric selection.
The baseline used the Python package archived from `53ce9286` and the second
run used the modified workspace. Both runs used the following arguments, with
`OUTPUT_DIR=/tmp/agent4-vnd-format-before` for baseline and
`OUTPUT_DIR=/tmp/agent4-vnd-format-after` plus
`BASELINE=/tmp/agent4-vnd-format-before/summary.json` for the second run.

```sh
AGENT4_WAREHOUSE_TENANT_ID=minh-phat AGENT4_DB_PATH=data/cfo_warehouse.duckdb \
AGENT4_METRIC_SELECTION_CONFIG=config/eval_governed_lexical.yaml AGENT4_LLM_PROVIDER=mock \
make eval PYTHON='python -P' ADAPTER=agent4.eval_adapter:predict \
  MODEL_VERSION=mock PROMPT_VERSION=metric-selection-v1-structured \
  EVAL_CONFIG=config/eval_governed_lexical.yaml \
  OUTPUT_DIR=/tmp/agent4-vnd-format-after BASELINE=/tmp/agent4-vnd-format-before/summary.json \
  EVAL_EXTRA='--category single_metric_aggregate'
```

For the baseline, `PYTHONPATH` put the archived package directory before the
workspace. For the second run, `PYTHONPATH` contained the workspace only. Both
commands exited 0. Metric selection, exact plan, and final status scored
20/20 in both runs. All 20 cases completed SQL, with identical result payloads,
execution metadata and warnings before and after. The rendered answer changed
in 12 cases. BM-001 now reads `1.062 tỉ 108 triệu 877 nghìn 222 đồng` for
`1062108877222.00 VND`. P50/P95 were 101.39/280.25 ms before and 95.20/286.79 ms
after. There were zero model usage samples and zero independent answer reviews.
These measurements cover the answer format, with model quality outside the
scope of this change.
