# CAM KẾT BẢO MẬT VÀ BẢO VỆ DỮ LIỆU
## Chương trình chạy thử "Trợ lý Dòng tiền"

> **Bản mẫu, 24/10/2026. Cần luật sư hoặc bộ phận pháp chế rà soát trước khi ký**, đặc biệt các điều liên quan Nghị định 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân
> (sao kê ngân hàng có thể chứa tên cá nhân chuyển tiền). Phần trong `[ ]` cần điền.

**Bên cung cấp dữ liệu (Bên A):** [Tên doanh nghiệp], MST [ ], đại diện [Họ tên, chức vụ].
**Bên nhận dữ liệu (Bên B):** [Tên đơn vị/cá nhân thực hiện chạy thử], đại diện [Họ tên, chức vụ].

### Điều 1. Dữ liệu thuộc phạm vi cam kết
Mọi dữ liệu Bên A cung cấp cho chương trình, gồm: hoá đơn điện tử, sao kê ngân hàng, số dư, sổ công nợ, lời hứa trả tiền, danh sách chi phí;
và mọi kết quả Bên B tạo ra từ dữ liệu đó (dự báo, báo cáo) — sau đây gọi chung là **"Dữ liệu"**.

### Điều 2. Mục đích sử dụng duy nhất
Bên B chỉ dùng Dữ liệu để: (a) chạy công cụ dự báo dòng tiền cho chính Bên A; (b) đánh giá độ chính xác của công cụ; (c) lập báo cáo gửi Bên A.
Bên B **không**: bán, chia sẻ, cho thuê Dữ liệu; liên hệ khách hàng hay đối tác của Bên A; dùng Dữ liệu để đánh giá tín dụng hay cung cấp cho tổ chức tài chính.

### Điều 3. Biện pháp bảo vệ
1. **Lưu trữ cục bộ:** Dữ liệu lưu trên máy của Bên B, không đưa lên dịch vụ đám mây công cộng hay máy chủ bên thứ ba.
2. **Mã hoá:** từng bản ghi được mã hoá trước khi ghi vào cơ sở dữ liệu (mã hoá đối xứng Fernet). Khoá mã hoá được lưu ở thư mục riêng, tách khỏi thư mục dữ liệu; hệ thống từ chối khởi động nếu hai thư mục trùng nhau.
3. **Kiểm soát truy cập:** chỉ người có khoá truy cập (token) mới đọc được qua giao diện; nhật ký ghi lại loại thao tác và số lượng bản ghi.
4. **Ẩn danh khi nạp:** mã khách hàng, mã số thuế, tên khách hàng, tên người chuyển tiền, và các từ là tên trong nội dung chuyển khoản được thay bằng mã ẩn danh
   (HMAC-SHA256 với khoá bí mật riêng) **ngay ở bước nạp, trước khi lưu**. Số hoá đơn và các từ thanh toán chung ("TT", "HD"...) trong nội dung chuyển khoản được giữ nguyên để ghép tiền.
   Bảng đối chiếu mã ẩn danh ↔ tên thật **không được lưu ở phía Bên B**; Bên A được cung cấp công cụ và khoá để tự dựng bảng này khi đọc báo cáo.
5. **Kênh truyền:** chỉ nhận file qua kênh có mật khẩu/mã hoá do hai bên thống nhất; không nhận qua email không mã hoá.
6. **Không có bên thứ ba:** không dùng dịch vụ AI hay phân tích bên ngoài để xử lý Dữ liệu thô của Bên A.

### Điều 4. Người được tiếp cận
Chỉ [số] người sau được tiếp cận Dữ liệu: [Họ tên, vai trò]. Mỗi người ký cam kết bảo mật cá nhân với Bên B.

### Điều 5. Thời hạn lưu giữ và xoá
1. Dữ liệu được lưu trong thời gian chạy thử và tối đa **[30] ngày** sau báo cáo tổng kết, trừ khi Bên A đồng ý bằng văn bản cho lưu lâu hơn.
2. Bên A có quyền yêu cầu **xoá toàn bộ Dữ liệu bất cứ lúc nào**. Bên B thực hiện trong **[5] ngày làm việc**, xoá khỏi cơ sở dữ liệu (kèm dọn tệp để loại bản mã cũ) và các bản sao làm việc,
   rồi gửi Bên A **biên bản xác nhận đã xoá**.
3. Kết quả tổng hợp **đã ẩn danh hoàn toàn và không thể truy ngược** về Bên A (ví dụ: "sai số dự báo trung bình trên các doanh nghiệp tham gia") có thể được giữ để cải tiến công cụ,
   **chỉ khi Bên A đánh dấu đồng ý** tại Điều 8.

### Điều 6. Sự cố
Nếu phát hiện truy cập trái phép hoặc rò rỉ Dữ liệu, Bên B thông báo cho Bên A trong **[24/72] giờ**, nêu phạm vi ảnh hưởng và biện pháp khắc phục,
và phối hợp thực hiện các nghĩa vụ thông báo theo quy định pháp luật.

### Điều 7. Quyền của Bên A
Bên A có quyền: được biết Dữ liệu đang được dùng thế nào; nhận bản sao các báo cáo; yêu cầu sửa, ngừng xử lý hoặc xoá; chấm dứt tham gia bất cứ lúc nào mà không cần nêu lý do.

### Điều 8. Đồng ý tuỳ chọn
- [ ] Bên A đồng ý cho Bên B giữ **kết quả tổng hợp đã ẩn danh hoàn toàn** sau chương trình để cải tiến công cụ.
- [ ] Bên A đồng ý được nêu tên là đơn vị tham gia chạy thử (không kèm số liệu).

### Điều 9. Hiệu lực
Cam kết có hiệu lực từ ngày ký đến khi Dữ liệu đã được xoá theo Điều 5. Nghĩa vụ bảo mật tiếp tục có hiệu lực sau khi chương trình kết thúc.

| Bên A | Bên B |
|---|---|
| (Ký, ghi rõ họ tên, đóng dấu) | (Ký, ghi rõ họ tên) |
| Ngày: | Ngày: |

---

## Việc phải làm phía Bên B trước lần nạp dữ liệu thật đầu tiên (nội bộ, KHÔNG gửi kèm)

| # | Việc | Trạng thái |
|---|---|---|
| 1 | Gắn ẩn danh HMAC vào bước nạp (`/ingest`, `/ingest/file`, `/promises`; `/whatif` nhận cả mã gốc) | **Xong 24/10** — `agent1_service/ingest/privacy.py`, `tests/test_privacy_ingest.py`; kiểm tra T9 không giảm: `outputs/pilot/privacy_t9_parity.csv` |
| 2 | Lưu khoá Fernet, khoá HMAC, token tách khỏi thư mục dữ liệu (`AGENT1_KEY_DIR`, mặc định `<data>-keys`; tự chuyển khoá cũ; từ chối nếu nằm trong thư mục dữ liệu) | **Xong 24/10** (mã); còn phải ghi rõ ai giữ khoá và đặt `AGENT1_KEY_DIR` sang thiết bị khác khi triển khai |
| 2b | Công cụ cho Bên A dựng bảng đối chiếu mã ↔ tên (`pseudonym_map` có sẵn; cần script/CSV giao Bên A) | Chưa làm |
| 3 | Kiểm thử quy trình xoá (`DELETE /data`) và mẫu biên bản xác nhận xoá | Mã xoá có sẵn; biên bản chưa có |
| 4 | Pháp chế rà soát bản cam kết (Nghị định 13/2023/NĐ-CP) | Chưa làm (chủ dự án) |
| 5 | Thống nhất kênh nhận file có mã hoá | Chưa làm |
