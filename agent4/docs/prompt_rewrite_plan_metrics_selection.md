# TASK: Redesign Metric Selection Module — Architecture, Implementation Plan & Issue Backlog

## 1. Your Role

You are acting as a **Senior AI/ML Engineer, LLM Systems Architect, and Technical Lead**.

Your responsibility is to review the existing Metric Selection module in this repository and redesign its implementation plan, milestones, issues, and tasks.

The project is a financial Text-to-SQL system intended for an AI competition.

Your objective is to maximize:

1. **End-to-end correctness and accuracy**
2. **Metric selection accuracy**
3. **Retrieval recall for multi-metric queries**
4. **Reproducibility and deterministic validation**
5. **Inference efficiency on local hardware**
6. **Modularity, testability, and maintainability**

Follow a **benchmark-driven engineering approach**.

Do not assume that a more complex architecture is automatically better.

The final architecture must be justified by empirical evaluation against simpler baselines.

---

## 2. Mandatory Repository Inspection

Before proposing any changes, inspect the existing repository.

Read the following files if available:

- `AGENTS.md` and any applicable nested agent instructions
- `docs/plans/metrics_selection.md` or the actual location of the existing module plan
- `contracts.md`
- `agent4/engine/metrics.py` or the actual Metric Catalog implementation
- `agent4/metric_selection/`
- Existing metric-related tests under `tests/contracts/`
- Existing evaluation/benchmark documentation
- Existing issue and milestone tracking documents
- Existing model-serving and environment configuration
- Any architecture, scope, dependency, or interface documentation relevant to this module

Discover actual paths rather than assuming the above paths are correct.

Identify existing implementations, tests, contracts, and dependencies before proposing changes.

**Do not overwrite working implementations or established contracts without explaining why.**

### Required repository audit

Report:

1. Existing Metric Selection architecture
2. Existing module structure and implemented components
3. Metric Catalog structure and actual metric count
4. Current LLM and embedding integration
5. Current offline/online retrieval design
6. Existing contracts and tests
7. Missing capabilities and architectural inconsistencies
8. Dependencies on upstream and downstream modules

Pay particular attention to the compatibility between `MetricDef` and the module contracts.

For example, verify whether these fields are supported or require explicit mapping:

- `views` vs `supported_views`
- `group_bys` vs `supported_dimensions`
- `status == approved`
- `verified_handler`
- `metric_id`
- `period_type`

Also verify that example metric IDs match actual catalog IDs.

Distinguish confirmed issues from assumptions.

---

## 3. Target Architecture

Redesign the Metric Selection module around two main operational stages.

### A. Offline Stage — Metric Index Building

Proposed workflow:

```text
Metric Catalog
    |
    v
Catalog Adapter / Governance Metadata
    |
    v
Approved Metric Filtering
    |
    v
Metric Document Builder
    |
    v
Local Embedding Model
    |
    v
Embedding Normalization
    |
    v
Persisted Vector Index + Metadata
```

Requirements:

- Build semantic documents using meaningful fields such as label, description, synonyms, category, unit, and supported dimensions.
- Avoid embedding SQL formulas, physical database schemas, transaction data, or sensitive information.
- Make the embedding provider configurable.
- Prefer `qwen3-embedding:0.6b` through Ollama as the initial model to evaluate, not as an unquestionable final choice.
- Document model ID, version, dimension, normalization, and preprocessing configuration.
- Support local inference without requiring external paid APIs.
- Store vectors using NumPy or a similarly lightweight approach for the initial version.
- Avoid introducing a dedicated vector database without a demonstrated need.
- Support `build_index`, `load_index`, `rebuild_index`, and stale-index detection.
- Use catalog hashes and embedding/index version metadata.
- Ensure index consistency and reproducible builds.
- Clearly distinguish offline index building from online inference.
- Define the error-handling behavior for embedding and index failures.

### B. Online Stage — Metric Selection

Target workflow:

```text
User Question
    |
    v
Query Normalization & Context Extraction
    |
    +----------------------------+
    |                            |
    v                            v
Dense Retrieval             Lexical Retrieval
    |                            |
    +-------------+--------------+
                  |
                  v
             RRF Fusion
                  |
                  v
           Metadata Reranking
                  |
                  v
           MetricCandidateSet
                  |
                  +----------------------+
                  |                      |
                  v                      v
             Candidate Data       Dynamic Few-shot
                  |                      |
                  +-----------+----------+
                              |
                              v
                       LLM Selector
                         Qwen3:4b
                              |
                              v
                      Structured Output
                              |
                              v
                    Deterministic Validator
                              |
                              v
                      ValidatedMetricSet
                              |
                              v
                      Downstream SQL Module
```

Treat this workflow as the proposed architecture, not an implementation mandate.

Evaluate whether every stage provides measurable benefits.

The architecture must preserve strict trust boundaries:

- Retrieval produces candidates, not final authoritative selections.
- Few-shot examples do not extend permissions or candidate sets.
- LLM output is untrusted.
- The LLM must not generate SQL or financial formulas.
- The validator remains the final authority.
- Selected metrics must satisfy all relevant catalog, candidate, authorization, handler, view, dimension, and compatibility constraints.

Preserve upstream/downstream interface compatibility unless an approved contract revision is necessary.

---

## 4. Mandatory Baseline: Full-Catalog LLM Selection

The initial milestone must deliver an operational baseline before implementing sophisticated retrieval.

**Experiment E0 — Full Catalog → Qwen3:4b → Validator**

Input:

- User question
- Authorized, eligible metric catalog entries
- Required business metadata

Output:

- Structured metric selection
- Validated metric IDs
- Explicit clarification or unsupported status when appropriate

The baseline must:

- Use the existing local LLM serving approach where possible.
- Produce schema-constrained output.
- Support multi-metric questions.
- Never generate SQL.
- Include deterministic validation.
- Be executable through automated tests.
- Produce evaluation metrics.

Do not assume retrieval is necessary merely because it appears in the original module design.

The Full-Catalog baseline will serve as the reference for all subsequent experiments.

---

## 5. Hybrid Metric Retrieval

Design a lightweight hybrid retrieval system.

### 5.1 Dense Retrieval

Use an embedding model to encode:

- Metric documents during offline indexing
- User queries during online inference

The query and documents must use compatible embedding configurations.

Specify whether query-specific instructions and document encoding conventions are required by the selected model.

Use cosine similarity or normalized dot-product similarity.

Make Top-K configurable.

Suggested initial experiments:

- Top-5
- Top-10
- Top-12

These are starting points, not fixed final values.

### 5.2 Lexical Retrieval

Use:

- Exact label matching
- Synonym/alias matching
- Normalized token matching
- Optional BM25 if justified

Prioritize recognition of financial terms in Vietnamese and English.

### 5.3 Fusion

Use Reciprocal Rank Fusion as the initial approach.

Suggested initial constant:

`rrf_k = 60`

Preserve retrieval trace information, including source, rank, and score.

### 5.4 Reranking

Start with metadata reranking.

Use existing contract requirements as the baseline.

Do not introduce an additional neural reranker until benchmark evidence shows that it is beneficial.

### 5.5 Multi-Metric Retrieval

The system must correctly support queries requiring multiple metrics.

For example:

"Compare net revenue and net profit between Q2 and Q3."

The retrieval system must include all required metrics in the candidate set.

Optimize for **Complete Gold Set Recall@K**, not only Top-1 accuracy.

Document the impact of candidate truncation on downstream metric selection.

---

## 6. Dynamic Few-shot Strategy

Redesign the Dynamic Few-shot component as a separately testable module.

Evaluate the following strategies:

1. No few-shot
2. Static few-shot
3. Dynamic few-shot using semantic relevance
4. Dynamic few-shot using diversity and coverage
5. Hybrid relevance + coverage, if justified

Prioritize examples representing different query structures, such as:

- Single metric
- Multiple metrics
- Comparison queries
- Aggregation or grouping queries
- Ambiguous financial terminology
- Unsupported or clarification-required queries

Maintain the existing few-shot governance rules:

- Only approved examples
- No prompt-injection examples
- No identical-question leakage
- Respect the token budget
- Respect supported views
- Respect candidate-set compatibility

In particular, production-compatible examples must satisfy:

`example.metric_ids ⊆ candidate_metric_ids`

Do not assume few-shot improves performance.

Require ablation studies against no-few-shot and static few-shot baselines.

Prevent contamination between training/development examples and final evaluation data.

---

## 7. LLM Selector & Validation

Keep the existing Qwen3:4b local selector as the initial baseline model.

Requirements:

- Structured JSON output
- Schema validation
- Deterministic configuration where practical
- Explicit status handling
- Multi-label metric selection
- Strict candidate-set constraints
- No SQL generation
- No invented metric IDs

The validator must preserve or strengthen the existing Contract 15 requirements.

Pay special attention to:

- Catalog membership
- Approved status
- Verified handlers
- Authorization and view permissions
- Supported dimensions
- Supported operations
- Candidate-set containment
- Flow/snapshot compatibility
- Ambiguous and unsupported requests

Clearly separate:

1. Model output validity
2. Selection validity
3. Business/semantic compatibility

The system must not silently convert validation errors into successful selections.

---

## 8. Recovery & Fallback Design

Propose bounded recovery mechanisms for:

- Empty retrieval results
- Missing candidates
- Invalid LLM JSON
- Selection outside candidate set
- Ambiguous questions
- Embedding provider unavailable
- Stale or incompatible index

Distinguish:

**Retrieval failure:** required metric was absent from the candidate set.

**Selection failure:** required metric was present but the LLM selected incorrectly.

Do not assume the system can identify a missing gold metric at inference time.

Any fallback trigger must rely on observable signals available during inference.

Consider full-catalog fallback if it is permitted by the active contracts and authorization rules.

If fallback expands the candidate set, produce a new valid retrieval result and reapply all required validation rules.

Do not bypass validator authority.

Keep retry counts bounded and measurable.

If fallback conflicts with current contracts, propose an explicit contract change instead of silently changing behavior.

---

## 9. Evaluation & Experiment Design

Evaluation must be treated as a first-class engineering component.

Create a benchmark plan with independently labeled examples.

Include Vietnamese financial questions with:

- Direct metric mentions
- Synonym-based questions
- Paraphrased questions
- Multi-metric questions
- Similar or confusing metrics
- Ambiguous questions
- Unsupported requests
- View and permission constraints
- Period, dimension, and operation constraints

Where possible, include difficult examples drawn from actual Metric Catalog definitions.

Do not fabricate benchmark results.

### Required metrics

**Retrieval:**

- Recall@K
- Complete Gold Set Recall@K
- MRR or ranking quality where applicable
- Retrieval latency

**Selection:**

- Exact Set Match
- Micro/Macro Precision, Recall, F1
- False-positive and missing-metric error analysis
- Schema validity rate
- Authorized/valid selection rate

**System:**

- End-to-end metric selection accuracy
- p50/p95 latency
- CPU/RAM usage
- Model loading overhead
- Failure/recovery rates
- Downstream SQL execution correctness where integration tests permit

### Required experiments

| Experiment | Retrieval | Few-shot |
|---|---|---|
| E0 | Full Catalog | None |
| E1 | Dense | None |
| E2 | Hybrid | None |
| E3 | Hybrid | Static |
| E4 | Hybrid | Dynamic |
| E5 | Best configuration | Recovery/Fallback |

Use the same evaluation split and comparable model settings where appropriate.

Build a framework to compare these experiments.

Require a decision gate after each major experiment.

If Full-Catalog selection performs better than retrieval-based selection, retain it as a valid production/submission candidate.

Select the final architecture based on measured accuracy, latency, resource constraints, and competition rules.

---

## 10. Rewrite the Implementation Plan

Rewrite the existing module plan into an execution-oriented document.

Use the structure:

### 1. Module Overview
- Goals
- Responsibilities
- Non-goals
- Competition requirements
- Trust boundaries

### 2. Current State
- Implemented components
- Missing components
- Existing contracts
- Technical debt and inconsistencies

### 3. Target Architecture
- Offline workflow
- Online workflow
- Baseline workflow
- Module boundaries
- Data contracts

### 4. Technology Decisions
- Embedding model
- LLM selector
- Embedding provider
- Vector storage
- Retrieval strategies
- Validation strategy
- Runtime/deployment assumptions

For every significant choice, document rationale, tradeoffs, alternatives, and whether the decision is provisional or confirmed.

### 5. Implementation Milestones
- Milestones
- Issues
- Tasks
- Dependencies
- Deliverables
- Acceptance criteria

### 6. Evaluation Strategy
- Dataset
- Experiment matrix
- Metrics
- Quality gates
- Reproducibility

### 7. Risks
- Technical risks
- Performance risks
- Contract compatibility
- Evaluation leakage
- Deployment risks

### 8. Definition of Done
- Functionality
- Tests
- Contract compliance
- Benchmark evidence
- Documentation

Preserve the existing useful information rather than replacing the document with a generic architectural proposal.

---

## 11. Redesign Milestones, Issues & Tasks

Reorganize the current module issues according to actual dependency order and benchmark-driven development.

Suggested milestone structure:

### M1 — Catalog & Full-Catalog Baseline
Deliver a working baseline and first measured results.

### M2 — Embedding & Offline Indexing
Deliver a versioned, reproducible local embedding index.

### M3 — Hybrid Retrieval
Deliver dense, lexical, fusion, and reranking with measurable retrieval performance.

### M4 — Dynamic Few-shot & Selector Improvements
Deliver few-shot experiments and selection improvements.

### M5 — Recovery, Evaluation & Submission Readiness
Deliver bounded recovery, end-to-end benchmarking, and a reproducible submission configuration.

These milestone identifiers are suggestions. Reconcile them with the repository's existing M1 numbering and related project milestones. Avoid conflicting identifiers or unnecessarily breaking existing issue references.

For every issue, provide:

**Issue metadata**
- Title
- Milestone
- Type
- Priority
- Dependencies
- Estimated complexity: S / M / L
- Relevant files/modules
- Relevant contracts

**Issue body**
- Problem statement
- Objective
- Scope
- Out of scope
- Technical approach
- Implementation tasks
- Expected deliverables
- Acceptance criteria
- Test requirements
- Evaluation requirements
- Definition of Done

Each task must be small enough for a coding agent to implement and verify in a focused issue loop.

Avoid issues that require implementing the entire module in one change.

Prefer vertical slices:

**Implement → Test → Benchmark (where applicable) → Review → Complete**

Do not postpone all testing until the final milestone.

Every milestone must produce a runnable or testable artifact, not documentation alone.

Include measurable acceptance criteria, but do not invent accuracy thresholds without an established competition requirement or baseline evidence.

Propose thresholds as provisional targets if necessary.

---

## 12. GitHub Issue Synchronization

Inspect the repository's issue-management workflow.

Determine whether issues are managed through:

- GitHub Issues
- Local Markdown documents
- GitHub Project boards
- Another existing mechanism

Preserve existing issue IDs where possible.

Classify current issues into:

- Keep
- Update
- Split
- Merge
- Close as obsolete
- Create new

Produce an old-to-new issue mapping.

If GitHub access and authenticated issue-management tools are available, update the relevant issues and create missing ones in accordance with repository conventions.

Do not modify unrelated issues.

Do not close completed issues without verifying their implementation and tests.

If GitHub access is unavailable, produce ready-to-publish issue bodies and an exact synchronization checklist instead of claiming GitHub was updated.

---

## 13. Deliverables

Produce or update the following artifacts, adapting filenames to the actual repository structure.

**A. Updated Module Plan**

`metrics_selection.md`

A complete implementation-oriented architecture and execution plan.

**B. Updated Issue Backlog**

Use the repository's existing issue format and location.

Include dependencies, tasks, deliverables, acceptance criteria, and Definition of Done.

**C. Evaluation Specification**

Create or update an appropriate evaluation document, such as:

`metric_selection/evaluation.md`

Cover datasets, metrics, experiments, baselines, decision gates, and reporting formats.

**D. Architecture Decision Record**

Document key tradeoffs, especially:

- Full Catalog vs Retrieval
- Dense vs Hybrid Retrieval
- Static vs Dynamic Few-shot
- Local embedding model selection
- NumPy vs external vector database

**E. Change Summary**

Provide:

1. Files created or modified
2. Existing issues modified
3. New issues created
4. Issues superseded or split
5. Contract changes proposed
6. Open technical risks
7. Recommended first issue for implementation

---

## 14. Execution Constraints

This is a **PLANNING AND ISSUE REFACTORING TASK ONLY**.

You may:

- Read and analyze repository files
- Update planning documentation
- Update issue documentation
- Prepare or synchronize GitHub issues when access is available
- Propose architecture and contract revisions

You must NOT:

- Implement the new Metric Selection pipeline yet
- Modify production source code
- Rewrite existing tests to force them to pass
- Change contracts silently
- Delete historical implementation artifacts without justification
- Invent benchmark results
- Introduce unnecessary distributed infrastructure
- Expand the scope into unrelated Text-to-SQL modules

If a contract change is required, document:

- Existing behavior
- Proposed behavior
- Reason
- Compatibility impact
- Tests that must change
- Migration strategy

Do not ask for clarification when repository evidence supports a reasonable decision. Record assumptions explicitly.

---

## 15. Final Instructions

Start by inspecting the repository and identifying architectural gaps.

Then revise the implementation plan and issue backlog.

Optimize for:

**Working baseline first → measurable experiments → incremental improvement → competition-ready submission.**

Do not optimize for architectural complexity.

Favor the smallest architecture that achieves the best validated results.

When finished, provide a concise summary containing:

- Final proposed architecture
- Milestone and issue breakdown
- Key architectural changes
- Updated files and issue status
- Evaluation strategy
- Recommended first issue to implement

**Do not start implementation. Stop after the plan, issues, and related planning artifacts are updated.**