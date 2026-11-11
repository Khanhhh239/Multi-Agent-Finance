# Agent 4 — Data Foundation

Repository này chứa nền dữ liệu tổng hợp và Metric Selection Engine của Agent 4.

Checkout này có code production đến bước chọn và xác thực metric (M1). Các
contract từ lập kế hoạch đến trả lời được kiểm tra qua test harness trên dữ
liệu mô phỏng.

## Thành phần được giữ lại

- `data/`: warehouse DuckDB và ground truth đã sinh (được giữ local, không commit).
- `agent4/datagen/`: bộ mô phỏng doanh nghiệp và sinh warehouse.
- `agent4/config.py`: cấu hình ngày chốt dữ liệu và đường dẫn warehouse.
- `docs/2_data/`: tài liệu chiến lược, lược đồ và quy tắc dữ liệu.
- `reference_v0/`: bộ sinh dữ liệu và tài liệu tham chiếu phiên bản đầu.
- `tests/test_budget_seed.py`: kiểm tra tính tất định của dữ liệu ngân sách.
- `agent4/metric_selection/`: pipeline chọn metric từ câu hỏi tiếng Việt.
- `config/selection.yaml`: cấu hình retrieval, expansion, reranking, few-shot và LLM.
- `data/example_bank.jsonl`, `data/eval/`: ví dụ quyết định và bộ đánh giá tách biệt.

## Cài đặt

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e . --no-deps
```

## Kho dữ liệu Agent 4

`AppConfig` mặc định dùng kho mô phỏng Minh Phát MPX10 v3.0.0 tại
`data/enterprise-x10-v3/warehouse.duckdb`. Seed là `20261108`, ngày chốt dữ
liệu là `2026-10-14` và tháng khóa sổ cuối là `2026-08`. Có thể chọn kho
khác qua `AGENT4_DB` và tệp ground truth tương ứng qua `AGENT4_GROUND_TRUTH`.

### Nghiệm thu module 0 và 1

Từ thư mục `agent4`, chạy:

```bash
make test-mpx10 PYTHON=.venv/bin/python
```

Lệnh chạy contract tests của M0 và M1, bao gồm E0, rồi mở DuckDB ở chế độ
chỉ đọc để so 29 kết quả catalog M0, 70 ca SQL tham chiếu và 5 kịch bản
ground truth với bộ MPX10 v3. Lệnh chạy offline. Test M1 dùng cấu hình kiểm
thử và phản hồi mô hình giả lập. Các ca SQL dùng truy vấn tham chiếu có sẵn.
Kết quả cuối phải hiện `29 catalog results, 70 golden cases and 5 scenarios matched`.

Baseline catalog và golden rows của MPX10 nằm trong
`data/eval/mpx10-v3-reference.json`. Trình kiểm tra phát lại SQL cố định của
v1 cho các ca còn phù hợp với MPX10. Các câu gắn với sự kiện, mã đối tác,
giả định doanh thu bằng 0 hoặc danh sách chiều riêng của kho cũ được liệt
kê trong `scripts/check_mpx10.py`. Đây là bộ tham chiếu dữ liệu để nghiệm thu
offline. Việc đưa kết quả số vào benchmark v2 cần đối soát và phê duyệt theo
`docs/evaluation.md`.

### Tạo lại kho MPX10

Tệp DuckDB sinh cục bộ được Git bỏ qua. Dùng thư mục checkout riêng của
`platform-Khanh` tại commit `2991a5354391e7c5174479c8516fa202174d929e` và
Python có DuckDB 2.0.0 theo lockfile. [Mã nguồn pipeline MPX10](https://github.com/Khanhhh239/Multi-Agent-Finance/tree/2991a5354391e7c5174479c8516fa202174d929e/data_pipeline)

```bash
# Chạy từ agent4, PLATFORM_CHECKOUT trỏ đến thư mục gốc của checkout riêng.
dataset=data/enterprise-x10-v3
.venv/bin/python "$PLATFORM_CHECKOUT/data_pipeline/enterprise.py" --out "$dataset"
.venv/bin/python "$PLATFORM_CHECKOUT/data_pipeline/validate.py" "$dataset"
.venv/bin/python - "$dataset" <<'PY'
import json
import sys
from pathlib import Path

dataset = Path(sys.argv[1])
report = json.loads((dataset / "validation.json").read_text(encoding="utf-8"))
assert report["all_pass"]
(dataset / "warehouse_ground_truth.json").write_text(
    json.dumps(report["ground_truth"], ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY
```

Pipeline yêu cầu đường dẫn đích chưa có `warehouse.duckdb`. Để build lần
khác, dùng thư mục phiên bản mới và đặt hai biến môi trường tương ứng. Chỉ
dùng tùy chọn `--smoke` ở thư mục thử riêng vì nó sinh bộ dữ liệu nhỏ hơn với
cùng version.

### Fixture v2.1 cho benchmark cũ

Các test chứa giá trị tuyệt đối và kịch bản của v2.1 dùng riêng
`data/cfo_warehouse.duckdb` và `data/cfo_warehouse_ground_truth.json`. Nếu
checkout mới thiếu fixture, tạo bằng lệnh:

```bash
python -m agent4.datagen.build \
  --out data/cfo_warehouse.duckdb \
  --seed 20251
```

Ngày dữ liệu của fixture mặc định là `2026-10-14`; có thể thay đổi bằng biến môi trường
`AGENT4_AS_OF`. Tháng khóa sổ mặc định là `2026-08`; có thể thay đổi bằng
`AGENT4_LAST_CLOSED_MONTH`.

## Kiểm tra

```bash
pytest
```

Các gate chi tiết:

```bash
make help
make format-check
make lint
make typecheck
make test-core
make test-selection
make test-warehouse
make test-planning
make test-sql
make test-answer
make test-security
make test-benchmark
make test
make verify
```

Khi đang làm một Issue, có thể giới hạn static checks vào đúng phạm vi thay đổi:

```bash
make lint CHECK_PATHS='agent4/core tests/contracts/test_intake_auth_catalog.py'
make format-check CHECK_PATHS='agent4/core tests/contracts/test_intake_auth_catalog.py'
```

`make eval-validate` chỉ kiểm tra schema/dataset, không phải quality evaluation.
Để chạy evaluator thật, truyền production adapter hoặc predictions đã ghi cùng
metadata bắt buộc:

```bash
make eval \
  EVAL_MODE=selection \
  ADAPTER=my_project.eval_adapter:predict \
  MODEL_VERSION=provider:model:revision \
  PROMPT_VERSION=metric-selection-v1 \
  OUTPUT_DIR=reports/eval/selection-dev-v1
```

## Governed query API

Tạo FastAPI app bằng `agent4.api.create_app()`. Middleware xác thực của host
đặt claims đã xác minh vào `request.state.idp_claims` và policy phía server vào
`request.state.server_policy`. Truyền mapping tenant đến file DuckDB bằng
`warehouses`, hoặc cấu hình một tenant bằng `AGENT4_WAREHOUSE_TENANT_ID` và
`AGENT4_DB`. Endpoint `POST /v1/query` từ chối truy vấn khi thiếu quyền hoặc
warehouse của tenant.

Bật `options.include_evidence_preview` để trả bằng chứng theo từng ô kết quả.
Chọn `options.clarification_mode: "guided"` để nhận lựa chọn và `session_id`
khi câu hỏi còn thiếu thông tin. Gửi câu trả lời bổ sung ở trường `question`
kèm `session_id` đó. Với cấu hình một warehouse, server có thể cung cấp gợi ý
kỳ bằng `AGENT4_REPORTING_DATA_WATERMARK` và `AGENT4_REPORTING_LAST_CLOSED_MONTH`.

### Demo governed có giao diện web

```bash
make demo PYTHON=.venv/bin/python
```

Mở [giao diện demo](http://localhost:8000). Demo dùng `data/cfo_warehouse.duckdb`
và `config/selection.yaml` theo mặc định. Đặt `AGENT4_DB_PATH` cho warehouse tổng
hợp khác và `AGENT4_SELECTION_CONFIG` cho preset model khác. Với runtime Kaggle,
có thể dùng preset ở mục Metric Selection Engine và override endpoint/model
bằng các biến môi trường được liệt kê ở đó. `AGENT4_METRIC_SELECTION_CONFIG` là
tên thay thế khi chưa đặt `AGENT4_SELECTION_CONFIG`.

Persona CFO và HCM có thể chọn từ trình duyệt. HCM chỉ đọc các dòng HCM của
view quản trị. Demo mode cấp quyền CFO demo mặc định cho khách truy cập và
trả SQL có placeholder trong phần bằng chứng, vì vậy hãy dùng warehouse
dữ liệu tổng hợp khi chạy chế độ này.

## Safe Text-to-SQL demo (tham chiếu phiên bản trước)

Các lệnh demo và API dưới đây cần checkout có vertical slice Text-to-SQL.

Portal dùng API demo Text-to-SQL hiện có để phục vụ `agent4_chat/`. Core M0–M2.1 và các test contract chạy độc lập trong cùng package. API demo tiếp tục dùng bộ chọn và bộ xác thực plan của nền tảng.

Chạy API bằng token demo do người vận hành tự chọn:

```bash
export AGENT4_DEMO_TOKEN='local-secret'
python -m uvicorn agent4.text2sql.api:create_app --factory
```

```bash
curl -s http://127.0.0.1:8000/v1/query \
  -H "Authorization: Bearer $AGENT4_DEMO_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"api_version":"v1","question":"Doanh thu thuần quý 3 năm 2026 là bao nhiêu?","locale":"vi-VN","session_id":null,"options":{"include_table":true,"explain_metrics":true}}'
```

Mọi response demo đều có cảnh báo `DEMO DATA — NOT REAL FINANCIAL RESULTS`.
API demo mặc định dùng `data/cfo_warehouse.duckdb`. Đặt `AGENT4_DB` để
trỏ đến một kho demo khác, ví dụ `data/enterprise-x10-v3/warehouse.duckdb`.

## Tài liệu review tiếng Việt

- [Mục lục review](docs/README_REVIEW_VI.md)
- [Hướng dẫn sử dụng](docs/usage_guide_vi.md)
- [Hướng dẫn review code](docs/review_guide_vi.md)
- [Checklist review](docs/code_review_checklist_vi.md)
- [Định hướng tiếp theo](docs/next_direction_vi.md)

## Metric Selection Engine

Chạy `make test-selection` để kiểm tra contract M1. Cấu hình model, URL và
timeout nằm trong `config/selection.yaml`. Xem [quy trình đánh giá](docs/evaluation.md)
để chạy benchmark qua adapter của từng thành phần.

### Ollama và OpenAI-compatible trên Kaggle

Dùng `config/eval_kaggle_qwen3.yaml` để bật hybrid retrieval và embedding
`qwen3-embedding:4b` (768 chiều). Preset yêu cầu endpoint có model ID
`hf.co/Qwen/Qwen3-9B-Instruct-2507-GGUF`. ID này chưa được xác minh trong
registry công khai. Với Ollama có model công khai cùng dòng 2507, đặt
`AGENT4_LLM_MODEL=qwen3:4b-instruct-2507-q4_K_M`.
[Tag Ollama](https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M)

- LLM đọc `AGENT4_LLM_PROVIDER`, `AGENT4_LLM_BASE_URL`, `AGENT4_LLM_MODEL` và
  `AGENT4_LLM_API_KEY`.
- Embedding đọc `AGENT4_EMBED_PROVIDER`, `AGENT4_EMBED_BASE_URL`,
  `AGENT4_EMBED_MODEL`, `AGENT4_EMBED_DIMENSIONS` và `AGENT4_EMBED_API_KEY`.
- `AGENT4_RETRIEVAL_MODE` đổi chế độ retrieval. Đặt provider thành `openai`
  cho endpoint tương thích OpenAI. Base URL có thể là server root hoặc có
  hậu tố `/v1`. Lấy API key từ Kaggle Secrets hoặc biến môi trường của server.

Khởi tạo trước index cho pipeline governed bằng cùng cấu hình và biến môi trường
sẽ dùng lúc chạy API hoặc benchmark.

```bash
python -m scripts.build_vector_index --config config/eval_kaggle_qwen3.yaml
```

Pipeline dùng `AGENT4_METRIC_SELECTION_CONFIG=config/eval_kaggle_qwen3.yaml`.
Khi caching được bật và backend remote sẵn sàng, hybrid/dense retrieval tự
xây lại index thiếu hoặc không tương thích. Nếu archive hỏng, chạy lại lệnh
CLI để tạo index mới sau khi kiểm tra file.
