# UP-07c verification — Clarification turn isolation

**Status:** Verified for the governed demo. No deployment performed.

## Change and hypothesis

The main question form and clarification reply both used the same textbox. A
new question submitted during an active session could be sent with the old
session ID. If the pending slot was `filters`, the resolver assigned that full
question string to `draft.filters`; plan validation then failed with HTTP 500.

The demo now has separate paths. Submitting the main query always starts a new
guided request without `session_id`. Choice buttons and the dedicated free-text
form continue the active session. The main button changes to “Hỏi câu mới”
while clarification is pending. If a supported continuation fails, the server
prompt and reply controls stay visible while the main field remains available
for a new question. Filter clarifications with no authorized choices show
guidance to start a new query with an explicit value and do not offer a reply
box the API cannot process. The API rejects answers for slots without a
supported resolver at the clarification boundary with HTTP 400, before plan
validation.

## Verification results

| Check | Command | Result |
|---|---|---|
| Invalid filter answer through API | `python -m pytest -q tests/contracts/test_governed_demo_api.py -k invalid_filter_clarification_answer` | Exit 0; 1 passed. The answer reached the clarification boundary, returned `400 invalid_request`, and produced no SQL evidence. |
| Existing multi-turn API contract | `python -m pytest -q tests/contracts/test_governed_demo_api.py -k guided_clarification_continues_original_question` | Exit 0; 1 passed. Metric selection and the HCM filter remained in the session while the next slot was time. |
| UI contract | `python -m pytest -q tests/contracts/test_governed_demo_ui.py` | Exit 0; 1 passed. |
| Embedded JavaScript syntax | `node --check /tmp/agent4-demo-ui-check.js` | Exit 0. The file was extracted from the current `demo_page()` response. |
| Client interaction smoke | `node reports/issues/UP-07c_clarification_ui_smoke.js /tmp/agent4-demo-ui-check.js` | Exit 0; verified canonical continuation, a new request without the stale session ID, retry after a 400, and successful continuation afterward. |
| Planning contracts | `make test-planning` | Exit 0; 116 passed. |
| Security contracts | `make test-security` | Exit 0; 12 passed. |
| Formatting | `make format-check CHECK_PATHS='agent4/demo_ui.py agent4/planning/clarification.py tests/contracts/test_governed_demo_ui.py tests/contracts/test_governed_demo_api.py'` | Exit 0; all 4 files formatted. |
| Lint | `make lint CHECK_PATHS='agent4/demo_ui.py agent4/planning/clarification.py tests/contracts/test_governed_demo_ui.py tests/contracts/test_governed_demo_api.py'` | Exit 0. |
| Compile check | `make typecheck` | Exit 0. |
| Whitespace check | `git diff --check` | Exit 0. |

## Clarification development evaluation

Command:

```sh
make eval ADAPTER=agent4.planning.eval_adapter:predict MODEL_VERSION=none PROMPT_VERSION=none OUTPUT_DIR=reports/eval/UP-07c_clarification_final BASELINE=reports/eval/M2.2_clarification_final/summary.json EVAL_EXTRA='--category ambiguous_needs_clarification'
```

The runner evaluated 15 `ambiguous_needs_clarification` dev cases using the
actual planner and validator adapter, with `config/selection.yaml`, split
`dev`, model and prompt versions `none`, and baseline
`reports/eval/M2.2_clarification_final/summary.json`.

| Metric | Baseline | After |
|---|---:|---:|
| Exact selection | 15/15 | 15/15 |
| Exact plan | 15/15 | 15/15 |
| Status accuracy | 15/15 | 15/15 |
| Failures | 0 | 0 |
| P50 latency | 0.899 ms | 0.909 ms |
| P95 latency | 5.487 ms | 5.617 ms |

The evaluator made no model or SQL calls, and recorded no answer reviews. Its
latency is a small deterministic component measurement. It does not measure
session handling; the API regression and Node client smoke above cover the
changed continuation behavior directly.

## Attempts and limitations

- A broader initial pytest selection included a synchronous `TestClient` case
  that stalled in this environment. It was interrupted. The new API regression
  uses `httpx.ASGITransport` and passed independently.
- The first format check identified one quote-style issue in the UI contract
  test. `make format` corrected it; the final format check passed.
- A repeated evaluation command first returned exit 2 because its output
  directory already existed. It was rerun to a fresh output directory and
  passed as recorded above. An earlier run to that directory also completed
  with the same 15/15 scores.
- The API does not parse natural-language answers to an unresolved filter
  slot. The demo directs users to restate the query with an explicit filter,
  and the API rejects unsupported answers safely. A filter parser or
  authorized filter-choice list remains a separate planner feature.
- Client behavior was exercised with Node and a deterministic fake DOM/API.
  Live browser rendering and the Kaggle deployment were not run in this issue.

## Review

The new server behavior does not alter session ownership, tenant/user scope,
policy and catalog revalidation, expiry, or the three-turn limit. The API
contract change is documented in `contracts.md`. Rebuild or re-upload the
current repository artifact and restart the Kaggle demo before retesting.
