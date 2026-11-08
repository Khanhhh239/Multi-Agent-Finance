# 2. T1 — Hazard nhị phân 13 tuần và đối chứng Khánh

> **Phạm vi sau gộp 06/11/2026:** Tài liệu này mô tả T1 nhị phân 13 tuần, dùng làm đối chứng Khánh/pipeline cũ. Phương pháp v5/v6 53 tuần đọc ở [tài liệu chung](T1_COMPETING_RISKS_V5_V6.md); bản 93 feature đọc ở [protocol practical](T1_V6_PRACTICAL_FEATURES_PROTOCOL_2026-11-05.md). Công thức fullweek đã đối chiếu lại code; các số đo/đề xuất gốc vẫn thuộc lần chạy cũ.

Mã: `agent1/models/t1.py` (`HazardGBM`, `expand`, `quantiles_from_hazard`), `agent1/models/features.py`.

## 2.1 Vì sao hazard rời rạc, không hồi quy phân vị

| Vấn đề | Hồi quy phân vị trên HĐ đã đóng (`QLGBM`) | Hazard rời rạc (`DH-GBM`) |
|---|---|---|
| Hoá đơn đang mở (kiểm duyệt phải) | Bị loại → **thiên lệch về phía trả nhanh** | Dùng được mọi tuần đã sống sót |
| Thông tin "đã quá hạn 20 ngày mà chưa trả" | Chỉ là một đặc trưng | Điều kiện hoá tự nhiên (chỉ xét tuần còn rủi ro) |
| Đầu ra | 3 phân vị rời rạc | **CDF theo tuần** → đưa thẳng vào Monte Carlo |
| Tính bất biến thời gian | Phải tạo nhiều mô hình theo chân trời | Một mô hình, biến `k` |
| Biến lịch tuần k (Tết, ngày chạy thanh toán) | Không dùng được | Dùng trực tiếp |

Trên dữ liệu thật AR (Customer Invoices) QLGBM vẫn có MAE điểm tốt (2,34 ngày) vì nhãn ít kiểm duyệt; hazard thắng ở **phân phối/độ phủ**
(cov80 0,87 vs 0,60) và IBS (0,0163 vs 0,0230). Ensemble lấy điểm tốt của cả hai.

## 2.2 Công thức

Với hoá đơn *i* tại ngày cắt *T*, tuần *k* = 1..13 (7 ngày): 
`h_ik = P(trả trong tuần k | chưa trả tới đầu tuần k, x_i(T), w_ik)`; 
`S_ik = Π_{j≤k}(1 − h_ij)`; `P_ik = S_{i,k−1}·h_ik`; `F_ik = 1 − S_ik`.

**Khai triển dữ liệu (`expand`):** mỗi (hóa đơn, snapshot) sinh tối đa 13 hàng.
Với `FULL_WEEK_ONLY` bật và có `obs_window`, hàng (i,k) chỉ có mặt khi
`time_obs > 7(k−1)` **và** `obs_window ≥ 7k`; `obs_window` là cửa sổ quan sát
hành chính `label_end − cutoff`, biết cho cả dòng có sự kiện.
`y=1` nếu `event ∧ ⌈remaining/7⌉ = k`. Tuần bị cắt dở không giữ riêng các
sự kiện đã xảy ra rồi bỏ các dòng chưa có sự kiện, vì sẽ gây thiên lệch.

Điều kiện cũ `event_trong_tuần_k OR time_obs ≥ 7k` chỉ còn là nhánh legacy
khi tắt fullweek hoặc thiếu `obs_window`. Các bảng dựng bằng `add_labels`
có trường này; không lấy công thức legacy làm mô tả mặc định. Đối chiếu
[`expand`](../../agent1/models/t1.py) và
[`add_labels`](../../agent1/models/features.py).

**Từ hazard ra phân vị (`quantiles_from_hazard`):** tìm tuần đầu mà `F ≥ q` và nội suy tuyến tính trong tuần; nếu `F_13 < q`, dùng đuôi hình học
`h_tail = clip(mean(h_10..13), 0,02; 0,6)`: `tuần = log((1−q)/S_13)/log(1−h_tail)`; chặn ở **120 ngày**. `E[T]` = Σ P_ik·(7(k−1)+3,5) + S_13·120.

## 2.3 Đặc trưng (46 + 7)

Nhóm (mã `FEATURES` trong `features.py`):

| Nhóm | Đặc trưng | Ý nghĩa |
|---|---|---|
| Hoá đơn | `log_amount_rel`, `term_days`, `age_days`, `days_to_due`, `days_past_due`, `is_overdue`, `issue_month`, `due_dom`, `due_dow`, `paid_frac_so_far` | tiền tương đối trung vị công ty; vị trí so với hạn; đã trả một phần |
| Khách — lịch sử | `c_n_hist`, `c_delay_mean/med/std`, **`c_delay_eb`** (co về trung bình công ty, k=4), **`c_delay_ewm`** (nửa đời 90 ngày), `c_late_share`, `c_late30_share`, `c_last_delay`, `c_trend`, `c_days_since_last_pay`, `c_tenure_days`, `c_life_med`, `c_amount_rel_med` | hành vi, độ bền, xu hướng |
| Khách — nhịp | `c_payrun_strength` (top-2 ngày-trong-tháng), `c_dow_strength`, `c_days_due_to_payrun` | khách trả ngày 10/25 → "hạn rơi tuần k" có ích |
| Khách — công nợ mở | `c_open_n`, `c_open_share`, `c_open_overdue_n`, `c_max_dpd`, `c_pay_30d` | tập trung, áp lực thanh khoản |
| Lời hứa (T8) | `has_promise`, `days_to_promised`, `promise_overdue`, `c_promise_rel` (Beta(4,2) co), `c_promise_n` | lời hứa dịch chuyển phân phối |
| Công ty / sốc chung | `f_n_hist`, `f_delay_mean`, **`f_resid_28d`** (trễ 28 ngày gần nhất − kỳ vọng theo khách), `f_resid_trend`, `f_open_n` | *đo sốc thanh khoản chung đang diễn ra* |
| Lịch | `days_to_tet`, `cut_month`, `due_near_tet` | |
| **Biến tuần k (`WEEK_FEATS`)** | `k`, `dtd_k = days_to_due − 7(k−1)`, `due_in_k`, `bd_in_k` (số ngày làm việc), `tet_in_k`, **`payrun_in_k`** (ngày chạy quen thuộc rơi vào tuần k), `promised_in_k` | thông tin tất định biết trước của từng tuần |

Quan trọng nhất theo `gain` (miền `src`, gốc 2024-07; `outputs/t1/dh_gbm_feature_importance.csv`): `dtd_k` (1,58M, vượt xa phần còn lại) ≫
`promised_in_k` (0,33M) > `c_payrun_strength` > `days_to_promised` > `due_in_k` > `c_days_since_last_pay` > `payrun_in_k` > `paid_frac_so_far` >
`days_to_due` > `c_delay_ewm` > `k`. Tức **biến tuần k (vị trí tuần so với hạn) và nhịp ngày chạy thanh toán** là chủ lực — đúng
thiết kế. **Cảnh báo:** `promised_in_k`/`days_to_promised` xếp cao vì trong máy phát lời hứa của khách "giữ lời" bám sát ngày trả thật
(σ=1,5 ngày) → có thể quá lạc quan so với thực tế (kiểm bằng thí nghiệm E và dữ liệu thật T13).

## 2.4 Tham số của bản nhị phân trong đối chứng

| Tham số | Giá trị | Ghi chú |
|---|---|---|
| objective | binary | |
| learning_rate | 0,05 | |
| num_leaves | 63 | |
| min_data_in_leaf | 200 | 100 cho bộ thật nhỏ; 50 khi thích nghi đích |
| feature_fraction / bagging | 0,8 / 0,8, freq 1 | |
| lambda_l2 | 5,0 | |
| num_boost_round | 600 (không early-stopping trong thí nghiệm A) | **cần early stopping theo pinball trên cửa sổ hiệu chỉnh** (WP-1.2) |
| threads | `AGENT1_THREADS` (6) | tránh quá tải luồng |

`QuantileLGBM`: 3 mô hình alpha 0,1/0,5/0,9; lr 0,1; leaves 63; 350 vòng (giảm để chạy nhanh). `AFT` (XGBoost): lr 0,1; depth 6; **σ=0,3** và `base_score=log(median)` (σ lớn → sai số tăng mạnh: 17→77 ngày — bẫy đã gặp).
`HazardLR`: logistic (C=0,5) chỉ làm đối chứng; trên 600k hàng khai triển.

## 2.5 Ensemble và hiệu chỉnh

- **Ensemble DH-GBM + QLGBM** = trung bình phân vị (Vincentization). Trên Customer Invoices cho kết quả tốt nhất (MAE 2,29; pinball 0,819), vì QLGBM có độ phân giải ngày, DH-GBM có phân phối đúng.
- **CQR** (Romano et al. 2019): `q̂` = phân vị mức `⌈(n+1)(1−α)⌉/n` của `E_i = max(q_lo − y, y − q_hi)` trên cửa sổ hiệu chỉnh; mở rộng/thu hẹp khoảng đối xứng. Hữu ích cho mô hình thiếu phủ (QLGBM, AFT, ensemble: cov 0,53→0,79).
- **Quan sát trong bảng cũ, trước các phép thử CQR bổ sung:** với DH-GBM, hàng "+CQR" cho kết quả *giống hệt* hàng không CQR (q̂≈0). Phải kiểm tra (WP-1.3): có thể do khoảng của DH-GBM quá dư (cov 0,86–0,89) nên q̂ ≤ 0 và đoạn hiệu chỉnh bị chặn; cần cho phép **thu hẹp** (q̂ âm) hoặc dùng hiệu chỉnh hai phía với α_lo, α_hi tách biệt.

## 2.6 Điểm mạnh / điểm yếu đã quan sát

| Bối cảnh | Kết quả | Giải thích |
|---|---|---|
| `src` rolling-origin | DH-GBM tốt nhất mọi chỉ số phân phối | môi trường có đủ thông tin lịch + hạn |
| Customer Invoices (thật) | Ensemble tốt nhất, giảm MAE 17% so với B1 | |
| BPI 2019 (thật, không có hạn) | DH-GBM đơn **kém** (pinball 8,78 vs B1d 5,07); ensemble hoà (5,10) | thiếu `days_to_due` ⇒ mất đặc trưng chủ lực; quy trình duyệt lô; hazard nhận ít thông tin hơn |
| Khách mới (ít lịch sử) | chưa phân tầng | cần phân tầng theo `c_n_hist` (WP-1.5) |

## 2.7 Các đề xuất ban đầu và bằng chứng tiếp nối

1. Ràng buộc đơn điệu (monotone constraints): hazard tăng theo `c_late_share`... để ổn định ngoài miền.
2. Early stopping + tối ưu siêu tham số bằng pinball trên cửa sổ hiệu chỉnh (Optuna).
3. Hazard theo **ngày** thay tuần ở 28 ngày đầu (độ phân giải cao hơn cho đòi nợ ngắn hạn).
4. Bayes phân tầng cho khách (thay EB cố định k=4): ước lượng k theo ngành/khối lượng.
5. Tách hazard thành 2 phần "đúng hạn" + "trễ" (mixture) để học điểm tập trung ngay quanh ngày hạn.
6. Đa nhiệm (trả một phần, tranh chấp) chia sẻ biểu diễn.


<a id="fullweek-20261021"></a>

## 2.8 Giao thức fullweek và đăng ký bổ sung ngày 21/10/2026

Phần này gộp nội dung còn giá trị kiểm toán của tài liệu fullweek cũ.
Lỗi từng giữ sự kiện ở tuần chưa đủ quan sát đã được sửa trong `expand`;
không trộn CSV legacy với kết quả hậu tố `-fullweek`. **181 CSV cũ** được
kê trong [manifest backup](../../outputs/implementation/legacy_expand_backups.json);
hash vùng khóa ở [fullweek_protected.json](../../outputs/implementation/fullweek_protected.json).
Kết quả và tiến trình gốc đọc ở
[nhật ký Sprint 1](../05_Coding_Agent_Plan/NHAT_KY_SPRINT1_2026-10-20.md),
[fullweek_refresh.json](../../outputs/implementation/fullweek_refresh.json) và
[fullweek_code_verification.json](../../outputs/implementation/fullweek_code_verification.json).

Chuỗi 18 job/điều phối chờ RAM và publish clone riêng là cách vận hành tại
thời điểm 21/10, không phải hướng dẫn chạy hiện tại. Các script/cache/log
có thể đã vắng; dữ liệu World đời đầu đã xóa. Giữ thông tin giao thức và
bằng chứng, bỏ lệnh khởi chạy điều phối/publish đã hết mục đích sử dụng.
Không có hoạt động train, commit hoặc push trong đợt gộp tài liệu này.

### Tiêu chí đã ghi trước phép đo

- `C-v2`: script gốc khoá nguyên trạng. `real_v2_b1_reference.py` chỉ tính
  mốc B1 trên đúng cohort CI; không huấn luyện hay đổi BLEND. G5: BLEND giảm
  pinball >=10% so B1 và CI thấp vs B1d >0 trên CI. G6: cả CI/BPI có CI cao
  >=0 và điểm >=-2%. G5_v1/G6_v1 giữ để kiểm toán. Registry tiêu chí ở
  `outputs/implementation/real_v2_gate_registration.json`.
  CSV v2 của Sprint 1 đã có expand mới nên không thuộc 18 job phải chạy lại;
  không huấn luyện lại toàn bộ LR/QLGBM của v2 chỉ để đăng ký job. Mốc BLEND
  sẽ được tái lập trong ablation P4 và kiểm chênh lệch <=0,5%.
- `P4`: `StationaryFeatures` fit phân vị 99 từ train; log1p số lịch sử/tuổi
  khách; ẩn tháng lịch nếu tuổi lịch sử DN <24 tháng theo lịch. Hai gốc A,
  B M12, CI/BPI v2 dùng cùng cohort/budget/params. Fine-tune giữ cùng biến
  đổi của mô hình nguồn. CI/BPI chuyển các cột float64 sang float32 đúng
  giao thức v2 trước cả hai nhánh để tránh nhiễu do độ chính xác số. CI cặp
  300 lần theo DN; CI/BPI dùng cụm khách như
  giao thức v2. Mặc định vẫn tắt. Tiêu chí: không xấu >1% ở đâu và cải thiện
  >=2% ở ít nhất một bộ thật; không chọn thêm phép biến đổi theo test.
- `G3`: từ dự báo A nguồn đóng băng, so khoảng thô, CQR hai phía toàn cục,
  Mondrian theo đã quá hạn / hạn 0–14 / 15–42 / >42 ngày. Mỗi nhóm >=100
  hàng calibration; nhóm ít hoặc chưa thấy dùng offset toàn cục. Cho phép
  offset âm để thu hẹp; không lấy q-hat từ mô hình chọn dữ liệu thật ngắn.
  Tiêu chí: hai gốc cov80 75–85%, IS80 không tăng so CQR toàn cục.

Phần đăng ký `T9-source-policy` được gộp vào
[giao thức T9 nguồn](07_t7_t9_t10.md#t9-source-policy).
Các tiêu chí trên là hồ sơ trước chạy; trạng thái P4/G3/G5/G6 và T9 đọc từ
CSV/protocol ở Evaluation. C-v2 có giao thức expand mới riêng; không tính
việc đăng ký nó như một lần retrain LR/QLGBM mới. G13 và các yêu cầu UAT,
chuyên gia, pilot không được coi là đã hoàn tất từ việc có code hoặc test.
