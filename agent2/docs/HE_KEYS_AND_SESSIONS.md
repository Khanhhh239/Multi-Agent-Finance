# Khóa và phiên HE lưu tại doanh nghiệp — CR-033

**CR-034:** đã có [màn hình chọn doanh nghiệp/dữ liệu và chạy phân tích](HE_WEB_ANALYSIS.md), dùng phiên Portal khi backend DN bật HE. Những mô tả chưa Portal dưới đây thuộc mốc CR-033; khóa vẫn không đưa ra browser/worker.

Node doanh nghiệp có thể dừng rồi chạy lại và tiếp tục nhận/giải mã kết quả bằng **phiên đã lưu**, thay vì mất khóa trong RAM. Kho phiên từ CR-032 dùng AES-256-GCM; CR-033 bổ sung **Windows DPAPI theo tài khoản đang chạy node** để bảo vệ cả khóa bọc kho phiên và khóa ký cấp quyền cho worker. Worker không nhận hai khóa này hoặc khóa giải mã HE.

Đây là phần API/CLI Mahalanobis thử nghiệm trên Windows. Chưa tích hợp thao tác HE vào Portal hoặc triển khai cloud public. [Báo cáo kiểm thử](../../Agent2_Spec_v2_1/evidence/HE/key_protection_20261112/REPORT.md).

## Những gì cần giữ tại doanh nghiệp

| Thành phần | Cách lưu và vai trò |
|---|---|
| Khóa giải mã HE của từng phiên | Trong checkpoint JSON của job, được mã hóa AES-256-GCM trong `state_dir/jobs.sqlite3`; chỉ mở tại node DN khi cần tiếp tục/giải mã |
| Khóa bọc kho phiên | 32 byte ngẫu nhiên, được DPAPI bọc vào `state-wrapping.dpapi.json`; HKDF tách khóa AES và HMAC idempotency, giữ tương thích DB cũ |
| Khóa ký node | Khóa Ed25519, được DPAPI bọc riêng với mục đích `node-signing`; worker chỉ được cấp public verify key trong grant |
| Kết quả đã hoàn tất | Mã hóa trong DB kho phiên tại DN; chỉ trả dữ liệu rõ sau kiểm tra quyền hiện tại |
| Phiếu theo dõi CLI | ID/key của yêu cầu, không bearer token, model hoặc khóa bí mật; dùng lại để retry |
| Danh tính Windows và profile | DPAPI cần ngữ cảnh người dùng phù hợp để mở khóa; sao chép riêng file khóa/DB sang tài khoản mới không đủ để bảo đảm phục hồi |

Khóa response-signing riêng của worker chỉ ký phản hồi, không giải mã HE; việc bảo vệ khóa đó không thuộc thay đổi này. Không đưa DB phiên DN, file khóa hoặc profile vào worker bundle, static web, Git hay báo cáo. Thư mục riêng của DN vẫn cần quyền filesystem phù hợp; DPAPI không thay thế quản trị quyền file.

## Tạo khóa cho node mới, chưa có kho phiên

Chạy dưới **đúng tài khoản Windows sẽ chạy node**, tại `D:/agent22/agent2`:

```powershell
& .venv/Scripts/python.exe -X utf8 -B -m experiments.he_inference.key_manager create --purpose state-wrapping --output .runtime/he-node/state-wrapping.dpapi.json
& .venv/Scripts/python.exe -X utf8 -B -m experiments.he_inference.key_manager create --purpose node-signing --output .runtime/he-node/provisioning.dpapi.json
& .venv/Scripts/python.exe -X utf8 -B -m experiments.he_inference.key_manager inspect --purpose node-signing --input .runtime/he-node/provisioning.dpapi.json
```

CLI chỉ in provider, purpose, key_id và trạng thái sử dụng; với khóa ký có thêm **public verify_key** để cấu hình grant worker. Không in khóa bí mật. Tệp đầu ra được ghi atomic, không ghi đè file đã tồn tại. Khóa mới độc lập, không dùng password/token hoặc khóa của worker.

**Nếu đã có DB phiên thì không tạo khóa bọc mới thay khóa cũ.** Dùng chuyển định dạng dưới đây để giữ nguyên giá trị khóa.

## Chuyển khóa hex cũ sang DPAPI, giữ phiên cũ

1. Dừng node DN theo quy trình vận hành để kho phiên nhất quán. Giữ bản sao lưu được quản lý an toàn của DB/khóa cũ và khả năng phục hồi profile Windows; không lưu khóa rõ vào thư mục chia sẻ/Git. Không sửa snapshot/model/worker DB.
2. Dưới tài khoản chạy node, bọc **đúng hai khóa cũ** sang file mới. Thay đường dẫn mẫu bằng đường dẫn thật:

```powershell
& .venv/Scripts/python.exe -X utf8 -B -m experiments.he_inference.key_manager protect --purpose state-wrapping --input '<khoa-state-cu.hex>' --output '<khoa-state-moi.dpapi.json>'
& .venv/Scripts/python.exe -X utf8 -B -m experiments.he_inference.key_manager protect --purpose node-signing --input '<khoa-ky-cu.hex>' --output '<khoa-ky-moi.dpapi.json>'
```

3. Dùng `inspect` trên nguồn/đích cùng purpose để đối chiếu `key_id`; với khóa ký kiểm thêm `verify_key`. Phải giữ nguyên hai giá trị tương ứng. Đây là bọc lại khóa, **không xoay khóa**; public grant và phiên cũ tiếp tục khớp.
4. Đổi cấu hình node sang 1.2.0 và hai đường dẫn DPAPI; giữ nguyên `state_dir`, model/snapshot DB, auth policy và identity worker. Khởi động lại cùng tài khoản Windows, xác thực owner rồi lấy một kết quả cũ/resume bằng phiếu cũ. Idempotency vẫn trả cùng job ID.
5. Công cụ không tự xóa file hex nguồn. Sau khi xác nhận phục hồi và backup đúng quy trình, người vận hành cần thu hồi các bản khóa rõ còn lưu và kiểm soát backup. **Nếu file hex vẫn bị lộ thì DPAPI ở bản mới không loại bỏ rủi ro đó.** Không khẳng định xóa an toàn các bản sao/page/backup.

Không chuyển khóa live tự động trong cập nhật mã này. Kiểm thử chuyển định dạng sử dụng kho mô phỏng riêng, xác nhận DB cũ và key idempotency còn đọc được. Rotation, chuyển máy/tài khoản và khôi phục thảm họa cần quy trình riêng, chưa có lệnh tự động.

## Cấu hình bắt buộc bảo vệ khóa

```json
{
  "version": "he-enterprise-service/1.2.0",
  "key_protection": "windows-dpapi-current-user",
  "auth_file": "<auth-policy-DN.json>",
  "model_db": "<models.sqlite3-cua-DN>",
  "snapshot_db": "<snapshots.sqlite3-cua-DN>",
  "worker_url": "http://127.0.0.1:8868",
  "worker_verify_key": "<public-response-key-64-hex>",
  "provisioning_key_file": "<private-node-provisioning.dpapi.json>",
  "state_dir": "<thu-muc-state-rieng-tai-DN>",
  "state_key_file": "<private-node-state-wrapping.dpapi.json>"
}
```

Các `<...>` là placeholder, không phải cấu hình chạy ngay. Bật node bằng lệnh/cấu hình tại [HE_TWO_SERVICES.md](HE_TWO_SERVICES.md); theo dõi job/retry tại [HE_JOB_LIFECYCLE.md](HE_JOB_LIFECYCLE.md). Cấu hình 1.2.0 từ chối file hex cho **cả hai** khóa, không tự hạ xuống plaintext. Config 1.0/1.1 vẫn đọc được khóa cũ cho tương thích và chuyển định dạng; chúng không bắt buộc DPAPI.

Loader kiểm version/provider/purpose/key_id, khóa thiếu/sai/hỏng hoặc DPAPI không mở được thì dừng. Không tự sinh khóa khác, không thay DB hỏng hoặc chạy lại bằng phiên mới để che lỗi. Sai khóa bọc phải bị phát hiện trước khi thay đổi bản ghi job.

## Khi node khởi động lại

- Giữ DB phiên, hai file khóa được bảo vệ, Windows profile và build/checkpoint tương thích. Không chạy hai node trên cùng thư mục state.
- Job chưa xong chuyển chờ xác thực. Owner dùng credential hiện tại để resume hoặc submit lại cùng key/body; không có bearer token lưu trên đĩa.
- Node dùng lại HE context và nonce đã lưu. Nếu worker đã có ciphertext, node lấy ciphertext cũ rồi giải mã; không fit/export/tạo yêu cầu chấm mới.
- Kết quả completed được đọc lại từ kho mã hóa tại DN sau kiểm quyền. Khóa HE riêng bị bỏ khỏi record hiện hành khi terminal, nhưng khóa bọc vẫn cần giữ để mở kết quả cũ.
- Mất DB/khóa/profile hoặc worker cache đã bị xóa không nằm trong bảo đảm phục hồi. Không chọn `create` để chữa lỗi mất khóa.

## Phạm vi bảo vệ và kiểm thử

DPAPI dùng chế độ **current-user**, UI forbidden; không bật `CRYPTPROTECT_LOCAL_MACHINE`. Theo [Microsoft CryptProtectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata), thông thường cần cùng thông tin đăng nhập và cùng máy để mở; roaming profile có ngoại lệ. Service cần chạy dưới đúng tài khoản và profile có thể sử dụng. [CryptUnprotectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptunprotectdata) là API mở tại DN. Không có fallback DPAPI cho Linux/macOS trong bản này.

Một process độc hại có cùng quyền Windows vẫn có thể gọi DPAPI và đọc dữ liệu khi node đang xử lý. Hai process demo cùng user chỉ chứng minh tách package/quy trình, chưa phải cách ly OS hoặc bảo vệ trước máy DN bị chiếm quyền. Chưa KMS/HSM, xoay khóa, chống rollback, HA, chứng nhận bảo mật hoặc proof trước worker ác ý.

Đã thử native DPAPI roundtrip và process mới dưới cùng user; sửa blob/key_id/purpose/provider bị chặn; khóa sai không viết lại DB; chuyển hex giữ phiên/idempotency; config strict chặn khóa rõ. Demo HTTP thử worker/node restart và nhận/giải mã lại bằng phiên đã lưu. **Chưa thử đăng nhập tài khoản Windows khác, reboot máy hoặc phục hồi sang máy mới.** Các giới hạn tài khoản/máy dựa trên semantics DPAPI, không phải kết quả kiểm thử các môi trường đó.

Demo hiện dùng config 1.2.0/DPAPI và cần Windows:

```powershell
& .venv/Scripts/python.exe -X utf8 -B -m experiments.he_inference.jobs_demo --output-dir '<thu-muc-moi-trong>'
& .venv/Scripts/python.exe -X utf8 -B scripts/run_he_tests.py --report '<he-tests-moi.json>'
```

Tất cả dùng dữ liệu mô phỏng/thư mục tạm; không đổi Portal/DB/model live. Điểm Mahalanobis không phải xác suất gian lận; thay đổi này không mở rộng bốn nhánh HE hoặc chứng minh hiệu quả nghiệp vụ của ML.
