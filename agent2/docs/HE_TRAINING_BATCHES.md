# Train nhiều batch mã hóa và giữ riêng tập đánh giá

Luồng mới dùng `encrypted-batch-training/0.1.0`, tách endpoint/tệp trạng thái
khỏi prototype một batch. Circuit, build, miền feature và khóa hiện có được
giữ nguyên. Trọng số khởi đầu chỉ mã hóa một lần; sau đó worker đưa trực tiếp
trọng số bản mã của lượt trước vào lượt tiếp theo, không giải mã giữa các batch.

## Phạm vi build hiện tại

| Thành phần | Giới hạn |
|---|---|
| Mỗi batch | Đúng 4 giao dịch, 2 feature binary đã chọn |
| Tập train | 2–4 batch: 8, 12 hoặc 16 giao dịch |
| Tổng cập nhật | Tối đa 4, theo `max_steps` của build hiện có |
| Epoch | Với 2 batch: 1 hoặc 2 epoch; với 3–4 batch: 1 epoch |
| Tập đánh giá giữ riêng | 1–4 batch, tức 4–16 giao dịch |

Không tự tăng `max_steps`, thay TTL worker HE inference cũ, đệm dòng, nhân bản
dòng, bỏ batch thiếu hoặc cắt nguồn. Muốn train lớn hơn phải kiểm chứng và cấp
build/policy mới. Nhiều batch không tự chứng minh model tốt hơn; lượng tử thô
hiện tại vẫn có thể cho cập nhật bằng 0 ở một số phân bố dữ liệu.

## Chốt dữ liệu trước khi mã hóa

Request `snapshot-he-batch-plan/0.1.0` gồm snapshot ID, as_of, hai khoảng thời gian
và danh sách ID/revision theo đúng thứ tự trong từng batch:

```
training_start < training_end <= evaluation_start < evaluation_end <= as_of
train:      [training_start, training_end)
evaluation: [evaluation_start, evaluation_end)
```

Mỗi giao dịch chỉ thuộc một vị trí trên toàn kế hoạch; cấm đưa cùng ID vào hai
phần kể cả khác revision. Không xáo batch theo điểm hoặc nhãn. Snapshot adapter
cũ xây từng batch bằng nguồn point-in-time, cùng feature contract/mapping và
chế độ nguồn. Giao dịch đồng thời vẫn dùng lịch sử trước nhóm. Có lỗi nguồn,
feature, miền hoặc thời gian thì kế hoạch bị từ chối, giữ chi tiết lỗi; không
âm thầm bỏ giao dịch rồi train số còn lại.

Kế hoạch ghim snapshot/checksum, contract/code/mapping, toàn bộ lựa chọn và
window bằng `plan_sha256`. Đổi source/mapping/as_of/lựa chọn phải preview lại.
Tập đánh giá được khóa từ đầu tại DN; không gửi các dòng này hoặc nhãn đánh giá
đến worker train. Worker chỉ nhận cam kết HMAC của hai phần, không nhận danh
sách định danh, X/y rõ hoặc khóa giải mã.

## Nhãn đã khóa

Tạo danh sách xác minh riêng cho từng batch từ chính child request của kế
hoạch. `batch-create-labels` tạo các danh sách trống trong cùng kho nhãn DN để
người rà mở trên màn hình **Xác minh nhãn**. Lệnh không gán nhãn hoặc chạy train.

Sau khi người có quyền xác minh và khóa từng bộ, người chạy train chỉ gửi
`packet_id/revision/lock_sha256` theo thứ tự các batch train. `batch-confirm-locked`
đọc đúng bản khóa từ kho AEAD, kiểm source plan, snapshot/mapping, thứ tự ID và
revision. Không tin nội dung nhãn do người dùng sửa trong tệp export. Người
fit cần `model.fit` và quyền đọc DN, không cần xác minh lại nhãn đã có. Các
reviewer có thể khác người fit, danh tính/thời gian gốc vẫn được giữ.

Nhãn trống chặn toàn phiên train; không tự lọc, đổi thành 0 hoặc thay bằng cảnh
báo luật/ML. Một batch có thể toàn một lớp, nhưng **toàn tập train phải có cả
hai lớp**. Vì vậy cờ `training_ready` của một bộ nhãn riêng lẻ không quyết định
điều kiện của toàn phiên nhiều batch. Điều kiện feature/nhãn vẫn kiểm đầy đủ.

Nhãn mô phỏng giữ `synthetic_expected`. Lệnh `batch-confirm` đọc review JSON chỉ
dùng thử nguồn mô phỏng; nguồn thật bắt buộc `batch-confirm-locked`. Không tự
cấp thêm quyền, thay danh tính workspace hoặc chuyển phiếu rà cũ thành nhãn.

## Thực thi, checkpoint và khôi phục

Cloud dùng endpoint `/v2/datasets`, `/v2/confirm`, `/v2/jobs`; v1 giữ nguyên.
Upload nhiều X bản mã chỉ tạo biên nhận ký, chưa tạo job. Consent ký ghim
dataset/receipt, thứ tự/hash batch, nhãn/phiên bản/cam kết HMAC, key epoch,
build và số epoch. Cùng upload/consent trả lại đúng kết quả cũ; đổi nội dung
cùng ID bị từ chối. Tệp nguồn, biên nhận, cache mã hóa và consent tại DN cũng
được ký và bất biến; mã hóa lại sau gián đoạn dùng đúng cache/key cũ.

Với hai batch A/B, hai epoch: `A → B → A → B`. Không khởi tạo lại trọng số khi
sang B hoặc khi bắt đầu epoch mới. SQLite ghi **weights ciphertext + checksum +
cursor + checkpoint** trong cùng transaction, synchronous FULL. Status có
completed_updates, total_updates, next_batch_index và inflight_update; polling
không phải chờ phép FHE đang chạy. Một process giữ lease của state, chống hai
worker đồng thời mở cùng kho. Yêu cầu run trùng khi đang chạy chỉ trả tiến độ.

Sau hard crash: xác thực lại rồi tiếp tục cùng job. Lượt chưa commit có thể được
tính lại từ trọng số đã commit; không tuyên bố phép tính native đúng một lần.
Lượt đã commit không chạy lại, model đã hoàn tất được đọc từ cache. Mất/sai
khóa, build, nguồn, consent, chữ ký hoặc checksum checkpoint thì từ chối, không
reset về trọng số 0 hoặc tạo phiên thay thế ngầm.

Chỉ khi hoàn tất mới trả model bản mã cho DN giải mã. DN đối chiếu chính xác
với scalar oracle theo đúng lịch batch/epoch và nhãn đã khóa trước khi lưu
candidate. `batch-evaluate` chỉ chấm tập đánh giá đã giữ riêng tại DN bằng
candidate đó; không fit/chọn ngưỡng, không dùng nhãn đánh giá cho train.
Điểm chưa hiệu chuẩn, `accuracy=null`, không kết luận gian lận hoặc đổi hàng đợi.

## Luồng thực hiện trên Portal (`/agent2/batch-training`)

Màn hình `/agent2/batch-training` (kết nối qua `portal/agent2_bridge.py` và `sme_fraud/batch_training_api.py`) chia thành 7 bước tuần tự, mỗi bước một nút thao tác chính, thông tin kỹ thuật/hash đặt trong `<details>`:

1. **Chọn dữ liệu và xem kế hoạch (`POST /api/v1/companies/<company>/batch-training/preview`)**:
   - Chọn doanh nghiệp, snapshot, kỳ train (`training_start < training_end`) và kỳ đánh giá giữ riêng (`evaluation_start < evaluation_end <= as_of`).
   - Kiểm tra qua `prepare_batch_plan`, hiển thị số giao dịch (`8–16` dòng train, `4–16` dòng đánh giá), danh sách batch, lỗi nguồn/feature và ghim `plan_sha256`.
2. **Xác minh nhãn (`POST .../create-labels` & `/agent2/label-verification`)**:
   - Tạo gói xác minh nhãn trong `LabelStore` cho từng batch theo đúng kế hoạch đã ghim và liên kết trực tiếp tới `/agent2/label-verification#company=<cid>&packet=<pid>`.
   - Nhãn chưa rõ giữ `null`. Mỗi batch có thể chỉ có một lớp nhưng tổng hợp các batch train phải có đủ hai lớp `{0, 1}`.
3. **Xác nhận train (`POST .../confirm`)**:
   - Trước nút chính hiển thị rõ: doanh nghiệp, snapshot, số dòng train/đánh giá, số batch, số epoch (`số batch × epoch <= 4`) và tình trạng nhãn.
   - Đọc lại các bản khóa nhãn từ `LabelStore` trên server theo `packet_id`, `revision`, `lock_sha256`; chặn nếu thiếu nhãn, mở khóa lại sau khi tạo, hoặc kế hoạch bị lệch (`plan_sha256`).
   - Điều phối `prepare_snapshot_batches`, `upload_batches`, `confirm_locked_batches` và lưu gắn kết `run_id` ↔ `dataset_id` ↔ `job_id` vào nhật ký AEAD `batch-training.sqlite3`.
4. **Theo dõi tiến độ (`GET .../batch-training` & `POST .../resume`)**:
   - Hiển thị trạng thái tiếng Việt (`Đang chuẩn bị`, `Đang gửi`, `Đang train`, `Bị gián đoạn`, `Hoàn tất — chờ nhận model`, `Lỗi`) và `completed_updates / total_updates`.
   - Tải lại trang hoặc bấm tiếp tục sau gián đoạn sẽ chạy tiếp đúng `job_id` đã lưu, không tạo job mới hay khởi tạo lại trọng số.
5. **Nhận model (`POST .../receive`)**:
   - Chỉ nhận khi worker hoàn tất (`completed_updates == total_updates`). Giải mã tại node doanh nghiệp và kiểm tra đối chiếu `quantized_batch_oracle_exact`.
   - Hiển thị rõ: **Model ứng viên đã nhận và kiểm tra kỹ thuật** (chưa được duyệt sử dụng).
6. **Đánh giá trên tập giữ riêng (`POST .../evaluate`)**:
   - Chạy `evaluate_holdout` trên tập đánh giá giữ riêng đã khóa từ đầu kế hoạch (`held_out_from_training=true`, `uncalibrated=true`, `accuracy=null`, `labels_used_for_fit=false`).
7. **Phê duyệt dùng shadow (`POST .../approve` & `POST .../shadow`)**:
   - Người có quyền `model.fit` nhập lý do (`10–1000` ký tự) và phê duyệt gắn với `candidate_sha256`, `model_cipher_sha256`, `plan_sha256`, `evaluation_sha256`.
   - Trước khi phê duyệt, mọi yêu cầu chấm shadow bị chặn (`BATCH_MODEL_NOT_APPROVED`). Sau khi phê duyệt, model chỉ chạy đối chiếu shadow (`shadow_only=true`, `active_model_replaced=false`, `operational_queue_changed=false`).

## Cách chạy bằng CLI

Ngoài giao diện Portal, có thể dùng operator CLI tại DN; mẫu cấu
hình ở `examples/encrypted_training/batch-config.example.json`, request ở
`batch-request.example.json`. Thay mã snapshot/giao dịch và đường dẫn bằng nguồn
đã lưu của đúng doanh nghiệp. Không đặt mật khẩu hoặc khóa bí mật lên argv.

```powershell
python agent2/scripts/encrypted_training.py batch-preview --config <config.local.json> --token-file <operator-token-file> --data <batch-request.json> --output <preview.json>
```

Xem lỗi và tách kỳ dữ liệu, sau đó ghim `expected_batch_plan_sha256` trong config
đúng giá trị preview đã xem. Các bước tiếp:

1. `batch-create-labels --data <batch-request.json>`: cần quyền `evidence.verify`,
   tạo danh sách trên kho nhãn DN. Người rà xác minh/khóa qua web.
2. `batch-prepare --data <batch-request.json>`: cần `model.fit`, kiểm lại plan
   rồi mã hóa các batch train bằng một context. Không mã hóa/gửi holdout vào fit.
3. `batch-upload`: nhận biên nhận ký.
4. `batch-confirm-locked --labels <ordered-training-locks.json>`: xác nhận train
   với các bản khóa, `batch_epochs` từ config; chưa tính trước thao tác run.
5. `batch-run`: chạy; có thể gọi `batch-status` song song. Sau gián đoạn gọi lại
   `batch-run` với cùng config/enterprise_root, không tạo nguồn hay context mới.
6. `batch-receive`: nhận/giải mã/đối chiếu model tại DN.
7. `batch-evaluate`: xem điểm trên holdout đã giữ riêng.
8. `batch-approve --reason-file <reason.txt>`: ký phê duyệt dùng đối chiếu shadow.
9. `batch-shadow`: chấm đối chiếu shadow trên tập giữ riêng (chặn nếu chưa `batch-approve`).

Mọi lệnh đều có `--config`, `--token-file`, `--output`; output mới để tránh ghi
đè bằng chứng. `label_db` và `node_state_key_file` phải trỏ đúng kho nhãn và khóa
DPAPI của backend DN; không tạo khóa hoặc migrate DB live khi dùng CLI.

## Chấm shadow trên snapshot giao dịch mới và lịch sử `shadow_run`

Sau khi model ứng viên được phê duyệt shadow (`approved_for_shadow = true`), người
vận hành trên Portal (`/agent2/batch-training`, Bước 8) thực hiện luồng:

1. Chọn doanh nghiệp (`C001` hoặc `C002`).
2. Chọn tường minh phiên bản model đã duyệt (`model_run_id`, ghim `model_cipher_sha256`
   và `approval_sha256`; hệ thống không tự động chọn model mới nhất).
3. Chọn snapshot giao dịch mới thuộc cùng doanh nghiệp và mốc `as_of`.
4. Kiểm tra tương thích (`POST /api/v1/companies/{company}/batch-training/shadow-runs/check`)
   và chạy chấm shadow (`POST /api/v1/companies/{company}/batch-training/shadow-runs`).
5. Xem lại từng lần chạy qua `GET .../shadow-runs` và `GET .../shadow-runs/{shadow_run_id}`.

Backend tự tạo feature tại `as_of` từ snapshot đã kiểm checksum (không nhận `x` nhập
tay trên luồng nghiệp vụ), chia lát tối đa `64` dòng mỗi lần gọi `predict_batch_shadow`
tại node doanh nghiệp, và trả đầy đủ mọi dòng giao dịch (`scored`, `unavailable`,
hoặc `incompatible_model`) kèm lịch sử `new_transaction` / `seen_in_training` /
`seen_in_evaluation`. Chi tiết nghiệm thu xem tại `agent2/docs/SHADOW_SNAPSHOT_RUNS_ACCEPTANCE.md`.

## Kiểm chứng và giới hạn

`test_batch_training.py` dùng fake ciphertext để kiểm vòng đời, không phải bằng
chứng HE. `demo_encrypted_training_batches.py` chạy Concrete thật trong worker
WSL riêng: snapshot mô phỏng → batch preview → nhãn khóa → mã hóa X/y → train
hai epoch → nhận/giải mã → holdout và khôi phục hard crash. Có thể tái dùng context
demo mô phỏng đã được phê duyệt để tránh sinh lại khóa lớn; không dùng context live.

Không triển khai cloud public/Portal live, tăng feature, train vô hạn, thay model
đang kích hoạt hoặc chứng minh accuracy trên doanh nghiệp thật. Portal workspace
vẫn chưa định danh từng người; worker tách process/bundle không phải sandbox OS
chống process ác ý cùng tài khoản hoặc bằng chứng mật mã về tính đúng phép tính.
