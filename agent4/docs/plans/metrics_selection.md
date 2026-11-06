# Module 2: Metric Retrieval, Dynamic Few-shot, Local Qwen Selection & Metrics Validation (`agent4/metric_selection/`)

> **Milestone:** M1 — Governed Metric Selection Pipeline (Local Qwen)  
> **Thư mục mã nguồn:** `agent4/metric_selection/`  
> **Contracts phụ trách:** Contracts 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15 trong [contracts.md](file:///home/ducquan/Documents/Python/AI-Fin/Multi-Agent-Finance/agent4/contracts.md)  
> **File kiểm thử nghiệm thu:**  
> - [tests/contracts/test_retrieval_and_fewshot.py](file:///home/ducquan/Documents/Python/AI-Fin/Multi-Agent-Finance/agent4/tests/contracts/test_retrieval_and_fewshot.py)  
> - [tests/contracts/test_selection_and_metric_validation.py](file:///home/ducquan/Documents/Python/AI-Fin/Multi-Agent-Finance/agent4/tests/contracts/test_selection_and_metric_validation.py)

---

## 1. Mục tiêu & Ranh giới Tin cậy (Trust Boundaries)

Module `agent4/metric_selection/` chịu trách nhiệm thu hẹp tập ứng viên (candidates), lấy ví dụ hướng dẫn (dynamic few-shot), gọi mô hình ngôn ngữ cục bộ (`Qwen3:4b`) để chọn metric, và thực thi chốt chặn thẩm định cuối cùng (`Metrics Validation`):
1. **Metric Retrieval chỉ tạo `MetricCandidateSet`, không quyết định metric cuối cùng**: Dense retriever, Lexical retriever, RRF Fusion và Reranker chỉ tìm và sắp xếp các metric đã `approved` trong `MetricCatalog`, không bao giờ tự bịa `metric_id` ngoài catalog.
2. **Dynamic Few-shot không được mở rộng candidate set hay cấp quyền**: Ở chế độ production (`compatible_only=True`), mọi ví dụ few-shot được chọn phải thỏa mãn bất biến:
   $$\text{example.expected\_selection.metric\_ids} \subseteq \text{candidate\_metric\_ids}$$
3. **Output của LLM (`Qwen3:4b`) luôn là `untrusted draft`**: LLM chỉ được chọn metric nằm trong `candidate_metric_ids`, không được sinh câu lệnh SQL, công thức tính toán, tên bảng vật lý (`gl_wide`, `v_mgmt`) hay tên cột.
4. **Metrics Validator là Authority cuối cùng cho Metric**: Kiểm tra nghiêm ngặt tính tập con ($\text{selected} \subseteq \text{candidates} \subseteq \text{catalog}$), quyền truy cập `view` (`mgmt` vs `tax`), quyền trên `allowed_metrics`, trạng thái `approved`, `verified_handler`, và tính tương thích `period_type` (không cho phép kết hợp metric `flow` và `snapshot` trong cùng một truy vấn).

---

## 2. Cấu trúc File trong `agent4/metric_selection/`

```text
agent4/metric_selection/
├── __init__.py
├── embedding.py      # Contract 5 (metric.embedding-provider.v1) & Contract 6 (metric.document-builder.v1)
├── dense.py          # Contract 7 (metric.retrieval.dense.v1)
├── lexical.py        # Contract 8 (metric.retrieval.lexical.v1)
├── fusion.py         # Contract 9 (metric.retrieval.fusion.v1 - Reciprocal Rank Fusion)
├── rerank.py         # Contract 10 (metric.retrieval.rerank.v1)
├── orchestrator.py   # Contract 11 (metric.retrieval.orchestrator.v1)
├── fewshot.py        # Contract 12 (fewshot.example-bank.v1) & Contract 13 (fewshot.retrieval.dynamic.v1)
├── llm_selector.py   # Contract 14 (metric.selection.llm.v1 - Tích hợp Qwen3:4b local)
└── validator.py      # Contract 15 (metric.validation.v1 - Ultimate authority cho metric)
```

---

## 3. Đặc tả Kỹ thuật Từng Thành phần & Hợp đồng (Contracts 5 $\rightarrow$ 15)

### 3.1. Embedding Provider & Document Builder (`embedding.py`)
- **`metric.embedding-provider.v1`**:
  - Kiểm tra khớp `model_id`, `model_version`, `dimension` và cờ `normalize=True`.
  - Kiểm tra giới hạn `max_batch_size` (ví dụ 32) và `max_text_length` (ví dụ 1000 ký tự).
  - **Quan trọng**: Khi provider gặp sự cố/timeout, phải ném lỗi có mã `retrieval_unavailable` (`final_status="temporarily_unavailable"`, `retryable=True`), tuyệt đối không trả về `unsupported`.
- **`metric.document-builder.v1`**:
  - Chỉ xây dựng `MetricDocument` cho các metric có `status == "approved"`.
  - Nội dung `document_text` chỉ mô tả nghiệp vụ, đơn vị và chiều hỗ trợ; tuyệt đối không chứa câu lệnh SQL (`SELECT`, `SUM(...)`) hay dữ liệu giao dịch.

### 3.2. Dense, Lexical, RRF Fusion, Reranking & Orchestrator (`dense.py`, `lexical.py`, `fusion.py`, `rerank.py`, `orchestrator.py`)
- **Dense Retrieval (`metric.retrieval.dense.v1`)**:
  - Kiểm tra `catalog_hash` của request phải khớp `catalog.get_catalog_hash()` và kích thước vector khớp `dimension`.
  - Trả về `{"source": "dense", "hits": [{"metric_id", "rank", "score", "index_version"}]}`.
- **Lexical Retrieval (`metric.retrieval.lexical.v1`)**:
  - Đối chiếu từ khóa/cụm từ trong `normalized_question` với `aliases` và `label` của các metric đã `approved`.
  - Trả về `{"source": "lexical", "hits": [{"metric_id", "rank", "score", "matched_terms"}]}`.
- **RRF Fusion (`metric.retrieval.fusion.v1`)**:
  - Gộp kết quả từ `dense` và `lexical`, khử trùng lặp (deduplicate) theo `metric_id`.
  - Tính điểm RRF với hằng số $k = 60$:
    $$\text{fusion\_score}(m) = \sum_{s \in \{\text{dense}, \text{lexical}\}} \frac{1}{60 + \text{rank}_s(m)}$$
  - Giữ nguyên `retrieval_sources`, `dense_score`, `lexical_score`. Nếu cả hai rỗng $\rightarrow$ trả `status: "empty_candidates"`.
- **Metadata Reranker (`metric.retrieval.rerank.v1`)**:
  - Chấm điểm lại dựa trên 3 thành phần: `label_match` (trọng số 0.60), `view_compatibility` (trọng số 0.25), `language_match` (trọng số 0.15).
  - Chỉ được thay đổi thứ tự `rank` và `rerank_score`; không được thêm `metric_id` mới ngoài tập đầu vào.
- **Orchestrator (`metric.retrieval.orchestrator.v1`)**:
  - Trả về đúng 1 trong 3 trạng thái: `candidates_found`, `empty_candidates`, hoặc `retrieval_unavailable`.

### 3.3. Dynamic Few-shot Example Bank & Retrieval (`fewshot.py`)
- **Ràng buộc an toàn trên Example Bank (`fewshot.example-bank.v1`)**:
  - Chỉ sử dụng các ví dụ có `quality_status == "approved"`.
  - Loại bỏ mọi ví dụ chứa mẫu câu tiêm nhiễm (prompt injection).
- **Ràng buộc chọn ví dụ (`fewshot.retrieval.dynamic.v1`)**:
  1. Không bao giờ chọn ví dụ có câu hỏi trùng khớp với câu hỏi hiện tại của user (`ex["question"].strip().lower() != query.strip().lower()`).
  2. Khi `compatible_only=True` (mặc định trên production): chỉ chọn ví dụ mà toàn bộ `expected_selection.metric_ids` nằm trong `candidate_metric_ids`.
  3. Kiểm tra `view` hiện tại nằm trong `context_constraints.supported_views`.
  4. Tổng số token của các ví dụ được chọn không vượt quá `token_budget` (mặc định 2500) và số lượng không vượt quá `max_examples` (mặc định 3).
  5. Trả về `status` thuộc `{"examples_found", "no_compatible_examples", "fewshot_unavailable"}`.

### 3.4. LLM Metric Selection với Local Qwen 4B (`llm_selector.py`)
- **Input (`metric.selection.llm.v1`)**:
  - Câu hỏi của user + Danh sách `candidates` (chỉ gồm `metric_id`, `label`, `description`, `supported_views`, `supported_dimensions`) + Các ví dụ `dynamic_fewshot`.
- **Tích hợp `Qwen3:4b` cục bộ**:
  - Gọi qua Ollama/OpenAI-compatible endpoint với `temperature=0.0` và ép định dạng JSON (`format="json"`):
    ```json
    {
      "status": "resolved",
      "metric_ids": ["net_profit_margin"],
      "clarification_question": null,
      "unsupported_reason": null
    }
    ```
  - Hỗ trợ chế độ deterministic fallback / mock khi chạy unit test offline.
- **Kiểm tra biên trên Output của LLM (`validate_llm_selection_draft`)**:
  - `status` bắt buộc thuộc `{"resolved", "ambiguous", "unsupported"}`.
  - Từ chối ngay lập tức (`code="invalid_request"`) nếu chuỗi JSON trả về chứa bất kỳ từ khóa SQL (`SELECT`, `FROM`, `DROP`, `SUM(`) hoặc tên bảng/cột vật lý (`v_mgmt`, `gl_wide`, `credit_amount`, `debit_amount`).

### 3.5. Metrics Validation Gate (`validator.py` — Authority cuối cùng)
Thực hiện tuần tự 8 bước kiểm tra bắt buộc (Contract 15 `metric.validation.v1`):
1. **Xử lý trạng thái `ambiguous` / `unsupported` từ LLM**:
   - Nếu `status == "ambiguous"` $\rightarrow$ trả về `status: "needs_clarification"` kèm `clarification_question`.
   - Nếu `status == "unsupported"` $\rightarrow$ ném `ContractError("unsupported_metric", final_status="unsupported")`.
2. **Kiểm tra quyền trên `requested_view`**:
   - Nếu `requested_view` không nằm trong `auth_context["allowed_views"]` $\rightarrow$ ném `ContractError("forbidden_metric", final_status="forbidden")`.
3. **Kiểm tra tồn tại trong Catalog**:
   - Nếu `m_id` không có trong `catalog` $\rightarrow$ ném `ContractError("unknown_metric", final_status="unsupported")`.
4. **Kiểm tra bất biến tập con Candidate Set**:
   - Nếu `m_id` không nằm trong `retrieved_candidate_metric_ids` $\rightarrow$ ném `ContractError("metric_outside_candidates", final_status="unsupported")`.
5. **Kiểm tra trạng thái phê duyệt (`approved`)**:
   - Nếu `cap["status"] != "approved"` $\rightarrow$ ném `ContractError("unsupported_metric", final_status="unsupported")`.
6. **Kiểm tra nguồn dữ liệu/handler (`verified_handler`)**:
   - Nếu `not cap["verified_handler"]` $\rightarrow$ ném `ContractError("unsupported_data_source", final_status="unsupported")`.
7. **Kiểm tra quyền truy cập Metric (`allowed_metrics`) & tương thích `view` / `dimension` / `operation`**:
   - Nếu user bị giới hạn `allowed_metrics` và `m_id` không nằm trong đó $\rightarrow$ `forbidden_metric` (`final_status="forbidden"`).
   - Nếu `requested_view` không nằm trong `cap["supported_views"]` $\rightarrow$ `unsupported_view` (`final_status="unsupported"`).
   - Nếu `requested_dimensions` hoặc `requested_operation` không được metric hỗ trợ $\rightarrow$ `unsupported_metric`.
8. **Kiểm tra tính tương thích `period_type` giữa các Metric được chọn**:
   - Nếu tập metric được chọn vừa có `flow` (ví dụ `net_revenue`) vừa có `snapshot` (ví dụ `cash_balance`) $\rightarrow$ ném `ContractError("incompatible_metrics", final_status="unsupported")`.

---

## 4. Phân rã Milestone 1 $\rightarrow$ Issues $\rightarrow$ Tasks

### Issue M1.1: Triển khai Retrieval Pipeline (`embedding.py`, `dense.py`, `lexical.py`, `fusion.py`, `rerank.py`, `orchestrator.py`)
- [ ] **Task M1.1.1**: Viết `EmbeddingProvider` và `build_metric_documents(catalog, locale)` trong `embedding.py`. Đảm bảo ẩn các metric `draft` và xử lý lỗi `retrieval_unavailable` khi provider tắt.
- [ ] **Task M1.1.2**: Viết `dense_retrieve()` trong `dense.py` và `lexical_retrieve()` trong `lexical.py`. Đảm bảo kiểm tra `catalog_hash`, kích thước vector, và chỉ trả về các metric có `status == "approved"`.
- [ ] **Task M1.1.3**: Viết `fuse_candidates(dense_out, lexical_out, rrf_k=60)` trong `fusion.py` gộp ứng viên theo RRF, giữ nguyên điểm gốc và danh sách `retrieval_sources`.
- [ ] **Task M1.1.4**: Viết `rerank_candidates()` trong `rerank.py` và `orchestrate_retrieval()` trong `orchestrator.py` kết nối toàn bộ luồng retrieval.

### Issue M1.2: Triển khai Dynamic Few-shot (`fewshot.py`)
- [ ] **Task M1.2.1**: Tạo kho ví dụ `DEFAULT_FEWSHOT_BANK` tuân thủ schema `fewshot.example-bank.v1` (có cả ví dụ `approved` và `draft` để kiểm chứng bộ lọc).
- [ ] **Task M1.2.2**: Viết hàm `retrieve_dynamic_fewshot(request, example_bank, available)`:
  - Lọc bỏ `quality_status != "approved"`, lọc bỏ câu hỏi chứa mẫu prompt injection, lọc bỏ câu hỏi trùng với câu hỏi hiện tại.
  - Kiểm tra `ex_metrics.issubset(candidate_set)` khi `compatible_only=True`.
  - Cộng dồn `token_count` không vượt quá `token_budget` và cắt theo `max_examples`.

### Issue M1.3: Triển khai Local Qwen Selector & Metrics Validator (`llm_selector.py`, `validator.py`)
- [ ] **Task M1.3.1**: Viết `LLMMetricSelector` trong `llm_selector.py`:
  - Xây dựng prompt truyền `question`, `candidates` và `dynamic_fewshot.examples` cho model `Qwen3:4b`.
  - Viết hàm `validate_llm_selection_draft(draft)` chặn mọi câu lệnh SQL, công thức, tên bảng/cột trong output của LLM.
- [ ] **Task M1.3.2**: Viết hàm `validate_metrics(llm_selection, retrieval_result, catalog, auth_context, query_context)` trong `validator.py` thực thi đầy đủ 8 bước kiểm tra và trả về `ValidatedMetricSet`.

---

## 5. Tiêu chí Nghiệm thu & Kiểm thử (Verification)

Chạy câu lệnh kiểm thử cho riêng Module 2:
```bash
PYTHONPATH=.venv/lib/python3.13/site-packages pytest -v \
  tests/contracts/test_retrieval_and_fewshot.py \
  tests/contracts/test_selection_and_metric_validation.py
```

**Các bài test bắt buộc phải PASS (18/18 tests)**:
- `TestEmbeddingAndDocumentBuilderContracts` (3 tests: kiểm tra dimension/version, lỗi `retrieval_unavailable`, document không chứa SQL).
- `TestMetricRetrievalPipelineContracts` (5 tests: chỉ trả metric approved, RRF deduplication, empty candidates, reranker giữ nguyên tập ứng viên, orchestrator 3 trạng thái).
- `TestDynamicFewShotContracts` (3 tests: `compatible_only`, `token_budget` & loại trừ chính câu hỏi hiện tại, `fewshot_unavailable`).
- `TestLLMMetricSelectionContract` (2 tests: schema output hợp lệ, chặn SQL/tên bảng trong LLM output).
- `TestMetricsValidationContract` (5 tests: happy path, chặn `metric_outside_candidates`, chặn `unknown_metric` / `unsupported_metric` / `unsupported_data_source`, chặn `forbidden_metric` / `unsupported_view`, chặn `incompatible_metrics` khi gộp `flow` và `snapshot`).
