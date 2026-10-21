# Đối chứng bổ sung cho dự báo số dư

`scripts/run_cash_baselines.py` chạy ETS, ARIMA và bảng tính đến hạn trên cùng
14 công ty × 52 cutoff với E2E dùng nhãn T9 ước lượng. Script kiểm tra số dư thật,
cohort và mẫu số chuẩn hoá khớp từng tuần trước khi ghép bảng.

- ETS: xu thế cộng có damping, không mùa vụ; bootstrap phần dư fit để mô phỏng 1.000 đường dòng ròng.
- ARIMA: cố định (1,0,1), có hằng số; mô phỏng đường có điều kiện từ trạng thái cuối lịch sử.
- Cả hai chỉ nhận 52 tuần dòng ròng tới cutoff. Fit không hội tụ hoặc đường không hữu hạn dùng mốc dự phòng
  đã khai báo: trung bình lịch sử cộng phần dư bootstrap iid. Số lần dự phòng và cảnh báo ghi trong
  `outputs/t6/traditional/fit_diagnostics.csv`; đây không phải kết quả của một ARIMA/ETS thuần nếu có dự phòng.
- B0: hoá đơn mở theo nhãn quan sát, thu đúng hạn (nợ quá hạn ở tuần 1), lịch chi ước lượng đã biết,
  doanh thu mới bằng trung bình lịch sử qua kernel thu tiền. Dự báo điểm có P10=P50=P90;
  chưa thêm capex không dự kiến và rút vốn chủ DN.

`scripts/run_chronos_baseline.py` chạy **Chronos-Bolt Tiny zero-shot** trên 52 số dư cuối tuần
đã quan sát, không fine-tune và không nhận nghĩa vụ chi tương lai. Revision cố định:
`a0e552de83495b5c28c14c71c374f3e33280b340`. Chạy CPU, float32, batch 32;
trọng số safetensors, hash checkpoint và phiên bản thư viện lưu trong metadata.
API và giấy phép được đối chiếu tại [model card của Amazon](https://huggingface.co/amazon/chronos-bolt-tiny).
Kết quả chỉ áp dụng cho bản Tiny và giao thức đầu vào này.

```powershell
.\.venv\Scripts\python.exe scripts/run_cash_baselines.py
# Cần phụ thuộc tuỳ chọn trong requirements-forecast.txt và tải checkpoint công khai lần đầu.
.\.venv\Scripts\python.exe scripts/run_chronos_baseline.py
.\.venv\Scripts\python.exe scripts/compare_cash_baselines.py
.\.venv\Scripts\python.exe scripts/make_report.py
```

So sánh cặp từ dự báo đã lưu nằm ở `outputs/t6/additional_baseline_comparisons.csv`.
Chiều cải thiện: dương nghĩa là E2E ACI tốt hơn đối chứng; CI bootstrap theo công ty, 300 lượt.
Không chọn lại tham số hoặc mô hình theo bảng test. G12 giữ tiêu chí bốn đối chứng gốc;
đạt G12 không đồng nghĩa thắng mọi đối chứng bổ sung. Mọi điểm và CI trong báo cáo được sinh từ CSV.
