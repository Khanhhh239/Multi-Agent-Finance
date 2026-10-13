# Phiên bản quality tại gate PLAN_05

10 file Python có SHA-256 khớp chính xác `docs/agent3/plans/evidence/plan05/validation_summary.json`. Đây là mã lưu để tái hiện bằng chứng lịch sử, không phải module chạy của ứng dụng hiện tại.

PLAN_06 bổ sung xác minh correction event và ngừng báo lỗi trích xuất cũ cho field đã được người duyệt sửa có bằng chứng. Vì implementation hash thay đổi, không dùng code mới để replay assessment cũ rồi sửa đè bằng chứng PLAN_05.

Chạy từ root bằng `agent3_tax_compliance/.venv/Scripts/python.exe scripts/replay_plan05_snapshot.py`. Script dùng snapshot policy, extractor và normalized OCR đã pin; chỉ đọc DB PLAN_05, không migrate, không chạy lại OCR và không tạo nhãn mới.
