# Agent 3 (`agent3_tax_compliance`) — Ứng dụng Kiểm tra Thuế GTGT

Đọc hóa đơn điện tử XML/ZIP, đối chiếu sao kê ngân hàng và bảng kê cổng thuế, cảnh báo các hóa đơn có nguy cơ bị loại khấu trừ GTGT kèm trích dẫn điều khoản luật. Mọi quyết định tính tiền dựa trên quy tắc xác định; các chức năng AI dùng API tương thích OpenAI và bắt buộc có API key.

Tạo `agent3/.env` từ [`.env.example`](../.env.example), điền `AGENT3_LLM_API_KEY` và `AGENT3_EMBED_API_KEY` (có thể dùng `AGENT3_API_KEY` chung). Web riêng sẽ từ chối khởi động nếu thiếu key.

## Cấu trúc chính

| Thư mục | Nội dung |
|---|---|
| `src/assistant/` | Ứng dụng web FastAPI (`web.py`), cầu đồng bộ Portal (`platform_context.py`), phân tích đối chiếu và hỏi đáp (`chat/`) |
| `src/lawbase/` | Kho văn bản pháp luật thuế: thu thập, tách điều khoản, tìm kiếm lai (BM25 + Dense Vector) và xếp hạng lại qua API |
| `rules/`, `configs/` | Bộ quy tắc rủi ro thuế và danh mục quy định chi tiêu, ngày nghỉ |
| `webui/` | Mã nguồn giao diện (đã biên dịch sẵn vào `src/assistant/static/`) |
| `migrations/` | Lược đồ SQLite |

## Chạy

Khi dùng chung nền tảng, chạy `.\run_web.ps1` ở thư mục gốc dự án. Chạy riêng Agent 3: `chay_agent3.bat` (mở `http://127.0.0.1:8640`).
