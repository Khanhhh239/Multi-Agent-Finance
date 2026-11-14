# CR-053 — kiểm thử routing Portal C001/C002

Trạng thái **FIXED / READY_FOR_REVIEW kỹ thuật**, 14/11/2026.

- [17 kiểm tra Chrome routing](routing_checks.json): Portal đăng nhập và HTTP
  backend thật trong môi trường tạm; nhập/commit/phân tích 5 giao dịch C002,
  outer reload giữ DN/màn hình/snapshot/as_of/analysis ID. Có thu hồi quyền,
  đổi actor, không còn DN, migration, tab riêng và phản hồi muộn.
- [12 kiểm tra Chrome luồng làm việc](workspace_checks.json): CSV/Excel,
  CKKS thật, phiếu rà server, retry, reload và báo cáo, môi trường tạm.
- [22 test quyền HTTP](auth_tests.json): session, tenant, role, scope,
  thu hồi, proxy và read/recheck hiện có.
- [Asset Portal 8800](live_assets.json): năm JS HTTP200, no-store và checksum
  khớp source; không restart. [Hash source](source_hashes.json).
- [Ảnh C002 sau reload Portal](C002-reloaded.png), dữ liệu mô phỏng.

Fixture routing chọn metadata landing HE4, không gửi HE job. Lifecycle
config model không được cấu hình tại fixture này; chỉ kiểm routing và nút
bị khóa. Không có live-login, nhãn nghiệp vụ thật, nghiệm thu HE4/circuit
hay thay đổi live DB/model/key/policy. Không tự chốt DONE R0–R6.

Chi tiết, nguyên nhân và lệnh tái chạy:
[báo cáo](../../../../reports/portal_company_routing_20261114.md).
