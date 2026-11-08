# PLAN_05 — Báo cáo kiểm chứng quality và trạng thái release

Ngày: **13/10/2026**. Đây là development/functional report, **không phải production release trên frozen test**. Scope kế thừa [quyết định PLAN_00](../plan00/technical_scope_decision.md).

| Kết quả trên baseline | Giá trị |
|---|---:|
| Tài liệu / trang | 15 / 17 |
| Tài liệu yêu cầu review | 15/15 — 100% |
| Field tự chấp nhận | 0 |
| Precision của accepted fields | Không xác định — không có field được accept |
| Wrong PRESENT đã biết từ PLAN_04 | 6 |
| Wrong PRESENT tự chấp nhận | 0 |
| Field có nhãn trong inventory | 211 |
| Mẫu đủ điều kiện calibration | 0 |
| Frozen release evaluation | Chưa chạy |

Review rate 100% và zero acceptance là chính sách manual, **không phải bằng chứng đạt precision production**. Quality chưa sửa lỗi OCR. Những lỗi tên/số hóa đơn chưa thể xác minh tự động; sai tiền có thể phát hiện qua đối chiếu số học khi đủ trường. Không hứa mọi sai tiền đều phát hiện được chỉ từ phép cộng.

211 dòng inventory gồm 162 field native và 49 field nhóm hybrid có nhãn. Các cohort trùng chứng từ logic và cùng template tổng hợp, không phải 211 mẫu độc lập. Labels là generator-verified, chưa có reviewer độc lập; data development đã dùng để sửa parser PLAN_04. Không dùng chúng để fit calibration hoặc làm frozen release test.

## Artifacts

- [baseline_summary.json](baseline_summary.json): từng assessment, critical coverage, confidence coverage, issue counts, latency và hashes.
- [calibration_dataset_manifest.json](calibration_dataset_manifest.json): nối correctness với candidate raw scores, field family, engine/preprocess/extractor; ghi lý do từng row chưa đủ điều kiện.
- [calibration_card.json](calibration_card.json): UNAVAILABLE, fit/holdout counts 0, Brier/ECE null, threshold owner chưa được giao.
- [review_recommendations.json](review_recommendations.json): reasons/actions theo assessment cho PLAN_06.
- [validation_summary.json](validation_summary.json): toàn bộ test/schema/replay/storage kiểm chứng; snapshots chi tiết ở `data invoice/plan05_local/`.

Latency trong summary đo worker quality/repository trên fixture development, có đọc DB/hash và tạo snapshot, không gồm OCR và không là production SLA. Replay không phụ thuộc latency này.

## Phạm vi đã kiểm chứng

| Nội dung | Trạng thái |
|---|---|
| Field format, MST structural, date/currency, Decimal consistency | Đã kiểm chứng chức năng; VALID không chứng minh hợp lệ pháp lý |
| Completeness theo invoice/receipt và critical coverage | Đã kiểm chứng; NP/NA loại mẫu số, thiếu items báo riêng |
| Calibration code, ECE/Brier/reliability, threshold diagnostics | Đã kiểm chứng bằng synthetic unit fixtures; chưa fit real calibration |
| Engine/preprocess/extractor/field scope, chống leakage | Đã kiểm chứng chức năng |
| Source fidelity/XML hoặc human proof | Nhánh chức năng đã kiểm chứng; chưa có connector/proof thực provision |
| Manual acceptance policy/recommendations/replay/storage/API | Đã kiểm chứng; auto-accept luôn tắt |
| Critical precision targets và ngưỡng acceptance | Chưa chốt; null/TBD, cần business owner và dữ liệu |
| Frozen production release / calibration độc lập | Chưa nghiệm thu; DQ-01/02/03/05 còn mở |

## Điều kiện để tiếp tục nghiệm thu thực tế

1. Có hóa đơn Việt Nam thực tế phù hợp phạm vi, quyền sử dụng/provenance rõ (DQ-01; DQ-04 nếu dùng dataset ngoài).
2. Người thứ hai đối chiếu nhãn critical và phân xử bất đồng; khóa phiên bản nhãn (DQ-02).
3. Kiểm tra duplicates, nhóm vendor/template/logical variants, exposure history; chia FIT/HOLDOUT/TEST đủ độc lập trước fit (DQ-03).
4. Giao owner và chốt target theo rủi ro MST/date/money; chọn threshold trên holdout, báo coverage/false acceptance/uncertainty rồi chạy test release đã khóa (DQ-05).

Cho tới lúc đó, giữ confidence UNAVAILABLE và manual review. PLAN_06 có thể tiếp tục review/correction MVP kỹ thuật, nhưng chưa được tuyên bố capture đã nghiệm thu trên hóa đơn thuế thực tế hoặc bật auto-accept. PLAN_07 nhận versioned field signals; không coi completeness hoặc VALID là rule eligibility đầy đủ.
