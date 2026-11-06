# T1 v6: kết quả competing risks và tiền thu (01/11/2026)

Đã chạy xong train, thử hiệu chỉnh, đánh giá và inference. V6 cải thiện nhẹ Brier so với v5, nhưng **chưa đạt toàn bộ tiêu chí nghiên cứu**; World khó vẫn lệch xác suất và cash head chưa tốt đồng đều. Model chưa được kích hoạt trong dịch vụ.

Báo cáo này gộp các bảng benchmark bổ sung từ bản tổng hợp phương pháp cùng ngày. Số liệu vẫn thuộc lần chạy đã lưu, không phải lần train hoặc benchmark mới. Công thức, feature, risk set, calibration và cách tính metric đọc tại [phương pháp chung v5/v6](../04_AI_Methods/T1_COMPETING_RISKS_V5_V6.md).

Mã ở [`experiments/t1_competing_v6/`](../../experiments/t1_competing_v6/), artifact ở [`outputs/data/t1_competing_v6_20261101/`](../../outputs/data/t1_competing_v6_20261101/). V4/v5 và các báo cáo lịch sử được giữ nguyên.

## Dữ liệu và split của lần chạy

V6 tái sử dụng [cohort v4](../../data/synthetic/v4_shortpay_4shock_20261028_cohort.json), giữ vai trò bốn World train/hai validation/hai test. Snapshot fit thực tế từ **01/04/2019–19/06/2023**, stride 28 ngày; ngày cuối tối đa trong protocol là 25/06/2023. Nhãn train và calibration kết thúc 01/07/2024, đủ ít nhất 371 ngày theo dõi. Nhóm calibration lấy anchor đầu tiên đủ điều kiện từ ngày cắt không sớm hơn 03/01/2022.

| Thành phần | Số lượng đã chạy |
|---|---:|
| Doanh nghiệp fit model | 128 |
| Snapshot đủ điều kiện của nhóm fit | 422.841 |
| Snapshot được lấy để fit | 200.000 |
| Hàng tuần fit model hazard | 2.589.709 |
| Nhãn open | 2.397.029 |
| Nhãn paid | 152.552 |
| Nhãn write-off | 40.128 |
| Nhãn credit-note-only | 0 |
| Hóa đơn đánh giá chính | 65.221 |
| Trong đó validation cũ | 25.162 |
| Trong đó test cũ | 20.336 |
| Trong đó fresh test | 19.723 |

Tập đánh giá chính lấy **snapshot đầu tiên đủ điều kiện của từng hóa đơn**, từ 01/07/2024–16/12/2024, nhãn đến 31/12/2025. Các mốc xác suất là 28/91/120/180/270/365 ngày. Mỗi hóa đơn đánh giá có đủ theo dõi đến mốc dài hạn.

Hai World fresh được khóa trước khi fit: `v6_holdout_20261101_000` và `001`, seed **106110101/106110102**, mỗi World 40 doanh nghiệp. Toàn kỳ chúng có 348.295 hóa đơn; chỉ **5.280/14.443** hóa đơn đủ điều kiện vào tập benchmark chính. Chúng dùng cấu hình/lịch shock của hai World test v4 với seed mới, nên kiểm tính ổn định qua seed trong cùng máy phát, chưa kiểm một họ shock hoàn toàn mới.

Các World validation/test cũ đã được xem trong phát triển trước đó; kết quả trên chúng là chẩn đoán. “Fresh” chỉ độc lập về seed đã khai báo, không phải dữ liệu kinh tế hay ledger độc lập với máy phát.

Nguồn: [protocol](../../experiments/t1_competing_v6/protocol.json), [train.json](../../outputs/data/t1_competing_v6_20261101/train.json), [registry fresh holdout](../../outputs/data/t1_competing_v6_20261101/fresh_holdout_registry.json), [evaluation.json](../../outputs/data/t1_competing_v6_20261101/evaluation.json).

Bộ hiệu chỉnh dùng **8.939 hóa đơn** thuộc 16 công ty nguồn để fit và
**10.454 hóa đơn** thuộc 16 công ty nguồn khác để chọn. Cả bốn khoảng tuần
đều hội tụ, nhưng Brier joint trên nhóm chọn không cải thiện, nên bộ chọn giữ
**identity**. Không dùng test để đảo lựa chọn này. Chi tiết ở
[`calibration.json`](../../outputs/data/t1_competing_v6_20261101/calibration.json).

## Kết quả xác suất

Các bảng gộp dùng trọng số số hóa đơn trong từng World. Brier cộng sai số theo các trạng thái, không chia thêm cho số trạng thái. Cohort không có credit-note-only nên Brier bốn trạng thái cùng thang với v5. Baseline tần suất chỉ fit từ train; v4/v5 được tải từ model đã lưu và chấm trên cùng hóa đơn.

### Brier trên tập đánh giá chính

| Tập | Ngày | Tần suất train | V4 | V5 | V6 |
| --- | --- | --- | --- | --- | --- |
| Validation | 28 | 0.487284 | 0.293500 | 0.294351 | 0.293299 |
| Validation | 91 | 0.397262 | 0.304898 | 0.286973 | 0.286848 |
| Validation | 365 | 0.247032 | 0.234812 | 0.157961 | 0.155638 |
| Test cũ | 28 | 0.478231 | 0.284876 | 0.283869 | 0.278077 |
| Test cũ | 91 | 0.428387 | 0.337489 | 0.299329 | 0.292289 |
| Test cũ | 365 | 0.287900 | 0.272474 | 0.166687 | 0.163226 |
| Fresh test | 28 | 0.492126 | 0.297510 | 0.294918 | 0.293049 |
| Fresh test | 91 | 0.381667 | 0.303348 | 0.275433 | 0.275250 |
| Fresh test | 365 | 0.214584 | 0.202965 | 0.130426 | 0.127721 |

Ở ngày 365, v6 giảm Brier so với v5 **2.08% trên test cũ** và **2.07% trên fresh test**. Ở fresh test ngày 91, mức giảm rất nhỏ. Các số này mô tả toàn bộ thay đổi của phiên bản, không đo riêng lợi ích từng thành phần.

Nguồn: [comparison.csv](../../outputs/data/t1_competing_v6_20261101/comparison.csv), [aggregate_summary.json](../../outputs/data/t1_competing_v6_20261101/aggregate_summary.json).

### ECE paid và Brier riêng paid

| Tập | Ngày | ECE paid v5 | ECE paid v6 | Brier paid v5 | Brier paid v6 |
| --- | --- | --- | --- | --- | --- |
| Validation | 28 | 0.030484 | 0.035841 | 0.143732 | 0.143270 |
| Validation | 91 | 0.029551 | 0.033343 | 0.137538 | 0.137637 |
| Validation | 365 | 0.017281 | 0.020391 | 0.075264 | 0.074227 |
| Test cũ | 28 | 0.038516 | 0.040626 | 0.136721 | 0.134161 |
| Test cũ | 91 | 0.054964 | 0.045432 | 0.136949 | 0.134772 |
| Test cũ | 365 | 0.035059 | 0.030157 | 0.080225 | 0.078160 |
| Fresh test | 28 | 0.033566 | 0.032112 | 0.143144 | 0.142217 |
| Fresh test | 91 | 0.022856 | 0.023705 | 0.130933 | 0.131405 |
| Fresh test | 365 | 0.011294 | 0.014694 | 0.062717 | 0.061270 |

ECE validation xấu hơn v5 ở cả ba mốc được trích; ECE fresh test 91/365 ngày cũng tăng. Trên fresh test ngày 91, Brier chung giảm nhưng Brier riêng paid hơi tăng. Vì vậy không mô tả v6 là tốt hơn v5 ở tất cả khía cạnh xác suất.

### Tiêu chí nghiên cứu và trường hợp chưa đạt

Protocol khóa trước yêu cầu: **ECE paid ≤ 0.05 tại 28/91/365 ngày**, sai lệch write-off ngày 365 không quá **3 điểm phần trăm**, và Brier paid ngắn hạn không xấu quá **2% tương đối so với v5**, kiểm riêng theo từng World. Đây là tiêu chí nghiên cứu, không phải cổng phát hành.

| World | Ngày | ECE paid v6 | Gap write-off v6 | Tiêu chí chưa đạt |
| --- | --- | --- | --- | --- |
| validation_000 | 91 | 0.052053 | Không áp ngưỡng dài hạn | ECE paid > 0.05 |
| test_000 | 28 | 0.071924 | Không áp ngưỡng dài hạn | ECE paid > 0.05 |
| test_000 | 91 | 0.086137 | Không áp ngưỡng dài hạn | ECE paid > 0.05 |
| test_000 | 365 | 0.059178 | -6.41 điểm % | ECE paid > 0.05; sai lệch tuyệt đối write-off > 3 điểm % |

Cả hai fresh World qua các tiêu chí trên **ở tập anchor đánh giá chính**, nhưng `research_checks_all_passed=false` vì các trường hợp cũ chưa đạt. Riêng `test_000` ngày 365 có write-off thực tế **20.32%** trong khi v6 dự báo khoảng **13.91%**, vẫn thiếu **6.41 điểm phần trăm**.

Nguồn: [evaluation.json](../../outputs/data/t1_competing_v6_20261101/evaluation.json). Gap trong bảng là dự báo trừ thực tế.

### Độ chắc chắn qua bootstrap theo công ty

Bootstrap ghép cặp 400 lần, lấy mẫu lại các công ty trong từng World. Delta là **Brier v6 − Brier v5** ở ngày 365; số âm có lợi cho v6.

| World | Delta Brier | CI 95% theo công ty |
| --- | --- | --- |
| validation_000 | -0.003343 | [-0.005550; -0.001080] |
| validation_001 | -0.001367 | [-0.003210; 0.000343] |
| test_000 | -0.004199 | [-0.006826; -0.001844] |
| test_001 | -0.003169 | [-0.007690; 0.000178] |
| fresh_000 | -0.004190 | [-0.009250; 0.002188] |
| fresh_001 | -0.002162 | [-0.004207; -0.000533] |

Một số khoảng còn chứa 0. Đây là khoảng tin cậy qua công ty trong một World, không phải qua nhiều đường kinh tế/shock chưa thấy; không khẳng định cải thiện chắc chắn ở mọi World.

Nguồn: [company_bootstrap.csv](../../outputs/data/t1_competing_v6_20261101/company_bootstrap.csv).

### Nhóm rủi ro và ngày cắt rolling

Ví dụ Brier ngày 365 trên các nhóm hóa đơn; một hóa đơn có thể thuộc nhiều nhóm nên không cộng các hàng để ra toàn tập:

| Tập | Nhóm | Hóa đơn | Brier v5 | Brier v6 |
| --- | --- | --- | --- | --- |
| Test cũ | Đã thu một phần | 1.238 | 0.223308 | 0.214026 |
| Test cũ | Tuổi trên 180 ngày | 1.978 | 0.292374 | 0.287212 |
| Test cũ | Dư nợ ≥ P90 train | 1.860 | 0.117505 | 0.116965 |
| Fresh test | Đã thu một phần | 919 | 0.194166 | 0.187298 |
| Fresh test | Tuổi trên 180 ngày | 1.241 | 0.263430 | 0.246440 |
| Fresh test | Dư nợ ≥ P90 train | 1.303 | 0.128415 | 0.128729 |

Ngưỡng hóa đơn lớn lấy từ P90 dư nợ trong train, bằng **395.616.000 VND**. V6 cải thiện các nhóm đã thu một phần và tuổi trên 180 ngày trong bảng, nhưng hơi kém v5 ở hóa đơn lớn của fresh test.

Nguồn: [subgroups.csv](../../outputs/data/t1_competing_v6_20261101/subgroups.csv).

Rolling kiểm riêng tất cả hóa đơn mở tại hai ngày cắt cố định; tập này khác tập lấy anchor đầu tiên của mỗi hóa đơn. Bảng dưới trích mốc 91/365 ngày, gộp World theo số hóa đơn:

| Tập | Ngày cắt | Mốc ngày | Brier v5 | Brier v6 | ECE paid v5 | ECE paid v6 |
| --- | --- | --- | --- | --- | --- | --- |
| Test cũ | 2024-07-01 | 91 | 0.412327 | 0.402573 | 0.094420 | 0.088878 |
| Test cũ | 2024-07-01 | 365 | 0.261671 | 0.256081 | 0.072183 | 0.063834 |
| Test cũ | 2024-10-07 | 91 | 0.323072 | 0.310222 | 0.048135 | 0.042485 |
| Test cũ | 2024-10-07 | 365 | 0.228507 | 0.218177 | 0.041237 | 0.036172 |
| Fresh test | 2024-07-01 | 91 | 0.313638 | 0.308598 | 0.053422 | 0.053457 |
| Fresh test | 2024-07-01 | 365 | 0.167732 | 0.160958 | 0.035510 | 0.038618 |
| Fresh test | 2024-10-07 | 91 | 0.334902 | 0.331516 | 0.041725 | 0.042987 |
| Fresh test | 2024-10-07 | 365 | 0.208948 | 0.204795 | 0.032301 | 0.036169 |

Ở rolling 01/07/2024, ECE paid fresh test gộp tại 28 ngày là **0.06069**, tại 91 ngày là **0.05346**, cao hơn 0.05. Kết luận fresh World đạt trên tập anchor chính không có nghĩa mọi cửa sổ rolling đều đạt. Hai ngày cắt cũng chưa đủ đại diện mọi giai đoạn kinh tế.

Nguồn: [rolling_origins.csv](../../outputs/data/t1_competing_v6_20261101/rolling_origins.csv).

## Kết quả tiền thu

Đối chứng là proxy v5: dư nợ tại cutoff × P(paid trước chân trời), chưa phải toàn bộ T6. WAPE công ty tính sai số sau khi cộng các hóa đơn trong công ty; WAPE hóa đơn tính trước khi cộng. Gộp World theo tổng tiền thực thu; công thức chi tiết ở tài liệu phương pháp chung.

| Tập | Ngày | WAPE công ty proxy v5 | WAPE công ty v6 | WAPE hóa đơn proxy v5 | WAPE hóa đơn v6 |
| --- | --- | --- | --- | --- | --- |
| Validation | 28 | 8.92% | 10.40% | 69.58% | 78.35% |
| Validation | 91 | 5.28% | 4.98% | 32.30% | 33.03% |
| Validation | 180 | 4.52% | 4.30% | 20.69% | 21.06% |
| Validation | 365 | 4.17% | 4.16% | 15.17% | 16.25% |
| Test cũ | 28 | 14.28% | 13.83% | 74.09% | 86.09% |
| Test cũ | 91 | 11.32% | 9.31% | 33.48% | 33.50% |
| Test cũ | 180 | 7.40% | 6.46% | 21.10% | 21.13% |
| Test cũ | 365 | 6.12% | 6.58% | 15.64% | 16.70% |
| Fresh test | 28 | 11.47% | 13.30% | 61.34% | 71.36% |
| Fresh test | 91 | 5.94% | 5.28% | 29.28% | 30.39% |
| Fresh test | 180 | 4.65% | 4.05% | 18.94% | 19.30% |
| Fresh test | 365 | 4.30% | 4.41% | 13.84% | 14.81% |

Ở test cũ và fresh test, cash head giúp WAPE công ty tại 91/180 ngày. Tuy nhiên, tại 365 ngày WAPE công ty xấu hơn proxy, và **WAPE hóa đơn xấu hơn ở toàn bộ các tập/chân trời đã đo**, gồm cả validation. Chưa có cơ sở dùng cash head làm thay thế mặc định; model cũng chưa xuất khoảng bất định tiền thu cho từng hóa đơn.

Nguồn: [cash_comparison.csv](../../outputs/data/t1_competing_v6_20261101/cash_comparison.csv), [aggregate_summary.json](../../outputs/data/t1_competing_v6_20261101/aggregate_summary.json).

## Inference ngày 31/12/2025

Artifact xuất dự báo cho **39.377 hóa đơn còn mở**, dư nợ tổng **5.724.149.436.000 VND**, khớp tập hóa đơn và dư nợ batch v4. Có **17.486 Q90** và **5.733 Q50** chưa đạt ngưỡng trong 365 ngày, được để null và ghi trạng thái.

Đầu ra gồm xác suất theo trạng thái/chân trời, Q10/Q50/Q90 có trạng thái và tiền thu dự báo ở 28/91/180/365 ngày. Không so trực tiếp số phân vị chưa đạt trong 365 ngày với tỷ lệ v4 chạm trần 120 ngày để tuyên bố chất lượng tốt hơn. Batch cuối 2025 không có nhãn tương lai để đo độ chính xác.

Nguồn: [predictions.csv](../../outputs/data/t1_competing_v6_20261101/inference_2025-12-31/predictions.csv), [summary inference](../../outputs/data/t1_competing_v6_20261101/inference_2025-12-31/summary.json).

## Kiểm tra và các giới hạn còn lại

[`verification.json`](../../outputs/data/t1_competing_v6_20261101/verification.json)
ghi **20/20 kiểm thử v5/v6 pass**, model/snapshot/hash hợp lệ, 24 Parquet của
hai World mới khớp manifest. 48 dòng đối chứng v4/v5 ở các World cũ khớp số
đã lưu với sai khác tối đa khoảng **1,11 × 10⁻¹⁶**. Toàn bộ dòng inference
qua kiểm tổng xác suất bằng 1, CIF tăng, tiền thu tăng theo chân trời và
không vượt dư nợ; trạng thái phân vị khớp giá trị null.

Đã kiểm giữ nguyên 162 file trong bảo vệ pipeline, tám file bổ sung gồm batch
inference/báo cáo/test cũ, cùng hash mã dùng chung v4. Không ghi đè v4/v5.

Các hạn chế chưa được giải quyết hoàn toàn:

1. Sai lệch xác suất ở World khó vẫn còn; bộ hiệu chỉnh thử chưa vượt qua
   điều kiện chọn, nên lần này chưa áp dụng một bộ hiệu chỉnh mới.
2. Core hiểu credit-note-only nhưng tập train có 0 nhãn này, nên
   `credit_note_risk_learned=false`; thu hồi sau write-off chưa được mô hình hóa.
3. Nhãn đánh giá vẫn có đủ theo dõi dài hạn. Chưa kiểm IPCW trên cohort gần
   hiện tại bị kiểm duyệt, hoặc xác suất ngoài 365 ngày.
4. Hai ngày cắt rolling và hai seed mới chưa bao phủ mọi lịch sử/shock;
   chưa có kiểm định ledger SME thật, khoảng tin cậy giữa nhiều World hoặc
   khoảng bất định tiền thu cho từng hóa đơn.
5. Nhiều thành phần cùng thay đổi: đặc trưng, sampling, số vòng, split công
   ty. Chưa có ablation để gán mức cải thiện riêng cho từng thành phần.
6. Cash head chưa tốt đồng đều và chưa nối vào dịch vụ. Artifact v6 được giữ
   để đối chiếu, không tự nâng thành model sản phẩm.

Model hazard SHA-256: `9375373bcf413618642cb12f39c7d9a63bb5f24bac24a7c64b9e2eb54f95db44`.

Model tiền thu SHA-256: `7af7980f4ef17149c52d374faded6ffa096fcbcdbba79fd9b07a07540f6eba76`.

## Tái lập và bảo toàn

```powershell
.\.venv\Scripts\python.exe -m experiments.t1_competing_v6.run --stage all
```

Đọc `environment.json`, `source_hashes.json`, `source_snapshot.zip` và
`preservation_before.json`/`preservation_after.json` trong artifact. Pipeline
từ chối dùng lại artifact khác hash/cấu hình và tạo file mới bằng chế độ
exclusive. Không ghi vào thư mục v4/v5. Các giới hạn còn lại được công bố
cùng kết quả tốt và kết quả không đạt.
