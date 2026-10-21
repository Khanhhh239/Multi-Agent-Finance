# Sao lưu tự động và phục hồi ReviewStore/P2 — 19/10/2026

**Đã triển khai và kiểm chứng kỹ thuật.** Lịch người dùng chọn là **02:00 hằng ngày theo giờ Việt Nam**, giữ **30 ngày và ít nhất 3 bản thành công**. [Bằng chứng tổng hợp](backup_automation_20261019/verification.json), [hướng dẫn vận hành](../examples/review_backup/automation.md).

## Lịch chạy thực tế

Tác vụ Windows `Agent22-ReviewBackup` đã đăng ký bằng tài khoản hiện tại, quyền thông thường, Python nền, không lưu mật khẩu. Có `StartWhenAvailable`, chống chạy song song; không đánh thức máy. Máy cần bật và tài khoản chạy phải đăng nhập. Chưa kiểm chứng vận hành khi đăng xuất hoặc máy ngủ.

[Quyền thực tế của tác vụ](backup_automation_20261019/task_security.json) xác nhận `Limited`/`Interactive`. XML xuất từ Windows lược bỏ trường `RunLevel` ở giá trị mặc định, nên bước tổng hợp đối chiếu thêm principal thực tế thay vì yêu cầu trường này luôn có trong XML.

Đã kiểm chứng bằng một trigger có hẹn giờ: **21:35:43 ngày 19/10/2026**, Task Scheduler tự khởi chạy, tạo gói `run-20261019T143548Z-652aef27`, kết thúc **mã 0**. Đây là lượt chạy theo giờ, không dùng `Start-ScheduledTask` để thay thế bằng chứng trigger. Trigger kiểm chứng đã gỡ; còn đúng **một lịch hằng ngày**, lượt kế tiếp **02:00 ngày 20/10/2026**. [Kết quả tác vụ](backup_automation_20261019/task_verification.json), [XML cuối](backup_automation_20261019/task_registered.xml), [định nghĩa đã chuẩn bị](backup_automation_20261019/task_definition.xml).

Config: `.runtime/backup_automation_20261019/job.json`. Kho: `.runtime/scheduled_review_backups`. Hiện có 2 bản tốt; chính sách tối thiểu 3 nghĩa là giữ tất cả khi mới có 1–2 bản, không tạo bản giả cho đủ số lượng.

## Phạm vi dữ liệu và phục hồi

Gói tổng hợp chứa ReviewStore, audit kết luận, identity/binding, các nguồn/kết quả cần cho web và **4 SQLite nghiệm thu P2 độc lập**. Tài nguyên cùng snapshot P2 được dùng chung trong gói. Mỗi SQLite dùng Backup API và read transaction riêng, có hash dữ liệu từng bảng và kiểm tra lịch sử. Không tuyên bố một giao dịch nguyên tử chung cho các DB UAT độc lập.

Đã phục hồi chính gói do Task Scheduler tạo vào `.runtime/backup_automation_20261019/restored`, đối chiếu toàn bộ bảng nghiệp vụ và lịch sử. [Biên bản phục hồi](backup_automation_20261019/restore_verification.json):

| Thành phần | Kết quả |
|---|---|
| Hồ sơ 001/003 | **584 + 627 = 1.211**, đủ và khớp dữ liệu |
| Yêu cầu tài liệu | **3 yêu cầu, 6 sự kiện lịch sử**, được giữ nguyên |
| Audit kết luận của demo nguồn | 001/003 đều có **0 kết luận**, giữ nguyên trạng thái này; không tự tạo kết luận để giả nghiệm thu |
| `step2_uat` | 0 ghi chú, phục hồi nguyên trạng |
| `browser_uat` | 0 ghi chú, phục hồi nguyên trạng |
| `assistant_review` | **20 sự kiện/20 ghi chú mô phỏng**, khớp đủ lịch sử và hash |
| `p2_web` | 0 ghi chú, phục hồi nguyên trạng |
| Tài nguyên P2 | Đủ **32 tình huống/73 giao dịch**, mở được bằng dữ liệu đã sao chép |

HTTP thực trên bản phục hồi xác nhận đủ danh sách 001/003, 7 hồ sơ đại diện, P2 và 20 ghi chú trợ lý. Đây là kiểm chứng API, chưa nghiệm thu trực quan browser hoặc kế toán độc lập. Các ghi chú `assistant_review` không phải kết luận nghiệp vụ đã được kế toán phê duyệt. Trường hợp audit kết luận không rỗng được kiểm chứng bằng fixture có kết luận SIM trong bộ kiểm thử, không sửa demo đang dùng.

## Retention và báo lỗi

Chỉ dọn sau khi bản mới được tạo và xác minh thành công. Chỉ xóa gói quá 30 ngày, thuộc đúng định danh kho/nguồn, khớp checksum, nằm trực tiếp trong kho và không thuộc 3 bản thành công mới nhất. Kiểm tra lại đường dẫn tuyệt đối và manifest trước mỗi lần xóa. Gói thủ công, gói khác chủ kho, gói hỏng, staging, symlink/junction được giữ hoặc báo lỗi, không dọn tùy tiện.

`latest.json` và `events.jsonl` ghi kết quả, lỗi, lịch sử chạy và bản tốt gần nhất. Lỗi sao lưu trả mã 1 và không dọn bản cũ; lỗi retention trả mã 2, giữ bản sao mới tốt và ghi cảnh báo. `status` phát hiện chưa từng chạy, lần cuối thất bại hoặc quá lịch với khoảng chờ 2 giờ. Đây là báo lỗi cục bộ, không gửi Email/Zalo.

## Kiểm thử và bảo toàn

**668 kiểm thử Python đạt, không lỗi hoặc bỏ qua**, gồm **22 kiểm thử mới** về P2 chỉ đọc/WAL/ghi đồng thời, phục hồi nhiều journal, thiếu/hỏng dữ liệu, chống ghi đè, runtime, cấu hình, chủ kho, retention/đường dẫn/lỗi xóa, chống chạy trùng, trạng thái lỗi và định nghĩa lịch Việt Nam. [Kết quả](backup_automation_20261019/tests.json), [log](backup_automation_20261019/tests.log).

Các ca retention dùng gói thử có ngày cũ được mô phỏng trong thư mục tạm; chưa cần chờ thực tế 30 ngày để kiểm tra điều kiện xóa. Diễn tập dữ liệu đầy đủ đối chiếu hash **1.209 tệp khóa không đổi**. 005 chỉ băm opaque, không parse/nạp/chấm hoặc dùng oracle. Rule/điểm/ngưỡng/model và quyết định RR09 giữ nguyên. Thông báo khi phục hồi chỉ dry-run, không tự dispatch và **không có tin gửi ra ngoài**.

Gói ReviewStore v1 cũ được giữ nguyên; chức năng mới là lớp tổng hợp ở [backup_suite.py](../sme_fraud/backup_suite.py) và [backup_job.py](../sme_fraud/backup_job.py). Khôi phục vẫn yêu cầu runtime tương thích, chưa có migration qua phiên bản khác hoặc bản sao ngoài máy. Cấu hình SMTP/OA và file chứng từ bên ngoài phạm vi kho không tự xuất.

Tham chiếu triển khai: [Python SQLite Backup API](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.backup), [đăng ký Windows Scheduled Task](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/register-scheduledtask), [StartWhenAvailable và thiết lập tác vụ](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset).
