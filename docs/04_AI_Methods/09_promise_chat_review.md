# T8: thu thập lời hứa từ chat và người duyệt

Đặc tả WP-8.4. API lưu chính thức là `POST /promises`, có xác thực và kiểm tra DN,
khách, hoá đơn, số tiền, ngày. Không tự biến một câu chat thành cam kết đã được khách xác nhận.

## Luồng xử lý

1. Người dùng đưa câu chat và ngày tham chiếu của cuộc hội thoại. Bộ trích xuất tạo **bản nháp**;
   chưa gọi API lưu, chưa dùng trong dự báo, chưa đặt `kept`.
2. Tra danh mục khách của DN. Tên trùng, tên viết tắt hoặc không có khách khớp phải giữ trạng thái cần đối chiếu.
   Không tự chọn hoá đơn nếu câu chat không xác định được hoá đơn.
3. Hiển thị người duyệt: nguyên văn, mã khách/hoá đơn, tiền và đơn vị, ngày hoặc khoảng ngày,
   nguồn hội thoại, thời điểm ghi nhận, những trường chưa rõ. Người duyệt xác nhận hoặc sửa.
4. Chỉ sau xác nhận, gửi JSON chuẩn hoá vào `POST /promises`. Máy chủ kiểm tra lại quyền DN và dữ liệu đầu vào.
   Không có ngày chính xác hoặc hoá đơn thì giữ bản nháp; API hiện hành chưa lưu khoảng thời gian mơ hồ.
5. Xác minh giữ lời từ tiền thực nhận tại thời điểm đến hạn; không lấy nhãn do bộ trích xuất hoặc người nhập suy đoán.
   Bản ghi đến hạn nhưng thiếu chứng từ vẫn chưa có outcome, không được dùng làm lịch sử T8.

## Ví dụ kiểm tra bản nháp

Với ngày hội thoại đã biết, câu “khách A xin khất 5 tỷ sang 15/8” cho các trường nháp:

```json
{
  "customer_text": "khách A",
  "amount": 5000000000,
  "currency": "VND",
  "date_text": "15/8",
  "customer_id": null,
  "invoice_id": null,
  "promised_date": null,
  "status": "needs_review"
}
```

Ngày không ghi năm phải đối chiếu bối cảnh; không mặc định sang năm sau chỉ vì đã qua hạn.
“Tuần sau” và “cuối tháng” là khoảng ngày, không tự biến thành một ngày chắc chắn.
Lời hứa trả một phần phải giữ số tiền riêng và kiểm không vượt dư nợ; lời hứa mới không tự xoá lịch sử khất trước đó.

## Bằng chứng hiện tại

`scripts/run_t8_reliability.py` đo Brier trên lời hứa tổng hợp sạch và nhiễu,
với lịch sử đóng băng hàng tuần và CI bootstrap theo công ty. Thí nghiệm không kiểm chất lượng trích xuất chat.
Giao diện duyệt chat chưa triển khai; yêu cầu WP-8.4 ở mức đặc tả, còn UAT cần người dùng thật.
