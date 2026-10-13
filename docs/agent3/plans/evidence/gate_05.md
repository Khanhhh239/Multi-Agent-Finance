# Gate PLAN_05 — Quality/calibration và review policy

Ngày: **13/10/2026**. Owner triển khai: Codex. Quyết định: **PASS_TECHNICAL_MANUAL_REVIEW_ONLY**. **Calibration production, ngưỡng acceptance và frozen release evaluation chưa nghiệm thu.** Phạm vi kỹ thuật kế thừa [decision PLAN_00](plan00/technical_scope_decision.md), không thay các điều kiện DQ-01–05.

## Kết quả đã triển khai

Quality tách completeness, validity và reliability. Invoice/receipt có mẫu số riêng và critical coverage; kiểm tra cấu trúc MST/date/currency, Decimal và consistency; source invalid cần fidelity proof. Không dùng checksum MST chưa xác minh, detection score hoặc heuristic để tạo xác suất đúng của field.

Có công cụ binned calibration + holdout metrics + threshold/uncertainty diagnostics, kiểm tra sample support, scope và leakage. **Chưa fit calibration trên nhãn development hiện có.** Policy v1 bắt buộc auto-accept tắt, thresholds null/TBD và owner chưa được giao; không thể bật production bằng sửa cờ. Mọi assessment có reasons/actions, version/hash/snapshot, append-only persistence và authenticated read API.

## Kiểm chứng và input

- Đầu vào: [gate_04](gate_04.md), CFR/FieldObject 1.0.0, extraction-v1, normalized OCR-v1.1. OCR mặc định PP-OCRv6 + VietOCR; chặng này không chạy OCR hoặc đổi model.
- Policy `quality-manual-v1`; profiles `invoice-quality-v1`, `receipt-quality-v1`; schemas `quality-v1`; calibration card `calibration-unavailable-dq-v1`.
- **133 tests PASS**: foundation 22 + ingestion 23 + OCR 27 + extraction 27 + quality 34. **12 schema mới** kiểm tra Draft 2020-12 và domain validation.
- Test bao gồm overall confidence cao nhưng date thấp vẫn review; deterministic fidelity không probability; human proof chưa xác minh bị từ chối; đổi engine/preprocess/extractor/field mất scope; TEST/DEV không được fit; logical/source/template leakage bị từ chối; source-invalid khác extraction-invalid.
- Storage/API kiểm tra idempotence/concurrency, policy mới append assessment, atomic audit rollback, tenant isolation/401/403/404, correction phải rederive, default-head race kể cả cached result, snapshot/code binding khi replay.
- 15 tài liệu / 17 trang, toàn bộ được đánh giá và replay; local snapshots/DB tại `data invoice/plan05_local/`. Chỉ DB bản sao PLAN_05 lên migration 5; bản baseline cũ vẫn 2/3/4. Report trước và DB legacy giữ nguyên; app env không thêm dependency.

Lệnh gate tại `D:\financial`: `python scripts/validate_quality.py`. [Runbook](plan05/runbook.md) có CLI/API, policy, calibration và cách tái hiện. [validation_summary.json](plan05/validation_summary.json) ghi counts, source/output hashes, replay/schema checks và trạng thái thực tế; test logs ở `plan05/*_test_output.txt`.

## Trạng thái từng task

| Task | Đã có | Phần chưa nghiệm thu |
|---|---|---|
| P05-T01 | `quality/validators.py`, typed issues và classification; evidence hoặc source block refs | Fidelity/source verification connector thực tế chưa provision |
| P05-T02 | `quality/completeness.py`, invoice/receipt profiles, critical count, NA/NP exclusions | Family hóa đơn thực tế chưa được xác nhận expectations bằng pilot |
| P05-T03 | [Score inventory](plan05/calibration_dataset_manifest.json), scope/correctness/raw kinds và exclusion reasons | Nhãn độc lập và split calibration thực tế chưa đủ |
| P05-T04 | Calibration code + functional tests + [UNAVAILABLE card](plan05/calibration_card.json) | Fit/holdout/reliability/Brier/ECE trên dữ liệu thực đủ điều kiện **chưa chạy** |
| P05-T05 | Manual policy, null thresholds, threshold/precision/coverage/interval tool | Business owner/target và ngưỡng acceptance thật **chưa chốt** |
| P05-T06 | Versioned review reasons/actions, [recommendations](plan05/review_recommendations.json) | Review UI/task/correction transactions thuộc PLAN_06 |
| P05-T07 | Development anti-false-acceptance report và timing | Frozen production release test **chưa chạy**, precision target chưa được chứng nhận |
| P05-T08 | Snapshot persistence/API/CLI, policy/revision/code replay và gate | Lịch sử replay cần đúng code hash; không replay bằng phiên bản khác như thể tương đương |

## Evaluation và giới hạn

Baseline: **review 15/15, accepted fields 0, accepted precision null**. Cả **6 wrong PRESENT đã biết** của PLAN_04 không được auto-accept. Đây là kết quả của manual-only policy, không chứng minh production precision hoặc đã sửa 6 lỗi OCR.

Score audit có **211 field rows** (cohorts chồng lặp chứng từ/template), chỉ thấy detection scores ở các candidate có score. **0 mẫu calibration đủ điều kiện**: generator labels chưa độc lập, development đã exposure, template grouping chưa cho split độc lập. Không đưa FATURA/MC-OCR vào calibration hoặc release scope. Brier/ECE, real fit/holdout metrics và thresholds hiện null/TBD.

Chi tiết limits và next actions: [quality release report](plan05/quality_release_report.md). VALID chỉ format/arithmetic; completeness không bảo đảm đúng; eligible field không phải verdict thuế hay permission tự duyệt. Missing pages/items dẫn tới REQUEST_DATA/REEXTRACT, không yêu cầu reviewer chọn bừa.

## Bàn giao và điều kiện còn mở

PLAN_06 có thể tiếp tục MVP review/correction kỹ thuật với assessment/recommendations/field signals và policy manual. Correction cần revision/audit → rederive → quality mới; không tái dùng assessment revision trước. PLAN_07 nhận field validity/reliability/critical coverage có version nhưng phải tự xét applicability/legal eligibility.

Để đóng **toàn bộ PLAN_05 về calibration/production release**, cần người quản lý dữ liệu cung cấp quyền/provenance hóa đơn Việt Nam (DQ-01/04), reviewer độc lập và adjudication (DQ-02), frozen grouped splits/exposure audit (DQ-03), business owner/target và calibration/holdout trước acceptance (DQ-05). Chưa có những bằng chứng này; tiếp tục UNAVAILABLE/manual review. Không đánh dấu các task nghiệm thu thực tế đã hoàn tất.
