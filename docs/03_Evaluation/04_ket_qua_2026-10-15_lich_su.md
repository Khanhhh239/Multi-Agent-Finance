> BẢN LỊCH SỬ: các số dưới đây đo trước sửa as-of/CDF; không dùng nghiệm thu hiện hành.

# 4. Kết quả đã đo (ngày 15/10/2026)

Nguồn số: `outputs/**/*.csv` (bảng đầy đủ tự sinh bằng `scripts/make_report.py` → `docs/RESULTS_TABLES.md`). Mọi kết quả ghi tầng bằng chứng:
**[Tổng hợp]** · **[Thật]** (dữ liệu thật tương tự, không phải SME VN).

> Kết quả [Tổng hợp] đo hệ thống xử lý được tình huống đã chèn, **không** chứng minh hiệu quả trên DN thật.
> Mọi so sánh dưới đây dùng cùng điểm cắt, cùng nhãn kiểm duyệt, cùng tập test.

## 4.1 T1 — Thời điểm trả, miền nguồn `src` (rolling-origin) [Tổng hợp]

Hai gốc: 2023-07-03 (test 76.324 snapshot-HĐ) và 2024-07-01 (68.425). Train nhãn kiểm duyệt tại gốc; hiệu chỉnh 63 ngày, cách test 120 ngày.

**Gốc 2024-07-01**

| Mô hình | MAE P50 | Pinball | cov80 | IS80 | IBS 13w | ECE@4w | C-index | WAPE thu 1–4 tuần | WAPE thu 5–13 |
|---|---|---|---|---|---|---|---|---|---|
| B0 đúng hạn | 35,5 | 17,76 | 0,04 | 355,2 | 0,279 | 0,327 | 0,522 | 1,135 | 0,836 |
| B1 trung vị khách | 34,1 | 17,03 | 0,05 | 340,5 | 0,267 | 0,303 | 0,538 | 1,080 | 0,790 |
| B1d phân vị khách | 34,1 | 14,36 | 0,61 | 260,1 | 0,243 | 0,191 | 0,536 | 1,011 | 0,750 |
| DH-LR | 19,3 | 6,18 | 0,85 | 88,7 | 0,132 | 0,029 | 0,731 | 0,507 | 0,759 |
| QLGBM | 27,6 | 9,93 | 0,61 | 159,9 | 0,177 | 0,088 | 0,688 | 0,569 | 0,832 |
| XGB-AFT | 16,6 | 6,44 | 0,49 | 110,1 | 0,123 | 0,076 | 0,783 | 0,639 | 0,782 |
| **DH-GBM** | **15,4** | **4,92** | 0,86 | **70,8** | **0,105** | **0,013** | 0,785 | **0,403** | **0,693** |
| ENS DH-GBM+QLGBM | 21,2 | 7,28 | 0,68 | 112,6 | 0,105* | 0,013* | 0,785* | 0,403* | 0,693* |
| AFT + CQR | 16,6 | 5,76 | 0,81 | 89,8 | 0,119 | 0,021 | 0,783 | 0,551 | 0,774 |

(*) IBS/ECE/C/WAPE của ENS lấy từ hazard (không đổi); chỉ phân vị thay đổi.

**Gốc 2023-07-03:** DH-GBM pinball 5,79 (B1 22,45), IBS 0,121 (0,345), WAPE 1–4 tuần 0,444 (1,408), cov80 0,885, ECE@4w 0,062.

**Kết luận T1 [Tổng hợp]:**
- DH-GBM giảm **pinball 71–74%**, **IBS 61–65%**, **WAPE dòng thu 4 tuần 63–68%** so với B1; thắng cả hồi quy phân vị, AFT, logistic hazard.
- B0 (đúng hạn) và B1 (trung vị) có cov80 chỉ 4–5% — **khoảng dự báo của bảng tính gần như không bao giờ đúng**.
- Hiệu chỉnh: cov80 0,86–0,89 (hơi thận trọng, vượt 85%) ⇒ G3/G4 "biên".
- CQR nâng cov80 của QLGBM/B1d/AFT từ 0,49–0,61 lên 0,79–0,85 nhưng **không** thay đổi hàng của DH-GBM (xem X2, 04_AI_Methods/02 §2.5).
- Ensemble với QLGBM **làm xấu** DH-GBM trên `src` (pinball 7,28 vs 4,92) nhưng tốt nhất trên dữ liệu thật AR (mục 4.2) ⇒ chọn ensemble theo miền, không mặc định.
- Caveat đo: WAPE/IBS của mô hình phân vị dùng CDF xấp xỉ từ 3 phân vị (thiên lợi cho hazard; X3).

Tính năng quan trọng: `dtd_k` ≫ `promised_in_k` > `c_payrun_strength` > `days_to_promised` > `due_in_k` (04_AI_Methods/02 §2.3). Lưu ý: tín hiệu lời hứa trong máy phát có thể quá mạnh.

## 4.2 T1 — Dữ liệu thật [Thật]

**Customer Invoices (AR giống ERP; train <2019-12-01, test 7.882 snapshot-HĐ đến 2020-01-23)**

| Mô hình | MAE P50 (ngày) | Pinball | cov80 | IBS 13w | C-index |
|---|---|---|---|---|---|
| B0 đúng hạn | 3,72 | 1,861 | 0,20 | 0,0333 | 0,764 |
| B1 trung vị khách | 2,77 | 1,386 | 0,28 | 0,0254 | 0,846 |
| B1d phân vị khách | 2,79 | 0,978 | 0,81 | 0,0252 | 0,845 |
| DH-GBM | 2,53 | 0,895 | 0,87 | 0,0163 | 0,837 |
| QLGBM | 2,34 | 0,855 | 0,60 | 0,0230 | 0,866 |
| DH-LR | 3,95 | 1,358 | 0,86 | 0,0265 | 0,757 |
| XGB-AFT (σ=0,6, trước sửa) | 17,2 | 5,60 | 0,24 | 0,154 | 0,751 |
| **ENS DH-GBM+QLGBM** | **2,29** | **0,819** | 0,84 | 0,0163 | 0,837 |

⇒ ensemble giảm **MAE 17%, pinball 41%, IBS 36%** so với B1 và cho cov80 0,84. (AFT đo trước khi sửa σ=0,3 — bảng sẽ cập nhật khi chạy lại.)

**BPI 2019 (P2P, không có hạn; 127.207 snapshot-HĐ test, data_end 2019-01-18)**

| Mô hình | MAE P50 | Pinball | cov80 | IBS |
|---|---|---|---|---|
| B0 | 40,5 | 20,27 | 0,00 | 0,345 |
| B1 | 13,95 | 6,98 | 0,05 | 0,120 |
| **B1d phân vị khách** | 14,00 | **5,07** | 0,69 | **0,102** |
| DH-LR | 15,3 | 5,24 | 0,86 | 0,116 |
| ENS DH-GBM+QLGBM | 15,5 | 5,10 | 0,72 | 0,184 |
| DH-GBM | 31,1 | 8,78 | 0,48 | 0,184 |
| QLGBM | 23,2 | 10,46 | 0,14 | 0,196 |

⇒ **Không thắng mốc B1d.** Nguyên nhân hợp lý: BPI không có hạn thanh toán, mất đặc trưng chủ lực (`dtd_k`), quy trình duyệt lô theo tác nhân. Đây là **kết quả xấu cần công bố** và là bằng chứng
phương pháp phụ thuộc vào có hạn thanh toán — điều kiện luôn đúng với hoá đơn B2B VN (HĐĐT có hạn) nhưng cần kiểm tra khi hạn thanh toán không ghi.

## 4.3 T2 — Cure / nợ xấu [Tổng hợp + Thật]

Bảng đầy đủ ở 04_AI_Methods/03 §3.1. Tóm tắt:
- [Tổng hợp] HĐ đã quá hạn (src tỷ lệ nợ xấu 31,9%): **Cure-GBM PR-AUC 0,965** (logistic 0,812, quy tắc TT48 0,603), Brier 0,048; tgt zero-shot PR-AUC 0,976, tổn thất kỳ vọng/thực 0,95.
- [Thật] SBA 7(a), FY2018–22 (n=223.259; nền 1,36%): LightGBM ROC-AUC 0,955, **PR-AUC 0,214 (15,7× nền)**, tổn thất kỳ vọng/thực 1,13 (isotonic: 1,02). Logistic: 0,840 / 0,057.
  *Cảnh báo:* nhãn `EXEMPT` (144.908 khoản y=0) và kỳ hạn dài chiếm 56% gain ⇒ AUC phóng đại; hiệu chỉnh theo năm lệch (FY2022: dự báo 0,92% vs thực 1,91%). Cổng G8 vì vậy **chưa kết luận** (X1).

## 4.4 T3 [Tổng hợp]
Lịch sử khách (EB) thắng LightGBM: tranh chấp AUC 0,668 vs 0,541; trả một phần AUC 0,718 vs 0,694 (04_AI_Methods/03 §3.2). Tiền thu/tiền HĐ trung bình 0,998 (2,6% HĐ thu <99,5%).

## 4.5 T4 — Doanh thu mới
Bảng ở 04_AI_Methods/04 §4.1. Tóm tắt: [Tổng hợp] LGBM+CQR thắng TB13 −4% (`src`), −10% (`tgt` zero-shot); [Thật] Online Retail II: Chronos-Bolt zero-shot tốt nhất (SPL 0,264), LGBM chỉ hơn TB13 khi tiền huấn luyện tổng hợp (0,2794 vs 0,2823). CQR đưa cov80 từ 0,67–0,79 lên 0,80–0,85.

## 4.6 T5, T0
15/15 kiểm thử đạt (hạn VAT tháng/quý, dịch Tết, TNDN tạm nộp/quyết toán, môn bài, lương tối thiểu vùng, VAT 8%/10%, MST, XML, cổng chất lượng ≥95%).

## 4.7 T7 [Tổng hợp]
Giữ lại (21 khách đủ điều kiện): CUSUM-PIT phát hiện 52,4% trong 180 ngày, lead 50 ngày, báo giả 0,63/khách-năm (cổng ≤0,5 ⇒ chưa đạt); Page–Hinkley 42,9%/0,42; BOCPD 9,5%/0,13 (04_AI_Methods/07 §7.1).

## 4.8 T9 [Tổng hợp]
F1 liên kết 0,689 (R1 0,632, R2 0,473); recall 0,616; precision 0,781 (quy tắc 0,99); sai số ngày trả 1,97 ngày so với 12,59 ngày của ngày ghi sổ ⇒ **giảm 84% sai số nhãn**; nhận đúng khách 95,3% giao dịch (04_AI_Methods/07 §7.2).

## 4.9 Thích nghi miền (thí nghiệm B) [Tổng hợp]

Nguồn: `outputs/t1/B_domain_adaptation_tgt.csv` — mô hình nguồn huấn luyện trên `src` đến 2024-07; đích `tgt` (14 công ty), test 52 tuần sau 2024-07-01; M = số tháng lịch sử đích nhìn thấy.

| M (tháng) | Mô hình | Pinball | cov80 | IBS | ECE@4w | WAPE thu 1–4 |
|---|---|---|---|---|---|---|
| 0 | B1 trung vị khách | 16,15 | 0,05 | 0,253 | 0,264 | 1,070 |
| 0 | **Zero-shot DH-GBM** | **6,42** | 0,82 | 0,131 | 0,030 | 0,465 |
| 3 | B1d phân vị khách | 18,46 | 0,21 | 0,299 | 0,346 | 1,415 |
| 3 | Zero-shot | 6,28 | 0,84 | 0,128 | 0,037 | 0,425 |
| 3 | TGT-only | 11,00 | 0,60 | 0,215 | 0,144 | 0,571 |
| 3 | POOLED / IW-POOLED | 6,44 | 0,83 | 0,131 | 0,052 | 0,432 |
| 3 | Fine-tune src→tgt | 6,83 | 0,78 | 0,138 | 0,038 | 0,418 |
| 6 | Zero-shot / Pooled / Fine-tune / TGT-only | 6,08 / 6,17 / 6,40 / 7,28 | 0,85 / 0,86 / 0,85 / 0,81 | | | |
| 12 | Zero-shot | 5,95 | 0,85 | 0,121 | 0,043 | 0,422 |
| 12 | **IW-POOLED** | **5,85** | 0,86 | 0,119 | 0,040 | 0,415 |
| 12 | POOLED | 5,87 | 0,86 | 0,119 | 0,043 | 0,418 |
| 12 | Fine-tune | 6,04 | 0,86 | 0,122 | 0,034 | 0,410 |
| 12 | TGT-only | 6,80 | 0,85 | 0,136 | 0,050 | 0,479 |
| 24 | Zero-shot / IW-POOLED / Pooled / Fine-tune / TGT-only | 5,99 / **5,86** / 5,85 / 6,01 / 6,55 | | | | |

**Kết luận (đọc trung thực):**
1. **Zero-shot đã rất mạnh**: pinball thấp hơn mốc B1 **60%** ngay tại M=0 (6,42 vs 16,15) và WAPE thu 4 tuần 0,465 vs 1,070 — nhờ đặc trưng bất biến miền và EB co về trung bình công ty. Miền đích tổng hợp chỉ lệch tham số vừa phải.
2. **Thích nghi chỉ mang lại cải thiện nhỏ**: tốt nhất IW-POOLED/POOLED chỉ hơn zero-shot **1,5–2%** (M=12–24). **Giả thuyết DA2 (fine-tune ≥10% tại M=3) bị bác bỏ** — fine-tune còn kém zero-shot (6,83 vs 6,28).
3. **TGT-only chỉ dùng được khi M≥12** và vẫn kém zero-shot (6,80 vs 5,95) — cần tiền huấn luyện. B1d với 3 tháng lịch sử rất tệ (cov80 0,21).
4. **CQR đích không thay đổi** (khoảng đã dư); IW-POOLED ≡ POOLED ở M=3–6 (trọng số mật độ gần 1 ⇒ ít covariate shift).
5. **Hàm ý**: giá trị thật của "domain adaptation" nằm ở *đặc trưng bất biến miền + tiền huấn luyện đa dạng*; tinh chỉnh chỉ có ích hơn khi miền đích lệch mạnh (cần `sens_*`, `hc_*`, Customer Invoices). Phải thử với miền lệch hơn trước khi kết luận chiến lược cuối (WP-3.3, 3.4).
6. Giới hạn: đích là tổng hợp cùng họ máy phát ⇒ có thể lạc quan (X21: src→Customer Invoices).

## 4.9b T8 và nguồn nhãn (thí nghiệm E/F) [Tổng hợp]

| Thí nghiệm | Mô hình | MAE P50 | MAE P50 (HĐ có lời hứa) | Pinball | IBS | WAPE thu 1–4 |
|---|---|---|---|---|---|---|
| T8 | DH-GBM **có** lời hứa | 15,41 | **11,33** | 4,92 | 0,105 | 0,405 |
| T8 | DH-GBM không lời hứa | 15,57 | 12,21 | 4,97 | 0,106 | 0,411 |
| T9 (nhãn) | huấn luyện bằng ngày **ngân hàng** | 15,41 | — | 4,92 | 0,105 | 0,405 |
| T9 (nhãn) | huấn luyện bằng ngày **sổ cái** | 15,89 | — | 5,09 | 0,108 | 0,429 |

- **T8**: lời hứa giảm MAE trên HĐ có lời hứa **7,2%** (12,21→11,33), toàn bộ chỉ −1% ⇒ **chưa đạt G17 (≥10%)**. Lời hứa tổng hợp rất sạch (σ=1,5 ngày); mức cải thiện thật có thể thấp hơn.
- **Nhãn sổ so với ngân hàng**: học từ ngày ghi sổ làm WAPE thu 4 tuần xấu hơn **5,9%** (0,429 vs 0,405), pinball +3,5% ⇒ **chưa đạt G18 (≥10%)**. Tác hại nhỏ hơn dự kiến vì hazard chủ yếu dựa vào `dtd_k`/nhịp trả; nhưng ngày trả dùng để đo hành vi khách và phát hiện điểm gãy vẫn lệch ~12,6 ngày. Tác hại lên T7/T6 chưa đo.

## 4.9c T6 — số dư 13 tuần, `tgt` 14 công ty × 52 điểm cắt [Tổng hợp]

Nguồn: `outputs/t6/*` (chạy 15/10). ρ chọn trên nguồn bằng interval score = **0,2** (lưới 0–0,5; IS 8,31 → 7,85). Số dư/khoảng chuẩn hoá theo chi tuần.

| Mô hình | Chân trời | cov80 | IS80 | Pinball | MAE P50 |
|---|---|---|---|---|---|
| **MC copula-t + ACI** | 1–4 | **0,794** | **5,22** | 0,352 | 1,07 |
| | 5–13 | **0,806** | 15,57 | 0,986 | 2,80 |
| MC copula-t (không ACI) | 1–4 | 0,701 | 5,17 | 0,351 | 1,07 |
| | 5–13 | 0,683 | 14,27 | 0,942 | 2,80 |
| MC độc lập (ρ=0) | 1–4 | 0,560 | 5,80 | 0,370 | 1,06 |
| | 5–13 | 0,598 | 15,39 | 0,979 | 2,80 |
| MC ngày điểm B1 | 1–4 | 0,187 | 20,47 | 1,099 | 2,50 |
| | 5–13 | 0,498 | 20,45 | 1,247 | 3,39 |
| LightGBM-Q trực tiếp | 1–4 | 0,574 | 7,25 | 0,472 | 1,38 |
| | 5–13 | 0,558 | 17,47 | 1,111 | 3,17 |
| Naive (chi biết + thu TB) | 1–4 | 0,699 | 7,05 | 0,464 | 1,37 |
| | 5–13 | 0,694 | 18,92 | 1,287 | 3,94 |

**Xác suất thiếu hụt** (số dư <0: 16,1% DN-tuần trong 4 tuần, 19,2% trong 13 tuần):

| Mô hình | Brier 4w | AUC 4w | Brier 13w | AUC 13w |
|---|---|---|---|---|
| **MC copula-t** | **0,014** | **0,998** | **0,033** | 0,983 |
| MC độc lập | 0,015 | 0,998 | 0,033 | 0,984 |
| LightGBM-Q trực tiếp | 0,018 | 0,986 | 0,046 | 0,921 |
| Naive | 0,022 | 0,990 | 0,041 | 0,982 |
| MC ngày điểm B1 | 0,047 | 0,929 | 0,061 | 0,936 |

**Đọc:**
- **ACI đưa cov80 về 0,79–0,81** (không ACI: 0,70 / 0,68) ⇒ đạt G12 về độ phủ. IS80 tốt hơn mọi đối chứng ở tuần 1–4; ở tuần 5–13 xấu hơn MC độc lập 1% (15,57 vs 15,39) nhưng tốt hơn trực tiếp (−11%) và naive (−18%) ⇒ **đạt biên**.
- **Phân phối T1 là yếu tố quyết định**: thay bằng ngày điểm B1 → IS80 ×4 (20,5 vs 5,2), cov80 0,19 ở tuần 1–4. Đây là bằng chứng kinh tế quan trọng nhất của dự án.
- **Sốc chung chủ yếu cải thiện độ phủ khoảng** (0,70 vs 0,56 ở tuần 1–4), **hầu như không cải thiện Brier** của P(thiếu hụt) (0,014 vs 0,015) trong thế giới này ⇒ giả thuyết "bỏ sốc chung đánh giá thấp rủi ro đuôi" chỉ được xác nhận một phần; sốc chung có thể yếu hơn thực tế (df=4, ρ=0,2).
- AUC 0,998 (4 tuần) rất cao vì số dư đầu kỳ và lịch chi biết trước có tín hiệu mạnh; phần khó là xác suất trung gian ⇒ cần đường hiệu chỉnh (reliability), **lead time và báo giả (G13 chưa đo)**.
- **Lỗi demo:** `t10_demo` ghi `P_shortfall_13w_base = 1,0` (không hợp lý) và lỗi mã hoá khi ghi `demo_whatif.json` (Windows cp1252) — chưa dùng được; sửa ở WP-6.1/6.3.

> **Cảnh báo giao thức:** các bảng A, B, E/F, T6 được tạo **trước** khi mã đo được chỉnh (as-of, CDF công bằng, bootstrap theo công ty) ở phiên tiếp theo (chiều 15/10; xem `outputs/t1/run_A_v2.log`, `scripts/make_report.py`). Bản v2 sơ bộ của A cho DH-GBM (gốc 2023-07): pinball 5,81, IBS 0,121, WAPE 0,464, cov80 0,866 — kết luận không đổi nhưng chi tiết khác nhẹ; bảng mới phải thay bảng cũ khi chạy xong.

## 4.10 Tóm lược "mô hình nào, bài nào"
| Bài toán | Mô hình chọn hiện tại | Bằng chứng | Điểm yếu |
|---|---|---|---|
| T1 | DH-GBM (src); ensemble DH-GBM+QLGBM (AR thật) | −63% WAPE; −17% MAE thật | BPI (không hạn); khoảng dư |
| T2 | Cure-GBM | PR-AUC 0,97 tổng hợp; 15,7× nền SBA | nhãn EXEMPT; hiệu chỉnh theo năm |
| T3 | EB lịch sử khách | thắng LGBM | phụ thuộc giả định máy phát |
| T4 | LGBM toàn cục + CQR; ensemble + Chronos | −10% (tgt) | thật: Chronos mạnh hơn |
| T5 | quy tắc | 100% | cập nhật luật |
| T7 | CUSUM-PIT | 52%/0,63 | báo giả cao hơn cổng |
| T9 | ML + (đề xuất lai quy tắc) | F1 0,69 | precision 0,78 |


## 4.11 Kết quả triển khai sinh từ CSV

