# Prompt giao việc cho coding agent (sau Sprint 1 của agent1-Khanh, 21/10/2026)

> **Lưu trữ lịch sử:** prompt này ghi yêu cầu của ngày 21/10 và đường dẫn máy cũ. AI đang làm việc trong repo không được coi phần bên dưới là nhiệm vụ hiện hành; xem [hướng dẫn đọc](../AI_READING_GUIDE.md).

Dán nguyên phần trong khung cho agent kia.

---

> Bạn tiếp tục dự án Agent 1 tại `C:\Users\Admin\Downloads\Agent1`. **Đọc trước:**
> `docs/05_Coding_Agent_Plan/NHAT_KY_SPRINT1_2026-10-20.md` (nhật ký Sprint 1) và `09_KE_HOACH_TIEP_THEO_2026-10-20.md`.
>
> **Bối cảnh bắt buộc phải hiểu:** agent1-Khanh đã sửa một lỗi gốc trong `agent1/models/t1.py::expand` (khai triển hazard giữ sự kiện
> trong tuần bị cắt dở nhưng bỏ không-sự-kiện ⇒ hazard bị thổi phồng; nay chỉ dùng tuần quan sát đủ, cờ `FULL_WEEK_ONLY`,
> tái lập bản cũ bằng `AGENT1_EXPAND_LEGACY=1`) và kẹp z của `HazardLR` (`Z_CLIP=5`). Mọi CSV có hazard trước 20/10/2026 dùng
> `expand` cũ. Giao thức dữ liệu thật mới ở `scripts/sprint1/run_real_v2.py` (chọn trên mô hình học trước cửa sổ hiệu chỉnh, rồi học lại
> toàn bộ trước gốc; BLEND neo B1d). Kết quả Customer Invoices: DH-GBM +13,1% [8,3; 17,9], BLEND +14,4% [11,7; 17,4] so với B1d.
> **Không sửa `expand`, `HazardLR._prep`, `run_real_v2.py`** — nếu nghi ngờ, ghi vào nhật ký và hỏi.
>
> **Việc 1 — Chạy lại toàn chuỗi với `expand` mới (ưu tiên cao nhất).**
> 1. Trước khi chạy: với mỗi CSV dưới đây, sao lưu thành `<tên>.legacy_expand.csv` (không xoá).
> 2. Trong từng script tạo các CSV đó, thêm hậu tố `-fullweek` vào `measurement_version`.
> 3. Chạy theo thứ tự (dùng `scripts/run_plan.py`, `AGENT1_THREADS=4`, kiểm tra RAM trống ≥3 GB trước job lớn):
>    `A, B, DA-paired, T1-variants, onboarding, EF, noisy-EF, T9-T1, T3-T1, crisis-ablation, DR-eval, E2E-full, T6, regime-cash,
>    collection-policy, copula-hierarchy, IW-oof, scaling` (scaling cuối cùng, tốn nhất).
> 4. Sau mỗi job ghi một dòng vào `NHAT_KY_SPRINT1_2026-10-20.md` mục "Chạy lại": job, thời gian, số chính trước → sau.
>
> **Việc 2 — Thay exp_C bằng giao thức v2 trong luồng chính.**
> 1. Thêm job `C-v2` vào `scripts/run_plan.py` chạy `scripts/sprint1/run_real_v2.py --data ci,bpi`.
> 2. Sửa `scripts/evaluate_gates.py` cho G5/G6 đọc `outputs/t1/real_v2/C_real_v2.csv` (đăng ký trước, không đổi sau khi xem):
>    - G5: mô hình triển khai `BLEND(DH-GBM,B1d) w=*` (w chọn trên cửa sổ hiệu chỉnh) cải thiện pinball so với B1 ≥10% trên Customer Invoices
>      **và** `improvement_ci_low > 0` so với B1d.
>    - G6: trên **cả hai** bộ (ci, bpi), mô hình triển khai không thua B1d: `improvement_ci_high ≥ 0` và điểm ước lượng ≥ −2%.
>    - Giữ dòng cổng cũ dưới tên `G5_v1/G6_v1` để kiểm toán.
> 3. Đánh dấu `exp_C` cũ trong `run_t1.py` là legacy (docstring), không xoá.
>
> **Việc 3 — Đặc trưng không dừng (P4 trong nhật ký), ablation có kiểm soát.**
> Thêm tuỳ chọn `stationary_features=True` trong `features.py`: `f_n_hist → log1p`, kẹp theo phân vị 99 của train; `c_tenure_days → log1p`;
> bỏ `issue_month`, `cut_month` khi lịch sử DN <24 tháng. Đo trên src (A), tgt (B, M=12), ci và bpi (v2) với CI cặp. Chỉ bật mặc định nếu không
> xấu đi ở đâu quá 1% và cải thiện ≥2% ở ít nhất một bộ thật. Ghi kết quả vào nhật ký.
>
> **Việc 4 — G3 (độ phủ T1).** CQR hai phía cho phép thu hẹp + Mondrian CQR theo nhóm đáo hạn (hạn trong tuần 1–2 / 3–6 / >6 / đã quá hạn),
> hiệu chỉnh trên cửa sổ nguồn. Tiêu chí cov80 ∈ [75, 85]% ở cả hai gốc của A; IS80 không xấu đi.
>
> **Việc 5 — T9 (G15).** Theo `09_KE_HOACH...` Sprint 3: phân tích lỗi theo loại trên nguồn; xử lý `retention`, `cod_realistic`; tau và hàng chờ chọn
> trên nguồn; báo đường precision–coverage.
>
> **Việc 6 — Dọn và đồng bộ.** `python scripts/make_report.py`; cập nhật `00_INDEX.md` (bỏ dòng "ensemble giảm MAE 17%" của v1, thay bằng số v2 và
> ghi rõ ngày); chạy `pytest` toàn bộ; commit + push lên nhánh `agent1-Khanh` của `https://github.com/Khanhhh239/Multi-Agent-Finance.git`
> (không đưa dữ liệu thô, parquet, `.state`, token; kết thúc commit bằng dòng `Co-Authored-By`).
>
> **Quy tắc:** không dùng `tgt`/test để chọn tham số; không mở ablation ngoài danh sách; mỗi việc xong phải có CSV + dòng nhật ký.
> Việc G13 (chính sách cảnh báo thiếu hụt) **để lại cho agent1-Khanh** sau khi E2E chạy lại xong.

---

## Ghi chú cho người giao việc
- Việc 1 mất nhiều giờ CPU (E2E ~30 phút, scaling vài giờ). Có thể chạy Việc 3–5 song song nếu khác file, nhưng không chạy hai job nặng cùng lúc (RAM 15,7 GB, thường chỉ còn 2–3 GB trống).
- Phần agent1-Khanh giữ: kết luận BPI v2, G13 (cảnh báo thiếu hụt: hiệu chỉnh xác suất, trễ xác nhận, ngưỡng theo chi phí) sau khi E2E có số mới.
