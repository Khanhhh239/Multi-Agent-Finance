# Báo Cáo Nghiệm Thu Trọn Luồng Portal Huấn Luyện Mã Hóa Nhiều Batch Với Worker Concrete FHE Thật (`C001` & `C002`)

- **Phiên bản báo cáo**: `portal-he-batch-training-acceptance/1.0.0`
- **Thời điểm nghiệm thu**: `2026-11-15T10:16:24Z`
- **Kịch bản tự động tái lập**: [`agent2/scripts/verify_batch_training_portal_he.py`](../scripts/verify_batch_training_portal_he.py)
- **Báo cáo JSON công khai (đã làm sạch)**: [`agent2/reports/portal_he_batch_training_acceptance.json`](../reports/portal_he_batch_training_acceptance.json)

> [!IMPORTANT]
> **Ghi chú bắt buộc về dữ liệu và nhãn**:
> - Toàn bộ nhãn dùng trong đợt nghiệm thu này là **nhãn synthetic kỳ vọng (`synthetic_expected`)** phục vụ kiểm chứng kỹ thuật trọn luồng giao diện Portal + API điều phối + worker Concrete FHE thật; **không phải** kết luận gian lận nghiệp vụ thật (`real_verified_fraud_labels = 0`).
> - Điểm chấm trên tập giữ riêng (`evaluation`) là điểm nội bộ **chưa hiệu chuẩn xác suất (`uncalibrated = true`, `accuracy = null`)** và chỉ phục vụ đối chiếu kỹ thuật / chế độ `shadow`.
> - Model ứng viên sau khi phê duyệt chỉ chạy ở chế độ đối chiếu `shadow` (`shadow_only = true`, `operational_activation = false`, `active_model_replaced = false`, `operational_queue_changed = false`).
> - Khóa bí mật (`context.sealed`, `wrapping.dpapi.json`, `node-signing.dpapi.json`), bản mã và dữ liệu nguồn thô chỉ nằm trong thư mục `.runtime` cục bộ cô lập; báo cáo công khai chỉ lưu mã băm (`sha256`), định danh phiên và trạng thái kiểm chứng.

---

## 1. Môi Trường Nghiệm Thu Cô Lập

| Thành phần | Cấu hình thực tế trong phiên nghiệm thu |
|---|---|
| Trình duyệt điều khiển tự động | Playwright Chromium (headless) thao tác trực tiếp trên `/agent2/batch-training` và `/agent2/label-verification` |
| Portal shell | `portal.server` (cổng loopback cô lập, xác thực qua `X-Session` và `PortalAuthorizer`) |
| Backend doanh nghiệp | `sme_fraud.review_server` + `BatchTrainingManager` + `LabelStore` + `SnapshotStore` + `BatchEnterprise` |
| Worker FHE | `experiments.he_training.worker` chạy trên WSL Debian (`concrete-python 2.9.0`), **không dùng fake/mock** cho mã hóa, tính toán FHE hay giải mã |
| Mã băm mạch FHE (`build_sha256`) | `190e1e67c6b8cb20c5b1879b9205a50faa4b631bb47e4c7d0639e613e3e09f9e` (`max_steps = 4`, 4 dòng × 2 đặc trưng nhị phân mỗi batch) |
| Tenant nghiệm thu | `training-demo` |
| Cấu hình dữ liệu mỗi doanh nghiệp | `8` giao dịch train (`2` batch × `4` dòng), `4` giao dịch đánh giá giữ riêng (`1` batch × `4` dòng), `2` batch train × `2` epoch = `4` bước cập nhật bản mã |
| Kiểm tra cô lập phía Cloud Worker | `cloud_secret_key_absent = true` (0 tệp `context.sealed`, `dpapi`, `labels.sqlite3`, hay `snapshots` trên thư mục cloud; tổng 28 tệp chỉ gồm mã nguồn worker, mạch công khai, khóa đánh giá công khai và bản mã trạng thái) |

---

## 2. Kết Quả 8 Tình Huống Nghiệm Thu Bắt Buộc Trên Trình Duyệt

| # | Tình huống | Doanh nghiệp kiểm thử | Cách thực hiện trên trình duyệt + hệ thống | Kết quả | Bằng chứng chính |
|---|---|---|---|---|---|
| **1** | **Luồng bình thường 7 bước** | `C001`, `C002` | Chọn snapshot → Kiểm tra & ghim kế hoạch → Tạo gói nhãn → Xác minh & khóa nhãn trên `/agent2/label-verification` → Xác nhận train (`2` epoch) → Nhận model ứng viên → Đánh giá trên tập giữ riêng → Phê duyệt & chạy đối chiếu shadow | **PASS** | `C001` giải mã ra `weights_code = [1, 1, -1]`, `C002` giải mã ra `weights_code = [-1, -1, 1]`, cả hai đều đạt `validation = "quantized_batch_oracle_exact"` |
| **2** | **Reload khi đang train** | `C001` | Nhấn reload (`page.reload`) ngay khi worker Concrete FHE thật đang chạy cập nhật bản mã | **PASS** | Trình duyệt giữ đúng doanh nghiệp `C001`, hiển thị `Trạng thái: Đang train · Mã công việc: btr_a5f7f53960d531c39955e7f9d2d289b1`, tiếp tục theo dõi cùng `job_id` |
| **3** | **Mất kết nối trình duyệt** | `C001` | Ngắt mạng trình duyệt (`context.set_offline(True)`) khi worker đang train rồi bật lại (`context.set_offline(False)`) | **PASS** | Worker tiếp tục chạy độc lập; trình duyệt tự đồng bộ lại đúng `job_id = btr_a5f7f53960d531c39955e7f9d2d289b1`, chỉ có duy nhất `1` phiên tại node DN |
| **4** | **Mất phản hồi xác nhận** | `C001` | Cho server nhận và xử lý `POST /confirm` (`HTTP 201`), nhưng chặn phản hồi về trình duyệt (`route.abort("failed")`), sau đó bấm xác nhận lại trên giao diện | **PASS** | Lần bấm lại trả về đúng `job_id = btr_a5f7f53960d531c39955e7f9d2d289b1` và `dataset_id = bds_894f4866d4e5d27863424b8c1ba4d0e3` đã tạo trước đó; không sinh phiên hay job thứ hai (`enterprise_session_count = 1`) |
| **5** | **Worker chết giữa chừng (`SIGKILL`)** | `C001` | Chờ worker hoàn tất bước cập nhật `1/4` và đang chạy bước `2/4` (`completed_updates = 1, inflight_update = 1`), bắn `SIGKILL` vào tiến trình worker của bài test; giao diện báo `Bị gián đoạn`; khởi động lại worker thật và bấm tiếp tục trên giao diện | **PASS** | Tiếp tục đúng `job_id = btr_a5f7f53960d531c39955e7f9d2d289b1` từ trọng số bản mã đã lưu ở bước 1/4, hoàn tất `4/4` bước cập nhật, giữ nguyên `key_epoch`, `build_sha256`, `consent_sha256` |
| **6** | **Đổi qua lại `C001` / `C002` + Reload** | `C001`, `C002` | Chuyển từ `C001` (đã duyệt shadow) sang `C002` (khi chưa có phiên và sau khi hoàn tất), kết hợp reload trang ở mỗi bên | **PASS** | Khi `C002` chưa chạy, giao diện báo `Chưa có phiên huấn luyện batch nào cho doanh nghiệp này.`; sau khi cả hai hoàn tất, mỗi bên giữ đúng `job_id`, gói nhãn và trọng số riêng (`[1, 1, -1]` vs `[-1, -1, 1]`), `cross_company_leakage = false` |
| **7** | **Shadow chưa được duyệt** | `C001` | Sau khi nhận model và chấm tập giữ riêng nhưng chưa phê duyệt, kiểm tra nút giao diện và gọi trực tiếp `POST /api/v1/companies/C001/batch-training/shadow` từ trình duyệt | **PASS** | Giao diện chỉ mở nút `Phê duyệt dùng đối chiếu shadow`; lệnh gọi trực tiếp API `/shadow` bị chặn với `HTTP 409` — mã lỗi `BATCH_MODEL_NOT_APPROVED` |
| **8** | **Shadow sau phê duyệt** | `C001`, `C002` | Nhập lý do phê duyệt, ghim đủ 3 mã băm (`model_cipher_sha256`, `plan_sha256`, `evaluation_sha256`), bấm phê duyệt rồi bấm chạy đối chiếu shadow trên giao diện | **PASS** | Chấm shadow thành công trên 4 giao dịch giữ riêng với `shadow_only = true`, `active_model_replaced = false`, `operational_queue_changed = false` |

---

## 3. Chi Tiết Kết Quả Theo Từng Doanh Nghiệp

### 3.1. Doanh Nghiệp `C001`

- **Kế hoạch dữ liệu & Snapshot**:
  - `snapshot_id`: `snp_e36fa44110b547f2a776c34a98d5216d`
  - Kỳ huấn luyện (`training_window`): `2025-08-11T00:00:00+07:00` → `2025-08-12T00:00:00+07:00` (`8` giao dịch = `2` batch × `4` dòng: `AUDIT_0000`..`AUDIT_0007`)
  - Kỳ đánh giá (`evaluation_window`): `2025-08-12T00:00:00+07:00` → `2025-08-13T00:00:00+07:00` (`4` giao dịch = `1` batch × `4` dòng: `AUDIT_0008`..`AUDIT_0011`)
  - Mốc `as_of`: `2025-08-13T00:00:00+07:00`
  - `plan_sha256`: `cbbb0e13f8a0391b8c0b52a55d4d3011ce29c4a567eca59da050d9050af84515`
- **Gói nhãn xác minh đã khóa trên trình duyệt (`/agent2/label-verification`)**:
  - Train batch #1 (`verified_fraud` synthetic):
    - `packet_id`: `lbl_fe866649380235c64fac794f630495e942b48cce78eab777742404bef1512429`
    - `revision`: `6`
    - `lock_sha256`: `a9641170b4837993110784632257720493d2a2201eb3f05b916172eb494d0074`
  - Train batch #2 (`verified_non_fraud` synthetic):
    - `packet_id`: `lbl_e862e185a5d51219a37f34c2b1cb519bbc8b69b341b6a3a610f5cd31e32fbda5`
    - `revision`: `6`
    - `lock_sha256`: `0df6b9e23e8ae2142ffe08db61c3be777dde4267184a0ecfb7eff37301fba7cc`
  - Evaluation batch #1 (`verified_fraud` synthetic — không đưa vào fit):
    - `packet_id`: `lbl_bc9f91ba2890081641eb9a02af31288fcd87b3c848e33f3cdc6fc3065794db67`
    - `revision`: `6`
    - `lock_sha256`: `1fc38a643d6cdb4a562bea9fe16b54e1529a2c3a16ad33c426061f84a21f7375`
- **Định danh phiên huấn luyện mã hóa & Worker**:
  - `dataset_id`: `bds_894f4866d4e5d27863424b8c1ba4d0e3`
  - `job_id`: `btr_a5f7f53960d531c39955e7f9d2d289b1`
  - `consent_sha256`: `a5f7f53960d531c39955e7f9d2d289b1ddae5627af0aca205ef1ccf13c087d12`
  - `key_epoch`: `key_79948863a9bb31ed540e6ed63c2f6b55`
  - `build_sha256`: `190e1e67c6b8cb20c5b1879b9205a50faa4b631bb47e4c7d0639e613e3e09f9e`
  - `batch_manifest_sha256`: `64f324b6949acd6e2e5c97ef72342ad8884466efe3e168ea236b09d54a9800da`
  - `training_commitment`: `b5087b2815966241a4dbeb51488bb8190a577c767b4c633b1ff57da530fffaa2`
  - `evaluation_commitment`: `e22f627b6b9d2d79dfd610e3e00a3acfb62c17fdfd43c1a500f4620af788d714`
  - Tiến độ & Khôi phục: `completed_updates = 4 / 4` (`2` batch × `2` epoch), đã vượt qua bài thử `SIGKILL` tại `completed_updates = 1, inflight_update = 1` và resume từ giao diện.
- **Model ứng viên nhận tại doanh nghiệp**:
  - `model_cipher_sha256`: `0b556814858303225a6b6e70b0c76eed318a266d54805891edcb86cc6a4d23fe`
  - `weights_code`: `[1, 1, -1]` (`coefficients = [0.5, 0.5]`, `intercept = -0.5`)
  - Đối chiếu kỹ thuật: `validation = "quantized_batch_oracle_exact"` (`oracle_exact_match = true`)
- **Đánh giá trên tập giữ riêng (`holdout`) & Phê duyệt `shadow`**:
  - `evaluation_sha256`: `4ae02f15fc12e559c309d11a386cd89e31871d54cb939ae56f52dc8482c9062c`
  - `held_out_from_training = true`, `labels_used_for_fit = false`, `uncalibrated = true`, `accuracy = null`
  - Điểm chấm 4 dòng giữ riêng: `AUDIT_0008 = 0.622459`, `AUDIT_0009 = 0.377541`, `AUDIT_0010 = 0.622459`, `AUDIT_0011 = 0.377541`
  - `approval_sha256`: `66163c5661e4147355a8456aab4fd78d1fe5e8dbfc7beda3d164c1502b2e5cae`
  - Trạng thái vận hành: `approved_for_shadow = true`, `shadow_only = true`, `operational_activation = false`, `active_model_replaced = false`, `operational_queue_changed = false`

---

### 3.2. Doanh Nghiệp `C002`

- **Kế hoạch dữ liệu & Snapshot**:
  - `snapshot_id`: `snp_ffa276bf7fea4724a15d7578f45508fb`
  - Kỳ huấn luyện (`training_window`): `2025-08-11T00:00:00+07:00` → `2025-08-12T00:00:00+07:00` (`8` giao dịch = `2` batch × `4` dòng: `AUDIT_0000`..`AUDIT_0007`)
  - Kỳ đánh giá (`evaluation_window`): `2025-08-12T00:00:00+07:00` → `2025-08-13T00:00:00+07:00` (`4` giao dịch = `1` batch × `4` dòng: `AUDIT_0008`..`AUDIT_0011`)
  - Mốc `as_of`: `2025-08-13T00:00:00+07:00`
  - `plan_sha256`: `3eb147183ab6b46c39f5ed4c653e26c3be8fda0b08dc30e0efbe27cebd971fb9`
- **Gói nhãn xác minh đã khóa trên trình duyệt (`/agent2/label-verification`)**:
  - Train batch #1 (`verified_non_fraud` synthetic):
    - `packet_id`: `lbl_8d2ec547171980da7143d8a5582b93a733eac2536813dc5abb4263c1bcefd4d4`
    - `revision`: `6`
    - `lock_sha256`: `26caad2bcbe006565b4799d4e6445b7eae203596b1895209598b9bffdd5cfa0d`
  - Train batch #2 (`verified_fraud` synthetic):
    - `packet_id`: `lbl_2978ea0dbef14f204411aeff0b7204bc5acb8e809970cb7d9ec6c15dafb3a3fa`
    - `revision`: `6`
    - `lock_sha256`: `c5872e7b9bfba893d904d3cc3a13ea628f8b87778a53ce0ee1f505c69ddfc8f0`
  - Evaluation batch #1 (`verified_non_fraud` synthetic — không đưa vào fit):
    - `packet_id`: `lbl_244005f3130a2e1e123695bbca322d9ab9f9688d7e74750f9a1380b20ec7317e`
    - `revision`: `6`
    - `lock_sha256`: `6fb780046fef8493de224b6b25332c48a37c89a8bd95a40d6af3c7e76b374f7c`
- **Định danh phiên huấn luyện mã hóa & Worker**:
  - `dataset_id`: `bds_0d705dcc2d3c1cbd5cd3187da1316272`
  - `job_id`: `btr_e63f486e2f3c237bb1eb7afcde6cbea5`
  - `consent_sha256`: `e63f486e2f3c237bb1eb7afcde6cbea5d271d1bcb607b574f34675974a04e5e2`
  - `key_epoch`: `key_9c233a47a85f8b8791fad44ae9ade86d`
  - `build_sha256`: `190e1e67c6b8cb20c5b1879b9205a50faa4b631bb47e4c7d0639e613e3e09f9e`
  - `batch_manifest_sha256`: `3e7dc1b37beb5793b8ccb0ef249c2a4d8ac95917c550f73c1cb3f22ad96939e0`
  - `training_commitment`: `876557692fc90f367f6f757edef0a286e85e487dc212d8e3298895da80dfe596`
  - `evaluation_commitment`: `e1d2ed1909f28e849777e1e3f3dd8b698f0230f0953352f615fea2c115ebd8ff`
  - Tiến độ: `completed_updates = 4 / 4` (`2` batch × `2` epoch)
- **Model ứng viên nhận tại doanh nghiệp**:
  - `model_cipher_sha256`: `a5edcc80bdb2d94151ec0f753ad47a7b027a0688951a832dca50ab81923d9063`
  - `weights_code`: `[-1, -1, 1]` (`coefficients = [-0.5, -0.5]`, `intercept = 0.5`)
  - Đối chiếu kỹ thuật: `validation = "quantized_batch_oracle_exact"` (`oracle_exact_match = true`)
- **Đánh giá trên tập giữ riêng (`holdout`) & Phê duyệt `shadow`**:
  - `evaluation_sha256`: `832d09ea611616ff889dd63dbfbe7bfdd8224ee5f6088a1a9d510372f6ed053b`
  - `held_out_from_training = true`, `labels_used_for_fit = false`, `uncalibrated = true`, `accuracy = null`
  - Điểm chấm 4 dòng giữ riêng: `AUDIT_0008 = 0.377541`, `AUDIT_0009 = 0.622459`, `AUDIT_0010 = 0.377541`, `AUDIT_0011 = 0.622459`
  - `approval_sha256`: `40ac9341561f20caf35df0c945d02bb7ce34a23d827cf76ddbbb22b655acb6bb`
  - Trạng thái vận hành: `approved_for_shadow = true`, `shadow_only = true`, `operational_activation = false`, `active_model_replaced = false`, `operational_queue_changed = false`

---

## 4. Các Điểm Lệch Phát Hiện Khi Ghép Giao Diện + Điều Phối + Worker Concrete FHE Thật Và Đã Sửa

Khi chuyển từ bộ kiểm thử `FakeEnterprise` sang chạy trình duyệt thật với `BatchEnterprise` + WSL `Concrete FHE 2.9.0`, có **4 điểm lệch thực tế** đã được phát hiện và khắc phục triệt để:

1. **Ánh xạ mã giao dịch từ snapshot `agent2-rule-snapshot/1.0.0` lên danh sách chọn batch trên giao diện ([`batch_training_api.py`](../sme_fraud/batch_training_api.py))**:
   - Bản ghi trong `source.tables.transactions` của `agent2-rule-snapshot/1.0.0` có cả `record_id` (`tx-rec-0`) và `transaction_id` (`AUDIT_0000`), trong khi bộ tạo kế hoạch `prepare_snapshot_training` định danh giao dịch theo `transaction_id`.
   - Đã sửa `_list_company_snapshots` ưu tiên `tx.get("transaction_id") or tx.get("record_id")` và `posted_at / occurred_at / effective_at`, giúp giao diện tự điền đúng `AUDIT_0000`..`AUDIT_0011` ngay khi chọn snapshot.
2. **Giữ lựa chọn số `epochs` trên giao diện trước khi bấm xác nhận train ([`batch-training.js`](../sme_fraud/web/batch-training.js), [`batch_training_api.py`](../sme_fraud/batch_training_api.py))**:
   - Trước đây `preview` gán sẵn `epochs = 1` vào trạng thái phiên và sự kiện `change` của `#bt-epochs` gọi `renderConfirmSection()` ghi đè ngược lại giá trị `1`, làm người dùng không đổi sang `2` epoch trên trình duyệt được.
   - Đã sửa `preview` để `epochs = None` trước khi confirm và chỉ đồng bộ `#bt-epochs` từ server sau khi `job_id` đã được khóa.
3. **Chế độ chạy bất đồng bộ (`run_mode = "async"`), polling tiến độ trực tiếp và tránh tranh chấp GIL khi worker nạp khóa đánh giá 1.35 GB ([`batch-training.js`](../sme_fraud/web/batch-training.js), [`batch_training_api.py`](../sme_fraud/batch_training_api.py), [`portal/agent2_bridge.py`](../../portal/agent2_bridge.py))**:
   - Với worker Concrete FHE thật, bước `confirm` phải mã hóa 2 batch dữ liệu (`encrypt-data` × 2) và 2 batch nhãn (`encrypt-batch-labels` × 2) qua WSL (~115–120 giây), và bước cập nhật đầu tiên trên worker nạp tệp `evaluation.keys` nặng ~1.35 GB.
   - Đã nâng timeout proxy `open_backend` trong `portal/agent2_bridge.py` lên `600s` (đồng bộ với `enterprise.py` và `worker.py`), tách việc trả phản hồi `confirm`/`resume` trước khi luồng chạy nền gửi lệnh `run` tới worker, bỏ tính lại `prepare_batch_plan` không cần thiết trong các lệnh poll trạng thái khi đã vào pha `training`, và bật tự động polling tiến độ trên giao diện trình duyệt.
4. **Idempotency khi trình duyệt mất phản hồi `POST /confirm` ([`batch_training_api.py`](../sme_fraud/batch_training_api.py))**:
   - Khi server đã hoàn tất `confirm` và tạo `job_id` nhưng phản hồi HTTP về trình duyệt bị đứt mạng, lần bấm xác nhận lại trên trình duyệt sẽ sinh `Idempotency-Key` mới kèm `expected_revision` cũ.
   - Đã bổ sung kiểm tra idempotent theo `(plan_sha256, epochs, locks)` trên phiên hiện tại để trả về lại đúng `job_id` và `dataset_id` đã tạo mà không sinh phiên hay job trùng lặp.

