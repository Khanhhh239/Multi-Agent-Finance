# Kế hoạch kiểm thử ViLegalBERT trong kiến trúc Agent 3

## 1. Mục tiêu

Xây dựng project thử nghiệm để đánh giá `ntphuc149/ViLegalBERT` trước khi quyết định có đưa model vào **Agent 3 – Tax Compliance Engine** hay không.

Câu hỏi kiến trúc chính:

> ViLegalBERT có cải thiện việc tìm và xếp hạng văn bản pháp luật thuế tiếng Việt đủ nhiều để đáng thêm vào tầng RAG không?

Kết quả phải cho biết:

1. Model/tokenizer có load và inference ổn định trên máy hiện tại không?
2. Latency, RAM/VRAM, context length và kích thước model thực tế là bao nhiêu?
3. ViLegalBERT có cải thiện legal retrieval/reranking so với baseline của Agent 3 không?
4. Mức tăng chất lượng có bù được chi phí vận hành không?

ViLegalBERT là encoder-only model. Không dùng model như chatbot và không dùng để tự kết luận nghĩa vụ thuế.

## 2. Vị trí trong kiến trúc

```text
Hóa đơn / diễn giải / ảnh
          ↓
OCR + LLM/PhoBERT Extraction
          ↓
Canonical Transaction JSON + confidence
          ├── thiếu trường / confidence thấp → REVIEW
          ↓
GoRules ZEN Tax Rule Engine
          ↓ verdict + rule_id + version + legal_ref
BM25 + BGE-M3 retrieval, có lọc ngày hiệu lực
          ↓
ViLegalBERT reranker (ứng viên cần benchmark)
          ↓
LLM Explainer + Citation Verifier
          ↓
Two-View Filter + Audit Log + FastAPI
```

| Thành phần | Nhiệm vụ | Không được làm |
|---|---|---|
| PhoBERT/LLM | Trích xuất thuộc tính giao dịch | Tự phát hành verdict |
| GoRules ZEN | Áp dụng rule có phiên bản, trả PASS/FAIL/REVIEW | Suy diễn từ văn bản mơ hồ |
| BM25 + BGE-M3 | Lấy các đoạn luật ứng viên | Tự tạo giải thích |
| ViLegalBERT | Xếp hạng lại đoạn luật theo query pháp lý | Thay Rule Engine |
| LLM Explainer | Diễn giải rule hit từ nguồn đã truy hồi | Thay đổi verdict hoặc căn cứ |
| Citation Verifier | Kiểm tra đoạn trích tồn tại trong nguồn | Chứng minh toàn bộ lập luận đúng |

ViLegalBERT không nhận ảnh hóa đơn. Nó cũng không phải lựa chọn mặc định cho `expense_category`, `payment_method` hay NER trên diễn giải kế toán; các tác vụ đó thuộc benchmark extraction/PhoBERT riêng.

## 3. Phạm vi

### A. Khả năng chạy

- Model/tokenizer compatibility và smoke test.
- Truncation, NaN/Inf, latency và memory.
- Fill-mask chỉ là diagnostic nếu checkpoint có MLM head hợp lệ.

### B. Giá trị trong Agent 3

- Xây tập query thuế–đoạn luật có ground truth.
- Đo BM25, BGE-M3 và hybrid retrieval.
- Rerank top-k bằng ViLegalBERT.
- So Recall@k, MRR, nDCG, độ đúng hiệu lực và latency.
- Tùy chọn fine-tune trên cặp `query, legal_chunk, relevance`.

Legal True/False hoặc visualization chỉ là kiểm tra phụ, không quyết định tích hợp.

## 4. Thông tin model cần xác minh

```text
Model: ntphuc149/ViLegalBERT
Tokenizer dự kiến: vinai/phobert-base-v2
```

Đọc trực tiếp từ model/tokenizer thay vì hard-code:

```text
architecture, model_type, num_parameters, hidden_size,
num_hidden_layers, num_attention_heads, max_position_embeddings,
model_max_length, vocab_size, tokenizer class, special token IDs,
dtype và model revision
```

Compatibility check bắt buộc:

- vocabulary size phù hợp embedding matrix;
- special tokens hợp lệ;
- câu đã word-segment forward pass được;
- ghi mọi missing/unexpected weights;
- xác định input length dùng được sau special tokens.

Nếu tokenizer yêu cầu word segmentation, dùng cùng pipeline cho các model so sánh có cùng tokenizer và ghi rõ công cụ/phiên bản.

## 5. Cấu trúc project

Không sửa pipeline production trong benchmark đầu tiên:

```text
vilegalbert_test/
├── README.md
├── requirements.txt
├── config.yaml
├── run_all.py
├── src/
│   ├── load_model.py
│   ├── preprocess.py
│   ├── smoke_test.py
│   ├── performance_test.py
│   ├── fill_mask_test.py
│   ├── build_eval_dataset.py
│   ├── retrieval_baselines.py
│   ├── vilegalbert_reranker.py
│   ├── evaluate_retrieval.py
│   └── finetune_reranker.py
├── data/
│   ├── smoke_sentences.json
│   ├── legal_chunks.jsonl
│   ├── retrieval_queries.jsonl
│   └── README.md
├── results/
│   ├── environment.json
│   ├── model_info.json
│   ├── smoke_test.json
│   ├── performance.csv
│   ├── retrieval_metrics.csv
│   ├── per_query_results.jsonl
│   └── decision_report.md
└── tests/
    ├── test_preprocess.py
    ├── test_metrics.py
    └── test_dataset_schema.py
```

Dependencies tối thiểu: `torch`, `transformers`, `accelerate`, `numpy`, `pandas`, `scikit-learn`, `psutil`, `pyyaml`, `rank-bm25`, `sentence-transformers` và một thư viện word segmentation thực sự được sử dụng.

Không hard-code Hugging Face token. Nếu cần xác thực, hướng dẫn `hf auth login`. Không tự đổi checkpoint nếu model lỗi.

# PHASE 1 — COMPATIBILITY VÀ SMOKE TEST

## 6. Load và kiểm tra

Dùng `AutoTokenizer` và `AutoModel`, cấu hình qua YAML. Chạy CUDA nếu có, nếu không dùng CPU.

```python
model.eval()
with torch.inference_mode():
    outputs = model(**inputs)
```

Ghi `model_info.json`, gồm metadata thực tế, parameter count, device, dtype, revision và cảnh báo load.

Smoke test ít nhất 16 mẫu:

- 4 diễn giải giao dịch kế toán;
- 4 đoạn luật thuế;
- 4 query tìm căn cứ pháp lý;
- 4 đoạn tăng dần độ dài, gồm một đoạn vượt context.

Ví dụ:

```text
Chi tiền mặt mua máy tính trị giá 25 triệu đồng, có hóa đơn.
Khoản chi mua hàng hóa có hóa đơn từ hai mươi triệu đồng trở lên phải có chứng từ thanh toán không dùng tiền mặt.
Điều kiện để chi phí mua hàng trị giá trên 20 triệu được trừ là gì?
```

Ghi token count trước/sau truncation, output shape, NaN/Inf và latency. Không suy ra độ đúng pháp lý từ smoke test.

Fill-mask chỉ chạy nếu `AutoModelForMaskedLM` load đúng mà không gắn random head. Nó không phải tiêu chí tích hợp.

# PHASE 2 — PERFORMANCE

Benchmark sequence length `32, 64, 128, 256` và batch size `1, 4, 8, 16`, trong giới hạn thật của model.

Mỗi cấu hình:

1. Warm-up ít nhất 5 lần.
2. Chạy ít nhất 30 lần.
3. GPU synchronize trước/sau timing.
4. Ghi mean, median, p95, throughput, peak memory.
5. Nếu OOM, ghi trạng thái rồi tiếp tục.

Đo thêm use case reranking thật:

```text
1 query × 10 legal chunks
1 query × 20 legal chunks
1 query × 50 legal chunks
```

# PHASE 3 — DATASET AGENT 3

## 7. Schema

Mỗi query:

```json
{
  "query_id": "Q-CASH-001",
  "query": "Hóa đơn 25 triệu thanh toán tiền mặt có được tính chi phí được trừ không?",
  "transaction_context": {
    "amount": 25000000,
    "payment_method": "cash",
    "has_docs": true
  },
  "rule_id": "R-CASH-20M",
  "document_date": "2026-07-19",
  "relevant_chunk_ids": ["TT96-D4-K1"],
  "hard_negative_chunk_ids": ["TT96-D4-K2"],
  "label_source": "tax_expert_verified"
}
```

Mỗi chunk:

```json
{
  "chunk_id": "TT96-D4-K1",
  "document_id": "TT96_2015",
  "citation": "Khoản 1 Điều 4 Thông tư 96/2015/TT-BTC",
  "content": "...",
  "effective_from": "2015-08-06",
  "effective_to": null
}
```

Ưu tiên corpus hiện có trong `agent3_tax_compliance/data/corpus/`, nhưng phải kiểm tra nguồn, nội dung và ngày hiệu lực trước khi coi là ground truth.

Tập ban đầu cần tối thiểu 100 query, phủ đủ 12 rule, có viết tắt/không dấu/câu mơ hồ và hard negative gần nghĩa. Nhãn cần người có chuyên môn duyệt. Citation trong rule JSON chỉ là nhãn ứng viên, không mặc nhiên là ground truth.

Nếu fine-tune, chia `70/15/15` theo rule, văn bản hoặc template để tránh rò rỉ. Giữ test set expert-verified đóng băng.

# PHASE 4 — RETRIEVAL/RERANKING

## 8. Cấu hình bắt buộc

Chạy cùng corpus, query set, date filter và top-k:

1. BM25.
2. BGE-M3 dense.
3. BM25 + BGE-M3 + RRF — baseline mục tiêu trong `PLAN.md`.
4. Hybrid top-k + ViLegalBERT reranker.

Nếu code hiện tại chỉ có FTS5/BM25, gọi đúng là **prototype baseline**, không gọi là hybrid.

## 9. Cách rerank

Không mặc định xem cosine từ raw mean-pooling là giải pháp production. Thử theo thứ tự:

1. Zero-shot representation scoring để diagnostic.
2. Fine-tune pair classifier trên `query + legal_chunk` với relevance label.
3. Chỉ rerank top-k từ retriever; không quét toàn corpus bằng cross-encoder.

Log truncation. Chunk theo Điều/Khoản và giữ metadata thay vì cắt tùy tiện.

Metrics bắt buộc:

```text
Recall@1, @3, @5, @10
MRR@10
nDCG@10
zero-result rate
date-valid retrieval rate
mean và p95 latency end-to-end
```

`date-valid retrieval rate` đo tỷ lệ kết quả có hiệu lực tại `document_date`. Versioning phải do metadata filter xử lý; ViLegalBERT không tự biết luật đang hiệu lực.

Báo metric tổng và theo `rule_id`.

## 10. Ablation

So sánh:

- query chỉ có `legal_ref`;
- mô tả giao dịch thô;
- `rule_id + legal_ref + fix_hint`;
- có/không word segmentation;
- top-k rerank 10, 20, 50.

Trong luồng thật sau ZEN, query ưu tiên dựa trên `rule_id/legal_ref`, không dựa hoàn toàn vào mô tả hóa đơn.

# PHASE 5 — OPTIONAL FINE-TUNING

Task ưu tiên:

```text
Input: query [SEP] legal_chunk
Label: relevant / not_relevant
```

Negative gồm random negative, BM25 hard negative, đoạn cùng thông tư nhưng sai Điều/Khoản, và văn bản đúng chủ đề nhưng hết hiệu lực.

Baseline: seed 42, 2–3 epochs, learning rate `2e-5`, weight decay `0.01`, max length theo giới hạn thật. Báo Macro-F1/PR-AUC cho pair classification, nhưng quyết định dựa chủ yếu vào retrieval metrics sau reranking.

ViLegalTF/Legal True-False chỉ là sanity check phụ.

# PHASE 6 — SO SÁNH VÀ QUYẾT ĐỊNH

Nếu có tài nguyên, so với PhoBERT-base-v2 trong cùng reranking pipeline: cùng split, seed, epoch, preprocessing phù hợp tokenizer, candidate set và device. Đây là baseline reranker, không phải PhoBERT extraction classifier.

Đề xuất tích hợp khi đồng thời:

1. MRR/nDCG/Recall tăng ổn định trên test expert-verified.
2. Không giảm `date-valid retrieval rate`.
3. p95 latency và memory nằm trong ngân sách.
4. Lợi ích xuất hiện ở nhiều rule.
5. Pipeline chạy offline và tái lập được.

Nếu chất lượng tương đương hybrid baseline nhưng latency tăng đáng kể, kết luận là không tích hợp hoặc chỉ dùng cho review ngoại tuyến.

## 11. Output và acceptance criteria

`retrieval_metrics.csv`:

```text
system, recall_at_1, recall_at_3, recall_at_5, recall_at_10,
mrr_at_10, ndcg_at_10, date_valid_rate,
mean_latency_ms, p95_latency_ms, peak_memory_mb
```

`decision_report.md` phải trả lời: khả năng load; compatibility; context length; latency/memory; metric baseline; mức thay đổi do reranker; rule tốt/xấu; truncation; chi phí; và đề xuất tích hợp/thử thêm/offline/loại.

Task hoàn thành khi:

- [ ] Có compatibility, smoke và performance report.
- [ ] Có dataset schema validation.
- [ ] Có ít nhất 100 query phủ 12 rule, hoặc ghi rõ chưa đủ dữ liệu kết luận.
- [ ] Có BM25 và hybrid baseline đúng với thành phần thực sự chạy.
- [ ] Có retrieval metrics và date filter.
- [ ] Có per-query output để audit.
- [ ] Không dùng ViLegalBERT phát hành verdict.
- [ ] Không fabricate hoặc chép metric paper thành kết quả local.
- [ ] Có quyết định dựa trên chất lượng và chi phí.

## 12. Error handling và reproducibility

Xử lý rõ: mất mạng, Hugging Face access fail, tokenizer/model mismatch, CUDA OOM, package/corpus/index thiếu và truncation. Không silent fail hoặc tự thay model.

Set seed cho `random`, `numpy`, `torch`, `torch.cuda`. Ghi OS, Python, package versions, CUDA, device, model revision, dataset hash và config vào `environment.json`.

## 13. Lệnh chạy mong muốn

```bash
python -m src.smoke_test
python -m src.performance_test
python -m src.build_eval_dataset --validate-only
python -m src.retrieval_baselines
python -m src.evaluate_retrieval --system hybrid
python -m src.evaluate_retrieval --system hybrid_vilegalbert
```

Tùy chọn:

```bash
python -m src.finetune_reranker
python -m src.evaluate_retrieval --system hybrid_vilegalbert_finetuned
python run_all.py
```

## 14. Không được làm

- Gọi ViLegalBERT là generative LLM.
- Dùng model thay GoRules ZEN hoặc quyết định PASS/FAIL/REVIEW.
- Dùng model thay PhoBERT extraction mà chưa benchmark dữ liệu giao dịch.
- Đưa ảnh hóa đơn trực tiếp vào model.
- Coi fill-mask, PCA/t-SNE hoặc cosine vài câu là bằng chứng retrieval tốt.
- Đánh giá retrieval không có ground truth.
- Bỏ qua hiệu lực văn bản.
- Để query/template gần trùng rò rỉ sang test.
- So model với candidate set, preprocessing hoặc device không tương đương.
- Chọn model chỉ dựa vào Legal True/False accuracy.

## 15. Nguồn tham khảo

```text
Model: https://huggingface.co/ntphuc149/ViLegalBERT
Project: https://github.com/ntphuc149/ViLegalLM
PhoBERT: https://huggingface.co/vinai/phobert-base-v2
```

Ưu tiên model card và source chính thức. Mọi thông số chưa xác minh phải được đọc lại bằng code khi benchmark.
