# Hiệu chỉnh và giả định

Phân biệt rõ tham số **có nguồn** với tham số **do người thiết kế đặt**. Người dùng dữ liệu không được coi tham số giả định là sự thật.

## 1. Có nguồn

| Tham số | Giá trị trong bộ sinh | Nguồn | Kết quả thực tế (3 thế giới phát triển) |
|---|---|---|---|
| Cấp người thực hiện | nhân viên .37, quản lý .41, lãnh đạo .19 (trọng số chọn) | ACFE 2024 [Đ] | Nhân viên 40 đến 49%, quản lý 43 đến 51%, lãnh đạo 7 đến 9% (lệch do không phải kịch bản nào cũng có vai trò lãnh đạo phù hợp) |
| Thông đồng | một người .46, hai .18, từ ba .36 | ACFE 2024 [Đ] | Một người 44 đến 53%; hai người 13 đến 18%; từ ba người 32 đến 41% |
| Tỷ lệ loại gian lận theo quy mô nhỏ | trọng số kịch bản theo tỷ lệ dưới 100 nhân sự (billing 31%, tamper 23%, skimming 19%, ...) | ACFE 2024 [Đ] | Xem tệp 05 |
| Có che giấu | 85% (L1 + L2) | ACFE: 89% [Đ] | |
| Hành vi trả tiền của khách | đúng hạn 45 đến 72%, nợ xấu 1 đến 5%, kỳ hạn 30 đến 60 ngày | Atradius 2025 Việt Nam [T] | |
| Chuẩn kế toán | TT133, TT200, cặp tài khoản chuẩn | Thông tư 133, 200 | Sổ cân 100% |
| Thủ đoạn kịch bản | 37 kịch bản | ACFE fraud tree; vụ án Việt Nam | Tệp 05 |

## 2. Do người thiết kế đặt (giả định)

| Tham số | Giá trị | Ghi chú |
|---|---|---|
| Tỷ lệ dòng gian lận | 0,4% | ACFE không cho tỷ lệ theo giao dịch; khuyến nghị chạy lưới 0,01%, 0,1%, 1% (chưa làm) |
| Tỷ lệ L0, L1, L2 | .15, .45, .40 | Chỉ tổng 85% có nguồn |
| Thời gian vụ | 30 đến 170 ngày | **Nén** so với ACFE 8 đến 24 tháng |
| Số tiền mỗi vụ | `8 triệu × hệ số × cấp` | **Rất thấp so với ACFE** (xem dưới) |
| Hạn mức tự duyệt, ngưỡng duyệt | 1 đến 5 triệu; 50 triệu | Giả định của công ty minh họa |
| Tỷ lệ công ty có vụ | 55% | |
| Tỷ lệ ca hợp lệ giống gian lận | 9% dòng | |
| Chỉ số kịch bản trong sinh vụ | trọng số theo bảng | Đặt tay quanh tỷ lệ ACFE |

## 3. Chỗ lệch cần biết

**Tổn thất mỗi vụ trong dữ liệu tổng hợp thấp hơn ACFE rất nhiều.** Trung vị `loss_vnd` mỗi vụ chỉ 29 đến 42 triệu đồng (khoảng 1.100 đến 1.600 đô la ở tỷ giá giả định 26.000), trong khi ACFE ghi 141.000 đô la cho tổ chức dưới 100 nhân sự và 60.000 đô la cho nhân viên. Lý do: mỗi công ty có khoảng 3.600 dòng trong 30 tháng, nên số tiền theo từng dòng nhỏ; vụ ngắn (trung vị 87 ngày). Hệ quả:

- **Không dùng cột `loss_vnd` của dữ liệu tổng hợp để tính hiệu quả kinh tế.** Phần kinh tế dùng ACFE trực tiếp (thư mục 03).
- Không dùng số tiền làm đặc trưng quyết định giữa các giai đoạn khi thay đổi quy mô.
- Cần lưới độ nhạy: nhân hệ số tiền 10 và 50 để xem mô hình có phụ thuộc quy mô tiền hay không (thí nghiệm H9, thư mục 05).

**Thời gian vụ bị nén** nên "độ sớm" đo trên dữ liệu tổng hợp (trung vị trễ 0 ngày) không so được với 12 tháng của ACFE. Chỉ so sánh tương đối giữa các phương pháp.

## 4. Bảng nhạy cảm cần chạy (chưa chạy)

| Tham số | Lưới | Câu hỏi |
|---|---|---|
| Tỷ lệ gian lận | 0,05%, 0,1%, 0,4%, 1% | Precision@B và vị trí các phương pháp có đổi không |
| Tỷ lệ L0:L1:L2 | .05:.35:.60 và .30:.50:.20 | Thứ hạng phương pháp có đổi không |
| Tỷ lệ công ty có vụ | 25%, 55%, 85% | Precision gộp |
| Hệ số tiền | ×1, ×10, ×50 | Phụ thuộc quy mô tiền |
| Thời gian vụ | ×1, ×3 | Độ sớm và ổn định |
