# HE trong bộ điều phối bundle

Luồng mới nối bộ điều phối chung với `FourJobs` và worker Concrete hiện có:

**Snapshot đã khóa → lập đầu vào tại DN → mã hóa tại DN → worker tính bản mã
→ nhận bản mã → giải mã tại DN → áp chính sách bundle → gộp vụ → xét ngân sách
→ hàng đợi shadow → phiếu rà → báo cáo.**

Dữ liệu rõ, khóa bí mật, xử lý nguồn, giải mã và nghiệp vụ sau giải mã ở node
doanh nghiệp. Cloud worker chỉ nhận bản mã, evaluation key công khai và metadata
giao thức (định tuyến DN, build, phiên, nonce, checksum, chữ ký). Việc gộp vụ,
cấp ngân sách và lưu phiếu **không chạy trên cloud**. Không có fallback chấm rõ
cho yêu cầu `cloud_ciphertext_only`.

## Phạm vi hiện nối

| Phần | Trạng thái trong bundle HE native |
| --- | --- |
| P1 | Mạch thanh toán hóa đơn hiện có, gồm đối chiếu khoản riêng và nhóm đồng thời |
| C3 | Mạch thời gian phê duyệt/thẩm quyền hiện có |
| B1 | Mạch định danh NCC/nhân viên hiện có |
| B5/E4 | Mạch liên kết định danh, giữ vai trò chất lượng master; không cộng đôi điểm giao dịch |
| 30 luật còn lại | `unavailable`; D1–D6/F4 ở kết quả cấp tập nguồn, không giả thành cảnh báo từng giao dịch |
| Thống kê/ML contract 33 feature | `unavailable`; không lấy model ECOD/RobustZ local hoặc model canonical khác để giả là HE native |
| Chính sách/gộp vụ/ngân sách/phiếu/báo cáo | Chạy tại DN sau giải mã, dùng chính sách đã ghim, chỉ hàng đợi shadow |

Mỗi phần còn phụ thuộc nguồn, thời điểm, miền số và khóa đã cấp. Giữ các giới
hạn của mạch hiện có (ví dụ tổng P1 tối đa 4 dòng, đồ thị tối đa 4 đối tượng);
không cắt nguồn, tự đổi dấu, lượng tử hay sửa giá trị để ép thành khả dụng.
Thiếu khóa cho một profile được ghi riêng; không tạo khóa ngầm khi chấm.
Yêu cầu HE không có phép tính nào thực sự chạy sẽ không mang cờ `he_execution=true`.

Mahalanobis/các profile canonical ở luồng HE cũ vẫn độc lập. Nối adapter này
không biến toàn catalog 35 luật hoặc toàn bộ ML thành mạch HE.

## Chuẩn bị và sử dụng

1. Người vận hành cấu hình `FourWorkbench` với `he4-enterprise/1.1.0`, build
   `rules`, `c3`, `graph`, public verify key và địa chỉ worker đúng; cấp khóa
   cần dùng tại DN bằng quy trình hiện hành. Cần ít nhất một profile đã cấp khóa.
2. Trong **Cấu hình phân tích → Phát hành**, chọn snapshot nguồn và gói
   validation/chính sách đã đăng ký; chọn **HE trên cloud — chỉ gửi bản mã**
   khi chuẩn bị bundle. API prepare nhận `execution_mode=cloud_ciphertext_only`.
3. Bundle ghim checksum build/specs, triển khai, worker, binding DN, các epoch
   khóa và hash evaluation key. Thiếu backend/khóa thì prepare bị chặn rõ ràng.
   Bundle local cũ không tự có khả năng HE.
4. Kiểm gate, phê duyệt staging và kích hoạt theo quy trình release. Gate kỹ
   thuật local và kiểm pin chưa tự là đánh giá chất lượng HE hoặc phê duyệt
   production. Không sửa checksum/runtime của study cũ để đi qua gate; cập
   nhật code yêu cầu validation/qualification phù hợp.
5. Trên **Vụ cần rà**, chọn DN, snapshot, chọn chế độ HE rồi bấm **Chạy phân tích**.
   Nếu còn đang chạy, giữ nguyên lần phân tích. Reload rồi bấm
   **Tiếp tục yêu cầu đã lưu** để tiếp tục cùng job. Chế độ lấy từ pin của lượt
   đang chạy, kể cả khi con trỏ release đã chuyển sang bundle khác.
6. Khi xong, mở vụ, đối chiếu chứng từ, ghi kết quả và giao/xử lý task như cùng
   màn hình chính. Báo cáo giữ `snapshot_id`, `run_id`, `bundle_id` và nguồn HE.
   Giới hạn từng nhánh hiển thị riêng; không coi thiếu nhánh là không vi phạm.

## Giao nhận và khôi phục

- `ReleaseStore.pin` ghim cả chế độ HE; tái dùng mã chạy với chế độ local trả
  xung đột. `he_job` là metadata được bảo vệ trong kho release, trỏ tới đúng
  job bền vững của DN. Không lưu bearer token trong pin/job/link.
- Child admission dùng idempotency key theo `pin_id`; DN chết giữa tạo child
  và lưu link không tạo child khác khi gửi lại. Job còn chạy chỉ tài khoản
  đã gửi được tiếp tục; kết quả đã lưu vẫn theo quyền đọc chung của DN.
- `FourJobs` lưu context và envelope trước gửi. Mất phản hồi dùng `/v1/results`,
  `/v1/resume` hoặc cơ chế admission đã có, giữ nonce/request hash và khóa.
  Không đổi TTL/replay của worker Mahalanobis.
- Trước nhận/chuyển kết quả vào nghiệp vụ, kiểm lại snapshot, cutoff, đủ định
  danh giao dịch, binding bundle, triển khai, build và epoch khóa. Sai lệch
  chặn trước cấp ngân sách. Thay khóa/build cần xử lý hoặc bundle mới.
- Sau checkpoint kết quả, retry sau lỗi queue/phiếu/observation sử dụng
  checkpoint và receipt cấp ngân sách cũ; không tính lại hay cấp quota lần nữa.

## Kiểm chứng

`tests_he/test_bundle_he.py` kiểm giao thức và adapter bằng transport mô phỏng
để thử nhanh cả nhóm luật, quyền, pin, restart và lỗi. Đây không phải bằng
chứng tính FHE thật.

`scripts/check_bundle_he_ui.py` kiểm Portal/Chrome trên transport test.
`scripts/check_bundle_he_native.py` dùng **Concrete thật, HTTP worker thật,
khóa DPAPI mới**, dữ liệu C001/C002 mô phỏng, kiểm P1 theo tính tay, mất phản
hồi sau commit và đọc lại observation sau restart doanh nghiệp. Mặc định chỉ
cấp khóa P1 để đồng thời kiểm tra các profile còn thiếu khóa giữ unavailable.
Worker chạy trong WSL cô lập trên máy kiểm thử, không phải triển khai cloud
internet. Script không có chế độ giả lập FHE và không sử dụng state/model/khóa
của Portal live.

Các bài này kiểm chứng luồng và tính toán giới hạn; không chứng minh độ chính
xác phát hiện gian lận trên dữ liệu doanh nghiệp thật hay thông qua gate production.
