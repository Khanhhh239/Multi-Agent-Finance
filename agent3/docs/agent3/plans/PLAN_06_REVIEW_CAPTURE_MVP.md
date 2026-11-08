# PLAN_06 — Review, sửa dữ liệu và nghiệm thu MVP đọc chứng từ

> Cập nhật 14/10/2026: **PLAN_06 vẫn đang được củng cố**, nhánh [OCR/extraction V2](PLAN_OCR_EXTRACTION_V2.md) IN_PROGRESS. [Baseline, thử nghiệm và giới hạn](evidence/ocr_extraction_v2/runbook.md). Theo người dùng, người code được tự đối chiếu trên UI cho gate kỹ thuật; nhãn này không đổi thành nhãn độc lập. Chưa chuyển sang PLAN_07 và chưa chốt real-data/statistical acceptance.

> Trạng thái triển khai 13/10/2026: **DONE_TECHNICAL_MANUAL_REVIEW — REAL_ACCEPTANCE_PENDING**. P06-T01–07 đã triển khai và kiểm chứng kỹ thuật; P06-T08 còn nghiệm thu dữ liệu thực, browser/người dùng và metrics sau review độc lập. [Gate và giới hạn](evidence/gate_06.md) · [Runbook](evidence/plan06/runbook.md).

[Lộ trình tổng](README.md) · Trước theo thứ tự đọc: [PLAN_05](PLAN_05_QUALITY_CALIBRATION.md) · Sau: [PLAN_07](PLAN_07_LEGAL_TAXONOMY_PLANNING.md)

## 1. Kết quả cần đạt và điều kiện bắt đầu

Người dùng upload, xem field cạnh evidence, sửa có audit và xuất CFR đã cập nhật; chốt sản phẩm OCR/PDF có thể sử dụng trước khi nối luật.

- Phụ thuộc bắt buộc: PLAN_02–05 đạt gate.
- Ước lượng: **4–6 ngày công**, một người làm tập trung; chưa bao gồm thời gian chờ dữ liệu/hạ tầng/nghiệp vụ.
- Đối chiếu [NEW_PLAN](../NEW_PLAN.md): mục 8, 11, 12, phụ lục state machine.
- Đầu vào: CFR repositories, evidence resolver, quality policy, rederive interface và authorization.

Không bắt đầu phần phụ thuộc khi gate đầu vào chưa qua. Có thể chuẩn bị fixture/tài liệu độc lập, nhưng không ghi cả chặng DONE vì đã tạo scaffold.

## 2. Tài sản hiện có và cách tái sử dụng

**Điều kiện chuyển từ PLAN_00:** kiểm DQ-01–05 trong [decision record](evidence/plan00/technical_scope_decision.md) trước nghiệm thu hóa đơn Việt Nam thực tế: bộ pilot 10 PDF text/10 scan/10 ảnh có quyền dùng, independent label review, chống leakage và metric evidence. Nhóm thiếu phải nằm ngoài tuyên bố hỗ trợ thực tế; demo kỹ thuật/manual review phải công khai giới hạn. Không dùng gate kỹ thuật PLAN_00 thay gate chất lượng này.

API /process_transaction cũ không đủ hợp đồng CFR/review. Không dùng legacy PASS/FAIL để gắn nhãn dữ liệu đã nhập đúng; mốc này chưa có tax verdict.

Kiểm tra lại tính tồn tại/phiên bản khi triển khai; kết quả kiểm kê là bằng chứng tham khảo, không thay nghiệm thu runtime đích.

## 3. Module và hợp đồng cần xây

Các đường dẫn sau là **đích dự kiến**, chưa hàm ý file đã tồn tại:

`agent3_tax_compliance/src/api/v1/{ingestions,records,review_tasks}.py; src/review/; src/jobs/; review client hoặc UI tối thiểu; tests/review/`

CorrectionCommand: tenant_id, taxpayer_id, record_id, expected_revision, task_id, field_path/item_id, selected_candidate_id hoặc new_value, reason. CorrectionEvent immutable, before/after/evidence/actor/time. Re-entry phải Layer 5 rederive → Layer 6 quality; sau PLAN_07 mới tiếp planning/rules.

Mọi artifact phải có schema/config version, input hash hoặc record revision, creator/stage và timestamp. Artifact chứa dữ liệu thật lưu ngoài git theo policy; tài liệu chỉ ghi metadata đã che dữ liệu.

## 4. Công việc chi tiết theo thứ tự

### P06-T01 — Định nghĩa state/job transitions

- [x] Phạm vi kỹ thuật: [state machine](evidence/plan06/state_machine.md), `src/jobs/state.py`, recovery/lease tests trong [report](evidence/plan06/validation_summary.json).
- Thực hiện: Liệt kê trạng thái upload/extraction/quality/review/done và lỗi. PROCESSING_ERROR có retry/reextract/request-data/operator path theo error type, bounded attempts.
- Đầu ra: state_machine.md + transition validator.
- Kiểm chứng: Invalid transition bị reject; job lỗi không kẹt vĩnh viễn hoặc tự hoàn tất.

### P06-T02 — API đọc và pagination

- [x] Phạm vi kỹ thuật: [OpenAPI](evidence/plan06/openapi.json), API auth/scope/signed snapshot pagination, [runbook](evidence/plan06/runbook.md).
- Thực hiện: Tạo POST /v1/ingestions, GET /v1/jobs/{id}, GET /v1/records/{id}, GET /v1/records/{id}/revisions, GET /v1/review-tasks với filter/status/cursor. Envelope response có schema version.
- Đầu ra: OpenAPI + repository queries.
- Kiểm chứng: Cursor ổn định, tenant-filter trước pagination, giới hạn page size; không lộ record tenant khác.

### P06-T03 — Tạo review tasks theo issue

- [x] Phạm vi kỹ thuật: task builder/repository, dedupe, revision lineage, expiring actor-bound evidence; [kiểm chứng](evidence/plan06/validation_summary.json).
- Thực hiện: Dedupe task bằng record/revision/issue/field; evidence links có quyền và thời hạn. Phân biệt sửa extraction, xác nhận candidate, yêu cầu dữ liệu.
- Đầu ra: task builder + review repository.
- Kiểm chứng: Retry quality không tạo trùng task; task revision cũ không được ghi đè record mới.

### P06-T04 — UI/client review tối thiểu

- [x] Client kỹ thuật `/review`: raw/candidate/trang/bbox, sửa batch, KCT/KKKNT; [walkthrough](evidence/plan06/runbook.md), JS syntax/DOM harness PASS. Browser/user acceptance chưa chạy, nằm trong phần nghiệm thu còn mở.
- Thực hiện: Hiển thị trang và bbox, raw vs normalized, candidates, issue và nguồn. Cho sửa seller/buyer/MST/date/money/items theo scope; không yêu cầu người dùng hiểu engine nội bộ.
- Đầu ra: màn review và sample walkthrough.
- Kiểm chứng: Người review tìm được vùng bằng chứng; KCT/KKKNT chọn rõ, không ép nhập rate số.

### P06-T05 — Correction transaction và concurrency

- [x] `src/review/correction_service.py`: atomic correction/revision/event/quality/tasks, CAS 409, idempotence, candidate ownership và rollback tests.
- Thực hiện: Validate actor/expected_revision/candidate ownership, append revision + event atomic. Idempotent correction key; conflict trả 409 cùng latest revision.
- Đầu ra: correction_service.py.
- Kiểm chứng: Double submit không tạo hai correction; lỗi audit rollback toàn bộ; reason không rỗng cho override.

### P06-T06 — Re-derive và re-assess

- [x] `src/review/revision_reprocessor.py`: Layer 5 → 6, DAG invalidation, proof giữ qua revision; direction/counterparty/Decimal totals được kiểm thử.
- Thực hiện: Invalidate derived fields theo dependency DAG rồi chạy Layer 5 và 6. Giữ human-confirmed field riêng, không ghi đè raw; tasks cũ đóng/superseded có lineage.
- Đầu ra: revision_reprocessor.py.
- Kiểm chứng: Sửa seller MST đổi direction/counterparty đúng; sửa items tính totals và quality lại, không dùng output cũ.

### P06-T07 — Export và audit replay

- [x] Export/audit API, raw hash + cached OCR/extraction replay + events + rederive; 15 head revisions và 15 assessment lịch sử PLAN_05 được kiểm chứng.
- Thực hiện: Xuất CFR JSON, summary dữ liệu và danh sách unresolved issues; signed evidence access. Không hiển thị tax compliance chưa tính.
- Đầu ra: export endpoint + audit view.
- Kiểm chứng: Rebuild revision từ raw + events khớp persisted CFR; log không chứa ảnh/MST đầy đủ.

### P06-T08 — Nghiệm thu luồng thực tế

- [ ] **PENDING nghiệm thu thực tế.** [Acceptance kỹ thuật](evidence/plan06/capture_mvp_acceptance.md) và [baseline](evidence/plan06/baseline_summary.json) đã có: 15 artifact/17 trang, sửa mô phỏng và latency correction local. Chưa đo human correction time, accuracy sau human review, p95 OCR end-to-end hoặc browser/user acceptance; DQ-01–05 chưa đóng.
- Thực hiện: Dùng functional set từ upload tới correction/export; đo thời gian người sửa, review load, field accuracy sau review, latency p95. Ghi unsupported cases rõ trên sản phẩm.
- Đầu ra: capture_mvp_acceptance.md + gate_06.md.
- Kiểm chứng: Các invariant bắt buộc qua; quality target chỉ công bố với tập/size thực đo và limitations.

## 5. Tiến độ bên trong chặng

- Ngày 1: states/API/read pagination.
- Ngày 2–3: review tasks + evidence UI/client.
- Ngày 4: atomic correction/rederive/export.
- Ngày 5–6: end-to-end, concurrency và nghiệm thu mốc M1.

Cuối mỗi ngày cập nhật task IDs đã làm, bằng chứng và blocker vào bảng tiến độ tổng. Khi phát hiện phụ thuộc mới hoặc scope tăng, ghi lại estimate còn lại; không cố giữ lịch bằng cách bỏ invariant.

## 6. Ca kiểm thử và tình huống bắt buộc

- [x] Sửa buyer/seller MST làm direction đổi INPUT/OUTPUT/AMBIGUOUS.
- [x] Hai người mở cùng revision rồi cùng submit: một thành công, một 409/latest revision.
- [x] Candidate_id từ record thứ hai bị reject.
- [x] Processing error có recovery/lease fencing; hết retry chuyển OPERATOR.
- [x] Sửa item rồi export có derived totals mới; observed totals giữ nguyên và mismatch vẫn được review.

Dùng fixture tổng hợp nhỏ cho contract/recovery tests, dữ liệu có nhãn cho accuracy và sandbox thật cho connector. Không thay accuracy evaluation bằng unit test parser. Chỉ chạy phần test phù hợp chặng và integration qua ranh giới vừa thay đổi.

## 7. Gate hoàn thành và bàn giao

**Điều kiện gate:** M1: upload→PDF/OCR→CFR→quality→review→rederive→export chạy được; audit/revision/tenant isolation qua; hạn chế OCR được hiển thị. Chưa tuyên bố tuân thủ thuế ở milestone này.

- [x] Task kỹ thuật có artifact/cách tái hiện; phần nghiệm thu T08 còn mở được ghi riêng.
- [x] Kiểm thử hợp đồng, tiền, tenant/revision/version trong phạm vi kỹ thuật PASS; chưa thay nghiệm thu vận hành thực tế.
- [x] [Acceptance](evidence/plan06/capture_mvp_acceptance.md) nêu giới hạn, ca chưa đạt và next action; không công bố quality target thiếu dữ liệu.
- [x] [evidence/gate_06.md](evidence/gate_06.md): 160 tests, 10 schemas, baseline 15 tài liệu/17 trang; gate kỹ thuật/manual, real acceptance PENDING.
- [x] Bàn giao kỹ thuật cho PLAN_07: CFR/confidence basis/evidence/revision; capture không phụ thuộc tax verdict.

## 8. Khi chưa đạt hoặc bị chặn

Ghi blocker cụ thể, task bị ảnh hưởng, điều kiện gỡ và người/nguồn cần cung cấp. Tiếp tục các task độc lập. Không biến thiếu dữ liệu, thiếu môi trường hoặc lỗi runtime thành kết quả thành công; không ghi DONE khi chỉ có mock mà gate yêu cầu dữ liệu thật.

Lệnh triển khai/test và API/worker/UI đã ghi trong [runbook PLAN_06](evidence/plan06/runbook.md). Dữ liệu pilot/reviewer độc lập, browser/user acceptance và metrics thực còn thiếu; tiếp tục manual-only theo [gate](evidence/gate_06.md). Quy ước cập nhật tiến độ nằm trong [README lộ trình](README.md).
