# UP-07b — Avoid asking for a period on unsupported comparisons

The reported Vietnamese question used “so với quý 2”. The comparison detector
missed that phrase, and the single-period parser treated the abbreviated
quarter as incomplete. Two regression variants returned
`needs_clarification` before the change, including the form with both years.

The planner now detects that comparison before deciding to ask for missing
slots. The governed demo returns HTTP 422 and `unsupported_comparison` with
Vietnamese guidance. The regression covers the exact wording routed through
the demo endpoint with the local mock selector. A grouped monthly series and
the catalog's budget-versus-actual query also have planner coverage.

## Verification

- Reproduction with `python -m pytest -o addopts='' -q tests/contracts/test_planner_time_regressions.py -k 'unsupported_comparison or budget_vs_actual'` exited 1 before the fix with two failures and two passes.
- `python -m pytest -o addopts='' -q tests/contracts/test_planner_time_regressions.py` exited 0 with 49 passes.
- `python -m pytest -o addopts='' -q tests/contracts/test_governed_demo_api.py -k 'unsupported_period_comparison or guided_clarification_continues_original_question'` exited 0 with two passes.
- `make test-planning test-security typecheck` exited 0.
- `make format-check lint CHECK_PATHS='agent4/planning/planner.py agent4/planning/validator.py agent4/planning/clarification.py agent4/pipeline.py tests/contracts/test_planner_time_regressions.py tests/contracts/test_governed_demo_api.py'` exited 0 after formatting the new error message. `git diff --check` exited 0.

## Component evaluation

```bash
make eval ADAPTER=agent4.planning.eval_adapter:predict_validated MODEL_VERSION=none PROMPT_VERSION=none OUTPUT_DIR=reports/eval/UP-07b_comparison_before EVAL_EXTRA='--category timeseries_and_comparison --category ambiguous_needs_clarification'
make eval ADAPTER=agent4.planning.eval_adapter:predict_validated MODEL_VERSION=none PROMPT_VERSION=none OUTPUT_DIR=reports/eval/UP-07b_comparison_after BASELINE=reports/eval/UP-07b_comparison_before/summary.json EVAL_EXTRA='--category timeseries_and_comparison --category ambiguous_needs_clarification'
```

Both commands exited 0. The 35 dev cases had the same per-case checks before
and after, with 33/35 exact plans and final statuses. BM-023 retained the
monthly series. BM-026 still misses its expected status in the component
selection stage, and BM-037 still requires actual period comparison support.
Adapter P50/P95 were 1.00/2.47 ms before and 1.00/1.73 ms after. The evaluation
uses an offline selector and measures neither SQL results nor model cost.
The exact reported wording is covered by the separate regression test.
The running Kaggle instance requires the updated files and a server restart
before it can exercise the new response.
