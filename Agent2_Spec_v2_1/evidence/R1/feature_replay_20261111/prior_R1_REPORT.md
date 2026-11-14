# REPORT — R1, trạng thái hiện hành 11/11/2026

- spec_version: 2.1; milestone **PARTIAL**, không DONE hoặc production release.
- Đã hoàn thành phần hợp đồng CR-005, validation backend CR-006 và snapshot backend CR-007 theo yêu cầu người dùng.
- Báo cáo mới nhất: [Immutable snapshots](immutable_snapshots_20261110/REPORT.md).
- 468 native tests và 108 focused tests pass, không skip; 42 test snapshot mới.
- R1-01/03/04/05/07 pass tại backend local được triển khai. R1-02/06 còn blocked cho feature replay bitemporal/nhóm đồng thời.
- API mới có upload JSON, source/mapping revision, preview khóa hash/context, xác nhận commit atomic/idempotent, đọc snapshot bất biến. Chưa nối Portal identity, màn nhập/CSV/Excel hay feature replay; chưa mở dữ liệu thật.
- Source/contract/storage/hashes/evidence: import_contract.json, snapshot_contract.json, module_map.csv, acceptance.json và immutable_snapshots_20261110/artifact_manifest.json.
- Báo cáo và kết quả trước được giữ tại immutable_snapshots_20261110/prior_R1_REPORT.md, backend_validation_20261110/REPORT.md và các log gốc; không ghi đè log/test baseline.
- Người thực hiện kỹ thuật: Codex; người duyệt thật chưa được chỉ định. Dừng phần snapshot; không tự chuyển R2.
