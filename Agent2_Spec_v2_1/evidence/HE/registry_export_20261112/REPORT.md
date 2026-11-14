# CR-030 — Xuất model registry vào HE, READY_FOR_REVIEW

Đã nối **model đã fit riêng tại DN từ MethodStore → snapshot feature contract hiện hành → mã hóa model/đầu vào → worker ciphertext → decrypt tại DN**. Chỉ READY_FOR_REVIEW cho adapter thử nghiệm được giao; không duyệt production/cloud service hoặc full R2/R5. [Hướng dẫn và CLI](../../../../agent2/docs/HE_REGISTRY_EXPORT.md).

## Kết quả

- [66 kiểm thử HE pass](he_tests_hardened.json), 0 fail/error/skip; gồm 34 phép thử crypto/boundary trước và 32 registry/CLI cases. [Log](he_tests_hardened.log), [execution exit 0](he_execution_hardened.json).
- [742 kiểm thử Agent2 pass](native_tests.json), 0 fail/error/skip; [log](native_tests.log), [execution exit 0](native_execution.json).
- [Demo cuối C001/C002](demo_hardened/summary.json): model từ DB thật, 32 history + 8 reference mỗi DN, snapshot query 5 giao dịch. Reader không có model.fit; fit/begin_fit/publish bị chặn trong phase export. DB model/snapshot dump trước/sau giống nhau; worker process mới không import enterprise/sklearn hoặc có HE secret key.

| DN | Giao dịch đủ điểm | Sai số tuyệt đối lớn nhất so primitive gốc | Worker giây gồm startup |
|---|---:|---:|---:|
| C001 | 5 | 0.000001443 | 1.991 |
| C002 | 5 | 0.000001442 | 1.222 |

Tolerance giữ nguyên profile CR-029: 1e-3 + 1e-5*abs(reference). Số đo local mô phỏng, không là hiệu năng cloud hoặc bằng chứng accuracy nghiệp vụ.

## Phạm vi adapter

Kho/catalog hiện hành chưa có model HE tương thích cho IF/ECOD/LOF/Autoencoder/RobustZ. Không giả chuyển chúng thành Mahalanobis. Thêm **job fit offline opt-in he_mahalanobis_2d** cho primitive ShrunkMahalanobis đang có, publish artifact cùng MethodStore bất biến, có config/job/hash/phiên bản, không thêm vào catalog web hoặc tự active. Export chỉ đọc artifact_id tường minh; chọn ECOD hoặc model khác trả he_adapter_unsupported trước deserialize, missing model trả null và không tạo DB.

Cả model/snapshot mở read-only sau auth. Kiểm scope, artifact/manifest/payload/model checksum, **full contract 33 feature**, runtime/core/preprocess, selected column order và job provenance succeeded trước joblib.load. Model đang dùng đúng **hai feature được chọn**, không chấm toàn 33 cột. Reader chỉ cần data.import; chỉ job fit cần model.fit. Artifact legacy/khác version không được tự gán metadata mới.

Snapshot feature R1 giữ as_of; thiếu nguồn, trước kỳ evaluation, reference/model tương lai, training identity overlap hoặc ngoài miền không sinh điểm 0. Giữ đủ dòng; một ca thiếu journal_line_count trả 5 dòng, chỉ mã hóa/chấm 4 dòng đủ dữ liệu. Batch >8 dòng khả dụng trả he_batch_limit, không cắt còn 8. Kết quả là raw squared Mahalanobis, chưa percentile/xác suất/ensemble/queue.

RegistryExport chỉ đưa request ciphertext và policy public tin cậy sang worker. Artifact/snapshot ID/hash plaintext/tên feature/reference/hệ số rõ/transaction IDs/receipt không có trong gói; opaque model_id có salt ràng buộc đúng nguồn, salt ở DN. Local receipt giữ provenance và ánh xạ về giao dịch. Recheck quyền trước/sau export, lấy gói, trước decrypt và trước trả/ghi kết quả. Worker nhận environment theo allowlist, không nhận token Portal/credential cloud hoặc PYTHONPATH tùy ý từ DN.

CLI có `fit` riêng và `score-local`; kiểm bằng tiến trình mới, reader không có quyền fit. Output atomic, không ghi đè kết quả cũ. Unsupported model vẫn ghi đủ kết quả unavailable/null và exit 2; không tự fit hoặc plaintext fallback.

## Kiểm thử bổ sung

Sai DN/model/snapshot; thiếu DB không tự tạo; read-only cấm ghi; IF/ECOD không deserialize khi unsupported; full contract/fingerprint/order/runtime/preprocess/hash/model version/registry version; nguồn gốc fit job không khớp; đổi evaluation metadata không có job mới; model hợp lệ nhưng kỳ evaluation muộn; history/identity overlap; partial missing; batch không cắt; revoke trong load/trước package/trước decrypt; gói không lộ provenance, bản sao gói không sửa pending request; fit idempotency/permission; CLI cold process/không ghi đè/unsupported; worker environment không truyền credential.

## Giới hạn còn lại

- Chưa UI Portal hoặc cloud/network API; worker là subprocess local, cùng tài khoản OS, chưa filesystem/host sandbox. Live config/model/snapshot không sửa hoặc khởi động lại. [17 core source giữ nguyên](preservation.json).
- Chưa adapter HE cho IF/ECOD/LOF/AE/RobustZ, nhiều hơn hai feature, hoặc bốn nhánh HE. Không ghim model mới vào web hoặc chạy fit trên dữ liệu live.
- Single-key riêng từng DN, không cloud training/multi-key. Chưa KMS/session persistence/rotation/retention/production resource sandbox/side-channel. Các metadata tenant/DN/profile/số dòng/kích thước/thời điểm vẫn nhìn thấy.
- Threat model thử nghiệm là code/policy/enterprise tin cậy, worker tính đúng và chỉ quan sát ciphertext. Chữ ký/hash/telemetry không chứng minh tính đúng trước cloud ác ý. Không tuyên bố privacy proof/attestation/accuracy hoặc phê duyệt production; D-11/D-12 và mốc R2/R5 giữ nguyên.

Lịch sử evidence giữ nguyên: `he_tests` 58 pass trước mở rộng; `he_tests_reviewed` 64 ca có một fixture timezone làm reason khác kỳ vọng, sửa fixture UTC và thêm ca model muộn hợp lệ; `he_tests_final` 65 pass. Sau lọc environment, **he_tests_hardened 66 pass và demo_hardened** là bằng chứng cuối. `demo`/`demo_reviewed` giữ để đối chiếu trước cập nhật.

[Source/provenance](source_provenance.json), [manifest evidence](artifact_manifest.json). Toàn bộ nguồn mô phỏng, không chứa HE secret key hoặc credential thật trong evidence.
