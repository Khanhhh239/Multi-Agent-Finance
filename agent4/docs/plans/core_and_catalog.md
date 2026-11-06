# Module 1: Core, Intake, Auth Context & Metric Catalog (`agent4/core/`)

> **Milestone:** M0 — Foundation & Core Contracts  
> **Thư mục mã nguồn:** `agent4/core/`  
> **Contracts phụ trách:** Quy ước chung (Mục 1), `query.intake.v1` (Mục 2), `auth.policy-context.v1` (Mục 3), `metric.catalog.v1` (Mục 4) trong [contracts.md](file:///home/ducquan/Documents/Python/AI-Fin/Multi-Agent-Finance/agent4/contracts.md)  
> **File kiểm thử nghiệm thu:** [tests/contracts/test_intake_auth_catalog.py](file:///home/ducquan/Documents/Python/AI-Fin/Multi-Agent-Finance/agent4/tests/contracts/test_intake_auth_catalog.py)

---

## 1. Mục tiêu & Ranh giới Tin cậy (Trust Boundaries)

Module `agent4/core/` đóng vai trò là cổng tiếp nhận đầu tiên và nguồn chân lý (Source of Truth) về danh mục chỉ tiêu tài chính:
1. **Không tin tưởng dữ liệu đầu vào từ Client**: Câu hỏi (`question`) luôn là `untrusted input`. Mọi trường lạ (`unknown fields`) hoặc thông tin định danh/quyền hạn (`tenant_id`, `roles`, `allowed_views`) do user tự truyền vào request body đều phải bị từ chối ngay tại ranh giới.
2. **Không bao giờ rò rỉ dữ liệu nhạy cảm qua Error**: Mọi lỗi phát sinh trong toàn hệ thống phải đi qua `ContractError` và bị lọc bỏ hoàn toàn câu lệnh SQL (`SELECT`, `WITH`, ...), stack trace, mật khẩu/token và các dòng dữ liệu tài chính thô.
3. **Metric Catalog là Source of Truth duy nhất**: Chỉ những metric có `status == "approved"` và `verified_handler == True` mới được hiển thị và đưa vào pipeline. Mọi thay đổi định nghĩa hoặc biểu thức SQL của metric phải làm thay đổi mã băm `catalog_hash`.

---

## 2. Cấu trúc File trong `agent4/core/`

```text
agent4/core/
├── __init__.py
├── config.py     # Cấu hình hệ thống (DuckDB path, Qwen local endpoint, giới hạn hệ thống)
├── errors.py     # Lớp ContractError, bộ lọc làm sạch thông báo lỗi và kiểm tra unknown fields
├── context.py    # Xử lý Query Intake (query.intake.v1) và Auth/Runtime Context (auth.policy-context.v1)
└── catalog.py    # Quản lý MetricCatalog (metric.catalog.v1), kiểm tra quyền và tính catalog_hash
```

---

## 3. Đặc tả Kỹ thuật & Hợp đồng Dữ liệu (Contracts)

### 3.1. Quy ước Chung & Chuẩn hóa Lỗi (`agent4/core/errors.py`)
- **Cấu trúc `CommonError` (Mục 1.3 `contracts.md`)**:
  ```json
  {
    "code": "unsupported_metric",
    "stage": "metrics_validation",
    "message": "Metric chưa được hỗ trợ.",
    "retryable": false,
    "details": {}
  }
  ```
- **Quy tắc bắt buộc**:
  - Hàm `enforce_exact_keys(obj, required_keys, optional_keys, stage)` kiểm tra từng dictionary đầu vào: thiếu trường bắt buộc hoặc thừa trường lạ đều ném `ContractError(code="invalid_request")`.
  - Không bao giờ sửa trực tiếp (mutate) dictionary đầu vào của module trước.

### 3.2. Query Intake Contract (`query.intake.v1` — `agent4/core/context.py`)
- **Input**:
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
- **Output (`NormalizedQuery`)**:
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
- **Mã lỗi phải xử lý**:
  - `invalid_request`: `api_version != "v1"`, `question` rỗng/chỉ chứa khoảng trắng, hoặc truyền thêm trường lạ (ví dụ `tenant_id`, `roles`, `admin_override`).
  - `unsupported_locale`: `locale` không thuộc `{"vi-VN", "en-US"}` (trạng thái cuối: `unsupported`).
  - `question_too_long`: `len(question) > 500` ký tự.

### 3.3. Auth & Policy Context Contract (`auth.policy-context.v1` — `agent4/core/context.py`)
- **Input**: `idp_claims` (`user_id`, `tenant_id`, `roles`) + `server_policy` (`allowed_views`, `allowed_metrics`, `policy_version`).
- **Output (`AuthContext`)**:
  ```json
  {
    "contract_version": "auth-context.v1",
    "user_id": "user-1",
    "tenant_id": "minh-phat",
    "roles": ["finance_analyst"],
    "allowed_views": ["mgmt"],
    "allowed_metrics": null,
    "policy_hash": "policy-a1b2c3d4e5f6"
  }
  ```
- **Quy tắc bắt buộc**:
  - Bỏ qua hoàn toàn mọi thông tin xác thực nằm trong `request_body` của người dùng.
  - Nếu thiếu `idp_claims`, `server_policy`, `user_id`, `tenant_id`, `roles` hoặc `allowed_views` rỗng $\rightarrow$ fail-closed ngay lập tức với `ContractError(code="forbidden", final_status="forbidden")`.

### 3.4. Metric Catalog Contract (`metric.catalog.v1` — `agent4/core/catalog.py`)
- **Danh sách 13 Metrics đã phê duyệt (`status: "approved"`, `verified_handler: True`) gắn với `cfo_warehouse.duckdb`**:
  1. `net_revenue` — Doanh thu thuần (TK `511%`, `flow`, `VND`, views: `mgmt`, `tax`, `gl`).
  2. `cogs` — Giá vốn hàng bán (TK `632%`, `flow`, `VND`, views: `mgmt`, `tax`, `gl`).
  3. `gross_profit` — Lợi nhuận gộp (`511% - 632%`, `flow`, `VND`, views: `mgmt`, `tax`, `gl`).
  4. `gross_margin` — Biên lợi nhuận gộp (`%`, `ratio`, `flow`, views: `mgmt`, `tax`).
  5. `operating_expense` — Chi phí hoạt động (TK `642%`, `flow`, `VND`, views: `mgmt`, `tax`, `gl`).
  6. `net_profit` — Lợi nhuận ròng (`REVENUE - EXPENSE`, `flow`, `VND`, views: `mgmt`, `tax`).
  7. `net_profit_margin` — Biên lợi nhuận ròng (`%`, `ratio`, `flow`, views: `mgmt`, `tax`).
  8. `payroll_expense` — Chi phí lương và bảo hiểm (`LUONG`, `BAOHIEM`, `THUONG` trên TK `642%`, `flow`, `VND`, views: `mgmt`, `tax`).
  9. `cash_balance` — Số dư tiền và tương đương tiền (TK `111%`, `112%`, `snapshot`, `VND`, views: `mgmt`, `gl`).
  10. `ar_balance` — Số dư nợ phải thu khách hàng (TK `131%`, `snapshot`, `VND`, views: `mgmt`, `gl`).
  11. `ap_balance` — Số dư nợ phải trả nhà cung cấp (TK `331%`, `snapshot`, `VND`, views: `mgmt`, `gl`).
  12. `loan_balance` — Tổng dư nợ vay (TK `341%`, `snapshot`, `VND`, views: `mgmt`, `gl`).
  13. `budget_amount` — Ngân sách kế hoạch (bảng `budget`, `flow`, `VND`, views: `mgmt`).
- **Metrics đặc biệt dùng để kiểm định chốt chặn**:
  - `experimental_cash_burn`: `status: "draft"` (chưa được phê duyệt).
  - `unverified_custom_kpi`: `status: "approved"`, `verified_handler: False` (chưa kiểm chứng nguồn/handler).

---

## 4. Phân rã Milestone 0 $\rightarrow$ Issues $\rightarrow$ Tasks

### Issue M0.1: Xây dựng `config.py`, `errors.py` và `context.py`
- [ ] **Task M0.1.1 — Thiết lập cấu hình hệ thống (`agent4/core/config.py`)**:
  - Định nghĩa `AppConfig` chứa:
    - `db_path: Path = Path("data/cfo_warehouse.duckdb")`
    - `ground_truth_path: Path = Path("data/cfo_warehouse_ground_truth.json")`
    - `qwen_model: str = "qwen3:4b"` (hoặc cấu hình qua biến môi trường `AGENT4_LLM_MODEL`)
    - `qwen_base_url: str = "http://localhost:11434/api/chat"`
    - `max_question_length: int = 500`
    - `default_row_cap: int = 1000`
    - `query_timeout_ms: int = 5000`
- [ ] **Task M0.1.2 — Hiện thực hóa `ContractError` và bộ lọc bảo mật (`agent4/core/errors.py`)**:
  - Viết hàm `_sanitize_message(msg: str) -> str`: dùng regex thay thế mọi chuỗi bắt đầu bằng `SELECT|WITH|INSERT|UPDATE|DELETE|DROP`, mọi chuỗi `Traceback (most recent call last)...`, và mọi chuỗi `password|secret|token|api_key=...` bằng `[REDACTED]`.
  - Viết hàm `_sanitize_details(details: dict) -> dict`: loại bỏ hoàn toàn các khóa `sql`, `raw_sql`, `stack_trace`, `traceback`, `credentials`, `password`, `rows`, `raw_rows`.
  - Viết hàm `enforce_exact_keys(obj, required_keys, optional_keys, stage)`.
- [ ] **Task M0.1.3 — Hiện thực hóa `query_intake` (`agent4/core/context.py`)**:
  - Kiểm tra schema bằng `enforce_exact_keys`.
  - Kiểm tra `api_version == "v1"`, `locale in {"vi-VN", "en-US"}`, `0 < len(question.strip()) <= max_question_length`.
  - Chuẩn hóa `normalized_question`: gộp khoảng trắng thừa, chuyển về chữ thường, cắt dấu câu cuối (`?!.`), nhưng giữ nguyên `question` gốc để phục vụ audit.
  - Sao chép sâu (`copy.deepcopy`) `options` để đảm bảo tính bất biến (immutability).
- [ ] **Task M0.1.4 — Hiện thực hóa `build_auth_context` & `build_runtime_context` (`agent4/core/context.py`)**:
  - Nhận `idp_claims` và `server_policy`, kiểm tra không rỗng, tính `policy_hash = "policy-" + sha256(...)[:12]`.
  - Tuyệt đối không đọc bất kỳ trường nào từ `request_body`.

### Issue M0.2: Xây dựng `MetricCatalog` (`agent4/core/catalog.py`)
- [ ] **Task M0.2.1 — Khởi tạo `MetricCatalog` với 15 metric definitions**:
  - Lưu trữ bản sao bất biến (`deepcopy`) của danh sách metric.
  - Tính `self._catalog_hash = "catalog-" + sha256(json.dumps(metrics, sort_keys=True))[:12]`.
- [ ] **Task M0.2.2 — Hiện thực hóa 5 phương thức bắt buộc của Contract 4**:
  - `get(metric_id: str) -> dict | None`: trả về bản sao `deepcopy` của metric.
  - `contains(metric_id: str) -> bool`: kiểm tra sự tồn tại của `metric_id`.
  - `get_capability(metric_id: str) -> dict`: trả về `unit`, `kind`, `period_type`, `supported_views`, `supported_dimensions`, `supported_operations`, `default_view`, `status`, `verified_handler`; ném `ContractError("unknown_metric")` nếu không tồn tại.
  - `list_visible_metrics(auth_context: dict) -> list[dict]`: lọc chỉ giữ lại các metric có `status == "approved"`, `verified_handler == True`, nằm trong `allowed_metrics` (nếu có giới hạn), và có giao tập khác rỗng giữa `supported_views` với `auth_context["allowed_views"]`.
  - `get_catalog_hash() -> str`: trả về mã băm hiện tại của catalog.

---

## 5. Tiêu chí Nghiệm thu & Kiểm thử (Verification)

Chạy câu lệnh kiểm thử cho riêng Module 1:
```bash
PYTHONPATH=.venv/lib/python3.13/site-packages pytest -v tests/contracts/test_intake_auth_catalog.py
```

**Các bài test bắt buộc phải PASS (11/11 tests)**:
- `TestGeneralConventions::test_reject_unknown_fields_at_boundary`
- `TestGeneralConventions::test_input_immutability`
- `TestGeneralConventions::test_common_error_sanitization`
- `TestQueryIntakeContract::test_intake_happy_path_vi_and_en`
- `TestQueryIntakeContract::test_intake_errors`
- `TestQueryIntakeContract::test_intake_rejects_embedded_auth_claims`
- `TestAuthAndPolicyContextContract::test_auth_context_server_sourced_only`
- `TestAuthAndPolicyContextContract::test_auth_context_fail_closed`
- `TestMetricCatalogContract::test_catalog_operations`
- `TestMetricCatalogContract::test_unapproved_and_unverified_metrics_hidden`
- `TestMetricCatalogContract::test_catalog_hash_reproducibility`
