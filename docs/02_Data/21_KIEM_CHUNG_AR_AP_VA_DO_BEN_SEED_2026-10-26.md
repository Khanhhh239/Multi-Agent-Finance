# Kiểm chứng AR/AP Việt Nam và độ bền seed của cohort ứng viên (26/10/2026)

**Cập nhật 27/10/2026:** báo cáo này mô tả các cohort đến `r3`, trước khi
thêm `supplier_due_date` và khóa cohort `r5`. Bản ứng viên sau sửa ở
[báo cáo 22](22_COHORT_SYNTHETIC_DA_KHOA_2026-10-27.md); bộ train synthetic cuối
và kết luận kỹ thuật mới nhất ở [báo cáo 23](23_BO_TRAIN_SYNTHETIC_CUOI_2026-10-27.md).
Kết luận thiếu dữ liệu SME thật để đối chiếu độc lập vẫn giữ nguyên.

## Phạm vi và cách đo

Chỉ đọc ba World train/validation của mỗi cohort `v3_candidate_20261026`,
`v3_candidate_r2_20261026` và `v3_candidate_r3_20261026`, các World đối chứng
10 seed trên từng mã và các World phản thực 94319/validation. **Không đọc kết
cục hóa đơn của các World test**. Mã
`scripts/audit_candidate_release_gates.py` kiểm manifest rồi xuất doanh thu theo
doanh nghiệp/năm/tháng, nhân tố chung, công nợ nhà cung cấp và snapshot AR/AP cuối
2025 vào `outputs/data/release_gate_audit_20261026/`.

AR cuối 2025 là `remaining_amount` của hóa đơn, AR quá hạn là phần còn mở có
`due_date < 31/12/2025`. AP nhà cung cấp cuối 2025 là tổng `purchase_gross` của
các giao dịch có `purchase_date <= 31/12/2025 < supplier_pay_date` trong
`inventory_weekly.parquet`. Chỉ số AP này **không** gồm lương, thuế, vay, hay
chi phí tiện ích; cũng không có kỳ hạn hợp đồng nhà cung cấp để tính AP quá hạn.

## Nguồn đối chiếu Việt Nam độc lập

| Nguồn | Chỉ số có thể dùng | Giới hạn so sánh |
|---|---|---|
| [UNU-WIDER/CIEM SME survey](https://www.wider.unu.edu/database/viet-nam-sme-database) và [nghiên cứu dùng khảo sát này](https://onlinelibrary.wiley.com/doi/full/10.1111/rode.13147) | AP là số dư còn nợ mọi nhà cung cấp; tỷ lệ doanh nghiệp AP dương khoảng 54–60% trong 2009/2011/2013; mẫu 7.311 doanh nghiệp-năm ngành sản xuất. | Vi dữ liệu phải điền biểu mẫu để truy cập; năm cũ, gồm nhiều hộ kinh doanh, không cùng ngày chốt hoặc cơ cấu doanh nghiệp với cohort 2025. Không dùng mức VND danh nghĩa cũ làm mục tiêu 2025. |
| [Funding Societies SME survey 2023](https://blog.fundingsocieties.com/payables-an-increasingly-critical-issue-for-apac-smes-in-2023/) | 10% doanh nghiệp Việt Nam được khảo sát nói có điều khoản mua chịu từ nhà cung cấp. | Khảo sát toàn vùng khoảng 977 doanh nghiệp, 74% siêu nhỏ và 59% là khách hàng của hãng; không công bố ở đây số mẫu Việt Nam theo ngành. Quyền mua chịu không đồng nghĩa AP dương tại một ngày chốt. |
| [World Bank Enterprise Survey Việt Nam 2023](https://www.enterprisesurveys.org/content/dam/enterprisesurveys/documents/country/Viet-Nam-2023.pdf) | 31,4% doanh nghiệp nhỏ và 42,2% doanh nghiệp vừa dùng tín dụng nhà cung cấp/**khách hàng** để tài trợ vốn lưu động. | Chỉ số gộp hai loại tín dụng và không phải số dư AP, nên chỉ dùng tam giác kiểm tra. |
| [CPA Australia Small Business Survey 2025–26, Việt Nam](https://www.cpaaustralia.com.au/-/media/project/cpa/corporate/documents/tools-and-resources/business-management/small-business-survey/2025-2026-market-summaries/vietnam---full-summary.pdf?rev=1bd95425ca94471d8f649d4465001607) | 84,5% doanh nghiệp nhỏ được hỏi báo hoạt động đã tăng trưởng trong 12 tháng của 2025. | Mẫu doanh nghiệp dưới 20 lao động, trả lời khảo sát về tăng trưởng chung; không đồng nhất với doanh thu thuần hóa đơn theo năm. Dùng để kiểm hướng vĩ mô, không làm mục tiêu AR/AP. |
| [Atradius Việt Nam 2025](https://group.atradius.com/dam/jcr%3Ac118f442-fed0-4104-a74a-bce847d3c2e4/payment-practices-barometer-asia-2025-vietnam-en.pdf) | 65% doanh số B2B bán chịu, kỳ hạn bình quân 45 ngày, 39% giá trị hóa đơn báo quá hạn. | Nguồn này đã được dùng làm neo tham số máy phát, nên **không độc lập**. Tỷ lệ báo quá hạn cũng không cùng mẫu số/cửa sổ với `AR quá hạn / AR còn mở` của audit. |

[Allianz Trade](https://www.allianz-trade.com/en_global/economic-research/collection-complexity/vietnam.html)
ghi nhận chưa có số liệu DSO Việt Nam chính thức, bao quát. Tìm kiếm công khai
trong lượt này chưa thu được ledger hóa đơn và thanh toán của SME Việt Nam kèm
ngành, quy mô, ngày phát hành, hạn, ngày thu/chi và ngày chốt đủ để kiểm định
**phân phối AR/AP cùng định nghĩa**.
Người dùng xác nhận hiện không có ledger AR/AP SME Việt Nam đã ẩn danh để bổ
sung cho lượt kiểm chứng này.

## Kết quả AR/AP trên cohort ứng viên

| World | AR mở cuối 2025 | AR quá hạn / AR mở | AP nhà cung cấp cuối 2025 | AP cuối kỳ / mua trong 2025 | Lag mua đến trả bình quân theo giá trị |
|---|---:|---:|---:|---:|---:|
| train_000 | 250,1 tỷ VND | 33,4% | 191,2 tỷ VND | 12,9% | 41,6 ngày |
| train_001 | 409,0 tỷ VND | 65,4% | 150,9 tỷ VND | 6,8% | 39,5 ngày |
| validation_000 | 358,8 tỷ VND | 40,5% | 214,1 tỷ VND | 12,7% | 43,8 ngày |

Cả **72/72 doanh nghiệp**, gồm **48/48 doanh nghiệp ở bốn ngành sản xuất**, có
AP dương cuối 2025. Chỉ 19/72 doanh nghiệp ứng viên có tối đa 10 lao động,
trong khi mẫu Funding Societies có 74% siêu nhỏ. Vì khác cơ cấu, năm và
định nghĩa, các khảo sát trên **không cho phép tính sai số đại diện theo cohort**;
tuy nhiên AP dương phổ quát là dấu hiệu cơ chế cần kiểm lại. Mã máy phát chọn
kỳ hạn nhà cung cấp và lên ngày trả cho mỗi đợt mua, không mô hình hóa nhóm
doanh nghiệp không được mua chịu hay AP quá hạn/chi trả từng phần một cách có
thể kiểm chứng bằng dữ liệu đối chiếu.
Ngay cả khi kỳ hạn nền của doanh nghiệp rút bằng 0, mỗi lần mua vẫn có xác suất
40% nhận kỳ hạn 30 hoặc 45 ngày trong `World.outflows()`; máy phát hiện chưa
có nhóm doanh nghiệp chỉ trả nhà cung cấp ngay khi mua. Đây là lý do cấu trúc
để kiểm lại, không phải cơ sở để áp tỷ lệ 10% của một mẫu khác vào code.

Ở `train_001`, **34,3% giá trị hóa đơn đã tất toán trong 2025** trả trễ, trong
khi **65,4% số dư AR còn mở tại 31/12/2025** đã quá hạn; trong phần quá hạn,
69,4% giá trị trễ trên 60 ngày. Hai tỷ lệ đầu có mẫu số khác nhau. AR quá hạn
đã ở mức 71,2% cuối 2019, nên không thể quy riêng mức 2025 cho một cú sốc mới.
Ngành dệt may 81,2% và bán buôn 69,9% AR quá hạn cuối 2025, nhưng World chỉ có
4 và 6 doanh nghiệp ở hai ngành này. Không có benchmark SME cùng định nghĩa để
kết luận đạt/không đạt độ sát AR theo ngành.

## Seed 94319 và doanh thu cao của train_001

Audit theo doanh nghiệp cho thấy seed 94319 giảm doanh thu 2025/2024 xuống
0,395, **24/24 doanh nghiệp cùng giảm**; số hóa đơn từ 21.102 xuống 7.879,
tổng khách mua hàng theo doanh nghiệp từ 1.194 xuống 889. Nhân tố chung trung
bình năm 2024 là +0,312 và năm 2025 là −1,114. `train_001` có doanh thu
2025/2019 bằng 2,668, **24/24 doanh nghiệp cùng tăng**; số hóa đơn từ 8.820
lên 23.123, tổng khách mua hàng theo doanh nghiệp từ 1.354 lên 1.607. Nhân tố
chung từ −0,655 (2019) lên +0,035 (2025). Các đồng biến này không tự chứng
minh nhân quả.

### Phát lại 10 seed bằng một bản mã

Đã phát lại 10 seed 94317–94326, cùng cấu hình không có episode mới và cùng
hash toàn bộ mã Python `23e5d909abb4cb3ca1f713ac33c878178df7ca51b3a8a4954bcf998b8f4f11e9`.
Ba hash nguồn calibration/OxCGRT/WDI cũng giống nhau trong cả lô. **120/120
bảng Parquet (10 World × 12 bảng) khớp byte** với v5/v6 lịch sử theo đúng seed,
dù hai lô lịch sử ghi hash toàn bộ mã khác nhau. Như vậy đã kiểm được tính tái
lập **dữ liệu đã quan sát** qua các phiên bản đó; không suy rằng mọi đường chạy
hay thay đổi tham số đều bất biến.

Trong 10 World cùng mã, tỷ số doanh thu 2025/2019 nằm trong **0,886–1,886**;
94319 vẫn là trường hợp duy nhất giảm xuống khoảng **0,395** so với 2024.
AR quá hạn / AR mở cuối 2025 trong **33,2–59,1%**. Mười seed chỉ mô tả dải
quan sát, không đủ để ước lượng tần suất cú sốc hiếm hay xác nhận phân phối SME.
Bảng World × năm × ngành: [`same_code_seed_metrics.csv`](../../outputs/data/release_gate_audit_20261026/same_code_seed_metrics.csv);
đối chiếu SHA-256 từng bảng: [`replay_hash_comparison.csv`](../../outputs/data/release_gate_audit_20261026/replay_hash_comparison.csv);
hash mã/nguồn và danh sách World: [`seed_counterfactual_provenance.json`](../../outputs/data/release_gate_audit_20261026/seed_counterfactual_provenance.json).

`scripts/run_release_seed_counterfactual.py` phát lại seed 94319 bằng mã hiện
tại, rồi tạo phản thực chỉ cộng hằng số +1,114 vào `common_factor` của năm
2025, giữ nguyên đường 2019–2024 và cùng seed/cấu trúc doanh nghiệp. Tỷ số
doanh thu 2025/2024 đổi từ **0,395 lên khoảng 0,908**; 19/24 doanh nghiệp vẫn
giảm nhẹ. Đây là **kiểm độ nhạy có can thiệp**, không phải ước lượng xác suất
cú sốc ngoài thị trường. Bảng doanh nghiệp của hai World khớp byte. Một vài
hóa đơn gần ranh giới năm trước can thiệp thay ngày ghi nhận; phần sai khác
doanh thu cấp World 2023/2024 khoảng 0,03–0,04%, cần sửa quy trình rút ngày
hóa đơn trước khi dùng phản thực làm chứng cứ nhân quả chặt.

### Sửa phát hành ngày hóa đơn

Test hồi quy mới thay số đơn hàng chỉ trong 2025 nhưng yêu cầu hóa đơn phát
hành trước 2025 giống hệt. Test **thất bại trước sửa** vì một lượt rút ngẫu
nhiên sau khi gộp hóa đơn của cả cửa sổ có thể chuyển ngày lập hóa đơn cũ.
Máy phát hiện sắp hóa đơn theo ngày trước lượt rút này và dùng RNG riêng theo
seed/doanh nghiệp; runner cohort dùng `rng_version=2` để giữ cấu trúc doanh
nghiệp khi làm phản thực. Test vừa nêu qua sau sửa; 20 test về causality và
pipeline đều qua. Đây là **bản mã mới**, nên các World trước sửa không được
gộp làm một lô phát hành với bản sau sửa.

### Cohort ứng viên sau sửa và phản thực validation

Đã sinh `v3_candidate_r2_20261026` với cùng seed 97100–97105 và lịch shock như
cohort trước, nhưng `rng_version=2` và mã rút ngày hóa đơn mới. Hash toàn bộ mã
Python của cả sáu World là
`e3d8843fc8794cdd50b92f423078544f3e5db00a22a08c2cf26cde15c35baa05`.
Runner dừng ở `audit_worlds`: **chưa khóa split, chưa train, chưa đọc kết cục
test**. [Readiness](../../outputs/data/v3_candidate_r2_20261026/readiness.json)
PASS với cửa sổ 2019–2025, nguồn vĩ mô và held-out hợp lệ; 72/72 Parquet khớp
manifest. Kiểm lại ba World train/validation cho 147 dòng World × năm × ngành,
không thấy tỷ lệ ngoài miền hoặc phân vị đảo thứ tự. Bảng chi tiết:
[`yearly_industry_metrics.csv`](../../outputs/data/release_gate_audit_20261026/r2/yearly_industry_metrics.csv).

| World | Doanh thu 2025/2019 | Bán chịu 2025 | AR quá hạn / AR mở cuối 2025 | AP nhà cung cấp cuối 2025 | Doanh nghiệp AP dương |
|---|---:|---:|---:|---:|---:|
| train_000 | 1,12 | 64,8% | 41,7% | 262,6 tỷ VND | 24/24 |
| train_001 | 1,47 | 64,5% | 40,3% | 416,0 tỷ VND | 24/24 |
| validation_000 | 0,85 | 58,9% | 63,4% | 76,6 tỷ VND | 22/24 |

AP dương ở **70/72** doanh nghiệp, gồm **47/49** doanh nghiệp thuộc bốn ngành
sản xuất. Vấn đề AP phổ quát vẫn còn. Cảnh báo AR cao không còn ở `train_001`
nhưng xuất hiện ở validation. Trong validation, doanh thu 2025/2024 là 0,629,
23/24 doanh nghiệp giảm và nhân tố chung 2025 trung bình −0,932. Vì vậy PASS
của readiness kỹ thuật không được xem là PASS độ sát phân phối.
Trong 35 doanh nghiệp ứng viên dưới 20 lao động, chỉ **11/35** có doanh thu
thuần 2025 cao hơn 2024. Đây là cảnh báo khi đặt cạnh tỷ lệ tăng trưởng tự báo
của khảo sát CPA, có giới hạn định nghĩa và mẫu như bảng nguồn trên. Ba World
chia sẻ nhân tố vĩ mô trong từng World; không xem 35 doanh nghiệp là 35 seed
độc lập để tính xác suất hay mức ý nghĩa thống kê.

Đã sinh một World nghiên cứu từ chính config validation r2, chỉ cộng +0,932
vào nhân tố chung năm 2025 để trung bình năm bằng 0. Tỷ số doanh thu
2025/2024 đổi **0,629 → 1,240**, số doanh nghiệp giảm **23/24 → 7/24**,
AR quá hạn / AR mở đổi **63,4% → 35,7%**. Bảng `firms.parquet`, hash toàn bộ mã
và **144/144 doanh nghiệp-năm 2019–2024** khớp giữa hai World. Phép thử này
cho thấy cảnh báo doanh thu/AR nhạy mạnh với `common_factor`; nó không chứng
minh phân phối nhân tố chung hoặc mức AR nào là đại diện cho SME Việt Nam.
Chi tiết:
[`validation_counterfactual/firm_year.csv`](../../outputs/data/release_gate_audit_20261026/r2/validation_counterfactual/firm_year.csv)
và
[`firm_2025_ar_ap.csv`](../../outputs/data/release_gate_audit_20261026/r2/validation_counterfactual/firm_2025_ar_ap.csv).

### Mười seed đối chứng trên đúng bản mã r2

Đã sinh và kiểm manifest 10 World không có episode mới, seed 94317–94326,
`rng_version=2`, cùng hash mã
`e3d8843fc8794cdd50b92f423078544f3e5db00a22a08c2cf26cde15c35baa05`
và cùng ba hash nguồn đầu vào với cohort ứng viên r2. Cả **120/120 bảng
Parquet** qua kiểm SHA-256 và kiểm cấu trúc theo manifest. Kết quả cấp World
trong [`world_summary.csv`](../../outputs/data/release_gate_audit_20261026/r2_controls/world_summary.csv),
nguồn gốc trong [`provenance.json`](../../outputs/data/release_gate_audit_20261026/r2_controls/provenance.json).

| Chỉ số trên 10 World | Kết quả |
|---|---:|
| Doanh thu 2025/2019 | 0,886–1,886 |
| Doanh thu 2025/2024 | 0,395–1,160 |
| AR quá hạn / AR mở cuối 2025 | 31,2–60,7% |
| Doanh nghiệp còn AP nhà cung cấp cuối 2025 | 237/240 |
| Doanh nghiệp bốn ngành sản xuất còn AP | 166/167 |
| Doanh nghiệp dưới 20 lao động tăng doanh thu thuần 2025/2024 | 54/116 |

Các doanh nghiệp trong cùng World chia sẻ đường vĩ mô, vì vậy 240 doanh nghiệp
không phải 240 phép rút seed độc lập. AP dương gần như phổ quát trên lô đối
chứng xác nhận cảnh báo cấu trúc đã thấy trong cohort ứng viên. So sánh 54/116
với khảo sát CPA 84,5% chỉ là cảnh báo hướng tăng trưởng; hai chỉ số khác định
nghĩa và cơ cấu mẫu.

Seed **94319** vẫn có nhân tố chung 2025 trung bình **−1,114**, doanh thu
2025/2024 **0,395**, **24/24** doanh nghiệp giảm và AR quá hạn/AR mở **55,0%**.
Đã sinh phản thực r2 đưa trung bình nhân tố chung 2025 về 0, giữ cùng seed,
config còn lại và mã. Doanh thu 2025/2024 thành **0,908**, số doanh nghiệp
giảm còn **19/24**; AR quá hạn/AR mở thành **43,7%**. Hash `firms.parquet`,
**144/144 dòng doanh nghiệp-năm 2019–2024** và **75.598/75.598 hóa đơn phát
hành trước 2025 xét theo bộ trường cốt lõi** khớp dưới dạng tập có lặp. Chi
tiết trong [`paired_check.json`](../../outputs/data/release_gate_audit_20261026/r2_controls/seed94319_counterfactual/paired_check.json).

Phản thực này **chưa phải phép đo nhân quả sạch cho AR**: trong hóa đơn phát
hành trước 2025, số credit note ghi ngày trước 2025 khác nhau giữa hai World
(720, tổng 16,4 tỷ VND; so với 702, tổng 18,7 tỷ VND). Bộ rút ngẫu nhiên
của `World.settle()` còn phụ thuộc tổng số hóa đơn cả cửa sổ. Sửa ngày phát
hành đã giữ nguyên lịch và giá trị hóa đơn quá khứ, nhưng chưa cô lập mọi
biến cố thanh toán/điều chỉnh quá khứ khỏi thay đổi lượng hóa đơn tương lai.
Vì vậy không quy toàn bộ chênh lệch AR 55,0% → 43,7% cho nhân tố chung; đây
là một lỗi nhân quả còn phải sửa và chạy lại kiểm định trên mã mới nếu muốn
chốt máy phát.

### Sửa tiếp RNG thanh toán và kiểm lại seed 94319

Đã tách từng lượt rút thuộc tính trong `World.settle()` thành luồng riêng theo
seed/doanh nghiệp/vị trí lượt rút, gắn `rng_version=3`, đồng thời giữ cách tách
luồng theo doanh nghiệp của v2. Test hồi quy thêm hóa đơn tương lai nhưng đòi
credit note cũ bất biến qua; test tích hợp giữ luồng phát hành v2 cũng qua.
**22/22 test** causality và pipeline qua. Đây là
thay đổi máy phát thực sự, nên cohort r2 ở trên vẫn là ứng viên nghiên cứu,
không phải lô phát hành của mã v3.

Trên cặp World nghiên cứu `v3_releasecheck_r3b_94319_base` và
`..._neutral2025`, cùng hash mã
`e9e249d388b2a790fa0dd0f36590955b8de6a91e3594f1dbf6815750e3bdf274`,
**144/144 dòng doanh nghiệp-năm trước 2025** khớp; **75.598 hóa đơn phát hành
trước 2025** khớp toàn bộ trường phát hành, kỳ hạn, giá trị và credit note khi
so theo tập có lặp. Số credit note trước 2025 đều là **710**. Mức can thiệp
chỉ cộng **+1,114** vào nhân tố chung 2025 để trung bình năm bằng 0.

| Seed 94319 trên mã v3 | Nền | Trung hòa nhân tố chung 2025 |
|---|---:|---:|
| Doanh thu 2025/2024 | 0,395 | 0,908 |
| Doanh nghiệp giảm doanh thu | 24/24 | 19/24 |
| AR quá hạn / AR mở cuối 2025 | 54,4% | 41,0% |

[`paired_check.json`](../../outputs/data/release_gate_audit_20261026/r3b_seed94319/paired_check.json)
lưu kiểm tra cặp. Kết quả củng cố giải thích rằng nhân tố chung 2025 đóng góp
lớn cho cú giảm doanh thu của 94319. Nó vẫn không xác nhận một năm tương tự có
xác suất hợp lý trên SME Việt Nam; điều đó cần đối chiếu ngoài mô hình.

Đã kiểm thêm **10 World đối chứng** seed 94317–94326 trên đúng hash mã v3 này,
không có episode mới. Cả **120/120 bảng Parquet** qua kiểm SHA-256 và cấu trúc
theo manifest; seed 94319 chạy lại độc lập khớp byte **12/12 bảng Parquet**
với World nền phản thực. Doanh thu 2025/2019 nằm trong **0,886–1,886**; doanh thu
2025/2024 trong **0,395–1,160**. AR quá hạn/AR mở cuối 2025 trong
**33,2–59,9%**. AP dương ở **237/240** doanh nghiệp, gồm **166/167** doanh
nghiệp trong bốn ngành sản xuất; trong 116 doanh nghiệp dưới 20 lao động,
**54/116** tăng doanh thu thuần 2025/2024. Bảng từng seed:
[`world_summary.csv`](../../outputs/data/release_gate_audit_20261026/r3b_controls/world_summary.csv);
hash mã/nguồn: [`provenance.json`](../../outputs/data/release_gate_audit_20261026/r3b_controls/provenance.json).
Mười World độc lập theo seed cho thấy vấn đề AP tồn tại bền qua seed và 94319
vẫn ở đuôi bất lợi, nhưng chưa ước lượng được tần suất biến cố hiếm hay độ sát
phân phối ngoài đời.

### Cohort ứng viên mới trên đúng mã v3

Đã sinh `v3_candidate_r3_20261026`: một World smoke, hai train, một validation
và hai test. Cùng seed/lịch shock của cohort r2 nhưng dùng `rng_version=3` và
hash mã v3 ở trên. **72/72 bảng Parquet** khớp manifest; ba hash nguồn chung;
[readiness kỹ thuật](../../outputs/data/v3_candidate_r3_20261026/readiness.json)
PASS cho cửa sổ, nguồn vĩ mô và held-out. **Chưa khóa split, chưa train, chưa
đọc kết cục hóa đơn của test**. Danh sách World/hash trong
[`provenance.json`](../../outputs/data/release_gate_audit_20261026/r3b_candidate/provenance.json).

| World | Doanh thu 2025/2019 | Doanh thu 2025/2024 | AR quá hạn / AR mở cuối 2025 | AP dương |
|---|---:|---:|---:|---:|
| train_000 | 1,124 | 1,062 | 42,9% | 24/24 |
| train_001 | 1,468 | 1,054 | 39,9% | 24/24 |
| validation_000 | 0,853 | 0,629 | 56,3% | 22/24 |

Chi tiết: [`world_summary.csv`](../../outputs/data/release_gate_audit_20261026/r3b_candidate/world_summary.csv).
Hai mức 2,668 và 65,4% của `train_001` cũ không còn ở ứng viên mã v3.
Validation vẫn có **23/24 doanh nghiệp giảm doanh thu 2025/2024** với nhân tố
chung năm 2025 trung bình **−0,932**. AP dương ở **70/72** doanh nghiệp ứng
viên; cảnh báo cơ chế AP vẫn còn.

## Quyết định

**GO kỹ thuật cho tính tái lập, kiểm manifest và hai sửa lỗi nhân quả đã thử;
NO-GO cho bộ train cuối.** Đã kiểm 10 seed trên mã v3 và sinh lại cohort ứng
viên cùng mã; seed 94319 được giải thích một phần bằng phép can thiệp vĩ mô
có đối chứng quá khứ ổn định. Tuy nhiên 10 seed không xác định tần suất cú sốc
ngoài thị trường, validation còn giảm mạnh, AP dương gần phổ quát và chưa có
ledger AR/AP SME Việt Nam cùng định nghĩa. Người dùng xác nhận không có ledger
đối chiếu ở lượt này, nên cổng độ sát AR/AP không thể đóng bằng các nguồn
hiện có. Không thay tham số chỉ để ép một chỉ số tổng hợp về mức của khảo sát
khác mẫu. Giữ cohort r3 làm **ứng viên**, chưa khóa split/training; cần đối
chiếu AR/AP phù hợp và đánh giá tính hợp lý của đuôi vĩ mô trước khi gọi là
train cuối.

Để đóng cổng đối chiếu, cần mẫu doanh nghiệp Việt Nam có ngành, quy mô lao động,
ngày chốt và trọng số chọn mẫu; ledger bán hàng và mua hàng có ngày phát hành,
ngày đến hạn, số tiền, các khoản thanh toán kèm ngày, credit note/điều chỉnh và
write-off. Khi có dữ liệu này, tính lại cùng một cửa sổ và cùng mẫu số cho từng
doanh nghiệp trước, rồi so phân phối theo quy mô/ngành và bootstrap theo
**doanh nghiệp**. Khảo sát chỉ công bố tỷ lệ tổng không thay thế được phép đối
chiếu này.
