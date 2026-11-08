# T1 v6: ngành, hành vi ledger và fresh holdout

**Ngày 05/11/2026. Đã triển khai và chạy P0–P4. Tầng bằng chứng: synthetic;
chưa đạt toàn bộ tiêu chí nghiên cứu, không thay model dịch vụ.**

**Cập nhật chốt nghiên cứu cùng ngày:** đã giữ nguyên nhánh `both` làm ứng
viên hiện tại và chấm bổ sung với baseline Khánh trên 65.221 anchor. Brier
Paid chính giảm 1,60%, Brier Paid 365 ngày giảm 26,54% so với baseline này;
Paid Brier chính tăng nhẹ 0,07% so với V6 gốc. Xem
[báo cáo chốt](T1_V6_PROGRESS_VS_KHANH_2026-11-05.md) và
[manifest](../../outputs/analysis/t1_v6_final_vs_khanh_20261105/research_candidate.lock.json).
Phần kết quả P0–P4 dưới đây giữ nguyên; không chọn lại nhánh theo lần chấm bổ sung.

**Kết quả chính:** ứng viên được chọn trên nguồn là **V6 + ngành + hành vi
ledger** (`both`), fit trên 200.000 snapshot gốc. Brier joint 365 ngày
trung bình theo World giảm **0,79% trên nguồn** và **0,49% trên bốn fresh
World**. Cải thiện fresh nhỏ, cả bốn CI bootstrap theo công ty đều chứa
0. ECE Paid vẫn không đạt ở ba World; World shock kéo dài còn thiếu
Write-off **6,13 điểm %**. Chưa thể kết luận đã giải quyết distribution shift.

Mã: [`experiments/t1_v6_practical/`](../../experiments/t1_v6_practical/).
Artifact: [`t1_v6_practical_20261105_r2`](../../outputs/data/t1_v6_practical_20261105_r2/).
[Protocol và định nghĩa feature](../04_AI_Methods/T1_V6_PRACTICAL_FEATURES_PROTOCOL_2026-11-05.md).

| Ưu tiên | Đã thực hiện | Kết quả / giới hạn |
|---|---|---|
| P0 | 14 feature ngành có nguồn/ngày biết, tenant và unknown | Loại 5 `macro_credit_*` khỏi pipeline mới; adapter không tự tạo ngành hoặc gán ngày biết từ hóa đơn |
| P1 | 15 feature biến động thanh toán từ ledger as-of | Có trend trễ, thu ròng, thay đổi quá hạn, thu từng phần, history/coverage và missing |
| P2 | Fit đủ bốn nhánh, cùng 200.000 dòng và cấu hình v6 | Chọn `both` bằng 10.666 anchor của 32 công ty nguồn giữ ngoài fit |
| P3 | Audit support và thử riêng hai World train bổ sung | Không chọn nhánh augmented; thiếu support tenure vẫn còn |
| P4 | Bốn World/episode mới, 80 công ty, 15.466 anchor | Lựa chọn khóa trước sinh fresh; 1/4 World qua toàn bộ tiêu chí, không chọn lại theo fresh |

## 1. Đầu vào thực tế và giới hạn dữ liệu

[`PracticalFeatureBuilder`](../../experiments/t1_v6_practical/ledger.py)
chỉ nhận schema hóa đơn, bút toán ledger, coverage và ngành có thời điểm
biết. Caller phải cung cấp tập tenant được phép; bảng/khóa ngoài tập này
bị từ chối. Mã khách trùng giữa hai người bán không làm chia sẻ lịch sử.
Không nhận nhãn oracle, exposure, shock hoặc macro giả lập vào feature.

Trend thanh toán dùng **thời điểm ledger ghi nhận tất toán**, không dùng
ngày trả tiền thật. Khoản thu/phân bổ ghi nhận muộn chỉ xuất hiện từ
`known_at`; cửa sổ trước đó được dựng bằng thông tin đã biết khi ấy.
Hỗ trợ bút toán thu/credit có dấu để ghi đảo bằng sự kiện mới. Không có
mẫu số, thiếu coverage hoặc dữ liệu quá cũ thì missing; không suy thành
thu tiền bằng 0. Khách có hóa đơn cũ trước coverage mà chưa xác minh được
số dư đầu kỳ cũng giữ missing; thiếu hạn thanh toán không được gán thành
không quá hạn.

**Lần chạy này chưa dùng dữ liệu SME thật.** Lớp ERP synthetic mới dùng mã
phân bổ `ledger_invoice_id` và ngày `ledger_post_date`, giữ sai số sổ sách,
thêm một ngày tiếp nhận. Ngành được mô phỏng qua customer master theo
quý, trễ 14 ngày, bao phủ 75% khách bằng mẫu hash cố định không dùng nhãn.
Đây không phải hồ sơ KYC thật đã tồn tại trong World cũ. Ngành được giả
định đúng khi đã được ghi; chưa hiệu chỉnh tỷ lệ thiếu, trễ hoặc phân loại
sai trên SME Việt Nam.

Trên tập chọn nguồn, thiếu ngành người mua khoảng **18,9–30,2% anchor**;
**5,7–9,3%** anchor chưa có hóa đơn hợp lệ trong ledger được biết tại cutoff
nên feature hành vi giữ cờ missing. Các con số theo anchor, không phải
tỷ lệ công ty. [Coverage nguồn](../../outputs/data/t1_v6_practical_20261105_r2/source_observation_coverage.csv).

Bộ 64 feature v6 gốc giữ nguyên để làm đối chứng: nó vẫn có giả định
synthetic về liên kết tiền, ngày đóng và lịch sử Write-off. Lần thử này
không tự hoàn thiện adapter vận hành cho toàn bộ baseline hoặc nối luồng
Write-off vào service cũ. Khả năng triển khai của feature mới và chất lượng
của một model trên dữ liệu SME thật là hai việc cần kiểm riêng.

## 2. Ablation chính: cùng dữ liệu và risk set

Giữ nguyên 200.000 snapshot fit, thứ tự hàng, 160 vòng, seed/cấu hình
LightGBM, identity calibration và 53 tuần. Cả bốn nhánh có đúng **2.589.709
hàng risk set**: Open 2.397.029, Paid 152.552, Write-off 40.128,
credit-only 0. Feature mới đóng băng tại cutoff trong toàn bộ chân trời.
Một hóa đơn có thể xuất hiện ở nhiều snapshot fit.

Refit baseline khớp **đúng hash model v6**; sai khác hazard trên mẫu đối
chứng qua 53 tuần bằng **0**. Không sửa model gốc.

Tập chọn: anchor đầu tiên mỗi hóa đơn trên 8 công ty được giữ ngoài fit
trong mỗi World nguồn, cutoff 01/07–16/12/2024, nhãn đến 31/12/2025. Có
10.666 anchor, đủ follow-up 365 ngày. Đây là lựa chọn trên công ty nguồn
và thời gian muộn hơn, không phải test xác nhận hoặc leave-one-World-out.

Các số Brier dưới đây là **trung bình World bằng trọng số**, không phải
ECE gộp hoặc trung bình có trọng số số hóa đơn. Brier nhỏ hơn là tốt hơn.

| Nhánh | Feature snapshot | Brier joint 365 | Brier Write-off 365 | Qua điều kiện chọn nguồn? |
|---|---:|---:|---:|---|
| V6 gốc | 64 | 0,134753 | 0,041910 | Đối chứng |
| + Ngành | 78 | 0,134218 | 0,041879 | Có |
| + Hành vi | 79 | 0,134886 | 0,041843 | Không: joint xấu hơn |
| **+ Cả hai** | **93** | **0,133687** | **0,041794** | **Có; được chọn** |

Cả bốn nhánh cộng thêm cùng 7 feature tuần. `both` giảm joint **0,7909%**
và Write-off Brier **0,2774%**; Brier Paid ngắn hạn xấu nhất tăng **0,9213%**,
trong ngưỡng 2%. Không suy từ đây rằng mọi feature hành vi đều hữu ích:
nhánh chỉ thêm hành vi làm joint xấu hơn khoảng 0,099% trên nguồn.

Nguồn: [primary scores](../../outputs/data/t1_v6_practical_20261105_r2/primary_source_scores.csv),
[primary selection](../../outputs/data/t1_v6_practical_20261105_r2/primary_selection.json),
[tái lập baseline](../../outputs/data/t1_v6_practical_20261105_r2/baseline_reproduction.json).

## 3. P3: support và bổ sung World là thí nghiệm riêng

**80,33%** giá trị hữu hạn `c_tenure_days` của tập chọn nguồn vượt range
fit, tối đa 1.629 ngày. `c_n_hist` có 1,53% vượt range; `f_n_hist` là 0%.
Theo ngưỡng 10% đã khóa, nhánh augmentation được kích hoạt. Range đơn
biến không chứng minh overlap đa biến hoặc nguyên nhân của sai lệch.

Kế hoạch warm-up 2016 ban đầu không chạy được vì thiếu quy tắc kinh tế
trước 2019; hai lần sinh dừng trước khi ghi Parquet. Đã lưu amendment và
đổi sang hai World hỗ trợ từ 2019, giữ các seed đã khai báo, đa dạng lịch
credit/demand/supply/price. Không sửa generator chung hoặc bịa quy tắc thuế
để vượt lỗi. Sửa thiết kế này xảy ra trước fit augmented và sinh fresh;
**không gọi P3 là một thiết kế không thay đổi từ đầu**. Lịch fresh và
quy tắc chọn giữ nguyên.

Hai World mới, mỗi World 20 công ty, thêm tổng 100.000 snapshot bằng quota
theo công ty. Hai đối chứng dùng cùng **300.000 snapshot / 4.505.815 hàng
tuần**; không thay dữ liệu của ablation chính.

| Nhánh mở rộng | Brier joint 365 nguồn | Brier Write-off 365 nguồn | Brier Paid ngắn hạn xấu nhất so V6 |
|---|---:|---:|---:|
| V6 trên 300k | 0,134348 | 0,043305 | +1,9523% |
| V6 + cả hai trên 300k | 0,133098 | 0,042560 | **+2,0589%** |

Joint tốt hơn chưa đủ: Write-off Brier của cả hai nhánh xấu hơn V6 gốc;
nhánh `aug_both` còn vượt giới hạn Paid 2%. Vì vậy không chọn chúng.
Support `c_n_hist` ngoài range giảm về 0%, nhưng tenure vẫn **80,33%** vì
không kéo dài được lịch sử trước 2019. Bổ sung World cùng giới hạn lịch
không giải quyết phần thiếu support này.

Nguồn: [support gốc](../../outputs/data/t1_v6_practical_20261105_r2/primary_source_support.csv),
[support mở rộng](../../outputs/data/t1_v6_practical_20261105_r2/augmented_source_support.csv),
[đánh giá nguồn đầy đủ](../../outputs/data/t1_v6_practical_20261105_r2/all_source_scores.csv),
[amendment P3](../../outputs/data/t1_v6_practical_20261105_r2/implementation_amendment_3.json).

## 4. Fresh: cải thiện nhỏ, chưa qua toàn bộ tiêu chí

Chốt `both` trước khi sinh bốn World mới, seed **261105201–261105204**, mỗi
World 20 công ty, lịch episode khác nhau đã được khai báo trước. Các
receipt ghi hash lựa chọn dùng tại lúc sinh. Không đọc `test_000` thành
bảng quan sát để fit/chọn model; các file lịch sử chỉ có thể được đọc byte
để kiểm hash bảo toàn.

| Model | Snapshot fit | Brier joint 365 fresh | Brier Write-off 365 fresh |
|---|---:|---:|---:|
| V6 gốc | 200.000 | 0,189867 | 0,067089 |
| + Ngành | 200.000 | 0,189825 | 0,067149 |
| + Hành vi | 200.000 | 0,189494 | 0,066743 |
| **+ Cả hai, đã chọn trên nguồn** | **200.000** | **0,188946** | **0,066521** |
| V6 trên dữ liệu mở rộng | 300.000 | 0,188324 | 0,066791 |
| + Cả hai trên dữ liệu mở rộng | 300.000 | 0,188140 | 0,066220 |

Ứng viên đã khóa giảm joint **0,4852%**, Write-off Brier **0,8455%** so với
V6. Hai nhánh augmented có joint fresh thấp hơn ứng viên đã chọn, nhưng
không dùng kết quả đó để đảo điều kiện chọn trên nguồn. Nhánh chỉ thêm
ngành làm Write-off Brier fresh hơi xấu hơn V6, dù joint giảm rất ít.

Kết quả riêng của ứng viên `both`; gap là dự báo trừ thực tế, điểm %.
ECE dùng thang 0–1, lấy giá trị lớn nhất ở 28/91/365 ngày.

| Fresh World | n | Joint 365 V6 → ứng viên | Gap Write-off 365 | Max ECE Paid | Tiêu chí không đạt |
|---|---:|---:|---:|---:|---|
| 000 | 4.109 | 0,099582 → **0,100625** | +1,30 | 0,05954 | ECE 91 ngày |
| 001 | 3.612 | 0,150932 → 0,149363 | −1,79 | 0,04453 | Qua cả ba điều kiện |
| 002 | 5.556 | 0,229685 → 0,227232 | −0,80 | 0,07994 | ECE 91 ngày |
| 003 | 2.189 | 0,279270 → 0,278565 | **−6,13** | **0,19322** | ECE 28/91/365; gap Write-off |

Cả bốn qua giới hạn Brier Paid ngắn hạn không xấu quá 2%. Fresh 003 có
Write-off thực tế **19,96%**, dự báo **13,83%**; thêm feature chưa sửa được
sai lệch lớn ở chế độ shock kéo dài. ECE Paid 91 ngày ở World này là
**0,1932**. Không chỉ nhìn mức giảm Brier trung bình để tuyên bố đạt.

Bootstrap ghép cặp 400 lần theo 20 công ty trong từng World, delta joint
365 = ứng viên − V6; số âm có lợi cho ứng viên:

| Fresh | Delta Brier | CI 95% |
|---|---:|---:|
| 000 | +0,001043 | [−0,000437; +0,002608] |
| 001 | −0,001570 | [−0,003797; +0,000040] |
| 002 | −0,002453 | [−0,004496; +0,000299] |
| 003 | −0,000705 | [−0,003349; +0,001534] |

**Cả bốn CI chứa 0.** Chưa chứng minh cải thiện chắc chắn qua công ty,
càng chưa có CI về nhiều nền kinh tế chưa thấy. Các World có seed/episode
mới nhưng vẫn chung generator và giả định tham số.

Che toàn bộ ngành sau khi khóa model làm joint 365 trung bình tăng từ
0,188946 lên **0,189525**. Đây là sensitivity khi nguồn ngành thiếu,
không phải ablation train lại và không dùng chọn lại model. Slice trước/
sau onset, khách thiếu ngành và thu từng phần được lưu riêng; onset chỉ
là annotation audit, không vào model.

Nguồn: [fresh scores](../../outputs/data/t1_v6_practical_20261105_r2/fresh_scores.csv),
[bootstrap](../../outputs/data/t1_v6_practical_20261105_r2/fresh_bootstrap.csv),
[slice](../../outputs/data/t1_v6_practical_20261105_r2/fresh_slices.csv),
[sensitivity](../../outputs/data/t1_v6_practical_20261105_r2/industry_missing_sensitivity.csv),
[lựa chọn đã khóa](../../outputs/data/t1_v6_practical_20261105_r2/final_selection.lock.json).

## Tái lập và bảo toàn

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m experiments.t1_v6_practical.run --stage all
.\.venv\Scripts\python.exe -X utf8 -B -m analysis.summarize_practical_results
.\.venv\Scripts\python.exe -X utf8 -B -m pytest tests/test_t1_v6_practical.py tests/test_t1_practical_context.py tests/test_t1_credit_context.py tests/test_t1_v6_diagnosis.py tests/test_t1_competing_v6.py tests/test_t1_competing_v5.py -q -p no:cacheprovider
```

CLI mặc định xác minh và dùng lại artifact đúng hash. Muốn tính lại từ
đầu, dùng `--output` trỏ thư mục mới theo cùng protocol; tên World/seed
được dùng lại để tái lập, không trở thành một test fresh độc lập mới.

**65 kiểm thử qua, 203 file được bảo vệ giữ nguyên hash.** Model V6 gốc
SHA-256 vẫn là
`9375373bcf413618642cb12f39c7d9a63bb5f24bac24a7c64b9e2eb54f95db44`.
Model ứng viên `both` là
`c7d51abf10fb0e692f98c928966680a1140de64bb7617959e467d47a60dfea50`.
Không fit calibration/cash head, không kích hoạt model hoặc thay cổng sản phẩm.

Protocol, khóa lựa chọn, checksum, phiên bản thư viện, raw provenance,
snapshot mã và các amendment được lưu cùng artifact. Các chặn dữ liệu
thiếu và sửa đọc/cache CSV được ghi trước bước phụ thuộc, không sửa giá
trị source đã fit; bằng chứng tương đương được lưu. P3 là amendment thiết
kế riêng đã nêu, bốn cấu hình fresh không đổi từ trước fit chính.
[Verification](../../outputs/data/t1_v6_practical_20261105_r2/verification.json),
[summary](../../outputs/data/t1_v6_practical_20261105_r2/summary.json),
[bảng số đầy đủ](../../outputs/data/t1_v6_practical_20261105_r2/report_tables.json).
