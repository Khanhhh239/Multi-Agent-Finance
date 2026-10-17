# Đợt 7 — cổng nghiệm thu nguồn thật

Đã thêm quy trình hai bước `prepare/evaluate` cho F1, C4, E2, F2, F3 và F4. Quy trình kiểm schema/checksum, cutoff, coverage theo công ty, khóa hash dự đoán, chấm mù hai người và áp cổng precision/recall/information gap đã phê duyệt.

Workspace hiện chưa có nguồn HR/ERP/công nợ SME thật nên kết quả readiness là `awaiting_real_data`; không dùng fixture phase 4 để nâng trạng thái rule thành accepted. Xem [phương pháp và nguồn cần cung cấp](rule_source_acceptance.md) cùng báo cáo chạy trên dataset hiện tại tại [real_source_acceptance](rule_repairs/real_source_acceptance/summary_vi.md).

Nghiệm thu kỹ thuật: **191/191 test qua**, gồm 10 test riêng cho commitment, chấm mù, độc lập reviewer, coverage, F1 authoritative source và scope F3/F4. Đây vẫn là kiểm tra pipeline, không thay cho kết luận rà soát thực địa.
