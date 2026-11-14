# CR-032 — Một lượt chấm HE có trạng thái/khôi phục, READY_FOR_REVIEW

Đã nối **gửi → theo dõi → nhận ciphertext → decrypt tại DN → lấy kết quả**, persistent idempotency và checkpoint/result mã hóa ở DN. Retry giữ nguyên job/context/nonce, không tạo lượt chấm thứ hai. [Hướng dẫn/API/CLI/cấu hình key](../../../../agent2/docs/HE_JOB_LIFECYCLE.md). Chưa UI Portal hoặc cloud public.

## Kiểm thử cuối

| Kiểm tra | Kết quả | Evidence |
|---|---|---|
| HE, registry, services, durable jobs | **116 pass**, 0 failure/error/skip, exit 0 | [JSON](he_tests_final.json), [log](he_tests_final.log), [execution](he_execution_final.json) |
| Regression Agent2 hiện có | **742 pass**, 0 failure/error/skip, exit 0 | [JSON](native_tests.json), [log](native_tests.log), [execution](native_execution.json) |
| Focused persistent jobs | 23 pass, exit 0 | [log](focused_jobs_final.log), [execution](focused_execution_final.json) |
| Demo trọn luồng HTTP/restart | **16 checks pass** | [summary](lifecycle_demo_final/summary.json), [execution](demo_execution.json) |
| Luồng hai services cũ/parity | 16 compatibility checks pass | [summary](compat_demo_fixed/summary.json) |

[C001 trạng thái](lifecycle_demo_final/C001-status.json), [kết quả](lifecycle_demo_final/C001-result.json); [C002 trạng thái](lifecycle_demo_final/C002-status.json), [kết quả](lifecycle_demo_final/C002-result.json). Mỗi DN có đủ 5 giao dịch và các điểm decrypted. [Trạng thái khôi phục](lifecycle_demo_final/recovered-status.json), [kết quả sau restart](lifecycle_demo_final/recovered-result.json). Nguồn chỉ mô phỏng, không accuracy claim.

## Hành vi được hoàn thiện

- Node API POST /he/jobs trả job_id/status/result URL; GET status có phase/message/history, GET result chỉ trả kết quả đúng quyền sau decrypt; POST resume hoặc submit cùng key sau restart tiếp tục đúng job. Cùng key/body/owner, kể cả submit đồng thời hoặc node restart, không nhân bản; đổi body conflict.
- Node có DB state riêng: request/HE checkpoint/receipt/result dùng AES-256-GCM, HKDF tách khóa encryption/HMAC. Wrapping key 32 byte do operator cấp qua file ngoài DB, không tự tạo/ghi đè khi thiếu/sai. AAD ràng buộc job/tenant/DN/actor/idem/request/phase/generation/timestamps; mỗi update nonce mới. Metadata scope/phase/ID còn nhìn thấy ở DN. Worker không nhận key file hoặc DB này.
- Ghi checkpoint **trước network**, đánh dấu có thể đã gửi **trước evaluate**, ghi response ciphertext **trước decrypt**, commit completed/result và bỏ checkpoint hiện hành cùng transaction. Khôi phục dùng strict JSON/private TenSEAL context đã wrap, không pickle model/callback hoặc lưu token. Không fit/đọc model/tạo context mới khi checkpoint đã tồn tại.
- Node restart pause job chưa xong để owner xác thực lại. Không lưu bearer credential trên đĩa; quyền hiện tại kiểm ở submit/status/result/resume và trước HE decrypt. Completed results encrypted-at-rest lấy lại được sau node restart. Exclusive OS lock ngăn hai node cùng mở state.
- Worker thêm POST /v1/results: retrieval mới được node có grant ký (TTL 60 giây) chỉ đọc ciphertext đúng scope/session/nonce/request hash đã tồn tại. Có thể lấy kết quả cũ sau TTL inference, nhưng evaluate hết hạn vẫn từ chối; không tái compute hoặc tạo nonce khác. Grant/key owner kiểm lại, không có endpoint giải mã.
- Retry transport exponential backoff 2/4/8/16/30 giây, cùng packet. Khi request chưa gửi đã hết hạn thì expired; nếu có thể đã gửi thì chờ worker trở lại để lấy cache. Worker bị gián đoạn trước commit/không còn state được báo rõ, không giả phục hồi bằng chạy lại plaintext.
- CLI job_client lưu receipt atomic trước POST; mất response đầu vẫn có key để POST lại cùng intent. Receipt không token/private key; output không ghi đè kết quả khác. Giữ cùng receipt/key khi chạy lại. Đây là API/CLI, chưa nút theo dõi trên Portal.

## Các ca khôi phục quan trọng đã qua

1. Bốn lần submit đồng thời cùng key trả một job và một worker computation.
2. Mất reply submit: client dùng receipt/key cũ, hoàn tất một lượt.
3. Worker mất kết nối rồi node/worker restart: job giữ ID; owner xác thực lại; HE key đã wrap decrypt được; chỉ một worker job.
4. Worker đã tính xong nhưng reply bị mất, sau đó node restart: resume lấy ciphertext cũ bằng key đã lưu; spy cấm export/context mới không bị gọi, worker job count tăng đúng một.
5. Node dừng sau commit received trước decrypt: restart decrypt checkpoint mà spy cấm toàn bộ network vẫn pass.
6. Completed result sau restart và client chạy lại cùng receipt giữ nguyên nội dung/run_id, không compute thêm.
7. Request inference hết TTL không evaluate lại; retrieval ký mới lấy đúng ciphertext cũ, sai hash hoặc key không được cấp bị chặn.
8. Sai wrapping key không sửa jobs; thiếu key không tự tạo DB/key; copy ciphertext giữa jobs/scope hoặc sửa phase/blob fail closed; nonce cập nhật không lặp; actor/DN/tenant khác không đọc job; quyền revoked chặn cached result.

23 case mới (12 storage + 11 flow/recovery) cùng 93 case trước đều qua. Model/snapshot/catalog/kernel/33 feature live không thay: [17 core hashes giữ nguyên](preservation.json). Demo/test processes tự dừng, không deploy/khởi động lại Portal/Agent2 live.

## Giới hạn

Mahalanobis hai feature thử nghiệm từ contract 33, không bốn nhánh HE/IF/ECOD/LOF/AE hoặc cloud training. Loopback-only; chưa UI Portal, TLS/mTLS/cloud public, KMS/HSM/key rotation, OS/native sandbox, proof worker ác ý hoặc production/full R2/R5 gate.

Recovery cần giữ nguyên DB/key và build/checkpoint/TenSEAL/exporter tương thích, quyền owner hiện tại và worker ciphertext cache khi còn cần. Không bảo đảm chống rollback backup, mất/xóa state/key, giải mã lại dữ liệu không tồn tại hoặc sửa identity worker. Key loại khỏi record hiện hành sau terminal không phải secure erase page/backup. Khóa wrapping là file private ở DN (chưa KMS); không đóng gói/push lên worker hoặc Git. DB giới hạn 512 job/8 active, 2 processors; chưa retention/purge/cancel/HA; backoff giữ checkpoint khi kết quả worker còn chưa rõ.

Lịch sử chẩn đoán được giữ: compat_demo đầu thiếu import secrets (đã sửa); focused_jobs đầu thiếu import helper test (đã sửa); he_tests intermediate 115 ca có fixture ngoại lệ signature không khớp kỳ vọng. **he_tests_final 116 pass + lifecycle_demo_final 16 pass** là bằng chứng cuối, không lấy lượt lỗi làm PASS.

[Source/provenance](source_provenance.json), [manifest evidence](artifact_manifest.json). Chỉ READY_FOR_REVIEW cho phần được giao, không tự ký DONE hoặc nghiệm thu nghiệp vụ/accuracy/production.
