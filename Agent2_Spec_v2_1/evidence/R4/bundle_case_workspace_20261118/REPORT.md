# Nghiệm thu xử lý vụ trên màn hình chính — 18/11/2026

Trạng thái kỹ thuật: **READY_FOR_REVIEW** trên dữ liệu mô phỏng và Portal cô lập.
Chưa triển khai/restart Portal live, sửa quyền live hoặc nghiệm thu production/HE.

## Kết quả

- Bổ sung PDF/PNG/JPEG vào đúng vụ, chọn loại chứng từ, giữ checksum và các
  phiên bản. Tệp mới/phiên bản mới chờ xác minh; xác minh bản cũ không xác minh
  hộ bản mới. Tệp đính kèm từ phiếu cũ chỉ nhập vào hồ sơ khi chọn rõ loại tài liệu.
- Gửi kết quả thực hiện cùng chứng từ, chờ bên ngoài, đổi bộ phận/hạn, xác nhận
  hoàn tất, yêu cầu làm lại và mở lại ngay trong màn hình **Vụ cần rà**.
- Kiểm tra quyền backend và trạng thái khả dụng của nút theo dữ liệu server.
  Hoàn tất cần kết quả đã gửi và chứng từ xác minh theo chính sách hiện hành;
  sau làm lại/mở lại cần gửi kết quả mới.
- Giữ binding `snapshot_id`, `run_id`, `bundle_id`, `pin_id`, `review_id`, mã vụ.
  Không nhận task/tài liệu của doanh nghiệp, vụ hoặc lượt chạy khác.
- Ghi thao tác và biên nhận trong cùng SQLite transaction. Mất quyền trước
  commit rollback cả hai. Retry cùng mã trả đúng biên nhận; đổi nội dung cùng
  mã bị từ chối. Revision cũ bị chặn.
- Sau reload, lệnh đang chờ giữ nguyên mã/nội dung. Với upload, chỉ lưu metadata
  và checksum trong sessionStorage; chọn lại đúng tệp trước khi tiếp tục.
- Báo cáo JSON/CSV và các số tổng có chứng từ/task hiện hành, tách kết quả rà
  khỏi hoàn tất công việc; lịch sử và checksum báo cáo được giữ.

## Kiểm thử

[Backend receipt và SHA-256 mã nguồn](backend_tests.json):
`test_bundle_remediation`, `test_bundle_workspace`, `test_remediation`.
Lượt hồi quy cuối **32 test qua, 0 lỗi**.
Bộ mới gồm 8 ca: vòng đời đầy đủ; phiên bản và evidence đã ghim; replay sau
restart/chống trùng; quyền và rollback tại commit; cách ly nguồn/vụ/DN; tệp cũ
và kiểu tệp; phân công/làm lại/CAS; HTTP qua Portal.

[Browser receipt](report.json): **14 nhóm qua** bằng Chrome headless, Portal
và Agent2 HTTP thật trong harness cô lập. C001 là operator; riêng C002 fixture
có thêm `evidence.verify`, không cấp quyền cho policy live.

Các ca chính gồm mất phản hồi sau commit khi phân tích/giao việc/upload/submit,
reload rồi gửi tiếp, từ chối tệp khôi phục khác checksum, không tạo version/task
trùng, C001 không có nút xác minh/hoàn tất, C002 hoàn tất → mở lại → gửi mới →
hoàn tất, export đúng checksum, đổi DN/hash và reload iframe Portal giữ C002,
nhập snapshot chuyển tới luồng bundle, viewport 390 px không tràn ngang.

Đã kiểm tra cú pháp Python/JavaScript và xem ảnh giao diện:
[desktop](desktop.png), [mobile](mobile.png).
Ví dụ báo cáo: [C001](C001-business-report.json), [C002](C002-business-report.json).

## Giới hạn được giữ

Hoàn tất task không tự đóng vụ hoặc tạo nhãn gian lận; không sửa snapshot,
feature/model/khóa hoặc điểm cũ. Portal hiện dùng danh tính workspace, chưa
xác minh danh tính cá nhân. Checklist/policy production chưa được tự chốt.
Nghiệm thu này kiểm chứng xử lý hồ sơ/task, không chứng minh hiệu quả phát hiện
gian lận, không mở rộng phạm vi HE và không gửi dữ liệu rõ lên cloud.

Hướng dẫn: [BUNDLE_CASE_WORKSPACE.md](../../../../agent2/docs/BUNDLE_CASE_WORKSPACE.md).
