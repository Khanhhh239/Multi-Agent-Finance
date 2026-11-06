# Module 4: SQL Compiler, SQL Safety Gate & Read-Only DuckDB Execution (`agent4/sql/`)

> **Milestone:** M3 — SQL Compilation, Safety & DuckDB Execution  
> **Thư mục mã nguồn:** `agent4/sql/`  
> **Contracts phụ trách:** `sql.compiler.v1` (Mục 18), `sql.safety.v1` (Mục 19), `sql.execution.v1` (Mục 20) trong [contracts.md](file:///home/ducquan/Documents/Python/AI-Fin/Multi-Agent-Finance/agent4/contracts.md)  
> **File kiểm thử nghiệm thu:** [tests/contracts/test_compiler_safety_execution.py](file:///home/ducquan/Documents/Python/AI-Fin/Multi-Agent-Finance/agent4/tests/contracts/test_compiler_safety_execution.py)

---

## 1. Mục tiêu & Ranh giới Tin cậy (Trust Boundaries)

Module `agent4/sql/` đảm nhận việc biên dịch xác định (deterministic) từ `ValidatedPlan` sang câu lệnh SQL tham số hóa, kiểm duyệt qua 7 chốt an toàn của `SQL Safety Validator`, và thực thi ở chế độ chỉ đọc (`read_only=True`) trên cơ sở dữ liệu [data/cfo_warehouse.duckdb](file:///home/ducquan/Documents/Python/AI-Fin/Multi-Agent-Finance/agent4/data/cfo_warehouse.duckdb):
1. **SQL Compiler chỉ nhận `ValidatedPlan`**: Không bao giờ nhận câu hỏi thô của user hay `SemanticPlanDraft` chưa qua thẩm định.
2. **100% Giá trị lọc phải qua Bind Parameters (`?`)**: Tuyệt đối không nối chuỗi trực tiếp giá trị ngày tháng, mã chi nhánh, mã đối tác vào câu lệnh SQL.
3. **SQL Executor chỉ nhận `SafeBoundQuery` đã qua `SQL Safety Validation`**: Không một câu lệnh SQL nào được chạm tới DuckDB nếu chưa vượt qua đủ 7 chốt kiểm tra của `sql.safety.v1`.
4. **Read-Only ở cả tầng Application và tầng Database Engine**: Kết nối DuckDB luôn khởi tạo với `read_only=True`, có giới hạn dòng (`row_cap <= 1000`) và giới hạn thời gian chạy (`timeout_ms`).

---

## 2. Cấu trúc File trong `agent4/sql/`

```text
agent4/sql/
├── __init__.py
├── compiler.py   # Contract 18 (sql.compiler.v1 - Biên dịch ValidatedPlan -> BoundQuery)
├── safety.py     # Contract 19 (sql.safety.v1 - Cổng kiểm duyệt 7 chốt an toàn SQL)
└── executor.py   # Contract 20 (sql.execution.v1 - Thực thi read-only trên cfo_warehouse.duckdb)
```

---

## 3. Đặc tả Kỹ thuật & Hợp đồng Dữ liệu (Contracts 18, 19, 20)

### 3.1. SQL Compiler Contract (`sql.compiler.v1` — `agent4/sql/compiler.py`)
- **Input**: `ValidatedPlan` (`contract_version == "validated-plan.v1"`, `status == "validated"`) + `MetricCatalog`.
- **Output (`BoundQuery`)**:
  ```json
  {
    "contract_version": "bound-query.v1",
    "sql": "WITH tenant_scoped AS (SELECT * FROM v_mgmt /* tenant:minh-phat */ WHERE posting_date >= CAST(? AS DATE) AND posting_date <= CAST(? AS DATE) AND NOT is_closing) SELECT ... FROM tenant_scoped LIMIT ?",
    "params": ["2026-08-01", "2026-08-31", 1000],
    "metric_ids": ["net_revenue"],
    "dimensions": [],
    "units": {"net_revenue": "VND"},
    "row_cap": 1000,
    "fingerprint": "sha256:a1b2c3d4e5f60123",
    "source": "v_mgmt",
    "catalog_hash": "catalog-abc123def456",
    "tenant_id": "minh-phat"
  }
  ```
- **Quy tắc biên dịch trên `cfo_warehouse.duckdb`**:
  1. **Chọn quan hệ nguồn (`source_relation`)**:
     - Nếu metric có `base_relation == "budget"` (`budget_amount`) $\rightarrow$ truy vấn bảng `budget`.
     - Ngược lại, ánh xạ theo `validated_plan["view"]`: `"mgmt"` $\rightarrow$ `v_mgmt`, `"tax"` $\rightarrow$ `v_tax` (chỉ gồm các dòng `tax_deductible = TRUE`), `"gl"` $\rightarrow$ `v_gl`.
  2. **Ánh xạ chiều phân tích (`DIMENSION_TO_SQL_COL`)**:
     - `"month"`: `year_month` (trên `v_mgmt`/`v_tax`/`v_gl`) hoặc `PRINTF('%04d-%02d', year_no, month_no)` (trên bảng `budget`).
     - `"quarter"`: `CAST(year_no AS VARCHAR) || '-Q' || CAST(quarter_no AS VARCHAR)`.
     - `"year"`: `CAST(year_no AS VARCHAR)`.
     - `"branch_code"`, `"product_line"`, `"department_code"`, `"cost_category"`, `"partner_code"`, `"segment"`: giữ nguyên tên cột đã allowlist.
  3. **Mệnh đề lọc thời gian (`WHERE`)**:
     - Trên bảng `budget`: dùng `(CAST(year_no AS INTEGER) * 100 + month_no) BETWEEN ? AND ?` (bắt buộc `CAST(year_no AS INTEGER)` vì cột `year_no` trong DuckDB có kiểu `SMALLINT`/`INT16`, nếu nhân trực tiếp `2025 * 100` sẽ gây lỗi `OutOfRangeException`).
     - Với metric `snapshot` (`mode == "as_of"`): dùng `posting_date <= CAST(? AS DATE)` (tính lũy kế số dư từ bút toán đầu kỳ `2024-12-31` đến ngày `as_of`).
     - Với metric `flow` (`mode == "range"`): dùng `posting_date >= CAST(? AS DATE) AND posting_date <= CAST(? AS DATE) AND NOT is_closing` (loại bỏ các bút toán kết chuyển cuối kỳ `911` có `is_closing = TRUE`).
  4. **Sắp xếp xác định (`ORDER BY`) & Giới hạn dòng (`LIMIT ?`)**:
     - Nếu có `top_k` hoặc `operation == "ranking"`: `ORDER BY <primary_metric> DESC` (hoặc `ASC`).
     - Nếu có `GROUP BY`: bắt buộc `ORDER BY {', '.join(dimensions)} ASC` trên **tất cả** các chiều để thứ tự dòng trả về từ DuckDB luôn xác định 100% khi breakdown đa chiều (như `BM-053`, `BM-056`).
     - Luôn kết thúc bằng `LIMIT ?` với `effective_cap = min(top_k, row_cap)`.

### 3.2. SQL Safety Validation Contract (`sql.safety.v1` — `agent4/sql/safety.py`)
Kiểm tra độc lập `BoundQuery` qua **7 chốt an toàn bắt buộc**:
1. `read_only`: Câu lệnh sau khi bỏ comment chỉ bắt đầu bằng `SELECT` hoặc `WITH`, và tuyệt đối không chứa bất kỳ từ khóa nào trong:
   `INSERT, UPDATE, DELETE, DROP, ALTER, COPY, ATTACH, DETACH, PRAGMA, CREATE, REPLACE, TRUNCATE, GRANT, REVOKE, CALL, EXPORT, IMPORT, LOAD, INSTALL`.
2. `single_statement`: Không chứa dấu chấm phẩy `;` trong câu lệnh SQL.
3. `approved_relations`: Mọi bảng/view sau từ khóa `FROM` (trừ tên CTE nội bộ) phải thuộc tập `ALLOWED_RELATIONS` (`v_mgmt`, `v_tax`, `v_gl`, `budget`, ...). Chặn hoàn toàn việc truy vấn các bảng hệ thống như `duckdb_tables`, `sqlite_master`.
4. `approved_columns`: Không truy xuất các cột nhạy cảm (`password`, `secret`, `tax_id`, `credit_limit`).
5. `parameterized`: Không có chuỗi literal do user kiểm soát nằm trực tiếp trong SQL; số lượng dấu `?` trong câu lệnh phải bằng đúng `len(params)`.
6. `row_cap_present`: Câu lệnh kết thúc bằng `LIMIT ?` (hoặc số nguyên) và `0 < row_cap <= 1000`.
7. `tenant_scope_present`: `bound_query["tenant_id"] == runtime_context["tenant_id"]`, có đánh dấu phạm vi tenant, và `bound_query["catalog_hash"] == catalog.get_catalog_hash()`.

Nếu bất kỳ chốt nào bằng `False` $\rightarrow$ ném `ContractError("unsafe_sql_rejected", stage="sql_safety", details={"checks": checks})`.

### 3.3. SQL Execution Contract (`sql.execution.v1` — `agent4/sql/executor.py`)
- **Input**: Kết quả `safety_result` (`status == "allowed"` và chứa `safe_bound_query`).
- **Quy trình thực thi trên `cfo_warehouse.duckdb`**:
  1. Kiểm tra đầu vào: nếu không phải output hợp lệ từ `validate_sql_safety` $\rightarrow$ từ chối ngay với `unsafe_sql_rejected`.
  2. Mở kết nối `duckdb.connect(str(db_path), read_only=True)`.
  3. Lấy `data_watermark` từ bảng `company_info` (`SELECT value FROM company_info WHERE key = 'as_of_date'` $\rightarrow$ `"2026-10-14"`).
  4. Thực thi `con.execute(bound["sql"], bound["params"])` và đo thời gian `execution_ms`.
  5. Định dạng từng giá trị số của metric thành chuỗi thập phân 2 chữ số sau dấu phẩy (`f"{Decimal(str(val)):.2f}"`), giữ `None` nếu giá trị SQL là `NULL` (ví dụ chia tỷ số có mẫu số bằng 0).
  6. Trả về `ExecutionResult`:
     ```json
     {
       "columns": [{"key": "net_revenue", "type": "decimal", "unit": "VND"}],
       "rows": [{"net_revenue": "19339316000.00"}],
       "row_count": 1,
       "truncated": false,
       "data_watermark": "2026-10-14",
       "execution_ms": 18
     }
     ```

---

## 4. Phân rã Milestone 3 $\rightarrow$ Issues $\rightarrow$ Tasks

### Issue M3.1: Xây dựng Deterministic SQL Compiler (`agent4/sql/compiler.py`)
- [ ] **Task M3.1.1**: Viết hàm `compile_sql(validated_plan, catalog, row_cap=1000)`:
  - Kiểm tra `validated_plan.get("contract_version") == "validated-plan.v1"` và khớp `catalog_hash`.
  - Ánh xạ `view` sang `v_mgmt` / `v_tax` / `v_gl` hoặc bảng `budget`.
  - Sinh mệnh đề `SELECT`, `WHERE` tham số hóa (`?`), `GROUP BY`, `ORDER BY` xác định trên toàn bộ `dimensions`, và `LIMIT ?`.
  - Tính `fingerprint = "sha256:" + sha256(sql + json.dumps(params))[:16]`.

### Issue M3.2: Xây dựng SQL Safety Validator (`agent4/sql/safety.py`)
- [ ] **Task M3.2.1**: Viết hàm `validate_sql_safety(bound_query, catalog, runtime_context)`:
  - Kiểm tra đủ 7 chốt (`read_only`, `single_statement`, `approved_relations`, `approved_columns`, `parameterized`, `row_cap_present`, `tenant_scope_present`).
  - Trả về `{"status": "allowed", "query_fingerprint": ..., "checks": checks, "safe_bound_query": ...}` hoặc ném `ContractError("unsafe_sql_rejected")`.

### Issue M3.3: Xây dựng Read-Only DuckDB Executor (`agent4/sql/executor.py`)
- [ ] **Task M3.3.1**: Viết hàm `execute_safe_sql(safety_result, db_path, timeout_ms=5000, simulate_outage=False)`:
  - Kết nối `cfo_warehouse.duckdb` với `read_only=True`.
  - Xử lý lỗi `database_unavailable` (`final_status="temporarily_unavailable"`, `retryable=True`) khi DB mất kết nối hoặc quá `timeout_ms`.
  - Trích xuất `data_watermark = "2026-10-14"` và chuẩn hóa `columns`, `rows`.

---

## 5. Tiêu chí Nghiệm thu & Kiểm thử (Verification)

Chạy câu lệnh kiểm thử cho riêng Module 4:
```bash
PYTHONPATH=.venv/lib/python3.13/site-packages pytest -v tests/contracts/test_compiler_safety_execution.py
```

**Các bài test bắt buộc phải PASS (14/14 tests)**:
- `TestSQLCompilerContract::test_compiler_accepts_only_validated_plan`
- `TestSQLCompilerContract::test_compiler_parameterized_and_row_cap`
- `TestSQLSafetyValidationContract::test_safety_gate_allows_valid_bound_query`
- `TestSQLSafetyValidationContract::test_safety_gate_rejects_unsafe_queries` (7 biến thể tấn công: DML/DDL, multi-statement, bảng lạ, nhúng literal, thiếu row cap, sai tenant, sai catalog hash).
- `TestSQLExecutionOnDuckDBContract::test_executor_rejects_unvalidated_query`
- `TestSQLExecutionOnDuckDBContract::test_duckdb_read_only_connection_blocks_writes`
- `TestSQLExecutionOnDuckDBContract::test_execute_mgmt_vs_tax_view_on_real_duckdb` (xác nhận trên `cfo_warehouse.duckdb` tháng `2026-08`: OPEX `v_mgmt = 3028615501.00` vs `v_tax = 2928697501.00`).
- `TestSQLExecutionOnDuckDBContract::test_database_outage_returns_temporarily_unavailable`
