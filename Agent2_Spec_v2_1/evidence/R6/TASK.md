# Task card CR-059 — release infrastructure và staging

Nguồn: yêu cầu người dùng 16/11/2026 và handoff release/rollback đính kèm.
Đã đọc: 00,01,02,03,04,05,99 và tasks/R6. Áp RULE-TASK-01.

Phạm vi thực hiện: bundle/schema/kho bảo vệ, gate có bằng chứng, phê duyệt,
CAS/idempotency, pin run, rollback không restore DB, API/UI và kiểm thử cô lập.
Không thay Portal live/DB/model/key/quyền/phiên, không push hoặc phê duyệt active.

Kết quả: READY_FOR_REVIEW kỹ thuật phần infrastructure/staging. Toàn R6 và
production vẫn BLOCKED; không thay mapping stage_commands hoặc tự ghi DONE.
Các thành phần full release executor/HE/ensemble/case-budget-delivery/monitoring
chưa nối và các quyết định owner còn mở được liệt kê trong REPORT.md.
