# Hợp đồng quan hệ hiện hành v1

Áp dụng cho feature contract `causal-evidence-20261024-v4`. Cutoff là `posted_at` của giao dịch; timestamp có bao gồm đúng cutoff.

| Nhóm | Trạng thái được dùng | Giá trị được xuất |
|---|---|---|
| Phone/address overlap | Snapshot nhân sự/NCC mới nhất có `recorded_at <= cutoff`, chuẩn hóa cùng B2, cùng công ty | Các cột `employee_*_overlap_current` |
| Graph | Slot bank/phone/representative còn hiệu lực từ master và liên kết đã biết | `graph_employee_count_current`, `linked_vendor_count_current` |
| Thành viên graph | Nhân sự/NCC có master hiện hành thuộc công ty đang chấm | Chỉ cộng các thành viên này vào count; NCC được tính cả chính nó |
| Quan hệ lịch sử đã hết hiệu lực | Không đóng góp vào nhóm feature quan hệ này | Chưa có cột lịch sử và chưa chọn cửa sổ lịch sử |

Mỗi `(company_id, source, link_type)` có một slot hiện hành. Master mới thay phone/bank đã có; contact rỗng hoặc không được cung cấp trong snapshot mới gỡ contact cũ. Trường đại diện được áp dụng khi snapshot có `representative_id`; giá trị rỗng gỡ đại diện. Một cạnh không có timestamp mới không thể khôi phục trạng thái đã gỡ. Master có ưu tiên cao hơn mirror cùng thời điểm. Snapshot cùng ID/timestamp mâu thuẫn bị từ chối, kể cả khi chỉ khác địa chỉ.

`entity_links` cho phép bank/phone/representative. Address là đối chiếu yếu, không là cạnh mạnh. `active` thay slot, `revoked/deleted/inactive` gỡ slot. Revocation chỉ rõ một target cũ không được hủy replacement khác đang có hiệu lực. Tài khoản thực cần bank institution theo chuẩn phase3; revocation thiếu định danh institution không tự hủy cạnh tài khoản đã xác định ngân hàng.

Khi đổi công ty, bỏ role thành viên và các slot master ở công ty cũ tại thời điểm phiên bản mới được biết, thêm chúng vào công ty mới. Không sửa lại vector/hit đã tính tại cutoff trước đó. Bộ đếm direct overlap giảm đúng token chuẩn hóa tại `previous.company_id`; nếu người khác vẫn giữ token, quan hệ của người đó vẫn còn.

UnionFind chỉ là bộ tính thành phần cho trạng thái hiện hành: khi edge/membership đổi, dựng lại từ các slot còn hiệu lực. Nó không giữ một thành phần “đã từng nối” xuyên suốt thời gian. Graph component count tính toàn thành phần hiện hành; đường bằng chứng B2 vẫn có giới hạn độ sâu của rules. Vì vậy không dùng count để khẳng định mọi đường trong thành phần đều là một hit B2.

Lịch sử gốc không bị xóa khỏi nguồn; phiên bản cũ vẫn được dùng khi chấm giao dịch trước thời điểm đổi. Nếu cần feature “đã từng liên hệ”, phải xác định tên cột, loại sự kiện, thời điểm biết, cửa sổ quan sát và cách xử lý thu hồi riêng trước khi đưa vào model; không tái dùng tên `_current` cho tích lũy lịch sử.

Ngữ nghĩa “hiện hành” trong hợp đồng này là phiên bản master/liên kết hiện hành đã biết, không phải xác nhận mọi sự kiện HR hoặc thay đổi ngoài hệ thống đã được nhập đủ. Timestamp phải do nguồn cung cấp đúng thời điểm biết; nguồn chỉ giữ bản cuối kỳ cần xuất lịch sử để backtest.
