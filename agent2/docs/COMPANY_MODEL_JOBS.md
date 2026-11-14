# Fit riêng và chấm bằng model đã lưu theo doanh nghiệp

Đã có CLI `python -m sme_fraud.method_jobs`, kho `MethodStore` SQLite riêng và artifact `company-method-artifact/1.0.0`. Fit và score là hai thao tác/process riêng. Không có endpoint HTTP fit, không tự chọn model mới nhất hoặc đổi model active.

## Thử ngay bằng dữ liệu mô phỏng

```powershell
cd D:\agent22
& agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/demo_company_models.py
```

Demo dùng C001/Isolation Forest và C002/ECOD. Mỗi bên có 10 dòng train, 5 dòng reference sau train và 5 dòng mới cần chấm. Fit ghi model vào `.runtime/company_model_demo/models.sqlite3`; score được gọi bằng **tiến trình Python mới**, nạp model từ DB với tài khoản chỉ có quyền đọc. Tệp `summary.json` in cuối lệnh chứa model/artifact/job IDs, contract 33 cột và các cột được dùng/loại trong preprocess.

Policy/credential demo là tạm và bị xóa sau chạy. Dữ liệu, model và các tệp kết quả là mô phỏng kỹ thuật; không dùng để báo accuracy hoặc coi là model đã active. Chạy lại demo tạo thư mục kết quả mới và giữ lịch sử cũ.

## Dữ liệu nào được fit?

Fit config bắt buộc snapshot, method/profile/minimum_history, chính sách thiếu, evaluation_mode và các ranh giới:

```text
history_start < history_end <= reference_start < reference_end <= evaluation_start
```

Mọi khoảng đều đầu bao gồm/cuối không bao gồm, timestamp phải có offset. Cả event-time và known-time của dòng phải nằm trong khoảng tương ứng. History và reference được replay **riêng** tại cutoff cuối mỗi kỳ; revision đến sau không thay phiên bản đã dùng trong train. Không đưa ID giao dịch chung vào cả history/reference.

Model fit trên history; reference chỉ được score để khóa phân phối midrank. Dữ liệu reference/test không được dùng để học median/scaler/model hoặc tự đổi cột. `minimum_history` phải khai báo rõ; mức 5 trong demo là điều kiện kỹ thuật, không duyệt D-03 sản xuất.

- `backtest`: đánh giá hồi cứu, chỉ dùng dữ liệu fit/reference trước kỳ chấm. Thời điểm tạo artifact thực vẫn được ghi, không giả model từng được triển khai trong quá khứ.
- `prospective`: job/model phải được tạo và hoàn tất trước kỳ đánh giá; kiểm lại deadline khi công bố. Fit qua ranh giới kỳ thì thất bại, không công bố model.

## Chính sách dữ liệu thiếu được lưu theo model

| Policy | Khi fit/reference | Khi chấm |
|---|---|---|
| strict | Thiếu bất kỳ cột được chọn: fit thất bại, không bỏ dòng | Dòng thiếu trả null/available=false |
| median_flags | Học median từ giá trị đã có **trong train**, thêm cờ thiếu | Dùng đúng median/cờ đã lưu; ghi imputed_features và lý do nguồn |

Với median_flags, cột all-null trong train bị loại cố định và ghi `no_observed_training_values`; không điền 0 hoặc học từ reference/test khi cột đó xuất hiện về sau. Mỗi dòng vẫn cần ít nhất một cột đang dùng có giá trị quan sát được; thiếu toàn bộ thì unavailable. Không sửa giá trị/mask gốc của snapshot. available nghĩa là tính được theo policy đã fit, không chứng minh đủ chứng từ hoặc kết luận nghiệp vụ đúng.

Full input FeatureContract vẫn là **33 cột theo đúng thứ tự/dtype/semantics hiện hành**. Sau preprocessing, số cột thực vào model có thể khác (median_flags thêm indicators và loại cột all-null); `selected_columns`, `kept_columns`, `dropped_columns`, `output_columns`, medians và hash/version đều được lưu. Không suy tương thích bằng số cột.

## Quyền và phiên bản

- Fit/job quản lý cần membership đúng DN, `data.import` và **`model.fit`** được cấp từ backend. Vai trò director không tự cấp quyền này.
- Score cần quyền đọc `data.import`, không cần quyền fit hoặc xác minh. CLI mở kho model `mode=ro`; thiếu kho/model trả unavailable, không tạo DB/model hoặc fit ngầm.
- Lookup model/job luôn theo tenant + DN. Cùng mã giao dịch ở hai DN vẫn tạo hai model bundle riêng. Model của DN khác không được nạp.
- Artifact lưu payload model/reference, full feature contract/fingerprint, preprocess và tham số đã học, model/reference versions, library/Python/platform/code hashes, snapshot/source checksums, kỳ/config/job/actor và thời điểm bắt đầu/hoàn tất.
- Kiểm format/checksum, full contract, code/runtime/preprocess trước khi đọc lại model đã đóng gói (deserialize, không phải giải mã mật mã). Model/caches legacy hoặc contract khác thứ tự/đơn vị/cutoff trả `artifact_incompatible`; không mở model cũ chỉ vì đủ 33 số.
- Artifact/audit bất biến. Artifact + trạng thái succeeded + audit được ghi cùng transaction; retry cùng key/config trả lại job/model cũ. Đổi config/snapshot/version dùng key mới. Không có pointer latest/active tự đổi.

Chỉ worker/backend nội bộ ghi model bytes. Không có API nhận pickle/code model từ người dùng. Nếu job crash hoặc quyền bị thu hồi giữa fit, job có thể còn running nhưng không có artifact mới; cần người có quyền xử lý job rồi tạo yêu cầu mới. Chưa có scheduler/lease/recovery tự động.

## CLI cho môi trường đã cấu hình

Tạo policy/token phía backend đúng DN; không dùng credential demo đã xóa. Dùng config do demo tạo làm mẫu, thay bằng snapshot và kỳ thực đã được phép xử lý. `selected_columns` có thể bỏ để dùng toàn bộ contract 33 cột; missing_policy/evaluation_mode phải ghi rõ.

```powershell
cd D:\agent22\agent2
& .venv/Scripts/python.exe -X utf8 -u -B -m sme_fraud.method_jobs fit `
  --snapshot-db .runtime/imports/snapshots.sqlite3 --model-db .runtime/company-models.sqlite3 `
  --auth-file .runtime/policy.json --token-file .runtime/fit.token --company C001 `
  --config .runtime/C001-fit-config.json --idempotency-key C001-fit-20261111-001 `
  --output .runtime/C001-fit-result-001.json
```

Lấy `job.artifact_id` từ kết quả. Ghi mapping JSON dạng `{ "isolation_forest": "mth_ID_THAT" }`, dùng artifact ID thật từ job; không có model fallback cũ.

```powershell
& .venv/Scripts/python.exe -X utf8 -u -B -m sme_fraud.method_jobs score `
  --snapshot-db .runtime/imports/snapshots.sqlite3 --model-db .runtime/company-models.sqlite3 `
  --auth-file .runtime/policy.json --token-file .runtime/score.token --company C001 `
  --snapshot-id snp_ID_THAT --as-of 2026-10-06T00:00:00+07:00 `
  --artifacts-file .runtime/C001-artifacts.json --output .runtime/C001-scores-001.json
```

Output phải là tệp mới để giữ lịch sử. Có thể thêm `--method ecod` để yêu cầu một phương pháp chưa có artifact và nhận trạng thái unavailable rõ. Tất cả dòng vẫn được trả về, không lọc hit luật/top-K trong bước chấm.

Luật canonical chưa có bridge đầy đủ, benchmark/release gate và UI/Portal identity còn là phần riêng. [Báo cáo CR-013](../../Agent2_Spec_v2_1/evidence/R2/company_fit_20261111/REPORT.md).
