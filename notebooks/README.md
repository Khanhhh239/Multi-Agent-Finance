# Notebook thực nghiệm Agent 1

Chạy theo thứ tự dưới đây; mỗi bước sử dụng artifact của các bước trước. Đường dẫn được tính theo gốc repo, kể cả khi mở notebook từ `notebooks/`. [Tổng quan hiện tại](../docs/project-overview.md) xác định đầu vào còn thiếu và trạng thái tích hợp; [Getting started](../docs/getting-started.md) hướng dẫn môi trường.

| Bước | Notebook | Nội dung |
|---|---|---|
| 01 | [Data preparation và EDA](01_data_preparation_eda.ipynb) | Chuẩn hóa AR, chất lượng dữ liệu, feature as-of và rolling snapshot |
| 02 | [Payment baselines](02_payment_baselines.ipynb) | B1/B1R, dự báo theo lịch sử khách và cổng baseline |
| 03 | [LightGBM payment quantiles](03_lightgbm_payment_quantiles.ipynb) | Phân vị ngày trả P10/P50/P90, chia theo thời gian và so baseline |
| 04 | [Conformal calibration](04_conformal_calibration.ipynb) | CQR, nhóm calibration, coverage và residual pool |
| 05 | [Monte Carlo cash-in](05_monte_carlo_cash_in.ipynb) | Copula, lấy mẫu thời điểm trả, backtest và phân phối cash-in |
| 06 | [Stress testing và regime detection](06_stress_testing_regime_detection.ipynb) | Kịch bản cú sốc, PSI và phát hiện điểm gãy |
| 07 | [Backtesting và evaluation](07_backtesting_evaluation.ipynb) | Metric hóa đơn/dòng tiền, phân khúc và cổng GO/NO-GO |
| 08 | [Discrete-time survival](08_discrete_time_survival.ipynb) | Hazard, censoring và kiểm chứng bằng tiền |
| 09 | [Collection prioritization](09_collection_prioritization.ipynb) | Xếp hạng thu nợ, năng lực xử lý và sàng lọc rủi ro |
| 10 | [Cash-in dashboard](10_cash_in_dashboard.ipynb) | Dashboard thử nghiệm, context pack và bản nháp nhắc nợ |
| 11 | [Extended-window retraining](11_extended_window_retraining.ipynb) | Thử train lại trên lưới cutoff mở rộng; [nguồn Python](11_extended_window_retraining.py) |
| 12 | [OOF Survival-Boost](12_oof_survival_boost.ipynb) | So feature survival in-sample, OOF và walk-forward; [nguồn Python](12_oof_survival_boost.py) |

[survival_utils.py](survival_utils.py) dùng chung cho 11/12. Hai file `.py` là nguồn để dựng các notebook tương ứng bằng [build_notebook.py](../scripts/notebooks/build_notebook.py):

```powershell
python scripts/notebooks/build_notebook.py 11_extended_window_retraining
python scripts/notebooks/build_notebook.py 12_oof_survival_boost
```

Chạy lệnh từ gốc repo. Công cụ sẽ thực thi toàn bộ cell trước khi ghi `.ipynb`, vì vậy cần có dữ liệu và artifact của các bước trước.

[Notebook tổng hợp](archive/invoice_forecast_full_pipeline.ipynb) là bản lưu trước khi chia pipeline thành các bước. Nội dung và kết quả cũ được giữ để đối chiếu.
