# Nối snapshot nghiệp vụ vào đầu vào train HE

15/11/2026. Adapter `snapshot-he-training-adapter/0.1.0` đọc snapshot đã commit,
tạo preview có kiểm tra và mã hóa đầu vào cho prototype train có nhãn. Đây là
bước chuẩn bị dữ liệu; không tự xác minh nhãn hoặc khởi động train.

## Nguồn và mapping

Hỗ trợ snapshot canonical 1.0/1.1/1.2 qua bộ feature hiện có và
`agent2-rule-snapshot/1.0.0` qua bridge 33 feature nguồn đầy đủ. Không đổi bộ
33 feature, engine luật hoặc contract của model không nhãn.

Chọn đúng thứ tự hai feature đã có:

| Cột train | Feature gốc | Ý nghĩa | Chuyển đổi |
|---|---|---|---|
| 0 | `round_million` | Số tiền VND có chia hết 1.000.000 | Giữ đúng 0/1 |
| 1 | `creator_equals_approver` | Người lập trùng người duyệt duy nhất đã biết | Giữ đúng 0/1; thiếu người duyệt là null |

Mapping version `existing-binary-pair/1.0.0` khóa tên/thứ tự, miền và fingerprint
contract nguồn. Chỉ đổi biểu diễn số binary 0.0/1.0 chính xác sang int64; không
round, scale, clip, abs số tiền, impute hoặc tự học preprocessing. Số tiền và
mã nhân viên/chứng từ/nhãn/điểm luật không được đưa trực tiếp vào X.

Đây là mapping đầu tiên để nối luồng, không chứng minh hai feature đủ để phát
hiện gian lận. Circuit logistic hiện lượng tử hóa thô, có thể không cập nhật
trọng số trên một số batch; không dùng việc tạo được X để kết luận model hữu ích.

## Kỳ và định danh

Yêu cầu tường minh snapshot ID, as_of có múi giờ, kỳ train `[start,end)` và
**đúng 4 mã giao dịch + revision**. Không tự lấy 4 dòng đầu, bù dòng, bỏ lỗi
hoặc lấy top theo cảnh báo/nhãn. Mã lịch sử có thể được chọn rõ từ snapshot;
giao dịch bằng chứng không tự trở thành dòng train.

Bộ feature được phát lại theo thời điểm: giao dịch/phiên bản phải khả dụng tại
as_of, bằng chứng chỉ dùng theo clock từng dòng; các nhóm đồng thời giữ semantics
của builder hiện có. Với nguồn đầy đủ, as_of không vượt source.as_of và khai báo
coverage transactions phải đã được biết tại as_of. Không lùi ngày khai báo.

Thiếu nguồn, sai revision, ngoài kỳ hoặc ngoài miền trả preview `rejected`, giữ
đủ bốn dòng và lỗi chỉ rõ dòng/trường/cách sửa; `x=null`, không mã hóa. Nguồn mô
phỏng và nguồn thật bị trộn cũng từ chối, không âm thầm đổi chế độ xác minh nhãn.

## Quyền và bất biến

Preview dùng `data.import` đúng tenant/company; không cần quyền xác minh mới
để đọc nguồn đã commit. Chuẩn bị dữ liệu train cần `model.fit`. Snapshot reader
mở SQLite mode=ro/query_only, kiểm schema/checksum/scope; không tạo/migrate DB,
ghi audit hoặc fit model. Thiếu DB thì lỗi, không tự tạo kho rỗng.

Preview khóa snapshot/checksum, cutoff, window, row/revision, source feature
contract, mapping và code hashes trong `plan_sha256`. Khi chuẩn bị, backend đọc
lại snapshot và kiểm lại hash; thay request/mapping/build nguồn không được dùng
preview cũ. Snapshot nguồn giữ nguyên.

Provenance được ghi cùng dataset đã ký tại DN, theo model candidate sau này.
Cloud chỉ nhận ciphertext và metadata protocol cũ; không nhận snapshot ID,
transaction IDs, mapping nguồn, evidence hoặc nhãn rõ. Model nguồn snapshot
không được chấm bằng ma trận không có fingerprint mapping tương ứng.

## Cách sử dụng CLI

1. Dùng [request mẫu](../examples/encrypted_training/snapshot-request.example.json),
   thay snapshot ID, thời gian và bốn transaction/revision thực tế. Các chuỗi
   REPLACE là ký hiệu, không phải dữ liệu hợp lệ.
2. Trong config operator private, thêm `snapshot_db` trỏ tới kho hiện có.
3. Chạy preview từ repo root, chưa cần build/khóa HE:

```powershell
agent2/.venv/Scripts/python.exe agent2/scripts/encrypted_training.py preview-snapshot --config CONFIG --token-file TOKEN_FILE --data SNAPSHOT_REQUEST --output PREVIEW_FILE
```

4. Đọc `status`, `rows`, `issues`. Chỉ khi ready, lưu `plan_sha256` đã xem vào
   `expected_plan_sha256` trong config operator và khai báo build/enterprise_root.
5. Chuẩn bị/mã hóa, chưa upload và chưa train:

```powershell
agent2/.venv/Scripts/python.exe agent2/scripts/encrypted_training.py prepare-snapshot --config CONFIG --token-file TOKEN_FILE --data SNAPSHOT_REQUEST --output PREPARED_RECEIPT
```

6. Dùng upload → review-template → xác minh nhãn → confirm theo
[luồng supervised HE](HE_SUPERVISED_TRAINING.md). `prepare-snapshot` không thực
hiện các bước này thay người dùng. Chưa có màn hình Portal mới cho adapter.

## Kiểm chứng

```powershell
agent2/.venv/Scripts/python.exe agent2/scripts/run_he_tests.py --suite test_training_snapshot_adapter --suite test_encrypted_training --report .runtime/snapshot-training-tests.json
```

Chạy thử mã hóa thật bằng snapshot mô phỏng đã commit và context DPAPI demo
riêng có sẵn, không dùng khóa/model/DB live. Thư mục output phải mới:

```powershell
agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/check_training_snapshot_adapter.py --build .runtime/he-training-20261115/build-v3 --demo-contexts .runtime/he-training-20261115/native-demo-bound-v2 --output .runtime/snapshot-training-native-new
```

Các đường dẫn context là bộ thử private, không có trong Git; nếu chưa có cần
chuẩn bị bằng demo supervised HE. Script chỉ kiểm snapshot→X→mã hóa→biên nhận,
không cung cấp nhãn và phải có **0 job train**. Đây không phải chứng minh đã
train model hữu ích trên doanh nghiệp thật, HE33 feature hoặc DONE R0–R6.

[Báo cáo](../../reports/he_training_snapshot_adapter_20261115.md).
