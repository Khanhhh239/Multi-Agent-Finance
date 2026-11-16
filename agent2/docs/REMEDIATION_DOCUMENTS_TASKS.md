# Quản lý hồ sơ/chứng từ và công việc khắc phục sau rà soát (R4)

## 1. Phạm vi và nguyên tắc thiết kế

Luồng R4 bổ sung vòng đời xử lý hậu kiểm sau khi mở vụ việc:

```
Mở vụ việc → Đánh giá checklist chứng từ theo nhóm vấn đề & nguồn
→ Yêu cầu bổ sung / Giao việc ActionTask (kèm người/bộ phận & hạn)
→ Nộp kết quả + tải chứng từ bổ sung (pending_verification, có phiên bản)
→ Người có quyền evidence.verify kiểm tra & xác minh chứng từ (present/rejected)
→ Xác nhận hoàn tất ActionTask hoặc Yêu cầu làm lại / Mở lại (lưu đủ lịch sử)
```

Ba trạng thái được quản lý **độc lập**:

1. **Kết luận & vòng đời vụ việc** (`Case.case_workflow_status`: `new`, `in_review`, `waiting_evidence`, `closed`; `Case.case_resolution`: `null`, `confirmed_risk`, `legitimate`, `inconclusive`).
2. **Hồ sơ/chứng từ** (`DocumentChecklist.item_status`: `unknown`, `missing`, `pending_verification`, `present`, `not_applicable`; và trạng thái xác minh từng tệp `pending_verification`, `present`, `rejected`).
3. **Công việc khắc phục** (`ActionTask.status`: `open`, `in_progress`, `waiting_external`, `completed`, `cancelled`).

Ràng buộc bắt buộc:
- Đóng vụ (`closed`) **không** tự đóng hoặc hoàn tất `ActionTask`.
- Hoàn tất `ActionTask` **không** tự sinh nhãn huấn luyện ML (`ReviewLabel` `0/1`) và **không** tự sửa snapshot đã commit hay điểm phân tích cũ.
- Tệp mới tải lên luôn bắt đầu ở `pending_verification` (*Đã nhận, chưa xác minh*), không thể tự trở thành `present` (*Đã xác minh*).

## 2. Hợp đồng dữ liệu và chính sách chứng từ

- Schema chuẩn: [`remediation.schema.json`](file:///D:/agent22/agent2/sme_fraud/remediation.schema.json)
- Module chính sách & đối chiếu: [`remediation_policy.py`](file:///D:/agent22/agent2/sme_fraud/remediation_policy.py)

Chính sách fixture (`document_requirement_policy/1.0.0`, `approved_for_production=false`, giữ nguyên cổng quyết định mở `D-08`, `D-14`):
- **Không dùng một danh sách chung cho mọi giao dịch**: tách riêng bộ chứng từ theo từng `problem_family` (`payment_invoice`, `payroll_entitlement`, `advance_lifecycle`, `vendor_bank_identity`, `approval_controls`, `split_obligation`, `accounting_controls`, `amount_deviation`, `ml_anomaly`) và `rule_overrides` (như `P1`, `C3`).
- **Không tự bịa hạn SLA mặc định (như 7 ngày)**: `sla_policy.default_due_days = null`; `due_at` do người tạo/giao việc truyền rõ kèm múi giờ (hoặc `null`).
- **Phân biệt 5 trạng thái checklist**:
  - `unknown` — *Chưa có nguồn kiểm tra*
  - `missing` — *Đã xác nhận thiếu*
  - `pending_verification` — *Đã nhận, chưa xác minh*
  - `present` — *Đã xác minh*
  - `not_applicable` — *Không áp dụng*

## 3. Kho SQLite ACID, chống trùng và tách biệt thời điểm

- Lưu trữ: [`remediation_store.py`](file:///D:/agent22/agent2/sme_fraud/remediation_store.py) (`APPLICATION_ID = 1380271437`, migration schema `v1 -> v2`, bảng nhật ký `remediation_audit_events` bất biến với trigger chặn `UPDATE`/`DELETE`).
- **Phạm vi doanh nghiệp `(tenant_id, company_id)`**: tách bạch với mô hình khóa theo `actor_id` của `ReviewStore` cũ; nhiều tài khoản trong cùng `C001` thấy chung danh sách hồ sơ/công việc và không tạo `ActionTask` trùng nhờ partial unique index `idx_unique_open_task_slot` + `Idempotency-Key`. Dữ liệu giữa `C001` và `C002` cách ly hoàn toàn.
- **Kiểm soát xung đột đồng thời**: mọi thao tác `assign`, `submit`, `decision` yêu cầu `expected_revision`; gửi revision cũ trả `409 REVISION_CONFLICT`.
- **Chứng từ nộp muộn**: so sánh `document_date` / `received_at` với `case_as_of`; nếu đến sau mốc snapshot thì gắn `late_arrival_after_as_of = true`, `mutates_snapshot_or_features = false` — chỉ dùng giải quyết xử lý hiện tại, không chỉnh sửa snapshot hoặc feature điểm quá khứ.

## 4. Phân quyền (RBAC), định danh Portal và API HTTP

- Endpoint HTTP xác thực: [`remediation_api.py`](file:///D:/agent22/agent2/sme_fraud/remediation_api.py), gắn trong [`review_server.py`](file:///D:/agent22/agent2/sme_fraud/review_server.py) và allowlist tại [`agent2_bridge.py`](file:///D:/agent22/portal/agent2_bridge.py).
- **Thành thật về định danh Portal**: Portal hiện đăng nhập dùng chung theo workspace, vì vậy `ActionTask.assignee` tách rõ `assignee_kind` (`department_role` vs `server_actor`) với `identity_verified = false`, không xem tên gõ tay tự do là định danh cá nhân đã xác thực.
- **Phân quyền backend hiện hành** (tương thích cấu hình Portal đang chạy):
  - Đọc hồ sơ, tải chứng từ chưa xác minh, tạo/giao việc, nộp kết quả: yêu cầu `data.import` + membership đúng doanh nghiệp.
  - Xác minh chứng từ (`present`/`rejected`), đánh dấu checklist `present`/`missing`, xác nhận hoàn tất/làm lại/mở lại `ActionTask`: yêu cầu quyền `evidence.verify`.
  - Quyền `model.fit` đơn lẻ **bị từ chối (`403 ACCESS_DENIED`)** ở mọi endpoint hồ sơ và công việc.
  - Khi chốt `D-14` cho production, cần tách quyền chi tiết (`case.*`, `evidence.*`, `task.*`) có migration access policy kèm backup.

## 5. Giao diện Workspace và nghiệm thu

- Giao diện tích hợp trong [`workspace.html`](file:///D:/agent22/agent2/sme_fraud/web/workspace.html), [`workspace.js`](file:///D:/agent22/agent2/sme_fraud/web/workspace.js), [`workspace.css`](file:///D:/agent22/agent2/sme_fraud/web/workspace.css):
  - Hiển thị ngay **Còn thiếu gì?**, **Ai đang xử lý, hạn nào?**, **Bước tiếp theo là gì?**.
  - Bộ lọc công việc (*Việc của tôi / bộ phận*, *Sắp đến hạn*, *Quá hạn*, *Chờ xác nhận*, *Đã hoàn tất*) và bảng báo cáo nghiệp vụ tách biệt số vụ riêng, số việc, tỷ lệ thiếu hồ sơ, thời gian xử lý/chờ chứng từ và số tiền khử trùng (`Chưa xác định` nếu chưa có nguồn/xác nhận).
- Kiểm thử tự động: [`test_remediation.py`](file:///D:/agent22/agent2/tests_he/test_remediation.py)
- Script nghiệm thu R4: [`run_remediation_acceptance.py`](file:///D:/agent22/agent2/scripts/run_remediation_acceptance.py)

