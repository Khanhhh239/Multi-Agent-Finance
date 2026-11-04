# Evaluation

`data/eval/` có train/dev/test JSONL. Paraphrase cùng nhóm phải dùng chung
`group_id` khi mở rộng dataset để tránh leakage. Nhãn hiện tại là seed dataset
và cần được người am hiểu nghiệp vụ duyệt trước khi dùng làm deployment gate.

Retrieval report gồm Recall@K, Precision@K, MRR, All-Gold-Covered@K, candidate
count và latency. End-to-end report gồm exact set match, metric P/R/F1, status
accuracy, valid output rate và latency.

```bash
python scripts/benchmark_retrieval.py
python scripts/benchmark_fewshot.py --strategy adaptive
python scripts/benchmark_pipeline.py
```

Benchmark few-shot/pipeline cần LLM provider đang hoạt động. Không ghi kết quả
benchmark vào source nếu lệnh chưa thực sự chạy.

Retrieval baseline đã chạy được ghi tại `docs/retrieval_baseline.md`. Báo cáo
bao gồm breakdown theo category trong output JSON của script.
