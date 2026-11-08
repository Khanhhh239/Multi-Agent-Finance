# P2_RECUR_A5 — kiểm tra lại ngày 20/10/2026

> Tài liệu tham chiếu theo mốc ghi trong tiêu đề. Xem [trạng thái hiện tại](../../STATUS.md) trước khi dùng số liệu hoặc kế hoạch cũ.

**PASS.** BUG01 đã được sửa trong lượt xử lý NO_GROSS bằng hàm trình bày tổng hóa đơn và phần giải thích không có P2 dùng chung. Lượt này đối chiếu lại code, nguồn khóa và thao tác trực tiếp trên Chrome, không cần sửa thêm code.

| Nội dung cần kiểm chứng | Kết quả hiện tại |
|---|---|
| Đủ 23 giao dịch | Đã chọn trực tiếp 23/23 giao dịch trên Chrome tại bản riêng 8771 |
| AUDIT_0000 thiếu hóa đơn | Ghi “Tổng giá trị hóa đơn: Chưa có thông tin; chưa đủ dữ kiện để so sánh tổng hóa đơn với mốc này”, không còn trình bày là 0 đồng |
| 21 dòng lịch sử tiếp theo | Cùng giữ trạng thái tổng hóa đơn chưa có thông tin |
| AUDIT_0022 | 22/20 mẫu, cửa sổ 90 ngày, ngưỡng 1.000.000 VND |
| Ngoại lệ định kỳ | PAT_CONTROL, giá trị 3.000.000 VND, dung sai 0, A5 giữ 0 điểm |
| Điều kiện as-of | Duyệt 01/01/2025 09:00, biết 10:00 cùng ngày; trước lúc chi 12/08/2025 11:00. Khoản chi nằm trong kỳ hiệu lực 01/01–31/12/2025; 22 dòng lịch sử có trước giao dịch |
| Hàng đợi và lịch sử | Không mở hồ sơ cho bộ này; ghi chú FAIL ban đầu và PASS sau sửa đều còn trong lịch sử |

[Bằng chứng đọc trực tiếp trên Chrome](../../../reports/recur_a5_retest_20261020/browser_observations.json) · [Đối chiếu code, nguồn và as-of](../../../reports/recur_a5_retest_20261020/completion_audit.json). Code hiện tại trùng hash bản có [22 kiểm tra hồi quy đạt](../../../reports/bug01_retest_20261020/renderer_tests.json); không chạy lại cùng bộ kiểm thử khi code chưa đổi. Toàn bộ 22 tệp RECUR_A5 trong baseline nguồn/kết quả khóa giữ nguyên.

Kết quả này chỉ nghiệm thu kỹ thuật mẫu P2_RECUR_A5 trên dữ liệu mô phỏng. Không suy từ thiếu hóa đơn, không có P2 hoặc ngoại lệ A5 thành giao dịch hợp lệ. Ghi chú UAT sau sửa đã có và được xác nhận lại; không thêm bản ghi trùng trong lượt này.

![AUDIT_0000 sau sửa](../../../reports/recur_a5_retest_20261020/AUDIT_0000_after.jpg)

![Ngoại lệ A5 của dòng cuối](../../../reports/recur_a5_retest_20261020/AUDIT_0022_after.jpg)
