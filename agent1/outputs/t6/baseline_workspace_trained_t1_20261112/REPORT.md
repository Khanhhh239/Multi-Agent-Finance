# Mốc ban đầu T6 Workspace · 12/11/2026

Chẩn đoán hồi cứu trên Đại Phát, dữ liệu 100% synthetic. Giữ nguyên thuật toán và cấu hình mặc định; không kích hoạt model, không chỉnh ngưỡng cảnh báo hoặc khoảng dự báo.

## Phạm vi đã chạy

- T1 được huấn luyện tại từng ngày chốt bằng `agent1.adaptive.methods.train()`, toàn bộ danh mục mặc định, chọn trên validation, audit độc lập và refit đến ngày chốt. Truyền `bundle` thực vào `forecast()`; kiểm tra kết quả mang mode `company_trained`.
- T6 giữ 400 đường mô phỏng độc lập, seed 7 và kỳ 13 tuần.
- Không bật ước lượng hoạt động hoặc hóa đơn bán chịu mới; không thêm lịch chi từ kết quả tương lai.
- Số dư đầu mỗi mốc lấy từ sao kê đã chốt và đã biết tại đúng ngày đó. Ngưỡng tiền 200 triệu VND giữ theo cấu hình demo.
- Bốn gốc không chồng lấn được chọn trước khi chấm. Mỗi tuần kết quả có đủ sao kê; nhãn cuối được đọc tại 31/10/2026.
- Đã đối chiếu dòng tiền khi truyền toàn bộ dữ liệu với khi loại các bản ghi biết sau ngày chốt: dung sai tiền 0,01 VND, xác suất 1e-12. Không so hash/nội dung SHAP vì tổng xác suất cây chạy nhiều luồng có sai khác làm tròn. Không dùng kế hoạch hồi cứu làm dữ liệu hiệu chỉnh prospective.

## Kết quả theo ngày chốt

Đơn vị tiền trong bảng: triệu VND. MAE và độ phủ tính trên 13 số dư cuối tuần.

| Ngày chốt | Số dư đầu | MAE số dư | Độ phủ P10–P90 | Độ rộng TB | MAE thu AR lũy kế | Báo giả / bỏ sót (tuần) |
|---|---:|---:|---:|---:|---:|---:|
| 2025-09-30 | 500.00 | 1,941.60 | 0.0% | 649.19 | 231.90 | 0 / 0 |
| 2025-12-31 | 500.00 | 2,021.73 | 0.0% | 578.15 | 426.96 | 0 / 0 |
| 2026-04-30 | 540.00 | 1,933.07 | 15.4% | 562.34 | 190.11 | 0 / 0 |
| 2026-07-31 | 540.00 | 2,244.75 | 23.1% | 603.94 | 350.12 | 0 / 0 |

## Gộp 52 tuần dự báo

- MAE số dư: **2,035.29 triệu VND**; bias (dự báo trừ thực tế): **1,809.77 triệu VND**.
- Độ phủ P10–P90: **9.6%**; độ rộng trung bình: **598.41 triệu VND**; interval score 80%: **18,108.72 triệu VND** (nhỏ hơn tốt hơn).
- MAE thu từ công nợ mở: **64.16 triệu/tuần**, **299.77 triệu lũy kế**.
- Tuần dưới ngưỡng tiền thực tế: **0**; tuần cảnh báo: **0**; báo giả: **0**; bỏ sót: **0**.
- Brier xác suất xuống dưới ngưỡng từng tuần: **0.000000**. Đây không phải xác suất thiếu tiền ít nhất một lần trong cả kỳ.

## Cách đọc sai số

Bộ Đại Phát có đủ hóa đơn, thanh toán và sao kê quá khứ, nhưng 27 lịch chi chỉ được biết ngày 31/10/2026 và đến hạn sau đó. Cả bốn ngày chốt đều chưa có lịch chi; mọi tuần dự báo báo trạng thái chi chưa biết. Không xác nhận các tuần đó là không có chi.

Nhánh mặc định chỉ dự thu công nợ mở. Sao kê thực tế còn có thu hóa đơn mới, bán thu ngay, chi biến đổi và khoản chi cuối tháng của máy phát. Vì vậy điểm số dư ngân hàng đầy đủ đo cả khoảng trống phạm vi, không được quy toàn bộ thành lỗi thuật toán T6 hoặc T1.

Từng tuần có đẳng thức kiểm tra: `sai số số dư = sai số thu AR lũy kế + tác động phạm vi lũy kế`, trong đó `tác động phạm vi = tổng chi thực tế − tổng thu ngoài công nợ mở`. Không thay đổi dòng tiền thật để làm điểm đẹp hơn.

MAE thu AR lũy kế tách riêng phần công nợ mở tại ngày chốt; đây là chẩn đoán sai số thu trong phạm vi hiện có, không phải điểm số dư đầy đủ đã sửa.

## Giới hạn và việc tiếp theo

- Một doanh nghiệp synthetic từ một máy phát; các tuần trong mỗi gốc có phụ thuộc. Không tính khoảng tin cậy từ 52 tuần như 52 quan sát độc lập.
- Đây là T1 học lại đúng quy trình Workspace tại từng gốc, không lấy model học sau ngày chốt để chấm ngược quá khứ; không phải competing-risks V6. Nếu audit từ chối hoặc chọn tỷ trọng 0, giữ nguyên chính sách dự phòng của Workspace và ghi rõ trong bảng T1.
- Khoảng dự báo thô, không hiệu chỉnh. Không có chuỗi kế hoạch prospective đủ điều kiện để dùng bộ hiệu chỉnh hiện hành.
- Đối chiếu phần phạm vi thu/chi trước khi lựa chọn thay đổi thuật toán. Giữ bộ điểm này để so sánh cùng giao thức sau mỗi sửa đổi.
- Các World v4/v6 còn config/manifest nhưng không còn Parquet ở lần kiểm tra này; không tái sinh hoặc thay dữ liệu để giả thành lần chạy lại nghiên cứu cũ.
- Không có tuần thiếu tiền theo ngưỡng đã chọn: recall để trống, chưa đánh giá được khả năng phát hiện thiếu hụt. Không đổi ngưỡng sau khi xem kết quả để tạo sự kiện.

## T1 thực sự đưa vào T6

Tỷ trọng là phần của model được chọn, phần còn lại là mốc lịch sử khách theo đúng cơ chế Workspace.

| Ngày chốt | Ứng viên chọn | Tỷ trọng phục vụ | Audit Brier 4 tuần | Mốc lịch sử | Audit chấp nhận |
|---|---|---:|---:|---:|---|
| 2025-09-30 | extra | 1.00 | 0.105172 | 0.153846 | True |
| 2025-12-31 | lightgbm | 1.00 | 0.094060 | 0.146341 | True |
| 2026-04-30 | hist | 1.00 | 0.099180 | 0.153846 | True |
| 2026-07-31 | hist | 1.00 | 0.098055 | 0.134146 | True |

## Tệp và tái lập

- `weekly.csv`: 52 tuần dự báo, thực tế và phân rã sai số.
- `metrics.csv`: điểm toàn kỳ, tuần 1–4 và tuần 5–13, gộp và theo gốc.
- `summary.json`: điểm tổng và chi tiết từng ngày chốt.
- `protocol.json`: cấu hình khóa, hash dữ liệu và mã nguồn, phiên bản thư viện.
- `plans/`: nguyên kết quả dự báo từ hàm phục vụ hiện có.
- `models/`: bundle T1 và hồ sơ chọn model/audit từng ngày chốt (chỉ có ở chế độ Workspace).
- `runtime_source/`, `inputs/`, `snapshot.json`: mã nguồn và dữ liệu cố định dùng riêng cho lần đo; không phụ thuộc các sửa đổi đồng thời ở workspace.

```powershell
.\.venv\Scripts\python.exe -X utf8 agent1/scripts/business/backtest_t6_baseline.py
```
