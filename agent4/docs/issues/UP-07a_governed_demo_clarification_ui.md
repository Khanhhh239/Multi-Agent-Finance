# Issue UP-07a — Continue Guided Clarification from the Demo UI

- **Status:** Verified
- **Module:** Governed demo client
- **Depends on:** M2.3 guided clarification contract
- **Contract:** `query.clarification.v1`

## Problem

The demo displayed three fixed reporting periods for every clarification. A
button appended its label to the original question and sent a new query without
the active `session_id`. That bypassed the backend's continuation path and
could repeat a confirmed choice or discard preserved interpretation.

## Objective

Render the first pending slot and its authorized choices from the API response.
Send a selected `choice.value` with the session ID so the existing validated
clarification session continues. Keep free-text replies and a clear way to
abandon a session and start a new question.

## Acceptance criteria

- Initial demo requests opt into guided clarification.
- The UI shows only the first server-provided pending slot and its choices.
- A choice sends its canonical value with the returned session ID; it does not
  mutate and resubmit the original question.
- A subsequent clarification renders the next pending slot while preserving
  the original question, locale, and current persona.
- Free-text answers continue the active session. Persona changes and example
  questions start a fresh request; the user can explicitly abandon a session.
- A regression case selects a metric, receives only the remaining time slot,
  and confirms the selected metric and HCM filter remain in the plan.

## Verification

Evidence is recorded in [UP-07a verification](../../reports/issues/UP-07a_verification.md).
The UI interaction smoke uses the embedded page script with deterministic API
responses; the API regression separately exercises the real guided session and
validated planner. The 15-case clarification development evaluation is
unchanged from its compatible baseline.
