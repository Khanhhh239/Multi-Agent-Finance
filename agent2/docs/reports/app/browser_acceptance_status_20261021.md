# Trạng thái khắc phục lỗi nghiệm thu — 21/10/2026

> Tài liệu tham chiếu theo mốc ghi trong tiêu đề. Xem [trạng thái hiện tại](../../STATUS.md) trước khi dùng số liệu hoặc kế hoạch cũ.

Bảng này tổng hợp kết quả sau sửa. Các trạng thái **OPEN/FAIL** trong [biên bản gốc ngày 20/10](../../../reports/browser_acceptance_20261020/executed/report.md) ghi lại thời điểm phát hiện lỗi và được giữ nguyên làm lịch sử.

| Mục | Trạng thái hiện tại | Căn cứ |
| --- | --- | --- |
| BUG01 · Thiếu tổng hóa đơn bị hiển thị thành 0 | **CLOSED · PASS kỹ thuật** | Đã sửa ngày 20/10; xác nhận lại trực tiếp NO_GROSS và RECUR_A5/AUDIT_0000 trên Chrome ngày 21/10. [Báo cáo mới](bug01_recheck_20261021.md) |
| BUG02 · URL không đồng bộ lựa chọn hồ sơ | **CLOSED · WF02/WF10 PASS** | Đã kiểm tra 39 liên kết, 73 lựa chọn giao dịch P2, tải lại và Back/Forward. [Báo cáo](navigation_retest_20261021.md) |
| BUG03 · Unknown case thô | **CLOSED · WF13 PASS** | Lỗi tiếng Việt, không treo đang nạp; tìm rỗng, làm mới và hồi phục C4 đã thao tác trên Chrome. [Báo cáo](wf13_retest_20261021.md) |
| BUG04 · Link thông báo sai cổng | **CLOSED · WF17 PASS giả lập** | Đã bấm liên kết Email/Zalo ở hai loại thông báo, mở đúng hồ sơ tại 8771. Bản xem trước dùng URL hiện tại; payload lịch sử cũ giữ riêng. 48 simulated, 0 live, 0 sent. [Báo cáo](wf17_retest_20261021.md) |
| WF16 · Giao diện màn hình hẹp | **BLOCKED trong biên bản gần nhất** | Chưa có bằng chứng viewport hẹp thực tế được xác nhận; không gán PASS. [Biên bản](browser_acceptance_20261020.md) |

Đây là trạng thái khắc phục từng lỗi kỹ thuật theo các lượt kiểm tra riêng. Chưa có một lượt chạy lại đầy đủ 39 mẫu/17 luồng sau tất cả thay đổi; nghiệm thu kế toán độc lập vẫn cần biên bản riêng.
