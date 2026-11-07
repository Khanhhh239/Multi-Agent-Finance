# Architecture Decision Record (ADR): Redesigning Module 2 — Governed Metric Selection (`agent4/metric_selection/`)

> **Trạng thái:** Proposed & Approved for M1 Execution  
> **Ngày cập nhật:** 2026-11-07  
> **Phạm vi:** `agent4/metric_selection/`, Contracts 5–15 (`contracts.md`), `vals/run_eval.py`  
> **Tài liệu liên quan:** [docs/plans/metrics_selection.md](plans/metrics_selection.md) | [docs/metric_selection_evaluation.md](metric_selection_evaluation.md)

---

## ADR-001: Full-Catalog LLM Selection (`E0`) vs Top-K Retrieval (`E1`/`E2`)

- **Trạng thái:** **Confirmed** cho việc triển khai cả hai chế độ; **Provisional** cho việc chọn chế độ mặc định cuối cùng (phụ thuộc kết quả Decision Gate G2).
- **Bối cảnh (Context):**
  - Danh mục metric chuẩn trong `agent4/engine/metrics.py` (`REGISTRY`) có **66 metrics** (và danh mục contract v1 trong `agent4/core/catalog.py` có **13 metrics** hợp lệ).
  - Trong kiến trúc cũ (`docs/plans/metrics_selection.md` bản trước), hệ thống mặc định bắt buộc cắt ứng viên qua Top-K Retrieval ($K=12$) trước khi đưa vào LLM, mà chưa hề đo đạc xem Retrieval giúp tăng độ chính xác hay ngược lại làm rớt metric trong các truy vấn đa chỉ tiêu (`multi_metrics`, yêu cầu 2–5 metrics cùng lúc).
  - Toàn bộ 66 định nghĩa metric rút gọn (gồm `metric_id`, `label`, `description`, `unit`, `period_type`, `supported_views`, `supported_dimensions`) chỉ chiếm khoảng **2,200–2,800 tokens**, hoàn toàn nằm gọn trong cửa sổ ngữ cảnh 8,192 tokens của `Qwen3:4b`.
- **Quyết định (Decision):**
  1. Bắt buộc xây dựng và đo đạc **Full-Catalog Baseline (`Experiment E0`)** ở ngay Issue đầu tiên (`M1.0`) trước khi xây dựng Dense/Hybrid Retrieval.
  2. Trong chế độ `full_catalog`, `orchestrate_retrieval` trả về một `MetricRetrievalResult` hợp lệ chứa toàn bộ `catalog.list_visible_metrics(auth_context)` với `retrieval_sources=["catalog_full"]`. Nhờ đó, đầu ra của `E0` vẫn đi qua `validate_metrics()` và tuân thủ 100% bất biến $\text{selected} \subseteq \text{candidates} \subseteq \text{catalog}$ của Contract 15.
  3. Giữ `Full-Catalog (E0)` làm một ứng viên production/submission hợp lệ nếu thực nghiệm cho thấy `E0` đạt `Exact Set Match` cao hơn hoặc tương đương `E2` (Hybrid Retrieval) với độ trễ p95 chấp nhận được.
- **Đánh đổi (Tradeoffs):**
  - *Ưu điểm của Full-Catalog (`E0`)*: `Complete Gold Set Recall` đạt **100% tuyệt đối** đối với mọi metric được phép; không bao giờ bị lỗi rớt 1 trong 3–5 metric của câu hỏi tổng hợp; không phụ thuộc vào chất lượng mô hình embedding khi diễn đạt câu hỏi lạ.
  - *Nhược điểm của Full-Catalog (`E0`)*: Prompt dài hơn (~2.5k input tokens so với ~600 tokens ở Top-12), thời gian prefill trên CPU/GPU local lâu hơn, và LLM phải tự phân biệt giữa 66 lựa chọn thay vì 12 lựa chọn.

---

## ADR-002: Dense Retrieval vs Hybrid Retrieval (Dense + Lexical + RRF + Metadata Reranking)

- **Trạng thái:** **Provisional** (Đánh giá thực nghiệm qua `E1` vs `E2` trong Issue `M1.1`).
- **Bối cảnh (Context):**
  - Câu hỏi tài chính doanh nghiệp Việt Nam vừa chứa các thuật ngữ kế toán/viết tắt cố định (*"TK 511"*, *"DSO"*, *"DPO"*, *"DIO"*, *"EBITDA"*, *"OPEX"*, *"GTGT"*, *"TNDN"*), vừa chứa các cách hỏi đời thường của CEO (*"tiền khách đang nợ"*, *"sống được bao lâu"*, *"lỗ hay lãi"*).
  - Dense retrieval đơn thuần dễ nhầm lẫn giữa các chỉ tiêu cùng miền ngữ nghĩa (ví dụ `dso` vs `dso_actual`, `gross_profit` vs `gross_margin_pct`), trong khi Lexical retrieval đơn thuần sẽ trả rỗng (`empty_candidates`) nếu người dùng dùng cách diễn đạt ngoài danh sách `synonyms`.
- **Quyết định (Decision):**
  - Thiết kế hệ thống Hybrid Retrieval nhẹ gồm 4 bước:
    1. **Dense Retrieval (`dense.py`)**: Cosine similarity trên vector chuẩn hóa L2 của `MetricDocument`.
    2. **Lexical Retrieval (`lexical.py`)**: Khớp chính xác `label`/`label_en`, khớp cụm từ trong `aliases`/`synonyms`, và độ phủ token chuẩn hóa tiếng Việt/tiếng Anh.
    3. **Reciprocal Rank Fusion (`fusion.py`)**: Trộn thứ hạng với hằng số $k = 60$:
       $$\text{score}_{\text{RRF}}(m) = \sum_{s \in \{\text{dense}, \text{lexical}\}} \frac{1}{60 + \text{rank}_s(m)}$$
    4. **Metadata Reranker (`rerank.py`)**: Chấm điểm lại dựa trên `0.60 * label_match + 0.25 * view_compatibility + 0.15 * language_match`, giữ nguyên tập ứng viên đầu vào.
  - **Không đưa vào Neural Cross-Encoder Reranker** ở giai đoạn đầu để tiết kiệm bộ nhớ và độ trễ; chỉ xem xét nếu Metadata Reranker không đạt yêu cầu ở `E2`.

---

## ADR-003: Zero-shot vs Static vs Dynamic Few-shot (`compatible_only=True`)

- **Trạng thái:** **Provisional** (Quyết định bật/tắt và chọn chiến lược qua Ablation `E2` $\rightarrow$ `E3` $\rightarrow$ `E4` trong Issue `M1.2`).
- **Bối cảnh (Context):**
  - Kho ví dụ `data/example_bank.jsonl` chứa các cặp câu hỏi đối조 (contrastive examples) được thiết kế đặc biệt cho các quyết định khó (`amount_vs_ratio`, `accounting_vs_tax`, `narrow_vs_broad_cost`, `formula_vs_actual`, `liquidity_ratio`, `multi_metric_disambiguation`, `ambiguous_metric`, `unsupported_metric`).
  - Tuy nhiên, Contract 13 (`fewshot.retrieval.dynamic.v1`) quy định bất biến an toàn bắt buộc ở chế độ production (`compatible_only=True`):
    $$\text{example.expected\_selection.metric\_ids} \subseteq \text{candidate\_metric\_ids}$$
  - Nếu chọn few-shot không cẩn thận, một ví dụ chỉ chứa 1 metric có thể làm mô hình `Qwen3:4b` thiên lệch (anchoring) sang chọn 1 metric thay vì nhiều metric, hoặc ngược lại.
- **Quyết định (Decision):**
  - Tách `fewshot.py` thành một module độc lập hỗ trợ 5 chế độ cấu hình (`zero`, `static`, `similarity`, `coverage`, `hybrid`) để chạy ablation study công bằng:
    - `zero`: Không chèn ví dụ (`examples=[]`).
    - `static`: Chọn cố định tối đa $M$ ví dụ đại diện cho các cấu trúc câu hỏi khác nhau (1 metric, đa metric, mơ hồ, ngoài phạm vi) thỏa mãn `compatible_only=True`.
    - `similarity`: Xếp hạng ví dụ tương thích theo độ tương đồng câu hỏi.
    - `coverage`: Ưu tiên các ví dụ có `matched_metric_ids` và `decision_tags` bao phủ các cặp ứng viên dễ nhầm (`confusable_metrics`) đang có mặt trong `candidate_metric_ids`.
    - `hybrid`: Kết hợp điểm tương đồng câu hỏi và điểm độ phủ quyết định (`alpha * similarity + beta * candidate_overlap + gamma * decision_tag_coverage`).

---

## ADR-004: Lựa chọn Mô hình Embedding Cục bộ (`qwen3-embedding:0.6b` qua Ollama + Deterministic Hash Provider)

- **Trạng thái:** **Provisional** cho `qwen3-embedding:0.6b` (đánh giá qua `E1`/`E2`); **Confirmed** cho kiến trúc đa provider (`ollama` + `hashing`).
- **Bối cảnh (Context):**
  - Hệ thống cần chạy hoàn toàn trên máy local trong môi trường thi đấu AI, không gọi API trả phí bên ngoài (OpenAI/Cohere), nhưng đồng thời bộ kiểm thử contract (`make test-selection`, `make verify`) phải chạy tức thời trong môi trường sandbox/CI kể cả khi dịch vụ Ollama chưa bật.
- **Quyết định (Decision):**
  - Thiết kế `EmbeddingProvider` (`agent4/metric_selection/embedding.py`) hỗ trợ cấu hình qua `EmbeddingConfig`:
    1. **Production / Benchmark Mode (`provider="ollama"`, `model_id="qwen3-embedding:0.6b"`)**: Gọi endpoint `/api/embed` của Ollama local, chuẩn hóa vector L2 (`normalize=True`), lưu rõ `model_id`, `model_version`, `dimension`.
    2. **Offline Contract / Unit Test Mode (`provider="hashing"`, `model_id="multilingual-embedding-v1"`)**: Tạo vector tất định từ mã băm văn bản và từ khóa để chạy 18 contract tests hoàn toàn offline trong `< 50ms`.
  - Khi provider bị ngắt kết nối hoặc timeout (`available=False` hoặc `httpx.HTTPError`), bắt buộc ném `ContractError(code="retrieval_unavailable", final_status="temporarily_unavailable", retryable=True)`, tuyệt đối không trả về `unsupported`.

---

## ADR-005: Lưu trữ Vector bằng NumPy (`.npz`) vs Cơ sở Dữ liệu Vector Bên ngoài

- **Trạng thái:** **Confirmed**.
- **Bối cảnh (Context):**
  - Số lượng chỉ tiêu tài chính trong catalog là $N = 15$ (v1) đến $N = 66$ (v2 canonical), ngay cả khi mở rộng trong tương lai cũng chỉ ở quy mô vài trăm metrics ($N < 500$).
- **Quyết định (Decision):**
  - Sử dụng **NumPy `.npz` (`agent4/metric_selection/index.py`)** kết hợp metadata JSON để lưu trữ chỉ mục vector tại `.cache/metric_selection_index.npz`.
  - Không đưa vào FAISS, Qdrant, Milvus, ChromaDB hay pgvector.
- **Lý do & Đánh đổi:**
  - Với ma trận $66 \times 1024$ (`float32`), dung lượng bộ nhớ chỉ là **~270 KB**, thời gian tính tích vô hướng chính xác 100% (`exact brute-force cosine similarity`) bằng NumPy mất **< 0.05 ms**, không có sai số xấp xỉ ANN (Approximate Nearest Neighbor), không tốn tài nguyên chạy background daemon, và kiểm tra tính toàn vẹn (`catalog_hash`) cực kỳ đơn giản.

---

## ADR-006: Quản trị Hai Không gian Tên Catalog (`DEFAULT_METRICS_DEFINITIONS` v1 vs `REGISTRY` v2)

- **Trạng thái:** **Confirmed**.
- **Bối cảnh (Context):**
  - Kiểm toán repository phát hiện `agent4/core/catalog.py` (`DEFAULT_METRICS_DEFINITIONS`, 15 metrics) sử dụng định danh của bộ contract test v1 (`gross_margin`, `net_profit_margin`, `operating_expense`, `cash_balance`, `loan_balance`...), trong khi `agent4/engine/metrics.py` (`REGISTRY`, 66 metrics) và bộ benchmark 140 câu `contract_benchmark_questions.jsonl` (`vals/run_eval.py`) sử dụng định danh canonical v2 (`gross_margin_pct`, `net_margin_pct`, `operating_expenses`, `cash_and_equivalents`, `debt_balance`...).
- **Quyết định (Decision):**
  - Xây dựng `agent4/metric_selection/catalog_adapter.py` cung cấp hàm `build_canonical_catalog() -> MetricCatalog` chuyển đổi toàn bộ 66 `MetricDef` trong `agent4/engine/metrics.py` sang đúng cấu trúc dictionary của `MetricCatalog` (`metric.catalog.v1`).
  - Mọi thành phần trong `agent4/metric_selection/` chỉ làm việc với giao diện `MetricCatalog`:
    - Trong `pytest` contract suite (`test_retrieval_and_fewshot.py`, `test_selection_and_metric_validation.py`): truyền `MetricCatalog()` mặc định (15 metrics v1).
    - Trong `vals/run_eval.py` (`eval_adapter.py`) và runtime chính: truyền `build_canonical_catalog()` (66 metrics v2).
  - Cách tiếp cận này bảo toàn 100% các bài test hiện có của M0 và M1 mà không vi phạm quy tắc chống gộp ngầm hai namespace của `docs/evaluation.md`.
