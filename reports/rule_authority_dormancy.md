# Thẩm quyền C2/C3 và ngoại lệ mùa/năm B6

Ngày kiểm tra: 15/10/2026. Bản sửa giữ nguyên trọng số, ngưỡng tốc độ 60 giây, thời gian ngủ đông 180 ngày và P90 lịch sử. Nguồn mới chỉ thay proxy khi có bằng chứng đầy đủ, đã được quan sát trước hành động.

**Cập nhật 16/10/2026:** đã sửa lịch sử nhân sự C2/C3 để thay đổi hồ sơ không vô hiệu bằng chứng đã ký và không dùng vai trò/hạn mức sau hành động. Toàn bộ 209/209 test đạt; [chi tiết và 11 test mới](rule_authority_history.md). Số liệu 181 test và snapshot validation bên dưới thuộc lần chốt đợt 6 trước cập nhật này.

**Cập nhật kiểm định nguồn R5 (16/10/2026):** quyền và coverage từ chối boolean/enum/hạn mức/ngày giờ sai trước khi chấm; 247/247 test đạt. [Miền dữ liệu, đối chứng và giới hạn](rule_authority_validation.md).

## C2 — quyền tự duyệt và ủy quyền

Khi `approval_authority_coverage` xác nhận ma trận đầy đủ cho `self_approve`, C2 không còn dựa riêng vào `employees.self_approval_limit_vnd`. Engine đối chiếu:

- nhân viên hoặc vai trò được cấp quyền;
- loại giao dịch, phòng ban, dự án và khoảng tiền;
- thời gian hiệu lực tại lúc duyệt;
- quyền `self_approval_allowed`;
- chính sách thường xuyên hoặc ủy quyền tạm thời có `delegated_by_id`;
- hồ sơ được người khác phê duyệt và đã quan sát trước thời điểm duyệt.

Không có quyền phù hợp, quyền mơ hồ, ma trận coverage chồng lặp, nguồn bị thu hồi hoặc tự cấp quyền đều không tạo ngoại lệ. Khi chưa có coverage hợp lệ, hạn mức tự duyệt trên master vẫn được dùng để giữ tương thích với dữ liệu hiện tại.

## C3 — cấp thẩm quyền thật

Khi coverage cho `approve` có hiệu lực, điều kiện “cấp cao” lấy từ `authority_level=high|executive` của đúng người duyệt và đúng phạm vi nghiệp vụ. Số tiền không còn được dùng để suy ra cấp thẩm quyền. Vì vậy giao dịch nhỏ do cấp cao duyệt dưới 60 giây vẫn có thể bị phát hiện, còn giao dịch lớn thuộc quyền chuẩn không bị đẩy vào C3 chỉ vì số tiền.

Nếu chưa có coverage, engine giữ `high_approval_vnd` làm proxy để không làm mất cảnh báo trên các dataset cũ. Ma trận đã tuyên bố đầy đủ nhưng thiếu quyền khớp không được quay lại dùng proxy số tiền.

## B6 — khoản theo mùa hoặc hằng năm

B6 vẫn yêu cầu NCC không phát sinh ít nhất 180 ngày, có tối thiểu 20 khoản lịch sử và khoản hiện tại vượt P90. Hit được loại khi khoản hiện tại có:

- lịch `annual` hoặc `seasonal` được duyệt, đúng NCC, nghiệp vụ và cửa sổ `MM-DD`;
- đúng hợp đồng, hóa đơn và tài khoản nhận tiền nếu lịch khai báo các ràng buộc đó;
- tổng mọi khoản trong cùng lần xuất hiện của mùa/năm, gồm các khoản cùng timestamp, không vượt `expected_amount_vnd + tolerance_vnd`;
- `allow_partial=1` nếu được phép trả nhiều đợt.

Lịch `recurring_payments` tần suất `yearly` hiện có cũng được chấp nhận với cùng kiểm tra tổng năm. Lịch tương lai, bị thu hồi, mơ hồ, sai cửa sổ hoặc vượt trần không loại B6.

## Nguồn và kiểm tra

[Schema thẩm quyền](../sme_fraud/authority_policy.schema.json), [CSV mẫu thẩm quyền](../examples/authority_sources/README.md), [schema nghĩa vụ chi](../sme_fraud/payment_evidence.schema.json) và [CSV lịch thanh toán](../examples/payment_evidence_sources/vendor_payment_schedules.csv) là hợp đồng nhập liệu của đợt này.

Có 12 đối chứng trực tiếp: quyền tự duyệt vượt hạn mức master, ma trận từ chối, ủy quyền hợp lệ, coverage chồng lặp, nguồn tương lai, cấp cao với khoản nhỏ, cấp chuẩn với khoản lớn, fallback proxy, lịch mùa/năm hợp lệ, lịch sai phạm vi/tương lai/vượt trần, lịch `yearly` hiện có và giới hạn tổng cho khoản cùng thời điểm. Toàn bộ 181 kiểm thử của dự án đều đạt; xem [kết quả máy đọc](../.runtime/authority_dormancy_test_result.json) và [log chi tiết](../.runtime/authority_dormancy_tests.log).

Đã chấm lại 37.500 dòng train/validation của seed `2026101401`; không đọc split test và không dùng ML. Dataset đóng băng chưa có ba nguồn mới nên tập candidate, hit góp điểm và hàng đợi đều giữ nguyên:

| Split | Rule/hàng đợi | TP | FP | Thêm | Loại |
| --- | --- | ---: | ---: | ---: | ---: |
| Train | B6 | 0 | 0 | 0 | 0 |
| Train | C2 | 10 | 0 | 0 | 0 |
| Train | C3 | 0 | 0 | 0 | 0 |
| Train | Hàng đợi | 63 | 332 | 0 | 0 |
| Validation | B6 | 0 | 0 | 0 | 0 |
| Validation | C2 | 6 | 0 | 0 | 0 |
| Validation | C3 | 0 | 0 | 0 | 0 |
| Validation | Hàng đợi | 30 | 169 | 0 | 0 |

Đây là kiểm tra chống hồi quy khi thiếu nguồn, chưa phải bằng chứng giảm FP trên SME thật. [Kết quả, replay và checksum](rule_repairs/authority_dormancy/seed_2026101401/sme_fraud_003/comparison.json).

## Giới hạn

Nguồn coverage là cam kết rằng ma trận cho action/khoảng thời gian đã đầy đủ. Nếu chỉ xuất một phần quyền nhưng khai coverage đầy đủ, engine có thể xem quyền còn thiếu là không hợp lệ. Quy trình ETL phải đối soát số người dùng, vai trò và thời gian hiệu lực trước khi bật coverage.

Engine chưa xác minh chữ ký hay quyết định ủy quyền bên ngoài hệ thống. Nghiệm thu cuối cần log IAM/workflow và kết luận rà soát độc lập của doanh nghiệp.
