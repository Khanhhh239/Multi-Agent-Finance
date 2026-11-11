# V0 — Tổng hợp triển khai, kiểm thử và benchmark

**Mốc tổng hợp:** 11/11/2026. Báo cáo gom các kết quả đã ghi nhận của M0–M4 và tích hợp kho MPX10 để làm căn cứ chọn hướng tiếp theo.

Pipeline V0 đã có luồng từ câu hỏi, chọn metric, lập plan, biên dịch SQL, thực thi DuckDB đọc-only đến trả lời có bằng chứng. Lần chạy `make verify` toàn repo gần nhất đạt **513 test**. Benchmark thực tế tốt nhất khớp **trạng thái cuối 80/140 ca dev (57,1%)**, chọn chính xác tập metric **49/140** và khớp plan **28/140**. V0 còn thiếu bằng chứng để nghiệm thu phát hành. [Báo cáo M4.3](issues/M4.3_verification.md)

## 1. Đã triển khai theo từng M

| M | Phần đã triển khai | Phạm vi đã xác minh |
| --- | --- | --- |
| **M0 — Core & Catalog** | Chuẩn hóa request, ngữ cảnh quyền, lỗi và catalog thực thi. Catalog M0.2 có 15 định nghĩa, trong đó 13 metric có handler đã xác minh. | 14/14 test Core/Catalog. [M0.1](issues/M0.1_verification.md) · [M0.2](issues/M0.2_verification_vi.md) |
| **M1 — Metric Selection** | Adapter canonical 66 metric, embedding và index offline, retrieval dense/lexical/hybrid, RRF và rerank, few-shot theo cấu hình, selector Qwen, metric validation, recovery có giới hạn và cache L1/L2 theo tenant, policy, catalog. | 106 test ở lần chạy target selection. Đã đo retrieval E1/E2 và đối chiếu cache nguội/ấm M1.4 bằng preset structured dev. Cấu hình Qwen3 mặc định và các thí nghiệm ablation còn mở. [M1.3](issues/M1.3_verification_vi.md) · [M1.4](issues/M1.4_verification.md) |
| **M2 — Planning & Clarification** | Semantic planner và plan validator cho metric, kỳ, dimension, filter, view và giới hạn. Chế độ `guided` gợi ý các lựa chọn được phép và tiếp tục qua session đa lượt có TTL, kiểm tra lại quyền trước khi xác thực plan. | 115 test planning ở lần chạy cuối. Benchmark thành phần giữ 15/15 ca clarification so với M2.2. [M2.2](issues/M2.2_verification_vi.md) · [M2.3](issues/M2.3_verification.md) |
| **M3 — SQL Engine** | Compiler tham số hóa từ plan đã xác thực và binding M0.2. Safety gate kiểm tra nguồn, projection, bind params, giới hạn và quyền trước khi executor mở kho. DuckDB đọc-only, tắt external access, áp deadline và cache L3 theo scope cùng phiên bản dữ liệu. | 38 test SQL và 12 test security tại gate M3.3. Đã chạy trên kho thật và kiểm tra các trường hợp timeout, mất file, phục hồi và cách ly cache. [M3.1](issues/M3.1_verification.md) · [M3.2](issues/M3.2_verification.md) · [M3.3](issues/M3.3_verification.md) |
| **M4 — Answer, API & Benchmark** | Xác thực bảng kết quả, trả lời song ngữ có dẫn chứng, fallback và evidence preview tối đa 5 dòng. Pipeline và `POST /v1/query` giữ 9 trường phản hồi mặc định, hỗ trợ bật evidence, hỏi lại đa lượt và tắt cache. Runner benchmark đi qua pipeline thực. | 15 test answer, 4 ca tích hợp API theo báo cáo M4.2, smoke có Ollama và 3 lượt benchmark đủ 140 ca dev. [M4.1](issues/M4.1_verification.md) · [M4.2](issues/M4.2_verification.md) · [M4.3](issues/M4.3_verification.md) |

Kho **MPX10 v3** đã tích hợp, có khoảng **19,8 triệu dòng sổ cái**. Đối soát dữ liệu đạt **32/32 kiểm tra và 5/5 tình huống**. Catalog M0 chạy **29/29 cặp metric/view** trên kho. Mốc **56/66** đến từ compiler tham chiếu `platform-Khanh`. Phạm vi của compiler V0 hiện là các binding đã xác minh trong M0.2. [Báo cáo MPX10](issues/MPX10_warehouse_verification.md)

## 2. Kiểm thử đã chạy

- `make verify PYTHON=.venv/bin/python` toàn repo thoát `0`, gồm Ruff format, Ruff lint, `compileall` và **513 test pass**. Target `typecheck` hiện dùng `compileall`. Lượt test đầy đủ chạy ngoài sandbox vì worker thread của test async bị treo trong sandbox. Các lỗi format và lint cũ cản gate toàn repo đã được dọn trong lượt triển khai. [Bằng chứng và lệnh chạy](issues/M4.3_verification.md)
- Các bộ test thành phần trong bảng thuộc suite toàn repo và phản ánh mốc kiểm tra của từng M. Bộ tích hợp API dùng selector giả lập cùng DuckDB thật để kiểm tra quyền, session, cache và telemetry. Các lượt smoke và benchmark E2E bên dưới gọi Ollama thật. [Thiết lập kiểm tra API](issues/M4.2_verification.md)
- Fixture benchmark v1 **120 ca** được giữ để chạy hồi quy. Đánh giá pipeline V0 dùng bộ v2 **140 ca dev** theo đặc tả đánh giá. [Protocol và dataset](../docs/evaluation.md)

## 3. Benchmark thành phần

### M1 — Retrieval và cache

| Retrieval trên 140 ca dev | Complete Gold Set Recall@5 | Complete Gold Set Recall@12 | MRR | Recall đầy đủ@5, nhóm nhiều metric |
| --- | ---: | ---: | ---: | ---: |
| E1 · Dense | 86,67% | 98,33% | 0,7113 | 55% |
| E2 · Hybrid | 97,50% | 98,33% | 0,9183 | 90% |

Recall tính trên 120 ca có gold metric. Hai ca BM-114 và BM-138 có `labor_cost` trong gold set, còn policy loại metric đó khỏi ứng viên được phép. Hồ sơ E0 có phép đo tầng ứng viên và còn thiếu lượt full-catalog selection hoàn chỉnh. E3/E4 chưa có ablation static/dynamic. Đối chiếu cache M1.4 dùng adapter selection thực và giữ nguyên cấu hình recovery giữa hai lượt, nên phép đo ablation riêng cho recovery vẫn còn mở. [E0](issues/M1.0_verification.md) · [E1](eval/M1_retrieval_dense_ks/summary.json) · [E2](eval/M1_retrieval_hybrid_ollama/summary.json) · [Báo cáo E0–E5](issues/M1.3_verification_vi.md)

| M1.4 · Selection trên cùng 140 ca dev | Cache nguội | Cache ấm |
| --- | ---: | ---: |
| Exact metric selection | 78/140 | 78/140 |
| Độ trễ P50 | 2.500,18 ms | 0,379 ms |
| Độ trễ P95 | 3.008,95 ms | 2.481,60 ms |
| Token trung bình trên 133 mẫu mỗi lượt | 969,40 | 87,10 |

Hai lượt trong cùng process đều thoát `0`, đầu ra nghiệp vụ trùng **140/140**, có **121 hit selection quan sát được** qua token chuyển từ có sử dụng sang 0 và 7 ca selection invalid lặp lại. Preset thử nghiệm dùng `qwen2.5:0.5b` với JSON Schema, embedding `qwen3-embedding:0.6b` và hybrid index 66 metric. `qwen3:4b` mặc định vẫn có lỗi `invalid_request` ở BM-001 ngay cả khi tắt cache. Phản hồi Ollama bị cắt ở giới hạn sinh và không parse được JSON trong lượt chẩn đoán. Chưa có phép đo nguội/ấm đủ 140 ca hợp lệ cho Qwen3 mặc định. [Báo cáo M1.4](issues/M1.4_verification.md) · [Đối chiếu từng ca](eval/M1.4_selection_cache_dev/comparison.json)

### M2 — Planning và clarification

Benchmark thành phần với adapter `agent4.planning.eval_adapter:predict_validated` giữ **15/15 ca khớp plan và trạng thái**, 0 lỗi so với baseline M2.2. Lượt cuối P50 **1,194 ms**, P95 **9,166 ms**, không gọi model. Hội thoại đa lượt có test contract riêng. [Baseline M2.2](eval/M2.2_clarification_final/summary.json) · [Kết quả M2.3](eval/M2.3_clarification_final/summary.json)

## 4. Benchmark E2E

Smoke M4.2 trên BM-001 và BM-112 cho thấy Qwen3 mặc định khớp trạng thái **1/2** và chưa chạy SQL. Preset `qwen2.5:0.5b` structured khớp **2/2**, chạy qua DuckDB và sinh câu trả lời ở BM-001, từ chối truy cập ở BM-112. Phép so sánh đổi đồng thời model và cấu hình. [Qwen3 mặc định](eval/M4.2_production_dev_smoke/summary.json) · [Qwen2.5 structured](eval/M4.2_structured_dev_smoke/summary.json)

M4.3 chạy `agent4.eval_adapter:predict` trên cùng **140 ca v2 dev**, seed `20261101`, kho MPX10 v3, `qwen2.5:0.5b@a8b0c5157701` và prompt `metric-selection-v1-structured`. Lượt 2 thêm kiểm tra phạm vi yêu cầu trước selection. Lượt 3 dùng lexical top 8 và tắt mở rộng quan hệ. Cả ba lượt ghi đủ artifact, runner trả exit `1` do còn ca được phân loại là lỗi runtime. [Cấu hình, baseline và lệnh tái lập](issues/M4.3_verification.md)

| Chỉ số | Lượt 1 · Baseline | Lượt 2 · Kiểm tra phạm vi | Lượt 3 · Lexical top 8 |
| --- | ---: | ---: | ---: |
| Khớp trạng thái cuối | 55/140 | 66/140 | **80/140** |
| Khớp chính xác tập metric | 27/140 | 35/140 | **49/140** |
| Khớp chính xác plan | 17/140 | 17/140 | **28/140** |
| SQL hoàn tất / đã thực thi | 37/37 | 35/35 | 50/50 |
| Ca gắn nhãn an toàn đạt theo runner | 4/15 | 13/15 | 13/15 |
| Độ trễ P50 / P95 | 1,007 s / 2,212 s | 1,030 s / 2,070 s | 1,456 s / 2,053 s |
| Token trung bình (số mẫu) | 1.065,04 (120) | 1.075,90 (115) | 607,00 (117) |
| Ca có đối soát số liệu và câu trả lời độc lập | 0/140 | 0/140 | 0/140 |

`80/140` đo khớp trạng thái, gồm cả các trạng thái từ chối hay cần hỏi lại. `50/50` đo số lệnh SQL chạy xong trong số lệnh được thực thi. Độ chính xác số liệu, chất lượng câu trả lời và chi phí USD đều chưa đo trong benchmark này. [Baseline](eval/M4.3_governed_dev/summary.json) · [Lượt 2](eval/M4.3_governed_dev_scope/summary.json) · [Lượt 3](eval/M4.3_governed_dev_lexical/summary.json) · [Danh sách ca lỗi](eval/M4.3_governed_dev_lexical/failures.jsonl)

- Kiểm tra quyền sớm giúp BM-114 và BM-138 dừng trước model và SQL, tránh việc trả một metric được phép thay cho metric bị cấm mà người dùng hỏi. BM-111 nhận diện view thuế và BM-115–BM-118 dừng trước thực thi. [Phân tích từng ca](issues/M4.3_verification.md)
- So với lượt 2, preset lexical cải thiện nhóm dimension/filter/top-k **4→15/20** và multi-metric **7→11/20**. Nhóm aggregate giảm **15→13/20**, clarification **14→13/15** và no-data/edge **3→2/8**. BM-100 ngoài catalog được từ chối trước SQL. [Phân tích từng nhóm](issues/M4.3_verification.md)
- **BM-119 và BM-120** vẫn dừng ở plan validation. Lượt 3 chọn `operating_expense`, còn binding M0.2 của metric này thiếu filter theo nhà cung cấp. Bộ v2 dùng canonical ID `operating_expenses`. Đây là hai ca còn trượt trong 15 ca gắn nhãn an toàn. [Kết quả từng ca](eval/M4.3_governed_dev_lexical/cases.jsonl)

## 5. Các điểm còn mở để quyết định

| Phạm vi | Hiện trạng |
| --- | --- |
| **Catalog và phạm vi hỗ trợ** | Catalog canonical dùng để định nghĩa bộ v2 có 66 metric. Pipeline thực thi hiện chạy trên binding M0.2. Các mapping canonical, định nghĩa nghiệp vụ, chiều và bộ lọc bổ sung cần được đối soát trước khi tính là được hỗ trợ. Chênh namespace cũng ảnh hưởng điểm exact match. |
| **Model và retrieval mặc định** | Đã có preset structured dev chạy hết 140 ca, với kết quả và các nhóm hồi quy ở trên. Qwen3 mặc định còn lỗi định dạng. E0 full selection, E3/E4 và phép đo riêng hiệu quả recovery còn thiếu. |
| **Nghiệm thu phát hành** | 140 ca v2 hiện là dev draft. Cần bộ test độc lập được niêm phong, ngưỡng do owner chốt và số liệu/câu trả lời được đối soát độc lập. Kết quả hiện tại chỉ hỗ trợ đánh giá trên dev. |
| **Tích hợp khi triển khai** | Host cần cung cấp claims đã xác minh, policy và mapping tenant → kho cho API. Clarification session hiện lưu trong process, cần xem lại vòng đời session nếu triển khai nhiều worker. |

[Issue index M0–M4](../docs/issues/README.md) · [Tiêu chí M4.3](../docs/issues/M4.3_full_benchmark.md) · [Hướng dẫn tích hợp API](../README.md)
