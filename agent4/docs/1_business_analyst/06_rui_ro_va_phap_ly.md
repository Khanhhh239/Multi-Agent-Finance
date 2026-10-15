# 06 · Rủi ro, pháp lý và đạo đức

> Các nhận định pháp lý dưới đây tổng hợp từ bài phân tích/báo chí tìm được ngày 14/10/2026 — **không thay thế tư vấn pháp lý**. Mục cần đối chiếu văn bản gốc được đánh dấu 🔎.

## 1. Ma trận rủi ro sản phẩm
| ID | Rủi ro | Xác suất | Tác động | Giảm thiểu (thiết kế) | Chỉ số theo dõi |
|---|---|---|---|---|---|
| R1 | Agent đưa ra số sai (chọn nhầm chỉ số, nhầm kỳ) | TB | Rất cao | Router hẹp công cụ + resolver tất định + verifier + hỏi lại | Exact‑match số trên bộ test; sai‑số‑không‑phát‑hiện = 0 |
| R2 | Ảo giác diễn giải ("vì sao" không có trong dữ liệu) | TB | Cao | Prompt buộc trích số từ công cụ; kiểm tra mệnh đề nhân quả bằng verifier mức "chỉ nêu yếu tố có số" | Tỷ lệ câu trả lời có mệnh đề không nguồn |
| R3 | Trộn khung quản trị/thuế | Thấp–TB | Cao | `ViewNotAllowedError` ở engine + luật chọn view trong router | Đúng‑view ≥ 98% |
| R4 | Tiêm nhiễm lệnh qua diễn giải chứng từ/tên đối tác | TB | Cao | Dữ liệu tự do đi qua *khối trích dẫn không thực thi*; công cụ chỉ trả cấu trúc; guardrail phát hiện mẫu lệnh | Red‑team 100% chặn; ca A8 trong dữ liệu |
| R5 | Rò rỉ dữ liệu tài chính | Thấp | Rất cao | Model tại chỗ, DB chỉ‑đọc, phân quyền hàng, log truy cập | Kiểm thử xuyên quyền |
| R6 | Agent thực thi hành động ngoài ý muốn | Thấp | Rất cao | Không có công cụ ghi; `propose_action` + phê duyệt người | 0 hành động không qua duyệt |
| R7 | Model nhỏ không gọi công cụ ổn định (bỏ qua gọi, sai tham số) | Cao | Trung bình | Thu hẹp công cụ (≤ 8), JSON schema ràng buộc, thử lại có chẩn đoán, fallback model lớn hơn *tùy chọn* | Tool‑selection acc, arg‑exact |
| R8 | Số liệu "tạm tính" bị hiểu là chốt | Cao | Trung bình | Nhãn bắt buộc + ghi chú kỳ dở dang | Tỷ lệ câu trả lời thiếu nhãn = 0 |
| R9 | Công thức chỉ số bị kế toán không đồng ý | TB | Cao | Rà soát công thức với kế toán trưởng; mỗi chỉ số có test và tài liệu | % chỉ số được duyệt |
| R10 | Dữ liệu thật lệch giả định mô phỏng (hạch toán lô, TK chi tiết khác) | Cao | Trung bình | Tầng ánh xạ tài khoản; kiểm thử trên dữ liệu thật ẩn danh trước khi go‑live | Số chỉ số cần chỉnh sau pilot |
| R11 | Chi phí không đủ cho 1 DN đơn lẻ | Cao | Trung bình | Chọn mô hình A/B (đa khách hàng) | Hoàn vốn (`3_evaluation/03`) |

## 2. Bối cảnh pháp lý cần lưu ý
| Chủ đề | Nội dung hiện biết | Ảnh hưởng thiết kế | Xác minh |
|---|---|---|---|
| **Chế độ kế toán** | TT133/2016 vẫn có thể áp dụng cho DNNVV; TT99/2025 thay TT200 từ 01/01/2026 | Lớp ánh xạ tài khoản, test với cả hai chế độ | 🔎 Điều 31 TT99/2025 |
| **Luật Trí tuệ nhân tạo 134/2025/QH15** | Hiệu lực 01/03/2026; nguyên tắc con người giám sát; hệ thống rủi ro cao theo danh mục sẽ ban hành; một chuyên gia cho rằng hệ thống tài chính đã vận hành có 18 tháng chuyển tiếp | Human‑in‑the‑loop, nhãn AI, nhật ký, đánh giá rủi ro nội bộ | 🔎 Danh mục AI rủi ro cao & nghĩa vụ minh bạch |
| **Dữ liệu cá nhân** | Dữ liệu lương, tên nhân viên, mã số thuế là dữ liệu cá nhân (khung NĐ 13/2023/NĐ‑CP và văn bản mới về bảo vệ dữ liệu cá nhân) | Phân quyền, ẩn danh dữ liệu mẫu, không đưa lương cá nhân vào câu trả lời cho người không có quyền | 🔎 Văn bản hiện hành & hiệu lực |
| **Thuế** | GTGT 8% đến 31/12/2026 (NĐ 174/2025, phạm vi có chỗ nguồn bất nhất); CIT 20% phổ thông | Chỉ số thuế là *ước tính*, ghi rõ giả định; không thay tư vấn thuế (Agent 3) | 🔎 Phụ lục NĐ 174/2025 |
| **Hóa đơn/chứng từ điện tử, lưu trữ** | Chứng từ phải lưu đúng thời hạn | Agent chỉ đọc; không thay đổi chứng từ | — |

## 3. Đạo đức & minh bạch
- **Không thay con người ra quyết định**: mọi đề xuất kèm lý do bằng số và nguồn; nút "Xem cách tính".
- **Không che giấu bất định**: kỳ chưa khóa sổ luôn nói rõ; số ước tính (thuế, DSO bình quân) ghi giả định.
- **Công bằng giữa người dùng**: phân quyền không phụ thuộc cách đặt câu hỏi.
- **Báo cáo giới hạn**: khi dữ liệu thiếu (ví dụ chưa có bảng lương tháng hiện tại) nêu rõ, không điền bằng ước đoán.

## 4. Kế hoạch ứng phó sự cố
| Sự cố | Phát hiện | Ứng phó |
|---|---|---|
| Phát hiện số sai đã trả lời | Người dùng báo / kiểm toán mẫu | Khóa chỉ số đó (feature flag) → thêm ca vào bộ regression → sửa → công bố |
| Tiêm nhiễm thành công | Red‑team / log bất thường | Cập nhật bộ lọc; thêm ca vào `E8` |
| Model không phản hồi | Health check | Chế độ lõi‑tất định (form chọn chỉ số + kỳ) |
