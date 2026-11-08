# Gate PLAN_04 — Extraction → CFR

Owner: Codex. Ngày: **12/10/2026**. Quyết định: **PASS_TECHNICAL_FUNCTIONAL_ONLY** theo [phạm vi PLAN_00](plan00/technical_scope_decision.md). **Accuracy thực tế / calibration / auto acceptance chưa nghiệm thu.**

Đã triển khai field/party extraction, normalization, item identity, VAT grouping, partial/multi-invoice handling, pure rederive/dependency DAG, evidence resolver, persistence append-only và authenticated read API/worker CLI. OCR mặc định vẫn PP-OCRv6 + VietOCR; producer CFR dùng normalized contract chung, không import framework OCR.

## Input versions và phạm vi

- Foundation CFR/FieldObject/ExactDecimal/evidence `1.0.0`; OCR normalized contract `ocr-v1.1`, protocol `ocr-bridge-1`, benchmark result `1.1`.
- Extraction profile `invoice-vi-v1`, method `label-region-v1`, derivation `derive-v1`, identity `item-identity-v1`; schemas mới `extraction-v1`.
- Hybrid đầu vào: `ppocrv6_vietocr`, config `ppocrv6-vietocr-cpu-v1`, model/runtime hashes từ [gate model switch](plan03/model_switch/validation_summary.json).
- Baseline 15 artifact / 17 trang tái dùng PLAN_02–03; 10 native và 5 hybrid. Không train, tải model hoặc chạy lại inference.
- Hash input/output/code/schema, kiểm tra replay và version được ghi ở [validation_summary.json](plan04/validation_summary.json), [baseline_summary.json](plan04/baseline_summary.json). Predicted CFR và DB bản sao lưu local tại `data invoice/plan04_local/`.

## Kiểm chứng

**99 tests PASS:** foundation 22 + ingestion 23 + OCR 27 + extraction 27. **7 schema mới** kiểm tra Draft 2020-12, domain validation và serialization. Các schema/report trước giữ nguyên.

| Task | Output | Evidence |
|---|---|---|
| P04-T01 | `extraction/invoice_fields.py`, `candidates.py` | Party role theo label/context; tên giống nhau nhưng khác MST; ambiguous candidates; merged OCR labels |
| P04-T02 | `canonicalization/normalize.py` | Decimal locale/negative/parentheses, không float/rounding; dates ambiguous; currency policy evidence |
| P04-T03 | `extraction/tables.py`, `canonicalization/identity.py` | Columns/continuation, rows nhiều trang, UUID/reorder/correction, explicit mapping/SPLIT/MERGE |
| P04-T04 | `extraction/vat_group_builder.py` | KCT/KKKNT rate NOT_APPLICABLE, 0% numeric zero; groups partition IDs; category chưa biết |
| P04-T05 | `canonicalization/derive.py` | Master revision/effective branch; 13 số không truncate; observed/derived totals riêng; mismatch issue |
| P04-T06 | `extraction/service.py` | Hai số hóa đơn cạnh tranh → REVIEW_SPLIT/null record; mất trang/rows → INCOMPLETE; bảng rỗng → UNKNOWN |
| P04-T07 | `extraction/evidence.py` | Resolve field → block/span/page/render/original bbox; hash/scope kiểm tra; API auth; DAG không cycle |
| P04-T08 | Baseline predictions và field diagnostics | 15 documents; field/party/money/row metrics, missing labels và wrong PRESENT được công khai |
| P04-T09 | `canonicalize`, `rederive`, `affected_nodes` | Replay cùng input/IDs/timestamp/hash; correction invalidates direction/counterparty; rederive trước quality |

Integration còn kiểm tra duplicate/concurrent calls không cấp lại item ID, append-only storage, audit failure rollback cả CFR/artifact, tenant isolation, 401/403/404, migration 4. Môi trường app không đổi, DB legacy và reports PLAN_00–03 không đổi; DB baseline trước vẫn version 2/3, chỉ bản sao PLAN_04 lên 4.

Lệnh/cwd/runtime, API, worker và replay: [runbook](plan04/runbook.md). Lệnh gate tại `D:\financial`: `python scripts/validate_extraction.py`. Log từng suite nằm trong `plan04/*_test_output.txt`.

## Kết quả evaluation và giới hạn

Native: **162/162 field**, **16/16 rows** khớp. Nhóm hybrid có native + OCR: **37/49 field**, **1/5 rows**; riêng 2 tài liệu có OCR và nhãn: **23/35 field**, **0/4 rows**. Có **6 wrong PRESENT**, gồm sai tên/số hóa đơn và OCR thêm chữ số tiền; tổng cộng **12 field không khớp**. Nhãn tổng hợp chưa có reviewer độc lập; không coi đây là real-world accuracy. Hai tài liệu extra không có nhãn field. Không cộng các cohort/subset thành sample độc lập.

**Mọi artifact bắt buộc `review_required=true`, field confidence UNAVAILABLE.** Discovery original fixtures UNKNOWN vì thiếu row-count evidence; totals quan sát không bị sửa để làm khớp items. Chỉ parser/table family đã nêu trong [báo cáo baseline](plan04/extraction_baseline.md) được kiểm chứng. Layout chưa hỗ trợ, boundary chưa xác nhận và OCR sai vẫn cần review. Detector scores không phải recognition probability hoặc confidence của field.

## Bàn giao

PLAN_05 có thể bắt đầu phần kỹ thuật quality/calibration từ CFR/candidates/evaluation errors. Phần nghiệm thu accuracy/calibration thực tế vẫn phụ thuộc DQ-01–05 (quyền dữ liệu, hóa đơn phù hợp, nhãn độc lập và frozen split). Không bật tự động chấp nhận khi thiếu những đầu vào này.

PLAN_06 nhận evidence resolver + DAG + rederive; phải sửa observed → revision/audit → rederive → quality. Mapping/lineage split/merge đã có contract và kiểm thử, giao dịch review và UI thuộc PLAN_06. Chưa tạo review correction endpoint hay legal verdict trong PLAN_04.
