# Module 3: Semantic Query Planning & Plan Validation (`agent4/planning/`)

> **Milestone:** M2 — Query Planning & Clarification  
> **Thư mục mã nguồn:** `agent4/planning/`  
> **Contracts phụ trách:** `query.planning.v1` (Mục 16) và `query.plan-validation.v1` (Mục 17) trong [contracts.md](file:///home/ducquan/Documents/Python/AI-Fin/Multi-Agent-Finance/agent4/contracts.md)  
> **File kiểm thử nghiệm thu:** [tests/contracts/test_planning_and_plan_validation.py](file:///home/ducquan/Documents/Python/AI-Fin/Multi-Agent-Finance/agent4/tests/contracts/test_planning_and_plan_validation.py)

---

## 1. Mục tiêu & Ranh giới Tin cậy (Trust Boundaries)

Module `agent4/planning/` chuyển đổi yêu cầu ngôn ngữ tự nhiên cùng tập `ValidatedMetricSet` thành một kế hoạch truy vấn ngữ nghĩa (`SemanticPlanDraft`), sau đó thẩm định và khóa lại thành đối tượng đáng tin cậy `ValidatedPlan`:
1. **`SemanticPlanDraft` là `untrusted draft`**: Tuyệt đối không chứa câu lệnh SQL (`SELECT`, `DROP`, ...) hay tên bảng vật lý (`gl_wide`, `ar_invoice_line`, `duckdb_tables`).
2. **Nguyên tắc Fail-Closed với sự mơ hồ (`needs_clarification`)**: Khi câu hỏi thiếu khoảng thời gian (`time`), mơ hồ giữa các chỉ tiêu hoặc thiếu thông tin làm thay đổi ý nghĩa nghiệp vụ, Planner bắt buộc trả về `status: "needs_clarification"` kèm `question_for_user` và `unresolved_slots`, tuyệt đối không tự đoán kỳ thời gian để chạy query.
3. **`ValidatedPlan` là Immutable Trust Boundary trước SQL Compiler**: Mọi thông tin bảo mật như `tenant_id`, `catalog_hash`, `policy_hash` chỉ được đóng dấu bởi `Plan Validator` từ `AuthContext` và `MetricCatalog`, không bao giờ lấy từ draft của LLM.

---

## 2. Cấu trúc File trong `agent4/planning/`

```text
agent4/planning/
├── __init__.py
├── planner.py        # Contract 16 (query.planning.v1 - Trích xuất slots & phát hiện needs_clarification)
├── validator.py      # Contract 17 (query.plan-validation.v1 - Thẩm định allowlist, giới hạn & niêm phong ValidatedPlan)
└── clarification.py  # Chế độ hỏi lại chủ động (Structured Clarification, gợi ý choices & ghép câu trả lời đa lượt qua session_id)
```

---

## 3. Đặc tả Kỹ thuật & Hợp đồng Dữ liệu (Contracts 16 & 17)

### 3.1. Query Planning Contract (`query.planning.v1` — `agent4/planning/planner.py`)
- **Input**: `NormalizedQuery` + `ValidatedMetricSet` + `QueryContext`.
- **Output (`SemanticPlanDraft`)**:
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
- **Quy tắc trích xuất Slots & Phát hiện câu hỏi mơ hồ**:
  - **Time slot**:
    - Với metric có `period_type == "flow"` (doanh thu, chi phí, lợi nhuận, ngân sách): yêu cầu `mode = "range"`, `start = "YYYY-MM-DD"`, `end = "YYYY-MM-DD"`, `grain` thuộc `{"month", "quarter", "year"}`.
    - Với metric có `period_type == "snapshot"` (số dư tiền mặt `cash_balance`, phải thu `ar_balance`, phải trả `ap_balance`, dư nợ vay `loan_balance`): yêu cầu `mode = "as_of"`, `as_of = "YYYY-MM-DD"`.
    - Nếu câu hỏi không nêu rõ kỳ thời gian hoặc ngày chốt số dư $\rightarrow$ trả về `status = "needs_clarification"`, `unresolved_slots = ["time"]`, `question_for_user = "..."`.
  - **Dimensions allowlist**:
    - Chỉ cho phép các chiều trong tập `ALLOWED_DIMENSIONS`:
      `{"month", "quarter", "year", "branch_code", "product_line", "department_code", "cost_category", "partner_code", "segment"}`.
  - **Filters allowlist** (khớp dữ liệu thật trong `cfo_warehouse.duckdb`):
    - `branch_code`: `{"HN", "HCM", "DN"}`
    - `product_line`: `{"IT", "OFF", "CON", "SVC"}`
    - `department_code`: `{"BGD", "KD", "MKT", "KT", "KHO", "TCKT", "HCNS"}`
    - `cost_category`: `{"LUONG", "BAOHIEM", "THUONG", "THUE_MB", "DIEN_NUOC", "VIENTHONG", "MARKETING", "VANCHUYEN", "CONGTAC", "TIEPKHACH", "KHAUHAO", "PHANMEM", "VPP", "BAOHIEM_TS", "PHI_NH", "DUPHONG", "VATTU_DV", "THUE_PHI", "KHAC"}`
    - `segment`: `{"GOV", "SME", "DLR", "RET", "ENT"}`
    - `partner_code`: mã đối tác hợp lệ (ví dụ `KH0082`, `KH0140`, `NCC-PP-TN`, `NCC-MK-DG`).
    - Toán tử `op` chỉ thuộc `{"=", "IN"}`.

### 3.2. Semantic Plan Validation Contract (`query.plan-validation.v1` — `agent4/planning/validator.py`)
Thực hiện 7 chốt kiểm tra nghiêm ngặt trước khi tạo `ValidatedPlan`:
1. **Kiểm tra schema & phiên bản**:
   - Đủ 14 trường bắt buộc của `SemanticPlanDraft`, không thừa trường lạ (`enforce_exact_keys`), `plan_version == "1.0"`.
2. **Chặn SQL và tên bảng vật lý trong Draft**:
   - Từ chối cú pháp SQL, định danh bảng vật lý và giá trị ngoài allowlist.
     Áp dụng cả khi draft chỉ yêu cầu làm rõ.
3. **Kiểm tra tập con Metric**:
   - `set(plan_draft["metric_ids"]).issubset(set(validated_metrics["metric_ids"]))`.
4. **Kiểm tra quyền trên `view`**:
   - `plan_draft["view"]` bắt buộc nằm trong `auth_context["allowed_views"]` (nếu vi phạm $\rightarrow$ `forbidden_metric`, `final_status="forbidden"`).
5. **Kiểm tra tính hợp lệ của `time` theo `period_type`**:
   - Nếu metric là `snapshot` nhưng `time["mode"] != "as_of"` hoặc thiếu `as_of` $\rightarrow$ ném `ContractError("invalid_request", final_status="unsupported")`.
   - Nếu metric là `flow` nhưng `time["mode"] != "range"` hoặc thiếu `start`/`end` $\rightarrow$ ném `ContractError("invalid_request", final_status="unsupported")`.
   - Kiểm tra `start <= end` và `(end - start).days <= max_days` (mặc định `max_days = 750` ngày).
6. **Kiểm tra `dimensions`, `filters` và `top_k`**:
   - Mọi chiều trong `dimensions` phải thuộc `ALLOWED_DIMENSIONS` và nằm trong `cap["supported_dimensions"]` của **tất cả** các metric trong plan.
   - Mọi bộ lọc trong `filters` phải có `field` thuộc `ALLOWED_FILTER_FIELDS`, `op` thuộc `{"=", "IN"}`, và `value` không chứa ký tự tiêm nhiễm (`'`, `;`, `--`, `DROP`, `OR 1=1`).
   - Nếu có `top_k`: bắt buộc là số nguyên dương `1 <= top_k <= 100`.
7. **Niêm phong `ValidatedPlan`**:
   - Tự động gán default được phép (ví dụ `operation = "aggregate"` nếu `operation` là `None`, ghi vào `applied_defaults = ["operation=aggregate"]`).
   - Đóng dấu `contract_version = "validated-plan.v1"`, `status = "validated"`, `tenant_id`, `catalog_hash`, `policy_hash`.
   - Lưu `row_cap` tối đa 1000 từ policy phía server. Draft yêu cầu làm rõ
     trả quyết định riêng `PlanClarification`.

### 3.3. Interactive Clarification Mode & Multi-turn Resolution (`query.clarification.v1` — `agent4/planning/clarification.py`)
- **Mục tiêu**: Biến trạng thái `needs_clarification` thành trải nghiệm hỏi lại có hướng dẫn (`guided clarification`) và hỗ trợ người dùng trả lời bổ sung qua `session_id` mà vẫn giữ nguyên các chốt chặn an toàn:
  1. **Structured Clarification Payload (`build_clarification_payload`)**:
     - Giữ lại các slot đã nhận diện được (`partial_interpretation`: `metric_ids`, `dimensions`, `filters`, `view`, `time`) để người dùng thấy hệ thống đã hiểu đúng phần nào.
     - Sinh danh sách `slot_prompts` cho từng slot trong `unresolved_slots` kèm danh sách lựa chọn gợi ý (`choices`) lấy từ `MetricCatalog` (lọc theo `auth_context`) và từ điển allowlist:
       - Mơ hồ `profit` $\rightarrow$ gợi ý `gross_profit` vs `net_profit`.
       - Mơ hồ `margin` $\rightarrow$ gợi ý `gross_margin` vs `net_profit_margin`.
       - Mơ hồ `debt` $\rightarrow$ gợi ý `ar_balance` vs `ap_balance` vs `loan_balance`.
       - Thiếu `time` / `as_of` $\rightarrow$ gợi ý tháng khóa sổ gần nhất (`2026-08`), quý gần nhất (`Quý 3/2026`), hoặc ngày chốt dữ liệu (`2026-10-14`).
  2. **Multi-turn Session Store & Slot Merging (`ClarificationSessionStore`, `resolve_clarification_turn`)**:
     - Lưu trạng thái chờ làm rõ trong `LRUTTLCache(maxsize=500, ttl_seconds=300)` với khóa cô lập `(tenant_id, user_id, session_id)` và giới hạn `max_turns = 3`.
     - Khi user gửi câu trả lời bổ sung kèm `session_id` (ví dụ lượt 1 hỏi *"Doanh thu thuần tại HCM?"*, lượt 2 trả lời *"Tháng 08/2026"*), hệ thống hợp nhất slot mới vào `partial_plan_draft` của lượt 1, sau đó **bắt buộc** đưa bản nháp đã hợp nhất qua `validate_semantic_plan_draft()` với `AuthContext` hiện tại.

---

## 4. Phân rã Milestone 2 $\rightarrow$ Issues $\rightarrow$ Tasks

### Issue M2.1: Xây dựng Semantic Planner (`agent4/planning/planner.py`)
- [x] **Task M2.1.1 — Bộ phân tích thời gian (`parse_time_slot`)**:
  - Hỗ trợ phân tích tháng (`tháng 08/2026` $\rightarrow$ `2026-08-01`..`2026-08-31`), quý (`Quý 2/2026` $\rightarrow$ `2026-04-01`..`2026-06-30`), 6 tháng đầu năm (`2026-01-01`..`2026-06-30`), năm (`năm 2025` $\rightarrow$ `2025-01-01`..`2025-12-31`), và ngày chốt số dư (`tính đến 31/08/2026` $\rightarrow$ `as_of = "2026-08-31"`).
- [x] **Task M2.1.2 — Bộ phân tích chiều, bộ lọc, view & phép toán (`build_semantic_plan_draft`)**:
  - Trích xuất `dimensions`, `filters` (chi nhánh `HN`/`HCM`/`DN`, dòng sản phẩm `IT`/`OFF`/`CON`/`SVC`, phòng ban, khoản mục chi phí, mã đối tác), `view` (`mgmt` hoặc `tax`), `operation` (`aggregate`, `timeseries`, `breakdown`, `ranking`), và `top_k`.
  - Phát hiện khi thiếu `time` để trả về `status = "needs_clarification"`, `unresolved_slots = ["time"]`, kèm câu hỏi làm rõ bằng tiếng Việt hoặc tiếng Anh theo `locale`.

### Issue M2.2: Xây dựng Semantic Plan Validator (`agent4/planning/validator.py`)
- [x] **Task M2.2.1 — Hiện thực hóa hàm `validate_semantic_plan_draft()`**:
  - Kiểm tra 14 trường bắt buộc của `SemanticPlanDraft` bằng `enforce_exact_keys`.
  - Kiểm tra chống nhúng SQL/bảng vật lý.
  - Kiểm tra `snapshot` (`as_of`) vs `flow` (`range`), kiểm tra `start <= end` và `max_days <= 750`.
  - Kiểm tra allowlist cho `dimensions`, `filters` (chặn SQLi qua filter value và dimension), và giới hạn `1 <= top_k <= 100`.
  - Trả về `ValidatedPlan` có đầy đủ `tenant_id`, `catalog_hash`, `policy_hash`, `applied_defaults`.

### Issue M2.3: Chế độ Hỏi lại Chủ động & Giải quyết Đa lượt (`agent4/planning/clarification.py`)
- [ ] **Task M2.3.1 — Hiện thực hóa `build_clarification_payload()`**:
  - Sinh cấu trúc `clarification` gồm `unresolved_slots`, `partial_interpretation`, và `slot_prompts` kèm danh sách `choices` song ngữ (`vi-VN`, `en-US`) được lọc theo quyền `auth_context`.
- [ ] **Task M2.3.2 — Hiện thực hóa `ClarificationSessionStore` & `resolve_clarification_turn()`**:
  - Lưu trạng thái chờ làm rõ theo `(tenant_id, user_id, session_id)` trên `LRUTTLCache` (`ttl_seconds=300`, `max_turns=3`).
  - Ghép câu trả lời bổ sung ở lượt tiếp theo vào các slot còn thiếu của `SemanticPlanDraft` và kiểm định lại qua `validate_semantic_plan_draft()`.
- [ ] **Task M2.3.3 — Kiểm thử Chế độ Hỏi lại (`tests/contracts/test_clarification_mode.py`)**:
  - Kiểm tra sinh `choices` gợi ý đúng với nhóm metric mơ hồ, giải quyết thành công hội thoại đa lượt, chặn truy cập chéo `session_id` giữa các user/tenant và chặn SQL injection trong câu trả lời lượt 2.

---

## 5. Tiêu chí Nghiệm thu & Kiểm thử (Verification)

Chạy câu lệnh kiểm thử cho riêng Module 3:
```bash
.venv/bin/python -m pytest -v \
  tests/contracts/test_planning_and_plan_validation.py \
  tests/contracts/test_clarification_mode.py \
  tests/security/test_security_redteam.py \
  tests/security/test_plan_validation_security.py -k "plan or sql_injection"
```

**Các bài test & câu hỏi Benchmark bắt buộc phải PASS**:
- 5/5 tests trong `TestQueryPlanningAndPlanValidationContracts`:
  - `test_validated_plan_trust_boundary_and_hashes`
  - `test_semantic_plan_draft_rejects_sql_or_physical_tables`
  - `test_planner_needs_clarification_path`
  - `test_snapshot_metric_rejects_invalid_range_mode`
  - `test_dimension_and_filter_allowlist_and_limits`
- Toàn bộ tests trong `tests/contracts/test_clarification_mode.py` (sinh gợi ý hỏi lại, ghép slot đa lượt, cô lập session và chặn injection).
- `test_sql_injection_in_filter_and_dimension_is_blocked` trong `test_security_redteam.py`.
- Các ca production trong `TestProductionPlanValidation` và `test_plan_validation_security.py`.
- 15/15 câu hỏi nhóm `5_ambiguous_needs_clarification` (`BM-076` $\rightarrow$ `BM-090`) trong `data/eval/contract_benchmark_questions.jsonl`.
