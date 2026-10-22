# Nhật ký Sprint 1 — T1 trên dữ liệu thật (agent1-Khanh, 20/10/2026)

Mục đích: ghi lại **đã làm gì, tìm ra gì, sửa gì, còn gì** để coding agent khác tiếp tục mà không phải chẩn đoán lại.
Kế hoạch gốc: [09_KE_HOACH_TIEP_THEO_2026-10-20.md](09_KE_HOACH_TIEP_THEO_2026-10-20.md) — Sprint 1 (1.1, 1.2, 1.3).

## 1. Phát hiện

### P1 — Lỗi thiên lệch khai triển hazard (`agent1/models/t1.py::expand`) — **nguyên nhân gốc, ảnh hưởng mọi thí nghiệm hazard**
- Mã cũ: `known = evk | (tobs >= 7k)`. Với tuần k chỉ quan sát **một phần** (bị cắt tại `label_end` giữa tuần), mã giữ hàng **có** sự kiện
  trong phần đã quan sát nhưng bỏ hàng **không** sự kiện ⇒ chỉ còn y=1 ở các tuần bị cắt ⇒ **hazard bị thổi phồng**.
- Mức độ phụ thuộc tỷ lệ kiểm duyệt: nhỏ trên `src` (7 năm, chỉ ~13 tuần cuối bị cắt), **rất lớn trên dữ liệu thật ngắn**:
  BPI dự báo hazard 0,92–0,99 ở tuần 3–13 (trong khi trung vị thời gian còn lại thật 38 ngày) ⇒ P50 dự báo ~5 ngày, cov80 0,10.
- Sửa: `known = obs_window >= 7k` (cửa sổ quan sát hành chính biết với mọi hàng). Cờ `t1.FULL_WEEK_ONLY` (mặc định bật);
  tái lập bản cũ: `AGENT1_EXPAND_LEGACY=1`.

### P2 — DH-LR ngoại suy tuyến tính (`HazardLR._prep`)
- Trên Customer Invoices, tập huấn luyện của exp_C chỉ có 5 cutoff (3/2019), test 10–11/2019: `c_tenure_days` lệch **16,9 SD**,
  `issue_month` lệch 12,7 SD ⇒ logistic ngoại suy ⇒ MAE 105 ngày, cov80 0,0001.
- Sửa: kẹp đặc trưng chuẩn hoá vào [−5, 5] (`t1.Z_CLIP`). Đây là sửa an toàn số học, không phải chọn tham số theo test.

### P3 — Thiết kế exp_C (v1, phiên trước) làm đói dữ liệu huấn luyện
- `exp_C` lấy cửa sổ hiệu chỉnh [O−183, O−120] rồi huấn luyện chỉ trên cutoff < O−183 **và** kiểm duyệt nhãn tại O−183.
  Customer Invoices chỉ có ~17 tháng ⇒ huấn luyện còn **10.291 hàng / 5 cutoff** (trước đó 82.509). BPI không đủ dài nên rơi về nhánh
  "không hiệu chỉnh" (huấn luyện trên 11 cutoff 3–7/2018).
- Đây là lý do chính khiến "mô hình thua B1d trên dữ liệu thật" sau khi đổi giao thức — không phải bằng chứng mô hình kém.
- Giao thức v2 (`scripts/sprint1/run_real_v2.py`): **chọn** (trọng số trộn, q̂ CQR) bằng mô hình học trước cửa sổ hiệu chỉnh;
  **huấn luyện lại** mô hình cuối trên mọi cutoff < O (nhãn tới O); test không dùng để chọn.

### P4 — Đặc trưng không dừng theo thời gian (chưa sửa, ghi nhận)
- `f_n_hist` (đếm lịch sử công ty) lệch 2,4 SD trên BPI; `c_tenure_days`, `issue_month`, `cut_month` lệch mạnh khi dữ liệu ngắn.
  Cây không ngoại suy nhưng rơi vào nhánh biên. Đề xuất (Sprint 4/agent khác): thay `f_n_hist` bằng `log1p` + kẹp, hoặc tỷ lệ theo
  khối lượng trung bình 90 ngày; cân nhắc bỏ `issue_month/cut_month` khi lịch sử <24 tháng.

## 2. Số đo (trước → sau sửa P1/P2, cùng chia dữ liệu của exp_C)

| Bộ | Mô hình | Pinball trước | Pinball sau | cov80 trước | cov80 sau | B1d (mốc) |
|---|---|---|---|---|---|---|
| BPI | DH-GBM | 15,09 | **7,80** | 0,10 | **0,76** | 4,80 / cov 0,71 |
| Customer Invoices | DH-GBM | 1,501 | **1,452** | 0,75 | 0,78 | 1,455 / cov 0,79 |
| Customer Invoices | DH-LR | 47,51 | **2,15** | 0,0001 | — | |

(Cùng chia dữ liệu bỏ đói của exp_C — chỉ để tách tác động của P1/P2.)

## 3. Mã đã đổi / thêm

| File | Thay đổi |
|---|---|
| `agent1/models/t1.py` | `import os`; `FULL_WEEK_ONLY`, `Z_CLIP`; `expand` dùng `obs_window`; `HazardLR._prep` kẹp z |
| `scripts/sprint1/diag_real.py` | Chẩn đoán tái hiện đúng chia của exp_C: `--step labels|lr|gbm` |
| `tests/test_expand_censoring.py` | 3 kiểm thử: khai triển mới không thiên lệch (hazard thật 0,2), bản cũ thổi phồng, LR kẹp z |
| `scripts/sprint1/run_real_v2.py` | Giao thức v2 + BLEND neo B1d + CQR + CI bootstrap theo khách → `outputs/t1/real_v2/C_real_v2.csv` |

**Hệ quả với kết quả cũ:** mọi CSV có hazard (A, B, DA, DR, E/F, E2E, T6, scaling…) được tạo với `expand` cũ. Trên `src`/`tgt` lệch có thể nhỏ
nhưng **phải chạy lại** trước khi dùng làm bằng chứng nghiệm thu (giao cho agent khác — xem mục 5).

## 4. Kết quả giao thức v2 (điền khi chạy xong)

### Customer Invoices (`outputs/t1/real_v2/C_real_v2_ci.csv`)
Gốc O=2019-10-01; mô hình CHỌN học 10.291 hàng (trước 2019-04-01); cửa sổ hiệu chỉnh 19.641 hàng; mô hình CUỐI học lại 64.587 hàng;
test 17.922 hàng (cutoff 10–11/2019, nhãn chín tới 2020-05-22). CI bootstrap 300 lần theo khách hàng.

| Mô hình | Pinball | MAE P50 | cov80 | Cải thiện vs B1d | CI 95% |
|---|---|---|---|---|---|
| B1d (mốc) | 1,455 | 3,79 | 0,789 | 0 | — |
| DH-GBM | 1,264 | 3,59 | 0,793 | **+13,1%** | [8,3; 17,9] |
| QLGBM | 1,310 | 3,44 | 0,490 | +10,0% | [4,0; 16,0] |
| ENS (DH-GBM+QLGBM) | **1,217** | 3,42 | 0,729 | **+16,4%** | [11,4; 21,4] |
| BLEND(DH-GBM,B1d), w=0,5 chọn trên cửa sổ hiệu chỉnh | 1,245 | **3,39** | **0,835** | **+14,4%** | [11,7; 17,4] |
| BLEND(DH-GBM,B1d)+CQR | 1,247 | 3,39 | 0,839 | +14,3% | [11,6; 17,4] |
| DH-LR | 1,738 | 5,21 | 0,899 | −19,5% | [−34,1; −7,9] |
| B1d+CQR | 1,450 | 3,79 | 0,845 | +0,4% | [−0,1; 1,0] |

**Kết luận CI:** sau sửa P1–P3, hazard **thắng mốc B1d có ý nghĩa thống kê** trên AR thật. Kết luận "thua mốc trên dữ liệu thật" của bảng v1
là do lỗi + thiết kế bỏ đói, **không còn đúng**. Mô hình đề xuất triển khai = **BLEND(DH-GBM,B1d)** (w chọn trên quá khứ; độ phủ tốt nhất, CI
hẹp nhất). DH-LR vẫn kém (giữ làm đối chứng, không triển khai).

### BPI 2019 (`outputs/t1/real_v2/C_real_v2_bpi.csv`)
Gốc O=2018-07-26 (dữ liệu tới 2019-01-18); mô hình CHỌN 58.979 hàng, hiệu chỉnh 72.393, mô hình CUỐI 400.000 (lấy mẫu), test 353.512.
CI bootstrap theo nhà cung cấp (1.850 cụm). Dự đoán theo khối 40k để vừa RAM.

| Mô hình | Pinball | MAE P50 | cov80 | Cải thiện vs B1d | CI 95% |
|---|---|---|---|---|---|
| B1d (mốc) | 4,799 | 13,28 | 0,714 | 0 | — |
| DH-GBM | 7,800 | 25,55 | 0,759 | −62,5% | [−90,4; −37,4] |
| DH-LR | 6,014 | 19,09 | 0,836 | −25,3% | [−43,8; −11,9] |
| QLGBM | 14,844 | 32,21 | 0,063 | −209% | |
| ENS | 5,816 | 17,07 | 0,691 | −21,2% | [−43,2; −3,4] |
| **BLEND(DH-GBM,B1d), w=0,25** | **4,487** | **12,90** | **0,808** | **+6,5%** | **[2,1; 11,0]** |
| BLEND(DH-GBM,B1d)+CQR | 5,211 | 12,90 | 0,960 | −8,6% | [−17,8; 0,8] |
| B1d+CQR | 5,662 | 13,28 | 0,969 | −18,0% | |

**Đọc:** BPI không có hạn thanh toán ⇒ hazard một mình kém (biết trước — Phần 4.2 cũ); **trộn neo B1d với w chọn trên quá khứ (0,25) thắng mốc có ý nghĩa**.
CQR làm xấu (q̂=28 ngày quá rộng vì ước từ mô hình CHỌN yếu hơn mô hình CUỐI) ⇒ **không áp CQR khi q̂ ước từ mô hình chọn** trên dữ liệu ngắn;
dùng hiệu chỉnh khoảng ở T6/ACI thay vào đó.

## 4b. Kết luận Sprint 1

| Câu hỏi | Kết luận |
|---|---|
| Mô hình thua mốc trên dữ liệu thật? | **Không** — do lỗi `expand` (P1), ngoại suy LR (P2) và thiết kế bỏ đói (P3). |
| Mô hình triển khai đề xuất | **BLEND(DH-GBM, B1d)** với w chọn theo pinball trên cửa sổ hiệu chỉnh trước gốc (CI: 0,5; BPI: 0,25). |
| Thắng B1d trên cả hai bộ thật? | **Có**: Customer Invoices +14,4% [11,7; 17,4]; BPI +6,5% [2,1; 11,0]. |
| Luật dừng Sprint 1 (dùng B1d + CQR) | **Không kích hoạt.** |
| CQR trên T1 dữ liệu ngắn | Không dùng q̂ từ mô hình chọn (làm xấu BPI); để G3 xử lý bằng Mondrian/hai phía trên nguồn. |
| Còn rủi ro | BPI chỉ 3 công ty, là phải trả; Customer Invoices nguồn gốc không rõ. Kết luận tầng 1 (phương pháp), không phải SME VN. |

## 5. Việc tiếp theo

- Agent khác: chạy lại toàn chuỗi với `expand` mới (prompt ở mục 6), cập nhật `measurement_version`, sinh lại báo cáo/cổng.
- agent1-Khanh (tiếp): đọc kết quả v2; nếu BLEND không thua B1d trên cả hai bộ thật ⇒ đề xuất đưa BLEND vào luồng mặc định (dịch vụ + E2E);
  nếu thua ⇒ kích hoạt luật dừng của Sprint 1 (B1d + CQR cho AR kỳ hạn ngắn).

## 6. Prompt giao cho coding agent khác
Xem [PROMPT_GIAO_VIEC_2026-10-21.md](PROMPT_GIAO_VIEC_2026-10-21.md) (Việc 1–6). agent1-Khanh giữ: kết luận BPI v2 và G13.

### 6b. Chuẩn bị chạy lại 21/10/2026

- Đã sao lưu 181 CSV cũ dưới đuôi `.legacy_expand.csv`, manifest SHA-256 ở `outputs/implementation/legacy_expand_backups.json`. Không đổi `expand`, `HazardLR._prep`, script v2; kiểm hash trước/sau từng job.
- Đăng ký C-v2 trong luồng chính. G5/G6 đọc BLEND v2, giữ G5_v1/G6_v1. Thêm B1 reference cùng 17.922 hàng CI: pinball 1,8978065592; G5/G6 mới đạt theo tiêu chí người giao việc, không thay ngưỡng. Registry: `outputs/implementation/real_v2_gate_registration.json`.
- P4/G3/P5 đã chuẩn bị mã và kiểm thử, **chưa coi là hoàn tất phép đo**. Thiết kế và lệnh: `docs/04_AI_Methods/13_fullweek_refresh_2026-10-21.md`.
- Rà soát trước lượt P4/T9 ngày 21/10: P4 chuyển float64 → float32 đúng như v2 trước cả hai nhánh, tránh khác biệt độ chính xác số làm nhiễu ablation. Cache T9 cũ thiếu `training_firms`; P5 dùng cache nguồn riêng, học đúng 12 DN nguồn năm 2023/hiệu chỉnh 2024H1 và lưu provenance trước khi chọn 28 DN ngoài tập học. Kiểm thử liên quan đạt (18 ca đặc trưng/cổng/CQR/xuất bản; 11 ca provenance/đối soát). Chưa có kết quả P4/P5 để kết luận; không đổi ba vùng mã khóa.
- Bộ đếm hàng scaling đã sửa theo tuần quan sát đủ, có kiểm thử sự kiện trong tuần bị cắt. CSV E2E cuối chỉ phát marker fullweek sau cả nhánh oracle; CSV chạy dở lưu riêng để không đánh thức bộ chờ sớm.
- Máy dùng chung, RAM có lúc <1 GiB. `fullweek_refresh.py` đợi >=3 GiB trước từng job, 4 luồng; không dừng Agent4. `fullweek_finish.py` chạy P4/T9-source-policy sau đủ chuỗi 18 job; G3 đã có thể đo nhẹ trực tiếp sau A. C-v2 đã có CSV expand mới nên chỉ đăng ký job/tích hợp cổng; P4 tái lập mốc BLEND, không huấn luyện thêm LR/QLGBM v2 ngoài nhu cầu. G13 để agent1-Khanh.
- Git thư mục cha trỏ dự án khác. Đã clone riêng đúng remote/nhánh tại `.publish-repo`; chỉ đồng bộ/commit/push sau khi đo và kiểm tra xong, không dùng Git của thư mục cha.

## 7. Chạy lại (agent khác ghi vào đây)

| Ngày | Job | Thời gian | Số chính trước → sau | Ghi chú |
|---|---|---|---|---|
| 21/10/2026 08:17 | A | 892.1s | pinball_avg=10.5744; cov80=0.627364 → pinball_avg=10.5673; cov80=0.62893 | passed; trung bình cột CSV `outputs\t1\A_rolling_origin_src.csv`; không đổi tiêu chí |
| 21/10/2026 | G3 | 6.8s | 2023-07-03: cov80 0.8857 → 0.8671, IS80 78.3571 → 81.2822; 2024-07-01: cov80 0.8510 → 0.8439, IS80 72.8795 → 72.9147 | phép đo xong; tiêu chí không đạt, không đưa Mondrian vào mặc định; CI cặp 300 lần/40 DN trong outputs/t1/G3/metrics.csv |
| 21/10/2026 09:23 | B | 1691.8s | pinball_avg=9.59214; cov80=0.603433 → pinball_avg=9.59214; cov80=0.603434 | passed; trung bình cột CSV `outputs\t1\B_domain_adaptation_tgt.csv`; không đổi tiêu chí |
| 21/10/2026 09:33 | DA-paired | 622.6s | pinball_avg=9.32263; WAPE_collect_w1_4=0.63048 → pinball_avg=9.32703; WAPE_collect_w1_4=0.630599 | passed; trung bình cột CSV `outputs\t1\DA_paired_metrics.csv`; không đổi tiêu chí |
| 21/10/2026 09:42 | T1-variants | 515.7s | pinball_avg=8.94929; cov80=0.693197 → pinball_avg=8.94639; cov80=0.693672 | passed; trung bình cột CSV `outputs\t1\T1_variants.csv`; không đổi tiêu chí |
| 21/10/2026 09:44 | onboarding | 158.3s | pinball_avg=6.74799; cov80=0.747671 → pinball_avg=6.75351; cov80=0.748821 | passed; trung bình cột CSV `outputs\t1\onboarding_source_validation.csv`; không đổi tiêu chí |
| 21/10/2026 09:54 | EF | 561.3s | pinball_avg=5.00984; cov80=0.855422 → pinball_avg=5.00984; cov80=0.855422 | passed; trung bình cột CSV `outputs\t1\EF_t8_t9.csv`; không đổi tiêu chí |
| 21/10/2026 09:58 | noisy-EF | 263.4s | pinball_avg=5.05832; cov80=0.853168 → pinball_avg=5.05832; cov80=0.853168 | passed; trung bình cột CSV `outputs\t1\EF_t8_t9_src_noisy_promises.csv`; không đổi tiêu chí |
| 21/10/2026 10:01 | T9-T1 | 149.1s | WAPE=0.632504 → WAPE=0.628972 | passed; trung bình cột CSV `outputs\t1\T9_T1_error_propagation.csv`; không đổi tiêu chí |
| 21/10/2026 10:02 | T3-T1 | 95.3s | pinball_avg=11.7501; cov80=0.704736 → pinball_avg=11.7456; cov80=0.706599 | passed; trung bình cột CSV `outputs\t1\T3_T1_ablation.csv`; không đổi tiêu chí |
| 21/10/2026 10:07 | crisis-ablation | 315.8s | pinball=9.57429 → pinball=9.55671 | passed; trung bình cột CSV `outputs\t1\crisis_ablation.csv`; không đổi tiêu chí |

## 8. Sprint 4 — dữ liệu (agent1-Khanh, 21/10/2026)

- **C2ST tách đặc trưng** (`agent1/synth/c2st.py::FEATURE_SETS`, `scripts/sprint4/c2st_split.py`, `outputs/data/c2st_split.csv`): AUC gộp 0,96–0,98 gồm khác biệt chủ đích (kỳ hạn: 0,89–0,96) và hành vi (0,67–0,79). Chi tiết ở `docs/02_Data/10_realism_v2.md`.
- **Máy phát `realism='v2'`** (mặc định `v1`, thế giới cũ không đổi): lập HĐ cuối tuần + phân tán số tiền + HĐ nhỏ. AUC hành vi 0,734 → 0,691 (CI chồng nhau).
- **Thử `customer_realism`** (khách mua lẻ + dị biệt): AUC hành vi **xấu đi** (0,806). Giữ làm cờ thử nghiệm, không bật. Thế giới: `c2st_ctrl_v1`, `c2st_v2`, `c2st_v2_customers_exp` (12 công ty, seed 1).
- Kiểm thử: `tests/test_realism_v2.py` (4 ca) + các test tái lập RNG vẫn đạt (v1 không đổi).
- **Vòng 3 — cửa sổ quan sát:** bộ thật ~14 tháng, tổng hợp 84 tháng ⇒ `cust_n` đo nhầm độ dài cửa sổ. Thêm `match_window`; đo lại 15 tháng
  (`outputs/data/c2st_split_window15m.csv`): v1 0,745, v2 0,697, customers_exp 0,699, src 0,785; thứ hạng đảo so với vòng 1–2, CI rộng 0,3–0,6.
  **Kết luận: 6 công ty thật không đủ để chọn phiên bản máy phát ⇒ dừng chỉnh theo C2ST.** v2 giữ làm tuỳ chọn, không bật.
- **Chưa làm / không đụng:** chưa sinh lại `src/tgt/big_*` bằng v2 (sẽ đổi mọi kết quả; quyết định của người giao việc); chưa khớp độ tập trung theo công ty.








| 21/10/2026 10:56 | DR-eval | 2904.9s | pinball_avg=7.83417; cov80=0.768881 → pinball_avg=7.87122; cov80=0.767209 | passed; trung bình cột CSV `outputs\t1\DR\metrics.csv`; không đổi tiêu chí |

| 21/10/2026 11:42 | E2E-full | 2771.3s | cov80=0.53627; IS80=25.4515 → cov80=0.531281; IS80=25.5441 | passed; trung bình cột CSV `outputs\e2e\e2e_metrics.csv`; không đổi tiêu chí |

| 21/10/2026 12:02 | T6 | 1187.5s | cov80=0.551582; IS80=16.6864 → cov80=0.550186; IS80=16.6989 | passed; trung bình cột CSV `outputs\t6\t6_interval_metrics.csv`; không đổi tiêu chí |

| 21/10/2026 12:07 | regime-cash | 344.3s | cov80=0.632736; IS80=13.4699 → cov80=0.64037; IS80=13.1051 | passed; trung bình cột CSV `outputs\t7\regime_cash\metrics.csv`; không đổi tiêu chí |

| 21/10/2026 12:13 | collection-policy | 352.8s | 21 hàng → 21 hàng | failed; trung bình cột CSV `outputs\t6\collection_policy\metrics.csv`; không đổi tiêu chí |

## 9. Tiếp quản phần còn lại (agent1-Khanh, 21/10/2026 15:30) — AGENT KIA ĐỪNG CHẠY TRÙNG

- **Sự cố:** khoảng 12:08–12:13 `collection-policy` (chuỗi Việc 1) và backtest G13 chạy chồng nhau ⇒ hết RAM, cả hai chết không báo lỗi;
  máy khởi động lại khoảng 15:20. `run_status.json` còn ghi `collection-policy: running` — thực tế đã chết.
- **Người dùng giao agent1-Khanh làm tiếp phần còn lại.** Một hàng đợi TUẦN TỰ duy nhất: `scripts/sprint5/queue_rest.sh`
  (log `outputs/implementation/queue_rest.log`). Mỗi job chờ RAM **khả dụng** ≥ 3 GB (`wait_ram_then.sh`, bộ đếm `Available MBytes`).
  Thứ tự: G13 backtest src → G13 policy → gates → `T9-source-policy` → `P4` → `collection-policy` (có checkpoint) → `copula-hierarchy` → `IW-oof`
  → gates → `scaling` → gates → `make_report`.
- **Đã xong trước đó:** Việc 2 (G5/G6 v2 **passed**); Việc 4 G3 đo xong (failed, không đưa Mondrian vào mặc định); Việc 1 11/18 job.
- **G13 v2** (đăng ký trước `docs/03_Evaluation/G13_ALERT_POLICY.md`): `agent1/eval/alert_policy.py` (isotonic OOF theo công ty + xác nhận k tuần),
  `scripts/sprint5/g13_source_backtest.py`, `g13_policy.py`, `tests/test_alert_policy.py` (4 ca đạt). `evaluate_gates.py`: G13 đọc
  `outputs/e2e/protocol/alert_policy_v2.csv` (copula-t, isotonic, 13 tuần); dòng cũ thành `G13_v1`.
- **Chưa commit:** `.publish-repo` có 492 file agent kia đồng bộ lúc 11:31 chưa commit; sẽ commit một lần sau khi hàng đợi xong.

## 10. Không có dữ liệu thật: luồng go/no-go (agent1-Khanh, 21/10/2026 16:05)

- Người dùng xác nhận **không có dữ liệu doanh nghiệp thật**. Chốt luồng kỹ thuật + luật an toàn, không chốt hiệu năng với doanh nghiệp thật:
  `docs/03_Evaluation/GO_NO_GO_SYNTHETIC_ONLY.md` (GO bậc 0 "bóng"; NO-GO mọi bậc hành động; cam kết duy nhất: không tệ hơn B1d và tự thoái lui).
- `agent1/eval/fallback_gate.py` + `tests/test_fallback_gate.py` (4 ca đạt): thoái lui BLEND → B1d sau 4 tuần thua >5%, chỉ dùng dữ liệu đến t-1.
- `scripts/sprint5/build_tgt2.py`: bộ đích niêm phong 40 công ty (xếp hàng chờ RAM ≥ 2,5 GB). **Chỉ chạy luồng đóng băng đúng một lần**; tiêu chí đăng ký trước ở mục 4 của tài liệu go/no-go.

## 11. G13 v2 và tgt2 (agent1-Khanh, 21/10/2026 22:30)

- Máy tắt ~16:30 giữa `P4`; G13 backtest src, G13 policy, T9-source-policy đã xong trước đó. Chạy lại từ P4: `scripts/sprint5/queue_rest2.sh` (log `outputs/implementation/queue_rest2.log`).
- **G13 v2 trên tgt: TRƯỢT** (chính sách đóng băng τ=0,30, k=1, isotonic): phát hiện ≥4 tuần 0,94 [0,87; 1,00], độ sớm trung vị 11,6 tuần,
  **báo giả 2,08/công ty-năm (cổng ≤1)**. Trên src (cùng chính sách) báo giả 0,75 ⇒ lỗi chuyển miền, không chỉnh theo tgt.
- `tgt2` đã sinh (40 công ty, 153.963 HĐ, 71 sự kiện / 20 công ty, niêm phong). `scripts/sprint5/run_tgt2_frozen.py` chạy T6 + chấm chính sách đóng băng
  đúng một lần, tự khởi động sau bước `gates-mid`. Giới hạn: tgt2 `write_xml=0` ⇒ nhãn oracle (không có đường T9 ước lượng), kết quả là cận trên so với E2E.
- 22:19–22:48: `P4`, `collection-policy`, `copula-hierarchy`, `IW-oof` đều **passed**; `gates-mid` chạy xong; `scaling` bắt đầu 22:48.
- **P4 (đặc trưng dừng): KHÔNG bật mặc định** theo quy tắc đăng ký trước (không xấu đi >1% ở đâu, và ≥2% ở một bộ thật):
  A gốc 2023 −1,4% [−2,7; −0,1], A gốc 2024 +0,4%, **B (tgt M12) −5,8% [−7,3; −3,1]**, CI +0,06%, **BPI +6,3% [2,3; 9,5]**.
  Giúp BPI rõ, nhưng hại tgt ⇒ giữ tuỳ chọn `stationary_features=False`. Không mở ablation theo miền (ngoài danh sách).
- `tgt2` frozen run khởi động 22:48 song song `scaling` (RAM khả dụng 3,6 GB, commit dự phòng 17 GB — an toàn).

## 12. HOÀN TẤT (agent1-Khanh, 21/10/2026 23:30) — commit `ad9effa` trên `agent1-Khanh`

- Chuỗi xong: `scaling` passed (22:58), báo cáo + cổng sinh lại; **340/340 kiểm thử đạt**.
- **tgt2 (niêm phong, chạy đúng một lần):** G13 chính sách đóng băng: phát hiện 0,746 [0,59; 0,84], độ sớm 7 tuần, báo giả 0,75 [0,43; 1,10]
  ⇒ đạt điểm ước lượng (dòng tham khảo `G13_tgt2`). cov80 copula-t gốc 0,62/0,72 (hẹp); **copula-t + ACI 0,767/0,771** (tgt: 0,754/0,767).
  Tiêu chí 1 (BLEND vs B1d) **chưa đo trên tgt2**. Chi tiết: `docs/03_Evaluation/GO_NO_GO_SYNTHETIC_ONLY.md` mục 4b, `G13_ALERT_POLICY.md` mục 4.
- **Cổng cuối:** đạt G1, G2, G5, G6, G9, G10, G12, G16, G18; trượt G3, G4, G7, G8, G11, G13 (tgt), G14, G15, G17. **Pilot NO-GO** cho bậc hành động;
  **GO bậc 0 "bóng"** với luật an toàn (BLEND neo B1d, cổng thoái lui, dải tiền copula-t + ACI, cảnh báo có người duyệt).
- **Việc mở còn lại (không chặn bậc 0):** G15 T9 (độ phủ ghép 0,47), G3/G4 hiệu chỉnh T1, G7 (tinh chỉnh M12), G14/G17;
  thử cổng thoái lui trên `hc_supply_shock`/`hc_retention`; bộ AR thật nhiều công ty để kiểm định giống/khác.

## 13. Sau hoàn tất: đóng các lỗ hổng còn lại (agent1-Khanh, 22/10/2026)

- **Tiêu chí 1 trên tgt2 (BLEND vs B1d): ĐẠT** — `scripts/sprint5/blend_fallback_eval.py`, luồng triển khai T1 (tinh chỉnh M12, w chọn trên cửa sổ
  hiệu chỉnh trước O của chính DN ⇒ w = 1,0): **+47,5% [30,9; 60,7]**. hc_supply_shock +46,2%, hc_retention +85,7%.
- **Cổng thoái lui:** tổng hợp — gần như không kích hoạt (mô hình không thua), tốn < 1 điểm. **Dữ liệu thật BPI**: DH-GBM thuần −62,5% → +cổng −22,3%;
  BLEND +6,5% → BLEND+cổng +4,7% [2,4; 6,7]. Customer Invoices tái lập đúng v2 (+13,1% / +14,4%). Tham số cổng đặt trước, không chỉnh theo BPI.
  ⇒ BLEND là lớp bảo vệ chính, cổng là lưới an toàn thứ hai (`GO_NO_GO_SYNTHETIC_ONLY.md` mục 4c–4d).
- **Đính chính T9:** "recall 0,47 / F1 0,63" là của quy tắc R1. Phương pháp triển khai trên tgt: **F1 0,796, precision 0,925** (cổng: F1 ≥ .80, P ≥ .95)
  ⇒ trượt sát nút, chủ yếu do precision. `docs/03_Evaluation/T9_RECALL_DIAGNOSIS.md`.
- **T9 lớp chặn bằng chứng** (`agent1/models/t9_fast.py::corroborate_below`, mặc định None = hành vi cũ; `tests/test_t9_corroboration.py`):
  liên kết qua mô hình khách có độ tin cậy < g chỉ tự động khi số HĐ có trong nội dung CK hoặc tên người chuyển khớp ≥ 90.
  Chọn (τ, g) trên DN nguồn giữ lại, đo một lần trên tgt/hc: `scripts/sprint5/t9_guard.py` → `outputs/t9/sprint5/`.
- `docs/00_INDEX.md` cập nhật trạng thái cuối (bỏ các dòng "đang chạy lại", số thế giới cũ).
- **T9 lớp chặn: giả thuyết bị bác** — mọi (g, τ) trên nguồn cho cùng P 0,951–0,952 ⇒ chọn không chặn; tgt tái lập P 0,925 / F1 0,796.
  Phân rã theo phương pháp (`outputs/t9/sprint5/method_breakdown.csv`): số HĐ trong nội dung CK precision 1,0; `R1_unique_amount` 0,96/0,95;
  `ML_subset` 0,87/0,81 (54% liên kết sai trên tgt); `hazard_weighted_subset` **0,54/0,50**. Độ tin cậy khách trung vị 1,0 kể cả khi sai.
  Không đổi quy tắc chọn sau khi nhìn tgt; đề xuất đăng ký trước và đo trên `tgt3` mới (`T9_RECALL_DIAGNOSIS.md` mục 2b–3).
- **Cổng thoái lui trên AR thật** (`scripts/sprint5/real_fallback_eval.py`): BPI DH-GBM −62,5% → +cổng −22,3%; BLEND +6,5% → +cổng +4,7% [2,4; 6,7].
- **Dịch vụ: dải công bố = copula-t + ACI** (`agent1_service/jobs/aci_band.py`; `nightly.run(aci_state=...)`; `/forecast` lưu trạng thái ACI theo DN ở store kind
  `aci_state`, id `current`). Phản hồi có `band_method`, `aci_ready` (≥ 8 tuần lộ diện), `band_note`, `band_raw`. Kiểm thử `tests/test_aci_band.py`,
  `tests/test_service_aci_state.py`. Gọi `run` trực tiếp không truyền `aci_state` giữ dải gốc (script nghiên cứu cũ không đổi).
- Prompt giao việc tiếp: `docs/05_Coding_Agent_Plan/PROMPT_GIAO_VIEC_2026-10-22.md`.
