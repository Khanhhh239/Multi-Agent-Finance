# 05 · Kế hoạch giao việc cho Coding Agent tiếp theo

Bạn (coding agent) nhận **Agent 1 — Trợ lý dòng tiền** ở trạng thái: dữ liệu + T0–T9 đã có mã và đã đo lần đầu (T1, T2, T3, T4, T6, T7, T8, T9, thích nghi miền); **T10 demo còn lỗi**, chưa có sản phẩm (API, dashboard, giám sát). Mục tiêu: hoàn thành thành **sản phẩm chạy được, đo được, đáng tin**.

> **Lưu ý trạng thái mã:** sau lần chạy đầu (15/10 sáng–trưa), một phiên khác đã bắt đầu làm WP-0/WP-1/WP-6 ngay trong cùng thư mục (chiều 15/10: thêm `t10.py`, `t7_portfolio.py`, `t8_promise.py`, `reconciliation_pipeline.py`, `tune_t1.py`, `validate_worlds.py`, sửa `features.py`/`t1.py`/`run_t1.py`/`run_t6.py`/`make_report.py`). Các CSV kết quả cũ (A, B, E/F, T6) đo bằng giao thức trước khi sửa; `make_report.py` đánh dấu "CSV cũ". Trước khi làm tiếp: `git diff`/so sánh với bản `v1`, chạy lại `pytest`, và chạy lại A/B/E/T6 để có bảng theo giao thức mới.

**Đọc theo thứ tự:** `00_INDEX.md` → `01_Business_Analyst/02_problem_statement.md` → `02_Data/01, 04` → `03_Evaluation/03, 04` → `04_AI_Methods/01, 02` → tài liệu này.

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

## Nguyên tắc làm việc (bắt buộc)

1. **Không đổi kết luận bằng cách đổi cách đo.** Sửa đo → chạy lại mọi mốc. Mốc đơn giản luôn chạy cùng mô hình mới.
2. **Mỗi gói việc kết thúc bằng 3 thứ:** (a) mã + kiểm thử, (b) CSV kết quả trong `outputs/`, (c) cập nhật `docs/03_Evaluation/04_ket_qua_hien_co.md` (số lấy từ CSV, không gõ tay).
3. **Kết quả xấu ghi lại.** Nếu giả thuyết sai, ghi "bị bác bỏ" kèm số và nguyên nhân giả định.
4. **Chống rò rỉ là việc số 1.** Mọi đặc trưng tính *as-of T*; mọi tập kiểm tra tách thời gian; hiệu chỉnh cách test ≥120 ngày; `tgt` niêm phong.
5. **Giới hạn luồng** (`AGENT1_THREADS`) — máy dùng chung, quá tải luồng làm chậm 10–50×.
6. **Giữ tiếng Việt cho tài liệu, tiếng Anh cho định danh code.** Comment/docstring tiếng Việt như mã hiện tại.
7. **Không tự sinh số bằng LLM** trong sản phẩm; bất kỳ văn bản LLM nào phải qua cổng đối chiếu số.
8. **Không commit dữ liệu thô** (`data/raw`, `data/interim`, `data/processed`, `data/synthetic/*/*.parquet`) — đã nằm trong `.gitignore`; chỉ commit mã, cấu hình, CSV kết quả nhỏ và docs.
9. **Hỏi lại người giao việc** nếu một giả định kinh tế (docs 03/06) cần thay: ghi vào "Quyết định đang chờ" trong `08_thu_tu_va_lich.md`.

## Định nghĩa "xong" cho từng gói việc (DoD)

- Chạy lại từ lệnh trong mục "Cách chạy" ra đúng CSV (sai khác <0,5% do đa luồng).
- `pytest tests` xanh, thêm kiểm thử cho mã mới.
- Chỉ số so với mốc được báo cáo kèm CI bootstrap theo công ty (≥200 lần).
- Docs cập nhật; cổng G tương ứng đổi trạng thái có bằng chứng.
