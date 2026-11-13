# Backtest T6 global, công nợ mở và số dư ngân hàng — 13/11/2026

## Phạm vi

So sánh global 18 feature Neural 75%/customer 25% với Workspace học tại từng
ngày chốt. Hai bên dùng cùng số dư đầu được đối chiếu, learner thu bán ngay/chi
biến đổi, lịch chi được biết và cấu hình T6 1.000 đường/seed 7. Nhánh dự báo thu
từ hóa đơn mới bị loại theo yêu cầu; không fit hoặc chọn learner new-credit.
SHAP được đặt bằng 0 trong vòng backtest; toàn bộ công nợ hợp lệ vẫn tham gia.

Bốn ngày chốt là 30/09/2025, 31/12/2025, 30/04/2026 và 31/07/2026; mỗi kỳ
13 tuần, không chồng lấn. Mỗi kế hoạch được đối chiếu với lần chạy chỉ giữ bản
ghi đã biết tại ngày chốt. Không dùng nhãn sau ngày chốt để fit/chọn local,
không tìm lại trọng số global hoặc ngưỡng cảnh báo trên kết quả.

## Kết quả và quyết định

Đã chạy 80 kế hoạch trên 20 trường hợp dữ liệu/ngày chốt: 4 bộ gốc và 16
stress, mỗi trường hợp có hai model và hai đường T6. Các stress vẫn là cùng
một doanh nghiệp synthetic, không phải 20 quan sát doanh nghiệp độc lập.

Đơn vị tiền: triệu VND; các số MAE càng thấp càng tốt.

| Chỉ số | Workspace local | Global 75/25 |
|---|---:|---:|
| MAE thu công nợ mở từng tuần, dữ liệu gốc | 64,16 | 198,75 |
| MAE thu công nợ mở lũy kế, dữ liệu gốc | 299,77 | 1.630,46 |
| MAE số dư, stress buffered có đủ lịch chi | 292,11 | 1.556,63 |
| Độ phủ P10–P90 số dư, stress buffered | 55,8% | 0,0% |

Global có MAE số dư ngân hàng gốc thấp hơn (1.048,96 so với 2.140,09), nhưng
không được diễn giải thành T1 tốt hơn. Trung bình theo tuần/origin, global
dự thu AR thấp hơn thực tế 1.630,46 triệu; tác động ngoài phạm vi làm sai số
số dư tăng 2.001,13 triệu. Hai phần bù trừ nhau. Bảng thu riêng và stress đủ
lịch cho thấy Workspace phù hợp với danh mục Đại Phát này hơn global.

Trong profile payment_pressure có 26 tuần thiếu tiền: global bỏ sót 0 tuần,
báo giả 14; Workspace bỏ sót 6, báo giả 13. Khi một phần lịch được biết muộn
(schedule_gap), cả hai bỏ sót 26/26 tuần thiếu tiền. Không có cơ sở dùng điểm
Brier bằng 0 ở các profile không có thiếu tiền để khẳng định cảnh báo tốt.

Chưa nên thay Workspace bằng global cho Đại Phát dựa trên lượt này. Cả hai
dải tiền chưa đạt mức phủ danh nghĩa 80% trong profile buffered; cần cải thiện
kiểm soát phạm vi lịch chi và đánh giá/hiệu chỉnh dải bằng lịch sử đủ điều kiện.
Kết luận này không phủ định báo cáo global trên 24 doanh nghiệp World trước:
đó là quần thể và giao thức khác. Không nâng model hoặc đổi gate dịch vụ.

## Hai loại dữ liệu phải đọc riêng

- **Đại Phát gốc:** giữ nguyên sao kê và khoản thu từ hóa đơn mới. Khoản thu
  bị loại khỏi phạm vi dự báo được ghi riêng trong phân rã sai số. Bộ này thiếu
  lịch chi tại các ngày chốt nên không thể gọi đường có hoạt động là dự báo đủ
  mọi nguồn tiền vào/ra của doanh nghiệp.
- **Stress phản thực tế:** bốn profile tại mỗi origin, dùng lại danh mục mở
  của cùng Đại Phát. Fixture ngừng phát hành hóa đơn sau origin; ngân hàng được
  dựng riêng từ thu danh mục mở, thu bán ngay và các khoản chi. Lịch/chi phí
  được khóa theo tiền quá khứ trước chấm, gồm trường hợp áp lực thanh toán,
  tăng chi biến đổi bất ngờ và lịch chi được biết muộn. Không sửa dữ liệu gốc.

Các profile không phải doanh nghiệp hoặc holdout độc lập. Không cộng số tuần
hoặc profile để tạo khoảng tin cậy như có nhiều doanh nghiệp thật.

## Số đo và bằng chứng

[Báo cáo số đo đầy đủ](../../outputs/t6/global_scope_no_new_credit_20261113/REPORT.md)
được sinh trực tiếp từ kết quả. Trong cùng thư mục:

- `ar_metrics.csv`: lỗi thu tuần/lũy kế và độ phủ/độ rộng dải thu lũy kế;
  dùng phần dữ liệu gốc khi đánh giá T1, tránh nhân bản cỡ mẫu bằng stress.
- `metrics.csv`, `per_origin_metrics.csv`: lỗi số dư, thu/chi tuần, P10–P90,
  interval score 80%, Brier, precision/recall, báo giả/bỏ sót; tách tuần 1–4
  và 5–13, model, đường T6 và profile.
- `weekly.csv`: nhãn sao kê, dự báo và phân rã sai số theo thu AR, thu bán
  ngay, lịch chi, chi biến đổi và dòng tiền ngoài phạm vi.
- `protocol.json`, `snapshot.json`, `models/`, `plans/`, `fixtures/`: thiết
  kế đã khóa, hash nguồn/đầu vào, model tại origin, kế hoạch và dữ liệu stress.
- `verification.json`, `independent_verification.json`: kiểm tra từ runner
  và phép tính lại độc lập từ sao kê/model đã lưu.

Độ phủ P10–P90 là độ phủ từng tuần, không phải độ phủ đồng thời cả 13 tuần.
Xác suất thiếu tiền được chấm theo tuần; ở cấp kỳ chỉ chấm quyết định cảnh
báo có ít nhất một lần, không ghép các xác suất tuần thành xác suất chung.
Không coi các kế hoạch hồi cứu là lịch sử prospective để hiệu chỉnh dải.

## Tái lập

Chạy từ thư mục gốc workspace:

```powershell
.\.venv\Scripts\python.exe -X utf8 agent1/scripts/business/backtest_t6_global.py
.\.venv\Scripts\python.exe -X utf8 agent1/scripts/business/verify_t6_global.py
```

Đây là chẩn đoán synthetic, không kích hoạt model của tenant hoặc thay đổi
cổng pilot. Nguồn/đầu vào đã khóa khác nội dung hiện tại sẽ khiến runner từ
chối dùng lại thư mục đo; dùng thư mục output mới cho lượt nghiên cứu khác.

## Kiểm chứng đã hoàn thành

- 48 kiểm thử Python liên quan đã qua; một cảnh báo Starlette/httpx đã có.
- 80/80 kế hoạch bất biến khi bỏ bản ghi biết sau ngày chốt; toàn bộ công nợ
  hợp lệ đều tham gia và không có dự báo từ nhánh hóa đơn mới.
- 173 hash snapshot nguồn/đầu vào/release khớp; dữ liệu ngân hàng gốc giữ nguyên.
- Phân rã sai số số dư khớp trong 0,000002 VND. Verifier độc lập tính lại
  1.040 dòng đo từ sao kê, 60 nhóm điểm số dư và 30 nhóm điểm AR, sai khác
  số học tối đa bằng 0; bốn kế hoạch được dựng lại trực tiếp từ model đã lưu.
- Các dòng đo lặp lại cùng nhãn cho nhiều model/đường dự báo; không coi là
  1.040 tuần hoặc doanh nghiệp độc lập.
