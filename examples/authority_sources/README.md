# Nguồn thẩm quyền C2/C3

`approval_authority_coverage.csv` xác nhận ma trận thẩm quyền đầy đủ cho `self_approve`, `approve` hoặc cả hai trong một khoảng thời gian. Chỉ khi coverage hợp lệ, engine mới thay hạn mức master/proxy số tiền bằng ma trận.

`approval_authorities.csv` khai báo quyền theo nhân viên hoặc vai trò, nghiệp vụ, phòng ban, dự án và khoảng tiền. `authority_type=delegation` cần `delegated_by_id` khác người nhận ủy quyền. Quyền tự duyệt phải có `self_approval_allowed=1`; cấp C3 dùng `authority_level=high` hoặc `executive`.

Revision phải giữ nguyên ID và binding. Thu hồi bằng `status=revoked` với `observed_at` mới. Xem [schema](../../sme_fraud/authority_policy.schema.json).
