# 8. Tài liệu tham khảo cho dữ liệu và máy phát

Phân loại: **[T]** = đã đọc kỹ nguồn gốc trong Phần 5/7; **[S]** = chỉ đọc tóm tắt/số tự báo cáo; **[R]** = dùng làm
tham chiếu phương pháp, chưa đọc toàn văn trong phiên này (cần đọc trước khi trích dẫn trong báo cáo chính thức).

## 8.1 Số liệu hiệu chỉnh

| Nguồn | Dùng cho | Loại |
|---|---|---|
| [Atradius, Payment Practices Barometer — Vietnam 2025](https://atradius.be/dam/jcr:c118f442-fed0-4104-a74a-bce847d3c2e4/payment-practices-barometer-asia-2025-vietnam-en.pdf) | Đích: bán chịu 65%, kỳ hạn 45, quá hạn 39%, nợ xấu 3%, theo ngành; nguyên nhân trễ | [T] |
| [Coface Asia Payment Survey 2025 (VIR)](https://vir.com.vn/asia-firms-see-payment-delays-worsening-in-2025-coface-survey-130281.html) | Đuôi trễ cực dài, tham số nhạy cảm | [S] |
| [UK Payment Practices Reporting](https://check-payment-practices.service.gov.uk/export/) | Họ phân phối trễ, tranh chấp (kiểm tra độc lập) | [T] |
| [Xero Small Business Insights — methodology](https://www.xero.com/uk/resources/small-business-insights/methodology/) | Minh hoạ thiên lệch người sống sót | [T] |
| [JPMorgan Chase Institute — Cash Flows, Balances, Buffer Days](https://www.jpmorganchase.com/institute/all-topics/business-growth-and-entrepreneurship/report-cash-flows-balances-and-buffer-days) | Phân bố đệm tiền mặt đầu kỳ | [T] |
| [OxCGRT](https://github.com/OxCGRT/covid-policy-tracker) | Sốc COVID VN | [T] |
| Luật Quản lý thuế 38/2019/QH14 (Đ.44, 55); NĐ 126/2020; NĐ 293/2025; NQ 198/2025/QH15; NQ giảm VAT; TT 48/2019 | Lịch nghĩa vụ, khung dự phòng | [S] nguồn thứ cấp — đối chiếu văn bản gốc |

## 8.2 Paper về dự báo thời điểm thanh toán hoá đơn (miền bài toán)

| Paper | Ý chính liên quan | Dùng ở | Loại |
|---|---|---|---|
| Saini et al. 2024, *Invoice level forecasting with discrete survival methods*, Discover Analytics ([link](https://link.springer.com/article/10.1007/s44257-024-00013-2)) | Hazard rời rạc để dự báo thời gian thanh toán HĐ phục vụ dòng tiền | Cơ sở T1 | [S] tóm tắt |
| Zeng et al. 2008, *Using predictive analysis to improve invoice-to-cash collection* (KDD, IBM) ([pdf](https://prem-melville.com/publications/equitant-kdd08.pdf)) | Phân lớp trễ 4 nhóm (đúng hạn, 1–30, 31–60, >60); thực tế thu hồi | Nhóm trễ trong fidelity | [S] |
| Appel et al. 2019, *Optimize Cash Collection* ([arXiv:1912.10828](https://arxiv.org/abs/1912.10828)); *Predicting Account Receivables with ML* ([arXiv:2008.07363](https://arxiv.org/abs/2008.07363)) | Mô hình phân lớp trễ, số liệu tự báo cáo 77–81% | Đối chiếu ý tưởng, không so số | [S] |
| Cluee 2025 ([arXiv:2511.03631](https://arxiv.org/pdf/2511.03631)) | Hệ thống tài chính SME tự do nhiều mô-đun | Kiến trúc tham chiếu | [S] |
| Singer & Willett 1993, *It's About Time* (JEBS) | Hazard rời rạc ước lượng bằng logistic trên dữ liệu khai triển | T1 | [R] |
| Tong, Mues & Thomas 2012, *Mixture cure models in credit scoring* (EJOR) | Tách "có vỡ nợ" và "khi nào" | T2 | [R] |

## 8.3 Phương pháp sinh dữ liệu và đánh giá tổng hợp

| Chủ đề | Tham chiếu | Ý dùng |
|---|---|---|
| Tác tử/agent-based simulation cho tài chính doanh nghiệp | Mô hình ABM của thanh toán thương mại | Cấu trúc nhân quả L0–L5 |
| Đánh giá dữ liệu tổng hợp bảng | Train-on-Synthetic-Test-on-Real (TSTR) | Quy tắc "huấn luyện tổng hợp – kiểm tra thật" |
| Đo độ trung thực | Khoảng cách Wasserstein/KS biên, bộ phân loại phân biệt thật–giả (C2ST) | Kiểm thử chuẩn (kế hoạch WP-D3) |
| Chữ ký "bộ sinh phẳng" | Benford, đếm theo tháng/ngày trong tuần, tỷ lệ tròn số | `realism_audit.py` (Phần 7) |
| Nhiều thế giới / miền | Domain randomization | Tham số đuôi, ghi sổ, memo thay đổi theo thế giới |
| Hoán đổi/thay đổi miền | Shimodaira 2000 (importance weighting); Bickel et al. 2009 | Thích nghi miền (04_AI_Methods/05) |

## 8.4 Bộ chuẩn dự báo

| Nguồn | Dùng |
|---|---|
| Makridakis et al., *M5 accuracy and uncertainty competitions* (IJF 2022) | SPL/WSPL chuẩn hoá, kết quả "LightGBM thắng" (retail, không phải dòng tiền) |
| Ansari et al. 2024, *Chronos* ([arXiv:2403.07815](https://arxiv.org/abs/2403.07815)); Chronos-Bolt | Mô hình nền tảng chuỗi thời gian zero-shot (dùng ở T4) |
| Romano, Patterson & Candès 2019 (CQR) ([arXiv:1905.03222](https://arxiv.org/abs/1905.03222)); Gibbs & Candès 2021 (ACI) ([arXiv:2106.00170](https://arxiv.org/abs/2106.00170)) | Hiệu chỉnh khoảng |
| Adams & MacKay 2007 (BOCPD) ([arXiv:0710.3742](https://arxiv.org/abs/0710.3742)); Truong et al. (ruptures) ([arXiv:1801.00826](https://arxiv.org/abs/1801.00826)) | T7 |

Những paper nhánh `agent1-Thắng` (thư mục `docs/*.pdf`: CQR, discrete-time survival, LightGBM, MIPP, predicting late
payment, regression quantiles, shock market) cũng là nguồn đọc thêm cùng hướng.
