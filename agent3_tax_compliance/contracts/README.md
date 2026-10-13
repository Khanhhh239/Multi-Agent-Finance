# Capture foundation contracts v1

> Cập nhật 12/10/2026: PLAN_02–04 đã bổ sung ingestion, OCR bridge và extraction/CFR. Những mô tả foundation-only dưới đây là phạm vi tại gate PLAN_01, không là trạng thái API hiện tại. Foundation schemas vẫn giữ nguyên; xem [gate_04](../../docs/agent3/plans/evidence/gate_04.md) và các namespace bổ sung ở cuối file.

Profile `capture-foundation-v1`, schema version `1.0.0`. Export: `scripts/export_foundation_contracts.py`; registry chứa checksum 17 JSON Schema Draft 2020-12. `v1/examples.json` có 7 positive producer/consumer messages và 4 negative messages.

Đây là **profile nền móng cho capture**, không là bản wire đầy đủ của mọi nguồn trong schema minh họa NEW_PLAN. Các module sau dùng profile này hoặc tăng version kèm migration; không deserialize payload legacy vào CFR mới. App legacy không mount dưới `/v1`.

| Semantic thiết kế | Profile hiện thực |
|---|---|
| Tenant/taxpayer/master revision | Fields trực tiếp trên SourceEnvelope/CFR, master table riêng |
| Source/provenance | `source_id` trỏ immutable envelope/raw; `source_format` dùng cùng SourceFormat enum với detector/interfaces |
| Seller/buyer | `parties.seller/buyer`; invoice/receipt có object partial, bank dùng `bank_transaction.account_owner/counterparty` |
| Invoice metadata | `invoice.number/series/issue_date`; tiền quan sát ở `totals`, tiền dẫn xuất ở `derived.totals` |
| Direction/counterparty | `derived.invoice_direction/counterparty`; INPUT/OUTPUT khi PRESENT, unresolved AMBIGUOUS/null |
| Field confidence | CALIBRATED có score/version; DETERMINISTIC có fidelity policy; HUMAN_CONFIRMED có review event; UNAVAILABLE không có probability |
| Items/discovery | `item_id` khác `line_number`; COMPLETE/INCOMPLETE/UNKNOWN; reorder không đổi IDs |
| VAT | TAXABLE_RATE/KCT/KKKNT; KCT/KKKNT không nhận numeric rate. Legal VAT category/taxonomy chưa hiện thực |
| Financial source union | INVOICE/RECEIPT/BANK_TRANSACTION shape cho nền móng; ERP/accounting/payment/rule output mở rộng tại PLAN tương ứng |

`SourceFormat` mô tả format/router contract. Enum architecture tổng quát `PDF_IMAGE` được biểu diễn ở profile bằng PDF/IMAGE; native-vs-scan phân loại từng page của Document. Không coi detector hints là capability hoặc legal scope. XML/Excel/bank enum có thể được khai báo mà adapter chưa implement; supported adapters phải được xác nhận tại PLAN_02/03/10/11, không suy từ enum.

Contract validation bắt buộc hai bước: JSON Schema structural validation rồi domain model validation. JSON Schema có điều kiện status/value/confidence, nhưng tính duy nhất item/candidate IDs, VAT relationships, bank shape và cross-record authorization/hash/revision vẫn phải qua domain/repository validators. Không chỉ validate schema rồi ghi database.

Tiền, quantity và rate nhận Decimal nội bộ hoặc plain decimal string ở JSON, reject float/int/bool/exponent/NaN; serialize chuỗi chính xác không rounding. Ngày nhận ISO YYYY-MM-DD hoặc date, không nhận epoch/localized guessing. Currency ba chữ hoa là format contract; membership và business validation thuộc PLAN_05.

Repository `append_revision` là storage primitive, **không phải review service**: chỉ ghi record đã được producer chuẩn bị, expected_revision và audit trong transaction. PLAN_06 phải implement correction → rederive Layer 5 → quality trước trả review result; chưa được gọi primitive này trực tiếp làm endpoint correction. Foundation chỉ cho giữ nguyên tập item IDs khi sửa; add/remove/re-extraction lifecycle cần contract/event policy riêng ở PLAN_04/06.

Protocols detect/extract/canonicalize/assess/review và typed StageResponse đã có; adapter implementations, API pagination, calibration, jobs execution/retry và rule outcomes thuộc PLAN sau. Jobs hiện là immutable QUEUED snapshots, không phải worker state machine. Artifact input hash ràng buộc đúng record revision. Không có endpoint đọc/ghi dữ liệu trước authentication.

Schema thay đổi tương thích phải cập nhật registry/examples và validate consumers; thay đổi breaking tăng schema/profile version, migration rõ ràng, giữ revision/raw cũ. Không ghi đè payload revision để “nâng schema”.

PLAN_03 bổ sung profile `ocr-v1/`: OCRConfig, JSONL bridge request/response, benchmark OCRResult 1.1, normalized blocks/pages/documents và OCRJobView. Registry có 11 schemas cùng request/response examples; domain validators tiếp tục kiểm tra ownership, polygon, completion và correlation. Line scores là heuristic chưa calibration. Migration 003 thêm OCR jobs/cache với lease/audit/immutable result; [runbook](../../docs/agent3/plans/evidence/plan03/bridge_runbook.md) ghi CLI và endpoint đọc artifact. CFR producer/line items thuộc PLAN_04.

Sau model switch, profile hiện hành là **`ocr-v1.1/` — 12 schemas**, thêm EngineProfile, model ID correlation và score_kind; profile cũ giữ nguyên. Ứng dụng chọn mặc định PP-OCRv6 + VietOCR từ `configs/ocr/default.json`, independent worker interpreter/profile cho từng engine. Confidence hybrid là detector score, không phải confidence của text. [Registry và cách thay model](../configs/ocr/README.md) · [runbook hiện hành](../../docs/agent3/plans/evidence/plan03/model_switch/runbook.md).

PLAN_04 bổ sung **`extraction-v1/` — 7 schemas**: profile, candidate, item identity/lineage, derivation DAG, VAT group, segmentation và extraction artifact bao CFR. `scripts/export_extraction_contracts.py` xuất registry; `scripts/validate_extraction.py` kiểm tra schemas/domain/replay và 99 tests. Migration 004 thêm artifact append-only, CFR/audit lưu atomic. Mọi artifact `review_required=true`; field PRESENT chưa được quality xác nhận. [Runbook/API/rederive](../../docs/agent3/plans/evidence/plan04/runbook.md) · [baseline và giới hạn](../../docs/agent3/plans/evidence/plan04/extraction_baseline.md). Foundation CFR không thêm VAT group vào items; nhóm VAT và derivation manifest ở lớp artifact để giữ tương thích.

PLAN_05 bổ sung **`quality-v1/` — 12 schemas**: policy/profiles, calibration scope/sample/artifact, source proof, field quality, issues, coverage/confidence, recommendations và assessment. Migration 005 thêm assessment/replay inputs append-only; revision/policy đổi tạo assessment mới. Gate kỹ thuật: 133 tests, 15 tài liệu; **manual-only**, calibration thực tế UNAVAILABLE, thresholds null/TBD. [Gate và phần chưa nghiệm thu](../../docs/agent3/plans/evidence/gate_05.md) · [Runbook/API/policy](../../docs/agent3/plans/evidence/plan05/runbook.md). Quality v1 không thay CFR/OCR/extraction schemas và không cung cấp tax verdict. Khi chạy code hiện hành, dùng validator chặng mới nhất; counts và migration versions trong report cũ là lịch sử tại gate của chặng đó.

PLAN_06 bổ sung **`review-v1/` — 10 schemas** và OpenAPI: correction command/event/result, task/page/action, evidence token và recovery. Migration 006 thêm tasks, immutable correction events, capture jobs và signing secret local. Review service lưu correction → rederive → quality → task lineage cùng transaction, không expose primitive append_revision làm API sửa trực tiếp. Task stamps gắn assessment nguồn, record revision và task ID; mọi input/candidate/evidence vẫn kiểm quyền và ownership. [Gate](../../docs/agent3/plans/evidence/gate_06.md) · [UI/API/worker runbook](../../docs/agent3/plans/evidence/plan06/runbook.md). 160 tests và JS DOM/syntax PASS; real-data/browser acceptance còn mở. Quality implementation đã đổi để xác minh human proof; dùng `scripts/replay_plan05_snapshot.py` với mã quality pin trong archive để replay bằng chứng PLAN_05, không ghi đè snapshot lịch sử.
