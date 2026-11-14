# CR-034 — Giao diện chạy phân tích HE, READY_FOR_REVIEW

Đã có giao diện **chọn doanh nghiệp → chọn bản dữ liệu đã lưu → Chạy phân tích**, dùng phiên Portal hiện tại, không yêu cầu chọn model/khóa. Node HE nhúng tại backend DN, model/khóa/giải mã giữ tại DN; worker vẫn ciphertext-only. Tính năng opt-in, chưa thay cấu hình hoặc restart live. [Hướng dẫn bật và sử dụng](../../../../agent2/docs/HE_WEB_ANALYSIS.md).

## Kiểm thử cuối

| Phạm vi | Kết quả | Evidence |
|---|---|---|
| HE/registry/keys/services/durable jobs/web API | **145 pass**, 0 failure/error/skip, exit 0 | [JSON](he_tests.json), [log](he_tests.log), [execution](he_execution.json) |
| Regression nghiệp vụ/Portal/nhập/snapshot | **742 pass**, 0 failure/error/skip, exit 0 | [JSON](native_tests.json), [log](native_tests.log), [execution](native_execution.json) |
| Focused API web sau hoàn thiện metadata | **14 pass**, exit 0 | [log](focused_web_final.log), [execution](focused_final_execution.json) |
| Chrome/Playwright, HE thật | **17 checks pass**, không JS error | [summary](browser_release/summary.json), [log](browser_release.log), [execution](browser_release_execution.json) |
| Khởi động CLI opt-in ở process mới | **3 checks pass** | [summary](cli_smoke.json) |

Browser đi qua Portal HTTP/session/introspection, node DPAPI và worker native TenSEAL thật, không mock điểm hoặc tính plaintext ở worker. C001/C002 mỗi DN 5 giao dịch đều nhận đủ điểm. Bấm lại/reload/mất worker chỉ tạo tổng cộng hai worker computations cho hai lượt; ID C002 giữ nguyên qua outage/reload. Dữ liệu train không được chấm như tập đánh giá, trả unavailable với giải thích và không bịa điểm 0. Thiếu model khóa nút cho dữ liệu chưa có phiếu; kết quả cũ đã có vẫn có thể đọc đúng quyền.

[Desktop](browser_release/01-completed-desktop.png), [chờ worker](browser_release/02-waiting-worker.png), [mobile](browser_release/03-completed-mobile.png). Đã xem ảnh desktop và kiểm không tràn viewport mobile. Phiếu chỉ giữ tham chiếu, không khóa/token/model. Browser chỉ POST snapshot ID tới backend DN, không gọi worker trực tiếp. Đổi nguồn bỏ kết quả cũ, phản hồi trễ không ghi đè; hết phiên hoặc thu hồi membership xóa kết quả/không fallback credential local trong Portal.

CLI smoke bật process mới của `sme_fraud.review_server` với `--he-node-config`, `--he-bindings`, cùng DB snapshot và Portal authorizer; catalog khả dụng và 5 dòng C001 hoàn tất qua worker thật. Không dùng auth_file để thay current Portal owner. Test API kiểm scope/cross-company, snapshot khác DN, không nhận artifact/as_of từ client, duplicate pin, missing model, metadata check không deserialize/fit, Idempotency-Key bắt buộc, result revocation và deny route/query ngoài allowlist.

## Quyết định tích hợp

- Thêm trang/assets và liên kết từ workbench; không đổi luồng nhập, feature hoặc bốn nhánh local. UI mới có hai selector và một nút chính; trạng thái tự poll/resume, điểm nằm trong phần mở rộng. Có nhãn nguồn mô phỏng.
- Backend cấu hình sẵn `he-ui-bindings/1.0.0` theo tenant/DN. Chọn artifact tường minh, không latest/refit. Catalog kiểm model metadata/hash/version/contract/provenance bằng chế độ metadata_only, không joblib.load. Export vẫn kiểm đầy đủ trước deserialize/chấm. Sai model không kích hoạt plaintext fallback.
- `as_of` bằng snapshot.created_at, cố định cùng dữ liệu để retry không thay body. Source catalog dùng reader checksum read-only, không trả raw source, artifact ID hoặc key; tối đa 100 snapshot gần nhất có thông báo giới hạn. Kỳ nguồn sắp theo thời gian có múi giờ, số lượng là bản ghi nguồn.
- Review server dùng authorizer hiện tại cho node nhúng; CLI yêu cầu config 1.2.0 và cùng đường dẫn DB snapshot. Standalone node không được mở đồng thời cùng state_dir. Portal chỉ thêm đúng allowlist trang/assets/datasets/jobs/status/result/resume, không mở decrypt/fit/worker proxy.
- Receipt localStorage ghi trước POST; namespace owner/company/snapshot, không token/HE key. Key/body/job cũ được dùng lại; nguồn/owner thay đổi bỏ context cũ. Không tạo job khác khi failed/expired hoặc khi mất state. Trình duyệt không cho ghi phiếu thì chưa gửi lượt mới.

Sau full HE suite, metadata kỳ nguồn được sửa để sắp UTC đúng và thêm nhãn mô phỏng; focused final 14 pass và browser cuối kiểm trên bản cuối này. Không cần chạy lại các native crypto/storage tests không bị tác động. Native regression 742 chạy trên thay đổi route/auth/server; kernel nghiệp vụ không đổi. Hai lượt browser đầu lỗi ở assertion newline và CSP của test helper, đã sửa test; browser_final2/acceptance 16 pass là lượt trung gian. **browser_release 17 pass** có thêm ca dữ liệu train unavailable, là evidence cuối. Việc dọn DOM kết quả cũ khi đổi nguồn được kiểm bằng assertion metadata rỗng trong browser cuối.

## Phạm vi và giới hạn

Không sửa luật/đồ thị/thống kê/ML estimators, bộ 33 feature, model hoặc snapshot đã có; [17 core hashes](preservation.json) giữ nguyên. Fixtures/model training chỉ tạo trong thư mục tạm để chuẩn bị test; inference/click không fit/publish. Không chép khóa/config vào evidence, Git hoặc worker. Không commit/push, thay cấu hình/restart Portal hoặc Agent2 live.

Vẫn Mahalanobis hai feature/8 dòng hợp lệ, không bốn nhánh HE/IF/ECOD/LOF/AE. Chưa queue/active, cloud public/TLS production/KMS/native sandbox/HA/rotation/proof worker ác ý hoặc accuracy claim. Node DPAPI cần tài khoản/profile Windows đúng; không bổ sung cross-machine restore hay reboot test. Browser xóa localStorage/đổi máy có thể mất phiếu; không bảo đảm dedup qua việc người dùng cố ý tạo key mới. Giữ mô hình quyền workspace Portal hiện tại, chưa tài khoản cá nhân.

Hiện cần người vận hành ghim model, cấp grant và bật cấu hình HE thật theo hướng dẫn trước khi dùng trên Portal live. Không tự tạo model/key demo trong cấu hình thật. Chỉ READY_FOR_REVIEW cho UI HE thử nghiệm; không ký DONE, nghiệm thu bảo mật/hiệu quả nghiệp vụ hoặc hoàn tất R2/R5.

[Source/provenance](source_provenance.json), [kiểm tra tĩnh](validation.json), [manifest](artifact_manifest.json).
