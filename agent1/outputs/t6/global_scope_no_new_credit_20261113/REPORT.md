# Backtest T6 global, phạm vi tiền rõ ràng — 13/11/2026

Dữ liệu 100% synthetic. Global là bản 18 feature Neural 75%/customer 25% đã khóa; Workspace học độc lập tại từng ngày chốt. Không học tiếp, đổi trọng số hoặc kích hoạt tenant.

## Phạm vi và giao thức

- Loại hoàn toàn nhánh dự báo thu từ hóa đơn phát hành sau ngày chốt, theo yêu cầu. Không fit/select learner new-credit.
- Hai đường T6: `ar_only` chỉ công nợ đang mở; `ar_operating_schedule` thêm thu bán ngay, lịch chi được biết và chi biến đổi. Hai model dùng cùng learner hoạt động/lịch chi/số dư đầu.
- 1.000 đường mô phỏng độc lập, seed 7; kỳ 13 tuần, ngưỡng tiền 200 triệu; giữ nguyên quy tắc cảnh báo của dịch vụ. Tắt SHAP trong vòng chấm điểm để dành thời gian cho backtest.
- Bốn ngày chốt: 2025-09-30, 2025-12-31, 2026-04-30, 2026-07-31. Các cửa sổ không chồng lấn. Mọi forecast được chạy lại khi bỏ bản ghi biết sau ngày chốt.
- Dải thô chưa hiệu chỉnh. P10–P90 đánh giá độ phủ từng tuần, không phải xác suất phủ toàn bộ 13 tuần. Không dùng các kế hoạch hồi cứu để giả thành lịch sử hiệu chỉnh prospective.

## Dự thu riêng danh mục mở

Chỉ bảng dữ liệu gốc dưới đây dùng để so dự thu; các stress lặp lại cùng danh mục nên không được cộng thêm cỡ mẫu T1. Đơn vị tiền: triệu VND.

| Model | MAE thu tuần | MAE thu lũy kế | Độ phủ dải thu lũy kế | Độ rộng |
|---|---:|---:|---:|---:|
| global75_25 | 198.75 | 1,630.46 | 0.0% | 538.76 |
| workspace | 64.16 | 299.77 | 53.8% | 606.74 |

## Số dư ngân hàng thực tế của bộ gốc

Giữ nguyên sao kê gốc, kể cả thu từ hóa đơn mới. Vì nhánh này đã bị loại, tiền đó nằm trong tác động ngoài phạm vi, không được âm thầm xóa khỏi nhãn. Bộ gốc thiếu lịch chi lịch sử; bật hoạt động không khiến phạm vi trở thành đầy đủ.

| Model | Đường T6 | MAE số dư | Độ phủ P10–P90 | Độ rộng | Interval score 80% | Báo giả / bỏ sót |
|---|---|---:|---:|---:|---:|---:|
| global75_25 | ar_only | 979.59 | 15.4% | 538.76 | 7,890.45 | 0 / 0 |
| global75_25 | ar_operating_schedule | 1,048.96 | 13.5% | 535.17 | 8,431.25 | 0 / 0 |
| workspace | ar_only | 2,035.29 | 9.6% | 606.74 | 17,979.60 | 0 / 0 |
| workspace | ar_operating_schedule | 2,140.09 | 9.6% | 610.95 | 18,978.78 | 0 / 0 |

## Stress số dư trong phạm vi đã khai báo

Bốn profile được khóa trước chấm: buffered, payment_pressure, cost_shock và schedule_gap. Đây là 16 fixture phản thực tế từ cùng bốn danh mục Đại Phát; không phải 16 doanh nghiệp độc lập hoặc holdout mới cho T1.
Các fixture ngừng phát hành hóa đơn sau ngày chốt. Số dư đầu lấy từ sao kê lịch sử; ngân hàng tương lai được dựng từ tiền thu danh mục mở, bán thu ngay, chi biến đổi và chi hợp đồng. Chi phí dùng quy mô tiền quá khứ; không chọn số tiền/ngưỡng theo kết quả tương lai.
payment_pressure có khoản chi lớn tuần 4 được biết tại origin; cost_shock tăng chi biến đổi tuần 5–9 chưa được biết tại origin; schedule_gap có một phần lịch chỉ được biết ngày chi. Bảng sau chỉ hiển thị đường có hoạt động/lịch; bảng đầy đủ giữ cả ar_only.

| Profile | Model | MAE số dư | Độ phủ | Độ rộng | Tuần thiếu tiền | Báo giả / bỏ sót | Recall tuần | Precision tuần | Brier tuần |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| buffered | global75_25 | 1,556.63 | 0.0% | 535.17 | 0 | 0 / 0 | — | — | 0.0000 |
| buffered | workspace | 292.11 | 55.8% | 610.95 | 0 | 0 / 0 | — | — | 0.0000 |
| cost_shock | global75_25 | 1,170.02 | 0.0% | 535.17 | 0 | 0 / 0 | — | — | 0.0000 |
| cost_shock | workspace | 474.29 | 44.2% | 610.95 | 0 | 0 / 0 | — | — | 0.0000 |
| payment_pressure | global75_25 | 1,556.63 | 0.0% | 535.17 | 26 | 14 / 0 | 100.0% | 65.0% | 0.2693 |
| payment_pressure | workspace | 292.11 | 55.8% | 610.95 | 26 | 13 / 6 | 76.9% | 60.6% | 0.2660 |
| schedule_gap | global75_25 | 1,290.99 | 1.9% | 535.17 | 26 | 0 / 26 | 0.0% | — | 0.5000 |
| schedule_gap | workspace | 2,618.26 | 15.4% | 610.95 | 26 | 0 / 26 | 0.0% | — | 0.5000 |

## Cách đọc và giới hạn

- `weekly.csv` phân rã sai số số dư thành lỗi thu AR, thu bán ngay, lịch chi, chi biến đổi và tác động ngoài phạm vi; tổng phải khớp sai số ngân hàng trong 0,01 VND.
- Số dư được chấm trực tiếp trên sao kê có đủ phủ, không lấy dự báo trừ ngược rồi gọi là số dư thực. Không coi tuần thiếu sao kê là dòng tiền bằng 0.
- MAE, bias, độ phủ, độ rộng, interval score, Brier, báo giả/bỏ sót, precision/recall được giữ theo profile, model, đường T6 và tuần 1–4/5–13. Recall/precision để trống khi không có mẫu số.
- `metrics.csv` có thêm đánh giá cảnh báo có ít nhất một lần trong kỳ ở cấp context; không ghép xác suất từng tuần thành một xác suất chung giả định độc lập.
- Một doanh nghiệp synthetic, các stress chung danh mục. Không tính khoảng tin cậy bằng cách coi tuần/profile là doanh nghiệp độc lập; không suy ra độ chính xác trên SME thật.
- Nghiên cứu không chọn model thắng để thay dịch vụ, không hiệu chỉnh ngưỡng trên outcomes và không đổi gate pilot.

## Bằng chứng và chạy lại

`protocol.json` khóa thiết kế trước chấm; `snapshot.json` giữ hash nguồn/đầu vào; `global_release/` giữ release global; `models/` giữ Workspace và learner hoạt động tại từng ngày; `plans/` giữ dự báo thực; `fixtures/` giữ stress; `contexts.json`, `metrics.csv`, `ar_metrics.csv`, `per_origin_metrics.csv`, `weekly.csv`, `verification.json` giữ số đo và kiểm tra.

```powershell
.\.venv\Scripts\python.exe -X utf8 agent1/scripts/business/backtest_t6_global.py
```
