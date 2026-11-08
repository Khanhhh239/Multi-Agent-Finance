# Kết quả Isolation Forest trên dữ liệu tổng hợp

Phiên bản dữ liệu: 2.0. Mã chi phí ML chuẩn hóa về nhóm 642; sổ cái giữ mã theo TT133/TT200.
Tập test: 25,000 quan sát; 25 gian lận (0.10%).
Average precision (AP): 0.0067. Mốc tỷ lệ dương tính: 0.0010.
Ngưỡng cảnh báo lấy từ validation chưa gán nhãn; train không dùng nhãn.

| Ngân sách validation | Precision test | Recall test | Cảnh báo sai | Tổng cảnh báo |
| --- | ---: | ---: | ---: | ---: |
| 0.1% | 0.0% | 0.0% | 23 | 23 |
| 0.3% | 1.5% | 4.0% | 64 | 65 |
| 0.5% | 0.9% | 4.0% | 105 | 106 |

| Loại gian lận | Số mẫu test | Phát hiện | Recall |
| --- | ---: | ---: | ---: |
| duplicate_payment | 4 | 0 | 0.0% |
| ghost_vendor | 5 | 0 | 0.0% |
| long_outstanding_advance | 4 | 1 | 25.0% |
| period_end_adjustment | 4 | 0 | 0.0% |
| risky_invoice | 4 | 0 | 0.0% |
| split_payments | 4 | 0 | 0.0% |

Kết quả chỉ đo trên mô phỏng. AP dùng `average_precision_score`; điểm IF không phải xác suất gian lận.
Đọc `metrics.json` để xem khoảng Wilson, precision@k, recall theo vụ, biến thể và báo nhầm trên hard negatives.
