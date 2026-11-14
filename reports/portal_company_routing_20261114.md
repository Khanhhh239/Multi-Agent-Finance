# Giữ đúng doanh nghiệp khi reload Portal — 14/11/2026

**Đã sửa và kiểm thử kỹ thuật.** Đang xem C002 thì tải lại Portal vẫn giữ
C002 và màn hình đang dùng. Nếu đang nhập dữ liệu đã lưu, màn hình khôi phục
đúng snapshot và `as_of`; bấm xem kết quả trả lại cùng mã phân tích.

## Nguyên nhân và cách sửa

Portal trước đây luôn tạo lại iframe tại `/agent2/`. Màn hình làm việc nhớ
doanh nghiệp bằng một khóa riêng, màn hình nhập lại nhớ theo snapshot; hai
lựa chọn có thể khác nhau. Vì vậy C002 đang nhập có thể trở thành C001 khi
Portal tải lại màn hình mặc định.

Năm tệp JavaScript được cập nhật: `portal/static/app.js` và các màn hình
`workspace.js`, `workbench.js`, `he-analysis.js`, `analysis-settings.js`.

- Dùng chung lựa chọn trong `sessionStorage` của tab, có version, actor,
  context quyền, doanh nghiệp và tên màn hình được phép. Các liên kết chuyển
  màn hình mang theo doanh nghiệp; chọn DN trước khi lưu cũng được ghi nhớ.
- Portal đọc context quyền mới trước khi dựng lại iframe. Màn hình con kiểm
  lại context độc lập; thông tin trình duyệt không cấp quyền. Liên kết DN hợp
  lệ được ưu tiên hơn lựa chọn đã lưu. Run chỉ ghi nhớ sau khi đọc được báo cáo.
- Khi quyền/actor/context không khớp, không khôi phục dữ liệu cũ. Không còn
  quyền C002 thì chọn DN còn được phép; không có DN nào thì không mở dữ liệu.
  Run của DN khác bị bỏ, kết quả và phiếu cũ được xóa khỏi màn hình.
- Chuyển từ lựa chọn nhập cũ của cùng actor sang cơ chế mới có kiểm quyền,
  để khắc phục trường hợp C002 nhập nhưng khóa workspace cũ còn C001.
- Phản hồi khôi phục về muộn không được mở lại iframe khi đã đổi phiên hoặc
  rời Agent2. Tab riêng cũng dùng context mới và giữ đúng DN.

## Bằng chứng kiểm thử

| Phạm vi | Kết quả |
|---|---|
| Chrome: routing trên Portal/backend thật, môi trường tạm | 17/17 kiểm tra qua |
| Chrome: luồng CSV/Excel, CKKS, phiếu rà và báo cáo | 12/12 kiểm tra qua |
| HTTP: quyền Portal, thu hồi, tenant/actor, session | 22/22 test qua |
| Cú pháp năm tệp JavaScript | Đạt `node --check` |
| Đọc công khai năm asset trên Portal 8800 | HTTP 200, `no-store`, checksum khớp source |

Kiểm tra routing có nhập và phân tích thật 5 dòng mô phỏng C002; reload ngoài
Portal giữ nguyên snapshot, cutoff và analysis ID. Có kiểm C001/C002, lựa
chọn chưa lưu, chuyển màn hình, tab riêng, migration, quyền bị thu hồi, không
còn DN, đổi actor, storage hỏng, tên màn hình ngoài allowlist và phản hồi muộn.

Script tái chạy:

```powershell
agent2/.venv/Scripts/python.exe agent2/scripts/check_portal_company_routing.py --output agent2/.runtime/routing-new-run
agent2/.venv/Scripts/python.exe agent2/scripts/test_workspace_ui.py --output agent2/.runtime/workspace-new-run
agent2/.venv/Scripts/python.exe agent2/scripts/run_r1_tests.py --suite test_portal_auth --report agent2/.runtime/routing-auth-new.json
```

Mỗi thư mục output của script trình duyệt phải chưa tồn tại. Bằng chứng công
khai tại [evidence routing](../Agent2_Spec_v2_1/evidence/R2/portal_company_routing_20261114/REPORT.md).

## Phạm vi xác nhận

Kiểm thử đăng nhập trên Portal tạm bằng tài khoản/mật khẩu mô phỏng, không
đăng nhập thay người dùng trên Portal live. Fixture routing chọn metadata
landing HE4 giống màn hình hiện tại nhưng không gửi job HE; test luồng làm
việc riêng dùng CKKS thật, không chứng minh circuit HE4. Lifecycle cấu hình
model không được cấu hình trong fixture routing: chỉ kiểm màn hình, lựa chọn
DN và nút bị khóa, không nghiệm thu fit/activate trong lần này.

Portal live 8800 đã phục vụ đủ năm asset mới; người dùng tải lại Portal để
nạp bản sửa. Không restart dịch vụ, sửa quyền, model, khóa, snapshot hoặc
phiên phân tích đang lưu; không thay thuật toán/điểm hay tuyên bố hiệu quả
phát hiện gian lận. Chưa push Git trong tác vụ này.
