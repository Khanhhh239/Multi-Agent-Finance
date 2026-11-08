# PLAN_08 — chạy ZEN, xem trace và tổng hợp kết quả

Ngày: 15/10/2026. [Gate](../gate_08.md), [kế hoạch thực hiện](implementation_plan.md), [báo cáo tái hiện](validation_summary.json).

## Hiện có gì

Đã có adapter chạy **ZEN thật 0.53.0**, typed context/outcome, process timeout/memory limit, retry hữu hạn, lưu từng attempt và ComplianceResult bất biến, logical replay, aggregator theo unit và API/CLI. Mỗi unit ELIGIBLE được xử lý độc lập; rule khác lỗi hoặc FAIL không làm dừng các unit còn lại.

Catalog có **7 model DRAFT** tương ứng version của ba họ rule PLAN_07. Đây là các bảng kỹ thuật giới hạn, không phải gói luật đã nghiệm thu:

- Content: kiểm tra observation về MST người bán; chưa là kiểm tra toàn bộ nội dung hóa đơn.
- VAT: nhánh minh họa TAXABLE_RATE + REDUCTION_CANDIDATE + rate 0.08; chưa bao phủ mọi nhóm hàng, kỳ và ngoại lệ VAT.
- Non-cash: tiêu thụ proof thanh toán độc lập; không đọc TM/CK trên hóa đơn làm bằng chứng. Ngưỡng/same-day aggregate ở PLAN_07. Trusted sidecar có scope/revision/hash/quality/provenance; chưa có connector nạp/match proof thật hoặc endpoint cho người dùng tự khai proof.

Models thực tế và rules PLAN_07 vẫn DRAFT, mappings hàng thật chưa duyệt. API dùng catalog thật sẽ trả blockers/REVIEW/NO_VERDICT, không chạy rule chưa được phê duyệt. Đường PASS/FAIL/REVIEW qua engine được kiểm chứng bằng **fixture tổng hợp approved riêng cho test**; không đổi catalog thực tế để làm demo PASS.

## Cài và kiểm chứng

Từ workspace gốc, sau khi đã có foundation/ingestion dependencies:

```powershell
python -m pip --python agent3_tax_compliance/.venv/Scripts/python.exe install -r agent3_tax_compliance/requirements-rules.lock
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\validate_plan08.py
```

Validator chạy tám suite và SDK spike, xuất schemas, truth tables và artifact tổng hợp. Các phép đo là kỹ thuật, không đo accuracy hóa đơn thực hoặc SLA production. Test timeout dùng worker thật; ma trận truth table chạy binding thật trong process test để kiểm nhanh toàn bộ tổ hợp; luồng ứng dụng mặc định chạy worker riêng có giới hạn OS. Windows venv cần tối đa hai process cho launcher Python và interpreter con, đều trong job memory/kill limits.

Artifacts:

- [validation_summary.json](validation_summary.json): số test thực chạy, Python/SDK/native binary và implementation/model hashes.
- [money_boundary_probe.json](money_boundary_probe.json), [quyết định Decimal](money_boundary_decision.md).
- [model_truth_tables.json](model_truth_tables.json): mọi tổ hợp boolean của các model DRAFT, kiểm offline; không là legal approval.
- [synthetic_compliance_result.json](synthetic_compliance_result.json): capture/review revision 2 → approved synthetic planning → ZEN process thật → SQLite → replay.

Tạo lại JDM DRAFT từ registry khi cần:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\build_plan08_models.py
```

Builder không tự duyệt hoặc mở rộng support dates. Invoice có ngày từ 15/10/2026 trở đi đang ngoài support snapshot PLAN_07; phải rà và phát hành snapshot mới trước khi đánh giá, không tự dùng latest.

## API và CLI

Khởi động lại launcher/server để nạp routes mới. Sao lưu DB đang dùng trước khi migrate; migration **008** thêm execution runs/attempts/results, không ghi đè CFR và artifacts cũ. API chưa tự gọi sau upload và UI chưa có nút compliance; tích hợp thuộc PLAN_09.

```http
POST /v1/rule-plans/{evaluation_id}/executions?taxpayer_id={taxpayer_id}
Authorization: Bearer YOUR_TOKEN

GET /v1/rule-executions/{execution_id}?taxpayer_id={taxpayer_id}
Authorization: Bearer YOUR_TOKEN

GET /v1/rule-executions/{execution_id}/attempts?taxpayer_id={taxpayer_id}&offset=0&limit=50
Authorization: Bearer YOUR_TOKEN
```

POST cần WRITE; GET cần READ. Mọi truy cập có tenant/taxpayer scope. Attempt page limit 1–200; result hiện trả đầy đủ canonical outcomes và attempts trong execution unit budget, không dùng omitted placeholders. Chưa stream/paginate toàn bộ result lớn; PLAN_09 cần chốt API/UI cho volume đích.

Từ thư mục ứng dụng:

```powershell
.\.venv\Scripts\python.exe -m src.rules.cli --database "EXISTING_DB.sqlite3" --tenant-id YOUR_TENANT --taxpayer-id YOUR_PAYER --actor-id YOUR_ACTOR --evaluation-id YOUR_EVALUATION
```

CLI dành cho chủ workspace local, không phải cơ chế xác thực người dùng từ xa. API không nhận model path/JDM/facts/payment proof tùy ý từ request.

## Cách hiểu kết quả

- SUCCEEDED chỉ có PASS/FAIL/REVIEW, error null; ERROR có result null và code/retry/next_action.
- Coverage đếm **unit**, distinct rule count báo riêng. ERROR không tính là evaluated thành công.
- FAIL giữ nguyên ngay cả khi unit khác lỗi hoặc cần review. Unknown/discovery/missing outcome chặn FULL và PASS.
- Không có in-scope unit: NONE/NO_VERDICT; mọi entry NOT_APPLICABLE có reason riêng. Empty plan là configuration error.
- Contract violation: processing ERROR, verdict null, không gửi sang explainer như một kết luận hợp lệ.
- Unit operational errors trong một plan hợp lệ: PARTIAL_ERROR; giữ NO_VERDICT hoặc FAIL/REVIEW đã có theo precedence. `technical_only=true` luôn có trên output hiện tại.

## Retry, resume và replay

Mặc định tối đa 2 attempts/unit, 10 giây/attempt, 256 MB, 1.000 planned entries/run và 2 MB raw response/attempt. Chỉ timeout được tự retry. Crash, model/input/version/trace sai không tự retry. Callback/audit/persistence lỗi dừng commit, không biến thành PASS.

Execution ID pin plan/package/policy/code. POST lặp lại trả kết quả đã lưu; không chạy lại engine hoặc thêm audit trùng. Lease heartbeat 120 giây; tiến trình dừng giữa chừng có thể resume sau lease hết hạn. Attempt đã commit được giữ, unit đã thành công không chạy lại. Tiến trình cũ bị thay lease không được ghi thêm. Kết quả ERROR đã terminal vẫn bất biến; đánh giá mới cần policy/package/version mới được kiểm soát, không sửa artifact cũ.

Replay kiểm hash/scope, dựng lại facts từ pinned inputs, đọc lại raw trace theo pinned model, chọn terminal và tính lại aggregate. Không đòi native performance timestamps giống nhau và không gọi lại engine trong logical replay. Chạy engine mới là execution mới, không ghi đè raw trace lịch sử.

## Bàn giao PLAN_09

PLAN_09 nhận ComplianceResult, blockers/next actions, canonical outcomes, attempts và trace. Cần nối job/UI và template explanation, hoàn tất API ở volume đích; không bật legal release trước khi duyệt rule/model, mappings và dữ liệu thực. Các giới hạn PLAN_05–07 vẫn được giữ riêng.
