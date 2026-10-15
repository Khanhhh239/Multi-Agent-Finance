# Agent 4 — "CFO ảo" (Trợ lý điều hành tài chính tức thời)

Trợ lý hội thoại tiếng Việt trả lời câu hỏi tài chính điều hành trên dữ liệu chưa khóa sổ, bằng lõi chỉ số tất định (TT133) + LLM ≤ 10B (Qwen3) chỉ để chọn công cụ và diễn giải.

**Trạng thái (14/10/2026):** ✅ bộ sinh dữ liệu doanh nghiệp mẫu · ✅ lõi 66 chỉ số + bộ phân giải thời gian/định dạng số · ✅ 12 test hợp đồng v0 · ⏳ agent LLM, guardrail, đánh giá, API/UI chưa làm — xem `docs/5_handoff/`.

## Bắt đầu
```bash
cd agent4
export PYTHONUTF8=1
pip install -r requirements.txt
python -m agent4.datagen.build --out data/cfo_warehouse.duckdb     # ~1 phút, seed 20251
python -m pytest tests -q                                          # 12 passed
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
