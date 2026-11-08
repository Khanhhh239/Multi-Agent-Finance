# Nguồn thẩm quyền C2/C3

`approval_authority_coverage.csv` xác nhận ma trận thẩm quyền đầy đủ cho `self_approve`, `approve` hoặc cả hai trong một khoảng thời gian. Chỉ khi coverage hợp lệ, engine mới thay hạn mức master/proxy số tiền bằng ma trận.

`approval_authorities.csv` khai báo quyền theo nhân viên hoặc vai trò, nghiệp vụ, phòng ban, dự án và khoảng tiền. `authority_type=delegation` cần `delegated_by_id` khác người nhận ủy quyền. Quyền tự duyệt phải có `self_approval_allowed=1`; cấp C3 dùng `authority_level=high` hoặc `executive`.

Revision phải giữ nguyên ID và binding. Thu hồi bằng `status=revoked` với `observed_at` mới. Xem [schema](../../sme_fraud/authority_policy.schema.json).

Nguồn được kiểm tra trước khi chấm C2/C3, kể cả revision tương lai hoặc đã thu hồi. Dữ liệu sai làm dừng lần chấm bằng `ValueError` có tên bảng/ID/trường; không tự ép thành quyền hợp lệ hoặc chuyển sang fallback.

- `self_approval_allowed` và `evidence_on_file`: số nguyên `0`/`1`, boolean JSON/Python, hoặc chuỗi CSV `"0"`/`"1"`. Từ chối `2`, `-1`, số thực, chuỗi `true`/`false` và ô rỗng.
- Hạn mức: số nguyên VND không âm hoặc chuỗi chữ số; `min_amount_vnd <= max_amount_vnd`, gồm cả hai đầu. Từ chối số thực, NaN/Infinity, ký hiệu khoa học và dấu phân cách hàng nghìn.
- Enum hành động, cấp quyền, loại quyền và trạng thái phải đúng schema. `covered_actions` là danh sách không rỗng, không trùng, chỉ gồm `self_approve`/`approve`; cho phép khoảng trắng quanh từng mục.
- Ngày hiệu lực/coverage: `YYYY-MM-DD` tồn tại và đầu không sau cuối. `approved_at`/`observed_at`: đúng `YYYY-MM-DDTHH:MM:SS+07:00`, không phần lẻ giây, với `approved_at <= observed_at`. Nguồn múi giờ khác cần chuyển về định dạng này trước khi nhập.
- Các cột còn lại là chuỗi; ID nguồn và công ty không rỗng. Bằng chứng thiếu (`evidence_on_file=0`, `evidence_id=''` hoặc `approver_id=''`) vẫn không cấp quyền theo kiểm tra bằng chứng hiện hành.

Giá trị cờ/số và thứ tự `covered_actions` được chuẩn hóa trên bản sao trước khi so revision; không sửa dữ liệu đầu vào của bên gọi. [Chi tiết kiểm thử R5](../../reports/rule_authority_validation.md).
