# Retrieval Baseline

Ngày chạy: 2026-11-01  
Dataset: `data/eval/test.jsonl` — 11 câu `resolved` (seed set, chưa phải deployment gate)  
Embedding: `hashing-v1:768`, CPU, in-memory NumPy  

| Variant | Recall@5 | All gold@5 | MRR | Avg candidates | Avg latency |
| --- | ---: | ---: | ---: | ---: | ---: |
| Dense | 1.000 | 1.000 | 1.000 | 20.00 | 0.15 ms |
| Lexical | 1.000 | 1.000 | 1.000 | 19.82 | 0.31 ms |
| Hybrid RRF | 1.000 | 1.000 | 1.000 | 18.73 | 0.51 ms |
| Hybrid + expansion | 1.000 | 1.000 | 1.000 | 24.64 | 0.62 ms |
| Hybrid + expansion + reranking | 1.000 | 1.000 | 0.894 | 12.00 | 0.85 ms |

Lệnh:

```bash
python scripts/benchmark_retrieval.py data/eval/test.jsonl
```

Kết luận ban đầu: candidate budget 12 vẫn giữ toàn bộ gold trong Top-5, nhưng
metadata reranker làm giảm MRR trên seed set. Trước khi production cần mở rộng
gold dataset, duyệt nhãn nghiệp vụ và tune trọng số/ranking signals trên dev set.
Không suy diễn các số này thành độ chính xác end-to-end của LLM.
