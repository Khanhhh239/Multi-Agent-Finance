# Pha E. Thí điểm và pháp lý

Mục tiêu: thay giả định bằng số đo thật. **Không bán** khi chưa có kết quả pha này. Phần lớn là việc con người; coding agent soạn tài liệu, mã đo, mẫu biểu và hỗ trợ phân tích. Những việc cần người thật được đánh dấu **[NGƯỜI]**.

## E1. Thẩm định pháp lý **[NGƯỜI]** (trước khi nhận bất kỳ dữ liệu thật nào)

Câu hỏi cần luật sư trả lời bằng văn bản:
1. Nghị định 13/2023/NĐ-CP: giám sát giao dịch gắn với tên nhân viên (người lập, người duyệt, bảng lương) có cần sự đồng ý của nhân viên hay chỉ cần thông báo? Căn cứ pháp lý của "lợi ích hợp pháp" của người sử dụng lao động?
2. Hợp đồng lao động và nội quy: cần bổ sung điều khoản nào để doanh nghiệp được phép dùng giám sát tự động?
3. Lưu trữ và chuyển dữ liệu ra ngoài doanh nghiệp: điều kiện (đánh giá tác động, hợp đồng xử lý dữ liệu).
4. Trách nhiệm khi cảnh báo sai gây hại nhân viên.
5. Quy định bảo mật dữ liệu kế toán (Luật Kế toán, bảo mật thông tin).
Đầu ra: biên bản tư vấn; danh mục việc doanh nghiệp phải làm.

## E2. Gói tài liệu thí điểm (coding agent soạn)

Tạo trong `docs/05_ke_hoach_giao_viec/templates/`:
- `thoa_thuan_du_lieu.md`: mẫu thỏa thuận (phạm vi dữ liệu, mục đích nghiên cứu, ẩn danh hóa, thời hạn lưu, quyền rút, bên chịu trách nhiệm, không chia sẻ).
- `thong_bao_nhan_vien.md`: mẫu thông báo cho nhân viên.
- `ke_hoach_do_luong.md`: các KPI K1 đến K8 (thư mục 03 tệp 02), cách đo và biểu mẫu thu thập.
- `kich_ban_chen_co_kiem_soat.md`: danh sách giao dịch thử (chi tiền mặt sát hạn mức, thanh toán trùng một hóa đơn thật, tạm ứng không hoàn trong môi trường thử), cách hủy sau, chữ ký đồng ý.
- `phieu_phan_hoi.md`: các lựa chọn kết luận và lý do ngắn.
- `phong_van.md`: câu hỏi phỏng vấn 4 tuần và 12 tuần (độ hiểu lý do, hành động đã làm, giá).
Mỗi mẫu đánh dấu "cần luật sư duyệt".

## E3. Chọn doanh nghiệp **[NGƯỜI]**

Tiêu chí: 20 đến 100 nhân sự; có phần mềm kế toán xuất được sổ chi tiết kèm người lập, người duyệt, thời gian; ít nhất 12 tháng lịch sử; chủ đồng ý ký thỏa thuận; đa dạng ngành (thương mại, sản xuất, dịch vụ). Nguồn: mạng lưới đơn vị kế toán dịch vụ, hiệp hội. Số lượng: 3 đến 5.

## E4. Chạy thí điểm chế độ chỉ xem

1. Nhận dữ liệu (E3, C4), kiểm đầu vào (C3), **ẩn danh hóa tại chỗ** nếu có thể (đổi tên người, tài khoản thành mã).
2. Đo khoảng cách miền (D5.4) giữa doanh nghiệp thật và dữ liệu sinh; **nếu AUC phân biệt trên 0,9, cảnh báo rằng mô hình huấn luyện sẵn có thể không chuyển giao** và chạy chế độ `cold` trước.
3. Chạy hằng tuần ở chế độ `cold`, sau đó `precision` (đo hai chế độ cùng nhau, để so).
4. Thu phản hồi: mỗi cảnh báo người dùng chọn một trong "đáng kiểm tra", "hợp lệ", "nghi vấn", "xác nhận".
5. **Chèn có kiểm soát** (E2) vào tháng thứ hai: đo tỷ lệ phát hiện thực.
6. Bấm giờ rà soát.
7. Phỏng vấn tuần 4 và 12.

## E5. Phân tích kết quả (coding agent)
- Tính K1 đến K8; điền vào bảng KPI; so với cổng G7.
- Hệ số suy giảm thực: tỷ lệ phát hiện chèn trên doanh nghiệp thật chia tỷ lệ trên dữ liệu tổng hợp cho cùng kịch bản.
- Cập nhật phép tính kinh tế (thư mục 03 tệp 05) với số thật: λ (nếu có phát hiện thật), tỷ lệ phát hiện, giờ rà soát, sẵn lòng trả.
- Cập nhật bộ sinh theo khoảng cách miền.
- Quyết định đi/không đi tiếp (ghi rõ điều kiện).

## E6. Điều kiện dừng
Dừng thí điểm và báo chủ dự án ngay nếu: (a) doanh nghiệp rút lại đồng ý; (b) phát hiện dữ liệu cá nhân lộ ra ngoài phạm vi; (c) một cảnh báo gây hậu quả bất lợi cho một nhân viên; (d) phát hiện gian lận thật nghiêm trọng (cần quy trình báo cáo cho chủ doanh nghiệp và tư vấn pháp lý, không tự kết luận).
