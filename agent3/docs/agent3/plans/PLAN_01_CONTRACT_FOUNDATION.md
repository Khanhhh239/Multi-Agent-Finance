# PLAN_01 — Hợp đồng dữ liệu, runtime và nền lưu trữ

> Trạng thái triển khai: **DONE — capture-foundation-v1**, 11/10/2026. Runtime riêng, domain/contracts, repository/migration và app factory đã qua 22 tests, 17 schema checks và producer/consumer examples. Xem [gate_01](evidence/gate_01.md), [runtime decision](evidence/plan01/runtime_decision.md) và [contract profile](../../../agent3_tax_compliance/contracts/README.md).

[Lộ trình tổng](README.md) · Trước theo thứ tự đọc: [PLAN_00](PLAN_00_SCOPE_DATASET.md) · Sau: [PLAN_02](PLAN_02_INGESTION_PDF.md)

## 1. Kết quả cần đạt và điều kiện bắt đầu

Đóng băng hợp đồng v1 cho luồng OCR trước khi nối các module; tạo môi trường và kho revision/audit độc lập với prototype cũ.

- Phụ thuộc bắt buộc: PLAN_00 đạt gate kỹ thuật `technical-functional-v1` — đã đáp ứng. Xem [quyết định phạm vi](evidence/plan00/technical_scope_decision.md); dùng fixture project, không phụ thuộc FATURA/MC-OCR hay real-data acceptance.
- Ước lượng: **3–5 ngày công**, một người làm tập trung; chưa bao gồm thời gian chờ dữ liệu/hạ tầng/nghiệp vụ.
- Đối chiếu [NEW_PLAN](../NEW_PLAN.md): mục 2, 3, 5, 8, 11, 12, 14.
- Đầu vào: Scope và nhãn PLAN_00; schema FieldObject/CFR trong NEW_PLAN; inventory runtime.

Không bắt đầu phần phụ thuộc khi gate đầu vào chưa qua. Có thể chuẩn bị fixture/tài liệu độc lập, nhưng không ghi cả chặng DONE vì đã tạo scaffold.

## 2. Tài sản hiện có và cách tái sử dụng

Prototype có API amount float, database amount REAL và đường dẫn cố định; không dùng chúng làm hợp đồng CFR mới. Giữ venv cũ để tái hiện thí nghiệm. Tránh tạo src/database/ vì đã có src/database.py.

Kiểm tra lại tính tồn tại/phiên bản khi triển khai; kết quả kiểm kê là bằng chứng tham khảo, không thay nghiệm thu runtime đích.

## 3. Module và hợp đồng cần xây

Các đường dẫn nền móng sau đã được hiện thực; phạm vi và giới hạn từng module nằm trong gate_01:

`agent3_tax_compliance/src/domain/{envelope,field,cfr,evidence,events}.py; src/persistence/; src/config.py; contracts/; migrations/; tests/contracts/`

SourceEnvelope v1 gắn tenant_id, taxpayer_id, request_id, source_id, hash, detected_format, adapter/profile version. CFR gắn record_id, revision, taxpayer_master_revision; tiền là Decimal nội bộ, chuỗi thập phân chuẩn ở JSON/storage. FieldObject giữ value/status/confidence/confidence_basis/source/provenance/candidates; validation bổ sung sau quality.

Mọi artifact phải có schema/config version, input hash hoặc record revision, creator/stage và timestamp. Artifact chứa dữ liệu thật lưu ngoài git theo policy; tài liệu chỉ ghi metadata đã che dữ liệu.

## 4. Công việc chi tiết theo thứ tự

### P01-T01 — Chốt runtime bằng kiểm tra tương thích

- [x] Hoàn thành: runtime decision, lock và isolated dependency snapshot; import/app tests trong `.venv` mới. OCR/ZEN integration để PLAN_03/08.
- Thực hiện: Kiểm tra Python/Pydantic/FastAPI/OCR bridge/ZEN; chọn runtime hỗ trợ dependency thực tế, ghi decision record và lockfile. Tạo .venv riêng nếu cần, không ghi đè venv/env benchmark.
- Đầu ra: runtime_decision.md, dependency lock.
- Kiểm chứng: Import smoke trong môi trường mới không gọi model/API ngoài hay sửa database khi import.

### P01-T02 — Mô hình hóa field và money

- [x] Hoàn thành: field.py/money.py, exact Decimal/ISO date/currency contracts và negative/roundtrip tests.
- Thực hiện: Cài enum, nullable rules, Decimal codec, date/currency types. PRESENT không null; AMBIGUOUS/MISSING/NOT_PROVIDED_BY_SOURCE/NOT_APPLICABLE có value null. KCT/KKKNT không biến thành VAT 0%.
- Đầu ra: domain/field.py, money.py và JSON Schema.
- Kiểm chứng: Roundtrip decimal lớn/lẻ không đổi; reject float input ở ranh giới tiền và status/value mâu thuẫn.

### P01-T03 — Mô hình hóa evidence/candidate

- [x] Hoàn thành: evidence.py, transform/candidate IDs, confidence provenance validators và schemas.
- Thực hiện: Định nghĩa document/page/block/span, hệ tọa độ, transform, raw value và candidate_id ổn định. Confidence basis phân biệt CALIBRATED, DETERMINISTIC, HUMAN_CONFIRMED, UNAVAILABLE.
- Đầu ra: evidence.py, schema registry v1.
- Kiểm chứng: CALIBRATED thiếu calibration version bị reject; HUMAN_CONFIRMED thiếu review event bị reject; không tự gán 1.0.

### P01-T04 — Mô hình hóa CFR và định danh

- [x] Hoàn thành: capture CFR profile, invoice/bank shapes, observed/derived, items/discovery và valid/invalid examples.
- Thực hiện: Thêm parties cho invoice, bank_transaction cho bank, items có item_id immutable, discovery status, observed/derived tách biệt. invoice_direction chỉ INPUT/OUTPUT khi PRESENT; chưa biết thì AMBIGUOUS/null.
- Đầu ra: cfr.py + ví dụ hợp lệ/không hợp lệ.
- Kiểm chứng: UNKNOWN/PRESENT bị chặn hoặc migrate trước predicates; reorder item không đổi item_id.

### P01-T05 — Thiết kế tenant/taxpayer

- [x] Hoàn thành: taxpayer.py, access matrix, master/relation contracts và tenant/branch tests. Auth provider chưa nối vào data API.
- Thực hiện: Tenant có nhiều taxpayer, request pin taxpayer_master_revision; định nghĩa authorization và branch mapping có thời gian hiệu lực. Không cắt MST 13 số thành 10 số để so sánh.
- Đầu ra: taxpayer.py và tenant access matrix.
- Kiểm chứng: Tenant A không đọc taxpayer thuộc tenant B; quan hệ chi nhánh chưa biết không được suy thành cùng pháp nhân.

### P01-T06 — Kho raw/revision/audit

- [x] Hoàn thành: migrations/001_foundation.sql và persistence/repository.py; rollback/concurrency/raw hash/legacy refusal tests.
- Thực hiện: Tạo migrations và repository cho sources, artifacts, records, revisions, jobs, events. Lưu tiền dạng chính xác; raw immutable, revision mới append-only; thao tác tạo revision/audit cùng transaction.
- Đầu ra: persistence/ và migrations trên database mới.
- Kiểm chứng: Migration không drop view/table legacy; rollback khi audit insert lỗi; hash raw giữ nguyên.

### P01-T07 — Chốt interface module

- [x] Hoàn thành: domain/interfaces.py, 5 protocols/typed responses/errors, 17 schemas và examples; implementations thuộc PLAN sau.
- Thực hiện: Định nghĩa detect(envelope), extract(document), canonicalize(extraction, master_revision), assess(cfr), review(correction). Mỗi response có version và error typed, không trả object backend tùy ý.
- Đầu ra: contracts/*.json và interface examples.
- Kiểm chứng: Fixture từ producer được consumer validate; source enum detector/router/adapter dùng cùng registry.

### P01-T08 — Tạo scaffold test và cấu hình

- [x] Hoàn thành: app.py/config.py/config.example và 22 offline tests; app factory chỉ public health, không mount legacy API.
- Thực hiện: Tách app factory khỏi global initialization; config theo biến môi trường/đường dẫn tương đối. Giữ API legacy tách khỏi /v1. Tạo test contract với fixtures giả lập.
- Đầu ra: src/app.py, tests/contracts/, config.example.
- Kiểm chứng: Chạy test offline trên database tạm, import app không cần OCR model hoặc secret.

## 5. Tiến độ bên trong chặng

- Ngày 1: runtime + field/money/evidence contracts.
- Ngày 2–3: CFR, tenant/taxpayer và repository/migrations.
- Ngày 4–5: module interfaces, negative fixtures và import smoke.

Cuối mỗi ngày cập nhật task IDs đã làm, bằng chứng và blocker vào bảng tiến độ tổng. Khi phát hiện phụ thuộc mới hoặc scope tăng, ghi lại estimate còn lại; không cố giữ lịch bằng cách bỏ invariant.

## 6. Ca kiểm thử và tình huống bắt buộc

- [x] Decimal 9007199254740993 và 0.1 roundtrip chính xác.
- [x] MST 13 số chưa có relation không tự match MST 10 số.
- [x] Bank record không có seller/buyer vẫn hợp lệ theo bank schema.
- [x] Hai reviewer sửa cùng revision: chỉ một transaction thắng.

Dùng fixture tổng hợp nhỏ cho contract/recovery tests, dữ liệu có nhãn cho accuracy và sandbox thật cho connector. Không thay accuracy evaluation bằng unit test parser. Chỉ chạy phần test phù hợp chặng và integration qua ranh giới vừa thay đổi.

## 7. Gate hoàn thành và bàn giao

**Điều kiện gate:** Schema v1 và negative contract tests qua; môi trường mới tái tạo được; database legacy không bị sửa; hợp đồng không phụ thuộc OCR engine cụ thể.

- [x] Mỗi task bắt buộc có artifact và cách tái hiện kiểm chứng.
- [x] Không phát hiện lỗi hợp đồng tiền/tenant/version trong checks đã chạy cho capture-foundation-v1.
- [x] Có giới hạn hỗ trợ và next action trong gate/profile; quality thực tế chưa nghiệm thu.
- [x] Đã ghi [evidence/gate_01.md](evidence/gate_01.md) và validation_summary/test output.
- [x] Bàn giao: PLAN_02–06 nhận contracts, repositories, config, fixture factories; PLAN_07–08 mở rộng cùng schema version policy.

## 8. Khi chưa đạt hoặc bị chặn

Ghi blocker cụ thể, task bị ảnh hưởng, điều kiện gỡ và người/nguồn cần cung cấp. Tiếp tục các task độc lập. Không biến thiếu dữ liệu, thiếu môi trường hoặc lỗi runtime thành kết quả thành công; không ghi DONE khi chỉ có mock mà gate yêu cầu dữ liệu thật.

Lệnh bootstrap/export/validate và giới hạn runtime nằm trong gate_01/runtime_decision. PLAN_02 là chặng tiếp theo; chưa chạy benchmark OCR hoặc cài model trong PLAN_01.
