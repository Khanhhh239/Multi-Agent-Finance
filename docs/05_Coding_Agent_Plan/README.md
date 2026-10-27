# 05 · Kế hoạch giao việc cho Coding Agent tiếp theo

> **Bộ kế hoạch lịch sử lập từ 15/10/2026.** Trạng thái triển khai đọc ở
> [TIEN_DO_TRIEN_KHAI.md](TIEN_DO_TRIEN_KHAI.md), rồi đối chiếu mã/CSV trên đĩa.
> Các câu giao việc, lệnh chạy, số ca kiểm thử và mô tả “chưa có/chưa chạy” trong
> file 01–08 không phải chỉ dẫn hay kết luận hiện hành cho AI.

**Bối cảnh khi lập kế hoạch:** dữ liệu + T0–T9 đã có mã và đã đo lần đầu (T1, T2, T3, T4, T6, T7, T8, T9, thích nghi miền); T10 demo còn lỗi, API/dashboard/giám sát chưa có. Mục tiêu khi đó là hoàn thành sản phẩm chạy được, đo được, đáng tin.

> **Mốc 15/10:** sau lần chạy đầu, một phiên khác đã bắt đầu WP-0/WP-1/WP-6 trong cùng thư mục (thêm `t10.py`, `t7_portfolio.py`, `t8_promise.py`, `reconciliation_pipeline.py`, `tune_t1.py`, `validate_worlds.py`; sửa `features.py`/`t1.py`/`run_t1.py`/`run_t6.py`/`make_report.py`). Các CSV A, B, E/F, T6 lúc đó dùng giao thức trước sửa; nhật ký và kết quả mới hơn đã thay thế. Đoạn này giữ để hiểu thứ tự các lần đo.

**Thứ tự đọc của bộ kế hoạch gốc:** `00_INDEX.md` → `01_Business_Analyst/02_problem_statement.md` → `02_Data/01, 04` → `03_Evaluation/03, 04` → `04_AI_Methods/01, 02` → tài liệu này. Để bắt đầu công việc mới, dùng [hướng dẫn đọc hiện hành](../AI_READING_GUIDE.md).

| File | Nội dung |
|---|---|
| [01_hien_trang_va_quy_uoc.md](01_hien_trang_va_quy_uoc.md) | Bản đồ mã, môi trường, cách chạy, quy ước code/số liệu, lỗi đã biết |
| [02_WP0_WP1_nen_tang_va_T1.md](02_WP0_WP1_nen_tang_va_T1.md) | Kiểm thử nền, hợp đồng dữ liệu; cải tiến T1 (X2, X3, X10–X14) |
| [03_WP2_WP3_T2_va_thich_nghi_mien.md](03_WP2_WP3_T2_va_thich_nghi_mien.md) | Sửa nhãn SBA, Home Credit, T3; hoàn thiện thí nghiệm B thích nghi miền, domain randomization |
| [04_WP4_WP5_WP7_WP8_T9_T5_T7_T8.md](04_WP4_WP5_WP7_WP8_T9_T5_T7_T8.md) | T9 lai quy tắc+ML, T5 mở rộng, T7 cụm, T8 lời hứa |
| [05_WP6_T6_T10_end_to_end.md](05_WP6_T6_T10_end_to_end.md) | Hoàn thiện Monte Carlo, ACI, T10, E2E |
| [06_WPD_du_lieu.md](06_WPD_du_lieu.md) | Vector hoá máy phát, hard-case worlds, sinh quy mô lớn, C2ST, dữ liệu thật bổ sung |
| [07_WP9_WP10_san_pham_va_pilot.md](07_WP9_WP10_san_pham_va_pilot.md) | API, dashboard, LLM diễn giải, giám sát, chuẩn bị pilot T13 |
| [08_thu_tu_va_lich.md](08_thu_tu_va_lich.md) | Đồ thị phụ thuộc, thứ tự ưu tiên, mốc, tiêu chí hoàn thành toàn bộ |
| [NHAT_KY_SPRINT1_2026-10-20.md](NHAT_KY_SPRINT1_2026-10-20.md) | **Nhật ký thực thi** Sprint 1–5: sửa `expand`, chạy lại, G13, tgt2, cổng thoái lui |
| [09_KE_HOACH_TIEP_THEO_2026-10-20.md](09_KE_HOACH_TIEP_THEO_2026-10-20.md) | Kế hoạch sprint sau Sprint 1 |

Các bản `PROMPT_GIAO_VIEC_*.md`, `CHIEN_LUOC_TIEP_THEO_2026-10-24.md`,
`HIEN_TRANG_AGENT1_KHANH_2026-10-25.md` và
`TIEN_DO_2026-10-16_lich_su.md` là hồ sơ theo ngày/commit, không dùng làm
trạng thái hiện hành. Bảng tổng hợp mới nhất trong repo là
[TIEN_DO_TRIEN_KHAI.md](TIEN_DO_TRIEN_KHAI.md), cần đối chiếu mã và CSV.

## Nguyên tắc ghi trong kế hoạch gốc

1. **Không đổi kết luận bằng cách đổi cách đo.** Sửa đo → chạy lại mọi mốc. Mốc đơn giản luôn chạy cùng mô hình mới.
2. **Mỗi gói việc kết thúc bằng 3 thứ:** (a) mã + kiểm thử, (b) CSV kết quả trong `outputs/`, (c) cập nhật `docs/03_Evaluation/04_ket_qua_hien_co.md` (số lấy từ CSV, không gõ tay).
3. **Kết quả xấu ghi lại.** Nếu giả thuyết sai, ghi "bị bác bỏ" kèm số và nguyên nhân giả định.
4. **Chống rò rỉ là việc số 1.** Mọi đặc trưng tính *as-of T*; mọi tập kiểm tra tách thời gian; hiệu chỉnh cách test ≥120 ngày; `tgt` niêm phong.
5. **Giới hạn luồng** (`AGENT1_THREADS`) — máy dùng chung, quá tải luồng làm chậm 10–50×.
6. **Giữ tiếng Việt cho tài liệu, tiếng Anh cho định danh code.** Comment/docstring tiếng Việt như mã hiện tại.
7. **Không tự sinh số bằng LLM** trong sản phẩm; bất kỳ văn bản LLM nào phải qua cổng đối chiếu số.
8. **Không commit dữ liệu thô** (`data/raw`, `data/interim`, `data/processed`, `data/synthetic/*/*.parquet`) — đã nằm trong `.gitignore`; chỉ commit mã, cấu hình, CSV kết quả nhỏ và docs.
9. **Hỏi lại người giao việc** nếu một giả định kinh tế (docs 03/06) cần thay: ghi vào "Quyết định đang chờ" trong `08_thu_tu_va_lich.md`.

## Định nghĩa "xong" theo kế hoạch gốc (DoD)

- Chạy lại từ lệnh trong mục "Cách chạy" ra đúng CSV (sai khác <0,5% do đa luồng).
- `pytest tests` xanh, thêm kiểm thử cho mã mới.
- Chỉ số so với mốc được báo cáo kèm CI bootstrap theo công ty (≥200 lần).
- Docs cập nhật; cổng G tương ứng đổi trạng thái có bằng chứng.
