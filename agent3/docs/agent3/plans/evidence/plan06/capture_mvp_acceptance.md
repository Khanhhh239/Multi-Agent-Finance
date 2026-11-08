# Nghiệm thu capture MVP — phạm vi kỹ thuật

Ngày: 13/10/2026. Bằng chứng máy: [validation_summary.json](validation_summary.json), [baseline_summary.json](baseline_summary.json). Không dùng kiểm thử chức năng làm metric OCR hoặc thay điều kiện DQ-01–05.

| Hạng mục | Bằng chứng / phạm vi |
|---|---|
| Upload → reader → normalized → extraction → quality → review → correction → export | TestClient upload PDF synthetic mới, reader subprocess thật, native OCR bridge không gọi model, worker capture, correction/export API |
| OCR-backed review | Tái dùng 5 artifact hybrid PP-OCRv6 + VietOCR đã pin và 10 native; tổng 15 tài liệu/17 trang. Không chạy lại OCR hoặc đổi model |
| Revision/audit atomic | Audit failure rollback CFR/head/event/assessment/tasks; append-only correction event; idempotence và hai reviewer cùng revision |
| Candidate/evidence isolation | Candidate của chứng từ thứ hai bị từ chối; scope tenant/payer/actor, token tamper/expiry, kiểm hash PNG và resolver |
| Correction → rederive | Sửa buyer/seller MST đổi INPUT/OUTPUT/AMBIGUOUS và counterparty; sửa item net/rate tính lại Decimal; không ghi đè observed totals |
| Human proof | Event immutable, field after khớp chính xác; tái dùng event ID cho giá trị khác không được HUMAN_CONFIRMED; proof giữ qua revision sau |
| Tasks/pagination | Dedupe, supersede/resolve có previous_ids; tenant/filter/revision trước pagination; signed snapshot cursor |
| Recovery | Transition validator, error recovery, bounded retries → OPERATOR, hết lease và stale worker fence, REQUEST_DATA |
| Manual completion | Chưa xử lý xong bị từ chối; chỉ hoàn tất sau khi xác nhận current fields/đủ items, không còn issue ngoài INFO hoặc task đang mở |
| Replay | Canonicalize lại từ cached normalized OCR gắn raw/Document hashes, áp events và derive cho từng revision; khớp persisted head. 15 assessment PLAN_05 vẫn replay bằng code pin cũ |
| UI | Static client, ảnh + bbox, raw/candidate, sửa/xác nhận batch, KCT/KKKNT, task actions, export/audit; syntax + DOM harness. Chưa chạy nghiệm thu browser/người dùng |

Baseline correction là script mô phỏng reviewer, actor ghi rõ `simulated-review-not-independent-label`. Chỉ chứng minh luồng HUMAN_CONFIRMED hoạt động và event ownership; **không chứng minh dữ liệu được chuyên gia xác nhận**. Những giá trị mới cố ý khác source để kiểm total mismatch/review còn hoạt động. Export luôn nêu issues còn lại và giới hạn.

Đã đo: số tài liệu/trang, review load trước/sau correction, p95 transaction correction local cho 15 lần đầu. Thời gian người sửa, field accuracy sau review thật, p95 upload→OCR→review và chất lượng trên hóa đơn Việt Nam thực tế: **NOT_MEASURED / NOT_EVALUATED**, không gán 0% hoặc 100%.

M1 đạt luồng kỹ thuật manual-review; chưa đạt nghiệm thu sản phẩm cho hóa đơn Việt Nam thực tế. Cần pilot có quyền dùng 10 native/10 scan/10 image, reviewer độc lập/adjudication, grouped frozen splits chống leakage, metric target/owner và kiểm thử người dùng. PLAN_07 có thể nhận CFR/revision/evidence kỹ thuật; không suy ra legal eligibility từ quality hay COMPLETED.

Các ca ngoài phạm vi: thêm/tách/gộp dòng, multi-invoice segmentation correction, mapping VAT category pháp lý, XML/Excel/bank, queue daemon và nhận nguồn bổ sung tự động. Mỗi ca phải chuyển người xử lý hoặc upload nguồn đã làm rõ; không tự đoán/ghép hoặc phát hành verdict thuế.
