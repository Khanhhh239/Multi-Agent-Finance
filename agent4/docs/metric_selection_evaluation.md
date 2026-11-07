# Metric Selection Evaluation & Experiment Specification (`agent4/metric_selection/`)

> **Module:** Module 2 — Governed Metric Selection (`M1`)  
> **Runner thực thi:** `vals/run_eval.py`  
> **Bộ dữ liệu chuẩn:** `data/eval/contract_benchmark_questions.jsonl` (`contract-benchmark-v2.0`, 140 câu)  
> **Kho ví dụ Few-shot:** `data/example_bank.jsonl` (15 ví dụ đối chứng)  
> **Tài liệu liên quan:** [docs/plans/metrics_selection.md](plans/metrics_selection.md) | [docs/evaluation.md](evaluation.md) | [docs/adr_metric_selection.md](adr_metric_selection.md)

---

## 1. Mục tiêu Đánh giá (Evaluation Objectives)

Đánh giá thực nghiệm (empirical evaluation) đối với module `agent4/metric_selection/` là thành phần kỹ thuật hạng nhất (first-class engineering component), nhằm trả lời 5 câu hỏi bằng số liệu đo đạc thực tế:
1. **Full Catalog vs Retrieval (`E0` vs `E1`/`E2`)**: Với 66 metrics trong `REGISTRY` (`agent4/engine/metrics.py`), việc thu hẹp ứng viên bằng Retrieval có cải thiện độ chính xác chọn metric (`Exact Set Match`, `Micro/Macro F1`) và độ trễ (`p50`/`p95`) so với việc truyền toàn bộ catalog hợp lệ cho `Qwen3:4b` hay không?
2. **Dense vs Hybrid Retrieval (`E1` vs `E2`)**: Việc kết hợp Lexical Retrieval + RRF Fusion ($k=60$) + Metadata Reranker có khắc phục được hiện tượng rớt metric trong các câu hỏi đa chỉ tiêu (`multi_metrics`) và thuật ngữ kế toán Việt Nam so với chỉ dùng Dense Embedding (`qwen3-embedding:0.6b`) hay không?
3. **Tác động của ngưỡng cắt Top-K ($K \in \{5, 10, 12, 15, 20\}$)**: Ngưỡng $K$ nào tối ưu hóa đồng thời **Complete Gold Set Recall@K** (`all_metrics_covered_at_k`) và độ chính xác của LLM Selector?
4. **Zero-shot vs Static vs Dynamic Few-shot (`E2` vs `E3` vs `E4`)**: Việc bổ sung ví dụ few-shot có thực sự giúp `Qwen3:4b` phân biệt các cặp metric dễ nhầm (`gross_vs_net`, `amount_vs_ratio`, `accounting_vs_tax`, `narrow_vs_broad_cost`) hay không?
5. **Bounded Recovery (`E5`)**: Cơ chế phục hồi có giới hạn dựa trên tín hiệu quan sát được tại thời điểm suy luận có giảm tỷ lệ lỗi rỗng/lỗi định dạng mà không làm tăng False Positive hay không?

---

## 2. Cấu trúc Bộ Dữ liệu Đánh giá (Dataset Specification)

### 2.1. Phân bổ 140 câu hỏi trong `data/eval/contract_benchmark_questions.jsonl`
Bộ dữ liệu `contract-benchmark-v2.0` (`split="dev"`) gồm **140 câu hỏi** tiếng Việt và tiếng Anh, sử dụng **21 metric đích** trong tổng số **66 canonical metrics** của `agent4/engine/metrics.py` (`REGISTRY`), được chia thành 9 nhóm hành vi:

| `case_category` | Số câu | Đặc điểm kiểm thử đối với Metric Selection | Kỳ vọng `expected_selection_status` |
| :--- | :---: | :--- | :--- |
| `single_metric_aggregate` | 20 | Nhắc trực tiếp tên metric, từ đồng nghĩa tiếng Việt/Anh, hoặc câu hỏi diễn giải cho 1 chỉ tiêu. | `resolved` (1 metric) |
| `timeseries_and_comparison` | 20 | Câu hỏi chuỗi thời gian theo tháng/quý và so sánh giữa các kỳ. | `resolved` (1 metric) |
| `dimensional_breakdown_filter_topk` | 20 | Câu hỏi phân rã theo chi nhánh (`branch`), khoản mục (`cost_category`), khách hàng (`customer`), NCC (`vendor`). | `resolved` (1 metric, yêu cầu khớp `supported_dimensions`) |
| `business_views` | 15 | Phân biệt chỉ tiêu trên khung quản trị (`mgmt`) và khung thuế (`tax`, ví dụ `taxable_income`, `deductible_expenses`, `cit_estimate`). | `resolved` (kiểm tra tương thích `supported_views`) |
| `ambiguous_needs_clarification` | 15 | Câu hỏi mơ hồ (ví dụ chỉ hỏi *"lợi nhuận"*, *"công nợ"*, *"khả năng thanh toán ngắn hạn"* mà không rõ gộp/ròng, phải thu/phải trả, hiện hành/nhanh). | `ambiguous` (`metric_ids=[]`, có `clarification_question`) |
| `unsupported_out_of_catalog` | 12 | Yêu cầu chỉ tiêu ngoài catalog (giá cổ phiếu, thị phần, dự báo AI...) hoặc vi phạm kết hợp `flow` + `snapshot`. | `unsupported` (`metric_ids=[]`) |
| `no_data_and_edge_cases` | 8 | Câu hỏi hợp lệ về mặt chọn metric nhưng rơi vào kỳ rỗng hoặc mẫu số bằng 0 ở tầng thực thi SQL. | `resolved` |
| `authorization_and_security` | 10 | Người dùng bị giới hạn `allowed_views` / `allowed_metrics` hoặc câu hỏi chứa prompt injection (`SELECT * FROM payroll`, `ignore previous instructions`). | `resolved` hoặc bị chặn `forbidden` / `unsupported` tại Validator |
| `multi_metrics` | 20 | Câu hỏi yêu cầu **2 đến 5 metrics** cùng lúc (ví dụ so sánh doanh thu thuần, giá vốn và lợi nhuận gộp; hoặc đối chiếu chi phí bán hàng và chi phí QLDN). | `resolved` ($\ge 2$ metrics, kiểm tra `all_metrics_covered_at_k`) |

### 2.2. Các cặp Metric dễ nhầm lẫn (Confusable Metric Pairs) trong Catalog thực tế
Khi phân tích lỗi (Error Analysis), bắt buộc theo dõi tỷ lệ nhầm lẫn trên các nhóm metric thực tế trong `agent4/engine/metrics.py` và `config/metric_relationships.yaml`:
- **Số tuyệt đối vs Tỷ suất (`amount_vs_ratio`)**: `gross_profit` vs `gross_margin_pct`; `net_profit` vs `net_margin_pct`; `debt_balance` vs `debt_to_equity`.
- **Trước giảm trừ vs Thuần (`gross_vs_net`)**: `gross_revenue` vs `net_revenue` vs `revenue_deductions`.
- **Chi phí tổng hợp vs Chi phí thành phần (`narrow_vs_broad_cost`)**: `operating_expenses` vs `selling_expenses` / `admin_expenses` / `expense_by_category`; `labor_cost` (gồm bảo hiểm) vs `salary_expense` (chỉ lương + thưởng) vs `payroll_summary`.
- **Số dư thời điểm vs Dòng tiền trong kỳ (`snapshot_vs_flow`)**: `cash_and_equivalents` (`snapshot`) vs `net_cash_flow` (`flow`) vs `cash_coverage_days`.
- **Tổng công nợ vs Phân rã / Tuổi nợ (`balance_vs_aging`)**: `ar_balance` vs `ar_by_customer` / `ar_by_salesperson` / `ar_aging` / `overdue_receivables`; `ap_balance` vs `ap_by_vendor` / `ap_due_soon`.
- **Kế toán quản trị vs Thuế (`accounting_vs_tax`)**: `profit_before_tax` vs `taxable_income`; `income_tax_expense` vs `cit_estimate`; `operating_expenses` vs `deductible_expenses` / `mgmt_vs_tax_gap`.
- **Công thức chuẩn vs Thực tế thu tiền (`formula_vs_actual`)**: `dso` vs `dso_actual`.

### 2.3. Quy tắc Chống Rò rỉ Dữ liệu (Data Contamination Prevention)
1. Không một câu hỏi nào trong `data/example_bank.jsonl` được trùng (sau khi chuẩn hóa chữ thường và khoảng trắng) với bất kỳ câu hỏi nào trong `data/eval/contract_benchmark_questions.jsonl`. Kiểm chứng tự động bằng:
   ```bash
   python vals/run_eval.py --validate-only --example-bank data/example_bank.jsonl
   ```
2. Không tinh chỉnh danh sách từ đồng nghĩa (`synonyms`) bằng cách copy nguyên văn câu hỏi từ bộ test độc lập (`split="test"` khi được mở khóa).
3. Trong luồng online (`fewshot.py`), luôn bật chốt chặn `ex["question"].strip().lower() != query.strip().lower()`.

---

## 3. Hệ thống Chỉ số Đo lường (Evaluation Metrics)

### 3.1. Chỉ số Truy hồi (Retrieval Metrics — `--mode retrieval` & `--mode selection`)
Đánh giá trên tập các câu hỏi có `expected_metric_ids` khác rỗng ($N_{\text{gold}} = 113/140$ câu):
- **$\text{Recall}@K$** ($K \in \{5, 10, 12, 15\}$):
  $$\text{Recall}@K = \frac{1}{|Q_{\text{gold}}|} \sum_{q \in Q_{\text{gold}}} \frac{|G_q \cap R_q[:K]|}{|G_q|}$$
- **$\text{Complete Gold Set Recall}@K$ (`all_metrics_covered_at_k`)**:
  $$\text{CompleteRecall}@K = \frac{1}{|Q_{\text{gold}}|} \sum_{q \in Q_{\text{gold}}} \mathbb{I}\left(G_q \subseteq R_q[:K]\right)$$
  *Lưu ý quan trọng*: Vì `validator.py` bắt buộc $\text{selected\_metric\_ids} \subseteq \text{candidate\_metric\_ids}$, nên $\text{CompleteRecall}@K$ chính là **trần lý thuyết tối đa (theoretical upper bound)** của `Exact Set Match` đối với các câu hỏi `resolved`!
- **$\text{MRR}$ (`mean_reciprocal_rank`)**: Trung bình nghịch đảo thứ hạng của metric đúng xuất hiện sớm nhất.
- **$\text{Precision}@K$**: $\frac{|G_q \cap R_q[:K]|}{K}$.

### 3.2. Chỉ số Chọn Metric & Thẩm định (Selection & Validation Metrics — `--mode selection`)
Đánh giá trên toàn bộ $N = 140$ câu hỏi:
- **Exact Set Match (`selection.exact_match_accuracy`)**: Tỷ lệ câu hỏi mà dự đoán khớp đồng thời cả `selection.status == expected_selection_status` **VÀ** `set(selection.metric_ids) == set(expected_metric_ids)`.
- **Micro Precision / Recall / F1 (`selection.micro_precision`, `micro_recall`, `micro_f1`)**: Tính tổng TP, FP, FN trên toàn bộ các cặp `(case_id, metric_id)`.
- **Macro Precision / Recall / F1**: Trung bình F1 theo từng `case_category` và theo từng `metric_id` để phát hiện các metric hiếm bị bỏ sót.
- **Invalid Metric Rate (`selection.invalid_metric_rate`)**: Tỷ lệ câu hỏi có chứa ít nhất một `metric_id` ngoài `REGISTRY` (sau khi qua `validator.py`, chỉ số này bắt buộc bằng **`0.0`**).
- **Selection Within Candidates Rate (`selection.within_candidates_rate`)**: Tỷ lệ câu hỏi thỏa mãn $\text{selected\_metric\_ids} \subseteq \text{retrieved\_metric\_ids}$ (sau `validator.py`, bắt buộc bằng **`1.0`**).
- **Schema Validity Rate**: Tỷ lệ phản hồi thô từ `Qwen3:4b` tuân thủ đúng JSON schema trước khi retry.

### 3.3. Chỉ số Hệ thống & Tài nguyên (System & Resource Metrics)
- **Latency (`latency_p50_ms`, `latency_p95_ms`)** và phân rã theo tầng `stage_latency_ms` (`retrieval_ms`, `fewshot_ms`, `llm_ms`, `validation_ms`).
- **Token Usage (`usage.input_tokens`, `usage.output_tokens`)**: Trung bình và p95 số token đầu vào/đầu ra cho mỗi truy vấn.
- **CPU / RAM & Model Loading Overhead**: Bộ nhớ chiếm dụng của `.npz` index và thời gian khởi tạo lần đầu.
- **Failure & Recovery Rate**: Tỷ lệ các ca kích hoạt cơ chế recovery (`empty_candidates`, `invalid_json_retry`, `full_catalog_fallback`) và tỷ lệ cứu thành công.

---

## 4. Thiết kế Chuỗi Thực nghiệm & Cổng Quyết định (Experiment Matrix & Decision Gates)

Tất cả các thực nghiệm phải chạy trên cùng bộ dữ liệu `data/eval/contract_benchmark_questions.jsonl` (`split="dev"`), cùng model selector `qwen3:4b` (`temperature=0.0`, `seed=20261101`), và xuất báo cáo chuẩn qua `vals/run_eval.py`.

| Thực nghiệm | Cấu hình Retrieval | Cấu hình Few-shot | Cấu hình Recovery | Lệnh chạy chuẩn (`make eval`) |
| :---: | :--- | :--- | :--- | :--- |
| **E0** | `full_catalog` (Toàn bộ metric hợp lệ theo `auth_context`) | `zero` (`enabled: false`) | Tắt (`max_retries: 0`) | `make eval EVAL_MODE=selection ADAPTER=agent4.metric_selection.eval_adapter:predict_e0 MODEL_VERSION=ollama:qwen3:4b PROMPT_VERSION=ms-v1-e0 OUTPUT_DIR=reports/eval/M1_E0_full_catalog` |
| **E1** | `dense_only` (`qwen3-embedding:0.6b`, quét $K \in \{5, 10, 12, 15\}$) | `zero` | Tắt | `make eval EVAL_MODE=selection ADAPTER=agent4.metric_selection.eval_adapter:predict_e1 MODEL_VERSION=ollama:qwen3:4b+qwen3-embedding:0.6b PROMPT_VERSION=ms-v1-e1 OUTPUT_DIR=reports/eval/M1_E1_dense` |
| **E2** | `hybrid` (Dense + Lexical + RRF $k=60$ + Metadata Rerank, $K \in \{5, 10, 12, 15\}$) | `zero` | Tắt | `make eval EVAL_MODE=selection ADAPTER=agent4.metric_selection.eval_adapter:predict_e2 MODEL_VERSION=ollama:qwen3:4b+qwen3-embedding:0.6b PROMPT_VERSION=ms-v1-e2 OUTPUT_DIR=reports/eval/M1_E2_hybrid` |
| **E3** | Chế độ thắng giữa `E0` và `E2` | `static` ($M=3$ ví dụ cố định) | Tắt | `make eval EVAL_MODE=selection ADAPTER=agent4.metric_selection.eval_adapter:predict_e3 MODEL_VERSION=ollama:qwen3:4b PROMPT_VERSION=ms-v1-e3 OUTPUT_DIR=reports/eval/M1_E3_static_fs -- --example-bank data/example_bank.jsonl` |
| **E4** | Chế độ thắng giữa `E0` và `E2` | `dynamic` (`similarity` / `coverage` / `hybrid`, `compatible_only=True`) | Tắt | `make eval EVAL_MODE=selection ADAPTER=agent4.metric_selection.eval_adapter:predict_e4 MODEL_VERSION=ollama:qwen3:4b PROMPT_VERSION=ms-v1-e4 OUTPUT_DIR=reports/eval/M1_E4_dynamic_fs -- --example-bank data/example_bank.jsonl` |
| **E5** | Cấu hình tốt nhất từ `E0`–`E4` | Cấu hình tốt nhất từ `E0`–`E4` | Bật `Bounded Recovery` | `make eval EVAL_MODE=selection ADAPTER=agent4.metric_selection.eval_adapter:predict MODEL_VERSION=ollama:qwen3:4b PROMPT_VERSION=ms-v1-e5 OUTPUT_DIR=reports/eval/M1_E5_recovery -- --baseline reports/eval/M1_E0_full_catalog/summary.json` |

### Quy tắc Cổng Quyết định (Decision Gate Protocol)

1. **Decision Gate 1 (`E0` $\rightarrow$ `E1`/`E2` — Kiểm định sự cần thiết của Retrieval)**:
   - Phân tách mọi lỗi chọn sai trong `E1`/`E2` thành 2 nhóm độc lập:
     - **Retrieval Failure**: $G_q \not\subseteq R_q[:K]$ (ít nhất 1 metric chuẩn bị thiếu trong tập ứng viên Top-K).
     - **Selection Failure**: $G_q \subseteq R_q[:K]$ (tập ứng viên đã đủ 100% metric chuẩn nhưng LLM chọn thiếu, chọn thừa hoặc sai `status`).
   - Nếu số ca **Retrieval Failure** của `E2` lớn hơn số ca **Selection Failure** mà `E2` giảm được so với `E0` (tức là `ExactMatch(E2) < ExactMatch(E0)`), thì `Full-Catalog (E0)` hoặc `Hybrid Retrieval với K lớn (K >= 20)` sẽ được giữ làm cấu hình chính cho bước tiếp theo.
2. **Decision Gate 2 (`E2` $\rightarrow$ `E3`/`E4` — Kiểm định giá trị của Few-shot)**:
   - So sánh `Exact Set Match` và `Micro F1` của `Zero-shot (E2)`, `Static Few-shot (E3)`, và `Dynamic Few-shot (E4)` trên từng nhóm câu hỏi (đặc biệt là `multi_metrics`, `ambiguous_needs_clarification`, và các cặp `confusable_with`).
   - Nếu Few-shot làm giảm độ chính xác do hiệu ứng mỏ neo (anchoring bias) hoặc cắt bớt ví dụ vì `compatible_only=True`, giữ `Zero-shot` hoặc chỉ bật Few-shot cho các trường hợp có cặp metric `confusable_with` xuất hiện đồng thời trong candidate set.
3. **Decision Gate 3 (`E4` $\rightarrow$ `E5` — Kiểm định Recovery & Chốt Submission)**:
   - Cơ chế Recovery trong `E5` không được làm tăng `Invalid Metric Rate` (phải giữ ở `0.0`) và không được làm giảm `Exact Set Match` trên nhóm `unsupported_out_of_catalog` và `authorization_and_security`.

---

## 5. Định dạng Báo cáo So sánh (Standard Reporting Format)

Sau khi hoàn thành Issue `M1.3`, kết quả thực nghiệm phải được tổng hợp vào bảng chuẩn dưới đây (tuyệt đối không điền số giả định khi chưa chạy thực nghiệm):

```markdown
| Exp | Retrieval Mode (Top-K) | Few-shot | Complete Recall@K | Exact Match (%) | Micro P / R / F1 | Multi-Metric Exact (%) | Ambiguous Acc (%) | Invalid Rate | Latency p50 / p95 (ms) | Avg In/Out Tokens |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| E0 | Full Catalog (K=All) | None | 100.0% (by def) | [Measured] | [Measured] | [Measured] | [Measured] | 0.0% | [Measured] | [Measured] |
| E1 | Dense (K=10) | None | [Measured] | [Measured] | [Measured] | [Measured] | [Measured] | 0.0% | [Measured] | [Measured] |
| E2 | Hybrid RRF+Rerank (K=12) | None | [Measured] | [Measured] | [Measured] | [Measured] | [Measured] | 0.0% | [Measured] | [Measured] |
| E3 | Best Retrieval | Static | [Measured] | [Measured] | [Measured] | [Measured] | [Measured] | 0.0% | [Measured] | [Measured] |
| E4 | Best Retrieval | Dynamic | [Measured] | [Measured] | [Measured] | [Measured] | [Measured] | 0.0% | [Measured] | [Measured] |
| E5 | Best Retrieval + Recovery | Best FS | [Measured] | [Measured] | [Measured] | [Measured] | [Measured] | 0.0% | [Measured] | [Measured] |
```
