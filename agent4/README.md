# Agent 4 — "CFO ảo" (Trợ lý điều hành tài chính tức thời)

Trợ lý hội thoại tiếng Việt trả lời câu hỏi tài chính điều hành trên dữ liệu chưa khóa sổ, bằng lõi chỉ số tất định (TT133) + LLM ≤ 10B (Qwen3) chỉ để chọn công cụ và diễn giải.

**Trạng thái (16/10/2026):** Đã thực hiện phần kỹ thuật T0.1–T0.5: **1.390 test xanh**, oracle độc lập **66 chỉ số × 6 kỳ**, phạm vi hàng, so sánh custom, ngày thu ngân hàng và data version. **Chờ kế toán trưởng duyệt T0.6/G0.7** trước P1. Agent LLM, đánh giá agent, API/UI và pilot chưa hoàn thành. Xem [báo cáo thực hiện](docs/5_handoff/PROGRESS.md) và [bảng duyệt công thức](docs/5_handoff/FORMULA_REVIEW.md).

## Bắt đầu
```bash
python -m venv .venv
# Windows PowerShell: dùng ./.venv/Scripts/python.exe cho các lệnh python bên dưới
export PYTHONUTF8=1
pip install -r requirements.txt
pip install -e . --no-deps
python -m agent4.datagen.build --out data/cfo_warehouse.duckdb     # ~1 phút, seed 20251
python -m pytest tests -q                                          # 1.390 passed
python -m eval.review_formulas                                    # oracle + bảng rà soát
```
```python
from agent4.engine.engine import ExecutionEngine
e = ExecutionEngine("data/cfo_warehouse.duckdb")
e.query("net_revenue", "last_quarter", compare_to="previous_period")
e.query("overdue_receivables", params={"min_days": 30})
e.explain("net_profit", "2026-Q2")
```

## Cấu trúc
```
agent4/agent4/{config.py, datagen/, engine/, agent/(trống), api/(trống), integrations/(trống)}
agent4/tests/   agent4/eval/ (trống)   agent4/web/ (trống)   agent4/docs/  ← đọc docs/README.md
```
Tệp tham chiếu ở gốc repo: `schema.md`, `metrics-v0.md`, `sample-questions.md`, `generate_data.py` (đã sửa 2 lỗi), `requirements.txt`.
