
# Text-to-SQL Evaluation Specification

## 1. Objectives

Evaluate the correctness, reliability, performance,
cost, and safety of the Text-to-SQL system.

Evaluation levels:
- Component-level evaluation
- End-to-end evaluation
- Regression evaluation

## 2. Datasets

Current contract benchmark:
- `data/eval/contract_benchmark_questions.jsonl`: versioned development specifications.
- `vals/run_eval.py`: schema validation and independent prediction scoring.

Legacy retrieval-only datasets remain at `data/eval/dev.jsonl` and
`data/eval/test.jsonl`. They use the older `gold_metric_ids` schema and are read
by `scripts/benchmark_retrieval.py`; do not mix them with the v2 contract dataset.

Each sample should contain:
- id
- user_query
- expected_metric_ids
- expected_filters
- expected_dimensions
- expected_result
- case_category

Rules:
- Dev set: debugging and optimization.
- Test set: independent final assessment.
- Never tune directly on the test set.
- Version datasets and ground-truth labels.

## 3. Metrics

### Metric Retrieval
- Recall@K
- MRR
- Precision@K

### Metric Selection
- Exact Match Accuracy
- Precision / Recall / F1
- Invalid Metric Rate

### SQL
- Execution Accuracy
- SQL Execution Error Rate
- Safety Test Pass Rate

### Answer Generation
- Numerical Correctness
- Faithfulness to query results

### End-to-End
- Answer Accuracy
- Latency p50 / p95
- Average token usage
- Cost per query

## 4. Evaluation Protocol

1. Load the versioned evaluation dataset.
2. Run the selected pipeline or component.
3. Record predictions and execution traces.
4. Calculate evaluation metrics.
5. Compare results with the baseline.
6. Categorize failure cases.
7. Generate a reproducible report.

Record:
- Git commit
- Dataset version
- Model and prompt version
- Configuration
- Timestamp
- Evaluation results

## 5. Quality Gates

Define minimum requirements for each release:
- Required tests must pass.
- SQL safety checks must pass.
- Quality targets must be satisfied.
- No unacceptable regression is allowed.
- Latency and cost must remain within budget.

Exact numerical thresholds are defined in
the version-specific acceptance criteria.

## 6. Error Analysis

Categorize failures into:
- Retrieval failure
- Metric selection failure
- Invalid parameters
- SQL generation failure
- SQL execution failure
- Answer hallucination
- Ambiguous query handling failure

For each important failure:
1. Identify the root cause.
2. Propose a targeted fix.
3. Add regression coverage.
4. Rerun affected evaluations.
5. Compare against the previous baseline.

## 7. Contract benchmark v2 — quy trình cho bản làm lại

### 7.1. Phạm vi và trạng thái

Bộ `contract_benchmark_questions.jsonl` gồm 140 câu, chia 9 nhóm:

| `case_category` | Số câu | Mục đích |
| --- | ---: | --- |
| `single_metric_aggregate` | 20 | Một metric, một phạm vi dữ liệu |
| `timeseries_and_comparison` | 20 | Chuỗi thời gian và kỳ so sánh |
| `dimensional_breakdown_filter_topk` | 20 | Dimension, filter, thứ hạng |
| `business_views` | 15 | Khác biệt giữa view quản trị và thuế |
| `ambiguous_needs_clarification` | 15 | Thiếu hoặc mơ hồ metric/kỳ |
| `unsupported_out_of_catalog` | 12 | Ngoài phạm vi sản phẩm/catalog |
| `no_data_and_edge_cases` | 8 | Không có dữ liệu, kỳ chưa đủ, mẫu số bằng 0 |
| `authorization_and_security` | 10 | Quyền truy cập và injection |
| `multi_metrics` | 20 | Chọn đúng toàn bộ tập 2–5 metric và kiểm tra khả năng kết hợp |

Tất cả hiện là `split=dev`, `review_status=draft`. Đây là bộ yêu cầu hành vi
cho các module đang được xây lại. Chưa có test set được niêm phong, chưa có
domain approval và chưa có kết quả đánh giá cho phiên bản này. Khi tạo test set,
tách theo nhóm câu hỏi/intent để tránh paraphrase leakage với dev và example bank.
Không chỉ đổi tên `dev` thành `test` để tuyên bố đánh giá độc lập.

Metric ID lấy từ `agent4/engine/metrics.py`; plan dùng schema trong
`agent4/text2sql/models.py`. Ví dụ canonical: `gross_margin_pct`, `net_margin_pct`,
`operating_expenses`, `cash_and_equivalents`, `debt_balance`. Các tên khác trong
test harness cũ không được tự động alias sang catalog mới.

`expected_result=null` nghĩa là **chưa có golden số liệu được đối soát độc lập**.
Không có nghĩa là kết quả rỗng hoặc số 0. Các golden cũ được compiler của test
harness sinh ra không được dùng làm bằng chứng độc lập cho chính compiler đó.
Runner không sinh lại câu hỏi, ghi đè nhãn, chạy golden SQL hoặc mở database.

### 7.2. Schema của một câu hỏi

```json
{
  "schema_version": "benchmark-case.v2",
  "dataset_version": "contract-benchmark-v2.0",
  "id": "BM-001",
  "split": "dev",
  "case_category": "single_metric_aggregate",
  "locale": "vi-VN",
  "user_query": "Tổng doanh thu thuần tháng 08/2026 là bao nhiêu?",
  "auth_context": {
    "user_id": "analyst-01",
    "tenant_id": "minh-phat",
    "roles": ["finance_analyst"],
    "allowed_views": ["mgmt"],
    "allowed_metrics": null
  },
  "query_context": {
    "reference_date": "2026-10-14",
    "timezone": "Asia/Ho_Chi_Minh"
  },
  "expected_selection_status": "resolved",
  "expected_metric_ids": ["net_revenue"],
  "expected_dimensions": [],
  "expected_filters": [],
  "expected_plan": {
    "plan_version": "1.0",
    "status": "ready",
    "metric_ids": ["net_revenue"],
    "time": {
      "mode": "range",
      "start": "2026-08-01",
      "end": "2026-08-31",
      "as_of": null,
      "grain": "month"
    },
    "dimensions": [],
    "filters": [],
    "view": "mgmt",
    "operation": "aggregate",
    "sort": null,
    "top_k": null,
    "comparison": null,
    "question_for_user": null,
    "unresolved_slots": [],
    "reason_code": null
  },
  "expected_result": null,
  "expected_final_status": "ready",
  "expected_warning_codes": [],
  "security_tags": [],
  "fixture_requirements": [],
  "review_status": "draft",
  "notes": "Semantic draft; cần owner đối soát kết quả số liệu độc lập."
}
```

`ready`/`no_data` phải có `expected_plan` đầy đủ. Các record được kiểm tra
bằng `BenchmarkCase` trong runner. `expected_dimensions` và `expected_filters`
phải khớp plan; không chấp nhận ID trùng, câu hỏi trùng, field lạ hoặc metric ID
không có trong catalog. `auth_context` là dữ liệu mô phỏng server để test,
không phải quyền do người dùng tự khai báo trong sản phẩm.

`fixture_requirements` mô tả điều kiện môi trường cần chuẩn bị, ví dụ một ngày
không có doanh thu hoặc nguồn có dữ liệu chứa injection. Runner không tự tạo
các điều kiện này và không chuyển chúng cho hệ thống dự đoán. Owner cần xác
nhận snapshot/fixture đáp ứng điều kiện trước khi chạy đánh giá có execution.

### 7.3. Adapter cho module đang xây lại

Adapter là một hàm async:

```python
async def predict(request: dict) -> dict:
    # Gọi module/pipeline thật và chuẩn hóa output sang Prediction.
    ...
```

Runner chỉ truyền:

```text
contract_version, id, user_query, locale, auth_context,
query_context, options, seed
```

Không truyền `expected_*`, category, notes hoặc fixture hints. Adapter không
được tự đọc dataset/nhãn, ép metric đúng vào retrieval, dùng expected plan thay
planner, hoặc đưa câu benchmark vào dynamic few-shot bank. Hệ thống phải tạo
prediction trước; runner mới đọc expectation để chấm.

Adapter E2E chuyển cảnh báo API `partial_data_watermark` thành `partial_data`
và `ratio_undefined` thành `undefined_ratio` trong `Prediction.warning_codes`.

Output dùng schema `Prediction` trong `vals/run_eval.py`. Tùy `--mode`:

- `retrieval`: trả `id`, `retrieved_metric_ids` theo thứ tự rank cuối.
- `selection`: thêm `selection={status, metric_ids, clarification_question}`;
  nên trả cả candidate set và `selected_example_ids` để phân tích retrieval/few-shot.
- `e2e`: trả `plan`, `final_status`, `result`, `answer`, `warning_codes`,
  `execution`, cùng trace component nếu có.

Các field không quan sát được để `null` hoặc bỏ qua. Không gán `0`, `true`
hoặc `ready` để làm đầy báo cáo. `execution` có `attempted`, `succeeded`,
`safety_passed`, `query_fingerprint`; thiếu bằng chứng execution/safety thì
không được coi là đã pass. Những ca bị chặn không được có execution hoặc result.

`usage={input_tokens, output_tokens}` phải là tổng usage thực của cả request,
bao gồm các lần retry. `latency_ms` và `stage_latency_ms` đo thực tế. Khi gọi
adapter, runner đo wall time; khi chấm file predictions, runner dùng latency đã
ghi lại, không lấy thời gian đọc file làm latency hệ thống. Adapter chịu trách
nhiệm timeout/cancel tại provider và database; cancel coroutine của runner không
chứng minh query nền đã dừng. Error chỉ lưu `stage`, `code`; không lưu secrets,
SQL raw hoặc toàn bộ lỗi database vào artifact.

### 7.4. Cách dùng sau khi module sẵn sàng

Chỉ kiểm tra cấu trúc, không gọi adapter/model/database và không tạo report:

```bash
python vals/run_eval.py --validate-only
```

Có thể thêm `--example-bank data/example_bank.jsonl` để kiểm tra câu benchmark
trùng chính xác với example bank mà không gọi embedding/model. Khi prediction
có `selected_example_ids`, phải cung cấp bank tương ứng; ID ví dụ ngoài bank
bị reject. Kiểm tra paraphrase/group overlap vẫn cần review độc lập.

Khi đã có adapter thật, ví dụ `my_project.eval_adapter:predict`:

```bash
python vals/run_eval.py --mode selection \
  --adapter my_project.eval_adapter:predict \
  --model-version 'provider:model:revision' \
  --prompt-version 'metric-selection-v1' \
  --output-dir reports/eval/selection-dev-v1
```

Tên adapter trên là ví dụ tích hợp, chưa có trong repo. Runner không tự dùng
test harness hoặc mock trả golden label làm hệ thống dự đoán.

Có thể chấm predictions đã ghi trước đó:

```bash
python vals/run_eval.py --mode e2e \
  --predictions path/to/predictions.jsonl \
  --model-version 'provider:model:revision' \
  --prompt-version 'pipeline-v1' \
  --output-dir reports/eval/e2e-dev-v1
```

Mỗi dòng file predictions là một `Prediction`, ghép bằng `id`. ID ngoài dataset
hoặc trùng bị reject; ID thiếu vẫn được tính là failure. Có thể dùng file predictions
toàn bộ dataset khi lọc `--category`; chỉ các ID được chọn tham gia chấm.
Mặc định là dev; chỉ dùng `--split test`
khi đã có test data được review. `--ks 5 10` dùng cho retrieval.

Artifact của một run:

- `summary.json`: metrics tổng và theo category, metadata, baseline và gates.
- `predictions.jsonl`: output chuẩn hóa cùng trace/usage.
- `cases.jsonl`: checks, prediction hash và thông tin so sánh từng case.
- `failures.jsonl`: các case có lỗi và failure category.

Output directory phải mới để tránh ghi đè baseline. Không sửa dataset trong run.

### 7.5. Cách chấm và giới hạn

- Retrieval: Recall@K, Precision@K, MRR của metric đúng đầu tiên; với nhiều
  metric, bổ sung `all_metrics_covered_at_k`. Precision@K chia cho K kể cả khi
  retrieval trả ít hơn K. Ca không có gold metric không tham gia retrieval score.
- Selection: exact match xét cả status và toàn bộ metric set; precision/recall/F1
  tính micro. `invalid_metric_rate` đếm selected ID ngoài canonical catalog.
  Chọn ID đúng catalog nhưng ngoài candidate set vẫn là contract failure.
- Plan: so toàn bộ semantic plan, bỏ khác biệt thứ tự của metric/filter và cách
  diễn đạt câu hỏi làm rõ; vẫn kiểm tra period, view, sort, limit và unresolved slots.
- SQL execution accuracy: chỉ chấm case có `expected_result` đã được review và
  snapshot trùng `result_reference.snapshot_id`. So schema/type/unit, số dòng,
  null, giá trị Decimal, duplicate rows và truncated flag. `rank`/`timeseries`
  giữ thứ tự; các result khác so không phụ thuộc thứ tự dòng.
- Safety: chỉ chấm từ execution evidence của adapter và decision mong đợi;
  đây không phải chứng nhận RLS/DB security. Trace thiếu được báo qua coverage.
- `expected_result=null` dẫn tới execution accuracy `null`, không phải pass.
  Status accuracy và plan accuracy được báo riêng, không gọi là answer accuracy.
- Numerical correctness, faithfulness và answer accuracy lấy từ review độc lập,
  không lấy self-score của Answer Validator. Khi chưa có review, các score là
  `null`; không dùng một LLM chưa được kiểm chứng để mặc định chấm đúng.
- Cost chỉ tính khi có giá input/output và usage đầy đủ; nếu thiếu là `null`.
  Dùng `--input-usd-per-million` và `--output-usd-per-million` để ghi giá của run.
- Mỗi metric có coverage/denominator để phân biệt chưa đo với đo sai. Missing
  prediction không được bỏ khỏi mẫu số để tăng accuracy.

Để thêm golden result sau này, finance owner phải đối soát qua independent SQL
hoặc human reconciliation, gắn `result_reference={snapshot_id, method, reviewer,
version}`, rồi đổi `review_status=approved`. Đây là tác vụ authoring riêng;
không dùng SQLCompiler đang bị đánh giá để tạo đáp án cho chính nó.

Review answer được cung cấp qua `--judgments path/to/judgments.jsonl`, mỗi dòng:

```json
{
  "id": "BM-001",
  "prediction_sha256": "hash từ cases.jsonl của prediction được review",
  "judge_id": "finance-reviewer",
  "judge_version": "rubric-v1",
  "numerical_correctness": true,
  "faithfulness": true,
  "answer_accuracy": true
}
```

Hash phải khớp đúng prediction; review trên answer cũ không được áp dụng cho
prediction mới. Báo cáo luôn ghi số câu đã được review độc lập.

### 7.6. Baseline và quality gates

Metadata ghi Git commit/dirty flag, dataset hash/version, catalog hash,
config hash/path, model/prompt version, seed, scoring settings và timestamp.
Configuration snapshot được lưu sau khi kiểm tra qua schema config của repo;
không copy secret tùy ý vào metadata. Model/config version là thông tin do người chạy khai báo; adapter phải thực sự
sử dụng đúng cấu hình đó. File predictions/judgments cũng được hash để truy vết.

Dùng `--baseline path/to/summary.json` để nhận delta. Chỉ so khi dataset,
catalog, split, tập ID, mode, K, tolerance và settings chấm tương thích. Khi
bộ câu hỏi đổi version, lập baseline mới; không so accuracy trực tiếp với bộ cũ.

Dùng `--thresholds path/to/gates.json` để áp acceptance criteria của milestone:

```json
{
  "retrieval.recall_at_k.10": {"min": 0.95},
  "selection.exact_match_accuracy.value": {"min": 0.90},
  "e2e.latency_p95_ms": {"max": 5000}
}
```

Các số trên chỉ minh họa cú pháp; owner phải chốt target chính thức. Gate trên
metric chưa đo phải fail. Trước release, gate cả coverage để tránh dùng vài
case có output/review làm đại diện cho toàn bộ dataset. Exit code: `0` hoàn tất
hoặc validate-only hợp lệ, `1` gate/runtime failure, `2` input/config không hợp lệ.

### 7.7. Giữ bộ contract test hiện có

Các file test hiện có là bộ test người dùng vừa viết cho bản rebuild và được
giữ nguyên; chỉ bổ sung unit test riêng cho runner. Riêng test benchmark hiện cố định 120 câu/8 nhóm cùng namespace của
`tests/contract_harness.py`. Để không đổi fixture/giao diện của bộ test này:

- Giữ snapshot ban đầu tại `data/eval/contract_benchmark_questions.v1.jsonl`.
- `scripts/evaluate_contract_benchmark.py` giữ `BENCHMARK_PATH` trỏ tới snapshot
  v1 và giữ hàm `evaluate_benchmark_question(item, catalog, embedding_provider)`.
- Helper đó kiểm tra integration bằng selection/plan đầu vào cố định. Không dùng
  pass rate của nó làm chỉ số retrieval/LLM/planner độc lập.
- CLI của script chuyển sang runner mới; không tự sinh lại golden hoặc ghi đè
  dataset. Runner `vals/run_eval.py` dùng bộ 140 câu v2 ở đường dẫn chính.

Catalog và plan của harness v1 khác catalog runtime hiện có, ví dụ
`gross_margin`/`gross_margin_pct`, `operating_expense`/`operating_expenses`,
`branch_code`/`branch`, và `ranking`/`rank`. V2 dùng canonical catalog/plan theo
AGENTS.md. Chốt mapping/interface của bản rebuild khi triển khai module; không
coi hai namespace này tương đương ngầm hoặc chuyển nhãn để tăng điểm.
