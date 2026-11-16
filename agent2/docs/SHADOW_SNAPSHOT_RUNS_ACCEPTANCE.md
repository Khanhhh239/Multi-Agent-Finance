# Báo cáo nghiệm thu: Chấm đối chiếu Shadow trên Snapshot giao dịch mới và Lịch sử lần chạy (`shadow_run`)

## 1. Phạm vi và luồng nghiệp vụ đã hoàn thiện

Luồng nghiệp vụ chấm đối chiếu shadow trên snapshot giao dịch mới đã được nối trọn vẹn từ giao diện Portal (`/agent2/batch-training`, **Bước 8**), qua cầu nối bảo mật (`portal/agent2_bridge.py`), tới điều phối viên tại node doanh nghiệp (`agent2/sme_fraud/batch_training_api.py`, `agent2/sme_fraud/review_server.py`) và kho lưu trữ mã hóa (`batch-training.sqlite3`):

1. **Chọn doanh nghiệp (`C001` / `C002`)**: Danh sách model và snapshot được cô lập nghiêm ngặt theo `(tenant_id, company_id)`.
2. **Chọn model đã duyệt (`approved_for_shadow = True`)**:
   - Giao diện chỉ liệt kê các phiên bản model đã được Giám đốc phê duyệt shadow của đúng doanh nghiệp đang chọn.
   - **Không tự động chọn model mới nhất** khi mở trang, tải lại trang hoặc đổi doanh nghiệp (`initial_selected_model = ""`), buộc người vận hành chọn tường minh phiên bản model cần chạy (`model_run_id`, ghim `model_cipher_sha256` và `approval_sha256`).
3. **Chọn snapshot giao dịch mới và mốc thời gian `as_of`**:
   - Cho phép chọn bất kỳ snapshot đã chốt (`committed`) thuộc cùng doanh nghiệp (kể cả khác snapshot huấn luyện).
   - Loại bỏ toàn bộ đường nhập tay ma trận feature (`x`, `features`) khỏi luồng nghiệp vụ (`400 SHADOW_MANUAL_FEATURES_FORBIDDEN`); đường nhập `x` thủ công tại endpoint kỹ thuật cũ chỉ mang nhãn `technical_manual_features_test_only`.
4. **Kiểm tra tương thích hợp đồng (`POST .../shadow-runs/check`)**:
   - Backend tự dựng bộ 33 feature chuẩn tại thời điểm `as_of` từ snapshot đã kiểm checksum (`build_from_rule_snapshot` cho `agent2-rule-snapshot/1.0.0` hoặc `build_from_snapshot` cho `1.0.0`).
   - Ánh xạ sang cặp 2 feature nhị phân đúng thứ tự cột `["round_million", "creator_equals_approver"]` (`existing-binary-pair/1.0.0`).
   - Đối chiếu chặt chẽ với metadata đã ghim khi huấn luyện model: `company_id`, `tenant_id`, `feature_names`, `source_contract_version`, `source_contract_fingerprint`, `mapping_version`, `mapping_fingerprint`, miền giá trị `{0, 1}`, chính sách thiếu dữ liệu và chế độ `simulated`.
5. **Chạy chấm shadow và lưu kết quả (`POST .../shadow-runs`)**:
   - Kết quả được lưu bất biến (append-only, mã hóa AES-GCM) vào bảng `batch_shadow_runs` với mã định danh `shadow_run_id` (`shrun_<seq>_<hash>`).
   - Trả về **đầy đủ mọi giao dịch của doanh nghiệp trong snapshot** (không âm thầm rơi dòng thiếu nguồn, dòng sau `as_of`, hay dòng không tương thích hợp đồng).
   - Tự động chia lát tối đa `64` dòng đủ điều kiện mỗi lần gọi `BatchEnterprise.predict_batch_shadow` (không áp giới hạn 4 dòng/batch của bước huấn luyện và không cắt cụt ở 64 dòng).

---

## 2. Minh bạch vị trí tính toán và giới hạn vận hành

Giao diện Bước 8 và mỗi bản ghi `shadow_run` đều công bố rõ ràng:

- **Vị trí thực thi (`execution_location = "enterprise_node_decrypted_candidate"`)**: Điểm shadow được tính trực tiếp tại **node doanh nghiệp** bằng model ứng viên đã giải mã локально và đã được phê duyệt shadow (`BatchEnterprise.predict_batch_shadow`). Không thực hiện suy luận FHE trên cloud (`cloud_he_inference_performed = false`).
- **Tính chất điểm số (`uncalibrated = true`)**: Điểm dự đoán từ mô hình hồi quy logistic lượng tử hóa dùng để xếp hạng đối chiếu nội bộ, **chưa hiệu chuẩn xác suất**.
- **An toàn vận hành (`active_model_replaced = false`, `operational_queue_changed = false`)**: Chạy chấm shadow chỉ lưu lịch sử đối chiếu, **không tự thay thế model đang vận hành** và **không tự động đẩy giao dịch vào hàng đợi rà soát chính thức**.

---

## 3. Bảng kết quả nghiệm thu toàn luồng (Playwright Chromium + Node DN thật)

Kịch bản nghiệm thu tự động [`agent2/scripts/verify_shadow_snapshot_runs.py`](file:///D:/agent22/agent2/scripts/verify_shadow_snapshot_runs.py) khởi chạy Portal thật, Agent2 Review Server thật, kho khóa/model Concrete FHE thật của `C001` và `C002`, và điều khiển trình duyệt headless Chromium qua Playwright. Báo cáo JSON chi tiết được lưu tại [`agent2/reports/shadow_snapshot_runs_acceptance.json`](file:///D:/agent22/agent2/reports/shadow_snapshot_runs_acceptance.json).

| STT | Tình huống nghiệm thu | Mã `shadow_run_id` / HTTP | Kết quả thực tế | Đánh giá |
| :--- | :--- | :--- | :--- | :--- |
| **0** | Không tự động chọn model mới nhất khi mở trang hoặc đổi DN | UI `#bt-shadow-model` | Giá trị mặc định `""`; nút *Kiểm tra tương thích* và *Chạy chấm shadow* đều khóa cho đến khi người dùng chọn rõ model & snapshot | **ĐẠT (`PASS`)** |
| **1 & 2** | Snapshot mới (7 dòng) có giao dịch đủ nguồn, giao dịch thiếu `approver_id` và giao dịch có `available_at > as_of` | `shrun_1_f1979903dba1d8c7` | Trả đủ `7/7` dòng: `5` dòng `scored` (`score` từ `0.377541` đến `0.622459`, có `score_rank` `1..5`), `1` dòng `unavailable` (`FEATURE_MISSING` tại `creator_equals_approver`, không tự điền `0`), `1` dòng `unavailable` (`ROW_NOT_AVAILABLE_AT_AS_OF`). Phục hồi nguyên vẹn sau khi nhấn F5 tải lại trang | **ĐẠT (`PASS`)** |
| **3** | Snapshot lớn (`70` giao dịch `> 64` giới hạn một lần gọi `predict_batch_shadow`) | `shrun_2_e33d5131745e940d` | Chấm đủ `70/70` giao dịch qua `2` lần gọi liên tiếp (`64` dòng + `6` dòng); `truncated_to_64 = false`, `training_four_row_limit_applied = false` | **ĐẠT (`PASS`)** |
| **4** | Chấm lại trên snapshot có giao dịch thuộc tập train (8 dòng) và tập đánh giá giữ riêng (4 dòng) | `shrun_3_fd31b176e9799938` | Gắn nhãn `history_status` chính xác: `seen_in_training_rows = 8`, `seen_in_evaluation_rows = 4`, `new_transaction_rows = 0`; đồng thời hiển thị cảnh báo trùng tập dữ liệu huấn luyện/đánh giá | **ĐẠT (`PASS`)** |
| **5** | Model chưa duyệt shadow (`approved_for_shadow = false`) | HTTP `409 Conflict` | Bị chặn trên UI (không xuất hiện trong dropdown) và bị chặn tại API với mã lỗi `BATCH_MODEL_NOT_APPROVED` | **ĐẠT (`PASS`)** |
| **6** | Snapshot không khớp hợp đồng feature (`canonical 1.0.0` so với model train từ `agent2-rule-snapshot/1.0.0`) | `shrun_4_331da8b149098937` | Phát hiện `3` lệch hợp đồng (`source_contract_version`, `source_contract_fingerprint`, `mapping_fingerprint`); giữ nguyên `4/4` dòng với `status = "incompatible_model"`, `score = null` | **ĐẠT (`PASS`)** |
| **7** | Chứng từ/phê duyệt đến muộn (`observed_at > as_of`, `approved_at > as_of`) | `shrun_5_d13542b6a2d32c0b` | Khi chấm tại cùng `as_of = 2025-09-02T00:00:00+07:00`, toàn bộ `7/7` dòng giữ nguyên trạng thái, vector feature và điểm số y hệt `shrun_1_f1979903dba1d8c7` | **ĐẠT (`PASS`)** |
| **8** | Idempotency và bảo toàn lịch sử nhiều lần chạy | `5` bản ghi `C001` | Chạy lại cùng `(model_run_id, snapshot_id, as_of)` trả lại đúng `shrun_5_d13542b6a2d32c0b` (`reused_existing = true`), không sinh bản ghi trùng; toàn bộ 5 lần chạy trước của `C001` vẫn xem lại được đầy đủ | **ĐẠT (`PASS`)** |
| **9** | Cô lập đa doanh nghiệp (`C001` vs `C002`) và chặn nhập feature thủ công | `shrun_6_289b852f7af7cd5e` / HTTP `404` & `400` | Đổi sang `C002` chỉ thấy model `btrun_1_3eb147183ab6b46c39f5` (`weights_code = [-1, -1, 1]`, ngược dấu `C001`), chấm `5` giao dịch (`4` `scored`, `1` `unavailable`). Gọi chéo model/snapshot giữa `C001` và `C002` bị từ chối `404`; gửi `x` thủ công bị từ chối `400 SHADOW_MANUAL_FEATURES_FORBIDDEN` | **ĐẠT (`PASS`)** |

---

## 4. Chi tiết đối chiếu dòng giao dịch tiêu biểu (`C001` và `C002`)

### 4.1. Doanh nghiệp `C001` — Model `btrun_1_cbbb0e13f8a0391b8c0b` (`weights_code = [1, 1, -1]`)
Snapshot `snp_653e67d0c6fd42598edcf2410e076f40` tại `as_of = 2025-09-02T00:00:00+07:00` (`shrun_1_f1979903dba1d8c7`):

| Mã giao dịch | Quan hệ lịch sử | Feature `[round_million, creator_equals_approver]` | Trạng thái | Điểm shadow | Hạng (`score_rank`) | Mã lý do (`issues`) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `C001_NEW_11` | `new_transaction` | `[1, 1]` | `scored` | `0.622459` | `#1` | — |
| `AUDIT_0000` | `seen_in_training` | `[1, 1]` | `scored` | `0.622459` | `#2` | — |
| `C001_NEW_10` | `new_transaction` | `[1, 0]` | `scored` | `0.500000` | `#3` | — |
| `C001_NEW_01` | `new_transaction` | `[0, 1]` | `scored` | `0.500000` | `#4` | — |
| `C001_NEW_00` | `new_transaction` | `[0, 0]` | `scored` | `0.377541` | `#5` | — |
| `C001_MISSING_APPROVER` | `new_transaction` | `[1, null]` | `unavailable` | `null` | `null` | `FEATURE_MISSING` |
| `C001_AFTER_CUTOFF` | `new_transaction` | `[null, null]` | `unavailable` | `null` | `null` | `ROW_NOT_AVAILABLE_AT_AS_OF` |

### 4.2. Doanh nghiệp `C002` — Model `btrun_1_3eb147183ab6b46c39f5` (`weights_code = [-1, -1, 1]`)
Snapshot `snp_c6d56f3269c0486da9e4b906c218d541` tại `as_of = 2025-09-10T00:00:00+07:00` (`shrun_6_289b852f7af7cd5e`):
- Giao dịch `C002_NEW_00` (`[0, 0]`) đạt điểm cao nhất `0.622459` (`#1`), còn `C002_NEW_11` (`[1, 1]`) có điểm `0.377541` (`#4`), phản ánh đúng bộ trọng số ngược dấu đã học riêng của `C002`.
- Giao dịch `C002_MISSING_APPROVER` (`[1, null]`) được giữ nguyên với trạng thái `unavailable` (`FEATURE_MISSING`), không bị loại bỏ hay tự gán `0`.

