# Khung chat Agent 4

Ba tệp tĩnh: `index.html`, `chat.css` và `chat.js`, không cần build. Portal phục vụ tại `/agent4/` và hiện trong khung Agent 4.

- Trang chỉ gọi portal: `POST /api/agent4/query` với `{"question": "..."}` và `GET /api/agent4/metrics`. Portal tự thêm khóa của Agent 4, nên trang không giữ khóa nào.
- Câu trả lời là `QueryResponse` của `agent4/agent4/text2sql/models.py`. Các trường đang dùng: `status`, `answer`, `data` (bảng), `interpretation`, `provenance`, `warnings`.
- Màu và chữ dùng cùng biến với portal (`--ink`, `--accent`, font Be Vietnam Pro) nên nằm liền với khung chung. Muốn đổi thì sửa `chat.css`.
- Câu gợi ý nằm ở đầu `chat.js` (`SUGGESTIONS`). Năm câu hiện có đều được Agent 4 trả lời trên kho demo.

Chạy riêng ngoài portal không được, vì trang cần portal chuyển câu hỏi tới Agent 4 kèm khóa.
