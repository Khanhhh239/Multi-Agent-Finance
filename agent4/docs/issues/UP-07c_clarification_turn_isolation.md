# Issue UP-07c — Isolate New Queries from Clarification Replies

- **Status:** Verified
- **Module:** Governed demo UI and clarification API
- **Depends on:** UP-07a guided clarification UI, `query.clarification.v1`

## Problem

The demo reused its main question field for clarification replies. While a
session was active, submitting an unrelated question attached the old session
ID and treated the whole question as the answer to the next pending slot. For
an unresolved filter slot this could put a string in `draft.filters`, which
failed plan validation as an HTTP 500.

## Objective

Make a main-form submission start a fresh query and provide a separate,
session-bound form for clarification replies. Reject clarification values for
slots that do not have a supported resolver before they reach plan validation.

## Scope assumptions

- Keep the existing session ownership, expiry, turn limit, authorization, and
  catalog checks.
- Do not add a new natural-language filter parser in this issue.
- An unsupported clarification answer returns the existing safe 400
  `invalid_request` clarification error. For filter slots with no resolver the
  UI explains the limitation and points to a fresh, explicit query.
- Preserve the existing API request shape and `query.clarification.v1`.

## Acceptance criteria

- Submitting the main query form never includes an active clarification
  `session_id`.
- Canonical choices and free-text clarification replies use a separate form
  and continue with the active session ID.
- A clarification error for a supported slot keeps its prompt and reply
  controls available; it does not turn the main question field into a
  clarification field.
- Answers for unresolved slots without a resolver, including `filters`, fail
  at the clarification boundary with HTTP 400 and do not reach plan validation
  or SQL execution.
- API and embedded-client regressions cover stale-session isolation,
  clarification retry controls, and invalid filter answers.
- Focused checks and the compatible clarification development evaluation are
  recorded in a verification report.

## Verification

Evidence is recorded in
[`UP-07c verification`](../../reports/issues/UP-07c_clarification_turn_isolation.md).
