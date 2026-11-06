# Module 5: Result Validation, Grounded Answer Generation & Answer Validation (`agent4/answer/`)

> **Milestone:** M4 (Phần 1) — Result Validation & Grounded Answer  
> **Thư mục mã nguồn:** `agent4/answer/`  
> **Contracts phụ trách:** `result.validation.v1` (Mục 21), `answer.generation.v1` (Mục 22), `answer.validation.v1` (Mục 23) trong [contracts.md](file:///home/ducquan/Documents/Python/AI-Fin/Multi-Agent-Finance/agent4/contracts.md)  
> **File kiểm thử nghiệm thu:**  
> - [tests/contracts/test_result_answer_response.py](file:///home/ducquan/Documents/Python/AI-Fin/Multi-Agent-Finance/agent4/tests/contracts/test_result_answer_response.py)  
> - [tests/security/test_security_redteam.py](file:///home/ducquan/Documents/Python/AI-Fin/Multi-Agent-Finance/agent4/tests/security/test_security_redteam.py)

---

## 1. Mục tiêu & Ranh giới Tin cậy (Trust Boundaries)

Module `agent4/answer/` là lớp chắn cuối cùng đảm bảo tính đúng đắn của số liệu và chống ảo giác (zero hallucination) trước khi trả câu trả lời cho người dùng:
1. **`ExecutionResult` bắt buộc phải qua `Result Validation`**: Kiểm tra schema cột, kiểu số thập phân hợp lệ (không `NaN`/`Infinity`), xử lý mẫu số bằng `0` cho các chỉ số tỷ suất (`ratio_undefined`), phát hiện kỳ không có dữ liệu (`no_data`), và gắn cảnh báo `partial_data_watermark` khi kỳ truy vấn vượt quá tháng đã khóa sổ (`last_closed_month = "2026-08"`) hoặc chạm mốc `data_watermark = "2026-10-14"`.
2. **Answer Generator không được tự tính toán hay thêm thông tin ngoài `ValidatedResult`**: Mọi khẳng định (`claim`) phải chỉ rõ `source_columns` và `source_rows` trong bảng kết quả.
3. **Answer Validator kiểm chứng từng con số và tự động Fallback**:
   - Nếu `AnswerDraft` (từ LLM) chứa số lệch với kết quả DB, nhắc thêm metric không nằm trong `ValidatedPlan`, bỏ sót cảnh báo `partial`, tự suy diễn nguyên nhân kinh doanh (như *"do nắng nóng"*, *"do sự kiện ra mắt"*), hoặc bị nhiễm Indirect Prompt Injection từ DB (`A8_PROMPT_INJECTION` của nhà cung cấp `NCC-MK-DG`) $\rightarrow$ `Answer Validator` từ chối ngay lập tức và chuyển sang **deterministic grounded template**, tuyệt đối không trả nguyên văn output lỗi của LLM ra ngoài.

---

## 2. Cấu trúc File trong `agent4/answer/`

```text
agent4/answer/
├── __init__.py
├── result_validator.py   # Contract 21 (result.validation.v1 - Kiểm định schema, NaN/Inf, partial watermark, no_data)
├── generator.py          # Contract 22 (answer.generation.v1 - Sinh AnswerDraft có claims gắn với dòng/cột)
└── validator.py          # Contract 23 (answer.validation.v1 - Đối chiếu số liệu, chặn suy diễn & fallback an toàn)
```

---

## 3. Đặc tả Kỹ thuật & Hợp đồng Dữ liệu (Contracts 21, 22, 23)

### 3.1. Result Validation Contract (`result.validation.v1` — `agent4/answer/result_validator.py`)
- **Input**: `ExecutionResult` + `ValidatedPlan` + `MetricCatalog`.
- **5 Chốt kiểm tra kỹ thuật (`checks`)**:
  1. `schema_valid`: Không có tên cột trùng lặp trong `columns`.
  2. `columns_expected`: Danh sách `key` của `columns` khớp chính xác với `validated_plan["dimensions"] + validated_plan["metric_ids"]`.
  3. `types_valid`: Mọi giá trị trong cột `type == "decimal"` phải chuyển đổi được sang `Decimal`, không được là `NaN` hay `Infinity`. Nếu giá trị là `None`: chỉ hợp lệ khi metric có `kind == "ratio"` (mẫu số bằng 0 $\rightarrow$ gắn warning `"ratio_undefined"`), ngược lại đánh dấu `types_valid = False`.
  4. `row_count_valid`: `len(rows) == execution_result["row_count"]`.
  5. `semantic_constraints_valid`: `unit` của từng cột metric phải khớp với `catalog.get_capability(m_id)["unit"]` (`"VND"` hoặc `"%"`).
- **Phân loại 4 trạng thái đầu ra (`valid`, `partial`, `no_data`, `invalid_result`)**:
  - Nếu bất kỳ chốt nào trong 5 chốt trên bằng `False` $\rightarrow$ ném `ContractError("invalid_result", stage="result_validation", details={"checks": checks})`.
  - **Phát hiện `no_data`**:
    - Nếu khoảng thời gian truy vấn kết thúc trước ngày mở sổ `2024-12-31` (ví dụ năm `2022`, `2023`) hoặc bắt đầu sau `data_watermark = 2026-10-14` (ví dụ tháng `12/2026`, năm `2028`), hoặc `len(rows) == 0` $\rightarrow$ trả về `status = "no_data"`, `warnings = ["no_data_for_period"]` (hoặc `["no_data_found"]`).
  - **Phát hiện `partial` theo Watermark & Kỳ khóa sổ**:
    - Trong `cfo_warehouse.duckdb`, `last_closed_month = "2026-08"` và `as_of_date = "2026-10-14"` (kỳ `2026-09` và `2026-10` đang `OPEN`).
    - Nếu `end_date` của truy vấn `range` vượt quá `2026-08` (ví dụ truy vấn tháng `2026-09`, `2026-10`) hoặc `as_of_date > 2026-10-14` $\rightarrow$ thêm `"partial_data_watermark"` vào `warnings` và trả về `status = "partial"`.

### 3.2. Answer Generation Contract (`answer.generation.v1` — `agent4/answer/generator.py`)
- **Output (`AnswerDraft`)**:
  ```json
  {
    "summary": "Biên lợi nhuận ròng: 12.45 %.",
    "claims": [
      {
        "text": "Biên lợi nhuận ròng: 12.45 %",
        "source_columns": ["net_profit_margin"],
        "source_rows": [0]
      }
    ],
    "warnings": [],
    "table_caption": "Result (1 rows)"
  }
  ```
- **Quy tắc sinh câu trả lời**:
  - Với `status == "no_data"` hoặc `rows` rỗng: trả về thông báo chuẩn theo `locale` (*"Không có dữ liệu phù hợp cho kỳ truy vấn."* / *"No matching financial data found for the requested period."*), `claims = []`.
  - Với `status in {"valid", "partial"}`: trích xuất giá trị từ `rows[0]` cho từng `metric_id` trong `validated_plan["metric_ids"]`, gắn kèm đơn vị `unit` (`VND` hoặc `%`) và tạo `claim` trỏ tới `source_columns: [m_id]`, `source_rows: [0]`.
  - Nếu `"partial_data_watermark"` nằm trong `warnings`: bắt buộc nối câu cảnh báo watermark (`2026-10-14`) vào cuối `summary` và giữ nguyên danh sách `warnings`.

### 3.3. Answer Validation Contract (`answer.validation.v1` — `agent4/answer/validator.py`)
Thực hiện **5 bước thẩm định nghiêm ngặt** trên `AnswerDraft`:
1. **Chặn rò rỉ SQL & Prompt Injection (bao gồm `A8_PROMPT_INJECTION`)**:
   - Kiểm tra `summary` không chứa từ khóa SQL (`SELECT`, `DROP`, `INSERT`, ...) và không chứa chuỗi tiêm nhiễm (`ignore all previous instructions`, `SYSTEM NOTE TO AI ASSISTANT`, ...).
2. **Chặn suy diễn nguyên nhân ngoài dữ liệu (`CAUSAL_SPECULATION_PATTERNS`)**:
   - Từ chối nếu `summary` tự giải thích nguyên nhân không có trong bảng kết quả số liệu (ví dụ: `"nắng nóng"`, `"sự kiện ra mắt"`, `"chiến dịch bổ sung"`, `"tăng giá"`).
3. **Kiểm tra bảo toàn Warning**:
   - Mọi cảnh báo bắt buộc trong `validated_result["warnings"]` (như `"partial_data_watermark"`, `"ratio_undefined"`) phải có mặt trong `answer_draft["warnings"]`.
4. **Chặn nhắc thêm Metric ngoài `ValidatedPlan`**:
   - Sau khi che (mask) tên nhãn của các metric nằm trong `validated_plan["metric_ids"]`, kiểm tra xem `summary` có nhắc tới tên tiếng Việt hoặc tiếng Anh của bất kỳ metric nào khác trong `MetricCatalog` không (ví dụ: hỏi `net_profit_margin` nhưng lại tự ý bình luận thêm về `operating_expense`).
5. **Đối chiếu từng con số trong `claims` với `ValidatedResult`**:
   - Mỗi phần tử trong `claims` phải có `source_columns` ($\subseteq \text{plan\_metrics}$) và `source_rows` ($0 \le r < \text{len(rows)}$).
   - Giá trị chuỗi thực tế `rows[r][col]` bắt buộc phải xuất hiện chính xác trong `claim["text"]`.

**Cơ chế Fallback an toàn**:
- Nếu `fallback_on_failure=True` (mặc định trên pipeline): khi bất kỳ bước nào trong 5 bước trên thất bại, `validate_answer` tự động gọi `generate_grounded_answer()` để lấy câu trả lời chuẩn từ template xác định, đánh dấu `used_fallback: True` và ghi rõ `rejection_reason`.
- Nếu `fallback_on_failure=False` (dùng khi test trực tiếp bộ chặn của validator): ném `ContractError("ungrounded_answer", stage="answer_validation")`.

---

## 4. Phân rã Milestone 4 (Phần 1) $\rightarrow$ Issues $\rightarrow$ Tasks

### Issue M4.1: Xây dựng `result_validator.py`, `generator.py` và `validator.py`
- [ ] **Task M4.1.1 — Hiện thực hóa `validate_result()` (`agent4/answer/result_validator.py`)**:
  - Kiểm tra 5 chốt `schema_valid`, `types_valid`, `columns_expected`, `row_count_valid`, `semantic_constraints_valid`.
  - Xử lý mẫu số bằng `0` cho metric `ratio` (`val is None` $\rightarrow$ thêm `"ratio_undefined"` vào `warnings`).
  - Đối chiếu ngày truy vấn với `data_start = 2024-12-31`, `last_closed_month = "2026-08"` và `data_watermark = "2026-10-14"` để phân loại chính xác `valid`, `partial`, `no_data`.
- [ ] **Task M4.1.2 — Hiện thực hóa `generate_grounded_answer()` (`agent4/answer/generator.py`)**:
  - Sinh `summary`, `claims` (kèm `source_columns`, `source_rows`), `warnings`, `table_caption` hỗ trợ cả `vi-VN` và `en-US`.
- [ ] **Task M4.1.3 — Hiện thực hóa `validate_answer()` (`agent4/answer/validator.py`)**:
  - Kiểm tra đủ 5 điều kiện reject trong Mục 23 của `contracts.md` và tự động fallback về `generate_grounded_answer()` khi phát hiện vi phạm.

---

## 5. Tiêu chí Nghiệm thu & Kiểm thử (Verification)

Chạy câu lệnh kiểm thử cho riêng Module 5:
```bash
PYTHONPATH=.venv/lib/python3.13/site-packages pytest -v \
  tests/contracts/test_result_answer_response.py \
  tests/security/test_security_redteam.py -k "a8"
```

**Các bài test bắt buộc phải PASS**:
- `TestResultValidationContract::test_result_validation_rejects_nan_infinity_and_duplicate_columns`
- `TestResultValidationContract::test_ratio_zero_denominator_is_valid_with_warning` (Chủ nhật `2026-08-16` có doanh thu = 0 $\rightarrow$ `gross_margin = None` kèm warning `ratio_undefined`).
- `TestResultValidationContract::test_partial_data_watermark_and_no_data_detection` (tháng `2026-10` trả `partial`; năm `2022` trả `no_data`).
- `TestAnswerGenerationAndValidationContracts::test_grounded_answer_passes_validation`
- `TestAnswerGenerationAndValidationContracts::test_answer_validator_rejects_hallucinations_and_falls_back` (chặn sai lệch con số, chặn suy diễn `"sự kiện ra mắt"`, chặn bỏ sót warning `partial_data_watermark`).
- `TestSecurityAndTrustBoundaries::test_indirect_prompt_injection_from_db_a8_is_neutralized` (chặn câu lệnh tiêm nhiễm từ hóa đơn `927` của `NCC-MK-DG` trong `cfo_warehouse.duckdb`).
