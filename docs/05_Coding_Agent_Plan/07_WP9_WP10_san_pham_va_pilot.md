# WP-9 Sản phẩm · WP-10 Chuẩn bị pilot (T13)

Làm sau khi G1/G2/G5/G9/G11/G12 ổn định (xem 08). Mục tiêu: một sản phẩm tối thiểu dùng được với DN thật (chạy song song, không can thiệp).

---

## WP-9.1 Kiến trúc dịch vụ

```
agent1_service/
  api/            FastAPI: /ingest, /forecast, /alerts, /whatif, /promises, /health
  jobs/           nightly.py (snapshot→T1/T2/T3→T6→T10→alerts), weekly.py (ACI, PSI, retrain check)
  store/          SQLite (pilot) → PostgreSQL; bảng chuẩn (invoices, payments, bank_txns, promises, forecasts, model_registry)
  ui/             Streamlit (pilot) hoặc web nhỏ
  text/           vi_templates.py, verbalize.py (cổng số)
```
- **Tách** mã khoa học (`agent1/`) khỏi dịch vụ; dịch vụ chỉ gọi hàm công khai (`predict_hazard`, `simulate`, …). Tạo `agent1/api_surface.py` liệt kê hàm công khai ổn định.
- **Tiêu chí**: một lệnh `docker compose up` chạy toàn hệ với dữ liệu `tgt`.

## WP-9.2 Nhập dữ liệu thật (T0) — P0 cho pilot
1. `ingest/einvoice_xml.py`: đọc thư mục XML (QĐ 1450/1510): hỗ trợ nhiều phiên bản (`PBan`), hoá đơn thay thế/điều chỉnh; xuất bảng chuẩn; cổng chất lượng (`schema.quality_gate`).
2. `ingest/bank_statement.py`: CSV/Excel của Vietcombank/BIDV/Techcombank/MB/ACB… (cột khác nhau) → `bank_txns`; bảng ánh xạ cột có thể cấu hình; lọc nội dung (tên, memo), chuẩn hoá ngày giờ.
3. `ingest/erp_ledger.py`: xuất từ MISA/FAST (Excel) → công nợ; ngày ghi sổ.
4. **Ẩn danh** (NĐ 13/2023): băm MST/tên bằng HMAC khoá của DN khi đưa vào môi trường phát triển; không ghi log thô.
5. **Kiểm thử bằng bộ giả lập**: sinh sao kê/Excel từ `tgt` theo định dạng từng ngân hàng (mẫu cột) và đọc lại — kiểm khớp 100%.

## WP-9.3 Dashboard
- Màn hình chính: dải màu P10/P50/P90 13 tuần + đường ngưỡng an toàn; thẻ "tuần nguy hiểm"; nhãn nguồn số liệu (mô hình / cam kết / kịch bản) và nhãn chế độ (bình thường / thận trọng).
- Màn "Đòi ai trước": top-10 theo `ΔP` + lý do; nút ghi lời hứa (một ô: ngày + số tiền).
- Màn "Thử kịch bản": kéo khoản thu; thêm/hoãn khoản chi; "khách X trễ N tuần".
- Màn "Dữ liệu": tỷ lệ khớp sổ–sao kê, lỗi cổng chất lượng, hàng chờ T9.
- Màn "Hiệu quả": cov80 trượt, PSI, so sánh dự báo – thực tế.
- **UAT**: kịch bản U1–U6 (03_Evaluation/07).

## WP-9.4 Cảnh báo
- Quy tắc: `P_4w ≥ τ_4`, `P_13w ≥ τ_13` (τ theo chi phí, WP-6.7), thay đổi chế độ (T7), thất hứa lớn. Hạn chế: ≤2 cảnh báo/tuần/DN; gộp theo nguyên nhân.
- Kênh: email/Zalo OA (cần tài khoản OA — hỏi người giao việc; mặc định mô phỏng gửi vào file).
- Mọi cảnh báo qua `verbalize.check_numbers`.

## WP-9.5 Diễn giải bằng LLM
- Chỉ sau cổng số. Prompt: bảng JSON + hướng dẫn "không thêm số". Dùng mô hình cấu hình được (Claude/khác); chi phí ≈ 1.500 token/cảnh báo.
- **Đánh giá**: 200 cảnh báo mẫu, tỷ lệ đạt cổng số = 100%; đánh giá tính tự nhiên bởi 3 người.

## WP-9.6 MLOps
- Model registry (MLflow cục bộ hoặc thư mục phiên bản): tham số, dữ liệu as-of (hash), chỉ số, đường dẫn mô hình.
- PSI hằng tuần, cov80 trượt, cảnh báo drift; lệnh retrain `python -m agent1.jobs.retrain --firm F --reason psi`.
- Hồi quy hiệu năng: batch ≤5 phút/DN (TC-11).

## WP-9.7 Bảo mật và pháp lý
- Mã hoá lưu trữ; kiểm quyền; nhật ký truy cập; xoá theo yêu cầu; hợp đồng xử lý dữ liệu; không gửi dữ liệu thô tới dịch vụ ngoài (kể cả LLM).
- Tài liệu: `docs/security_privacy.md` (mô hình đe doạ, dòng dữ liệu, xử lý yêu cầu chủ thể dữ liệu).

---

## WP-10 · Chuẩn bị pilot (T13)

### WP-10.1 Tuyển DN đối tác (việc của con người; agent chuẩn bị tài liệu)
- Tờ giới thiệu 1 trang, mẫu thỏa thuận đồng ý dữ liệu (NĐ 13/2023), checklist dữ liệu cần (HĐĐT XML 24 tháng, sao kê 24 tháng, sổ công nợ, lịch lương).
- Tiêu chí chọn: ≥10 lao động, có bán chịu B2B, dùng HĐĐT, ≥12 tháng lịch sử.

### WP-10.2 Giao thức đo
- Theo 03_Evaluation/02 §2.5 và 07 §7.4: giai đoạn 0 (song song 8–12 tuần), giai đoạn 1 (hiển thị 12–24 tuần), DiD.
- **Tạo** `pilot/analysis.py`: tính K1–K9, G tầng thật, DiD, báo cáo trường hợp sai tự động.
- **Tạo** `pilot/baseline_snapshot.md`: mẫu thu thập hiện trạng (cách DN dự báo hiện nay, đệm tiền mặt, sự kiện thiếu hụt 24 tháng trước, chi phí tài chính).

### WP-10.3 Đối chiếu giả định kinh tế
- Bảng 03_Evaluation/06 §6.8: mỗi giả định → chỉ số đo → ngưỡng chấp nhận; cập nhật `scripts/roi_calc.py` bằng số thật, báo cáo ROI thật.

### WP-10.4 Rủi ro pilot và kế hoạch dự phòng
| Rủi ro | Dấu hiệu | Dự phòng |
|---|---|---|
| Dữ liệu bẩn/thiếu | tỷ lệ khớp <40% | chạy chế độ "chỉ sổ" với nhãn khoảng (WP-1.4); phiên làm việc làm sạch với kế toán |
| Không ai dùng | WAU <30% | đơn giản hoá UI, gửi bản tin Zalo hằng tuần |
| Cảnh báo giả nhiều | >30% bị đánh dấu | tăng τ, giảm tần suất |
| Mô hình lệch | cov80 ngoài [70,90] 4 tuần | chế độ thận trọng + retrain |
| Sự cố bảo mật | | quy trình sự cố trong `docs/security_privacy.md` |

**DoD WP-9/10**: hệ thống chạy trên dữ liệu `tgt` giả lập định dạng thật; UAT U1–U6 đạt với ≥3 người; bộ tài liệu pilot đủ; kiểm thử bảo mật cơ bản; phân tích pilot sẵn sàng chạy ngay khi có dữ liệu.
