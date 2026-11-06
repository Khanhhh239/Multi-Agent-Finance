# T1 competing risks v5 (độc lập với v4)

Thử nghiệm này đọc cohort/model v4 theo hash, giữ nguyên bốn World train và bốn
World validation/test. Mọi model và bảng kết quả mới được ghi dưới
`outputs/data/v5_competing_risks_53w_20261028/`; không sửa artifact v4.

`protocol.json` khóa P0 (định nghĩa sự kiện, kiểm duyệt, credit note), mốc thời
gian, chân trời 53 tuần, chọn mẫu train và siêu tham số trước khi đọc kết quả.
`core.py` tạo nhãn sự kiện đầu tiên, khai triển risk set theo tuần, tích lũy
incidence và tính Aalen–Johansen. `run.py` train mô hình LightGBM ba lớp cho
paid/write-off/open rồi đánh giá v5/v4 trên cùng hóa đơn. Hai script còn lại
xuất event table và reliability bins để kiểm toán.

Trong môi trường đã cài package dự án:

```powershell
python -m experiments.t1_competing_v5.run --stage all
python -m experiments.t1_competing_v5.calibration
python -m experiments.t1_competing_v5.materialize_events
```

Model có 53 tuần để dự báo ngày 365 thực, không dùng đường đuôi cố định của v4.
Chỉ snapshot train trước 01/07/2024 được fit. Evaluation lấy snapshot đầu tiên
của mỗi hóa đơn trong từng World validation/test, có đủ thời gian theo dõi tới
ngày 365. `closure_type`, ngày paid/write-off và nhãn chỉ dùng sau khi tạo
feature nhìn thấy tại ngày cắt.

Xem [báo cáo đánh giá](../../docs/03_Evaluation/T1_V5_COMPETING_RISKS_2026-10-28.md).
