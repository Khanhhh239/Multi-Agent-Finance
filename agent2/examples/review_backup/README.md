# Sao lưu/khôi phục Case Management

[Công cụ](../../sme_fraud/review_backup.py) sao lưu SQLite bằng `Connection.backup()`, cùng nhật ký kết luận, định danh hồ sơ và các nguồn/snapshot cần cho web. [Biên bản kiểm chứng](../../docs/reports/operations/operational_reliability_20261019.md).

**Bổ sung 19/10:** [Sao lưu tự động và gói tổng hợp P2](automation.md) dùng `sme_fraud.backup_job`: lịch 02:00, giữ 30 ngày/tối thiểu 3 bản tốt, trạng thái lỗi và phục hồi cả các journal P2 riêng. Hướng dẫn dưới đây vẫn dành cho gói ReviewStore v1; gói tổng hợp dùng CLI riêng và không thay các bản sao cũ.

## Tạo và kiểm tra bản sao

Thư mục báo cáo cần được `ReviewStore.prepare()` bằng đúng database đang dùng. Bước này tạo/kiểm tra `review_store_binding.json`, liên kết thư mục với SQLite có thẩm quyền; không chạy lại rules khi cache còn đúng.

```powershell
python -B -m sme_fraud.review_backup backup --database .runtime/step2_review_20261019/demo.sqlite3 --data-root data/synthetic_sources_20261017_v2 --reports-root .runtime/step2_review_20261019/demo_reports --output .runtime/my_backups/review_NEW
python -B -m sme_fraud.review_backup verify --backup .runtime/my_backups/review_NEW
```

Output phải là thư mục **chưa tồn tại**, nằm ngoài nguồn và báo cáo đầu vào. Công cụ không có chế độ ghi đè. Nếu ứng dụng dùng lịch làm việc riêng, truyền cùng `--working-weekdays` và các `--non-working-date`; đây là cấu hình do người vận hành cung cấp, không tự đọc từ một tiến trình web khác.

Trong lúc chụp, công cụ giữ khóa nhật ký của mọi kịch bản đã chuẩn bị và một SQLite read transaction. Các thao tác ghi nhật ký có thể phải chờ/thử lại. Writer SQLite khác vẫn có thể hoạt động qua WAL; bản sao giữ một snapshot nhất quán của DB, không ghép tùy ý file `.sqlite3` với WAL ở thời điểm khác.

Bản sao gồm:

- `review.sqlite3`: toàn bộ bảng của ReviewStore, gồm hồ sơ/bằng chứng cache, yêu cầu tài liệu, ngân sách/lượt đã phân bổ, settings và outbox/receipt nếu có.
- `reports/sme_fraud_001` và/hoặc `003`: kết quả detector cần cho web, `case_identity.json`, `feedback_audit.jsonl`, `case_review_states.csv` nếu có, `review_store_binding.json`.
- `data/sme_fraud_*`: các file nguồn mà ReviewStore thực sự dùng. Không gom feature/model/labels/splits chỉ để vận hành web.
- `backup_manifest.json`: checksum từng file, phạm vi, fingerprint ban đầu, phiên bản runtime, số dòng/hash từng bảng và đầu chuỗi lịch sử.

Cả hai kịch bản trong DB phải được sao lưu cùng nhau; không tạo bản sao DB đầy đủ nhưng chỉ giữ một phần báo cáo. Phiên bản đầu hỗ trợ 001/003 và từ chối 005. Nội dung UAT P2 nằm trong database riêng, không tự gộp vào bản sao ReviewStore này. File cấu hình SMTP/OA, mật khẩu/token bên ngoài và file chứng từ ngoài kho hiện tại cũng không thuộc gói.

## Khôi phục vào bản riêng

```powershell
python -B -m sme_fraud.review_backup restore --backup .runtime/my_backups/review_NEW --output .runtime/restored_review_NEW
python -B -m sme_fraud.review_backup serve --restored .runtime/restored_review_NEW --port 8770
```

Mở `http://127.0.0.1:8770/`. Bản khôi phục chứa đủ nguồn và báo cáo để mở hồ sơ; không cần đường dẫn nguồn gốc còn tồn tại. `serve` bật thông báo **dry-run**, không tự dispatch hoặc nạp cấu hình gửi thật.

Công cụ đối chiếu checksum, `integrity_check`, foreign keys, chuỗi hash nhật ký và scope hồ sơ trước khi công bố bản phục hồi. Fingerprint cache chứa đường dẫn tuyệt đối nên được tính lại cho vị trí mới; liên kết SQLite/báo cáo được cập nhật đường dẫn và giữ nguyên `binding_id`. Chỉ các tham chiếu đường dẫn này được đổi; điểm, thành viên hồ sơ, dữ kiện và lịch sử nghiệp vụ giữ nguyên. `restore_receipt.json` ghi nhận việc di chuyển.

Không chạy khôi phục lên thư mục đang dùng. Việc `restore` không thay DB hoặc báo cáo gốc; nguồn bị sửa/thiếu, DB sai thẩm quyền, nhật ký hỏng hoặc runtime không tương thích sẽ bị từ chối. Giữ phiên bản ứng dụng phù hợp với `runtime_contract` trong manifest; công cụ này chưa làm migration giữa các phiên bản schema/code khác nhau.

Gói sao lưu dùng checksum để phát hiện hỏng/thay đổi dữ liệu, chưa phải chữ ký xác thực hoặc bản sao mã hóa. Chưa có lịch chạy/retention tự động. Nội dung phục hồi từ SQLite được kiểm tra bằng hash dữ liệu từng bảng; không yêu cầu byte của file DB giống hệt sau khi cập nhật fingerprint đường dẫn.

## Bản diễn tập của đợt 19/10

- Bản sao demo đang dùng: `.runtime/backup_restore_20261019/final/backup_live_demo`.
- Bản khôi phục tương ứng: `.runtime/backup_restore_20261019/final/restored_live_demo`.
- Thử kết luận có dữ liệu không rỗng: `simulation_source` → `backup_marked_simulation` → `restored_marked_simulation`, cùng thư mục `final`. Hai kết luận mang `SIM_BACKUP_RESTORE`, chỉ để kiểm tra phục hồi; không phải nghiệm thu kế toán và không ghi vào demo đang dùng.

Tham khảo cơ chế [SQLite Online Backup API](https://www.sqlite.org/backup.html) và [Python Connection.backup](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.backup).
