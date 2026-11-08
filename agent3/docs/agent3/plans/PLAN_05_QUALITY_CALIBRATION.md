# PLAN_05 — Data Quality, hiệu chỉnh confidence và chính sách review

> Trạng thái triển khai: **DONE phần kỹ thuật/manual review; calibration và production release PENDING**, 13/10/2026. [Gate_05](evidence/gate_05.md): 133 tests PASS, 12 schema mới, 15 tài liệu/17 trang; có validators/completeness, score audit, calibration tools, manual policy, recommendations và replay/storage/API. Calibration thực tế UNAVAILABLE, thresholds null/TBD, auto-accept tắt; 0 mẫu đủ điều kiện fit. [Runbook](evidence/plan05/runbook.md) · [Release status](evidence/plan05/quality_release_report.md). Không coi gate kỹ thuật là nghiệm thu đầy đủ các task real fit/threshold/frozen release bên dưới.

[Lộ trình tổng](README.md) · Trước theo thứ tự đọc: [PLAN_04](PLAN_04_EXTRACTION_CFR.md) · Sau: [PLAN_06](PLAN_06_REVIEW_CAPTURE_MVP.md)

## 1. Kết quả cần đạt và điều kiện bắt đầu

Tách độ đầy đủ, độ tin cậy và tính hợp lệ; quyết định field nào có thể dùng tự động và field nào phải review.

- Phụ thuộc bắt buộc: PLAN_04 đạt gate.
- Ước lượng: **4–6 ngày công**, một người làm tập trung; chưa bao gồm thời gian chờ dữ liệu/hạ tầng/nghiệp vụ.
- Đối chiếu [NEW_PLAN](../NEW_PLAN.md): mục 6, 7.2.1, 13.
- Đầu vào: CFR predictions, calibration labels tách test, critical-field list và acceptance matrix PLAN_00.

Không bắt đầu phần phụ thuộc khi gate đầu vào chưa qua. Có thể chuẩn bị fixture/tài liệu độc lập, nhưng không ghi cả chặng DONE vì đã tạo scaffold.

## 2. Tài sản hiện có và cách tái sử dụng

**Điều kiện chuyển từ PLAN_00:** DQ-01–05 trong [decision record](evidence/plan00/technical_scope_decision.md). Có thể phát triển/test chức năng bằng fixture project. Trước freeze accuracy test/calibration phải có quyền dùng, labels được đối chiếu và splits đủ độc lập; trước bật auto-accept phải có baseline/target/calibration phù hợp. Nếu thiếu, giữ UNAVAILABLE/manual review và chưa nghiệm thu chất lượng thực tế.

Không coi OCR detector confidence hay heuristic extractor confidence là calibrated accuracy. Deterministic parsing có fidelity policy riêng; không yêu cầu mọi XML/native text đạt confidence=1.0.

Kiểm tra lại tính tồn tại/phiên bản khi triển khai; kết quả kiểm kê là bằng chứng tham khảo, không thay nghiệm thu runtime đích.

## 3. Module và hợp đồng cần xây

Các module sau đã triển khai và kiểm chứng chức năng:

`agent3_tax_compliance/src/quality/{assessor,validators,calibration,policy}.py; configs/quality/; tests/quality/`

Có thêm contracts, completeness, repository/API/CLI, migration 005 và `contracts/quality-v1/`. Nhãn development của PLAN_04 chỉ dùng để audit/evaluation chức năng, không fit calibration. Các checkbox chưa tích ở P05-T04/T05/T07 và gate đầy đủ phản ánh những phần nghiệm thu thực tế còn thiếu dữ liệu/owner.

QualityAssessment gắn record_revision/policy_version/calibration_version; field validation VALID/INVALID_SOURCE_CONTENT/UNKNOWN/NOT_CHECKED/NOT_APPLICABLE. Completeness có mẫu số theo profile; confidence aggregate chỉ gồm tập CALIBRATED đủ điều kiện, kèm count/coverage. Review recommendation không phải tax verdict.

Mọi artifact phải có schema/config version, input hash hoặc record revision, creator/stage và timestamp. Artifact chứa dữ liệu thật lưu ngoài git theo policy; tài liệu chỉ ghi metadata đã che dữ liệu.

## 4. Công việc chi tiết theo thứ tự

### P05-T01 — Tạo field validation theo nguồn

- [x] Hoàn thành chức năng và đính kèm bằng chứng tại gate_05; source fidelity thực tế chưa provision.
- Thực hiện: Kiểm tra type/format, date/currency, cấu trúc MST và amount consistency; phân biệt OCR parse sai với nội dung nguồn sai. Không coi thuật toán checksum chưa xác minh là identity FAIL.
- Đầu ra: validators.py + issue codes.
- Kiểm chứng: INVALID_EXTRACTION khác INVALID_SOURCE_CONTENT; mỗi issue có field/evidence và severity.

### P05-T02 — Tính completeness đúng mẫu số

- [x] Hoàn thành chức năng và đính kèm bằng chứng tại gate_05.
- Thực hiện: Dùng document/profile field expectations và applicability; NOT_PROVIDED_BY_SOURCE/NOT_APPLICABLE không bị phạt như MISSING. Báo riêng critical field coverage.
- Đầu ra: completeness.py.
- Kiểm chứng: Receipt và tax invoice dùng mẫu số riêng; overall cao không che seller MST thiếu.

### P05-T03 — Kiểm kê score có nhãn

- [x] Đã audit 211 field rows; 0 calibration-eligible, không fit development labels. Xem calibration_dataset_manifest và card.
- Thực hiện: Ghép candidate confidence với correctness theo field/family/engine; tách raw score, deterministic parse và human confirmation. Nhóm quá ít dữ liệu ghi insufficient sample.
- Đầu ra: calibration_dataset_manifest + score audit.
- Kiểm chứng: Không dùng test split để fit; không gán calibrated score cho nhóm không có support.

### P05-T04 — Fit và kiểm tra calibration

- [ ] Hoàn thành và đính kèm bằng chứng.
- Đã có code/functional tests; real fit/holdout chưa chạy do DQ-01/02/03/05. Calibration card UNAVAILABLE, không giả lập số liệu Brier/ECE thực tế.
- Thực hiện: Chọn phép hiệu chỉnh đơn giản theo dữ liệu; đo reliability/ECE/Brier hoặc precision theo threshold khi phù hợp. Lưu fit split, sample size và uncertainty.
- Đầu ra: calibration artifact + card.
- Kiểm chứng: Kết quả trên holdout có báo cáo; fallback UNAVAILABLE/review khi domain khác hoặc mẫu không đủ.

### P05-T05 — Chốt threshold theo rủi ro field

- [ ] Hoàn thành và đính kèm bằng chứng.
- Đã có manual policy và threshold/precision/coverage/uncertainty tool. Thresholds null/TBD, business owner chưa được giao; chưa chốt ngưỡng thực tế và chưa bật auto-accept.
- Thực hiện: Chọn threshold bằng false acceptance/coverage trade-off trên calibration holdout. Critical MST/date/money có policy riêng; DETERMINISTIC dùng policy/version thay probabilistic threshold.
- Đầu ra: quality_policy_v1.yaml.
- Kiểm chứng: Không có min_confidence=1.0 chung; ngưỡng TBD chưa được dùng để tự accept production.

### P05-T06 — Xây review reason và action

- [x] Hoàn thành chức năng; reasons/actions xuất trong review_recommendations.json, mọi tài liệu yêu cầu review.
- Thực hiện: Phân loại LOW_CONFIDENCE, AMBIGUOUS_CANDIDATES, INVALID_EXTRACTION, MISSING_FIELD, INCOMPLETE_ITEMS. Request dữ liệu không bị biến thành reviewer chọn bừa.
- Đầu ra: review_recommendations.json.
- Kiểm chứng: Thiếu trang đề xuất REQUEST_DATA/REEXTRACT; confidence unavailable không auto PASS.

### P05-T07 — Đánh giá chống false acceptance

- [ ] Hoàn thành và đính kèm bằng chứng.
- Đã chạy development/manual baseline: review 15/15, accepted 0, accepted precision null, 6 wrong PRESENT không được tự accept. Frozen production release chưa chạy; không dùng development thay test đã khóa.
- Thực hiện: Chạy frozen evaluation đúng lần release; kiểm tra precision accepted fields, review rate và latency. Khi không đạt target đã chốt, giảm phạm vi/auto acceptance có ghi decision.
- Đầu ra: quality_release_report.md.
- Kiểm chứng: Không tune trên kết quả test; nếu mở test để debug thì version và thay bộ holdout cho lần đánh giá sau.

### P05-T08 — Đóng gói policy replay

- [x] Hoàn thành chức năng; append-only snapshot/audit, policy/revision/code binding, idempotent replay và authenticated read API.
- Thực hiện: Persist policy/calibration version với assessment, hỗ trợ deterministic replay. Không ghi đè assessment cũ khi policy thay đổi.
- Đầu ra: assessment snapshots + gate_05.md.
- Kiểm chứng: Cùng revision và versions tái hiện đúng recommendations; policy mới tạo assessment mới.

## 5. Tiến độ bên trong chặng

- Ngày 1: validators/completeness và score inventory.
- Ngày 2–3: calibration artifacts, uncertainty và threshold policy.
- Ngày 4: review action + evaluation.
- Ngày 5–6: xử lý domain thiếu dữ liệu, replay và báo cáo gate.

Cuối mỗi ngày cập nhật task IDs đã làm, bằng chứng và blocker vào bảng tiến độ tổng. Khi phát hiện phụ thuộc mới hoặc scope tăng, ghi lại estimate còn lại; không cố giữ lịch bằng cách bỏ invariant.

## 6. Ca kiểm thử và tình huống bắt buộc

- [x] Overall confidence cao nhưng invoice date thấp — vẫn review, không lấy mean để tự accept.
- [x] XML deterministic không có probability vẫn kiểm qua fidelity policy — nhánh chức năng, chưa provision connector/proof thực tế.
- [x] Một field chưa có nhãn calibration không được giả định score.
- [x] Đổi engine/config/runtime/preprocess làm calibration cũ không còn scope.
- [x] Source ghi MST sai rõ ràng khác OCR đọc MST sai — source-invalid cần fidelity proof.

Dùng fixture tổng hợp nhỏ cho contract/recovery tests, dữ liệu có nhãn cho accuracy và sandbox thật cho connector. Không thay accuracy evaluation bằng unit test parser. Chỉ chạy phần test phù hợp chặng và integration qua ranh giới vừa thay đổi.

## 7. Gate hoàn thành và bàn giao

**Điều kiện gate:** Quality outputs có version, phân biệt status/validity/confidence đúng; policy tự chấp nhận chỉ bật cho nhóm có bằng chứng đạt target. Nhóm còn lại tiếp tục qua review, có báo cáo phạm vi.

- [ ] Mỗi task bắt buộc có artifact và cách tái hiện kiểm chứng.
- [ ] Không còn lỗi vi phạm hợp đồng dữ liệu, tiền, tenant hoặc version trong phạm vi chặng.
- [ ] Có bảng giới hạn hỗ trợ, ca chưa đạt và next action; quality target thiếu dữ liệu không được đánh dấu đạt.
- [ ] Ghi `evidence/gate_05.md`: input versions, test/eval command, ngày chạy, kết quả, số mẫu, lỗi còn lại và quyết định gate.
- [ ] Bàn giao: PLAN_06 nhận review reasons và acceptance policy; PLAN_07 nhận field eligibility signals có version.

## 8. Khi chưa đạt hoặc bị chặn

Ghi blocker cụ thể, task bị ảnh hưởng, điều kiện gỡ và người/nguồn cần cung cấp. Tiếp tục các task độc lập. Không biến thiếu dữ liệu, thiếu môi trường hoặc lỗi runtime thành kết quả thành công; không ghi DONE khi chỉ có mock mà gate yêu cầu dữ liệu thật.

Lệnh worker/API/test/replay đã ghi tại [runbook PLAN_05](evidence/plan05/runbook.md). Kết quả kỹ thuật: [gate_05](evidence/gate_05.md). Toàn bộ calibration/release vẫn chờ bằng chứng dữ liệu và business target theo [release status](evidence/plan05/quality_release_report.md); có thể tiếp tục PLAN_06 kỹ thuật/manual, chưa tuyên bố capture/auto acceptance đã nghiệm thu trên dữ liệu thực.
