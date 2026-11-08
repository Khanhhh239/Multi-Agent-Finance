# Triển khai PLAN_09 — 15/10/2026

Bám P09-T01–T08. Tiếp tục phạm vi kỹ thuật từ PLAN_06–08; rules/models thực tế DRAFT và nghiệm thu pháp lý/mapping/dữ liệu thật vẫn mở.

1. Orchestrator nhận record revision đã lưu; chạy quality, planning, eligible execution, aggregate và template. Pin snapshots; idempotency/resume giữ versions cũ, yêu cầu mới có public evaluation ID mới.
2. API evaluation, lịch sử theo revision, signed cursor cho rule-results/attempts, detail/trace và export/replay. Kiểm quyền tenant/payer, stale revision, concurrent request và audit rollback.
3. Template cố định cho verdict/coverage/blockers; legal citations lấy registry đúng snapshot, evidence lấy CFR/observations đã kiểm. Contract error chỉ mô tả lỗi xử lý, không dựng kết luận thuế.
4. UI thêm phần kiểm tra phạm vi, trạng thái đang chạy/lỗi/chưa có kết quả, rule rows, nguồn/căn cứ, xem thêm, export. Sửa CFR làm kết quả cũ không còn đại diện revision mới; capture export vẫn độc lập.
5. Acceptance: capture/review→planning→ZEN→template/API, revision change/direction, mixed/error/scope/unknown/discovery, pagination, idempotency/resume; browser desktop/mobile và hồi quy các suite trước.
6. Báo cáo kỹ thuật, dữ liệu thật/frozen có gì và thiếu gì; release manifest/gate/runbook/recovery. Không ghi M2 legal release DONE khi chưa có legal labels/rule approval.
