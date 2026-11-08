# Export lý do tiếp nhận dòng và đóng lô — 17/10/2026

**Đã sửa kỹ thuật mục 4.** Bản export bổ sung ở [admission_export_20261017_v1](admission_export_20261017_v1/summary.json), schema `admission-provenance-v2`. Đã giải thích đủ **3.315 giao dịch được nhận thêm** trên ba snapshot train/validation đã khóa. Điểm, cờ dòng, hard trigger, queue, model và 192 file nguồn/baseline được bảo vệ giữ nguyên hash. Đợt này đọc artifact, không chấm lại detector/model, không dựng lại queue hoặc ghi SQLite/feedback.

## Kết quả đối chiếu membership

| Bộ | Thành viên trước | Thành viên sau | Nhận thêm | Chỉ dòng | Dòng và lô | Chỉ lô |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 001 | 1.304 | 2.399 | 1.095 | 1.093 | 2 | 0 |
| 003 | 1.436 | 2.541 | 1.105 | 1.103 | 2 | 0 |
| 005 | 1.576 | 2.691 | 1.115 | 1.111 | 2 | 2 |
| Tổng | 4.316 | 7.631 | 3.315 | 3.307 | 6 | 2 |

Đơn vị là **giao dịch thuộc hồ sơ**, không phải số hồ sơ hoặc hit. Tập 3.315 ID mới trong export bằng đúng `membership_after − membership_before`, không có dòng mất hoặc dòng trùng. Queue gốc vẫn 5.538 hồ sơ; không cộng số hit hoặc số lý do để suy ra thay đổi toàn queue.

## File và các trường

Mỗi bộ có:

- `added_admissions_v2.csv`: đúng các ID được nhận thêm, giữ các thuộc tính nhãn/kỳ từ delta cũ để đối chiếu; nhãn không tham gia xác định membership hoặc lý do.
- `admission_evidence.jsonl`: một record bằng chứng cho mỗi dòng, có locator, hash record gốc và nội dung bằng chứng.
- `membership_comparison.json`: số lượng/hash tập ID, đối chiếu thành viên và danh sách dòng chỉ nhận qua lô.
- `export_commitment.json`: hash ba file mới, commitment dự đoán gốc và delta cũ.

| Trường CSV | Ý nghĩa |
| --- | --- |
| `rule_score`, `row_operational_alert`, `row_hard_trigger` | Giá trị quan sát gốc tại dòng, không ghi ngược kết quả đóng lô |
| `row_rule_ids`, `row_admission_basis`, `row_review_rule_ids` | Rule/lý do ở dòng theo `rule_scores.csv` |
| `effective_admission_basis` | Hợp lý do tiếp nhận của dòng và các nhóm đóng lô thực sự nhận giao dịch |
| `effective_review_rule_ids` | Hợp rule tiếp nhận mẫu chia nhỏ từ dòng/nhóm lô; vẫn là trường review, không phải toàn bộ rule có điểm |
| `admission_source` | `row`, `batch_closed` hoặc `row|batch_closed` |
| `effective_admitted_at` | Thời điểm bằng chứng tiếp nhận đã có trong snapshot |
| `case_ids` | Mảng JSON ID hồ sơ thật đang chứa giao dịch |
| `batch_event_ids`, `event_rule_ids` | Mảng JSON ID sự kiện nhận giao dịch và rule của các sự kiện đó |
| `row_hit_evidence_ids` | Mảng JSON ID hit còn điểm của dòng được nhận tại dòng |
| `admission_evidence_ref` | `admission_evidence.jsonl#AE_...`; phần sau `#` tra bằng trường `admission_evidence_id` |

Các trường rule/lý do nhiều giá trị dùng dấu `|`; trường ID nhiều giá trị là chuỗi mảng JSON. Locator trong JSONL gồm `path`, `identity_field`, `identity`; đường dẫn tính từ thư mục export của bộ. Ví dụ locator hit trỏ `rule_hits.jsonl` theo `evidence_id`, locator lô trỏ `batch_events.jsonl` theo `event_id`. Hash record JSON chuẩn hóa và hash toàn file gốc trong plan hỗ trợ kiểm tra nội dung tương ứng.

## Hai dòng đã tái hiện

[CSV mới của bộ 005](admission_export_20261017_v1/sme_fraud_005/added_admissions_v2.csv) ghi cho cả `T000021842` và `T000068394`:

| Trường | Giá trị |
| --- | --- |
| `rule_score` / `row_operational_alert` / `row_hard_trigger` | `0` / `0` / `0` |
| `row_admission_basis` / `row_review_rule_ids` | rỗng / rỗng |
| `effective_admission_basis` | `split_pattern` |
| `effective_review_rule_ids` / `event_rule_ids` | `A4` / `A4` |
| `admission_source` | `batch_closed` |
| `case_ids` | `["BC_ed1f5db6ff4fec85"]` |
| `batch_event_ids` | `["BE_ffeb37e528e38a9b942c"]` |
| `effective_admitted_at` | `2025-01-12T10:00:00+07:00` |

Hai dòng có record `AE_...` riêng trong [bằng chứng bộ 005](admission_export_20261017_v1/sme_fraud_005/admission_evidence.jsonl), cùng trỏ tới sự kiện A4 gốc: ba khoản trong tháng 1, tổng 54.835.000 VND; `T000059266` là khoản trước trong ngữ cảnh, không được tự coi là thành viên mới chỉ vì được tham chiếu.

## Quy tắc truy vết và phạm vi

Exporter dùng chính `batch_groups` của queue với **cấu hình đã lưu trong snapshot**. Event 0 điểm/bị loại hoặc lô không đạt chính sách tiếp nhận không trở thành lý do. ID ở `related_transaction_ids` là ngữ cảnh; chỉ thành viên của nhóm lô đủ điều kiện được nhận. Không lấy toàn bộ rule/event của hồ sơ để gán cho từng giao dịch.

Với nhóm sự kiện chồng thành viên, một giao dịch có thể được nhận qua thành phần liên thông. JSONL lưu toàn bộ nhóm, danh sách thành viên và cờ `direct_participant` cho từng event để phân biệt đường trực tiếp và qua nhóm; hard trigger của nhóm không ghi đè cờ hard ở dòng. Snapshot thiếu hit, thiếu liên kết case–event, khác công ty, sai thời điểm hoặc lệch membership sẽ bị từ chối export.

Hai module mới [admission_export.py](../sme_fraud/admission_export.py) và [export_admissions.py](../sme_fraud/export_admissions.py) phục vụ export riêng. Runner [run_split_pattern_review.py](../sme_fraud/run_split_pattern_review.py) cũng xuất thêm CSV v2/JSONL/commitment cho các lần chạy tương lai vào thư mục mới. File `added_admissions.csv` cũ vẫn giữ nghĩa lịch sử; mọi báo cáo đã khóa được giữ nguyên.

```powershell
python -B -m sme_fraud.export_admissions --output reports/admission_export_new
```

**Kiểm tra:** 437/437 test đạt, gồm 12 test mới; [log hồi quy](../.runtime/admission_export_20261017/tests_final.log). 7/7 probe readiness đạt; [log probe](../.runtime/admission_export_20261017/readiness_probes.log). [Kiểm tra artifact độc lập](../.runtime/admission_export_20261017/verification.json) lần theo mọi locator tới record gốc, đối chiếu điểm/cờ/nhãn/kỳ, tập ID, case/event và commitment, xác nhận 192 file giữ nguyên. Bản sửa đóng vấn đề truy vết export; replay ưu tiên theo sự kiện, công sức/reviewer A4 và nghiệm thu nguồn thật vẫn là việc riêng.
