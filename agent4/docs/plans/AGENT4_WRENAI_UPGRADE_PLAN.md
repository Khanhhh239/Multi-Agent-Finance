# Kế hoạch nâng cấp Agent 4 sau khi đối chiếu WrenAI

Kế hoạch triển khai cho [Roadmap V1](ROADMAP_V1_WREN_INSPIRED.md), dựa trên source Agent 4 và checkout WrenAI tại `6e8ac818d443eb3a42bd58f63b564a4b459c2da6`. Phạm vi gồm catalog, retrieval, planner, compiler, execution, answer, knowledge, benchmark và khả năng tái lập checkout. Phân tích nguồn dựa trên module tương ứng. Xuất xứ của các đoạn code được sao chép nguyên văn chưa được xác minh.

## 1. Bằng chứng hiện có

| Chỉ số trên 140 câu dev | V1.1 lexical | V1.2 mentions |
| --- | ---: | ---: |
| Recall@10 | 95,0% | 95,0% |
| Exact metric selection | 91/140 (65,0%) | 78/140 (55,7%) |
| Exact plan | 79/140 (56,4%) | 67/140 (47,9%) |
| Đúng trạng thái cuối | 117/140 (83,6%) | 96/140 (68,6%) |
| SQL hoàn tất / đã thử | 92/92 | 71/71 |
| Ca gắn nhãn security đạt theo runner | 13/15 | 13/15 |
| Answer có review độc lập | 0/140 | 0/140 |

Hai artifact dùng cùng dataset, model revision và khóa so sánh. Preset V1.2 đổi nhãn phiên bản prompt và bật mentions. Trong code, khi có `matched_terms`, selector cũng đổi payload và thêm chỉ dẫn vào prompt. Bật/tắt mentions hiện đo tác động của cả gói. Muốn quy nguyên nhân phải tách việc xếp hạng ứng viên khỏi việc đưa tín hiệu vào prompt. Xem [V1.1](../../reports/eval/V1.1-M66_final_dev_lexical/summary.json), [V1.2](../../reports/eval/V1.2_mentions_dev/summary.json) và [selector](../../agent4/metric_selection/llm_selector.py#L242).

Báo cáo M66 ghi nhận 66/66 metric thực thi và qua kiểm tra answer nội bộ khi chỉ định ID. Khi hỏi bằng tên để model chọn metric, 55/66 ca đạt phép kiểm tra của script. Độ đúng số liệu trên bộ 140 câu chưa được chấm độc lập. BM-119/BM-120 vướng fixture nhà cung cấp của kho cũ theo báo cáo M66. BM-096 là ca ngoài catalog bị chọn thành metric chi phí. Xem [báo cáo M66](../../reports/issues/V1.1-M66_completion.md), [script kiểm chứng](../../scripts/check_catalog_execution.py) và [ma trận coverage](../metric_coverage_66.md).

## 2. Ánh xạ từ source WrenAI sang Agent 4

| Source WrenAI đã đối chiếu | Áp dụng vào Agent 4 |
| --- | --- |
| `context.py`, `context_adapter.py::load_snapshot`, `examples/v5-jaffle` | Xây snapshot semantic có schema, ID và hash. Retrieval, planner, compiler và API cùng đọc metadata đã kiểm tra. Giữ công thức và handler tài chính trong code đã review. |
| `memory/schema_indexer.py`, `memory/store.py`, `memory/markdown.py` | Tách glossary/rules khỏi ví dụ đã duyệt. Giữ JSONL/YAML làm nguồn chuẩn và cho phép dựng lại index. Ví dụ của Agent 4 lưu câu hỏi, metric và plan đã duyệt. |
| `engine.py::dry_plan`, `engine.py::dry_run`, `agent_sql.py::AdHocSQL.prepare` | Thêm khả năng kiểm tra plan và binding trước khi truy vấn. Dùng compiler theo template và safety gate hiện có cho warehouse DuckDB. |
| `agent_service.py`, `governed_query.py::QueryLifetime`, `skills_content/wren-planner/SKILL.md` | Dùng deadline và số lần recovery có giới hạn, kiểm tra bằng chứng theo scope và chỉ tách truy vấn khi các kết quả thực sự có grain khác nhau. |

Các quyết định cần giữ xuyên suốt V1 là catalog và công thức tài chính do repo quản lý, auth và row scope do server cấp, model chỉ đưa ra draft. Đường thực thi đi qua `ValidatedPlan → BoundQuery → SafeBoundQuery`, bind params, warehouse đúng tenant, read-only, timeout và row cap. Rust, DataFusion, MCP, WASM, GenBI và hệ connector đa nguồn thuộc phạm vi roadmap riêng nếu sau này có nhu cầu sản phẩm.

## 3. Thứ tự Issue và tiêu chí nghiệm thu

ID dưới đây dùng để theo dõi plan này. Làm từng Issue theo [issue-loop](../../.agents/skills/issue-loop/SKILL.md). Cột phụ thuộc cho biết điều kiện để bắt đầu phần triển khai tương ứng.

| Thứ tự | Issue | Phụ thuộc | Kết quả cần có |
| ---: | --- | --- | --- |
| 1 | UP-01 · Sửa text hiển thị | — | Bảng, answer và evidence dùng cùng chính sách hiển thị |
| 2 | UP-02 · Khóa baseline và sửa phép đo | UP-01 | Chạy lại được baseline và chấm được theo warehouse, cấu hình và từng case |
| 3 | UP-03 · Tách tác động của mentions | UP-02 | Quyết định giữ, đổi hoặc bỏ từng tín hiệu dựa trên ablation |
| 4 | UP-04 · Snapshot semantic | UP-02, UP-03 | Các module dùng chung capability và binding đã kiểm |
| 5 | UP-05 · Đối soát 66 metric | UP-02, UP-04 | Coverage thực thi, ngôn ngữ và số liệu của từng metric |
| 6 | UP-06 · Retrieval và selection | UP-03, UP-04, UP-05 | Chọn đúng cả tập metric và xử lý câu ngoài catalog |
| 7 | UP-07 · Planner và clarification | UP-04, UP-06 | Chuẩn hóa các slot, từ chối hoặc hỏi lại đúng lý do |
| 8 | UP-08 · Logical query và compiler | UP-04, UP-07 | Ràng buộc nguồn, grain, filter và query preview có kiểm tra |
| 9 | UP-09 · So sánh kỳ và multi-metric | UP-05, UP-07, UP-08 | Một lát cắt so sánh kỳ được xác minh từ câu hỏi đến answer |
| 10 | UP-10 · Answer và provenance | UP-01, UP-05, UP-09 | Câu trả lời có đơn vị, kỳ, phạm vi và bằng chứng phù hợp |
| 11 | UP-11 · Knowledge và memory | UP-04, UP-06, UP-10 | Nội dung đã duyệt, index dựng lại được, có ablation |
| 12 | UP-12 · Release và checkout | UP-01 đến UP-11 | Release gate có holdout, tài liệu đúng và checkout tái lập được |

### UP-01 · Sửa text hiển thị

- Sửa `safe_display_text` để chuỗi đã qua xử lý là chuỗi được xuất. Kiểm tra tác động của NFKC, whitespace và ký tự điều khiển hướng chữ lên nhãn Việt/Anh. Giữ giá trị nghiệp vụ gốc trong phép tính và đối chiếu.
- Kiểm tra các call site trong result validator, answer và evidence. Thêm ca hồi quy cho Unicode format controls, label tiếng Việt, ký tự hợp lệ và text cần redaction.
- Nghiệm thu khi cùng một ô hiện nhất quán trên các đường hiển thị, số liệu và kiểu dữ liệu giữ đúng contract hiện có. Chạy `make test-answer test-security` và static checks cho phần đổi. [result_validator.py](../../agent4/answer/result_validator.py#L25)

### UP-02 · Khóa baseline và sửa phép đo

- Ghi Git revision, SHA dataset, warehouse snapshot, runtime catalog hash, policy, example bank, prompt thực tế, model revision, seed, cache, timeout, phần cứng và điều kiện đo latency. Nếu tree còn dirty, lưu diff liên quan đã review để tái lập. Giữ bản V1.1 và V1.2 làm mốc lịch sử. Chạy baseline mới bằng pipeline thật trên cấu hình đã ghi khi bắt đầu ablation.
- Đồng bộ `EVAL_CONFIG` của runner và `AGENT4_METRIC_SELECTION_CONFIG` của adapter. Runner hiện sinh `catalog_sha256` từ `REGISTRY`, còn adapter ghi runtime catalog hash trong trace. Ràng buộc provenance với snapshot thực sự chạy, thêm `data_snapshot_id` từ fixture server đã xác minh, và kiểm tra reference date/timezone trong các ca kỳ tương đối. Adapter chỉ nhận input và runtime fixture, giữ nhãn ngoài pipeline.
- Bổ sung kiểm tra preflight fixture của mỗi kho. Xác nhận điều kiện của BM-119/BM-120 trên MPX10 và fixture legacy. Nếu cần một bộ fixture mới, tạo version riêng có review, giữ artifact cũ và lập baseline mới. Theo dõi riêng các ca bị từ chối đúng, lỗi truy vấn và thiếu điều kiện fixture. Giữ BM-096 làm ca hồi quy hành vi ở UP-06.
- Chạy `make test-benchmark eval-validate` và một `make eval` thật qua `agent4.eval_adapter:predict`. Nghiệm thu khi provenance đủ để tái lập các run cần so, mỗi case có classification, và kết quả chưa đo được thể hiện qua coverage cùng giá trị `null`. [Runner](../../vals/run_eval.py), [adapter](../../agent4/eval_adapter.py), [quy trình eval](../evaluation.md)

### UP-03 · Tách tác động của mentions

- Thử bốn biến thể trên cùng source, dataset, warehouse, model và seed. Dùng lexical làm đối chứng. Thử chỉ đổi candidate ranking, chỉ cung cấp `matched_terms` và phần chỉ dẫn tương ứng trên danh sách lexical cố định, rồi thử cả hai. Dùng bộ TOP-K và cache policy nhất quán. Ghi số lần lặp nếu provider có dao động.
- Lưu rank và tập ứng viên trước/sau, tín hiệu mention, status của draft, tỷ lệ lỗi schema và kết quả đã validate. Kiểm tra BM-009, BM-122 và các ca Việt/Anh, tax view, multi-metric bị mất kết quả. Đo `all_metrics_covered_at_k` và xem metric đúng đã bị loại khỏi danh sách hay selector chọn sai khi metric vẫn có mặt.
- Chạy `make test-selection` và real dev eval cho cả bốn biến thể. Chỉ đổi mặc định nếu có lợi ích theo nhóm mục tiêu, exact selection, exact plan và trạng thái cuối không giảm vượt ngưỡng đã chốt, không có metric sai ID hoặc vượt scope sau validation, và latency/token trong ngân sách. Nếu không đạt, đóng thí nghiệm bằng báo cáo và giữ cấu hình lexical đã kiểm chứng. [Retrieval](../../agent4/metric_selection/orchestrator.py), [recovery](../../agent4/metric_selection/recovery.py)

### UP-04 · Snapshot semantic

- Mở đầu bằng snapshot sinh từ registry và các handler hiện có. Khai báo ID/alias Việt–Anh, nguồn, đơn vị và scale, view, grain, time policy, dimension binding, toán tử/giá trị filter, capability, compatibility, caveat và handler ID. Ánh xạ rõ legacy IDs và `budget_amount`. Giữ một đầu mối cho biểu thức nghiệp vụ.
- Thí điểm với `net_revenue` (flow), `net_margin_pct` (ratio), `cash_and_equivalents` (snapshot), `ar_aging` (custom) và `budget_amount` (nguồn ngân sách). Cho các module đọc snapshot qua adapter tương thích, sau đó chuyển các metric còn lại theo nhóm để kiểm parity.
- Thêm linter cho duplicate ID, alias cố ý mơ hồ, binding thiếu, handler chưa đăng ký, vai trò/view, capability không thể compile và compatibility không nhất quán. Snapshot cho nội dung tương đương có cùng hash. Thay đổi metadata có ảnh hưởng đến runtime cập nhật hash và invalidation cho index/cache.
- Chạy `make test-core test-selection test-planning test-sql check-metric-coverage check-catalog-execution`. Chứng minh parity metric, visible set và kết quả áp dụng của API trước khi mở capability mới. [Registry](../../agent4/engine/metrics.py), [catalog](../../agent4/core/catalog.py), [handlers](../../agent4/engine/metric_queries.py)

### UP-05 · Đối soát 66 metric

- Giữ một bảng theo metric, view và snapshot. Tách trạng thái có binding, đã chạy qua ID, đã đạt câu hỏi tự nhiên và đã có golden số liệu độc lập. Theo dõi `budget_amount` riêng. Ưu tiên nhóm đã lộ lỗi gồm gross/net margin, tiền gửi kỳ hạn, vốn lưu động, DSO/DPO, sau đó phủ hết registry.
- Mỗi metric có ít nhất năm ca golden về label/alias/kỳ và các chiều hoặc tình huống mơ hồ phù hợp, cùng ít nhất một ca hard negative. Bổ sung fixture cho flow/snapshot, mẫu số 0, đơn vị, rounding, thiếu dữ liệu, watermark và các view/row scope được khai báo. Chú thích các capability chưa được finance owner đối soát.
- Finance reviewer xác nhận expected rows bằng SQL đối chứng độc lập hoặc đối soát nghiệp vụ. Gắn snapshot, phương pháp, reviewer và phiên bản theo `result_reference`. Reviewer chuẩn bị holdout theo nhóm intent ngoài luồng tuning từ Issue này.
- Chạy `make check-metric-coverage check-catalog-execution test-mpx10` và real dev eval trên tập mở rộng. Nghiệm thu khi 66/66 có evidence tương ứng từng trạng thái và mọi metric công bố đã được đối soát có golden được duyệt. Công bố phần thiếu nếu reviewer hoặc fixture chưa sẵn sàng.

### UP-06 · Retrieval và selection

- Sinh document từ snapshot theo quyền của request. Đo lexical, dense, fusion, metadata rerank và few-shot bằng từng thay đổi riêng. Chỉ bật cấu hình có kết quả tốt hơn trên các nhóm cần cải thiện. Giữ giới hạn candidate, prompt và số lần recovery.
- Ưu tiên phân biệt gross/net, số dư/phát sinh, phải thu/phải trả, mgmt/tax và tập multi-metric. Thêm bằng chứng phủ đủ toàn bộ metric set và đo false acceptance của các câu ngoài catalog. Kiểm tra BM-096 và các câu cùng intent trên dev.
- Chạy `make test-selection test-security` và real dev eval. Mục tiêu từ roadmap là Recall@10 ≥ 95%, exact selection ≥ 85%, invalid metric = 0. Gate thêm multi-metric coverage và số ca ngoài catalog bị trả số liệu trong tập bắt buộc. Báo cáo theo locale, view và loại câu.

### UP-07 · Planner và clarification

- Dùng snapshot làm nguồn cho alias, time policy, operation, dimension và filter. Chuyển parser theo từng nhóm slot và giữ các ca đã đúng. Chỉ thử structured extraction qua model nếu failure cases cho thấy parser hiện tại thiếu trường hợp quan trọng. Mọi draft phải qua validator và policy server.
- Xử lý kỳ tuyệt đối/tương đối, range/as-of, grain, sort/top-k và filter ambiguity. Clarification cho biết phần đã hiểu, slot thiếu và lựa chọn trong scope. Xác thực lại quyền, catalog và expiry khi tiếp tục session. Dùng selection cố định trong phép đo planner cô lập, rồi chạy lại từ câu hỏi thật để đo toàn pipeline.
- Chạy `make test-planning test-security` và real dev eval. Mục tiêu exact plan ≥ 80%, clarification precision ≥ 95% theo roadmap. Báo riêng recall của các ca cần hỏi lại và lỗi theo từng slot, gồm trường hợp hỏi thiếu hoặc dùng default lệch nghiệp vụ. [Planner](../../agent4/planning/planner.py), [validator](../../agent4/planning/validator.py), [clarification](../../agent4/planning/clarification.py)

### UP-08 · Logical query và compiler

- Chuẩn hóa bước từ `ValidatedPlan` sang cấu trúc gồm source, grain, projection, time, scope, params, sort và cap. Dùng binding từ snapshot và giữ các custom handler đã review. Chỉ dùng CTE hoặc join đã khai báo khi có nhu cầu cụ thể và fixture chứng minh kết quả tương đương.
- Thí điểm preview nội bộ sau auth, validation và safety. Trả scope, view, grain, fingerprint và trạng thái kiểm tra. Nếu cần kiểm tra binding với database, dùng warehouse fixture chỉ đọc và truy vấn kiểm tra không trả rows. Tách hai kết quả plan preview và DB validation. Chỉ cân nhắc AST check bổ sung khi có trường hợp template hiện tại chưa kiểm được.
- Chạy `make test-sql test-security check-catalog-execution`, đối soát SQL và rows trên fixture độc lập. Nghiệm thu khi mọi query thực thi đều được bind, safety-approved và đúng scope, mọi combination không hỗ trợ bị chặn trước execution. Đo timeout, cancellation, giới hạn result và tải đồng thời theo deployment. Ưu tiên sửa đường DuckDB hiện có trước khi cân nhắc tách worker. [Compiler](../../agent4/sql/compiler.py), [safety](../../agent4/sql/safety.py), [executor](../../agent4/sql/executor.py)

### UP-09 · So sánh kỳ và multi-metric

- Bắt đầu bằng hai kỳ tường minh cho một flow metric đã đối soát, cùng view và row scope. Plan có kiểu ghi rõ kỳ hiện tại, kỳ gốc, đơn vị, thứ tự và phép chênh lệch. Xác định cách xử lý mẫu số 0, kỳ không đủ và dữ liệu rỗng trong contract trước khi bật.
- Mở tiếp kỳ trước/cùng kỳ và snapshot comparison khi có time policy cùng fixture đối chứng phù hợp. Với multi-metric, dùng compatibility theo nguồn/grain và chỉ ghép các kết quả có scope phù hợp. Chốt semantics riêng trước khi mở share/contribution hoặc nhiều result có grain khác nhau.
- Xác minh route API thực tế qua `make test-planning test-sql test-answer test-security`, fixture độc lập và dev eval. Bật từng operation khi parser, catalog, compiler, validator, answer và evidence cùng hỗ trợ. Giữ lối trả clarification/unsupported cho phần chưa hỗ trợ.

### UP-10 · Answer và provenance

- Giữ rendering xác định. Trả metric, unit, kỳ/closed period, applied filters được phép hiển thị, watermark, status, truncation và fingerprint khi phù hợp với contract. Evidence cho mỗi claim phải chỉ đúng ô hoặc phép tính đã quy định từ kết quả đã validate. Nếu truy vấn trả nhiều dòng nhưng request ẩn bảng, tránh câu dẫn yêu cầu người dùng xem bảng không có.
- Phủ các ca zero/null/no data, partial period, ratio không xác định, ranking/top-k, kết quả so sánh và table ẩn. Ràng buộc evidence preview với quyền và redaction hiện hành. Phân biệt unsupported, forbidden, timeout và execution failure.
- Chạy `make test-answer test-security` và eval E2E. Finance reviewer chấm numerical correctness, faithfulness và answer accuracy bằng `judgments.jsonl` gắn đúng prediction hash. Nghiệm thu khi mọi câu trong tập số liệu bắt buộc có review, các ca quan trọng không có lỗi số liệu hoặc claim thiếu bằng chứng. [Generator](../../agent4/answer/generator.py), [evidence](../../agent4/answer/evidence.py), [quy trình judgments](../evaluation.md#75-cách-chấm-và-giới-hạn)

### UP-11 · Knowledge và memory

- Version hóa glossary, business rules, disambiguation và các ví dụ đã duyệt. Tái dùng example bank hiện có. Gắn owner, trạng thái duyệt, catalog hash, locale và phạm vi áp dụng. Rule ảnh hưởng kết quả phải được kiểm qua catalog/validator hoặc handler, cùng fixture độc lập.
- Lưu ví dụ dưới dạng câu hỏi → metric/plan đã duyệt qua một bước review rõ ràng. Dùng index xây lại từ file nguồn, lọc theo catalog và policy trước khi tạo prompt. Chỉ index context được phép dùng, loại dữ liệu giao dịch, thông tin nhận dạng và secrets khỏi nguồn recall.
- Chạy `make test-selection test-security test-benchmark` và kiểm tra overlap chính xác/paraphrase với dev và holdout. So no-few-shot, bank hiện tại và bank mở rộng trên cùng cấu hình. Chỉ bật retrieval mới nếu lợi ích vượt chi phí token/latency và không giảm coverage, accuracy hoặc policy isolation. [Few-shot hiện tại](../../agent4/metric_selection/fewshot.py)

### UP-12 · Release và checkout

- Chốt gate theo bảng bên dưới với người phụ trách sản phẩm và finance reviewer trước khi mở holdout. Chạy `make verify test-mpx10 check-metric-coverage check-catalog-execution eval-validate`, benchmark dev, rồi đánh giá holdout đã duyệt trên ứng viên đã khóa cấu hình. Ghi report theo từng stage, trạng thái còn thiếu và cách quay lại preset/snapshot tốt gần nhất.
- Đồng bộ README, architecture và contracts với API governed hiện tại. `AGENTS.md` đang trỏ tới `docs/architecture.md`, cần bổ sung tài liệu đúng hoặc sửa liên kết. Tách mô tả contract demo/legacy khỏi đường chạy governed. Ghi rõ `make typecheck` hiện kiểm compile Python.
- Git index hiện chứa WrenAI dạng gitlink `160000` và `git submodule status` báo thiếu mapping. Chốt một cách phân phối. Nếu cần checkout WrenAI cùng dự án, đăng ký path `agent4/WrenAI` và URL trong `.gitmodules` tại Git root rồi kiểm tra clone mới ở đúng SHA. Nếu WrenAI chỉ để đọc tham khảo, lưu upstream URL và SHA trong tài liệu và xử lý gitlink khi owner chốt lựa chọn.
- Nghiệm thu khi một checkout mới có thể làm theo tài liệu, dựng hoặc nhận fixture đã version, chạy các gate được ghi và tìm được từng artifact bằng đường dẫn trong báo cáo. Các quyết định đổi contract public, kiến trúc lớn, chính sách quyền, production data hoặc triển khai tuân theo quyền phê duyệt của repo.

## 4. Gate chất lượng và cách vận hành

| Gate | Tiêu chí |
| --- | --- |
| Kiểm tra kỹ thuật | Focused format/lint/compile và test theo Issue. `make verify` ở release. |
| So sánh dev | Dùng baseline tương thích theo runner. Khi catalog, dataset hay phép chấm đổi, chạy lại phiên bản đối chứng trên bộ chung nếu tương thích và ghi rõ phần khác. Nếu runner vẫn từ chối so vì khác catalog, giữ nguyên kiểm tra và lập bảng case chung với giới hạn so sánh được ghi rõ. Mọi thay đổi hành vi cần so stage bị ảnh hưởng và E2E. |
| Quality V1 | Mục tiêu dev tham chiếu từ roadmap gồm Recall@10 ≥ 95%, exact selection ≥ 85%, exact plan ≥ 80%, clarification precision ≥ 95% và status accuracy ≥ 80%. Chốt ngưỡng chính thức theo nhóm và áp thêm gate không hồi quy so với baseline phù hợp. Mốc status 80% thấp hơn artifact V1.1, nên một kết quả chỉ vừa qua 80% chưa đủ để promote. |
| Authorization và SQL | 100% ca security hợp lệ đạt kết quả mong đợi, 0 query vượt scope, 100% query thực thi có safety evidence. Fixture mismatch được chẩn đoán và đưa vào bộ đã version trước khi dùng làm release gate. |
| Số liệu và answer | Báo đúng mẫu số của golden rows và judgments. So khớp số liệu trong các ca bắt buộc với snapshot đã duyệt. Chấm faithfulness và accuracy bằng review độc lập. `null` hoặc thiếu coverage để gate ở trạng thái chưa đạt. |
| Latency và chi phí | Ghi p50/p95, số mẫu, token, model calls và cache. Đo trên cùng runtime và điều kiện cache khi so. Có giá và usage đủ mới tính USD. Chốt ngân sách trước khi promote cấu hình có thêm call hoặc token. |
| Holdout | Reviewer giữ tập riêng có SHA đã duyệt, đối chiếu trùng ý với dev/example bank. Chốt rubric, mẫu số và ngưỡng trước khi chấm. Giữ holdout ngoài việc tune. |

Lệnh tham chiếu cho các Issue ảnh hưởng hành vi. Dùng model revision thực tế, đường dẫn warehouse và tenant của fixture đã khóa từ UP-02. Chọn thư mục output mới mỗi lần. Truyền cùng config vào adapter và runner.

```bash
make help
make format-check lint CHECK_PATHS='agent4/metric_selection tests/contracts'

AGENT4_WAREHOUSE_TENANT_ID=minh-phat \
AGENT4_METRIC_SELECTION_CONFIG=config/eval_governed_lexical.yaml \
make eval PYTHON=.venv/bin/python \
  EVAL_CONFIG=config/eval_governed_lexical.yaml \
  EVAL_SPLIT=dev EVAL_MODE=e2e \
  ADAPTER=agent4.eval_adapter:predict \
  MODEL_VERSION='provider:model:revision' \
  PROMPT_VERSION=metric-selection-v1-structured \
  OUTPUT_DIR=reports/eval/UP-02-baseline-dev
```

Khi có baseline tương thích, truyền `BASELINE=…/summary.json` và file `THRESHOLDS` của Issue. Với holdout, dùng `EVAL_SPLIT=test`, `EVAL_DATASET` và `EVAL_EXTRA` để truyền `--holdout-sha256`, `--example-bank` hoặc `--judgments` theo nhu cầu. Judgments chỉ dùng với prediction hash khớp. Chạy lại một prediction dump đã nhận review để chấm artifact đó qua `PREDICTIONS` thay cho `ADAPTER`.

Mỗi Issue lưu `reports/issues/<ID>_verification.md` cùng đường dẫn tới `summary.json`, `predictions.jsonl`, `cases.jsonl` và `failures.jsonl` nếu có eval. Ghi hypothesis, cấu hình, lệnh, exit code, trước/sau, case thất bại, coverage và điều còn thiếu. Khi không đạt, thử tối đa ba cải tiến có giả thuyết riêng theo issue-loop, giữ kết quả của từng lần và quyết định dựa trên evidence.

Issue mở đầu là **UP-01**. **UP-02 và UP-03** quyết định preset đánh giá chuẩn trước khi thay semantic catalog. Finance reviewer có thể chuẩn bị fixtures và holdout trong thời gian các Issue đầu đang chạy.
