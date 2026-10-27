# Sao lưu/khôi phục và thống nhất kết luận web/CLI — 19/10/2026

> Tài liệu tham chiếu theo mốc ghi trong tiêu đề. Xem [trạng thái hiện tại](../../STATUS.md) trước khi dùng số liệu hoặc kế hoạch cũ.

**Cập nhật tiếp ngày 19/10:** [Sao lưu tự động và gói P2](backup_automation_20261019.md) đã bổ sung lịch 02:00, giữ 30 ngày/tối thiểu 3 bản tốt, báo lỗi cục bộ và phục hồi 4 journal P2. Các mục “chưa có” bên dưới ghi trạng thái của đợt triển khai v1 trước đó; xem báo cáo mới cho phần tự động hóa.

Đã bổ sung hai phần phục vụ bản dùng thử: gói sao lưu ReviewStore tự chứa nguồn/snapshot cần thiết và một cổng kết luận dùng chung cho web/CLI. Kết quả nghiệm thu cuối được ghi tại [verification.json](../../../reports/backup_restore_20261019/final/verification.json), [kiểm thử](../../../reports/backup_restore_20261019/final/tests.json), [log](../../../reports/backup_restore_20261019/final/tests.log).

## Sao lưu và phục hồi

Sao lưu dùng SQLite Backup API từ read transaction đã ghim snapshot. Khóa nhật ký tất cả kịch bản được giữ khi chụp SQLite cùng audit/identity/binding. Nguồn và báo cáo được kiểm tra trước/sau sao chép; không dùng phép copy riêng file DB để bỏ sót WAL.

Gói chứa toàn bộ bảng SQLite, nhật ký kết luận, định danh/quan hệ scope hồ sơ, liên kết kho SQLite và nguồn/kết quả detector thực sự cần cho web. Có checksum file, integrity/foreign-key check, hash dữ liệu từng bảng và kiểm tra chuỗi lịch sử. Khôi phục chỉ công bố sang thư mục mới, tính lại fingerprint chứa đường dẫn và cập nhật binding; giữ nguyên dữ liệu nghiệp vụ.

Diễn tập dùng demo 001/003: **584 + 627 = 1.211 hồ sơ**, đếm theo `case_queue.csv` và đối chiếu với DB/identity. Con số 1.326 + 1.359 = 2.685 trong log prepare là số giao dịch thành viên, không phải hồ sơ. Bản phục hồi nằm ở `.runtime/backup_restore_20261019/final/restored_live_demo`; có thể mở riêng bằng lệnh `serve` trong [hướng dẫn](../../../examples/review_backup/README.md). Nguồn gốc không phải còn tồn tại mới mở được bản khôi phục. Thông báo mặc định dry-run, không tự dispatch.

Hai kết luận `SIM_BACKUP_RESTORE` chỉ được tạo trong nhánh mô phỏng riêng để kiểm chứng nhật ký không rỗng. Không tạo kết luận vào demo đang dùng hoặc nhận đây là review nghiệp vụ độc lập. Gói ReviewStore chưa tự gom SQLite UAT P2 riêng hoặc cấu hình gửi tin/bí mật nằm ngoài DB.

## Cổng kết luận chung

`ReviewStore.save_feedback` và CLI/API `record_feedback` cùng gọi `_record_feedback` → `check_decision` dưới `feedback_lock`. Nếu yêu cầu hiện hành còn `open` hoặc `received`, mọi kết luận cuối bị chặn. `information_gap` vẫn được ghi có lý do. Sau khi mọi yêu cầu đã `reviewed`/`cancelled`, người dùng mới có thể chủ động ghi kết luận cuối có lý do.

Mỗi thư mục báo cáo gắn với một SQLite có thẩm quyền qua `review_store_binding.json` và ID trong `settings`. Nhầm/mất DB, thiếu liên kết, scope không khớp hoặc nhật ký hỏng đều không được diễn giải là không còn yêu cầu tài liệu. CLI hỗ trợ `--database` để đối chiếu kho và `--expected-hash` để kiểm tra phiên bản kết luận; hash chain cũ không bị sửa.

Liên kết kho là bổ sung vận hành, không tham gia tính điểm. Bước prepare trên demo hiện hành chỉ đăng ký đúng cặp DB/báo cáo khi cache còn khớp; không chấm lại rules, graph, A5 hay ML. Xem [hướng dẫn CLI và chuyển phiên bản](../../../examples/review_decision_gate/README.md).

## Kiểm chứng và phần còn mở

**646 kiểm thử Python đạt**, không lỗi hoặc bỏ qua. Trong đó có 20 kiểm thử sao lưu/khôi phục và 12 kiểm thử cổng kết luận mới. [HTTP trên bản phục hồi](../../../reports/backup_restore_20261019/final/http_verification.json) xác nhận web trả 409 và tiến trình CLI từ chối cùng hồ sơ còn yêu cầu tài liệu; nhật ký không thêm kết luận. API hiển thị đúng 584/627 hồ sơ, yêu cầu đang mở và chế độ dry-run.

Đã phục hồi và đối chiếu hash dữ liệu mọi bảng cho **1.211 hồ sơ, 3 yêu cầu tài liệu với 6 sự kiện lịch sử**. Nhánh mô phỏng riêng bảo toàn thêm 2 kết luận có nhãn `SIM`; 1.209 tệp đã khóa không đổi. Bản phục hồi đang mở tại [localhost:8770](http://127.0.0.1:8770/), dùng code mới và không tự gửi thông báo.

- Kiểm thử mới bao gồm SQLite WAL đang có dữ liệu, writer khác cập nhật khi backup, chờ khóa feedback, nhiều kịch bản, phục hồi thiếu nguồn gốc, từ chối ghi đè, checksum/manifest/runtime/scope sai và dọn staging khi lỗi ghi.
- Kiểm thử web/CLI gồm HTTP thực, tiến trình CLI thực, tất cả loại kết luận cuối, đã nhận chưa rà, hủy có lý do, alias ID, DB nhầm/mất, liên kết/chuỗi hash bị sửa và ghi nhận thiếu bằng chứng.
- Đối chiếu snapshot phục hồi bằng hash dữ liệu mọi bảng, scope/đầu chuỗi audit và lịch sử yêu cầu; kiểm tra lại 1.209 tệp đã khóa. 005 chỉ băm opaque, không parse/nạp/chấm hay dùng oracle.
- Chưa nghiệm thu trực quan browser hoặc kế toán độc lập; RR09 vẫn chờ chủ kiểm soát. Chưa có lịch backup/retention tự động, chữ ký/mã hóa gói hoặc migration khác phiên bản runtime. Cấu hình lịch làm việc do người vận hành cung cấp; bí mật SMTP/OA không tự xuất.

Cơ chế backup dựa trên [SQLite Online Backup API](https://www.sqlite.org/backup.html) và [Python Connection.backup](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.backup).
