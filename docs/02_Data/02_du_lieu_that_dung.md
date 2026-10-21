# 2. Dữ liệu thật đang dùng (đã crawl, có SHA-256)

Tổng ~1,5 GB tại `data/raw/`. Bộ nạp: `agent1/data/real_loaders.py`; cache: `data/interim/*.parquet`.
Thang tin cậy: A = chính thức/bình duyệt; B = uy tín nhưng có hạn chế phương pháp; C = cộng đồng, nguồn gốc không rõ.

## 2.1 Tổng quan

| # | Bộ | Loại | Quy mô sau chuẩn hoá | Tin cậy | Dùng cho |
|---|---|---|---|---|---|
| 1 | BPI Challenge 2019 | Nhật ký sự kiện P2P thật | 211.142 "hoá đơn" (dòng PO), 1.850 nhà cung cấp, 3 công ty | A | T1 trên dữ liệu thật (phía phải trả) |
| 2 | Customer Invoices (HighRadius) | AR giống ERP | 49.998 hoá đơn, 1.461 khách | C | T1 trên AR; kiểm tra độc lập cấu trúc |
| 3 | SBA 7(a) | Khoản vay SME Mỹ | 638.249 khoản (FY2010–2023), nhãn xoá nợ ≤3 năm, tỷ lệ 1,64% | A | T2 nợ xấu trên dữ liệu thật |
| 4 | Berka PKDD'99 | Giao dịch ngân hàng thật | 1.478 tài khoản × 6 năm = 404.880 tài khoản-tuần | A | T6/T7 dòng tiền thật, khoảng dự báo |
| 5 | Online Retail II | Giao dịch bán buôn/bán lẻ Anh | 1.067.371 dòng → 73 chuỗi doanh thu tuần × 106 tuần | A | T4 doanh thu mới trên dữ liệu thật |
| 6 | UK Payment Practices | Thống kê thật | 115.490 báo cáo DN lớn | A | Kiểm tra họ phân phối trễ (độc lập), tranh chấp |
| 7 | OxCGRT (Việt Nam) | Chỉ số chính sách COVID | 1.096 ngày | A | Sốc COVID thật trong máy phát; T7 |
| 8 | WDI Việt Nam | Vĩ mô | 6 chỉ số | A | Lãi suất vay, vĩ mô |

## 2.2 Chi tiết từng bộ

### BPI Challenge 2019 (`bpi2019/BPI_Challenge_2019.xes`, 729 MB, MD5 đã xác minh)
- **Là gì**: quy trình mua hàng – nhận hàng – hoá đơn – thanh toán của một tập đoàn sơn đa quốc gia Hà Lan; 76.349 chứng từ,
  251.734 dòng hàng, ~1,5 triệu sự kiện, 42 loại hoạt động, 627 tác nhân (20 là tác nhân xử lý theo lô). CC BY 4.0.
- **Chuẩn hoá của chúng ta**: mỗi dòng hàng PO có "hoá đơn" khi có sự kiện `Record Invoice Receipt`/`Vendor creates invoice`;
  "tất toán" = `Clear Invoice` sau đó. Giữ hoá đơn lập 02/01/2018–17/01/2019. Hoá đơn chưa clear khi log kết thúc = **kiểm
  duyệt phải tự nhiên** (13,3%).
- **Thống kê**: số ngày từ nhận hoá đơn đến clear — phân vị 10/50/90/99 = 29 / 64 / 106 / 146 ngày (trung vị dài hơn nhiều so
  với hạn 30 ngày thông thường → quy trình duyệt lô).
- **Giới hạn**: phía **phải trả** của tập đoàn châu Âu (không phải phải thu SME VN); không có hạn thanh toán → dùng
  `due_date = issue_date`, đặc trưng "ngày tới hạn" mất tác dụng — kết quả ở BPI chủ yếu kiểm tra khả năng chịu miền
  khó, không phải bài toán chính.

### Customer Invoices (`customer_invoices/Dataset.csv`, 7,9 MB, bản sao GitHub của Kaggle pradumn203)
- **Là gì**: 50.000 dòng × 19 cột (dedupe còn 49.998), hoá đơn 14/12/2018–19/05/2020, USD 92,3%, CAD 7,7%; điều khoản kiểu SAP
  (NAA8, NAH4, CA10…); `clear_date` là ngày ghi sổ ERP.
- **Dấu hiệu "giống ERP thật"** (Phần 7 §6): khoảng đáo hạn cố định theo mã điều khoản; trả cuối tuần 0,34%; số tiền lệch
  phải (skew 2,99), gần Benford (MAD 0,0082); khách giải thích 46–60% phương sai trễ; Spearman 0,75 giữa hai nửa thời gian.
- **Dấu hiệu bị biến đổi**: tên khách thay ngẫu nhiên theo dòng (65,9% mã khách có >1 tên); 9,6% chưa đóng nhưng từ 3/2020
  gần như 100% "chưa đóng" (cột `isOpen` do người ra đề chia theo ngày).
- **Phân bố trễ (đã đóng)**: sớm 36,6%, đúng hạn 21,0%, trễ 1–30 ngày 40,2%, 31–60 ngày 1,7%, >60 ngày 0,5%.
  Ngắn hơn nhiều so với "một tháng" của Atradius VN → **không dùng để hiệu chỉnh độ trễ cho VN**.
- **Giới hạn**: nguồn gốc/giấy phép không rõ; không có nhãn vỡ nợ; không có sao kê; kết thúc ngay trước COVID.
  → Chỉ dùng để thử phương pháp và làm tham chiếu cấu trúc; không ghi là "dữ liệu thật của doanh nghiệp".

### SBA 7(a) (`sba/FOIA_7a_FY2010_FY2019.csv` 255 MB + `FOIA_7a_FY2020_Present.csv` 181 MB + từ điển dữ liệu)
- **Là gì**: toàn bộ khoản vay 7(a) được phê duyệt, trạng thái (PIF/CHGOFF/EXEMPT…), ngày xoá nợ, số tiền, lãi suất, kỳ hạn,
  NAICS, bang, loại hình DN, tuổi DN, có thế chấp, bán thứ cấp… (as-of 30/06/2026).
- **Chuẩn hoá**: loại CANCLD/COMMIT; chỉ giữ khoản phê duyệt ≥3 năm trước as-of để nhãn "xoá nợ trong 3 năm" không bị
  kiểm duyệt; 638.249 khoản; tỷ lệ dương 1,64%, thay đổi theo năm: 2,3% (FY2010) → 0,7–0,8% (FY2020–21, hỗ trợ COVID) → 2,8% (FY2023).
- **Chia theo thời gian**: train FY≤2016, hiệu chỉnh FY2017, test FY2018–2022.
- **Giới hạn**: cho vay chứ không phải hoá đơn B2B; Mỹ; nhãn thưa. Dùng để chứng minh **phần "nhạy cảm vỡ nợ" của mô hình
  chữa lành** và độ hiệu chỉnh xác suất hiếm (T2), không dùng làm số liệu nợ xấu cho VN.

### Berka PKDD'99 (`berka/*.asc`, 70 MB; bản sao GitHub jlacko)
- **Là gì**: 8 bảng của một ngân hàng Séc (1993–1998): 4.500 tài khoản, ~1 triệu giao dịch, 682 khoản vay.
- **Chuẩn hoá**: dòng ròng tuần/tài khoản; giữ tài khoản có ≥150 tuần → 1.478 tài khoản, 404.880 tài khoản-tuần
  (28/12/1992–28/12/1998); số dư cuối tuần.
- **Giới hạn**: nước khác, thập niên 1990, đa số cá nhân. Dùng để kiểm tra **độ phủ khoảng dự báo trên chuỗi dòng tiền thật**
  và thử bộ phát hiện điểm gãy; không để học hành vi trả hoá đơn.

### Online Retail II (`online_retail_ii/*.zip`, 46 MB; UCI, CC BY 4.0)
- **Là gì**: 1.067.371 dòng giao dịch của một nhà bán buôn/bán lẻ online Anh, 12/2009–12/2011.
- **Chuẩn hoá**: doanh thu tuần (đã trừ trả hàng) theo 12 quốc gia lớn + 60 khách lớn + tổng = 73 chuỗi × 106 tuần.
- **Giới hạn**: bán lẻ, không có thanh toán/công nợ, mùa vụ Giáng sinh thay vì Tết. Chỉ dùng cho T4 (và đánh giá mô hình
  nền tảng Chronos trên chuỗi thật).

### UK Payment Practices (`uk_ppr/payment_practices.csv`, 103 MB; OGL v3.0)
- **Là gì**: báo cáo 6 tháng của DN lớn Anh: thời gian trả trung bình, % hoá đơn trả trong 30/31–60/>60 ngày, % không trả
  đúng hạn, % không trả do tranh chấp, điều khoản.
- **Thống kê (trung vị các báo cáo)**: 33 ngày trả trung bình; 60% trong 30 ngày; 27% trong 31–60; 7% >60; 20% không đúng hạn.
  Tranh chấp: trung vị 0%, P90 0% (đa số báo cáo ghi 0 → tỷ lệ tranh chấp thật nằm ở đuôi; xem hạn chế).
- **Giới hạn**: tổng hợp theo công ty–kỳ, bên trả là DN lớn Anh. Dùng để kiểm tra họ phân phối, **không** làm đích hiệu chỉnh.

### OxCGRT (`oxcgrt/OxCGRT_compact_national_v1.csv`, 43 MB; CC BY 4.0)
- Chỉ số nghiêm ngặt trung bình của Việt Nam: 2,8 (1/2020) → 88,8 (4/2020) → ~58–78 (2020–2021) → 25,9 (6–12/2022).
  Máy phát chuyển thành "sốc kinh tế" = phần vượt ngưỡng 55 của chỉ số, nhân mức yêu cầu ở nhà (C6M).

### WDI Việt Nam (`wdi_vn/wdi_vietnam.csv`)
- 6 chỉ số: tăng trưởng GDP, lạm phát, lãi suất cho vay, tỷ giá, tín dụng tư nhân/GDP, GDP. Máy phát dùng lãi suất cho vay
  để tính lãi vay; còn lại dành cho kịch bản vĩ mô.

## 2.3 Bảng "dữ liệu thật → năng lực"

| Năng lực | Bộ thật | Cách dùng | Câu hỏi trả lời được |
|---|---|---|---|
| T1 thời điểm trả | Customer Invoices, BPI 2019 | Train/test theo thời gian, mốc B0/B1 | Phương pháp hazard có thắng mốc trên dữ liệu thật? |
| T2 nợ xấu | SBA 7(a) | Train FY≤2016, test FY2018–2022 | Xác suất hiếm có được hiệu chỉnh? PR-AUC? |
| T4 doanh thu mới | Online Retail II | Rolling-origin 26 tuần cuối | LightGBM/Chronos/mốc: ai thắng trên dữ liệu thật? |
| T6 khoảng dự báo | Berka | Dòng tiền ròng tuần → độ phủ khoảng | Khoảng có đạt độ phủ trên chuỗi tiền thật? (chưa chạy — kế hoạch 05) |
| T7 điểm gãy | Berka, OxCGRT | Phân đoạn/CUSUM trên chuỗi thật | Phát hiện thay đổi chế độ thật? (chưa chạy) |
| T12 độ trung thực | UK PPR, Customer Invoices | So dấu hiệu cấu trúc | Máy phát có "thật" hơn trọng số cố định? |
# Bổ sung đối chiếu công khai ngày 20/10/2026

Đã đọc BCTC chính chủ SMC 2024, TCM 2022 và NTP 2024 để kiểm tra DSO/DPO mô tả,
không hiệu chỉnh máy phát. Xem [phạm vi, trang nguồn và giới hạn mẫu](09_vn_listed_spot_check.md).
Ba DN-kỳ chưa đại diện ngành hoặc SME; BMP trả HTTP403, mẫu nhựa dùng NTP riêng.
Lệnh tải: `python scripts/crawl.py --only vn_listed_fy2024,vn_tcm_fy2022,vn_ntp_fy2024`;
lệnh đối chiếu: `python scripts/run_vn_listed_check.py`.

