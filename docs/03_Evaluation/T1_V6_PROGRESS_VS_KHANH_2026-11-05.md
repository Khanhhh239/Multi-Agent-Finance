# So sánh T1 của Khánh và T1 v6 ngày 05/11

**Ngày 05/11/2026. Phạm vi: so sánh hai mô hình trên cùng 65.221 anchor thuộc sáu World synthetic, tập trung vào xác suất trả đủ và phân vị thời điểm trả đủ.**

**Kết luận: T1 v6 ngày 05/11 tốt hơn đối chứng T1 Khánh về xác suất trả đủ trong benchmark này.** Brier Paid chính 28/91 ngày giảm **1,60%**, thấp hơn ở **5/6 World**; Brier Paid 365 ngày giảm **26,54%**. Cải thiện thời điểm trả đủ nhỏ hơn: pinball giới hạn 120 ngày giảm **2,57%**, MAE median giảm khoảng **0,27 ngày**.

Đối chứng Khánh là **HazardGBM mặc định từ commit `70c0ceb` ngày 24/10/2026, tái train trên cùng tập fit**. Chưa xác nhận được booster lịch sử đã push; kết luận chưa bao quát mọi cấu hình tuned, BLEND/CQR mà Khánh có thể đang sử dụng. V6 được chấm là nhánh **ngành + hành vi ledger (`both`), 93 feature snapshot**, đã chọn trên nguồn và giữ nguyên weights trước lần đối chiếu.

**Kết quả theo nhiệm vụ.**

| Nhiệm vụ chung | Kết quả | Đánh giá |
|---|---|---|
| Xác suất trả đủ 28/91 ngày | Brier 0,141217 → 0,138958; giảm 1,60% | V6 cải thiện trung bình, mức tăng nhỏ |
| Xác suất trả đủ 365 ngày | Brier 0,099248 → 0,072913; giảm 26,54% | V6 cải thiện rõ trong benchmark |
| Phân vị trả đủ, mục tiêu giới hạn 120 ngày | Pinball giảm 2,57%; MAE median giảm 0,27 ngày | Cải thiện nhỏ về thời điểm |

<a id="chot-nghien-cuu"></a>

## Chốt ứng viên và phạm vi của kết luận

**Đã chốt nhánh `both` ngày 05/11 làm ứng viên nghiên cứu**, giữ weights,
160 vòng, identity calibration và quy trình feature. Quyết định được ghi
trước khi đọc kết quả lần chấm này, kế thừa lựa chọn trên nguồn. Chưa kích
hoạt model hoặc nghiệm thu dịch vụ.

Model SHA-256: `c7d51abf10fb0e692f98c928966680a1140de64bb7617959e467d47a60dfea50`.
[Manifest chốt nghiên cứu](../../outputs/analysis/t1_v6_final_vs_khanh_20261105/research_candidate.lock.json)
ghi artifact, thứ tự feature và phạm vi sử dụng. Competing risks/chân trời
53 tuần đã bắt đầu từ v5; v6 kế thừa và cải tiến tiếp, không tính mọi thay
đổi so với Khánh là đóng góp mới lần đầu của v6.

**Cập nhật biên tập 06/11/2026:** bản này đã gộp phần chốt nghiên cứu và
thay các bản nháp trước benchmark. Bảng của V6 gốc 01/11 vẫn giữ riêng ở
[báo cáo V6 gốc so với Khánh](T1_V6_PROGRESS_VS_KHANH_V6_ORIGINAL_DETAIL_2026-11-05.md).
Các số 1,67% / 25,72% thuộc V6 gốc; 1,60% / 26,54% thuộc bản 93 feature.
Chúng không phải hai ước lượng của cùng một artifact. Các số so v5 hoặc
fresh ngành/ledger đọc ở [báo cáo v6](T1_V6_COMPETING_RISKS_2026-11-01.md)
và [ablation practical](T1_V6_PRACTICAL_FEATURES_2026-11-05.md), không gán
chúng thành mức thắng toàn bộ pipeline Khánh.

**Thiết kế hai mô hình.**

| Thành phần | T1 Khánh tái train | T1 v6 ngày 05/11 |
|---|---|---|
| Estimator | HazardGBM nhị phân Paid | Competing risks Open/Paid/Write-off |
| Chân trời học | 13 tuần | 53 tuần |
| Sau tuần 13 | Đuôi hình học; hazard kẹp [0,02; 0,6] | Tiếp tục dùng hazard được học |
| Feature snapshot + tuần | 46 + 7 | 93 + 7 |
| Vòng / leaves | 600 / 63 | 160 / 31 |
| Learning rate / L2 | 0,05 / 5 | 0,05 / 8 |
| Feature fraction / bagging fraction | 0,80 / 0,80 | 0,85 / 0,85 |
| Seed | 7 | 20261101 |
| Hàng risk set fit | 1.561.446 | 2.589.709 |
| Risk set | Write-off tiếp tục là không Paid trong nhãn T1 cũ | Dừng ở mọi cause đóng |
| Calibration | Mặc định, không thêm BLEND/CQR | Identity |
| Số cây / file model | 600 / 4,05 MiB | 480 / 1,66 MiB |

160 vòng đa lớp tạo 480 cây cho ba lớp có support; credit-note-only không có support trong train. File nhỏ hơn chưa chứng minh latency/RAM thấp hơn vì chưa đo hiệu năng. Không dùng năm feature `macro_credit_*` giả lập.

V6 có thêm 47 feature snapshot: 18 biến lịch sử rủi ro/cơ cấu quá hạn/thu từng phần, 14 one-hot ngành mua/bán và 15 biến động ledger as-of. Lịch sử khách, trend và lịch thanh toán đã có trong T1 Khánh, nên không tính lại chúng thành đóng góp mới. Thêm feature không tự chứng minh từng feature đều cần thiết; đây là đối chứng toàn bộ phiên bản.

**Cách giữ đối chứng chung.** Hai bên dùng đúng 200.000 snapshot fit, từ 128 công ty nguồn, gồm 100.028 hóa đơn riêng biệt. Thứ tự và 46 feature chung giống nhau theo builder hiện tại; công ty calibration không được trộn vào fit. Chân trời, risk set và cấu hình riêng của từng phiên bản được giữ nguyên; không chuẩn hóa về cùng số vòng/ngân sách tính toán.

Tập đánh giá gồm 25.162 anchor validation, 20.336 test và 19.723 holdout tạo ngày 01/11; mỗi World 40 công ty. Mỗi hóa đơn có một anchor đầu tiên đủ điều kiện, cutoff 01/07–16/12/2024, đủ follow-up 365 ngày. Hai mô hình được chấm trên đúng cùng khóa/thứ tự, nhãn và dư nợ. Dự báo Khánh được dùng lại nguyên vẹn; lần chấm V6 không fit, hiệu chỉnh hoặc tìm tham số.

Chỉ số chính đã khóa là trung bình Brier Paid ở 28 và 91 ngày trong từng World, rồi trung bình sáu World bằng trọng số. ECE cũng tính riêng từng World trước khi lấy trung bình. Brier/ECE nhỏ hơn là tốt hơn; giảm % là giảm sai số tương đối. Paid nghĩa là trả đủ, không phải chỉ có một khoản thu từng phần.

**Xác suất Paid theo sáu chân trời.**

| Ngày từ cutoff | Brier Khánh | Brier V6 | V6 giảm Brier | ECE Khánh → V6 |
|---|---:|---:|---:|---:|
| 28 | 0,143219 | 0,141947 | 0,89% | 0,04207 → 0,04267 |
| 91 | 0,139216 | 0,135970 | 2,33% | 0,05217 → 0,03993 |
| 120 | 0,120219 | 0,115482 | 3,94% | 0,05626 → 0,03585 |
| 180 | 0,101484 | 0,092957 | 8,40% | 0,06752 → 0,03003 |
| 270 | 0,096757 | 0,079499 | 17,84% | 0,08521 → 0,02799 |
| 365 | 0,099248 | 0,072913 | 26,54% | 0,09755 → 0,02612 |

V6 giảm Brier ở cả sáu chân trời trung bình. ECE 28 ngày lại tăng nhẹ **0,04207 → 0,04267**, nên V6 chưa thắng đồng đều về calibration. Sau 91 ngày Khánh dùng đuôi ngoại suy, V6 tiếp tục dùng hazard được học; lợi thế dài hạn cần được hiểu trong khác biệt thiết kế đó.

**V6 giảm dự báo trả đủ quá cao ở dài hạn.** Gap = dự báo − thực tế, đơn vị điểm phần trăm.

| Ngày | Paid thực tế | Khánh dự báo | V6 dự báo | Gap Khánh → V6, điểm % |
|---|---:|---:|---:|---:|
| 28 | 38,59% | 42,32% | 42,05% | 3,73 → 3,46 |
| 91 | 72,88% | 76,59% | 75,93% | 3,71 → 3,05 |
| 120 | 76,88% | 81,52% | 79,30% | 4,64 → 2,42 |
| 180 | 81,25% | 87,54% | 82,97% | 6,29 → 1,71 |
| 270 | 83,74% | 92,12% | 85,42% | 8,38 → 1,67 |
| 365 | 84,96% | 94,71% | 86,53% | 9,75 → 1,58 |

Ở 365 ngày, tỷ lệ Paid thực tế trung bình khoảng 85%; Khánh dự báo gần 95%, V6 gần 87%. V6 giảm mức kỳ vọng trả đủ quá cao, đặc biệt ở phần đuôi.

**Độ ổn định theo World.** Delta = Brier V6 − Khánh; âm có lợi cho V6. CI bootstrap ghép cặp 1.000 lần theo công ty trong từng World.

| World | Anchor | Giảm Brier chính 28/91 | CI 95% delta chính | Giảm Brier 365 | CI 95% delta 365 |
|---|---:|---:|---:|---:|---:|
| validation_000 | 12.169 | 1,33% | [-0,003441; -0,000482] | 24,62% | [-0,034382; -0,023421] |
| validation_001 | 12.993 | -0,17% | [-0,001150; 0,001662] | 20,09% | [-0,019923; -0,010378] |
| test_000 | 5.772 | 3,01% | [-0,007636; -0,001094] | 30,35% | [-0,050898; -0,033916] |
| test_001 | 14.564 | 2,99% | [-0,008186; 0,000189] | 22,64% | [-0,029449; -0,014280] |
| holdout_000 | 5.280 | 1,58% | [-0,005181; 0,001729] | 37,35% | [-0,050245; -0,024106] |
| holdout_001 | 14.443 | 0,68% | [-0,002438; 0,000671] | 18,52% | [-0,019235; -0,008816] |

Delta chính chung **-0,002259**, CI 95% **[-0,003394; -0,001037]**, không chứa 0. V6 có điểm chính tốt hơn ở 5/6 World; `validation_001` xấu hơn nhẹ khoảng 0,17%. Bốn CI chính riêng theo World còn chứa 0. Ở 365 ngày cả sáu CI đều dưới 0. CI chỉ đo bất định qua công ty trong các World cố định, chưa bao gồm nền kinh tế mới hoặc nhiều seed train.

**Cải thiện theo nhóm quá hạn tại cutoff.** Phân tích hồi cứu, trung bình World bằng trọng số trong từng nhóm; chưa có CI slice và không dùng chọn model.

| Quá hạn | Anchor | Giảm Brier chính | Giảm Brier 365 |
|---|---:|---:|---:|
| Chưa quá hạn | 54.210 | 1,16% | 6,38% |
| 1–30 ngày | 3.229 | 3,27% | 20,55% |
| 31–90 ngày | 2.181 | 6,44% | 43,61% |
| 91–180 ngày | 2.829 | 2,40% | 65,92% |
| Trên 180 ngày | 2.772 | 4,15% | 64,13% |

Lợi thế dài hạn lớn hơn ở nhóm quá hạn lâu. Đây là kết quả mô tả của hai phiên bản; chưa tách riêng tác động của competing risks, feature hay tham số và chưa đối chiếu với cure T2.

**Phân vị thời điểm trả đủ.** Mục tiêu đánh giá là `min(thời gian tới trả đủ, 120 ngày)`, gồm cả hóa đơn không trả. Trung bình bằng trọng số World.

| Chỉ số | T1 Khánh | T1 v6 | Cải thiện |
|---|---:|---:|---:|
| Pinball Q10/Q50/Q90 | 7,1362 | 6,9532 | Giảm 2,57% |
| MAE median, ngày | 22,8366 | 22,5630 | Giảm 0,2736 ngày |

Cải thiện về ngày trả cụ thể còn nhỏ. Hóa đơn không trả có giá trị 120 trong mục tiêu giới hạn, không được coi là thực sự trả ngày 120. Phân vị V6 chưa đạt được giữ trạng thái; khi chấm mục tiêu giới hạn thì quy về giới hạn. Không suy ra MAE ngày trả thật chưa bị chặn hoặc chất lượng Q90 dài hạn.

**Giới hạn của kết luận.**

- Đối chứng là bản mặc định từ mã Khánh tái train trên cùng fit; chưa phải booster lịch sử hoặc toàn bộ pipeline tuned/BLEND/CQR. Các feature chung dùng builder hiện tại, không phát lại toàn bộ ingest cũ.
- Sáu World đều synthetic và đã xem: đây là benchmark hồi cứu, chưa chứng minh ưu thế trên SME thật. Ngành/ledger dùng quy trình quan sát synthetic có ngày biết/độ trễ; chưa phải dữ liệu doanh nghiệp thật đã xác nhận.
- Phạm vi đối chiếu này là Paid và phân vị thời điểm trả đủ. Không suy kết quả sang chất lượng tiền thu hoặc kết luận thắng pipeline T1 + T2 cũ về Write-off.

**Kết luận trao đổi với Khánh:** V6 cải thiện nhiệm vụ chung xác suất trả đủ, rõ nhất ở dài hạn và nợ quá hạn lâu. Ngắn hạn và phân vị ngày trả tăng ít hơn; calibration 28 ngày cùng một World vẫn có điểm yếu. Các mức cải thiện trên áp dụng cho đúng hai phiên bản được định nghĩa trong báo cáo.

**Bằng chứng:** 70 kiểm thử qua; 144 file được bảo vệ giữ nguyên hash trong lần chấm; các chỉ số Paid tính lại từ dự báo lưu có sai khác 0. Bản gửi này chỉ lọc và trình bày lại kết quả hai model, không chạy dự báo/train lại.

Nguồn: [tóm tắt](../../outputs/analysis/t1_v6_vs_khanh_only_20261105/comparison_summary.json), [protocol đối chiếu](../../outputs/analysis/t1_v6_vs_khanh_only_20261105/comparison_protocol.json), [điểm theo World](../../outputs/analysis/t1_v6_vs_khanh_only_20261105/scores.csv), [điểm tổng hợp](../../outputs/analysis/t1_v6_vs_khanh_only_20261105/aggregate_scores.csv), [CI chính](../../outputs/analysis/t1_v6_vs_khanh_only_20261105/primary_by_world.csv), [CI từng chân trời](../../outputs/analysis/t1_v6_vs_khanh_only_20261105/bootstrap.csv), [phân vị](../../outputs/analysis/t1_v6_vs_khanh_only_20261105/quantiles_restricted120.csv), [phân nhóm](../../outputs/analysis/t1_v6_vs_khanh_only_20261105/slices_equal_world.csv), [kiểm tra bản gửi](../../outputs/analysis/t1_v6_vs_khanh_only_20261105/verification.json).


## Phần bổ sung so với V6 gốc 01/11

Trên cùng benchmark này, Brier Paid chính là **0,138855 → 0,138958**, **tăng 0,07%**; delta = **0,000103**, CI 95% **[-0,000252; 0,000488]**. Đây là đối chiếu mô tả sau khi đã chọn ứng viên, không dùng để chọn lại bản chốt. Tiêu chí chọn nhánh trước đó là joint/Write-off Brier 365 ngày trên nguồn với giới hạn Paid ngắn hạn; không phải tối thiểu hóa riêng Paid Brier ở benchmark này.

Trong lần P0–P4 trước, nhánh `both` đã được chọn bằng 10.666 anchor nguồn trước khi sinh bốn fresh World. Joint Brier 365 giảm 0,49% trên fresh; cả bốn CI theo công ty chứa 0, chỉ 1/4 World qua toàn bộ tiêu chí nghiên cứu. Vì vậy việc chốt bản hiện tại không đồng nghĩa phần bổ sung có lợi chắc chắn hoặc đã giải quyết distribution shift.

Cash head chưa được train/chấm lại với 93 feature. Kết quả WAPE của bản gốc
đọc ở [phần tiền thu lịch sử](T1_V6_PROGRESS_VS_KHANH_V6_ORIGINAL_DETAIL_2026-11-05.md#cash-v6-goc);
đối chứng là `dư nợ × P(Paid trước h)`, không phải toàn bộ T6 của Khánh.
Không chuyển bảng tiền thu của bản gốc sang ứng viên hiện tại.

## Giới hạn đầu vào và bước tiếp theo

Feature ngành/ledger mới có known_at, missing/coverage và giới hạn tenant. Lần benchmark vẫn dùng lớp quan sát ERP synthetic: ngành là customer-master giả lập theo quý, coverage 75%, trễ 14 ngày; ledger có sai số phân bổ và trễ tiếp nhận. 64 feature V6 gốc vẫn giữ giả định synthetic về lịch sử/đóng nợ/liên kết tiền. Chưa thể gọi toàn bộ đầu vào là đã kiểm chứng trên doanh nghiệp thật.

Riêng test_000, Write-off 365 ngày của bản mới là **13,84%**, thực tế **20,32%**. Thắng Paid so với T1 không tự giải quyết calibration Write-off. Không so trực tiếp cure T2 với Write-off hữu hạn.

Benchmark unified v2 trước đây dùng V6 gốc 01/11, chưa dùng nhánh 93 feature này. Không chuyển điểm CRPS/coverage cũ sang bản 05/11. Việc chốt nghiên cứu hiện tại không thay cổng sản phẩm hoặc model dịch vụ.

Công việc tiếp theo đã thu hẹp: **giữ nguyên model hiện tại; kiểm toàn bộ nguồn/thời điểm biết của đầu vào; hoàn thiện adapter và tích hợp thử nghiệm**. Calibration, hazard theo thời gian và cash head là hướng dự phòng khi phép đo sử dụng chỉ ra lỗi cụ thể, không phải ba vòng nâng cấp bắt buộc trước khi kết thúc nghiên cứu này.

## Bằng chứng gốc và cách tái lập

**70 kiểm thử qua**, gồm chặn lệch khóa/thứ tự/nhãn/dư nợ và hồi quy feature/risk set. **144 file được bảo vệ giữ nguyên hash**. Các chỉ số Paid được tính độc lập lại từ dự báo lưu, sai khác lớn nhất **0**. Không fit, sinh World hoặc hiệu chỉnh; baseline Khánh và model V6 giữ nguyên.

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -u -m analysis.benchmark_t1_v6_final_vs_khanh --output outputs/analysis/t1_v6_final_vs_khanh_rerun
.\.venv\Scripts\python.exe -X utf8 -B -m pytest tests/test_t1_v6_final_benchmark.py tests/test_t1_khanh_benchmark.py tests/test_t1_v6_practical.py tests/test_t1_practical_context.py tests/test_t1_competing_v6.py tests/test_t1_competing_v5.py -q -p no:cacheprovider
```

Thư mục output mới phải chưa tồn tại. Script đọc weights, baseline và bảng quan sát theo thiết kế đã khóa; không retrain. Lặp lại cùng seed/World không trở thành một test fresh mới.

Nguồn: [protocol lần chấm](../../outputs/analysis/t1_v6_final_vs_khanh_20261105/protocol.lock.json), [summary](../../outputs/analysis/t1_v6_final_vs_khanh_20261105/summary.json), [điểm từng World](../../outputs/analysis/t1_v6_final_vs_khanh_20261105/scores.csv), [điểm tổng hợp](../../outputs/analysis/t1_v6_final_vs_khanh_20261105/aggregate_scores.csv), [CI chính](../../outputs/analysis/t1_v6_final_vs_khanh_20261105/primary_by_world.csv), [CI từng chân trời](../../outputs/analysis/t1_v6_final_vs_khanh_20261105/bootstrap.csv), [phân nhóm](../../outputs/analysis/t1_v6_final_vs_khanh_20261105/slices_equal_world.csv), [phân vị](../../outputs/analysis/t1_v6_final_vs_khanh_20261105/quantiles_restricted120.csv), [missingness](../../outputs/analysis/t1_v6_final_vs_khanh_20261105/feature_missingness.csv), [verification](../../outputs/analysis/t1_v6_final_vs_khanh_20261105/verification.json), [source snapshot](../../outputs/analysis/t1_v6_final_vs_khanh_20261105/source_snapshot.zip), [baseline gốc](../../outputs/analysis/t1_khanh_vs_v6_20261105/protocol.lock.json), [cash lịch sử](../../outputs/analysis/t1_khanh_vs_v6_20261105/cash_scores.csv), [lựa chọn trên nguồn](../../outputs/data/t1_v6_practical_20261105_r2/final_selection.lock.json), [fresh trước đó](../../outputs/data/t1_v6_practical_20261105_r2/fresh_scores.csv).

Số kiểm thử/hash xác nhận trên đây thuộc **lần chấm 05/11**, không phải một
lần benchmark mới do gộp tài liệu. Bản Markdown đã thay đổi ngày 06/11 nên
hash báo cáo cũ trong `report_review.json`/`verification.json` là hồ sơ của
phiên bản văn bản cũ; không sửa lại chúng để khớp bản biên tập này. Các script
đóng gói báo cáo tại thời điểm cũ có thể yêu cầu đúng hash đó; không dùng
chúng để ghi đè tài liệu gộp. Artifact CSV/JSON/model giữ nguyên.
