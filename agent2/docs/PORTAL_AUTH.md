# Đăng nhập Portal và dùng Agent2 — CR-025

## Người dùng

1. Mở **http://127.0.0.1:8800/#agent2**, bấm **Mở đăng nhập Portal** nếu chưa mở khóa.
2. Lần đầu, tự đặt và xác nhận mật khẩu trên Portal. Các lần sau dùng mật khẩu đó. Không cần mã truy cập local của Agent2.
3. Chọn **Soát giao dịch** ở menu. Agent2 tự nhận phiên Portal, chỉ liệt kê doanh nghiệp được cấp quyền.
4. Chọn doanh nghiệp, nhập JSON → kiểm tra → xác nhận lưu → xem kết quả. Có thể dùng **Mở tab riêng** trên thanh Portal; không cần đăng nhập Agent2 lần nữa.

Tải lại trang tự nhận lại phiên và snapshot gần nhất nếu còn quyền. **Về Portal** quay lại trang nạp dữ liệu; **Khóa lại** tại Portal chặn ngay API của phiên đó, kể cả tab Agent2 cũ. Giao diện tab riêng kiểm tra lại khi có thao tác/focus và tối đa mỗi 15 giây; dữ liệu đang xem bị bỏ khi mất phiên hoặc thay quyền. Tab đã bị khóa cần mở lại từ Portal sau khi đăng nhập mới.

Phiên tự hết hạn sau 20 phút không thao tác. Kiểm tra nền bằng GET không kéo dài thời gian này. Nhập/lưu/phân tích bằng POST là thao tác làm mới phiên.

**Giới hạn hiện hữu:** Portal dùng một mật khẩu và danh tính workspace chung, chưa có tài khoản cá nhân riêng. Mọi phiên workspace này có cùng các membership được quản lý cấp phía server. Đây chưa phải hệ thống SSO đa người dùng. Các kiểm tra/quyền của Agent2 đã nối; luồng CSV cũ tại trang Nạp dữ liệu chung chưa nối API import v2. Nhập JSON trong Agent2 để tạo snapshot mới.

## Người vận hành

Khởi động Portal từ workspace, sau đó bật Agent2 bằng nút **Bật agent** trong Portal:

```powershell
cd D:\agent22
& agent1/.venv/Scripts/python.exe -X utf8 -u -B portal/server.py
```

Portal cấp secret nội bộ ngẫu nhiên cho Agent2 qua environment và chạy backend với `--portal-url` cùng `--snapshot-db`. Secret không nằm trên URL, command line hoặc trong mã HTML. Khi khởi động lại Portal, khởi động lại Agent2 qua cùng Portal để đồng bộ secret; các phiên cũ không được khôi phục.

Trên Windows, thao tác dừng Agent2 nhắm đúng cây tiến trình do Portal tạo, gồm interpreter con của Python venv, để cổng cũ được giải phóng. Portal không dừng instance Agent2 do chương trình khác tạo.

Khai báo trong `portal/config.local.json`, dưới `agents.agent2`:

```json
{
  "port": 8766,
  "snapshot_db": "agent2/.runtime/platform/snapshots-v2.sqlite3",
  "access_file": "portal/workspace/agent2_access.json"
}
```

`snapshot_db` là kho snapshot v2 riêng, không dùng database nghiệp vụ cũ. Phiên local hiện tại giữ nguyên `agent2/.runtime/live_check_20261111/snapshots.sqlite3` và đúng tenant/actor/quyền C001 đã được cấp trước đó. Không cấp thêm C002 hoặc quyền director/fit/verify. Mật khẩu Portal thật chưa được tạo hộ người dùng.

Sao chép `portal/agent2-access.example.json` tới access_file và để người quản lý khai báo danh tính/quyền. Mẫu mặc định không cấp doanh nghiệp nào. Ví dụ một quyền nhập được cấp rõ:

```json
{
  "version": "portal-agent2-access/1.0.0",
  "actor_id": "portal-workspace",
  "tenant_id": "your-tenant",
  "status": "active",
  "memberships": [
    {"company_id": "YOUR_COMPANY", "role": "accountant", "status": "active", "permissions": ["data.import"]}
  ]
}
```

File này thuộc cấu hình quản lý phía server; không nhận nội dung file qua giao diện hồ sơ doanh nghiệp. Đổi company profile hoặc trường `agent2_company` không tạo quyền. Để đọc import do actor cũ tạo, binding actor/tenant phải khớp; snapshot vẫn dùng scope tenant/doanh nghiệp. Director không được xem DN ngoài membership; technical view kiểm vai trò ở backend. Quyền `evidence.verify` và `model.fit` phải được cấp riêng khi cần; đăng nhập không tự cấp chúng.

Policy được đọc mỗi lần kiểm quyền. Thu hồi membership, bỏ `data.import`, đổi vai trò/tenant hoặc thu hồi danh tính có hiệu lực mà không cần khởi động lại. Sửa file bằng thay thế nguyên tử để tránh đọc giữa lúc đang ghi. File thiếu/sai hoặc Portal không kết nối được đều chặn truy cập, không dùng quyền lưu tạm hoặc quay về mã local.

## Cơ chế

- UI cùng origin tại `/agent2/`; dùng `X-Session` của Portal đã có, không tạo thêm credential backend cho browser. Phiên Portal vẫn ở `sessionStorage["kt-session"]` theo cơ chế sẵn có của Portal.
- Proxy kiểm Host/Origin/`X-Platform`/session, chỉ chuyển route allowlist, bỏ Authorization/role/tenant do browser tự gửi. Upload giữ nguyên byte, Idempotency-Key và thông tin revision.
- Agent2 `PortalAuthorizer` xác minh session qua `POST /api/internal/agent2/identity`, bằng secret backend riêng. Endpoint này không nhận Origin từ browser. Cả hai kênh chỉ loopback, không theo redirect hoặc proxy môi trường.
- Agent2 vẫn kiểm tenant/membership/permission trước đọc body và trong các bước đọc/trước trả kết quả. Logout giữa lúc phân tích không được trả các dòng dữ liệu. Không có local credential fallback trong mode Portal.
- `context_id` là hash của danh tính/tenant/quyền, chỉ giúp UI bỏ trạng thái cũ. Nó không cấp quyền. Các detector/feature/model/snapshot và quy tắc tính điểm không đổi.
- Chế độ `--auth-file` độc lập vẫn tồn tại cho công cụ local và kiểm thử; khác với launcher Portal hiện tại. Mở trực tiếp 8766 khi chạy mode Portal sẽ hướng dẫn quay về Portal.

Không đưa workspace security/access files, session hoặc secret vào Git. Mọi mã/trạng thái hết hạn do Portal quản lý; Agent2 không có mật khẩu thứ hai.

## Kiểm thử

`test_portal_auth.py` dùng Portal và Agent2 HTTP thật với session/policy/SQLite tạm. Browser acceptance dùng Chrome riêng và dữ liệu mô phỏng:

```powershell
& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/test_portal_sso_ui.py --output-dir <thu-muc-evidence>
```

Kết quả và ảnh giao diện: `Agent2_Spec_v2_1/evidence/R5/portal_auth_20261112/`.
