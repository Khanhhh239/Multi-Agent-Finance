# Agent 4 — Data Foundation

Repository này chỉ giữ lại dữ liệu và bộ sinh dữ liệu tổng hợp để làm nền cho
việc xây dựng lại Agent 4 từ đầu.

## Thành phần được giữ lại

- `data/`: warehouse DuckDB và ground truth đã sinh (được giữ local, không commit).
- `agent4/datagen/`: bộ mô phỏng doanh nghiệp và sinh warehouse.
- `agent4/config.py`: cấu hình ngày chốt dữ liệu và đường dẫn warehouse.
- `docs/2_data/`: tài liệu chiến lược, lược đồ và quy tắc dữ liệu.
- `reference_v0/`: bộ sinh dữ liệu và tài liệu tham chiếu phiên bản đầu.
- `tests/test_budget_seed.py`: kiểm tra tính tất định của dữ liệu ngân sách.

## Cài đặt

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e . --no-deps
```

## Sinh lại dữ liệu

```bash
python -m agent4.datagen.build \
  --out data/cfo_warehouse.duckdb \
  --seed 20251
```

Ngày dữ liệu mặc định là `2026-10-14`; có thể thay đổi bằng biến môi trường
`AGENT4_AS_OF`. Tháng khóa sổ mặc định là `2026-08`; có thể thay đổi bằng
`AGENT4_LAST_CLOSED_MONTH`.

## Kiểm tra

```bash
pytest
```
