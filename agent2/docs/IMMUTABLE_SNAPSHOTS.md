# Nhập tệp và tạo snapshot bất biến

CR-023: sau commit, có thể gọi [API phân tích snapshot P1/E3](SNAPSHOT_ANALYSIS_API.md). Chỉ đọc nguồn/checksum đã lưu, không tạo snapshot/job mới hoặc tự fit. Backend hiện đọc input 1.0.0/1.1.0 theo phiên bản payload; phần CR-007 bên dưới giữ lịch sử triển khai, không tự nâng snapshot cũ.

Luồng backend đã có: **Tải tệp → Xem kết quả kiểm tra → Xác nhận lưu → Tạo snapshot**. Giai đoạn này nhận **tệp JSON theo hợp đồng 1.0.0** và mapping đổi tên cột. Job feature được nối theo CR-008; màn hình Portal/CSV/Excel vẫn làm sau, không phục hồi luồng nhập Agent2 cũ.

**CR-008:** đã nối [job feature theo thời điểm](SNAPSHOT_FEATURES.md) từ snapshot. Các mô tả “feature replay chưa có” bên dưới là phạm vi khi bàn giao CR-007; job mới không đổi tính bất biến hoặc tự kích hoạt model/hàng đợi.

## Chạy demo không cần tự cấu hình credential

```powershell
cd D:\agent22\agent2
& .venv/Scripts/python.exe -X utf8 -B scripts/demo_snapshot_flow.py
```

Demo dùng dữ liệu mô phỏng C001 từ fixture của repo, khởi động HTTP backend ở cổng tạm, tải tệp, preview, xác nhận và gửi lại 10 lần. Snapshot được giữ trong `.runtime/snapshot_demo/snapshots.sqlite3`, tách kho vận hành. Credential/policy thử được tạo trong thư mục tạm và dọn sau demo, không in credential. Chạy demo lại có import mới, nhưng cùng dữ liệu/source/mapping/phiên kiểm tra được dùng lại snapshot, không tăng số bản dữ liệu. Nếu bộ kiểm tra thay phiên thì snapshot mới có provenance riêng.

## Khởi động API để tích hợp

```powershell
cd D:\agent22\agent2
& .venv/Scripts/python.exe -B start_review.py --port 8766 `
  --auth-file .runtime/validation-auth.json `
  --snapshot-db .runtime/imports/snapshots.sqlite3
```

Auth policy và quyền data.import theo [hướng dẫn backend](BACKEND_VALIDATION.md). Có thể dùng biến `AGENT2_SNAPSHOT_DB`. Không dùng DB review cũ; backend từ chối DB không đúng application_id/schema version. Không có auth bypass hay credential mặc định. Portal chưa cấp identity/membership cho luồng này.

## Các bước qua API

Mọi route bắt đầu bằng `/api/v1/companies/C001`, cần Bearer credential được backend cấp đúng DN. Tenant/role do backend xác định; gửi company_id hay report trong body không tạo quyền. Backend kiểm trước đọc body và kiểm lại trong transaction, kể cả sau khi chờ writer khác và trước khi hoàn tất.

| Bước | Route/phương thức | Nội dung |
|---|---|---|
| 1. Tải tệp | POST /imports/upload | Body là byte nguyên tệp .json; Content-Type application/json hoặc application/octet-stream; X-File-Name và Idempotency-Key. Trả import_id, revision=1, source_hash, mapping_hash. Chưa coi dữ liệu là hợp lệ. |
| 2. Xem kiểm tra | POST /imports/{import_id}/preview | JSON `{"expected_revision":1}`. Trả preview_id, lỗi/cảnh báo/giới hạn nguồn, checksums, context_hash, report_hash và expires_at. |
| 3. Xác nhận lưu | POST /imports/{import_id}/commit | Gửi đúng các trường dưới đây, acknowledge=true và Idempotency-Key. Còn lỗi, hết hạn hoặc không khớp revision/hash thì từ chối. |
| 4. Xem snapshot | GET /snapshots/{snapshot_id} | Manifest gồm ID, checksum, phiên bản hợp đồng và nguồn. |
| Tải dữ liệu đã khóa | GET /snapshots/{snapshot_id}/data | Byte JSON canonical chính xác; SHA256 body bằng data_checksum. |
| Xem trạng thái nhập | GET /imports/{import_id} | Revision/trạng thái hiện hành và snapshot_id nếu đã lưu. |
| Xem report hiện hành | GET /imports/{import_id}/report | Report bất biến đã lưu; nếu source/mapping đã đổi thì yêu cầu preview lại. |

Body commit, lấy nguyên từ preview server:

```json
{
  "expected_revision": 1,
  "preview_id": "prv_<32 ký tự hex từ server>",
  "source_hash": "<SHA256 tệp>",
  "mapping_hash": "<SHA256 mapping chuẩn hóa>",
  "report_hash": "<SHA256 report đã khóa>",
  "context_hash": "<SHA256 phiên kiểm tra/quyền>",
  "acknowledge": true
}
```

Đây là cấu trúc minh họa; giá trị `<...>` phải lấy từ server. Không nhận báo cáo accepted do client tự gửi. Report accepted_with_warnings vẫn có thể xác nhận; người thao tác phải xem phần giới hạn nguồn. Báo lỗi HTTP: upload 201; preview 200 hoặc 422 nếu dữ liệu lỗi (403 nếu dữ liệu ngoài quyền); commit/read thành công 200; conflict/stale/expired 409; xác nhận thiếu/sai 400. Auth 401/403, DB chưa cấu hình hoặc lỗi tạm thời 503. Không thông báo lưu thành công khi transaction chưa commit.

## Nếu đổi tệp hoặc mapping

- **Đổi tệp:** PUT `/imports/{import_id}/source`, body byte tệp JSON mới; header X-File-Name, X-Expected-Revision và Idempotency-Key.
- **Đổi mapping:** PUT `/imports/{import_id}/mapping`, JSON `{"expected_revision":1,"mapping":{"tables":{"transactions":{"Số tiền":"amount_vnd"}}}}`, kèm Idempotency-Key.

Thay đổi tạo revision mới, giữ bản gốc/report cũ và bỏ active preview. Phải preview revision mới rồi xác nhận bằng các hash mới. Gửi source/mapping khác với một Idempotency-Key cũ bị conflict; không tự ghi đè. Mapping chuẩn hóa cùng nghĩa/không đổi source không tạo revision vô ích. Sau khi import đã committed, sửa nguồn phải tạo import mới.

Mapping chỉ đổi tên cột ở mỗi record của bảng. Không đổi giá trị, không nhận code/biểu thức, không tự tạo mã DN hoặc thời điểm nguồn. Hai cột cùng đích bị báo lỗi, không âm thầm ghi đè. Tệp vẫn cần đủ bảng/nguồn tham chiếu theo hợp đồng; đây chưa phải bộ nhập tăng dần ghép dữ liệu cũ. Dữ liệu thiếu lịch sử/chứng từ giữ cảnh báo/capability và giới hạn theo giao dịch.

## Điều gì được khóa

- `source_hash`: SHA256 byte nguyên tệp tải lên; khác khoảng trắng/encoding cũng là nguồn khác.
- `mapping_hash`: SHA256 JSON mapping đã chuẩn hóa; thứ tự khóa không làm đổi nghĩa.
- `data_checksum`: SHA256 byte JSON canonical của dataset sau mapping, UTF-8, sort key, không khoảng trắng thừa, giữ thứ tự dòng và số nguyên chính xác. Giữ dấu điều chỉnh và observed_at, không tự thay bằng giờ upload.
- `context_hash`: khóa tenant/DN/actor/quyền, schema SHA256, parser/validator/profile/report versions và fingerprint code liên quan. Đổi quyền/bộ kiểm tra phải preview lại.
- `report_hash`: khóa toàn report cùng source/mapping/revision/context và thời hạn. Preview mặc định có hiệu lực 15 phút; preview lại sau khi hết hạn tạo report mới.
- `checksum` snapshot: SHA256 JSON canonical `{"manifest": <manifest không có checksum>, "data_checksum": <data_checksum>}`. Manifest chứa snapshot_id, contract_version, nguồn/mapping, provenance kiểm tra, người và thời điểm tạo. Đọc snapshot kiểm lại cả data_checksum và checksum manifest.

Tệp/report/revision/snapshot/audit/receipt là append-only, có trigger chặn UPDATE/DELETE. API snapshot chỉ đọc. Bản mới không sửa bản cũ. Checksum dùng kiểm tra toàn vẹn, không phải chữ ký số hoặc bằng chứng chứng từ là thật; không thay kết luận nghiệp vụ.

## Retry, đồng thời và mất phản hồi

Giữ nguyên Idempotency-Key và body khi mất mạng hoặc hết thời gian chờ. Các khóa được phân theo tenant/DN/actor/thao tác. Dùng UUID/chuỗi ngẫu nhiên cho một yêu cầu mới; không tạo khóa mới chỉ vì chưa nhận phản hồi.

Upload, đổi source/mapping và commit lưu receipt cùng transaction. Retry không tạo thêm draft/revision/snapshot tương ứng. Với cùng import đã committed, cùng xác nhận nhưng khóa retry khác vẫn trả snapshot cũ. Hai import có cùng nguồn, mapping, dữ liệu canonical và phiên kiểm tra trong cùng DN dùng lại snapshot; provenance lần đầu được giữ, từng import/receipt/audit vẫn truy được.

Commit kiểm và tạo snapshot/cập nhật trạng thái/receipt/audit trong một transaction SQLite BEGIN IMMEDIATE, synchronous=FULL, foreign_keys=ON. Mất tiến trình/lỗi giữa các bước rollback; retry sau khi server đã commit nhưng mất phản hồi trả đúng snapshot trước đó, kể cả preview cũ đã hết hạn. Quyền hiện tại vẫn phải hợp lệ. Source/mapping đang đua với commit chỉ có một bên thắng; bên còn lại nhận conflict và không ghi đè.

Report và draft chỉ thuộc actor + tenant + DN. Snapshot đã committed có thể được đọc bởi actor có quyền data.import trong cùng tenant/DN; không cho truy cập DN khác bằng cách đoán mã snapshot. Không trả raw source trước kiểm tra; tệp chưa hợp lệ nằm trong staging riêng, không thành dataset snapshot.

## Phạm vi còn lại

Chưa có màn hình dùng Portal login, CSV/Excel/multipart, feature replay theo as_of/nhóm đồng thời, model hay hàng đợi. Snapshot là artifact đầu vào có thể tái hiện, không tự là model đã fit hoặc kết quả phân tích. Các API Agent2 cũ vẫn đóng và pipeline_ready/active_delivery vẫn false. DB/source local chỉ dùng fixture ở giai đoạn này theo các decision chưa chốt cho dữ liệu thật.
