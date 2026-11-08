# Artifact, đơn vị đo và đối chiếu hồ sơ — 17/10/2026

Đã đối chiếu chỉ đọc hai lượt đánh giá, mỗi lượt gồm ba bộ `001/003/005`, trên cùng **225.000 quan sát train/validation**. Hai lượt dùng chung giao dịch; không cộng thành 450.000 quan sát độc lập. Không chấm test hoặc chuyển trạng thái người dùng trong lần kiểm tra này.

## Đường dẫn theo lượt

| Lượt | Thư mục báo cáo từng bộ | Hồ sơ trong ba SQLite riêng |
| --- | --- | ---: |
| Đồng bộ feature/model, trước sửa tiếp nhận A2/A4 | `reports/feature_model_sync_20261017/sme_fraud_00x/` | 3.434 |
| Sau sửa tiếp nhận A2/A4 | `reports/split_pattern_admission_20261017_v2/sme_fraud_00x/` | 5.538 |

Đây là **thư mục báo cáo**. Nguồn và cache feature nằm ở `data/feature_model_sync_20261017/sme_fraud_00x/`. Model mới của lượt đồng bộ nằm trong thư mục báo cáo lượt đầu; lượt tiếp nhận dùng lại model tương thích và không fit lại.

## Đọc từng artifact

Các file sau thuộc lượt **đồng bộ trước sửa tiếp nhận**:

| File | Nội dung và giới hạn |
| --- | --- |
| `score_changes_train_validation.csv` | Các ID đổi điểm, hard trigger hoặc cờ cảnh báo dòng; có giá trị trước/sau. Không phải danh sách mọi thay đổi ID hồ sơ |
| `score_change_analysis.json` | Tổng hợp thay đổi theo kỳ và các dòng gian lận mô phỏng mất cảnh báo, kèm giao dịch/hit hiện tại tại snapshot đó |
| `changed_hits_train_validation.csv` | Thêm/mất **hit còn điểm** theo ID/rule. Hit chẩn đoán 0 điểm và ngoại lệ phải xem trong `rule_hits.jsonl` |
| `comparison_train_validation.json` | Chất lượng theo dòng, từng rule/công ty, hard negatives, loại gian lận, chế độ kế toán, precision hồ sơ hồi cứu và tải 1/3/5 hồ sơ/công ty/ngày |
| `case_identity_comparison.json` | Hồ sơ cũ và các hồ sơ mới có giao dịch chung; `automatic_feedback_transfer=false` |

Lượt **sau sửa tiếp nhận** dùng `added_admissions.csv` và `comparison.json`. Điểm và hit không đổi, nên không có bộ file delta điểm/hit mới với các tên trên. `previous_losses_review.json` nằm ở gốc `reports/split_pattern_admission_20261017_v2/`, đối chiếu các dòng từng mất cảnh báo. Mỗi bộ vẫn có `rule_scores.csv`, `rule_hits.jsonl`, `case_queue.csv`, `case_events.csv`, `batch_events.jsonl` và `case_identity_comparison.json` để lần ngược bằng chứng.

## Không trộn đơn vị đo

- **Hit** là điều kiện phát hiện của một rule. Nhiều hit có thể thuộc cùng họ điểm hoặc cùng một giao dịch.
- **Giao dịch được nhận** là hợp của cảnh báo dòng và các khoản tham gia sự kiện đóng lô đủ điều kiện. Điểm dòng không được ghi ngược sau đóng lô.
- **Hồ sơ** được gom từ giao dịch theo phạm vi/cửa sổ; một hồ sơ có thể chứa nhiều giao dịch. Precision hồ sơ hồi cứu tính nhãn thành viên tại cutoff, khác độ hữu ích theo bằng chứng khi mở hồ sơ trong mô phỏng tải.

Vì vậy, không cộng số hit mới hoặc số dòng đổi điểm để suy ra số hồ sơ/TP/FP của toàn queue. Lượt đồng bộ báo chất lượng cảnh báo dòng; lượt tiếp nhận báo đầy đủ tập giao dịch được nhận, gồm đóng lô. Phải dùng đúng đơn vị khi đối chiếu.

**Ví dụ thực tế:** bộ `005` sau sửa có hai dòng validation `T000021842`, `T000068394` được nhận riêng nhờ đóng lô. Cả hai vẫn có `rule_score=0`, `operational_alert=0` trong `rule_scores.csv`. Chúng có mặt trong `added_admissions.csv` vì file này ghi thay đổi tập nhận hồ sơ. Các trường `admission_basis`/`review_rule_ids` của file này được lấy từ dòng, nên có thể rỗng ở trường hợp chỉ nhận nhờ lô. Tra nguyên nhân qua `case_queue.csv.batch_event_ids` và `batch_events.jsonl`; [kết quả kiểm tra](../.runtime/artifact_inventory_20261017/verification.json) lưu liên kết hồ sơ/sự kiện cho hai dòng này.

**Đã sửa export ở phiên bản bổ sung:** [added_admissions_v2.csv của bộ 005](admission_export_20261017_v1/sme_fraud_005/added_admissions_v2.csv) giữ `row_*` đúng quan sát gốc và ghi `effective_admission_basis=split_pattern`, `event_rule_ids=A4`, ID hồ sơ/lô cùng reference tới record bằng chứng cho hai dòng này. Cả ba bộ đã đối chiếu đủ 3.315 ID nhận thêm; CSV cũ, score/hit/queue/model và commitment gốc giữ nguyên. [Schema và kết quả](rule_admission_export.md). Khi cần giải thích tiếp nhận, dùng bản v2 thay vì suy luận `admission_basis` cũ là lý do hiệu lực.

## Đối chiếu ID không thay thế migration R6

`case_identity_comparison.json` chỉ chứng minh có giao dịch chung. Giao dịch chung không đủ để xác nhận hai hồ sơ có phạm vi, bằng chứng và thời điểm tương đương, hoặc để chuyển phản hồi/phân công. File này không phải bảng alias đã được phê duyệt theo R6.

Khi áp dụng vào bộ rà soát có lịch sử người dùng, dùng đúng snapshot trước/sau và nhật ký audit theo [quy trình R6](rule_case_identity.md): chỉ chuyển trường hợp tương đương một-một; hồ sơ tách/gộp, đổi phạm vi hoặc mơ hồ phải rà lại. Sáu SQLite ở đây là cache đánh giá riêng; database/feedback vận hành chưa được migration.

## Bằng chứng kiểm tra

[Kết quả máy đọc](../.runtime/artifact_inventory_20261017/verification.json) và [log kiểm tra](../.runtime/artifact_inventory_20261017/verification_final.log) xác nhận:

- Các file delta điểm/hit/tiếp nhận khớp từng ID với snapshot tương ứng; số liệu TP/FP, hard negatives, loại gian lận, chế độ kế toán, từng rule/công ty và tổng công sức khớp nguồn đã lưu.
- Thành viên queue là đúng tập được nhận, không trùng và không lẫn công ty; mỗi hồ sơ có đúng một sự kiện mở.
- Bảng hồ sơ và bảng thành viên trong sáu SQLite khớp CSV; chỉ mở SQLite bằng `mode=ro`.
- Hash nguồn, model/baseline và đầu ra dự đoán đã khóa giữ nguyên. Kiểm tra replay model/cache trước đó vẫn được lưu trong [lượt đồng bộ](../.runtime/feature_model_sync_20261016/artifact_verification.json) và [lượt tiếp nhận](../.runtime/split_pattern_admission_20261017/artifact_verification.json); lần này không chạy lại model hoặc viết lại cache.

Ước lượng công sức vẫn là mô phỏng 20–45 phút/hồ sơ với năng lực mỗi ngày lịch, không phải thời gian/SLA đã đo trên SME thật.

**Đã sửa công suất sau rà lại:** simulator nhận riêng lượt/phút và dùng chung hợp đồng với API; cấu hình nghiên cứu 5/225 được đặt tên riêng với UI 5/120. Đã tính lại tải, gồm lịch T2–T6, tồn cuối kỳ và thời gian xử lý tồn, ở thư mục mới; không viết lại sáu snapshot này. Thứ hạng vẫn lấy lúc mở, chưa cập nhật nâng ưu tiên đang chờ. [Bản sửa và kết quả](rule_review_capacity.md), [việc còn mở](rule_readiness_next_20261017.md).
