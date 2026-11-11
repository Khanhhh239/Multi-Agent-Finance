# M1-P0-3 — Bằng chứng xác minh

## Phạm vi

- Selector và embedding hỗ trợ Ollama và OpenAI-compatible. Cấu hình YAML nhận override từ môi trường. API key được chuyển qua Bearer header và được loại khỏi cấu hình serialize cho benchmark. Cache request phân biệt credential bằng digest nội bộ.
- Selector dùng budget mặc định 1.024 token, bỏ khối thinking, chuẩn hóa trường tin nhắn thừa và bổ sung câu làm rõ tại ranh giới provider. Nội dung giải mã được kiểm tra trước khi bỏ trường. E0 giữ JSON mode, 384 token và không retry để giữ cấu hình đối chứng.
- CLI dùng catalog canonical của pipeline governed. Hybrid/dense có thể tự tạo index remote thiếu hoặc stale khi hai cờ cache đang bật. Archive hỏng giữ nguyên và báo lỗi. Quá trình rebuild được đồng bộ trong một tiến trình và publish archive nguyên tử. Nhiều worker riêng biệt có thể cùng thực hiện cold build.
- Preset Kaggle giữ nguyên ID `hf.co/Qwen/Qwen3-9B-Instruct-2507-GGUF` theo Issue. ID này chưa xác minh được trên registry công khai. Tag `qwen3-embedding:4b` và tag thay thế `qwen3:4b-instruct-2507-q4_K_M` đã được xác minh. Máy chạy test có Ollama nhưng không có endpoint Kaggle hoặc model 4B embedding và 9B theo yêu cầu. Benchmark bên dưới dùng các model đã cài cục bộ. [Ollama Qwen3](https://ollama.com/library/qwen3/tags) · [Ollama Qwen3 Embedding](https://ollama.com/library/qwen3-embedding/tags)

## Các lượt xác minh

1. Kết nối hai giao thức, thêm chuẩn hóa và rebuild có điều kiện. Lượt kiểm tra cũ phát hiện E0 từ chối cấu hình mới vì E0 pin `max_retries: 0`. Giữ wire format/budget/retry lịch sử trong adapter E0. Pytest tập trung chạy qua 92 test. Toàn suite thoát 1 do test cache warm vẫn kỳ vọng index Ollama stale báo lỗi mặc dù server mock hoạt động.
2. Cập nhật test cache để xác nhận index stale và index thiếu được dựng lại, đồng thời kiểm tra số lượt embedding và tiếp tục chặn lỗi few-shot. Bộ hồi quy mới kiểm tra archive hỏng, cache tắt, provider lỗi, hai request concurrent, dữ liệu batch OpenAI và việc chặn SQL trong trường sẽ bị loại. Lượt xác minh cuối qua toàn suite.

| Lệnh | Exit | Kết quả |
| --- | ---: | --- |
| `.venv/bin/python -m ruff check agent4/metric_selection scripts` | 0 | Qua |
| `make format-check lint typecheck PYTHON=.venv/bin/python CHECK_PATHS='agent4/metric_selection scripts/build_vector_index.py tests/contracts/test_remote_metric_selection.py tests/contracts/test_cache_governance.py'` | 0 | 26 tệp đúng format, lint và compileall qua |
| `.venv/bin/python -m pytest tests/contracts/test_metric_selection_e0.py tests/contracts/test_retrieval_and_fewshot.py tests/contracts/test_selection_and_metric_validation.py tests/contracts/test_metric_selection_recovery.py -v` | 0 | 92 qua |
| `.venv/bin/python -m pytest -o addopts='' -q tests/contracts/test_remote_metric_selection.py` | 0 | 24 qua |
| `.venv/bin/python -m pytest -q tests` | 0 | 594 qua |
| `git diff --check` | 0 | Qua |

Smoke test thật gọi Ollama tại `http://127.0.0.1:11434`. Hai lệnh `.venv/bin/python -m scripts.build_vector_index --config /tmp/agent4-m1-p0-3.9iGICN/ollama.yaml` và `.venv/bin/python -m scripts.build_vector_index --config /tmp/agent4-m1-p0-3.9iGICN/openai.yaml` đều thoát 0, tạo và đọc lại 70 vector × 768. Hai YAML là bản sao preset với đường dẫn index tạm. Cùng endpoint đã trả JSON structured hợp lệ qua `/v1/chat/completions` với Qwen2.5 0.5B. CLI/HTTP smoke không phải benchmark chất lượng.

## Benchmark dev

Baseline là M1-P0-2 lexical. Cả hai lượt dùng 140 ca dev, MPX10 v3, seed `20261101`, model `qwen2.5:0.5b` digest `a8b0c51577010a279d933d14c2a8ab4b268079d44c5c8830c0a93900f1827c67` và prompt `metric-selection-v1-structured`. Dataset SHA-256 `094fb090bff62ee8c83045eed3780c371ec3f4cf38095f274237c02a6b5b88d5`.

Lượt M1-P0-3 dùng endpoint OpenAI-compatible của Ollama cục bộ cho cả chat và embedding, hybrid retrieval với `qwen3-embedding:0.6b` digest `ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d`, 768 chiều và index đã tạo từ CLI. Cấu hình khác baseline cả retrieval, giao thức, budget và retry, nên chênh lệch phản ánh preset kết hợp. Cấu hình thực tế được ghi trong `summary.json`.

```bash
export AGENT4_LLM_PROVIDER=openai AGENT4_EMBED_PROVIDER=openai
export AGENT4_LLM_BASE_URL=http://127.0.0.1:11434 AGENT4_EMBED_BASE_URL=http://127.0.0.1:11434
export AGENT4_LLM_MODEL=qwen2.5:0.5b AGENT4_EMBED_MODEL=qwen3-embedding:0.6b
export AGENT4_EMBED_DIMENSIONS=768 AGENT4_RETRIEVAL_MODE=hybrid
AGENT4_WAREHOUSE_TENANT_ID=minh-phat AGENT4_METRIC_SELECTION_CONFIG=/tmp/agent4-m1-p0-3.9iGICN/openai.yaml \
  make eval PYTHON=.venv/bin/python ADAPTER=agent4.eval_adapter:predict \
  MODEL_VERSION=qwen2.5:0.5b@a8b0c5157701 PROMPT_VERSION=metric-selection-v1-structured \
  EVAL_CONFIG=/tmp/agent4-m1-p0-3.9iGICN/openai.yaml OUTPUT_DIR=reports/eval/M1-P0-3_local_openai_hybrid \
  BASELINE=reports/eval/M1-P0-2_governed_dev_lexical_final/summary.json
```

Runner ghi đủ 140 dự đoán, đánh dấu baseline tương thích theo tiêu chí dataset và chấm điểm. Runner thoát 1 do 13 ca `runtime_failure`, nên `make eval` thoát 2. Lượt này không đặt ngưỡng chất lượng riêng.

| Chỉ số | M1-P0-2 lexical | M1-P0-3 OpenAI-compatible hybrid |
| --- | ---: | ---: |
| Chọn metric chính xác | 79/140 | 89/140 |
| Plan chính xác | 67/140 | 73/140 |
| Trạng thái E2E chính xác | 107/140 | 116/140 |
| Retrieval recall@5, coverage 114/120 | 95% | 95% |
| SQL thực thi thành công | 80/80 | 85/85 |
| Ca kiểm tra safety đạt | 13/15 | 13/15 |
| Runtime failure | 11 | 13 |
| P50 / P95, 140 mẫu mỗi lượt | 1,590 / 2,169 giây | 2,170 / 2,871 giây |
| Token trung bình quan sát được | 722 trên 116 mẫu | 1.018 trên 125 mẫu |
| Chi phí USD và đối soát số liệu độc lập | Chưa đo | Chưa đo |

- Trạng thái đúng tăng 15 ca và giảm 6 ca. BM-017 và BM-109 đi qua selector và trả `ready`, nhưng chọn `net_profit` trong khi câu hỏi cần `net_margin_pct`. Đây chỉ là cải thiện ở chỉ số trạng thái.
- BM-023 chọn thêm metric không tương thích với bộ lọc. BM-029 chọn thêm `budget_amount`, làm trộn hai nguồn warehouse và bị compiler từ chối. Bộ chấm cũng tính `budget_amount` là ID ngoài `REGISTRY`, dù ID có binding ở catalog production. Đây là ca invalid metric duy nhất trong lượt hybrid.
- 13 runtime failure gồm sáu plan không tương thích hoặc yêu cầu ngoài phạm vi, bốn lựa chọn trộn flow/snapshot và ba `unknown_metric`. BM-119 và BM-120 chọn đúng metric và thực thi an toàn, với `no_data` trên MPX10 v3.
- Kết quả xác minh transport và pipeline cục bộ. Chất lượng, thời gian và chi phí trên Kaggle với cặp model đích vẫn cần đo ở endpoint thật.

[Baseline](../eval/M1-P0-2_governed_dev_lexical_final/summary.json) · [Tóm tắt lượt hybrid](../eval/M1-P0-3_local_openai_hybrid/summary.json) · [Kết quả từng ca](../eval/M1-P0-3_local_openai_hybrid/cases.jsonl)
