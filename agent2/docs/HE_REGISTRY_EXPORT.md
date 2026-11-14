# Xuất model từ kho doanh nghiệp sang luồng HE — CR-030

**CR-031:** đã có [hai dịch vụ HTTP riêng cho node DN và worker ciphertext](HE_TWO_SERVICES.md). Nội dung CLI bên dưới giữ cách thử CR-030; các giới hạn model hai feature/crypto/production vẫn áp dụng.

Đã nối **MethodStore → kiểm quyền/phiên bản → feature snapshot → mã hóa model và đầu vào → worker ciphertext → giải mã và ghép kết quả**. Đây vẫn là adapter thử nghiệm, chưa tích hợp web hoặc cloud thật. Bản thử toán học trước ở [HE_INFERENCE_EXPERIMENT.md](HE_INFERENCE_EXPERIMENT.md).

## Adapter nào đang dùng được?

Hiện hỗ trợ **he_mahalanobis_2d**, là ShrunkMahalanobis đang giữ trong core, fit offline tại doanh nghiệp và lưu vào cùng kho MethodStore bất biến. Tên này dành riêng cho thí nghiệm; không tự đưa vào catalog/active bundle của web.

Các artifact IF/ECOD/LOF/Autoencoder/RobustZ đang có vẫn được đọc metadata đúng scope, nhưng trả **he_adapter_unsupported / chưa hỗ trợ HE** trước khi deserialize. Không lấy weights của model này để giả thành Mahalanobis, không tự fit lại hoặc dùng plaintext scoring thay thế. Bản thử cũ chỉ giữ model trong bộ nhớ, nên không có sẵn artifact Mahalanobis trong kho live; muốn thử cần một job fit offline riêng được cấp quyền.

## Hợp đồng và quyền

- Dùng **artifact_id tường minh**, không lấy latest hoặc đọc pickle/path do browser gửi. Kiểm credential backend và quyền `data.import` đúng tenant/DN trước khi mở model/snapshot DB. Export/chấm không đòi `model.fit`; job fit riêng cần cả hai quyền như cơ chế hiện có.
- ModelStore chỉ mở `read_only=True`; snapshot dùng reader mode=ro/query_only và checksum/scope reader hiện hành, không chạy DDL hoặc tạo DB khi không có. Inference không ghi model/fit job/audit hoặc snapshot.
- Trước deserialize kiểm artifact/manifest/payload/model checksum, scope, loại adapter, full **contract 33 cột theo đúng thứ tự**, fingerprint, runtime/core/preprocess versions, selected columns, hash preprocess và cấu hình fit. Kiểm provenance của fit job succeeded đúng artifact/request/snapshot bằng transaction scoped chỉ đọc, không dùng API quản lý fit đòi thêm quyền.
- Job implementation binding gồm code job HE, cửa sổ fit hiện có và replay snapshot; không dùng lại artifact legacy/phiên bản khác chỉ vì đủ hai số.
- Chỉ **hai feature đã chọn** trong contract 33 cột được dùng cho model HE hiện tại. Thứ tự cột phải khớp manifest; missing policy chỉ `strict`. Không coi đây là model chấm cả 33 feature hoặc adapter của bốn nhánh.
- Mỗi dòng dùng cutoff nguồn theo R1. Bỏ chấm nếu model/reference từ tương lai, ngoài kỳ evaluation, đã ở tập fit/reference, nguồn thiếu hoặc z ngoài miền. Dữ liệu thiếu không thành 0. Reference là bất biến và ở lại doanh nghiệp; hiện đầu ra là raw squared Mahalanobis distance, không percentile/probability/nhãn sai phạm.
- Giữ đủ dòng được snapshot cung cấp tại as_of; dòng không khả dụng có null và reason. Mã hóa tối đa 8 dòng đủ điều kiện; nhiều hơn thì toàn batch báo he_batch_limit, **không cắt bớt dòng**. Tối đa 200 dòng đầu ra thử nghiệm, vượt trả lỗi.
- Recheck quyền trước/sau export, lúc lấy gói gửi, trước decrypt và trước trả/ghi kết quả. Thu hồi quyền không được trả kết quả cũ. Thay file source không sửa snapshot/model bất biến; phải tạo phiên mới theo luồng hiện có.

## Phần nào gửi worker?

`RegistryExport.cloud_package()` chỉ trả **request ciphertext + policy public được provision qua kênh quản trị tin cậy**. Policy không phải quyền do người gửi tự khai trong HTTP. Worker hiện vẫn là subprocess CLI, chưa có API provision/network. Chỉ chuyển các biến môi trường hệ điều hành cần thiết; không chuyển token Portal, credential cloud hoặc PYTHONPATH tùy ý từ process doanh nghiệp. Subprocess local vẫn dùng cùng tài khoản hệ điều hành và chưa là sandbox filesystem/host riêng; không dùng nó để giả định chống worker ác ý.

Gói không chứa artifact ID thật, snapshot ID, hash model/feature plaintext, tên feature, hệ số rõ, reference rõ, mã giao dịch gốc hoặc thông tin chứng từ. `model_id` là commitment có salt ngẫu nhiên giữ tại doanh nghiệp, ràng buộc artifact/model/full feature contract/preprocess chính xác. Request/model ciphertext có hash, chữ ký và context/key epoch như thí nghiệm trước. Tenant/DN, profile, kích thước, số dòng và thời điểm vẫn là metadata nhìn thấy.

**Local receipt** giữ artifact/job/snapshot ID, model/preprocess/reference version, contract fingerprint, salt và ánh xạ opaque row handle về giao dịch. Receipt và kết quả rõ chỉ lưu/đọc trong môi trường doanh nghiệp, không gửi cloud. HE secret key chỉ ở bộ nhớ session và không được ghi ra tệp. Chưa có KMS/persist session để nhận trả bất đồng bộ qua nhiều lần khởi động.

## Chạy demo trọn luồng

Từ D:/agent22/agent2, cài dependency opt-in nếu chưa có:

```powershell
& .venv/Scripts/python.exe -m pip install -r requirements-he.txt
& .venv/Scripts/python.exe -X utf8 -B -m experiments.he_inference.registry_demo --output-dir <thu-muc-moi-trong>
```

Demo tạo policy/DB tạm, hai DN có 32 dòng history + 8 dòng reference + 5 dòng query, nhập/validate/snapshot thật, fit riêng và publish model. Sau đó chặn fit/begin_fit/publish, mở lại registry read-only, export/chấm/decrypt bằng worker process mới. So điểm với primitive gốc và kiểm dump DB trước/sau không đổi. Nguồn chỉ mô phỏng; không tạo model hoặc quyền trên live.

## Dùng với kho local được cấp quyền

CLI nội bộ dùng credential worker do backend cấp; token để trong tệp riêng, không truyền trực tiếp trên command line hoặc gửi worker. Mật khẩu mở khóa Portal không thay token này. Chưa nối màn hình Portal cho bước export. Các đường dẫn sau là ký hiệu, cần thay bằng DB/config/ID thật.

Job **fit riêng**, không phải một phần của export:

```powershell
& .venv/Scripts/python.exe -X utf8 -B -m experiments.he_inference.registry_cli fit --snapshot-db <snapshots.sqlite3> --model-db <models.sqlite3> --auth-file <policy.json> --token-file <fit.token> --company <DN> --config <fit-config.json> --idempotency-key <khoa-fit-moi> --output <fit-receipt-moi.json>
```

Config JSON chính xác:

```json
{
  "version": "experimental-he-fit-config/1.0.0",
  "snapshot_id": "snp_<32-hex-tu-kho>",
  "method_id": "he_mahalanobis_2d",
  "missing_policy": "strict",
  "minimum_history": 20,
  "profile_id": "he-thu-nghiem-chua-nghiem-thu-production",
  "evaluation_mode": "backtest",
  "selected_columns": ["log_abs_amount", "event_hour_sin"],
  "history_start": "2026-09-02T00:00:00+07:00",
  "history_end": "2026-09-12T00:00:00+07:00",
  "reference_start": "2026-09-15T00:00:00+07:00",
  "reference_end": "2026-09-20T00:00:00+07:00",
  "evaluation_start": "2026-10-01T00:00:00+07:00"
}
```

ID trong dấu `<...>` không phải ID hợp lệ. Các mốc/history tối thiểu và hai feature là cấu hình thử, không phê duyệt chính sách dữ liệu thật. History/reference là cửa sổ start-inclusive/end-exclusive, không trùng transaction identity; evaluation phải sau reference. Model và reference dùng đúng phiên bản đã biết ở từng cửa sổ. Prospective cần job tạo/xong trước kỳ evaluation; chạy hồi cứu phải ghi backtest.

Lấy `job.artifact_id` từ receipt rồi chạy **score-local**:

```powershell
& .venv/Scripts/python.exe -X utf8 -B -m experiments.he_inference.registry_cli score-local --snapshot-db <snapshots.sqlite3> --model-db <models.sqlite3> --auth-file <policy.json> --token-file <reader.token> --company <DN> --artifact-id <mth-id-da-fit> --snapshot-id <snp-id-can-cham> --as-of <ISO-8601-co-mui-gio> --output <ket-qua-local-moi.json>
```

Lệnh này export vào worker local chỉ nhận ciphertext rồi decrypt tại process enterprise; **không gọi dịch vụ cloud**. Output là tệp local riêng, atomic/không ghi đè, recheck quyền trước publish. Exit 0 khi có kết quả available/partial, exit 2 khi thiếu model/unsupported/lỗi; xem reason từng dòng. Thiếu model hoặc không tương thích không tạo DB, fit lại hoặc chọn model khác.

Python adapter: `registry_export.export_snapshot(...)` trả session/pending export trong bộ nhớ. Dùng `.cloud_package()` cho kênh gửi riêng, `.open(response)` để kiểm quyền/binding rồi decrypt, `.local_result()` để đọc trạng thái có quyền. Không gửi toàn bộ object/receipt lên cloud.

## Kiểm thử và phần còn lại

```powershell
& .venv/Scripts/python.exe -X utf8 -B scripts/run_he_tests.py --report <he-tests-moi.json>
```

[Báo cáo CR-030](../../Agent2_Spec_v2_1/evidence/HE/registry_export_20261112/REPORT.md) có demo, kiểm quyền/phiên bản/provenance/missing, CLI process mới và bảo toàn DB. Quy tắc crypto/tolerance/resource/threat model ở [thí nghiệm HE ban đầu](HE_INFERENCE_EXPERIMENT.md) vẫn áp dụng: chưa chứng minh tính đúng trước cloud ác ý, chưa sandbox/KMS/rotation/side-channel/production, chữ ký không phải proof phép tính. Chưa UI/cloud network, adapter các model khác, nhiều feature hơn, phối hợp bốn nhánh, queue/active hoặc accuracy claim. Model và cấu hình đang chạy trên web không thay đổi.
