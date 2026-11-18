# Agent 4 · Hỏi đáp Số liệu Tài chính & Sổ cái (Governed Analytics)

Phân hệ trợ lý số liệu cho lãnh đạo và kế toán trưởng: tiếp nhận câu hỏi tiếng Việt tự nhiên, ánh xạ vào danh mục chỉ tiêu tài chính được kiểm soát (`MetricCatalog`), sinh kế hoạch truy vấn an toàn trên kho sổ cái **DuckDB** chỉ đọc và trả lời kèm bảng số liệu + giải thích nguồn.

## Thành phần chính

- **`agent4/api.py` & `agent4/pipeline.py`**: Dịch vụ FastAPI (`create_demo_app` / `create_app`) thực thi luồng Governed Query Pipeline (chọn chỉ tiêu → kiểm tra phân quyền → biên dịch SQL → đối chứng kết quả).
- **`agent4/metric_selection/`**: Bộ chọn chỉ tiêu kết hợp tìm kiếm từ vựng/ngữ nghĩa và mô hình ngôn ngữ cục bộ qua Ollama (`config/eval_governed_lexical.yaml`).
- **`agent4/core/` & `agent4/planning/`**: Danh mục chỉ tiêu chuẩn hóa (khung quản trị `mgmt` và khung thuế `tax`), kiểm soát quyền truy cập và xử lý làm rõ câu hỏi mơ hồ.
- **`agent4/datagen/`**: Bộ sinh kho dữ liệu tham chiếu cho kiểm thử độc lập (`cfo_warehouse.duckdb`).
- **`../agent4_chat/`**: Giao diện trò chuyện nhúng trên Portal (`http://127.0.0.1:8800/#agent4`).

## Chạy & Kiểm thử

Khi chạy `.\run_web.ps1` từ thư mục gốc, Portal tự động khởi chạy Agent 4 ở cổng `8040` và trỏ `AGENT4_DB_PATH` tới kho dữ liệu Minh Phát (`MPX10`).

Chạy bộ kiểm thử tự động của Agent 4:

```powershell
Set-Location agent4
.\.venv\Scripts\python.exe -m pytest tests/contracts -q
```
