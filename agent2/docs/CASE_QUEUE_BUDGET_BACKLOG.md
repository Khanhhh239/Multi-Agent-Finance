# Tài liệu R3: Gộp vụ việc, Ngân sách rà soát cấp vụ, Chống gửi trùng và Quản lý Backlog

Tài liệu này mô tả tầng điều phối hàng đợi rà soát cấp vụ (R3) của Agent2 tại doanh nghiệp và cách tách biệt hoàn toàn khỏi phép so sánh 5 giao dịch/kỳ (`selection_comparison.BUDGET = 5`).

## 1. Kiến trúc mô-đun & tích hợp

- Schema & Hợp đồng dữ liệu: [`agent2/sme_fraud/case_queue.schema.json`](../sme_fraud/case_queue.schema.json) (`case-queue-policy/1.0.0`, `coalesced_case`, `financial_summary`, `AlertDecision.decision`, `backlog_reason_code`, `delivery_status`, `case-queue-report/1.0.0`).
- Gộp vụ việc & tách ứng viên/bằng chứng: [`agent2/sme_fraud/case_coalescing.py`](../sme_fraud/case_coalescing.py).
- Chính sách tiếp nhận, xếp hạng ưu tiên & cổng quyết định mở: [`agent2/sme_fraud/case_queue_policy.py`](../sme_fraud/case_queue_policy.py).
- Lưu trữ ACID SQLite, outbox 2 pha, idempotency, backlog & migration: [`agent2/sme_fraud/case_queue_store.py`](../sme_fraud/case_queue_store.py).
- HTTP API xác thực & kiểm soát RBAC (`review` vs `technical`): [`agent2/sme_fraud/case_queue_api.py`](../sme_fraud/case_queue_api.py).
- Gắn vào server & Portal bridge: [`agent2/sme_fraud/review_server.py`](../sme_fraud/review_server.py), [`portal/agent2_bridge.py`](../../portal/agent2_bridge.py).

## 2. Nguyên tắc nghiệp vụ & Gộp vụ

1. **Tách `candidate` và `evidence`** (`R3-02`):
   - Giao dịch kích hoạt luật hành động / hard trigger / điểm ML đủ điều kiện mới nằm trong `candidate_ids`.
   - Giao dịch lịch sử thanh toán trước (ví dụ `T096` trên hóa đơn `HD78`), chứng từ nghĩa vụ, bút toán/giao dịch tham chiếu chỉ nằm trong `evidence_tx_ids`, `evidence_ids`, `source_links`; không bao giờ vào `candidate_ids`, cộng `0.0` điểm (`evidence_adds_score = false`) và tiêu tốn `0` ngân sách.
2. **Khóa gộp & Định danh vụ việc ổn định** (`R3-01`):
   - Khóa gộp: `(tenant_id, company_id, problem_family, obligation_id)`.
   - `stable_case_id` băm từ `[case-identity/1.0.0, tenant_id, company_id, problem_family, obligation_id]` nên độc lập với `snapshot_id`, `run_id`, `analysis_id`, `model_id` và thứ tự bản ghi.
   - Hai nghĩa vụ độc lập có chung `vendor_id`, `recipient_account` hoặc liên kết đồ thị yếu (`weak_graph_context`) **không bao giờ tự gộp** thành một vụ.
3. **Tách số tiền theo `RULE-MONEY-01`**:
   - Tách riêng `obligation_gross_vnd`, `prior_evidence_allocated_vnd`, `candidate_amount_vnd`, `candidate_allocated_vnd`, `net_settled_vnd`, `related_amount_vnd`, `discrepancy_amount_vnd`, giữ nguyên dấu âm cho điều chỉnh/hoàn trả (`contains_negative_adjustment`).
   - `confirmed_loss_vnd` giữ `null` trước khi có kết luận điều tra xác nhận thiệt hại thực.

## 3. Chính sách, Ngân sách cấp vụ & Trạng thái

- **Tách khỏi benchmark giao dịch**: `default_fixture_policy` khai báo `unit = "case"`, `benchmark_transaction_cap_preserved = 5`, `approved_for_production = false`. Các quyết định nghiệp vụ `D-04`, `D-05`, `D-06`, `D-07` vẫn ở trạng thái `OPEN`.
- **Thứ tự đánh giá (`assess_case_eligibility`)**:
  1. Đã gửi fingerprint trọng yếu hiện tại hoặc cập nhật không trọng yếu -> `already_notified`.
  2. Vụ `closed` khi không đủ điều kiện mở lại trọng yếu -> giữ nguyên kết luận, trả `already_notified` (`case_closed_no_material_change`).
  3. Đang giữ `waiting_evidence` thủ công -> `need_evidence` (`waiting_external_evidence`).
  4. Không chấm được (`!scorable`) -> `unscorable` (`unscorable_sources`).
  5. Thiếu nguồn / bằng chứng bắt buộc -> `need_evidence` (`missing_evidence`).
  6. Luật bắt buộc ở chế độ fixture (`mandatory_rules`) -> `mandatory_route`.
  7. Ngưỡng điểm / `hard_trigger` -> `selected` nếu đạt, ngược lại `below_threshold` (`below_admission_threshold`).
- **Không tự đôn cho đủ ngân sách** (`R3-03`): Khi có `0` vụ đạt ngưỡng, hệ thống đưa `0` vụ vào hàng đợi. Khi nhiều vụ đạt ngưỡng vượt `case_budget_limit`, xếp hạng theo `case_priority_key`, cấp phát nguyên tử trong kỳ, phần dư chuyển `budget_deferred` với lý do `budget_exhausted`.
- **Quản lý Backlog**: Các mục chờ lưu `expires_at = NULL` (`auto_expire_backlog = false`, `retention_without_decision_indefinite = true`), hỗ trợ tái đánh giá khi sang kỳ ngân sách mới hoặc khi có nguồn chứng từ bổ sung (`reevaluate_backlog`) kèm audit log đầy đủ.

## 4. Độ tin cậy ACID, Chống gửi trùng, Crash Recovery & Cô lập Shadow

- SQLite `PRAGMA application_id = 1129468741`, `WAL`, `BEGIN IMMEDIATE`, trigger append-only trên `case_revisions`, `alert_decisions`, `case_audit_events`, và ràng buộc `CHECK(reserved_count <= budget_limit)`.
- `delivery_outbox` + `delivery_ledger` 2 pha với khóa chống trùng `(mode_namespace, tenant_id, company_id, policy_version, case_id, material_fingerprint)` và `request_receipts` kiểm tra `Idempotency-Key` (trả `409 IDEMPOTENCY_CONFLICT` nếu trùng key khác payload).
- `recover_outbox()` khôi phục an toàn các bản ghi dở dang ở mọi điểm lỗi (`before_reserve_commit`, `after_reserve_before_sink`, `after_sink_before_ack`) mà không cấp đúp ngân sách hoặc gửi lặp.
- Cô lập hoàn toàn namespace `active` vs `shadow` (`active_queue` vs `shadow_queue`, ngân sách riêng), và cô lập dữ liệu giữa các công ty (`C001` vs `C002`).
- Hỗ trợ nâng cấp schema không mất dữ liệu từ `v1` lên `v2` (`schema_migrations`).

## 5. API & Phân quyền (`RULE-UI-01`)

Các route không nhận query string (`?` trả `400 QUERY_NOT_SUPPORTED`):
- `POST /api/v1/companies/{company_id}/case-queue/evaluate`
- `POST /api/v1/companies/{company_id}/case-queue/recover`
- `POST /api/v1/companies/{company_id}/case-queue/reevaluate-backlog`
- `GET  /api/v1/companies/{company_id}/case-queue/(active|shadow)[/periods/{period_key}][/technical]`
- `GET  /api/v1/companies/{company_id}/case-queue/backlog[/shadow][/technical]`
- `GET  /api/v1/companies/{company_id}/case-queue/cases/{case_id}[/shadow][/technical]`
- `POST /api/v1/companies/{company_id}/case-queue/cases/{case_id}/workflow`

Chế độ mặc định `review` (vai trò `accountant`) ẩn điểm nội bộ, trọng số, xác suất hiệu chuẩn và hash cấu hình; nhánh `/technical` và tham số `policy` tùy biến yêu cầu quyền `director` (`403 TECHNICAL_VIEW_DENIED`).

## 6. Kiểm thử & Nghiệm thu R3

- Chạy bộ kiểm thử đơn vị/tích hợp (19 test cases):
  ```powershell
  $env:PYTHONPATH='D:\agent22\agent2;D:\agent22\shared\finance_input\src;D:\agent22\agent2\tests;D:\agent22\agent2\tests_he'
  D:\agent22\agent2\.venv\Scripts\python.exe -m unittest tests_he.test_case_queue -v
  ```
- Chạy kịch bản nghiệm thu R3 cô lập (sinh báo cáo tại `.runtime/case-queue-acceptance-v1`, `Agent2_Spec_v2_1/evidence/R3/*` và `agent2/reports/case_queue_acceptance.json`):
  ```powershell
  $env:PYTHONPATH='D:\agent22\agent2;D:\agent22\shared\finance_input\src;D:\agent22\agent2\tests;D:\agent22\agent2\tests_he'
  D:\agent22\agent2\.venv\Scripts\python.exe D:\agent22\agent2\scripts\run_case_queue_acceptance.py
  ```

