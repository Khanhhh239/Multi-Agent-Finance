# 1. Chỉ số kỹ thuật

Mã chỉ số: `agent1/eval/metrics.py`. Nguyên tắc: **đo phân phối, không chỉ điểm**; đo theo **kết quả người dùng thấy**
(dòng thu theo tuần, số dư, cảnh báo), không chỉ sai số từng hoá đơn.

## 1.1 T1 — thời điểm trả (phân phối theo tuần)

| Chỉ số | Công thức | Vì sao dùng | Đọc thế nào |
|---|---|---|---|
| **Pinball loss** (q=0,1/0,5/0,9) | `mean(max(q·e, (q−1)·e))`, `e = y − ŷ_q`; `y = min(số ngày còn lại, 120)` | Quy tắc chấm điểm phù hợp cho phân vị; chỉ số cuộc thi M5 | Thấp tốt; so mốc cùng đơn vị ngày |
| **MAE P50** | `mean|y − ŷ_0,5|` | Dễ hiểu | Bị đuôi (nợ xấu cap 120) kéo; dùng kèm pinball |
| **Độ phủ khoảng 80% (cov80)** | `P(ŷ_0,1 ≤ y ≤ ŷ_0,9)` | Hiệu chỉnh | Đích 80%, chấp nhận 75–85% |
| **Interval score 80%** | `(hi−lo) + (2/α)(lo−y)·1[y<lo] + (2/α)(y−hi)·1[y>hi]` | Phạt cả khoảng rộng lẫn trượt | Thấp tốt |
| **IBS 13 tuần** | `mean_k mean_i ( 1[y_i ≤ 7k] − F̂_i(7k) )²` | Chấm toàn bộ đường CDF theo tuần — đúng đầu vào của Monte Carlo | Thấp tốt |
| **Brier / ECE @4 tuần** | `P(trả trong ≤28 ngày)` so nhãn; ECE 10 bin | Độ hiệu chỉnh xác suất | ECE ≤0,05 |
| **C-index** | tỷ lệ cặp (i trả sớm hơn j) được xếp đúng; lấy mẫu 400k cặp | Xếp hạng ưu tiên đòi nợ | >0,5 tốt hơn ngẫu nhiên |
| **WAPE dòng thu theo tuần** | `Σ|thực − dự báo| / Σ thực` của `số tiền mở × P(trả tuần k)` cộng theo (công ty, ngày cắt), tuần 1–4 và 5–13 | **Con số kinh tế gần nhất**: sai số dòng thu mà CFO nhìn | Thấp tốt; mốc B1 |

**Lưu ý đo (trung thực):** với mô hình chỉ cho 3 phân vị (B0, B1, QLGBM, AFT) CDF theo tuần được nội suy từ 3 phân vị
(`weekly_cdf_from_quantiles`) — đây là xấp xỉ thô, **thiên lợi cho mô hình hazard** ở IBS và WAPE. So sánh công bằng
nhất ở các chỉ số phân vị (pinball, MAE, cov80, IS80).

## 1.2 T2 — nợ xấu / cure

| Chỉ số | Ghi chú |
|---|---|
| PR-AUC (ưu tiên vì lớp hiếm), ROC-AUC | tỷ lệ nền 1–4% |
| Brier, log-loss, ECE | hiệu chỉnh |
| **Tổn thất kỳ vọng / thực tế** `Σ p·amt / Σ y·amt` | gần 1 là tốt; đo theo FY/danh mục |
| Calibration theo năm tài khoản | ổn định dưới trôi (SBA: tỷ lệ nền 0,7%→2,8%) |

## 1.3 T3 — tranh chấp, trả một phần
AUC, Brier; MAE tỷ lệ thu `paid/invoiced`; tổng tiền kỳ vọng thu so thực.

## 1.4 T4 — doanh thu mới
**SPL** = pinball trung bình 3 phân vị chia thang `mean|Δy|` trong mẫu (kiểu M5); cov80; WAPE P50; tách chân trời 1–4 / 5–13 tuần.

## 1.5 T5 — lịch nghĩa vụ
Đúng/sai theo ví dụ trong văn bản (kiểm thử đơn vị) — nhị phân, cần 100%.

## 1.6 T6 — số dư 13 tuần
| Chỉ số | Công thức / cách đo |
|---|---|
| cov80 theo tuần k và gộp | khoảng [P10, P90] của mô phỏng chứa số dư thật |
| Interval score (chuẩn hoá chi tuần) | `y,lo,hi` chia chi tuần trung bình để so giữa công ty |
| CRPS từ mẫu | `E|X−y| − ½E|X−X'|` |
| **P(thiếu hụt)**: Brier & AUC | sự kiện "số dư <0 trong 4 / 13 tuần tới" |
| **Lead time** | số tuần từ lần đầu P(thiếu hụt) ≥ ngưỡng đến lúc thiếu hụt thật |
| Báo giả / DN-năm | cảnh báo mà không có thiếu hụt trong 13 tuần sau |
| Độ phủ ACI theo thời gian | cov80 trượt 12 tuần — phát hiện trôi |

## 1.7 T7 — điểm gãy
Tỷ lệ phát hiện trong 180 ngày (chỉ tính khách còn ≥5 lần trả sau điểm gãy), độ trễ phát hiện (trung vị), **báo giả /
khách-năm** (tách báo động trong giai đoạn sốc vĩ mô — là thay đổi thật).

## 1.8 T8 — lời hứa
Giảm MAE P50 trên hoá đơn có lời hứa so với mô hình không dùng; độ hiệu chỉnh độ tin cậy lời hứa (Brier của "giữ lời").

## 1.9 T9 — khớp sao kê
Link precision/recall/F1 trên cặp (giao dịch, hoá đơn); `txn_customer_recall`; **sai số ngày trả ước lượng** so ngày tiền về thật
(đối chiếu với sai số của ngày ghi sổ); tỷ lệ khớp nhầm giao dịch nhiễu.

## 1.10 T10 — giải thích & khuyến nghị
Độ ổn định xếp hạng (Spearman giữa các seed MC); **mô phỏng chính sách** "đòi K khoản đầu": giảm P(thiếu hụt) / giảm DSO so
với "đòi khoản to nhất" và "không làm gì"; tỷ lệ lý do SHAP được chuyên gia (kế toán) gật đầu (UAT).

## 1.11 Chỉ số vận hành (MLOps)
PSI của `c_delay_ewm` hàng tuần (retrain nếu >0,1); độ phủ ACI trượt; thời gian chạy batch/DN; tỷ lệ dữ liệu không qua cổng chất lượng; độ trễ dữ liệu.

## 1.12 Phân tầng bắt buộc khi báo cáo
Theo `c_n_hist` (khách mới <3 HĐ / quen), kích cỡ HĐ (top 10% giá trị), kỳ hạn, ngành, giai đoạn (bình thường / quanh Tết /
sốc COVID / đóng băng tín dụng), `posting_mode`, `tail` (atradius/uk/coface). Công bố **nhóm tệ nhất**.

## 1.13 Kiểm định thống kê
Bootstrap theo **công ty** (cụm) 300 lần cho CI 95%; so sánh mô hình bằng chênh lệch cặp trên cùng điểm cắt; không tuyên bố
"tốt hơn" nếu CI của hiệu chứa 0.
