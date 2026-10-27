# Hoàn thiện thông báo theo vai trò — 27/10/2026

Đã hoàn thiện phần kỹ thuật cho sự kiện cần báo, người nhận theo công ty/vai trò, chống trùng, nhắc quá hạn và lịch sử gửi. **140 test Python, 92 kiểm tra JavaScript và 11 kiểm tra Chrome đạt**. Lượt kiểm tra dùng dữ liệu/danh tính mô phỏng trong workspace riêng; không gửi thông báo ra ngoài.

## Chính sách đã chốt

Version **notification-roles-20261027-v1**, gồm 10 loại thông báo. Ma trận và cách cấu hình đầy đủ ở [hướng dẫn thông báo](../../../examples/notifications/README.md).

| Nhóm | Người nhận trong đúng công ty |
| --- | --- |
| Hồ sơ mới ưu tiên cao, tài liệu đã nhận | Kế toán viên |
| Kết quả chờ kiểm tra | Kế toán trưởng khác người rà; giám đốc thay khi không có người phù hợp |
| Trả lại, kết quả đã kiểm tra | Đúng người đã gửi bản rà |
| Kết quả nghi vấn/vi phạm | Báo thêm giám đốc, loại người đã rà và người vừa chốt |
| Quá hạn hồ sơ/tài liệu | Kế toán viên; quá hạn rà bổ sung báo đúng người đã rà |
| Quá hạn kiểm tra | Kế toán trưởng, hoặc giám đốc thay |
| Tóm tắt tuần | Kế toán trưởng, hoặc giám đốc thay |

Mặc định kiểm tra bản rà và rà bổ sung trong **48 giờ lịch**, nhắc mỗi **24 giờ**, báo thêm giám đốc sau **48 giờ quá hạn**. Các mốc được cấu hình riêng, không đổi điểm/SLA của luật. Hồ sơ dùng `sla_due_at`; yêu cầu tài liệu dùng `due_at` của vận hành. Sau trả lại hoặc xác nhận thiếu bằng chứng, hạn rà bổ sung lấy từ sự kiện đó nếu không có yêu cầu tài liệu đang mở.

Ngân sách vẫn **5 hoặc 10 hồ sơ khác nhau/công ty/ngày**, dùng chung cho các sự kiện/kênh/tóm tắt, không phải số tin. Sự kiện duyệt được xét trước nhắc việc, rồi cảnh báo/tóm tắt. Thiếu người nhận hoặc ngân sách được ghi chờ xử lý, không tự gán tài khoản/địa chỉ. Không dùng địa chỉ mô phỏng mặc định trong workspace hai cấp, kể cả khi bật hai cấp sau khi tạo service.

## Đã triển khai

- Planner đọc nhật ký duyệt và yêu cầu tài liệu; kiểm tra lại trạng thái, scope và người nhận trước lúc gửi. Kết quả vừa chốt vẫn báo được dù hồ sơ đã đóng; nhắc/cảnh báo không còn phù hợp bị hủy.
- Khóa job theo mode, bộ dữ liệu, công ty, sự kiện/phiên bản, kênh và đích. Đích trùng giữa các tài khoản chỉ có một job; planner/worker đồng thời và khởi động lại không nhân đôi lần gửi.
- Retry có backoff và giới hạn lần thử. Kết quả chưa rõ hoặc worker gián đoạn lúc gửi dừng ở `uncertain`, không tự gửi lại.
- Nhật ký từng bước nối hash và có điểm kết thúc để phát hiện thay đổi/cắt log: xếp lịch, thử gửi, retry, mô phỏng/chấp nhận, lỗi/hủy và phản hồi Zalo. Giữ nội dung xếp lịch và nội dung lần thử; không dựng lịch sử cho job cũ.
- Giao diện hiển thị sự kiện, người nhận/vai trò, đích, thời gian, lần thử, lỗi, phản hồi và lịch sử phân trang. Kế toán viên chỉ xem; kế toán trưởng/giám đốc chạy giả lập trong công ty được cấp. Chưa đăng nhập không xem lịch sử có đích nhận. API cũ không đăng nhập vẫn che đích/danh tính, kể cả bản sao trong lịch sử.
- Workspace hai cấp gửi thật bắt buộc dùng cấu hình vai trò; không trộn với định dạng người nhận kiểu cũ. Worker quét định kỳ; app không tự bật gửi thật.

## Kết quả kiểm chứng

| Lớp | Kết quả |
| --- | --- |
| Python | **140/140**, không lỗi hoặc bỏ qua; gồm 38 test mới cho vai trò, mốc nhắc, hai công ty, nhận/rà tài liệu, ngân sách, concurrency, restart, retry, unknown, audit, HTTP và backup/restore. Các bộ cũ về duyệt, quyền, feedback, tài liệu, backup và adapter vẫn đạt. |
| JavaScript | **92 kiểm tra đạt**, gồm 12 test mới cho nhãn sự kiện/người nhận, escape dữ liệu, lịch sử, retry, phân biệt chấp nhận–đã nhận, quyền chạy giả lập và chờ cấu hình/ngân sách. |
| Chrome | **11 kiểm tra đạt**: lập giả lập, chạy lại, người nhận đúng vai trò, lịch sử, chính sách, phân trang, liên kết hồ sơ, quyền kế toán viên, từ chối chưa đăng nhập, reload và viewport 360×800. |
| Outbox test | **36 job mô phỏng / 8 hồ sơ C001**, **108 mốc lịch sử**, mỗi job đúng một lần thử. Chạy giả lập lần hai không tăng job/lần thử. Không có job C002 trong preview của C001. |

Viewport 360px có chiều rộng trang 345px, dialog khoảng 310,67px, chữ thẻ 14px và vùng mở lịch sử cao 44px; không tràn ngang. Hai tab xác thực không ghi nhận console error; override viewport đã được reset.

Các test live-mode dùng **transport mock**. SMTP và Zalo adapter được kiểm tra bằng mock; không kết nối dịch vụ thật. Khôi phục backup giữ lịch sử và mode giả lập. Chỉnh/cắt audit được phát hiện; job cũ chưa có audit được ghi rõ là lịch sử chưa đầy đủ.

## Cách thử

- [Mẫu chưa có người nhận](../../../examples/notifications/config.roles.template.json) giữ `dry_run=true`, để điền sau khi có tài khoản thực tế.
- [Cấu hình mô phỏng](../../../examples/notifications/config.roles.dry_run.json) có ba vai trò C001; không dùng làm danh bạ thật.
- [Hướng dẫn chạy worker](../../../examples/notifications/README.md#chạy) mô tả việc quét định kỳ và tách gửi thật khỏi giao diện.
- Môi trường browser của lượt này: `.runtime/notification_roles_20261027/serve.py`, database dưới `fixture/` cùng thư mục. Cổng **8795 kế toán viên, 8796 kế toán trưởng, 8797 giám đốc, 8798 chưa đăng nhập**. Tất cả loopback và mô phỏng; không dùng database demo 8774 để thử ghi.

## Bằng chứng lưu

[Python](../../../reports/notification_roles_20261027/python_results.json) · [JavaScript](../../../reports/notification_roles_20261027/javascript_results.json) · [Chrome](../../../reports/notification_roles_20261027/browser_checks.json) · [đối soát outbox](../../../reports/notification_roles_20261027/outbox_verification.json) · [outbox mô phỏng](../../../reports/notification_roles_20261027/outbox.json) · [nhật ký gửi](../../../reports/notification_roles_20261027/delivery_history.json).

[Ảnh desktop](../../../reports/notification_roles_20261027/screenshots/history_desktop.jpg) · [lịch sử ba bước](../../../reports/notification_roles_20261027/screenshots/history_desktop_end.jpg) · [ảnh 360px](../../../reports/notification_roles_20261027/screenshots/history_360.jpg) · [mã nguồn trước/sau](../../../reports/notification_roles_20261027/source_snapshot.zip) · [hash đầu ra](../../../reports/notification_roles_20261027/commitment.json) · [đối soát file bảo vệ](../../../reports/notification_roles_20261027/protected_verification.json).

## Phần chưa đóng

**Email/Zalo chưa được xác nhận gửi–nhận thực tế.** Dịch vụ chấp nhận không chứng minh người nhận đã nhận/đọc; phản hồi Zalo được ghi riêng. Chưa có tài khoản thật, cấu hình kênh và người nhận thật được chỉ định. Cần nghiệm thu riêng khi có các phần này; mã kỹ thuật và mô phỏng không thay thế biên bản nghiệm thu kênh.

Không sửa luật/model, không huấn luyện/chấm lại, không tạo kết luận rà ML độc lập. Các nguồn và báo cáo đã khóa được giữ nguyên; các file mã nguồn đang phát triển được thay đúng phạm vi. IF tiếp tục shadow. Đây là nghiệm thu thông báo trên Chrome/viewport mô phỏng, không phải nghiệm thu mọi trình duyệt, thiết bị hoặc toàn bộ bộ mẫu lịch sử.
