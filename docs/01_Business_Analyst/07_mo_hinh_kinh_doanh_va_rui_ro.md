# 7. Mô hình kinh doanh và rủi ro

## 7.1 Mô hình doanh thu (đề xuất, cần kiểm chứng bằng phỏng vấn giá)

| Gói | Đối tượng | Giá (giả định) | Gồm |
|---|---|---|---|
| Starter | DN <20 tỷ/năm, 1 pháp nhân | 750.000đ/tháng (9 triệu/năm) | Dải 13 tuần, cảnh báo, lịch nghĩa vụ, khớp sao kê 1 tài khoản |
| Growth | 20–150 tỷ/năm | 1.500.000đ/tháng (18 triệu/năm) | + danh sách đòi nợ, kịch bản, nhiều tài khoản NH, T2 nợ xấu |
| Partner/API | Phần mềm kế toán, ngân hàng | chia doanh thu / phí theo DN | API dự báo, nhúng vào sản phẩm đối tác |

Cơ sở giá: thấp hơn hoặc ngang gói phần mềm kế toán đang trả; bằng 1/10–1/5 giá Float (£79–295/tháng); và nhỏ hơn
~1/20 giá trị kinh tế tạo ra (03_Evaluation/06).

## 7.2 Kênh

1. **Tích hợp phần mềm kế toán / HĐĐT** (đã có dữ liệu, có tệp khách) — kênh chính.
2. **Ngân hàng**: dự báo dòng tiền có kiểm định làm đầu vào thẩm định vốn lưu động; tặng sản phẩm cho khách DN.
3. **Văn phòng dịch vụ kế toán**: một kế toán phục vụ 10–30 DN → đòn bẩy phân phối.

## 7.3 Cấu trúc chi phí (chi tiết ở 03_Evaluation/05)

Chi phí cố định: đội phát triển, đối chiếu pháp lý hằng năm, bảo mật/kiểm toán. Chi phí biến đổi rất thấp: mô hình
cây + mô phỏng chạy CPU; LLM chỉ diễn giải số → vài trăm token/cảnh báo.

## 7.4 Rủi ro và giảm thiểu

| Loại | Rủi ro | Xác suất | Tác động | Giảm thiểu |
|---|---|---|---|---|
| Dữ liệu | Chưa có dữ liệu hoá đơn – thanh toán thật của SME VN | Cao | Cao | Ba tầng dữ liệu; domain adaptation; T13 với đối tác; ghi rõ phạm vi kết luận |
| Dữ liệu | Ngày ghi sổ theo lô làm nhãn sai | Cao | Cao | Sao kê làm nguồn sự thật (T9); nhãn khoảng khi không có sao kê |
| Mô hình | Sốc chưa từng thấy (thiên nga đen) | Trung bình | Cao | T7 chế độ khủng hoảng, kịch bản căng thẳng tất định, ACI nới khoảng |
| Mô hình | Quá tự tin (khoảng quá hẹp) | Trung bình | Cao | CQR/ACI, giám sát độ phủ hằng tuần |
| Sản phẩm | Người dùng không tin "AI" | Trung bình | Cao | Dải xác suất + lý do + nhãn nguồn số (mô hình / cam kết / kịch bản) |
| Sản phẩm | Cảnh báo giả nhiều → tắt thông báo | Trung bình | Trung bình | Ngưỡng theo chi phí quyết định; giới hạn báo giả (T7 ≤0,5/khách-năm) |
| Pháp lý | Dữ liệu cá nhân/doanh nghiệp | Thấp–TB | Cao | NĐ 13/2023, đồng ý rõ ràng, ẩn danh, không gửi dữ liệu thô ra ngoài |
| Pháp lý | Luật thuế/lương thay đổi | Cao | Trung bình | Quy tắc có ngày hiệu lực + kiểm thử; quy trình cập nhật hằng năm |
| Thị trường | Phần mềm kế toán lớn tự làm tính năng tương tự | Trung bình | Cao | Đi kênh đối tác sớm; lợi thế mô hình hành vi + dữ liệu tổng hợp + phản hồi thật |
| Đạo đức | Khuyến nghị đòi nợ gây áp lực khách nhỏ | Thấp | Trung bình | Chỉ xếp hạng ưu tiên; không tự động liên hệ; người duyệt cuối |

## 7.5 Lộ trình kinh doanh

| Giai đoạn | Mốc | Bằng chứng cần có |
|---|---|---|
| Bản mẫu thi (hiện tại) | T0, T1, T4, T5, T7, T9, T12 chạy; T6 demo | Vượt mốc trên tổng hợp + dữ liệu thật tương tự |
| Pilot (3–6 tháng) | 3–5 SME hoặc 1 văn phòng kế toán, chạy song song không can thiệp | Độ phủ khoảng thật, tỷ lệ khớp sao kê, mức dùng lại |
| Thương mại hoá | Kênh đối tác phần mềm kế toán / ngân hàng | Giảm DSO, giảm sự kiện thiếu hụt trên DN thật |
