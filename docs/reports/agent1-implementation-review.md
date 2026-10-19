# Agent 1 — Tài Liệu Tổng Hợp Duy Nhất (Pipeline + Đánh Giá + Đề Xuất + Triển Khai)

> **Ghi chú checkout:** nội dung và số liệu dưới đây được chốt ngày 24/09/2026 theo artifact được tài liệu dẫn lại. Lần sắp xếp ngày 18/10/2026 cập nhật tên file/đường dẫn; chưa chạy lại huấn luyện hoặc xác minh các metric. Checkout hiện không kèm `data/processed/` và model đầu vào.

> File này gộp 4 file cũ thành một và thay thế toàn bộ chúng:
> `AGENT1_PIPELINE_OPTIMIZED.md` (24/09 — mới nhất, làm khung chính) ·
> `DANH_GIA_AGENT1_VA_HO_SO_VONG1.md` (đánh giá vòng 1 + hồ sơ .docx) ·
> `DE_XUAT_CAI_TIEN_AGENT1.md` (Đ1–Đ19) ·
> `DANH_GIA_TRIEN_KHAI_D2_D15.md` (kết quả chạy thật Đ2/Đ15).
> Nguyên tắc gộp: chỗ nào file sau sửa file trước thì chỉ giữ bản mới nhất; số liệu sai/cũ
> (77.842 dòng, 10.000 hóa đơn mở, gate "PASS", cash wMAPE 10,53%/13,76%, Survival B 8,1pp,
> gate 7 điều kiện, Survival-Boost +12,60%) đã bỏ; nội dung trùng lặp chỉ giữ một bản.

Ngày chốt: 2026-09-24. Mọi con số đều tính lại từ artifact trong `data/processed/`.

---

## 1. Kết Luận Thiết Kế

"Một trục dự báo chính + các challenger có điều kiện".

```text
Raw AR data
  -> Data quality gate
  -> Rolling as-of snapshots (hai lưới song song)
  -> As-of feature engineering
  -> Baseline gate
  -> LightGBM quantile landmark model
  -> Calibration (CQR)
  -> Monte Carlo cash-in simulation
  -> Market shock & stress testing
  -> Backtest report + dashboard + monitoring
```

Right-censoring là trường hợp dừng quan sát trước khi sự kiện xảy ra — tồn tại ở mọi pool
đang mở và là lý do lớp Survival được tách riêng (Tầng 10A, đã nâng lên MVP).

**Scope contract (bắt buộc ghi trong báo cáo):**

- Prototype chỉ dự báo cash-in từ AR invoices hiện có, chưa dự báo toàn bộ cash balance.
- `clear_date` là proxy cho ngày tiền về vì chưa có `bank_txn_date` (xem §9 — việc P0 còn lại).
- Hóa đơn đang mở không có label → dùng cho inference; train survival thì dùng như
  right-censored observations.
- Đơn vị dự báo chính là invoice snapshot tại cutoff `T`, không phải hóa đơn tại ngày phát hành.

---

## 2. Bằng Chứng Từ Tài Liệu Trong Project

| Tài liệu | Điều rút ra | Tác động đến pipeline |
|---|---|---|
| `invoice_forecasting_discrete_survival.pdf` | Discrete survival phù hợp AR invoice-level, dự báo time-to-payment, tổng hợp amount bằng Monte Carlo | Survival (Tầng 10A) đã nâng lên MVP: bias hậu cú sốc 8,4pp vs LightGBM 62,7pp |
| `invoice_forecasting_discrete_survival.R` | Expand time interval, fit hazard bằng cloglog GLMM, Monte Carlo tổng hợp daily amount | Monte Carlo (Tầng 7) là tầng bắt buộc |
| `customer_invoice_payment_prediction_framework.pdf` | Survival Boost đưa survival features vào ML classifier, tăng F1 trong case study | Survival-Boost OOF +11,0% K-fold (vượt ngưỡng 3–5%), walk-forward +0,65% → giữ có điều kiện |
| `offline_change_point_detection_review.pdf` | Change-point detection tổ chức bằng cost function + search method + constraint | Tự cài binary segmentation (~40 dòng, không dùng `ruptures`); điểm gãy `late_rate` 2020-03-14 ổn định 5/5 mức penalty |
| `predicting_late_payment_sales_invoices.pdf` | Phân loại paid-by-horizon | Classifier H=7/30 trong `09_collection_prioritization`; dùng được quan sát censored đã theo dõi đủ H ngày; AUC 0,994 trên `test_post` |
| `conformalized_quantile_regression.pdf` | CQR: bảo đảm coverage hữu hạn mẫu, interval thích ứng heteroscedasticity | Tầng 6: CQR đối xứng + Mondrian theo aging bucket; validation 70,3% → 80,0%, test 75,6% → 84,7% (+0,42 ngày width) |
| `lightgbm_efficient_gradient_boosting.pdf` | GBDT hiệu quả cho tabular (histogram-based, leaf-wise) | Model chính Tầng 5: 3 quantile LightGBM, early stopping trên validation |
| `regression_quantiles.pdf` | Pinball loss (Koenker & Bassett 1978 — dẫn theo docstring `03_lightgbm_payment_quantiles`, file là bản scan) | Hàm mất mát Tầng 5; tại α=0,5 pinball = ½·MAE nên gate hai lớp MAE+pinball cũ chỉ là một điều kiện |

Ký hiệu nguồn học thuật: **[CQR]** Conformalized Quantile Regression (Romano, Patterson, Candès,
Stanford) · **[SURV]** *Discover Analytics* (2024) 2:5 — discrete-time survival cho AR cash-flow,
nêu rõ COVID-19 gây "significant shifts in consumer behaviour" · **[IPPP]** Moore & van Vuuren —
survival mạnh ở "khi nào" nhưng yếu ở "có hay không" nên IPPP cũng là bài toán phân loại
(dẫn Appel et al.: hóa đơn có trả trong 5 ngày kể từ hạn không) · **[CPD]** review offline
change-point detection · **[LGBM]** Ke et al., Microsoft Research/Peking University ·
**[QREG]** pinball loss.

---

## 3. Pipeline Triển Khai (Tầng 0–11)

### Tầng 1 — Data Quality Gate

Input `data/dataset.csv` → `data/processed/invoices_ar_clean.csv`,
`data_quality_report.csv`, `invoice_id_conflicts.csv`. Notebook `01_data_preparation_eda`.

| Check | Cách xử lý | Số liệu |
|---|---|---:|
| Missing `invoice_id` | Drop + log | 6 dòng |
| Exact duplicate rows | Collapse trước khi train | 1.161 dòng |
| Cùng `invoice_id` khác customer/date/amount | Flag conflict, không aggregate ngầm | 0 nhóm |
| `amount <= 0` | Drop/flag | 0 dòng |
| `due_date < issue_date` | Flag | 131 dòng |
| `payment_terms <= 0` | Fallback từ `due_date − issue_date` hoặc term median | 90 dòng (88 imputed) |

Kết quả: **48.833 invoice** (39.152 closed + 9.681 open).

### Tầng 2 — Rolling As-Of Snapshot Factory (hai lưới song song, quyết định thiết kế)

| | Lưới cũ (trục LightGBM) | Lưới mở rộng (survival + money check) |
|---|---|---|
| Dải bảo vệ | 90 ngày (`cutoff_end = max(paid_date) − 90`) | 7 ngày |
| Cutoffs | 47 | 59 |
| Tổng dòng | 76.151 | 146.069 |
| Dòng censored | — | 66.653 (45,6%), có cờ `is_censored_at_T` |
| Output | `rolling_snapshot_features.csv` | `survival_snapshot_censored.csv` |
| Train/val/test | 50.083 / 15.162 / 10.906 | 4 cửa sổ pre/post × legacy/post |

Hai lưới bổ sung, không loại trừ: lưới cũ dừng trước ngày phát hành sớm nhất của mọi hóa đơn
đang mở (2020-02-27) nên không thể chứa pool mở thật; kéo lưới cũ về −7 ngày sẽ tạo 45,6% dòng
không nhãn và phá vỡ trục `02`→`07`, nên **không làm** — đây là quyết định thiết kế, không phải lỗi
(Đ1 tại nguồn → xem §6). Lưới mở rộng định nghĩa một lần trong `notebooks/survival_utils.py`, dùng lại
cho survival, money check và Đ2/Đ15.

Mỗi cutoff `T`: tập hóa đơn "đang mở tại T" = `issue_date <= T < paid_date`; feature chỉ từ
`history = invoices where paid_date <= T`. Target `remaining_days_at_T`; `HORIZONS = [30, 60, 90]`
(lưu ý: không có 7d ở lưới cũ). Split theo `cutoff_date` (28 train / 9 val / 10 test), không random
row split. Evaluate aggregate theo cutoff/week (row-level, mean-of-cutoffs, unique-invoice) vì mỗi
invoice xuất hiện trung bình 1,93 lần trong test.

### Tầng 3 — As-Of Feature Engineering

`03_lightgbm_payment_quantiles` §2: **31 feature** + target `remaining_days_at_T`.

| Nhóm | Feature |
|---|---|
| Invoice state | `observed_age_days`, `days_until_due_at_T`, `days_past_due_at_T`, `is_overdue_at_T`, aging bucket |
| Value | `amount`, `amount_log1p`, amount percentile, amount vs customer median |
| Terms/calendar | `payment_terms`, due month/quarter/day-of-week, cutoff month/quarter/day-of-week |
| Customer history | historical count, median/mean delay, late rate, median life, paid amount |
| Recency | last paid date age, last-k median delay, trend 3-6 tháng nếu đủ dữ liệu |
| Fallback stats | term median, global median, customer history sufficiency flags |

Nguyên tắc: mỗi feature phải trả lời "tại ngày T, hệ thống đã biết chưa?" — loại trừ `paid_date`,
`days_late`, `invoice_life_days`, `target_paid_date`, calendar của `paid_*`. Anti-leakage đã kiểm
chứng thật (`attach_history_features` chỉ dùng history đã closed tại T).

### Tầng 4 — Baseline Gate (B1 + B1R)

`02_payment_baselines` → `baseline_invoice_metrics.csv`. Chỉ giữ 2 baseline có ý nghĩa nghiệp vụ:

| ID | Baseline | Vai trò |
|---|---|---|
| B1 | Customer median delay + backoff term → global | Baseline mạnh bắt buộc phải thắng |
| B1R | Recency last-5 median + backoff customer → term → global | Challenger cho drift |

Không đặt `due-date clamped` (sanity only, quá yếu, không học payment persona), `global median`,
`term median` làm baseline chính.

| Baseline | MAE overall (76.151) | MAE test (10.906) |
|---|---:|---:|
| B1 | 4,67 | **4,03** |
| B1R | 5,11 | 4,60 |

(Ghi rõ scope overall vs test — bản plan cũ thiếu ghi chú này.)

### Tầng 5 — Primary Model: LightGBM Quantile Landmark

`03_lightgbm_payment_quantiles`, models ở `models/lgbm_q*.txt`. Input: as-of snapshot tại T; target
`remaining_days_at_T`; output P10/P50/P90 (α = 0,1/0,5/0,9). Early stopping trên validation
(9 tham số dùng chung 3 quantile, **chưa tuning riêng — khai báo thẳng, không nhận đã tune**).
Feature set gồm `pred_b1_remaining_days` (stacking; §4 báo cáo kèm biến thể không stacking).
Monotone rearrangement sau predict (min/median/max) chống quantile crossing.

Vì sao là trục chính: tabular snapshot; cần quantile trực tiếp cho Monte Carlo; dễ debug/so với
baseline; nhanh cho rolling backtest.

### Tầng 6 — Calibration (CQR)

`04_conformal_calibration`. Raw coverage validation chỉ 70,3% vs danh nghĩa 80% → interval quá hẹp, dải
cash-in sẽ lạc quan giả (nguy hiểm nhất với bài toán cảnh báo thanh khoản).

| Split | Coverage trước | Coverage sau | Width trước | Width sau |
|---|---:|---:|---:|---:|
| train | 81,3% | 88,6% | 5,28 | 5,70 |
| validation | 70,3% | 80,0% | 5,33 | 5,75 |
| **test** | 75,6% | **84,7%** | 8,57 | 8,99 |

Kỹ thuật: CQR đối xứng + Mondrian theo aging bucket; nhóm < 250 dòng fallback bảo thủ = `Q` lớn
nhất các nhóm đã fit; sàn dự báo 1 ngày (target min = 1; bản cũ clip về 0 tạo 6,71% dự báo B1 = 0).
Danh nghĩa **80%**, dung sai 75–85%. Chọn biến thể bằng chia `val_A → val_B` trong validation,
không nhìn test (Đ11). Giá: +0,42 ngày width (target là số nguyên nên nới nhỏ vẫn nhảy coverage lớn).
Hạn chế khai báo: calibration set trùng set early stopping nên exchangeability không hoàn toàn sạch —
bù bằng kiểm chứng trên test chưa dùng vào việc gì (84,7% trong dung sai).

### Tầng 7 — Monte Carlo Cash-In Simulation

`05_monte_carlo_cash_in`, N_SIMS = 2.000 (triển khai) / 20.000 (diagnostic).

- **Sampler chính: bootstrap residual theo nhóm aging** — ngày trả = q̂₅₀ + r, r bốc từ pool residual
  thực nghiệm cùng nhóm aging. Giữ hình dạng sai số thật, không giả định đuôi. Phương án
  piecewise-linear + đuôi mũ có trong code nhưng thua ở validation.
- **Cấu trúc phụ thuộc: Gaussian copula 3 tầng** (sốc chung danh mục + sốc mức khách hàng + phần
  riêng), chọn trên validation. Giả định độc lập cho band coverage chỉ 44,4% (tuần 1: 100% cutoff
  tiền thực nằm trên P90) → cấu hình chọn `(ρ_c=0,25, ρ_m=0,75)` đạt **80,3%** với độ rộng tương đối
  0,839. Phân phối biên không đổi (vẫn từ CQR), chỉ đổi cách liên kết — đây không phải macro shock
  stochastic mà plan loại khỏi MVP (không bịa sốc ngoại sinh, chỉ đo phụ thuộc từ validation).
- Không thêm macro shock stochastic ở bước này để tránh trùng vai stress scenario. Không dùng
  triangular distribution (chỉ khớp min/mode/max → tái tạo sai chính 3 quantile đã hiệu chỉnh).

Output: base cash-in P10/P50/P90 theo ngày/tuần 30/60/90 ngày; SUSTAIN_DAYS = 5; top
invoices/customers theo `amount × P(chưa trả trong 30 ngày)` (**gộp theo `customer_id`, không theo
tên** — Đ13: `customer_id = 200769623` có 11 biến thể tên, nắm 18,4% dư nợ; gộp sai làm top-10 rủi ro
hiện 14,8% thay vì 46,1% thật).

Nguyên tắc chống rớt-nhầm-bucket: model điểm Q50 cộng thẳng tiền theo bucket tuần phóng đại sai số
timing — Tầng 7 biến mỗi hóa đơn thành phân phối ngày trả, bốc 2.000 lần rồi mới cộng tổng.
Vì vậy `lgbm_metrics.csv` (điểm Q50) không đủ đánh giá cash; phải đọc `eval_cash_metrics.csv` và
`mc_backtest_weekly.csv`.

### Tầng 8 — Market Shock & Stress Testing

`06_stress_testing_regime_detection`. Tự viết binary segmentation (~40 dòng, không cài `ruptures`) + bảng độ nhạy
penalty 1·log n → 8·log n.

| Thành phần | Khi dùng |
|---|---|
| Stress scenario tất định (11 kịch bản + 2 haircut) | Luôn có trong dashboard MVP |
| Macro shock stochastic | Đã bật ở Tầng 7 qua copula; phần còn lại không dùng trong MVP |
| Change-point/crisis monitoring | Sau backtest hoặc khi vận hành thật |

| ID | Kịch bản | Tác động cash 30 ngày |
|---|---|---:|
| S0 | Base | $272M (P10) |
| S1a/b/c | Trả chậm +15/+30/+60 ngày | −33,8% / −100% / −100% |
| S2a/b | Top-1 / Top-3 không trả | −18,4% / −27,8% |
| S2c | Nhóm WAL-MAR không trả | −18,4% |
| S3 | Overdue trễ thêm 30 ngày | −96,7% |
| S4 (20/30) | Haircut −20%/−30% trên P10 | — |
| S5 / S5b | Lặp cú sốc 2020-03-14 (+8 median / +17 mean) | −1,7% / −50,6% |
| S6 | Kép S1b+S3+S2b | −100% |

Change-point: `late_rate` gãy tại **2020-03-14**, ổn định 5/5 mức penalty; `median_days_late` gãy
2020-04-18 (3/5). Trước/sau gãy: trả trễ 40,2% → 81,4%; tiền thu/tuần 19,4M → 0,99M.
PSI train vs live: 5/9 feature > 0,25, max **6,229** (`customer_last_paid_age_days`).
Luật regime (Đ12): ≥2/3 tín hiệu (PSI > 0,25; điểm gãy trong 8 tuần gần nhất; band coverage < 75%)
→ **CRISIS (3/3)**, lưu ở `regime_status.csv` kèm 6 hành động bắt buộc. Lưu ý: chuỗi tiền cuối kỳ bị
right-truncation nên chỉ minh họa; kết luận regime dựa vào PSI (không cần nhãn) và `late_rate`.

### Tầng 9 — Evaluation & Go/No-Go

`07_backtesting_evaluation`. Gate = **5 điều kiện quyết định + 3 điều kiện nhạy** (`eval_gate_decision.csv`);
gate hai lớp cũ (MAE + pinball) đã bỏ vì `pinball_q50 = ½·MAE` là một điều kiện. Mọi lựa chọn thiết
kế (20 lựa chọn: 4 biến thể CQR, 2 sampler MC, 14 điểm copula) đều chọn trên `val_A → val_B`,
không nhìn test (Đ11).

| Cách tổng hợp | MAE B1 | MAE LGBM | Cải thiện |
|---|---:|---:|---:|
| Row-level | 4,027 | 3,529 | +12,38% |
| **Mean-of-cutoffs (số chính)** | 3,727 | 3,306 | **+11,31%** |
| Unique invoice | 3,009 | 2,761 | +8,26% |

LightGBM thắng B1 ở **10/10 test cutoffs** (không nhờ cutoff may mắn). Segment test đúng (bug
segment cũ đã sửa — file segment cũ mọi dòng ra cùng một số đã bỏ):

| Segment | n | MAE B1 | MAE LGBM | Cải thiện |
|---|---:|---:|---:|---:|
| not_overdue (93% dòng) | 10.139 | 3,36 | 3,04 | +9,7% |
| overdue | 767 | 12,82 | 10,04 | +21,6% |
| cold start | 292 | 9,07 | 8,87 | +2,2% |
| aging 31_60 | 74 | 10,35 | 6,71 | +35,1% |

**Gate cuối: CONDITIONAL** — thắng rõ mức hóa đơn, chưa thắng mức dòng tiền:

| Điều kiện | Giá trị | Kết luận |
|---|---:|---|
| R2 · MAE invoice thắng B1 ≥ 10% | +11,3% | PASS |
| R4 · coverage trong 75–85% (test, sau CQR) | 84,7% | PASS |
| R1a · thắng baseline cash wMAPE tuần | 23,21% vs 10,46% | FAIL |
| R1b · thắng baseline CRPS | 0,1431 vs 0,1293 | FAIL |
| Action · value-precision@100 | 43,6% (B1 42,2%, aging 6,3%) | PASS |
| S1 · thắng ở cách tổng hợp bảo thủ nhất | +8,3% | FAIL |
| S2 · MASE < 1 | 0,564 (B1 0,254) | PASS |
| S3 · phần thắng không từ stacking B1 | +4,6% (nostack) | FAIL |

Cash metric phân phối-vs-phân phối (`eval_cash_metrics.csv`): B1 điểm wMAPE tuần **10,46%**;
LGBM Q50 18,02%; B1+bootstrap 20,04% / CRPS **0,1293** / coverage 62,3%; LightGBM+CQR+MC 23,21% /
CRPS 0,1431 / coverage 53,8%. Đọc đúng: B1 kém sắc hơn ở mức ngày nhưng residual rộng-trung thực hơn
nên thắng ở mức tổng tuần; LightGBM sắc nét mà chưa hiệu chỉnh đúng ở mức tổng. Định nghĩa cash cũ
(cumulative-horizon indicator, wMAPE 0,13%–2,2%) đã bỏ vì không phân biệt được gì.

Rule chọn model: LightGBM chỉ được chọn nếu thắng B1 trên pinball/MAE P50 **và** cash wMAPE/MASE
**và** CRPS; mục tiêu tối thiểu 10–15% (stretch 25%); thắng invoice mà không thắng cash thì **không
claim thành công với CFO**; coverage sai thì calibrate trước khi so cash.

### Tầng 10 — Challenger Modules (phán quyết cuối)

**10A — Survival** (`08_discrete_time_survival`): lưới mở rộng + censoring là **bắt buộc** (45,6% dòng censored).
Discrete-time hazard (bin tuần, person-period, LightGBM binary) + trọng số recency (không dùng
feature lịch `cutoff_month/quarter` — quy tắc "tháng 3–4/2020 hazard thấp" vô dụng sang tháng mới;
trọng số recency dùng lại được). Không dùng logistic cho hazard (AUC 0,127 trên `test_post` do ngoại
suy tuyến tính khi `days_past_due` vượt dải train). Biến thể B (học có censoring + recency): bias thu
14 ngày `test_post` **8,4%** vs LightGBM 62,7%, C-index 0,985 → **nâng lên MVP**. Biến thể A (chỉ học
trước sốc) gần trùng LightGBM → không giữ riêng. Bài học phương pháp: bộ máy survival một mình không
cứu được gì (train cũ có 0% censored); giá trị đến từ việc dữ liệu train **chứa** quan sát censored.

**10A-Đ2 — Train lại trục chính trên lưới mở rộng: REJECT** (`11_extended_window_retraining`, 6 biến thể
M0–M4, cùng siêu tham số, 500 cây cố định, không lựa chọn nào nhìn test):

| Biến thể | MAE legacy | Bias tiền `test_post` |
|---|---|---:|
| M0 (hiện trạng) | 3,29 | 62,7pp |
| M1 (train_pre, loại censored) | 3,88 | 58,9pp |
| M2a (pre+post, loại censored, đều) | 3,28 | 62,2pp |
| **M2b (Đ2 nguyên văn: pre+post, loại censored, recency 8 tuần)** | 3,52 | **71,1pp** |
| M3 (giữ censored, pinball-censoring, recency) | 6,37 (+94%) | 35,7pp |
| M4 (IPCW) | 3,59 | 76,4pp |

Không biến thể nào đạt cả 3 điều kiện (MAE legacy không tệ hơn M0 quá 5%; bias giảm ≥ 20pp; ngang
Survival B). Nguyên nhân đo được: bộ lọc "chỉ dòng có nhãn" ở `train_post` giữ lại **11,7%** dòng —
đúng nhóm trả nhanh (16,8 ngày vs chặn dưới thật 49,8 ngày) = chọn mẫu theo kết cục; trọng số recency
khuếch đại chỗ sai (M2b tệ hơn M2a 8,9pp). M3 hạ bias nhưng MAE legacy +94%; sensitivity 4 cấu hình
xác nhận đánh đổi này là tính chất của lớp hồi quy ngày-trả (câu trả lời thật nằm ngoài cửa sổ quan
sát), không phải chuyện chỉnh tham số. M4/IPCW tệ nhất (76,4pp) vì khối lượng xác suất nằm ngoài dải
quan sát được. Kết luận: **giữ nguyên trục LightGBM; chuyển trục sang survival khi regime = crisis**
(đã có sẵn ở `08_discrete_time_survival` §7b + dashboard). Hạn chế khai báo: `test_post` chỉ 5 cutoff (H=30 còn 1);
cột MAE chỉ đọc giữa các biến thể mới với nhau (M0 early stopping 75 cây vs 500 cây cố định); toàn bộ
kết luận hậu sốc phụ thuộc giả thuyết cú sốc là thật (xem §9 Đ3).

**10A-Đ15 — Survival-Boost OOF: GIỮ CÓ ĐIỀU KIỆN** (`12_oof_survival_boost`; fold chia theo cutoff,
không theo dòng — chia theo dòng để cùng invoice nằm cả hai phía là "OOF đội lốt"):

| Bộ feature | MAE improve vs F0 |
|---|---:|
| F1 in-sample (bản 08) | +13,65% |
| **F2 OOF K-fold** | **+11,02%** (vượt ngưỡng 3–5%) |
| F3 walk-forward (chỉ dùng quá khứ) | +0,65% (fair, cùng tập dòng với F2′ +3,82%) |

Optimistic bias in-sample chỉ 2,63 điểm % (nhỏ hơn lo ngại). 6 feature survival chiếm 27,4% total
gain, `S_7` quan trọng nhất. Số báo cáo là **+11,0%** (không phải +12,6%), kèm câu: dưới kiểm tra
walk-forward nghiêm ngặt còn +0,65%, phần chênh chưa tách khỏi hiệu ứng kích thước tập fit hazard
(fold đầu walk-forward chỉ ~15k dòng). Production fit hazard trên toàn bộ lịch sử → thực tế nằm giữa
hai con số; cần backtest cửa sổ mở rộng nhiều kỳ để chốt (xem §9).

**10B — Collection & Action** (`09_collection_prioritization`): classifier paid-by-horizon C_all (AUC `test_post`
**0,994**; value-precision@100 43,6% vs aging 6,3%) → **GIỮ**, tách thành sản phẩm riêng cho đội thu
hồi (quan sát censored theo dõi đủ H ngày vẫn có nhãn 0 → dùng được toàn bộ giai đoạn hậu sốc; báo
cáo tách bạch phân biệt vs hiệu chỉnh; metric tính theo tiền: gọi 25 hóa đơn bắt 50% tiền rủi ro vs
280 theo aging). Recency/EWMA challenger xem xét cho segment drift. Two-part default/cure → **BỎ**
(chỉ 4 hóa đơn > 180 ngày, không có cột bad-debt/PTP; thay bằng watchlist 1.187 hóa đơn > 60 ngày +
xác suất thu 30 ngày, không gọi là model default). Crisis mode bật (regime = crisis 3/3).

### Tầng 11 — Dashboard & Agent Layer

`10_cash_in_dashboard` → `reports/dashboard.html`, `agent_context_pack.json`, `dunning_drafts.md`.
Dashboard show quyết định, không chỉ metric: forecast P10/P50/P90; **hai số khi bất đồng** —
Survival B **95,4M** (crisis) vs LightGBM+CQR+MC **307,9M** (giả định hồi phục), chênh 212,5M = 68%
dư nợ; số chính = số của regime hiện tại, số đối chiếu luôn cạnh bên kèm nhãn giả định; 3 mức tin
cậy (đã kiểm chứng / thận trọng / chưa kiểm chứng — số 312M thuộc nhóm ba); shortfall vs plan
(proxy); top rủi ro; reason codes; forecast source; confidence regime.
Agent chỉ nhận context pack JSON (10 khóa tính sẵn: portfolio, evidence, regime + 6 hành động, top
20 invoices, `allowed_actions` / `forbidden_actions` — cấm tính/sửa forecast, tự xếp thứ tự gọi, gửi
thư chưa duyệt, nêu số ngoài pack). 5 thư nhắc nợ bằng template tất định (không dùng LLM để đúng số).
LLM chỉ giải thích và soạn hành động thu hồi — không tự tính forecast.

---

## 4. Timeline Đã Triển Khai

| Phase | Việc | Output |
|---|---|---|
| MVP-0 | Data quality gate + snapshot factory | 48.833 invoices; 76.151 dòng / 47 cutoffs |
| MVP-1 | Baseline gate + LightGBM quantile | B1 MAE test 4,03; LGBM +12,4% row-level |
| MVP-2 | Calibration + Monte Carlo | CQR test 84,7%; copula (0,25/0,75), coverage band 80,3% |
| MVP-3 | Stress test + evaluation + change-point | 11 kịch bản + 2 haircut; PSI 6,229; gãy 2020-03-14; gate **CONDITIONAL** |
| MVP-4A | Survival + Collection | Survival B bias 8,4pp vs 62,7pp; Precision@K 85,7% @K=50 |
| MVP-4B-Đ2 | Retrain trên lưới mở rộng | 6 biến thể M0–M4 → reject Đ2 nguyên văn (71,1pp) |
| MVP-4B-Đ15 | OOF survival feature | F2 +11,02% OOF vs F3 +0,65% → giữ có điều kiện |
| MVP-5 | Dashboard + Agent Layer | dashboard.html, context pack, dunning drafts |

---

## 5. Điểm Mạnh Nên Giữ Để Bảo Vệ Trước Hội Đồng

1. Anti-leakage thật: feature chỉ từ history đã closed tại T; loại đúng `paid_date`/`days_late`/`paid_*`.
2. Đơn vị dự báo đúng: `remaining_days_at_T` trên rolling snapshot — đúng nghiệp vụ và đúng cho Monte Carlo.
3. Temporal split đúng: theo `cutoff_date` (28/9/10), early stopping trên validation, không random split.
4. Baseline mạnh thật (B1 MAE 4,03) — khó thắng, thắng được mới đáng nói.
5. Data quality gate có số thật (1.161 duplicate, 6 missing ID, 90 terms imputed, 131 due<issue).
6. Monotone rearrangement chống quantile crossing.
7. Thắng 10/10 test cutoffs — không nhờ may mắn.
8. Scope khiêm tốn, đúng mực: "công cụ cảnh báo sớm, không phải dự báo tuyệt đối"; tách stress tất
   định khỏi Monte Carlo ("không gọi deterministic stress là xác suất"); change-point đặt ở tầng
   monitoring; challenger bật/tắt bằng ngưỡng định lượng (≥3–5%).
9. Tầng 0 Scope Contract trung thực (`clear_date` là proxy) — hội đồng chấm cao.

---

## 6. Bảng Trạng Thái Cuối Cùng Đ1–Đ19

| # | Đề xuất | Trạng thái cuối |
|---|---|---|
| Đ1 | Kéo lưới cutoff về −7 ngày | Không sửa tại nguồn `01_data_preparation_eda` — giữ kiến trúc hai lưới (§3 Tầng 2); lưới mở rộng sống trong `survival_utils.py` |
| Đ2 | Train lại trục chính trên lưới mở rộng | ❌ REJECT — M2b nguyên văn tệ hơn (71,1pp vs 62,7pp); dùng crisis-switch đã có sẵn |
| Đ3 | Xác minh `clear_date` | ⏸ P0 quan trọng nhất còn lại — cần dữ liệu ngoài (§9) |
| Đ4 | Survival lên MVP, train có censoring | ✅ `08_discrete_time_survival` (Biến thể B, bias 8,4pp) |
| Đ5 | Cash metric theo bucket tuần | ✅ `05`, `07` (bỏ cumulative-horizon) |
| Đ6 | CRPS + baseline phân phối | ✅ `05` D32, `07` §5 |
| Đ7 | CQR calibration | ✅ `04_conformal_calibration` |
| Đ8 | Copula phụ thuộc trong MC | ✅ `05_monte_carlo_cash_in` |
| Đ9 | 3 cách tổng hợp metric | ✅ `07` §2 (số chính: mean-of-cutoffs) |
| Đ10 | Biến thể không stacking B1 | ✅ `07` §2b (+4,6% phần tự học; gọi đúng tên "B1 + residual correction") |
| Đ11 | Không dùng test khi chọn tham số | ✅ `04` D20, `05` D26/D31, `07` D40 (val_A → val_B) |
| Đ12 | Change-point + PSI + luật regime | ✅ `06_stress_testing_regime_detection` (regime CRISIS 3/3) |
| Đ13 | Gộp khách theo `customer_id` | ✅ `05` §7 |
| Đ14 | Classifier paid-by-horizon riêng | ✅ `09_collection_prioritization` (C_all AUC 0,994) |
| Đ15 | Survival-Boost OOF | ✅ có điều kiện — báo cáo +11,0%, kèm caveat walk-forward +0,65% |
| Đ16 | Bỏ two-part default | ✅ `09_collection_prioritization` §5 (watchlist thay thế) |
| Đ17 | Dashboard hai số + nhãn tin cậy | ✅ `10_cash_in_dashboard` |
| Đ18 | Ràng buộc agent thành cơ chế kỹ thuật | ✅ `10_cash_in_dashboard` (context pack + template tất định) |
| Đ19 | Sửa số liệu/citation trong plan | ⏸ Việc văn bản 1 giờ: bỏ benchmark Kaggle "4,1d/4,3d/5,2d" và "−15…−25% MAE" (không kiểm chứng được, đã có số thật `eval_nostack_comparison.csv` thay thế); sửa citation `num_leaves=31`; các số 77.842→76.151, 10.000→9.681 đã chốt trong file này |

**Được nói trong báo cáo:** thắng baseline 11,3% mức hóa đơn (kèm cả 3 cách tổng hợp + số
không-stacking 4,6%); coverage test 84,7%; gọi 25 hóa đơn bắt 50% tiền rủi ro (vs 280 truyền thống);
phát hiện điểm gãy 2020-03-14 + 13 kịch bản stress. **Không được nói:** "cải thiện dòng tiền X%"
(đang thua baseline cả wMAPE lẫn CRPS); trình bày 312,5M như dự báo đã backtest (hậu sốc thực thu
0,17% trong 14 ngày trong khi model nói 71,3%).

---

## 7. Đánh Giá Hồ Sơ Nộp Vòng 1 (`01-mau-nop-bai-du-thi-vong-1.docx`)

Nội dung tư duy (III, IV, V, VII) tốt hơn trung bình: có số liệu có nguồn, có lập luận "vì sao không
dùng cách đơn giản hơn", định vị khiêm tốn đúng mực. Nhưng hồ sơ chưa nộp được: Phần I trống, không
checkbox nào tick, ~12 khối text hướng dẫn template còn nguyên, Phần VII.3 bỏ trống câu hỏi Quantum,
và không đưa một con số thực nghiệm nào dù đã có.

### 7.1. Lỗi hình thức chặn nộp (2–3 giờ)

1. Điền Phần I (mã/tên đội, đề tài, đủ 3 thành viên); tick Lĩnh vực (Liên ngành) + Nhóm chủ đề.
2. Xóa toàn bộ text hướng dẫn template (III.1–III.4, IV.1, IV.2, IV.4, V.4, V.5, VII.1–VII.3).
3. Tick checkbox Phần IX (Dashboard, Web App, Chatbot, API, Hỗ trợ ra quyết định).
4. Xóa bảng rỗng (VI.1, VII.1) + dòng trống (IV.2–IV.3). Sửa đánh số Phần V (thêm mục 2, 3), Phần III
   (thêm số 1). Bảng VI.1 đang là text tab — dựng lại thành bảng Word thật.

### 7.2. Nội dung (3–4 giờ, tác động cao nhất)

- **VII.3 Quantum** — trả lời trung thực (khuyến nghị): không dùng Quantum vì bài toán là suy luận
  theo luật + ML trên dữ liệu bảng, hạ tầng lượng tử hiện tại chưa có lợi thế vs LightGBM/GBDT; hướng
  lượng tử nếu mở rộng là QAOA cho xếp thứ tự thu hồi có ràng buộc và lấy mẫu cho Monte Carlo — để ở
  dạng hướng nghiên cứu, không cam kết prototype.
- **Khối "Kết quả thực nghiệm sơ bộ"** (việc đơn lẻ có lợi nhất) — thêm vào cuối Phần V hoặc Phụ lục D,
  viết bảo thủ: 47 rolling cutoffs, 76.151 quan sát, MAE 3,5 vs baseline 4,0 ngày (cải thiện 11–12%,
  aggregate theo mốc thời gian, thắng 10/10 mốc), overdue cải thiện 21,6%; tự nêu 2 hạn chế (coverage
  70–76% chờ CQR; backtest chỉ gồm hóa đơn đã thu, đang bổ sung right-censored bằng survival). Đừng ghi
  "12,38%" đơn lẻ — dao động 8,3%–12,4% tùy cách đếm.
- **Phần VIII** — mốc thời gian + deliverable thật theo 4 mô-đun, ghi rõ cái nào Vòng 2, cái nào roadmap
  (giữ tầm nhìn 4 trợ lý nhưng tự giới hạn scope — tăng tin cậy). **Phụ lục A** — một sơ đồ duy nhất:
  4 trợ lý + nền dữ liệu chung + 3 luồng xử lý + tầng phê duyệt con người.
- **Mục Dữ liệu** — sửa cho đúng sự thật: mô hình huấn luyện/backtest trực tiếp trên bộ công nợ B2B
  công khai (~50.000 hóa đơn 2019–2020, USD/CAD), vì đây là bộ công khai duy nhất đủ
  issue/due/clear date để dựng rolling backtest; feature chỉ dùng trường có sẵn trong mọi phần mềm kế
  toán VN nên chuyển sang dữ liệu VN không đổi mô hình; không dùng dữ liệu tự sinh để tránh học lại
  giả định của bộ sinh. Bổ sung hạn chế `clear_date` là proxy. Chuẩn bị câu trả lời "dữ liệu Mỹ/Canada
  cho SME Việt Nam".
- **Điểm mới 2** — viết lại bằng thuật ngữ chuẩn (chênh lệch tạm thời/vĩnh viễn, VAS 17/IAS 12): một
  nguồn giao dịch gốc, hai góc nhìn (quản trị / cơ sở thuế), độ lệch theo dõi như chỉ số rủi ro thuế tồn
  đọng. Bỏ "không giải pháp quốc tế nào từng chạm tới" → "chưa được các giải pháp phổ biến tại VN xử lý
  ở tầng dữ liệu". (Tránh cách hiểu "hai hệ số liệu".)
- **Tách V.3** (~600 từ) thành 3 khối có tiêu đề + gạch đầu dòng; cắt ngắn II.3/II.4 đúng 2–3 câu; sửa
  tham chiếu ngược III.1 ("bốn lỗ hổng đã nêu ở trên" → "ở mục 2 dưới đây"); thêm mục **Rủi ro & giảm
  thiểu** từ Tầng 0.
- **Dẫn chứng cần soát:** Coca-Cola 821 tỷ (truy thu 2019? cấp tòa/năm thua kiện 2025? nguồn cụ thể);
  số hiệu Luật Thuế TNDN (hiệu lực 01/10/2025); Ledge (2025) qua G-Accon (nguồn thứ cấp yếu — tìm gốc
  hoặc thay APQC/Deloitte); số 940.000 DN (tên báo cáo + năm thay vì chỉ "Tổng cục Thống kê"). Điền
  Phụ lục B/C (đang trích ~10 nguồn không danh mục).

Ước lượng điểm: hình thức hiện Yếu → Tốt sau sửa; Tiêu chí 3 (Ý tưởng, 20%) cải thiện nhiều nhất nhờ
V.3 dễ đọc + sơ đồ + số thực nghiệm; điểm mất lớn nhất nằm ở hình thức — phần dễ sửa nhất.

---

## 8. Việc Còn Lại

| Việc | Ưu tiên | Ghi chú |
|---|---|---|
| Đ3: xác minh `clear_date` (lấy `bank_txn_date` hoặc bản trích xuất muộn ≥ 60 ngày) | P0 | Quyết định khoảng cách 199M giữa hai kịch bản dashboard; nếu không làm được, ghi giả thuyết (2) làm hạn chế bắt buộc |
| Backtest cửa sổ mở rộng nhiều kỳ cho Survival-Boost | P1 | Chốt dứt điểm +11,0% vs +0,65% (tách hiệu ứng kích thước tập fit hazard) |
| Đ19: sửa số liệu/citation (plan + `03_lightgbm_payment_quantiles` D1/D4/D7) | P2 | 1 giờ, việc văn bản |
| Sửa tại nguồn `02_payment_baselines` (clip `lower=1`, công thức B1 nhóm overdue) | P1 | Nửa ngày; công thức overdue nên dùng `max(1, customer_median_life − observed_age)` hoặc hazard theo aging bucket |
| Hồ sơ .docx theo §7 | P0 (nộp bài) | 6–9 giờ tổng |
| Sau Vòng 2: ngưỡng kế hoạch thật thay proxy; change-point online; competing risk (cần nhãn mới) | P2 | — |

Thứ tự làm cho code: Đ3 trước (quyết định cách đọc mọi số hậu sốc), rồi backtest mở rộng Đ15, rồi
dọn Đ19 + `02_payment_baselines`. Không train lại trục chính (Đ2 đã reject — 1 ngày công ước tính chuyển sang Đ3).

---

## 9. Cách Tái Tạo

```text
notebooks/04_conformal_calibration.ipynb   -> cqr_*.csv
notebooks/05_monte_carlo_cash_in.ipynb   -> mc_*.csv, mc_*.npy
notebooks/06_stress_testing_regime_detection.ipynb   -> stress_*.csv, psi_*.csv, changepoint_*.csv, regime_status.csv
notebooks/07_backtesting_evaluation.ipynb    -> eval_*.csv
notebooks/08_discrete_time_survival.ipynb      -> survival_*.csv
notebooks/09_collection_prioritization.ipynb    -> collection_*.csv, default_screen.csv
notebooks/10_cash_in_dashboard.ipynb     -> reports/dashboard.html, agent_context_pack.json, dunning_drafts.md
python notebooks/11_extended_window_retraining.py    -> ext_retrain_*.csv   (~15 phút)
python notebooks/12_oof_survival_boost.py  -> oof_boost_*.csv     (~4 phút)
python scripts/notebooks/build_notebook.py 11_extended_window_retraining
python scripts/notebooks/build_notebook.py 12_oof_survival_boost
```

Mỗi notebook kết thúc bằng sanity check pass/fail — bất kỳ dòng FAIL nào cũng làm các con số trong
file này mất hiệu lực: tổng tiền mô phỏng = tổng dư nợ (lệch 1,91e-16); chặn khách hàng giảm cash đúng
phần dư nợ; S(t) không tăng; P(7 ngày) ≤ P(30 ngày); bộ lọc "chỉ dòng có nhãn" loại >50% dữ liệu hậu
sốc; q10 ≤ q50 ≤ q90 mọi biến thể; OOF phủ đúng một lần mọi dòng train; fold fit/dự báo không chung
cutoff; thực thu hậu sốc < 1%.

Nguồn số liệu chính (`data/processed/`): `cqr_coverage_report.csv` · `eval_invoice_metrics.csv` ·
`eval_cash_metrics.csv` · `eval_gate_decision.csv` · `eval_nostack_comparison.csv` ·
`mc_dependence_grid.csv` · `psi_train_vs_live.csv` · `regime_status.csv` ·
`survival_money_check.csv` · `collection_capacity_curve.csv` · `default_screen.csv` ·
`stress_scenario_summary.csv` · `ext_retrain_*.csv` · `oof_boost_*.csv`.

---

## 10. Một Câu Chốt Để Bảo Vệ

Pipeline không chọn mô hình vì "hot", mà theo thứ tự nghiệp vụ: tái lập đúng trạng thái hóa đơn tại
ngày dự báo (hai lưới cutoff song song, 76.151 + 146.069 dòng), bắt model thắng baseline hành vi khách
hàng (B1 MAE 4,03 → LGBM 3,53; gate 8 điều kiện độc lập), rồi biến dự báo hóa đơn thành dải dòng tiền
bằng Monte Carlo (bootstrap residual + copula, band coverage 80,3% thay vì 44,4% khi giả định độc lập).
Gate hiện ra **CONDITIONAL**: thắng rõ mức hóa đơn (+11,3% mean-of-cutoffs, Precision@K 43,6%), chưa
thắng mức dòng tiền (CRPS thua baseline). Survival và change-point là tầng bảo hiểm cho censoring, tail
risk và đứt gãy thị trường (gãy 2020-03-14, bias hậu sốc 8,4pp vs 62,7pp). Đ2 train lại trục chính đã
test 6 biến thể và reject (M2b 71,1pp); Đ15 Survival-Boost OOF giữ có điều kiện (+11,0% vs +0,65%
walk-forward) — cả hai đều đã kiểm chứng qua sanity check trong notebook 11/12, không phải đề xuất
tương lai.
