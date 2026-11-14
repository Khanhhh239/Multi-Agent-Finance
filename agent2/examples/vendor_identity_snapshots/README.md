# JSON mẫu B5/E4 — mô phỏng

Mỗi doanh nghiệp C001/C002 có năm gói snapshot input 1.2.0:

- `*_signal.json`: NCC trùng tài khoản và điện thoại.
- `*_control.json`: NCC có thông tin khác nhau.
- `*_phone_only.json`: chỉ trùng điện thoại.
- `*_address_only.json`: chỉ trùng địa chỉ, tín hiệu yếu theo engine giữ lại.
- `*_declared.json`: trùng thông tin và có khai báo quan hệ đã biết đúng lúc.

Mỗi tệp có một giao dịch và nguồn master riêng; ID giao dịch giữa hai doanh
nghiệp cố ý giống nhau. Các tệp không chứa nhãn/điểm/kết quả kỳ vọng. Đây là
dữ liệu mô phỏng, không phải chứng từ gốc. Không có hóa đơn/phân bổ nên chưa
đủ nguồn P1. JSON này khác profile native 35 luật trước đó.

[Cách chạy pipeline và đọc kết quả](../../docs/VENDOR_IDENTITY_SNAPSHOT.md).
