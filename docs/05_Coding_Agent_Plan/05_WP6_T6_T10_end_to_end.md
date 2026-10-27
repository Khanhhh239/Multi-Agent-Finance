# WP-6 · T6 Monte Carlo + ACI + T10 + đầu-cuối (cổng chính G12, G13)

> **Hồ sơ kế hoạch từ 15/10/2026.** Các trạng thái, lệnh và danh sách việc dưới đây phản ánh thời điểm lập; đọc [tiến độ hiện hành](TIEN_DO_TRIEN_KHAI.md) trước khi dùng.

**Hiện trạng**: `agent1/models/t6_cash.py` (simulate, collection_kernel, ACI) và `scripts/run_t6.py` đã viết, **chưa được chạy xác nhận** (script được đưa vào chuỗi `run_rest.sh`, kết quả có thể chưa tồn tại). Bạn là người đầu tiên chạy và sửa lỗi đầu-cuối. Cổng: cov80 số dư ∈ [75,85]%, thắng 4 đối chứng, lead time ≥4 tuần.

## WP-6.1 Làm cho `run_t6.py` chạy được và sạch — P0
1. Chạy `AGENT1_THREADS=4 python scripts/run_t6.py > outputs/t6.log`. Sửa lỗi theo thứ tự xuất hiện. Điểm đã nghi:
   - dòng thừa `Xr, Yr, _, _ = R1_build = (None, None, None, None)` (L6) — xoá;
   - `direct_features` có biến thừa (`pos`, `d`, `inflow_hist`) — dọn;
   - `known_outflows`: `sup[4:] = sup_hist` dùng TB 13 tuần; kiểm hợp lý;
   - `m4` huấn luyện bằng `build(ss, True, lambda n: list(range(20, n-13-13-70)))` — đảm bảo cửa sổ train không chạm giai đoạn đánh giá (tgt/`src` test sau 2024-07);
   - `Ste` đã gồm `amount_open` có thể NaN: dùng `amount_gross` khi `paid_frac_so_far` NaN (đã làm; kiểm).
2. **Không để dò rò rỉ**: `truth_path` dùng số dư thật chỉ để chấm; `B0` là số dư tại T (thông tin biết). Kiểm.
3. Xuất: `outputs/t6/t6_interval_metrics.csv`, `t6_shortfall_metrics.csv`, `t6_rho.json`, `t6_predictions.parquet`, demo (`demo_band.csv`, `demo_collect_first.csv`, `demo_whatif.json`).

## WP-6.2 Sửa mô hình nếu cần (theo kết quả)

| Triệu chứng | Chẩn đoán | Sửa |
|---|---|---|
| cov80 thấp (<70%) ở tuần xa | thiếu bất định chi/doanh thu mới | tăng bất định T4 (CQR rộng), thêm lỗi dự báo chi NCC, `capex` |
| cov80 cao (>90%) | copula quá mạnh hoặc ACI quá rộng | giảm ρ, kiểm `ACI.interval` |
| P(thiếu hụt) lệch hệ thống | thiếu nhân vỡ nợ T2 hoặc kernel thu sai | WP-2.2 (p_bad), kiểm `collection_kernel` với cửa sổ 365 ngày |
| Thua LGBM trực tiếp ở tuần 1–2 | thiếu đặc trưng hành vi gần | thêm phần dư `f_resid_7d`; hoặc ensemble với trực tiếp |
| Chậm | nhiều HĐ mở | gộp HĐ nhỏ; CRN; giảm `n` ở tuần xa |

## WP-6.3 T10 hoàn thiện (`run_t6.py::t10_demo` → `agent1/models/t10.py`)
- **Tạo** `agent1/models/t10.py` với:
  - `explain_invoice(model, X_row)` → top-3 đóng góp âm/dương (dùng `pred_contrib`), ánh xạ tên đặc trưng → câu tiếng Việt qua `agent1/text/vi_templates.py` (bảng tên đặc trưng → mô tả).
  - `rank_collections(snapshot, P, sim_args, top_n=50)`: chọn top-n theo `amount × P(trễ >2 tuần)`, mô phỏng lại với CRN, trả `ΔP(thiếu hụt)`; chuẩn hoá theo "giờ công" nếu có.
  - `what_if(sim_args, delay_customer=None, delay_weeks=2, shift_out=None, revenue_drop=None)`.
  - `scenario_library()`: kịch bản tất định (toàn bộ khách +30/+60 ngày; khách top-1 vỡ nợ; doanh thu −30% 3 tháng) trả *runway*.
- **Mô phỏng chính sách** (E2E-4): chạy 3 chính sách trên `tgt` 52 tuần: (P0) không làm gì; (P1) đòi khoản to nhất trước; (P2) đòi theo ΔP; giả định đòi thành công kéo `tuần trả` về tuần 1 với xác suất `q` (q∈{0,3; 0,5; 0,7}); đo số sự kiện thiếu hụt và DSO. **Đây là mô phỏng chính sách, không phải bằng chứng nhân quả** — ghi rõ.
- **Cổng LLM**: `agent1/text/verbalize.py`: nhận bảng số → câu; `check_numbers(text, table)` đảm bảo 100% số trong câu có trong bảng (TC-09). Không gọi LLM thật trong CI (dùng mẫu); LLM chỉ nâng chất lượng câu và phải qua kiểm.

## WP-6.4 Ước lượng bậc tự do (X32) — P1
- Tải SEC FSDS 2020q1–q3 (cần `SEC_USER_AGENT="Tên tổ chức email"` của chính bạn — **không tự điền**; xem `scripts/crawl.py --list`). Lọc `NetCashProvidedByUsedInOperatingActivities`, chuẩn hoá theo tài sản, fit Student-t (MLE) trên thay đổi theo quý ⇒ `df̂`. Ghi vào `agent1/models/t6_cash.py::DEFAULT_NU`.

## WP-6.5 Copula phân tầng (X31) — P1
- Hai nhân tố: toàn danh mục `g` (ν=4) và nhóm theo khách `h_c` (mỗi khách một hệ số riêng, cùng khách các HĐ tương quan): `u_ic = Φ(√ρ_p·g + √ρ_c·h_c + √(1−ρ_p−ρ_c)·e_i)`; ρ_p, ρ_c chọn trên nguồn bằng IS. So với một nhân tố.

## WP-6.6 Đối chứng thêm
- **ARIMA/ETS** trên chuỗi dòng ròng (statsmodels) — mốc truyền thống.
- **Chronos** trực tiếp trên chuỗi số dư tuần (zero-shot) — xem nó mạnh đến đâu so với MC (kỳ vọng thua vì không biết lịch nghĩa vụ).
- **Bảng tính của DN (B0)**: đúng hạn + lịch chi — chính là "cách làm hiện tại".

## WP-6.7 Hiệu chỉnh ngưỡng cảnh báo
- Đường PR/ROC cho `P_4w`, `P_13w`; chọn ngưỡng theo chi phí (c_miss/c_false ∈ {2,5,10}); đo lead time và báo giả/DN-năm (G13). Xuất `outputs/t6/alert_policy.csv`.

## WP-6.8 E2E (E2E-1..4)
- **Tạo** `scripts/run_e2e.py`: từ `tgt` thô → T9 (links) → nhãn ước lượng → T1 (fine-tune 12 tháng) → T4 → T5 → T6+ACI → T10; gọi theo từng điểm cắt tuần; ghi dự báo & kết quả thật; đo mọi chỉ số E2E. Hiển thị **lan truyền sai số T9→T1→T6** (so với dùng `*_true`).
- **Tiêu chí**: G12, G13 trên nhãn ước lượng (không chỉ nhãn thật); báo cáo "trường hợp sai" (tuần thiếu hụt không báo; DN có sai nhiều nhất).

## WP-6.9 Berka (E-T6c, X33)
- Chạy phân vị trực tiếp + ACI trên chuỗi dòng ròng tuần Berka (train 1993–96, test 1997–98), cov80 theo tài khoản; đây là kiểm tra khả năng hiệu chỉnh khoảng trên **dữ liệu dòng tiền thật** (không phải mô hình hoá đơn).

**DoD WP-6**: G12, G13 có kết luận; `demo_*` tái lập; `t10.py` + kiểm thử TC-07/09; bảng đối chứng đầy đủ; `run_e2e.py` chạy trong ≤60 phút trên `tgt`.
