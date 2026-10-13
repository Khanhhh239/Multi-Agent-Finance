# PLAN_13 — ERP connector và adapter registry mở rộng

> Trạng thái triển khai: **NOT_STARTED**. Tài liệu là công việc dự kiến, không chứng nhận code đã hoàn thành.

[Lộ trình tổng](README.md) · Trước theo thứ tự đọc: [PLAN_12](PLAN_12_RAG_EXPLANATION.md) · Sau: [PLAN_14](PLAN_14_PRODUCTION_HARDENING.md)

## 1. Kết quả cần đạt và điều kiện bắt đầu

Kết nối một ERP cụ thể theo phiên bản, đồng bộ có checkpoint và đưa records vào cùng CFR; không làm đồng thời mọi ERP.

- Phụ thuộc bắt buộc: PLAN_09 đạt gate; có sandbox ERP và schema được chọn.
- Ước lượng: **4–7 ngày công**, một người làm tập trung; chưa bao gồm thời gian chờ dữ liệu/hạ tầng/nghiệp vụ.
- Đối chiếu [NEW_PLAN](../NEW_PLAN.md): mục 3, 4.1, 12, 15.
- Đầu vào: Sandbox credentials có quyền đọc, API/schema của một ERP, tenant mapping, source capability.

Không bắt đầu phần phụ thuộc khi gate đầu vào chưa qua. Có thể chuẩn bị fixture/tài liệu độc lập, nhưng không ghi cả chặng DONE vì đã tạo scaffold.

## 2. Tài sản hiện có và cách tái sử dụng

Thiết kế nhắc nhiều ERP nhưng phạm vi triển khai đầu chỉ một hệ được chọn theo nhu cầu thực. Nếu chưa có sandbox, dùng mock contract để phát triển nhưng không đánh dấu connector nghiệm thu thật.

Kiểm tra lại tính tồn tại/phiên bản khi triển khai; kết quả kiểm kê là bằng chứng tham khảo, không thay nghiệm thu runtime đích.

## 3. Module và hợp đồng cần xây

Các đường dẫn sau là **đích dự kiến**, chưa hàm ý file đã tồn tại:

`agent3_tax_compliance/src/connectors/erp/; src/adapters/erp/; configs/erp/; tests/connectors/`

ConnectorProfile: vendor/API/schema version, tenant/taxpayer mapping, read scope, cursor/checkpoint, watermark overlap policy. ERP row giữ source record ID/version và accounting date khác invoice/payment date.

Mọi artifact phải có schema/config version, input hash hoặc record revision, creator/stage và timestamp. Artifact chứa dữ liệu thật lưu ngoài git theo policy; tài liệu chỉ ghi metadata đã che dữ liệu.

## 4. Công việc chi tiết theo thứ tự

### P13-T01 — Chọn connector và giới hạn dữ liệu

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Chọn hệ có sandbox; định nghĩa entities/date ranges/fields cần đọc, rate limits và quyền tối thiểu.
- Đầu ra: ERP_SCOPE.md.
- Kiểm chứng: Không tuyên bố hỗ trợ MISA/Odoo/ERPNext/SAP đồng loạt.

### P13-T02 — Secrets và HTTP client

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Cấu hình secret refs, timeout, retry/backoff, pagination, token refresh. Không ghi token/raw PII vào logs.
- Đầu ra: connector client.
- Kiểm chứng: 401/403/429/network failure ra typed errors; không retry vô hạn.

### P13-T03 — Mapping schema và provenance

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Map source fields vào CFR observed, pin mapping/profile version và master; money Decimal codec và dates riêng semantic.
- Đầu ra: ERP mapper.
- Kiểm chứng: Accounting date không bị dùng thay invoice date để chọn luật.

### P13-T04 — Incremental sync

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Checkpoint chỉ advance khi batch persist thành công; overlap window/dedupe theo source ID/version, handle late changes/deletions.
- Đầu ra: sync worker + checkpoints.
- Kiểm chứng: Crash giữa batch không mất rows; cùng record updated tạo revision có audit.

### P13-T05 — Capability và stale data

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Khai evidence nào ERP thật sự có, freshness/ledger completeness và period scope. Không giả mọi ERP đều cung cấp chứng từ thanh toán.
- Đầu ra: capability + freshness rules.
- Kiểm chứng: Ledger thiếu kỳ làm aggregate applicability UNKNOWN thay vì NO_MATCH.

### P13-T06 — Integration sandbox

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Chạy pagination/rate limit/update/delete/retry trên sandbox thật; mock chỉ dùng CI.
- Đầu ra: sandbox_acceptance_report.
- Kiểm chứng: Số imported/revised/errors khớp source query trong scope.

### P13-T07 — Runbook vận hành

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Hướng dẫn revoke token, resync range, mapping version rollout và lỗi permissions.
- Đầu ra: gate_13.md + runbook.
- Kiểm chứng: Resync không phá raw/revisions; tenant separation qua.

## 5. Tiến độ bên trong chặng

- Ngày 1: scope/sandbox/API contract.
- Ngày 2–3: HTTP client và mapping.
- Ngày 4–5: checkpoint/dedupe/capability.
- Ngày 6–7: sandbox integration và vận hành.

Cuối mỗi ngày cập nhật task IDs đã làm, bằng chứng và blocker vào bảng tiến độ tổng. Khi phát hiện phụ thuộc mới hoặc scope tăng, ghi lại estimate còn lại; không cố giữ lịch bằng cách bỏ invariant.

## 6. Ca kiểm thử và tình huống bắt buộc

- [ ] ERP sửa record cũ sau watermark.
- [ ] 429 hoặc token hết hạn giữa page.
- [ ] Accounting date khác invoice date.
- [ ] Hai tenant có cùng source record ID.

Dùng fixture tổng hợp nhỏ cho contract/recovery tests, dữ liệu có nhãn cho accuracy và sandbox thật cho connector. Không thay accuracy evaluation bằng unit test parser. Chỉ chạy phần test phù hợp chặng và integration qua ranh giới vừa thay đổi.

## 7. Gate hoàn thành và bàn giao

**Điều kiện gate:** Một connector có sandbox evidence đạt gate; không có sandbox thì gate còn BLOCKED, giữ mock implementation riêng. Không chặn core OCR/compliance vì chờ ERP.

- [ ] Mỗi task bắt buộc có artifact và cách tái hiện kiểm chứng.
- [ ] Không còn lỗi vi phạm hợp đồng dữ liệu, tiền, tenant hoặc version trong phạm vi chặng.
- [ ] Có bảng giới hạn hỗ trợ, ca chưa đạt và next action; quality target thiếu dữ liệu không được đánh dấu đạt.
- [ ] Ghi `evidence/gate_13.md`: input versions, test/eval command, ngày chạy, kết quả, số mẫu, lỗi còn lại và quyết định gate.
- [ ] Bàn giao: PLAN_14 nhận sync operations; PLAN_15 nhận ledger completeness/freshness và source records.

## 8. Khi chưa đạt hoặc bị chặn

Ghi blocker cụ thể, task bị ảnh hưởng, điều kiện gỡ và người/nguồn cần cung cấp. Tiếp tục các task độc lập. Không biến thiếu dữ liệu, thiếu môi trường hoặc lỗi runtime thành kết quả thành công; không ghi DONE khi chỉ có mock mà gate yêu cầu dữ liệu thật.

Lệnh triển khai/test sẽ được ghi cùng artifact khi module đã tồn tại. Quy ước lệnh và cách cập nhật tiến độ nằm trong [README lộ trình](README.md); tài liệu này không yêu cầu chạy benchmark hoặc cài dependency ngay lúc chia kế hoạch.
