# Kiểm toán sau sửa máy phát và quyết định về bộ train (26/10/2026)

> Đây là ảnh chụp kiểm toán **trước** đợt sửa vòng đời khách hàng và hai hard case cùng ngày. Kết quả tái sinh sau sửa nằm ở [báo cáo 15](15_SUA_VONG_DOI_KHACH_VA_HARD_CASE_2026-10-26.md). Các con số cũ bên dưới được giữ để so sánh, không phải trạng thái mới nhất.

**Kết luận: NO-GO cho bộ train cuối cùng.** Các bản sửa về thứ tự thời gian, đối soát tiền và kiểm duyệt đã qua kiểm thử; bốn kênh sốc mới có tác động đo được. Tuy nhiên một thế giới **không có episode mới** vẫn suy giảm doanh thu và số khách rất mạnh qua 2019–2025. Tôi đã tải OxCGRT/WDI công khai và sinh lại đối chứng: lỗi suy giảm vẫn còn. Các hệ số sốc chưa hiệu chỉnh bằng vi dữ liệu Việt Nam, và thiết kế test chưa giữ riêng một họ sốc. Khóa train trên dữ liệu này sẽ học một xu thế do máy phát tạo ra rồi gọi nhầm là thị trường. Cổng runner mới dừng trước `lock_split` khi bộ đủ 2019–2025 không qua kiểm tra nội bộ.

## Phạm vi và cách tái lập

- Kiểm trên working tree hiện tại; không sửa hoặc ghi đè `src`, `tgt`, `big_*` và các báo cáo lịch sử. Các thư mục cũ này chỉ có cấu hình/báo cáo, **không có Parquet giao dịch**, nên không thể xác nhận lại từng kịch bản cũ từ hóa đơn gốc. Kết quả bên dưới là **tái sinh theo mã hiện tại**, không phải kiểm chứng rằng bản cũ đã đúng.
- Hai thế giới đối chứng cùng seed `94317`, RNG v2, 24 doanh nghiệp, 1.374 khách, 01/01/2019–31/12/2025: `v3_audit_baseline_20261026` không có episode mới; `v3_audit_distribution_20261026` có đủ bốn episode mặc định. Cả hai có manifest SHA-256, 12 bảng bắt buộc, qua `validate_world`. File máy đọc được: `outputs/data/v3_readiness_20261026.json`; mã tính: `scripts/audit_train_readiness.py`.
- Sau phép thử đầu, chạy `scripts/crawl.py --only wdi_vn,oxcgrt` để tải World Bank WDI (396 dòng) và OxCGRT (43.837.034 byte) vào `data/raw`, có hash trong `MANIFEST.json`. Sinh đối chứng mới `v3_audit_public_macro_20261026` với cùng 24 công ty/seed; manifest của bộ mới ghi OxCGRT `fa5c95...e79` và WDI `ad14c8...c26`. Bộ trước vẫn giữ hash nguồn `null` và fallback, không viết lại. Kết quả mới: `outputs/data/v3_readiness_public_macro_20261026.json`.
- Nhóm 12 hard case v3 được sinh lại theo seed `901`, 12 doanh nghiệp/case và kiểm hợp đồng; `new_company` chỉ năm 2025. Có cả smoke một doanh nghiệp để bắt lỗi vận hành. File: `outputs/data/hard_cases_v3.csv`, `outputs/data/hard_case_fidelity_v3_full.csv`, `outputs/data/hard_case_fidelity_v3_smoke.csv`. Mỗi bộ full có manifest; `fx_rates.parquet` cũng được hash.
- Mốc bên ngoài: [Atradius Việt Nam 2025](https://group.atradius.com/dam/jcr:c118f442-fed0-4104-a74a-bce847d3c2e4/payment-practices-barometer-asia-2025-vietnam-en.pdf) là khảo sát 300 người trả lời ở **ba ngành** thép, dệt, nhựa, nửa cuối Q2/2025; không phải mẫu hóa đơn SME giao dịch. [NSO 2021](https://www.nso.gov.vn/en/data-and-statistics/2022/01/socio-economic-situation-in-the-fourth-quarter-and-2021/) và [NSO 2025](https://www.nso.gov.vn/en/data-and-statistics/2026/01/press-release-social-economic-situation-in-the-fourth-quarter-and-2025/) chỉ giúp kiểm dấu xu thế vĩ mô, không phải đích doanh thu cho 24 công ty giả lập.

Chạy lại báo cáo trên các thế giới đã hash:

```powershell
python scripts/audit_train_readiness.py data/synthetic/v3_audit_distribution_20261026 --control data/synthetic/v3_audit_baseline_20261026 --output outputs/data/v3_readiness_20261026.json
python scripts/audit_hard_case_fidelity.py --v3-full
```

## 1. Phân phối, nhiễu và tiền mặt

| Chỉ tiêu | V3 tích hợp | Đối chứng không episode | Mốc khảo sát 2025 | Diễn giải |
|---|---:|---:|---:|---|
| Hóa đơn | 34.490 | 36.924 | — | Cùng 24 công ty/seed; tác động sốc làm phát sinh ít hóa đơn hơn. |
| Doanh số bán chịu theo giá trị gốc | 73,46% | 73,89% | 65% | Lệch khoảng +8,5 điểm %, nhưng V3 gộp 2019–2025, khác cửa sổ và cơ cấu mẫu Atradius. Cần hiệu chỉnh theo ngành/năm; không ép mọi năm đúng 65%. |
| Đúng hạn / quá hạn / nợ xấu theo giá trị hóa đơn bán chịu **đã có kết cục** | 64,41 / 32,09 / 3,50% | 66,73 / 29,75 / 3,52% | 58 / 39 / 3% giá trị hóa đơn B2B | Dấu sốc đi đúng hướng tổng thể, nhưng mẫu số/cửa sổ không đồng nhất. Cột 2025 bị kiểm duyệt phải, không so tỷ lệ nợ xấu 2025 trực tiếp. |
| Kỳ hạn bán chịu bình quân theo giá trị | 42,37 ngày | 42,09 ngày | 45 ngày | Gần về cỡ số, không chứng minh phân phối kỳ hạn đúng. |
| Tỷ lệ ngày công ty có số dư **tài khoản vận hành** âm | 38,77% | 32,29% | Không có mốc cùng định nghĩa | Rất cao cho chính mẫu synthetic; không được gọi là tỷ lệ SME Việt Nam. |

Trong năm 2025, **20,61% giá trị hóa đơn bán chịu V3 còn bị kiểm duyệt** tại 31/12/2025. Chỉ tiêu `value_outcomes` bỏ những khoản này khỏi mẫu đã có kết cục; nợ xấu 2025 nhìn thấp một cách cơ học vì xóa nợ cần thêm thời gian. Cần báo riêng cohort đến hạn, số dư còn mở, số dư xóa nợ sau thu hồi và cửa sổ quan sát.

Nhiễu hiện có: nhân tố chung AR(1) với đổi mới Student-t, thanh khoản riêng khách, phân tán lognormal số tiền, lịch Tết, ngày chạy thanh toán, trả một phần, sai khác sao kê/sổ cái. **Chưa có mốc vi dữ liệu Việt Nam** để xác nhận tham số đuôi `atradius`/`uk`/`coface`, độ lệch lời hứa, phương sai trễ theo khách, phương sai số tiền, hoặc 38,77% ngày âm. `uk` và `coface` là phép thử độ nhạy, không phải phân phối ngày trả của Việt Nam.

### Lỗi cấu trúc mới phát hiện: mất khách và doanh thu dài hạn

| Thế giới | Hóa đơn 2019 → 2025 | Khách có hóa đơn 2019 → 2025 | Doanh thu hóa đơn thuần / `revenue_annual` 2019 → 2025 | Sự kiện khách vỡ nợ |
|---|---:|---:|---:|---:|
| V3 có episode | 8.681 → 4.003 | 732 → 298 | 0,701 → 0,266 | 894 |
| Đối chứng không episode | 9.799 → 3.982 | 752 → 312 | 0,793 → 0,255 | 886 |
| Thử `pd_mult=1` cùng seed, không episode | 10.043 → 6.630 | 763 → 463 | 0,807 → 0,437 | 476 |
| Đối chứng có OxCGRT/WDI công khai | 9.799 → 3.988 | 752 → 294 | 0,793 → 0,268 | 890 |

Ngay cả không có episode mới, doanh thu 2025/2019 còn **0,322** khi dùng fallback và **0,338** khi dùng OxCGRT/WDI thật, nên không thể đổ lỗi chính cho bốn kênh sốc hoặc nguồn macro vắng. `customer_paths` dùng `pd_mult` hiệu chỉnh cũ trong hazard vỡ nợ; `observed_credit_holds` chặn đơn sau sự kiện vỡ nợ, trong khi `make_customers` không sinh dòng khách thay thế đủ để giữ cơ sở kinh doanh. Thử hạ `pd_mult` về 1 làm suy giảm nhẹ hơn nhưng tỷ trọng nợ xấu còn **1,23%**, cách xa mốc khảo sát 3%. Vì vậy hạ hệ số đơn lẻ không giải quyết đồng thời mục tiêu nợ xấu và sự sống của khách. Cần tách mất nợ trên hóa đơn khỏi việc khách biến mất vĩnh viễn, có cơ chế thu hút/thay thế khách theo thời gian và hiệu chỉnh lại trên cohort. Sự sụt giảm của nhóm công ty giả lập này cũng khác dấu với tăng trưởng tổng thể được NSO công bố; GDP toàn nền **không phải** mốc định lượng cho doanh thu một SME.

## 2. Kiểm bốn kênh sốc mở rộng

Đối chứng cùng seed khớp **chính xác** `booked_orders`, mua vào, chỉ số giá bán và giá đầu vào trước episode đầu tiên (max sai khác = 0). Trong 13 tuần hoạt động của từng episode, so với đối chứng cùng thời điểm:

| Kênh | Tuần bắt đầu giả định | Đơn đã nhận V3 / đối chứng | Mua vào V3 / đối chứng | Dấu cơ chế ghi trong dữ liệu |
|---|---|---:|---:|---|
| Cầu | 21/10/2019 | 0,563 | 0,539 | Đơn giảm. |
| Cung | 03/05/2021 | 0,657 | 0,738 | Công suất trung bình 0,733; chỉ số giá đầu vào 1,336. |
| Giá | 21/11/2022 | 1,000 | 1,339 | Giá bán 1,185; giá đầu vào 1,464; số tiền mua tăng dù đơn danh nghĩa xấp xỉ đối chứng. |
| Tín dụng | 25/03/2024 | 0,510 | 0,454 | Giữ đơn/thiếu thanh khoản lan sang mua hàng. |

Các tỷ số trên xác nhận **máy phát phản ứng**; không phải ước lượng tác động lịch sử. Mức giảm ~44–49% đơn ở episode cầu/tín dụng là cường độ do người viết chọn, chưa neo bằng nguồn có cùng đơn vị. `region` vẫn là **vùng lương 1–4**, không phải tỉnh, nên không tái hiện phân bố hạn mặn hay bão. Không có tỷ trọng xuất khẩu, nguyên liệu vùng, dư nợ thả nổi hoặc mạng mua bán để định lượng phơi nhiễm. Không có backlog/lead time theo SKU; mua hàng và giao hàng diễn ra trong cùng tuần. Giao dịch giải ngân vay nhiễu có vào số dư tài khoản nhưng chưa có sổ dư nợ/lịch trả gốc đối ứng.

Kế hoạch mở rộng nêu bốn **họ sự kiện tham chiếu**: [xuất khẩu 2009 của NSO](https://www.nso.gov.vn/du-lieu-va-so-lieu-thong-ke/2019/04/tinh-hinh-kinh-te-xa-hoi-nam-2009/), [lạm phát/tín dụng 2011 của IMF](https://www.elibrary.imf.org/abstract/journals/002/2012/165/article-A005-en.xml), [hạn mặn 2016 của NSO](https://www.nso.gov.vn/du-lieu-va-so-lieu-thong-ke/2020/11/bc-tinh-hinh-kinh-te-xa-hoi-quy-i-nam-2016/) và [giá nhiên liệu 2026 của NSO](https://www.nso.gov.vn/tin-tuc-thong-ke/2026/10/thong-cao-bao-chi-ve-tinh-hinh-gia-thang-chin-quy-iii-va-9-thang-nam-2026/). Các nguồn xác nhận **kênh và khác biệt ngành/vùng**: ví dụ năm 2009 xuất khẩu cả năm −9,7% nhưng Q4 +7,1%; năm 2011 tín dụng **vẫn tăng** 14,3% dù chậm lại; năng suất lúa đông xuân ĐBSCL 2016 −5,6% nhưng Bến Tre −33,5%; nhiên liệu tháng 9/2026 +23,96% so cùng kỳ. Runner hiện **chưa mã hóa bốn template này** hoặc chuỗi tháng/độ bất định của chúng: `reference_event='synthetic_v3_assumption'`, bốn episode toàn quốc, và **cùng ngày/cường độ trong train, validation, test**. Test hiện chỉ có một thế giới và không có Test B giữ kín họ giá năng lượng. Do đó không thể tuyên bố mô hình chuyển giao sang cú sốc Việt Nam chưa thấy.

## 3. Kiểm lại 12 hard case cũ trên mã mới

Tất cả 12 thế giới full qua **hợp đồng bảng** (`136/136`, riêng FX `138/138`). Trong **19 mục tiêu tình huống tự đặt**, 18 đạt. `heterogeneity` còn thất bại: phương sai trễ giữa khách **0,303** so dải đích **0,55–0,65**; smoke một doanh nghiệp là 0,332. Đây là dải thử từ ERP tham chiếu nước ngoài, không phải mục tiêu Việt Nam, nhưng case hiện vẫn không đạt chính mục đích tăng dị biệt khách. Smoke một doanh nghiệp cũng lệch COD, `verbal`, `seasonal_extreme`; khi lên 12 công ty cả ba đạt, nên không dùng một doanh nghiệp để kết luận sai cơ chế.

Hai lỗi nghĩa rõ đã được sửa trong `agent1/synth/hard_cases.py`:

- `credit_note`: hóa đơn gốc hủy bằng credit note đủ giá trị vẫn tồn tại; hóa đơn thay thế tham chiếu ID gốc. Trên full case, **100%** tham chiếu tìm thấy; công nợ, thanh toán và sao kê được tính lại. Hóa đơn hủy phải loại hoặc bù credit note khi tính doanh thu gộp, nếu không sẽ đếm đôi.
- `supply_shock`: thay sửa riêng thanh khoản khách **sau khi đã rút mặc định** bằng `ShockEpisode` tác động công suất và giá vốn của bên bán thép. Ba công ty thép trong full case đều có đúng 8 tuần giảm công suất/tăng giá đầu vào; tỷ số đơn đã nhận/đơn yêu cầu trong cửa sổ là **0,702**. Smoke cũ chọn nhầm công ty bán buôn nên không hề kích hoạt case; smoke mới ép ngành thép và được lưu riêng.

**Các case còn là thử thuật toán, chưa là tần suất/hành vi Việt Nam:** `group_payer` đổi tên người chuyển nhưng không có sổ mẹ-con; `discount_early` dùng chiết khấu và ngày trả gần như tất định; `retention` giữ 5% đúng 730 ngày; `fx` rải USD ngẫu nhiên 15% không gắn chuỗi xuất nhập khẩu; `verbal` dịch ngày trả đồng loạt theo khách; `new_company` chỉ rút ngắn lịch sử. `lumpy_customer` hiện còn **nhìn toàn bộ doanh thu tương lai** để ép tỷ trọng anchor 40–60%, rồi không điều chỉnh đơn mua/tồn kho tương ứng: không đưa case này vào train as-of cho đến khi chuyển sang quyết định theo tuần. `idio_sd` được lưu trên khách nhưng vẫn không đi vào phương trình thanh khoản. Nguồn Parquet của các case cũ không còn, nên 12 case v3 là kiểm tái sinh, không sửa lại lịch sử đánh giá cũ.

## 4. Quyết định vận hành

`scripts/build_final_train.py` nay có bước `audit_worlds` **trước** `lock_split`. Với kỳ đầy đủ 2019–2025, cổng kỹ thuật yêu cầu file OxCGRT/WDI có hash, tỷ số doanh thu hóa đơn thuần 2025/2019 của mỗi thế giới ≥0,6, và ít nhất một họ sốc chỉ có trong test. **0,6 là ngưỡng phát hiện sụp đổ nội tại, không phải mốc thị trường.** Nếu không đạt, runner lưu `readiness.json` rồi dừng; `--stop-after audit_worlds` cho phép lấy báo cáo mà chưa khóa train. Runner hiện cũng trượt điều kiện họ sốc giữ kín. Cổng này không thay thế ma trận đánh giá G1–G18 và không thay đổi lịch sử cổng.

Trạng thái hiện tại: **chưa khóa split, chưa huấn luyện model cuối, chưa có bộ train đạt chuẩn phát hành**. Nguồn công khai OxCGRT/WDI đã tải và hash; riêng vi dữ liệu thanh toán B2B Việt Nam chưa có. Cần sửa dòng khách mới/đào thải, tách xác suất mất nợ khỏi mặc định vĩnh viễn, xử lý `lumpy_customer` và `heterogeneity`, sau đó sinh đối chứng nhiều seed và hiệu chỉnh thống kê theo năm/ngành/cohort. Tiếp theo mới khóa lịch Test A/Test B khác nhau và chạy T1/T6/T9 trên cùng test. Khi chưa có vi dữ liệu Việt Nam, kết quả được gọi là **bộ synthetic kiểm thử có giới hạn**, không là phân phối giao dịch Việt Nam đã xác nhận.

Mã máy phát/runner ở working tree đang có nhiều thay đổi chưa commit. Manifest lưu hash tại lúc đăng ký thế giới; cần đóng băng chính xác mã nguồn và các file nguồn cùng cohort khi sinh bộ ứng viên cuối. Không diễn giải hash của một working tree đang tiếp tục đổi như một bản phát hành bất biến.
