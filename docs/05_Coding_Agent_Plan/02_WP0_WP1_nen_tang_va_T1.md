# WP-0 Nền tảng · WP-1 Cải tiến T1

> **Hồ sơ kế hoạch từ 15/10/2026.** Các trạng thái, lệnh và danh sách việc dưới đây phản ánh thời điểm lập; đọc [tiến độ hiện hành](TIEN_DO_TRIEN_KHAI.md) trước khi dùng.

Mỗi bước: **file** → **việc** → **cách làm** → **kiểm**. Ưu tiên P0.

---

## WP-0 · Nền tảng chất lượng (1–2 ngày)

### WP-0.1 Ghim môi trường
- **Tạo** `requirements.txt` (từ `.venv/Scripts/pip freeze`, giữ gói trực tiếp) và `requirements-lock.txt` (đầy đủ).
- **Tạo** `Makefile`/`scripts/dev.ps1` với `test`, `lint`, `world-small`, `report`.
- **Kiểm**: môi trường mới cài từ `requirements.txt` chạy `pytest` xanh.

### WP-0.2 Hợp đồng dữ liệu (data contract)
- **Tạo** `agent1/data/contracts.py` với hàm `validate_world(dir)`: kiểm cột/kiểu/khoá/miền giá trị của `invoices, payments, bank_txns, promises, outflows, firms, customers, events, macro, daily_cash`.
- **Kiểm bất biến** (TC-01): `paid_date_true ≥ issue_date`; Σ `payments.amount` ≤ `amount_gross` + thu hồi; ≥98,5% `pay_date_true` là ngày làm việc; MST hợp lệ; `balance` khớp luỹ kế; `customers` không bị đưa vào đặc trưng (kiểm bằng danh sách cột cấm).
- **Gọi** trong `World.run()` cuối cùng (cảnh báo/raise) và trong `build_worlds.py`.
- **Kiểm**: chèn lỗi có chủ ý → `validate_world` bắt được.

### WP-0.3 Kiểm thử rò rỉ (TC-02, TC-03)
- **Tạo** `tests/test_features.py`:
  1. Dựng `SnapshotBuilder` trên `smoke` (3 công ty); với T cố định, **xoá mọi hoá đơn có `issue_date > T`** và mọi thanh toán `> T` rồi tính `snapshot(T)` ⇒ đặc trưng phải **không đổi** (trừ cột nhãn).
  2. `add_labels(df, label_end)`: kiểm `event`, `time_obs`, `bad_known` trên bộ ca tay.
- **Kiểm**: kiểm thử đỏ nếu cố tình thêm đặc trưng nhìn tương lai.

### WP-0.4 Kiểm thử mô hình cơ bản (TC-04, 05)
- **Tạo** `tests/test_t1_math.py`: hazard ngẫu nhiên ⇒ `Σ P + S_K = 1`; `quantiles_from_hazard` đơn điệu; `expected_days` trong [0, 120+]; CQR trên dữ liệu hoán đổi được đạt độ phủ ≥1−α−0,02.

### WP-0.5 Báo cáo tự động
- Mở rộng `scripts/make_report.py`: thêm CI bootstrap theo công ty; bảng so với mốc ở dạng "% cải thiện"; tự cập nhật bảng trong `docs/03_Evaluation/04_ket_qua_hien_co.md` giữa hai thẻ `<!-- AUTO:... -->`.
- **Kiểm**: chạy hai lần cho kết quả giống nhau.

---

## WP-1 · Cải tiến và đo lại T1

Mã chính: `agent1/models/t1.py`, `scripts/run_t1.py::exp_A`. Mọi thay đổi chạy lại `exp A` và so với bảng 03_Evaluation/04 §4.1 (bảng cũ lưu thành `outputs/t1/A_rolling_origin_src.v1.csv` trước khi ghi đè).

### WP-1.1 Sửa đo: CDF công bằng cho mô hình phân vị (X3, L2)
- **Việc**: `QuantileLGBM` hiện có 3 phân vị ⇒ CDF thô. Thêm `QuantileLGBM(alphas=np.linspace(0.05,0.95,19))` và hàm `cdf_from_quantiles(Q, alphas, grid=7*np.arange(1,14))` (nội suy đơn điệu PCHIP).
- **Làm**: tham số `alphas` cấu hình; `fit` chạy song song 19 mô hình (n_jobs hạn chế) hoặc dùng `objective="quantile"` với `alpha` lặp; để tiết kiệm, dùng 9 phân vị {.05,.1,.2,.3,.5,.7,.8,.9,.95}.
- **Đo**: IBS/WAPE của QLGBM, AFT, B1d với CDF mới. Giả thuyết: hiệu IBS so với DH-GBM vẫn ≥20%. Ghi vào kết quả "bị bác bỏ" nếu <10%.
- **Kiểm**: `evaluate` trả cả `IBS_13w_fair`.

### WP-1.2 Early stopping và tối ưu siêu tham số (X11)
- **Việc**: `HazardGBM.fit(valid=...)` đã hỗ trợ; **tạo** `scripts/tune_t1.py` dùng Optuna (thêm `optuna` vào requirements).
- **Làm**: mục tiêu = pinball trung bình trên cửa sổ hiệu chỉnh (không phải test); không gian: `num_leaves∈[15,127]`, `min_data_in_leaf∈[50,800]` (log), `lambda_l2∈[0.1,50]` (log), `feature_fraction∈[0.5,1]`, `learning_rate∈[0.02,0.1]`, `bagging_fraction∈[0.5,1]`; 50 trials, tối đa 12 phút/trial, `AGENT1_THREADS=6`; pruner = `MedianPruner`.
- **Quan trọng**: ghi `best_params.json`; chạy lại exp A với tham số mới; **không** dùng tập test để chọn.
- **Tiêu chí**: pinball giảm ≥3% mà cov80 và ECE không xấu đi.

### WP-1.3 Hiệu chỉnh khoảng hai phía (X2, L1)
- **Việc**: `cqr_fit/cqr_apply` hiện đối xứng 1 tham số. Thêm `cqr_fit_asym(y, Q, alpha_lo=0.1, alpha_hi=0.1)` (Romano 2019 hai phía: `q_lo = quantile(Q_lo − y, 1−α_lo)`, `q_hi = quantile(y − Q_hi, 1−α_hi)`) cho phép giá trị âm (thu hẹp).
- **Làm**: áp dụng cho mọi mô hình; thêm cờ `allow_shrink=True`.
- **Điều tra L1**: in `q̂` thực tế cho DH-GBM; xác nhận lý do hàng "+CQR" giống hệt.
- **Tiêu chí**: DH-GBM cov80 ∈ [78, 82]% với IS80 ≤ giá trị cũ.

### WP-1.4 Nhãn khoảng khi chỉ có sổ cái (interval-censored)
- **Bối cảnh**: DN không có sao kê ⇒ chỉ có ngày ghi sổ (lệch ngày thật). Cần hàm hợp lý khoảng: ngày trả thật ∈ [`last_seen_open`, `ledger_post_date`].
- **Làm**: trong `expand`, với nhãn khoảng `(L, R]` đặt `y_k = 1` nếu `R` thuộc tuần k **và** `L < 7(k−1)+1`; nếu khoảng trải qua nhiều tuần, dùng trọng số **phân bổ xác suất** theo hazard hiện tại (EM nhẹ: 2 vòng).
- **Tạo** `HazardGBM.fit_interval(df, left, right)`.
- **Kiểm**: trên `src` với nhãn sổ (ledger) + khoảng, so với (a) nhãn sổ thẳng, (b) nhãn ngân hàng. Giả thuyết: (c) nhãn khoảng ở giữa (a) và (b). Đây là một phần thí nghiệm F.

### WP-1.5 Đối chứng AFT đúng
- **Việc**: lưới σ ∈ {0.2,0.3,0.5,0.8} trên cửa sổ hiệu chỉnh; chọn σ; đặt cố định; chạy lại exp C để bảng thật có AFT đúng (L7).

### WP-1.6 BPI và trường hợp không có hạn (L8)
- **Việc**: khi `due_date` thiếu, tạo "hạn ảo" = `issue_date + trung vị khách` hoặc `issue_date + 30`; thêm cờ `no_due=1`; đặc trưng `days_to_due` bị thay bằng `age_days`.
- **Đo**: DH-GBM với đặc trưng thay thế vs B1d trên BPI. Nếu vẫn thua: ghi lại và khuyến nghị DN không có hạn dùng B1d + CQR.

### WP-1.7 Phân tầng báo cáo (§1.12 của 03_Evaluation/01)
- **Tạo** `agent1/eval/strata.py`: hàm gán nhóm (khách mới/quen, HĐ lớn top 10%, kỳ hạn, ngành, giai đoạn Tết/COVID/crunch, posting_mode, tail).
- **Làm**: `exp_A` xuất `A_strata.csv` với pinball/IBS/cov80/WAPE theo nhóm.
- **Tiêu chí**: nhóm tệ nhất được nêu tên trong báo cáo; không nhóm nào cov80 <60%.

### WP-1.8 Ổn định theo seed (X4)
- Chạy exp A với seed `{3,7,11}` của LightGBM; xuất CV; tiêu chí CV <0,5% ở pinball.

### WP-1.9 Cải tiến mô hình (thứ tự thử, mỗi cái là một nhánh thí nghiệm)
1. **Monotone constraints (X10)**: dùng `monotone_constraints` — hazard tuần k *giảm* khi `c_late_share`, `c_delay_eb`, `c_delay_ewm`, `c_max_dpd` tăng (khách hay trễ trả muộn hơn) và *tăng* khi `c_promise_rel` tăng; kiểm dấu bằng phụ thuộc từng phần (PDP) trước khi áp; chạy `tgt` zero-shot.
2. **Hazard theo ngày 28 ngày đầu (X12)**: thêm bin ngày cho k≤4: tạo `expand_daily(df, days=28)` + mô hình thứ hai; ghép đầu ra.
3. **Mixture (X13)**: xác suất "đúng ngày hạn ± 3" `π_i` bằng một mô hình riêng + hazard trễ có điều kiện.
4. **EB học k (X14)**: tìm `k` theo ngành bằng ML-II trên lịch sử.
5. **Đa nhiệm (X15)**: MLP nhỏ (PyTorch CPU) cho trả/không, tranh chấp, trả một phần — chỉ nếu 1–4 không đủ.
Mỗi bước phải thắng DH-GBM mặc định trên `tgt` zero-shot và `src`; nếu không, bỏ.

**Cách chạy gói**: `AGENT1_THREADS=6 python scripts/run_t1.py --exp A` (≈25–60 phút khi máy rảnh); báo cáo bằng `make_report.py`.

**DoD WP-1**: L1, L2, L7 đóng; có `A_strata.csv`; best_params; CQR hai phía; cov80 DH-GBM trong [78,82]%.
