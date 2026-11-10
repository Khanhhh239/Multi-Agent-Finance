# Financial Analytics Assistant — Module Contracts

**Version:** 0.1  
**Status:** Draft for contract-first review  
**Last updated:** 2026-11-05

Tài liệu này định nghĩa interface giữa các module. Đây là contract thiết kế, chưa phải implementation.

## 1. Quy ước chung

### 1.1. Nguyên tắc

- Mọi object đều có schema version.
- Unknown field phải bị từ chối ở boundary.
- Module không được sửa input object của module trước.
- Output của LLM luôn là untrusted draft.
- Hash/version phải được truyền qua các boundary cần reproducibility.
- Public error không chứa raw SQL, stack trace, credential hoặc raw financial rows.

### 1.2. Runtime context

```json
{
  "request_id": "req-123",
  "trace_id": "trace-123",
  "tenant_id": "tenant-a",
  "user_id": "user-1",
  "roles": ["finance_analyst"],
  "allowed_views": ["mgmt"],
  "locale": "vi-VN",
  "timezone": "Asia/Ho_Chi_Minh",
  "catalog_hash": "catalog-abc",
  "policy_hash": "policy-def"
}
```

`tenant_id`, `user_id`, `roles`, `allowed_views` và `policy_hash` phải đến từ auth/policy layer, không đến từ user question hoặc LLM.

### 1.3. Common error

```json
{
  "code": "unsupported_metric",
  "stage": "metrics_validation",
  "message": "Metric chưa được hỗ trợ.",
  "retryable": false,
  "details": {}
}
```

### 1.4. Common status

```text
ok
needs_clarification
unsupported
forbidden
rejected
unavailable
```

## 2. Query Intake Contract

**Contract ID:** `query.intake.v1`

### Input

```json
{
  "api_version": "v1",
  "question": "Biên lợi nhuận ròng tháng này là bao nhiêu?",
  "locale": "vi-VN",
  "session_id": null,
  "options": {
    "include_table": true,
    "explain_metrics": true
  }
}
```

### Output: `NormalizedQuery`

```json
{
  "contract_version": "normalized-query.v1",
  "question": "Biên lợi nhuận ròng tháng này là bao nhiêu?",
  "normalized_question": "biên lợi nhuận ròng tháng này là bao nhiêu",
  "locale": "vi-VN",
  "options": {
    "include_table": true,
    "explain_metrics": true
  }
}
```

### Rules

- Question không rỗng và có giới hạn độ dài.
- Normalize whitespace/case nhưng giữ bản gốc để audit có kiểm soát.
- Không parse user-provided tenant, role hoặc authorization claim.
- Prompt injection trong question là input không đáng tin, không phải policy.

### Errors

`invalid_request`, `unsupported_locale`, `question_too_long`.

## 3. Auth and Policy Context Contract

**Contract ID:** `auth.policy-context.v1`

### Input

```text
Authenticated request + identity provider claims + server policy
```

### Output: `AuthContext`

```json
{
  "user_id": "user-1",
  "tenant_id": "tenant-a",
  "roles": ["finance_analyst"],
  "allowed_views": ["mgmt"],
  "allowed_metrics": null,
  "policy_hash": "policy-def"
}
```

### Rules

- Không lấy auth context từ request body.
- Không cho LLM thay đổi policy.
- Policy hash phải được gắn vào `ValidatedPlan`.
- Authorization failure phải fail closed.

## 4. Metric Catalog Contract

**Contract ID:** `metric.catalog.v1`

### Metric definition

```json
{
  "metric_id": "net_profit_margin",
  "label": "Biên lợi nhuận ròng",
  "description": "Lợi nhuận ròng chia cho doanh thu thuần",
  "unit": "%",
  "kind": "ratio",
  "period_type": "flow",
  "supported_views": ["mgmt"],
  "supported_dimensions": ["month", "quarter", "branch"],
  "supported_operations": ["aggregate", "timeseries", "breakdown"],
  "default_view": "mgmt",
  "status": "approved",
  "owner": "finance",
  "catalog_version": "2026.11.1"
}
```

### Required operations

```text
get(metric_id)
contains(metric_id)
get_capability(metric_id)
list_visible_metrics(auth_context)
get_catalog_hash()
```

### Rules

- Catalog là source of truth duy nhất của metric.
- Metric chưa approved không được public cho production selection.
- Formula/handler/source phải được version hóa cùng metric.
- Downstream module không được tự copy hoặc thay đổi business definition.

## 5. Embedding Provider Contract

**Contract ID:** `metric.embedding-provider.v1`

### Input: `EmbeddingRequest`

```json
{
  "texts": ["biên lợi nhuận ròng tháng này là bao nhiêu?"],
  "model_id": "multilingual-embedding-v1",
  "model_version": "2026.10",
  "normalize": true
}
```

### Output: `EmbeddingResponse`

```json
{
  "vectors": [
    {
      "values": [0.013, -0.044, 0.221],
      "dimension": 768,
      "normalized": true
    }
  ],
  "model_id": "multilingual-embedding-v1",
  "model_version": "2026.10",
  "dimension": 768
}
```

### Rules

- Query và index phải dùng cùng model/version/dimension/normalization.
- Batch size và text length phải có giới hạn.
- Không gửi raw financial data nhạy cảm nếu provider chưa được phê duyệt.
- Provider failure là `unavailable`, không phải `unsupported`.

## 6. Metric Document Builder Contract

**Contract ID:** `metric.document-builder.v1`

### Input

```text
Approved MetricCatalogSnapshot
```

Offline builders enumerate the snapshot with `MetricCatalog.list_approved_metrics()`.
This snapshot is for indexing. `list_visible_metrics(auth_context)` governs selection.

### Output: `MetricDocument`

```json
{
  "metric_id": "net_profit_margin",
  "document_text": "Biên lợi nhuận ròng. Tỷ lệ lợi nhuận ròng trên doanh thu thuần. Đơn vị phần trăm. Hỗ trợ theo tháng, quý và chi nhánh.",
  "locale": "vi-VN",
  "catalog_hash": "catalog-abc",
  "document_version": "metric-doc-v2"
}
```

### Rules

- Document mô tả nghiệp vụ, không phải executable SQL.
- Không nhúng transaction data.
- Document phải reproducible từ catalog snapshot.
- Mỗi index build phải lưu catalog hash và document version.

## 7. Dense Metric Retrieval Contract

**Contract ID:** `metric.retrieval.dense.v1`

### Input

```json
{
  "query": "Biên lợi nhuận ròng tháng này là bao nhiêu?",
  "query_embedding": {
    "values": [0.013, -0.044, 0.221],
    "dimension": 768,
    "normalized": true
  },
  "top_k": 15,
  "catalog_hash": "catalog-abc",
  "index_version": "metric-dense-index-v3"
}
```

### Output

```json
{
  "source": "dense",
  "hits": [
    {
      "metric_id": "net_profit_margin",
      "rank": 1,
      "score": 0.912,
      "index_version": "metric-dense-index-v3"
    }
  ]
}
```

### Rules

- Chỉ trả metric ID tồn tại trong catalog/index.
- Score chỉ có ý nghĩa trong cùng retriever/index.
- Dense retrieval không quyết định metric cuối cùng.
- Không được tự tạo candidate khi index không tìm thấy kết quả.

## 8. Lexical Metric Retrieval Contract

**Contract ID:** `metric.retrieval.lexical.v1`

### Input

```json
{
  "query": "biên lợi nhuận ròng tháng này",
  "top_k": 15,
  "index_version": "metric-lexical-index-v2"
}
```

### Output

```json
{
  "source": "lexical",
  "hits": [
    {
      "metric_id": "net_profit_margin",
      "rank": 1,
      "score": 8.42,
      "matched_terms": ["biên lợi nhuận ròng"]
    }
  ]
}
```

### Rules

- Không so sánh lexical score trực tiếp với dense score.
- `matched_terms` chỉ là evidence/debug.
- Không quyết định metric cuối cùng.

## 9. Metric Retrieval Fusion Contract

**Contract ID:** `metric.retrieval.fusion.v1`

### Input

```text
DenseHits + LexicalHits + OptionalMentionHits + FusionConfig
```

### Output

```json
{
  "status": "candidates_found",
  "candidates": [
    {
      "metric_id": "net_profit_margin",
      "rank": 1,
      "retrieval_sources": ["dense", "lexical"],
      "dense_score": 0.912,
      "lexical_score": 8.42,
      "fusion_score": 0.0327
    }
  ],
  "fusion_method": "rrf",
  "fusion_version": "rrf-v1"
}
```

### Rules

- Deduplicate theo `metric_id`.
- Giữ source và score của từng retriever.
- Nếu rỗng, trả `empty_candidates`.
- Fusion chỉ tạo `MetricCandidateSet`, không tạo `ValidatedMetricSet`.

## 10. Metric Reranking Contract

**Contract ID:** `metric.retrieval.rerank.v1`

### Input

```text
NormalizedQuery + MetricCandidateSet + QueryContext + CatalogSnapshot
```

### Output

```json
{
  "ranked_candidates": [
    {
      "metric_id": "net_profit_margin",
      "rank": 1,
      "rerank_score": 0.94,
      "score_components": {
        "label_match": 0.95,
        "view_compatibility": 1.0,
        "language_match": 1.0
      },
      "retrieval_sources": ["dense", "lexical"]
    }
  ],
  "reranker_version": "metadata-reranker-v2"
}
```

### Rules

- Chỉ được thay đổi thứ tự hoặc score candidate.
- Không được tạo metric ID mới.
- Không được bỏ qua authorization.
- Không được biến candidate thành validated metric.

## 11. Metric Retrieval Orchestrator Contract

**Contract ID:** `metric.retrieval.orchestrator.v1`

### Input

```text
NormalizedQuery + CatalogSnapshot + RetrievalConfig + QueryContext
```

### Output: `MetricRetrievalResult`

```json
{
  "status": "candidates_found",
  "query": "Biên lợi nhuận ròng tháng này là bao nhiêu?",
  "candidates": [
    {
      "metric_id": "net_profit_margin",
      "rank": 1,
      "retrieval_sources": ["dense", "lexical"],
      "dense_score": 0.912,
      "lexical_score": 8.42,
      "fusion_score": 0.0327,
      "rerank_score": 0.94
    }
  ],
  "catalog_hash": "catalog-abc",
  "embedding_model": "multilingual-embedding-v1",
  "dense_index_version": "metric-dense-index-v3",
  "lexical_index_version": "metric-lexical-index-v2",
  "reranker_version": "metadata-reranker-v2"
}
```

### Status

```text
candidates_found
empty_candidates
retrieval_unavailable
```

Ở chế độ full catalog, candidate được xếp theo thứ tự catalog sau khi lọc quyền truy cập, với `retrieval_sources=["catalog_full"]`. Các trường score, embedding và phiên bản index là `null` khi tầng tương ứng không chạy.

Ở chế độ online, `AuthContext` do server cung cấp giới hạn tập metric trước khi cắt Top-K. Dense retrieval dùng index offline khớp phiên bản và trả `retrieval_unavailable` khi index thiếu, lỗi thời hoặc provider gặp sự cố. Nếu cấu hình bật mở rộng quan hệ, orchestrator thêm các metric được phép trước khi rerank. Reranker giữ nguyên tập đã nhận.

## 12. Dynamic Few-shot Example Bank Contract

**Contract ID:** `fewshot.example-bank.v1`

### Example record

```json
{
  "example_id": "fs-margin-001",
  "question": "Tỷ suất lợi nhuận ròng quý trước là bao nhiêu?",
  "locale": "vi-VN",
  "intent": "metric_selection",
  "expected_selection": {
    "status": "resolved",
    "metric_ids": ["net_profit_margin"]
  },
  "context_constraints": {
    "supported_views": ["mgmt"],
    "required_dimensions": [],
    "required_time_modes": ["range"]
  },
  "quality_status": "approved",
  "source": "human_reviewed",
  "example_version": "fewshot-v4",
  "token_count": 185
}
```

### Rules

- Chỉ example `approved` mới được dùng production.
- Không lưu raw transaction data trong example.
- Không lưu prompt injection chưa được làm sạch.
- Example phải có version và quality source.
- `decision_tags` và `confusable_metrics` là metadata tùy chọn dùng cho xếp hạng. Prompt chỉ nhận `question` và `expected_selection`.
- Example có output metric ngoài candidate set phải bị loại trong production mode `compatible_only`.

## 13. Dynamic Few-shot Retrieval Contract

**Contract ID:** `fewshot.retrieval.dynamic.v1`

### Input

```json
{
  "question": "Biên lợi nhuận ròng tháng này là bao nhiêu?",
  "locale": "vi-VN",
  "candidate_metric_ids": ["net_profit_margin", "gross_margin"],
  "context": {
    "view": "mgmt"
  },
  "max_examples": 3,
  "token_budget": 2500,
  "selection_strategy": "hybrid",
  "example_bank_version": "fewshot-v4",
  "compatible_only": true
}
```

### Output

```json
{
  "status": "examples_found",
  "examples": [
    {
      "example_id": "fs-margin-001",
      "question": "Tỷ suất lợi nhuận ròng quý trước là bao nhiêu?",
      "expected_selection": {
        "status": "resolved",
        "metric_ids": ["net_profit_margin"]
      },
      "matched_metric_ids": ["net_profit_margin"],
      "similarity_score": 0.91,
      "compatibility_score": 1.0,
      "rank": 1,
      "token_count": 185
    }
  ],
  "total_token_count": 185,
  "example_bank_version": "fewshot-v4",
  "selection_strategy": "hybrid"
}
```

### Rules

- Dynamic few-shot không được mở rộng candidate set.
- Dynamic few-shot không được cấp quyền cho metric.
- Không chọn chính câu hỏi hiện tại.
- Không vượt token budget.
- Budget tính bằng ước lượng bảo thủ trên JSON của ví dụ sẽ gửi vào prompt. Ví dụ phải khớp locale, version và view của request.
- Nên ưu tiên đa dạng intent/time/view nhưng không đánh đổi compatibility.
- `no_compatible_examples` là kết quả hợp lệ, không nhất thiết là system error.
- Production mặc định dùng `compatible_only=true`:

```text
example.expected_selection.metric_ids ⊆ candidate_metric_ids
```

### Status

```text
examples_found
no_compatible_examples
fewshot_unavailable
```

## 14. LLM Metric Selection Contract

**Contract ID:** `metric.selection.llm.v1`

### Input

```json
{
  "question": "Biên lợi nhuận ròng tháng này là bao nhiêu?",
  "candidates": [
    {
      "metric_id": "net_profit_margin",
      "label": "Biên lợi nhuận ròng",
      "description": "Tỷ lệ lợi nhuận ròng trên doanh thu thuần",
      "supported_views": ["mgmt"],
      "supported_dimensions": ["month", "quarter"]
    }
  ],
  "dynamic_fewshot": {
    "examples": []
  },
  "output_schema": "metric-selection-output.v1"
}
```

### Output

```json
{
  "status": "resolved",
  "metric_ids": ["net_profit_margin"],
  "clarification_question": null,
  "unsupported_reason": null
}
```

### Rules

- `metric_ids` phải là subset của candidate IDs.
- Không trả SQL, formula, table name hoặc column name.
- Không tạo metric mới.
- Không tự thay đổi view, tenant hoặc role.
- LLM output luôn phải qua Metrics Validation.
- `metric_ids` gồm các định danh duy nhất. Trạng thái `ambiguous` và `unsupported` phải có danh sách rỗng. Tin nhắn nếu có phải đúng với trạng thái tương ứng.
- Pipeline tích hợp có tối đa một hành động recovery mỗi request. Retry định dạng chỉ dùng lời nhắc schema cố định và không đưa bản nháp lỗi vào prompt.

### Status

```text
resolved
ambiguous
unsupported
```

## 15. Metrics Validation Contract

**Contract ID:** `metric.validation.v1`

### Input

```text
LLMMetricSelection
+ MetricRetrievalResult
+ MetricCatalogSnapshot
+ AuthContext
+ QueryContext
```

### Output: `ValidatedMetricSet`

```json
{
  "status": "validated",
  "metric_ids": ["net_profit_margin"],
  "catalog_hash": "catalog-abc",
  "validated_capabilities": {
    "net_profit_margin": {
      "period_type": "flow",
      "supported_views": ["mgmt"],
      "supported_dimensions": ["month", "quarter"],
      "supported_operations": ["aggregate", "timeseries", "breakdown"]
    }
  },
  "warnings": []
}
```

### Required checks

```text
selected_metric_ids ⊆ retrieved_candidate_metric_ids
selected_metric_ids ⊆ catalog_metric_ids
```

Ngoài ra phải kiểm tra:

- Metric tồn tại và đã approved.
- User có quyền xem metric.
- View được phép.
- Metric có source/handler được kiểm chứng.
- Các metric có period type tương thích.
- Dimension và operation có capability tương ứng.
- `ambiguous` trả `needs_clarification` cùng câu hỏi làm rõ. `unsupported` và bản nháp `resolved` không có metric đều trả lỗi `unsupported_metric`.
- Validator trực tiếp giữ nguyên kiểm tra subset. Nếu bật recovery và mọi metric thiếu đều hiển thị theo policy, pipeline có thể mở rộng tập ứng viên rồi gọi lại Validator với toàn bộ draft và context ban đầu.

### Errors

`unknown_metric`, `metric_outside_candidates`, `forbidden_metric`, `unsupported_metric`, `unsupported_view`, `incompatible_metrics`, `unsupported_data_source`.

## 16. Query Planning Contract

**Contract ID:** `query.planning.v1`

### Input

```text
NormalizedQuery + ValidatedMetricSet + QueryContext
```

### Output: `SemanticPlanDraft`

```json
{
  "plan_version": "1.0",
  "status": "ready",
  "metric_ids": ["net_profit_margin"],
  "time": {
    "mode": "range",
    "start": "2026-09-01",
    "end": "2026-09-30",
    "as_of": null,
    "grain": "month"
  },
  "dimensions": [],
  "filters": [],
  "view": "mgmt",
  "operation": "aggregate",
  "sort": null,
  "top_k": null,
  "comparison": null,
  "question_for_user": null,
  "unresolved_slots": [],
  "reason_code": null
}
```

### Rules

- Không chứa SQL.
- Không chứa physical table name.
- Chỉ sử dụng metric trong `ValidatedMetricSet`.
- Có thể trả `needs_clarification` nếu thiếu kỳ, view hoặc dimension quan trọng.
- Không tự thêm default làm thay đổi business meaning nếu chưa được policy cho phép.
- `build_semantic_plan_draft(normalized_query, validated_metrics, query_context)`
  trả dict đủ 14 trường. Bản nháp vẫn phải qua Plan Validation trước khi dùng downstream.
- Khoảng thời gian dùng ngày ISO và bao gồm cả ngày đầu lẫn ngày cuối. Nửa năm
  dùng grain tháng. Ngày dạng số dùng ngày/tháng/năm cho `vi-VN` và
  tháng/ngày/năm cho `en-US`. Snapshot cần ngày chốt cụ thể, flow cần một kỳ
  có giới hạn. Kỳ thiếu, không hợp lệ hoặc mơ hồ có `time.mode = "none"` và
  các trường ngày và grain bằng `null`.
- Planner giữ các slot đã xác định khi cần làm rõ. Khi metric còn mơ hồ,
  `metric_ids` rỗng. `unresolved_slots` liệt kê các slot cần bổ sung và
  `question_for_user` dùng ngôn ngữ của `NormalizedQuery`. Nếu view không được
  nêu, planner theo mặc định `mgmt` của Metrics Validation. Hai yêu cầu view
  xung đột cần làm rõ.
- Chiều dùng allowlist của module plan. Bộ lọc dùng `{field, op, value}` với
  `=` cho một giá trị và `IN` cho danh sách. Xếp hạng dùng `ranking`,
  `sort = {metric_id, direction}` và, khi được yêu cầu, `top_k` từ 1 đến 100.
  Adapter đánh giá chuyển riêng sang tên chiều, toán tử và `rank` của benchmark v2.
- `comparison` là `null` trong M2.1. Yêu cầu so sánh rõ ràng mà không còn slot
  cần làm rõ có trạng thái `unsupported`. Draft không mang theo câu hỏi gốc,
  câu làm rõ từ model, metadata phân quyền hay định danh vật lý.

## 17. Semantic Plan Validation Contract

**Contract ID:** `query.plan-validation.v1`

### Input

```text
SemanticPlanDraft + ValidatedMetricSet + CatalogSnapshot + AuthContext + Policy
```

### Output: `ValidatedPlan`

```json
{
  "contract_version": "validated-plan.v1",
  "status": "validated",
  "metric_ids": ["net_profit_margin"],
  "time": {"mode": "range", "start": "2026-09-01", "end": "2026-09-30", "as_of": null, "grain": "month"},
  "dimensions": [],
  "filters": [],
  "view": "mgmt",
  "operation": "aggregate",
  "sort": null,
  "top_k": null,
  "comparison": null,
  "row_cap": 1000,
  "tenant_id": "tenant-a",
  "catalog_hash": "catalog-abc",
  "policy_hash": "policy-def",
  "applied_defaults": ["operation=aggregate"]
}
```

### Rules

- `agent4.planning.validator.validate_semantic_plan_draft()` là điểm tạo
  `ValidatedPlan` bất biến của core mới. Ví dụ JSON trên mô tả các giá trị
  trường. Downstream dùng đối tượng đã niêm phong với ngày dạng `date`, tuple
  và các record con bất biến. Dict và kiểu plan của API demo không thuộc contract này.
- Chỉ nhận 14 trường của draft và đúng cấu trúc từng slot. Chặn SQL, định danh
  vật lý và giá trị ngoài allowlist. Metric phải nằm trong `ValidatedMetricSet`
  và vẫn được phê duyệt, hỗ trợ và cấp quyền trong catalog cùng auth hiện tại.
  `tenant_id` và `policy_hash` lấy từ `AuthContext`. `catalog_hash` lấy từ
  catalog hiện tại và phải khớp hash của kết quả chọn metric.
- Flow cần range với grain tháng, quý hoặc năm. Snapshot cần ngày chốt
  as-of. Không trộn hai loại kỳ. Policy có thể hạ giới hạn tối đa 750 ngày
  tính bằng `end - start`, 100 cho `top_k` và 1000 cho `row_cap`.
  Xếp hạng cần chiều và thứ tự theo một metric trong plan. Khi có `top_k`
  thì cần thứ tự. Compiler áp giới hạn dòng hiệu dụng nhỏ hơn giữa hai giới hạn.
- Default được áp là `operation=aggregate` khi operation rỗng và được ghi
  trong `applied_defaults`. `comparison` hiện phải là `null`.
- Draft cần làm rõ trả `PlanClarification` với `status`,
  `question_for_user` và `unresolved_slots`. Chỉ draft sẵn sàng, hợp lệ mới
  được niêm phong.

## 18. SQL Compiler Contract

**Contract ID:** `sql.compiler.v1`

### Input

```text
ValidatedPlan + CatalogSnapshot
```

### Output: `BoundQuery`

```json
{
  "sql": "WITH aggregated AS (...) SELECT ... LIMIT ?",
  "params": ["2026-09-01", "2026-10-01"],
  "metric_ids": ["net_profit_margin"],
  "dimensions": [],
  "units": {
    "net_profit_margin": "%"
  },
  "row_cap": 1000,
  "fingerprint": "sha256:abc",
  "source": "v_mgmt",
  "catalog_hash": "catalog-abc"
}
```

### Rules

- Không nhận raw question hoặc raw LLM output.
- Identifier chỉ lấy từ allowlist/catalog.
- Value dùng bind parameters.
- Chỉ sinh read-only `SELECT`/CTE.
- Luôn có row cap.
- Catalog hash của plan phải khớp catalog hiện tại.

## 19. SQL Safety Validation Contract

**Contract ID:** `sql.safety.v1`

### Input

```text
BoundQuery + DatabasePolicy + RuntimeContext
```

### Output

```json
{
  "status": "allowed",
  "query_fingerprint": "sha256:abc",
  "checks": {
    "read_only": true,
    "single_statement": true,
    "approved_relations": true,
    "approved_columns": true,
    "parameterized": true,
    "row_cap_present": true,
    "tenant_scope_present": true
  }
}
```

### Reject nếu

- Có DML/DDL.
- Có nhiều statement.
- Relation ngoài allowlist.
- Identifier ngoài catalog/policy.
- Literal user-controlled bị nhúng trực tiếp.
- Thiếu tenant predicate hoặc DB-side RLS tương đương.
- Thiếu row cap.
- Hash không khớp.

## 20. SQL Execution Contract

**Contract ID:** `sql.execution.v1`

### Input

```text
SafeBoundQuery + ExecutionPolicy
```

### Output: `ExecutionResult`

```json
{
  "columns": [
    {
      "key": "net_profit_margin",
      "type": "decimal",
      "unit": "%"
    }
  ],
  "rows": [
    {
      "net_profit_margin": "12.45"
    }
  ],
  "row_count": 1,
  "truncated": false,
  "data_watermark": "2026-10-14",
  "execution_ms": 184
}
```

### Rules

- Connection read-only.
- Timeout bắt buộc.
- Row cap bắt buộc.
- `AppConfig` dùng kho MPX10 v3.0.0 tại `data/enterprise-x10-v3/warehouse.duckdb`
  theo mặc định. Có thể chỉ định cặp kho và ground truth tương ứng bằng
  `AGENT4_DB` và `AGENT4_GROUND_TRUTH`.
- Không trả credential, stack trace hoặc raw SQL trong public response.
- Retry giới hạn và chỉ áp dụng cho lỗi hạ tầng retryable.

## 21. Result Validation Contract

**Contract ID:** `result.validation.v1`

### Input

```text
ExecutionResult + ValidatedPlan + MetricCatalog
```

### Output

```json
{
  "status": "valid",
  "result": {},
  "warnings": [],
  "checks": {
    "schema_valid": true,
    "types_valid": true,
    "columns_expected": true,
    "row_count_valid": true,
    "semantic_constraints_valid": true
  }
}
```

### Rules

- Column trả về phải khớp plan.
- Không duplicate column.
- Decimal không được NaN/Infinity.
- Unit phải khớp metric.
- Ratio có thể null nếu denominator bằng zero.
- Phải phát hiện partial data theo watermark.
- Phân biệt `valid`, `no_data`, `partial`, `invalid_result`.

## 22. Answer Generation Contract

**Contract ID:** `answer.generation.v1`

### Input

```text
ValidatedPlan + ValidatedResult + MetricMetadata + Locale + ResponseOptions
```

### Output: `AnswerDraft`

```json
{
  "summary": "Biên lợi nhuận ròng tháng 09/2026 là 12,45%.",
  "claims": [
    {
      "text": "Biên lợi nhuận ròng tháng 09/2026 là 12,45%.",
      "source_columns": ["net_profit_margin"],
      "source_rows": [0]
    }
  ],
  "warnings": [],
  "table_caption": null
}
```

### Rules

- Không tự tính số liệu mới.
- Không thêm metric, period hoặc entity ngoài plan/result.
- Không đưa SQL vào answer.
- Không bỏ qua warning quan trọng.
- Với answer đơn giản, ưu tiên deterministic template hơn LLM.

## 23. Answer Validation Contract

**Contract ID:** `answer.validation.v1`

### Input

```text
AnswerDraft + ValidatedResult + ValidatedPlan
```

### Output

```json
{
  "status": "valid",
  "answer": "Biên lợi nhuận ròng tháng 09/2026 là 12,45%.",
  "validated_claims": [
    {
      "source_columns": ["net_profit_margin"],
      "source_rows": [0],
      "verified": true
    }
  ],
  "warnings": []
}
```

### Reject nếu

- Claim không map được về result.
- Số trong answer khác result.
- Answer nhắc metric không nằm trong plan.
- Answer bỏ qua partial/no-data warning.
- Answer thêm nguyên nhân hoặc kết luận không được dữ liệu chứng minh.

Khi validation fail, dùng fallback template hoặc trả lỗi an toàn; không trả nguyên văn LLM output.

## 24. Final Response Contract

**Contract ID:** `query.response.v1`

```json
{
  "api_version": "v1",
  "request_id": "req-123",
  "status": "ready",
  "error": null,
  "answer": "Biên lợi nhuận ròng tháng 09/2026 là 12,45%.",
  "data": {
    "columns": [],
    "rows": [],
    "row_count": 1,
    "truncated": false
  },
  "interpretation": {
    "metric_ids": ["net_profit_margin"],
    "dimensions": [],
    "view": "mgmt",
    "time": {}
  },
  "provenance": {
    "catalog_hash": "catalog-abc",
    "data_watermark": "2026-10-14",
    "source": "v_mgmt",
    "query_fingerprint": "sha256:abc"
  },
  "warnings": []
}
```

### Final statuses

```text
ready
needs_clarification
unsupported
forbidden
no_data
temporarily_unavailable
error
```

## 25. Observability Contract

**Contract ID:** `observability.pipeline.v1`

Mỗi request nên ghi được:

- `request_id`, `trace_id`.
- Stage name và latency.
- Catalog/index/model/version.
- Candidate count và selected metric IDs.
- Few-shot example IDs, không ghi raw sensitive content nếu không cần.
- Token usage và provider latency.
- Query fingerprint, không nhất thiết ghi raw SQL.
- Result row count, truncated flag và data watermark.
- Final status và error code.

Không ghi:

- Chain-of-thought.
- Credential.
- Raw SQL vào public log.
- Raw financial rows ngoài retention policy.
- Prompt hoặc example chứa dữ liệu nhạy cảm chưa được mask.

## 26. Contract testing requirements

Mỗi contract phải có:

- Schema validation test.
- Happy-path test.
- Empty/ambiguous/unsupported test.
- Invalid field/type test.
- Version compatibility test.
- Adversarial test nếu contract liên quan LLM, SQL hoặc authorization.

Các test tối thiểu cho metric pipeline:

- Dense và lexical retrieval trả candidate hợp lệ.
- Fusion deduplicate đúng.
- Dynamic few-shot không vượt token budget.
- Few-shot không bổ sung metric ngoài candidate set.
- LLM trả metric ngoài candidate set thì bị reject.
- Metric validator chặn metric chưa approved hoặc không có quyền.
- Retrieval unavailable được phân biệt với unsupported.

## 27. Trust-boundary summary

```text
User question
  → untrusted input
LLM metric output
  → untrusted draft
SemanticPlanDraft
  → untrusted draft
ValidatedMetricSet / ValidatedPlan
  → trusted internal objects
BoundQuery
  → must pass SQL Safety Validation
ExecutionResult
  → must pass Result Validation
AnswerDraft
  → must pass Answer Validation
FinalResponse
  → public contract
```
