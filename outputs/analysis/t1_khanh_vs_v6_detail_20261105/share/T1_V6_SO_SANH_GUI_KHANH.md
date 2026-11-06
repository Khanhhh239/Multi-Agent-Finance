# T1 của Khánh và T1 v6 — đối chiếu chi tiết để trao đổi kỹ thuật

**Ngày 05/11/2026. Hai mô hình được chấm trên cùng 65.221 anchor thuộc sáu
World synthetic. Báo cáo dùng kết quả đã khóa; phần phân nhóm bổ sung không
train, hiệu chỉnh hoặc chọn lại model.**

**Kết luận chính: V6 cải thiện dự báo xác suất trả đủ so với đối chứng
`HazardGBM` mặc định từ mã Khánh được tái train trên cùng tập fit.** Brier
Paid trung bình 28/91 ngày giảm **1,67%**, thấp hơn ở 6/6 World; tại 365
ngày giảm **25,72%**. Lợi thế lớn nhất nằm ở dự báo dài hạn và các khoản
quá hạn lâu. Cash head chưa tốt đồng đều: cải thiện tổng tiền công ty ở
91–365 ngày nhưng làm sai số từng hóa đơn tăng.

Đối chứng là **T1 Khánh tái train từ commit `70c0ceb`**, không phải booster
lịch sử đã push. Kết luận áp dụng cho bản mặc định được xác định bên dưới;
chưa phải kết luận vượt mọi cấu hình tuned, BLEND hoặc CQR có thể được
Khánh sử dụng. Phần này cần được đối chiếu khi thống nhất baseline chính
thức giữa hai bên.

**Ý nghĩa theo từng nhiệm vụ của T1.**

| Nhiệm vụ | Kết quả so sánh | Đánh giá |
|---|---|---|
| Dự báo khả năng trả đủ trong 28/91 ngày | Brier chính giảm 1,67%; CI chung không chứa 0 | V6 cải thiện, mức tăng còn nhỏ |
| Dự báo khả năng trả đủ trong 365 ngày | Brier giảm 25,72%; gap Paid từ +9,75 còn +1,56 điểm % | V6 cải thiện rõ trong benchmark |
| Ước lượng ngày trả bằng median | MAE của mục tiêu giới hạn 120 ngày giảm khoảng 0,27 ngày | Cải thiện nhỏ; chưa chứng minh đoán ngày cụ thể tốt hơn nhiều |
| Tiền thu cộng theo công ty | WAPE thấp hơn ở 91/180/365 ngày | Cash head V6 có lợi ở cấp tổng hợp dài hạn |
| Tiền thu từng hóa đơn | WAPE cao hơn đối chứng ở cả bốn chân trời | Cash head V6 còn kém ở nhiệm vụ này |
| Write-off so với T2 cũ | Chưa có đối chứng cùng định nghĩa đầu ra | Chưa kết luận V6 thắng pipeline T1 + T2 cũ |

**Thiết kế hai mô hình và những phần thực sự thay đổi.**

| Thành phần | T1 Khánh tái train | T1 v6 |
|---|---|---|
| Estimator | `HazardGBM` nguyên bản tại commit `70c0ceb` ngày 24/10/2026 | Competing risks đã khóa ngày 01/11/2026 |
| Đầu ra được học | Hazard nhị phân Paid; cure thuộc T2 riêng | Hazard chung Open/Paid/Write-off |
| Chân trời học | 13 tuần | 53 tuần |
| Sau tuần 13 | Đuôi hình học, hazard đuôi kẹp trong [0,02; 0,6] | Tiếp tục dùng hazard được học theo tuần |
| Feature snapshot / tuần | 46 / 7 | 64 / 7 |
| Số vòng / leaves | 600 / 63 | 160 / 31 |
| Learning rate / L2 | 0,05 / 5 | 0,05 / 8 |
| Feature fraction / bagging fraction | 0,80 / 0,80 | 0,85 / 0,85 |
| Seed | 7 | 20261101 |
| Risk set | Dừng ở Paid hoặc hết quan sát; Write-off tiếp tục là không Paid trong nhãn T1 cũ | Dừng ở mọi cause đóng; sau Write-off không còn invoice-week |
| Hàng tuần fit | 1.561.446 | 2.589.709 |
| Calibration trong đối chứng này | Giữ `HazardGBM` mặc định; không thêm CQR/BLEND | Identity đã được chọn trên nguồn từ lần V6 gốc |
| Số cây / kích thước file model | 600 cây / 4,05 MiB | 480 cây / 1,66 MiB |

V6 là mô hình đa lớp: 160 vòng tạo 480 cây cho ba lớp đang có support;
không so số vòng như thể hai bên đều là binary. File nhỏ hơn chưa chứng
minh inference nhanh hơn, vì V6 phải dự báo 53 tuần thay vì 13. Benchmark
này chưa đo latency hoặc RAM. Core V6 có nhánh credit-note-only nhưng
train không có nhãn này, nên chưa được coi là đã học thêm rủi ro đó.

18 feature bổ sung gồm sáu biến lịch sử đóng/xóa nợ của khách và người
bán; năm biến cơ cấu dư nợ/quá hạn; năm biến thu tiền trên hóa đơn; hai
biến credit note và phần dư nợ còn lại. T1 Khánh đã có lịch sử khách,
trend thanh toán, lịch tuần/Tết, lời hứa và `paid_frac_so_far`; các nhóm
đó được kế thừa. Nhánh ngành/ledger thử sau ngày 01/11 không nằm trong
artifact V6 đang được so sánh ở báo cáo này.

Nguồn: [protocol benchmark](evidence/outputs/analysis/t1_khanh_vs_v6_20261105/protocol.lock.json),
[metadata V6](evidence/outputs/data/t1_competing_v6_20261101/train.json),
[kích thước model](evidence/outputs/analysis/t1_khanh_vs_v6_detail_20261105/model_sizes.csv),
[risk set T1 cũ](evidence/outputs/analysis/t1_khanh_vs_v6_detail_20261105/legacy_risk_counts.json).

**Điều kiện so sánh được giữ chung.**

Hai mô hình dùng đúng **200.000 snapshot fit**, từ **128 công ty nguồn**,
bao gồm **100.028 hóa đơn riêng biệt**. Thứ tự snapshot và giá trị 46
feature chung giống nhau. Snapshot train từ 04/2019–06/2023, nhãn chốt
01/07/2024; các công ty calibration của V6 không được trộn vào fit.

Tập đánh giá có 25.162 anchor validation, 20.336 anchor test và 19.723
anchor thuộc hai holdout tạo ngày 01/11. Mỗi World có 40 công ty. Đơn vị
là anchor đầu tiên đủ điều kiện của từng hóa đơn đang mở; cutoff từ
01/07 đến 16/12/2024, nhãn đến 31/12/2025, đủ follow-up 365 ngày. Hai
bên được chấm trên đúng cùng khóa hóa đơn/cutoff và kết quả quan sát.
Tất cả các World đã từng được xem, nên đây là đối chứng hồi cứu, chưa
phải xác nhận trên một holdout mới chưa đụng tới.

Cùng snapshot không có nghĩa cùng số invoice-week: hai mô hình có chân
trời và quy tắc dừng khác nhau. Cấu hình từng phiên bản được giữ nguyên,
không chuẩn hóa về cùng số cây hoặc ngân sách tính toán. Các feature
chung được lấy từ cùng builder hiện tại, nên phép đo không phát lại toàn
bộ ingest/feature builder lịch sử của Khánh.

**Chỉ số chính được khóa trước khi tái train baseline** là trung bình
Brier Paid ở 28 và 91 ngày, sau đó lấy trung bình với trọng số bằng nhau
cho sáu World. Paid là sự kiện **trả đủ**, không phải chỉ có một khoản
thu từng phần. Chân trời tính từ cutoff. Brier đo bình phương sai số
xác suất; ECE đo độ lệch giữa xác suất và tần suất quan sát theo các bin.
Cả hai nhỏ hơn là tốt hơn. Các mức giảm % dưới đây là giảm sai số tương
đối, không phải tăng tương ứng tỷ lệ thu tiền hoặc độ chính xác phân loại.
Không gán Write-off của T1 Khánh bằng 0 để tạo một điểm nhiều trạng thái.

**Kết quả xác suất theo đủ sáu chân trời.**

| Ngày từ cutoff | Brier Paid Khánh | Brier Paid V6 | V6 giảm Brier | ECE Paid Khánh → V6 |
|---|---:|---:|---:|---:|
| 28 | 0,143219 | 0,141713 | 1,05% | 0,04207 → 0,04126 |
| 91 | 0,139216 | 0,135997 | 2,31% | 0,05217 → 0,03949 |
| 120 | 0,120219 | 0,115740 | 3,73% | 0,05626 → 0,03492 |
| 180 | 0,101484 | 0,093489 | 7,88% | 0,06752 → 0,03001 |
| 270 | 0,096757 | 0,080211 | 17,10% | 0,08521 → 0,02864 |
| 365 | 0,099248 | 0,073725 | 25,72% | 0,09755 → 0,02626 |

Brier chính 28/91 ngày là **0,141217 → 0,138855**, giảm **1,67%**. Mức
cải thiện tăng theo chân trời: từ khoảng 1% ở 28 ngày lên khoảng 26% ở
365 ngày. Diễn giải phù hợp là V6 có lợi thế lớn hơn trong phần dự báo
vượt chân trời học trực tiếp của T1 cũ. Đây là kết quả của toàn bộ phiên
bản, chưa phải ablation chứng minh riêng competing risks, 18 feature,
regularization hay số vòng đóng góp bao nhiêu.

**V6 giảm dự báo Paid quá cao ở dài hạn.** Các số dưới đây đều là trung
bình với trọng số bằng nhau theo World; gap = dự báo − thực tế, đơn vị
điểm phần trăm.

| Ngày | Paid thực tế | T1 Khánh dự báo | V6 dự báo | Gap Khánh → V6, điểm % |
|---|---:|---:|---:|---:|
| 28 | 38,59% | 42,32% | 41,61% | +3,73 → +3,02 |
| 91 | 72,88% | 76,59% | 75,75% | +3,71 → +2,87 |
| 120 | 76,88% | 81,52% | 79,14% | +4,64 → +2,26 |
| 180 | 81,25% | 87,54% | 82,93% | +6,29 → +1,68 |
| 270 | 83,74% | 92,12% | 85,41% | +8,38 → +1,66 |
| 365 | 84,96% | 94,71% | 86,51% | +9,75 → +1,56 |

Ví dụ, trên 100 hóa đơn theo tỷ lệ trung bình này, ở 365 ngày quan sát
khoảng 85 hóa đơn trả đủ; T1 cũ dự báo gần 95, V6 gần 87. Điều này cho
thấy V6 giảm kỳ vọng trả đủ quá cao. Nó chưa chứng minh dòng tiền từng
hóa đơn được dự báo đúng, vì tiền còn có thể về từng phần trước tất toán.

Calibration chưa tốt hơn đồng đều. Khi gộp theo số anchor trong từng vai
trò, tại **28 ngày**, ECE của nhóm test
cũ tăng **0,03246 → 0,04063**, nhóm holdout 01/11 tăng **0,02525 →
0,03211**. Vì vậy, Brier trung bình tốt hơn không được diễn giải thành
mọi nhóm xác suất đều được hiệu chỉnh tốt hơn.

Nguồn: [aggregate_scores.csv](evidence/outputs/analysis/t1_khanh_vs_v6_20261105/aggregate_scores.csv).

**Độ ổn định theo từng World và độ chắc chắn của chênh lệch.**

Delta = Brier V6 − Brier Khánh; số âm có lợi cho V6. CI dưới đây lấy mẫu
lại công ty 1.000 lần trong từng World, giữ hai mô hình ghép cặp.

| World | Anchor | Giảm Brier chính 28/91 | CI 95% delta chính | Giảm Brier 365 | CI 95% delta 365 |
|---|---:|---:|---:|---:|---:|
| validation_000 | 12.169 | 1,28% | [-0,003433; -0,000442] | 23,56% | [-0,032729; -0,022712] |
| validation_001 | 12.993 | 0,02% | [-0,001117; 0,001195] | 18,96% | [-0,019055; -0,009735] |
| test_000 | 5.772 | 3,75% | [-0,007908; -0,003574] | 29,94% | [-0,049894; -0,033703] |
| test_001 | 14.564 | 2,74% | [-0,007543; 0,000332] | 21,94% | [-0,028281; -0,013751] |
| holdout_000 | 5.280 | 1,62% | [-0,005061; 0,001453] | 36,18% | [-0,048404; -0,023611] |
| holdout_001 | 14.443 | 0,38% | [-0,001547; 0,000679] | 18,00% | [-0,018910; -0,008356] |

Brier chính thấp hơn ở **6/6 World**, nhưng `validation_001` gần như hòa.
Bốn CI riêng của chỉ số chính còn chứa 0. Khi tổng hợp với trọng số bằng
nhau cho sáu World, delta chính là **−0,002362**, CI 95%
**[−0,003418; −0,001271]**, không chứa 0. Riêng ở 365 ngày, cả sáu CI
theo World đều nằm dưới 0, ủng hộ lợi thế dài hạn trong tập đã đánh giá.
Các CI này chỉ phản ánh bất định qua công ty ở các World cố định, chưa
bao gồm các đường kinh tế/World mới hoặc nhiều seed train.

Ở 28 ngày, V6 có hai World Brier hơi xấu hơn: `validation_001` tăng
khoảng **0,26%** và `holdout_001` tăng **0,55%** tương đối. Cả hai vẫn có
chỉ số chính 28/91 tốt hơn do kết quả tại 91 ngày.

Nguồn: [primary_by_world.csv](evidence/outputs/analysis/t1_khanh_vs_v6_20261105/primary_by_world.csv),
[bảng ghép điểm và CI](evidence/outputs/analysis/t1_khanh_vs_v6_detail_20261105/paired_by_world_horizon.csv).

**Cải thiện tập trung ở những hóa đơn nào?** Phân nhóm bổ sung theo số
ngày quá hạn tại cutoff, tính từ due date của hóa đơn. Đây là phân tích
hồi cứu trên dự báo đã khóa, không phải tiêu chí chọn model hoặc kết
luận nhân quả. Mỗi nhóm có mặt trong cả sáu World; điểm được lấy trung
bình với trọng số World bằng nhau trong từng nhóm.

| Quá hạn tại cutoff | Anchor | V6 giảm Brier chính 28/91 | V6 giảm Brier 365 |
|---|---:|---:|---:|
| Chưa quá hạn | 54.210 | 1,28% | 6,38% |
| 1–30 ngày | 3.229 | 3,31% | 17,08% |
| 31–90 ngày | 2.181 | 5,44% | 40,60% |
| 91–180 ngày | 2.829 | 3,36% | 65,66% |
| Trên 180 ngày | 2.772 | 3,67% | 62,81% |

Nhóm chưa quá hạn chiếm phần lớn anchor và có lợi ích dài hạn nhỏ hơn.
Lợi thế mạnh ở nhóm quá hạn lâu phù hợp với nhu cầu mô hình hóa khả năng
không trả đủ và rời risk set bằng Write-off, thay vì tiếp tục đẩy Paid
lên qua đuôi ngoại suy. Đây là diễn giải cơ chế, chưa tách riêng tác động
của từng thay đổi thiết kế hoặc so với đầu ra cure của T2 cũ.

Theo tháng anchor, Brier chính tháng 7 giảm **3,30%**; tháng 8, 9 và 12
lại tăng nhẹ khoảng **0,44%, 0,17% và 0,46%**. Kết quả tổng thể không có
nghĩa V6 thắng ở mọi thời kỳ con. Các slice có phụ thuộc và chưa có CI
riêng; không dùng chúng để chọn lại tham số theo các tháng đã xem.
Nguồn: [slices_equal_world.csv](evidence/outputs/analysis/t1_khanh_vs_v6_detail_20261105/slices_equal_world.csv).

**Độ chính xác thời điểm thanh toán: cải thiện còn nhỏ.** Hai mô hình
được so trên mục tiêu `min(thời gian tới trả đủ, 120 ngày)`, bao gồm cả
hóa đơn chưa trả. Điểm dưới đây dùng trọng số bằng nhau cho mỗi World.

| Chỉ số của mục tiêu giới hạn 120 ngày | T1 Khánh | V6 | Giảm sai số |
|---|---:|---:|---:|
| Pinball trung bình Q10/Q50/Q90 | 7,1362 | 6,9453 | 2,68% |
| MAE median, ngày | 22,8366 | 22,5714 | 1,16% |

MAE median giảm khoảng **0,2652 ngày**. Đây là cải thiện nhỏ về dự báo
median của mục tiêu giới hạn, chưa phải bằng chứng V6 đoán chính xác
ngày trả thật hơn nhiều. Hóa đơn chưa trả có giá trị 120 trong mục tiêu
đánh giá giới hạn; không được coi là đã trả thật ở ngày 120. Q của V6
chưa đạt trong chân trời được giữ trạng thái, khi chấm mục tiêu giới hạn
thì quy về giới hạn tương ứng. Không suy từ bảng này ra chất lượng Q90
chưa bị chặn hoặc khoảng bất định ngày thanh toán dài hạn.
Nguồn: [quantiles_restricted120.csv](evidence/outputs/analysis/t1_khanh_vs_v6_20261105/quantiles_restricted120.csv).

**Tiền thu: cần phân biệt chất lượng từng hóa đơn và chất lượng tổng công ty.**
Đối chứng của Khánh là `dư nợ × P(Paid trước h)` từ T1, không phải toàn
bộ pipeline T6 cũ. V6 dùng cash head riêng dự báo tỷ lệ thu. Thực thu
là tiền về trong chân trời; WAPE gộp theo tổng tiền thực thu trên cùng
sáu World, khác với cách lấy trung bình World của các bảng xác suất.

| Ngày | WAPE công ty Khánh → V6 | WAPE hóa đơn Khánh → V6 | Bên có sai số thấp hơn |
|---|---:|---:|---|
| 28 | 12,03% → 12,38% | 65,78% → 78,49% | Khánh thấp hơn ở cả hai cấp |
| 91 | 8,21% → 6,56% | 30,73% → 32,41% | V6 thấp hơn ở công ty; Khánh thấp hơn ở hóa đơn |
| 180 | 6,02% → 4,98% | 17,84% → 20,56% | V6 thấp hơn ở công ty; Khánh thấp hơn ở hóa đơn |
| 365 | 7,30% → 5,07% | 12,22% → 15,98% | V6 thấp hơn ở công ty; Khánh thấp hơn ở hóa đơn |

WAPE hóa đơn cộng trị tuyệt đối sai số của từng hóa đơn; WAPE công ty
cộng dự báo/thực thu trong công ty trước khi lấy trị tuyệt đối. Sai số
có thể triệt tiêu khi cộng gộp, nên WAPE công ty thấp hơn không chứng
minh từng hóa đơn được dự báo tốt hơn. Kết quả ủng hộ nghiên cứu cash
head ở cấp tổng hợp dài hạn, chưa ủng hộ thay mặc định ở cấp hóa đơn
hoặc dự báo tiền 28 ngày. Chưa có CI WAPE trong đối chứng này.
Nguồn: [cash_aggregate.csv](evidence/outputs/analysis/t1_khanh_vs_v6_detail_20261105/cash_aggregate.csv).

**Giá trị của phần cải tiến và giới hạn kết luận.**

Phần đầu tư V6 có giá trị kỹ thuật rõ nhất ở **phân phối trả đủ dài hạn**
và **giảm dự báo Paid quá cao với nợ lâu ngày**. Brier ngắn hạn cũng tốt
hơn, nhưng biên cải thiện nhỏ; dự báo ngày cụ thể mới tăng nhẹ. Chưa có
ablation để khẳng định cả 18 feature hoặc mọi thay đổi tham số đều cần
thiết, và cash head còn một phần chưa thắng. Chưa đo hiệu quả kinh tế
để quy mức giảm Brier thành tiền thu thêm hoặc ROI của công sức phát triển.

Ba giới hạn cần giữ khi trao đổi kết quả:

- Đối chứng hiện tại là `HazardGBM` mặc định từ mã Khánh, tái train trên
  cùng tập fit. Nếu bản Khánh đang dùng là một cấu hình tuned, BLEND/CQR
  hoặc một booster khác, cần chấm đúng bản đó trước khi quyết định thay thế.
- Benchmark kiểm nhiệm vụ chung Paid. Cure T2 không đồng nhất với
  Write-off trong 365 ngày; chưa có phép so trực tiếp pipeline T1 + T2 cũ.
- Các World đều synthetic và đã xem. Kết quả là bằng chứng hồi cứu cho
  hai phiên bản được định nghĩa ở đây, chưa chứng minh triển khai tốt hơn
  trên SME thật hoặc đã giải quyết distribution shift.

**Phần cần cải thiện tiếp chỉ tập trung vào mô hình.** Những hướng dưới
đây là đề xuất thí nghiệm, chưa phải kết quả đã đo.

| Ưu tiên | Điểm còn yếu | Hướng kiểm tiếp | Điều kiện giữ ứng viên |
|---|---|---|---|
| P0 — Calibration | ECE 28 ngày chưa thắng đều; World khó còn lệch Paid/Write-off | Hiệu chỉnh joint có regularization theo thời gian, đối chứng identity | Chọn trên nguồn; ECE Paid ≤ 0,05, gap Write-off 365 trong ±3 điểm %, Paid Brier ngắn hạn không xấu quá 2% |
| P1 — Hazard theo thời gian | Paid đầu kỳ cao, Write-off đuôi thấp trong chẩn đoán World khó | Kiểm tương tác thời gian và regularization trong cùng competing risks | Giảm sai số đồng thời hai cause và survival; không chỉ tăng Write-off cuối kỳ |
| P2 — Cash head | WAPE từng hóa đơn và 28 ngày còn xấu hơn proxy Khánh | Đối chứng mục tiêu/loss của head, chấm cả công ty và hóa đơn | Thắng đối chứng ở đơn vị sử dụng đã chọn; giữ tiền tích lũy tăng và không vượt dư nợ |

V6 vẫn có `test_000` Write-off 365 ngày dự báo khoảng **13,91%** so với
**20,32%** thực tế, thiếu **6,41 điểm %**. Kết quả thắng Paid so với T1
không làm sai lệch này tự biến mất. Xem [chẩn đoán V6](evidence/docs/03_Evaluation/T1_V6_CAUSE_DIAGNOSIS_2026-11-05.md).
Ưu tiên một thí nghiệm calibration trên nguồn trước khi mở thêm nhiều họ
mô hình. Không fit/chọn theo các World hoặc slice đã dùng trong báo cáo.

**Nội dung cần thống nhất với Khánh trước bước tiếp theo:** baseline
chính thức có đúng là `HazardGBM` mặc định đang chấm hay là cấu hình khác;
đầu ra ưu tiên của T1 là xác suất theo chân trời hay ngày trả cụ thể;
đơn vị sử dụng cash forecast là từng hóa đơn hay tổng công ty. Đây là
các quyết định ảnh hưởng trực tiếp tiêu chí giữ V6 và cách sửa cash head.

**Bằng chứng và tái lập.** Mã baseline khớp nguyên bản Git; dự báo Paid,
Brier và WAPE của V6 tái lập với artifact gốc có sai khác **0**. Đối
chứng có **32 kiểm thử qua**, **100 file đầu vào/mã/model giữ nguyên hash**.
Phân nhóm bổ sung chỉ đọc dự báo và due date, có kiểm tổng 65.221 anchor,
không thiếu due date và không thay model, calibration hoặc cổng sản phẩm.

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -u -m analysis.benchmark_t1_khanh_vs_v6 --output outputs/analysis/t1_khanh_vs_v6_rerun
.\.venv\Scripts\python.exe -X utf8 -B -m analysis.detail_t1_khanh_comparison --output outputs/analysis/t1_khanh_vs_v6_detail_rerun
```

Output mới phải chưa tồn tại. Lệnh chi tiết đọc artifact benchmark gốc đã
khóa. Đọc [summary](evidence/outputs/analysis/t1_khanh_vs_v6_20261105/summary.json),
[verification benchmark](evidence/outputs/analysis/t1_khanh_vs_v6_20261105/verification.json),
[verification chi tiết](evidence/outputs/analysis/t1_khanh_vs_v6_detail_20261105/verification.json),
[script benchmark](evidence/analysis/benchmark_t1_khanh_vs_v6.py) và
[script phân nhóm](evidence/analysis/detail_t1_khanh_comparison.py).
