# 06 · Runbook môi trường và vận hành

## Kết quả cập nhật 17/10/2026
Môi trường tại workspace đã có `.venv` Python 3.12.13. Chạy PowerShell:
```powershell
cd C:\Users\Admin\Downloads\Agent4
$env:AGENT4_RUN_LLM='1'
./.venv/Scripts/python.exe -X utf8 -m pytest --junitxml=artifacts/t1_10-final-pytest.xml
./.venv/Scripts/python.exe -X utf8 -m agent4.agent.cli --model qwen3:4b-instruct-2507-q4_K_M
```
Lượt kiểm chứng cuối: **2.586 passed, 0 skipped**, 64,53s (JUnit), có hai test kết nối Ollama thật. **M1 10/10 câu dev đúng bằng Qwen4B**, 31.702/1.680 token vào/ra, p50/p95=4,109/6,622s. Đã dừng tại M1; không chạy held-out val/test hoặc bộ đánh giá lớn. Chi tiết `M1_REPORT.md`/`PROGRESS.md`. **công thức chưa được kế toán duyệt (G0.7 mở)**; G0.7 **CHƯA ĐẠT**, 22 Must **cần duyệt trước pilot**.

Kho cũ giữ tại `data/cfo_warehouse.duckdb.unversioned`; kho mặc định đã tái sinh với metadata `data_version=v2.0`, cùng hash sổ cái. Kho DuckDB không commit; phép đo/trace dev dùng làm bằng chứng ở `measurements/`. Git local độc lập; dùng `scripts/publish_card.py` để đồng bộ từng commit vào `agent4/` của monorepo và push `agent4-Khanh` qua checkout `.publish/`.

CLI mặc định 4B/context4096/deadline20s, tắt thinking; khác mặc định `LLMConfig` chung ở bảng dưới. `--question '…'` dùng batch, `--samples 10 --json` chạy demo, trace mặc định `data/traces/cli.jsonl`. Model lỗi trả lựa chọn form; chạy `--query net_revenue --period 2026-Q3` để tra không cần model. Engine dùng 4 threads/512MB để chia sẻ RAM. Integration test unload model sau mỗi test; client thường giữ 5 phút. 8B/context8192 đã từng HTTP500, chưa xác nhận ổn định.

Chạy lại phép đo (dùng run-id mới, không ghi đè bằng chứng):
```powershell
./.venv/Scripts/python.exe -X utf8 -m eval.smoke_m1 --run-id m1-repeat
```

## 1. Yêu cầu
| Thành phần | Phiên bản đã dùng | Ghi chú |
|---|---|---|
| OS | Windows 11 (Git Bash + PowerShell) | Mã chạy cả Linux/macOS |
| Python | 3.12 (qua `uv`) | Trình khởi chạy `py`/Python cài sẵn trên máy dev bị hỏng ⇒ **dùng venv của `uv`** |
| DuckDB | ≥ 1.0 (bản mới nhất trong venv) | Kho ~28 MB |
| Ollama | 0.40.5 (đo ở M1) | Model: `qwen3:8b` (5,2 GB), `qwen3:4b-instruct-2507-q4_K_M` (2,5 GB) |
| GPU | RTX 4050 Laptop 6 GB | Xem `4_ai_engineering/06` |
| Thư viện | `duckdb pytest openai httpx pydantic numpy pandas rich fastapi uvicorn` | P1+ thêm `rank-bm25 sqlglot hypothesis` (tùy chọn `sentence-transformers`) |

## 2. Cài đặt từ đầu
```bash
# 1) lấy mã (nhánh agent4-Khanh)
git -c core.longpaths=true clone -b agent4-Khanh https://github.com/Khanhhh239/Multi-Agent-Finance.git maf
cd maf/agent4

# 2) môi trường (uv)
uv venv .venv --python 3.12
source .venv/Scripts/activate          # Windows Git Bash;  Linux: source .venv/bin/activate
uv pip install -r requirements.txt
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8     # tránh lỗi mã hóa cp1252 khi in tiếng Việt

# 3) dữ liệu (không commit; tái sinh được)
python -m agent4.datagen.build --out data/cfo_warehouse.duckdb      # seed mặc định 20251

# 4) test
python -m pytest tests -q

# 5) model
ollama pull qwen3:8b
ollama pull qwen3:4b-instruct-2507-q4_K_M
```
> Nếu `uv python` báo "Missing expected target directory…": dùng đường dẫn trực tiếp của Python do uv tải về (`…\uv\python\cpython-3.12.x-windows-x86_64-none\python.exe`) làm tham số `--python`.

## 3. Biến môi trường (`agent4/config.py`)
| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `AGENT4_DATA_DIR` | `<dự án>/data` | Thư mục dữ liệu |
| `AGENT4_DB` | `data/cfo_warehouse.duckdb` | Kho sổ cái |
| `AGENT4_OPS_DB` | `data/cfo_ops.duckdb` | Ops DB (approvals/audit) |
| `AGENT4_AS_OF` | `2026-10-14` | Ngày chốt dữ liệu (mốc "hôm nay") |
| `AGENT4_LAST_CLOSED_MONTH` | `2026-08` | Tháng khóa sổ gần nhất |
| `AGENT4_LLM_BASE_URL` | `http://localhost:11434` | Ollama |
| `AGENT4_LLM_MODEL` | `qwen3:8b` | Model |
| `AGENT4_LLM_TEMPERATURE` | `0` | |
| `AGENT4_LLM_NUM_CTX` | `8192` | |
| `AGENT4_LLM_THINK` | `0` | `1` bật thinking (Qwen3‑8B) |
| `AGENT4_MAX_STEPS` | `5` | Số bước tối đa/câu |
Ollama: `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0` (tùy chọn), `OLLAMA_NUM_PARALLEL=1`.

## 4. Quy ước kho dữ liệu cho dev/val/test
| Mục đích | Seed | Lệnh |
|---|---|---|
| dev | 20251 (mặc định) | `python -m agent4.datagen.build --out data/dev.duckdb --seed 20251` |
| val | 71 | `--out data/val.duckdb --seed 71` |
| test | 9001 (giữ kín) | `--out data/test.duckdb --seed 9001` |
(`build.py` đã có tham số `--seed`; `--as-of` và `--last-closed` dùng biến môi trường — xem K12.)

## 5. Việc thường gặp
| Muốn | Làm |
|---|---|
| Xem nhãn sự thật | `duckdb data/cfo_warehouse.duckdb "SELECT id, detail FROM ground_truth"` |
| Chạy một chỉ số | `python -c "from agent4.engine.engine import ExecutionEngine as E; print(E('data/cfo_warehouse.duckdb').query('dso','2026-Q3')['display'])"` |
| Kiểm tra đối soát | Chạy `build` và đọc phần thống kê cuối (`*_gap` phải bằng 0) |
| Đổi số liệu mẫu | Sửa `datagen/company.py` / `simulator.py` → tăng `data_version` (`company_info`) → chạy lại `build` → chạy toàn bộ test |
| Xóa dữ liệu sinh | Xóa `data/*.duckdb` |

## 6. Sự cố thường gặp
| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `UnicodeEncodeError: 'charmap'…` khi in tiếng Việt | Console Windows cp1252 | `PYTHONUTF8=1` |
| `Filename too long` khi `git clone` | Đường dẫn dài trên Windows | Clone vào thư mục ngắn + `-c core.longpaths=true` |
| `Failed to launch …\Python3xx\python.exe (0x80070003)` | Python cài sẵn hỏng | Dùng venv `uv` |
| DuckDB `IOException` mở file | File đang được tiến trình khác ghi | Đóng kết nối; engine mở `read_only=True` |
| Ollama trả lời bị cắt | `num_ctx` mặc định ngắn | Đặt `num_ctx`/`num_predict` rõ (mục 3) |
| Model 8B chậm/lỗi VRAM | 5,2 GB + KV > 6 GB | Dùng 4B‑2507 hoặc `num_ctx` 4096, KV `q8_0` |
