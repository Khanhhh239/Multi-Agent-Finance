# T1 competing risks v5: P0–P4 trên synthetic v4

**Trạng thái:** thử nghiệm độc lập, không phải bản thay thế T1 v4 trong sản phẩm.
Code ở [`experiments/t1_competing_v5/`](../../experiments/t1_competing_v5/),
artifact mới ở [`v5_competing_risks_53w_20261028/`](../../outputs/data/v5_competing_risks_53w_20261028/).
Cohort v4 và model v4 chỉ được đọc, kiểm SHA-256 trước khi dùng; không ghi đè.
Không tạo nhánh Git riêng. Thiết kế đã khóa trong
[`protocol.json`](../../experiments/t1_competing_v5/protocol.json).

## P0 — Quy tắc sự kiện

Một hóa đơn có trạng thái `open` tại ngày cắt. `paid` xảy ra tại
`paid_date_true` khi tiền thu đủ giá trị phải thu sau credit note đã có ngày.
`paid_after_credit_note` thuộc nhóm này. `write-off` xảy ra tại
`writeoff_date` và loại hóa đơn khỏi khả năng trả đủ về sau trong World
synthetic. Nếu chưa có sự kiện trước cuối cửa sổ nhãn, hóa đơn bị kiểm duyệt
hành chính tại ngày đó. Hai ngày kết thúc cùng tồn tại hoặc sự kiện đã xảy ra
trước ngày cắt bị báo lỗi. `credit_note` chỉ đóng hóa đơn mà không có khoản
trả là một loại kết thúc khác; pipeline **dừng** nếu gặp nó, không gán nhầm
thành paid hoặc censored. Cohort v4 được kiểm tra không có trường hợp này.

`closure_type`, ngày paid/write-off và tương lai chỉ đi vào nhãn sau khi
[`model_snapshot_view`](../../agent1/models/features.py) đã dựng đặc trưng
nhìn thấy tại ngày cắt; chúng không nằm trong 46 feature đầu vào của model.

## P1 — Nhãn và risk set

[`event_table.parquet`](../../outputs/data/v5_competing_risks_53w_20261028/event_table.parquet)
ghi từng `(world, invoice_id, cutoff)`, ngày/cause sự kiện đầu, ngày kiểm
duyệt và `risk_weeks`. Bốn World train có **100.000 snapshot được lấy mẫu
theo seed khóa trước** từ 540.414 snapshot đủ điều kiện; bốn World
validation/test có **45.498 hóa đơn duy nhất**. Tổng `risk_weeks` trong event
table bằng đúng **1.310.739** hàng tuần đã dùng để fit. Chỉ hóa đơn còn open ở
đầu tuần và có đủ bảy ngày quan sát mới có một hàng risk set; sau paid hoặc
write-off không còn hàng nào. Nhãn tuần gồm 1.214.435 `open`, 75.693 `paid`
và 20.611 `write-off`. Số sự kiện đầu trong event table có thể cao hơn nhãn
tuần vì một số xảy ra sau tuần 53 hoặc ở tuần chưa quan sát đủ.

Train dùng snapshot 01/04/2019–25/06/2023, nhãn tối đa đến 01/07/2024.
Đánh giá dùng snapshot đầu tiên của mỗi hóa đơn từ 01/07/2024 đến
16/12/2024, kết quả đến 31/12/2025. Mọi hóa đơn đánh giá có đủ ít nhất 371
ngày theo dõi, nên nhãn 365 ngày biết được; không kẹp hóa đơn chưa trả thành
paid tại ngày 120.

## P2 — Baseline Aalen–Johansen

[`aj_curves.csv`](../../outputs/data/v5_competing_risks_53w_20261028/aj_curves.csv)
ghi CIF paid, CIF write-off và xác suất vẫn open theo từng World tại 28, 91,
98, 120, 180, 270, 365 ngày. Với tập đánh giá có đủ theo dõi, CIF tại các
mốc này trùng tỷ lệ sự kiện quan sát. Ở ngày 365:

| World | Hóa đơn | Paid | Write-off | Open |
|---|---:|---:|---:|---:|
| validation_000 | 12.169 | 82,56% | 13,11% | 4,33% |
| validation_001 | 12.993 | 89,71% | 7,87% | 2,42% |
| test_000 | 5.772 | 78,64% | 20,32% | 1,04% |
| test_001 | 14.564 | 85,86% | 9,70% | 4,44% |

[`actual_weekly_hazards.csv`](../../outputs/data/v5_competing_risks_53w_20261028/actual_weekly_hazards.csv)
ghi mẫu số open đầu tuần, số paid/write-off trong tuần và hazard thực tế
theo World. Ở tuần 14, hazard paid quan sát là 3,30% trên validation gộp và
3,83% trên test gộp. V4 ngoại suy lần lượt 5,73% và 5,27%; v5 dự báo 4,95%
và 4,27% trên cùng risk set. V5 giảm sai lệch ở chỗ nối tuần 13–14 nhưng
vẫn cao hơn thực tế.

## P3 — T1 competing risks v5

LightGBM ba lớp dự báo xác suất `open`, `paid`, `write-off` có điều kiện còn
open đầu từng tuần, từ tuần 1 đến 53. Xác suất mỗi tuần cộng thành 1; tích
lũy theo tuần bảo đảm `F_paid + F_writeoff + S_open = 1`. Tuần 53 cho phép
đánh giá đúng ngày 365; ở ngày nằm trong tuần, dùng chuyển tiếp hazard theo
tỷ phần ngày. Không dùng hazard trung bình bốn tuần cuối của v4 để ngoại suy.

Model mới [`model.txt`](../../outputs/data/v5_competing_risks_53w_20261028/model.txt)
có SHA-256 `0afb6f43f74a5033e8e22d6882769722c4381166af446a88b28c8ccd4617fb6b`.
[`train.json`](../../outputs/data/v5_competing_risks_53w_20261028/train.json)
ghi hash protocol, cohort, model v4 và mã v5, feature order, số hàng và World
fit. Chỉ bốn World train được dùng để fit; siêu tham số 120 vòng khóa trước,
không chọn trên validation/test.

## P4 — Đánh giá v5 so với v4

[`comparison.csv`](../../outputs/data/v5_competing_risks_53w_20261028/comparison.csv)
dùng cùng 45.498 hóa đơn và cùng nhãn đầu tiên. Để so sánh ba trạng thái,
v4 giữ xác suất paid gốc, đặt xác suất write-off bằng 0 và xác suất open là
phần còn lại. Điểm Brier ba trạng thái thấp hơn là tốt hơn.

| Tập | Mốc | Paid thực tế | Paid v4 / v5 | Write-off thực tế | Write-off v5 | Brier ba trạng thái v4 / v5 |
|---|---:|---:|---:|---:|---:|---:|
| Validation | 91 ngày | 74,08% | 73,86% / 76,50% | 1,80% | 1,92% | 0,305 / 0,287 |
| Test | 91 ngày | 71,85% | 67,98% / 71,27% | 2,99% | 3,00% | 0,338 / 0,299 |
| Validation | 365 ngày | 86,25% | 94,18% / 87,73% | 10,40% | 9,74% | 0,235 / 0,158 |
| Test | 365 ngày | 83,81% | 91,86% / 84,15% | 12,72% | 11,76% | 0,273 / 0,167 |

[`calibration_bins.csv`](../../outputs/data/v5_competing_risks_53w_20261028/calibration_bins.csv)
và [`calibration_ece.csv`](../../outputs/data/v5_competing_risks_53w_20261028/calibration_ece.csv)
chia xác suất paid/write-off thành tối đa 10 nhóm số lượng gần bằng nhau
trong từng World. ECE paid ngày 365 trên test gộp giảm từ **0,0863** (v4)
xuống **0,0351** (v5); ECE write-off từ **0,1272** xuống **0,0303**.
Ở ngày 91 trên validation, ECE paid **tăng** từ 0,0167 lên 0,0296, nên v5
chưa hơn v4 ở mọi phép đo.

**Chưa đạt:** test_000 có write-off thực tế **20,32%** ngày 365 nhưng v5 dự
báo **13,82%**, đồng thời paid thực tế **78,64%** nhưng v5 dự báo **84,58%**.
Kết quả gộp che sai lệch này. Đây là dữ liệu synthetic và chỉ bốn World
holdout; chưa có khoảng tin cậy theo World, chưa có kiểm định trên ledger SME
thật hoặc shock thực. Mô hình chỉ được fit 53 tuần; nếu CIF paid chưa đạt 90%
tại ngày 365 thì Q90 nên ghi **chưa đạt trong chân trời**, không suy diễn ngày
trả vô hạn hay tăng trần để tạo số. `credit_note` chỉ đóng hóa đơn chưa được
mô hình hóa như cause thứ tư khi xuất hiện ở cohort khác.

Chạy lại bằng môi trường đã cài các package của dự án:

```powershell
python -m experiments.t1_competing_v5.run --stage all
python -m experiments.t1_competing_v5.calibration
python -m experiments.t1_competing_v5.materialize_events
python -m pytest tests/test_t1_competing_v5.py -q
```

`run.py` từ chối ghi đè model v5 nếu protocol/mã/hash không khớp artifact đã
có; các script không ghi vào thư mục v4.
