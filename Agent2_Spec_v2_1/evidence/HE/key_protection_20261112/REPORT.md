# CR-033 — Khóa và phiên tại DN, READY_FOR_REVIEW

Đã bổ sung **Windows DPAPI current-user** để bảo vệ khóa bọc kho phiên và khóa ký node. Kho job/checkpoint/kết quả AES-GCM từ CR-032 tiếp tục dùng cùng schema/HKDF/AAD. Node khởi động lại có thể dùng khóa được bảo vệ để nhận và giải mã kết quả cũ; retry giữ nguyên yêu cầu. [Hướng dẫn tạo/chuyển khóa/cấu hình/khôi phục](../../../../agent2/docs/HE_KEYS_AND_SESSIONS.md).

## Kiểm thử thực hiện trong lượt này

| Kiểm tra | Kết quả | Evidence |
|---|---|---|
| Toàn bộ HE/registry/services/jobs/keys | **131 pass**, không failure/error/skip, exit 0 | [JSON](he_tests.json), [log](he_tests.log), [execution](he_execution.json) |
| Ca mới về khóa, nằm trong 131 ca trên | **15 pass** | Các ID `test_key_manager.LocalKeyProtectionTests.*` trong JSON |
| Demo HTTP/restart với config 1.2.0/DPAPI | **16 checks pass**, 2 DN/10 giao dịch | [summary](restart_demo_final/summary.json), [trạng thái khôi phục](restart_demo_final/recovered-status.json), [kết quả](restart_demo_final/recovered-result.json) |
| Bảo toàn nghiệp vụ | **17/17 source hash không đổi** so CR-032 | [preservation](preservation.json) |

Native DPAPI roundtrip và process con mới dưới cùng Windows user đã chạy thật. Demo tạo khóa DPAPI trong thư mục DN tạm, hai process HTTP riêng, dừng worker/node rồi khôi phục và giải mã kết quả bằng phiên đã lưu; kiểm worker chỉ tính một lần và DB model/snapshot không đổi. `checkpoint_storage` trong summary mô tả lớp AES-GCM và file khóa bên ngoài DB; provider DPAPI/config strict được xác định bởi Pair trong [source provenance](source_provenance.json) và các ca khóa/service. Không chỉnh sửa output demo sau chạy.

Các ca khóa bao gồm distinct keys/no overwrite; đúng purpose/public key; sai ciphertext/key_id/provider; khóa thiếu; không fallback khi provider không có; từ chối raw hex trong chế độ strict; inspect process mới không in raw key; chuyển khóa giữ DB/idempotency; khóa sai không viết lại DB; node config strict chặn legacy signing key trước phục vụ.

Lượt focused đầu có 14 ca pass ([log](focused_keys.log)); ca strict config bổ sung sau đó được chạy trong bộ cuối 131 pass. `restart_demo` là lượt sơ bộ cũng pass; **he_tests.json và restart_demo_final là evidence cuối**. Bộ regression nghiệp vụ 742 pass ở [CR-032](../job_lifecycle_20261112/REPORT.md), **không chạy lại trong lượt này** vì không thay 17 source nghiệp vụ và thay đổi nằm ở phần HE opt-in được kiểm bằng bộ 131.

## Thay đổi và tương thích

- Thêm `key_manager.py`: CryptProtectData/CryptUnprotectData native, chế độ current-user, UI forbidden; không LOCAL_MACHINE. Envelope có version/provider/purpose/key_id; payload khóa nằm trong blob DPAPI. Publish atomic, không ghi đè; CLI create/protect/inspect chỉ in metadata/public verify key, không in private key.
- Config `he-enterprise-service/1.2.0` thêm `key_protection=windows-dpapi-current-user`, bắt buộc cả khóa state-wrapping và node-signing được bảo vệ. Config 1.0/1.1 giữ reader legacy để chuyển dần; file DPAPI hỏng không bị diễn giải lại thành raw hex.
- Bọc đúng 32 byte của khóa cũ giữ nguyên khóa HKDF/AES/HMAC và public Ed25519 key. Không rotation, không thay grant identity, không đổi DB format. Thử kho cũ → bọc khóa → mở lại → submit cùng key/body trả cùng job ID và đọc request cũ.
- Checkpoint HE vẫn lưu AES-GCM tại DN; không có thay đổi native HE circuit/model/33 feature hoặc worker bundle. Worker không nhận enterprise key files, checkpoint, token hoặc đường dẫn DB DN.
- Không tự sửa file khóa/config live. Công cụ protect không xóa nguồn hex; operator phải xác nhận backup/phục hồi và quản lý bản rõ cũ. Giữ file hex ở nơi không an toàn sẽ làm mất ý nghĩa bảo vệ bản mới.

## Điều kiện khôi phục và giới hạn

Giữ DB state, file khóa đúng và profile/tài khoản Windows có thể mở DPAPI, cùng checkpoint/TenSEAL/exporter tương thích và current owner auth. Job chưa xong chờ xác thực lại; không bearer token trên đĩa. Worker cache phải còn khi node chưa nhận kết quả. Không tự tạo khóa/nonce/model mới khi mất hoặc sai khóa.

DPAPI mặc định thông thường cần cùng logon/máy, có ngoại lệ roaming theo [Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata). Không bảo đảm chỉ copy file/DB là khôi phục sang máy/tài khoản mới được. **Chưa thử khác Windows user, reboot máy hoặc cross-machine restore**; ca unavailable dùng mô phỏng provider không có, không phải kiểm thử đăng nhập user thứ hai. Same-user malicious process có thể gọi DPAPI; đây không phải sandbox/KMS hoặc bảo vệ máy DN đã bị chiếm quyền. Native buffer được giải phóng, không khẳng định xóa sạch mọi Python bytes khỏi RAM.

Chưa Linux/macOS provider, KMS/HSM/rotation/anti-rollback/HA/DR tooling, chứng nhận bảo mật hoặc proof trước worker ác ý. Recovery không chống xóa/rollback DB, mất profile/key hoặc worker state. Loại checkpoint khỏi record terminal không phải secure erase page/backup. Worker response-signing key chưa chuyển sang DPAPI trong thay đổi này và không phải khóa HE.

Vẫn Mahalanobis hai feature thử nghiệm/loopback HTTP, dữ liệu mô phỏng; không IF/ECOD/LOF/AE HE, Portal HE UI, cloud public hoặc accuracy claim. Không đổi/restart Portal và Agent2 live, không gửi dữ liệu thật lên cloud; không commit/push. R0–R6/D-11/D-12 và gate sản phẩm giữ nguyên; chỉ READY_FOR_REVIEW cho phần được giao.

[Source/provenance](source_provenance.json), [kiểm tra tĩnh](validation.json), [manifest evidence](artifact_manifest.json).
