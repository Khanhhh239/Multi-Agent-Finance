# Prompt khởi động

Bạn thực hiện riêng R{n} trong spec v2.1. Đọc 00_INDEX_va_quy_tac.md, 99_decision_log.md, CHANGE_REQUESTS.md, task card tasks/R{n}.md và các file task chỉ định. Kiểm tra dependency và quyền truy cập repo. R0 không bị chặn bởi việc chưa chốt stack/deployment; chính R0 phải điều tra các mục này. Chỉ phần không truy cập được mới BLOCKED.

Giữ thành phần đúng, sửa lỗi có test, không làm mốc sau hoặc HE tương lai. Chỉ sửa phạm vi trong task; ghi mọi thay đổi contract/fixture bằng change request. Chạy runner/check_evidence, tạo REPORT theo template, cập nhật tối đa READY_FOR_REVIEW rồi dừng. Chỉ người được chỉ định mới duyệt DONE. Không tự đặt quality threshold sản xuất hoặc giả testcase xanh.
