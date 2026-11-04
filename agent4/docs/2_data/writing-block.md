# METRIC SELECTION ENGINE — IMPLEMENTATION PLAN

**Project:** AI-fin\
**Component:** Intelligent Metric Selection Engine\
**Language:** Python 3.11+\
**Architecture:** Modular, configurable, testable pipeline\
**Source of truth:** `metrics.py`\
**Primary objective:** Natural Language → Validated Metric Selection Schema

---

# 1. Project Objective

Build a complete Metric Selection Engine that converts Vietnamese natural-language financial questions into validated structured selections referencing metrics already defined in `metrics.py`.

The engine must implement the following pipeline:

```text
User Question
    |
    v
Stage 1: Candidate Generation
    |-- Dense Retrieval
    |-- Lexical Retrieval
    |-- Optional Mention-level Retrieval
    |-- Candidate Fusion
    |
    v
Stage 2: Candidate Expansion
    |-- Metric Relationships
    |-- Metric Specialization
    |-- Related Metric Discovery
    |
    v
Stage 3: Reranking
    |-- Semantic Relevance
    |-- Business Metadata
    |-- Optional Cross-encoder
    |
    v
Stage 4: Adaptive Few-shot + LLM
    |-- Example Bank
    |-- Decision Boundary Selection
    |-- Adaptive Example Budget
    |-- Prompt Construction
    |-- Structured LLM Output
    |
    v
```

The engine must be usable independently of the SQL generation and execution systems.

**Non-goals:**

- Generating SQL.
- Executing financial queries.
- Modifying accounting formulas.
- Calculating metric values.
- Producing final natural-language financial answers.
- Training or fine-tuning an LLM during v1 development.

These capabilities belong to downstream components.

---

# 2. Mandatory Engineering Principles

## 2.1 Preserve existing business logic

The existing `metrics.py` defines 66 metrics using `MetricDef` and `Term`.

Relevant fields include:

- `id`
- `label`
- `description`
- `kind`
- `unit`
- `category`
- `formula`
- `synonyms`
- `group_bys`
- `views`
- `default_view`
- `params`
- `period_type`

The implementation must reuse the existing `REGISTRY`.

`metrics.py` remains the single source of truth for metric definitions.

Do not duplicate metric formulas or manually redefine existing metrics in another module.

Additional retrieval metadata must live in separate version-controlled configuration files.

## 2.2 Maintain stage independence

Each pipeline stage must expose a typed interface.

A stage should be replaceable without modifying unrelated stages.

Examples:

- Dense retrieval can be replaced with another embedding backend.
- BM25 can be enabled or disabled.
- Reranking can use heuristics or cross-encoder.
- Adaptive few-shot can be replaced with static or zero-shot.
- LLM providers can be changed using a provider interface.

## 2.3 Optimize for correctness first

Priority order:

1. Candidate recall.
2. Final metric selection accuracy.
3. Structured output validity.
4. Computational efficiency.
5. Latency.
6. Token cost.

The first retrieval stages should favor recall over aggressive filtering.

The LLM stage is responsible for final semantic selection, while deterministic validation checks registry and business constraints.

## 2.4 Avoid unnecessary LLM calls

Do not use an LLM call for every internal decision.

In particular:

- Query decomposition is optional.
- Skill classification is not required.
- Few-shot allocation should use local deterministic logic.
- Metadata validation should be deterministic.

The normal request path should require only one final LLM selection call.

## 2.5 Reproducibility

Record model versions, embedding models, retrieval settings, prompt versions, example-bank versions and random seeds.

The same configuration and input should support reproducible evaluation, subject to model-provider nondeterminism.

---

# 3. Proposed Project Structure

Create the following structure, adapting it to the existing repository rather than blindly introducing a new root package.

```text
metric_selection/
├── __init__.py
├── config.py
├── schemas/
│   ├── request.py
│   ├── retrieval.py
│   ├── selection.py
│   └── evaluation.py
├── catalog/
│   ├── adapter.py
│   ├── document_builder.py
│   ├── index_builder.py
│   └── relationships.py
├── retrieval/
│   ├── embedding.py
│   ├── dense.py
│   ├── lexical.py
│   ├── fusion.py
│   ├── mentions.py
│   └── candidate_generator.py
├── expansion/
│   └── metric_expander.py
├── reranking/
│   ├── metadata_ranker.py
│   ├── cross_encoder.py
│   └── reranker.py
├── fewshot/
│   ├── example_bank.py
│   ├── selector.py
│   ├── adaptive_policy.py
│   └── prompt_builder.py
├── llm/
│   ├── provider.py
│   ├── selector.py
│   └── parser.py
├── validation/
│   └── validator.py
├── pipeline.py
└── api.py

config/
├── metric_relationships.yaml
├── metric_retrieval.yaml
└── selection.yaml

data/
├── example_bank.jsonl
├── metric_query_examples.jsonl
└── eval/
    ├── train.jsonl
    ├── dev.jsonl
    └── test.jsonl

tests/
├── unit/
├── integration/
└── regression/

scripts/
├── build_index.py
├── benchmark_retrieval.py
├── benchmark_fewshot.py
└── benchmark_pipeline.py

docs/
├── architecture.md
├── metric_retrieval.md
├── fewshot_strategy.md
└── evaluation.md
```

Use Pydantic for input and output contracts.

Use pytest for testing.

All model services must be injectable or mockable.

---

# 4. Shared Data Contracts

Implement shared schemas before working on the stages.

## 4.1 Selection Request

```python
class MetricSelectionRequest(BaseModel):
    question: str
    context: dict[str, Any] = {}
    debug: bool = False
```

The context may carry explicitly supplied information such as an accounting view or reference date.

Do not silently assume missing business parameters.

## 4.2 Metric Candidate

```python
class MetricCandidate(BaseModel):
    metric_id: str
    dense_score: float | None = None
    lexical_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None
    retrieval_sources: list[str] = []
    expansion_source: str | None = None
```

Scores from different rankers must not be treated as calibrated probabilities.

## 4.3 Final Selection

```python
class MetricSelectionResult(BaseModel):
    status: Literal[
        "resolved",
        "ambiguous",
        "unsupported"
    ]
    metric_ids: list[str]
    clarification_question: str | None = None
    unsupported_reason: str | None = None
```

Validation requirements:

- `resolved`: at least one valid selected metric.
- `ambiguous`: no forced arbitrary selection.
- `unsupported`: no fabricated metric IDs.
- Every selected metric must exist in `REGISTRY`.

Keep this as the minimal v1 schema. If the existing application already specifies a richer downstream schema, adapt to that contract without changing the metric-selection semantics.

## 4.4 Pipeline Debug Trace

Debug mode should expose:

- Initial dense candidates.
- Initial lexical candidates.
- Fused candidates.
- Expanded candidates.
- Final ranked candidates.
- Selected few-shot IDs.
- Prompt token estimate.
- LLM output.
- Validation errors.
- Latency per stage.

Do not expose hidden reasoning or sensitive financial data in production logs.

---

# 5. Stage 1 — Candidate Generation

**Objective:** Retrieve a high-recall set of relevant candidate metrics.

## Task 1.1 — Metric Catalog Adapter

Implement an adapter that reads all metric definitions from `REGISTRY`.

Requirements:

- Validate unique metric IDs.
- Extract retrieval-relevant metadata.
- Preserve original business definitions.
- Expose a version/hash of the catalog.
- Provide lookup by metric ID.
- Support deterministic iteration order.

Deliverables:

- `catalog/adapter.py`
- Unit tests for all 66 metrics.

Acceptance criteria:

- All registered metrics are accessible.
- No metric formula is modified.
- Duplicate and invalid metric metadata are detected.

## Task 1.2 — Build Retrieval Documents

Create a semantic retrieval document for each metric.

The first version should concatenate:

```text
Metric Name:
{label}

Description:
{description}

Synonyms:
{synonyms}

Category:
{category}
```

Do not include raw account-term formulas in the initial embedding text.

Preserve `kind`, `unit`, `views`, `group_bys`, `period_type` and `params` as structured metadata.

Create a separate, optional set of business-question paraphrases.

The questions must be manually reviewed or verified against the metric registry.

Deliverables:

- `catalog/document_builder.py`
- Retrieval documents generated from `REGISTRY`.
- Tests asserting stable document generation.

## Task 1.3 — Dense Retrieval

Implement an embedding provider interface:

```python
class EmbeddingProvider(Protocol):
    def embed_query(self, text: str) -> list[float]: ...
    def embed_documents(
        self, texts: list[str]
    ) -> list[list[float]]: ...
```

Requirements:

- Support configurable multilingual embedding models.
- Batch embedding during index building.
- Cache document embeddings.
- Rebuild when the catalog or embedding configuration changes.
- Use cosine similarity or normalized dot product consistently.

Because there are only 66 metrics, begin with an in-memory NumPy matrix.

Do not introduce a vector database until benchmarking demonstrates a real need.

Deliverables:

- `retrieval/embedding.py`
- `retrieval/dense.py`
- `catalog/index_builder.py`

## Task 1.4 — Lexical Retrieval

Implement lexical matching over:

- Metric IDs.
- Labels.
- Synonyms.
- Descriptions.

Use BM25 or an equivalent lexical ranking algorithm.

Support Vietnamese Unicode normalization and case-insensitive matching.

Be careful not to destroy meaningful distinctions during normalization.

Do not use English-only stemming.

Deliverables:

- `retrieval/lexical.py`
- Lexical matching tests for Vietnamese metric queries.

## Task 1.5 — Candidate Fusion

Combine dense and lexical candidate rankings using Reciprocal Rank Fusion.

```text
RRF(m) = sum(1 / (k + rank_i(m)))
```

The constant `k` must be configurable.

Preserve score provenance.

Apply deterministic tie-breaking by metric ID.

Deliverables:

- `retrieval/fusion.py`
- `retrieval/candidate_generator.py`

## Task 1.6 — Optional Mention-level Retrieval

Develop an optional metric-mention extraction mechanism for multi-metric questions.

Example:

```text
"So sánh doanh thu và lợi nhuận sau thuế"
```

Potential mentions:

```json
[
  "doanh thu",
  "lợi nhuận sau thuế"
]
```

The mechanism must not execute for every query by default.

Use a configurable trigger, such as multiple recognized metric phrases or an explicit multi-metric pattern.

When mention extraction is enabled:

1. Retrieve candidates for the original question.
2. Retrieve candidates for each extracted metric mention.
3. Union all candidate sets.
4. Deduplicate.
5. Preserve retrieval provenance.

Do not discard original-query candidates.

Mention extraction must be optional and benchmarked separately.

**Stage 1 acceptance criteria:**

- Configurable dense retrieval.
- Configurable lexical retrieval.
- Working candidate fusion.
- Index cache and reproducible index rebuilding.
- Stage-level tests.
- Evaluation of Recall\@5, Recall\@10 and All-Gold-Covered\@K.

---

# 6. Stage 2 — Candidate Expansion

**Objective:** Recover relevant metrics that retrieval may have omitted, especially specialized or closely related metrics.

## Task 2.1 — Metric Relationship Registry

Create `config/metric_relationships.yaml`.

Define explicit relationships such as:

```yaml
relationships:
  - source: ar_balance
    target: ar_by_customer
    type: specialization
    metadata:
      group_by: customer

  - source: ar_balance
    target: ar_by_salesperson
    type: specialization
    metadata:
      group_by: salesperson
```

Additional relationship types may include:

- `specialization`
- `related_concept`
- `alternative_definition`
- `confusable_with`

Relationships must be curated from the existing catalog.

Do not generate relationships automatically based only on text similarity and treat them as verified business facts.

## Task 2.2 — Expansion Algorithm

Input:

```text
Top-K candidates from Stage 1
```

Output:

```text
Expanded candidate set
```

Algorithm:

1. Read candidate metric IDs.
2. Find directly related metrics.
3. Expand one hop by default.
4. Deduplicate candidates.
5. Record the expansion source.
6. Enforce a configurable maximum candidate budget.

Avoid recursive expansion without limits.

Do not automatically treat every related metric as equally relevant.

Implement query-aware expansion as an optional later strategy.

For example, the word "khách hàng" may increase the value of expanding `ar_balance` toward `ar_by_customer`.

## Task 2.3 — Expansion Evaluation

Compare retrieval before and after expansion.

Track:

- Recall improvement.
- Candidate set growth.
- Precision impact.
- Added latency.
- Downstream selection accuracy.

Expansion is useful only if it recovers relevant metrics without introducing excessive confusion.

**Stage 2 acceptance criteria:**

- Validated relationship configuration.
- Deterministic one-hop expansion.
- Deduplication and configurable limits.
- No new or fabricated metric IDs.
- Documented before/after evaluation.

---

# 7. Stage 3 — Reranking

**Objective:** Prioritize candidates using semantic and business constraints while preserving relevant metrics.

## Task 3.1 — Metadata-aware Ranker

Use the existing `MetricDef` metadata:

- `unit`
- `kind`
- `group_bys`
- `views`
- `period_type`
- `category`
- `params`

Examples:

**Case A — Ratio**

User asks:

```text
"Biên lợi nhuận ròng là bao nhiêu phần trăm?"
```

Potential candidates:

- `net_profit`
- `net_margin_pct`

Metric metadata supports preferring `net_margin_pct`.

**Case B — Snapshot vs Flow**

User asks:

```text
"Hiện tại công ty còn bao nhiêu tiền?"
```

Potential candidates:

- `cash_and_equivalents`
- `net_cash_flow`

The distinction between current balance and period movement should influence ranking.

**Case C — Tax vs Management**

User asks:

```text
"Thu nhập chịu thuế của công ty là bao nhiêu?"
```

The correct business view must be considered.

Use conservative ranking boosts and penalties.

Do not hard-filter based on uncertain interpretation of a question.

Only apply strict filters when the corresponding business constraint is explicit and verified.

## Task 3.2 — Optional Cross-encoder

Implement a configurable cross-encoder reranker.

Input:

```text
(question, candidate metric document)
```

Output:

```text
Relevance score
```

The implementation must support disabling the cross-encoder.

Do not assume the scores are directly comparable with BM25 or cosine similarity.

Use a documented ranking or normalization strategy.

## Task 3.3 — Final Candidate Budget

Configure a maximum number of metrics sent to the LLM.

Example defaults for initial experiments:

```yaml
retrieval:
  dense_top_k: 15
  lexical_top_k: 15
  fusion_top_k: 20

expansion:
  enabled: true
  max_hops: 1
  max_candidates: 30

reranking:
  final_top_k: 12
  cross_encoder_enabled: false
```

These are starting hyperparameters, not validated optimal values.

Ensure that final Top-K does not silently eliminate required metrics in multi-metric evaluation.

**Stage 3 acceptance criteria:**

- Metadata-aware ranking works independently.
- Cross-encoder support is optional.
- Candidate ranking is explainable through logged score components.
- Ranking remains deterministic with fixed model outputs.
- Reranking performance is measured against Stage 1 and Stage 2 baselines.

---

# 8. Stage 4 — Adaptive Few-shot + LLM Metric Selection

**Objective:** Select appropriate examples based on metric ambiguity and candidate characteristics, then use an LLM to produce valid metric selections.

## Task 4.1 — Example Bank

Create a curated example bank containing:

```json
{
  "id": "ex_001",
  "question": "Công ty còn bao nhiêu tiền?",
  "answer": {
    "status": "resolved",
    "metric_ids": [
      "cash_and_equivalents"
    ]
  },
  "decision_tags": [
    "snapshot_vs_flow"
  ],
  "confusable_metrics": [
    "net_cash_flow"
  ]
}
```

Organize examples around **metric selection decisions**, not generic reasoning capabilities.

Suggested decision tags:

- `gross_vs_net`
- `amount_vs_ratio`
- `snapshot_vs_flow`
- `specialized_vs_generic`
- `accounting_vs_tax`
- `implicit_business_intent`
- `ambiguous_metric`
- `unsupported_metric`
- `multi_metric_disambiguation`

Example metadata is used for retrieval and selection.

The LLM prompt should contain only the necessary demonstrations, not all retrieval metadata.

Requirements:

- Every positive metric ID exists in `REGISTRY`.
- Examples are reviewed for business correctness.
- No examples are automatically accepted from synthetic generation without review.
- Keep evaluation questions separate from the example bank.

## Task 4.2 — Example Retrieval

Implement semantic retrieval over user questions in the example bank.

Inputs:

- User question.
- Final candidate metric IDs.
- Candidate metadata.
- Example bank.

Retrieve an initial example pool using semantic similarity.

Then prioritize examples relevant to the candidate set.

Do not rely exclusively on similarity.

## Task 4.3 — Decision Boundary Coverage

Implement coverage over metric-confusion boundaries.

For example:

```text
Candidates:
  gross_profit
  gross_margin_pct
  net_profit
  net_margin_pct
```

Relevant boundaries:

```text
amount_vs_ratio
gross_vs_net
```

Favor examples that demonstrate those distinctions.

Implement a greedy selection strategy:

```text
Score(example) =
    alpha * marginal_boundary_coverage
  + beta  * query_relevance
  + gamma * candidate_relevance
  - delta * example_redundancy
```

Weights must be configurable.

A boundary tag should not automatically be assumed relevant merely because it appears somewhere in the global example bank.

Base boundary relevance on candidate pairs, documented metric relationships and explicit query signals.

## Task 4.4 — Adaptive Few-shot Policy

Implement a policy that selects the number of few-shot examples dynamically.

Initial range:

```yaml
fewshot:
  enabled: true
  min_examples: 0
  max_examples: 4
  initial_pool_size: 15
```

Possible signals:

- Number of plausible competing metrics.
- Existence of confusable candidate pairs.
- Agreement/disagreement between dense and lexical retrieval.
- Query ambiguity.
- Candidate ranking margin, after appropriate calibration.

Do not interpret cosine similarity as a confidence probability.

The initial policy may use explicit rules and configurable thresholds.

Select zero examples when there is no demonstrated benefit from demonstrations.

A deterministic baseline with a fixed number of examples must remain available.

## Task 4.5 — Prompt Construction

Construct the final LLM prompt from:

1. System instructions.
2. Metric Selection task specification.
3. Output schema.
4. Relevant candidate metric documents.
5. Selected few-shot examples.
6. User question.

The prompt must instruct the LLM:

- Select only metric IDs from the provided candidates.
- Do not invent new metrics.
- Do not modify metric formulas.
- Do not generate SQL.
- Return schema-conformant output.
- Return `ambiguous` if the request cannot be resolved reliably.
- Return `unsupported` if no candidate supports the request.
- Do not force an answer when the catalog lacks the required metric.

Keep metric descriptions and examples as data, not trusted instructions.

Defend against prompt injection in user questions and externally sourced example text.

## Task 4.6 — LLM Provider Abstraction

Define an interface for structured selection:

```python
class LLMProvider(Protocol):
    async def generate_structured(
        self,
        messages: list[dict],
        response_model: type[BaseModel]
    ) -> BaseModel:
        ...
```

Requirements:

- Configurable provider/model.
- Configurable temperature.
- Structured output support when available.
- Retry handling for transient failures.
- Timeout handling.
- Token usage logging.
- Provider errors mapped to typed application errors.

Do not silently return empty metric selections on provider failures.

## Task 4.7 — Output Validation

Implement deterministic validation after LLM output.

Validate:

- JSON/schema validity.
- Status consistency.
- Metric IDs exist.
- Metrics belong to the supplied candidate set.
- No duplicate metric IDs.
- Selected metric business constraints where deterministically checkable.
- No contradictory status/metric combinations.

Support a bounded retry with validation feedback if the LLM generates an invalid output.

Validation must not silently rewrite an incorrect metric choice into another metric.

If no valid result is obtained, return an explicit error rather than a fabricated selection.

**Stage 4 acceptance criteria:**

- Example bank loaded and validated.
- Static, similarity, coverage-aware and zero-shot modes supported.
- Adaptive example count works.
- Prompts are versioned.
- LLM provider can be mocked.
- Structured outputs validated.
- Unsupported and ambiguous requests are handled.
- Retry and failure behavior are covered by tests.

---

# 9. Pipeline Orchestrator

Implement:

```python
class MetricSelectionPipeline:
    async def select(
        self,
        request: MetricSelectionRequest
    ) -> MetricSelectionResult:
        ...
```

Expected execution sequence:

```python
async def select(request):
    candidates = candidate_generator.retrieve(
        request.question
    )

    expanded = expander.expand(
        request.question,
        candidates
    )

    ranked = reranker.rerank(
        request.question,
        expanded,
        request.context
    )

    examples = fewshot_selector.select(
        question=request.question,
        candidates=ranked
    )

    result = await llm_selector.select(
        question=request.question,
        candidates=ranked,
        examples=examples,
        context=request.context
    )

    return validator.validate(
        result,
        candidates=ranked
    )
```

The above is conceptual pseudocode. Final method signatures must follow the typed schemas.

All stages should emit structured telemetry.

Add configuration switches allowing individual stages to be bypassed.

A retrieval failure, an empty candidate set and an LLM provider failure must be treated as distinct conditions.

---

# 10. API Integration

Expose a FastAPI endpoint:

```http
POST /api/metrics/select
```

Request example:

```json
{
  "question": "Biên lợi nhuận ròng tháng này là bao nhiêu?",
  "context": {},
  "debug": false
}
```

Response example:

```json
{
  "status": "resolved",
  "metric_ids": [
    "net_margin_pct"
  ],
  "clarification_question": null,
  "unsupported_reason": null
}
```

Implement an internal diagnostic endpoint or CLI for stage inspection.

Debug traces must be gated behind a development or authorized diagnostic configuration, not publicly exposed by default.

Do not add authentication infrastructure if the existing project already supplies it. Integrate with the current authentication and logging conventions.

---

# 11. Evaluation Framework

Evaluation is mandatory, not optional.

## 11.1 Build Gold Evaluation Dataset

Create a manually verified dataset of natural-language questions and expected metric IDs.

Include:

- Direct metric mentions.
- Paraphrased financial questions.
- Implicit business intents.
- Confusable metrics.
- Multi-metric queries.
- Colloquial Vietnamese.
- Questions with irrelevant context.
- Ambiguous questions.
- Unsupported questions.

Each dataset entry should include:

```json
{
  "id": "test_001",
  "question": "Công ty còn bao nhiêu tiền?",
  "gold_metric_ids": [
    "cash_and_equivalents"
  ],
  "gold_status": "resolved",
  "category": "snapshot_vs_flow"
}
```

Use train/dev/test partitions.

Keep paraphrases of the same underlying question grouped to avoid data leakage.

Examples selected for few-shot must not overlap with held-out test questions or their close paraphrases.

Initial dataset sizes may be selected based on available annotation capacity. Prioritize label quality and coverage of failure modes over arbitrary volume targets.

## 11.2 Retrieval Evaluation

Implement:

- Recall\@K.
- Precision\@K.
- Mean Reciprocal Rank.
- All-Gold-Covered\@K.
- Average candidate count.
- Retrieval latency.

For multi-metric questions, All-Gold-Covered\@K is particularly important.

Compare:

- Description-only dense.
- Enriched-document dense.
- Multi-representation dense.
- Hybrid dense + lexical.
- Hybrid + expansion.
- Hybrid + reranking.

## 11.3 Few-shot Evaluation

Compare:

- Zero-shot.
- Static few-shot.
- Similarity-based few-shot.
- Coverage-aware few-shot.
- Adaptive few-shot.

Keep model, candidate inputs, output schema and other prompt settings constant when isolating few-shot selection effects.

Track:

- Metric Exact Set Match.
- Metric Precision/Recall/F1.
- Ambiguous/unsupported classification accuracy.
- Valid Output Rate.
- Average number of examples.
- Token cost.
- Latency.

## 11.4 End-to-end Evaluation

Measure final accuracy of the entire pipeline.

Required comparisons:

1. Full catalog → LLM without retrieval.
2. Dense retrieval → LLM.
3. Hybrid retrieval → LLM.
4. Hybrid + expansion → LLM.
5. Hybrid + expansion + reranking → LLM.
6. Full pipeline with adaptive few-shot.

All variants should use the same held-out dataset.

Do not claim improvements from a single small test sample.

Report per-category results and confidence intervals where practical.

---

# 12. Implementation Milestones

## Milestone 0 — Repository Inspection and Contracts

Tasks:

- Inspect existing repository and dependencies.
- Read the complete `metrics.py`.
- Identify existing LLM infrastructure.
- Identify existing API conventions.
- Define typed request/response schemas.
- Document architecture decisions.

Deliverables:

- Architecture documentation.
- Interfaces and schema definitions.
- Initial test setup.

**Exit condition:** The pipeline interfaces are agreed and all source metric definitions load successfully.

## Milestone 1 — Retrieval Baseline

Tasks:

- Metric catalog adapter.
- Retrieval document builder.
- Dense retrieval.
- Lexical retrieval.
- RRF fusion.
- Retrieval evaluation CLI.

Deliverables:

- Working Stage 1.
- Reproducible index build.
- Baseline retrieval benchmark.

**Exit condition:** Retrieval returns valid candidates and Recall\@K can be measured reproducibly.

## Milestone 2 — Candidate Expansion

Tasks:

- Relationship configuration.
- Relationship validation.
- One-hop expansion.
- Candidate-budget enforcement.
- Before/after evaluation.

Deliverables:

- Working Stage 2.
- Relationship tests.
- Expansion benchmark.

**Exit condition:** Expansion is correct, bounded and measurable.

## Milestone 3 — Reranking

Tasks:

- Metadata-aware ranker.
- Optional cross-encoder interface.
- Candidate score tracing.
- Reranking benchmark.

Deliverables:

- Working Stage 3.
- Ranker unit tests.
- Reranking evaluation.

**Exit condition:** Reranking is configurable and downstream candidate recall is measured.

## Milestone 4 — Few-shot and LLM

Tasks:

- Example bank.
- Example validation.
- Similarity retrieval.
- Decision-boundary-aware selection.
- Adaptive example budget.
- Prompt builder.
- LLM provider integration.
- Structured output validation.

Deliverables:

- Working Stage 4.
- Few-shot ablation benchmark.
- Provider mock tests.

**Exit condition:** LLM returns schema-conformant metric selections and adaptive few-shot behavior is measurable.

## Milestone 5 — Integration and Hardening

Tasks:

- Pipeline orchestrator.
- FastAPI integration.
- Integration tests.
- Error handling.
- Structured logging.
- Latency profiling.
- Configuration documentation.
- End-to-end benchmark.

Deliverables:

- Complete Metric Selection Engine.
- API endpoint.
- Evaluation report.
- Operational documentation.

**Exit condition:** All configured stages work together and the full evaluation suite passes.

---

# 13. Required Test Scenarios

At minimum, implement the following regression cases:

| User query                                    | Expected metric             |
| --------------------------------------------- | --------------------------- |
| "Doanh thu thuần tháng này?"                  | `net_revenue`               |
| "Doanh thu trước giảm trừ?"                   | `gross_revenue`             |
| "Lãi gộp là bao nhiêu?"                       | `gross_profit`              |
| "Biên lãi gộp bao nhiêu phần trăm?"           | `gross_margin_pct`          |
| "Công ty còn bao nhiêu tiền trong tài khoản?" | `cash_and_equivalents`      |
| "Dòng tiền thuần tháng này?"                  | `net_cash_flow`             |
| "Khách hàng nào nợ nhiều nhất?"               | `ar_by_customer`            |
| "Công nợ phải thu hiện tại?"                  | `ar_balance`                |
| "Tiền hiện tại đủ hoạt động mấy ngày?"        | `cash_coverage_days`        |
| "Lợi nhuận sau thuế?"                         | `net_profit`                |
| "Doanh thu và lợi nhuận sau thuế?"            | `net_revenue`, `net_profit` |

These are preliminary reference labels. Review implicit business conventions before treating all labels as final gold annotations.

Additional tests must cover:

- Empty questions.
- Invalid metric IDs.
- Duplicate candidates.
- Ambiguous queries.
- Unsupported queries.
- Embedding service timeout.
- LLM service timeout.
- Malformed structured output.
- Invalid relationship configuration.
- Empty example bank.
- Zero-shot mode.
- Candidate-budget overflow.
- Registry changes requiring index rebuilding.
- Prompt-injection attempts.

---

# 14. Performance and Operational Requirements

The system must provide:

- Offline metric index building.
- Cached metric embeddings.
- Async LLM API calls.
- Configurable timeouts.
- Per-stage latency tracking.
- Token usage tracking.
- Model and prompt version logging.
- Deterministic configuration loading.
- Structured error responses.

Avoid unnecessary infrastructure for the initial 66-metric catalog.

Prefer an in-memory index and local configuration files unless existing repository infrastructure makes another approach simpler.

Do not add a graph database merely for metric relationships.

Do not add a standalone vector database without a demonstrated requirement.

---

# 15. Configuration

Create a central configuration file.

Example:

```yaml
embedding:
  provider: configurable
  model: configurable
  cache_enabled: true

retrieval:
  dense_enabled: true
  lexical_enabled: true
  fusion_method: rrf
  dense_top_k: 15
  lexical_top_k: 15
  fusion_top_k: 20
  mention_retrieval_enabled: false

expansion:
  enabled: true
  max_hops: 1
  max_candidates: 30

reranking:
  metadata_enabled: true
  cross_encoder_enabled: false
  final_top_k: 12

fewshot:
  enabled: true
  strategy: adaptive
  min_examples: 0
  max_examples: 4
  initial_pool_size: 15

llm:
  provider: configurable
  model: configurable
  temperature: 0
  max_retries: 1

evaluation:
  save_traces: true
  report_per_category: true
```

All credentials must come from environment variables or existing secret-management mechanisms.

Do not hardcode API keys.

---

# 16. Definition of Done

The project is complete only when:

- All 66 metrics are loaded from the existing registry.
- All four pipeline stages are implemented.
- Individual stages can be enabled or disabled.
- No existing accounting formulas have been modified.
- Retrieval documents can be rebuilt reproducibly.
- Relationship expansion is bounded and validated.
- Reranking supports metadata and optional cross-encoder.
- Few-shot supports zero-shot, static, similarity, coverage-aware and adaptive modes.
- LLM outputs satisfy a typed schema.
- Invalid metric IDs are rejected.
- Ambiguous and unsupported questions are handled explicitly.
- Integration tests and regression tests pass.
- Evaluation scripts generate quantitative reports.
- Baseline comparisons are available.
- API documentation and usage examples exist.
- The implementation does not introduce unnecessary infrastructure.

No arbitrary metric-accuracy threshold is imposed before the gold evaluation dataset and baseline have been established. Record measured performance and agree on a deployment threshold based on results.

---

# 17. Coding Agent Execution Rules

Follow these rules strictly:

1. Inspect the existing repository before editing.
2. Reuse existing dependencies and architectural patterns where reasonable.
3. Do not rewrite `metrics.py` or change accounting formulas.
4. Implement the milestones in their specified order.
5. Complete unit tests for each milestone before moving on.
6. Keep modules small and independently testable.
7. Use interfaces for external embedding and LLM providers.
8. Never fabricate metric IDs or business rules.
9. Do not silently hardcode benchmark results.
10. Keep new relationship metadata and examples auditable.
11. Record assumptions and unresolved decisions in the project documentation.
12. If a model provider is unavailable, complete the implementation with mocks and mark external integration tests as unverified.
13. Do not claim that an unexecuted test has passed.
14. Maintain a progress checklist with completed deliverables, test results and remaining issues.
15. At the end, provide a repository-level summary of implemented components, configuration instructions, benchmark commands and known limitations.

**Final objective:** A complete, modular and empirically evaluated Metric Selection Engine, ready to be integrated into the existing Text-to-SQL workflow without giving the LLM responsibility for accounting formulas or SQL generation.
