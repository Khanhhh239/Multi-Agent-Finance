# Hạn chế và việc cần làm về dữ liệu

## 1. Hạn chế đã biết

| # | Hạn chế | Hệ quả | Cách giảm |
|---|---|---|---|
| L1 | Toàn bộ là tổng hợp | Hiệu năng thật chưa biết | Thí điểm chế độ chỉ xem; đối chiếu BPI, chi trả thành phố |
| L2 | Hành vi gian lận do tay viết; cùng người viết bộ sinh và đặc trưng | Mô hình có giám sát có thể quen cách viết của tôi; AP 0,5 là giới hạn trên | Bộ kịch bản độc lập do người khác viết; tập niêm phong mới |
| L3 | Số tiền mỗi vụ rất thấp so với ACFE; vụ ngắn | Không dùng cho tính kinh tế; độ sớm không so được | Lưới độ nhạy (tệp 07); sinh bản có số tiền lớn và vụ dài |
| L4 | Không có dòng hàng chi tiết trên hóa đơn (chỉ đơn giá và số lượng một dòng) | Bán không ghi doanh thu, trộm hàng chỉ để lại dấu vết gián tiếp; giá theo mặt hàng không kiểm được | Nhận hóa đơn điện tử XML có dòng hàng |
| L5 | Không có sao kê ngân hàng riêng | Không đối chiếu độc lập tiền thật | Thêm bảng sao kê sinh từ dòng tiền |
| L6 | Không có tồn kho theo mã hàng | Trộm hàng chỉ thấy qua hủy hàng | Thêm sổ tồn kho đơn giản |
| L7 | Chỉ 48 hoặc 40 công ty mỗi thế giới; cùng một họ bộ sinh | Phụ thuộc phân phối bộ sinh | Nhiều thế giới, ngẫu nhiên hóa mạnh hơn |
| L8 | Nhãn giả định "gian lận chưa bị phát hiện" trong P2 là nhãn 0 | Mô phỏng nhãn bị thiếu, chưa mô phỏng nhãn nhiễu theo người | Mô phỏng nhiễu nhãn 0%, 15%, 30% (đã làm ở vòng phản hồi) |
| L9 | Một giai đoạn kiểm thử khoảng 200 dòng dương mỗi thế giới | Sai số recall khoảng 3 điểm phần trăm | Nhiều thế giới; bootstrap theo vụ |
| L10 | Lịch lễ minh họa, không phải lịch thật | | Thay bằng lịch thật |

## 2. Việc cần làm (xếp theo giá trị)

1. **Bộ kịch bản độc lập:** nhờ một người khác (kiểm toán viên hoặc kế toán) viết 5 đến 10 kịch bản gian lận bằng văn xuôi, rồi mã hóa không xem đặc trưng; làm tập niêm phong mới.
2. **Nhận dữ liệu thật ở chế độ chỉ xem** ở 3 đến 5 doanh nghiệp; chạy chẩn đoán khoảng cách (tệp 08).
3. **Lưới độ nhạy** (tệp 07 mục 4).
4. **Bổ sung dòng hàng hóa đơn, sao kê ngân hàng, tồn kho** vào bộ sinh.
5. **Sinh quy mô lớn** (tệp 08) và tối ưu tốc độ.
6. **Chạy BPI 2019, 2020 và bộ chi trả thành phố** để đếm cảnh báo trên 1.000 giao dịch.
