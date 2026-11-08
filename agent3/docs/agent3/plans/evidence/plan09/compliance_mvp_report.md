# Báo cáo phạm vi nghiệm thu compliance MVP

Ngày 15/10/2026. [Test summary](validation_summary.json), [release manifest](release_capture_compliance_v1.json), [browser](browser_summary.json), [public smoke](public_smoke.json).

## Đã kiểm chứng kỹ thuật

Capture fixture PDF/native → extraction/CFR → reviewer correction/rederive → quality → planning → ZEN process thật → aggregate → template → API/UI/export/replay. Riêng primitive rules vẫn có truth tables/Decimal oracle/unknown/discovery/error cases từ PLAN_08, được chạy hồi quy cùng chặng này.

Acceptance mới kiểm idempotency và version changes, sửa MST đổi direction, revision cũ không thành kết quả mới, signed stable pagination, source scope, mixed FAIL/REVIEW/timeout, no false violation khi thiếu date/confidence, contract-error template không kết luận thuế, audit rollback và resume theo snapshot. Browser kiểm sáu nhóm hành vi ở desktop 1366px và mobile 390px, không có page errors.

Demo PASS/FAIL/REVIEW dùng synthetic approved legal/model fixtures; không phải chứng nhận mẫu luật thực tế. Dữ liệu thật chỉ chạy smoke qua pipeline với catalog DRAFT. Điểm quality và số trường điền không được gọi là tax accuracy.

## P09-T06 còn mở

Chưa có bộ expected legal verdict độc lập với rules/models đã duyệt cho functional/frozen legal evaluation. Không có mẫu số hợp lệ để báo legal accuracy, false PASS hoặc nghiệm thu M2 pháp lý. Frozen legal holdout **NOT_RUN**, không lấy dữ liệu đã dùng sửa OCR hoặc unit fixtures thay holdout. Smoke một PDF công khai (nếu chạy được trên máy có runtime) chỉ xác nhận kỹ thuật cho một chứng từ; không xác nhận khả năng tổng quát, tỷ lệ chính xác hay độc lập nhãn.

Confidence calibration, nhãn thực/độc lập và những giới hạn PLAN_05–07 vẫn mở. VAT mapping thực tế còn trống, content model chỉ có nhánh observation MST, non-cash chưa có nạp/match proof ngân hàng thật. Snapshot pháp lý hiện chỉ hỗ trợ invoice date trước 15/10/2026; phải rà/publish snapshot mới để mở rộng khoảng này.

## Latency và release

Report mỗi evaluation ghi thời gian quality/planning/execution/template. Validation ghi một sample tổng hợp, public smoke ghi thời gian riêng gồm OCR nếu có. Chưa đủ mẫu/phần cứng/tải để kết luận p95 hoặc SLA; không trộn hai đường native/OCR thành một số accuracy/latency chung.

Manifest pin source/API/UI/template hashes, schema/DB/runtime/model/rules/legal/taxonomy versions. Artifact từng evaluation pin CFR/master/quality/context/capability/calibration và liên kết các stage snapshots. Đây là **TECHNICAL_ONLY_LEGAL_RELEASE_PENDING**, không phải M2 legal release hoặc production.
