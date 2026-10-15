# Yêu cầu sản phẩm

Ưu tiên theo MoSCoW: **M** bắt buộc cho bản thí điểm, **S** nên có, **C** có thể có, **W** không làm lần này.

## 1. Yêu cầu chức năng

| Mã | Yêu cầu | Ưu tiên | Trạng thái hiện tại |
|---|---|:-:|---|
| FR-1 | Nhận bảng giao dịch theo lược đồ chuẩn (xem 02_du_lieu/10) từ phần mềm kế toán hoặc tệp CSV | M | Lược đồ có; bộ nhận từ MISA, hóa đơn điện tử chưa có |
| FR-2 | Tính đặc trưng chỉ từ quá khứ, không rò rỉ thời gian | M | Có (`feats.py`, `feats_v4.py`) |
| FR-3 | Chạy 31 luật nghiệp vụ và truy vấn đồ thị quan hệ (tài khoản, địa chỉ, điện thoại, người đại diện dùng chung) | M | Có (bạn bạn, `sme_fraud/rules.py`) |
| FR-4 | Chạy ở chế độ khởi đầu lạnh không cần nhãn | M | Có (kênh Novelty) |
| FR-5 | Chạy chế độ có huấn luyện sẵn từ thế giới tổng hợp, áp cho công ty mới | M | Có trên v3; cần huấn luyện lại cho v4 |
| FR-6 | Chọn cảnh báo theo ngân sách mỗi công ty mỗi tuần, 2 khe cho mô hình chính và 1 khe cho kênh mới lạ | M | Có |
| FR-7 | Gộp cảnh báo thành vụ theo thực thể và tuần, có mức ưu tiên và thời hạn xử lý | M | Có |
| FR-8 | Lý do bằng tiếng Việt, mỗi lý do trỏ tới số liệu cụ thể | M | Có cho luật và 12 bộ lệch thực thể; **thiếu cho 15 dấu hiệu đỏ v4** |
| FR-9 | Ghi kết luận của người rà soát và dùng làm phản hồi | S | Mô phỏng có (`feedback_sim.py`); giao diện có (`review_ui`); chưa nối |
| FR-10 | Xuất hồ sơ vụ việc | S | Một phần (`case_queue.csv`) |
| FR-11 | Kiểm soát tỷ lệ phát hiện sai theo conformal và Benjamini–Hochberg | C | Có (`alerting.py`), chưa bật mặc định |
| FR-12 | Cảnh báo tức thời cho sự kiện nghiêm trọng (ví dụ đổi tài khoản nhà cung cấp rồi chi ngay) | C | Chưa |
| FR-13 | Tự động chặn thanh toán | W | Không làm: con người quyết định |
| FR-14 | Kết luận một cá nhân là gian lận | W | Không làm |

## 2. Yêu cầu phi chức năng

| Mã | Yêu cầu | Mục tiêu đề xuất **[G]** |
|---|---|---|
| NFR-1 | Chạy trên 100.000 dòng/năm của một công ty | dưới 5 phút cho tính đặc trưng và chấm điểm hằng tuần trên máy 4 nhân, 16 GB |
| NFR-2 | Cách ly dữ liệu giữa công ty | Không bao giờ dùng nhãn hoặc điểm của công ty khác để chấm công ty này, trừ mô hình huấn luyện sẵn trên dữ liệu tổng hợp |
| NFR-3 | Tính tái lập | Cùng dữ liệu, cùng hạt giống, cùng mã băm cho cùng kết quả |
| NFR-4 | Giải thích trung thực | Mọi con số trong câu giải thích phải có trong bằng chứng |
| NFR-5 | Có thể kiểm tra | Giữ nhật ký phiên bản mô hình, ngưỡng, cảnh báo, kết luận |
| NFR-6 | Chế độ ngoại tuyến | Không gửi dữ liệu đi ngoài máy chủ của khách trừ khi có thỏa thuận |

## 3. Yêu cầu pháp lý và đạo đức
- Giám sát ở mức nhân viên là xử lý dữ liệu cá nhân: cần căn cứ pháp lý và thông báo theo Nghị định 13/2023/NĐ-CP. **Chưa có thẩm định pháp lý.**
- Ngôn ngữ cảnh báo trung tính: "đáng kiểm tra". Không công bố tên người trong cảnh báo gửi ra ngoài nhóm được phân quyền.
- Dữ liệu thí điểm: thỏa thuận bằng văn bản, ẩn danh hóa, chỉ dùng cho nghiên cứu.

## 4. Ngoài phạm vi (lần này)
Gian lận từ bên ngoài, rửa tiền, kiểm tra tuân thủ thuế, báo cáo tài chính hợp nhất, nhận dạng chứng từ giấy.

## 5. Liên kết với kiểm thử
Mỗi yêu cầu M có phép kiểm thử và cổng chấp nhận trong [03_danh_gia_va_hieu_qua_kinh_te/03_chien_luoc_kiem_thu.md](../03_danh_gia_va_hieu_qua_kinh_te/03_chien_luoc_kiem_thu.md).
