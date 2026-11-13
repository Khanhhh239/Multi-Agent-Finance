# Module 6: End-to-End Pipeline Orchestrator, Observability, FastAPI & Benchmark (`agent4/pipeline.py`, `agent4/api.py`)

> **Milestone:** M4 (Phần 2) — End-to-End Orchestration, Observability & Benchmark Sign-off  
> **File mã nguồn:** `agent4/pipeline.py`, `agent4/api.py`, `scripts/evaluate_contract_benchmark.py`  
> **Contracts phụ trách:** `query.response.v1` (Mục 24) và `observability.pipeline.v1` (Mục 25) trong [contracts.md](file:///home/ducquan/Documents/Python/AI-Fin/Multi-Agent-Finance/agent4/contracts.md)  
> **File kiểm thử nghiệm thu:**  
> - [tests/contracts/test_result_answer_response.py](file:///home/ducquan/Documents/Python/AI-Fin/Multi-Agent-Finance/agent4/tests/contracts/test_result_answer_response.py)  
> - [tests/benchmark/test_e2e_benchmark_db.py](file:///home/ducquan/Documents/Python/AI-Fin/Multi-Agent-Finance/agent4/tests/benchmark/test_e2e_benchmark_db.py)

---

## 1. Mục tiêu & Trách nhiệm của Module

Module Orchestrator & API kết nối toàn bộ 5 module trước đó (`core`, `metric_selection`, `planning`, `sql`, `answer`) thành một luồng xử lý thống nhất, đóng gói phản hồi theo đúng hợp đồng công khai `query.response.v1` và ghi nhận telemetry theo `observability.pipeline.v1`:
1. **Xử lý trọn vẹn 7 trạng thái cuối (`FINAL_STATUSES`)**:
   - `ready`: Truy vấn thành công, đã qua toàn bộ 9 cổng kiểm duyệt, có số liệu và `provenance` đầy đủ.
   - `needs_clarification`: Câu hỏi mơ hồ về metric hoặc thiếu kỳ thời gian, trả câu hỏi làm rõ cho user.
   - `unsupported`: Yêu cầu ngoài phạm vi MVP (forecasting, tạo công thức mới, ghi dữ liệu, locale không hỗ trợ, metric chưa duyệt).
   - `forbidden`: User không có quyền truy cập view (`tax`) hoặc metric bị giới hạn (`allowed_metrics`).
   - `no_data`: Truy vấn hợp lệ nhưng kỳ truy vấn không có dữ liệu trong `cfo_warehouse.duckdb` (ví dụ năm 2022, 2028).
   - `temporarily_unavailable`: Embedding provider hoặc DuckDB tạm thời không sẵn sàng / quá timeout.
   - `error`: Lỗi hệ thống hoặc vi phạm contract không thể phục hồi an toàn.
2. **Đảm bảo đầy đủ `provenance`**: Mọi phản hồi `ready` bắt buộc có `catalog_hash`, `data_watermark` (`"2026-10-14"`), `source` (`"v_mgmt"`, `"v_tax"`, `"budget"`), và `query_fingerprint` (`"sha256:..."`).
3. **Observability an toàn (Zero Sensitive Leak)**: Bản ghi log/trace theo dõi độ trễ từng stage, số lượng ứng viên, các metric đã chọn, mã ví dụ few-shot, nhưng tuyệt đối **không** ghi Chain-of-Thought, credential, câu lệnh SQL thô hay các dòng dữ liệu tài chính thô.

---

## 2. Cấu trúc File & Luồng Kết Nối

```text
agent4/
├── pipeline.py                         # Hàm điều phối End-to-End run_governed_pipeline()
└── api.py                              # FastAPI application (POST /v1/query, GET /healthz)

scripts/
└── evaluate_contract_benchmark.py      # Script sinh & chấm điểm tự động 120 câu hỏi Benchmark

data/eval/
└── contract_benchmark_questions.jsonl  # Bộ 120 câu hỏi Benchmark chuẩn hóa qua 8 categories
```

---

## 3. Đặc tả Kỹ thuật & Hợp đồng Dữ liệu (Contracts 24 & 25)

### 3.1. Final Response Contract (`query.response.v1` — `agent4/pipeline.py`)
```json
{
  "api_version": "v1",
  "request_id": "req-123",
  "status": "ready",
  "error": null,
  "answer": "Doanh thu thuần: 19339316000.00 VND.",
  "data": {
    "columns": [
      {"key": "net_revenue", "type": "decimal", "unit": "VND"}
    ],
    "rows": [
      {"net_revenue": "19339316000.00"}
    ],
    "row_count": 1,
    "truncated": false
  },
  "interpretation": {
    "metric_ids": ["net_revenue"],
    "dimensions": [],
    "view": "mgmt",
    "time": {
      "mode": "range",
      "start": "2026-08-01",
      "end": "2026-08-31",
      "as_of": null,
      "grain": "month"
    }
  },
  "provenance": {
    "catalog_hash": "catalog-abc123def456",
    "data_watermark": "2026-10-14",
    "source": "v_mgmt",
    "query_fingerprint": "sha256:1234567890abcdef"
  },
  "warnings": []
}
```
- Nếu `options.include_table == False`: trường `data.columns` và `data.rows` trả về mảng rỗng `[]`, nhưng vẫn giữ `row_count` và `truncated`.
- Nếu `status` là lỗi (`unsupported`, `forbidden`, `temporarily_unavailable`, `error`): trường `error` chứa đối tượng `CommonError` đã được làm sạch (`code`, `stage`, `message`, `retryable`, `details`), còn `data` và `provenance` là `null`.
- **Tích hợp Opt-in `evidence` (Preview Evidence — `evidence.preview.v1`)**:
  - Khi `options.include_evidence_preview == True` (hoặc khi bật chế độ trả kèm bằng chứng đối chiếu), `build_final_response()` đính kèm khóa `"evidence"` từ `agent4/answer/evidence.py` gồm `claim_citations`, `preview_table` (`sample_rows` tối đa 5 dòng), `metric_explanations` và `verification_badge`. Mặc định giữ nguyên đúng 9 khóa gốc của `query.response.v1` để tương thích 100% với các bài kiểm thử schema nghiêm ngặt.
- **Tích hợp Opt-in `clarification` (Chế độ hỏi lại có hướng dẫn — `query.clarification.v1`)**:
  - Khi `status == "needs_clarification"` và `options.clarification_mode == "guided"` (hoặc khi request có `session_id`), đính kèm khối `"clarification"` từ `agent4/planning/clarification.py` chứa `unresolved_slots`, `partial_interpretation` và `slot_prompts` (kèm `choices`).

### 3.2. Observability Contract (`observability.pipeline.v1` — `agent4/pipeline.py`)
```json
{
  "contract_version": "observability.pipeline.v1",
  "request_id": "req-001",
  "trace_id": "trace-001",
  "stage_latencies_ms": {
    "query_intake": 1,
    "metric_retrieval": 8,
    "fewshot_retrieval": 2,
    "llm_selection": 120,
    "metrics_validation": 1,
    "query_planning": 45,
    "plan_validation": 1,
    "sql_compilation": 1,
    "sql_safety": 1,
    "sql_execution": 18,
    "result_validation": 1,
    "answer_generation": 2,
    "answer_validation": 1
  },
  "catalog_hash": "catalog-abc123def456",
  "embedding_model": "multilingual-embedding-v1",
  "candidate_count": 5,
  "selected_metric_ids": ["net_revenue"],
  "fewshot_example_ids": ["fs-rev-001"],
  "token_usage": 410,
  "query_fingerprint": "sha256:1234567890abcdef",
  "row_count": 1,
  "truncated": false,
  "data_watermark": "2026-10-14",
  "final_status": "ready",
  "error_code": null
}
```
- Hỗ trợ ghi nhận bổ sung chỉ số hiệu quả bộ nhớ đệm (`cache_stats`: `embedding_hit`, `selection_hit`, `sql_result_hit`, `active_entries`, `estimated_memory_kb`) phục vụ đo lường tối ưu hóa thời gian và bộ nhớ.

---

## 4. Phân rã Milestone 4 (Phần 2) $\rightarrow$ Issues $\rightarrow$ Tasks

### Issue M4.2: Xây dựng Pipeline Orchestrator & FastAPI Endpoint (`agent4/pipeline.py`, `agent4/api.py`)
- [ ] **Task M4.2.1 — Hiện thực hóa `build_final_response()` và `build_observability_record()` (`agent4/pipeline.py`)**:
  - Kiểm tra `status in FINAL_STATUSES`.
  - Đóng gói `data`, `interpretation`, `provenance`, `warnings`, và đính kèm có điều kiện `evidence` (`evidence.preview.v1`) / `clarification` (`query.clarification.v1`).
  - Tạo bản ghi observability (kèm `cache_stats` khi bật) không chứa bất kỳ khóa nhạy cảm nào (`sql`, `rows`, `chain_of_thought`, `credentials`).
- [ ] **Task M4.2.2 — Hiện thực hóa hàm điều phối `run_governed_pipeline(request_payload, idp_claims, server_policy)` (`agent4/pipeline.py`)**:
  - Chạy tuần tự từ Bước 1 (`query_intake` & `build_auth_context`) đến Bước 9 (`validate_answer`, `build_evidence_preview` & `build_final_response`), đo thời gian từng bước vào `stage_latencies_ms`.
  - Kết nối `ClarificationSessionStore` (khi request có `session_id`) để hỗ trợ hội thoại làm rõ đa lượt (`M2.3`) và kết nối Multi-Tier Governed Cache (`L1`/`L2`/`L3` từ `M1.4` & `M3.3`).
  - Bắt mọi `ContractError` ở bất kỳ tầng nào và chuyển thành `FinalResponse` có `status = exc.final_status` và `error = exc.to_dict()`.
- [ ] **Task M4.2.3 — Xây dựng FastAPI Endpoint (`agent4/api.py`)**:
  - Tạo endpoint `POST /v1/query` nhận body theo `query.intake.v1`, lấy `AuthContext` từ dependency xác thực của server, gọi `run_governed_pipeline()` và trả về JSON `query.response.v1`.

### Issue M4.3: Benchmark dev v2 và regression snapshot v1

Benchmark dev dùng 140 ca v2 với `vals/run_eval.py` và production adapter
`agent4.eval_adapter:predict`. Bộ 120 ca v1 bên dưới được giữ làm fixture
regression. Xem [báo cáo M4.3](../../reports/issues/M4.3_verification.md) để
đối chiếu kết quả dev và các cổng phát hành còn mở.
- [ ] **Task M4.3.1 — Kiểm định 8 Nhóm Câu Hỏi Benchmark (120 câu)**:
  1. `1_single_multi_metric_aggregate` (`BM-001` $\rightarrow$ `BM-020`, 20 câu): Tính 1 hoặc nhiều metric tương thích (`flow` hoặc `snapshot`).
  2. `2_timeseries_and_comparison` (`BM-021` $\rightarrow$ `BM-040`, 20 câu): Chuỗi thời gian theo tháng/quý/năm, so sánh kỳ và phát hiện `partial_data_watermark` ở tháng `2026-10`.
  3. `3_dimensional_breakdown_filter_topk` (`BM-041` $\rightarrow$ `BM-060`, 20 câu): Breakdown theo chi nhánh, dòng sản phẩm, phòng ban, khoản mục chi phí, phân khúc và xếp hạng Top-K.
  4. `4_business_views_and_ground_truth` (`BM-061` $\rightarrow$ `BM-075`, 15 câu): Đối chiếu chênh lệch giữa `v_mgmt` và `v_tax`, kiểm tra các sự kiện thật `A1`, `A2`, `A3`, `A7`, `A9`, `A10`, `LIQ_*` trong `cfo_warehouse.duckdb`.
  5. `5_ambiguous_needs_clarification` (`BM-076` $\rightarrow$ `BM-090`, 15 câu): Câu hỏi thiếu thời gian hoặc mơ hồ giữa các metric $\rightarrow$ trả về `needs_clarification`.
  6. `6_unsupported_out_of_catalog` (`BM-091` $\rightarrow$ `BM-102`, 12 câu): Yêu cầu dự báo (forecast), tư vấn chiến lược, ghi/xóa sổ cái, hoặc metric ngoài catalog $\rightarrow$ trả về `unsupported`.
  7. `7_no_data_and_edge_cases` (`BM-103` $\rightarrow$ `BM-110`, 8 câu): Kỳ năm `2021`–`2023` hoặc `2028` trả về `no_data`; ngày Chủ nhật `16/08/2026` có doanh thu bằng 0 trả về `ratio = null` kèm warning `ratio_undefined`.
  8. `8_authorization_and_security` (`BM-111` $\rightarrow$ `BM-120`, 10 câu): Chặn user chỉ có quyền `mgmt` truy cập `tax` (`forbidden`), chặn Direct Prompt Injection / DDL SQLi (`unsupported`), và khử độc Indirect Prompt Injection từ nhà cung cấp `NCC-MK-DG` (`A8_PROMPT_INJECTION`).

---

## 5. Tiêu chí Nghiệm thu Toàn Hệ thống (Final Acceptance Commands)

1. **Chạy toàn bộ 180 bài kiểm thử (Contract + Security + E2E Benchmark)**:
   ```bash
   PYTHONPATH=.venv/lib/python3.13/site-packages pytest -v tests
   ```
   - Yêu cầu: **180/180 passed (100%)**.

2. **Chạy Script Đánh giá Benchmark 120 câu hỏi**:
   ```bash
   PYTHONPATH=.venv/lib/python3.13/site-packages python3 scripts/evaluate_contract_benchmark.py
   ```
   - Yêu cầu: **`total_questions: 120`, `passed_questions: 120`, `accuracy: 1.0` (100%)** trên tất cả 8 nhóm.
