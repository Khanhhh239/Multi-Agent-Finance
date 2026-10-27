# Sao lưu tự động ReviewStore và nghiệm thu P2

Để giữ đúng code/schema cho backup và nâng cấp, xem [gói phát hành và hướng dẫn chuyển phiên bản](../../RELEASES.md), cùng [bằng chứng cài sạch/mở backup cũ](../../docs/reports/operations/release_20261019.md). Các gói v1 vẫn dùng kiểm tra runtime hiện có; không sửa manifest để ép tương thích.

Lịch đã chọn: **02:00 hằng ngày, Asia/Saigon; giữ 30 ngày và ít nhất 3 bản thành công**. Tác vụ Windows mang tên `Agent22-ReviewBackup`, dùng Python nền và tài khoản hiện tại, quyền thông thường, không lưu mật khẩu. Có bật `StartWhenAvailable` cho lịch bị lỡ; không đánh thức máy. Máy cần bật và tài khoản chạy phải đăng nhập để tác vụ có ngữ cảnh chạy.

Định nghĩa tác vụ và bằng chứng thực thi nằm trong [báo cáo](../../docs/reports/operations/backup_automation_20261019.md). Config thực tế: `.runtime/backup_automation_20261019/job.json`. Công cụ không tự đoán DB P2 hoặc cấu hình ngày làm việc của web: các nguồn và lịch được liệt kê rõ trong config.

## Phạm vi

- ReviewStore demo 001/003: SQLite, nhật ký kết luận, định danh/binding và nguồn/kết quả cần để mở lại hồ sơ.
- Bốn SQLite P2 riêng: `step2_uat`, `browser_uat`, `assistant_review`, `p2_web`. Mỗi journal giữ toàn bộ lịch sử, kể cả nhiều lần rà hoặc snapshot trước.
- Nguồn và kết quả P2 đã khóa cần cho đủ 32 tình huống/73 giao dịch. Các journal cùng snapshot dùng chung một bản tài nguyên trong gói.

Mỗi SQLite dùng Backup API và một read snapshot riêng; ReviewStore vẫn chụp cùng audit/identity dưới khóa hiện có. Các journal UAT P2 độc lập với ReviewStore, không có giao dịch nguyên tử chung giữa các DB; manifest ghi thời điểm chụp từng journal. Khi kiểm tra gói, P2 được mở chỉ đọc, không tạo DB thiếu hoặc thay journal mode.

Không đưa bí mật SMTP/OA, cấu hình gửi thật hoặc các file chứng từ bên ngoài kho vào gói. Khôi phục mặc định dry-run, không có worker hoặc gửi tự động.

## Vị trí và theo dõi lỗi

Kho: `.runtime/scheduled_review_backups`. Mỗi lượt thành công là một thư mục `run-...` bất biến có `suite_manifest.json`.

- `latest.json`: kết quả lượt gần nhất, mã lỗi, số lần thất bại liên tiếp và đường dẫn/lúc có bản thành công gần nhất.
- `events.jsonl`: lịch sử lượt chạy, bao gồm lỗi sao lưu hoặc dọn bản cũ.
- `backup_repository.json`: định danh kho và liên kết đúng nhóm nguồn. Không sửa/xóa để ép kho nhận một nguồn khác.
- Task Scheduler giữ mã kết thúc: `0` thành công hoặc bỏ qua lượt đang trùng, `1` lỗi sao lưu/cấu hình, `2` sao lưu tốt nhưng dọn bản cũ có cảnh báo. Lệnh `status` cũng trả `2` nếu trạng thái không khỏe hoặc lỡ lịch quá khoảng chờ 2 giờ.

```powershell
$backupPython = 'C:\Users\Technical Support\AppData\Local\Programs\Python\Python312\python.exe'
& $backupPython -B -m sme_fraud.backup_job status --config .runtime/backup_automation_20261019/job.json
Get-ScheduledTaskInfo -TaskName 'Agent22-ReviewBackup'
```

Lỗi trước khi đọc được config hợp lệ không thể ghi an toàn vào một kho chưa xác định; xem mã lỗi Task Scheduler và chạy `check-config` từ terminal. Lỗi trong lượt sao lưu hợp lệ được ghi vào các file trên. Báo lỗi hiện là cục bộ, không gửi Email/Zalo.

## Chạy thủ công và xem kế hoạch dọn

```powershell
& $backupPython -B -m sme_fraud.backup_job check-config --config .runtime/backup_automation_20261019/job.json
& $backupPython -B -m sme_fraud.backup_job run --config .runtime/backup_automation_20261019/job.json
& $backupPython -B -m sme_fraud.backup_job prune-plan --config .runtime/backup_automation_20261019/job.json
```

`run` thực hiện một lượt ngay, còn lịch giờ do Windows Task Scheduler quản lý. Hai lượt trùng dùng khóa liên tiến trình; lượt sau được bỏ qua và không ghi đè trạng thái của lượt đang chạy.

Chỉ dọn sau khi tạo và xác minh một bản mới thành công. Một bản chỉ đủ điều kiện xóa khi quá 30 ngày, không thuộc 3 bản thành công mới nhất, có đúng định danh chủ kho và còn khớp checksum. Nếu chỉ có 1–2 bản thì giữ cả hai, không tạo bản giả để đủ 3. Không dùng mtime của thư mục làm ngày sao lưu.

Không dọn bản thủ công, gói không thuộc kho, gói hỏng, thư mục staging hoặc đường dẫn symlink/junction. Gói hỏng được giữ để điều tra và báo cảnh báo. Trước từng lần xóa đệ quy, chương trình kiểm tra lại đường dẫn tuyệt đối là con trực tiếp của đúng kho và manifest không đổi. Lỗi sao lưu không chạy retention; lỗi xóa không biến bản sao mới thành hỏng nhưng được báo riêng.

## Kiểm tra và khôi phục

```powershell
$backupState = Get-Content .runtime/scheduled_review_backups/latest.json -Raw | ConvertFrom-Json
& $backupPython -B -m sme_fraud.backup_job verify --backup $backupState.last_success_bundle
& $backupPython -B -m sme_fraud.backup_job restore --backup $backupState.last_success_bundle --output .runtime/restored_review_p2_NEW
& $backupPython -B -m sme_fraud.backup_job serve --restored .runtime/restored_review_p2_NEW --p2-store step2_uat --port 8772
```

Thư mục đích phải chưa tồn tại. Sau phục hồi:

- `review/`: bản ReviewStore đầy đủ, đã di chuyển binding/fingerprint tới đường dẫn mới.
- `p2/stores/<id>.sqlite3`: cả bốn journal P2.
- `p2/snapshots/<snapshot-id>/data` và `reports`: tài nguyên để mở P2 độc lập với nguồn ban đầu.
- `suite_restore_receipt.json`: bằng chứng phục hồi được ghi cuối cùng. Thư mục thiếu receipt là chưa hoàn tất, không tự ghi đè hoặc mở như một gói hoàn chỉnh.

Màn hình `/p2-controls` phục vụ journal chọn bằng `--p2-store`. Muốn xem 20 ghi chú trợ lý cũ dùng `assistant_review`; chúng vẫn là nhận xét mô phỏng, không phải nghiệm thu kế toán độc lập. Có thể mở journal khác trên một cổng riêng. Khi dùng web, journal của bản phục hồi mới được ghi; gói backup gốc giữ nguyên.

Giữ runtime tương thích với manifest khi khôi phục; công cụ chưa chuyển đổi giữa các phiên bản schema/code. Đổi giờ trong config không tự cập nhật trigger Windows: cần cập nhật cả tác vụ đúng tên và đối chiếu `NextRunTime`/XML. Đổi nhóm nguồn hoặc vị trí DB cần kho mới hoặc quy trình chuyển kho rõ ràng, không sửa định danh kho để vượt kiểm tra.

Cơ chế dựa trên [SQLite Backup API](https://www.sqlite.org/backup.html), [Python Connection.backup](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.backup) và [Windows Task Scheduler](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/register-scheduledtask).
