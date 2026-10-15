# Chỉ số kinh tế và KPI

## 1. Chỉ số kinh tế phía doanh nghiệp (khách hàng)

| Chỉ số | Công thức | Nguồn đầu vào |
|---|---|---|
| Tổn thất kỳ vọng hằng năm EL | `Doanh thu × λ`, λ là tỷ lệ tổn thất gian lận kỳ vọng so với doanh thu | λ **chưa đo được**; giả định 0,1% đến 1% (ACFE ước tính chuyên gia khoảng 5%) |
| Phần tổn thất tránh được s | `Tỷ lệ vụ phát hiện thực × (1 − D1/D0)` | D0 = 12 tháng (ACFE), D1 = 3 tháng giả định, tỷ lệ phát hiện thực = 50% tỷ lệ trên dữ liệu tổng hợp |
| Tổn thất tránh được | `EL × s` | |
| Chi phí sản phẩm | Phí cấp phép + thời gian rà soát + khấu hao nối dữ liệu | Tệp 05 |
| Lợi ích ròng | `EL × s − chi phí sản phẩm` | |
| ROI | `(Lợi ích ròng + chi phí sản phẩm) / chi phí sản phẩm − 1` hoặc `Lợi ích ròng / chi phí sản phẩm` (nói rõ định nghĩa) | |
| λ hòa vốn | `Chi phí sản phẩm / (Doanh thu × s)` | Chỉ số bền nhất: không cần biết λ |
| Chi phí trên mỗi cảnh báo đúng | `(1 / precision) × thời gian mỗi cảnh báo × giá giờ` | Precision@B3 4,5%: 22 cảnh báo, 3,7 giờ, khoảng 316 nghìn đồng mỗi cảnh báo đúng (kèm giả định 10 phút, 85 nghìn đồng/giờ) |

## 2. Chỉ số vận hành phía người dùng

| Chỉ số | Mục tiêu đề xuất **[G]** | Đo ở đâu |
|---|---|---|
| Số cảnh báo mỗi công ty mỗi tuần | không quá 3 | Cấu hình, nhật ký |
| Thời gian rà soát mỗi tuần | không quá 30 phút | Bấm giờ trong thí điểm |
| Tỷ lệ cảnh báo được đánh giá "đáng kiểm tra" | từ 25% (tối thiểu 15%) | Phản hồi trong giao diện |
| Thời gian từ cảnh báo đến kết luận | trung vị không quá 3 ngày làm việc | Nhật ký |
| Tỷ lệ cảnh báo có lý do được người dùng hiểu | từ 90% | Khảo sát nhanh |
| Tỷ lệ người dùng còn dùng sau 3 tháng | từ 80% | Nhật ký sử dụng |

## 3. Chỉ số bên cung cấp

| Chỉ số | Công thức |
|---|---|
| Doanh thu thường niên định kỳ (ARR) | Số khách × phí |
| Lợi nhuận gộp mỗi khách | Phí − máy chủ − hỗ trợ − chi phí bán |
| Số khách hòa vốn vận hành | Chi phí cố định hằng năm / lợi nhuận gộp mỗi khách |
| Số khách hòa vốn có khấu hao | (Chi phí cố định hằng năm + chi phí xây dựng / 3) / lợi nhuận gộp mỗi khách |
| Thời gian hoàn vốn khách | Chi phí nối dữ liệu / lợi ích ròng hằng tháng |
| Tỷ lệ rời bỏ | Khách ngừng / tổng khách |

## 4. KPI thí điểm (3 đến 5 doanh nghiệp, 3 đến 6 tháng, chế độ chỉ xem)

| KPI | Cách đo | Ngưỡng thành công |
|---|---|---|
| K1. Số cảnh báo thật mỗi công ty mỗi tuần | Đếm | Đúng ngân sách |
| K2. Tỷ lệ cảnh báo "đáng kiểm tra" | Phản hồi | Từ 15% |
| K3. Số phát hiện có giá trị (sai sót, vi phạm quy trình, nghi vấn gian lận) | Kết luận của kế toán trưởng và chủ | Ít nhất 1 phát hiện có giá trị mỗi 2 doanh nghiệp |
| K4. Kết quả chèn kiểm thử có sự đồng ý (ví dụ chi tiêu giả có kiểm soát) | Chèn trong môi trường thử | Phát hiện từ 50% |
| K5. Thời gian rà soát | Bấm giờ | Không quá 30 phút mỗi tuần |
| K6. Sẵn lòng trả | Phỏng vấn, báo giá thử | Ít nhất 3 trên 5 doanh nghiệp đồng ý giá đề xuất |
| K7. Vấn đề pháp lý dữ liệu | Rà soát | Không có phát hiện nghiêm trọng |
| K8. Khoảng cách dữ liệu | Adversarial validation trên các trường không nhãn | AUC phân biệt thật/sinh dưới 0,8; ghi nhận nếu cao hơn |

## 5. Chỉ số cảnh báo sớm cho dự án
- Độ chênh giữa kết quả phát triển và kết quả niêm phong trên cùng cấu hình (chênh lớn nghĩa là quá khớp phát triển).
- Độ chênh giữa kết quả tổng hợp và kết quả ngoài (ERP Fraud Data, DFKI).
- Tỷ lệ cảnh báo trên ca hợp lệ khó vượt 20%.
