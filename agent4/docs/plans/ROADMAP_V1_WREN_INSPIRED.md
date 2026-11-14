# Roadmap V1 — Hoàn thiện Financial Analytics Assistant

## 1. Mục tiêu và chẩn đoán hiện trạng

Roadmap này lấy các ý tưởng tốt nhất từ WrenAI, nhưng không sao chép toàn bộ
kiến trúc Rust/DataFusion/WASM của Wren. Mục tiêu là biến `agent4` từ một hệ
thống trả lời tốt các câu hỏi metric đơn giản thành một semantic analytics
assistant có khả năng:

- hiểu nhiều cách diễn đạt tiếng Việt/Anh cho cùng một nghiệp vụ;
- phân biệt metric gần nghĩa, metric gộp/ròng, flow/snapshot và các view;
- lập kế hoạch cho breakdown, filter, ranking, multi-metric và comparison;
- hỏi lại có căn cứ khi thiếu thông tin;
- chỉ sinh và thực thi SQL đã được kiểm chứng;
- trả lời có số liệu, provenance, caveat và trạng thái rõ ràng;
- đo được chất lượng theo từng stage thay vì chỉ nhìn điểm end-to-end.

### Baseline cần dùng làm mốc

Theo báo cáo [`M4.3_verification.md`](../issues/M4.3_verification.md), cấu hình
lexical tốt nhất hiện đạt:

| Chỉ số | Baseline |
|---|---:|
| End-to-end final status | 80/140 |
| Exact metric selection | 49/140 |
| Exact semantic plan | 28/140 |
| SQL executions hoàn tất | 50/50 ca đã chạy |
| Independent numerical/answer review | 0/140 |

Kết luận: nút thắt chính đang ở metric selection và semantic planning, không
phải ở DuckDB hoặc lớp SQL safety. `make verify` có thể pass các test kỹ thuật,
nhưng chưa đủ để chứng minh chất lượng nghiệp vụ.

## 2. Nguyên tắc kiến trúc đích

Giữ nguyên ranh giới an toàn hiện tại và bổ sung một semantic layer giàu hơn:

```text
User question
    ↓
Query intake + auth context
    ↓
Candidate retrieval
    ↓
Untrusted intent/selection draft
    ↓
Deterministic semantic validation
    ↓
Validated logical query
    ↓
Approved SQL compiler / custom handler
    ↓
SQL safety + tenant/policy gate
    ↓
Read-only execution
    ↓
Result validation + grounded answer
```

Các invariant không được thay đổi:

1. LLM không viết công thức tài chính.
2. LLM không được tự quyết định quyền truy cập.
3. LLM không được sinh SQL được thực thi trực tiếp.
4. Chỉ `ValidatedPlan`/`LogicalQuery` mới được đưa vào compiler.
5. Không chắc chắn thì `needs_clarification`, `unsupported` hoặc `forbidden`;
   không đoán im lặng.
6. Mọi output quality phải gắn với catalog hash, policy hash, dataset hash,
   model version và prompt version.

## 3. Các phase và dependency

```text
V1.0 Observability & Evaluation Baseline
                 ↓
       V1.1 Semantic Catalog V2
          ↙                 ↘
V1.2 Retrieval & Selection   V1.3 Planner V2
          ↘                 ↙
       V1.4 Logical Query & Compiler
                 ↓
       V1.5 Grounded Answer
                 ↓
       V1.6 Knowledge & Memory
                 ↓
       V1.7 Release Hardening
```

V1.2 và V1.3 có thể làm song song sau khi V1.1 hoàn thành. Không bắt đầu
WASM, Rust engine, MCP hoặc GenBI trước V1.4; các công nghệ đó không giải
quyết nút thắt chất lượng hiện tại.

## 4. V1.0 — Observability và benchmark đáng tin cậy

[Báo cáo kiểm chứng và baseline dev V1.0](../../reports/issues/V1.0_verification.md)

### Mục tiêu

Biết chính xác mỗi câu hỏi sai ở retrieval, selection, planning, compilation,
execution hay answer generation.

### Việc cần làm

- Giữ nguyên dataset v2 hiện tại làm dev baseline. Bổ sung kiểm tra file và
  SHA-256 cho holdout. Reviewer độc lập chuẩn bị và giữ bộ holdout mới cho V1.7.
- Giữ category gốc khi đối chiếu với M4.3. Các bộ coverage mới phân rõ:
  - single metric aggregate;
  - time series;
  - breakdown;
  - filters;
  - ranking/top-k;
  - multi-metric;
  - comparison;
  - ambiguous/clarification;
  - unsupported/out-of-catalog;
  - security/authorization.
- Ghi artifact theo từng case gồm:
  - retrieved metric IDs và rank;
  - candidate coverage;
  - selection draft;
  - validated metric IDs;
  - semantic plan;
  - validation error;
  - compiled query fingerprint;
  - execution status;
  - answer validation status;
  - latency, token usage và cost nếu có.
- Không ghi raw credential, raw financial rows hoặc raw SQL vào public error.
- Gán một phân loại chính cho mỗi câu. Giữ cờ lỗi chi tiết có thể chồng lấn
  để đối chiếu với M4.3.
- Thêm report `coverage` cho mọi metric; `null` phải được xem là chưa đo,
  không phải pass.

### Exit criteria

- 100% case có đúng một final classification.
- Có thể dựng failure report từ `cases.jsonl` mà không đọc log thủ công.
- Tách được stage failure với runtime failure.
- Có baseline reproducible chứa dataset SHA, catalog SHA, model, prompt,
  config và git revision.

### Verification

```bash
make verify PYTHON=.venv/bin/python
make eval-validate PYTHON=.venv/bin/python
```

## 5. V1.1 — Semantic Catalog V2 / MDL-lite

### Mục tiêu

Biến metric catalog hiện tại thành semantic catalog có đủ thông tin để planner
và compiler hiểu nghiệp vụ, thay vì chỉ biết metric ID, formula và một số
dimension tổng quát.

### Thiết kế dữ liệu

Giữ tương thích với `metric.catalog.v1`, đồng thời thêm snapshot/schema v2:

```text
MetricDefinition
  id, labels, aliases, description, unit, kind, period_type
  source_model
  formula_or_handler
  time_policy
  dimensions: DimensionBinding[]
  filters: FilterBinding[]
  supported_operations
  compatible_metrics
  default_view, supported_views
  disambiguation_rules
  canonical_examples
  negative_examples
  caveats
  status, owner, verified_handler
```

Thêm các type mới:

- `SemanticModel`: relation logic và physical source.
- `DimensionBinding`: tên nghiệp vụ, alias, cột nguồn, grain, value mapping.
- `FilterBinding`: field, operator, allowed values, normalization.
- `TimePolicy`: flow/range, snapshot/as-of, calendar và closed-period rule.
- `MetricCompatibility`: metric pair/group có thể chạy chung hay không.
- `RelationshipDefinition`: join path được phê duyệt.

### Cách triển khai

- Giai đoạn đầu vẫn giữ registry Python trong `agent4/engine/metrics.py`.
- Tạo adapter/snapshot JSON hoặc YAML có `catalog_hash`.
- Không copy formula vào nhiều module.
- Compiler chỉ đọc catalog snapshot và handler registry đã đăng ký.
- Thêm linter phát hiện alias trùng, dimension không có binding, metric không
  có verified handler và compatibility không đối xứng.

### Mục tiêu bắt buộc: hoàn thiện đầy đủ 66 canonical metrics

`agent4/engine/metrics.py` có **66 metric trong `REGISTRY`**. Mốc ban đầu
của web demo là 22 binding gồm 21 metric registry và `budget_amount`.

Plan này đặt mục tiêu hoàn thiện toàn bộ 66 metric trong `REGISTRY`, bao gồm
semantic metadata, selection, planning, compiler/handler, fixture và answer
validation. Không được đánh dấu tất cả 66 là verified chỉ để tăng số lượng;
metric chỉ được promote khi đủ bằng chứng độc lập.

Ma trận theo dõi 66 ID từ `REGISTRY` và ghi `budget_amount` riêng vì metric
này dùng catalog ngân sách hiện tại. Tập hiển thị mục tiêu cho persona đủ
quyền gồm 66 metric registry và một metric ngân sách bổ sung. Web demo có
binding cho cả 67 mục. Bấm tên metric để điền câu hỏi mẫu theo ID và kỳ.
Trạng thái benchmark tự nhiên và đối soát nghiệp vụ được theo dõi riêng.

[Ma trận coverage](../metric_coverage_66.md) · [Kết quả thực thi 66 metric](../../reports/issues/V1.1-M66_completion.md) · [Kết quả lô sổ cái](../../reports/issues/V1.1-M66_ledger_verification.md)

Coverage manifest phải khóa đủ 66 ID sau:

| Nhóm | Metric IDs |
|---|---|
| P&L / operating flow | `net_revenue`, `gross_revenue`, `revenue_deductions`, `goods_revenue`, `service_revenue`, `cogs`, `gross_profit`, `gross_margin_pct`, `selling_expenses`, `admin_expenses`, `operating_expenses`, `finance_income`, `finance_cost`, `operating_profit`, `other_income`, `other_expenses`, `profit_before_tax`, `income_tax_expense`, `net_profit`, `net_margin_pct`, `ebitda`, `depreciation_expense`, `salary_expense`, `labor_cost` |
| Balance sheet / liquidity | `cash_and_equivalents`, `term_deposits`, `ar_balance`, `ar_by_customer`, `ar_by_salesperson`, `ap_balance`, `ap_by_vendor`, `inventory_value`, `tax_payable`, `debt_balance`, `fixed_assets_net`, `total_assets`, `total_liabilities`, `equity`, `working_capital`, `current_ratio`, `quick_ratio`, `debt_to_equity` |
| Cash flow / working capital | `net_cash_flow`, `cash_flow_breakdown`, `cash_coverage_days`, `ar_aging`, `overdue_receivables`, `dso`, `dso_actual`, `dpo`, `dio`, `cash_conversion_cycle`, `ap_due_soon`, `upcoming_obligations` |
| Operational / tax / control | `expense_by_category`, `expense_spikes`, `unusual_account_movements`, `unbalanced_journals`, `top_sales_transactions`, `budget_vs_actual`, `payroll_summary`, `taxable_income`, `cit_estimate`, `deductible_expenses`, `mgmt_vs_tax_gap`, `vat_position` |

#### Definition of complete cho từng metric

Mỗi metric trong 66 metric phải có đủ các artifact sau:

1. Catalog metadata: label Việt/Anh, mô tả, alias, unit, kind,
   `period_type`, view, owner và catalog version.
2. Semantic capability: supported dimensions, operations, time policy,
   filter fields, allowed values và metric compatibility.
3. Formula hoặc custom handler đã review; không để placeholder `0`,
   `metadata_only` hoặc `verified_handler=False` trong production surface.
4. Source model/relation và dimension bindings rõ ràng.
5. SQL fixture độc lập đã được finance owner đối soát; không lấy output của
   chính compiler đang đánh giá làm ground truth.
6. Result/answer fixture gồm unit, rounding, null/no-data, watermark và caveat.
7. Ít nhất năm câu hỏi golden cho metric:
   - hỏi trực tiếp bằng label chuẩn;
   - hỏi bằng alias/diễn đạt tự nhiên;
   - hỏi theo khoảng thời gian hoặc ngày chốt phù hợp;
   - breakdown/filter nếu metric hỗ trợ;
   - câu mơ hồ hoặc không tương thích phải clarification/unsupported đúng.
8. Ít nhất một câu hard-negative với metric dễ nhầm.
9. Được kiểm tra qua cả catalog, selection, planner, compiler, executor và
   answer validator.

#### Issue V1.1-M66 — Full Canonical Metric Completeness

Issue này làm ngay sau V1.0 và là điều kiện để V1.2/V1.3 dùng đầy đủ catalog
canonical. Có thể thực hiện theo batch, nhưng mỗi batch phải đi hết vòng
catalog → retrieval → planning → execution → answer.

Tasks:

- Tạo `docs/metric_coverage_66.md` hoặc manifest tương đương, một dòng cho
  từng metric và trạng thái của 9 artifact trên.
- Thêm test kiểm tra đủ 66 ID trong canonical manifest. Endpoint `/v1/metrics`
  có thể chỉ expose metric đã verified, nhưng phải có endpoint/report riêng
  để phân biệt `implemented`, `verified`, `visible` và `metadata_only`.
- Kiểm tra mỗi metric có capability phù hợp với flow/snapshot/ratio.
- Bổ sung alias tiếng Việt/Anh và các cách nói thực tế vào catalog, không nhét
  alias riêng vào planner bằng regex.
- Bổ sung binding dimension/filter còn thiếu trước khi mở operation tương ứng.
- Bổ sung verified SQL handler và independent expected result cho từng metric.
- Tạo coverage dataset tối thiểu 66 × 5 golden cases, cộng hard-negative
  cases cho các cặp dễ nhầm.
- Bổ sung benchmark category theo metric để biết metric nào chưa được đo,
  không để metric có trong registry nhưng chỉ tồn tại dưới dạng metadata.
- Đảm bảo `build_canonical_catalog()`, `MetricCatalog(canonical=True)`,
  pipeline production, evaluator và web API dùng cùng một snapshot/hash hoặc
  công khai rõ các namespace khác nhau.

#### Exit criteria riêng cho 66 metric

- `66/66` có metadata đầy đủ.
- `66/66` có `status=approved` và `verified_handler=True` khi đóng Issue.
- `66/66` có fixture độc lập và ít nhất một execution assertion trước khi
  promote sang production.
- `66/66` có golden cases và hard-negative case.
- `66/66` nhất quán trong manifest, retrieval, evaluator và web demo với persona
  đầy đủ quyền khi đóng Issue. Trong từng batch, web hiển thị tập đã verified.
- `0` placeholder/unverified metric xuất hiện trong production selection.
- `0` metric bị chọn nhưng không có compiler/handler tương ứng.
- Flow/snapshot time policy và ratio divide-by-zero behavior được test đầy đủ.

#### Ma trận kiểm thử tối thiểu

| Lớp | Điều cần chứng minh |
|---|---|
| Catalog | ID, label, alias, capability, hash |
| Retrieval | Recall và hard-negative separation |
| Selection | Chọn đúng metric set hoặc từ chối/clarify |
| Planning | Time, dimension, filter, operation hợp lệ |
| Compiler | Formula/handler, grouping, parameterization |
| Safety | Read-only, scope, row cap, policy/catalog hash |
| Execution | Kết quả khớp fixture độc lập |
| Answer | Unit, rounding, provenance, no-data/caveat |

### Exit criteria

- Mọi metric approved có alias Việt/Anh và ít nhất một canonical example.
- Mọi supported dimension có binding cụ thể hoặc bị đánh dấu unsupported.
- Mọi custom metric có handler và fixture độc lập.
- Catalog hash thay đổi khi metadata có ý nghĩa thay đổi.
- Catalog v1 hiện tại vẫn chạy được qua compatibility adapter.
- Canonical inventory đạt đầy đủ `66/66` metric theo Issue V1.1-M66.

### Tests

- Snapshot/hash stability.
- Alias collision.
- Metric visibility theo auth.
- Flow/snapshot compatibility.
- Dimension/filter compatibility.
- Relationship path validation.

## 6. V1.2 — Retrieval và Metric Selection V2

### Mục tiêu

Tăng recall ứng viên và giảm việc model chọn metric “gần nghĩa nhưng sai”.

### Pipeline đích

```text
mention/alias matching
        + lexical retrieval
        + dense retrieval
        + canonical-example retrieval
        ↓
RRF fusion
        ↓
metadata rerank
        ↓
compatibility filter
        ↓
LLM selection draft
        ↓
deterministic validation
```

### Việc cần làm

- Xây document từ catalog v2, không đưa SQL hoặc dữ liệu giao dịch vào index.
- Bật mention retrieval cho tên metric, viết tắt, tài khoản và thuật ngữ
  kế toán.
- Thêm negative/confusable pairs như:
  - doanh thu gộp / doanh thu thuần;
  - lợi nhuận gộp / lợi nhuận hoạt động / lợi nhuận sau thuế;
  - phải thu / phải trả;
  - số dư / phát sinh;
  - chi phí rộng / chi phí theo nhóm hẹp.
- Khi một mention tường minh chưa có ứng viên phù hợp, thử mở rộng candidate
  set có giới hạn. Dùng gold metric để đo coverage sau khi dự đoán.
- Giữ fallback có bounded retry; không tự sửa metric ID bằng fuzzy match sau
  validator.
- Dùng dynamic few-shot chỉ với example tương thích với candidate set.
- Ghi matched terms và retrieval evidence để phân tích lỗi.

### Exit criteria mục tiêu

- Recall@10 gold metric: ≥ 0.95 trên dev.
- Exact selection: ≥ 0.85 trên dev, có báo cáo riêng từng category.
- Invalid metric rate: 0%.
- Câu hỏi unsupported không được biến thành metric hợp lệ ngẫu nhiên.
- Multi-metric coverage được đo riêng, không bị che bởi aggregate cases.

### Verification

```bash
make test-selection PYTHON=.venv/bin/python
make eval PYTHON=.venv/bin/python \
  ADAPTER=agent4.eval_adapter:predict \
  MODEL_VERSION=<model>@<revision> \
  PROMPT_VERSION=metric-selection-v2 \
  OUTPUT_DIR=reports/eval/v1-selection-v2
```

## 7. V1.3 — Planner V2 và clarification có ngữ nghĩa

### Mục tiêu

Cho phép hiểu plan phức tạp mà không để regex hoặc LLM một mình quyết định.

### Thiết kế

LLM chỉ trích xuất untrusted intent:

```json
{
  "metric_mentions": ["doanh thu thuần"],
  "time": {"mode": "range", "grain": "month"},
  "dimensions": ["branch"],
  "filters": [],
  "operation": "breakdown",
  "sort": null,
  "top_k": null,
  "comparison": null
}
```

Code deterministic sẽ:

- map mention → canonical metric;
- normalize ngày, kỳ, grain và timezone;
- map alias dimension/filter;
- kiểm tra operation;
- áp compatibility matrix;
- thêm policy filter;
- quyết định ready/clarification/unsupported.

### Phạm vi tăng dần

1. Aggregate.
2. Timeseries.
3. Breakdown + filters.
4. Ranking/top-k.
5. Multi-metric.
6. Period-over-period comparison.
7. Share/contribution và các metric derived.

Không bật một operation mới chỉ vì parser đã nhận diện được nó. Operation chỉ
được bật khi catalog binding, compiler và execution fixture đã tồn tại.

### Clarification

Mỗi clarification phải có:

- slot chưa giải quyết;
- phần hệ thống đã hiểu;
- lựa chọn được phép;
- lý do cần hỏi;
- auth-filtered choices;
- session TTL và turn limit.

Ví dụ với “lợi nhuận tháng này”:

```text
Bạn muốn xem:
1. Lợi nhuận gộp
2. Lợi nhuận hoạt động
3. Lợi nhuận sau thuế
```

### Exit criteria mục tiêu

- Exact plan ≥ 0.80 trên dev.
- Clarification precision ≥ 0.95: chỉ hỏi khi thật sự thiếu hoặc mơ hồ.
- Không tự đặt default cho metric/view/time khi ambiguity ảnh hưởng kết quả.
- Multi-metric flow/snapshot incompatibility được chặn trước compiler.

## 8. V1.4 — Logical Query và compiler theo semantic model

### Mục tiêu

Tách semantic planning khỏi SQL string generation.

### Kiến trúc

```text
ValidatedPlan
    ↓
LogicalQuery
    ↓
Model/relationship expansion
    ↓
Approved CTE/template/custom handler
    ↓
BoundQuery
```

`LogicalQuery` nên chứa:

- models cần dùng;
- metric expressions đã được catalog chọn;
- dimensions và bindings;
- filters đã normalize;
- time predicates;
- join paths;
- grouping/order/limit;
- source và dialect.

### Việc cần làm

- Đưa source model, dimension binding và join path ra khỏi các đoạn SQL rải
  rác trong compiler.
- Dùng CTE cho base semantic models, lấy cảm hứng từ Wren.
- Giữ custom handlers cho `ar_aging`, `dso`, payroll và metric đặc biệt.
- Chỉ nhận `ValidatedPlan`/`LogicalQuery`, không nhận raw LLM output.
- Bổ sung SQLGlot AST validation; giữ exact-template check hiện tại như lớp
  defense-in-depth.
- Duy trì bind parameters, row cap, timeout, tenant scope, policy hash,
  catalog hash và query fingerprint.

### Exit criteria

- 100% query execution eligible có SQL đã bind và safety-approved.
- 0% query dùng physical table/column do LLM tự đưa vào.
- SQL golden tests cho từng operation và từng metric handler.
- Execution result khớp independent expected result trên các case đã được
  finance owner đối soát.
- Không làm yếu bất kỳ security test hiện tại.

## 9. V1.5 — Grounded answer và provenance

### Mục tiêu

Đảm bảo câu trả lời cuối chỉ nói những gì có trong result đã validate.

Response nên có:

- answer value;
- unit và formatting;
- metric definition;
- applied time/view/filter defaults;
- data watermark/closed period;
- query fingerprint;
- row count/truncation;
- caveat và null/no-data explanation;
- evidence preview nếu được phép.

LLM không được tự tính lại số liệu hoặc điền số khi execution không có result.

### Exit criteria

- Numerical correctness được review độc lập.
- Faithfulness không dùng raw database row ngoài scope.
- No-data, timeout, forbidden và unsupported có response khác nhau.
- Không có answer “thành công” khi SQL execution hoặc result validation thất bại.

## 10. V1.6 — Knowledge và memory có kiểm soát

### Mục tiêu

Đưa glossary, business rule và canonical query vào retrieval mà vẫn
reproducible.

### Layout đề xuất

```text
knowledge/
  glossary.yml
  business_rules.yml
  disambiguation.yml
  canonical_queries.jsonl
  caveats.yml
```

Quy tắc:

- Markdown/YAML/JSONL là source of truth.
- Vector/lexical index chỉ là derived artifact.
- Mỗi document có owner, quality status, catalog hash và version.
- Không đưa raw financial data hoặc secret vào embedding.
- Bắt đầu bằng lexical/token retrieval; chỉ bật embedding khi ablation chứng
  minh có lợi.

## 11. V1.7 — Release hardening

### Release gates

| Gate | Điều kiện tối thiểu |
|---|---|
| Verification | `make verify` pass |
| Warehouse | `make test-mpx10` pass |
| Security | 100% security tests pass, không có regression |
| Retrieval | Recall@10 và coverage có số đo, không null |
| Selection | Đạt threshold theo category, invalid metric = 0 |
| Planning | Đạt threshold theo category, clarification được chấm riêng |
| SQL | 100% eligible cases safety-pass; execution errors có phân loại |
| Answer | Có independent numerical/faithfulness review |
| Reproducibility | Dataset/config/catalog/model/prompt/hash đầy đủ |
| Diff | Không có thay đổi ngoài scope |

Threshold chính thức phải được chốt sau khi có baseline V1.0. Mục tiêu ban đầu
là selection ≥ 0.85, plan ≥ 0.80 và end-to-end ≥ 0.80 trên dev; holdout phải
được giữ kín và không dùng để tuning.

## 12. Những việc cố ý chưa làm

Chưa triển khai các phần sau trong V1:

- Rust rewrite.
- DataFusion thay DuckDB.
- PyO3.
- WASM/browser execution.
- MCP server đầy đủ.
- GenBI/dashboard deployment.
- Multi-database connector framework.
- Vector database nặng như Qdrant/Chroma.

Các phần này chỉ nên mở thành roadmap V2 khi semantic quality, plan quality,
answer grounding và evaluation gates của V1 đã ổn định.

## 13. Thứ tự Issue thực thi

1. `V1.0` — Evaluation trace và failure taxonomy.
2. `V1.1-M66` — Hoàn thiện đủ 66 canonical metrics, xử lý rõ `budget_amount`.
3. `V1.1` — Semantic catalog v2 và catalog snapshot.
4. `V1.2` — Mention/alias retrieval và candidate coverage.
5. `V1.3` — Structured intent planner và clarification.
6. `V1.4` — LogicalQuery/CTE compiler.
7. `V1.5` — Independent answer evaluation và provenance.
8. `V1.6` — Knowledge source-of-truth và memory retrieval.
9. `V1.7` — Release gate, holdout và regression hardening.

Mỗi Issue phải đi hết vòng:

```text
Understand → Implement → Verify → Evaluate → Analyze/Fix → Evidence report
```

Không đánh dấu Issue hoàn thành chỉ vì unit tests pass. Acceptance phải có
case-level evaluation và artifact lưu lại.

## 14. Kết luận thực thi

Việc đầu tiên nên làm không phải đổi model hoặc thêm framework. Hãy làm
`V1.0` và `V1.1` trước. Khi catalog biết rõ metric, dimension, filter, time
policy, compatibility và examples, retrieval/planner mới có nền để cải thiện.

Sau đó dùng đúng một hypothesis cho mỗi vòng cải tiến:

```text
Hypothesis → one targeted change → verification → same benchmark → comparison
```

Giới hạn tối đa ba vòng cải tiến cho mỗi Issue. Nếu chất lượng không tăng,
giữ artifact và quay lại kiểm tra semantic catalog hoặc nhãn benchmark thay vì
tiếp tục tăng độ phức tạp của hệ thống.
