# Cổng kết luận chung cho web và CLI

Web `ReviewStore.save_feedback`, CLI `python -m sme_fraud.feedback` và hàm `record_feedback` cùng đi qua [_record_feedback](../../sme_fraud/feedback.py) và [check_decision](../../sme_fraud/review_decision_gate.py), dưới một khóa nhật ký.

## Quy tắc

| Trạng thái yêu cầu tài liệu của scope hiện hành | Cần bổ sung bằng chứng | Kết luận cuối |
|---|---|---|
| Chờ bổ sung (`open`) | Cho ghi có lý do | Chặn |
| Đã nhận, chờ rà lại (`received`) | Cho ghi có lý do | Chặn |
| Đã rà lại (`reviewed`) hoặc hủy có lý do (`cancelled`), không còn yêu cầu khác đang mở | Cho ghi có lý do | Người dùng có thể ghi kết luận có lý do |
| Thiếu/sai SQLite, thiếu liên kết hoặc nhật ký hỏng | Không suy là đã đủ chứng từ | Từ chối |

Các kết luận cuối gồm `confirmed_suspicion`, `confirmed_fraud`, `non_compliance`, `false_positive`. Đã nhận/rà tài liệu không tự tạo bất kỳ kết luận nào. Yêu cầu của scope cũ vẫn giữ trong lịch sử; không tự áp sang scope mới hoặc bị xóa khi đổi ID hồ sơ tương đương.

## SQLite có thẩm quyền

Khi `ReviewStore.prepare()` thành công, mỗi thư mục báo cáo có `review_store_binding.json`. File chứa kịch bản, đường dẫn SQLite/báo cáo và ID được đối chiếu với `settings` trong chính DB. CLI đọc liên kết này để kiểm tra yêu cầu, không đoán đường dẫn database từ tên thư mục. Mở database khác trên cùng thư mục báo cáo sẽ bị chặn; muốn dùng bản sao độc lập hãy [khôi phục sang thư mục mới](../review_backup/README.md).

Với bản cài trước thay đổi này, chạy lại bước prepare của **đúng ReviewStore đang sử dụng**, rồi khởi động lại web để nạp code mới. Các cache còn khớp chỉ được đăng ký liên kết; không chấm lại detector hoặc đổi điểm. Không xóa DB/liên kết như cache tạm. Nếu mất một trong hai, phục hồi cặp tương ứng từ bản sao lưu.

Ví dụ đăng ký demo hiện tại, không mở server hoặc gửi thông báo:

```powershell
python -B -m sme_fraud.review_server --data-root data/synthetic_sources_20261017_v2 --reports-root .runtime/step2_review_20261019/demo_reports --database .runtime/step2_review_20261019/demo.sqlite3 --prepare-only
```

## Dùng CLI

```powershell
python -X utf8 -B -m sme_fraud.feedback --report .runtime/step2_review_20261019/demo_reports/sme_fraud_003 --case-id IR_c39bd6eef7d31a7c --decision information_gap --reviewer "Tên người rà" --reason "Cần hóa đơn gốc và phiếu chi"
```

Lệnh này ghi vào nhật ký thật của thư mục được chọn; dùng báo cáo bản sao khi diễn tập. Không ghi nhận là nghiệm thu độc lập nếu chỉ thử kỹ thuật.

Có thể thêm `--database PATH` để kiểm tra tường minh rằng PATH trùng kho đã gắn, và `--expected-hash HASH` để từ chối lưu khi kết luận đã đổi sau lúc đọc. Hash rỗng dành cho lần đầu; nếu bỏ tùy chọn, CLI giữ hành vi nối sự kiện mới sau khi lấy khóa, không ghi đè sự kiện cũ. Web vẫn dùng kiểm tra phiên bản bắt buộc như trước.

CLI trả mã khác 0 khi bị chặn, không thêm kết luận hoặc làm hồ sơ thành đóng. JSON đầu ra dùng ASCII escapes để không lỗi sau khi đã ghi thành công trên console Windows; chuỗi tiếng Việt vẫn được lưu UTF-8 và giải mã JSON bình thường.

Báo cáo lịch sử chưa có DB/liên kết chỉ được ghi `information_gap`; kết luận cuối phải qua một ReviewStore đã chuẩn bị. Phân bổ ngân sách của web giữ như hiện tại; thay đổi này thống nhất cổng quyết định và nhật ký, chưa thêm cơ chế đăng nhập hay thay tên nhập thành danh tính đã xác thực.

[Biên bản kiểm chứng](../../docs/reports/operations/operational_reliability_20261019.md).
