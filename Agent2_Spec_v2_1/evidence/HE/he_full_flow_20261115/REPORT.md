# Báo cáo Nghiệm thu Đầy đủ Luồng HE Thực trên Hồ sơ `agent2-rule-snapshot/1.0.0` (`he4-enterprise/1.1.0`)

**Ngày lập:** 2026-11-15  
**Chế độ xác thực chính:** `real_concrete_http_fhe` (`concrete-python 2.11.0` trong WSL Debian qua HTTP Worker `experiments.he4.service`)  
**Dữ liệu gốc tổng hợp:**
- [full_flow_metrics.json](file:///D:/agent22/Agent2_Spec_v2_1/evidence/HE/he_full_flow_20261115/full_flow_metrics.json) (timestamp: `2026-11-15T13:15:44.458809+07:00`)
- [next_rule_assessment.json](file:///D:/agent22/Agent2_Spec_v2_1/evidence/HE/he_full_flow_20261115/next_rule_assessment.json)
- Kiến trúc & mã nguồn kiểm chứng: [rule_snapshot_coordinator.py](file:///D:/agent22/agent2/experiments/he4/rule_snapshot_coordinator.py), [coordinator.py](file:///D:/agent22/agent2/experiments/he4/coordinator.py), [web.py](file:///D:/agent22/agent2/experiments/he4/web.py), [blob_store.py](file:///D:/agent22/agent2/experiments/he4/blob_store.py), [he_result_view.py](file:///D:/agent22/agent2/sme_fraud/he_result_view.py), [he_workbench.py](file:///D:/agent22/agent2/sme_fraud/he_workbench.py), [verify_he_full_flow.py](file:///D:/agent22/agent2/scripts/verify_he_full_flow.py)

> [!IMPORTANT]
> Toàn bộ chạy kiểm chứng thực nghiệm (`task-3216`, [verify_he_full_flow.py](file:///D:/agent22/agent2/scripts/verify_he_full_flow.py)) chạy trên sandbox tách biệt hoàn toàn với Portal live (`8800`), không thay đổi cấu hình live `he4-enterprise/1.0.0` (`8869`/`8868`), không lưu khóa bí mật hay bản mã thô trong repo, và **không có fallback plaintext** hoặc cắt bớt dữ liệu vượt miền mạch Concrete.

---

## 1. Bảng Độ Phủ 35 Luật Trung Thực (`agent2-rule-snapshot/1.0.0`)

Theo định nghĩa 35 luật trong [`RULE_NAMES`](file:///D:/agent22/agent2/sme_fraud/rules.py#L40-L82) và bảng nguồn bắt buộc [`REQUIRED`](file:///D:/agent22/agent2/sme_fraud/native_rule_node.py#L21-L46), hiện trạng giữa chạy **Local Node doanh nghiệp (`agent2-rule-snapshot/1.0.0`)** và **Mã hóa đồng cấu thực (`Concrete FHE`)** được phân tách rạch ròi:

- **5/35 luật đã nối trọn luồng FHE thực qua HTTP Worker & Portal sandbox (`he4-enterprise/1.1.0`):** `P1`, `C3`, `B1`, `B5`, `E4` (trên 3 mạch Concrete: `rules`, `c3`, `graph`).
- **30/35 luật còn lại:** Đã đạt chuẩn đối chiếu tại node doanh nghiệp (`Plain Parity`), nhưng **chưa có mạch FHE cho hồ sơ `agent2-rule-snapshot/1.0.0`**. Trong lần chạy HE, các luật này (cùng nhánh `statistics` và `ml` bridge 33 feature / Isolation Forest / ECOD) báo rõ `unavailable` với mã `rule_snapshot_he_unsupported` và được tóm tắt tại `unsupported_summary.unencrypted_rule_count = 30`.
- **Các nhánh HE di sản trên `canonical 1.1.0` (`he4-enterprise/1.0.0`):** Nhánh `statistics` (RobustZ 2 biến giới hạn) và `ml` (CKKS Mahalanobis 2 feature) giữ tách biệt hoàn toàn, không gán nhầm cho bridge 33 feature hoặc cho hồ sơ 35 luật.

### 1.1. Nhóm 5 Luật Đã Nối Trọn Luồng Real Concrete FHE (`HE5`)

| Mã luật | Tên nghiệp vụ & Trọng số (`rules.py`) | Design | Plain Parity | Native / Real HE | HTTP Worker | Recovery (`R1–R4`) | Portal (`1.1.0`) | Limits / Quy tắc Fail-Closed | Evidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **P1** | Thanh toán vượt tổng giá trị cùng hóa đơn (`W=20`, Hard Trigger) | Đủ | Đạt | Đạt (`rules` / `build-rules-difference-v1`, 128-bit accumulator từ `int64`) | Đạt (`/v1/admit`, `/v1/evaluate`, `/v1/resume`) | Đạt (`R1–R4`) | Đạt (`he-rule-snapshot-groups-result/1.0.0`, sandbox FourWorkbench) | Tối đa `PRIOR_ROWS=4`, `CURRENT_ROWS=4`, `CAP_ROWS=4`; prior `<= 0` -> `he_p1_nonpositive_prior_unsupported`; vượt 4 dòng -> `he_p1_source_limit`; `amount_vnd < 0` bị schema `agent2-rule-snapshot/1.0.0` từ chối (`rejected_schema`) | [rule_snapshot_adapter.py](file:///D:/agent22/agent2/experiments/he4/rule_snapshot_adapter.py), `P1_01`–`P1_06` |
| **C3** | Duyệt dưới 60 giây ở cấp thẩm quyền cao (`W=8`) | Đủ | Đạt | Đạt (`c3` / `build-c3-v1`, 64-bit signed epoch $\mu s$) | Đạt (`/v1/admit`, `/v1/evaluate`, `/v1/resume`) | Đạt (`R1–R4` + OS `SIGKILL`) | Đạt | Tối đa `MAX_AUTHORITIES=4` quy tắc ứng viên; `INT64_MIN..INT64_MAX`; $0 \le \Delta t_{\mu s} < 60{,}000{,}000$; thiếu phạm vi/xung đột -> `authority_not_covered_or_ambiguous_at_action`; vượt 4 -> `he_c3_authority_limit` | [c3_circuit.py](file:///D:/agent22/agent2/experiments/he4/c3_circuit.py), [rule_snapshot_c3_adapter.py](file:///D:/agent22/agent2/experiments/he4/rule_snapshot_c3_adapter.py), `C3_01`–`C3_07` |
| **B1** | Tài khoản hoặc căn cước NCC trùng nhân viên (`W=20`, Hard Trigger) | Đủ | Đạt | Đạt (`graph` / `build-graph-difference-v1`, nibble SHA-256) | Đạt | Đạt (`R1–R4`) | Đạt | Tối đa `GRAPH_NODES=4` (1 giao dịch/NCC + $\le 3$ nhân viên), `GRAPH_FIELDS=4`, `TOKEN_DIGITS=64`; quá 4 nút -> `he_graph_node_limit`; TK không mã ngân hàng -> `recipient_bank_identity_incomplete` (trùng mờ riêng); giảm mức công bố liên quan | [rule_snapshot_identity_adapter.py](file:///D:/agent22/agent2/experiments/he4/rule_snapshot_identity_adapter.py), `B1_01`–`B1_06` |
| **B5** | Nhiều NCC chung thông tin định danh (`W=3`, family `master_quality`) | Đủ | Đạt | Đạt (`graph` thống nhất nhóm `b5_e4`) | Đạt | Đạt (`R1–R4`) | Đạt | Tối đa 4 NCC/nhóm (`GRAPH_NODES=4`); giữ phân biệt `shared_address_only` (yếu) và `shared_bank_or_phone` (mạnh); khóa đếm trùng family với `E4` | [rule_snapshot_identity_adapter.py](file:///D:/agent22/agent2/experiments/he4/rule_snapshot_identity_adapter.py), `B5E4_01`–`B5E4_04` |
| **E4** | NCC trùng định danh (`W=3`, family `master_duplicate`) | Đủ | Đạt | Đạt (`graph` thống nhất nhóm `b5_e4`) | Đạt | Đạt (`R1–R4`) | Đạt | Dùng chung mạch & rào giới hạn 4 nút như `B5`; không cộng điểm kép khi cùng căn cứ với `B5` | [rule_snapshot_identity_adapter.py](file:///D:/agent22/agent2/experiments/he4/rule_snapshot_identity_adapter.py), `B5E4_01`–`B5E4_04` |

### 1.2. Nhóm 30 Luật Chưa Có HE Thực (`Local Only — rule_snapshot_he_unsupported`)

Toàn bộ 30 luật dưới đây đạt **Design = Đủ**, **Plain Parity = Đạt** tại node doanh nghiệp (`native_rule_node.py`), và đang là **No / Deferred** ở 4 cột HE (`Native / Real HE`, `HTTP Worker`, `Recovery`, `Portal HE`). Kết quả HE trả về `unsupported_summary` minh bạch thay vì giả lập mã hóa.

| Nhóm | Các mã luật (`RULE_NAMES`) | Nguồn yêu cầu chính (`REQUIRED`) | Đánh giá HE thực tế & Ghi chú giới hạn |
| :--- | :--- | :--- | :--- |
| **Nhóm A (Chia nhỏ & Số tiền bất thường)** | **A1** (`W=8`), **A2** (`W=4`), **A3** (`W=8`), **A4** (`W=3`), **A5** (`W=3`), **A6** (`W=8`) | `transactions`, `employees`, `vendors`, `payment_requests`, `procurement_links`, `transaction_documents`, `supplier_payment_agreements`, `entity_links`, `recurring_payments`, `journal_documents`, `journal_lines` | `A1–A4` cần gom cụm cửa sổ dài (`3`/`30` ngày, `entity_links`, baseline thống kê). **`A6`** đã được benchmark thực nghiệm (`next_rule_assessment.json`): cho **0** cảnh báo tăng thêm ngoài `HE5` và **thất bại khi biên dịch Concrete trực tiếp** do lỗi `uint24` table lookup (Concrete giới hạn LUT $\le 16$-bit; `peak_rss_mb=340.6`). |
| **Nhóm B (Hồ sơ & Trạng thái NCC)** | **B2** (`W=8`), **B3** (`W=8`), **B4** (`W=10`), **B6** (`W=8`), **B7** (`W=20`, Hard Trigger) | `vendors`, `employees`, `entity_links`, `procurement_links`, `vendor_status_history`, `tax_risk_history`, `vendor_payment_schedules`, `bank_account_changes` | Cần chuỗi lịch sử trạng thái/ngày thay đổi TK ngân hàng (`bank_account_changes`, `vendor_status_history`) theo mốc `as_of`; chưa thiết kế mạch FHE. |
| **Nhóm C (Lịch, Quyền & Nghỉ phép)** | **C1** (`W=1`), **C2** (`W=20`, Hard Trigger), **C4** (`W=8`) | `companies`, `calendar`, `operating_schedules`, `approval_authorities`, `approval_authority_coverage`, `leave_periods`, `system_actions`, `leave_activity_authorizations` | **`C2` là ứng viên số 1 cho lát cắt HE kế tiếp**: dùng chung 100% bảng với `C3`, đạt **+30 cảnh báo tăng thêm ngoài `HE5`** trên `670` giao dịch và biên dịch sạch bằng `Concrete` (`bit_width=1`, `compile_s=0.379s`, xem mục 1.3). `C1`, `C4` phụ thuộc lịch công ty/nghỉ phép, chưa nối HE. |
| **Nhóm D (Benford & Đuôi số)** | **D1**, **D2**, **D3**, **D4**, **D5**, **D6** | `transactions`, `employees` (+ baseline phân bố) | Thống kê phân bố chữ số / MAD bậc thập phân trên tập lịch sử; phù hợp chạy local hoặc tiền xử lý có kiểm soát hơn là mạch Concrete từng dòng. |
| **Nhóm E (Nhân sự, Lương & Tên NCC)** | **E1** (`W=20`, Hard Trigger), **E2** (`W=20`, Hard Trigger), **E3** (`W=3`) | `attendance`, `payroll_entitlements`, `employment_events`, `payroll_settlements`, `vendors` | `E1`/`E2` áp dụng cho `payroll` với bảng chấm công/chấm dứt HĐ; `E3` so khớp xấp xỉ chuỗi tên (`fuzzy_similarity=0.85`), quá nặng cho FHE thuần. |
| **Nhóm F (Sổ sách, Ghi đè & Công nợ)** | **F1** (`W=8`), **F2** (`W=8`), **F3** (`W=3`), **F4** (chưa gán điểm cứng trong `WEIGHTS`) | `journal_audit_log`, `closing_periods`, `materiality_policies`, `workflow_policies`, `override_events`, `document_series`, `document_register`, `document_cancellations`, `customers`, `receivable_*` | Phụ thuộc nhiều bảng sổ cái, số sê-ri chứng từ, phân bổ công nợ; chưa thiết kế mạch HE. |
| **Nhóm P2 & T (Tiền mặt & Tạm ứng)** | **P2** (`W=8`), **T1** (`W=8`), **T2** (`W=20`, Hard Trigger) | `transactions`, `employees`, `transaction_documents`, `advances`, `advance_events` | `P2` kiểm tiền mặt/VAT; `T1`/`T2` theo dõi dư nợ/xóa nợ tạm ứng qua lịch sử sự kiện. Chưa nối HE. |

### 1.3. Benchmark Chọn Luật Tiếp Theo (`A6` vs `C2`) — Cơ Sở Thực Chứng Cho Quyết Định

Từ [next_rule_assessment.json](file:///D:/agent22/Agent2_Spec_v2_1/evidence/HE/he_full_flow_20261115/next_rule_assessment.json) trên **`14` gói hợp lệ / `670` giao dịch** (`covered_he5_hits = 152` cảnh báo thuộc `HE5`) và benchmark biên dịch Concrete trực tiếp trên WSL Debian:

| Chỉ tiêu đánh giá | `C2` — Tự duyệt vượt quyền được cấp | `A6` — Thanh toán làm tròn vượt hóa đơn gốc | Kết luận |
| :--- | :--- | :--- | :--- |
| **Trọng số & Hard Trigger** | `weight = 20`, `hard_trigger = true` | `weight = 8`, `hard_trigger = false` | **`C2` ưu tiên cao hơn** |
| **Bảng nguồn yêu cầu** | Dùng chung 100% bảng với **`C3`** (`transactions`, `employees`, `approval_authorities`, `approval_authority_coverage`) | Cần thêm `transaction_documents` ngoài `transactions`, `employees` | **`C2` tái sử dụng trực tiếp nguồn `C3`** |
| **Đủ nguồn (`source_complete_rate`)** | `0.691` (`463 / 670`) | `0.9751` (`352 / 361` dòng áp dụng) | `C2` phản ánh đúng trường hợp thiếu bảng phân quyền |
| **Vừa miền HE (`domain_fit_rate_of_complete`)** | `0.879` (`407 / 463`) | `1.0` | `C2` loại trừ đúng 56 ca >4 quy tắc ở `gen_C003` |
| **Tổng số hits / Số hits MỚI ngoài `HE5`** | **`31` hits / `+30` hits tăng thêm** | `9` hits / **`0` hits tăng thêm** | **`C2` mang lại giá trị phát hiện mới duy nhất (+30 ca)** |
| **Biên dịch Concrete (WSL Debian)** | **Thành công** (`bit_width = 1`, `compile_s = 0.379s`, `keygen_s = 1.682s`, `encrypt_run_decrypt_s = 0.657s`, `peak_rss_mb = 662.1 MB`) | **Thất bại biên dịch trực tiếp** (`uint24` table lookup error: Concrete chỉ hỗ trợ LUT tới `16-bit`, `peak_rss_mb = 340.6 MB`) | **Chọn `C2` làm lát cắt mở rộng kế tiếp**, hoãn `A6` |

---

## 2. Báo Cáo Đối Chiếu 3 Lớp & Ma Trận Khôi Phục (`R1–R4`)

Dữ liệu chạy lại hoàn chỉnh từ [`verify_he_full_flow.py`](file:///D:/agent22/agent2/scripts/verify_he_full_flow.py) lưu tại [full_flow_metrics.json](file:///D:/agent22/Agent2_Spec_v2_1/evidence/HE/he_full_flow_20261115/full_flow_metrics.json):

### 2.1. Tổng hợp Ma trận Đối chiếu 3 Lớp (`Design ↔ Plain ↔ Real Concrete HTTP FHE`)

- **Tổng số ca kiểm định (`parity_matrix_summary`):** **`23` ca**
  - **`passed`:** **`20`** (khớp 100% cả 3 lớp `design`, `plain`, `real_he` về `available`, `status`, `matched`, `score`, `hard_trigger`, `reason`)
  - **`partial`:** **`3`** (fail-closed đúng thiết kế khi vượt rào/miền mạch, không fallback hay cắt dữ liệu)
  - **`failed`:** **`0`**

Ba ca `partial` theo thiết kế ranh giới an toàn:
1. **`P1_05_prior_limit_over_4`**: Vượt giới hạn `4` giao dịch trước đó cùng hóa đơn của mạch `rules` -> lớp HE trả `unavailable` (`he_p1_source_limit`) thay vì cộng sẵn trên plaintext.
2. **`P1_06_negative_amount_rejected_schema`**: Khoản âm (`amount_vnd < 0`) bị schema `agent2-rule-snapshot/1.0.0` từ chối tường minh (`rejected_schema`) ngay từ khâu validate; điều chỉnh ghi âm được giữ riêng trên `canonical 1.1.0`.
3. **`C3_07_authority_rules_over_4_limit`**: Có hơn `4` quy tắc thẩm quyền ứng viên cho một giao dịch -> mạch `c3` trả `unavailable` (`he_c3_authority_limit`) đúng chuẩn fail-closed.

### 2.2. Kịch bản Khôi phục Sau Sự cố (`R1–R4`) & Cách ly Đa Doanh nghiệp

| Kịch bản | Trạng thái | Cơ chế kiểm chứng thực tế | Ghi nhận kỹ thuật quan trọng |
| :--- | :--- | :--- | :--- |
| **`R1_encrypt_checkpoint_recovery`** | **PASS (`true`)** | Mô phỏng crash khi đang mã hóa để lại file tạm `argument-0.cipher`, chạy lại `encrypt` với `recover_uncommitted=True`. Thời gian mã hóa giảm từ `42.0–46.5s` xuống `1.86s` nhờ tái sử dụng checkpoint. | Phát hiện kiểm chứng thực tế (`enterprise_helper.py`): helper fail-closed trả `he4_helper_unavailable` nếu gặp tên file lạ ngoài mẫu `argument-{i}.cipher`. |
| **`R2_lost_evaluate_reply_results_recovery`** | **PASS (`true`)** | Làm mất phản hồi HTTP `/v1/evaluate` của worker; coordinator tự gọi `/v1/resume`, tải lại `result.cipher` theo `result_sha256` đã ký và giải mã khớp hoàn toàn. | Khớp chữ ký Ed25519 `he4-worker/0.1.0` & ràng buộc `request_sha256` / `circuit_sha256`. |
| **`R3_ttl_pause_fresh_admission`** | **PASS (`true`)** | Hết hạn phiên giữa batch chuyển job sang `waiting_authorization` (`AUTH_REQUIRED`); khi cấp phiên mới, `/v1/resume` nhận `HE4_REQUEST_NOT_ADMITTED` và tự động chuyển tiếp an toàn sang `/v1/admit` với `purpose = FRESH_ADMISSION` giữ nguyên `nonce` / hash gói gốc. | Đảm bảo batch HE kéo dài >20 phút không mất tiến độ hay làm sai lệch toàn vẹn gói đã ký. |
| **`R4_real_sigkill_worker_restart_resume`** | **PASS (`true`)** | Phóng `SIGKILL` (`kill -9`) trực tiếp vào tiến trình worker WSL Concrete ngay khi file `attempt_<hex>/native.started` vừa xuất hiện dưới thư mục `state/`, khởi động lại worker HTTP và gọi `/v1/resume` (`73.7s`). | Không hỏng trạng thái SQLite (`jobs.sqlite3`), không rò khóa bí mật, kết quả sau phục hồi khớp đối chiếu. |
| **`portal_cross_company_isolation`** | **PASS (4/4 `true`)** | Cố ý dùng trùng mã `AUDIT_0000` ở `C001` (có tín hiệu) và `C002` (sạch): `c1_audit_matched=true`, `c2_audit_clean=true`, `accountant_masked=true`, `workspace_review_csv_verified=true`. | Không lẫn hồ sơ, không lẫn kết quả giữa hai doanh nghiệp; Workspace review & CSV xuất giữ nguyên liên kết bằng chứng. |

---

## 3. Bảng Chi Phí Thực Tế Theo Ca, Thành Phần FHE & Dung Lượng BlobStore

Số liệu đo thực nghiệm trên phần cứng chạy benchmark WSL Debian (`concrete-python 2.11.0`):

### 3.1. Kích thước Mạch & Evaluation Key (`C001` / per-company)

| Thành phần / Mạch | `server.zip` (bytes) | `client.specs.json` (bytes) | Evaluation Key (`bytes`) | Evaluation Key (`MiB`) | Payload mẫu đo được (`request` / `result` bytes) |
| :--- | ---: | ---: | ---: | ---: | :--- |
| **`rules`** (`build-rules-difference-v1`, `P1`) | `470,493` | `10,368` | `1,394,657,872` | `1,330.05 MiB` | — |
| **`c3`** (`build-c3-v1`, `C3`) | `104,587` | `13,753` | `1,541,004,464` | `1,469.62 MiB` | Request: `6,537,264 B` (10 args) / Result: `270,760 B` |
| **`graph`** (`build-graph-difference-v1`, `B1`/`B5`/`E4`) | `148,667` | `6,127` | `1,616,717,208` | `1,541.82 MiB` | Request: `33,891,248 B` (`33,562,896 + 262,536 + 65,816`, 3 args) / Result: `1,311,608 B` |
| **Tổng cộng / 1 Doanh nghiệp** | **`723,747`** | **`30,248`** | **`4,552,379,544`** | **`4.2397 GiB`** | *(Tham khảo mạch `statistics` `build-statistics-v1`: `72,570` + `2,424 B`)* |

### 3.2. Thời gian Chi tiết Từng Bước & Theo Batch

- **Chi phí từng pha đo trực tiếp trên mạch `c3` (`R1–R4`):**
  - Mã hóa (`encrypt`): **`42.0 – 46.5s`** (khi có checkpoint `R1`: **`1.86s`**)
  - Upload evaluation key: **`13.9 – 15.8s`**
  - Upload 10 cipher arguments: **`0.38 – 0.72s / arg`**
  - Worker tính toán FHE: `/v1/admit` **`63.0s`**, `/v1/evaluate` **`64.5s`**, `/v1/resume` sau `SIGKILL` **`73.7s`**
  - Giải mã (`decrypt`): **`41.6 – 50.8s`**
- **Tổng thời gian Batch & RAM (`peak_wsl_rss_mb = 7,479.3 MB` ~ `7.30 GiB`):**

| Batch / Ca | Số dòng | Thời gian đo thực tế | Ghi chú vận hành |
| :--- | ---: | ---: | :--- |
| **`C001_COLD`** | 3 | **`1,173.0s`** (`1,173.56s` log, ~`19m 33s`) | Bao gồm keygen lần đầu cho cả 3 mạch + full HTTP FHE |
| **`C001_WARM_EXTRA`** | 2 | ~`32 phút` FHE hoạt động liên tục | Log resume cuối ghi `22,333.0s` do bao gồm ~`20,420s` Windows sleep giữa hai phiên; bản thân thời gian chạy thực ~`32 phút` |
| **`C001_LIMITS_GAPS`** | 2 | **`0.0s`** SQLite (`0.38s` log) | Fail-closed trước khi mã hóa / từ trạng thái lập kế hoạch |
| **`C002_COLD`** | 3 | **`1,215.0s`** (`1,215.17s` log, ~`20m 15s`) | Độc lập khóa doanh nghiệp thứ 2 (`worker2_c002`) |
| **`C001_ACCT`** | 3 | **`1,441.0s`** (`1,441.44s` log, ~`24m 01s`) | Luồng đầy đủ với vai trò kế toán / che giấu metadata |

### 3.3. Tác Động Dung Lượng `BlobStore` (Giới hạn `8 GiB` / Worker)

Theo [blob_store.py](file:///D:/agent22/agent2/experiments/he4/blob_store.py#L14-L33), mỗi `BlobStore` mặc định có `limit = 2 GiB` (`2 * 1024**3 B`) mỗi blob và **`quota = 8 GiB` (`8,589,934,592 B`) cho toàn worker**:

- **`worker1_c001` (sau dọn/xong chuỗi C001):** **`4,685,992,656 B`** (**`4.3642 GiB`**, `106` blobs) — chiếm **54.55%** quota 8 GiB.
- **`worker1_c001_pre_resume` (trước resume R4):** **`4,825,801,608 B`** (**`4.4944 GiB`**, `99` blobs) — chiếm **56.18%** quota 8 GiB.
- **`worker2_c002` (chỉ riêng C002):** **`4,645,144,512 B`** (**`4.3261 GiB`**, `40` blobs) — chiếm **54.08%** quota 8 GiB.

> [!WARNING]
> **Rủi ro cạn quota ngay ở 2 doanh nghiệp dùng chung 1 worker:** `4.36 GiB + 4.33 GiB = 8.69 GiB > 8 GiB`, chắc chắn kích hoạt lỗi `413 BLOB_QUOTA` khi upload khóa của doanh nghiệp thứ hai nếu không tách shard! Do đó, triển khai thực tế bắt buộc **sharding worker theo doanh nghiệp hoặc theo mạch** (`worker_c001` / `worker_c002` hoặc tách quota theo worker), kết hợp chính sách dọn blob hết hạn sau khi job hoàn tất.

---

## 4. Portal/API Schema & Hành Vi Vận Hành (`he-rule-snapshot-groups-result/1.0.0`)

1. **Cổng cấu hình & Phản hồi `/datasets` (`he4/web.py`, `he4/coordinator.py`):**
   - Với `he4-enterprise/1.0.0`: gửi `agent2-rule-snapshot/1.0.0` bị từ chối fail-closed với HTTP `422 HE_PROFILE_UNSUPPORTED`.
   - Với `he4-enterprise/1.1.0` (`supports_rule_snapshot = True`): `FourWorkbench.datasets` hỏi `/v1/readiness` của worker bằng challenge ký số + xác minh SHA-256 của từng `server.zip` trong `builds` (`rules`, `c3`, `graph`). Khi đủ điều kiện, trả về `rule_snapshot_he_supported = true`, `he_covered_rules = ['P1', 'C3', 'B1', 'B5', 'E4']`, `analysis_mode = 'rule_snapshot_and_four_branches'`.
2. **Cấu trúc kết quả `he-rule-snapshot-groups-result/1.0.0` ([rule_snapshot_coordinator.py](file:///D:/agent22/agent2/experiments/he4/rule_snapshot_coordinator.py#L412-L505)):**
   - **Từng giao dịch (`rows[]`):** giữ nguyên trạng thái (`evaluated_hit`, `evaluated_no_hit`, `not_applicable`, `unavailable`), chi tiết từng nhóm `groups` (`p1`, `c3`, `b1`, `b5_e4`), cùng `branches` và `unsupported_summary` (`covered_he_rules`, `covered_rule_count: 5`, `total_rule_count: 35`, `unencrypted_rule_count: 30`, `ml_bridge_he_supported: false`, `statistics_he_supported: false`, `reason: 'rule_snapshot_he_unsupported'`).
   - **Không tự trộn điểm (`aggregation`):** `available: false`, `score: null`, ghi rõ 4 nhóm HE đã mã hóa, 30 luật local còn lại và ML 33 feature tách biệt hoàn toàn.
   - **Ràng buộc nguồn & mã build (`provenance`):** lưu `snapshot_id`, `snapshot_checksum`, `data_checksum`, `as_of`, `source_sha256`, `plan_sha256`, `implementation_sha256`, `builds` (`circuit_sha256`, `specs_sha256`), `evaluation_keys_sha256_by_profile`, `key_epochs_by_profile`.
3. **Phân quyền RBAC & Chống mất độ chính xác tiền tệ ([he_workbench.py](file:///D:/agent22/agent2/sme_fraud/he_workbench.py#L160-L175), [he_result_view.py](file:///D:/agent22/agent2/sme_fraud/he_result_view.py)):**
   - Mọi trường `*_vnd` kiểu `int` được chuyển sang `string` qua `money_strings()` để tránh mất chữ số chính xác trên IEEE-754 float của trình duyệt.
   - Khi vai trò không phải `director` (ví dụ kế toán `accountant`), `review_result()` lọc whitelist giữ phần giải thích nghiệp vụ, bằng chứng, lỗ hổng dữ liệu và `provenance` rút gọn (`snapshot_id`, `snapshot_checksum`, `data_checksum`, `as_of`, `covered_he_rules`, `covered_rule_count`, `total_rule_count`), che toàn bộ `implementation_sha256`, `plan_sha256`, `builds`, `evaluation_keys_sha256_by_profile`, `raw_score`, `tenant_id` và nội bộ cấu hình model/worker.
4. **Bearer Session TTL trong Portal so với Thời gian Batch HE:**
   - `portal/server.py` thiết lập `SESSION_TTL = 20 * 60` (`1200s`), trượt gia hạn qua `session_left(token, touch=True)` mỗi lần gọi API có tương tác.
   - Trong khi đó, một batch 3 giao dịch qua cả 3 mạch Concrete HE tốn **`1,173 – 1,441s` (~19.5 – 24 phút)** — sát hoặc vượt cửa sổ `20 phút` nếu người dùng không thao tác hoặc tab trình duyệt ngủ. Nhờ cơ chế `waiting_authorization` + `R3 FRESH_ADMISSION`, job không bị hủy mà tạm dừng an toàn chờ mở lại phiên và `/resume` với body `{}`. Khuyến nghị bổ sung keep-alive nhẹ khi UI đang poll job hoặc nâng hướng dẫn gia hạn phiên trước khi chạy batch lạnh.

---

## 5. Kế Hoạch Triển Khai Theo Từng Chặng (`he4-enterprise/1.1.0`) & Rollback Tức Thì (`1.0.0`)

### 5.1. Hiện trạng Live Đã Quan Sát Trên Đĩa (Tuyệt đối chưa chạm)

Theo [start_platform.ps1](file:///D:/agent22/start_platform.ps1) và [config.local.json](file:///D:/agent22/portal/config.local.json):
- **Portal Shell:** cổng `8800`
- **Agent2 Backend:** cổng `8766`
- **Kiến trúc Dual-Worker bắt buộc:**
  1. `he_worker` (`he-worker-readiness/1.0.0`, cổng `8868`): cấu hình tại `agent2/.runtime/he-company-demo/worker/`
  2. `he4_worker` (`he4-enterprise/1.0.0`, cổng `8869`, WSL `Debian`, python `/home/sang/.local/share/agent2/he4/bin/python`): cấu hình tại `agent2/.runtime/he-four-managed-v1/worker/worker.json` & `enterprise/node.json`
- Hàm `FourWorkbench.datasets` yêu cầu **cả hai** worker (`8868` và `8869`) đều qua bước sẵn sàng thì `worker_ready` mới bằng `true`.

### 5.2. Chặng Chuyển Đổi Sang `he4-enterprise/1.1.0`

| Chặng | Hành động cụ thể | Điều kiện vượt qua (Gate) |
| :--- | :--- | :--- |
| **Chặng 0 — Chuẩn bị Build & Sharding** | Đóng gói `build-rules-difference-v1`, `build-c3-v1`, `build-graph-difference-v1` (và tùy chọn `build-statistics-v1`) vào thư mục runtime mới riêng cho `1.1.0` (giữ nguyên `he-four-managed-v1`). Cấp tách worker/BlobStore theo doanh nghiệp hoặc nâng hạn mức dung lượng tránh ngưỡng `8 GiB`. | Kiểm tra `manifest.json` (`he4-circuit-build/0.1.0`) + SHA-256 `server.zip` / `client.specs.json` khớp 100%; RAM WSL >= `16 GB` (`peak_wsl_rss_mb = 7.48 GB`). |
| **Chặng 1 — Thẩm định Shadow trước Cutover** | Chạy `verify_he_full_flow.py --dry-plain` + kịch bản smoke trên node/port shadow, kiểm tra `FourWorkbench` với `agent2-rule-snapshot/1.0.0` và giữ nguyên `he_worker` (`8868`) song song với `he4_worker` (`1.1.0`). | `23/23` parity matrix không có `failed`; `R1–R4` PASS; `worker_ready = true` qua cả dual-worker readiness. |
| **Chặng 2 — Cutover Pilot Có Kiểm Soát** | Trong khung bảo trì, trỏ `AGENT2_HE4_CONFIG` và `he4_worker` trong `portal/config.local.json` sang gói `he4-enterprise/1.1.0`; khởi động lại qua `start_platform.ps1`. | `/datasets` trả `analysis_mode = 'rule_snapshot_and_four_branches'`; thử 1 snapshot nhỏ `C001` qua Portal -> Workspace Review -> CSV xuất thành công. |
| **Chặng 3 — Giám sát Vận hành & Mở rộng Kế tiếp (`C2`)** | Theo dõi dung lượng từng `BlobStore` (`< 75%` của `8 GiB`), RSS WSL, tỷ lệ hết phiên `401 AUTH_REQUIRED`. Khởi động triển khai lát cắt tiếp theo ưu tiên **`C2`** dựa trên kết quả benchmark mục 1.3. | Không phát sinh `413 BLOB_QUOTA`; tỷ lệ phục hồi `/resume` đạt `100%` khi worker restart. |

### 5.3. Phương Án Rollback Tức Thì Về `he4-enterprise/1.0.0`

Không cần hoàn tác cấu trúc CSDL SQLite (kho phiếu rà giữ tách `current` vs `legacy` theo phiên bản kết quả):
1. Dừng tiến trình Portal (`Ctrl+C` ở `start_platform.ps1` / `portal/server.py`).
2. Trả `AGENT2_HE4_CONFIG`, `he4_worker.bundle` và `he4_worker.config` trong `portal/config.local.json` về lại đúng đường dẫn gốc của `he-four-managed-v1` (`he4-enterprise/1.0.0`) vốn không hề bị sửa đổi.
3. Khởi động lại `start_platform.ps1`.
4. Xác nhận tức thì: các nhánh `canonical 1.1.0` (`he4-enterprise/1.0.0`) phục vụ bình thường; mọi yêu cầu phân tích HE trên `agent2-rule-snapshot/1.0.0` tự động fail-closed trả `422 HE_PROFILE_UNSUPPORTED` an toàn, không làm hỏng phiên hay rò rỉ dữ liệu.

