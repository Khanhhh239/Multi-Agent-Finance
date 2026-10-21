# Nghiệm thu P2 trên web

Chạy trong thư mục dự án:

```powershell
& 'C:\Users\Technical Support\AppData\Local\Programs\Python\Python312\python.exe' -B -m sme_fraud.p2_controls_server --port 8767
```

Mở **http://127.0.0.1:8767/p2-controls**. Mặc định dùng bộ nguồn `data/p2_controls_20261018_v2` và kết quả đã khóa `reports/p2_controls_20261018`. Nhật ký người dùng nằm riêng tại `.runtime/p2_controls_web/reviews.sqlite3`, giữ được khi khởi động lại cùng lệnh.

Mỗi tình huống được giữ độc lập vì các mẫu dùng lại mã giao dịch. Danh sách gồm đủ **32 tình huống / 73 giao dịch**, bao gồm 43 dòng không phát sinh P2. Không áp dụng ngân sách hồ sơ vận hành cho danh sách nghiệm thu.

1. Chọn nhóm hoặc tìm mã tình huống. Có bộ lọc kết quả P2 và trạng thái nghiệm thu.
2. Mở **Giao dịch & P2** và chọn từng dòng để xem số tiền, chiều Nợ/Có, hóa đơn, trạng thái hạn mức, thông tin thiếu và hướng xử lý. Mặc định chọn giao dịch cuối, tiện xem dòng hoàn hoặc khoản định kỳ sau lịch sử.
3. Xem **Chứng từ & liên kết** để đối chiếu sổ, hóa đơn, liên kết hoàn/đảo và thỏa thuận định kỳ.
4. Xem **Hàng đợi** và mở **Xem kỳ vọng đã khai báo…** để so kết quả với kỳ vọng độc lập. “Không mở hồ sơ” vẫn có giao dịch để đọc.
5. Chọn **Đạt / Cần sửa / Cần bổ sung**, nhập người nghiệm thu và lý do. Kết quả áp dụng cho toàn bộ tình huống, được lưu vào lịch sử riêng. “Đạt” là kết quả nghiệm thu, không phải xác nhận giao dịch hợp lệ hay kết luận gian lận.
6. Dùng **CSV** để xuất đúng danh sách đang lọc, kèm kết quả, người nghiệm thu và ghi chú gần nhất.

Lần đầu nên đọc `FULL_BELOW`, `FULL_EQUAL`, `NO_INVOICE`, `INSTALL_SMALL`, `REFUND_FULL`, `RECUR_A5`, `LIMIT_VERIFIED`.

Muốn đổi nguồn/kết quả hoặc database:

```powershell
python -B -m sme_fraud.p2_controls_server --source data/p2_controls_20261018_v2 --report reports/p2_controls_20261018 --database .runtime/p2_controls_web/reviews.sqlite3 --port 8767
```

Nguồn và kết quả phải khớp manifest/commitment. Nhật ký được gắn với phiên bản nguồn + dự đoán; thay bộ đối chứng không tự áp dụng kết luận cũ. Database bị từ chối nếu đặt trong các thư mục nguồn/kết quả đã khóa.

Để tích hợp vào **Case Management đang dùng**, thêm `--p2-controls` vào lệnh `sme_fraud.review_server` hiện tại. Khi đó menu **Đối chứng P2** mở `/p2-controls` ngay trên cùng cổng. Có thể đặt journal riêng bằng `--p2-controls-database PATH`. Không bật cờ này thì menu được ẩn.

Luồng web đọc kết quả detector đã khóa, không chấm lại hoặc sửa kỳ vọng khi mở trang, không gửi thông báo. Các ghi chú kiểm thử tự động nằm ở `.runtime/p2_controls_web_20261018/integration.sqlite3`, tách khỏi database mặc định dành cho bạn.

[Biên bản kiểm chứng và giới hạn](../../reports/p2_controls_web_20261018.md) · [Nguồn và quy trình chấm bộ đối chứng](../p2_controls/README.md).
