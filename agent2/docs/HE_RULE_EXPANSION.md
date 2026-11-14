# Mở rộng FHE (Concrete) cho hệ thống 35 luật từ profile đầy đủ `agent2-rule-snapshot/1.0.0`

## 1. Mục tiêu và nguyên tắc triển khai

- **Không làm giả HE (No Fake HE)**: Mọi phép tính/so sánh quyết định nghiệp vụ trong phạm vi circuit đều chạy trên **ciphertext thật** trong worker cô lập (WSL `concrete-python 2.11.0`, `all_inputs_encrypted=true`, `contains_secret_keys=false`). Enterprise node (Windows + DPAPI) chỉ thực hiện chuẩn hóa bản ghi đã biết theo thời điểm `as_of`, kiểm tra coverage/completeness/source limit, mã hóa đầu vào, ký Ed25519 từng gói, và giải mã kết quả.
- **Không cắt dữ liệu hoặc cộng sẵn để né giới hạn circuit**: Khi số dòng lịch sử (`> 4` khoản prior hoặc `> 4` khoản đồng thời với `P1`; `> 4` authority candidates với `C3`; `> 4` thực thể với `graph`) hoặc miền giá trị vượt khả năng của circuit đã compile, adapter **bắt buộc đánh dấu `unavailable` kèm mã lý do tường minh** (`he_p1_source_limit`, `he_c3_authority_limit`, `he_graph_node_limit`, v.v.), tuyệt đối không cắt bớt dòng hay cộng dồn ở client để biến `unavailable` thành `no_signal`.
- **Bảo toàn đầy đủ logic engine gốc (`sme_fraud/rules.py` + `native_rule_node.py` + `rule_snapshot.py`)**: Giữ nguyên quy tắc applicability theo `txn_type`, kiểm tra `observed_at <= as_of`, `posted_at <= as_of`, clock hóa đơn (`invoice_issued_at`, `invoice_observed_at`), coverage (`complete` + `since_inception`), batch controls (`simultaneous_group`), authority matrix vs legacy fallback, miễn trừ/giảm trừ và `scoring_role`.
- **An toàn vận hành live**: Toàn bộ bước phát triển/biên dịch/kiểm thử HTTP & recovery thực hiện trên sandbox riêng; không đụng tới daemon Portal live (`8800`/`8766`/`8868`/`8869`), SQLite live, khóa DPAPI live hay `he4-enterprise/1.0.0` đang phục vụ.

---

## 2. Bảng độ phủ 35 luật (Inventory trạng thái chi tiết)

Quy ước trạng thái theo từng cột:
- **Design**: Đã đặc tả hợp đồng FHE / phân tích khả thi (hay chưa).
- **Plain Parity**: Đã đối chiếu 100% logic plaintext của circuit/adapter với `sme_fraud/rule_snapshot.py` + `rules.py`.
- **Native HE**: Đã chạy thật bằng `concrete-python` (`server.zip` + `evaluation.keys` + ciphertext thật, `simulation=False`).
- **HTTP Worker**: Đã kiểm chứng qua giao thức HTTP ký Ed25519 (`experiments/he4/service.py` + worker cô lập).
- **Recovery**: Đã kiểm chứng khôi phục sau crash (mất kết nối, worker `SIGKILL`, hết hạn TTL / fresh admission, đọc lại khi restart).
- **Portal**: Đã nối vào giao diện/API Portal chính (`live` hay `deferred_pending_verify`).

| Mã luật | Tên nghiệp vụ | Design | Plain Parity | Native HE | HTTP Worker | Recovery | Portal | Ghi chú hợp đồng / miền giới hạn / lý do |
|---|---|---|---|---|---|---|---|---|
| **P1** | Thanh toán vượt tổng giá trị cùng hóa đơn | Slice 1 (Done) | Verified (5/5 ca) | Verified (`C001_hit`, `C002_simultaneous_group`) | Verified (`/v1/evaluate`, `/v1/admit`, `/v1/results`) | Verified (`R1`, `R2`, `R3` SIGKILL/`/v1/resume`, `R4`) | Deferred (chờ deploy Portal có kiểm soát) | Circuit `p1` (`build-rules-difference-v1`, max 4 prior + 4 simultaneous current, `tolerance=1`). Vượt 4 dòng -> `he_p1_source_limit`. |
| **C3** | Duyệt dưới 60 giây ở cấp thẩm quyền cao | Slice 2 (Done) | Verified (4/4 ca) | Verified (`C001_C3_hit_20s`, `C002_C3_boundary_60s`, `C002_C3_ambiguous_unavailable`) | Verified (`/v1/evaluate` 10 cipher args) | Verified (`build-c3-v1` parity + worker state isolation) | Deferred (chờ deploy Portal có kiểm soát) | Circuit `c3` (`experiments/he4/c3_circuit.py`, `build-c3-v1`, 16 nibbles int64 epoch us + VND, max 4 authority bands). Vượt 4 rules -> `he_c3_authority_limit`. |
| **B1** | Tài khoản hoặc căn cước NCC trùng nhân viên | Slice 3 (Done) | Verified (2/2 suite ca) | Verified (`C001_B1`, `<=4` thực thể) | Verified (`/v1/evaluate` `graph`) | Scope-bounded | Deferred (chờ deploy Portal có kiểm soát) | Tái sử dụng `circuits.graph` (`build-graph-difference-v1`, 4 thực thể x 4 trường SHA-256 nibbles: `bank_identity`, `national_id`, `bank_token`). `>= 4` nhân viên (`tong >= 5`) -> `he_graph_node_limit`. |
| **B5** | Nhiều NCC chung thông tin định danh | Slice 3 (Done) | Verified (2/2 suite ca) | Verified (`C002_B5_E4`, `<=4` NCC) | Verified (`/v1/evaluate` `graph`) | Scope-bounded | Deferred (chờ deploy Portal có kiểm soát) | Tái sử dụng `circuits.graph` (`bank_account`, `phone`, `address`); ghép `master_quality` chung `E4`. `>= 5` NCC -> `he_graph_node_limit`. |
| **E4** | NCC trùng định danh | Slice 3 (Done) | Verified (alias `B5`) | Verified (qua `C002_B5_E4`) | Verified (qua `B5`) | Scope-bounded | Deferred (chờ deploy Portal có kiểm soát) | Alias chuẩn hóa của `B5` (`phase2`), dùng chung `evidence_id` & nhóm điểm `master_duplicate`, không tính trùng điểm. |
| **A1** | Chia nhỏ cùng người nhận trong 3 ngày | Assessed (Infeasible w/o new large LUT) | No | No | No | No | Deferred | Phụ thuộc hàng đợi trượt `N` khoản trong 3 ngày + `payment_evidence.scope` + `independent_requests` + `long_installment_exception`. |
| **A2** | Chia nhỏ cùng người lập/người nhận trong 30 ngày | Assessed | No | No | No | No | Deferred | Cửa sổ 30 ngày không giới hạn số lượng + ngoại lệ PO/hợp đồng nhiều bảng. |
| **A3** | Chia nhỏ qua cụm người nhận liên kết | Assessed | No | No | No | No | Deferred | Cần đồ thị liên thông `entity_links` toàn công ty + cửa sổ 3/30 ngày. |
| **A4** | Người lập có nhiều khoản cận hạn mức | Slice 2 Feasibility (Rejected for Slice 2) | No | No | No | No | Deferred | Đã đánh giá chi tiết §4: hàng đợi 30 ngày không chặn trên + tỷ lệ `amount/limit` + cumulative `PeriodPayments`. |
| **A5** | Số tiền tròn lệch baseline lịch sử | Future ML/Stat | No | No | No | No | Deferred | Dynamic rolling 90d P99 / RobustZ theo chu kỳ 180d & `journal_lines`. |
| **A6** | Thanh toán làm tròn vượt hóa đơn gốc | Candidate (Low effort future) | No | No | No | No | Deferred | So sánh `gross % 1000 != 0`, `amount % 1000 == 0`, `amount > gross + 1` — đơn giản nhưng ưu tiên sau P1/C3. |
| **B2** | Thông tin hoặc người đại diện NCC liên kết nhân viên | Candidate (Graph ext) | No | No | No | No | Deferred | Cần duyệt đồ thị `KnownGraph` toàn công ty (`entity_links` + `phone`/`address`), vượt `4` nút. |
| **B3** | NCC mới thành lập nhận giao dịch lớn đầu tiên | Deferred | No | No | No | No | Deferred | Cần `vendor_economics` toàn bộ lịch sử + `moments` baseline + `vendor_fulfilment`. |
| **B4** | Trạng thái người phát hành hóa đơn rủi ro | Deferred | No | No | No | No | Deferred | Lịch sử trạng thái thuế `tax_risk_history` tại ngày xuất hóa đơn & `now`. |
| **B6** | NCC ngủ đông nhận khoản lớn | Deferred | No | No | No | No | Deferred | Cần P90 toàn lịch sử NCC + `vendor_payment_schedules`. |
| **B7** | Đổi tài khoản gần ngày thanh toán chưa xác minh | Candidate (Future) | No | No | No | No | Deferred | So sánh chênh lệch ngày đổi tài khoản gần nhất & cờ xác minh callback. |
| **C1** | Lập hoặc duyệt ngoài lịch vận hành | Deferred | No | No | No | No | Deferred | Lịch vận hành ưu tiên (`schedule` employee/role/company) + ngày lễ + múi giờ. |
| **C2** | Tự duyệt vượt quyền được cấp | Candidate (Same matrix as C3) | No | No | No | No | Deferred | Tương tự `C3` nhưng cho action `self_approve` & `self_approval_limit_vnd`. |
| **C4** | Thao tác trong kỳ nghỉ phép chính thức | Deferred | No | No | No | No | Deferred | Khoảng thời gian `leave_periods` & `leave_activity_authorizations` + `system_actions`. |
| **D1..D6** | Benford / MAD / Segment distributions | Aggregate-only (Enterprise/Future HE stats) | No | No | No | No | Deferred | Luật thống kê theo tập/tháng (`SCOPE_RULES`), histogram log-bin / chi-square trên toàn bộ mẫu. |
| **E1** | Lương không có chấm công hoặc bằng chứng thay thế | Deferred | No | No | No | No | Deferred | `payroll` + `attendance` + `paid_leave_entitlement` theo kỳ lương. |
| **E2** | Lương sau chấm dứt hợp đồng | Deferred | No | No | No | No | Deferred | `employment_events` + `payroll_settlements` khớp khoảng ngày dịch vụ. |
| **E3** | Tên NCC tương tự | Infeasible for exact TFHE | No | No | No | No | Deferred | `difflib.SequenceMatcher` trên chuỗi tên — không phù hợp TFHE thuần mà không đổi thuật toán. |
| **F1** | Điều chỉnh thủ công sát khóa sổ và trọng yếu | Deferred | No | No | No | No | Deferred | Join `journal_audit_log`, `closing_periods`, `materiality_policies` + chênh ngày khóa sổ. |
| **F2** | Quản lý ghi đè quy trình | Deferred | No | No | No | No | Deferred | Đánh giá `workflow_policies` vs `override_events`. |
| **F3** | Khoảng trống/trùng số chứng từ | Scope-heavy | No | No | No | No | Deferred | Quét toàn sổ `document_register` / `document_cancellations` phát hiện hổng/trùng chuỗi số. |
| **F4** | Doanh thu/công nợ kéo dài chưa đối chiếu tiền | Aggregate-only | No | No | No | No | Deferred | `SCOPE_RULES`, phân bổ thu tiền nhiều hóa đơn `receipt_allocations`. |
| **P2** | Chi tiền mặt cần rà soát hạn mức và chứng từ VAT | Candidate | No | No | No | No | Deferred | Luật chi tiền mặt theo hạn mức công ty / tách đợt trong ngày + hóa đơn VAT. |
| **T1** | Tạm ứng còn dư nợ quá hạn | Deferred | No | No | No | No | Deferred | Dư nợ tạm ứng & gia hạn `advances`/`advance_events`. |
| **T2** | Xóa nợ tạm ứng thiếu hồ sơ | Deferred | No | No | No | No | Deferred | Sự kiện `advance_writeoff` & bằng chứng hồ sơ `observed_at <= now`. |

---

## 3. Lát cắt 1 (Ưu tiên 1): Nối `P1` từ `agent2-rule-snapshot/1.0.0` với circuit Concrete `p1` hiện có

### 3.1. Khác biệt cấu trúc nguồn giữa `canonical 1.1.0` và `agent2-rule-snapshot/1.0.0`
- `experiments/he4/snapshot_adapter.py` cũ đọc các bảng `payment_allocations`, `invoices`, `p1_sources` của `canonical 1.1.0`.
- `agent2-rule-snapshot/1.0.0` (`native-rule-source/1.0.0`) lưu nghĩa vụ hóa đơn **ngay trên tiêu đề giao dịch `transactions`** (`invoice_number`, `invoice_gross_vnd`, `invoice_issued_at`, `invoice_observed_at`, `payment_channel`, `is_financial_entry`, `txn_type`, `posted_at`, `observed_at`) kết hợp với `coverage` của `transactions`, `vendors`, `transaction_documents`.

### 3.2. Hợp đồng adapter mới (`experiments/he4/rule_snapshot_adapter.py`)
1. **Xác thực nguồn và thời điểm tại Enterprise Node (DN)**:
   - Kiểm tra phạm vi `AccessScope` (`company_id`, `tenant_id`), toàn vẹn checksum snapshot, `validate_bundle(source, scope)`, và `utc(as_of) == utc(source['as_of'])`.
   - Kiểm tra đầy đủ `coverage`: `transactions` (`status == 'complete'` và `history_basis == 'since_inception'`), `vendors` (`complete`), `transaction_documents` (`complete`).
   - Kiểm tra quy tắc `ROW_KINDS['P1'] = ('vendor_payment',)`: nếu toàn nguồn tới `as_of` không có `vendor_payment` -> `status = 'not_applicable'`.
   - Áp dụng đầy đủ `native_rule_node._gaps(source, 'P1')` và `rule_snapshot.source_guards`: thiếu `invoice_number` trên candidate `vendor_payment`, thiếu `invoice_gross_vnd`, hoặc bất kỳ thiếu nguồn `P1` -> `unavailable` (không đẩy giá trị giả vào circuit).
   - Loại bỏ bản ghi tương lai (`observed_at > as_of` hoặc `posted_at > as_of`) trước khi lập lịch sử nhân quả theo từng mốc `posted_at`.
2. **Tách chế độ đơn lẻ và nhóm đồng thời (Row vs Simultaneous Batch)**:
   - Khóa hóa đơn theo `rules.invoice_payment_key(row)`: `txn_type == 'vendor_payment'`, `is_financial_entry == 1`, `payment_channel in {'bank', 'cash'}`, `company_id`, `vendor_id`, `normalize(invoice_number)` đều khác rỗng.
   - Kiểm tra clock hóa đơn (`p1_unavailable_fields(tx, now)` và toàn bộ `prior` cho cùng hóa đơn): nếu có `invoice_issued_at > now` hoặc `invoice_observed_at > now` -> `unavailable`.
   - **Row check (`role='row'`, `group_mode=0`)**:
     - `prior = [int(r['amount_vnd']) for r in previous_invoice]`, `current = [int(tx['amount_vnd'])]`, `caps = [int(tx['invoice_gross_vnd'])]`, `kinds = ['payment'] * len(prior)`, `tolerance = 1`.
     - Guard parity: vì circuit `p1` dùng `prior[i] > 0` cho `previous`, còn `rules.py:557` kiểm `bool(previous_invoice)`, nếu `len(prior) > 0` và mọi `prior[i] <= 0` -> báo `unavailable` (`he_p1_nonpositive_prior_unsupported`).
   - **Simultaneous batch check (`role='simultaneous_group'`, `group_mode=1`, khi có >= 2 khoản cùng `invoice_key` ở cùng `posted_at`)**:
     - Khớp `batch_controls.close`: nếu có `prior` bị `p1_unavailable_fields`, hoặc `len({int(r['invoice_gross_vnd']) for r in [*prior_rows, *batch_rows]}) != 1`, hoặc `gross <= 0` -> `unavailable` (`simultaneous_invoice_gap`).
     - `prior = [int(r['amount_vnd']) for r in prior_rows]`, `current = [int(r['amount_vnd']) for r in batch_rows]`, `caps = [gross]`, `tolerance = 1`.
   - **Giới hạn bất biến của circuit `p1`**:
     - `len(prior) <= 4` và `len(current) <= 4`; vượt quá -> `unavailable` (`he_p1_source_limit`), **tuyệt đối không cắt lát hoặc cộng sẵn ở DN**.
     - Tất cả giá trị tiền (`amount_vnd`, `invoice_gross_vnd`) phải nằm trong `signed int64` (`-(2**63) .. 2**63 - 1`); tổng 4 dòng nằm trong `signed int128`.

---

## 4. Lát cắt 2: Đánh giá khả thi A4 vs C3 và thiết kế circuit FHE cho `C3`

### 4.1. So sánh khả thi A4 và C3

| Tiêu chí | A4 (Nhiều khoản cận hạn mức) | C3 (Duyệt < 60 giây ở cấp thẩm quyền cao) |
|---|---|---|
| **Phạm vi dữ liệu** | Cửa sổ trượt 30 ngày / tháng dương lịch theo `(cid, maker)`, số dòng `N` không chặn trên (thực tế 10–100+ dòng). | **Đơn giao dịch**: chỉ cần `created_at`, `approved_at`, `amount_vnd` của giao dịch hiện tại và tập rule thẩm quyền khớp metadata cho `approver_id`. |
| **Biến logic phụ thuộc ngữ cảnh** | Phải lọc từng dòng quá khứ theo tỷ lệ `0.8 <= amount/limit <= 0.99`, đánh giá `payment_evidence.exemption` từng dòng, kiểm `batch_payment_keys > 1`, và chạy **prefix sum tuần tự** `PeriodPayments` theo tháng. | Toàn bộ đối chiếu ngày/vai trò/phòng ban/dự án/mức phủ `approval_authority_coverage` độc lập với `amount_vnd` và thời gian duyệt; các phép quyết định chính còn lại thuần số học/so sánh. |
| **Rủi ro "HE giả"** | Nếu lọc `near_low..near_high` và miễn trừ tại DN rồi chỉ gửi `count` vào Concrete -> toàn bộ logic A4 bị tính sẵn tại plaintext. | Circuit `c3` nhận bản mã `created_us`, `approved_us`, `amount_vnd`, `high_threshold`, `mode_legacy`, và các dải `[min_vnd, max_vnd]` + độ ưu tiên/kết quả thẩm quyền: toàn bộ `0 <= dt < 60s`, chọn dải thẩm quyền theo `amount`, phát hiện nhập nhằng `ambiguous_authority`, so sánh ngưỡng `high_approval_vnd` đều thực thi **trên ciphertext**. |
| **Kích thước / độ trễ TFHE** | Rất lớn hoặc bất khả thi với bảng lịch sử tùy ý. | Nhỏ gọn: 4 slot rule (`<= 4`), word 16 nibbles (64-bit signed int cho epoch microseconds & VND). |
| **Kết luận Lát cắt 2** | **Từ chối cho Lát cắt 2** (chưa khả thi nếu giữ đúng 100% logic & không tính trước). | **Chọn `C3`** cho Lát cắt 2. |

### 4.2. Thiết kế circuit `c3` (`experiments/he4/c3_circuit.py`)
- **Mã hóa số học**: Word `C3_WORD_DIGITS = 16` nibbles radix-16 (biểu diễn hai bù chuẩn `signed int64`: `[-2^63, 2^63 - 1]`). Phép trừ `subtract_word64` và so sánh `unsigned_gt64` dùng phép cộng bù không dấu 1 vòng (radix-16 carry-complement trong dải `0..31`) để giữ bit-width thấp và kích thước khóa `< 1.54 GB` (dưới trần `2 GiB` của `vault.py` và `BlobStore`).
  - Thời điểm `created_at`, `approved_at`: chuyển thành số nguyên **microseconds từ Unix epoch UTC** (`(dt - EPOCH) // timedelta(microseconds=1)`). Mọi năm 1970–292.000 đều có trị số `< 2^62`, không tràn dấu khi tính `dt_us = approved_us - created_us`.
  - Kiểm `0 <= (approved_at - created_at) < 60s` tương đương chính xác `dt_us >= 0` và `dt_us < 60_000_000`.
- **Biên thẩm quyền (`MAX_AUTHORITIES = 4`)**:
  - DN chỉ kiểm tra phần **phi số tiền / phi thời gian duyệt**: coverage `approve` tại `approved_at[:10]`, `approved_evidence`, `employee_at(cid, approver_id, approved_at)`, và lọc các bản ghi trong `approval_authorities` khớp metadata (`action in {'approve','all'}`, `txn_type in {tx.txn_type, '*'}`, subject/role, `department`, `project_id`, `effective_from..to`, không self-delegation).
  - Nếu không có coverage -> `mode_legacy = 1` (chú ý ở tầng `rule_snapshot.py:123`, `source_guards` vẫn đánh dấu `C3` là `unavailable` khi snapshot thiếu coverage hoặc coverage không phủ; circuit vẫn hỗ trợ đủ cả 2 nhánh `mode_legacy=0/1` để giữ parity 100% với `rules.py:731-734`).
  - Nếu có `> 4` candidate authority records khớp metadata -> **`unavailable` (`he_c3_authority_limit`)**, tuyệt đối không cắt bớt.
  - Sắp các candidate theo thứ tự `specificity` giảm dần; nén `specificity` thành số nguyên `rank in {1..4}` (`0` nếu slot trống, đồng thời hai rule đồng specificity có cùng giá trị `rank`). Mã hóa `outcome` (kết hợp `(self_approval_allowed, authority_level)`) thành `1..8` và bit `is_high` (`1` nếu `authority_level in {'high','executive'}`).
  - **Bên trong circuit Concrete `c3`**:
    1. `dt_us = subtract_word(approved_us, created_us)`
    2. `fast_60s = signed_ge(dt_us, 0) * signed_gt(60_000_000, dt_us)`
    3. Với từng slot `i in 0..3`: `in_range[i] = (rule_rank[i] > 0) * signed_ge(amount, rule_min[i]) * signed_ge(rule_max[i], amount)`; `eff_rank[i] = in_range[i] * rule_rank[i]`
    4. Tìm `best_rank = max_4(eff_rank)` trên ciphertext -> `selected[i] = (best_rank > 0) * (eff_rank[i] == best_rank)`
    5. Kiểm tra đồng thuận kết quả tại mức `best_rank`: tính tổng xung đột theo cặp trên các slot đã chọn `conflicts = sum(selected[i] * selected[j] * ((rule_outcome[i] - rule_outcome[j]) != 0))` -> `ambiguous = (conflicts > 0)`
    6. `explicit_high = (best_rank > 0) * (1 - ambiguous) * (sum(selected[i] * rule_is_high[i]) > 0)`
    7. `legacy_high = signed_ge(amount, high_threshold)`
    8. `matched = fast_60s * ((1 - mode_legacy) * explicit_high + mode_legacy * legacy_high)`
  - **Ranh giới bảo mật**: Worker không biết `amount_vnd`, `created_at`, `approved_at`, `dt < 60s`, rule nào trúng ngưỡng `[min, max]`, hay `matched`. DN sau khi giải mã chỉ cần kiểm tra thêm điều kiện `source_guards` (`ambiguous_authority`, `unknown_actor`, missing role, thiếu bảng `approval_authorities`/`approval_authority_coverage`).

---

## 5. Lát cắt 3: Nghiên cứu & phân tích nhóm định danh `B1`, `B5`, `E4`

### 5.1. Yêu cầu chính xác của engine gốc
- **`B1` (`rules.py:601-617`, `spec_policy.py:9-25`, `native_rule_node.py:175`)**:
  - Phạm vi (`phase3`): `vendor_outflow = is_financial_entry == 1 and payment_channel in {'bank','cash'} and credit_account.startswith(('111','112')) and bool(vendor_id)`.
  - Phải đối chiếu giao dịch NCC với **toàn bộ nhân viên cùng công ty đang hoạt động tại thời điểm `now`**.
  - Khớp mạnh (`hard_trigger = 1, weight = 20`, hoặc `weight = 4, hard_trigger = 0` nếu `related_party_disclosed_at <= now`):
    - `bank_identity(recipient_account, recipient_bank_code) == bank_identity(emp.bank_account, emp.bank_code)` (hai bên đều đủ mã ngân hàng & số tài khoản chuẩn hóa).
    - `national_id` (9 hoặc 12 chữ số sau chuẩn hóa) trùng giữa NCC và nhân viên.
  - Khớp nhập nhằng (`b1_ambiguous`, `evidence_status='bank_institution_missing'`, `weight=0`, `scoring_role='context'`): số tài khoản `bank_token` trùng nhưng một trong hai bên thiếu `bank_code` (`_gaps` chặn thiếu `recipient_bank_code` trên giao dịch từ nguồn; nhân viên thiếu `bank_code` tạo nhánh `b1_ambiguous`).
- **`B5` & `E4` (`rules.py:658-671`, `noise_policy.py`, `rule_snapshot.py:128-136`)**:
  - So sánh mọi cặp NCC cùng công ty (nhìn thấy đến `now`) trên 3 trường đã chuẩn hóa (`normalize(val, field)`): `'bank_account'`, `'phone'`, `'address'`. Lưu ý `B5` dùng `normalize(..., 'bank_account')`, khác với `bank_identity` có mã ngân hàng của `B1`!
  - Phân biệt mức: chỉ trùng `'address'` (`set(duplicates) == {'address'}`) -> `weight = 1`, `overlap_kind = 'shared_address_only'`; trùng `'bank_account'` hoặc `'phone'` -> `weight = 3`, `overlap_kind = 'shared_bank_or_phone'`.
  - Hợp nhất điểm `master_quality` (`phase2`): `B5` mang `aliases=['E4']`, dùng chung `evidence_id('vendor_overlap', ...)` và nhóm điểm `master_duplicate` (**không bao giờ cộng trùng 2 lần** `B5 + E4`). Ở giao diện rà, `scoring_role='master_quality'` luôn phân loại `context_only` (`needs_review=False`).

### 5.2. Đánh giá tái sử dụng circuit `graph` (`GRAPH_NODES = 4`) và giới hạn mở rộng
- Circuit `circuits.graph(tokens (4,4,64), known (4,4), active (4,))` (đã compile trong `build-graph-difference-v1`, `server.zip = 148,667 bytes`) đối chiếu bình đẳng hoàn toàn trên ciphertext toàn bộ SHA-256 nibbles cho tối đa **4 thực thể x 4 trường**.
- **Tính khả dụng cho `B1`**:
  - Có thể tái sử dụng `graph` khi một giao dịch đối chiếu `1 nút nguồn NCC/giao dịch + tối đa 3 nhân viên` (`tong <= 4`): slot trường `0 = bank_identity`, `1 = national_id` (hai slot mạnh), `2 = bank_token` (slot kiểm tra ứng viên nhập nhằng khi thiếu `bank_code`), `3 = unused`. Khi mọi trường trong nhóm đối chiếu đều đã công bố trước `now` hay không vẫn do DN áp trọng số/role theo chứng từ gốc.
  - **Giới hạn thực tế**: Chỉ cần doanh nghiệp có **>= 4 nhân viên** (tổng nút >= 5), `GRAPH_NODES = 4` bị tràn và bắt buộc trả **`unavailable` (`he_graph_node_limit`)** để không cắt bớt danh sách nhân viên.
- **Tính khả dụng cho `B5` / `E4`**:
  - Có thể dùng `graph` khi tổng số NCC nhìn thấy tới `now` **<= 4** (`field 0 = normalize(bank_account)`, `1 = normalize(phone)`, `2 = normalize(address)`, `3 = unused`). Kết quả `links[0..2]` giữ tách biệt hoàn toàn liên kết mạnh (`bank_account`/`phone`) vs yếu (`address` ở `field 2`, không tham gia `reach`).
  - Khi tổng số NCC **>= 5**, bắt buộc trả **`unavailable` (`he_graph_node_limit`)**.
- **Hướng mở rộng dài hạn cho nhóm định danh**: Nếu muốn chạy cho N thực thể lớn hơn 4 mà không gửi rõ plaintext hash lên worker (vì gửi token hash plaintext sẽ lộ tần suất trùng lặp giữa các bản ghi!), cần either (a) batched encrypted token equality circuit `1 vs M` (vd `M = 8` hoặc `16`) chỉ kiểm cặp `(target, candidate_j)` thay vì ma trận `N x N`, giúp giảm chi phí từ $O(N^2)$ xuống $O(N)$ cho `B1` và cho NCC mục tiêu trong `B5`, hoặc (b) chạy hoàn toàn tại node doanh nghiệp (`agent2-rule-snapshot/1.0.0`) cho tới khi compile và kiểm chứng xong circuit batched `1 x M`.

---

## 6. Kết quả thực nghiệm, ranh giới bảo mật, cổng nối Portal và Rollback

### 6.1. Thông số biên dịch circuit (`D:\agent22\.runtime\he4`)

| Profile | Thư mục build | Thời gian compile | `server.zip` (bytes) | `client.specs.json` (bytes) | `all_inputs_encrypted` | `contains_secret_keys` |
|---|---|---:|---:|---:|:---:|:---:|
| `rules` (`p1`) | `build-rules-difference-v1` | `615.05s` | `470,493` | `10,368` | `true` | `false` |
| `c3` | `build-c3-v1` | `104.17s` | `104,587` | `13,753` | `true` | `false` |
| `graph` | `build-graph-difference-v1` | `81.20s` | `148,667` | `6,127` | `true` | `false` |

### 6.2. Kết quả chạy thật Concrete FHE + HTTP + DPAPI trong sandbox (`scripts/verify_he_rule_expansion.py`)

- **Provisioning 6 vault DPAPI (`C001`, `C002` × `rules`, `c3`, `graph`)**:
  - `C001:rules`: keygen `113.438s`, `evaluation_key_bytes = 1,394,657,872`
  - `C002:rules`: keygen `80.391s`, `evaluation_key_bytes = 1,394,657,872`
  - `C001:c3`: keygen `104.625s`, `evaluation_key_bytes = 1,541,004,464`
  - `C002:c3`: keygen `91.110s`, `evaluation_key_bytes = 1,541,004,464`
  - `C001:graph`: keygen `95.546s`, `evaluation_key_bytes = 1,616,717,208`
  - `C002:graph`: keygen `92.953s`, `evaluation_key_bytes = 1,616,717,208`
  - Lưu ý: tài khoản read-only không có quyền `model.fit` bị chặn với `MODEL_FIT_DENIED`.

- **Đo đạc từng ca qua HTTP Worker + FHE thật (`concrete-python 2.11.0`, `peak_wsl_rss_mb = 8,017.2 MB`)**:

| Ca kiểm chứng | Doanh nghiệp | Parity Engine | Mã hóa / Tải lên | Thực thi FHE HTTP | Giải mã | Request Cipher (bytes) | Result Cipher (bytes) |
|---|---|:---:|---:|---:|---:|---:|---:|
| `P1` `C001_hit` (`AUDIT_0000`) | `C001` | `True` (hit, `+2,000,000`) | `41.641s` / `24.094s` | `159.797s` | `40.828s` | `6,751,008` | `1,992,200` |
| `P1` `C002_simultaneous_group` (sub #0) | `C002` | `True` (group hit, `+1,000,000`) | `40.797s` / `18.640s` | `158.094s` | `40.984s` | `6,751,008` | `1,992,200` |
| `P1` `C002_simultaneous_group` (sub #1) | `C002` | `True` (hỗ trợ đa nhóm) | `37.953s` / `14.187s` | `140.063s` | `41.687s` | `6,751,008` | `1,992,200` |
| `C3` `C001_C3_hit_20s` (`dt=20s`) | `C001` | `True` (`matched=True`) | `55.578s` / `25.110s` | `69.859s` | `49.797s` | `6,537,264` | `270,760` |
| `C3` `C002_C3_boundary_60s` (`dt=60s`) | `C002` | `True` (`matched=False`) | `58.172s` / `25.531s` | `76.531s` | `50.328s` | `6,537,264` | `270,760` |
| `C3` `C002_C3_ambiguous_unavailable` | `C002` | `True` (`status='unavailable'`) | `47.250s` / `21.828s` | `73.063s` | `52.750s` | `6,537,264` | `270,760` |
| `B1` `C001_B1` (`<= 4` thực thể) | `C001` | `True` (`score=20`) | `52.094s` / `24.437s` | `221.766s` | `49.610s` | `33,891,248` | `1,311,608` |
| `B5/E4` `C002_B5_E4` (`<= 4` NCC) | `C002` | `True` (`intrinsic=3, score=0`) | `49.344s` / `21.828s` | `221.406s` | `62.266s` | `33,891,248` | `1,311,608` |

- **Ma trận khôi phục sau lỗi (Crash & Recovery Matrix)**:
  - `R1_lost_reply_idempotency`: `True` — gửi lại gói `/v1/evaluate` trùng `(session, nonce, request_hash)` và `/v1/results` trả về đúng receipt/ciphertext cũ mà không chạy lại FHE.
  - `R2_ttl_expiry_fresh_admission`: `True` — gói quá TTL bị từ chối với `HE4_EXPIRED`; gửi qua `/v1/admit` giữ nguyên `request_sha256` của gói gốc vẫn đánh giá FHE thành công.
  - `R3_mid_compute_sigkill_resume`: `True` — phát hiện `native.started`, gửi `SIGKILL` giết worker (`state='running'`), khởi động worker mới trên cùng `state_dir` tự chuyển `running -> retryable`, gọi `/v1/resume` hoàn tất và giải mã khớp oracle.
  - `R4_read_completed_after_restart`: `True` — restart worker thêm lần nữa, `/v1/results` vẫn đọc lại đúng receipt/ciphertext đã hoàn thành.
  - Lưu ý vận hành quota: `BlobStore` giữ nguyên trần bảo mật `limit = 2 GiB/blob`, `quota = 8 GiB/worker`. Khi chạy đồng thời nhiều công ty × 3 mạch (~1.39–1.62 GB `evaluation.keys`/cặp), cần cấp worker state tách theo nhóm mạch hoặc luân chuyển cache khóa công khai để tránh vượt trần `8 GiB`.

- **Báo cáo chi tiết công khai**: Xem [REPORT.md](file:///D:/agent22/Agent2_Spec_v2_1/evidence/HE/he_rule_expansion_20261114/REPORT.md) và [metrics.json](file:///D:/agent22/Agent2_Spec_v2_1/evidence/HE/he_rule_expansion_20261114/metrics.json) (đã loại bỏ toàn bộ secret key, mật khẩu và raw ciphertext).

### 6.3. Phương án Cổng nối Portal & Rollback
- **Hiện trạng nối Portal**: Chưa sửa `he4-enterprise/1.0.0` hoặc cơ chế chạy Portal live trong phạm vi bàn giao sandbox này; các adapter mới (`rule_snapshot_adapter.py`, `rule_snapshot_c3_adapter.py`, `rule_snapshot_identity_adapter.py`) và build `build-c3-v1` sẵn sàng tích hợp theo cờ opt-in phiên bản `he4-enterprise/1.1.0` ở bước triển khai Portal riêng có backup SQLite/DPAPI trước khi restart.
- **Rollback**: Giữ nguyên `experiments/he4/snapshot_adapter.py` (`canonical 1.1.0`), cấu hình `he4-enterprise/1.0.0`, và 3 build gốc (`build-rules-difference-v1`, `build-graph-difference-v1`, `build-statistics-v1`). Nếu gặp sự cố sau khi bật opt-in, chỉ cần tắt cấu hình `c3`/adapter mới hoặc trỏ `worker.json` về lại 3 build `1.0.0` mà không ảnh hưởng snapshot, model ML, khóa DPAPI hay lịch sử job cũ.

