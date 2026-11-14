# R2 — adapter và job model theo doanh nghiệp, CR-012/013 ngày 11/11/2026

**Đã hoàn thành bước chuẩn hóa và phần fit/persist/score theo DN được giao. R2 tổng thể PARTIAL**, không phải nghiệm thu full R2 hoặc duyệt production. Mã mới theo mapping methods/calibration R0; không sửa kernel luật, graph, thống kê hoặc ML cũ. Chưa mở HTTP/UI chấm, ensemble, active config hoặc hàng đợi R3.

**Cập nhật hiện hành CR-013:** [Job model theo DN](company_fit_20261111/REPORT.md). Fit bằng history/reference trước kỳ đánh giá, ghi model/preprocess/full FeatureContract 33 cột vào kho SQLite riêng; score mở kho read-only và không fit lại. Thêm quyền model.fit cho thao tác tạo model, không yêu cầu quyền này khi đọc/chấm. Kiểm full contract/versions trước load; không dùng model/cache legacy hoặc tự suy tương thích từ số cột.

**Kiểm thử bổ sung CR-014:** [Báo cáo adapter R2](adapter_acceptance_20261111/REPORT.md): 32 tests liên quan pass, gồm snapshot riêng đúng 5 giao dịch trả đúng 5 dòng khi có/thiếu/chưa cấu hình model; fit_calls=0 và DB model không đổi. Kiểm thêm full contract 33 cột, format/method/preprocess/runtime/kernel mismatch trước model load. Chỉ thêm tests và sửa tài liệu trạng thái, không thay runtime. [Nghiệm thu kỹ thuật giới hạn R2-04/R2-07](adapter_acceptance_20261111/acceptance.json), không phải gate toàn R2.

- **557 regression tests pass**, 0 skip/failure/error; [kết quả mới](company_fit_20261111/native_tests.json). 30 focused tests source cuối, gồm 17 ca job/missing policy và 13 normalization; auth suite 31 ca đã chạy riêng.
- [Demo process riêng C001/C002](company_fit_20261111/demo_final/summary.json): C001/Isolation Forest, C002/ECOD, mỗi bên train 10/reference 5, nạp từ DB để chấm 5/5 giao dịch mới. Artifact riêng, policy median_flags học từ train; contract input 33, model input 62 sau flags/loại hai cột all-null có lý do. Không phải accuracy 5/5.
- [Fit manifests hiện hành](fit_manifest.json), [parity](parity_report.json), [provenance mới](company_fit_20261111/provenance.json). Bản CR-012 trước giữ tại `company_fit_20261111/prior_R2_*`.

## Hành vi đã có

- Mọi giao dịch có row metadata + một MethodScore cho mỗi phương pháp yêu cầu: raw_score, score_kind, score, available, reason, missing_features và version/source references.
- Điểm luật hợp lệ 0 vẫn available=true. Thiếu artifact/feature hoặc không tương thích/thời gian không hợp lệ trả null, available=false và lý do. Không loại dòng hoặc tự điền 0.
- ML/thống kê được gọi độc lập với rule flags, không top-K nội bộ. Giữ nguồn feature/reference theo DN và contract. Không gọi fit trong inference; không fit reference theo batch test hoặc tự impute/chọn cột từ batch mới.
- GraphEvidence riêng gồm nodes/links/findings/information_gaps/source refs; không có điểm rủi ro. Đúng DN/cutoff mới được trả; weak_context không tự là giao dịch sai.
- Giữ nguyên rule_points và raw anomaly score. Chuẩn hóa ML/thống kê bằng empirical midrank trên reference đã khóa; không gọi là xác suất hoặc cộng trực tiếp với điểm luật khi D-04 còn mở.

Contract/schema: [method_scores.schema.json](../../../agent2/sme_fraud/method_scores.schema.json) trong repo; hướng dẫn dùng tại `agent2/docs/METHOD_OUTPUTS.md`. Schema kiểm output đã chạy trong tests. Các IDs, hash/source text và membership chỉ là metadata/guard, không vào predictor.

## Demo thực tế

Demo normalization CR-012: [demo_output.json](demo_output.json), [log](demo.log). Demo có model bền vững hiện hành ở link CR-013 phía trên; manifest cũ giữ tại `company_fit_20261111/prior_R2_fit_manifest.json`.

1. **Snapshot canonical:** tải/preview/commit thật trong kho demo riêng; 10 history + 5 reference + 5 giao dịch mới. ECOD/RobustZ chấm được cả 5 giao dịch mới. Output giữ đủ 20 dòng; 15 dòng cũ không được chấm ngược bằng reference chứa tương lai của chúng, nên có lý do unavailable. Graph nguồn được biết đúng từng cutoff.
2. **Native đầy đủ nguồn:** gọi nguyên engine luật và graph. Có 5 giao dịch, trong đó **3 dòng điểm luật bằng 0 vẫn được ECOD chấm**, có các điểm ML lần lượt 0,4 / 0,1 / 0,8. Những số đó là midrank bất thường, không phải 40% / 10% / 80% xác suất gian lận. Dòng trúng C2 và dòng có ngữ cảnh C1 cũng được ML chấm; không ưu tiên/lọc row trong adapter.

**Giới hạn quan trọng:** canonical snapshot chưa có bộ chuyển đổi đầy đủ tới các nguồn/chính sách luật legacy. Ở profile đó, rules trả `rule_sources_unavailable` và null; không giả gọi luật bằng các placeholder trong feature projection, không đổi unavailable thành no-hit. Ví dụ no-hit thực sự được chứng minh bằng profile native có score luật 0. Đây là phần bridge còn lại của R2, không được tuyên bố đã nối toàn bộ luật với snapshot mới.

## Kiểm chứng

- **13 focused tests pass:** [kết quả](focused_tests.json), [log](focused_tests.log). Kiểm chấm đủ 5 dòng, no-hit thật, output schema, thiếu artifact/feature, fit spy trong inference, scope/version/checksum, reference cực trị/ties không đổi, thời gian/ID overlap, nguồn graph, thu hồi quyền và CLI snapshot demo.
- [parity_report.json](parity_report.json) được tính bằng `agent2/scripts/check_method_outputs.py`: 5 phương pháp số (RobustZ, ECOD, IF, LOF, AE) đối chiếu frozen fixture theo D-13, atol 1e-8 + rtol 1e-6. Năm dòng native có scores/hits/graph bằng core trực tiếp. Test còn giữ nguyên ngoại lệ tự duyệt được phép, không bỏ hit suppressed có điểm 0.
- Frozen numeric arrays phục vụ parity, có thể lặp giá trị giữa reference/query; không phải tập đánh giá phát hiện ngoài mẫu. Demo nghiệp vụ chia thời gian và ID riêng, nhưng vẫn là nguồn mô phỏng chưa có kết luận xác minh. Không báo precision/recall/accuracy từ các dữ liệu này.
- Lần chạy đầu có 1 failure vì tên NCC mô phỏng đồng dạng của Generator thật sự bị E3 gắn cờ, nên fixture chưa có no-hit: [log gốc](initial_focused_tests.log). Đã dùng một tên NCC riêng biệt trong ví dụ clean-row, giữ nguyên toàn bộ ngưỡng/engine; không xóa cảnh báo thật để báo ML tốt hơn.
- Regression khi giao normalization CR-012: 540 tests pass, 0 skip/failure/error, 209,941 giây; [JSON cũ](native_tests.json), [log cũ](native_tests.log). Sau CR-013 đã chạy lại 557 tests, link đầu báo cáo. R1 evidence/gate cũ được giữ nguyên, không đổi acceptance R1 để làm R2 đạt. Các full regression này không phải formal acceptance của cả R2.

## Fit/reference và phạm vi còn lại

`fit_local_reference` chạy offline với explicit columns/minimum_history/profile. History kết thúc trước reference trên cả hai thời gian; ID giao dịch history/reference không trùng. Inference kiểm reference_end trước event/known-time và không gọi điểm trên chính ID thuộc fit/reference như thể ngoài mẫu. Feature thiếu trả null riêng dòng, không impute. LocalArtifact bất biến chứa model bytes + manifest tenant/DN, feature/preprocess/code/runtime/reference versions, source hashes và diagnostics; scope/hash/version kiểm trước khi giải mã model.

Đây là bytes do code/worker nội bộ tin cậy tạo, không có API nhận pickle hoặc biểu thức từ client. CR-013 đã thêm MethodStore để lưu/nạp sau restart, offline fit job riêng và preprocessing strict/median_flags đóng băng. Khả dụng trong backtest xét điều kiện dữ liệu/tương thích, không giả model đã được triển khai trong quá khứ; prospective còn kiểm thời gian hoàn tất/công bố thực. Active lifecycle/release gate chưa mở.

Chưa hoàn tất: bridge luật canonical, benchmark detector E1–E2/quality gate, scheduler/lease recovery và UI/active lifecycle. Kho artifact/job local, quyền fit và score riêng đã có; không tự đổi latest/active hoặc model của DN khác. EntityDeviation/HBOS chưa thêm vì không có trong catalog được giữ. D-03/D-04/D-09 và triển khai dữ liệu thật vẫn mở theo 99. Ngưỡng minimum_history=5 của demo là điều kiện thử kỹ thuật, không quyết định sản xuất.

Không có formal R2 command mapping hoặc full acceptance report trong phần nhỏ này; không chạy checker để gán READY_FOR_REVIEW cho cả R2. `stage_commands.json` R2 giữ chưa cấu hình cho full milestone. Các kiểm thử kỹ thuật ở trên không thay thế R2-01…07/benchmark khi giao trọn mốc. `normalization_checks.json` và provenance chỉ tổng hợp ca thực đã chạy, không giả human approval.

## Chạy lại

```powershell
cd D:\agent22
& agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/demo_method_scores.py
& agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/run_r1_tests.py `
  --suite test_method_adapters --report agent2/.runtime/method_demo/tests.json
& agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/check_method_outputs.py `
  --output agent2/.runtime/method_demo/parity_report.json
```

Dừng ở các phần CR-012/013 đã giao; không tự chuyển R3, mở active hoặc ghi DONE. Người duyệt/owner nghiệp vụ, ML, triển khai chưa được nhóm chỉ định. [Adapter map](adapter_map.csv), [provenance hiện hành](company_fit_20261111/provenance.json), [artifact manifest hiện hành](company_fit_20261111/artifact_manifest.json).
