# Kết quả Isolation Forest trên dữ liệu tổng hợp

Phiên bản dữ liệu: 2.0. Mã chi phí ML chuẩn hóa về nhóm 642; sổ cái giữ mã theo TT133/TT200.
Tập test: 25,000 quan sát; 75 gian lận (0.30%).
Average precision (AP): 0.0342. Mốc tỷ lệ dương tính: 0.0030.
Ngưỡng cảnh báo lấy từ validation chưa gán nhãn; train không dùng nhãn.

| Ngân sách validation | Precision test | Recall test | Cảnh báo sai | Tổng cảnh báo |
| --- | ---: | ---: | ---: | ---: |
| 0.1% | 13.8% | 5.3% | 25 | 29 |
| 0.3% | 6.4% | 6.7% | 73 | 78 |
| 0.5% | 7.8% | 13.3% | 119 | 129 |

| Loại gian lận | Số mẫu test | Phát hiện | Recall |
| --- | ---: | ---: | ---: |
| duplicate_payment | 13 | 0 | 0.0% |
| ghost_vendor | 13 | 0 | 0.0% |
| long_outstanding_advance | 12 | 5 | 41.7% |
| period_end_adjustment | 12 | 0 | 0.0% |
| risky_invoice | 12 | 0 | 0.0% |
| split_payments | 13 | 0 | 0.0% |

Kết quả chỉ đo trên mô phỏng. AP dùng `average_precision_score`; điểm IF không phải xác suất gian lận.
Đọc `metrics.json` để xem khoảng Wilson, precision@k, recall theo vụ, biến thể và báo nhầm trên hard negatives.
