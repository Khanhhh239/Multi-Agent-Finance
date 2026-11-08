# Hoàn thiện đầu vào nghiệp vụ PLAN_09 — 16/10/2026

Đã triển khai bảng quyết định và lớp chuẩn bị nghiệp vụ cho ba nhóm rule: hiện diện MST người bán, VAT giảm thuế và chứng cứ thanh toán. Trạng thái **IMPLEMENTED_TECHNICAL**, chưa phát hành kết luận thuế thật. Người dùng xác nhận **chưa có danh mục sản phẩm**: mapping SKU thật và nghiệm thu nghiệp vụ tiếp tục PENDING. OCR V2 vẫn thuộc PLAN_06; PLAN_14 chưa bắt đầu.

Kết quả: **416/416 Python tests PASS**, gồm **32 ca mới**; Chrome **11 nhóm kiểm tra PASS**. Không có test bị skip. Những số này đo chức năng kỹ thuật trên fixture, không phải độ chính xác thuế thực tế.

[Bảng quyết định](DECISION_TABLE.md) · [Kiểm thử](validation_summary.json) · [Schema](../../../../../../agent3_tax_compliance/contracts/business-review-v1/ReviewDossier.schema.json) · [Template](../../../../../../agent3_tax_compliance/configs/business_review/dossier.template.json).

## Hoạt động đã triển khai

- `src/business_review` gồm contract hồ sơ, kiểm file chứng cứ, bộ chuẩn bị PlanningContext/FieldObservation/ItemClassification/PaymentProof, kho hồ sơ và CLI.
- Dossier gắn tenant/taxpayer/record/revision/hash, reviewer, timestamp có timezone, tài liệu/hash và lý do phân loại. Item ID phải tồn tại trong bản hóa đơn đã lưu.
- Chứng cứ được giữ nguyên byte theo scope/hash. File hóa đơn phải khớp source capture. Đổi file bên ngoài không đổi chứng cứ đã lưu; hỏng bản lưu bị phát hiện khi đọc. API không lộ đường dẫn external.
- Profile `reviewed_capture_v1` chỉ dùng sau nhập hồ sơ qua backend local. Không đổi profile OCR cũ thành đủ chứng cứ ngân hàng; không suy OCR trống thành xác nhận thiếu.
- Phân loại từng item cần catalogue/hợp đồng độc lập và đối chiếu phụ lục/ngữ cảnh luật. Không dùng rate in trên hóa đơn để đoán nhóm; không tự tái dùng product code trên hóa đơn khác.
- Payment proof cần chứng từ đã thực hiện, phương thức cụ thể, đúng hai bên, VND và thanh toán đủ bằng gross. Cash deposit vào tài khoản người bán không phải non-cash. Một phần, trả chậm/trả góp, ngoại tệ và SPECIAL còn cần review.
- Ledger đối chiếu từng dòng với bản hiện tại đã lưu lúc nhập và lúc đánh giá: scope/revision/hash/ngày/MST/gross/currency. Completeness là xác nhận của operator dựa trên tài liệu, không tự suy từ tập upload.
- API chỉ đọc `GET /v1/records/{record_id}/business-readiness?taxpayer_id=...` trả readiness/lý do/căn cứ, typed inputs và draft plan qua planner thật. HTTP không nhận dossier hoặc payment/taxonomy assertions. Có auth/scope và no-store.
- Kho `{capture-db-stem}.business.sqlite3` và evidence store cạnh nó có đuôi `.business.evidence`, nằm ngoài Git. Import cùng ID/nội dung idempotent; thay nội dung phải có ID mới. Revision mới không dùng hồ sơ cũ. Không sửa CFR, raw, quality hay evaluations cũ.

`READY_FOR_TECHNICAL_CHECK` không phải PASS. Đã có bank proof nhưng dưới 5 triệu và ledger chưa đầy đủ: applicability trong draft plan vẫn UNKNOWN. Publication/taxonomy gates được giữ; endpoint luôn `tax_verdict=null`, `technical_only=true`.

## Cách dùng

Khởi động lại launcher để nạp route mới. **Chưa thêm màn nhập hồ sơ nghiệp vụ vào UI**; thao tác hiện tại qua CLI/API. Nút kiểm tra thuế cũ không tự dùng dossier để chạy rule DRAFT.

1. Upload/review/lưu hóa đơn. Readiness cần quality assessment cho bản đã lưu; thiếu trả `QUALITY_REQUIRED`.
2. Xem readiness ban đầu để lấy record ID/revision/hash và phần còn thiếu. Hash CFR dùng serializer canonical của ứng dụng, không hash cả file export JSON.
3. Điền template theo schema; placeholder không phải bằng chứng. Reviewer phải trùng actor đăng nhập. Chỉ xác nhận absence sau xem tài liệu đầy đủ; chưa có catalogue thì để `products=[]`.
4. Đặt chứng cứ trong thư mục local, khai báo đường dẫn tương đối và SHA-256. INVOICE phải đúng file đã capture; tài liệu bổ sung phải là bản đã được đối chiếu.
5. CLI dùng **cùng database/auth với web**: `CAPTURE_DATABASE_PATH`, `CAPTURE_AUTH_GRANTS_JSON`, token trong biến `AGENT3_ACCESS_TOKEN`. Terminal mới không tự nhận môi trường riêng của launcher. Không đưa token vào Git/tham số dòng lệnh; không tự tạo grant khác để lách quyền.

Từ thư mục `agent3_tax_compliance`, trong môi trường đã cấu hình như ứng dụng:

```powershell
.\.venv\Scripts\python.exe -m src.business_review.cli import `
  --taxpayer-id YOUR_PAYER --record-id YOUR_RECORD `
  --dossier data\business_review\review.json `
  --evidence-root data\business_review\documents `
  --output data\business_review\import_result.json

.\.venv\Scripts\python.exe -m src.business_review.cli assess `
  --taxpayer-id YOUR_PAYER --record-id YOUR_RECORD `
  --output data\business_review\readiness.json
```

Readiness không yêu cầu dossier để liệt kê thiếu dữ liệu. Hash CFR cũng có thể lấy bằng `src.canonicalization.derive.sha(record.model_dump(mode='json'))` sau khi validate object CFR từ export.

## Kiểm chứng và giới hạn

Test mới bao phủ scope/hash/revision, file traversal/tampering, form đặc thù, absent vs ambiguous, phân loại độc lập với printed rate, KCT/KKKNT/DIRECT/base 5%, phụ lục theo năm, cash/non-cash/cash deposit, tiền âm/ngoại tệ, ledger cũ, quyền READ/WRITE/cross-payer, local CLI thật và lưu chứng cứ. Có ca prepared inputs → planner → binder → **native ZEN**, chỉ promote rule/taxonomy trong bộ nhớ của fixture tổng hợp.

Validation chạy 12 suites; số ca và kết quả ở JSON đi kèm. Hash workflow V1 giữ `f7f54d632a83f15e22d30662ce65dcd6a8180bfecabe55b8fb58633cacc18dd7`, có test replay trước/sau readiness. Không ghi đè evidence lịch sử.

Hồi quy Chrome thực: [6 nhóm compliance](browser_compliance.json) và [5 nhóm explanation](browser_explanation.json) đều PASS, không có page errors. Đây là luồng UI cũ dùng chứng từ tổng hợp; explanation dùng provider giả lập, không phải Qwen thật hoặc benchmark thuế.

```powershell
# Từ D:\financial
agent3_tax_compliance/.venv/Scripts/python.exe scripts/validate_business_review.py
```

Chưa tự động xác minh nội dung ngân hàng/catalogue, chữ ký số ngân hàng hay phân bổ giao dịch. Chưa có SKU thật hoặc legal accuracy trên dữ liệu thật. Hash chứng minh bytes được giữ, không chứng minh xác nhận nghiệp vụ đúng. Core rules và taxonomy vẫn DRAFT/chưa duyệt. Cần dữ liệu sản phẩm và rà soát bảng quyết định trước khi mở execution thật.
