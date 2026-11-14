# REPORT — R1 immutable snapshots, CR-007

- spec_version: 2.1. Bắt đầu 10/11/2026, bàn giao 11/11/2026 (Asia/Saigon).
- Task được giao: tải tệp → xem kiểm tra → xác nhận → snapshot bất biến; khóa source/mapping/checksum/version và retry không trùng.
- Phần được giao: **READY_FOR_REVIEW**. Toàn bộ R1: **PARTIAL** vì R1-02/06 chưa nối feature replay. Không ghi DONE/production hoặc tự chuyển R2.
- Base commit: `f203b39828f567171916b5b4744728ed4b63d17f`, working tree chưa commit. Không reset/merge/push trong task này.
- Người thực hiện kỹ thuật: Codex. Người duyệt thật: chưa được chỉ định.
- Input contract 1.0.0, validator/report 1.1.0 giữ nguyên. Import/snapshot/parser protocol 1.0.0, SQLite storage user_version=1, application_id=1093817137.
- Source/spec/fixture hashes: `artifact_manifest.json`, `preservation.json`, `spec_hash_changes.json`; source .sql và parser/backend/test đều được ghi hash.

## Kết quả

Đã có backend upload JSON nguyên byte → preview → xác nhận lưu → DataSnapshot. Không khôi phục API Agent2 cũ. Snapshot lưu ID, checksum dữ liệu canonical, checksum manifest, phiên bản hợp đồng/schema, source/mapping hashes, parser/validator/profile/report versions, nguồn report/import/revision và người/thời điểm tạo. Giữ số nguyên VND có dấu, ID dạng chuỗi và observed_at của nguồn; không tự đổi thành giờ upload.

Tệp gốc lưu BLOB theo SHA256 trong đúng tenant/DN. Draft/import revision, mapping, preview/report và provenance được giữ; đổi source hoặc mapping tạo revision mới và bỏ active preview. Không commit preview cũ hoặc client report tự tạo. Mapping chỉ đổi tên cột cấp record theo schema, không code/biểu thức/default thời gian; phát hiện cột ghi đè. JSON lỗi được giữ ở staging/report bị rejected, không thành snapshot. Tệp của DN khác không được preview/commit thành dataset của DN đang chọn; không trả bản ghi của DN khác.

Preview khóa schema SHA256, source/mapping/data/report checksums, revision, quyền tenant/DN/actor/permissions và fingerprint code/dependency liên quan; mặc định TTL 15 phút. Commit cần acknowledge=true, expected_revision, preview_id, các hash đúng và Idempotency-Key. Backend parse/validate lại nguồn trong transaction, so kết quả với preview; expiry được kiểm cả trước/sau revalidation. Thay validator/schema/permission context buộc preview lại.

Tạo snapshot, cập nhật import committed, audit và idempotency receipt trong một transaction SQLite BEGIN IMMEDIATE, synchronous=FULL, foreign_keys=ON, WAL. Idempotency key cùng scope/thao tác/nội dung trả lại receipt cũ; dùng khóa cũ với nội dung mới bị conflict. Mất phản hồi sau commit hoặc restart vẫn lấy đúng snapshot qua receipt, kể cả preview đã hết hạn; quyền hiện hành vẫn bắt buộc. Hai import cùng source/mapping/data/versions trong cùng DN dùng lại snapshot, vẫn giữ từng import/audit/receipt và provenance gốc. Bản snapshot cũ không bị thay khi có dữ liệu mới.

Source/report/revision/snapshot/audit/receipt có trigger chặn UPDATE/DELETE. Draft đã committed không sửa được; API snapshot chỉ đọc. Đọc snapshot và replay receipt kiểm lại checksum; dữ liệu/manifest hỏng bị báo ARTIFACT_INTEGRITY, không trả data. Checksum là kiểm tra toàn vẹn, không phải chữ ký số hay chống mọi quyền quản trị trực tiếp DB/OS.

Auth guard dùng chung với validate: quyền được kiểm trước body/storage, sau khi chờ writer và trước transaction COMMIT/return. Thu hồi quyền trong lúc đọc/parse gây rollback, không để commit bằng scope cũ. Draft/report riêng theo actor + tenant + DN; snapshot đọc theo quyền data.import trong cùng tenant/DN. Kho mới do --snapshot-db/AGENT2_SNAPSHOT_DB cấu hình; không đụng --database legacy hoặc DB review cũ. DB cũ không đúng application_id/version bị từ chối, không migration ngầm.

## Đường dẫn thực

| Path | Thay đổi |
|---|---|
| agent2/sme_fraud/snapshots.py | Store/revision/cache report/checksum/atomic commit/idempotency/audit/read |
| agent2/sme_fraud/snapshot_storage.sql | Schema storage v1 và immutability triggers |
| agent2/sme_fraud/import_files.py | Canonical JSON, source/mapping hash, mapping contract và parser/context fingerprint |
| agent2/sme_fraud/snapshot_api.py | Upload/source/mapping/preview/commit/report/manifest/data HTTP |
| agent2/sme_fraud/validation_api.py | Guard/transport được dùng chung, giữ route validate cũ và kiểm lại quyền sau body |
| agent2/sme_fraud/review_server.py | Nối GET/POST/PUT mới, --snapshot-db; health vẫn pipeline_ready=false |
| agent2/tests/test_snapshots.py | 42 test mới về workflow, stale, retry, concurrent, scope, rollback, corruption |
| agent2/scripts/demo_snapshot_flow.py | Demo HTTP tự tạo credential thử, lưu snapshot mô phỏng trong kho riêng |
| agent2/docs/IMMUTABLE_SNAPSHOTS.md | Hướng dẫn thao tác/API/hash/retry và giới hạn |

Metadata core_manifest/README/spec cập nhật trạng thái. Các lõi luật/thống kê/graph/ML/feature không thay. Không thay code Portal hoặc Agent1/3/4.

## Kiểm thử

```powershell
cd D:\agent22\agent2
$env:PYTHONPATH='.;tests'
& .venv/Scripts/python.exe -X utf8 -u -B -m unittest discover -s tests -v
& .venv/Scripts/python.exe -X utf8 -u -B -m unittest test_input_contract test_validation_backend test_transition_server test_snapshots -v
& .venv/Scripts/python.exe -X utf8 -B scripts/demo_snapshot_flow.py
```

- Full suite: **468 test pass**, exit 0, skip 0, khoảng 170 giây. Baseline trước task 426; thêm 42 test. `native_tests.json/log` ghi command/cwd/commit/log SHA256.
- Final focused suite: **108 test pass**, exit 0, skip 0, từng testcase tại `focused_tests.json/log`; kiểm cả metadata/status và toàn bộ chức năng đang đổi.
- HTTP thực: upload + preview + commit + tải data, gửi commit lại 10 lần vẫn đúng một snapshot; `http_examples.json` có report/manifest/response/checksum thực từ fixture, không credential.
- Ten concurrent commits: đúng một snapshot; source change đua commit chỉ một bên thắng. Lỗi được tiêm giữa snapshot/audit/receipt làm rollback; sửa lỗi và retry cùng key tạo đúng một snapshot.
- Snapshot qua restart và mất phản hồi được trả lại đúng ID. Key bị tái sử dụng với body khác bị conflict. Đổi file/mapping/context hoặc hết hạn preview không tạo snapshot.
- Permission guard: DN A gọi mọi route B không đọc body/storage; đã có resource B thì đoán ID trên route A trả 404, counts/data rỗng. Thu hồi quyền sau body hoặc ngay trước transaction hoàn tất gây rollback. JSON lỗi giữ report có dòng/cột, không tạo snapshot.
- Trigger UPDATE/DELETE có test; test corruption cố ý bỏ trigger trong DB tạm để kiểm checksum source/data/manifest và structured integrity error. Không sửa DB vận hành.
- Demo checked-in đã chạy thành công, lưu một snapshot mô phỏng thật trong `agent2/.runtime/snapshot_demo/snapshots.sqlite3`. Chạy lại không tăng số snapshot (vẫn 1); `demo.log`, `demo_result.json`. Credential thử được dọn, không in/lưu vào Git. DB runtime bị ignore.
- Hash 56 tệp Python baseline R0 giữ nguyên; diff Portal/Agent1/3/4 rỗng, tại `preservation.json`. Snapshot task không thay quy tắc/threshold, train/fit hoặc đánh giá accuracy.

## Acceptance R1

| ID | Trạng thái | Evidence chính |
|---|---|---|
| R1-01 | pass | Scope/query/import/snapshot không trộn ID giữa DN |
| R1-02 | blocked | Chưa bridge snapshot vào feature replay bitemporal; giữ helper và source timestamps chưa đủ để nghiệm thu toàn điều kiện |
| R1-03 | pass | Đổi file/mapping làm revision mới và preview cũ không commit; hash/context/expiry đều bị kiểm |
| R1-04 | pass | Retry tuần tự/đồng thời 10 lần, mất phản hồi/restart, transaction failure không tạo bản trùng/nửa chừng |
| R1-05 | pass | Số âm/nguồn thiếu được giữ/phân loại rõ, không bỏ dòng ngầm |
| R1-06 | blocked | Import concurrency không thay cho replay feature nhóm đồng thời từ lịch sử trước nhóm |
| R1-07 | pass | Backend thực có auth/scope guard trên upload/preview/commit/report/snapshot; không chỉ mock scope từ client |

`acceptance.json` chưa all-pass; không tạo kết quả R1 full READY_FOR_REVIEW hoặc sửa checker để lách gate. Stage wrapper toàn R1 còn phụ thuộc native mapping/feature tests sau khi làm R1-02/06.

## Giới hạn và bước sau

Giai đoạn này chỉ file JSON và mapping tên cột, chưa UI Portal/CSV/Excel/multipart, chưa identity/membership Portal. Kho local cho fixture theo D-10/D-18/D-19; chưa mở nguồn thật/production hoặc storage retention/deletion policy. Snapshot là tập đóng theo tham chiếu, chưa merge import tăng dần vào một dataset đang active. Không tự kích hoạt snapshot vào model/hàng đợi.

D-02 posted/D-16 VND giữ profile thử; D-03 history, D-04 weights, D-09 quality gate, D-14 checklist không tự chốt. Tiếp theo trong R1 là nối snapshot vào feature và replay known-time/nhóm đồng thời, rồi mới chạy đầy đủ gate. Phần snapshot được giao đã sẵn sàng rà; dừng, không tự chuyển R2.
