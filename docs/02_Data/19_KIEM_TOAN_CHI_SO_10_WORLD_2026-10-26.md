# Kiểm toán doanh thu, công nợ và tiền mặt trên 10 World đối chứng (26/10/2026)

> **Hồ sơ đo ngày 26/10; gộp tài liệu ngày 06/11/2026.** Dữ liệu lifecycle nguồn đã xóa. CSV/JSON kết quả vẫn được giữ; lệnh tái lập bên dưới cần có lại World đúng manifest và phiên bản mã. Việc gộp báo cáo 16/17 không tạo phép đo hay seed mới.

## Phạm vi và cách đọc

Kiểm lại **10 World không có `ShockEpisode` mới**, seed 94317–94326, mỗi World 24 doanh nghiệp trong 2019–2025. Ba World v5 và bảy World v6 đã có từ trước; lượt này chỉ đọc Parquet, dùng `one_world()` trong `scripts/audit_existing_world_metrics.py`, không sinh dữ liệu, sửa máy phát hoặc train. Bảng chi tiết `outputs/data/v6_existing_world_metrics_10seed_20261026.csv` có **490 dòng**: 10 World × 7 năm × `ALL` và 6 ngành. Mỗi dòng giữ mẫu số và ngày chốt riêng. Các bảng tóm tắt bên dưới lấy **trung vị của 10 World**; không coi mỗi hóa đơn là một seed độc lập.

Tái lập bảng chi tiết từ thư mục gốc repo với môi trường Python đã cài `pandas`, `numpy` và `pyarrow`:

```powershell
python -c "import pandas as pd; from scripts.audit_existing_world_metrics import one_world; from agent1.paths import SYNTH; names=[f'v5_lifecycle_control_{s}' for s in range(94317,94320)]+[f'v6_lifecycle_control_{s}' for s in range(94320,94327)]; pd.DataFrame([row for name in names for row in one_world(SYNTH/name)]).to_csv('outputs/data/v6_existing_world_metrics_10seed_20261026.csv',index=False)"
```

Định nghĩa dùng chung cho bảng ba World và mười World: doanh thu thuần/khách/tỷ lệ bán chịu theo **năm phát hành**; thời gian trả chỉ trên hóa đơn **bán chịu đã thu đủ trong năm**; nợ quá hạn là **số dư còn mở tại 31/12, đã qua hạn**, sau tiền thu, credit note và xóa nợ có ngày; số dư tiền là **tài khoản vận hành** theo ngày × doanh nghiệp. P50/P90 ngày trả tính theo số hóa đơn, P50/P90 tuổi nợ quá hạn tính theo **giá trị còn nợ**. `credit_value_share` dùng giá trị hóa đơn gốc; nợ quá hạn / AR mở dùng toàn bộ AR mở (gồm cả COD nếu còn nợ), nên không cùng mẫu số với khảo sát về hóa đơn bán chịu.

## Kết quả theo năm

| Năm | Doanh thu / 2019 cùng World | Khách có hóa đơn | Bán chịu theo giá trị | Thu đủ P50 / P90, ngày | Trả trễ theo giá trị đã thu đủ | Nợ quá hạn / AR mở 31/12 | Tuổi nợ quá hạn P90, ngày | Số dư tiền P10 / P50, tỷ VND | Ngày số dư âm |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 1,000 | 1.243 | 66,3% | 34,5 / 83,5 | 27,1% | 35,7% | 166 | 1,23 / 6,73 | 4,0% |
| 2020 | 0,766 | 1.154 | 65,4% | 42 / 120 | 36,2% | 35,5% | 280 | 0,81 / 6,40 | 6,2% |
| 2021 | 0,801 | 1.173 | 66,5% | 42 / 116 | 37,2% | 40,8% | 311 | 0,79 / 6,73 | 6,0% |
| 2022 | 0,755 | 1.086 | 65,7% | 42 / 125 | 40,0% | 53,2% | 281 | 0,13 / 6,12 | 8,6% |
| 2023 | 1,059 | 1.148 | 68,7% | 41 / 111 | 36,1% | 37,1% | 240 | −0,18 / 5,99 | 10,5% |
| 2024 | 1,539 | 1.241 | 67,3% | 42 / 102 | 35,2% | 37,1% | 238 | −0,78 / 5,42 | 12,4% |
| 2025 | 1,579 | 1.255 | 66,7% | 43 / 115 | 37,3% | 41,7% | 268 | −0,09 / 6,75 | 10,8% |

Doanh thu là **tỷ số của từng World với chính năm 2019**, rồi mới lấy trung vị; số khách là trung vị số khách riêng từng World. Kỳ hạn bán chịu bình quân theo giá trị năm 2025 có trung vị **42,7 ngày**. Tiền mặt P90 cùng năm có trung vị **26,1 tỷ VND**. Trong AR đã quá hạn cuối 2025, trung vị **66,8% giá trị** quá hạn trên 60 ngày; đây là tuổi của số dư chưa được thu hoặc xóa tại ngày chốt.

Xu hướng giữa các seed còn rộng: doanh thu 2025/2019 **0,886–1,886**; khách có hóa đơn năm 2025 **889–1.372**. Seed 94319 có doanh thu 2025/2024 chỉ **0,395**. Đây là một đợt giảm trong mô phỏng cần điều tra, dù không có xu hướng sụp giảm bắt buộc trên cả 10 seed. Trung vị 2022 có nợ quá hạn / AR mở **53,2%** và thời gian thu đủ P90 **125 ngày**; cùng thời kỳ có `credit_crunch` nền trong máy phát, nhưng bảng mô tả này không tách được tác động nhân quả của từng cơ chế.

## Phân bố năm 2025 giữa các World và ngành

| Chỉ số toàn World | Nhỏ nhất | Trung vị | Lớn nhất |
|---|---:|---:|---:|
| Bán chịu theo giá trị | 62,1% | 66,7% | 71,4% |
| Kỳ hạn bán chịu bình quân theo giá trị | 37,9 ngày | 42,7 ngày | 45,3 ngày |
| Thu đủ P50 | 36 ngày | 43 ngày | 44 ngày |
| Thu đủ P90 | 96 ngày | 115 ngày | 176 ngày |
| Trả trễ theo giá trị hóa đơn đã thu đủ | 34,8% | 37,3% | 48,5% |
| Nợ quá hạn / AR mở 31/12 | 33,2% | 41,7% | 59,1% |
| Tuổi nợ quá hạn P90 có trọng số số dư | 234 ngày | 268 ngày | 424 ngày |
| Số dư tiền P10 | −2,64 tỷ | −0,09 tỷ | 1,29 tỷ |
| Ngày × doanh nghiệp có số dư âm | 4,6% | 10,8% | 19,3% |

Trung vị theo 10 World của từng ngành trong năm 2025. Do số doanh nghiệp/ngành thay đổi giữa World, doanh thu và khách được chia cho **số doanh nghiệp của chính ngành trong World**, rồi mới lấy trung vị:

| Ngành | Doanh thu thuần / DN, tỷ VND | Khách có hóa đơn / DN | Bán chịu theo giá trị | Thu đủ P50, ngày | Nợ quá hạn / AR mở | Tuổi nợ quá hạn P90, ngày | Ngày số dư âm |
|---|---:|---:|---:|---:|---:|---:|---:|
| Thực phẩm | 72,6 | 45,9 | 58,6% | 34 | 33,5% | 364 | 1,2% |
| Nhựa, cao su | 84,7 | 48,3 | 69,5% | 55,5 | 40,6% | 243 | 5,1% |
| Dịch vụ | 64,1 | 57,7 | 62,9% | 32,5 | 44,5% | 258 | 1,1% |
| Thép, kim loại | 69,2 | 43,5 | 66,7% | 42 | 29,3% | 317 | 19,1% |
| Dệt may | 106,8 | 46,5 | 68,3% | 36,5 | 53,4% | 248 | 11,6% |
| Bán buôn | 86,7 | 54,5 | 62,9% | 42 | 38,3% | 241 | 3,7% |

Mỗi ngành chỉ có **1–8 doanh nghiệp trong một World**. Các trung vị ngành không nên được xem là thứ hạng ngành Việt Nam. Phân vị số dư tiền P10/P50/P90 theo **từng năm và từng ngành** nằm ở bảng CSV 490 dòng. Phân vị VND gộp các công ty lớn/nhỏ nên phụ thuộc phân bố quy mô doanh nghiệp; đây không phải phân vị đệm tiền chuẩn hóa theo chi phí của một SME điển hình.

## Censoring, đối chiếu Việt Nam và kiểm tra kỹ thuật

Giá trị hóa đơn bán chịu **phát hành năm 2025** còn `censored` tại 31/12 chiếm **20,8–26,2%** giữa 10 World (trung vị **21,7%**). Vì vậy P50/P90 ngày thu đủ chỉ mô tả các khoản đã tất toán; khoản còn mở có thể làm phân phối cuối cùng dài hơn. Tỷ lệ trả trễ của hóa đơn đã thu đủ, tỷ lệ AR còn mở đang quá hạn và tỷ lệ nợ xấu đã chốt là **ba đại lượng khác nhau**. Không dùng số 2025 đã kiểm duyệt để suy ra tỷ lệ mất nợ cuối cùng.

[Báo cáo 14](14_KIEM_TOAN_SAU_SUA_VA_QUYET_DINH_TRAIN_2026-10-26.md) đã dẫn khảo sát Atradius Việt Nam 2025 làm neo tham khảo: 65% doanh số bán chịu, kỳ hạn 45 ngày, 39% giá trị hóa đơn quá hạn và 3% nợ xấu. Lượt này **không tải hoặc xác minh lại nguồn ngoài**, theo giới hạn chỉ dùng dữ liệu/code hiện có. Trung vị synthetic 2025 là 66,7% bán chịu và 42,7 ngày kỳ hạn, gần về cỡ số với hai neo đầu. Các neo Atradius đã tham gia hiệu chỉnh máy phát, nên mức gần này **không phải kiểm chứng độc lập**. Mẫu khảo sát, ngành, cửa sổ, đơn vị và mẫu số khác. Không so 37,3% **đã thu đủ nhưng trả trễ** hoặc 41,7% **AR mở đang quá hạn** trực tiếp với 39% khảo sát. Không có mốc Việt Nam cùng định nghĩa cho P90 tuổi nợ, doanh thu/khách của 24 doanh nghiệp giả lập hoặc ngày tài khoản vận hành âm. Kết quả là kiểm toán **nội bộ synthetic**, chưa xác nhận phân phối thị trường Việt Nam.

Kiểm tra đã chạy trong lượt này:

- `one_world()` xác minh manifest và `validate_world` cho cả 10 World, tái dựng AR từng 31/12; số dư từng hóa đơn tại 31/12/2025 khớp `remaining_amount` với sai khác không quá **1,01 VND**.
- **147/147** dòng của ba World v5 khớp bảng audit trước; tỷ số doanh thu 2025/2019 của **10/10** World khớp `v6_multiseed_trend_20261026.csv`.
- **490/490** dòng qua kiểm miền 0–1 của các tỷ lệ, thứ tự P10≤P50≤P90 tiền mặt, P50≤P90 thời gian thu, tổng ba bucket tuổi nợ bằng 1 và nợ quá hạn không vượt AR mở.
- `pytest -q tests/test_synthetic_accounting.py tests/test_contracts.py`: **15 passed**. Không chạy train hoặc mở outcome của các World test held-out.

Hai lô v5/v6 có cùng hash calibration/OxCGRT/WDI và config khác `name`/`seed`, nhưng **hash toàn bộ mã Python khác nhau**; không coi 10 World là một phát hành mã bất biến. Mười seed chưa đủ để ước xác suất các biến cố hiếm. Việc còn thiếu: vi dữ liệu AR/AP Việt Nam cùng định nghĩa để hiệu chỉnh theo cohort/ngành, đo độ nhạy nhiều seed hơn, phân tích seed 94319 và đánh giá shock held-out sau khi chốt một cohort full. Trạng thái bộ train cuối và tuyên bố “đại diện thị trường Việt Nam” vẫn **NO-GO**.


<a id="ba-world-v5"></a>

## Phụ lục A — Mẫu ba World v5 trước khi mở rộng

Gộp từ báo cáo 16 ngày 26/10. Ba World này **nằm trong cùng mẫu mười World**
ở trên; không cộng chúng như ba seed độc lập bổ sung. Bảng chi tiết ban đầu:
`outputs/data/v5_existing_world_metrics_20261026.csv`, 147 dòng.
Sai khác cho phép khi đối soát `remaining_amount` là 1,01 VND/hóa đơn.

| Seed | Doanh thu thuần, nghìn tỷ VND | Khách có hóa đơn | Bán chịu theo giá trị | Kỳ hạn bình quân theo giá trị | Ngày phát hành → thu đủ P50/P90 | Trả trễ trong hóa đơn đã thu đủ, theo giá trị | Nợ quá hạn / công nợ mở 31/12 | Tuổi nợ quá hạn P50/P90 | Số dư tiền P10/P50, tỷ VND | Ngày số dư âm |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 94317 | 3,503 | 958 | 71,4% | 42,8 ngày | 42 / 120 ngày | 37,1% | 33,6% | 69 / 259 ngày | −2,47 / 6,46 | 19,3% |
| 94318 | 2,364 | 1.277 | 67,7% | 45,3 ngày | 43 / 118 ngày | 40,5% | 41,1% | 80 / 234 ngày | 0,41 / 6,63 | 6,6% |
| 94319 | 1,049 | 889 | 68,5% | 37,9 ngày | 44 / 176 ngày | 48,5% | 55,6% | 190 / 424 ngày | −1,26 / 4,26 | 13,6% |

Doanh thu 2025/2019 lần lượt là **1,173; 1,443; 0,886**. Số khách có hóa đơn 2019→2025 lần lượt **1.017→958; 1.215→1.277; 1.109→889**. Vì vậy lỗi suy giảm đồng loạt trước sửa không lặp ở cả ba seed, nhưng seed 94319 vẫn có giảm khách và đuôi thanh toán/nợ quá hạn đáng chú ý. Ba seed không đủ để ước xác suất suy giảm hoặc khoảng tin cậy.

Khoản quá hạn tại 31/12/2025 là **186,3; 153,9; 125,6 tỷ VND** tương ứng ba seed. Trong số dư quá hạn, tỷ phần đã quá hạn trên 60 ngày là **55,8%; 65,4%; 73,6%**. Đây là tồn kho công nợ tại ngày chốt, không phải tỷ lệ hóa đơn phát hành năm 2025 rốt cuộc trở thành nợ xấu.

## Phân tách theo ngành

Trung vị của ba kết quả theo seed trong năm 2025 (mỗi ngành chỉ có khoảng 2–5 doanh nghiệp/seed; xem CSV để kiểm từng seed):

| Ngành | Bán chịu theo giá trị | Thu đủ P50, ngày | Trả trễ theo giá trị đã thu đủ | Nợ quá hạn / công nợ mở | Tuổi nợ quá hạn P90, ngày | Ngày số dư âm |
|---|---:|---:|---:|---:|---:|---:|
| Thực phẩm | 65,5% | 30 | 35,1% | 31,4% | 278 | 0,5% |
| Nhựa, cao su | 69,9% | 57 | 51,5% | 43,1% | 251 | 5,6% |
| Dịch vụ | 62,1% | 41 | 42,4% | 44,7% | 243 | 0,8% |
| Thép, kim loại | 63,7% | 43 | 38,9% | 31,6% | 388 | 21,5% |
| Dệt may | 68,6% | 36 | 29,1% | 49,9% | 252 | 9,4% |
| Bán buôn | 73,1% | 45 | 38,2% | 34,3% | 284 | 3,6% |

<a id="xu-huong-muoi-seed"></a>

## Phụ lục B — Xu hướng của từng seed

Gộp phần nhiều seed của báo cáo 17; thiết kế held-out/pilot được gộp tại
[mục runner của máy phát](04_may_phat_tong_hop.md#runner-manifest-split).

Ba World v5 đã có (`94317`–`94319`) được ghép với bảy World v6 mới (`94320`–`94326`). Mỗi World gồm 24 doanh nghiệp, 2019–2025, RNG v2, cùng calibration và hash đầu vào OxCGRT/WDI; config chỉ khác `name` và `seed`. Bảy World mới đã qua hợp đồng dữ liệu và có manifest riêng. Hash **toàn bộ code** giữa hai đợt khác nhau vì runner/script audit được sửa giữa hai đợt; mã máy phát không bị sửa trong đợt này. Bảng máy đọc được: `outputs/data/v6_multiseed_trend_20261026.csv`; audit gốc: `outputs/data/v5_lifecycle_audit_20261026.json` và `outputs/data/v6_lifecycle_audit_20261026.json`.

| Seed | Doanh thu thuần 2025/2019 | Khách có hóa đơn 2025/2019 | Doanh thu 2025/2024 |
|---|---:|---:|---:|
| 94317 | 1,173 | 0,942 | 1,040 |
| 94318 | 1,443 | 1,051 | 1,032 |
| 94319 | 0,886 | 0,802 | 0,395 |
| 94320 | 1,042 | 0,930 | 0,875 |
| 94321 | 1,886 | 1,013 | 1,160 |
| 94322 | 1,622 | 0,938 | 0,973 |
| 94323 | 1,715 | 1,039 | 1,056 |
| 94324 | 1,748 | 1,063 | 0,990 |
| 94325 | 1,624 | 1,007 | 1,118 |
| 94326 | 1,537 | 1,064 | 1,140 |

Tỷ số doanh thu 2025/2019 có **min 0,886; trung vị 1,579; max 1,886**. Chỉ **1/10** World có doanh thu 2025 dưới 2019; **0/10** dưới ngưỡng phát hiện sụp đổ 0,6 của cổng nội bộ. Khách có hóa đơn giảm trong **4/10** World; trung vị tỷ số 2025/2019 là **1,010**. Doanh thu năm 2021 dưới 2019 trong **7/10** World, phù hợp việc 2020–2021 có stress vĩ mô trong cấu hình. Doanh thu 2025 thấp hơn 2024 trong **4/10** World; vì thế không được hiểu kết quả dài hạn là mọi năm đều tăng.

Seed `94319` là cảnh báo: doanh thu 2025/2024 chỉ 0,395, trung vị tỷ số này ở cấp doanh nghiệp khoảng 0,424 nên không do một doanh nghiệp lớn duy nhất. `macro.common_factor` của seed này có bình quân 2025 là −1,114; đây là tín hiệu synthetic, chưa phải bằng chứng nguyên nhân thị trường. Cần kiểm thêm độ nhạy của nhân tố chung và nhiều seed độc lập trước khi dùng đuôi phân phối cho train cuối.
