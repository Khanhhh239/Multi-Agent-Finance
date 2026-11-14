# CR-040 — Khôi phục worker chết giữa phép tính, READY_FOR_REVIEW

**Đã sửa HE-AC-01 trong phạm vi managed request còn hạn và state còn nguyên.** Đo lại trên đúng model/snapshot C001/C002 hiện có: hard crash **2/2 khôi phục**, trước sửa là 0/2. Mỗi DN đủ 5 điểm, giữ cùng request/job/nonce/context, không fit hoặc đổi model/khóa. Đã áp dụng bundle mới lên Agent2/worker trên Portal 8800; không restart Portal hoặc đổi quyền/mật khẩu/config.

[Hướng dẫn/cơ chế/giới hạn](../../../../agent2/docs/HE_WORKER_RECOVERY.md). [Bảng đối chiếu mới](comparison/comparison.html), [Markdown](comparison/REPORT.md), [JSON từng lượt/ca](comparison/comparison.json). Bằng chứng [0/2 cũ](../plaintext_comparison_20261112/REPORT.md) giữ nguyên theo thời điểm, không sửa thành pass.

## Kết quả

| Kiểm tra | Kết quả | Evidence |
|---|---|---|
| Toàn bộ HE sau sửa test | **202 pass**, 0 error/failure/skip | [JSON](he_final_tests.json), [log](he_final_tests.log), [execution](he_final_execution.json) |
| Hồi quy nghiệp vụ | **742 pass**, 0 error/failure/skip | [JSON](native_tests.json), [log](native_tests.log), [execution](native_execution.json) |
| Worker recovery chuyên biệt | **21 pass**, subset của 202 | [Subset](recovery_subset.json) |
| Chrome/Portal với node/worker thật, fixture riêng | **14 checks pass**, không lỗi JS | [Browser summary](browser/summary.json) |
| Portal quản lý: tắt có kiểm soát / hard crash | **Cả hai khôi phục cùng job, đủ 5 điểm**, một record worker mỗi ca | [Managed interruption](managed_interruption/summary.json) |
| Nâng bản trên Portal đang chạy | owned/ready, worker DB version 2; **6 cache worker cũ giữ nguyên**; model/snapshot/khóa/config/agent khác giữ nguyên | [Deployment](deployment.json) |
| Bộ C001/C002 mở lại sau nâng bản | **40 checks pass**, parity/scope/checksum/key/repeated ID | [Packet check](packet_check.json) |

14 browser checks dùng Portal/node/worker process thật trong fixture tách biệt; không nhận là đã đăng nhập thay người dùng trên Portal live. Lượt live này áp dụng bundle, xác minh readiness bằng chữ ký/pin, schema migration và bảo toàn cache/config/khóa, không thử phá các tác vụ người dùng hiện có. Các ca gây chết worker chạy trong kho/process riêng.

## Đo lại cùng model/dữ liệu

| Loại sự cố | Thành công / ngắt xác nhận | Thời gian khôi phục p50 |
|---|---:|---:|
| Mất worker trước claim | 2/2 | 1.847,96 ms |
| Đóng có kiểm soát rồi mở lại | 2/2 | 688,65 ms |
| Hard crash khi worker đã nhận, trước commit | **2/2** | **2.092,42 ms** |

Mỗi kiểu một ca/DN, cả 6 lần ngắt được xác nhận; không xem đây là SLA hoặc ước lượng tin cậy diện rộng. Có đúng **18 record worker = 2 warmup + 10 lượt đo + 6 sự cố**, không tạo record tính trùng. Các lượt HE đều dùng request mới để đo, không dùng cache để làm nhanh số đo. Điểm và thứ tự giữ nguyên trong ngưỡng profile có sẵn, model registry/snapshot/key file trước/sau không đổi. Loopback, không suy ra độ trễ cloud public hoặc độ chính xác phát hiện sai phạm.

## Nguyên nhân và cách sửa

Trước sửa, WorkerStore đánh dấu mọi running job thành failed/WORKER_INTERRUPTED khi mở lại. Nonce đã reserve không được dùng lại, và worker chưa có hash binding/attempt cho việc tiếp tục. Node gặp terminal failure rồi loại checkpoint khỏi record hiện hành, không còn đường khôi phục đúng yêu cầu.

Bản mới giữ khóa file hệ điều hành độc quyền mỗi worker state. Worker thứ hai bị chặn trước khi mở DB/reset running jobs. Mỗi claim lưu request SHA256, attempt token và generation. Restart chỉ chuyển running managed job thành retryable, attempt cũ vô hiệu. Cùng nonce nhưng envelope có chữ ký khác bị từ chối trước native parse; chữ ký/grant/policy/TTL vẫn kiểm lại.

Replay ledger giữ nguyên bảng nonce; thêm bảng managed hash binding, nonce + hash ghi nguyên tử. Standalone evaluate vẫn burn nonce và từ chối replay. Chỉ callback nội bộ của attempt đang sở hữu đúng request được reserve lại cùng hash. Không có resuming/bypass flag từ HTTP client.

Kết quả commit nguyên tử dưới attempt fence, không ghi đè cache đã hoàn tất. Chết sau commit thì lấy đúng ciphertext cũ; chết trước commit có thể **tính lại phép toán trên đúng bản mã cũ**. Bảo đảm một job logic/kết quả đã commit, **không hứa native compute thực hiện đúng một lần**. Khóa/model/feature/circuit/nonce của yêu cầu đang tiếp tục không đổi; không plaintext fallback.

Worker DB `user_version=2` thêm attempt/generation trong transaction và giữ cache/failed cũ. Legacy nonce chưa có managed hash vẫn burned; legacy running chuyển WORKER_INTERRUPTED_LEGACY. Không mở lại terminal failed/expired cũ hoặc dựng lại HE key đã bỏ. State rollback/copy/missing/corruption, mất key, shared network filesystem và nhiều máy không được bảo đảm. TTL ban đầu tối đa 300 giây, không gia hạn khi restart. Cache đã có vẫn fresh signed retrieval như trước.

## Các điểm ngắt đã kiểm

Process riêng được ngắt sau claim; sau managed replay reservation đã commit; sau native compute trước commit; sau result commit trước reply. Các ca kiểm đúng request hash, opaque model binding, private context qua node restart, 5 điểm/parity rõ và một record worker, generation đúng. Chết sau commit giữ nguyên bytes ciphertext cache, không tạo attempt mới.

Kiểm thêm hai process tranh cùng state khi worker thứ nhất đang pause; gửi lại đồng thời; attempt cũ ghi đè; valid signature nhưng đổi ciphertext; grant bị revoke; request expired; nonce legacy bị burn; schema tương lai; failed terminal. Bootstrap pause chỉ trong test, không thêm fault switches vào sản phẩm.

Full HE lần đầu có 201 pass/1 error do test trực tiếp gọi Worker trong tiến trình doanh nghiệp (đã import sklearn), rồi dùng enterprise.open và bị WORKER_BOUNDARY chặn đúng. Đã sửa test trực tiếp chỉ kiểm chữ ký/hash/cache; parity/boundary/decrypt vẫn được kiểm trong các ca process riêng. **Không hạ guard sản phẩm.** [Lượt đầu](he_tests.json), [log lỗi](he_tests.log); full suite đã chạy lại và đạt 202/202 ở he_final_tests.json. Sửa thêm helper Pair.stop để dừng đúng cây Popen Windows khi restart, tránh venv child giữ lock/port; không kill theo port.

## Rollout và trạng thái

Private backup trong `.runtime/he-company-demo/recovery_20261112`: config/manifest trước sửa, SQLite backup node/worker/replay sau khi dừng đúng Agent2 và worker do Portal tạo, bundle cũ archive. Bundle mới cùng sáu module allowlist, config giữ nguyên; prepared manifest chỉ cập nhật bundle hash/release. Start worker/node và signed readiness pass. Model/snapshot DB, hai DPAPI key files, worker signing key, config Portal và trạng thái các agent khác đối chiếu giữ nguyên. Portal không restart, không đổi mật khẩu/phiên.

Không đưa backup/key/session/password vào evidence hoặc Git. Không tự rollback DB/replay về backup cũ sau khi có request mới. Nguồn luật/thống kê/graph/ML/33 feature và model store không đổi. HE-AC-01 là **FIXED_READY_FOR_REVIEW cho managed recovery trong phạm vi này**; R0–R6/D-11/D-12/production và đánh giá nghiệp vụ vẫn chưa tự duyệt. Chưa mở rộng hai feature, queue hoặc tỷ trọng ML.
