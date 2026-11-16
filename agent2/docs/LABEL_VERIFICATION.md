# Xác minh nhãn tại doanh nghiệp

Màn hình `Cấu hình phân tích → Xác minh nhãn giao dịch`, hoặc
`http://127.0.0.1:8800/agent2/label-verification#company=C001`.
Đây là xác minh nhãn cho train có giám sát, tách biệt với phiếu rà nghiệp vụ và
đánh giá cảnh báo hữu ích. Cảnh báo, điểm ML và `confirmed_risk` không tự trở
thành nhãn gian lận.

## Cách sử dụng

1. Đăng nhập Portal, chọn doanh nghiệp được cấp quyền.
2. Mở **Tạo danh sách từ dữ liệu đã lưu**, chọn snapshot và chọn từng giao dịch.
   Phiên thử train HE hiện dùng đúng **4 giao dịch / 2 feature**; không tự lấy
   bốn dòng đầu. Luồng xác minh này ghim cùng kế hoạch snapshot của phiên thử.
3. Bấm **Tạo danh sách xác minh**. Tất cả nhãn khởi đầu trống.
4. Mở từng giao dịch, xem ngày, số tiền, phiên bản, giao dịch và căn cứ liên quan.
   Bản ghi nguồn có thể gồm hóa đơn, phân bổ, phê duyệt, nhân viên và bút toán
   theo provenance hiện có. Đây là bản xuất dữ liệu, không tự trở thành bản scan
   chứng từ gốc đã xác minh. Chỉ hiển thị căn cứ mà builder point-in-time đã dùng.
5. Chọn kết luận:

   | Kết luận | Điều kiện |
   |---|---|
   | Gian lận đã xác minh | Người có quyền đã đối chiếu đủ chứng từ và có căn cứ xác nhận gian lận. Một sai sót kế toán hoặc cảnh báo chưa đủ cho kết luận này. |
   | Đã xác minh không gian lận | Đã đối chiếu đủ chứng từ và có căn cứ xác nhận giao dịch không gian lận trong phạm vi xác minh. |
   | Chưa rõ — để trống | Thiếu chứng từ, nguồn mâu thuẫn hoặc chưa xác định được bản chất. Lưu `null`, không đổi thành 0. |

   Với hai kết luận đã xác minh: chọn căn cứ đã xem, ghi giải thích ít nhất
   10 ký tự, xác nhận đã đối chiếu đủ chứng từ rồi **Lưu nhãn giao dịch**.
   Không có căn cứ phù hợp thì để trống; màn hình này chưa nhận thêm tài liệu ngoài
   snapshot. Bổ sung nguồn qua quy trình nhập và tạo snapshot/danh sách mới.
6. Bấm **Khóa phiên bản nhãn**. Có thể khóa một bộ còn nhãn trống để lưu tiến độ,
   nhưng không đủ điều kiện dùng bộ đó cho circuit train hiện tại.
7. **Tải bộ nhãn đã khóa** để kiểm tra phiên bản/checksum. Nếu cần sửa, bấm
   **Mở phiên bản mới để sửa**. Nhãn được giữ nguyên; bản khóa cũ vẫn xuất lại
   bằng đúng revision và checksum cũ.

## Quyền và giới hạn

- Đọc nguồn, danh sách và bộ nhãn đã khóa: quyền `data.import` đúng tenant/DN.
- Tạo, sửa, khóa hoặc mở phiên bản mới: thêm `evidence.verify`.
- Không yêu cầu `model.fit` chỉ để xác minh; không yêu cầu quyền xác minh mới
  khi chỉ đọc bộ nhãn đã xác minh. Quyền được kiểm lại trước/sau thao tác.
- Reviewer và thời điểm do server ghi, không nhận danh tính/thời gian tự khai
  trong body. Portal hiện dùng danh tính workspace chung; đây chưa phải bằng
  chứng định danh riêng từng cá nhân. Cần tài khoản riêng trước quy trình vận
  hành đòi hỏi truy trách nhiệm từng người.
- Dữ liệu mô phỏng luôn xuất chế độ `synthetic_expected`. Căn cứ mô phỏng
  không được dùng để xác nhận nhãn thật; không tuyên bố precision/recall/accuracy.
- Xuất `training_ready=true` chỉ khi đủ 4 nhãn có cả hai lớp và đầu vào feature
  hợp lệ. Đây chỉ là kiểm tra điều kiện kỹ thuật; không phê duyệt nghiệp vụ/model.
- Màn hình **không gửi nhãn lên cloud, không consent/train, không kích hoạt model**
  hoặc đổi hàng đợi. Tệp xuất là `enterprise-label-packet/1.0.0`, chưa tự chuyển
  thành tệp `verified_labels` của CLI consent cũ; bước tiêu thụ phải kiểm lại
  `packet_id/revision/lock_sha256` và nguồn dataset/receipt, không sửa JSON tay để
  bỏ ràng buộc. Nhãn trống không được đưa vào train.

Với [luồng nhiều batch](HE_TRAINING_BATCHES.md), `batch-create-labels` tạo các
danh sách từ kế hoạch đã ghim để rà ngay trên web này. Sau khi khóa, người fit
dùng `batch-confirm-locked` đọc bản khóa trực tiếp từ kho DN, không sửa file
export. Mỗi batch được phép một lớp nếu toàn tập train có cả hai lớp; cờ
`training_ready` của bộ riêng lẻ chỉ nói về việc dùng riêng bộ đó. Thiếu nhãn
vẫn chặn toàn phiên, không tự lọc dòng. Nút khóa trên màn hình vẫn không train.

## Ràng buộc và lưu trữ

`enterprise-label-packet/1.0.0`, target `verified-fraud/1.0.0`. Ghim tenant/DN,
snapshot ID, manifest/data checksum, source contract, as_of, kỳ train, thứ tự
ID/revision giao dịch, mapping fingerprint và source plan hash. Căn cứ từng
giao dịch có ID băm chính nội dung và bảng nguồn; chỉ chọn đúng tập đã ghim.
Không dùng file bên ngoài để tự bổ sung căn cứ vào bản khóa cũ.

Mỗi lần lưu tăng revision của bộ nhãn, chỉ sửa dòng đã chọn; giữ các nhãn khác.
`expected_revision` chống ghi đè đồng thời; thông báo xung đột yêu cầu tải lại.
`request_id` giữ nguyên khi mất phản hồi; gửi lại cùng nội dung nhận đúng phiên
bản đã lưu, đổi nội dung cùng ID bị từ chối. Khóa là một revision bất biến có
SHA-256 toàn nội dung. Mở phiên bản mới sao chép nhãn và giữ toàn bộ lịch sử.

SQLite riêng `verified-labels.sqlite3`, payload AES-GCM với AAD theo owner,
packet ID và revision; trigger append-only cho history/receipt. Trong backend
HE hiện tại, khóa nhãn dẫn xuất HKDF riêng từ khóa kho phiên doanh nghiệp đang
được bảo vệ DPAPI, không phát sinh khóa rõ/config/token mới. Không đổi model,
khóa gốc, snapshot DB hoặc dữ liệu cũ. Sai khóa/tamper từ chối đọc.

Backend mới tự mở kho nhãn khi có HE durable backend. Không cấu hình thì trả
`LABELS_NOT_CONFIGURED`, không lưu tạm trên trình duyệt. Muốn dùng bản mới cần
khởi động lại Agent2 và Portal để nạp route allowlist; triển khai live chưa thực
hiện trong thay đổi này. Chỉ thêm allowlist Portal cho màn hình/asset và API
nhãn, không sửa đăng nhập hay cấp thêm quyền cho tài khoản live.

## API và kiểm tra

Tiền tố `/api/v1/companies/{company}` (qua Portal thêm `/agent2`):

| Phương thức | Đường dẫn | Chức năng |
|---|---|---|
| GET | `/label-sources`, `/label-sources/{snapshot_id}` | Snapshot được cấp quyền và giao dịch đã biết tại cutoff |
| GET, POST | `/label-packets` | Xem hoặc tạo bộ nhãn từ request adapter snapshot |
| GET | `/label-packets/{packet_id}` | Xem bản hiện tại |
| POST | `/label-packets/{packet_id}/save` | Ghi đúng một dòng với expected_revision/request_id |
| POST | `/label-packets/{packet_id}/lock`, `/reopen` | Khóa hoặc mở phiên bản mới |
| POST | `/label-packets/{packet_id}/export` | Xuất đúng revision/lock_sha256 bất biến |

`tests_he/test_label_packets.py` kiểm tra hai profile nguồn, phân quyền, tách
tenant/DN, null/khóa/version/retry/xung đột, nhãn cũ, AEAD/restart/tamper và HTTP
Portal thật. `scripts/check_label_verification_ui.py` chạy Chrome headless với
Portal và dữ liệu mô phỏng riêng, không dùng thông tin đăng nhập hoặc dịch vụ live.
