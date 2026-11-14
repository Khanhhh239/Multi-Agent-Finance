# Đại Phát · CSV synthetic

Các file 01–06, manifest và `invalid_cases/` phục vụ diễn tập Workspace trong kho `DEMO_DAIPHAT` riêng. Ngày CSV ISO `yyyy-mm-dd`, tiền `plain`; giữ ID nguồn.

[Hướng dẫn đầu vào Đại Phát](../../docs/06_Pilot/DEMO_INPUT_TRAIN_DAIPHAT.md) là nơi duy nhất ghi thứ tự nạp và tham số bài tập. [Sổ tay Workspace](../../docs/06_Pilot/SO_TAY_AGENT1.md) giữ thao tác, cách đọc audit và kế hoạch.

Manifest mô tả quy mô/giả định. Dữ liệu không đại diện cho doanh nghiệp thật; cutoff bài tập phải phù hợp ngày sẵn sàng của bundle hiện dùng. Không dùng PDF/điểm dự báo cũ làm đáp án. Tái tạo bằng `scripts/business/make_large_demo.py` từ thư mục `agent1/` sẽ ghi lại bộ demo và gói ZIP; chỉ chạy khi chủ động muốn tái tạo.
