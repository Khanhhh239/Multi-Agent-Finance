# Agent 1 — Thẻ dữ liệu (Data Card)

> **Ảnh chụp dữ liệu giai đoạn đầu.** Bảng bốn World và tám nguồn bên dưới
> không phải tồn kho ngày 27/10/2026: file thô hiện chỉ còn WDI và OxCGRT.
> Manifest tám nguồn đã chuyển thành [hồ sơ lịch sử](02_Data/MANIFEST_RAW_8_SOURCES_2026-10-14_ARCHIVE.json).
> Để dùng bộ train synthetic cuối, đọc [báo cáo 23](02_Data/23_BO_TRAIN_SYNTHETIC_CUOI_2026-10-27.md)
> và [cohort JSON](../data/synthetic/v3_final_20261027_cohort.json); trạng thái
> pilot đọc ở [cổng hiện hành](03_Evaluation/GATES_CURRENT.md).

Dữ liệu của Agent 1 theo **ba tầng** (Phần 5, mục 0). Mỗi tầng chỉ được dùng cho đúng loại kết luận của nó:

| Tầng | Nội dung | Được kết luận gì |
|---|---|---|
| 1. Thật, tương tự | BPI 2019, Customer Invoices, SBA 7(a), Berka, Online Retail II | Phương pháp chạy được trên dữ liệu thật |
| 2. Thống kê thật để hiệu chỉnh | Atradius VN 2025, UK Payment Practices, OxCGRT VN, WDI VN, JPMorgan Chase Institute | Phân phối biên của máy phát khớp số liệu công bố |
| 3. Tổng hợp có nhãn | 4 "thế giới" SME Việt Nam (`data/synthetic/`) | Xử lý được tình huống đã chèn (lô, lời hứa, sốc, Tết…) |

Không tầng nào chứng minh hiệu quả trên hoá đơn thật của SME Việt Nam; việc đó chỉ có ở T13 (thử nghiệm với doanh nghiệp đối tác).

---

## 1. Crawl (`scripts/crawl.py`, có `data/raw/MANIFEST.json` với SHA-256)

| Khoá | Nguồn | Kích thước | Giấy phép | Dùng cho |
|---|---|---|---|---|
| `uk_ppr` | check-payment-practices.service.gov.uk (115.490 báo cáo) | 103 MB | OGL v3 | T12 hình dạng trễ 30/31–60/60+ (kiểm tra độc lập), T3 tỷ lệ tranh chấp |
| `oxcgrt` | OxCGRT national compact (Việt Nam) | 44 MB | CC BY 4.0 | T12 chỉ số sốc COVID theo tuần, T7 mốc gãy thật |
| `wdi_vn` | World Bank API (6 chỉ số VN) | 396 dòng | CC BY 4.0 | lãi suất cho vay (chi phí vay trong máy phát), vĩ mô |
| `online_retail_ii` | UCI (1.067.371 dòng) | 46 MB | CC BY 4.0 | T4 dữ liệu thật: 73 chuỗi doanh thu tuần |
| `berka` | PKDD'99 (bản sao GitHub jlacko) | 67 MB | dữ liệu thử thách công khai | T6/T7 dòng tiền ngân hàng thật (404.880 tài khoản-tuần) |
| `sba_7a` | data.sba.gov FOIA 7(a) FY2010–nay | 436 MB | dữ liệu công của chính phủ Mỹ | T2 thật: 638.249 khoản vay, nhãn xoá nợ trong 3 năm |
| `bpi2019` | 4TU/figshare, **MD5 đã kiểm** | 729 MB | CC BY 4.0 | T1 thật (phía phải trả): 211.142 hoá đơn, kiểm duyệt phải tự nhiên |
| `customer_invoices` | bản sao GitHub của Kaggle pradumn203 | 7,9 MB | chưa rõ (độ tin cậy C) | T1 thật-tương-tự: 49.998 hoá đơn AR kiểu ERP |

Nguồn cần đăng nhập / chấp nhận điều khoản **không tự động**: Home Credit, M5, Freddie Mac, Payment Times Úc, SEC (bắt buộc khai User-Agent có email của chính bạn), UNU-WIDER (`python scripts/crawl.py --list`).

Bộ nạp chuẩn hoá ở `agent1/data/real_loaders.py` (cache `data/interim/*.parquet`).

## 2. Máy phát tổng hợp (T12) — `agent1/synth/world.py`

Cơ chế (không dùng trọng số cố định, tránh các dấu hiệu "bộ sinh phẳng"):

- **Nhân tố thanh khoản chung** AR(1) nhiễu Student-t (df=4) + **chỉ số sốc COVID tính từ OxCGRT Việt Nam thật** + cú sốc đóng băng tín dụng 10/2022–06/2023 theo ngành; thanh khoản riêng từng khách AR(1) có tải nhân tố.
- **Kỳ hạn rời rạc** (0/15/30/45/60/90) theo ngành; **đúng hạn / trễ / nợ xấu** hiệu chỉnh tự động theo Atradius VN 2025 (vòng lặp 5 lần, `scripts/build_worlds.py`, kết quả `calibration_fit.json`).
- **Trễ**: lognormal theo khách (trung tâm "khoảng một tháng"), đuôi cực dài kiểu Coface, tranh chấp, **điểm gãy riêng khách** (10% khách), **suy giảm trước vỡ nợ**.
- **Ngày chạy thanh toán** của khách (thứ cố định / ngày 10–25 / 5–20 / 15–cuối tháng / cuối tháng), không trả cuối tuần, **Tết**: dồn trả trước Tết, đóng băng trong kỳ nghỉ chính thức (có nghỉ bù), chậm khởi động sau Tết.
- **Vỡ nợ cấp khách** (hazard theo thanh khoản + sốc) → nợ xấu tương quan, thu hồi một phần sau 4–12 tháng; khách vỡ nợ ngừng phát sinh hoá đơn.
- **Trả một phần**, giảm trừ do tranh chấp, trả thiếu, **phí chuyển tiền bị trừ**, **gộp nhiều hoá đơn trong một lệnh chuyển**.
- **Sao kê ngân hàng**: tên đối tác không dấu/viết tắt/cắt 50 ký tự/đôi khi trống; **nội dung chuyển khoản kiểu VN** (`CTY ABC TT HD 123, 124`, tiền tố `MBVCB.…`, `FT…`, lỗi gõ, cắt 70/140/210 ký tự, ~50% không ghi số HĐ); giao dịch nhiễu (lãi, nộp tiền mặt, nội bộ, hoàn cọc, giải ngân vay).
- **Sổ cái**: kế toán ghi theo ngày / tuần / cuối tháng (**nhiễu lô W1**), **phân bổ FIFO sai** khi không có số HĐ.
- **Lời hứa trả** (T8) tại mốc quá hạn 7/21/45/75 ngày, độ tin cậy Beta theo khách, nhất quán với ngày trả thật.
- **Chi**: NCC (mua trước bán 2 tuần, kỳ hạn NCC, ngày chạy chi), lương (≥ lương tối thiểu vùng theo NĐ 90/2019→293/2025), BHXH 32%, VAT tháng/quý theo ngưỡng 50 tỷ, TNDN tạm nộp quý, lệ phí môn bài (bãi bỏ từ 2026), thuê, lãi vay (lãi suất WDI), tiện ích, thưởng tháng 13 trước Tết, capex bất thường — tất cả qua **bộ máy quy tắc T5** (`agent1/calendar_vn.py`).
- **Số dư đầu kỳ** theo đệm tiền mặt của JPMorgan Chase Institute (trung vị 27 ngày chi); chủ DN rút lợi nhuận khi số dư vượt ngưỡng → thiếu hụt xảy ra khi có sốc, không trôi lên vô hạn.
- **Hoá đơn điện tử XML** theo cấu trúc QĐ 1450/1510 (`einvoice_xml/`), MST có chữ số kiểm tra hợp lệ, ký hiệu TT78 (`C25TAA`).

### Các thế giới (miền) — cho domain adaptation

| Thế giới | Vai trò | Công ty | Khách | Hoá đơn | Giao dịch NH | Lời hứa |
|---|---|---|---|---|---|---|
| `src` | miền **nguồn** (huấn luyện/tiền huấn luyện) | 40 | 3.427 | 193.469 | 188.260 | 44.327 |
| `tgt` | miền **đích niêm phong** (seed riêng; SME nhỏ hơn, ghi sổ theo lô nhiều hơn, trễ dài hơn 25%, tranh chấp ×1,5, ít ghi số HĐ hơn, cơ cấu ngành khác) | 14 | 617 | 41.762 | 39.512 | 13.255 |
| `sens_uk` | kiểm thử chịu nhiễu: đuôi trễ kiểu Anh (ngắn) | 12 | 772 | 89.031 | 82.959 | 16.350 |
| `sens_coface` | kiểm thử chịu nhiễu: đuôi trễ cực dài kiểu Coface | 12 | 594 | 70.583 | 65.346 | 15.631 |

Mỗi thế giới: `invoices, payments, bank_txns, promises, outflows, firms, customers, events (nhãn điểm gãy & vỡ nợ), macro, daily_cash (số dư thật), einvoice_xml/, fidelity_report.json, config.json`.

### Kiểm định độ trung thực (`agent1/synth/fidelity.py`)

**(A) Đích đã dùng để hiệu chỉnh** — chỉ chứng minh máy phát chạy đúng (quy tắc chống ảo tưởng 1):

| Theo giá trị | Đích Atradius VN | `src` | `tgt` | `sens_uk` | `sens_coface` |
|---|---|---|---|---|---|
| Đúng hạn | 58% | 54,4% | 57,0% | 55,2% | 55,2% |
| Quá hạn | 39% | 42,4% | 39,2% | 41,2% | 40,0% |
| Nợ xấu | 3% | 3,2% | 3,8% | 3,6% | 4,8% |
| Kỳ hạn TB (ngày) | 45 | 41,6 | 48,3 | 39,2 | 35,2 |
| Tỷ trọng bán chịu | 65% | 58,9% | 64,0% | 63,3% | 57,2% |

**(B) Kiểm tra độc lập** (không dùng để chỉnh) — so với bộ AR giống ERP thật (Customer Invoices):

| Dấu hiệu | `src` (trung vị theo công ty) | `tgt` | Tham chiếu thật | Nhận xét |
|---|---|---|---|---|
| Tỷ lệ trả cuối tuần | 0,14% | 0,08% | 0,37% | khớp (ERP thật gần như không trả cuối tuần) |
| Độ lệch Benford (MAD) | 0,0075 | 0,0101 | 0,0082 | khớp |
| Độ bền hành vi khách (Spearman 2 nửa) | 0,72 | 0,83 | 0,75 | khớp |
| Tập trung top-10 khách | 54% | 70% | 43% | SME tập trung hơn (hợp lý) |
| Phương sai trễ do danh tính khách | 0,20 | 0,19 | 0,60 | **thấp hơn** — khách tổng hợp đồng nhất hơn thật; giới hạn đã biết |
| CV khối lượng tháng | 0,37 | 0,41 | 0,18 | cao hơn do giai đoạn COVID/Tết (tham chiếu chỉ 17 tháng trước COVID) |

Nhóm trễ (pooled, `src`): sớm 25%, đúng ngày 17%, trễ 1–30 ngày 46%, 31–60 ngày 7,7%, >60 ngày 4,1%. UK PPR (trung vị các báo cáo): 60% trả trong 30 ngày, 27% 31–60, 7% >60 — tính từ ngày lập, phía người trả là DN lớn Anh, nên chỉ dùng như kiểm tra họ phân phối, không làm đích.

**Thiếu hụt tiền** (ground truth T6): `src` 26/40 công ty có ít nhất một ngày số dư âm (2,4% số ngày); `tgt` 12/14 (9,8%) — miền đích căng thẳng hơn.

## 3. Sản phẩm dữ liệu theo nhiệm vụ

| T | Dữ liệu huấn luyện | Dữ liệu đánh giá | Nhãn |
|---|---|---|---|
| T0 | XML hoá đơn điện tử + bộ chèn lỗi có nhãn (`agent1/data/schema.py`) | `tests/test_t0_t5.py` | lỗi đã chèn |
| T1 | snapshot as-of mỗi tuần (landmark) từ `src`; Customer Invoices; BPI 2019 | `src` rolling-origin, `tgt` (onboard 2024-07 với 0–24 tháng lịch sử), hai bộ thật | ngày tiền về NH, kiểm duyệt phải tại ngày cắt |
| T2 | snapshot quá hạn (`src`); SBA 7(a) FY2010–2016 | `src`/`tgt` 2024-07→2025-06; SBA FY2018–2022 | nợ xấu thật (tổng hợp); xoá nợ ≤3 năm (SBA) |
| T3 | hoá đơn `src` với lịch sử tranh chấp/trả một phần as-of ngày lập | `tgt` | cờ tranh chấp / trả một phần |
| T4 | chuỗi doanh thu tuần 40 công ty `src`; Online Retail II | 26 tuần cuối, rolling mỗi 4 tuần (`src`, `tgt`, thật) | doanh thu tuần |
| T5 | — (quy tắc tất định) | ví dụ theo văn bản luật (15 kiểm thử) | ngày hạn đúng luật |
| T6 | T1+T4+T5 trên `src` | 14 công ty `tgt` × 52 điểm cắt × 13 tuần | số dư "không can thiệp" thật |
| T7 | phần dư trễ theo khách `src` (chỉnh ngưỡng) | `tgt`+`sens_uk`+`sens_coface` | điểm gãy đã chèn |
| T8 | lời hứa trả `src` | `src` 2024-07→2024-12 | ngày trả thật |
| T9 | cặp sao kê–hoá đơn của 12 công ty `src` (2023) | toàn bộ `tgt` 2024 | liên kết giao dịch–hoá đơn thật |

## 4. Giả định và giới hạn (ghi rõ)

- Hình dạng trễ quá hạn, nhiễu ghi sổ theo lô, thoả thuận miệng **không có nguồn số liệu** — là giả định của người thiết kế, chạy dưới dạng khoảng nhạy cảm (3 giả định đuôi).
- Ngày nghỉ bù hằng năm: python-holidays + bảng kỳ nghỉ Tết chính thức; cần đối chiếu thông báo của Chính phủ mỗi năm.
- Thuế suất 8% áp dụng theo các NQ giảm thuế; loại trừ kim loại được đơn giản hoá ở cấp ngành.
- Hạn BHXH rơi vào ngày nghỉ được lùi về ngày làm việc trước đó (giả định thận trọng; cần đối chiếu QĐ 595).
- Tỷ lệ tranh chấp UK PPR có trung vị 0% (đa số báo cáo ghi 0) nên máy phát dùng mức ~1,2%/hoá đơn làm tiền nghiệm.
