# Thử hồ sơ mẫu A4 — 17/10/2026

**Đã có bản thử và đối chiếu kỹ thuật; chưa đóng điều kiện giảm việc rà trùng được reviewer xác nhận.** Trên cùng 225.000 dòng train/validation, queue thử có **4.774 hồ sơ**, so với **5.538** hồ sơ trước: giảm **764 hồ sơ**, khoảng **13,8%**. Tập giao dịch được nhận, điểm/hit/hard trigger và TP/FP giữ nguyên. Đây là thay đổi đơn vị tổ chức hồ sơ, chưa phải mức giảm công sức thực tế hoặc tăng chất lượng phát hiện.

Queue mặc định vẫn là `entity_v1`. Phương án `a4_pattern_trial_v1` chỉ chạy khi truyền rõ vào [`review_queue`](../sme_fraud/case_queue.py); không sửa database/report vận hành. [Kế hoạch khóa](a4_pattern_trial_20261017_v2/evaluation_plan.json), [kết quả toàn bộ](a4_pattern_trial_20261017_v2/summary.json).

## Phạm vi thử đã khóa

[`a4_pattern_queue.py`](../sme_fraud/a4_pattern_queue.py) tổ chức lại **khoản được nhận riêng nhờ A4**, có `admission_basis=split_pattern`, chỉ A4 còn điểm và không hard trigger. Phạm vi là công ty + người lập + tháng lịch + cấu hình predicate A4. ID `PC_...` băm phạm vi đó, không phụ thuộc thứ tự nguồn, root đồ thị hoặc NCC đầu tiên.

- Khoản có hard trigger, đủ ngưỡng điểm thông thường, A2 hoặc hỗn hợp A2/A4 vẫn đi đường hồ sơ NCC/lô hiện hành. Lô có thành viên mạnh/hard cũng giữ đường hiện hành; không kéo hard trigger vào hồ sơ A4 yếu.
- Mẫu A4 có thể chứa nhiều NCC/ngân hàng/hóa đơn để rà chuỗi theo người lập; việc gom **không khẳng định các khoản cùng nghĩa vụ hoặc người nhận có liên hệ**. Giao diện hiển thị riêng từng khoản, NCC, ngân hàng, tài khoản và hóa đơn; ngân hàng thiếu mã được ghi chưa xác nhận. Không dựng đồ thị quan hệ chung chỉ từ phạm vi A4.
- Ngoại lệ nghĩa vụ chi, PO, hóa đơn, hợp đồng và lịch định kỳ vẫn do rule/bằng chứng gốc quyết định. Nguồn thiếu vẫn giữ cảnh báo; không có ngoại lệ mới nhằm giảm FP.
- Chỉ hỗ trợ thử theo tháng lịch. `rolling_30d` phải có thiết kế riêng, không âm thầm gom theo tháng. Tháng 31 ngày giữ cùng mẫu; sang tháng hoặc đổi người lập/công ty là phạm vi khác.

Ca năm khoản 17 triệu đến năm NCC độc lập: ba khoản cuối trước đây mở ba hồ sơ; bản thử mở **một hồ sơ mẫu**, ba khoản thành viên và hai khoản ngữ cảnh. Mở tại cùng thời điểm A4 đầu tiên, vẫn 3 điểm, ưu tiên trung bình, không hard trigger. Các khoản ngữ cảnh không bị ghi ngược thành cảnh báo dòng hoặc cộng thành thành viên đã được nhận.

## Bằng chứng, liên kết và R6

Hồ sơ mẫu lưu `pattern_scope`, `pattern_evidence_ids`, `pattern_context_ids` và `linked_case_ids`. [`ReviewStore`](../sme_fraud/review_store.py) kiểm tra ID/phạm vi, ràng buộc hit/sự kiện, người lập/công ty/tháng và thời gian; nạp đủ giao dịch ngữ cảnh/chứng từ. Sửa mất ngữ cảnh hoặc lệch bằng chứng bị từ chối trước khi cache được chốt.

Liên kết với hồ sơ NCC là điều hướng, không phải alias và không dùng để chuyển kết luận. Kết luận ở hồ sơ mẫu không đóng hồ sơ liên quan. Hash phạm vi mẫu gồm bằng chứng và ngữ cảnh; thêm thành viên/đổi nguồn làm kết luận cũ không tự áp dụng dù ID mẫu chưa đổi.

Một số hồ sơ hard trước đây mở từ khoản A4 yếu; khi khoản yếu được chuyển sang mẫu, hồ sơ hard có thể đổi ID/phạm vi. Bản thử đã kiểm tra mọi dòng hard vẫn ở hồ sơ riêng ưu tiên cao nhất, với mức ưu tiên đó đã xuất hiện tại hoặc trước đúng thời điểm dòng hard được quan sát. Có **3/10/17 dòng hard** chạm hồ sơ đổi ID/phạm vi trong ba bộ; không đồng nghĩa thêm/mất hard trigger. Danh sách nằm trong `comparison.json.changed_hard_scopes`.

Các ánh xạ giao dịch chung đều ghi `automatic_feedback_transfer=false`. Test migration xác nhận kết luận đóng/phân công cũ không chuyển vào mẫu mới; nhật ký cũ giữ nguyên và hồ sơ mới cần rà lại. Chưa migration bộ rà soát người dùng thật.

## So sánh toàn queue

Không chạy lại detector hoặc IF. Runner [`run_a4_pattern_trial.py`](../sme_fraud/run_a4_pattern_trial.py) nạp điểm/hit/lô đã khóa, buộc queue mặc định replay đúng trước khi dựng queue thử. Chính sách, code và queue/gói reviewer được khóa trước khi nối nhãn cho chẩn đoán.

| Bộ | Hồ sơ train/validation trước → thử | Hồ sơ mẫu | Hồ sơ validation trước → thử | TP/FP validation, giữ nguyên |
| --- | ---: | ---: | ---: | --- |
| 001 | 1.740 → 1.479 | 300 | 569 → 493 | 22 / 780 |
| 003 | 1.852 → 1.592 | 300 | 608 → 532 | 65 / 782 |
| 005 | 1.946 → 1.703 | 305 | 641 → 565 | 113 / 785 |

Validation gộp: **TP 200, FP 2.347**, không đổi. Ba bộ dùng cùng seed, không phải ba đợt SME độc lập. [Chẩn đoán precision thành viên hồ sơ hồi cứu](a4_pattern_trial_20261017_v2/retrospective_case_metrics.json) có đơn vị riêng; đổi cách gom có thể làm tỷ lệ này đổi dù không thêm/bớt giao dịch. Không coi đó là precision reviewer hoặc hiệu quả phát hiện tăng.

Đã so sánh toàn queue ở cùng năm cấu hình lượt/phút và hai lịch, cho baseline, trial và kiểm tra độ nhạy công sức: **180 tổ hợp tải**. Cách xếp hạng vẫn lấy lúc mở, chưa replay nâng mức sau mở; không dùng các số này để kết luận SLA phản ứng hard trigger mới.

Với **UI 5 lượt/120 phút, lịch T2–T6, validation**:

| Bộ | Chuyển ngày, baseline → trial theo heuristic cũ | Phút nhu cầu, baseline → trial theo heuristic cũ |
| --- | ---: | ---: |
| 001 | 113 → 91 | 12.495 → 11.365 |
| 003 | 124 → 103 | 13.310 → 12.175 |
| 005 | 134 → 110 | 14.060 → 12.930 |

Đây chỉ là ước lượng theo công thức ban đầu 20–45 phút/hồ sơ. **Chưa được dùng bảng này để tuyên bố tiết kiệm thời gian thực tế.** Đã tính thêm phương án không giả định tiết kiệm phút: chia toàn bộ phút baseline sang các hồ sơ mới theo tỷ lệ thành viên, bảo toàn tổng nhu cầu trên toàn train/validation. Tổng theo từng kỳ có thể dịch chuyển khi việc tách hồ sơ làm đổi kỳ mở.

Ở phương án giữ tổng phút, validation bộ **001 và 003 mỗi bộ có một công việc mẫu vượt 120 phút**, không thể nhận như một công việc không chia nhỏ trong ngày; kết quả báo `unschedulable_work_items` và chưa có ngày giải phóng hết tồn. Bộ 005 không có công việc vượt trần này. Cấu hình nghiên cứu phút thấp còn có thể gặp nhiều công việc vượt trần hơn. Cần reviewer đo độ trùng và thời gian, rồi chốt việc tách phiên/giữ nhiệm vụ nghĩa vụ riêng; không tự cắt phút để làm kết quả đẹp hơn.

## Gói reviewer và điều kiện còn thiếu

Đã chuẩn bị **905 đơn vị** không kèm nhãn gian lận: [001](a4_pattern_trial_20261017_v2/sme_fraud_001/review_packet.json), [003](a4_pattern_trial_20261017_v2/sme_fraud_003/review_packet.json), [005](a4_pattern_trial_20261017_v2/sme_fraud_005/review_packet.json). Mỗi đơn vị có phạm vi, khoản thành viên/ngữ cảnh, bằng chứng, hồ sơ baseline và liên kết; có chỗ ghi hai reviewer, chấp nhận phạm vi, việc rà trùng được xác nhận, nhu cầu giữ nhiệm vụ nghĩa vụ riêng và phút đo trước/sau.

**Hiện 0 đơn vị được reviewer xác nhận; trạng thái `awaiting_independent_review`.** Đây là gói mô phỏng phục vụ đối chiếu, không thay nghiệm thu nguồn SME thật. Cần khóa tiêu chí/chọn mẫu trước đợt review độc lập mới, đo công việc còn lặp và trường hợp phải giữ hồ sơ riêng. Chỉ chọn làm mặc định khi reviewer xác nhận phạm vi và công việc giảm, không mất phủ mẫu, không chậm hard trigger và đủ công suất theo phút đo thực tế.

Có thể mở riêng bộ thử, không dùng database vận hành:

```powershell
python -m sme_fraud.review_server --data-root data/feature_model_sync_20261017 --reports-root reports/a4_pattern_trial_20261017_v2 --database .runtime/a4_pattern_trial_20261017/reviewer.sqlite3 --port 8772
```

## Kiểm chứng

**412/412 test hồi quy đạt**, gồm **22 test mới**, 84,586 giây; **7/7 probe readiness đạt**, 0,697 giây. Có đối chứng tháng 31 ngày, đảo nguồn, snapshot nhân sự tương lai, ngân hàng khác nhau, ngoại lệ đủ/thiếu nguồn, batch/hard, và migration không kế thừa kết luận/phân công sai phạm vi. JavaScript đã kiểm tra cú pháp và renderer bảng với hai ngân hàng cùng chuỗi TK, cùng đối chứng escape HTML; chưa có kết luận usability từ reviewer.

[Test](../tests/test_a4_pattern_queue.py), [log hồi quy](../.runtime/a4_pattern_trial_20261017/tests_final.log), [probe](../.runtime/a4_pattern_trial_20261017/readiness_probes_final.log), [đối chiếu độc lập](../.runtime/a4_pattern_trial_20261017/verification.json), [checkpoint](../.runtime/a4_pattern_trial_20261017/result.json). Ba SQLite thử nạp/replay thành công; kiểm tra độc lập mở bằng `mode=ro`, đối chiếu thành viên và ưu tiên. Hash nguồn, feature, model, snapshot trước và database vận hành giữ nguyên. Thư mục thử đầu tiên có [ghi nhận không dùng](a4_pattern_trial_20261017/REJECTED.md); kết quả hiện tại chỉ ở `..._v2`.
