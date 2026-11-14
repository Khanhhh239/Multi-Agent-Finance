# Báo cáo Kiểm chứng Mở rộng FHE (`he_rule_expansion_20261114`)

- **Ngày xác minh**: `2026-11-14`
- **Phạm vi**: Mở rộng mã hóa đồng hình FHE thật (`concrete-python 2.11.0`, WSL + worker HTTP cô lập ký Ed25519 + khóa DPAPI Windows) từ profile đầy đủ `agent2-rule-snapshot/1.0.0` cho 3 lát cắt (`P1`, `C3`, `B1`/`B5`/`E4`), giữ nguyên toàn bộ điều kiện nguồn/thời điểm/ngoại lệ của engine gốc (`sme_fraud/rules.py` + `native_rule_node.py` + `rule_snapshot.py`) và không can thiệp DB/khóa/Portal live.
- **Tính sạch của gói chứng cứ**: Toàn bộ tệp trong thư mục chứng cứ này (`REPORT.md`, `metrics.json`) không chứa khóa bí mật DPAPI/HE, mật khẩu, token xác thực hay bản mã raw.

---

## 1. Thành phần mã nguồn & build đã triển khai (chưa nối Portal live)

| Thành phần | Đường dẫn | Vai trò & ghi chú |
|---|---|---|
| Adapter `P1` | [rule_snapshot_adapter.py](file:///D:/agent22/agent2/experiments/he4/rule_snapshot_adapter.py) | Nối `agent2-rule-snapshot/1.0.0` với circuit `p1` (`build-rules-difference-v1`), kiểm `coverage`, `invoice_clock`, `simultaneous_group`, giới hạn `<= 4` prior / `<= 4` current -> `he_p1_source_limit`. |
| Circuit `C3` | [c3_circuit.py](file:///D:/agent22/agent2/experiments/he4/c3_circuit.py) | Circuit FHE 16 nibbles radix-16 signed `int64` epoch microseconds & VND, tối đa `4` dải thẩm quyền, kiểm `0 <= dt < 60s`, specificity rank, xung đột kết quả `ambiguous_authority`, fallback legacy trên ciphertext. |
| Adapter `C3` | [rule_snapshot_c3_adapter.py](file:///D:/agent22/agent2/experiments/he4/rule_snapshot_c3_adapter.py) | Chuẩn hóa candidate `approval_authorities` cho `C3`, chặn `> 4` candidates -> `he_c3_authority_limit`. |
| Adapter `B1`/`B5`/`E4` | [rule_snapshot_identity_adapter.py](file:///D:/agent22/agent2/experiments/he4/rule_snapshot_identity_adapter.py) | Tái sử dụng `circuits.graph` (`build-graph-difference-v1`, tối đa `4` thực thể x `4` trường SHA-256 nibbles); vượt 4 thực thể -> `he_graph_node_limit`. |
| Mở rộng Worker/Bridge (Opt-in) | [public_worker.py](file:///D:/agent22/agent2/experiments/he4/public_worker.py), [enterprise_helper.py](file:///D:/agent22/agent2/experiments/he4/enterprise_helper.py), [windows_bridge.py](file:///D:/agent22/agent2/experiments/he4/windows_bridge.py), [service.py](file:///D:/agent22/agent2/experiments/he4/service.py) | Hỗ trợ thêm profile `'c3'` (`10` argument ciphertexts) trong khi worker không cấu hình `'c3'` tiếp tục từ chối như cũ. |
| Bảng độ phủ 35 luật & kiến trúc | [HE_RULE_EXPANSION.md](file:///D:/agent22/agent2/docs/HE_RULE_EXPANSION.md) | Phân loại đủ 35 luật (`Design`, `Plain Parity`, `Native HE`, `HTTP Worker`, `Recovery`, `Portal`), đánh giá A4 vs C3, phương án mở rộng & rollback. |

### Thông số build Concrete (`D:\agent22\.runtime\he4`)

| Profile | Build directory | Compile | `server.zip` | `client.specs.json` | `all_inputs_encrypted` | `contains_secret_keys` |
|---|---|---:|---:|---:|:---:|:---:|
| `rules` (`p1`) | `build-rules-difference-v1` | `615.05s` | `470,493 bytes` | `10,368 bytes` | `true` | `false` |
| `c3` | `build-c3-v1` | `104.17s` | `104,587 bytes` | `13,753 bytes` | `true` | `false` |
| `graph` | `build-graph-difference-v1` | `81.20s` | `148,667 bytes` | `6,127 bytes` | `true` | `false` |

---

## 2. Kết quả chạy thật FHE + DPAPI + HTTP trong sandbox (`verify_he_rule_expansion.py`)

Chạy trọn vẹn qua WSL `concrete-python 2.11.0` (`task-1618`, thoát `0`), đỉnh RAM WSL đo được `8,017.2 MB` (`peak_wsl_rss_mb`):

### Provisioning 6 vault DPAPI (`C001`, `C002` × `rules`, `c3`, `graph`)

| Context | Keygen (giây) | `evaluation.keys` (bytes) | Kiểm soát quyền |
|---|---:|---:|---|
| `C001:rules` | `113.438s` | `1,394,657,872` | Chặn scope read-only (`MODEL_FIT_DENIED`) |
| `C002:rules` | `80.391s` | `1,394,657,872` | Cô lập theo `company_id` & `circuit_sha256` |
| `C001:c3` | `104.625s` | `1,541,004,464` | Dưới trần `2 GiB` của `vault.py` & `BlobStore` |
| `C002:c3` | `91.110s` | `1,541,004,464` | Cô lập theo `company_id` & `circuit_sha256` |
| `C001:graph` | `95.546s` | `1,616,717,208` | Tái sử dụng `build-graph-difference-v1` |
| `C002:graph` | `92.953s` | `1,616,717,208` | Tái sử dụng `build-graph-difference-v1` |

### Đối chiếu từng ca FHE qua HTTP (`metrics.json`)

| Lát cắt & Ca thử | Công ty | Khớp Oracle? | Encrypt | Upload | HTTP FHE | Decrypt | Request Cipher | Result Cipher |
|---|---|:---:|---:|---:|---:|---:|---:|---:|
| `P1` `C001_hit` (`AUDIT_0000`) | `C001` | `True` (hit, `+2,000,000`) | `41.641s` | `24.094s` | `159.797s` | `40.828s` | `6,751,008 B` | `1,992,200 B` |
| `P1` `C002_simultaneous_group` (#0) | `C002` | `True` (group hit, `+1,000,000`) | `40.797s` | `18.640s` | `158.094s` | `40.984s` | `6,751,008 B` | `1,992,200 B` |
| `P1` `C002_simultaneous_group` (#1) | `C002` | `True` (hỗ trợ đa nhóm) | `37.953s` | `14.187s` | `140.063s` | `41.687s` | `6,751,008 B` | `1,992,200 B` |
| `C3` `C001_C3_hit_20s` (`dt=20s`) | `C001` | `True` (`matched=True`) | `55.578s` | `25.110s` | `69.859s` | `49.797s` | `6,537,264 B` | `270,760 B` |
| `C3` `C002_C3_boundary_60s` (`dt=60s`) | `C002` | `True` (`matched=False`) | `58.172s` | `25.531s` | `76.531s` | `50.328s` | `6,537,264 B` | `270,760 B` |
| `C3` `C002_C3_ambiguous_unavailable` | `C002` | `True` (`matched=None`, `unavailable`) | `47.250s` | `21.828s` | `73.063s` | `52.750s` | `6,537,264 B` | `270,760 B` |
| `B1` `C001_B1` (`<= 4` thực thể) | `C001` | `True` (`score=20`) | `52.094s` | `24.437s` | `221.766s` | `49.610s` | `33,891,248 B` | `1,311,608 B` |
| `B5/E4` `C002_B5_E4` (`<= 4` NCC) | `C002` | `True` (`intrinsic=3, score=0`) | `49.344s` | `21.828s` | `221.406s` | `62.266s` | `33,891,248 B` | `1,311,608 B` |

---

## 3. Ma trận khôi phục & ranh giới bảo mật

| Kịch bản kiểm chứng | Trạng thái | Hành vi thực tế quan sát được |
|---|:---:|---|
| `R1_lost_reply_idempotency` | **PASS** | Gửi lại `/v1/evaluate` và gọi `/v1/results` với đúng `request_sha256` trả lại đúng receipt/ciphertext cũ, không chạy lại FHE. |
| `R2_ttl_expiry_fresh_admission` | **PASS** | Gói quá TTL bị từ chối với `HE4_EXPIRED`; `/v1/admit` giữ nguyên packet & ciphertext đã mã hóa và hoàn tất FHE. |
| `R3_mid_compute_sigkill_resume` | **PASS** | Đợi `native.started`, gửi `SIGKILL` giết worker (`state='running'`), khởi động worker mới tự chuyển `running -> retryable`, `/v1/resume` hoàn tất & giải mã đúng oracle. |
| `R4_read_completed_after_restart` | **PASS** | Restart worker thêm lần nữa, `/v1/results` đọc lại đúng receipt/ciphertext đã lưu. |

- **Ranh giới bảo mật**: Worker public (`he4-public-bundle`) kiểm tra `find_spec('sme_fraud') is None` (`worker_has_sme_fraud = false`), không có `secret_key` (`worker_has_secret_key = false`), mọi request/response đều ký Ed25519 (`all_requests_ed25519_signed = true`), vault dùng DPAPI Windows (`windows-dpapi-current-user`), khóa/dữ liệu cô lập theo từng `company_id` (`cross_company_isolated = true`).
- **Giới hạn đã tuân thủ**: Mọi ca vượt biên circuit (`> 4` prior/current với `P1`, `> 4` authorities với `C3`, `>= 4` nhân viên với `B1`, `>= 5` NCC với `B5/E4`) đều trả `unavailable`, không cắt dữ liệu hay tính trước tại DN.

---

## 4. Kiểm thử hồi quy sau lần chỉnh sửa cuối

1. **Bộ HE4 mở rộng + hồi quy HE4 nền** (`14` module, chạy với `PYTHONPATH=D:\agent22\agent2;D:\agent22\agent2\tests_he;D:\agent22\agent2\tests`):
   - `tests_he.test_he4_inputs`, `test_he4_reference`, `test_he4_snapshot_adapter`, `test_he4_p1_demo`, `test_he4_coordinator`, `test_he4_service`, `test_he4_blobs`, `test_he4_vault`, `test_he4_config_api`, `test_p1_portal_check`, `test_he4_c3_worker_contract`, `test_he4_rule_snapshot_p1`, `test_he4_rule_snapshot_c3`, `test_he4_rule_snapshot_identity`
   - Kết quả: **`Ran 65 tests in 40.307s - OK`** (0 failure, 0 skip).
2. **Bộ rule-snapshot & engine parity** (`6` module):
   - `tests.test_rule_snapshot`, `tests.test_native_rule_node`, `tests.test_rule_snapshot_ml_bridge`, `tests.test_rule_snapshot_cutoff`, `tests.test_rules`, `tests.test_rule_parity`
   - Kết quả: **`Ran 69 tests in 132.489s - OK`** (0 failure, 0 skip).

---

## 5. Trạng thái nối Portal & Rollback

- Chưa gắn `c3` hay adapter `agent2-rule-snapshot/1.0.0` vào cấu hình Portal live; dữ liệu SQLite/DPAPI/`he4-enterprise/1.0.0` trước đây được giữ nguyên hoàn toàn.
- Khi triển khai nối Portal có kiểm soát, khuyến nghị tách worker state theo nhóm mạch (hoặc quản lý luân chuyển khóa công khai) để không chạm trần quota mặc định `8 GiB/worker` của `BlobStore`, và luôn giữ sẵn đường rollback về `he4-enterprise/1.0.0` + 3 build cũ (`build-rules-difference-v1`, `build-graph-difference-v1`, `build-statistics-v1`).

