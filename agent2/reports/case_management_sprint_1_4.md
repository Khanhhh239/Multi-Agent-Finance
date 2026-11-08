# Sprint 1.4 — Hàng đợi, đồ thị và thông báo Zalo/Email

Cập nhật 18/10/2026. Đã tích hợp UI với luồng thông báo **giả lập**, theo lựa chọn của người dùng. Có adapter SMTP và Zalo OA, worker định kỳ, outbox và receiver webhook; chưa gửi tin ra ngoài. [Kết quả kiểm thử hồi quy](../.runtime/sprint_1_4_20261018/final.json), [log](../.runtime/sprint_1_4_20261018/final.log), [8 kiểm tra JavaScript/đồ thị](../.runtime/sprint_1_4_20261018/ui_checks.json).

**540/540 kiểm thử đạt**, gồm **20 kiểm thử mới** cho Sprint 1.4; **8/8 kiểm tra JavaScript/đồ thị đạt**. CLI worker đã chạy lại bản mẫu, không tạo thêm job hoặc bản ghi gửi giả lập khi không có sự kiện mới.

## Đối chiếu yêu cầu

| Đầu việc | Kết quả |
| --- | --- |
| Thẻ hồ sơ bằng ngôn ngữ kế toán | Giữ tiêu đề theo tình huống; thêm tóm tắt `explanation_vi` ngay trên thẻ, mức ưu tiên, trạng thái, quy tắc và số nghiệp vụ. Chi tiết tiếp tục có chứng từ Nợ/Có, hóa đơn, bằng chứng và lịch sử. |
| Đồ thị tương tác Cytoscape/D3 | Dùng **Cytoscape.js 3.34.3** cho đồ thị bằng chứng và mạng lưới sáu loại thực thể. Kéo nút, pan, zoom, fit và chọn nút/cạnh để đọc dữ kiện. Có giới hạn hiển thị rõ ràng. |
| Một chạm, có lý do nhanh | Nút **Xác nhận nghi vấn** / **Bỏ qua, hợp lệ**; chọn lý do nhanh hoặc nhập nội dung riêng, tên reviewer lưu cục bộ để dùng lần sau. Giữ hash chống ghi đè kết luận và nhật ký hiện có. |
| Ngân sách 5–10 hồ sơ ưu tiên/ngày | UI mặc định bật **Ưu tiên hôm nay**: xếp mức ưu tiên → điểm → ngày mở → ID, chọn trong lượt/phút còn lại theo công ty. Outbox có hạn mức hồ sơ thông báo riêng, dùng chung cho Email/Zalo/tóm tắt tuần. |
| Thông báo ưu tiên cao và tóm tắt tuần | Sự kiện hồ sơ mới/đổi phạm vi ưu tiên cao vào outbox. Tóm tắt tuần theo giờ Việt Nam; chạy bù nếu worker khởi động sau lịch trong cùng chu kỳ tuần. Khóa SQLite bảo vệ phân bổ và claim khi chạy đồng thời. |
| Email và Zalo OA | Email qua SMTP STARTTLS/SSL, OA qua API gửi text tới nhóm GMF nội bộ. Credential lấy từ biến môi trường. UI có mục **Thông báo**, bản xem trước, trạng thái và lỗi gọn. |
| Webhook | Route nhận receipt có MAC, kiểm app/timestamp, chống ghi lặp; chỉ đối chiếu message ID đã gửi. Receipt không tạo kết luận rà soát hoặc thay đổi hồ sơ. |

## Cách mở bản mẫu riêng

Đã dựng bản mẫu từ snapshot train/validation hiện có, lưu báo cáo và database riêng. Nguồn dữ liệu/báo cáo gốc giữ nguyên hash; không nhập kết luận giả vào hồ sơ nguồn.

```powershell
python -B -m sme_fraud.review_server --data-root data/feature_model_sync_20261017 --reports-root reports/case_management_20261018 --database .runtime/review/sprint14_demo.sqlite3 --port 8765 --qa
```

Mở `http://127.0.0.1:8765`. Nếu cổng đang có dịch vụ khác, chọn `--port 8766`; cấu hình `case_url` cùng cổng trong file notification config để liên kết thông báo mở đúng dịch vụ. Tiến trình server cũ cần khởi động lại để nạp mã/UI mới. Ở máy hiện tại có thể thay `python` bằng `& 'C:\Users\Technical Support\AppData\Local\Programs\Python\Python312\python.exe'`.

Trên bản UI mặc định, `python start_review.py` vẫn hoạt động. Route và tài nguyên được whitelist, app giữ bind loopback. Không cần CDN; thư viện và giấy phép ở [review_ui/vendor](../review_ui/vendor/manifest.json), có SHA512 tarball và SHA256 asset. [Nguồn phát hành Cytoscape](https://github.com/cytoscape/cytoscape.js/releases/tag/v3.34.3), [API tương tác](https://js.cytoscape.org/).

Trong UI:

1. **Ưu tiên hôm nay** hiển thị hồ sơ có thể xử lý trong ngân sách. Bỏ chọn để xem tồn đọng/tìm hồ sơ khác; mọi lần nhận việc vẫn đi qua admission kiểm quota ở backend. Bộ lọc tìm kiếm không được đưa hồ sơ ưu tiên thấp vào thay suất đã chọn.
2. Mở hồ sơ, đối chiếu chi tiết/đồ thị. Chọn lý do nhanh phù hợp và nhập reviewer; bấm một trong hai nút để ghi kết luận.
3. **Xác nhận nghi vấn** kết thúc bước sàng lọc với quyết định `confirmed_suspicion`, chuyển kiểm tra sâu theo nội dung nhật ký. Nó tách biệt với quyết định `confirmed_fraud` dành cho kết luận gian lận. Các lựa chọn cũ vẫn được giữ; `information_gap` tiếp tục mở hồ sơ.
4. Chọn **Thông báo → Chạy luồng giả lập**. Có điểm vào trên thanh trên cùng khi dùng màn hình nhỏ. Liên kết trong bản xem trước mở đúng scenario/case qua URL hash.

## Hợp đồng ngân sách và thời gian

Ngân sách nhận việc giữ cơ chế đã có: 5 lượt/120 phút hoặc 10 lượt/240 phút theo công ty, snapshot, ngày Việt Nam. Các lượt đã cấp được giữ khi đóng hồ sơ, đổi bộ lọc hoặc giảm ngân sách; mở lại trong cùng ngày không tính thêm. Chế độ ưu tiên hôm nay có thể trả dưới 5/10 hồ sơ khi thiếu phút xử lý; hồ sơ đã nhận và còn mở vẫn xuất hiện để tiếp tục.

Ngân sách thông báo đếm **hồ sơ duy nhất**, không đếm số kênh hoặc người nhận. Giới hạn áp dụng là `min(ngân sách UI, daily_budget trong config thông báo)`, phạm vi công ty/snapshot/ngày Việt Nam. Mặc định trần thông báo là 10, ngân sách UI ban đầu là 5. Tóm tắt tuần chỉ liệt kê các hồ sơ trong cùng pool phân bổ ngày; tổng số tồn đọng là số liệu tổng hợp. Có thể có nhiều job gửi cho một hồ sơ khi bật nhiều kênh/người nhận.

Nguồn được theo dõi bằng case ID và hash phạm vi/bằng chứng của R6. Thay đổi thật có thể tạo sự kiện mới; tách/gộp không tự kế thừa kết luận. Hồ sơ còn chờ vì hết quota được xét lại ở ngày sau. Một hồ sơ không phát lại vô hạn ở mỗi poll. Ngày/giờ snapshot không bị trình bày thành thời điểm giao dịch mới hôm nay.

Tóm tắt mặc định thứ Hai 08:00 +07:00. Worker khởi động muộn có thể gửi một bản cho chu kỳ tuần gần nhất; cùng kỳ, cùng công ty, cùng đích không tạo thêm job. Số liệu và danh sách tóm tắt được làm mới ngay trước gửi; loại tham chiếu đã đóng/đổi bằng chứng, không tự cấp thêm suất thay thế.

## Worker và cấu hình

Chạy một lô giả lập trên cùng database với UI:

```powershell
python -B -m sme_fraud.notification_worker --data-root data/feature_model_sync_20261017 --reports-root reports/case_management_20261018 --database .runtime/review/sprint14_demo.sqlite3 --scenario 003
```

Thêm `--watch --interval-seconds 60` để lập kế hoạch và xử lý outbox theo chu kỳ khi không mở browser. Worker đọc lại config và chuẩn bị snapshot mỗi lô; backend dữ liệu cần công bố nguồn nhất quán. Có thể chạy một lô từ scheduler hiện có. Chưa đăng ký lịch nền hay bật worker lâu dài trong lượt này.

[Config giả lập](../examples/notifications/config.dry_run.json) có người nhận mẫu `.invalid`/nhóm `SIMULATION_GMF`. Nếu không cấu hình recipients, dry-run tạo hai đích giả cho mỗi công ty; khi đã khai báo recipients, chỉ công ty/kênh được liệt kê mới có đích. Giá trị bí mật không nằm trong JSON mẫu hoặc được trả về UI.

[Mẫu cấu hình gửi thật](../examples/notifications/config.live.template.json) để trống recipients/SMTP/OA. Khi triển khai, điền đích theo công ty, host và email gửi; đặt `SME_SMTP_PASSWORD`, `SME_ZALO_OA_TOKEN`, `SME_ZALO_WEBHOOK_SECRET` ngoài repository. Token OA cần được cung cấp/cập nhật bởi quy trình OAuth của môi trường; chưa có trình quản lý refresh token. Live chỉ hoạt động khi config có `dry_run=false`, `replay_existing=false` và worker có `--send`. Browser không có thao tác bật gửi thật.

Mode dry-run/live tách khóa sự kiện và outbox; job giả lập không được đổi thành job gửi thật. Lần quét đầu ở live chốt các hồ sơ hiện có làm baseline, không phát hàng loạt cảnh báo ưu tiên cao từ dữ liệu lịch sử. Tóm tắt tuần vẫn theo lịch được cấu hình. Dùng output/database thử riêng khi diễn tập trước pilot; UI và worker muốn xem cùng trạng thái phải dùng cùng database/config.

### Email

Adapter dùng [smtplib](https://docs.python.org/3.12/library/smtplib.html), xác minh TLS qua SSL context mặc định, SMTP timeout 15 giây. Một recipient/job, Message-ID ổn định theo job ID. Nội dung chỉ có mã hồ sơ, công ty, ưu tiên và đường dẫn; không tự đưa tài khoản ngân hàng, SĐT, tên cá nhân hoặc số tiền vào thông báo.

### Zalo OA và webhook

Luồng gửi dùng **nhóm GMF nội bộ** đã cấu hình `group_id` và OA token, endpoint `POST https://openapi.zalo.me/v3.0/oa/group/message`. Cần nhóm/quyền OA phù hợp. [Tổng quan hiện hành của OA](https://oa.zalo.me/home/documents/vie/guides/tong-quan-cac-loai-tin-nhan-tren-zalo-official-account-_3651713298729094511), [điều kiện nhắn nhóm](https://developers.zalo.me/docs/official-account/nhom-chat-gmf/tin-nhan/condition), [gửi text](https://developers.zalo.me/docs/official-account/nhom-chat-gmf/tin-nhan/text_message). Đây là cấu hình thông báo nội bộ; các luồng template qua SĐT/UID cần adapter/mẫu riêng khi có yêu cầu.

`POST /api/webhooks/zalo` không dùng CSRF của browser, dùng `X-ZEvent-Signature`, app ID và timestamp millisecond trong payload. Hợp đồng receiver hiện thực: `mac=SHA256(app_id + raw_body + timestamp + secret)`, timestamp lệch tối đa 5 phút. Hỗ trợ các receipt `user_received_message`/`user_seen_message` với `message.msg_ids`, bỏ qua sự kiện khác. Chỉ ghi receipt khớp Zalo message ID của live job đã gửi, mỗi loại receipt chỉ ghi một lần. Không lưu toàn bộ tin nhắn inbound hoặc diễn giải nội dung chat thành hành động nghiệp vụ.

Đã kiểm thử chữ ký, dấu thời gian và replay bằng fixture của dự án. **Chưa xác nhận schema/quyền/receipt thực tế với OA**, gồm các sự kiện riêng của GMF; cần đối chiếu payload/chữ ký thực ở bước nghiệm thu tài khoản. Trang tài liệu kỹ thuật hiện dùng nội dung phía client mà công cụ đọc chưa trích được toàn bộ ví dụ. Chưa đăng ký webhook ra Zalo. App loopback cần reverse proxy/gateway HTTPS chuyển tiếp đúng raw body, header và clock nếu nhận callback thật; triển khai UI nhiều người dùng còn cần danh tính/phân quyền.

### Trạng thái và khôi phục

Outbox có `pending`, `sending`, `simulated`, `sent`, `failed`, `uncertain`, `cancelled`. `sent` nghĩa dịch vụ đã nhận yêu cầu, chưa tự đồng nghĩa người dùng đã đọc. Receipt được lưu riêng. Lỗi chắc chắn có thể thử lại theo backoff; giới hạn mặc định 4 lần. Pending được hủy nếu đích nhận bị gỡ khỏi config hoặc hồ sơ ưu tiên cao đã đóng/đổi phạm vi. Timeout/mất kết nối sau gửi hoặc worker ngắt giữa chừng chuyển `uncertain`, cần đối chiếu ở nhà cung cấp trước khi phát lại. Không cam kết exactly-once qua mạng; không tự lặp mù các yêu cầu chưa rõ kết quả.

## Mã và API nên đọc

- [review_ui/app.js](../review_ui/app.js): thẻ, thao tác nhanh, bảo vệ double-click, xem trước thông báo và deep link.
- [review_ui/case_graph.js](../review_ui/case_graph.js): mô hình đồ thị và quản lý vòng đời Cytoscape; không ghép ngân hàng chỉ bằng số tài khoản khi chưa có mã ngân hàng.
- [review_store.py](../sme_fraud/review_store.py): chọn ưu tiên hôm nay, admission theo phút/lượt và lưu kết luận.
- [notifications.py](../sme_fraud/notifications.py): phạm vi người nhận, phân bổ ngân sách, lịch tuần, outbox và receipt.
- [notification_channels.py](../sme_fraud/notification_channels.py), [notification_worker.py](../sme_fraud/notification_worker.py): adapter và tiến trình xử lý.
- [review_server.py](../sme_fraud/review_server.py): `GET /api/cases?daily=1`, `/api/notifications`; `POST /api/feedback`, `/api/notifications/preview`, `/api/webhooks/zalo`. Các POST từ UI giữ CSRF/Origin/Host và giới hạn body. API trạng thái không trả credential hoặc địa chỉ người nhận.

## Bằng chứng nghiệm thu và giới hạn

[Kết quả bản mẫu](case_management_20261018/verification.json), [outbox giả lập](case_management_20261018/notification_outbox.mock.json), [hàng đợi ưu tiên](case_management_20261018/daily_priority.mock.json). Bản mẫu có 1.146 hồ sơ còn mở; chọn 24 hồ sơ cho lịch xử lý ngày vì có giới hạn phút. Thông báo phân bổ 25 hồ sơ/5 công ty (5 mỗi công ty), tạo 50 job ưu tiên cao và 10 job tóm tắt tuần cho hai kênh: **60 job simulated, 0 tin gửi ra ngoài**. Đó là mô phỏng trên snapshot đã có; không phải 25 sự kiện mới hôm nay hay bằng chứng giảm tải trên SME thật.

Các kiểm thử HTTP/SQLite dùng thư mục tạm, có kiểm quota đồng thời, khởi động lại, lịch ngày/tuần, retry, chữ ký/replay, đích nhận, quyền CSRF và optimistic feedback. Node VM chạy thư viện Cytoscape thật ở headless và kiểm mô hình, lý do nhanh, reviewer bắt buộc, double-click, hash kết luận, thứ tự asset và điểm vào mobile. Những kiểm tra này không thay thế DOM/browser rendering.

**Chưa kiểm tra trực quan trong browser**: công cụ browser không có surface được kết nối, Computer Use báo native pipe unavailable sau quy trình thử lại/reset. **Chưa kiểm chứng gửi SMTP/Zalo thật**, đúng chế độ nghiệm thu người dùng đã chọn. Chưa bật scheduler/daemon, public hosting hoặc đăng nhập nhiều người dùng. Sprint hoàn tất tích hợp kỹ thuật ở chế độ giả lập; pilot thật cần kiểm UI trên browser mục tiêu, cấu hình người nhận/tài khoản và nghiệm thu dịch vụ qua staging.
