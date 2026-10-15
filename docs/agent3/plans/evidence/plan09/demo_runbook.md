# Demo PLAN_09 — compliance có phạm vi

Ngày 15/10/2026. Đây là tích hợp kỹ thuật; rules/models thực tế vẫn DRAFT, không phải phát hành kết luận thuế. [Gate](../gate_09.md), [recovery](recovery.md), [phạm vi nghiệm thu](compliance_mvp_report.md).

## Dùng UI trên workspace hiện tại

1. Dừng phiên launcher/server cũ, sao lưu DB khi đã đóng kết nối, mở lại `OPEN_AGENT3.cmd`. Migration 009 thêm evaluation snapshots/reports; không ghi đè CFR hoặc outcomes lịch sử.
2. Kết nối như trước, upload PDF/ảnh hoặc mở chứng từ đã có. Đối chiếu nguồn, sửa và **lưu** các trường trước khi kiểm tra.
3. Trong **Kiểm tra phạm vi thuế**, bấm **Kiểm tra bản đã lưu**. UI hiển thị coverage, số unit đã chạy, distinct rule count, yêu cầu người đối chiếu và các bước bổ sung.
4. Mở **Chi tiết kiểm tra và bằng chứng** để xem rule/version, trạng thái planning, nguồn trường và căn cứ registry. **Các lần thực thi** cho biết retry/errors; trace chỉ tải khi yêu cầu.
5. **Xuất kết quả kiểm tra** xuất report cùng CFR đúng revision. **Xuất JSON** ở phần capture tiếp tục hoạt động độc lập khi compliance chưa đủ coverage.
6. Khi sửa chứng từ và lưu revision mới, UI bỏ kết quả của bản cũ khỏi vùng kết quả hiện tại. Bấm kiểm tra lại; lịch sử cũ vẫn đọc được qua API.

Không phải mọi trường đã điền đều đủ tin cậy hoặc đủ căn cứ. Với catalog hiện tại, thấy REVIEW/NO_VERDICT và blocker rule/model chưa duyệt là đúng; không đổi DRAFT hoặc nâng confidence để tạo PASS. Hóa đơn ghi TM/CK không thay bằng chứng thanh toán độc lập.

## Kiểm chứng tự động

Từ `D:\financial`:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\check_compliance_browser.py
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\validate_plan09.py
```

Browser checker dùng Chrome local và Playwright đang có ở `agent3_tax_compliance/data/local_web/browser_tools`; máy mới cần chuẩn bị tooling trước. Checker tạo DB tạm, synthetic reviewed capture và approved models **chỉ trong test**, chạy engine thật, source navigation, export, dirty-draft guard, sửa→đánh giá lại và layout desktop/mobile. Không mở hay sửa DB demo của người dùng. Screenshot local tại `agent3_tax_compliance/data/plan09/browser/`; [browser summary](browser_summary.json) chỉ chứa kết quả tổng hợp.

Validator chạy chín suite, syntax/DOM checks, export schemas và report/manifest. [Synthetic evaluation](synthetic_evaluation.json) và [revision acceptance](revision_acceptance.json) không phải hóa đơn thật hoặc legal labels độc lập. Replay kiểm snapshots/trace/template đã pin, không gọi LLM hoặc chạy lại engine.

Smoke công khai tùy chọn, cần file pilot local và runtime OCR đã cấu hình:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\smoke_plan09_public.py
```

Script dùng một PDF CyberBill công khai đã có trong pilot, production router/OCR và DB tạm. [Kết quả](public_smoke.json) báo riêng; không đo tax accuracy, không dùng nhãn để điền runtime, không gửi chứng từ ra dịch vụ ngoài.

## API

```http
POST /v1/records/{record_id}/evaluations?taxpayer_id={payer}
Authorization: Bearer YOUR_TOKEN
Idempotency-Key: YOUR_REQUEST_KEY
Content-Type: application/json

{"expected_record_revision":2,"version_policy":"CURRENT_VERSIONS","reason":"Đã đối chiếu bản đã lưu"}
```

```http
GET /v1/evaluations/{evaluation_id}?taxpayer_id={payer}
GET /v1/records/{record_id}/evaluations?taxpayer_id={payer}&revision=2
GET /v1/evaluations/{evaluation_id}/rule-results?taxpayer_id={payer}&limit=25&cursor={cursor}
GET /v1/evaluations/{evaluation_id}/rule-results/{result_id}?taxpayer_id={payer}
GET /v1/evaluations/{evaluation_id}/attempts?taxpayer_id={payer}&limit=25&cursor={cursor}
GET /v1/evaluations/{evaluation_id}/export?taxpayer_id={payer}
POST /v1/evaluations/{evaluation_id}/resume?taxpayer_id={payer}
POST /v1/evaluations/{evaluation_id}/replay?taxpayer_id={payer}
```

Tất cả cần bearer auth và tenant/payer scope. Write/replay/resume cần WRITE; đọc cần READ. Cursor có chữ ký, bind evaluation/kind/snapshot/page size/scope; giữ nguyên limit khi dùng trang tiếp. Rule page không chứa raw trace lớn; detail trả trace đầy đủ. GET history hiện trả tối đa 20 evaluation gần nhất của revision; chưa có phân trang lịch sử evaluation dài hạn.

Public `evaluation_id` đại diện yêu cầu toàn luồng; `planning_evaluation_id` và `execution_id` là stage artifacts bên trong. Outcome gốc giữ nguyên key của planning; RuleResultView giữ cả hai ID, không đổi raw engine trace. Một yêu cầu mới có public ID mới; các stage artifacts giống hệt có thể được tái sử dụng an toàn.

CLI local từ thư mục `agent3_tax_compliance`:

```powershell
.\.venv\Scripts\python.exe -m src.orchestration.cli --database "EXISTING_DB.sqlite3" --tenant-id YOUR_TENANT --taxpayer-id YOUR_PAYER --actor-id YOUR_ACTOR --record-id YOUR_RECORD --revision 2 --idempotency-key YOUR_REQUEST_KEY
```

CLI dành cho chủ workspace; không thay cơ chế xác thực HTTP. API không nhận model/JDM, legal approval hoặc payment proof do người gọi tùy ý khai.
