# CR-022 — sửa P1-NATIVE-LATE-INVOICE

Bản sửa chặn nguồn hóa đơn khai báo đến muộn ở nhánh P1 native, gồm current, lịch sử và nhóm đồng thời. R2 tổng thể vẫn **PARTIAL**; chưa nghiệm thu toàn engine/pipeline.

## Bằng chứng kiểm thử

- [97 kiểm thử liên quan](focused_tests.json) qua trước khi bỏ metadata coverage bổ sung; gồm P1 native/canonical, nguồn, thời gian feature/lịch sử và adapter parity.
- [15 kiểm thử tương thích sau chỉnh metadata](compatibility_tests.json) qua: 10 regression mới và bộ retained core. Fixture cũ khớp nguyên checksum toàn bộ đầu ra rules, feature và contract; không sửa fixture hoặc expected hash để làm đẹp kết quả.
- **657 kiểm thử hồi quy cuối pass**, 0 failure/error/skip, 548.448 giây; gồm 10 regression mới. [JSON](native_tests.json), [log](native_tests.log). Exit 0, toàn bộ test được ghi nhận; fixture cũ không bị đổi expected.
- [Audit cuối](audit_final/summary.json) qua 7 tình huống, **exit 0**; P1-NATIVE-LATE-INVOICE có trạng thái FIXED_IN_TESTED_SCOPE. Hai giới hạn biểu diễn legacy (coverage và thời điểm phân bổ) vẫn ghi riêng, không coi native 0 tương đương canonical null.
- [Trước sửa](before_tests.json): 10 ca mới, 7 failure/2 error; có cả lỗi fixture offset không đúng wire format +07:00, đã chuyển thành kiểm riêng helper so sánh instant. [Focused đầu](initial_focused_tests.json) giữ lỗi fixture đó. Không xóa lịch sử chẩn đoán.
- Lượt hồi quy đầu bị ngắt khi test retained core phát hiện ba trường metadata coverage làm đổi checksum. Đã bỏ phần metadata không cần thiết, giữ nguyên bản sửa; test retained core nghiêm ngặt sau đó qua. [Log lượt ngắt](first_regression_interrupted.log).

## Hành vi đã sửa

1. Current invoice_issued_at hoặc invoice_observed_at sau cutoff: P1 tạo information_gap, points=0, hard_trigger=0, signal=null, role=information_request. Không dùng hoặc đưa gross/tổng từ nguồn chưa biết vào căn cứ. Đây là yêu cầu bổ sung nguồn, không phải evaluated_no_hit.
2. Lịch sử có header chưa khả dụng ở cutoff hiện tại: row/batch giữ information_gap, không phát risk từ tổng từng phần.
3. Current chưa có header khả dụng không được gom vào cap/tổng nhóm. Nhóm đủ nguồn vẫn tổng hợp riêng: row 0, group 20; không cộng điểm nhóm vào từng dòng.
4. Giữ dòng lịch sử gốc. Khi chứng từ đã đến, khoản chi sau được dùng lịch sử đó; kết quả các khoản cũ không đổi. Cutoff bằng thời điểm nguồn được nhận, sau một giây bị chặn.
5. So instant có múi giờ trong helper; wire native vẫn yêu cầu timestamp canonical +07:00 như trước, không mở thêm định dạng wire.

Giữ P1=20, dung sai >1 VND, chính sách khoản thanh toán trước và số dòng. Shape MethodScore/RuleResult, input schemas, feature/model và active configuration không đổi. Chỉ rules.py/batch_controls.py và helper p1_timing.py được sửa/thêm cho logic chấm này; không sửa các luật khác.

## Giới hạn còn lại và tiến độ

Header legacy không khai báo thời gian vẫn giữ hợp đồng cũ, không được chứng nhận as_of. Native chưa biểu diễn coverage/availability theo phân bổ hoặc signed correction như canonical; không suy thành nghiệm thu toàn engine. Canonical vẫn trả unavailable/null khi thiếu nguồn, tổng rules vẫn rules_incomplete/null.

Backend local http://127.0.0.1:8766 được giữ chạy, dùng kho demo cũ riêng; snapshot đã nhập vẫn giữ nguyên. Bản web hiện là status page/backend, chưa UI nghiệp vụ mới. Không fit hoặc đổi active model/weight/queue trong task này.

Để đẩy tiến độ sau bản sửa: ưu tiên nối luồng chạy phân tích từ snapshot qua API có kiểm quyền, rồi một màn hình demo tối thiểu nhập → kiểm tra → lưu → xem P1/E3 và phần chưa đủ nguồn. Chưa mở hàng đợi hoặc coi các luật chưa được nối là không vi phạm. Việc đó cần task riêng, không được thực hiện ngầm trong bản sửa P1.

[Bảo toàn feature/model và hash mã cuối](preservation_final.json), [adapter giữ gap của row/batch](native_adapter_time_parity_final.json), [dịch vụ và snapshot sau sửa](live_final.json), [provenance](provenance.json). Backend 8766 healthy; snapshot cũ đọc qua HTTP 200 và chấm lại vẫn đủ 3 dòng, một snapshot, kết quả canonical không đổi.
