# Kiểm tra dữ liệu đầu vào tại backend

Đã có API kiểm tra theo quyền doanh nghiệp. Endpoint `/imports/validate` **chỉ kiểm tra**, không lưu dữ liệu, tạo snapshot hay chạy ML. Luồng lưu mới được triển khai riêng theo [hướng dẫn snapshot bất biến](IMMUTABLE_SNAPSHOTS.md). Input contract 1.0.0; validator/report 1.1.0. Hướng dẫn cấu trúc nguồn: [INPUT_DATA_CONTRACT.md](INPUT_DATA_CONTRACT.md).

## API

`POST http://127.0.0.1:8766/api/v1/companies/C001/imports/validate`

- `Authorization: Bearer <credential do backend/identity service cấp>`
- `Content-Type: application/json`
- Body là bundle theo hợp đồng, chỉ chứa C001 trong ví dụ này. Một DN cho mỗi yêu cầu; tenant lấy từ credential phía backend, không lấy từ vai trò client tự gửi.
- Giới hạn 10 MB, 50.000 bản ghi toàn gói; JSON UTF-8, không nén, không khóa lặp hay NaN/Infinity. Endpoint này chưa đọc file CSV/Excel trực tiếp. Adapter file sau này phải chuyển sang hợp đồng chung và giữ mapping dòng gốc.

Backend kiểm Host/Origin, credential, hạn dùng, membership active, permission data.import đúng DN **trước đọc body**. Có role director không tự có quyền DN khác hoặc tự được cấp data.import. Chính sách thu hồi được đọc lại mỗi request. Dữ liệu chứa một DN khác trong bundle vẫn bị chặn, kể cả credential có quyền cả hai DN nhưng URL chỉ chọn một DN.

| HTTP | Ý nghĩa |
|---|---|
| 200 | accepted hoặc accepted_with_warnings; dữ liệu chưa được lưu |
| 400 | JSON/header/cấu trúc truyền sai, body rỗng hoặc không đầy đủ |
| 401 | Thiếu/sai credential, credential bị thu hồi hoặc hết hạn |
| 403 | Không có membership/quyền đúng DN, bundle chứa tenant/DN ngoài phạm vi, Host/Origin không cho phép |
| 408 | Truyền dữ liệu quá thời gian chờ |
| 413 | Vượt giới hạn kích thước/số bản ghi |
| 415 | Sai Content-Type hoặc gửi body nén |
| 422 | Thiếu trường/cột, sai kiểu, mã và revision trùng, tham chiếu hoặc dữ liệu nghiệp vụ sai hợp đồng |
| 503 | Auth policy backend bị thiếu/hỏng; đóng quyền, không đọc dữ liệu |

Không trả lại nội dung giao dịch, credential hay ID DN khác trong lỗi bị từ chối. Chưa có API commit/snapshot; report kiểm tra không phải token được phép lưu.

## Ví dụ lỗi có dòng, trường và cách sửa

```json
{
  "code": "REQUIRED_FIELD",
  "path": "/transactions/11/record_id",
  "table": "transactions",
  "row": 12,
  "field": "record_id",
  "message": "Thiếu mã giao dịch.",
  "action": "Bổ sung mã giao dịch từ nguồn rồi gửi lại; không tự điền giá trị giả."
}
```

`row` đếm từ 1 trong bảng JSON, không tính header. Khi nối CSV/Excel, adapter phải dẫn về đúng dòng/sheet của tệp gốc, không tự cộng 1 nếu có hàng tiêu đề/mapping khác. Lỗi cấp gói không có dòng thì row/field là null; path vẫn chỉ ra bảng hoặc phần dữ liệu.

Mã nghiệp vụ gợi ý: REQUIRED_FIELD, UNKNOWN_FIELD, SCHEMA, DUPLICATE_REVISION, REFERENCE_MISSING, ADJUSTMENT_CONTEXT. Khóa duy nhất có cả DN và revision: hai bản sao cùng revision bị từ chối; sửa thông tin hợp lệ tạo revision mới. Hai khoản thanh toán khác ID cùng hóa đơn/trả vượt vẫn được nhận để phân tích, không coi là lỗi nhập. Giữ số âm điều chỉnh có loại/lý do/bản gốc.

## Thiếu lịch sử và chứng từ

`warnings` giải thích giới hạn; `analysis_limits[company_id]` chỉ rõ phân tích bị hạn chế, cách bổ sung, số giao dịch bị ảnh hưởng và danh sách tham chiếu dòng/ID/revision. Danh sách mẫu tối đa 20 dòng; nếu còn nhiều có affected_rows_truncated=true và affected_count vẫn là tổng đầy đủ. Không bỏ dòng dữ liệu.

| Giới hạn | Ý nghĩa và cách xử lý |
|---|---|
| BANK_HISTORY_MISSING | Chưa có bank history cho đúng NCC/revision của các giao dịch liên quan. Bổ sung lịch sử có thời điểm hiệu lực/được biết; tài khoản hiện tại không thay lịch sử. |
| DOCUMENT_BASIS_MISSING | Chưa có chứng từ gốc đã xác minh gắn đúng giao dịch hoặc hóa đơn qua allocation. Bổ sung/đối chiếu nguồn. Một tệp của T001 không làm T002 hết thiếu căn cứ. |
| INVOICE_LINK_MISSING | Khoản payment chưa có allocation hóa đơn, chưa đối chiếu được nghĩa vụ cho khoản đó. Không tự ghép theo số tiền gần giống. |
| APPROVAL_BASIS_MISSING | Chưa có nguồn approved tương ứng khoản chi/lương. Bổ sung dấu vết; không tự kết luận chưa được duyệt hay có sai phạm. |

Coverage tính theo revision mới nhất trong **bundle được gửi**, chưa là chứng nhận đủ hồ sơ nghiệp vụ hay khả năng chấm ở một as_of. Chứng từ verified cũ không lấn revision unverified mới. Bản mô phỏng/bản xuất không tự thành bản gốc, original chưa verified vẫn thiếu căn cứ xác minh. Nguồn đến muộn vẫn giữ cảnh báo thời gian; feature replay theo as_of làm ở bước sau.

Capability records_present chỉ nói có nguồn, không chứng minh model đủ lịch sử/đã fit. Chưa chọn min-history, trọng số hay đánh giá accuracy ở bước này.

## Cấu hình quyền cho thử local

Backend hiện dùng adapter policy file tin cậy, **không có màn đăng nhập mới**. Portal vừa pull có cổng mở khóa chung nhưng chưa cung cấp identity + membership theo DN cho Agent2. Không coi phiên mở khóa Portal hoặc company_id do browser gửi là bằng chứng quyền. Identity/bridge chung phải được nối sau; file bên dưới chỉ là adapter vận hành local cho fixture, không phải account store sản xuất.

Khởi động bằng môi trường Agent2:

```powershell
cd D:\agent22\agent2
& .venv/Scripts/python.exe -m pip install -r requirements-lock.txt
& .venv/Scripts/python.exe -B start_review.py --port 8766 --auth-file .runtime/validation-auth.json
```

Cũng có thể đặt biến `AGENT2_AUTH_FILE` phía process server. Không cấu hình credential mặc định. File bị thiếu/sai cấu trúc đóng quyền; không tự cấp quyền QA. Policy có dạng:

```json
{
  "policy_version": "1.0.0",
  "principals": [{
    "actor_id": "local-validator",
    "tenant_id": "demo",
    "token_sha256": "<SHA256 lowercase 64 ký tự của credential ngẫu nhiên>",
    "status": "active",
    "expires_at": "<thời điểm hết hạn ISO 8601 có offset>",
    "memberships": [{
      "company_id": "C001",
      "role": "accountant",
      "status": "active",
      "permissions": ["data.import"]
    }]
  }]
}
```

Các giá trị `<...>` là chỗ điền, không phải file chạy được hay credential mặc định. Identity service/người vận hành cấp credential ngẫu nhiên đủ mạnh, chỉ lưu hash trong policy. Role accountant/director; membership active/suspended/revoked; principal active/revoked. Quyền evidence.verify phải được cấp rõ nếu import thông tin đã xác minh và vẫn cần verification đủ căn cứ/thời điểm. Không đưa credential/policy runtime vào Git; `.runtime/` đã bị ignore.

Chạy kiểm thử đầy đủ phần này mà không cần tự tạo credential hoặc sửa dữ liệu đang dùng:

```powershell
cd D:\agent22\agent2
$env:PYTHONPATH='.;tests'
& .venv/Scripts/python.exe -X utf8 -u -B -m unittest test_input_contract test_validation_backend test_transition_server -v
```

Tests tự tạo credential/policy và server cổng tạm trong TemporaryDirectory, kiểm cả HTTP thực, không đọc/ghi công ty thật. Các API nhập/commit/hồ sơ cũ vẫn trả 410. Pipeline_ready/active_delivery vẫn false.
