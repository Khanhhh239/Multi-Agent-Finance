# Gate PLAN_06 — review và capture MVP

## Cập nhật 14/10/2026

PLAN_06 tiếp tục nhánh [OCR/extraction V2](ocr_extraction_v2/runbook.md), chưa chuyển PLAN_07. Baseline và ablation mới có nhãn tự đối chiếu, OCR split giữ profile thử nghiệm; sửa binding tổng tiền đã được regression/replay. Người dùng cho phép người code tự test UI cho nghiệm thu kỹ thuật; không coi đây là independent adjudication hoặc pass calibration. [UI/browser evidence bổ sung](ui_review_v2/runbook.md) đã có sau báo cáo ngày 13/10 bên dưới; user acceptance thực tế vẫn cần ghi nhận. Nội dung tiếp theo là snapshot gate cũ, không sửa đè các số đo lịch sử.

Ngày: **13/10/2026**. Quyết định: **PASS_TECHNICAL_MANUAL_REVIEW_ONLY**. **Nghiệm thu hóa đơn Việt Nam thực tế và browser/user acceptance còn PENDING.** Kế thừa phạm vi kỹ thuật đã cho phép ở PLAN_00 và gate kỹ thuật/manual PLAN_05; không thay các điều kiện DQ-01–05.

Đã nối upload → reader/PDF → OCR/layout → CFR → quality → review/correction → rederive → export. Có UI `/review` với trang/bbox/raw/candidates, sửa batch và VAT KCT/KKKNT, task actions, xuất JSON và kiểm audit. Worker capture chạy hữu hạn ngoài HTTP, lease/fencing/retry có giới hạn và đường REQUEST_DATA/OPERATOR. Không có tax verdict hoặc auto-accept.

## Bằng chứng kiểm chứng

- [validation_summary.json](plan06/validation_summary.json): **160 kiểm thử Python PASS** — foundation 22, ingestion 23, OCR 27, extraction 27, quality 34, review 27. JavaScript syntax và DOM harness PASS; **10 schema** Draft 2020-12 được kiểm tra. OpenAPI/schema và HTTP auth/tenant checks đã có.
- Correction kiểm tra actor/scope/candidate/task/expected revision, idempotency key. Revision, immutable event, audit, derive lại, quality mới và task lineage commit cùng transaction; audit lỗi rollback toàn bộ. Hai reviewer cùng revision chỉ một người thành công, người còn lại nhận 409/latest revision.
- Sửa seller/buyer MST đổi direction/counterparty; sửa item tính lại tiền Decimal và quality; giữ source/observed totals. Human proof phải khớp event immutable và after-field, không nhận score=1.0 hoặc dùng lại event ID cho giá trị khác.
- [baseline_summary.json](plan06/baseline_summary.json): **15 artifact / 17 trang**, gồm 10 native và 5 hybrid PP-OCRv6 + VietOCR đã pin. 15 lượt sửa mô phỏng tạo revision 2, export/replay/signed evidence đều qua; không chạy lại OCR. Correction transaction p95 **49,91 ms** cho 15 lần đầu trên máy local; loại trừ upload/PDF/OCR/HTTP/UI và thời gian người sửa.
- **15 assessment PLAN_05 cũ replay PASS** bằng 10 file quality nguyên bản có SHA-256 khớp report cũ, lưu tại `archive/plan06_pinned_plan05_quality`. Code quality mới có fingerprint mới; không sửa đè assessment/report cũ để làm chúng khớp implementation mới.
- Validator xác nhận bằng chứng cũ, các DB PLAN_02–05/legacy và package files trong environment snapshots không thay đổi. DB PLAN_06 là bản sao riêng nâng lên migration 6. Raw/candidate/revision cũ không bị ghi đè.

## Phần chưa đạt và giới hạn

P06-T01–07 đạt **phạm vi chức năng kỹ thuật**. P06-T08 mới có acceptance tự động/synthetic: **0 tài liệu được reviewer độc lập duyệt trong chặng này**, chưa đo thời gian người sửa, accuracy sau human review hoặc p95 pipeline OCR hoàn chỉnh. Native/hybrid dùng chung logical documents/template, không phải 15 mẫu độc lập để công bố accuracy.

Chưa có browser automation/kiểm tra trực quan hoặc người dùng nghiệm thu thao tác, mobile và accessibility. DOM harness chỉ kiểm DOM IDs, item identity, exempt VAT, signed image/bbox, auth trong memory, text an toàn, conflict và reset; không thay browser/user acceptance.

Thêm/tách/gộp dòng và chỉnh segmentation nhiều hóa đơn chưa hỗ trợ; phải REQUEST_DATA/OPERATOR rồi upload nguồn đã làm rõ. Worker cần gọi CLI theo job, chưa có queue daemon. Auth còn local shared-secret adapter; production hardening ở PLAN_14. Calibration/threshold thực tế vẫn UNAVAILABLE và auto-accept tắt.

Để chốt toàn bộ PLAN_06/M1 cho hóa đơn Việt Nam thực tế: cần pilot có quyền dùng 10 native/10 scan/10 ảnh, nhãn/reviewer độc lập và adjudication, frozen grouped splits/chống leakage, owner/target metrics, kiểm thao tác UI và đo thời gian/accuracy sau review thật. Không đánh dấu các yêu cầu đó DONE bằng lượt sửa script.

## Tái hiện và bàn giao

Cwd root `D:\financial`:

```powershell
agent3_tax_compliance/.venv/Scripts/python.exe scripts/export_review_contracts.py
agent3_tax_compliance/.venv/Scripts/python.exe scripts/build_review_baseline.py
python scripts/validate_review.py
```

[Runbook](plan06/runbook.md) · [State machine](plan06/state_machine.md) · [Acceptance và giới hạn](plan06/capture_mvp_acceptance.md).

PLAN_07 nhận CFR/evidence/revision, confidence basis và quality có hash/version; tiếp tục trong scope kỹ thuật. COMPLETED của capture không chứng minh legal applicability, khấu trừ thuế hoặc compliance.
