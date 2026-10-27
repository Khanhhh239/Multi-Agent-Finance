# WP-2 T2/T3 · WP-3 Thích nghi miền

> **Hồ sơ kế hoạch từ 15/10/2026.** Các trạng thái, lệnh và danh sách việc dưới đây phản ánh thời điểm lập; đọc [tiến độ hiện hành](TIEN_DO_TRIEN_KHAI.md) trước khi dùng.

---

## WP-2 · T2 nợ xấu và T3 tranh chấp/trả một phần

### WP-2.1 Sửa nhãn SBA và đo lại (X1, L3) — P0
- **File**: `agent1/data/real_loaders.py::sba_7a`, `scripts/run_t2_t3.py::t2_sba`.
- **Việc**: thêm tham số `exempt="drop"|"keep"|"censor"`.
  - `drop`: loại `LoanStatus=="EXEMPT"` (và tính lại tỷ lệ nền).
  - `keep`: như hiện tại (để so).
  - `censor`: coi EXEMPT là kiểm duyệt phải tại as-of: dùng `CureGBM`-kiểu loại khỏi huấn luyện, báo cáo riêng.
- **Phân tầng đánh giá**: `TermInMonths ≤120` (khoản vốn lưu động/thương mại) vs `>120` (BĐS). Báo cáo mọi chỉ số trong nhóm ≤120 tháng — đây mới gần hoá đơn B2B.
- **Giả thuyết**: PR-AUC/nền ≥5 trong nhóm ≤120 tháng sau khi loại EXEMPT; hiệu chỉnh theo năm sai lệch <40% tương đối.
- **Cải thiện hiệu chỉnh theo FY**: thêm đặc trưng chu kỳ vĩ mô *chỉ dùng thông tin biết tại ngày phê duyệt* (lãi suất, tỷ lệ xoá nợ của cohort 1 năm trước); không dùng tỷ lệ xoá nợ cùng năm (rò rỉ).
- **Đầu ra**: `outputs/t2_t3/t2_sba_variants.csv` (3 biến thể × 4 mô hình × 2 phân tầng).

### WP-2.2 Cure đầy đủ trong T6 (chuẩn bị)
- **File**: `agent1/models/t1.py::CureGBM` → thêm `predict_proba_calibrated` (isotonic trên cửa sổ hiệu chỉnh).
- **Làm**: xuất cho mỗi HĐ mở `p_bad`; truyền vào `simulate(...)` (tham số mới `p_bad`): mỗi đường rút Bernoulli(p_bad_i) *tương quan* với sốc chung (`u_bad = Φ(√ρ_bad·g + …)`), HĐ vỡ nợ có thu hồi 25% với độ trễ 120–360 ngày.
- **Kiểm**: tổng tổn thất kỳ vọng mô phỏng ≈ Σ p_bad·amt (sai <2%).

### WP-2.3 T3 — giữ EB, mở rộng dữ liệu thật
- **File**: `scripts/run_t2_t3.py::t3_synth`.
- **Việc**: tải **Home Credit `installments_payments`** (xem WP-D4.1), map: `DAYS_INSTALMENT→due`, `DAYS_ENTRY_PAYMENT→paid`, `AMT_INSTALMENT`, `AMT_PAYMENT`; xây `payments` kiểu partial.
- **Thí nghiệm**: dự đoán `paid_ratio<0.995` và `late>0` — EB vs LightGBM vs hồi quy tỷ lệ; kiểm lại kết luận "EB đủ".
- **Tiêu chí**: nếu LGBM thắng EB trên dữ liệu thật ≥3% AUC ⇒ chuyển sang LGBM cho T3.

### WP-2.4 Tranh chấp → độ trễ
- Quan hệ đã biết trong máy phát (+15–75 ngày). Thêm `p_dispute` làm đặc trưng cho T1 *tại ngày lập* (đặc trưng mới `c_disp_eb`); đo giảm pinball trên HĐ có tranh chấp.

---

## WP-3 · Thích nghi miền (trọng tâm đề bài)

**Mục tiêu**: định lượng "cần bao nhiêu tháng dữ liệu của DN đích để vượt mốc", và chiến lược thích nghi tốt nhất. Mã đã viết: `scripts/run_t1.py::exp_B`, `domain_weights`. Kết quả cũ chưa có do tiến trình bị gián đoạn.

### WP-3.1 Chạy lại exp B có kiểm soát — P0
- **Việc**: `python scripts/run_t1.py --exp B` với `AGENT1_THREADS=6`; nếu OOM, giảm `Ssrc` bằng cách lấy chu kỳ 28 ngày (`cut_src`).
- **Bổ sung vào exp B** (sửa mã):
  1. Lưu `B_domain_adaptation_tgt.csv` kèm cột `strategy`, `months_history`, `n_target_rows`.
  2. Thêm mốc **B1d với lịch sử M tháng** (đã có) và **"Customer-EB"**.
  3. Thêm chiến lược **S5 = ENS(S3, B1d)** (trung bình phân vị).
  4. Đo **thời gian huấn luyện** từng chiến lược.
  5. Bootstrap theo công ty (14 công ty) cho CI.
- **Tạo biểu đồ** `outputs/t1/B_learning_curve.png` (pinball vs M, mỗi chiến lược một đường).

### WP-3.2 Kiểm giả thuyết DA1–DA7
Bảng 04_AI_Methods/05 §5.4. Với mỗi DA, ghi **Chấp nhận/Bác bỏ** + số + CI vào 03_Evaluation/04 §4.9.

### WP-3.3 Domain randomization (X20) — P0
- **File**: `scripts/build_worlds.py`; **tạo** `scripts/build_multiworld.py`.
- **Việc**: sinh `K=20` thế giới huấn luyện `dr_000..dr_019`, mỗi cái 12–15 công ty, tham số lấy ngẫu nhiên (Sobol/LHS):
  `tail∈{atradius,uk,coface}`, `late_scale∈[0.7,1.5]`, `dispute_scale∈[0.5,2]`, `posting_mode_p∈Dirichlet`, `payrun_p∈Dirichlet`, `memo_invoice_no_p∈{Beta(a,b)}`, `cod_mult∈[1,2.4]`, `ontime_shift` ± 0.3, `revenue_median∈[10e9,60e9]`, `n_cust_median∈[20,100]`.
  Ghi `design.csv` (tham số mỗi thế giới) để phân tích hồi quy "tham số nào gây sụt giảm".
- **So sánh**: (A) 1 thế giới × 400 công ty; (B) 20 thế giới × 20 công ty — **cùng tổng số hoá đơn**. Đánh giá zero-shot ở `tgt` và `sens_*` + Customer Invoices.
- **Tiêu chí**: (B) giảm pinball zero-shot ≥5% so với (A) hoặc bác bỏ.

### WP-3.4 Khoảng cách miền (X22)
- **Việc**: bộ phân loại miền (LightGBM) phân biệt snapshot `src` vs `tgt` vs `sens_*` vs Customer Invoices; báo cáo AUC và 10 đặc trưng khác biệt nhất.
- **Dùng**: tiêu chí quyết định dùng IW hay không (AUC>0,9 ⇒ IW không ổn, dùng fine-tune).

### WP-3.5 Test-time adaptation đơn giản
- Thêm đặc trưng cập nhật nhanh (EWM 30 ngày) và `f_resid_7d`; thử tắt/bật; đo giai đoạn khủng hoảng (2021-07→10, 2022-10→2023-06): gói `eval_by_regime`.

### WP-3.6 Tiền huấn luyện lớn (X21, DA6)
- Sau WP-D3 (sinh lớn): huấn luyện `HazardGBM` trên 1M/3M/10M hàng khai triển; vẽ pinball(zero-shot `tgt`) theo kích cỡ (scaling). Tìm điểm bão hoà.

### WP-3.7 Chọn chính sách onboarding
- Từ kết quả: viết `agent1/models/onboarding.py` — hàm `choose_strategy(M, n_rows, domain_distance)` trả chiến lược (zero-shot / fine-tune / tgt-only / ens với B1d). Kèm kiểm thử trên đường cong.

**Cách chạy WP-3**: `AGENT1_THREADS=6 python scripts/run_t1.py --exp B` (dự kiến 1–3 giờ).
**DoD WP-3**: DA1–DA7 có kết luận; biểu đồ đường cong học; `choose_strategy` + kiểm thử; G7 có bằng chứng.
