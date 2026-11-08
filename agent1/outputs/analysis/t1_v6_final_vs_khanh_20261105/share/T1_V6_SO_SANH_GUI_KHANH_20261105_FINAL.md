# T1 của Khánh và T1 v6 ngày 05/11 — báo cáo chốt nghiên cứu

**Ngày 05/11/2026. Bản V6 hiện tại là V6 + ngành + hành vi ledger (`both`), 93 feature snapshot. Đã chấm trên cùng 65.221 anchor thuộc sáu World với baseline Khánh đã lưu. Không train hoặc hiệu chỉnh trong lần này.**

**Kết luận: V6 ngày 05/11 cải thiện dự báo xác suất trả đủ so với `HazardGBM` mặc định từ mã Khánh được tái train trên cùng tập fit.** Brier Paid chính 28/91 ngày giảm **1,60%**, thấp hơn ở **5/6 World**; Brier Paid 365 ngày giảm **26,54%**. Các mức này thuộc đúng artifact ngày 05/11, thay cho số của V6 gốc trong phần kết luận hiện hành.

**Đã chốt V6 ngày 05/11 làm ứng viên nghiên cứu hiện tại**, giữ nguyên weights, 160 vòng, identity calibration và quy trình feature. Quyết định được ghi trước khi đọc kết quả lần chấm này, kế thừa nhánh đã chọn trên nguồn. Tạm dừng thêm feature/kiến trúc; bước tiếp theo là kiểm đầu vào và tích hợp thử nghiệm. Đây chưa phải nghiệm thu hoặc kích hoạt dịch vụ.

Bản chốt có SHA-256 `c7d51abf10fb0e692f98c928966680a1140de64bb7617959e467d47a60dfea50`. [Manifest chốt nghiên cứu](evidence/outputs/analysis/t1_v6_final_vs_khanh_20261105/research_candidate.lock.json) ghi model, thứ tự feature, trạng thái và phạm vi sử dụng.

Đối chứng Khánh là bản mặc định tại commit `70c0ceb` ngày 24/10/2026, đã tái train trong benchmark trước. Không có booster lịch sử đúng mốc được xác nhận; kết luận chưa bao quát cấu hình tuned, BLEND/CQR hoặc pipeline T1 + T2/T6 đầy đủ của Khánh.

**Kết quả theo nhiệm vụ.**

| Nhiệm vụ | Kết quả | Đánh giá |
|---|---|---|
| Xác suất trả đủ 28/91 ngày | Brier 0,141217 → 0,138958; giảm 1,60% | Cải thiện trung bình; xem CI và từng World bên dưới |
| Xác suất trả đủ 365 ngày | Brier giảm 26,54%; gap Paid 9,75 → 1,58 điểm % | Lợi thế dài hạn rõ hơn ngắn hạn trong benchmark |
| Thời điểm trả đủ | Chấm lại phân vị của bản 05/11 trên mục tiêu giới hạn 120 ngày | Chỉ kết luận trong mục tiêu này |
| Tiền thu | Không có cash head mới cho nhánh 05/11 | Bảng tiền thu bên dưới là lịch sử V6 gốc, không gán cho bản mới |
| Write-off so với T2 cũ | Không có đối chứng cùng định nghĩa | Chưa kết luận thắng pipeline T1 + T2 cũ |

**Hai mô hình được chấm.**

| Thành phần | T1 Khánh tái train | V6 ngày 05/11 |
|---|---|---|
| Estimator | HazardGBM nhị phân Paid | Competing risks Open/Paid/Write-off |
| Chân trời học | 13 tuần; sau đó đuôi hình học, hazard kẹp [0,02; 0,6] | 53 tuần |
| Feature snapshot + tuần | 46 + 7 | 93 + 7 |
| Số vòng / leaves | 600 / 63 | 160 / 31 |
| Learning rate / L2 | 0,05 / 5 | 0,05 / 8 |
| Feature fraction / bagging fraction | 0,80 / 0,80 | 0,85 / 0,85 |
| Seed | 7 | 20261101 |
| Hàng risk set fit | 1.561.446 | 2.589.709 |
| Risk set | Write-off tiếp tục là không Paid trong nhãn T1 cũ | Dừng ở mọi cause đóng |
| Calibration | Mặc định; không thêm BLEND/CQR | Identity |
| Số cây / file model | 600 / 4,05 MiB | 480 / 1,66 MiB |

160 vòng đa lớp tạo 480 cây cho ba lớp có support; không so số vòng như thể cả hai đều là binary. File nhỏ hơn không chứng minh latency/RAM thấp hơn: lần này chưa đo hiệu năng. Credit-note-only không có support trong train.

So với Khánh, V6 gốc thêm 18 feature về lịch sử Write-off, cơ cấu quá hạn, thu từng phần và điều chỉnh dư nợ. Bản 05/11 thêm 14 one-hot ngành mua/bán có ngày biết và 15 feature biến động ledger as-of. Tổng cộng 47 feature snapshot bổ sung; không dùng năm `macro_credit_*` giả lập. Lịch sử khách, trend và lịch thanh toán đã có trong T1 Khánh.

**Điều kiện đối chứng.** Hai bên dùng đúng 200.000 snapshot fit, 128 công ty nguồn, 100.028 hóa đơn riêng biệt. Thứ tự và 46 feature chung giống nhau theo builder hiện tại; đây không phải phát lại toàn bộ ingest lịch sử của Khánh. Bản 05/11 giữ nguyên tập fit/risk set/cấu hình V6, chỉ thêm whitelist ngành/ledger đã định nghĩa.

65.221 anchor gồm 25.162 validation, 20.336 test và 19.723 holdout của lần 01/11; mỗi World 40 công ty. Mỗi hóa đơn có một anchor đầu tiên đủ điều kiện, cutoff 01/07–16/12/2024, đủ follow-up 365 ngày. Đã đối chiếu nguyên thứ tự khóa, nhãn, thời gian theo dõi và dư nợ với dự báo cũ. Baseline Khánh được dùng lại nguyên vẹn, không fit lại.

Chỉ số chính kế thừa benchmark đã khóa: trung bình Brier Paid 28/91 ngày trong từng World, sau đó trung bình sáu World bằng trọng số. Brier/ECE nhỏ hơn là tốt hơn; giảm % là giảm sai số tương đối. Paid nghĩa là trả đủ, không phải chỉ có thu từng phần. Không gán Write-off Khánh bằng 0 để chấm joint Brier.

Tất cả sáu World đều đã xem: đây là đối chứng hồi cứu, không phải fresh confirmation mới hoặc bằng chứng trên SME thật. Không chọn lại ứng viên theo điểm các World này.

**Xác suất Paid theo sáu chân trời, trung bình World bằng trọng số.**

| Ngày | Brier Khánh | Brier V6 05/11 | V6 giảm Brier | ECE Khánh → V6 |
|---|---:|---:|---:|---:|
| 28 | 0,143219 | 0,141947 | 0,89% | 0,04207 → 0,04267 |
| 91 | 0,139216 | 0,135970 | 2,33% | 0,05217 → 0,03993 |
| 120 | 0,120219 | 0,115482 | 3,94% | 0,05626 → 0,03585 |
| 180 | 0,101484 | 0,092957 | 8,40% | 0,06752 → 0,03003 |
| 270 | 0,096757 | 0,079499 | 17,84% | 0,08521 → 0,02799 |
| 365 | 0,099248 | 0,072913 | 26,54% | 0,09755 → 0,02612 |

Sau 91 ngày Khánh ngoại suy đuôi, V6 tiếp tục dùng hazard được học. Lợi thế dài hạn phản ánh toàn bộ thay đổi phiên bản, chưa phân rã riêng đóng góp của competing risks, feature hay regularization.

| Ngày | Paid thực tế | Khánh dự báo | V6 dự báo | Gap Khánh → V6, điểm % |
|---|---:|---:|---:|---:|
| 28 | 38,59% | 42,32% | 42,05% | 3,73 → 3,46 |
| 91 | 72,88% | 76,59% | 75,93% | 3,71 → 3,05 |
| 120 | 76,88% | 81,52% | 79,30% | 4,64 → 2,42 |
| 180 | 81,25% | 87,54% | 82,97% | 6,29 → 1,71 |
| 270 | 83,74% | 92,12% | 85,42% | 8,38 → 1,67 |
| 365 | 84,96% | 94,71% | 86,53% | 9,75 → 1,58 |

**Kết quả theo World và bất định.** Delta = Brier V6 05/11 − Khánh; âm có lợi cho V6. Bootstrap ghép cặp 1.000 lần theo công ty trong từng World.

| World | Anchor | Giảm Brier chính | CI 95% delta chính | Giảm Brier 365 | CI 95% delta 365 |
|---|---:|---:|---:|---:|---:|
| validation_000 | 12.169 | 1,33% | [-0,003441; -0,000482] | 24,62% | [-0,034382; -0,023421] |
| validation_001 | 12.993 | -0,17% | [-0,001150; 0,001662] | 20,09% | [-0,019923; -0,010378] |
| test_000 | 5.772 | 3,01% | [-0,007636; -0,001094] | 30,35% | [-0,050898; -0,033916] |
| test_001 | 14.564 | 2,99% | [-0,008186; 0,000189] | 22,64% | [-0,029449; -0,014280] |
| holdout_000 | 5.280 | 1,58% | [-0,005181; 0,001729] | 37,35% | [-0,050245; -0,024106] |
| holdout_001 | 14.443 | 0,68% | [-0,002438; 0,000671] | 18,52% | [-0,019235; -0,008816] |

Delta chính chung là **-0,002259**, CI 95% **[-0,003394; -0,001037]**. CI này chỉ đo bất định qua công ty trong sáu World cố định, không bao gồm nền kinh tế mới hoặc nhiều seed train. Điểm tốt hơn ở một World không đồng nghĩa CI riêng của World đó loại trừ 0.

**Phần bổ sung ngày 05/11 so với V6 gốc 01/11.**

Trên cùng benchmark này, Brier Paid chính là **0,138855 → 0,138958**, **tăng 0,07%**; delta = **0,000103**, CI 95% **[-0,000252; 0,000488]**. Đây là đối chiếu mô tả sau khi đã chọn ứng viên, không dùng để chọn lại bản chốt. Tiêu chí chọn nhánh trước đó là joint/Write-off Brier 365 ngày trên nguồn với giới hạn Paid ngắn hạn; không phải tối thiểu hóa riêng Paid Brier ở benchmark này.

Trong lần P0–P4 trước, nhánh `both` đã được chọn bằng 10.666 anchor nguồn trước khi sinh bốn fresh World. Joint Brier 365 giảm 0,49% trên fresh; cả bốn CI theo công ty chứa 0, chỉ 1/4 World qua toàn bộ tiêu chí nghiên cứu. Vì vậy việc chốt bản hiện tại không đồng nghĩa phần bổ sung có lợi chắc chắn hoặc đã giải quyết distribution shift.

**Phân nhóm hồi cứu theo quá hạn.** Trung bình World bằng trọng số trong mỗi nhóm; không phải tiêu chí chọn model hoặc kết luận nhân quả, chưa có CI slice.

| Quá hạn tại cutoff | Anchor | Giảm Brier chính | Giảm Brier 365 |
|---|---:|---:|---:|
| Chưa quá hạn | 54.210 | 1,16% | 6,38% |
| 1–30 ngày | 3.229 | 3,27% | 20,55% |
| 31–90 ngày | 2.181 | 6,44% | 43,61% |
| 91–180 ngày | 2.829 | 2,40% | 65,92% |
| Trên 180 ngày | 2.772 | 4,15% | 64,13% |

Số âm ở cột giảm sai số nghĩa là V6 xấu hơn. Bảng tháng và kết quả đầy đủ giữ trong CSV; các nhóm phụ thuộc nhau, không dùng để tối ưu theo tháng/tuổi nợ đã xem.

**Phân vị thời điểm trả đủ.** Chấm mục tiêu `min(thời gian tới trả đủ, 120 ngày)`, gồm cả hóa đơn không trả. Trung bình bằng trọng số World.

| Model | Pinball Q10/Q50/Q90 | MAE median, ngày |
|---|---:|---:|
| T1 Khánh | 7,1362 | 22,8366 |
| V6 gốc 01/11, đối chiếu phụ | 6,9453 | 22,5714 |
| V6 hiện tại 05/11 | 6,9532 | 22,5630 |

Hóa đơn không trả có giá trị 120 trong mục tiêu giới hạn, không coi là đã trả thật ngày 120. Phân vị V6 chưa đạt được giữ trạng thái; khi chấm mục tiêu giới hạn thì quy về giới hạn. Không suy từ đây ra MAE ngày trả thật chưa bị chặn hoặc chất lượng Q90 dài hạn.

**Tiền thu — kết quả lịch sử V6 gốc 01/11, không phải cash head của bản 05/11.** Lần này chỉ đánh giá hazard/phân vị mới. Cash head cũ không được train hoặc chấm lại với 93 feature. Đối chứng Khánh là `dư nợ × P(Paid trước h)`, không phải toàn bộ T6.

| Ngày | WAPE công ty Khánh → V6 gốc | WAPE hóa đơn Khánh → V6 gốc |
|---|---:|---:|
| 28 | 12,03% → 12,38% | 65,78% → 78,49% |
| 91 | 8,21% → 6,56% | 30,73% → 32,41% |
| 180 | 6,02% → 4,98% | 17,84% → 20,56% |
| 365 | 7,30% → 5,07% | 12,22% → 15,98% |

WAPE gộp theo tổng tiền thực thu, khác cách lấy trung bình World của bảng xác suất. Sai số có thể triệt tiêu khi cộng theo công ty; kết quả không ủng hộ dùng cash head cũ làm mặc định cho từng hóa đơn. Chưa có CI WAPE.

**Giới hạn thực tế và quyết định tiếp theo.**

Feature ngành/ledger mới có known_at, missing/coverage và giới hạn tenant. Lần benchmark vẫn dùng lớp quan sát ERP synthetic: ngành là customer-master giả lập theo quý, coverage 75%, trễ 14 ngày; ledger có sai số phân bổ và trễ tiếp nhận. 64 feature V6 gốc vẫn giữ giả định synthetic về lịch sử/đóng nợ/liên kết tiền. Chưa thể gọi toàn bộ đầu vào là đã kiểm chứng trên doanh nghiệp thật.

Riêng test_000, Write-off 365 ngày của bản mới là **13,84%**, thực tế **20,32%**. Thắng Paid so với T1 không tự giải quyết calibration Write-off. Không so trực tiếp cure T2 với Write-off hữu hạn.

Benchmark unified v2 trước đây dùng V6 gốc 01/11, chưa dùng nhánh 93 feature này. Không chuyển điểm CRPS/coverage cũ sang bản 05/11. Việc chốt nghiên cứu hiện tại không thay cổng sản phẩm hoặc model dịch vụ.

Công việc tiếp theo đã thu hẹp: **giữ nguyên model hiện tại; kiểm toàn bộ nguồn/thời điểm biết của đầu vào; hoàn thiện adapter và tích hợp thử nghiệm**. Calibration, hazard theo thời gian và cash head là hướng dự phòng khi phép đo sử dụng chỉ ra lỗi cụ thể, không phải ba vòng nâng cấp bắt buộc trước khi kết thúc nghiên cứu này.

**Bằng chứng và tái lập.**

**70 kiểm thử qua**, gồm chặn lệch khóa/thứ tự/nhãn/dư nợ và hồi quy feature/risk set. **144 file được bảo vệ giữ nguyên hash**. Các chỉ số Paid được tính độc lập lại từ dự báo lưu, sai khác lớn nhất **0**. Không fit, sinh World hoặc hiệu chỉnh; baseline Khánh và model V6 giữ nguyên.

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -u -m analysis.benchmark_t1_v6_final_vs_khanh --output outputs/analysis/t1_v6_final_vs_khanh_rerun
.\.venv\Scripts\python.exe -X utf8 -B -m pytest tests/test_t1_v6_final_benchmark.py tests/test_t1_khanh_benchmark.py tests/test_t1_v6_practical.py tests/test_t1_practical_context.py tests/test_t1_competing_v6.py tests/test_t1_competing_v5.py -q -p no:cacheprovider
```

Thư mục output mới phải chưa tồn tại. Script đọc weights, baseline và bảng quan sát theo thiết kế đã khóa; không retrain. Lặp lại cùng seed/World không trở thành một test fresh mới.

Nguồn: [protocol lần chấm](evidence/outputs/analysis/t1_v6_final_vs_khanh_20261105/protocol.lock.json), [summary](evidence/outputs/analysis/t1_v6_final_vs_khanh_20261105/summary.json), [điểm từng World](evidence/outputs/analysis/t1_v6_final_vs_khanh_20261105/scores.csv), [điểm tổng hợp](evidence/outputs/analysis/t1_v6_final_vs_khanh_20261105/aggregate_scores.csv), [CI chính](evidence/outputs/analysis/t1_v6_final_vs_khanh_20261105/primary_by_world.csv), [CI từng chân trời](evidence/outputs/analysis/t1_v6_final_vs_khanh_20261105/bootstrap.csv), [phân nhóm](evidence/outputs/analysis/t1_v6_final_vs_khanh_20261105/slices_equal_world.csv), [phân vị](evidence/outputs/analysis/t1_v6_final_vs_khanh_20261105/quantiles_restricted120.csv), [missingness](evidence/outputs/analysis/t1_v6_final_vs_khanh_20261105/feature_missingness.csv), [verification](evidence/outputs/analysis/t1_v6_final_vs_khanh_20261105/verification.json), [source snapshot](evidence/outputs/analysis/t1_v6_final_vs_khanh_20261105/source_snapshot.zip), [baseline gốc](evidence/outputs/analysis/t1_khanh_vs_v6_20261105/protocol.lock.json), [cash lịch sử](evidence/outputs/analysis/t1_khanh_vs_v6_20261105/cash_scores.csv), [lựa chọn trên nguồn](evidence/outputs/data/t1_v6_practical_20261105_r2/final_selection.lock.json), [fresh trước đó](evidence/outputs/data/t1_v6_practical_20261105_r2/fresh_scores.csv).
