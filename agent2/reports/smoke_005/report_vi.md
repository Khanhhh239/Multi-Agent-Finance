# Kết quả Isolation Forest trên dữ liệu tổng hợp

Tập test: 2,500 quan sát; 12 gian lận (0.48%).
Average precision (AP): 0.0366. Mốc tỷ lệ dương tính: 0.0048.
Ngưỡng cảnh báo lấy từ validation chưa gán nhãn; train không dùng nhãn.

| Ngân sách validation | Precision test | Recall test | Cảnh báo sai | Tổng cảnh báo |
| --- | ---: | ---: | ---: | ---: |
| 0.1% | 0.0% | 0.0% | 0 | 0 |
| 0.3% | 8.3% | 8.3% | 11 | 12 |
| 0.5% | 11.8% | 16.7% | 15 | 17 |

| Loại gian lận | Số mẫu test | Phát hiện | Recall |
| --- | ---: | ---: | ---: |
| duplicate_payment | 2 | 0 | 0.0% |
| ghost_vendor | 2 | 0 | 0.0% |
| long_outstanding_advance | 2 | 1 | 50.0% |
| period_end_adjustment | 2 | 0 | 0.0% |
| risky_invoice | 2 | 0 | 0.0% |
| split_payments | 2 | 0 | 0.0% |

Kết quả chỉ đo trên mô phỏng. AP dùng `average_precision_score`; điểm IF không phải xác suất gian lận.
Đọc `metrics.json` để xem khoảng Wilson, precision@k, recall theo vụ, biến thể và báo nhầm trên hard negatives.
