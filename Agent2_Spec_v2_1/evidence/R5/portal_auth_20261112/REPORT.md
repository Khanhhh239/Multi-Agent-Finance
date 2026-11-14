# CR-025 — phiên Portal và quyền doanh nghiệp Agent2

**READY_FOR_REVIEW cho bridge workspace được giao; R5 tổng thể PARTIAL.** Không phải SSO đa người dùng/full R5 hoặc production approval.

## Hành vi đã nối

Mở http://127.0.0.1:8800/#agent2. Portal đang chạy 8800, Agent2 chạy 8766 bằng PortalAuthorizer và kho snapshot cũ. Đăng nhập/mở khóa Portal một lần, chọn Soát giao dịch; iframe và tab riêng tự nhận phiên, không nhập mã local. Lần đầu người dùng tự đặt mật khẩu Portal. Không tạo hộ mật khẩu thật hoặc phiên thật để kiểm thử.

Danh tính workspace và membership từ file quản lý server, không lấy từ hồ sơ DN/request body. Local demo chỉ giữ tenant/actor và C001 accountant/data.import đã được cấp; không tự mở C002/director/fit/verify. Backend kiểm mỗi guard/recheck qua introspection secret nội bộ, đọc policy mới nhất; không cache quyền hoặc fallback credential local khi Portal lỗi. Director chỉ technical trong đúng DN. Thay quyền/tenant bỏ tham chiếu dữ liệu cũ; logout/expiry chặn API ngay. GET nền không gia hạn idle TTL.

Proxy chỉ allowlist cùng origin, guard Host/Origin/X-Platform/X-Session, loại Authorization/role/tenant do browser tự gửi; không theo redirect/proxy môi trường. Secret không vào URL/command/browser. Nhập giữ byte, checksum, revision/idempotency cũ. Chế độ local độc lập vẫn được kiểm thử nhưng launcher Portal không sử dụng làm fallback.

## Kiểm thử hiện hành

| Bộ kiểm tra | Kết quả | Bằng chứng |
|---|---|---|
| Native backend, gồm 22 ca bridge/quyền/lifecycle mới | **714/714 pass**, 0 fail/error/skip; process exit 0; 337.703 giây | [JSON](native_tests.json), [log](native_tests.log), [execution](native_execution.json) |
| Hồi quy Portal hiện hữu bằng môi trường Agent1/Portal | **11/11 pass**, process exit 0 | [log](portal_regression.log), [execution](portal_regression_execution.json) |
| Chrome: đăng nhập Portal một lần/iframe/tab/reload/khóa/expiry/thay quyền/không fallback | **16/16 pass**, không lỗi JS | [report](portal_browser_tests.json), [ảnh](01-portal-workbench.png) |
| Chrome: chế độ local/nhập/preview/lưu/mất phản hồi/thiếu nguồn/VND lớn/XSS | **19/19 pass** | [report](local_mode_browser/browser_tests.json) |
| Cây tiến trình Windows thực, start/stop/restart | **pass**, cổng được giải phóng rồi bật lại mode Portal; toàn bộ là tiến trình/DB tạm | [report](isolated_lifecycle.json), [script](../../../../agent2/scripts/test_portal_lifecycle.py) |
| Live 8800/8766 | Root/assets/settings 200; thiếu phiên 401 đúng header; mã local cũ 401; kho snapshot **1 → 1**; màn hình khóa/mở mật khẩu qua | [summary](live_summary.json), [ảnh](02-live-locked.png) |

Test HTTP bao gồm: giả role/tenant không tạo quyền, profile edit không cấp DN, C001 accountant không technical, C002 director technical đúng scope, quyền bị thu hồi giữa preview/commit, logout giữa analyze không trả rows, tenant/actor mới không đọc snapshot/import cũ, policy thiếu/sai/revoked hoặc Portal offline đều fail closed. Các fixture và phiên/password kiểm thử đều tạm, mô phỏng.

[Preservation](preservation.json): 17 file core/feature/model/scoring/snapshot/analysis API giữ nguyên hash. Không đổi luật/trọng số/model/feature contract hoặc ghi queue/active. [Provenance](provenance.json) khóa source working tree, command, exit code và lịch sử chẩn đoán; không xem HEAD dirty là mã đã commit.

## Giới hạn và vận hành

Xem [hướng dẫn](../../../../agent2/docs/PORTAL_AUTH.md). Portal hiện chỉ có mật khẩu workspace chung, chưa phân biệt tài khoản từng người; access_file là binding được quản lý cấp, mặc định mẫu không cấp DN. Hai UI/config lifecycle/full R4/R5 chưa hoàn tất. Luồng CSV cũ tại Nạp dữ liệu chung chưa nối import v2; nhập JSON trong Agent2. Các detector/ML HTTP/queue ngoài phạm vi này vẫn chưa mở.

Live auth đã hoạt động. Sau bản sửa dừng cây tiến trình Windows, lệnh reload đồng thời hai dịch vụ live bị automatic review từ chối với thông tin duy nhất “blocked by policy”. Không thử vượt chặn; giữ dịch vụ đang phục vụ, chuyển kiểm thử start/stop/restart sang OS subprocess tạm và đã qua. Helper dừng cây tiến trình mới nằm trong source và sẽ được nạp ở lần khởi động Portal bình thường tiếp theo; không tuyên bố live helper đã được reload.

Diagnostic cũ được giữ rõ: lần Portal regression đầu thiếu dependency ở sai venv, bản full 713 trước helper, lỗi UI đã sửa. Chỉ các kết quả hiện hành trong bảng trên là nghiệm thu kỹ thuật. Chưa có reviewer nghiệp vụ ký DONE.
