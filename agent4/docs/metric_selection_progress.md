# Metric Selection Progress

- [x] 66 metrics load và validate từ REGISTRY.
- [x] Typed request, candidate, result, debug và evaluation schemas.
- [x] Dense baseline, BM25, RRF, cache và optional mention retrieval.
- [x] Curated one-hop relationship expansion có budget.
- [x] Metadata reranking và injectable cross-encoder interface.
- [x] Example bank và năm few-shot modes.
- [x] Structured Ollama/mock provider, bounded retry và validation.
- [x] Pipeline orchestrator và FastAPI factory.
- [x] Evaluation helpers, scripts và seed train/dev/test data.
- [x] Retrieval baseline/ablation đã chạy; kết quả ở `docs/retrieval_baseline.md`.
- [x] `pytest`: 38 tests passed; `ruff check`: passed (2026-11-01).
- [ ] Xác minh integration thực tế với Ollama/model production (localhost:11434
      chưa chạy tại thời điểm kiểm thử).
- [ ] Nghiệp vụ duyệt example bank, relationship graph và gold labels.
- [ ] Chọn multilingual embedding/cross-encoder sau benchmark.
- [ ] Chốt deployment accuracy/latency threshold sau baseline.
