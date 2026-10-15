# Pha C. Sản phẩm hóa

Mục tiêu: một đường ống chạy hằng tuần cho một công ty thật ở chế độ chỉ xem, với đầu vào chuẩn, đầu ra có lý do tiếng Việt và hàng đợi rà soát. Phụ thuộc: A6 xong (có mô hình v2) và quyết định cấu hình. Pha C làm song song với B; nhận kết quả B khi có.

| # | Việc | Công | Phụ thuộc |
|---|---|---:|---|
| C1 | Đường ống v4 theo cấu hình | 2 ngày | A5, A6 |
| C2 | Lý do tiếng Việt cho 15 dấu hiệu đỏ và kiểm tra trung thực (H14) | 2 ngày | C1 |
| C3 | Lược đồ chuẩn và bộ kiểm tra đầu vào | 2 ngày | |
| C4 | Bộ nhận dữ liệu (adapter) mẫu | 3 ngày | C3 |
| C5 | Dịch vụ cục bộ: nhập, chấm điểm, hàng đợi, phản hồi | 3 ngày | C1, C3 |
| C6 | Nối giao diện rà soát và nhật ký phản hồi | 2 ngày | C5 |
| C7 | Hiệu năng và quy mô | 2 ngày | C1 |
| C8 | Quản lý phiên bản, thẻ mô hình, giám sát | 1 ngày | C1 |

---

## C1. Đường ống v4 theo cấu hình

**Hiện trạng:** `pipeline.py` chạy cho v3: `Agent2Detector` chỉ có CES và L3 (hồ sơ `precision`, `wide`) và Novelty (`cold`); chưa gọi `attach_unsupervised`, L4, Collective, chưa đọc tệp đóng băng.
**Các bước:**
1. Thêm tệp cấu hình `configs/agent2_default.json` (tạo từ `v4_frozen.json`): tên cấu hình chọn, hồ sơ, ngân sách, số khe, đường mô hình, phiên bản mã.
2. Sửa `pipeline.py`: `Agent2Detector.from_config(cfg)`; nạp `pretrained_v2`; nếu cấu hình dùng L4 thì gọi `hybrid.attach_unsupervised(df, cache)` (khớp trên giai đoạn huấn luyện của **chính công ty**), nếu dùng Collective thì `set_history([train, valid])`.
3. Thêm chế độ `--week YYYY-Www`: chỉ chấm các dòng của một tuần, dùng quá khứ làm lịch sử; đây là chế độ vận hành thật.
4. Bảo đảm `explanation_vi` và `rule_ids` được tạo cho cả cảnh báo từ L4.
5. Viết `tests_agent2/test_pipeline_v4.py`: chạy trên `v4s_smoke` (hoặc thế giới nhỏ do `generate_v4` sinh trong `tmp_path`, 30.000 dòng); kiểm: không quá B cảnh báo mỗi công ty mỗi tuần; mọi cảnh báo thuộc về tuần được chọn; không cảnh báo nào dựa trên thông tin sau tuần đó (dịch tập kiểm thử một ngày và so kết quả).
**Xong khi:** `python -m agent2.pipeline --data ... --week ... --config configs/agent2_default.json` chạy và kiểm thử qua.

## C2. Lý do tiếng Việt và kiểm tra trung thực (H14)

1. Thêm 15 mẫu câu vào `alerting.ENTITY_REASONS` hoặc bảng mới `V4_REASONS`. Mỗi mẫu có chỗ trống cho số liệu thật lấy từ dòng (ví dụ số ngày trễ, tên cột đối chiếu). Gợi ý:
   - `receipt_payer_mismatch`: "Phiếu thu áp dụng cho khách {khach} nhưng tiền đến từ tài khoản đã đăng ký của khách khác."
   - `payroll_after_leave`: "Lương đăng sau ngày ghi nhận nghỉ việc ({ngay}) của nhân viên."
   - `refund_to_foreign_account`: "Hoàn tiền {so_tien} sang tài khoản không phải của khách."
   - `writeoff_overdue_days`: "Xóa nợ khi hóa đơn mở lâu nhất của khách đã quá hạn {n} ngày."
   - `payee_not_on_master`: "Thanh toán cho tài khoản không có trong danh mục nhà cung cấp và không có thay đổi tài khoản đã ghi."
2. Module `agent2/explain_check.py`: hàm `check(reason_text, evidence_row)` trích mọi số trong câu (phần trăm, ngày, tiền, số lần) và kiểm chúng bằng giá trị trong `evidence_row` (làm tròn theo định dạng). Trả `ok` và danh sách số không có chứng cứ.
3. Kiểm thử: câu đúng qua; sửa một số thì thất bại; mọi mẫu câu sinh ra từ dữ liệu `v4s_smoke` đều qua (hồi quy).
4. Nếu dùng mô hình ngôn ngữ để làm mượt: chỉ làm mượt câu mẫu; chạy `check` sau làm mượt; nếu thất bại dùng câu mẫu.
**Xong khi:** 100% lý do của cảnh báo trên 3 thế giới phát triển qua kiểm tra.

## C3. Lược đồ chuẩn và kiểm tra đầu vào

1. Viết `docs/05_ke_hoach_giao_viec/data_contract.md` hoặc `agent2/schema.py`: bảng cột bắt buộc và tùy chọn (suy ra từ `10_tu_dien_du_lieu.md`): tối thiểu `transactions` (`company_id`, `transaction_id`, `posted_at`, `created_at`, `approved_at`, `txn_type`, `amount_vnd`, `vendor_id`/`customer_id`/`employee_id`, `creator_id`, `approver_id`, `recipient_account`, `invoice_*`, `support_doc_count`) và danh mục chủ (`employees` với `hired_at`, `terminated_at`; `vendors` với `bank_account`, `registered_at`, `onboarded_at`; `customers`).
2. `agent2/schema.py`: hàm `validate_input(tables) -> report` kiểm kiểu, khóa ngoại, thứ tự thời gian (tạo ≤ duyệt ≤ đăng), thiếu cột; trả mức: lỗi (dừng), cảnh báo (chạy với chế độ giảm).
3. Chế độ giảm: khi thiếu cột nào đó, bộ phát hiện phụ thuộc bị tắt và ghi vào báo cáo.
**Xong khi:** kiểm thử với thế giới v4 (qua), với bản cố ý làm hỏng (cột thiếu, thời gian sai, khóa ngoại sai) cho báo cáo đúng.

## C4. Bộ nhận dữ liệu mẫu

**Chưa biết** định dạng xuất của phần mềm kế toán phổ biến (giả định A9). Việc đầu tiên là **hỏi và xin tệp mẫu** từ 2 đến 3 doanh nghiệp hoặc hãng; không đoán.
1. Dựng khung `agent2/adapters/base.py` (giao diện `load(path) -> tables`), và `agent2/adapters/csv_generic.py` đọc CSV theo tệp ánh xạ cột (`mapping.yaml`: cột nguồn → cột chuẩn, quy tắc đổi kiểu, múi giờ).
2. `agent2/adapters/einvoice_xml.py` khung đọc hóa đơn điện tử XML (cần mẫu thật; ban đầu viết theo tài liệu công khai của cơ quan thuế, đánh dấu **chưa kiểm chứng**) trích dòng hàng, đơn giá, số lượng.
3. Một bộ chuyển đổi theo từng phần mềm khi đã có mẫu.
4. Kiểm thử với tệp mẫu tổng hợp mô phỏng (sinh từ thế giới v4 rồi đổi tên cột).
**Xong khi:** CSV chung chạy; XML khung đọc được mẫu; tài liệu ghi những gì cần từ khách.

## C5. Dịch vụ cục bộ

Phạm vi nhỏ, chạy cục bộ (SQLite), không đám mây ở giai đoạn này:
- Điểm vào: `POST /ingest` (tải tệp), `POST /score?week=...`, `GET /cases?status=new`, `POST /cases/{id}/decision`, `GET /report`.
- Lưu: bảng `ingest`, `scores`, `cases`, `decisions` (người, thời điểm, kết luận, lý do), `model_versions`.
- Cách ly công ty: mọi truy vấn có `company_id`; kiểm thử nhiều công ty không rò rỉ.
- Nhật ký chỉ ghi thêm cho quyết định (dùng lại cơ chế khóa tệp của `sme_fraud/feedback.py` hoặc bảng SQLite chỉ thêm).
Chọn FastAPI hoặc Flask; kiểm thử bằng client thử. **Không** mở cổng ra ngoài mặc định.

## C6. Nối giao diện rà soát

`review_ui/` của bạn bạn đọc `case_queue.csv`; `review_server.py`, `review_store.py` trong `sme_fraud/`. Cách làm: (1) đọc mã giao diện hiện có và `docs/06_ghi_chep_lam_viec/review_ui.md`; (2) để giao diện gọi dịch vụ C5 thay vì đọc tệp; (3) thêm trường: lý do tiếng Việt, mức ưu tiên, thời hạn, nút "đáng kiểm tra / hợp lệ / nghi vấn / xác nhận" ghi vào `decisions`; (4) vòng phản hồi nạp `decisions` để học lại trọng số (thiết kế ở `06_phan_hoi_va_hoc_dan.md`), với quy tắc hard trigger không bị hạ cấp.

## C7. Hiệu năng

1. Đo thời gian từng giai đoạn trên 200.000 dòng và trên 1.000.000 dòng (ghép 5 thế giới sau khi thêm tiền tố mã).
2. Tối ưu theo thứ tự đo được: `feats.py` và `feats_v4.py` (vòng lặp Python) chạy theo công ty song song bằng `joblib`; bộ nhớ float32; `memory_features` thay `groupby().rolling()` bằng `searchsorted` khi vượt 500.000 dòng.
3. Mục tiêu: 100.000 dòng của một công ty chấm một tuần dưới 5 phút trên máy 4 nhân.
**Xong khi:** bảng thời gian trong nhật ký; không đổi kết quả (hồi quy).

## C8. Phiên bản và giám sát
- Mỗi lần chạy ghi `run_manifest.json`: băm mã, băm mô hình, băm dữ liệu vào, cấu hình, ngày.
- Thẻ mô hình (`models/*.card.json`), bản ghi nhận cảnh báo kèm phiên bản.
- Số theo dõi hằng tuần: số cảnh báo, hạng điểm trung vị, PSI đặc trưng chính so với huấn luyện, tỷ lệ "đáng kiểm tra" từ phản hồi.
