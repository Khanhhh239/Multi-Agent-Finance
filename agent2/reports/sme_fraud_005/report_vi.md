# Kết quả Isolation Forest trên dữ liệu tổng hợp

Phiên bản dữ liệu: 2.0. Mã chi phí ML chuẩn hóa về nhóm 642; sổ cái giữ mã theo TT133/TT200.
Tập test: 25,000 quan sát; 125 gian lận (0.50%).
Average precision (AP): 0.0533. Mốc tỷ lệ dương tính: 0.0050.
Ngưỡng cảnh báo lấy từ validation chưa gán nhãn; train không dùng nhãn.

| Ngân sách validation | Precision test | Recall test | Cảnh báo sai | Tổng cảnh báo |
| --- | ---: | ---: | ---: | ---: |
| 0.1% | 29.4% | 4.0% | 12 | 17 |
| 0.3% | 9.2% | 4.8% | 59 | 65 |
| 0.5% | 10.9% | 11.2% | 114 | 128 |

| Loại gian lận | Số mẫu test | Phát hiện | Recall |
| --- | ---: | ---: | ---: |
| duplicate_payment | 21 | 0 | 0.0% |
| ghost_vendor | 21 | 0 | 0.0% |
| long_outstanding_advance | 20 | 6 | 30.0% |
| period_end_adjustment | 21 | 0 | 0.0% |
| risky_invoice | 21 | 0 | 0.0% |
| split_payments | 21 | 0 | 0.0% |

Kết quả chỉ đo trên mô phỏng. AP dùng `average_precision_score`; điểm IF không phải xác suất gian lận.
Đọc `metrics.json` để xem khoảng Wilson, precision@k, recall theo vụ, biến thể và báo nhầm trên hard negatives.
