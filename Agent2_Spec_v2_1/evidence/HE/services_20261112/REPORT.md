# CR-031 — Hai dịch vụ node DN / worker bản mã, READY_FOR_REVIEW

Đã tách Mahalanobis HE thành hai HTTP service/process/thư mục: **node DN đọc model/snapshot, tạo feature, giữ HE key và decrypt; worker chỉ policy public/ciphertext, tính và trả ciphertext**. [Hướng dẫn/API/config](../../../../agent2/docs/HE_TWO_SERVICES.md). Đây là thử nghiệm loopback, chưa triển khai cloud thật hoặc thay Portal.

## Evidence cuối

| Kiểm tra | Kết quả | Evidence |
|---|---|---|
| HE + registry + hai service | **93 pass**, 0 fail/error/skip, process exit 0 | [JSON](he_tests_final.json), [log](he_tests_final.log), [execution](he_execution_final.json) |
| Regression Agent2 | **742 pass**, 0 fail/error/skip, process exit 0 | [JSON](native_tests.json), [log](native_tests.log), [execution](native_execution.json) |
| Hai process HTTP, gói worker riêng, hai DN | **16 checks pass**, đủ 10 giao dịch | [summary](demo_audited/summary.json), [execution](demo_execution.json) |

| DN | Dòng đủ điểm qua HTTP | Sai số tuyệt đối lớn nhất so model gốc |
|---|---:|---:|
| C001 | 5 | 0.000001442 |
| C002 | 5 | 0.000001439 |

Tolerance giữ profile CR-029/030: 1e-3 + 1e-5*abs(reference); không coi sai số đạt là bằng chứng accuracy phát hiện sai phạm. [C001 business result](demo_audited/C001-node-result.json), [C002](demo_audited/C002-node-result.json).

## Đã tách gì?

- **Worker bundle allowlist** chỉ 6 module protocol/evaluator/HTTP/store/server, không source enterprise hoặc sme_fraud, model DB, snapshot, auth token, HE secret key hoặc module giải mã. Worker startup từ chối import path còn nhìn thấy source enterprise/business. Health thật từ process bundle báo enterprise_module_available=false và business_module_available=false. [Manifest bundle](demo_audited/worker-bundle-manifest.json).
- **Node doanh nghiệp** authorize trước đọc body/DB, dùng artifact đã fit/version/contract/scope được CR-030 kiểm, mã hóa feature/hệ số, giữ key trong RAM, kiểm quyền/binding/chữ ký rồi decrypt. DTO trả người dùng không có receipt kỹ thuật/tên feature/hệ số/key/ciphertext; worker không nhận credential của người dùng hoặc raw data. Registry/snapshot dump không đổi sau HTTP.
- **Cấp phiên tin cậy**: worker có grant tenant/DN/public key node do operator cài, node ký registration policy. Không nhận policy tự cấp trong evaluate body. Grant, signature, context/model/key epoch, session và request expiry kiểm cả trước tính và trước trả ciphertext cache.
- **Retry có ranh giới**: cùng Idempotency-Key/body/actor/DN trả cùng node run_id và không tạo job thứ hai; đổi body conflict. Mất phản hồi worker vẫn retry cùng ciphertext/HE key tại node, đọc cache ciphertext đã ký. Worker restart đọc được ciphertext đã hoàn tất trong phiên còn hạn. Request đã hết hạn không đọc cache dù session khác còn hạn.
- **API tối thiểu**: node POST /v1/companies/{company}/he/analyze chỉ tham chiếu artifact/snapshot/as_of; worker POST /v1/sessions và /v1/evaluate. Không có fit/decrypt/raw-upload/file endpoint. Loopback-only, Host/Origin/body/content-type guards, bounded concurrency; mã lỗi không trả traceback hoặc dữ liệu nguồn.

## Case đã kiểm tra

27 case service thêm vào 66 case HE/registry: hai DN/tách process, bundle không source DN, không ghi DB nguồn, idempotent node/worker, body conflict, invalid/missing credentials và company scope trước body, raw feature/URL tùy ý bị từ chối, Host/Origin, body lớn/content-type, route giải mã/fit/upload không tồn tại, evaluate không tự đăng ký policy, ký node không có grant, signature tamper, sai company session, revoke grant/reader/cached plaintext, worker restart, mất response retry không thêm job, partial missing 5 dòng/4 điểm, thiếu/unsupported model không gọi worker, business DTO không metadata kỹ thuật và cached request expiry.

66 case trước vẫn kiểm missing/contract 33/version/preprocess/model/fit provenance/no-fit/read-only, opaque binding không lộ source ID/weights, HE key ở DN, worker public context không decrypt, primitive parity và domain/batch. Bản thử chỉ Mahalanobis hai feature đã chọn trong contract 33, không IF/ECOD/LOF/AE HE hoặc bốn nhánh HE.

## Giới hạn cần giữ rõ

- Chỉ localhost/127.0.0.1; **chưa cloud/network deployment, TLS/mTLS hoặc server production**. Portal live, active models/catalog/kernel/33 feature không đổi. [17 core source hashes giữ nguyên](preservation.json).
- Worker bundle/process boundary không là OS/filesystem sandbox; demo cùng Windows account. Chưa bảo vệ trước người kiểm soát host hoặc native parser độc hại; chữ ký/telemetry không phải proof worker tính đúng. Chưa KMS/rotation/attestation/side-channel gate, privacy certification hoặc production approval.
- **HE key/pending của node chỉ trong RAM**, chưa recovery qua node restart. Node idempotency/cached plaintext chỉ trong process; worker ciphertext cache durable không thay key persistence. Phiên 300 giây; node tối đa 8 active/512 expired identities, worker 128 session/512 job, 2 phép tính/8 kết nối; chưa retention tự động hoặc HA.
- Tenant/DN/profile/số dòng/kích thước/thời điểm là metadata public. Không có raw feature/model/hash plaintext/transaction IDs gốc trong gói worker. Model/reference/receipt rõ chỉ tại DN.
- Không fit trong service, không học chung DN/cloud training, không thêm model hoặc ghép queue, không tăng tỷ trọng ML hoặc công bố xác suất. Các mốc R0–R6/D-11/D-12 sản phẩm giữ nguyên, không tự ký DONE.

Lịch sử chẩn đoán: demo đầu lỗi GET health do tên semaphore trùng _threads của ThreadingMixIn, đã đổi _request_slots; demo_transport_fix/demo_final 14 checks pass. he_tests 92 pass trước thêm check expiry cache; **he_tests_final 93 pass**. demo_audited cuối bổ sung parity primitive qua HTTP, **16 checks pass**. Không giấu failure hoặc coi lượt trước là phiên bản cuối.

[Source/provenance](source_provenance.json), [artifact manifest](artifact_manifest.json). Toàn bộ fixture mô phỏng, không có private key/credential thật trong evidence; các process demo/test được dừng sau kiểm thử.
