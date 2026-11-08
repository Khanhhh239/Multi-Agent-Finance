# Demo: Công ty TNHH Phần mềm Sao Việt (dữ liệu mô phỏng)

Một công ty phần mềm, khai thuế theo quý, quý 3 năm 2026. Làm tuần tự 7 bước dưới đây, khoảng 10 phút. Mỗi bước ghi rõ **bấm gì** và **phải thấy gì**; nếu khác, đó là lỗi.

Cần: ứng dụng đang chạy (`chay_agent3.bat`). Bước 6 và 7 cần Ollama.

## Bước 1. Đặt mật khẩu quản trị (một lần)

Bấm biểu tượng bánh răng ở góc trên bên phải, nhập mật khẩu ít nhất 8 ký tự hai lần, bấm **Đặt mật khẩu**. Mật khẩu này chỉ cần để thay đổi cấu hình; nạp dữ liệu, xử lý việc và hỏi đáp không cần.

## Bước 2. Thêm doanh nghiệp

Bấm **Thêm doanh nghiệp** (trong trang Quản trị, hoặc chọn "+ Thêm doanh nghiệp" ở ô chọn doanh nghiệp). Nhập:

| Ô | Nhập |
|---|---|
| Mã số thuế | `0317776666` |
| Tên doanh nghiệp | `Công ty TNHH Phần mềm Sao Việt` |
| Địa chỉ | `Tầng 8, tòa nhà Mô Phỏng, quận Thử Nghiệm, TP Hồ Chí Minh` |
| Phương pháp tính thuế | Khấu trừ |
| Kỳ khai | Theo quý |
| Ngành nghề | `6201 Lập trình máy vi tính; 6202 Tư vấn máy vi tính; 6311 Xử lý dữ liệu, cho thuê máy chủ` |
| Năm tài chính kết thúc | Tháng 12 |

Phải thấy: gõ thử mã `0317776667` thì hiện **✗ Sai số kiểm tra**; gõ lại `0317776666` thì hiện **✓**. Bấm **Tiếp tục**: bước 2 đã đánh dấu sẵn 5 quy định gợi ý (thiết bị công nghệ thông tin, dịch vụ mua của nước ngoài, bản quyền trả trước, tiếp khách, hàng từ 30 triệu). Giữ nguyên, bấm **Tiếp tục** đến hết rồi **Tạo doanh nghiệp**.

## Bước 3. Nạp dữ liệu

Mở thư mục `A_tha_vao_Nap_nhanh`, chọn cả 6 tệp (Ctrl+A), kéo vào ô trong **Nạp dữ liệu → Nạp tệp** (hoặc bấm **Chọn tệp**).

Phải thấy:
- **Đã nhận 22 tệp**: 17 hóa đơn mua vào, 3 hóa đơn bán ra, 1 sao kê, 1 bảng kê cổng thuế.
- Khung xanh dương: **sao kê đã tự nhận dạng cột** (ngân hàng này hệ thống chưa gặp).
- Khung vàng: 1 hóa đơn ghi sai mã số thuế doanh nghiệp.
- Hệ thống tự phân tích: **12 việc, thuế có nguy cơ 17.400.000 đồng**.

## Bước 4. Nhập danh sách doanh nghiệp rủi ro

**Quản trị → Cấu hình doanh nghiệp → Danh sách rủi ro**. Tên: `Doanh nghiệp bỏ địa chỉ kinh doanh`; ngày: `15/09/2026`; bấm **Chọn tệp và nhập**, chọn tệp trong thư mục `B_nhap_o_Quan_tri`. Phải thấy **Đã nhập 2 mã số thuế**. Sang **Tổng quan**, bấm **Chạy phân tích**: có thêm việc "người bán trong danh sách rủi ro" (13 việc).

## Bước 5. Xử lý một việc

Vào **Việc cần xử lý**. Danh sách có ô chọn "Mọi vấn đề" để lọc theo nhóm, ô tìm kiếm và ô chọn tháng. Bấm hóa đơn **396** (bản quyền phần mềm 52.800.000 đồng, trả tiền mặt). Khung bên phải cho: lời giải thích dễ hiểu, bảng **"Nên xử lý thế nào để ít thiệt hại nhất"** (tự khai bổ sung ngay so với để cơ quan thuế phát hiện), các căn cứ. Chọn **Không kê khai khấu trừ hóa đơn này**, ghi lý do và người duyệt, bấm **Lưu**: thuế có nguy cơ giảm 4.800.000 đồng.

## Bước 6. Dùng AI (cần Ollama)

Vào **Việc cần xử lý**, khung "Trợ lý AI chạy trên máy":
1. Bấm **Phân loại dòng hàng** (khoảng 2 phút). Phải thấy việc **"Hàng hóa có thể không phục vụ kinh doanh"** cho hóa đơn 264 (máy chơi game PlayStation 5 Pro, tivi OLED 65 inch).
2. Bấm **Đọc nội dung chuyển khoản** (vài giây). Phải thấy **1 đề xuất**. Vào **Ngân hàng**: khoản 15.000.000 đồng nội dung "chuyen tien bao tri phong may cho nhat tin" được đề xuất ghép với hóa đơn 536 của Công ty Bảo trì Hệ thống Nhất Tín. Nhập tên người duyệt, bấm **Xác nhận**: việc "giao dịch cùng số tiền nhưng không xác định được" biến mất.

## Bước 7. Hỏi đáp

Trang **Hỏi đáp**, bấm **"Trợ lý trả lời được gì"** để xem 23 loại câu hỏi. Thử:

| Gõ | Phải thấy |
|---|---|
| Quý 3 có bao nhiêu thuế có nguy cơ bị loại? | Số tiền và bảng theo lý do, khớp trang Tổng quan |
| Vì sao hóa đơn 396 bị cảnh báo? | Thông tin hóa đơn kèm điều khoản luật làm căn cứ |
| Hạn nộp tờ khai gần nhất là khi nào? | Lịch thuế (hạn tờ khai quý 3 là 31/10/2026, vì thứ Bảy nên dời sang 02/11/2026) |
| Tiền chậm nộp tính bao nhiêu phần trăm một ngày? | Trích nguyên văn điều luật, mất 30 đến 60 giây |
| Thời tiết Hà Nội hôm nay? | Trợ lý từ chối, không đoán |

## Đáp án: các tình huống cài sẵn

| Tình huống | Hóa đơn | Hệ thống phải báo |
|---|---|---|
| Thuê máy chủ tháng 9, 19,8 triệu, chưa chuyển khoản | Mây Việt số 768 | Có nguy cơ (thuế 1,8 triệu); đồng thời "không có trên bảng kê cổng thuế" |
| Bản quyền phần mềm 52,8 triệu trả tiền mặt | Toàn Cầu số 396 | Có nguy cơ (thuế 4,8 triệu) |
| 3 lần mua ổ cứng cùng ngày 27/8, mỗi lần 2,2 triệu, tiền mặt | Hưng Thịnh số 408, 409, 410 | Mua nhiều lần trong ngày (cộng dồn 6,6 triệu) |
| Bản sao hóa đơn laptop nhập trùng | Phương Nam số 675 (bản sao) | Hóa đơn trùng (thuế 9,6 triệu) |
| Ghi nhầm mã số thuế người mua | Hà Thành số 714 | Có nguy cơ (thuế 0,6 triệu); vẫn nạp kèm cảnh báo |
| Bảo trì phòng máy 15 triệu, trả từ tài khoản giám đốc | Nhất Tín số 536 | Cần xem; sau bước 6 AI đề xuất ghép, bấm Xác nhận thì hết |
| Máy chủ 77 triệu của người bán mới, hóa đơn số 4 | Minh Phát số 4 | Người bán phát hành rất ít hóa đơn |
| PlayStation 5 Pro và tivi OLED | An Khang số 264 | Sau bước 6: hàng có thể không phục vụ kinh doanh; sau bước 4: người bán trong danh sách rủi ro |
| Hóa đơn có trên cổng thuế nhưng không có tệp | Phương Nam số 999 | Có thể đang bỏ sót khấu trừ (thuế 2,4 triệu) |
| Khách tạm ứng 150 triệu ngày 30/9, chưa có hóa đơn bán ra | (sao kê) | Có tiền khách trả chưa đối chiếu được với hóa đơn bán ra |

Tổng thuế đầu vào có nguy cơ khi chưa xử lý gì: **17.400.000 đồng** = 1,8 + 4,8 + 0,6 + 9,6 + 0,6 triệu.
