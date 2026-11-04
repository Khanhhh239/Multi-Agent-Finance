# Metric Selection Architecture

`metrics.py` và `REGISTRY` là nguồn sự thật duy nhất. Engine chỉ đọc metadata,
không sao chép hoặc thay đổi công thức.

Luồng xử lý:

```text
request -> dense + BM25 -> RRF -> one-hop expansion -> metadata reranking
        -> adaptive examples -> one structured LLM call -> deterministic validation
```

Mỗi stage nhận/trả contract có kiểu và được inject ở composition root
`agent4.metric_selection.factory`. Dense index hiện là ma trận NumPy trong bộ
nhớ vì catalog chỉ có 66 metrics. Provider embedding mặc định là hashing
deterministic để phát triển offline; cần benchmark model multilingual trước khi
đưa vào production. Provider LLM mặc định gọi Ollama và có thể thay bằng mock.

Lỗi retrieval rỗng, provider LLM và output validation là các lớp lỗi riêng.
Debug trace không ghi chain-of-thought, công thức hay dữ liệu tài chính đầu vào.
