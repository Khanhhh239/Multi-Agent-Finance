# CR-037 — Bật/Tắt Agent2 kèm worker, READY_FOR_REVIEW

Đã triển khai ba thao tác được giao: **Bật Agent2** khởi động worker và kiểm kết nối/khóa trước chấm; **Tắt Agent2** dừng đúng cây node/worker do Portal tạo, giữ model/khóa/phiên; **Kết nối lại** phục hồi worker và dùng tiếp cùng phiếu/job. Đã áp dụng trên Portal local 8800, node 8766 và worker 8868. [Hướng dẫn](../../../../agent2/docs/HE_MANAGED_WORKER.md).

## Kết quả cuối

| Kiểm tra | Kết quả | Evidence |
|---|---|---|
| Toàn bộ HE/keys/registry/services/jobs/managed/web | **159 pass**, 0 failure/error/skip | [JSON](he_tests.json), [log](he_tests.log), [execution](he_execution.json) |
| Regression nghiệp vụ/Portal/import/snapshot | **742 pass**, 0 failure/error/skip | [JSON](native_tests.json), [log](native_tests.log), [execution](native_execution.json) |
| Managed lifecycle, subset của 159 | **7 pass** | [log](focused.log), [execution](focused_execution.json) |
| Durable jobs cũ, subset của 159 | **23 pass** | [log](jobs.log), [execution](jobs_execution.json) |
| Browser Portal thật/worker thật trong fixture riêng | **11 checks pass**, 0 JS error | [summary](browser_acceptance/summary.json), [execution](browser_acceptance_execution.json) |
| Portal đang chạy tại 8800 | **start → stop → start pass**, owned/ready true, hai cổng được đóng đúng khi stop | [deployment](deployment.json) |
| Bộ C001/C002 sau nâng bundle | **40 checks pass**, parity/record checksum/cross-scope | [packet check](packet_check.json) |

[Đã sẵn sàng](browser_acceptance/01-ready.png), [mất worker](browser_acceptance/02-worker-offline.png), [khôi phục](browser_acceptance/03-recovered.png). Browser dùng Portal/password fixture riêng, Node/Worker subprocess thật và native TenSEAL; không mock điểm, không thay password thật. C001/C002 mỗi bên đủ 5 điểm, dừng/bật lại giữ result cũ; outage rồi reconnect giữ C002 job ID và node process. Reload vẫn cùng kết quả. Worker chỉ có **hai computations** cho hai DN sau các lần reload/restart/recovery. Không fit khi inference, không đổi model/key/snapshot nguồn.

Trên desktop thật đã restart Portal để nạp code/config, chuyển worker thủ công sang worker được Portal sở hữu và thử API nút start/stop/start. Agent1 giữ cùng PID/cổng, không restart; Agent3/4 giữ tắt. Mật khẩu, model, hai private DPAPI keys, worker response key và dữ liệu cũ giữ bytehash, bốn snapshot demo vẫn khớp checksum. Portal restart làm hết session cũ nên người dùng cần đăng nhập lại một lần; **11 browser checks của release này là fixture tách biệt**, không nhận là đã tự đăng nhập/retest phiên người dùng thật sau restart. CR-036 giữ evidence lần đăng nhập thật trước đó.

## Cơ chế

- Portal thêm Runtime stdlib, config he_worker; chỉ thực thi module/argument cố định từ cấu hình operator, không command từ browser. Bundle phải đúng manifest/file set và bằng source worker allowlist hiện tại. Environment/cwd/PYTHONPATH riêng, không bridge secret/khóa DN/model/data rõ.
- Preflight mở hai DPAPI keys tại DN, không in material. Node chỉ health sau mở/kiểm kho phiên; sai khóa/store không tự sinh key mới. Worker key proof dùng node-signed random challenge/expiry/scope, worker xác minh grant rồi ký reply; DN verify key ghim và toàn binding. Không dùng một public health response làm proof. RPC readiness không fit/eval, tạo context/session/job hoặc ghi số liệu nghiệp vụ.
- Catalog available chỉ khi model phù hợp và worker ready. Jobs kiểm lại worker trước export/gửi khi chưa có response, status retryable nếu mất kết nối. Response đã lưu thì decrypt không đòi network. Scope/auth kiểm như trước và không đổi request/schema model/feature.
- Start lặp không tạo thêm processes. Startup fail rollback những process mới sở hữu. Cổng bị process ngoài chiếm thì báo lỗi, không adopt/kill; stop chỉ đúng cây Popen, gồm Windows venv child. Node dừng trước, worker có grace để commit ciphertext đang tính; không purge state hoặc rotate keys.
- Recover cần Portal session; worker được bật/verify lại, node đang sống giữ nguyên. Client giữ receipt/key/job, bỏ poll cũ, resume hoặc lấy lại kết quả của cùng intent. Thông báo ngắn, nút Kết nối lại chỉ hiện khi cần; sửa nhãn nút tránh mang “Xem kết quả đã có” từ dataset trước sang một request mới đang chờ.

## Bảo toàn và rollout

Cấu hình và manifest trước rollout cùng bundle cũ được lưu trong packet private managed_20261112. Sau khi dừng đúng old node và manual worker đã đối chiếu identity, nâng bundle tại cùng path; cập nhật checksum manifest bundle theo release, không thay worker response key. Thêm he_worker vào riêng config Agent2, giữ quyền demo hiện tại và snapshot/model pins. Portal mới tự bật dependency, không cần worker thủ công. Không commit/push file runtime hoặc đưa private key/session/password hash vào evidence. [17 core sources](preservation.json) giữ nguyên; readiness/lifecycle không thay estimator/circuit/33 features.

Hai lượt browser đầu lỗi đọc innerText của metadata trong details đóng (chuỗi hiển thị rỗng), đã sửa test dùng textContent. browser_final2 11 pass là intermediate; sau chỉnh nhãn nút khi đổi nguồn, **browser_acceptance 11 pass** kiểm bản cuối và cả nút recovery ở Portal/iframe. Full 159/742 chạy trên code backend cuối; thay đổi sau đó chỉ là nhãn JS, được browser cuối kiểm lại. Không ghi các lượt lỗi là pass.

## Giới hạn

Vẫn thử nghiệm Mahalanobis 2 feature, tối đa 8 dòng hợp lệ/packet, loopback Windows và nguồn mô phỏng. Không tăng tỷ trọng ML, thêm queue/bốn nhánh HE, labels hoặc accuracy claim. Không public cloud/TLS production, KMS/rotation, OS sandbox/attestation hoặc proof tính đúng trước worker ác ý. Chưa Windows Service/Task Scheduler; sau reboot bật Portal rồi dùng Bật Agent2, không tự chạy khi chưa bật Portal.

Grace timeout/worker crash giữa native compute trước commit có thể dẫn failed/expired rõ ràng; không hứa exactly-once cho việc xóa/rollback state hoặc tự chấm lại bằng nonce mới. Force-kill Portal ngoài đường shutdown kiểm soát không nằm trong bảo đảm dừng mọi child. Cached completed result vẫn đọc tại DN theo quyền hiện tại khi worker tắt. Không tự tái sở hữu agent khác chạy ngoài Portal. Chỉ READY_FOR_REVIEW phần được giao; không ký DONE/gate R2/R5/production.

[Source/provenance](source_provenance.json), [kiểm tra tĩnh](validation.json), [manifest](artifact_manifest.json).
