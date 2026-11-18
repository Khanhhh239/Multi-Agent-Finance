# CR-063 — Nối HE thật vào bộ điều phối bundle chung (18/11/2026)

- **spec_version**: `2.1`
- **Trạng thái kỹ thuật**: **READY_FOR_REVIEW** cho luồng shadow HE có giới hạn (`P1`, `C3`, `B1`, `B5/E4`) trên môi trường cô lập và dữ liệu mô phỏng.
- **Toàn bộ R6, full 35-luật / 33-feature HE và phát hành production**: **BLOCKED**.
- **Ranh giới vận hành**: chưa deploy/restart Portal live, không đổi khóa/model/quyền live, không push GitHub.

---

## 1. Kiến trúc và phạm vi đã nối

Luồng thực thi `execution_mode=cloud_ciphertext_only` trong bộ điều phối bundle chung (`ReleaseService` + `BundleHE` `bundle-he4-native/1.0.0` + `FourJobs` `he4-enterprise/1.1.0`):

1. **Chuẩn bị và ghim vào bundle (`prepare`)**:
   - Kiểm tra cấu hình `FourJobs` hỗ trợ `agent2-rule-snapshot/1.0.0` (`rules`, `c3`, `graph`) và ít nhất một profile đã cấp khóa tại doanh nghiệp (`CryptoBridge.public_context`).
   - Ghim `context` (bindings DN, worker URL, worker verify key, `implementation_sha256`, checksums `server.zip` và `client.specs.json`) cùng `key_contexts` (epoch khóa và hash evaluation key theo từng profile; profile chưa cấp khóa giữ `null`, không tự sinh khóa khi chấm) vào slot `he` của bundle.
2. **Pin lượt chạy và khôi phục bền vững (`run` / `execute`)**:
   - `ReleaseStore.pin` ghim cả `execution_mode=cloud_ciphertext_only`; dùng lại cùng `run_id` cho chế độ local trả `RELEASE_RUN_CONFLICT`.
   - Liên kết `he_job` (`rhej_`) trong `ReleaseStore` gắn `pin_id`, `job_id` và `bundle_binding` (tenant, company, `run_id`, `pin_id`, `bundle_id`, `snapshot_id`, checksums, `as_of`, `he_component_sha256`); không lưu bearer token.
   - Child job trong `FourJobs` dùng idempotency key `bundle:<pin_id>` nên nếu node doanh nghiệp gián đoạn giữa lúc tạo child job và lưu `he_job` thì khi gửi lại vẫn nối đúng job cũ, không tạo job thứ hai.
   - Khi worker đang tính, trả `409 PIPELINE_RUN_PENDING`; giao diện hiển thị nút **Tiếp tục yêu cầu đã lưu** giữ nguyên `run_id`, `snapshot_id` và chế độ HE sau reload (kể cả khi con trỏ staging đã chuyển sang bundle khác). Chỉ tài khoản đã gửi được tiếp tục job đang chạy; kết quả hoàn tất đọc theo quyền chung của doanh nghiệp.
3. **Tính trên bản mã và hậu xử lý tại doanh nghiệp (`adapt` → `score_and_coalesce`)**:
   - Cloud worker chỉ nhận bản mã và evaluation key công khai cho các mạch hiện hỗ trợ: `P1` (khoản đơn và nhóm đồng thời), `C3`, `B1`, `B5/E4` (giữ vai trò `master_quality`, không cộng đôi điểm giao dịch).
   - **30 luật còn lại** (`unavailable`; `D1–D6`, `F4` ở cấp tập nguồn) và **nhánh thống kê / ML theo contract 33 feature** trả `unavailable` (`complete_catalogue=false`, `native_33_feature_he_unsupported`); không lấy điểm ECOD/RobustZ local giả làm kết quả HE và không fallback chấm rõ.
   - Trước khi đưa kết quả vào gộp vụ và cấp ngân sách, `BundleHE` kiểm lại snapshot/cutoff, đủ định danh giao dịch, `bundle_binding`, checksums build/implementation và `key_epoch` / `evaluation_keys_sha256` của từng profile đã chạy.
   - Giải mã, áp chính sách bundle đã ghim, gộp vụ, xét ngân sách, ghi hàng đợi shadow, tạo `review_packet`, xử lý `ActionTask`/chứng từ và xuất báo cáo JSON/CSV đều thực hiện tại node doanh nghiệp, giữ nguyên bộ ba `snapshot_id`, `run_id`, `bundle_id`.

---

## 2. Đường dẫn thay đổi chính

| Thành phần | Mô tả |
|---|---|
| `agent2/sme_fraud/bundle_he.py` | Adapter `BundleHE` (`bundle-he4-native/1.0.0`): capture/check build & key epoch, dispatch/resume `FourJobs`, kiểm provenance và chiếu kết quả HE về contract phân tích nguồn 35 luật |
| `agent2/sme_fraud/pipeline_release.py`, `pipeline_release_store.py`, `pipeline_release_api.py` | Ghim slot `he` khi prepare `cloud_ciphertext_only`, đối tượng `he_job` (`rhej_`), checkpoint `execution` trước khi cấp ngân sách queue |
| `agent2/sme_fraud/release_shadow_plan.py` | Đánh dấu `he_execution`, `execution_location='cloud_ciphertext_only'`, `is_selected_arm_complete=False` và giới hạn độ phủ HE trong `score_and_coalesce` |
| `agent2/sme_fraud/bundle_reviews.py`, `bundle_workspace_api.py`, `review_server.py` | Expose `execution_modes`, nhận `execution_mode` khi submit/resume, truyền `he_header` và tự động gắn `BundleHE` khi `FourJobs` hỗ trợ `submit_bound` |
| `agent2/experiments/he4/coordinator.py`, `windows_bridge.py` | `FourJobs.submit_bound`, kiểm `_check_bundle_keys` theo epoch đã ghim và `CryptoBridge.public_context` chỉ đọc (không tự sinh khóa) |
| `agent2/sme_fraud/web/bundle-workspace.html`, `bundle-workspace.js`, `pipeline-releases.html`, `pipeline-releases.js` | Chọn chế độ `cloud_ciphertext_only`, hiển thị trạng thái/giới hạn HE, lưu/reload/tiếp tục đúng `run_id` đang chờ |
| `agent2/tests_he/test_bundle_he.py`, `agent2/scripts/check_bundle_he_ui.py`, `agent2/scripts/check_bundle_he_native.py` | Kiểm thử tích hợp giao thức/cắt lỗi, kiểm thử UI Portal/Chrome và kịch bản nghiệm thu Concrete FHE thật qua HTTP cho `C001`/`C002` |
| `agent2/docs/BUNDLE_HE.md`, `agent2/docs/BUNDLE_ORCHESTRATOR.md` | Tài liệu vận hành, phạm vi, giao nhận/khôi phục và giới hạn HE trong bộ điều phối bundle |

---

## 3. Bằng chứng chạy thực tế

Toàn bộ kiểm thử chạy trên môi trường cô lập, khóa DPAPI mới tạo trong thư mục tạm, dữ liệu `C001`/`C002` mô phỏng; tách bạch rõ bằng chứng Concrete FHE thật khỏi các bài kiểm thử dùng transport mô phỏng.

| Nhóm kiểm chứng | Tệp bằng chứng | Quan sát chính | Kết quả |
|---|---|---|---|
| **Concrete FHE thật qua HTTP (`C001` & `C002`)** | [native_fhe_report.json](native_fhe_report.json), [C001-business-report.json](C001-business-report.json), [C002-business-report.json](C002-business-report.json) | Worker Concrete thật trên WSL HTTP xác thực; chỉ cấp khóa `rules` (`P1`), các profile chưa cấp khóa giữ `unavailable`. `C001` (`herun_2e4c6fd391f74359b726820a17ef7099`): `AUDIT_0000` trúng `P1` (`evaluated_hit`, điểm `20`), `2` vụ (`1` tiếp nhận vào shadow queue, `1` chờ backlog), tạo `1` phiếu rà. `C002` (`herun_2712dcce2d994f5c8a61a7038bc73f6c`): `AUDIT_0000` `evaluated_no_hit` (điểm `0`), `1` vụ chờ backlog, `0` phiếu rà. Cắt kết nối giả lập sau `/v1/evaluate` của `C001` tự khôi phục qua `/v1/results`; khởi động lại `ReleaseService` đọc lại đúng observation mà không gửi lại worker (`861.468s`). | **PASS (`actual_fhe=true`)** |
| **Backend unit & integration (`8` modules)** | [backend_tests.json](backend_tests.json) | `test_bundle_he` (9 ca: dispatch/replay không gọi clear scorer, chặn bundle local/thiếu khóa, lệch key/config, chỉ bật phần có khóa, crash trước `he_job` & sau queue commit, chặn sửa `data_checksum`, restart `FourJobs`, Portal HTTP pending→resume, cô lập `C001`/`C002` và không lưu token), cùng `test_bundle_workspace`, `test_bundle_remediation`, `test_pipeline_release`, `test_release_shadow_plan`, `test_he4_coordinator`, `test_he4_rule_snapshot_coordinator`, `test_bundle_release_e2e_acceptance`. Tổng **89 tests, 0 failures, 0 errors, 0 skipped**. | **PASS** |
| **Portal UI — chế độ HE & tiếp tục job (`Chrome`)** | [he_ui_report.json](he_ui_report.json), [he-business-report.json](he-business-report.json), [desktop.png](desktop.png), [mobile.png](mobile.png) | 5 nhóm kiểm tra trên Portal/Chrome: chọn `cloud_ciphertext_only` → nhận run pending bền vững → reload trang giữ nguyên `run_id` và chế độ HE → bấm **Tiếp tục yêu cầu đã lưu** hoàn tất vào hàng đợi/báo cáo chung → mở vụ, kiểm tra nút giao việc và tải JSON (`he_execution=true`) → kiểm tra mobile `390x844` không tràn ngang và cô lập `C002`. | **PASS** |
| **Hồi quy UI bundle local & xử lý task (`Chrome`)** | [local_ui_report.json](local_ui_report.json) | 14 nhóm kiểm tra `check_bundle_workspace_ui.py` trên `C001`/`C002` sau khi cập nhật `bundle-workspace.js`: chạy local shadow, rà phiếu, giao việc, upload/verify/complete/reopen chứng từ & task, retry/reload, xuất JSON/CSV và điều hướng Portal. | **PASS** |
| **Hồi quy UI phát hành & rollback (`Chrome`)** | [release_ui_report.json](release_ui_report.json) | 8 nhóm kiểm tra `UI-01`..`UI-08`: prepare, qualify gate, approve, activate, resume request cũ sau khi đổi bundle, rollback và thu hồi quyền director. | **PASS** |

---

## 4. Giới hạn và lý do chưa mở Production / DONE R6

1. **Độ phủ HE hiện tại là từng phần (`complete_35_rule_he=false`, `native_33_feature_he=false`)**: chỉ các mạch `P1`, `C3`, `B1`, `B5/E4` có circuit Concrete; 30 luật còn lại và toàn bộ nhánh thống kê/ML 33 feature trả `unavailable` trong chế độ `cloud_ciphertext_only`.
2. **Dữ liệu và kết quả rà là mô phỏng (`synthetic=true`)**: chưa có bộ nhãn `ReviewLabel` đã xác minh trên dữ liệu doanh nghiệp thật để chứng minh hiệu quả phát hiện gian lận (`D-09`).
3. **Các cổng quản trị mở (`D-04, D-05, D-06, D-07, D-09, D-14, D-17, D-18, D-19`)**: ngân sách vụ sản xuất, SLA tồn đọng, ngưỡng chất lượng và định danh cá nhân độc lập trên Portal vẫn đang mở (`production_approved=false`).
4. **Chưa triển khai lên Portal live (`live_deployed=false`)**: toàn bộ thay đổi được giữ ở workspace kiểm thử, sẵn sàng để người phụ trách rà soát.
