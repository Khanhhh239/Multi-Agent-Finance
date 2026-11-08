# Kiểm tra sau khi đóng lô cùng timestamp

Ngày kiểm tra: 16/10/2026. Đã sửa R4 trong [báo cáo readiness](rule_readiness_recheck_20261016.md): bổ sung bằng chứng sau khi đóng lô cho P1 và A1–A4, đưa kết quả đủ ngưỡng vào hàng đợi rà soát.

## Chính sách thời gian

Mỗi nhóm giao dịch cùng `posted_at` trong snapshot được chấm theo hai bước:

1. Chấm từng dòng bằng nguồn đã biết và lịch sử **trước timestamp**. Điểm, hit và feature của các dòng cùng thời điểm không đọc lẫn nhau.
2. Khi đã đọc đủ nhóm, kiểm tra tổng lô bằng lịch sử trước đó cộng toàn bộ thành viên hiện tại. Kết quả nằm trong `batch_events`, có `phase=batch_closed`, không ghi ngược vào điểm/hit từng dòng.

Phát hiện lô có thời điểm `detected_at` bằng timestamp vừa chốt và pha đóng lô riêng. Không dùng thứ tự ID để giả lập khoản nào xảy ra trước. Thêm giao dịch tương lai không đổi sự kiện lô đã chốt; đảo thứ tự dòng đầu vào không đổi sự kiện.

Đây là xử lý snapshot, chưa phải dịch vụ streaming có watermark. ETL cần bảo đảm snapshot/cutoff chứa trọn lô cùng timestamp; engine không tự biết còn bản ghi chưa được xuất từ hệ thống nguồn.

## Phạm vi kiểm tra

| Rule | Kiểm tra khi chốt lô |
| --- | --- |
| P1 | Ít nhất hai khoản hiện tại cùng công ty–NCC–số hóa đơn đã chuẩn hóa; cộng toàn lịch sử chi tiền mặt/ngân hàng, kể cả ngoài cửa sổ chia nhỏ. Tổng vượt gross + dung sai 1 VND tạo 20 điểm, hard trigger. |
| A1 | Ít nhất hai khoản hiện tại cùng người nhận trong cửa sổ ngắn; tổng và số lượng xét cả lô, so với hạn mức tương ứng của từng người lập. |
| A2 | Cùng người lập–người nhận, có ít nhất hai khoản hiện tại; tổng số khoản trong cửa sổ dài đạt từ ba và tổng đạt hạn mức. |
| A3 | Cụm NCC liên kết còn hiệu lực tại cutoff, ít nhất hai khoản hiện tại; kiểm tra cả nhánh 3 ngày/85% và 30 ngày/100% theo policy. Tắt graph không tạo A3. |
| A4 | Bộ đếm khoản cận hạn mức của cùng người lập gồm lịch sử và lô hiện tại; giữ tháng lịch hoặc 30 ngày trượt theo cấu hình, cùng ngoại lệ quyền chi đã kiểm tra. |

Ngưỡng/trọng số giữ nguyên. A2 4 điểm và A4 3 điểm có thể chỉ là tín hiệu lô; không tự nâng lên ngưỡng vận hành 7. Các tín hiệu cùng nhóm A chỉ lấy điểm cao nhất, không cộng chồng A1–A4. P1 vẫn là hard trigger.

Ngoại lệ trả góp, request/PO độc lập, hợp đồng và lịch định kỳ vẫn phải có bằng chứng hợp lệ. Tổng quyền chi gồm toàn bộ lô nên không thể tái sử dụng một trần cho từng khoản đồng thời. Khi loại nghĩa vụ độc lập, tổng tiền hiển thị chỉ gồm phần thực sự được kiểm tra; tổng thô được giữ riêng để đối chiếu.

Định danh người nhận của kiểm tra lô dùng ngân hàng + số TK; chi tiền mặt dùng NCC. TK thực thiếu ngân hàng ghi `information_gap`, 0 điểm. P1 không gộp số hóa đơn rỗng; gross mâu thuẫn/thiếu tạo information gap trong kiểm tra lô thay vì tự chọn một gross để hard trigger. Đây không phải bản sửa toàn bộ R2: A1/A2/B7 theo từng dòng vẫn cần rà soát riêng.

## Hàng đợi, file kết quả và UI

- [Bộ kiểm tra lô](../sme_fraud/batch_controls.py#L102) tạo sự kiện có ID ổn định theo công ty, cutoff, rule, scope và các giao dịch hiện tại; lịch sử liên quan nằm riêng trong `related_transaction_ids`.
- [Engine](../sme_fraud/rules.py#L818) gọi kiểm tra sau khi chấm xong mọi dòng, trước khi commit lịch sử dùng chung; không cộng lô hai lần vào quyền chi.
- [Hàng đợi](../sme_fraud/case_queue.py#L64) gộp tín hiệu lô trùng thành viên, áp điểm theo nhóm và xử lý sau các điểm dòng cùng thời điểm. Nếu đã có hồ sơ liên quan thì bổ sung bằng chứng; không tạo trùng thành viên giao dịch. Hồ sơ mới từ lô có `case_type=batch` và ID `BC_...`.
- `operational_members(result)` đối soát cả cảnh báo theo dòng và thành viên lô đủ ngưỡng. Cờ `operational_alert` của từng dòng không được sửa thành nhãn cảnh báo lô.
- Các runner rules/repair/noise/spec/evidence ghi thêm **`batch_events.jsonl`**; `case_queue.csv` có `batch_event_ids`. Các metric TP/FP theo dòng vẫn giữ đơn vị cũ; không diễn giải chúng là metric của lô.
- [ReviewStore](../sme_fraud/review_store.py#L173) nạp bằng chứng, giao dịch hiện tại/ngữ cảnh và đường dẫn đồ thị của lô. Cache có fingerprint của file mới; hồ sơ tham chiếu sự kiện nhưng thiếu file/bằng chứng bị từ chối. Snapshot cũ không có sự kiện lô vẫn đọc được.
- [UI](../review_ui/app.js#L107) hiển thị phần “Đối chiếu các khoản cùng thời điểm”, tổng tiền, giá trị hóa đơn, phần vượt và liên kết tra cứu giao dịch; nhật ký có sự kiện đóng lô.

Hash mã nguồn của quy trình nghiệm thu/đánh giá đã bao gồm module kiểm tra lô. Không tự cập nhật các snapshot báo cáo hoặc database UI cũ; cần sinh snapshot mới bằng runner đã cập nhật.

## Kiểm chứng

**227/227 test đạt**, không failure/error, gồm 209 test trước và 18 test mới: [16 test lô](../tests/test_batch_controls.py), [2 test nạp artifact/cache](../tests/test_review.py). [Kết quả và hash](../.runtime/batch_close_20261016/result.json), [log](../.runtime/batch_close_20261016/tests.log).

Các đối chứng gồm tiền mặt/ngân hàng, lịch sử ngoài cửa sổ, thiếu/mâu thuẫn hóa đơn, chia nhỏ A1–A4, biên ngày/tháng, graph bật/tắt, trả góp/PO độc lập hợp lệ, vượt trần request, nguồn thu hồi/tương lai, thiếu/khác ngân hàng, thứ tự đầu vào, giữ điểm quá khứ và không trùng thành viên hàng đợi. Cú pháp JS, render phần bằng chứng lô và escape HTML đã kiểm tra; chưa kiểm tra trực quan trong trình duyệt.

```powershell
python -B -m unittest discover -s tests
```

Hai probe R4 trong file audit ban đầu kỳ vọng hit theo dòng, phản ánh thiết kế trước sửa và được giữ làm snapshot lịch sử. Hồi quy hiện tại kiểm tra `batch_events` theo đặc tả đóng lô; không cần bỏ bất biến nhân quả của test cũ.

Chưa chấm lại benchmark lớn hoặc nghiệm thu nguồn SME thật, nên chưa khẳng định mức tăng recall/giảm FP thực địa. R5 đã có [kiểm định nguồn quyền](rule_authority_validation.md), R2 đã có [định danh ngân hàng thống nhất](rule_bank_identity.md), R8 đã có [lịch sử người ký dùng chung](rule_signer_history.md), R7 đã có [kiểm định nguồn ngoại lệ](rule_exception_validation.md), R6 đã có [định danh và migration hồ sơ](rule_case_identity.md). Bước tích hợp/nghiệm thu vẫn còn thiếu.
