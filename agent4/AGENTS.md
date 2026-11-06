# Text-to-SQL Agent — Repository Instructions

## 1. Project Context

This project implements a metric-driven Text-to-SQL system.

Core pipeline:
User Query -> Metric Selection -> Metric Validation
-> SQL Generation -> SQL Execution
-> Answer Generation -> Answer Validation.

Priorities:
1. Correctness and data safety.
2. Reproducible evaluation.
3. Maintainable and testable code.
4. Performance and cost efficiency.

## 2. Repository Navigation

Consult relevant documentation when needed:
- `docs/architecture.md`: system architecture.
- `docs/contracts.md`: module interfaces.
- `docs/metrics.md`: metric definitions.
- `docs/evaluation.md`: benchmark methodology.
- `README.md`: setup and development commands.

Use existing code and tests as the source of truth
when documentation is missing or outdated.
Report material inconsistencies.

## 3. Engineering Principles

- Keep changes focused on the requested task.
- Prefer simple solutions over unnecessary abstractions.
- Preserve existing interfaces unless change is required.
- Validate structured data at module boundaries.
- Separate LLM logic, business rules and database access.
- Do not silently swallow errors.
- Do not introduce unrelated refactoring.
- Update affected contracts when behavior changes.

## 4. Text-to-SQL Invariants

- Metric IDs must exist in the metric catalog.
- Validate metric, dimension and filter compatibility.
- Never execute unvalidated model-generated SQL.
- Database access must be read-only and least-privileged.
- Enforce query timeouts and resource limits.
- Never expose credentials or unauthorized data.
- Do not fabricate metric values or query results.
- Surface ambiguity rather than guessing silently.

## 5. Codex Issue Execution Loop

Use `.agents/skills/issue-loop/SKILL.md` for every implementation Issue.
Work on one Issue at a time and complete the entire loop.
Do not stop after code generation.

### 5.1 Understand

1. Read the Issue specification, contracts and acceptance criteria.
2. Inspect relevant architecture, implementation and tests.
3. Identify dependencies, affected files, risks and trust boundaries.
4. Discover the real verification and evaluation programs available in the repository.
5. Record assumptions when requirements are ambiguous.

Escalate only decisions that materially affect contracts, security,
data integrity, architecture or product behavior.

### 5.2 Implement

1. Make the smallest coherent implementation.
2. Add or update production-facing tests.
3. Preserve existing interfaces unless the Issue authorizes a change.
4. Avoid unrelated refactoring and speculative features.

### 5.3 Verify

Run all checks applicable to the Issue:

- formatting and lint;
- type checks;
- unit tests;
- integration and contract tests;
- security and regression tests.

When verification fails:

1. Diagnose the root cause.
2. Fix the problem within Issue scope.
3. Add regression coverage when appropriate.
4. Rerun the affected checks.

Do not continue to evaluation while required verification is failing.
Never remove, skip or weaken tests to obtain a pass.

### 5.4 Evaluate

When the Issue affects AI quality or system behavior:

1. Run the real development evaluation or benchmark program.
2. Evaluate the actual implementation, not a reference or golden-output mock.
3. Compare against a compatible recorded baseline and acceptance thresholds.
4. Analyze case-level failures, not only aggregate scores.
5. Record quality, latency, cost and measurement coverage when available.
6. Preserve datasets, ground truth, seeds and evaluation settings.

A dry-run, schema validation, command wrapper, or written instruction to
"run the benchmark" is not evaluation evidence.

If evaluation is required but no executable evaluator exists, implement the
smallest legitimate evaluator within Issue scope or report the missing
capability as a blocker. Never fabricate evaluation results.

### 5.5 Analyze and Fix

If acceptance criteria are not met:

1. Identify the highest-impact failure.
2. Determine its root cause from evidence.
3. Form one specific improvement hypothesis.
4. Implement one targeted fix.
5. Rerun verification and evaluation.
6. Compare the new result with the previous attempt.

Limit the improvement loop to three attempts per Issue unless the Issue
defines another budget.

Stop and report evidence when:

- progress stalls after the attempt budget;
- required access, infrastructure or evaluation budget is unavailable;
- continuing requires a product, contract, security or architecture decision.

### 5.6 Issue Verified

Mark an Issue verified only after:

- every acceptance criterion has evidence;
- required verification checks pass;
- required evaluation gates pass without unacceptable regression;
- the final diff has no accidental or out-of-scope changes;
- a concise evidence report is saved.

For every attempt, record the hypothesis, exact commands, exit status,
observed results, benchmark configuration, baseline identity, before/after
metrics, important failed cases and remaining limitations.

Missing or null measurements are unverified, not passing.

## 6. Implementation Workflow

For each task:
1. Inspect relevant code, contracts and existing tests.
2. Identify the expected behavior and affected modules.
3. Make a short plan for non-trivial changes.
4. Implement the smallest coherent change.
5. Add or update relevant tests.
6. Run appropriate verification.
7. Fix failures caused by the change and recheck.
8. Summarize results and remaining risks.

For bug fixes, reproduce the bug with a regression
test when practical.

Continue through verification without requesting
approval for routine local, non-destructive actions.

## 7. Testing and Evaluation

Use the repository Makefile as the canonical command layer for deterministic
checks. Run `make help` to list available targets. The Makefile does not execute
the Issue loop; Codex still owns implementation, failure analysis and fixes.
During an Issue, prefer focused static checks with `CHECK_PATHS`, then run the
broader module or full gate required by its acceptance criteria.

Choose checks proportional to the change:

- Small code change: relevant unit tests and lint.
- Interface change: contract and integration tests.
- LLM/retrieval change: affected tests and dev evals.
- SQL change: integration, execution and safety tests.
- Release candidate: full regression and evaluation.

For evaluation:
- Compare against a recorded baseline.
- Keep dataset and evaluation settings comparable.
- Track accuracy, failures, latency and cost.
- Record model, prompt, config and dataset versions.
- Analyze failure cases, not just aggregate scores.
- Never modify ground-truth labels to improve scores.
- Never tune on the held-out test set.
- Report regressions and unverified assumptions.

Use commands documented by the repository.
Never claim a test or benchmark passed unless run.

## 8. Review and Completion

Before marking a task complete:
- Inspect the diff for unrelated changes.
- Check for correctness, security and regressions.
- Verify acceptance criteria.
- Identify high-risk changes requiring human review.

Final report:
1. Summary of changes.
2. Changed components and their responsibilities.
3. Tests run and observed results.
4. Benchmark comparison, if applicable.
5. Known issues and remaining risks.
6. Areas requiring human review.

Do not dump every changed file into the report.

## 9. Approval Boundaries

Request approval before:
- Changing production database schemas or data.
- Deploying or performing external write operations.
- Changing security or authorization policies.
- Introducing major architectural changes.
- Merging or pushing changes unless authorized.

Never modify secrets or production credentials.

If blocked, explain the blocker and provide the
best verified partial result.

## 10. Definition of Done

A task is complete when:
- Requested behavior is implemented.
- Relevant tests pass.
- Required evaluation is completed or clearly blocked.
- No unacceptable regression is identified.
- Changes and risks are documented for review.
