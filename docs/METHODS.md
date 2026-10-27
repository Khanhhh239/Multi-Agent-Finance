# Agent 1 — Lựa chọn mô hình và phương pháp theo từng nhiệm vụ T

> **Bản đồ phương pháp theo thiết kế giai đoạn đầu.** Tên “phương pháp chính”
> không bảo đảm nhánh đó đang chạy trong dịch vụ hoặc đã đạt cổng. Đối chiếu
> [kết quả từ CSV](03_Evaluation/04_ket_qua_hien_co.md),
> [cổng hiện hành](03_Evaluation/GATES_CURRENT.md) và mã trước khi tái dùng.

Nguyên tắc chọn (T11): mỗi mô hình phải thắng mốc đơn giản trên **tập kiểm tra theo thời gian**; đo **phân phối**
(pinball, độ phủ, IBS, Brier/ECE) chứ không chỉ điểm; tách ba tầng kết luận; công bố cả kết quả xấu.

| T | Bài toán | Phương pháp chính (lý do) | Đối chứng bắt buộc | Mã |
|---|---|---|---|---|
| T0 | Lược đồ chuẩn, khớp sổ | Quy tắc: MST checksum, cộng tiền, ngày, trùng khoá; parser XML QĐ 1450/1510 | — | `agent1/data/schema.py`, `synth/einvoice.py` |
| T1 | Thời điểm trả từng hoá đơn | **Hàm nguy cơ thời gian rời rạc bằng LightGBM trên dữ liệu khai triển (hoá đơn × tuần), landmarking** + biến lịch biết trước theo tuần + conformal (CQR) | B0 đúng hạn, B1 trung vị khách, B1d phân vị khách, QLGBM, XGBoost-AFT, logistic hazard | `models/t1.py`, `models/features.py` |
| T2 | Không bao giờ trả (nợ xấu) | **Cure classifier LightGBM** (phần "nhạy cảm" của mixture cure, Tong–Mues–Thomas 2012) + isotonic | Quy tắc tuổi nợ TT48/2019, logistic, tỷ lệ nền | `models/t1.py::CureGBM`, `scripts/run_t2_t3.py` |
| T3 | Tranh chấp, trả một phần | LightGBM trên lịch sử khách co về trung bình (EB) | tỷ lệ nền, tỷ lệ lịch sử khách | `scripts/run_t2_t3.py` |
| T4 | Doanh thu mới | **LightGBM phân vị toàn cục, trực tiếp đa chân trời, chuẩn hoá quy mô** (+ tiền huấn luyện tổng hợp) + **Chronos-Bolt** zero-shot, ensemble | naive mùa vụ, trung bình 13 tuần | `models/t4_revenue.py` |
| T5 | Chi cố định, lịch nghĩa vụ | Bộ máy quy tắc có ngày hiệu lực (Luật QLT 38/2019, NĐ 126/2020, NĐ 293/2025, NQ giảm VAT, NQ 198/2025) | kiểm thử theo ví dụ văn bản | `calendar_vn.py`, `tests/` |
| T6 | Số dư 13 tuần, xác suất thiếu hụt | **Monte Carlo copula-t một nhân tố** (sốc thanh khoản chung đuôi dày) trên phân phối T1 + T4 + T5, **ACI** (conformal thích ứng, Gibbs & Candès 2021); ρ chọn trên miền nguồn | MC độc lập, MC ngày điểm B1, LightGBM phân vị trực tiếp, naive | `models/t6_cash.py`, `scripts/run_t6.py` |
| T7 | Điểm gãy hành vi | **CUSUM trên phần dư PIT** (hạng thực nghiệm → chuẩn tắc, bền với phân phối hai đỉnh), Page–Hinkley, BOCPD; ngưỡng chỉnh trên nguồn, đánh giá trên đích | trung bình trượt ngây thơ, CUSUM-MAD | `models/t7_changepoint.py` |
| T8 | Lời hứa trả | Beta-Binomial độ tin cậy theo khách (co về tiền nghiệm Beta(4,2)) đưa vào hazard (biến "lời hứa rơi vào tuần k") | DH-GBM không có lời hứa | `features.py`, `run_t1.py exp E` |
| T9 | Khớp sao kê | Sinh ứng viên (RapidFuzz trên tên bỏ dấu/tiền tố pháp lý + số HĐ trong nội dung + số tiền) → **LightGBM chấm điểm** (học ở nguồn) → phân bổ theo thời gian với số dư còn lại + subset-sum | R1 đúng số tiền, R2 regex số HĐ; ngày ghi sổ | `models/t9_recon.py` |
| T10 | Giải thích, khuyến nghị | SHAP (LightGBM `pred_contrib`) cho hazard; xếp hạng HĐ theo **mức giảm P(thiếu hụt) khi thu sớm** (chạy lại MC); kịch bản "nếu như" | — | `run_t6.py::t10_demo` |
| T11 | Đánh giá | rolling-origin, kiểm duyệt nhãn tại ngày cắt, bootstrap theo công ty | — | `eval/metrics.py` |
| T12 | Máy phát | mô phỏng tác tử có nhân tố chung, hiệu chỉnh vòng lặp theo Atradius | — | `synth/` |

## Vì sao những lựa chọn này là "đúng bài toán"

1. **Kiểm duyệt là bản chất của T1.** Tại thời điểm dự báo, hoá đơn gần nhất chưa trả — chính là dữ liệu quý nhất
   về hành vi hiện tại. Hồi quy phân vị (QLGBM) chỉ học được từ hoá đơn đã đóng → thiên lệch về phía trả nhanh
   (Xero cũng công bố cận dưới vì lý do này). Hazard rời rạc dùng được mọi tuần đã quan sát của mọi hoá đơn
   (Singer & Willett 1993), cho trực tiếp **phân phối theo tuần** — đúng đầu vào mà Monte Carlo T6 cần.
2. **Landmarking + biến biết trước theo tuần.** Đặc trưng đóng băng tại ngày cắt (chống rò rỉ), còn các biến lịch
   của tuần k (hạn rơi vào tuần k, ngày chạy thanh toán quen thuộc của khách rơi vào tuần k, số ngày làm việc,
   Tết, lời hứa rơi vào tuần k) là thông tin tất định biết trước — đây là chỗ mô hình vượt trội baseline.
3. **Bất biến miền** để chuyển giao từ tổng hợp → doanh nghiệp thật: mọi đặc trưng tính theo ngày tương đối hạn,
   số tiền chia trung vị của chính công ty, thống kê khách co về trung bình công ty (empirical Bayes).
   Thích nghi miền: (a) zero-shot, (b) chỉ dữ liệu đích, (c) gộp có trọng số, (d) **tiếp tục boosting
   (fine-tune) từ mô hình nguồn**, (e) **trọng số tỷ lệ mật độ** bằng bộ phân loại miền (Shimodaira 2000).
   Bối cảnh VN: hoá đơn điện tử bắt buộc từ 07/2022 nên DN mới onboard thường có 1–3 năm lịch sử tải từ cổng
   GDT — thí nghiệm B đo đúng tình huống này (0/3/6/12/24 tháng).
4. **Rủi ro tương quan.** Giả định khách trả độc lập đánh giá thấp xác suất thiếu hụt; copula-t một nhân tố đưa vào
   sốc thanh khoản chung có đuôi dày, ρ được chọn bằng interval score trên miền nguồn, không đặt tay.
5. **Độ phủ dưới trôi phân phối.** CQR (Romano 2019) cho T1/T4; ACI (Gibbs & Candès 2021) cho T6 vì chuỗi điểm cắt
   theo thời gian vi phạm giả định hoán đổi được.
6. **Nhãn đúng trước mô hình đúng (T9).** Ngày ghi sổ theo lô sai lệch ~12 ngày so với ngày tiền về; học từ sổ cái
   làm mô hình học hành vi của kế toán thay vì của khách (thí nghiệm F đo ảnh hưởng này).

## Đã cân nhắc nhưng không chọn làm chính

- **DeepHit / mạng nơ-ron sống sót**: dữ liệu bảng cỡ vừa, GBDT thường mạnh hơn và giải thích được (SHAP); để dành.
- **TabPFN v2**: hạn chế số dòng ngữ cảnh và trọng số có điều khoản; chưa phù hợp hàng triệu dòng khai triển.
- **Chronos cho T1**: không phải chuỗi thời gian; dùng Chronos-Bolt cho T4 (chuỗi doanh thu) — và báo cáo trung thực
  nơi nó thắng (dữ liệu thật Online Retail II).
