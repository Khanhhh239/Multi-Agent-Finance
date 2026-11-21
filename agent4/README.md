# Agent 4 · Hỏi đáp Số liệu Tài chính & Sổ cái (Governed Analytics)

Phân hệ trợ lý số liệu cho lãnh đạo và kế toán trưởng: tiếp nhận câu hỏi tiếng Việt tự nhiên, ánh xạ vào danh mục chỉ tiêu tài chính được kiểm soát (`MetricCatalog`), sinh kế hoạch truy vấn an toàn trên kho sổ cái **DuckDB** chỉ đọc và trả lời kèm bảng số liệu + giải thích nguồn.

## Thành phần chính

- **`agent4/api.py` & `agent4/pipeline.py`**: Dịch vụ FastAPI (`create_demo_app` / `create_app`) thực thi luồng Governed Query Pipeline (chọn chỉ tiêu → kiểm tra phân quyền → biên dịch SQL → đối chứng kết quả).
- **`agent4/metric_selection/`**: Bộ chọn chỉ tiêu kết hợp tìm kiếm từ vựng/ngữ nghĩa và mô hình OpenAI-compatible qua API key (`config/selection.yaml`).
- **`agent4/core/` & `agent4/planning/`**: Danh mục chỉ tiêu chuẩn hóa (khung quản trị `mgmt` và khung thuế `tax`), kiểm soát quyền truy cập và xử lý làm rõ câu hỏi mơ hồ.
- **`agent4/datagen/`**: Bộ sinh kho dữ liệu tham chiếu cho kiểm thử độc lập (`cfo_warehouse.duckdb`).
- **`../agent4_chat/`**: Giao diện trò chuyện nhúng trên Portal (`http://127.0.0.1:8800/#agent4`).

## Chạy & cấu hình

Khi chạy `.\run_web.ps1` từ thư mục gốc, Portal tự động khởi chạy Agent 4 ở cổng `8040` và trỏ `AGENT4_DB_PATH` tới kho dữ liệu Minh Phát (`MPX10`).

Web Agent 4 yêu cầu đồng thời `AGENT4_LLM_API_KEY` và
`AGENT4_EMBED_API_KEY`, đặt trong tệp `.env` duy nhất ở thư mục gốc dự án (mẫu: `../.env.example`). Cả giao diện governed trực tiếp lẫn Portal đều dùng
`config/selection.yaml`; không có fallback sang mô hình cục bộ.

| Tệp | Dùng cho |
|---|---|
| `requirements-cloud.txt` | Gói cài vào image Docker (Azure VM và Render) |
| `requirements.txt`, `pyproject.toml` | Cài môi trường cục bộ (`setup_all.ps1`, `setup_env.sh`) |
| `config/selection.yaml` | Chọn chỉ tiêu khi chạy trong Portal (Azure VM, máy cục bộ) |
| `config/selection_cloud.yaml` | Chọn chỉ tiêu cho dịch vụ cloud độc lập (`render.yaml`, `cloud/Dockerfile`) |
| `config/metric_relationships.yaml`, `data/example_bank.jsonl` | Dữ liệu cấu hình mà hai tệp `selection*.yaml` trỏ tới |
| `scripts/build_vector_index.py` | Dựng sẵn chỉ mục embedding (`.cache/`) |
| `scripts/migrate_neon.py` | Áp dụng `database/migrations` lên Neon cho bản cloud |

## Triển khai

Nhánh `deploy` chỉ giữ phần chạy thật của Agent 4; bộ kiểm thử, công cụ đánh giá và tài liệu nội bộ nằm ở nhánh `main`.
Xem [deploy/azure-vm/README.md](../deploy/azure-vm/README.md).
