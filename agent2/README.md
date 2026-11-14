# Agent2 — pipeline v2.1 và không gian làm việc

**Cập nhật 14/11/2026:** đã sửa [reload Portal giữ đúng C001/C002, màn hình và
snapshot](../reports/portal_company_routing_20261114.md); ghép tương thích với
Portal mới dùng iframe riêng cho từng Agent và giữ cơ chế phiên đăng nhập của
nhóm. [Model bridge mô phỏng](../reports/rule_bridge_models_20261114.md) dùng
Isolation Forest/C001, ECOD/C002 và RobustZ riêng từng doanh nghiệp; model,
database, khóa và cấu hình local không được đưa lên Git, cần chuẩn bị riêng
theo hướng dẫn. Kết quả mô phỏng chưa chứng minh độ chính xác nghiệp vụ thật.

**CR-050: đã nối [đủ 35 luật qua pipeline snapshot nguồn đầy đủ](docs/FULL_RULE_PIPELINE.md)**
tại node doanh nghiệp, có kiểm tra/lưu bất biến, API theo quyền và giao diện.
Nguồn thiếu giữ chưa khả dụng, D/F4 tách khỏi điểm từng giao dịch. Profile
canonical ít cột và luồng HE cũ giữ tương thích; chưa HE 35 luật hoặc chốt
tỷ trọng luật/ML. Có [JSON mẫu](examples/full_rules/README.md).

**Luồng sử dụng hiện tại:** đăng nhập Portal → chọn doanh nghiệp → nhập
CSV/Excel/JSON → kiểm tra và lưu snapshot → chạy phân tích mã hóa → rà giao
dịch có căn cứ → lưu kết quả → tải báo cáo CSV/JSON.

Mở [Công việc Agent2](http://127.0.0.1:8800/agent2/workspace).
Xem [hướng dẫn sử dụng và bộ demo có sẵn](docs/WORKSPACE_GUIDE.md).
Kiểm kê hiện tại: [bảng đủ 35 luật, nguồn thiếu, adapter và HE](../reports/rule_coverage_status_20261114.md).
CR-047: đã có [bộ nguồn và kiểm chứng 35 luật tại node doanh nghiệp](docs/NATIVE_RULE_NODE.md),
chạy local bằng engine giữ lại; chưa mở rộng hợp đồng snapshot hoặc luật HE trên Portal.
CR-048: đã [nối B5/E4 khi đủ nguồn vào pipeline snapshot local](docs/VENDOR_IDENTITY_SNAPSHOT.md)
với input 1.2.0 opt-in. Snapshot có P1/E3/B5/E4; HE chưa mở rộng bởi cập nhật này.
CR-049: [kiểm chứng P1/ML bằng bản mã và so lại baseline bốn luật local](docs/EXPANDED_BASELINE_HE.md).
E3/B5/E4 chưa có HE; không coi phép so sánh này là baseline hoàn toàn mã hóa.
Các mục CR bên dưới là lịch sử triển khai theo thời điểm; chức năng hiện tại
và giới hạn được mô tả trong hướng dẫn mới. Chưa nghiệm thu toàn bộ spec hoặc
hiệu quả nghiệp vụ trên dữ liệu thật.

**CR-040: đã sửa [khôi phục worker chết giữa phép tính](docs/HE_WORKER_RECOVERY.md).** Managed request giữ cùng hash/nonce/context, khóa state độc quyền và attempt fencing; gửi trùng không tạo thêm job logic. Đo lại C001/C002 hard crash 2/2 khôi phục, đủ 5 điểm/DN, không đổi model/khóa. Chỉ trong TTL và state còn nguyên; failed/expired/legacy không tự mở lại. Các dòng HE-AC-01 OPEN/0-of-2 ở báo cáo cũ là lịch sử trước lần sửa này.

**CR-039: chuẩn bị [10 phiếu rà nghiệp vụ mô phỏng](docs/HE_BUSINESS_REVIEW_DEMO.md).** Tệp thử offline riêng, có nguồn/câu hỏi/tài liệu thiếu, kết quả và hữu ích độc lập, đồng hồ trình duyệt chưa xác minh, lịch sử sửa và xuất/tổng hợp JSON. Chưa có kết quả rà của người thật, không nhãn train/queue hoặc mở rộng feature.

**CR-038: thêm [bảng đối chiếu chấm rõ và chấm mã hóa](docs/HE_PLAINTEXT_COMPARISON.md).** Cùng model/snapshot từng DN, đo sai số, thứ tự, thời gian chấm mới và tỷ lệ khôi phục theo loại sự cố; không fit hoặc thay cấu hình Portal. Worker chết giữa compute trước commit vẫn ghi là khôi phục thất bại.

**CR-037: đã nối [Bật/Tắt Agent2 với worker và khôi phục kết nối](docs/HE_MANAGED_WORKER.md).** Portal quản lý đúng cây worker do nó tạo, kiểm DPAPI và signed readiness trước khi chấm; mất worker báo ngắn và tiếp tục cùng job. Model/khóa/phiên giữ nguyên, không fit hoặc plaintext fallback.

**CR-036: đã bật [bộ thử HE trên Portal 8800](docs/HE_PORTAL_ACTIVATION.md).** Agent2 8766 dùng model/snapshot/quyền C001/C002 riêng, worker 8868 chạy ciphertext-only; giữ mật khẩu và DB cũ, Agent1 không restart. Sau người dùng đăng nhập, 7 bước UI live pass: mỗi DN đủ 5 điểm, reload giữ cùng run ID/kết quả. Checker 1.1 khóa snapshot record và có state riêng, không tranh khóa với web.

**CR-035: đã chuẩn bị [bộ C001/C002 lưu bền vững để thử HE](docs/HE_COMPANY_DEMO.md).** Mỗi DN có model fit riêng trên 32 dòng lịch sử + 8 tham chiếu và 5 dòng đánh giá; khóa node DPAPI, thư mục riêng có ACL. Có lệnh prepare/check, không ghi đè hoặc fit khi kiểm tra; chưa bật HE/thay dữ liệu Portal live.

**CR-034: đã nối [giao diện chọn doanh nghiệp → chọn dữ liệu → Chạy phân tích bảo mật](docs/HE_WEB_ANALYSIS.md).** Dùng phiên Portal, model ghim phía server và durable jobs; theo dõi/khôi phục qua reload, điểm giải mã tại DN. Bật bằng cấu hình HE opt-in; chưa nối vào queue hoặc thay luồng bốn nhánh local.

**CR-033: đã bổ sung [bảo vệ khóa và khôi phục phiên tại DN bằng Windows DPAPI](docs/HE_KEYS_AND_SESSIONS.md).** Khóa bọc kho phiên và khóa ký node được bảo vệ theo tài khoản Windows; config 1.2.0 bắt buộc định dạng này. Có lệnh chuyển khóa hex cũ giữ nguyên giá trị/phiên; không tự chuyển khóa live, chưa KMS/rotation hoặc cloud production.

**CR-032: đã có [job HE bền vững: gửi → trạng thái → nhận → giải mã, khôi phục khi mất kết nối/restart](docs/HE_JOB_LIFECYCLE.md).** Idempotency và phiên HE/kết quả mã hóa lưu riêng tại DN, không lưu token; worker chỉ lưu/trả ciphertext. API/CLI giữ cùng yêu cầu sau retry, chưa UI Portal/cloud public hoặc KMS production.

**CR-031: đã tách [node doanh nghiệp và worker bản mã thành hai dịch vụ HTTP thử nghiệm](docs/HE_TWO_SERVICES.md).** Node giữ snapshot/model/HE key và decrypt; worker bundle riêng chỉ kiểm policy và tính ciphertext. Dùng Mahalanobis, grant node ký/được cấp theo DN, không fit trong request. Chỉ loopback, chưa Portal/cloud public hoặc key recovery sau node restart.

**CR-030: đã nối [xuất model từ kho sang luồng HE thử nghiệm](docs/HE_REGISTRY_EXPORT.md).** Adapter Mahalanobis fit offline riêng, lưu MethodStore bất biến; export đọc đúng artifact/DN/full contract 33 feature, mã hóa hai feature được chọn và hệ số, giữ null/lý do cho dòng thiếu nguồn. Chưa HE cho IF/ECOD/LOF/Autoencoder, web hoặc cloud deployment.

**CR-029: đã có [thử nghiệm chấm model trên bản mã](docs/HE_INFERENCE_EXPERIMENT.md)** theo lựa chọn fit tại DN, cloud chỉ chấm. Hai DN, model/đầu vào mã hóa CKKS, worker subprocess không có khóa giải mã; chưa web/cloud deployment hoặc adapter bốn nhánh/33 feature. [Ranh giới ciphertext-only CR-028](docs/ENCRYPTED_CLOUD_BOUNDARY.md) vẫn áp dụng; pipeline web hiện tại vẫn local/plaintext.

**CR-027: đã nối [bốn nhánh phân tích snapshot](docs/FOUR_BRANCH_ANALYSIS.md) lên web/API 1.1.0:** luật, thống kê, đồ thị và ML không nhãn. Model/reference ghim riêng theo tenant/DN, đọc từ MethodStore, không fit trong request; thiếu/sai phiên bản trả chưa khả dụng. Luật canonical ngoài P1/E3 vẫn thiếu evaluator/nguồn theo thực tế; chưa có điểm tổng hoặc queue.

**CR-025: đã nối [phiên đăng nhập và quyền doanh nghiệp Portal](docs/PORTAL_AUTH.md).** Mở http://127.0.0.1:8800/#agent2, đăng nhập/mở khóa Portal một lần rồi dùng Agent2 trong khung hoặc tab riêng, không nhập mã local. Backend xác minh lại phiên và membership mỗi thao tác; profile doanh nghiệp không tự cấp quyền. Portal hiện chỉ có danh tính workspace chung, chưa có tài khoản cá nhân riêng.

**CR-024: đã có màn hình [nhập JSON → kiểm tra → lưu → xem kết quả](docs/IMPORT_WORKBENCH.md) tại http://127.0.0.1:8766/.** Có tệp mẫu 5 giao dịch C001, xác nhận trước lưu và phần chưa đủ nguồn theo từng kiểm tra. Dùng quyền backend hiện có; phiên Portal hiện theo CR-025. Chưa CSV/Excel, ML HTTP hoặc hàng đợi. Các cập nhật dưới đây là lịch sử theo từng CR.

CR-023 đã nối [API phân tích snapshot P1/E3](docs/SNAPSHOT_ANALYSIS_API.md): `POST /api/v1/companies/{company_id}/snapshots/{snapshot_id}/analyze`, body có as_of bắt buộc. Kế toán nhận DTO nghiệp vụ; view technical chỉ director đúng DN. Phân tích chỉ đọc, không fit/model/queue, nhóm trả một lần và giữ đủ dòng khả dụng. Chạy demo HTTP: `scripts/demo_snapshot_analysis.py --output-dir <thư-mục-mới>`. UI nhập và xem kết quả hiện theo CR-024 ở trên.

CR-022 sửa guard thời gian P1 native cho hóa đơn khai báo biết/phát hành sau cutoff, gồm current/lịch sử/nhóm đồng thời. Thiếu nguồn tạo information_gap 0 điểm, không phải no-hit; canonical vẫn unavailable/null. Xem [trạng thái và giới hạn P1](docs/P1_EVALUATION.md). Giữ bộ 33 feature và model; chưa mở UI/queue mới.

CR-019 đã nối [bộ đánh giá P1](docs/P1_EVALUATION.md): lịch sử thanh toán, nhóm đồng thời và điều chỉnh có dấu từ [đầu vào 1.1.0](docs/P1_INPUTS.md). Thiếu nguồn vẫn unavailable/null; tổng luật canonical chưa đầy đủ. Không đổi feature/model hoặc active.

CR-017 bổ sung [đối chiếu điểm/cảnh báo/ngoại lệ](docs/RULE_PARITY.md) với engine gốc trên cùng nguồn native. Output 1.1.0 giữ cả batch events/ngoại lệ trong native_rule_diagnostics; không đổi điểm dòng hoặc kernel.

CR-016 đã có [kết quả từng luật](docs/RULE_RESULTS.md): E3 được đánh giá khi đủ nguồn, tách hit/no-hit khỏi unavailable và not_applicable. Giữ điểm gốc và đóng góp theo policy, có source/evidence references; chưa có tổng điểm luật canonical đầy đủ.

CR-015 bổ sung `sme_fraud/rule_sources.py` và [bản đồ nguồn 35 luật](docs/RULE_SOURCE_MAP.md). Kết quả snapshot/CLI score có `methods.rules.details.rule_inputs` theo từng giao dịch và cutoff. Đây là lớp nối nguồn, chưa phải bộ tính điểm luật canonical; không biến thiếu nguồn thành điểm 0.

Đã dọn bản làm việc ngày 10/11/2026 theo chỉ đạo mới. Đặc tả chuẩn: [Agent2_Spec_v2_1](../Agent2_Spec_v2_1/00_INDEX_va_quy_tac.md). Trạng thái hiện tại: **R1 chờ rà duyệt + MethodScore/GraphEvidence và job/model store theo DN thuộc R2**, chưa phải pipeline v2.1 hoàn chỉnh.

Đã có [hợp đồng đầu vào 1.0.0](docs/INPUT_DATA_CONTRACT.md), package chung `shared/finance_input` và profile `sme_fraud/imports.py`; kiểm số tiền có dấu, nguồn/thời điểm, định danh/phạm vi và liên kết. [API kiểm tra đầu vào](docs/BACKEND_VALIDATION.md) dùng auth policy backend: `POST /api/v1/companies/{company_id}/imports/validate`; validator/report 1.1.0, lỗi có dòng/trường/cách sửa và giới hạn nguồn theo giao dịch. Snapshot và feature theo CR-007/008 bên dưới đã nối; identity/membership Portal chưa nối.

**Cập nhật CR-007:** đã có [upload JSON → preview → xác nhận → snapshot bất biến](docs/IMMUTABLE_SNAPSHOTS.md) khi cấu hình auth và DB snapshot mới riêng. Đổi source/mapping tạo revision và phải preview lại; commit có idempotency, transaction và checksum; không ghi đè snapshot cũ. Màn hình/CSV/Excel/Portal identity và feature replay còn chờ. Chạy thử trọn luồng: `.venv/Scripts/python.exe -X utf8 -B scripts/demo_snapshot_flow.py` (chỉ dữ liệu mô phỏng, kho riêng).

**Cập nhật CR-008:** đã nối [feature theo thời điểm từ snapshot](docs/SNAPSHOT_FEATURES.md), gọi nguyên core qua adapter version mới, 33 predictor số có missing mask. ID/revision ở rows, nguồn đối chiếu ở evidence; nhãn không vào ma trận. Chạy demo: `& .venv/Scripts/python.exe -X utf8 -B scripts/demo_snapshot_features.py`. Riêng bước feature này không fit/chấm ML; adapter R2 theo CR-012 được mô tả bên dưới.

## Thành phần giữ lại

| Nhóm | Mã chính | Ý nghĩa đầu ra |
| --- | --- | --- |
| Luật cứng | `sme_fraud/rules.py`, các policy/bằng chứng phụ thuộc | Điểm luật, hit, ngoại lệ và căn cứ |
| Thống kê/điểm | `benford.py`, `dynamic_thresholds.py`, `score_statistics.py`, `unsupervised_statistics.py` | P-value, ngưỡng lịch sử, midrank và độ bất thường; không tự là xác suất gian lận |
| Đồ thị | `identity_graph.py`, `entity_graph.py` | Liên kết theo công ty và thời điểm đã biết |
| ML không nhãn | `ml_estimators.py` | Isolation Forest, ECOD, LOF, Autoencoder; phải fit lịch sử trước khi score |

Giữ thêm feature, accounting, schema, định danh và hàm sinh fixture vì các lõi trên phụ thuộc chúng. Generator và `rule_audit_cases.py` phục vụ fixture kiểm thử; nhãn mô phỏng không là đầu vào fit của ML được giữ lại. Các lớp RobustZ, TailExceedance, ShrunkMahalanobis, MaskedField và Reference được tách nguyên thuật toán khỏi bộ chọn model bằng tiêm mẫu cũ.

## Phần cũ đã đưa ra ngoài workspace

Web nghiệp vụ, nhập dữ liệu, quản lý model/nhãn, phiếu rà, hàng đợi, notification, benchmark/release cũ, dữ liệu/model/runtime và báo cáo cũ nằm tại **`D:/agent22_legacy_20261110/agent2`**. Môi trường `.venv` được dùng lại tại vị trí cũ để tránh cài lại thư viện. Mã và dữ liệu cũ không được chạy bởi bản core-only.

CatBoost và cơ chế chọn model bằng tiêm mẫu không còn trong catalog đang dùng. Đã có [MethodScore/unavailable và GraphEvidence](docs/METHOD_OUTPUTS.md): chấm đủ dòng, không lọc hit trước ML; graph chỉ cung cấp liên kết/bằng chứng. Native đủ nguồn dùng nguyên luật cũ; canonical snapshot chưa có bridge luật đầy đủ thì unavailable rõ. Đã có [job fit và kho model bền vững theo DN](docs/COMPANY_MODEL_JOBS.md), lưu contract 33 cột, missing policy và versions; score nạp read-only, không fit lại hoặc tự dùng model legacy. Chưa bổ sung EntityDeviation/HBOS hoặc benchmark R2 đầy đủ. Chưa chốt trọng số, ngưỡng, budget hay probability calibration cho bản mới.

Demo chuẩn hóa: `& .venv/Scripts/python.exe -X utf8 -u -B scripts/demo_method_scores.py`. Chỉ nguồn mô phỏng; xem [báo cáo bước adapter R2](../Agent2_Spec_v2_1/evidence/R2/REPORT.md). HTTP hiện nối cả bốn nhánh theo CR-027; canonical rules vẫn mới có P1/E3, chưa có active queue.

Demo fit/score qua process riêng: `& .venv/Scripts/python.exe -X utf8 -u -B scripts/demo_company_models.py`. C001 dùng Isolation Forest, C002 dùng ECOD; model lưu trong DB local mới riêng, không dùng model cũ. Quyền fit backend cần `model.fit` và `data.import`; đọc/chấm chỉ cần `data.import`.

## Kiểm tra lõi

```powershell
cd D:\agent22\agent2
$env:PYTHONPATH='.;tests'
& .venv/Scripts/python.exe -B -m unittest discover -s tests
& .venv/Scripts/python.exe -B -m sme_fraud.core_manifest
```

`requirements-lock.txt` ghi đúng phiên bản đã kiểm tra trong môi trường hiện tại. Python được kiểm kê tại evidence/R0/environment.json của bộ đặc tả.

## Màn hình local và trạng thái

```powershell
& .venv/Scripts/python.exe -B start_review.py --port 8766
```

Lệnh trên chỉ bật backend standalone theo cấu hình được cấp; để chạy bộ demo
đã cấu hình worker/khóa/quyền, dùng Portal 8800 → **Bật Agent2**. Trang chủ
Agent2 có cấu hình HE4 là không gian **Công việc**; `/data-import` nhận
CSV/Excel/JSON theo mẫu, `/encrypted-analysis` chạy và theo dõi, `/status`
giữ thông tin trạng thái. API cũ đã loại bỏ vẫn trả 410. Các API mới kiểm
quyền trước khi xử lý; chấm không tự fit model. Xem [hướng dẫn](docs/WORKSPACE_GUIDE.md).

## Tiếp theo

Rà thử các phiếu mô phỏng theo [hướng dẫn](docs/WORKSPACE_GUIDE.md), sau đó
đối chiếu nguồn thật cùng người hiểu nghiệp vụ. Toàn catalog luật, model HE
ngoài các profile đã kiểm chứng, hiệu quả nghiệp vụ, danh tính từng người rà,
chính sách tổng hợp/queue và triển khai production vẫn cần phần việc riêng.
Báo cáo kỹ thuật mới: [workspace core](../Agent2_Spec_v2_1/evidence/R5/workspace_core_20261113/REPORT.md).
