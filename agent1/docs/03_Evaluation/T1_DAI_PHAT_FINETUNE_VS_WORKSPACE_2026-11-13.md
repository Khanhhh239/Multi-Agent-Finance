# Fine-tune global trên Đại Phát và so sánh Workspace — 13/11/2026

**Đề xuất giữ Workspace cho T1 của bản bàn giao Đại Phát.** Global sau fine-tune
cải thiện mạnh so với global gốc, nhưng trung bình bốn kỳ vẫn có lỗi thu tuần,
lũy kế và xác suất cao hơn Workspace. Đây là kết quả của một doanh nghiệp mô
phỏng tại bốn origin đã được xem trước trong các lượt chẩn đoán.

So sánh tại 30/09/2025, 31/12/2025, 30/04/2026 và 31/07/2026, mỗi kỳ 13 tuần.
Workspace được lấy lại từ đúng model đã học trước từng ngày chốt, có kiểm hash,
dữ liệu và tái tạo điểm baseline. Global được fine-tune riêng bằng lịch sử Đại
Phát trước từng ngày chốt theo phương pháp đã thử trên cohort World trước.

Đơn vị MAE và độ rộng dải là triệu VND. Cash score và Brier càng thấp càng tốt.

| Chỉ số | Workspace | Global gốc 75/25 | Global fine-tune |
|---|---:|---:|---:|
| Cash score | 0,054186 | 0,202117 | 0,069644 |
| MAE thu từng tuần | 64,16 | 198,75 | 85,24 |
| MAE thu lũy kế | 299,77 | 1.630,46 | 364,97 |
| Brier tất toán 4 tuần | 0,120972 | 0,201201 | 0,172438 |
| Brier tất toán 13 tuần | 0,169906 | 0,353556 | 0,239063 |
| Integrated Brier, trọng số dư nợ | 0,137930 | 0,243459 | 0,188202 |
| Độ phủ P10–P90 thu lũy kế | 53,8% | 0,0% | 71,2% |
| Độ rộng P10–P90 trung bình | 606,74 | 538,76 | 735,33 |
| Interval score 80% | 1.296,89 | 14.229,93 | 2.283,66 |

So với Workspace, fine-tune có cash score cao hơn 28,53%, MAE thu tuần cao hơn
32,85% và MAE lũy kế cao hơn 21,75%. Workspace có MAE thu tuần thấp hơn ở cả
bốn kỳ. Fine-tune có MAE lũy kế thấp hơn ở ba kỳ đầu, nhưng lỗi lớn ở kỳ cuối
làm kết quả trung bình xấu hơn. Độ phủ tăng đi cùng dải rộng hơn; interval
score vẫn cao hơn Workspace và độ phủ chưa đạt mức danh nghĩa 80%.

| Ngày chốt | MAE lũy kế Workspace | MAE lũy kế fine-tune | Epoch | Alpha | Audit quá khứ |
|---|---:|---:|---:|---:|---|
| 30/09/2025 | 231,90 | 200,02 | 5 | 1,00 | Chấp nhận |
| 31/12/2025 | 426,96 | 141,29 | 20 | 0,75 | Chấp nhận |
| 30/04/2026 | 190,11 | 125,38 | 20 | 0,75 | Chấp nhận |
| 31/07/2026 | 350,12 | 993,21 | 20 | 1,00 | Chấp nhận |

Fine-tune thử 5/20 epoch, learning rate 0,0001, scaler global và trọng số học
local/replay 70/30. Alpha trộn global gốc với Neural học tiếp được chọn trên
validation quá khứ từ lưới 0/25/50/75/100%. Mỗi ngày chốt có 650 snapshots fit,
100 validation và 50 audit; nhãn đã đủ 91 ngày theo dõi trước khi được dùng.
Snapshots có thể lặp hóa đơn ở các ngày khác nhau. Toàn bộ 287/286/291/295 hóa
đơn mở hợp lệ tại bốn ngày chốt được chấm và đưa vào T6, tổng 1.159 snapshots
origin–hóa đơn.

Cả bốn audit đều chọn và chấp nhận fine-tune, nên nhánh thích nghi qua audit
cho cùng dự báo với fine-tune ở lượt này. Nhánh chỉ chọn lại trọng số global
cũng được chấm riêng, có MAE tuần 112,80 và lũy kế 528,53 triệu VND. Không chỉnh
epoch, replay, alpha hoặc ngưỡng audit bằng kết quả của bốn kỳ đang chấm.

Đánh giá tiền chỉ xét thu từ danh mục mở. Nhánh dự báo hóa đơn mới được tắt.
Dải thu được tính bằng T6 1.000 đường, seed 7. Số dư ngân hàng đầy đủ và cảnh
báo thiếu tiền thuộc backtest T6 riêng. Các origin này là dữ liệu hồi cứu đã
được xem; kết quả không cung cấp khoảng tin cậy tổng quát cho nhiều doanh
nghiệp độc lập.

[Báo cáo và dữ liệu đầy đủ](../../outputs/t1/dai_phat_adaptation_20261113/REPORT.md)
gồm protocol, snapshot nguồn/đầu vào, model từng origin, receipt validation/audit,
phân phối từng hóa đơn, dự báo, điểm tổng hợp và điểm từng kỳ.

Kiểm chứng đã hoàn thành với 22 kiểm thử liên quan, 223 hash nguồn/đầu vào,
bốn kiểm tra loại dữ liệu tương lai khi dựng mẫu học và 20 kiểm tra khi dự báo.
Verifier tính lại tiền thu và ngày tất toán từ CSV gốc cho 20 trường hợp
model–origin, kiểm đủ 15 nhóm số đo, tái tạo 20 phân phối và bốn kế hoạch Monte
Carlo từ model đã lưu. Kiểm tra tham số xác nhận Neural đã học tiếp tại cả bốn
mốc và đầu ra bộ tiền xử lý trùng global. Kết quả chi tiết nằm trong
`verification.json` và `independent_verification.json` của thư mục output.

`verification_amendment.json` ghi bản sửa phép tính lại integrated Brier dùng
trọng số dư nợ, cùng hash mã kiểm chứng đã sửa. Hàm học, chọn cấu hình, dự báo
và tính điểm được đối chiếu AST với snapshot ban đầu. Snapshot nguồn ban đầu
và mã kiểm chứng bổ sung đều được lưu để truy vết.

Trong `metrics.csv`, cột horizon áp dụng cho lỗi thu và dải tiền. Các cột cash
score, Brier 4/13 và integrated Brier mô tả toàn kỳ, được lặp ở ba dòng horizon
của mỗi model.

Để chạy lại toàn bộ bằng mã hiện tại, dùng thư mục output mới.

```powershell
.\.venv\Scripts\python.exe -X utf8 agent1/scripts/business/backtest_t1_dai_phat_adaptation.py --output agent1/outputs/t1/dai_phat_adaptation_rerun
.\.venv\Scripts\python.exe -X utf8 agent1/scripts/business/verify_t1_dai_phat_adaptation.py --output agent1/outputs/t1/dai_phat_adaptation_rerun
```
