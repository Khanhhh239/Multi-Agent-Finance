# Hiệu quả kinh tế: doanh nghiệp trước và sau khi có sản phẩm

**Cảnh báo đọc trước.** Chưa ai đo được tần suất và tổn thất gian lận thật của DNNVV Việt Nam. Phép tính dưới đây là **mô hình có giả định**, mục đích là (1) chỉ ra điều kiện để sản phẩm có lãi cho khách, (2) chọn phân khúc, (3) biết cần đo gì ở thí điểm. Không dùng con số tiền tiết kiệm như dự báo.

## 1. Cấu trúc phép tính

```
EL   = Doanh thu × λ                          tổn thất gian lận kỳ vọng mỗi năm
s    = (r_thật) × (1 − D1/D0)                 phần tổn thất tránh được
Lợi ích gộp = EL × s
Chi phí SP  = phí cấp phép + giờ rà soát × giá giờ + khấu hao nối dữ liệu
Lợi ích ròng = EL × s − Chi phí SP
λ hòa vốn = Chi phí SP / (Doanh thu × s)
```

## 2. Đầu vào và nguồn

| Đại lượng | Giá trị | Nguồn |
|---|---|---|
| λ (tổn thất kỳ vọng / doanh thu) | 0,1%; 0,25%; 0,5%; 1% | **[G]**. ACFE: tổ chức mất khoảng 5% doanh thu (ước tính chuyên gia, không phải đo); ta lấy 2% đến 20% của mức đó |
| r_thật: tỷ lệ vụ phát hiện thực | 50% của 87% = 43,5% (cơ sở); thận trọng 25% của 87%; lạc quan 75% của 87% | 87% là **vụ tìm thấy@B3 của L3 trên dữ liệu tổng hợp v4** [M]; hệ số 25%, 50%, 75% là **[G]** |
| D0 (phát hiện không có sản phẩm) | 12 tháng | ACFE 2024 [Đ] |
| D1 (có sản phẩm) | 3 tháng | **[G]**; dữ liệu tổng hợp cho trung vị trễ 0 ngày nhưng vụ bị nén |
| Tổn thất tăng đều theo thời gian | Có | **[G]**; nếu tổn thất tập trung đầu vụ, lợi ích thấp hơn |
| s | thận trọng 0,163; cơ sở 0,326; lạc quan 0,489 | `0,25 hoặc 0,5 hoặc 0,75` × 0,87 × 0,75 |
| Phí | siêu nhỏ 12; nhỏ 24; vừa 36 triệu đồng/năm | Giá đề xuất (BA 07) |
| Giờ rà soát | 26 giờ/năm (3 cảnh báo × 52 tuần × 10 phút) × 85.227 đồng/giờ (lương kế toán 15 triệu đồng/tháng chia 176 giờ) = 2,22 triệu đồng | **[G]** |
| Nối dữ liệu | 5 triệu đồng một lần, khấu hao 3 năm = 1,67 triệu đồng/năm | **[G]** |

Ba quy mô khách (theo Nghị định 80/2021):

| | Siêu nhỏ | Nhỏ | Vừa |
|---|---:|---:|---:|
| Nhân sự | 12 | 40 | 90 |
| Doanh thu (tỷ đồng/năm) | 8 | 60 | 250 |
| Chi phí sản phẩm mỗi năm (triệu đồng) | 15,9 | 27,9 | 39,9 |

## 3. Điểm hòa vốn: λ cần đạt (phần trăm doanh thu)

| Quy mô | Thận trọng (s = 0,163) | Cơ sở (s = 0,326) | Lạc quan (s = 0,489) |
|---|---:|---:|---:|
| Siêu nhỏ | 1,22% | 0,61% | 0,41% |
| Nhỏ | 0,285% | **0,142%** | 0,095% |
| Vừa | 0,098% | 0,049% | 0,033% |

Diễn giải: với doanh nghiệp nhỏ, nếu cứ 1.000 đồng doanh thu thì kỳ vọng mất 1,4 đồng vì gian lận nội bộ, sản phẩm đã huề vốn trong kịch bản cơ sở. ACFE ước tính mức mất khoảng 50 đồng trên 1.000 đồng; mức hòa vốn bằng khoảng một phần ba mươi lăm số đó. Với siêu nhỏ cần mức cao gấp bốn lần, nên **siêu nhỏ không phải thị trường mục tiêu của gói độc lập**.

## 4. Lợi ích ròng mỗi năm (triệu đồng), kịch bản cơ sở

| Quy mô | λ = 0,1% | λ = 0,25% | λ = 0,5% | λ = 1% |
|---|---:|---:|---:|---:|
| Siêu nhỏ | −13,3 | −9,4 | −2,8 | 10,2 |
| Nhỏ | −8,3 | 21,1 | **70,0** | 167,9 |
| Vừa | 41,7 | 164,0 | 367,9 | 775,7 |

Kịch bản thận trọng (s = 0,163), doanh nghiệp nhỏ: −18,1; −3,4; 21,1; 70,0. Kịch bản lạc quan (s = 0,489): 1,5; 45,5; 118,9; 265,7.

## 5. Bảng trước và sau (doanh nghiệp nhỏ, doanh thu 60 tỷ đồng, λ = 0,5%, kịch bản cơ sở)

| Khoản (triệu đồng/năm) | Trước | Sau | Ghi chú |
|---|---:|---:|---|
| Tổn thất gian lận kỳ vọng | 300,0 | 202,1 | giảm `300 × 0,326` = 97,9 |
| Thời gian rà soát thủ công của kế toán trưởng hoặc chủ (40 giờ rồi 10 giờ) | 3,4 | 0,9 | **[G]** |
| Rà soát bên ngoài định kỳ (một lần mỗi hai năm, 30 triệu đồng) | 15,0 | 15,0 | giữ nguyên, thận trọng |
| Phí sản phẩm | 0 | 24,0 | |
| Thời gian rà soát cảnh báo của sản phẩm | 0 | 2,2 | 26 giờ |
| Khấu hao nối dữ liệu | 0 | 1,7 | |
| **Tổng chi phí và tổn thất** | **318,4** | **245,9** | |
| **Tiết kiệm ròng** | | **72,5** | |

- Lợi ích gộp (tổn thất tránh được cộng giờ thủ công tiết kiệm) là 100,4 triệu đồng so với chi phí sản phẩm 27,9: tỷ lệ lợi ích trên chi phí 3,6 lần, tức ROI 2,6 (260%).
- Thời gian hoàn vốn chi phí nối dữ liệu (5 triệu đồng): chưa đầy 1 tháng nếu lợi ích đến đều; thực tế vụ gian lận là biến cố hiếm, nên lợi ích đến **theo cục** (một vụ lớn tránh được), không đều.

## 6. Quan điểm nhà cung cấp
Chi phí xây dựng 700 triệu đồng, vận hành cố định 250 triệu đồng/năm, lợi nhuận gộp mỗi khách 13,2 triệu đồng/năm: hòa vốn vận hành ở khoảng 19 khách và hòa vốn có khấu hao ở khoảng 37 khách (BA 07). Phân khúc mục tiêu 42.000 đến 83.000 DN (BA 01), 37 khách là khoảng 0,05% đến 0,09% phân khúc: **không phải rào cản về thị trường mà là rào cản về niềm tin và bán hàng**.

## 7. Điều phép tính này cố ý bỏ qua (nên làm tiếp)
1. Giá trị phòng ngừa (răn đe) khi nhân viên biết có giám sát; có thể lớn hơn giá trị phát hiện.
2. Tổn thất không phải tiền: uy tín, thời gian điều tra, rủi ro pháp lý.
3. Phân phối đuôi dày: một vụ cấp lãnh đạo (tổn thất lớn hơn 7 lần theo ACFE) có thể quyết định toàn bộ kết quả của nhiều năm; nhưng cấp này lại là cấp ít có người nhận cảnh báo độc lập.
4. Lợi ích thuế: phát hiện lỗi thuế do cùng dữ liệu (thuộc agent khác trong hệ thống).
5. Chi phí báo nhầm: người bị cảnh báo oan, quan hệ lao động.

## 8. Việc cần đo để thay giả định bằng số
| Giả định | Cách đo ở thí điểm |
|---|---|
| λ | Phỏng vấn kiểm toán viên và kế toán dịch vụ; thống kê vụ thật qua kênh pháp lý |
| Tỷ lệ phát hiện thực | Chèn có kiểm soát; so với dữ liệu tổng hợp để lấy hệ số suy giảm thật |
| D1 | Thời gian từ giao dịch đến cảnh báo đầu tiên trong chế độ chỉ xem |
| Giờ rà soát | Bấm giờ |
| Sẵn lòng trả | Thử giá |
