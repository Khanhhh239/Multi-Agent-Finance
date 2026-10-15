# 05 · Thẻ việc P3–P4: sản phẩm, tích hợp, pilot và mở rộng

## P3 — Sản phẩm

### T3.1 Ops DB: phê duyệt, nhật ký, hội thoại
- **Tệp:** `agent4/ops/{schema.sql, store.py, audit.py, approvals.py}`; DB `data/cfo_ops.duckdb` (đường dẫn trong `config.Settings.ops_path`). **Tách khỏi kho sổ cái**; kho sổ cái luôn mở `read_only=True`.
- **Bảng:** `pending_approvals`, `audit_log`, `conversations`, `messages`, `payment_promises`, `credit_flags`, `review_requests` (xem `4_ai_engineering/04` §7).
- **API nội bộ:**
  ```python
  audit.append(actor, event, payload) -> hash       # prev_hash||canonical_json → sha256
  audit.verify_chain() -> (ok, first_bad_id)
  approvals.propose(action_type, params, rationale, requested_by) -> id
  approvals.decide(id, decided_by, approve: bool, comment) -> status      # kiểm tra quyền; người duyệt ≠ người yêu cầu nếu rủi ro cao
  approvals.execute(id)                                                  # handler tất định theo action_type; idempotent
  ```
- **Test:** I3 — "0 hành động không qua duyệt": cố gọi `execute` khi chưa `APPROVED` → lỗi; sửa tay một dòng log → `verify_chain` phát hiện; handler chạy hai lần không nhân đôi.
- **Xong khi:** ba hành động v1 (`record_payment_promise`, `set_credit_hold`, `flag_for_review`) chạy đầu‑cuối.

### T3.2 Phân quyền/gateway
- **Tệp:** `agent4/security/{principal.py, policy.yaml}`.
- **Việc:** `Principal(user_id, role, scope)`; bảng quyền theo chỉ số (`policy.yaml`: chỉ số nào cho vai trò nào; chỉ số nào cần phạm vi); tiêm `scope` vào `engine.query` (T0.5); từ chối có thông điệp rõ; nhật ký mọi từ chối.
- **Test:** I2 — ma trận vai trò × chỉ số × phạm vi (≥ 60 ca).

### T3.3 API
- **Tệp:** `agent4/api/server.py` (FastAPI), `api/schemas.py`.
- **Điểm cuối:**
  | Method | Path | Mô tả |
  |---|---|---|
  | POST | `/v1/chat` | `{conversation_id?, message}` → `AgentReply` (text, blocks, lineage_ids, behavior, suggestions) |
  | GET | `/v1/explain/{lineage_id}` | "Xem cách tính" |
  | GET | `/v1/approvals?status=PENDING` | Danh sách chờ duyệt |
  | POST | `/v1/approvals/{id}/decide` | `{approve, comment}` |
  | GET | `/v1/brief?week=` | Bản tin tuần |
  | GET | `/v1/metrics` | Danh mục chỉ số (cho UI form suy biến) |
  | POST | `/v1/query` | Chế độ form (không LLM): `{metric, period, filters, …}` |
  | GET | `/health` | LLM, DB, phiên bản dữ liệu |
- **Yêu cầu:** xác thực đơn giản (token → `Principal`), CORS cấu hình, mỗi yêu cầu dùng `engine.cursor()`, giới hạn tốc độ, log có `request_id`; không log nội dung nhạy cảm đầy đủ.
- **Test:** `httpx.AsyncClient` + ScriptedClient; test phân quyền; test `/query` hoạt động khi LLM tắt (NFR‑R1).

### T3.4 UI web tối thiểu (`web/`)
- **Phạm vi:** một trang chat; hiển thị khối sự kiện (kỳ, khung, nhãn **tạm tính/khóa sổ**, mốc dữ liệu); nút "Xem cách tính" (gọi explain, hiển thị công thức + chứng từ lớn nhất; văn bản diễn giải bọc/dán nhãn "dữ liệu"); nút chọn khi `clarify`; trang "Chờ duyệt"; nhãn "Do AI tạo"; chế độ form khi LLM lỗi; bảng + biểu đồ cột/đường đơn giản cho `group_by`.
- **Công nghệ gợi ý:** HTML + HTMX hoặc React nhẹ; không cần bản dựng phức tạp.
- **Kiểm thử:** Playwright 5 kịch bản (hỏi, so sánh, hỏi lại, từ chối, duyệt).

### T3.5 Bản tin điều hành tuần
- **Tệp:** `agent/brief.py`, `agent/data/brief_rules.yaml`.
- **Nội dung (tất định, LLM chỉ viết lời dẫn):** (1) tiền & thanh khoản (`cash_and_equivalents`, `cash_coverage_days`, `upcoming_obligations` 15 ngày); (2) công nợ (top quá hạn, thay đổi `overdue_receivables` tuần/tuần); (3) chi phí tăng (`expense_spikes`); (4) lợi nhuận tháng/lũy kế so cùng kỳ; (5) bất thường (`unbalanced_journals`, `unusual_account_movements`); (6) cảnh báo từ Agent 1/2/3 (mock).
- **Xếp hạng:** điểm = |tác động VND| × độ bất thường × độ hành động; chọn top‑5; mỗi mục có nguồn (`lineage_id`).
- **Test (E10):** kho có ca cài → bản tin chứa ≥ 90% ca "phải nêu" và < 20% mục nhiễu.

### T3.6 Adapter Agent 1/2/3 + `orchestrate_agents`
- **Tệp:** `agent4/integrations/{base.py, mock_cashflow.py, mock_risk.py, mock_tax.py}`.
- **Hợp đồng (JSON, pydantic):**
  ```python
  cash_forecast(days:int) -> {"horizon_days","p10","p50","p90":[…],"shortfall_probability","as_of","source":"A1"}
  get_top_alerts(k:int)   -> [{"alert_id","type","score","entity","amount","reason","evidence_ids":[…],"as_of","source":"A2"}]
  tax_exposure_pending()  -> {"fail":n,"review":n,"amount_at_risk","items":[…],"as_of","source":"A3"}
  ```
- **Quy tắc:** chạy song song (`asyncio.gather`), timeout 3 s mỗi agent; số liệu từ adapter được tag `source`, đưa vào tập số cho phép của verifier; nếu một agent lỗi ⇒ bản tin nêu "chưa có dữ liệu từ …".
- **Mock:** dùng `ground_truth` + engine để tạo dữ liệu hợp lý (ví dụ A2 lấy từ `overdue_receivables`).

### T3.7 Text‑to‑SQL có kiểm soát
- **Tệp:** `agent/sql_fallback.py`, `agent/data/schema_card.md`.
- **Bước:** (1) *schema card* ≤ 1.200 token mô tả 8 bảng cho phép (`ar_invoice`, `ar_invoice_line`, `ar_receipt`, `ap_bill`, `ap_payment`, `inventory_txn`, `dim_*` chọn lọc) — **không** cho `gl_entry` thô trừ view hạn chế; (2) LLM sinh SQL qua `format` hoặc công cụ `run_readonly_sql`; (3) `sqlglot` parse: chỉ `SELECT`, whitelist bảng/cột, không hàm nguy hiểm (`read_csv`, `COPY`, `ATTACH`), bắt buộc `LIMIT ≤ 200`; (4) chạy bằng kết nối `read_only` + `timeout 5s` + giới hạn bộ nhớ; (5) kết quả đi qua `render_facts`/verifier như chỉ số; (6) khi câu không thể trả lời bằng lược đồ ⇒ từ chối.
- **Đo:** E9 (exec‑acc, an toàn). Mặc định **tắt** bằng cờ cho đến khi đạt AST‑safety 100%.

---
## P4 — Pilot & mở rộng

### T4.1 Hồ sơ doanh nghiệp tham số hóa (sinh nhiều công ty)
- **Tệp:** `agent4/datagen/profiles/*.yaml`, `datagen/profile.py`, `datagen/run_many.py`.
- **Việc:** theo `2_data/06` §2: đưa hằng số `company.py`/`simulator.py` vào `CompanyProfile`; thêm ≥ 3 họ ngành (dịch vụ, sản xuất nhỏ, bán lẻ) bằng cách tạo lớp sự kiện con (ví dụ không tồn kho ⇒ bỏ `inventory`; sản xuất ⇒ thêm 152/154/155); CLI `python -m agent4.datagen.run_many --profiles profiles/ --seeds 1..30 --out data/multi/`; bảng `registry`.
- **Kiểm thử:** mỗi công ty qua `_validate` (cân đối, đối soát = 0); báo cáo fidelity (`2_data/06` §3.4).

### T4.2 Kiểm thử quy mô
- **Việc:** nhân bản kho (hoặc profile lớn) tới 1M, 5M, 10M dòng; đo p50/p95 cho 10 chỉ số tiêu biểu; thêm chỉ mục/phân vùng/Parquet khi cần; cache kết quả (`data_version`).
- **Xong khi:** NFR‑P2.

### T4.3 Adapter nhập dữ liệu ERP thật
- **Tệp:** `agent4/ingest/{csv_loader.py, mapping.yaml, reconcile.py}`.
- **Việc:** nạp CSV sổ cái chi tiết + công nợ; ánh xạ `account_code` thực tế → chuẩn; dựng `gl_wide`, `dim_*`; báo cáo đối soát với bảng cân đối thử đã chốt (sai lệch từng TK, từng kỳ); danh sách giả định bị vi phạm. Bắt buộc ẩn danh (băm mã/tên đối tác, giữ cấu trúc).
- **Xong khi:** G2.1.

### T4.4 Red‑team mở rộng & demo
- Chạy garak/bộ tự soạn lên `/v1/chat`; cập nhật E8; dựng kịch bản demo 7 cảnh (xem `1_business_analyst/04`); ghi hình dự phòng; kiểm tra chế độ suy biến.

### T4.5 Pilot kinh tế
- Theo `3_evaluation/02` §3: đo 6 tuần trước/sau, ghi nhật ký yêu cầu ad‑hoc, DSO, quá hạn, số lần rút vốn; thu thập phản hồi; điền lại `3_evaluation/03` với số đo thật; **quyết định tiếp tục/dừng**.

---
## Phụ lục — Danh sách tệp cần tạo (đối chiếu nhanh)
```
agent4/agent/{llm,tools,packer,retriever,preprocess,prompts,fewshot,state,validator,render,verifier,orchestrator,policy,guardrails,cli,trace,brief,sql_fallback}.py
agent4/agent/data/{fewshot_bank.jsonl, injection_patterns.yml, brief_rules.yaml, schema_card.md}
agent4/engine/scope.py            agent4/ops/{schema.sql,store,audit,approvals}.py     agent4/security/{principal.py,policy.yaml}
agent4/api/{server,schemas}.py    agent4/integrations/{base,mock_cashflow,mock_risk,mock_tax}.py   agent4/ingest/*
eval/{oracle,run,scorers,report}.py   eval/gen/*   eval/configs/*   eval/experiments/*
tests/{test_metrics_golden,test_invariants,test_periods,test_formatting,test_validator,test_verifier,test_orchestrator,test_guardrails,test_scope,test_approvals,test_api}.py
web/*     train/* (tùy chọn)     docs/5_handoff/{FORMULA_REVIEW.md,DECISIONS.md}
```
