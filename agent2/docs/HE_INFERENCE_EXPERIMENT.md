# Thử nghiệm chấm model trên bản mã — CR-029

**Cập nhật CR-030:** đã có [adapter xuất từ MethodStore và snapshot R1](HE_REGISTRY_EXPORT.md) cho model Mahalanobis thử nghiệm; kênh subprocess được lọc environment để không chuyển credential của doanh nghiệp. Phần dưới giữ phạm vi proof-of-concept CR-029 trước khi có registry adapter; các giới hạn crypto/cloud production vẫn còn.

**Đã chạy proof-of-concept HE thật; chưa tích hợp web hoặc triển khai cloud thật.** Người dùng chọn giai đoạn đầu: model fit riêng tại doanh nghiệp, cloud chỉ chấm dữ liệu mã hóa. Quy tắc ranh giới ở [ENCRYPTED_CLOUD_BOUNDARY.md](ENCRYPTED_CLOUD_BOUNDARY.md).

## Đã kiểm chứng gì?

- Hai doanh nghiệp mô phỏng C001/C002, mỗi bên fit riêng `ShrunkMahalanobis` đang có trong `sme_fraud/unsupervised_statistics.py` bằng 32 dòng lịch sử không nhãn, rồi chấm 5 dòng mới.
- Mỗi DN có HE secret key riêng, giữ trong bộ nhớ enterprise process. Đầu vào và các hệ số model đều được mã hóa CKKS; public context loại secret key và chỉ mang public/relinearization keys. Model mean/std/location dùng chuẩn bị feature tại DN, không gửi rõ cho worker.
- Worker chạy subprocess mới, chỉ nhận gói ciphertext và policy tin cậy. Worker không import enterprise/sklearn, không fit, không gọi decrypt và không thể tự decrypt bằng public context. Trả ciphertext kết quả; DN kiểm signature/binding rồi mới decrypt.
- Chữ ký Ed25519 ràng buộc gói, tenant/DN, phiên, context/key epoch, model, nonce và request. Policy/verify key được cài theo kênh quản trị tin cậy, không lấy từ request. Ledger SQLite riêng chống replay; nonce được giữ cả khi phép tính sau đó thất bại. Kết quả chỉ được mở một lần trong pending session.
- Không fallback dữ liệu rõ. Thiếu feature/missing, ngoài miền hoặc model không hỗ trợ bị từ chối; không thay bằng 0. Gói thêm trường `features` rõ bị từ chối dù có chữ ký hợp lệ.

Đây là primitive không nhãn được giữ lại, **không phải** chuyển xong bốn model IF/ECOD/LOF/Autoencoder hoặc bốn nhánh nghiệp vụ. Nó không đọc artifact đang ghim trong MethodStore, không sửa catalog/version/33 feature hiện tại và không tự đưa model thử vào active.

## Phép tính và profile cố định

Tại DN, fit giữ nguyên primitive OAS gốc. Với hai feature số `x`, DN chuẩn bị:

```text
z = (x - fitted_mean) / fitted_std - fitted_OAS_location
q = precision[0,0] * z0² + 2*precision[0,1] * z0*z1 + precision[1,1] * z1²
```

Cloud nhận Enc(z0), Enc(z1) và ba hệ số đã mã hóa, thực hiện nhân/cộng ciphertext. Đây là chính squared Mahalanobis distance, không phải xác suất hay một model Logistic có nhãn. Không thêm clipping/threshold/rank vào score. B0 primitive gốc, B1 công thức rõ trên, B2 phép tính HE được đối chiếu riêng; không có xấp xỉ đa thức thay thuật toán trong circuit này.

Profile thử `experimental-ckks-mahalanobis-2d/1.0.0` dùng TenSEAL 0.3.18, degree 8192, coeff bits [60,40,40,60], scale 2^40 và một thread. Đây là lựa chọn thử nghiệm từ các phép toán CKKS được thư viện hỗ trợ, chưa phê duyệt crypto/production. Contract `experimental-numeric-pair/1.0.0` chỉ có hai biến số, chưa phải adapter của contract 33 feature.

Các giới hạn được đặt **trước khi chạy** trong protocol.py: tối đa 8 dòng/2 cột, trị tuyệt đối z ≤ 8, trị tuyệt đối hệ số ≤ 64, packet ≤16 MiB, public context ≤3 MiB, một ciphertext ≤1 MiB, request ≤300 giây, worker subprocess timeout 45 giây. So B1/B2 dùng abs tolerance 1e-3 + relative tolerance 1e-5. Miền B0/B1 đối chiếu 1e-10/1e-10. Đây không phải ngưỡng nghiệp vụ hoặc tiêu chuẩn sai số tiền VND; không dùng CKKS này thay đối chiếu VND nguyên của luật P1.

## Chạy lại

Từ thư mục gốc D:/agent22:

```powershell
& agent2/.venv/Scripts/python.exe -m pip install -r agent2/requirements-he.txt
& agent2/.venv/Scripts/python.exe -X utf8 -B agent2/scripts/run_he_tests.py --report <duong-dan-json-moi>
cd agent2
& .venv/Scripts/python.exe -X utf8 -B -m experiments.he_inference.demo --output-dir <thu-muc-moi-trong>
```

Dependency HE là opt-in, không import qua web/backend hiện tại. Demo dùng thư mục tạm cho request/policy/ledger và signing key của worker; HE secret key không được ghi ra tệp. Thư mục evidence chỉ nhận số đo/kết quả mô phỏng, không chứa khóa. Private signing key của worker khác HE secret key và không giải mã được ciphertext.

Mở [báo cáo và kết quả chạy](../../Agent2_Spec_v2_1/evidence/HE/inference_20261112/REPORT.md). `demo_reviewed` và `he_tests_reviewed` là bằng chứng cuối. Kết quả HE thay đổi rất nhỏ mỗi lần do mã hóa ngẫu nhiên.

## Giới hạn bảo mật/triển khai

- Giả định thử nghiệm: enterprise và worker chạy code đúng, filesystem policy/key tin cậy; cloud có thể quan sát gói nhưng không có HE secret key. Chữ ký phát hiện gói bị sửa/người gửi sai; **không chứng minh cloud ác ý đã thực hiện đúng circuit**. Các cờ worker là telemetry kiểm thử, không phải attestation hay zero-knowledge proof.
- Chưa có dịch vụ HTTP cloud, TLS/mTLS, key provisioning/KMS, OS sandbox/giới hạn RSS, durable enterprise pending store, rotation/recovery, retention/cleanup ledger, attestation/proof hoặc chống side channel. Timeout và giới hạn packet không thay sandbox native parser. Chưa dùng dữ liệu thật hoặc chứng nhận bảo mật.
- Local subprocess chỉ mô phỏng ranh giới hai bên. Worker có thể thấy DN, profile, hai cột, số dòng, kích thước/thời điểm và handles ngẫu nhiên; chưa che metadata bằng padding. Không gửi original transaction IDs, plaintext feature/model coefficients hoặc hash plaintext dễ đoán.
- Model/key/session được fit và tạo mới trong demo. Chưa có bước export model phiên bản từ registry, kiểm as_of nguồn thực/snapshot hiện có và chuẩn hóa contract 33 feature. Time trong fixture history/evaluation chỉ là thứ tự mô phỏng, không phải nghiệm thu replay kế toán.
- Chưa ghim HE adapter vào bốn nhánh hiện tại; unsupported profile từ chối. Không tăng tỷ trọng ML, không thay queue hoặc công bố accuracy. Chưa train trên cloud, chưa học chung nhiều DN/multi-key/threshold. D-11/D-12 vẫn mở cho sản phẩm thật; profile này chỉ áp thử nghiệm single-key riêng từng DN.

## Nguồn kỹ thuật

[TenSEAL](https://github.com/OpenMined/TenSEAL), [serialization context](https://github.com/OpenMined/TenSEAL/blob/main/tenseal/enc_context.py), [Microsoft SEAL](https://github.com/microsoft/SEAL), [Ed25519 của cryptography](https://cryptography.io/en/stable/hazmat/primitives/asymmetric/ed25519/). Các thư viện cung cấp phép toán/khóa; adapter, kiểm thử và số đo ở đây là phần dự án vừa thực hiện, không phải chứng nhận từ nhà cung cấp.
