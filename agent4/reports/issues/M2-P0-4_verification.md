# M2-P0-4 — Bằng chứng xác minh

## Thay đổi và phạm vi

- `create_demo_app()` và `AGENT4_DEMO_MODE=1` bật UI, thông tin runtime, danh mục 22 chỉ tiêu và 12 câu mẫu. `create_app()` ở chế độ thường tiếp tục yêu cầu claims và policy từ host middleware. Khi host đã đưa một phần danh tính, demo cũng từ chối thay vì tự cấp persona.
- CFO demo có hai view quản trị và thuế. HCM Branch Viewer chỉ được đọc view quản trị và dòng HCM. Policy hash gồm phạm vi dòng. Validator từ chối mã chi nhánh ngoài quyền và gắn filter HCM nếu câu hỏi không nêu chi nhánh. Quy tắc áp dụng cả ở lượt tiếp tục session làm rõ.
- Demo trả trace ID. Sau khi SQL safety, thực thi và kiểm chứng kết quả hoàn tất, tenant demo nhận template SQL chỉ đọc có placeholder và semantic plan với mã đối tác đã che. Mã cảnh báo production vẫn theo contract pipeline.
- `AGENT4_DB_PATH` mặc định chọn warehouse tổng hợp v2.1. `AGENT4_SELECTION_CONFIG` mặc định chọn `config/selection.yaml`, với `AGENT4_METRIC_SELECTION_CONFIG` là tên thay thế. Host tự vận hành tunnel khi cần. Lượt này xác minh trên loopback và Ollama cục bộ, chưa chạy Kaggle hoặc Cloudflare.

## Các lượt kiểm tra

1. Kiểm thử tập trung phát hiện test mới kỳ vọng 403 cho session của persona khác, trong khi contract session trả 400 cho ID ngoài scope. Sửa kỳ vọng của test mới và xác nhận phiên HCM hợp lệ vẫn dùng filter bắt buộc. Kiểm tra tập trung thoát 0 với 160 test.
2. Toàn suite ban đầu thoát 1 với ba ca demo trả 503. Tái hiện bằng hai kết nối DuckDB cùng file với cấu hình khác nhau, nhận `ConnectionException`. Dùng bản sao read-only riêng cho nhóm test demo, tương tự test governed pipeline. Toàn suite sau đó qua với 610 test. Test bảo mật và governed pipeline có sẵn giữ nguyên.

| Lệnh | Exit | Kết quả |
| --- | ---: | --- |
| `.venv/bin/python -m pytest -o addopts='' -q tests/contracts/test_governed_demo_api.py tests/contracts/test_governed_pipeline.py tests/contracts/test_intake_auth_catalog.py tests/contracts/test_planning_and_plan_validation.py tests/security` | 0 | 160 qua ở lượt tập trung |
| `make verify PYTHON=.venv/bin/python` | 0 | Format, Ruff, compile và 610 test qua |
| `node --check /tmp/agent4-demo-ui.js` | 0 | JavaScript trích từ trang hợp lệ |
| `make -n demo PYTHON=.venv/bin/python` | 0 | Đúng factory và cổng 8000 |
| `git diff --check` | 0 | Qua |

Kiểm tra trình duyệt trên Uvicorn thật. D-11 tự chuyển sang HCM và hiển thị `UNAUTHORIZED (403)`. D-10 hiển thị các nút bổ sung kỳ. Chọn tháng 8 trả `OK (200)`, bảng kết quả và ngăn SQL với `branch_code = ?` cùng trace ID. Ở viewport 390 px, hai cột xếp thành một và không tràn ngang.

## Đánh giá 12 câu mẫu qua HTTP

- Đối chứng trước khi bật demo. Gọi cùng 12 câu qua `create_app()` không có host middleware và nhận 12 phản hồi 403. Đối chứng này đo fail-closed, không đo chất lượng model.
- Runtime thực dùng `qwen3:4b` digest `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`, Ollama cục bộ, seed mặc định `20261101` và full catalog. SHA-256 preset `fe66cfd516f2dc3c4f13001fb624199d3ebf45bbffc60d291d5ebeaa2b932f47`. SHA-256 warehouse v2.1 `02955b237682e623a4e0cb022e3c8fefe5089c8698609ba7aad2111b29c1f6eb`.
- Cổng thực thi khớp **12/12** kỳ vọng, gồm 9 kết quả ready, 1 lượt cần làm rõ, 1 từ chối 403 và 1 chỉ tiêu thử nghiệm trả 422. D-02 chọn alias `gross_margin`, tương đương metric canonical và giữ đơn vị phần trăm. D-08/D-09 thực thi được trên v2.1 và có warning watermark, SQL placeholder và mã đối tác đã che. D-09 dùng đúng từ 2026-01-01 đến 2026-09-30.
- P50/P95 lần lượt **4,36 / 38,39 giây** trên 12 mẫu, với browser QA chạy trong cùng khoảng thời gian. Đây là độ trễ quan sát được, không phải đo tải riêng. Chi phí và tính đúng của từng giá trị số chưa được đối soát độc lập.

```bash
AGENT4_DEMO_MODE=1 AGENT4_DB_PATH=data/cfo_warehouse.duckdb \
  AGENT4_SELECTION_CONFIG=config/selection.yaml AGENT4_LLM_PROVIDER=ollama \
  AGENT4_LLM_MODEL=qwen3:4b AGENT4_LLM_BASE_URL=http://127.0.0.1:11434 \
  AGENT4_RETRIEVAL_MODE=full_catalog \
  .venv/bin/python -m uvicorn agent4.api:create_demo_app --factory --host 127.0.0.1 --port 8765

PYTHONPATH=. .venv/bin/python reports/eval/M2-P0-4_demo_api/check_demo_api.py \
  http://127.0.0.1:8765 reports/eval/M2-P0-4_demo_api/summary.json
```

[Chi tiết từng câu mẫu](../eval/M2-P0-4_demo_api/summary.json)
