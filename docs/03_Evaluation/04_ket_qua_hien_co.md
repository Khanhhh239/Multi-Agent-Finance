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

<!-- AUTO:IMPLEMENTATION_RESULTS -->

## T1-A rolling-origin, miền nguồn src

Nguồn: `outputs/t1/A_rolling_origin_src.csv`

CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.

| setting | model | MAE_p50 | pinball_avg | cov80 | IS80 | IBS_13w | ECE_4w | C_index | WAPE_collect_w1_4 | WAPE_collect_w5_13 |
|---|---|---|---|---|---|---|---|---|---|---|
| A_src_origin_2023-07-03 | B0-due | 46.2 | 23.1 | 0.0330 | 462.2 | 0.3559 | 0.4088 | 0.4690 | 1.5037 | 0.7689 |
| A_src_origin_2023-07-03 | B1-cust-median | 44.9 | 22.4 | 0.0467 | 448.9 | 0.3448 | 0.3875 | 0.4791 | 1.4075 | 0.7655 |
| A_src_origin_2023-07-03 | B1d-cust-quantiles | 45.0 | 19.6 | 0.5052 | 363.5 | 0.3178 | 0.2811 | 0.4766 | 1.3226 | 0.7081 |
| A_src_origin_2023-07-03 | DH-GBM | 19.5 | 5.7917 | 0.8852 | 76.5 | 0.1208 | 0.0615 | 0.7860 | 0.4438 | 0.6995 |
| A_src_origin_2023-07-03 | DH-LR | 22.2 | 6.7852 | 0.8590 | 92.5 | 0.1402 | 0.0415 | 0.7520 | 0.5160 | 0.7339 |
| A_src_origin_2023-07-03 | QLGBM | 35.7 | 13.7 | 0.5358 | 232.7 | 0.2280 | 0.1113 | 0.6287 | 0.6469 | 0.8554 |
| A_src_origin_2023-07-03 | AFT | 21.8 | 8.2977 | 0.4607 | 140.1 | 0.1489 | 0.1032 | 0.7725 | 0.6711 | 0.8694 |
| A_src_origin_2023-07-03 | ENS DH-GBM+QLGBM | 26.6 | 9.4030 | 0.6089 | 149.0 | 0.1208 | 0.0615 | 0.7860 | 0.4438 | 0.6995 |
| A_src_origin_2023-07-03 | B1d-cust-quantiles+CQR | 45.0 | 12.6 | 0.7937 | 152.3 | 0.2409 | 0.1600 | 0.4766 | 1.1642 | 0.7908 |
| A_src_origin_2023-07-03 | DH-GBM+CQR | 19.5 | 5.7917 | 0.8852 | 76.5 | 0.1208 | 0.0615 | 0.7860 | 0.4438 | 0.6995 |
| A_src_origin_2023-07-03 | QLGBM+CQR | 35.7 | 11.2 | 0.7945 | 157.8 | 0.2108 | 0.1029 | 0.6287 | 0.7676 | 0.8162 |
| A_src_origin_2023-07-03 | AFT+CQR | 21.8 | 7.1010 | 0.8269 | 104.2 | 0.1399 | 0.0458 | 0.7725 | 0.5944 | 0.8197 |
| A_src_origin_2023-07-03 | ENS DH-GBM+QLGBM+CQR | 26.6 | 8.4315 | 0.7984 | 119.9 | 0.1208 | 0.0615 | 0.7860 | 0.4438 | 0.6995 |
| A_src_origin_2024-07-01 | B0-due | 35.5 | 17.8 | 0.0407 | 355.2 | 0.2788 | 0.3268 | 0.5221 | 1.1346 | 0.8356 |
| A_src_origin_2024-07-01 | B1-cust-median | 34.1 | 17.0 | 0.0528 | 340.5 | 0.2667 | 0.3032 | 0.5384 | 1.0800 | 0.7897 |
| A_src_origin_2024-07-01 | B1d-cust-quantiles | 34.1 | 14.4 | 0.6051 | 260.1 | 0.2429 | 0.1912 | 0.5360 | 1.0114 | 0.7498 |
| A_src_origin_2024-07-01 | DH-GBM | 15.4 | 4.9221 | 0.8575 | 70.8 | 0.1045 | 0.0133 | 0.7845 | 0.4030 | 0.6934 |
| A_src_origin_2024-07-01 | DH-LR | 19.3 | 6.1785 | 0.8452 | 88.7 | 0.1318 | 0.0293 | 0.7306 | 0.5069 | 0.7589 |
| A_src_origin_2024-07-01 | QLGBM | 27.6 | 9.9301 | 0.6082 | 159.9 | 0.1765 | 0.0883 | 0.6877 | 0.5691 | 0.8320 |
| A_src_origin_2024-07-01 | AFT | 16.6 | 6.4401 | 0.4891 | 110.1 | 0.1231 | 0.0760 | 0.7825 | 0.6387 | 0.7822 |
| A_src_origin_2024-07-01 | ENS DH-GBM+QLGBM | 21.2 | 7.2843 | 0.6801 | 112.6 | 0.1045 | 0.0133 | 0.7845 | 0.4030 | 0.6934 |
| A_src_origin_2024-07-01 | B1d-cust-quantiles+CQR | 34.1 | 10.9 | 0.8518 | 157.0 | 0.2129 | 0.1393 | 0.5360 | 0.9552 | 0.8450 |
| A_src_origin_2024-07-01 | DH-GBM+CQR | 15.4 | 4.9221 | 0.8575 | 70.8 | 0.1045 | 0.0133 | 0.7845 | 0.4030 | 0.6934 |
| A_src_origin_2024-07-01 | QLGBM+CQR | 27.6 | 8.8339 | 0.8434 | 127.0 | 0.1759 | 0.1223 | 0.6877 | 0.6878 | 0.8512 |
| A_src_origin_2024-07-01 | AFT+CQR | 16.6 | 5.7610 | 0.8130 | 89.8 | 0.1186 | 0.0208 | 0.7825 | 0.5508 | 0.7743 |
| A_src_origin_2024-07-01 | ENS DH-GBM+QLGBM+CQR | 21.2 | 6.8742 | 0.8421 | 100.3 | 0.1045 | 0.0133 | 0.7845 | 0.4030 | 0.6934 |

## T1-B domain adaptation, miền đích tgt (onboard 2024-07)

Nguồn: `outputs/t1/B_domain_adaptation_tgt.csv`

CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.

| months_history | model | MAE_p50 | pinball_avg | cov80 | IBS_13w | ECE_4w | WAPE_collect_w1_4 | WAPE_collect_w5_13 |
|---|---|---|---|---|---|---|---|---|
| 0 | B1-cust-median | 32.3 | 16.1 | 0.0501 | 0.2531 | 0.2641 | 1.0697 | 0.6771 |
| 0 | SRC-only DH-GBM (zero-shot) | 20.9 | 6.4161 | 0.8207 | 0.1305 | 0.0303 | 0.4648 | 0.6124 |
| 0 | SRC-only QLGBM | 25.5 | 8.4690 | 0.6637 | 0.1573 | 0.0408 | 0.5466 | 0.7268 |
| 3 | B1-cust-median | 34.3 | 17.1 | 0.0492 | 0.2672 | 0.2834 | 1.1135 | 0.6423 |
| 3 | B1d-cust-quantiles | 38.9 | 18.5 | 0.2140 | 0.2988 | 0.3460 | 1.4148 | 0.6972 |
| 3 | SRC-only DH-GBM (zero-shot) | 20.9 | 6.2770 | 0.8382 | 0.1283 | 0.0365 | 0.4253 | 0.5638 |
| 3 | SRC-only QLGBM | 27.0 | 8.9998 | 0.6570 | 0.1653 | 0.0487 | 0.5207 | 0.7042 |
| 3 | TGT-only DH-GBM | 33.8 | 11.0 | 0.6041 | 0.2150 | 0.1441 | 0.5708 | 0.6888 |
| 3 | POOLED (tgt-upweighted) | 21.4 | 6.4427 | 0.8290 | 0.1314 | 0.0518 | 0.4321 | 0.5721 |
| 3 | FINE-TUNE src->tgt | 22.0 | 6.8249 | 0.7754 | 0.1377 | 0.0376 | 0.4176 | 0.5756 |
| 3 | IW-POOLED (density-ratio) | 21.4 | 6.4427 | 0.8290 | 0.1314 | 0.0518 | 0.4321 | 0.5721 |
| 6 | B1-cust-median | 38.7 | 19.4 | 0.0460 | 0.2988 | 0.3181 | 1.2119 | 0.6508 |
| 6 | B1d-cust-quantiles | 41.2 | 18.1 | 0.4121 | 0.2960 | 0.2968 | 1.2868 | 0.6433 |
| 6 | SRC-only DH-GBM (zero-shot) | 20.6 | 6.0831 | 0.8528 | 0.1239 | 0.0445 | 0.4249 | 0.5642 |
| 6 | SRC-only QLGBM | 29.9 | 9.8927 | 0.6260 | 0.1760 | 0.0621 | 0.5256 | 0.7063 |
| 6 | TGT-only DH-GBM | 24.5 | 7.2793 | 0.8087 | 0.1455 | 0.0377 | 0.4693 | 0.6118 |
| 6 | POOLED (tgt-upweighted) | 20.9 | 6.1722 | 0.8549 | 0.1254 | 0.0467 | 0.4175 | 0.5589 |
| 6 | FINE-TUNE src->tgt | 22.1 | 6.3986 | 0.8502 | 0.1307 | 0.0403 | 0.4258 | 0.5657 |
| 6 | IW-POOLED (density-ratio) | 20.9 | 6.1722 | 0.8549 | 0.1254 | 0.0467 | 0.4175 | 0.5589 |
| 6 | FINE-TUNE src->tgt+CQR | 22.1 | 6.3986 | 0.8502 | 0.1307 | 0.0403 | 0.4258 | 0.5657 |
| 6 | POOLED (tgt-upweighted)+CQR | 20.9 | 6.1722 | 0.8549 | 0.1254 | 0.0467 | 0.4175 | 0.5589 |
| 12 | B1-cust-median | 41.8 | 20.9 | 0.0439 | 0.3201 | 0.3407 | 1.2738 | 0.6340 |
| 12 | B1d-cust-quantiles | 44.0 | 18.6 | 0.4882 | 0.3071 | 0.2779 | 1.2867 | 0.6404 |
| 12 | SRC-only DH-GBM (zero-shot) | 20.3 | 5.9535 | 0.8524 | 0.1215 | 0.0432 | 0.4216 | 0.5572 |
| 12 | SRC-only QLGBM | 32.7 | 11.1 | 0.5957 | 0.1918 | 0.0752 | 0.5408 | 0.7193 |
| 12 | TGT-only DH-GBM | 23.3 | 6.7947 | 0.8449 | 0.1364 | 0.0499 | 0.4793 | 0.5928 |
| 12 | POOLED (tgt-upweighted) | 19.9 | 5.8719 | 0.8610 | 0.1193 | 0.0426 | 0.4178 | 0.5488 |
| 12 | FINE-TUNE src->tgt | 20.5 | 6.0426 | 0.8606 | 0.1220 | 0.0339 | 0.4103 | 0.5484 |
| 12 | IW-POOLED (density-ratio) | 19.8 | 5.8526 | 0.8616 | 0.1191 | 0.0400 | 0.4146 | 0.5503 |
| 12 | FINE-TUNE src->tgt+CQR | 20.5 | 6.0426 | 0.8606 | 0.1220 | 0.0339 | 0.4103 | 0.5484 |
| 12 | POOLED (tgt-upweighted)+CQR | 19.9 | 5.8719 | 0.8610 | 0.1193 | 0.0426 | 0.4178 | 0.5488 |
| 24 | B1-cust-median | 41.9 | 20.9 | 0.0452 | 0.3206 | 0.3421 | 1.2935 | 0.6399 |
| 24 | B1d-cust-quantiles | 44.0 | 18.6 | 0.4997 | 0.3067 | 0.2787 | 1.2915 | 0.6403 |
| 24 | SRC-only DH-GBM (zero-shot) | 20.5 | 5.9876 | 0.8533 | 0.1217 | 0.0371 | 0.4188 | 0.5526 |
| 24 | SRC-only QLGBM | 33.2 | 11.2 | 0.5888 | 0.1941 | 0.0849 | 0.5572 | 0.7119 |
| 24 | TGT-only DH-GBM | 22.1 | 6.5459 | 0.8448 | 0.1337 | 0.0374 | 0.4786 | 0.5846 |
| 24 | POOLED (tgt-upweighted) | 19.8 | 5.8495 | 0.8603 | 0.1187 | 0.0319 | 0.4152 | 0.5437 |
| 24 | FINE-TUNE src->tgt | 20.6 | 6.0073 | 0.8660 | 0.1223 | 0.0362 | 0.4212 | 0.5520 |
| 24 | IW-POOLED (density-ratio) | 19.8 | 5.8588 | 0.8625 | 0.1181 | 0.0309 | 0.4109 | 0.5404 |
| 24 | FINE-TUNE src->tgt+CQR | 20.6 | 6.0073 | 0.8660 | 0.1223 | 0.0362 | 0.4212 | 0.5520 |
| 24 | POOLED (tgt-upweighted)+CQR | 19.8 | 5.8495 | 0.8603 | 0.1187 | 0.0319 | 0.4152 | 0.5437 |

## T1-C dữ liệu THẬT (Customer Invoices, BPI 2019)

Nguồn: `outputs/t1/C_real_domains.csv`

CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.

| setting | model | MAE_p50 | pinball_avg | cov80 | IBS_13w | C_index |
|---|---|---|---|---|---|---|
| C_real_customer_invoices | B0-due | 3.7227 | 1.8613 | 0.1982 | 0.0333 | 0.7644 |
| C_real_customer_invoices | B1-cust-median | 2.7711 | 1.3856 | 0.2773 | 0.0254 | 0.8463 |
| C_real_customer_invoices | B1d-cust-quantiles | 2.7903 | 0.9780 | 0.8070 | 0.0252 | 0.8453 |
| C_real_customer_invoices | DH-GBM | 2.5272 | 0.8954 | 0.8733 | 0.0163 | 0.8365 |
| C_real_customer_invoices | DH-LR | 3.9539 | 1.3581 | 0.8580 | 0.0265 | 0.7574 |
| C_real_customer_invoices | QLGBM | 2.3377 | 0.8550 | 0.6040 | 0.0230 | 0.8655 |
| C_real_customer_invoices | AFT | 17.2 | 5.6010 | 0.2352 | 0.1542 | 0.7505 |
| C_real_customer_invoices | ENS DH-GBM+QLGBM | 2.2882 | 0.8187 | 0.8367 | 0.0163 | 0.8365 |
| C_real_bpi2019 | B0-due | 40.5 | 20.3 | 0.0015 | 0.3449 | 0.5000 |
| C_real_bpi2019 | B1-cust-median | 14.0 | 6.9765 | 0.0479 | 0.1195 | 0.7938 |
| C_real_bpi2019 | B1d-cust-quantiles | 14.0 | 5.0720 | 0.6932 | 0.1024 | 0.7934 |
| C_real_bpi2019 | DH-GBM | 31.1 | 8.7773 | 0.4834 | 0.1845 | 0.7666 |
| C_real_bpi2019 | DH-LR | 15.3 | 5.2446 | 0.8620 | 0.1164 | 0.7833 |
| C_real_bpi2019 | QLGBM | 23.2 | 10.5 | 0.1360 | 0.1959 | 0.7622 |
| C_real_bpi2019 | AFT | 38.2 | 10.8 | 0.4571 | 0.2246 | 0.7594 |
| C_real_bpi2019 | ENS DH-GBM+QLGBM | 15.5 | 5.0974 | 0.7207 | 0.1845 | 0.7666 |

## T2 cure: P(không bao giờ trả | quá hạn)

Nguồn: `outputs/t1/D_t2_cure.csv`

CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.

| world | model | n | base_rate | PR_AUC | ROC_AUC | Brier | ECE | expected_loss_vs_actual |
|---|---|---|---|---|---|---|---|---|
| src | TT48 aging rule | 54650 | 0.3188 | 0.6029 | 0.7325 | 0.2378 | 0.2646 | 0.1895 |
| src | Logistic | 54650 | 0.3188 | 0.8121 | 0.9104 | 0.1048 | 0.0224 | 1.0322 |
| src | Cure-GBM | 54650 | 0.3188 | 0.9646 | 0.9754 | 0.0480 | 0.0358 | 0.8819 |
| tgt | TT48 aging rule | 20809 | 0.4465 | 0.6817 | 0.7288 | 0.3339 | 0.3732 | 0.1765 |
| tgt | Logistic | 20809 | 0.4465 | 0.8620 | 0.8859 | 0.1379 | 0.0526 | 1.1538 |
| tgt | Cure-GBM | 20809 | 0.4465 | 0.9762 | 0.9735 | 0.0534 | 0.0332 | 0.9527 |

## T8 lời hứa trả / T9 nguồn nhãn

Nguồn: `outputs/t1/EF_t8_t9.csv`

CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.

| setting | model | MAE_p50 | MAE_p50_promised_only | IBS_13w | cov80 | WAPE_collect_w1_4 |
|---|---|---|---|---|---|---|
| E_T8 | DH-GBM with promises (T8) | 15.4 | 11.3 | 0.1046 | 0.8606 | 0.4046 |
| E_T8 | DH-GBM without promises | 15.6 | 12.2 | 0.1060 | 0.8550 | 0.4112 |
| F_T9_label_source | DH-GBM trained on LEDGER dates | 15.9 |  | 0.1083 | 0.8480 | 0.4287 |
| F_T9_label_source | DH-GBM trained on BANK dates (T9) | 15.4 |  | 0.1046 | 0.8606 | 0.4046 |

## T2 SBA 7(a) thật + T3

Nguồn: `outputs/t2_t3/t2_t3_results.csv`

CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.

| task | model | n_test | ROC_AUC | PR_AUC | Brier | ECE | mean_p | base_rate |
|---|---|---|---|---|---|---|---|---|
| T2 SBA 7(a) charge-off<=3y (REAL) | Base rate (train) | 223259 | 0.5000 | 0.0136 | 0.0134 | 0.0031 | 0.0166 | 0.0136 |
| T2 SBA 7(a) charge-off<=3y (REAL) | Logistic | 223259 | 0.8402 | 0.0572 | 0.0131 | 0.0034 | 0.0170 | 0.0136 |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM | 223259 | 0.9550 | 0.2138 | 0.0122 | 0.0054 | 0.0127 | 0.0136 |
| T2 SBA 7(a) charge-off<=3y (REAL) | LightGBM + isotonic (FY2017) | 223259 | 0.9539 | 0.2078 | 0.0126 | 0.0076 | 0.0127 | 0.0136 |
| T3 dispute at issue (synthetic tgt) | Base rate (src) | 4536 | 0.5000 | 0.0227 | 0.0223 | 0.0077 | 0.0150 | 0.0227 |
| T3 dispute at issue (synthetic tgt) | Customer history rate (EB) | 4536 | 0.6675 | 0.0500 | 0.0219 | 0.0043 | 0.0186 | 0.0227 |
| T3 dispute at issue (synthetic tgt) | LightGBM (src->tgt) | 4536 | 0.5408 | 0.0244 | 0.0224 | 0.0078 | 0.0154 | 0.0227 |
| T3 partial at issue (synthetic tgt) | Base rate (src) | 4536 | 0.5000 | 0.0957 | 0.0877 | 0.0343 | 0.1299 | 0.0957 |
| T3 partial at issue (synthetic tgt) | Customer history rate (EB) | 4536 | 0.7177 | 0.1940 | 0.0826 | 0.0214 | 0.0931 | 0.0957 |
| T3 partial at issue (synthetic tgt) | LightGBM (src->tgt) | 4536 | 0.6938 | 0.1894 | 0.0828 | 0.0122 | 0.0933 | 0.0957 |
| T3 collected/invoiced ratio (src) | descriptive | 66655 |  |  |  |  | 0.9981 | 0.0266 |
| T3 collected/invoiced ratio (tgt) | descriptive | 4407 |  |  |  |  | 0.9978 | 0.0251 |

## T4 doanh thu mới

Nguồn: `outputs/t4/t4_revenue_forecast.csv`

CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.

| setting | model | SPL | SPL_h1_4 | SPL_h5_13 | cov80 | WAPE_p50 |
|---|---|---|---|---|---|---|
| synthetic src (in-domain) | Global-LGBM-Q | 0.2596 | 0.2600 | 0.2594 | 0.7868 | 0.3283 |
| synthetic src (in-domain) | Global-LGBM-Q+CQR | 0.2608 | 0.2611 | 0.2607 | 0.8371 | 0.3283 |
| synthetic src (in-domain) | Seasonal-naive | 0.3271 | 0.3342 | 0.3240 | 0.8055 | 0.4050 |
| synthetic src (in-domain) | Mean-13w | 0.2701 | 0.2655 | 0.2722 | 0.8217 | 0.3402 |
| synthetic src (in-domain) | Chronos-Bolt (zero-shot) | 0.2628 | 0.2618 | 0.2632 | 0.8206 | 0.3355 |
| synthetic src (in-domain) | Ensemble LGBM+Chronos | 0.2563 | 0.2570 | 0.2560 | 0.8154 | 0.3269 |
| synthetic tgt (zero-shot transfer from src) | Global-LGBM-Q | 0.3483 | 0.3427 | 0.3509 | 0.7465 | 0.3721 |
| synthetic tgt (zero-shot transfer from src) | Global-LGBM-Q+CQR | 0.3474 | 0.3419 | 0.3498 | 0.7951 | 0.3721 |
| synthetic tgt (zero-shot transfer from src) | Seasonal-naive | 0.4249 | 0.4040 | 0.4342 | 0.7771 | 0.4718 |
| synthetic tgt (zero-shot transfer from src) | Mean-13w | 0.3861 | 0.3762 | 0.3906 | 0.7661 | 0.3895 |
| synthetic tgt (zero-shot transfer from src) | Chronos-Bolt (zero-shot) | 0.3667 | 0.3571 | 0.3710 | 0.7912 | 0.3798 |
| synthetic tgt (zero-shot transfer from src) | Ensemble LGBM+Chronos | 0.3524 | 0.3467 | 0.3549 | 0.7567 | 0.3709 |
| real Online Retail II (trained on own past) | Global-LGBM-Q | 0.2928 | 0.2579 | 0.3083 | 0.6660 | 0.3647 |
| real Online Retail II (trained on own past) | Global-LGBM-Q+CQR | 0.2875 | 0.2542 | 0.3024 | 0.8316 | 0.3647 |
| real Online Retail II (trained on own past) | Seasonal-naive | 0.3638 | 0.3216 | 0.3826 | 0.7005 | 0.2961 |
| real Online Retail II (trained on own past) | Mean-13w | 0.2823 | 0.2450 | 0.2989 | 0.8136 | 0.3593 |
| real Online Retail II (trained on own past) | Chronos-Bolt (zero-shot) | 0.2641 | 0.2316 | 0.2785 | 0.7877 | 0.2752 |
| real Online Retail II (trained on own past) | Ensemble LGBM+Chronos | 0.2685 | 0.2372 | 0.2824 | 0.6907 | 0.3065 |
| real Online Retail II (pretrain synthetic + own past) | Global-LGBM-Q | 0.2818 | 0.2464 | 0.2975 | 0.6181 | 0.3263 |
| real Online Retail II (pretrain synthetic + own past) | Global-LGBM-Q+CQR | 0.2794 | 0.2457 | 0.2944 | 0.8536 | 0.3263 |
| real Online Retail II (pretrain synthetic + own past) | Ensemble LGBM+Chronos | 0.2684 | 0.2351 | 0.2832 | 0.6440 | 0.2957 |

## T6 số dư 13 tuần — khoảng

Nguồn: `outputs/t6/t6_interval_metrics.csv`

CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.

| model | horizon | cov80 | IS80 | pinball | MAE_p50 |
|---|---|---|---|---|---|
| Direct LGBM-Q (src) | w1-4 | 0.5738 | 7.2525 | 0.4722 | 1.3824 |
| Direct LGBM-Q (src) | w5-13 | 0.5578 | 17.5 | 1.1107 | 3.1694 |
| MC with B1 point dates | w1-4 | 0.1868 | 20.5 | 1.0990 | 2.4998 |
| MC with B1 point dates | w5-13 | 0.4977 | 20.4 | 1.2472 | 3.3936 |
| MC-copula-t (T1+T4+T5) | w1-4 | 0.7009 | 5.1681 | 0.3505 | 1.0695 |
| MC-copula-t (T1+T4+T5) | w5-13 | 0.6830 | 14.3 | 0.9424 | 2.8008 |
| MC-copula-t + ACI | w1-4 | 0.7943 | 5.2169 | 0.3522 | 1.0695 |
| MC-copula-t + ACI | w5-13 | 0.8059 | 15.6 | 0.9857 | 2.8008 |
| MC-independent (rho=0) | w1-4 | 0.5598 | 5.8039 | 0.3697 | 1.0577 |
| MC-independent (rho=0) | w5-13 | 0.5980 | 15.4 | 0.9793 | 2.7981 |
| Naive (known out + avg in) | w1-4 | 0.6988 | 7.0508 | 0.4635 | 1.3710 |
| Naive (known out + avg in) | w5-13 | 0.6938 | 18.9 | 1.2873 | 3.9400 |

## T6 xác suất thiếu hụt

Nguồn: `outputs/t6/t6_shortfall_metrics.csv`

CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.

| model | shortfall_rate_4w | Brier_4w | AUC_4w | shortfall_rate_13w | Brier_13w | AUC_13w |
|---|---|---|---|---|---|---|
| Direct LGBM-Q (src) | 0.1607 | 0.0176 | 0.9857 | 0.1923 | 0.0460 | 0.9213 |
| MC with B1 point dates | 0.1607 | 0.0465 | 0.9293 | 0.1923 | 0.0615 | 0.9359 |
| MC-copula-t (T1+T4+T5) | 0.1607 | 0.0140 | 0.9982 | 0.1923 | 0.0328 | 0.9832 |
| MC-independent (rho=0) | 0.1607 | 0.0146 | 0.9980 | 0.1923 | 0.0333 | 0.9841 |
| Naive (known out + avg in) | 0.1607 | 0.0219 | 0.9899 | 0.1923 | 0.0414 | 0.9815 |

## T7 điểm gãy

Nguồn: `outputs/t7/t7_changepoint.csv`

CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.

| detector | params | world | detection_rate_180d | median_lag_days | false_alarms_per_cust_year | macro_alarms_per_cust_year | n_eligible_shifted |
|---|---|---|---|---|---|---|---|
| CUSUM [pit] | {'k': 0.25, 'h': 5} | src (tuned) | 0.5556 | 61.0 | 0.4664 | 0.1503 | 18 |
| CUSUM [pit] | {'k': 0.25, 'h': 5} | held-out (tgt+sens_uk+sens_coface) | 0.5238 | 50.0 | 0.6334 | 0.2021 | 21 |
| Page-Hinkley [pit] | {'delta': 0.1, 'lam': 6} | src (tuned) | 0.5000 | 75.0 | 0.3041 | 0.1002 | 18 |
| Page-Hinkley [pit] | {'delta': 0.1, 'lam': 6} | held-out (tgt+sens_uk+sens_coface) | 0.4286 | 65.0 | 0.4244 | 0.1349 | 21 |
| BOCPD [pit] | {'hazard': 0.03333333333333333, 'thr': 0.3} | src (tuned) | 0.1111 | 89.0 | 0.0985 | 0.0287 | 18 |
| BOCPD [pit] | {'hazard': 0.03333333333333333, 'thr': 0.3} | held-out (tgt+sens_uk+sens_coface) | 0.0952 | 108.0 | 0.1322 | 0.0400 | 21 |

## T9 khớp sao kê

Nguồn: `outputs/t9/t9_reconciliation_tgt.csv`

CSV cũ: chưa xác nhận lại sau sửa as-of/CDF; không dùng làm bằng chứng nghiệm thu mới.

| link_precision | link_recall | link_f1 | n_pred | n_true | false_match_noise_txn_rate | pay_date_MAE_est_days | pay_date_exact_share | pay_date_MAE_ledger_days | method | txn_customer_recall |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.7811 | 0.6163 | 0.6890 | 6145 | 7789 | 0.0194 | 1.9681 | 0.9685 | 12.6 | ML reconciler (src->tgt) | 0.9532 |
| 0.9891 | 0.4648 | 0.6324 | 3660 | 7789 | 0.0161 | 0.2034 | 0.9981 | 12.6 | R1 exact-amount rule |  |
| 0.9902 | 0.3106 | 0.4728 | 2443 | 7789 | 0.0000 | 1.9111 | 0.9547 | 12.6 | R2 memo-regex rule |  |

## WP-0 hợp đồng dữ liệu

Nguồn: `outputs/wp0/world_contract_summary.csv`

Kiểm tra dữ liệu, không phải đo chất lượng mô hình.

| world | checks | passed | failed |
|---|---|---|---|
| sens_coface | 68 | 68 | 0 |
| sens_uk | 68 | 68 | 0 |
| src | 68 | 68 | 0 |
| tgt | 68 | 68 | 0 |

<!-- /AUTO:IMPLEMENTATION_RESULTS -->
