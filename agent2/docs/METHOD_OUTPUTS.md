# Cập nhật CR-027

[API/UI bốn nhánh](FOUR_BRANCH_ANALYSIS.md) đã nối các adapter này với ModelStore chỉ đọc và binding artifact theo DN. Nội dung CR-023 bên dưới ghi phạm vi cũ P1/E3; core MethodScore/GraphEvidence không đổi.

# Đầu ra theo giao dịch — bước adapter R2

Đã có `sme_fraud/method_adapters.py`, contract `method-output/1.1.0` và schema `sme_fraud/method_scores.schema.json`. Adapter dùng được với [job fit/kho model bền vững](COMPANY_MODEL_JOBS.md) tại backend/CLI; chưa nối UI, ensemble hoặc hàng đợi.

CR-017 thêm [đối chiếu và native diagnostics](RULE_PARITY.md): profile native giữ cả cảnh báo/ngoại lệ sau đóng nhóm tại top-level native_rule_diagnostics, không cộng lại vào điểm dòng. Output snapshot canonical không giả có native diagnostics khi chưa chạy đủ engine native.

Mỗi giao dịch luôn có một dòng, với tenant, doanh nghiệp, ID, revision và mốc thời gian. `methods` chứa kết quả riêng của luật, thống kê và từng ML được yêu cầu; `graph` chứa liên kết/bằng chứng. Không lọc theo hit luật hoặc top-K trước khi chấm.

| Trường | Ý nghĩa |
|---|---|
| raw_score | Điểm gốc của phương pháp |
| score | Điểm luật nguyên bản, hoặc midrank trên reference lịch sử đã khóa |
| score_kind | rule_points / empirical_midrank; không cộng trực tiếp hai thang này |
| available | Có đủ feature/artifact đúng phiên bản và thời gian để chấm hay không |
| reason | Code/thông báo khi chưa khả dụng; nếu khả dụng thì null |
| missing_features | Các biến model cần nhưng nguồn chưa có |
| artifact_id, preprocess_version, reference_version | Phiên bản model/tiền xử lý/reference dùng cho dòng đó |
| evidence_refs, details | Nguồn đối chiếu, hit/ngoại lệ nguyên bản và lý do thiếu feature |

**Điểm 0 hợp lệ:** available=true, raw_score/score=0. **Chưa đủ dữ liệu:** available=false, raw_score/score=null và có reason; không thay bằng 0 hoặc loại dòng. Điểm ML cao là bất thường hơn so với reference, không phải tỷ lệ gian lận. Chưa chọn trọng số hoặc xác suất tổng hợp.

Đồ thị không có điểm rủi ro. GraphEvidence trả nodes, links, findings, information_gaps, source references và available/reason. Giữ phân loại weak_context; có liên kết không tự xác nhận giao dịch sai. Đồ thị phải đúng DN/thời điểm của giao dịch; reference tới tương lai bị chặn.

## Hai profile đầu vào

- `native_inputs`: bộ bảng legacy đầy đủ, đúng một DN; gọi nguyên `build_features`, `score_rules`, `EntityGraph`. Điểm/hit/ngoại lệ giữ nguyên. Labels/splits không vào ma trận hay nguồn chấm. Metadata thời gian giữ `posted_at` theo ngữ nghĩa engine legacy, được phân biệt bằng feature contract; không tự gọi đây là effective_at của canonical.
- `score_snapshot`: snapshot R1 đã kiểm quyền/checksum; tạo feature và graph theo từng cutoff. **Chưa có bridge đầy đủ từ canonical snapshot sang mọi nguồn luật cũ**, nên rules unavailable rõ, không giả điểm luật 0. ML/thống kê vẫn chấm các dòng đủ feature/model. Không gọi luật bằng DTO placeholder của feature projection.

`score_batch` là hợp đồng dùng chung, gọi mọi ML/statistical adapter độc lập với kết quả luật. Luồng snapshot kiểm lại quyền trước khi trả kết quả. Đây là API Python nội bộ với AccessScope từ backend. CR-023 thêm [HTTP P1/E3](SNAPSHOT_ANALYSIS_API.md) với DTO allowlist theo vai trò; không trả toàn bộ MethodScore/thuật toán cho kế toán hoặc mở HTTP ML.

## Fit và inference

CR-016 bổ sung [kết quả từng luật](RULE_RESULTS.md) tại `details.rule_results`: phân biệt evaluated_hit, evaluated_no_hit, unavailable và not_applicable. E3 chạy bằng helper/policy mặc định giữ lại khi đủ nguồn; điểm master-quality 0 vẫn có thể matched=true với intrinsic_points=3. CR-019 thêm [P1](P1_EVALUATION.md) và kiểm nhóm đồng thời riêng trong RuleResult.details; điểm nhóm không cộng vào điểm dòng. Điểm tổng canonical chưa đầy đủ vẫn null, reason=rules_incomplete; không cộng tổng một phần.

CR-015 đã nối [đầu vào nguồn cho từng luật](RULE_SOURCE_MAP.md): `methods.rules.details.rule_inputs` có catalog 35 luật, nguồn/field/reference còn thiếu và trạng thái dữ liệu. Resolver giữ payload nguồn ở kênh riêng, không đưa vào predictor; `ready` nghĩa là đủ các trường đã khai báo trong snapshot, chưa phải đã chạy evaluator. Điểm tổng luật vẫn unavailable/null cho tới khi adapter đánh giá luật canonical được đối chiếu đầy đủ.

`fit_local_reference` là bước offline tách khỏi inference: fit trên history, score reference giữ lại sau history, lưu preprocess/feature/runtime/code versions và reference hash trong LocalArtifact bất biến. History/reference không được trùng ID giao dịch; query đã thuộc fit/reference không được coi như chấm ngoài mẫu. Dữ liệu fit/reference phải kết thúc trước cả event-time và known-time của dòng được chấm. available trong demo/backtest nói về đủ nguồn/khả năng tính và tương thích, chưa xác nhận model từng được triển khai/duyệt tại một mốc lịch sử; deployment lifecycle còn thuộc worker/registry và release gate phía sau.

Selected columns và minimum_history/profile phải được khai báo rõ. Helper mặc định strict: thiếu biến cần dùng thì fit bị từ chối hoặc inference trả unavailable riêng dòng. Job bền vững có thể chọn median_flags rõ trong config, học median/cờ thiếu chỉ từ train; không tự đổi policy hoặc học lại từ batch test. Xem [chính sách thiếu theo model](COMPANY_MODEL_JOBS.md). Model được giữ lại: ECOD, IF, LOF, Autoencoder và thống kê RobustZ. Kernel không đổi. Reference midrank dùng hàm cũ, ties lấy midrank; thêm outlier vào batch test không đổi reference hoặc điểm các dòng còn lại.

LocalArtifact là bytes do worker/code nội bộ tin cậy tạo, chưa nhận pickle/file model từ HTTP. CR-013 đã thêm [MethodStore và job fit/score riêng](COMPANY_MODEL_JOBS.md), lưu bundle qua restart; demo normalization cũ vẫn dùng bundle ở bộ nhớ. Chưa có scheduler/recovery hoặc active lifecycle hoàn chỉnh. `minimum_history=5` trong demo là điều kiện kỹ thuật thử, không phê duyệt ngưỡng sản xuất D-03. Không thay active config/queue hoặc chốt D-04/D-09.

## Chạy demo

```powershell
cd D:\agent22
& agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/demo_method_scores.py
```

Demo tạo snapshot mô phỏng gồm 10 history + 5 reference + 5 giao dịch mới; chấm 5 giao dịch mới bằng ECOD/RobustZ. Kết quả vẫn giữ đủ 20 dòng: model mới không được chấm ngược 15 dòng cũ nên những dòng đó có lý do unavailable. Có thêm ví dụ native 5 dòng, trong đó ba dòng điểm luật 0 vẫn được ML chấm. Tệp kết quả mặc định `.runtime/method_demo/output.json`; không có nhãn xác minh hoặc kết luận accuracy.

Kiểm tra parity:

```powershell
& agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/check_method_outputs.py `
  --output agent2/.runtime/method_demo/parity_report.json
```

Đọc [báo cáo R2 hiện hành](../../Agent2_Spec_v2_1/evidence/R2/REPORT.md). Kho/job local đã bền vững; bridge luật canonical, benchmark theo thời gian/nghiệp vụ và vòng đời active/recovery vẫn cần hoàn tất.
