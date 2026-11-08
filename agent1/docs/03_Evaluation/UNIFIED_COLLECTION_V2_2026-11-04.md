# Unified collection v2: đã sửa adapter, mô hình chưa thắng v6

**Ngày 04/11/2026. Bằng chứng: prototype synthetic đã chạy, revision r3.**

**Kết luận: đã thực hiện các sửa chữa và chạy hết protocol mới; chưa đủ bằng
chứng thay v6.** Các lỗi RNG, thời điểm rút vốn, bridge phí và phạm vi dòng
tiền đã được xử lý trong luồng riêng. Trên bốn World mới, CRPS số dư ngân
hàng của unified xấu hơn v6 **0,85–5,08%**. AR CRPS cũng xấu hơn ở ba World.
Không thay model dịch vụ, v1/v4/v5/v6 hoặc các cổng sản phẩm.

**Cập nhật dọn bản cũ ngày 04/11:** theo yêu cầu chủ dự án, bản unified v1
riêng đã được xóa. V2 không còn import v1; core/scoring/calibration/copula
cần thiết nằm trong package v2, hai ca kế toán được giữ bằng fixture nhỏ.
Weights, CSV benchmark và snapshot mã của lần đo v2/r3 giữ nguyên. Các số
57 kiểm thử và 540 file bên dưới là kết quả tại thời điểm benchmark, trước
lần dọn này. Đây là thay đổi tổ chức mã, không phải lần train/benchmark mới.
Sau khi gỡ v1, **62 kiểm thử hồi quy đã qua**. Phần hậu kiểm khi chạy lại
analysis được ghi vào các thư mục có hậu tố `_after_cleanup`, giữ nguyên
bảng và verification lịch sử. [Biên bản dọn mã](../../outputs/maintenance/unified_v1_removal_20261104.json)
ghi danh sách đã xóa và hash các artifact được bảo toàn.

Mã/cách chạy: [unified_collection_v2](../../experiments/unified_collection_v2/README.md).
Thiết kế: [contract v2](../04_AI_Methods/UNIFIED_COLLECTION_V2_CONTRACT_2026-11-04.md).
Quyết định máy đọc: [decision.json](../../outputs/data/unified_collection_v2_20261104_r3/decision.json).

**1. Các sửa chữa đã thực hiện và kiểm chứng.**

| Phần | Thực hiện | Bằng chứng/giới hạn |
|---|---|---|
| RNG | Stream có tên theo thành phần, case và MC replicate | Kiểm phản ví dụ 13 hóa đơn; không dùng lại nhiễu doanh thu mới cho collection |
| Owner draw | Cập nhật sổ 91 ngày, rút đúng ngày cuối quý | Hai ca F000/F003 trước đây bỏ sót thiếu tiền khớp truth khi dùng raw flow oracle |
| Phí | Tách AR-applied, tiền bank net và phí | AR đóng hết khi paid; phí không để lại dư nhỏ hoặc bị trừ hai lần |
| Phạm vi bank | Có financing, internal transfer, cash deposit, external và unclassified | Scenario lấy block lịch sử biết tại cutoff; không gọi các khoản này là doanh thu |
| T4 và kernel | Tuần Thứ Ba–Thứ Hai, dùng thu từng phần của cohort đã đủ follow-up | Không đưa hóa đơn ngày cutoff vào doanh thu tương lai lần nữa |
| T5 | Lịch sử chi định kỳ; supplier/capex theo block; override có `known_at` | Không đọc undated future actuals; tổng category/day được biết thay phần lấy mẫu tương ứng |
| Calibration | Ba dải tuần với guard tiền và Brier | Giữ một joint classifier; không thêm head/T2 hoặc class weighting |
| Batch/RAM | Dựng feature từng batch trước predict; lấy mẫu RSS | Đã bỏ ma trận feature toàn bước trước khi chia batch |
| Mốc thời gian | Kiểm ngày đóng nhãn baseline, follow-up nguồn và ngày forecast | Không chọn nguồn ở thời điểm trước khi baseline có thể được fit |

**57 kiểm thử đã qua**, gồm các sửa trên, hồi quy v1/v5/v6/T6, rollout rỗng,
receipt history rỗng, bảo toàn tiền và thay dữ liệu sau cutoff. Test rỗng ở
mức rollout không đồng nghĩa đã nghiệm thu mọi luồng tích hợp sản phẩm.

Trong hồi quy oracle F003, số dư cuối tuần trước đây bị tính thành +1,4779
tỷ, nay khớp **−0,5383 tỷ VND**; F000 khớp **−0,3615 tỷ**. Bridge phí và
ledger đầy đủ khớp trong các ca kiểm này. Đây là kiểm thuật toán với raw
flow thật được biết để chẩn đoán, không phải độ chính xác dự báo.
Nguồn: [accounting_regression.json](../../outputs/data/unified_collection_v2_20261104_r3/accounting_regression.json).

**2. Learning curve và lựa chọn trên nguồn.**

Ba ngân sách dùng cùng 160 vòng, cùng 128 công ty fit của v6 và các quota
anchor lồng nhau, không chọn theo outcome. Không thêm công ty vào fit.

| Anchor | Hàng chuyển tiếp | AR CRPS nguồn | So v6 nguồn | Thời gian fit gốc | RSS đỉnh lấy mẫu |
|---:|---:|---:|---:|---:|---:|
| 20.000 | 148.338 | 0,053136 | Xấu hơn 1,92% | 37,3 s | 695 MiB |
| 50.000 | 370.887 | 0,051678 | Tốt hơn 0,88% | 82,0 s | 782 MiB |
| 200.000 | 1.497.862 | 0,052251 | Xấu hơn 0,22% | 289,4 s | 1.803 MiB |

V6 nguồn là 0,052137. Các hàng có phụ thuộc theo hóa đơn, origin, khách và
công ty; số hàng không phải số quan sát độc lập. Thời gian fit ở bảng là
lần tạo weights tại r2; r3 tái sử dụng chính weights đó theo hash.

Chọn **50.000 anchor, rho công ty/khách 0,15/0,15**. Hai lựa chọn rho 0/0 và
0,30/0,15 có AR CRPS lần lượt 0,054127 và 0,051733. Mỗi case nguồn pool hai
seed, 250 đường/seed. Cải thiện 0,88% chỉ là điểm chọn cấu hình trên nguồn,
không phải kết quả test hoặc chứng minh đạt mức cải thiện nghiên cứu 5%.

Các tham số fit/calibration-fit dùng dữ liệu kết thúc trước 02/10/2023.
V6 đóng nhãn train tại 01/07/2024. Vì vậy r3 chọn trên các công ty
calibration-select riêng tại **01/07 và 07/10/2024**, với follow-up kết thúc
06/01/2025. Các lựa chọn đều có thể biết trước forecast test đầu tiên.
T4 chỉ fit trên công ty source-fit đến 06/01/2025; không dùng T4 cho việc
chọn AR ở các origin nguồn trước ngày đó.

Replay chuỗi lớp thật trên tập nguồn mới cho WAPE thu khoảng **0,263%** ở
model được chọn. Vì chưa có bằng chứng phần rời rạc hóa này là nguyên nhân
chính, giữ đại diện/lớp, không tăng lớp hoặc thêm sampler phức tạp để kéo
điểm. Đây là phép đo discretization, không được trừ trực tiếp vào CRPS.

Residual cùng không thu chỉ tính trên invoice-week đang mở. Tương quan
lag một tuần của residual trung bình theo công ty nằm khoảng −0,059 đến
+0,044 trên bốn World nguồn, mỗi World 96 cặp tuần liền kề. Đây là thống kê
mô tả, chưa chứng minh không có shock kéo dài ngoài nguồn. Không tự thêm
factor AR(1) làm thay đổi xác suất có điều kiện đã học.

Nguồn: [learning curve](../../outputs/analysis/unified_collection_v2_20261104/learning_curve_summary.csv),
[selection](../../outputs/data/unified_collection_v2_20261104_r3/selection.json),
[calibration](../../outputs/analysis/unified_collection_v2_20261104/calibration_summary.csv),
[serial residual](../../outputs/data/unified_collection_v2_20261104_r3/source_serial_dependence.csv).

**3. Kiểm chứng trên bốn World mới.**

Seed 106110501–106110504, tám công ty/World, tổng 32 công ty. Origin test là
**06/01 và 07/07/2025**. Origin tháng 7 có cuối quý nằm trong tuần để kiểm
cash sau draw. Mỗi case chạy ba seed MC 101/211/307, mỗi seed 1.000 đường;
pool 3.000 đường để chấm, giữ điểm từng seed. Có 64 cặp công ty–origin,
128 hàng công ty–origin–model, 384 hàng MC và 1.664 dự báo tuần.

Bank CRPS chia thang chi forecast tuần biết tại cutoff. AR CRPS chấm 13
phân phối thu AR-applied tích lũy, chia tổng dư origin. Hai scale khác nhau;
không so trực tiếp trị số AR với bank CRPS. Brier 4/13 chấm việc có ít nhất
một **số dư cuối tuần** âm, không phải mọi thời điểm trong ngày.

| World | Bank CRPS v6 → unified | Xấu hơn | Coverage v6 → unified | Brier 13 tuần v6 → unified |
|---|---:|---:|---:|---:|
| 000 | 3,110382 → 3,136915 | 0,85% | 69,23% → 68,27% | 0,005889 → 0,005521 |
| 001 | 1,880395 → 1,910125 | 1,58% | 85,58% → 81,73% | 0,089275 → 0,086115 |
| 002 | 3,344504 → 3,514484 | 5,08% | 65,87% → 61,54% | 0,117671 → 0,117578 |
| 003 | 1,421859 → 1,459812 | 2,67% | 88,46% → 85,58% | 0,202476 → 0,198385 |

Cả bốn World không đạt CRPS giảm 5%. Coverage World 000/002 dưới 70%.
Brier 13 tuần tốt hơn ở cả bốn World, nhưng Brier 4 tuần World 000 xấu hơn
dung sai: khoảng 0,001191 → 0,001276. Interval score World 001/002 cũng
xấu hơn ngưỡng 2%. Chênh bank CRPS giữ dấu xấu hơn trong cả ba seed MC ở
mỗi World; đây không chỉ là một lần chọn seed thuận lợi/bất lợi.

| World | AR CRPS v6 → unified | Thay đổi chất lượng |
|---|---:|---|
| 000 | 0,052908 → 0,051342 | Tốt hơn 2,96% |
| 001 | 0,054775 → 0,058256 | Xấu hơn 6,35% |
| 002 | 0,072005 → 0,092848 | Xấu hơn 28,95% |
| 003 | 0,041019 → 0,044215 | Xấu hơn 7,79% |

AR chưa tốt nhất quán sau khi sửa adapter. Không còn đủ cơ sở giải thích
kết quả xấu chỉ bằng các lỗi nối T6 của v1. Với World 002, CI bootstrap theo
tám công ty cho chênh AR CRPS unified − v6 là **[0,01083; 0,03132]**, nghiêng
về xấu hơn. CI ba World còn lại cắt 0. Các CI chỉ đo công ty trong World,
không đại diện bất định giữa các nền kinh tế hoặc dữ liệu SME thật.

Ở 48 công ty–tuần có shock theo lịch của World 001: interval score v6 →
unified là 9,6579 → 9,8086; coverage 89,58% → 85,42%. Nhóm 20% khách có dư
origin lớn nhất có WAPE thu tuần tốt hơn ở World 000, xấu hơn ở ba World
còn lại. Không có kết luận thắng riêng ở shock/khách lớn để bù tiêu chí chính.

Nguồn: [bank summary](../../outputs/data/unified_collection_v2_20261104_r3/fresh_test/summary.csv),
[AR summary](../../outputs/data/unified_collection_v2_20261104_r3/fresh_test/ar_summary.csv),
[điểm công ty](../../outputs/data/unified_collection_v2_20261104_r3/fresh_test/company_scores.csv),
[từng MC seed](../../outputs/data/unified_collection_v2_20261104_r3/fresh_test/mc_scores.csv),
[AR bootstrap](../../outputs/analysis/unified_collection_v2_20261104/ar_company_bootstrap.csv),
[shock slices](../../outputs/analysis/unified_collection_v2_20261104/fresh_test_shock_slices.csv).

**4. Hiệu năng, kế toán và bảo toàn phiên bản.**

Benchmark collection 1.000 đường × 2.000 hóa đơn × 13 tuần mất **14,55 / 14,89 /
14,51 giây**. RSS tăng được lấy mẫu tối đa **187,27 MiB**, RSS tổng cao nhất
khoảng 605 MiB. Batch feature tối đa 20.000 hàng. Cả latency 120 giây và
RSS tăng 2.000 MiB đều qua. Đây là collection rollout, không gồm đọc World,
T4/T5 hoặc bộ máy bank; RSS lấy mẫu 50 ms không phải cận cứng của peak.

Trong test, thời gian lớn nhất cho một MC replicate của cặp comparator,
gồm dựng context và tính bank, khoảng 4,92 giây ở cohort có tối đa 427
hóa đơn. Phép đo này bắt đầu sau khi đã đọc dữ liệu và dựng PMF v6, không
phải latency toàn bộ dịch vụ. Không dùng nó làm cam kết sản phẩm.

Sai lệch identity bank lớn nhất là **3,06 × 10⁻⁵ VND**; identity AR là
**1,28 × 10⁻⁷ VND**, đều dưới 1 VND. Không có outcome ngoài vocabulary
trong các hàng test đã chấm. Model vẫn chưa học credit-only vì không có
nhãn hỗ trợ, dù code kế toán có trạng thái này.

**540 file được bảo vệ không đổi**, gồm các phiên bản cũ và artifact phát
triển r1/r2; source r3 đã khóa không đổi. Kiểm đủ cohort, không trùng/mất
tuần và manifest các World mới. Không ghi đè dữ liệu/model v1/v4/v5/v6.
Nguồn: [latency](../../outputs/data/unified_collection_v2_20261104_r3/latency.json),
[verification](../../outputs/data/unified_collection_v2_20261104_r3/verification.json),
[kiểm cohort](../../outputs/analysis/unified_collection_v2_20261104/verification.json).

R1 được giữ trước sửa override `known_at`; r2 giữ kết quả train và các chẩn
đoán hồi cứu ở origin nguồn trước ngày đóng nhãn v6. Không coi cổng nguồn
r2 là bằng chứng forward-valid. R3 giữ nguyên weights theo hash, sửa mốc
lựa chọn và khóa lại trước khi tạo bốn World test. Không hạ ngưỡng để ép qua.

**5. Phần đã sửa và phần còn hạn chế.**

Các lỗi thực thi chính đã được sửa và kiểm chứng. Learning curve, band
calibration, AR distribution score, dependence diagnostic, MC replicates
và memory measurement đã có. Những phần đó giúp có phép thử rõ hơn; chúng
chưa làm mô hình thu tiền mới tốt hơn đối chứng trên tập cuối.

V2 vẫn dùng đại diện hữu hạn trong lớp; bối cảnh khách/công ty giữ ở origin;
không mô hình hóa latent shock kéo dài. Scenario phi AR và phân bổ ngày
dựa history, T4 vẫn chỉ ba quantile; draw cap có trường hợp chưa định danh.
Override `known_at` đang hiểu số tổng category/day là đầy đủ cho ngày đó;
ledger chỉ công bố một phần nghĩa vụ cần contract tách phần known/new.
Chưa nghiệm thu API ứng dụng, onboarding ngắn lịch sử hoặc ledger SME thật.

Đóng lần thử với kết luận **chưa thay v6**. Không thêm head/T2 hoặc chỉnh
lại mô hình theo bốn World đã xem. Mọi nghiên cứu sau phải coi chúng là
diagnostic và khóa protocol/test mới trước thử xác nhận tiếp theo.

**Tái lập.**

```powershell
.\.venv\Scripts\python.exe -B -m pytest tests/test_unified_collection_v2.py tests/test_unified_collection_core.py tests/test_unified_collection_artifacts.py tests/test_t1_competing_v6.py tests/test_t1_competing_v5.py tests/test_t6.py tests/test_cash_context.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -B -m experiments.unified_collection_v2.run --stage saved
.\.venv\Scripts\python.exe -B -m analysis.summarize_unified_collection_v2
```

Runner đọc artifact đã lưu và kiểm hash cùng snapshot mã của lần đo;
không yêu cầu bản mã hiện tại trùng snapshot cũ sau lần dọn được ghi nhận,
không ghi đè hash lịch sử và không tạo lại điểm test.
R3 cần các cache/weights nguồn r2 đã giữ, được kiểm hash và ghi rõ đường tái
sử dụng trong protocol/metadata. Script analysis chỉ đọc điểm đã lưu.
