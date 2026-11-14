# UP-07a verification

**Date:** 2026-11-14 · **Scope:** Governed demo UI guided clarification

## Hypothesis and change

The repeated clarification came from the demo client resubmitting a modified
copy of the original question without `session_id`, while showing fixed period
buttons unrelated to the server's pending slot. The client now opts into guided
clarification, renders the first `slot_prompts` entry and its authorized
choices, sends `choice.value` with the active session, supports free-text
replies, and lets the user abandon the session. Persona changes and example
questions clear the local session state.

No planner, catalog, SQL, authorization, or API contract behavior changed.

## Verification

| Check | Command | Result |
|---|---|---|
| UI contract and session regressions | `python -m pytest -q tests/contracts/test_governed_demo_ui.py tests/contracts/test_clarification_mode.py` | Exit 0; 9 passed |
| Governed API continuation | `python -m pytest -q tests/contracts/test_governed_demo_api.py -k guided_clarification_continues_original_question` | Exit 0; 1 passed. The test sends a real metric choice with the session ID and confirms the response contains only the time slot, preserving gross profit and HCM. |
| Planning and clarification suite | `make test-planning` | Exit 0; passed |
| Formatting | `make format-check CHECK_PATHS='agent4/demo_ui.py tests/contracts/test_governed_demo_api.py tests/contracts/test_governed_demo_ui.py'` | Exit 0 |
| Lint | `make lint CHECK_PATHS='agent4/demo_ui.py tests/contracts/test_governed_demo_api.py tests/contracts/test_governed_demo_ui.py'` | Exit 0 |
| Embedded JavaScript syntax | `node --check /tmp/agent4-demo-ui-check.js` | Exit 0 |
| UI interaction smoke | `node reports/issues/UP-07a_demo_ui_smoke.js /tmp/agent4-demo-ui-check.js` | Exit 0; exercised guided start, metric click, next-slot rendering, period click, and same-session request payloads using deterministic API responses. |
| Clarification dev evaluation | `make eval ADAPTER=agent4.planning.eval_adapter:predict_validated MODEL_VERSION=none PROMPT_VERSION=none OUTPUT_DIR=reports/eval/UP-07a_clarification BASELINE=reports/eval/M2.2_clarification_final/summary.json EVAL_EXTRA='--category ambiguous_needs_clarification'` | Exit 0; 15/15 selection, plan, and status matches; zero failures. |
| Diff whitespace | `git diff --check` | Exit 0 |

The clarification evaluation's compatible baseline was `M2.2_clarification_final`.
Selection, exact plan, and status accuracy stayed at 15/15. P50 moved from
0.899 ms to 1.028 ms and P95 from 5.487 ms to 6.268 ms; this deterministic
component evaluation makes zero model calls and does not measure the UI itself.

## Attempts and limitations

- The first API regression probe used Starlette `TestClient`, which blocked in
  `TestClient.__enter__` in this environment. A bare FastAPI `TestClient` smoke
  also timed out after 8 seconds. The regression now uses HTTPX `ASGITransport`
  and passes.
- An exploratory continuation through final SQL execution did not complete
  under the in-process ASGI transport. This issue's tested interaction ends at
  the next clarification. The existing planning suite covers plan validation.
- A live browser server could not be started because `uvicorn` is not installed
  (`python -m uvicorn ...` exited 1 with `No module named uvicorn`). The Node
  smoke runs the actual embedded client JavaScript against deterministic API
  responses. Visual browser rendering remains unverified.
- The first Node smoke harness attempted to spawn Python from Node and hit the
  sandbox's `EPERM` restriction. It now reads the script extracted separately
  by Python and passes without child processes.
- The initial format check found one unformatted test file. `make format` fixed
  it, and the final format check passes.
- The change covers the governed demo at `agent4/demo_ui.py`. The sibling legacy
  portal client is outside this Issue's scope.

## Review

The final diff contains only the governed demo client, its UI/API regression
coverage, this Issue specification, and its evidence. Existing server-side
session ownership and validation remain in force.
