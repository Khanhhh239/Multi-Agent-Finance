
---
name: issue-loop
description: Execute a software engineering issue through implementation, testing, debugging, evaluation, and review preparation.
---

# Issue Execution Loop

## Objective

Complete one Issue according to its requirements,
contracts, acceptance criteria, and evaluation protocol.

Do not stop after code generation.

## 1. Understand

- Read AGENTS.md and the Issue specification.
- Inspect relevant architecture and contracts.
- Inspect existing implementation and tests.
- Identify dependencies, affected files and risks.
- Identify available verification commands.

If requirements are ambiguous, document assumptions.
Escalate only decisions that materially affect
contracts, security, or product behavior.

## 2. Implement

- Make the smallest coherent implementation.
- Add or update relevant tests.
- Avoid unrelated changes and unnecessary refactoring.
- Preserve existing interfaces unless authorized.

## 3. Verify

Run applicable:
- Lint and type checks.
- Unit tests.
- Integration tests.
- Contract and security tests.

When a test fails:
1. Diagnose the root cause.
2. Fix the problem within Issue scope.
3. Add regression coverage when appropriate.
4. Rerun affected checks.

Do not remove or weaken tests to make them pass.

## 4. Evaluate

If the change affects AI quality or system behavior:

- Run the applicable development benchmark.
- Compare against the recorded baseline.
- Analyze failed cases.
- Record quality, latency and cost.
- Preserve dataset and ground-truth integrity.

If the baseline is missing, establish one first.

## 5. Improvement Loop

If acceptance criteria are not met:
1. Identify the highest-impact failure.
2. Form a specific improvement hypothesis.
3. Implement a targeted change.
4. Rerun verification and evaluation.
5. Compare with previous results.

Limit improvement attempts to 3 per Issue
unless its specification defines another budget.

Stop if:
- Progress stalls after the attempt budget.
- Safety or access permissions are insufficient.
- The change requires an architectural decision.
- Evaluation resources or budget are exhausted.

Never claim success without evidence.

## 6. Completion

Before marking an Issue verified:

- Confirm all acceptance criteria.
- Inspect the final diff.
- Check for regressions and out-of-scope edits.
- Save a concise verification report.
- Record remaining risks and limitations.

Report:
- Changes made.
- Tests executed and results.
- Evaluation before/after, if applicable.
- Known failures.
- Files requiring human review.

Do not merge, deploy, or perform destructive
operations without explicit authorization.
