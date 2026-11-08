# T1 v4: sinh lại synthetic và full retrain (28/10/2026)

## Kết quả đã chạy

Đã sinh một cohort mới từ máy phát có sửa vòng đời `short_pay`, khóa split theo
World, train T1 từ đầu và chạy inference ngày **31/12/2025**. Không ghi đè
cohort/model v3 ngày 27/10 tại thời điểm chạy. Dữ liệu, model, báo cáo riêng
của v3 và hồ sơ dọn dữ liệu đã được xóa theo yêu cầu ngày 06/11/2026;
không còn tái lập được đối chứng v3 từ tồn kho hiện tại.

- Thiết kế đã khóa trước sinh: [`v4_shortpay_4shock_20261028_design.json`](../../data/synthetic/v4_shortpay_4shock_20261028_design.json), cùng [`scenario_protocol.json`](../../outputs/data/v4_shortpay_4shock_20261028/scenario_protocol.json).
- Cohort tám World (4 train, 2 validation, 2 test), 40 doanh nghiệp mỗi World:
  [`v4_shortpay_4shock_20261028_cohort.json`](../../data/synthetic/v4_shortpay_4shock_20261028_cohort.json), SHA-256
  `b8448695225b78ca29f202f7167def653aaf515c1adc03fc62d281365eef0155`.
- [`readiness.json`](../../outputs/data/v4_shortpay_4shock_20261028/readiness.json)
  ghi `passed=true`; tám World đều có manifest, 12 bảng Parquet/World và qua
  `validate_world`. Smoke tách riêng khỏi split.
- [`train.json`](../../outputs/data/v4_shortpay_4shock_20261028/train.json):
  **645.497 snapshot**, **491.279 sự kiện trả đủ**, 200 vòng, `max_rows=10.000.000`
  nên không cắt mẫu. Chỉ bốn World train được fit.
- Model mới [`model.txt`](../../outputs/data/v4_shortpay_4shock_20261028/model.txt),
  SHA-256 `70bee43bc0f0247d5041466a6ecdb7fde2692cf5b0b31d4c7dfaa215f7439a38`.
  Hash mã nguồn lúc train là
  `5e4422d889d8e7b3764582b9ec1e8440fd11f7f0a284f023edb96950119551f2`;
  [`source_snapshot.zip`](../../outputs/data/v4_shortpay_4shock_20261028/source_snapshot.zip)
  và [`source_snapshot.json`](../../outputs/data/v4_shortpay_4shock_20261028/source_snapshot.json)
  lưu đúng 192 file Python đã tạo hash. Commit trong metadata là revision nền;
  snapshot này cũng chứa các thay đổi chưa commit.

## Bốn shock được bổ sung

Bốn **template tham chiếu** đã được phát lại trong giai đoạn 2019–2023 của
**cả bốn World train**, cùng các tuần bình thường. `shock_truth.parquet` ghi
episode có cường độ dương tại mỗi World train: cầu xuất khẩu 2008–09 (13 tuần),
lạm phát + tín dụng 2011–12 (17 tuần), hạn mặn 2015–16 qua kênh cung ứng
(17 tuần), và năng lượng 2026 qua kênh giá (16 tuần). Đây là **ngày phát lại
giả định**, không phải ngày sự kiện lịch sử. Hai World test có thêm kịch bản
đa kênh 2024 và năng lượng 2025, khác lịch/biên độ; tất cả bốn họ template đã
vào train nên đây không phải phép thử họ shock hoàn toàn chưa thấy.

Mốc sự kiện và cơ chế lấy từ [kế hoạch shock 11](11_KE_HOACH_SOC_THI_TRUONG_TICH_HOP_2026-10-25.md).
Hiện chỉ có tệp WDI và OxCGRT trong `data/raw/MANIFEST.json`; biên độ,
độ dài, độ trễ và ảnh hưởng lên ngày thanh toán **vẫn là giả định mô phỏng**.
Riêng 2026, hồi phục sau mốc đã quan sát được là giả định. Hạn mặn dùng proxy
ngành thực phẩm/bán buôn, không có tọa độ tỉnh. T1 không đọc `shock_truth`
hoặc mã sự kiện làm feature; nó học gián tiếp từ lịch sử hóa đơn và thanh toán.

## Kiểm lỗi `short_pay` và kết quả dự báo

Trong bốn World train, số hóa đơn đã thu trên 75% nhưng còn dư, chưa write-off
ở cuối kỳ là **220/748.714**; trong bốn World train v3 cũ là **5.756/709.304**.
V4 có **5.620** hóa đơn ghi ít nhất ba lần thanh toán, v3 không có hóa đơn nào.
Mười một hóa đơn v4 còn dư gần trả đủ có ngày phát hành trước 01/07/2024;
chúng vẫn có thể bị kiểm duyệt phải tại ngày kết thúc quan sát. Hai cohort
khác seed và lịch shock, nên chênh lệch này không đo riêng tác động của bản sửa.
Kiểm thử vòng đời `short_pay`, kế toán và nhân quả: **21/21 pass**.

[`evaluation.csv`](../../outputs/data/v4_shortpay_4shock_20261028/evaluation.csv)
ghi pinball trung bình của DH-GBM trên validation là **6,934 / 7,088**, trên
test là **6,392 / 6,898**. `cov80` lần lượt **0,908 / 0,894 / 0,890 / 0,898**;
đây là **metric lịch sử cho mục tiêu bị kẹp nhãn**, không đo chính xác ngày
trả đủ khi nhãn chưa quan sát được. Riêng `cov80` còn bị thổi phồng vì nhãn
và Q90 cùng bị kẹp ở 120 ngày. Xem
[bản đánh giá lại có xử lý kiểm duyệt](../03_Evaluation/T1_V4_CENSOR_AWARE_2026-10-28.md)
trước khi diễn giải chất lượng T1.

[`summary.json`](../../outputs/t1/v4_shortpay_4shock_20261028_inference_2025-12-31/summary.json)
và [`predictions.csv`](../../outputs/t1/v4_shortpay_4shock_20261028_inference_2025-12-31/predictions.csv)
ghi **39.377 hóa đơn còn mở**, tổng số dư **5.724.149.436.000 VND**. Q50 chạm
trần 120 ngày ở **11.690 (29,7%)** và Q90 ở **29.273 (74,3%)**. Ở v3 cũ là
43,3% và 71,3% trên 48.961 hóa đơn. Nhóm đã thu trên 75% nhưng còn mở trong
CSV inference giảm từ **11.669** xuống **427** hóa đơn; Q50 chạm trần trong
nhóm v4 là **176**. So sánh giữa hai cohort là mô tả, không phải thí nghiệm
đối chứng cùng seed/shock. Hash `predictions.csv` v4:
`29df0f4d0a4ac3b3ace8cca118aa7815695488b1df2d53aaf3855c27438010f2`.

## Chẩn đoán Q90 chạm trần 74,3% (28/10/2026)

Đã tính lại hazard của toàn bộ 39.377 hóa đơn bằng đúng model v4 và đối chiếu
từng cờ `q90_capped` với công thức tại ngày 120. Kết quả chi tiết ở
[`q90_diagnostic.json`](../../outputs/t1/v4_shortpay_4shock_20261028_inference_2025-12-31/q90_diagnostic.json);
[`diagnose_q90.py`](../../outputs/t1/v4_shortpay_4shock_20261028_inference_2025-12-31/diagnose_q90.py)
cho phép chạy lại. Hash model và CSV đầu vào đều được kiểm trước khi tính.

T1 học xác suất trả đủ trực tiếp trong **13 tuần (91 ngày)**. Nếu đến ngày 91
chưa đạt mức 90%, hàm phân vị dùng **hazard trung bình bốn tuần cuối** làm
hazard cố định cho phần sau đó, kẹp trong `[0,02; 0,6]`. Từ 91 đến 120 chỉ có
thêm khoảng 4,14 tuần. Với xác suất trả đủ đến ngày 91 là `F91` và hazard đuôi
`h`, xác suất suy ra đến ngày 120 là
`F120 = 1 - (1 - F91) × (1 - h)^((120 - 91)/7)`.
Q90 chạm trần khi `F120` chưa tới 0,90. Kiểm lại công thức cho ra đúng **29.273**
cờ chạm trần trong CSV; không thấy lỗi ghi nhầm phân vị hay cờ ở bước inference.

| Nhóm tại 31/12/2025 | Số hóa đơn | Q90 chạm trần | Tỷ lệ trong nhóm |
|---|---:|---:|---:|
| Tuổi 0–30 ngày | 18.160 | 10.574 | 58,2% |
| Tuổi 31–90 ngày | 10.070 | 7.591 | 75,4% |
| Tuổi 91–180 ngày | 4.794 | 4.755 | 99,2% |
| Tuổi trên 180 ngày | 6.353 | 6.353 | 100% |
| Chưa thu khoản nào | 34.777 | 24.973 | 71,8% |

**Nguyên nhân chính là xác suất 90% chưa đạt trong chân trời ngắn, cộng với
giới hạn hiển thị 120 ngày.** Ở **33.275/39.377 (84,5%)** hóa đơn, xác suất
trả đủ dự báo đến ngày 91 dưới 90%; phần ngoại suy chỉ giúp 4.002 hóa đơn
trong số này đạt Q90 trước ngày 120. Trong nhóm chạm trần, xác suất trả đủ
ngày 91 trung vị **52,3%**, hazard đuôi trung vị **4,76% mỗi tuần** và xác suất
suy ra ở ngày 120 trung vị **61,6%**. Có **14.027** hóa đơn chạm trần có xác
suất ngày 91 dưới 50%, nên nhiều trường hợp cách xa ngưỡng 90%, không chỉ
vượt trần vài ngày.

**Không còn chủ yếu do `short_pay`.** Có **24.973/29.273 (85,3%)** trường hợp
chạm trần chưa thu lần nào; nhóm đã thu trên 75% chỉ chiếm **365 (1,2%)**.
Hóa đơn tuổi không quá 90 ngày chiếm **18.165/29.273 (62,1%)** trường hợp
chạm trần. Số dư của nhóm chạm trần chiếm **68,3%** tổng AR mở, nên đây cũng
không chỉ là hiện tượng ở các số dư nhỏ. Tỷ lệ theo World dao động khoảng
**54–89%**; cả train, validation và test đều có tỷ lệ cao. Những con số này
không tách riêng được tác động của từng shock hay chứng minh model sai trên
dữ liệu thật.

**Tăng trần không sửa được độ tin cậy của phần đuôi.** Nếu chỉ đổi trần hiển
thị thành 180 hoặc 365 ngày trong cùng công thức, số Q90 vẫn vượt trần tương
ứng là **22.098 (56,1%)** và **12.857 (32,7%)**. Q90 chưa kẹp của các hàng
hiện chạm trần có trung vị **306 ngày**, nhưng đây là phép ngoại suy toán học
từ bốn tuần cuối, **không phải dự báo dài hạn đã được kiểm định**. Sàn hazard
đuôi 0,02 được áp ở **6.993** hàng, tất cả vẫn chạm trần; sàn này không tạo ra
tỷ lệ chạm trần cao. T1 hiện cũng không ước lượng riêng xác suất không bao giờ
trả đủ khi xuất Q90. Batch 31/12/2025 nằm ở cuối kỳ dữ liệu, chưa có nhãn
tương lai để đo tỷ lệ thực trả đủ trong 120 ngày.

Hướng xử lý tiếp theo: xác định có cần cam kết Q90 dài hạn hay chỉ cần xác
suất trả đủ theo mốc 4/13 tuần; nếu cần Q90, mở rộng cửa sổ nhãn/model và xử
lý riêng xác suất không trả đủ, sau đó đánh giá trên cửa sổ có nhãn tương lai
với kiểm duyệt đúng nghĩa. Không dùng việc nâng `CAP` để tuyên bố Q90 đã đạt.

**Bổ sung chẩn đoán với 365 ngày theo dõi:**
[phân phối ngày trả đủ, survival curve và hazard](../03_Evaluation/T1_V4_PAYMENT_SURVIVAL_DIAGNOSTIC_2026-10-28.md)
trên 45.498 hóa đơn validation/test duy nhất cho thấy 8,2% trả đủ trong ngày
121–365, còn 11,4% đã write-off đến ngày 365. Hazard ngoại suy cao hơn thực
tế ngay từ tuần 14 ở cả bốn World. Với write-off là trạng thái đóng không
trả đủ trong synthetic, Q90 vô điều kiện của nhóm gộp này không có giá trị
hữu hạn. Nhóm theo dõi này bắt đầu năm 2024, không phải nhãn tương lai của
batch inference 31/12/2025.

## Chưa đạt / giới hạn

1. **Q90 vẫn chạm trần nhiều:** 74,3% ở batch v4. T1 chỉ fit hazard trực tiếp
   13 tuần rồi ngoại suy đến trần 120 ngày; sửa `short_pay` chưa giải quyết
   chân trời dài. Q50 v4 còn 29,7% chạm trần.
2. **Calibration dài hạn vẫn chưa kết luận được:** bản đánh giá lại đã sửa
   nhãn 4/13 tuần và chỉ đo Q10/Q50/Q90 dưới trần trên các hàng đủ 120 ngày
   theo dõi. `cov80` cũ bị thổi phồng bởi phép kẹp nhãn. Phần lớn Q90 chạm
   trần, nên vẫn cần cửa sổ quan sát dài hơn và phép đo survival đúng nghĩa.
3. **Bốn shock chưa được hiệu chỉnh bằng ledger SME Việt Nam hoặc chuỗi macro
   sự kiện đầy đủ.** Bản phát lại dùng hình dạng và tham số giả định; không
   chứng minh T1 thích nghi với cú sốc thật hoặc với họ chưa thấy.
4. **Chưa đủ điều kiện pilot thật.** Split World và kiểm nội bộ chỉ xác nhận
   tính hợp lệ kỹ thuật của synthetic; các cổng sản phẩm trong
   [`GATES_CURRENT.md`](../03_Evaluation/GATES_CURRENT.md) phải đánh giá riêng.

Chạy lại trong môi trường dự án:

```powershell
python scripts/build_v4_shortpay_4shock.py --stop-after evaluate
python scripts/infer_t1_final.py --cohort data/synthetic/v4_shortpay_4shock_20261028_cohort.json --model-dir outputs/data/v4_shortpay_4shock_20261028 --as-of 2025-12-31 --output-dir outputs/t1/v4_shortpay_4shock_20261028_inference_2025-12-31
python analysis/evaluate_t1_censor_aware.py
python analysis/analyze_t1_v4_payment_survival.py
```

Runner xác minh hash và từ chối dùng lại World/artifact nếu mã nguồn hoặc
cấu hình khác bản đã khóa. Khi tái lập từ commit nền, trước tiên cần khôi phục
đúng snapshot mã trong artifact.
