# Agent2: luồng làm việc cốt lõi

**READY_FOR_REVIEW cho phần kỹ thuật được giao; chưa duyệt toàn bộ R0–R6.**

Người dùng yêu cầu hoàn thiện các chức năng quan trọng để Agent2 thành một
luồng sử dụng được. Phạm vi: nhập và kiểm tra → snapshot → phân tích theo
doanh nghiệp → phiếu rà → báo cáo. Tái sử dụng backend/HE đã có, không thay
thuật toán, trọng số, ngân sách hay tự đưa kết quả vào hàng đợi nghiệp vụ.

## Chức năng

- Trang `/workspace` tập hợp dữ liệu đã lưu, lịch sử phân tích, trạng thái,
  phiếu và tải báo cáo. Portal live dùng trang này làm trang chủ Agent2.
- Nhập CSV/Excel/JSON vẫn qua validation và xác nhận trước khi tạo snapshot.
  Liên kết giữa các màn hình giữ doanh nghiệp và bản dữ liệu đã chọn.
- Mở lại yêu cầu đã lưu, xem tiến độ và tiếp tục đúng yêu cầu khi có thể.
  Lượt thất bại giữ nguyên; tạo lượt mới là thao tác riêng, có receipt mới.
- Mỗi giao dịch có câu hỏi, lý do, bước tiếp theo, nguồn đối chiếu và phần
  chưa đủ dữ liệu. P1 giữ số âm và nhóm đồng thời; đồ thị đọc đúng trục
  `field/entity/entity`, tách liên kết mạnh khỏi bối cảnh.
- Bắt đầu rà, ghi kết luận/giải thích/hành động/căn cứ, bổ sung PDF/ảnh,
  lưu thời gian kết nối và lịch sử sửa trên server. Mất phản hồi lưu dùng lại
  request ID; không tự tạo revision thứ hai.
- CSV có BOM và chống công thức ở dữ liệu chữ, giữ số âm ở cột tiền đã kiểm
  tra; JSON giữ thêm căn cứ/lịch sử. Hai định dạng lấy bản server đã lưu.
- Kiểm scope ở backend; kết quả công việc có allowlist nghiệp vụ. Người dùng
  kế toán không nhận model/feature contract/ngưỡng/cấu hình riêng. Cấu hình
  quản lý vẫn kiểm quyền thực tế phía server. Chuyển doanh nghiệp xóa view cũ.
- Bố cục điện thoại hiển thị đủ nút mở kết quả, không đẩy thao tác khỏi màn hình.

## Khôi phục trước lần gửi đầu tiên

Yêu cầu cũ C002 đã hết hạn được giữ thất bại. Bản sửa bổ sung fresh admission:
node ký quyền gửi mới cho **đúng packet đã lưu**, giữ ciphertext/context/
session/nonce/hash. Worker kiểm purpose, chữ ký, owner/grant/build và nhận
một lần; phản hồi mất vẫn lấy đúng cache. Không kéo dài TTL hoặc đổi replay
của worker Mahalanobis. Không tự mở lại terminal job.

21 ca service/coordinator focused và một phép tính P1 native Concrete qua HTTP
đã kiểm packet có thời gian hết hạn trước 7 giờ. Đây là mô phỏng lệch timestamp,
không phải ngồi chờ 7 giờ. Kết quả C002 T05: 24 + 3 = 27 triệu / hóa đơn
30 triệu, không trúng P1; lấy cache không tính lại. Chạy native này ở bộ key/
worker cô lập. Đối chiếu P1 Portal thật C001/C002 có bằng chứng riêng tại
[CR-043](../../HE/p1_portal_recheck_20261113/REPORT.md).

## Kiểm chứng và giới hạn

| Bằng chứng | Kết quả |
|---|---|
| native-regression.json | 748 kiểm thử qua; 0 lỗi, 0 bỏ qua |
| full-he-tests.json | 281 kiểm thử HE/API/recovery qua; gồm các kiểm thử workspace mới |
| workspace-focused.json | 24 kiểm thử focused qua, là tập con trước khi thêm ca trục đồ thị |
| browser-flow.json | 12 kiểm tra thao tác qua, không lỗi JavaScript |
| portal-sso.json | 16 kiểm tra đăng nhập/quyền qua trong fixture cô lập |
| p1-business-view.json | C001/C002 hiển thị đủ 8 kết quả native đã lưu: số tiền P1, điều chỉnh, căn cứ nhóm, liên kết ngân hàng và thiếu lịch sử |
| fresh-admission-focused.json, fresh-admission-native.json | 21 focused qua và 1 lượt Concrete HTTP thật; không cộng vào full HE |
| live-smoke.json | 6 trang/asset live trả 200; API dữ liệu và báo cáo chưa đăng nhập trả 401 |
| preservation.json | Model, snapshot, phiếu/job, config, mật khẩu/quyền và khóa giữ nguyên sau deploy |

Các tệp JSON kèm theo ghi số lượng/kết quả thực tế; không cộng các bộ focused
giao nhau vào full suite. Browser acceptance dùng Portal/node/CKKS thật trong
fixture riêng, C001 nhập CSV và C002 nhập Excel. Chỉ metadata khai báo mode
HE4 trên màn hình nhập được mock để kiểm liên kết tiếp tục; không coi lượt
browser này là native Concrete bốn nhánh. Failure đầu vào terminal được tạo
trong kho test rồi chạy lượt thay thế CKKS thật, không phá worker live.
Kiểm tra `p1-business-view.json` nạp kết quả native đã lưu từ CR-043 vào kho
test riêng để thử màn hình nghiệp vụ; không thực hiện lại phép tính HE.

Bộ SSO kiểm phiên/đổi quyền trong fixture riêng. Kiểm smoke sau deploy đọc
trang live, health và việc từ chối API riêng tư khi chưa đăng nhập. Không
tạo phiên đăng nhập giả, đổi mật khẩu hoặc ghi kết luận nghiệp vụ trên live.
Sao lưu 7 DB local trước deploy; đối chiếu logical dump sau restart và hash
model/khóa/quyền/config/mật khẩu. Không công bố DB, key, token hoặc backup.

Các profile HE vẫn có giới hạn hiện tại: P1 tối đa 4 source values/tổng,
graph tối đa 4 đối tượng, RobustZ hai biến và Mahalanobis hai feature.
Thiếu/vượt miền trả unavailable, không cắt nguồn. Chưa HE toàn catalog,
IF/ECOD/LOF/AE/33 feature, public cloud, xác minh từng cá nhân rà soát hoặc
đo hiệu quả trên doanh nghiệp thật. Danh sách hồ sơ giữ đủ giao dịch của lần
chạy; chưa là queue có trọng số/ngân sách/mandatory routing được duyệt.

Hướng dẫn: [WORKSPACE_GUIDE.md](../../../../agent2/docs/WORKSPACE_GUIDE.md).
