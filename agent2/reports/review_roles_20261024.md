# Phân quyền rà soát và kiểm tra cuối — 24/10/2026

**Đã cấu hình luồng hai cấp: kế toán viên rà; kế toán trưởng hoặc giám đốc chốt hoặc trả lại. Chưa tạo tài khoản hay triển khai đăng nhập, đúng lựa chọn của người dùng.** Bản app cục bộ tại [http://127.0.0.1:8774/](http://127.0.0.1:8774/) đã nạp chính sách mới; vẫn xem được hồ sơ khi chưa đăng nhập, còn thao tác ghi cần danh tính hợp lệ từ phía máy chủ.

## Quyền đã chốt

| Vai trò | Việc được làm |
|---|---|
| Kế toán viên | Rà lần đầu, ghi đề xuất, phần thiếu và phút thực tế; gửi để kiểm tra cuối; cập nhật yêu cầu tài liệu trong công ty được cấp |
| Kế toán trưởng | Kiểm tra kết quả của người khác, chốt hoặc trả lại kèm lý do |
| Giám đốc | Kiểm tra kết quả của người khác, chốt hoặc trả lại kèm lý do |

Chỉ cần **một** kế toán trưởng **hoặc** giám đốc chốt; không bắt cả hai duyệt. Một người không tự duyệt kết quả của mình dù dùng tài khoản khác: máy chủ kiểm tra cả mã tài khoản và mã người thật. Quyền lấy từ `ReviewPrincipal` do tầng đăng nhập phía máy chủ cung cấp; không lấy từ tên/vai trò nhập trong request. Hiện chưa có tầng đăng nhập đó và chưa có người dùng thực tế được tạo.

## Luồng thực hiện

1. Kế toán viên gửi kết quả → hồ sơ **chờ kiểm tra cuối**, chưa đóng.
2. Kế toán trưởng/giám đốc khác người rà xem lại. Có thể chốt cùng kết quả hoặc sửa kèm lý do.
3. Nếu trả lại, kế toán viên phải rà và gửi lại trước khi chốt.
4. Phút của hai cấp được ghi riêng từ số đo thực tế; không tự lấy phút ước lượng của hàng đợi. Nếu chưa nhập đủ thì chưa ghi kết quả.

Nhật ký nối tiếp có chuỗi hash, gắn phiên bản bằng chứng/phạm vi. Request cũ không áp dụng lên bằng chứng mới. Cổng yêu cầu tài liệu đang mở tiếp tục chặn kết luận cuối. Đường ghi feedback cũ và CLI không bỏ qua được luồng hai cấp trên kho đã bật chính sách. Backup/restore giữ chính sách và nhật ký; kiểm tra hash không phải chữ ký số.

## Kiểm chứng

**149 kiểm thử Python đạt**, gồm 8 kiểm thử quyền/ML và 18 kiểm thử luồng mới; **56 kiểm tra renderer/điều hướng đạt**, gồm 8 kiểm tra giao diện phân quyền. [Kết quả Python](review_roles_20261024/tests.json), [renderer](review_roles_20261024/ui_tests.json).

Đã kiểm tra HTTP trên instance mới: đọc hồ sơ khi chưa đăng nhập thành công; giả vai trò, gửi kết quả, ghi kết luận trực tiếp và thay ngân sách khi chưa có danh tính đều bị từ chối. Không ghi thêm sự kiện rà thật, không đổi ngân sách qua các kiểm tra từ chối. [Biên bản app](review_roles_20261024/app_verification.json). Không khẳng định đã kiểm tra trực quan bằng trình duyệt.

## Gói rà ML

Tạo [workspace theo quyền mới](review_roles_20261024/ml_review_workspace/public/README.md) từ bản sao gói 74 phiếu; bằng chứng và ZIP giữ cùng hash. File phân công mới có `role_policy=accountant-review-final-approval-v1`, vai trò đã chọn nhưng các ID người rà/người chốt vẫn null, danh sách người dùng rỗng. Không thay phiếu, kết luận hay gói đã khóa trước đó.

**0/74 lượt rà độc lập, phút thực tế vẫn null.** Phân quyền là cấu hình trách nhiệm, chưa phải người thật đã rà. Kiểm định ML còn yêu cầu người thật khác nhau, xác nhận độc lập/mù, lý do, bằng chứng và phút thực tế; vai trò không tự thay thế các điều kiện đó. Kết quả rà trên màn hình có điểm rules không tự trở thành đánh giá mù. [Trạng thái ML](review_roles_20261024/ml_role_status.json).

## Nối với đăng nhập sau này

Đã để sẵn `identity_provider` trong server: sau khi xác thực phiên, tầng đăng nhập trả về mã tài khoản, mã người thật, tên hiển thị, vai trò và công ty được phép. Chưa có endpoint tự chọn vai trò hoặc tự nâng quyền. [Hướng dẫn tích hợp](../examples/review_roles/README.md), [chính sách](review_roles_20261024/role_policy.json).

App nạp lại chính sách đã bật từ SQLite khi khởi động lại. Có bản sao SQLite trước khi bật trong `.runtime/review_roles_20261024/review_before_roles.sqlite3`. Khởi động bằng [run_app.ps1](../.runtime/review_roles_20261024/run_app.ps1). Môi trường hiện tại tiếp tục là bản mô phỏng cục bộ; quyền đọc dữ liệu thật, đăng nhập và cấp/thu hồi tài khoản thuộc bước tích hợp sau.

[Bảo toàn và thay đổi code](review_roles_20261024/verification.json): feature contract không đổi; nguồn/model/gói/báo cáo cũ giữ nguyên. Các điều kiện nguồn và hiệu quả ML còn mở trong báo cáo trước không được đóng bởi việc cấu hình quyền.
