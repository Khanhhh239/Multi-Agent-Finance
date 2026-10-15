# Nhật ký quyết định (DECISIONS)

> Mỗi dòng: ngày · bối cảnh · quyết định · lý do · hệ quả. Người tiếp nhận ghi tiếp bên dưới.

| Ngày | Bối cảnh | Quyết định | Lý do | Hệ quả |
|---|---|---|---|---|
| 2026-10-14 | Chọn kiến trúc | Lõi chỉ số tất định + LLM chỉ chọn công cụ/diễn giải | NL2SQL tự do kém trên schema thật (Spider 2.0, trích trong tài liệu nhóm); số tài chính không chấp nhận sai | LLM không có công cụ ghi; verifier bắt buộc |
| 2026-10-14 | Doanh nghiệp mẫu | "Minh Phát": phân phối CNTT/VP + dịch vụ, TT133, 3 chi nhánh | Đủ tồn kho/công nợ/biên mỏng; nỗi đau DNVVN thương mại | Dữ liệu tổng hợp 140k dòng, 21,5 tháng |
| 2026-10-14 | Mốc dữ liệu | `AS_OF=2026-10-14`, khóa sổ đến 2026-08 | Buộc agent xử lý kỳ chưa khóa sổ | Mọi câu hỏi "tháng này" là kỳ dở dang |
| 2026-10-14 | Kiểm soát tín dụng mô phỏng | Chặn bán khi dư nợ > 120% hạn mức; Hoàng Long được nới 200% | Kịch bản "sale override" — nợ phình nhưng có điểm chặn | Dư nợ Hoàng Long đạt ~8 tỷ |
| 2026-10-14 | Vay | Hạn mức xoay vòng 20 tỷ rút khi tiền gửi < 2,5 tỷ | Thanh khoản căng là hard case | Dư nợ vay 25 tỷ cuối kỳ (căng) — **chủ ý** |
| 2026-10-14 | Test v0 gốc lỗi | Sửa `generate_data.py` (2 lỗi) và port test sang `agent4/tests/test_legacy_contract.py`, đóng băng "hôm nay" = 15/05/2026, sửa kỳ vọng doanh thu 129,6 tr, giá vốn 77,76 tr, chi phí HĐ 30 tr | Test gốc tự mâu thuẫn và chưa từng chạy được (K1, K2) | Cần người xem lại; ghi ở `01_hien_trang…` |
| 2026-10-14 | TT133 không có TK 521 | Giảm trừ doanh thu = Nợ 511; `revenue_deductions` đọc cả 511 (Nợ) và 521 | Đúng TT133; vẫn hỗ trợ TT200/TT99 | Chỉ số đa chế độ |
| 2026-10-14 | Model | Dev trên `qwen3:4b-instruct-2507-q4_K_M` (6 GB) & `qwen3:8b` | Hai điểm cân bằng kích thước/chất lượng ≤ 10B | Chưa có số đo — H4 |
| 2026-10-14 | Thiếu kỳ trong câu hỏi | **Đề xuất (chưa chốt):** chỉ số dòng chảy thiếu kỳ ⇒ mặc định `this_month` và nêu rõ; chỉ số số dư ⇒ `today` | Giảm hỏi lại vô ích | Cần xác nhận với người dùng; thử ở E3 |
| _(tiếp theo)_ | | | | |
