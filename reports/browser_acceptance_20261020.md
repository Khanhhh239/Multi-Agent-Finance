# Nghiệm thu Chrome — kết quả ngày 20/10/2026

**Đã thao tác trực tiếp trên Chrome. Giao diện 39 mẫu: 37 PASS, 2 FAIL. Luồng chức năng: 12 PASS, 4 FAIL, 1 BLOCKED (WF16: màn hình hẹp chưa có bằng chứng). Có 4 lỗi đang mở, chưa đủ điều kiện nghiệm thu cuối.**

[Báo cáo đầy đủ, bước tái hiện và ảnh](browser_acceptance_20261020/executed/report.md) · [39 kết quả mẫu](browser_acceptance_20261020/sample_results.csv) · [17 luồng](browser_acceptance_20261020/executed/workflow_results.csv) · [Danh sách lỗi](browser_acceptance_20261020/executed/issue_log.csv).

Đã kiểm tra 32 P2/73 giao dịch và 7 hồ sơ 001/003 trên **bản riêng 8771**, sau khi mở và xác định 8765 là demo cũ không có P2 tích hợp. Kết quả từng mẫu đánh giá nội dung UI; các luồng URL/tải lại đánh giá riêng và có lỗi. Không thao tác ghi tại 8765.

Lỗi cần sửa: thiếu số tiền hiển thị thành 0; URL không đồng bộ hồ sơ và tải lại mở hồ sơ cũ; lỗi Unknown case khó hiểu; link thông báo 8771 trỏ 8765. Chưa sửa hoặc kiểm tra sau sửa trong đợt này.

Đã lưu 32/32 ghi chú UAT P2, gồm 30 Đạt và 2 Cần sửa. Thử cổng tài liệu, kết luận và xung đột hai tab bằng dữ liệu SIM; 48 tác vụ thông báo đều dry-run/simulated, không có tác vụ live/sent. Hash 1.209 tệp khóa và 16 tệp UI/runtime giữ nguyên so với baseline trước khi rà. [Đối chiếu chỉ đọc](browser_acceptance_20261020/executed/verification.json).

WF16 đã xem màn hình rộng; công cụ vẫn báo 1280/1440 px dù người dùng đã báo thu hẹp. Phần hẹp chưa được kiểm chứng và không ghi PASS. Chưa có nghiệm thu kế toán độc lập; RR09 còn chờ người phê duyệt và tham số nghiệp vụ.

[Lịch sử trước khi Chrome kết nối](browser_acceptance_20261020/connection_history_before_chrome.md) được giữ riêng. connection_and_readiness.json và http_preflight.json là tiền kiểm cũ, không phải trạng thái nghiệm thu cuối.
