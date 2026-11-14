# CR-029 — HE inference thử nghiệm, READY_FOR_REVIEW

Người dùng chọn **fit riêng tại doanh nghiệp, cloud chỉ chấm trên dữ liệu mã hóa**. Đã thực hiện proof-of-concept với HE thật, không phải Base64/plaintext simulator. [Hướng dẫn](../../../../agent2/docs/HE_INFERENCE_EXPERIMENT.md).

## Kết quả đã chạy

- [33 kiểm thử HE pass](he_tests_reviewed.json), 0 fail/error/skip; [log](he_tests_reviewed.log), [process exit 0](he_execution_reviewed.json).
- [742 regression Agent2 pass](native_tests.json), 0 fail/error/skip; [log](native_tests.log), [process exit 0](native_execution.json).
- [Demo subprocess hai DN/10 dòng pass](demo_reviewed/summary.json). Hai model fit 32 dòng lịch sử riêng trước kỳ chấm, hai bộ khóa HE riêng. Worker không có HE secret key, không import enterprise/sklearn hoặc gọi fit/decrypt. Public context không tự giải mã được kết quả.
- [Dependencies](dependency_check.json) không xung đột. Dependency HE opt-in: TenSEAL 0.3.18 và cryptography 50.0.2; native/runtime packages cũ giữ phiên bản.

| DN | Dòng chấm | Sai số tuyệt đối lớn nhất B1/B2 | Worker giây, gồm startup | Peak RSS MiB |
|---|---:|---:|---:|---:|
| C001 | 5 | 0.00000594 | 0.873 | 71.8 |
| C002 | 5 | 0.00000768 | 0.818 | 71.8 |

B0 là ShrunkMahalanobis gốc; B1 là cùng công thức quadratic rõ; B2 là tính trên ciphertext. B0/B1 sai số <1e-10 trong fixture. B1/B2 sai số lớn nhất 0.0000076832, đạt tolerance đặt trước 1e-3 + 1e-5*abs(reference). Số đo chỉ trên máy local này, không suy thành hiệu năng cloud hoặc độ chính xác phát hiện sai phạm. Request khoảng 4,7 MB/5 dòng (gồm public context và model mã hóa), response khoảng 176 KB; chưa tối ưu cache/batching/traffic.

## Ranh giới được kiểm chứng

Enterprise chuẩn hóa theo model fit, mã hóa cả hai cột feature và ba hệ số bậc hai. Worker mới chỉ nhân/cộng ciphertext, trả ciphertext được ký. HE secret key chỉ ở bộ nhớ enterprise, không có trong gói/ledger/evidence; signing key của worker khác khóa HE. DN kiểm signature/request/context/model/epoch/row handles trước decrypt, không có dịch vụ giải mã tùy ý.

Case HE có: sai tenant/DN/key epoch/model/profile, policy tắt, model/context ciphertext bị thay, packet/chữ ký sai, gói thêm feature rõ, private context bị lẫn, expiry/lifetime, replay qua nhiều lần gọi, không sửa DB lạ, thiếu/NaN/inf/bool, ngoài miền/quá batch, lịch sử trùng kỳ đánh giá, kết quả sai request/đơn vị/bị sửa/mở lại, ciphertext ngẫu nhiên, đủ 8 dòng và zero/biên miền. Fit/decrypt spies trong evaluator không được gọi. Native parser chỉ nhận gói đã ký/hash pin, nhưng vẫn cần sandbox khi triển khai.

## Phạm vi và giới hạn

- **Chỉ là thí nghiệm single-key riêng từng DN trên hai biến số.** Model là primitive ShrunkMahalanobis đang có, chưa là IF/ECOD/LOF/Autoencoder HE hoặc bốn nhánh hoàn chỉnh. Contract thử riêng, chưa export/read model từ registry 33 feature hoặc replay snapshot nghiệp vụ hiện hành.
- Worker chạy subprocess local mô phỏng cloud, **chưa có server cloud, mạng/TLS hay web tích hợp**. Không chuyển Portal hoặc dữ liệu thật lên cloud; không khởi động lại dịch vụ live, thay active model hoặc queue. [Bảo toàn 17 nguồn](preservation.json).
- Threat model thử: code/enterprise/policy tin cậy và worker chỉ tò mò, tuân thủ circuit. Chữ ký và hash không chứng minh tính đúng trước worker ác ý. Telemetry không là attestation/proof. Chưa KMS, rotation/recovery, durable client pending, OS resource sandbox, chống side channel hoặc nghiệm thu production.
- Metadata DN/profile/số dòng/kích thước/thời điểm vẫn nhìn thấy. Không công bố hash plaintext nguồn/model có thể đoán; không có HE secret key trong source/evidence.
- R2/R5 và D-11/D-12 sản phẩm vẫn giữ trạng thái trước; không cloud training, multi-key hoặc tự dùng Logistic có nhãn. Tolerance/profile ở đây chỉ cho thí nghiệm, không chốt sai số luật tiền VND hay hiệu quả nghiệp vụ.

Lịch sử chẩn đoán: `he_tests.json` có lỗi cleanup connection SQLite của test, đã sửa bằng explicit close; `he_tests_final` 32 pass trước thêm boundary/RSS; **he_tests_reviewed** 33 pass là lần cuối. `demo` là lượt đầu pass; **demo_reviewed** là lượt cuối có số đo RSS. Không ghi đè hoặc giấu lần chẩn đoán lỗi.

[Provenance và hashes mã nguồn](provenance.json), [manifest evidence](artifact_manifest.json). Chỉ READY_FOR_REVIEW cho phép thử, không tự ký DONE hoặc production.
