# Agent 4 — "CFO ảo" (Trợ lý điều hành tài chính tức thời)

Trợ lý hội thoại tiếng Việt trả lời câu hỏi tài chính điều hành trên dữ liệu chưa khóa sổ, bằng lõi chỉ số tất định (TT133) + LLM ≤ 10B (Qwen3) chỉ để chọn công cụ và diễn giải.

**Trạng thái (17/10/2026):** P1 thử nghiệm đã tới **M1: 10/10 câu mẫu đúng bằng Qwen 4B thật**, qua hints → retriever → LLM schema → validator → engine → facts → verifier, đủ trace JSONL. Toàn bộ **2.586 test passed, 0 skipped** trước commit cuối. Đã dừng tại M1; chưa chạy đánh giá lớn, held-out val/test, API/UI hay pilot. Xem [số đo và lỗi quan sát](docs/5_handoff/M1_REPORT.md) và [tiến độ](docs/5_handoff/PROGRESS.md).

**công thức chưa được kế toán duyệt (G0.7 mở).** G0.7 **CHƯA ĐẠT**; 22 Must **cần duyệt trước pilot**. [Phiếu kế toán một trang](docs/5_handoff/FORMULA_REVIEW_ONE_PAGE.pdf), [hồ sơ 66 chỉ số](docs/5_handoff/FORMULA_REVIEW.md).

## Bắt đầu
```bash
python -m venv .venv
# Windows PowerShell: dùng ./.venv/Scripts/python.exe cho các lệnh python bên dưới
export PYTHONUTF8=1
pip install -r requirements.txt
pip install -e . --no-deps
python -m agent4.datagen.build --out data/cfo_warehouse.duckdb     # ~1 phút, seed 20251
python -m pytest tests -q                                          # test offline; hai test Ollama tùy chọn
python -m eval.review_formulas                                    # oracle + bảng rà soát
```
CLI thử nghiệm, cần Ollama cục bộ và model đã tải:
```powershell
./.venv/Scripts/python.exe -X utf8 -m agent4.agent.cli --model qwen3:4b-instruct-2507-q4_K_M
# Tra form khi model chưa sẵn sàng:
./.venv/Scripts/python.exe -X utf8 -m agent4.agent.cli --query net_revenue --period 2026-Q3
# Toàn bộ test gồm model thật:
$env:AGENT4_RUN_LLM='1'
./.venv/Scripts/python.exe -X utf8 -m pytest
```
Trace mặc định ở `data/traces/cli.jsonl`; `--json` xuất kết quả máy đọc được, `--samples 10` chạy 10 câu đầu. CLI dùng context4096, deadline20s; mọi số tài chính từ engine. Model chỉ chọn công cụ/diễn giải định tính; verifier có thể trả nguyên khối sự kiện khi diễn giải bị chặn.
```python
from agent4.engine.engine import ExecutionEngine
e = ExecutionEngine("data/cfo_warehouse.duckdb")
e.query("net_revenue", "last_quarter", compare_to="previous_period")
e.query("overdue_receivables", params={"min_days": 30})
e.explain("net_profit", "2026-Q2")
```

## Cấu trúc
```
agent4/{config.py, datagen/, engine/, agent/}    # package Python trong dự án này
tests/   eval/   docs/   reference_v0/
agent4/api/   agent4/integrations/   web/        # sản phẩm P3 chưa triển khai
```
Trong monorepo upstream, dự án nằm dưới `agent4/`. Tệp tham chiếu gốc được giữ trong `reference_v0/`; bắt đầu từ `docs/5_handoff/00_START_HERE.md`.
