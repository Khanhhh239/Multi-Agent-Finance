# Thông báo theo vai trò và công ty

Chính sách hiện tại: **notification-roles-20261027-v1**. Đây là cấu hình phân tuyến thông báo, không tạo tài khoản hoặc cấp quyền duyệt. `user_id`, `person_id`, vai trò và công ty phải khớp nguồn danh tính đã xác thực khi bổ sung đăng nhập.

## Sự kiện và người nhận

| Sự kiện | Người nhận trong đúng công ty |
| --- | --- |
| Hồ sơ mới ưu tiên cao | Kế toán viên |
| Kế toán viên gửi/gửi lại kết quả | Kế toán trưởng khác người rà; nếu không có người phù hợp thì giám đốc khác người rà |
| Trả lại để rà bổ sung | Đúng kế toán viên đã gửi bản rà |
| Người kiểm tra chốt kết quả, kể cả cần bổ sung | Kế toán viên đã gửi bản rà |
| Kết quả nghi vấn, vi phạm kiểm soát hoặc xác nhận gian lận | Báo thêm giám đốc; loại người vừa chốt và người đã rà |
| Tài liệu đã nhận, đang chờ rà lại | Kế toán viên; tên người phụ trách dạng văn bản không tự trở thành địa chỉ gửi |
| Hồ sơ quá SLA | Kế toán viên |
| Quá hạn kiểm tra kết quả | Kế toán trưởng; giám đốc thay khi không có người phù hợp |
| Quá hạn rà bổ sung | Người đã rà |
| Quá hạn tài liệu | Kế toán viên |
| Tóm tắt tuần | Kế toán trưởng; giám đốc thay khi không có người phù hợp |

Giám đốc được báo thêm khi quá mốc escalation của nhắc việc. Định danh người thật được dùng để loại người đã rà, kể cả khi có tài khoản khác. Người không còn được cấu hình hoặc đổi vai trò không tiếp tục nhận việc chờ gửi. Quyền duyệt vẫn được máy chủ kiểm tra riêng.

## Mốc thời gian đã chọn

- Kiểm tra bản rà: **48 giờ lịch** từ lần kế toán viên gửi bản đang chờ.
- Rà bổ sung sau trả lại hoặc xác nhận thiếu bằng chứng: **48 giờ lịch** từ sự kiện đó, khi không có yêu cầu tài liệu đang mở.
- Nhắc lại: mỗi **24 giờ** quá hạn; giám đốc nhận thêm sau **48 giờ quá hạn**.
- Hồ sơ chưa có bước duyệt dùng `sla_due_at`; tài liệu dùng `due_at` của yêu cầu được tạo trong vận hành. Không lấy ngày giao dịch cũ làm hạn bổ sung tài liệu.
- Mọi mốc theo **giờ Việt Nam**. Chỉ nhắc khi `now > due_at`. Đổi bước duyệt, đổi bằng chứng, sửa hạn hoặc rà xong tài liệu làm nhắc cũ hết hiệu lực.

Các mốc trên nằm trong `reminders`, không sửa SLA hay điểm của luật. Worker quét định kỳ nên thông báo được xử lý ở lượt quét đầu tiên sau mốc, không bảo đảm đúng từng giây. Khi worker dừng lâu, chỉ lập nhắc cho kỳ hiện tại.

## Cấu hình

[Mẫu để điền sau](config.roles.template.json) giữ danh sách người nhận rỗng và `dry_run=true`. [Ví dụ mô phỏng](config.roles.dry_run.json) có ba danh tính và đích `.invalid`/`SIM_*`, dùng để kiểm thử riêng.

Không trộn `recipients` kiểu cũ với `role_recipients`. Workspace bật duyệt hai cấp tự dùng chính sách vai trò; không có người nhận thì ghi **chờ cấu hình**, không dùng địa chỉ giả mặc định. Gửi thật trong workspace hai cấp bắt buộc có cấu hình `role_recipients` rõ ràng. Các file cấu hình kiểu cũ vẫn dành cho workspace cũ không bật hai cấp.

## Chống trùng, ngân sách và lịch sử

Khóa outbox gắn mode, bộ dữ liệu, công ty, loại sự kiện, phiên bản nguồn, kênh và đích gửi. Một đích lặp qua nhiều tài khoản chỉ có một job cho sự kiện/kênh đó. Email được so khớp không phân biệt hoa thường. Hai planner hoặc worker đồng thời không nhận cùng một job. Khởi động lại giữ các khóa đã lưu.

Các sự kiện duyệt được xét trước nhắc quá hạn, rồi cảnh báo/tóm tắt. Tất cả dùng chung hạn mức **5 hoặc 10 hồ sơ khác nhau/công ty/ngày**, không phải số tin nhắn; nhiều bước trên cùng hồ sơ không cộng thêm suất cùng ngày. Thiếu suất ghi chờ ngân sách; chưa có người phù hợp ghi chờ cấu hình. Sự kiện hết hiệu lực không gửi bù về sau.

Mỗi job có nhật ký chuỗi hash và điểm kết thúc: xếp lịch, bắt đầu lần gửi, mô phỏng/dịch vụ chấp nhận, hẹn thử lại, lỗi, chưa rõ kết quả, hủy và phản hồi Zalo. Nội dung lúc xếp lịch được giữ riêng nội dung lúc thử gửi. Có phân trang lịch sử trên app. Job cũ chưa có nhật ký chi tiết được ghi rõ, không tạo lại lịch sử giả.

Lỗi tạm thời được retry theo backoff, tối đa `max_attempts` (mặc định 4). Kết quả **uncertain** hoặc worker bị gián đoạn lúc gửi không được tự gửi lại; cần đối soát với dịch vụ. Đây là chống trùng trong ứng dụng, không phải cam kết gửi đúng một lần qua mọi lỗi mạng. Nhắc ở kỳ sau là một sự kiện mới.

`sent` nghĩa là dịch vụ đã chấp nhận. SMTP chấp nhận không xác nhận người nhận đã nhận/đọc. Phản hồi Zalo được ghi riêng sau kiểm tra chữ ký/thời hạn và chống nhận lặp; không thay kết luận hồ sơ. **Email/Zalo chưa có nghiệm thu gửi–nhận thực tế.**

## Chạy

Thiết lập Python theo [DEVELOPMENT](../../docs/DEVELOPMENT.md). Với **workspace test riêng**:

```powershell
& $projectPython -B -m sme_fraud.notification_worker `
  --data-root <TEST_DATA> --reports-root <TEST_REPORTS> --database <TEST_SQLITE> `
  --scenario 003 --config examples/notifications/config.roles.dry_run.json --watch
```

Worker hiện có quét mặc định mỗi 60 giây. App không tự khởi chạy worker hoặc gửi thật; nút **Chạy luồng giả lập** chỉ dành cho kế toán trưởng/giám đốc, trong phạm vi công ty được cấp. Kế toán viên xem lịch sử; chưa đăng nhập không được xem lịch sử chứa đích nhận. API cũ không có đăng nhập vẫn che đích nhận và danh tính trong lịch sử.

Khi có tài khoản/người nhận thật và cấu hình kênh, thực hiện nghiệm thu gửi–nhận riêng trước khi vận hành. Adapter gửi thật cần config và `--send`; token/mật khẩu đọc từ biến môi trường, không đưa vào outbox hoặc nhật ký. Lượt hoàn thiện này chỉ chạy mô phỏng và transport mock; không có thông báo gửi ra ngoài.
