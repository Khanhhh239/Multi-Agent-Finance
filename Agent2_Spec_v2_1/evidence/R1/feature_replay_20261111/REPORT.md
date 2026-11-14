# REPORT — R1 snapshot feature/replay, CR-008

- spec_version: 2.1; ngày 11/11/2026, Asia/Saigon.
- Trạng thái **R1 READY_FOR_REVIEW**, checker exit 0, release_approved=false. Không ghi DONE hoặc tự chuyển R2.
- Base commit `f203b39828f567171916b5b4744728ed4b63d17f`, working tree chưa commit; hash provenance từ stage runner trong `../commands_result.json`, hashes cuối tại `artifact_manifest.json`.
- Người thực hiện kỹ thuật: Codex; reviewer thật chưa được nhóm chỉ định.
- Input contract 1.0.0, validator/report 1.1.0, snapshot protocol 1.0.0 giữ nguyên. Contract feature adapter mới `snapshot-point-in-time/1.0.0`, **33 predictor số**.

## Kết quả và cách tái sử dụng

Đã nối DataSnapshot qua `snapshot_features.build_from_snapshot` vào **features.build_features nguyên bản**. Không sửa lõi/contract legacy, không gọi generator, nhãn hoặc fit model. Adapter chỉ xuất các primitive có nguồn/ý nghĩa phù hợp: magnitude/lịch sử theo loại, chu kỳ giờ/thứ nghiệp vụ, graph ngân hàng và số dòng/cân đối bút toán. Quan hệ canonical invoices–allocations–documents–approvals được đọc sau lọc thời điểm để tạo các số đếm/tỷ lệ nguồn đã biết; không giả đây là toàn bộ đối chiếu nghĩa vụ R4.

Schema input mới không có đầy đủ policy, lịch, VAT, tuổi pháp nhân và trường legacy. Private DTO đáp ứng core có placeholder chỉ cho phần không xuất; không biến framework TT200, hạn mức 1 VND, lịch nghỉ trống hoặc stub người lập thành dữ kiện predictor. Allowlist mới không chứa những feature phụ thuộc các giả định đó. Contract mới không tự tương thích cache/model legacy; fingerprint gồm ordered columns, mô tả/transform/missing, cutoff và fingerprint core/adapter.

Core chỉ chấp nhận số dương và timestamp giây +07:00. Adapter dùng magnitude trong DTO, giữ dấu/zero riêng và tiền VND signed nguyên vẹn ở snapshot/evidence. Zero ảnh hưởng legacy magnitude history thì trả null với lý do thay vì xuất thống kê sai. Timestamp full precision được dùng cho tất cả selection/grouping; thứ tự thời gian riêng đưa vào core để không gộp microseconds, chỉ các primitive không lệ thuộc cửa sổ đồng hồ đó được xuất. Biến lịch `event_*` vẫn dùng ngày/giờ nghiệp vụ thật VN. Các field như giờ tạo, ngày nghỉ, framework, quyền tự duyệt, VAT không có nguồn không được xuất.

## Semantics thời gian

`as_of` job chặn giao dịch tương lai trên cả effective_at và observed_at. Mỗi revision được tạo feature tại available_at=max(effective_at, observed_at), ghi rõ per-row as_of và event_at. Revision mới có vector/provenance mới; rerun ở global as_of muộn hơn không lấy thêm chứng từ để sửa vector cũ.

Trước mỗi nhóm, lọc context observed_at<=cutoff và effective_at<=event_at rồi mới chọn revision, không chọn latest toàn cục trước. Lịch sử giao dịch có effective_at<event_at và available_at<cutoff; loại self identity và chỉ chọn một revision đủ điều kiện. Cùng thời điểm nghiệp vụ **hoặc cùng availability** không thấy nhau trong history. Target cùng nhóm được đưa vào core theo batch hiện có, lịch sử được cập nhật sau nhóm. Chọn source/current master theo hai thời gian, clearing bank không giữ cạnh cũ. So sánh datetime aware, không so text offset hỗn hợp.

Ví dụ fixture: H0 có trước; T001/T002 đồng thời cùng thấy đúng H0 và 4 triệu phân bổ trước, không cộng khoản của nhau. DOC_LATE không thay vector quá khứ; khi một document hóa đơn đủ điều kiện cho dòng ngày sau thì được dùng ở dòng đó. Late transaction/master/revision và future-effective master không backfill cho quá khứ. Hai doanh nghiệp có cùng T001/E001/V001 và thậm chí cùng bank identity vẫn tách lịch sử/graph đúng phạm vi.

## Kênh output và quyền

Job CLI `feature_pipeline.py` xác thực trước mở business DB, dùng snapshot scope/checksum và kiểm lại quyền trước xuất. Publish thư mục artifact khi đủ các file; không ghi đè. Retry cùng input/contract/as_of trả artifact cũ sau kiểm checksum. Không có HTTP fit/score/job endpoint mới.

- features.json: chỉ numeric/null theo allowlist, không ID, nhãn, hash, tên nguồn, seed/template hoặc văn bản chứng từ.
- missing.json: mask boolean song song; null không tự thành 0 hoặc normal score.
- rows.json: row_index + tenant/DN/ID/revision/event_at/as_of.
- evidence.json: source refs/revision/thời điểm thực, số tiền signed/tổng đối chiếu và missing reasons.
- contract.json/manifest.json: thứ tự/dtype/transform/fingerprint, snapshot checksums/as_of và hash từng kênh.

Đổi ID đồng bộ với tham chiếu không đổi số dự báo; đổi tên nguồn/hash chứng từ không đổi số. Label field lạ trong snapshot bị từ chối, không làm predictor. `read_artifact` kiểm manifest/file checksum, contract fingerprint, scope, row/column alignment, kiểu số hữu hạn và missing mask. Artifact hỏng báo lỗi thay vì ghi đè cache. Đây là integrity checksum, không là chữ ký số hoặc xác nhận chứng từ thật.

## Path thay đổi

| Path | Trách nhiệm |
|---|---|
| agent2/sme_fraud/snapshot_features.py | Replay hai thời gian, scoped selection, legacy DTO, allowlist/missing/provenance |
| agent2/sme_fraud/feature_pipeline.py | Authenticated local job + immutable separated artifact export/read |
| agent2/tests/fixtures/r1_feature_replay_v1.json | Frozen fixture 2 DN cùng IDs, prior/simultaneous/late/revision/signed/zero |
| agent2/tests/test_snapshot_features.py | 33 test causal, precision, anti-leakage, signed/zero, scope, CLI/artifact |
| agent2/tests/test_r1_acceptance.py | Bảy acceptance case nối snapshot/HTTP/feature thực |
| agent2/scripts/run_r1_tests.py | Unittest native JSON; map duy nhất 7 test catalog, không gán PASS thủ công |
| Agent2_Spec_v2_1/stage_commands.json | Lệnh native đã xác minh, versions, report/timeout đúng workspace |
| agent2/scripts/demo_snapshot_features.py | Demo local synthetic, tạo artifact, đối chiếu vector quá khứ giữa hai as_of |
| agent2/docs/SNAPSHOT_FEATURES.md | Semantics, missing/units/limits, CLI và cách thử |

Metadata/status/README/spec cập nhật; code Portal/Agent1/3/4 không đổi. Lõi `features.py`, `feature_contract.py` và 56 file Python thuộc baseline R0 giữ nguyên hash tại preservation.json.

## Bằng chứng kiểm thử

Lệnh formal từ D:/agent22:

```powershell
& agent2/.venv/Scripts/python.exe -X utf8 -u -B Agent2_Spec_v2_1/scripts/run_stage.py R1
& agent2/.venv/Scripts/python.exe -X utf8 -B Agent2_Spec_v2_1/scripts/check_evidence.py R1
```

- **508 tests pass**, 0 skip, 0 failure/error: `../machine_report_0.json`, `../command_0.log`, `../commands_result.json`. So baseline 468, thêm 33 feature tests và 7 catalog tests. Native exit 0, không timeout, report hash khớp.
- Bảy ID R1-01…07 đều map từ assertion thật trong test_r1_acceptance, acceptance dùng đúng run_id **b136fe73-dc33-49c3-889c-2553ce70b4cc**. Các test khác cũng được ghi riêng; skipped/expected-failure không được đổi thành pass.
- Checker exit 0: `checker_result.json/log`, status READY_FOR_REVIEW, release_approved=false.
- Final focused **43 tests pass** sau cập nhật metadata/status: `final_focused.json/log`; code adapter/core đã giữ nguyên trong formal run.
- Demo chạy thật, nguồn mô phỏng và kho riêng: `demo.log`, `demo_result.json`, `demo_feature_manifest.json`, `demo_rows.json`, `demo_features.json`, `demo_evidence.json`. Cùng T001/T002 có 1 giao dịch trước nhóm; global as_of muộn hơn giữ vector cũ.
- Full run đầu lỗi phần xuất báo cáo vì testcase dùng tên self.id đè unittest.id(). Đã đổi biến fixture thành snapshot_id, kiểm native runner focused trước chạy lại toàn suite. Bản lỗi được giữ ở `initial_runner_failure/`; không bỏ test hoặc đổi tolerance/threshold để làm xanh.

| ID | Bằng chứng chính | Kết quả |
|---|---|---|
| R1-01 | Hai snapshot C001/C002 cùng ID, feature prior count lần lượt 1/0, graph không trộn | pass |
| R1-02 | Snapshot thêm late document đổi data checksum nhưng vector/mask/evidence quá khứ bằng nhau | pass |
| R1-03 | HTTP đổi file/mapping làm preview cũ conflict, 0 snapshot trước preview mới | pass |
| R1-04 | 10 HTTP concurrent + 10 retry sequential: 1 snapshot ID, 1 commit event; restart/rollback unit tests cùng qua | pass |
| R1-05 | Signed/zero không mất dòng; missing có mask/lý do; tiền signed gốc nguyên vẹn | pass |
| R1-06 | Hai khoản đồng thời cùng baseline trước nhóm, đảo input không đổi; có thêm test microsecond và cùng availability | pass |
| R1-07 | Auth/scope deny trước body/storage, ID resource DN khác không trả data, thu hồi quyền chặn lưu/xuất | pass |

Fixture/contract được freeze trước formal run tại ../fixture_manifest.json và ../feature_contract.json. Contract/dtype/null/peer/window/zero-denominator có định nghĩa tại contract và hướng dẫn, không tự chốt threshold/weights ML.

## Hạn chế và kết thúc

Đây là nghiệm thu **kỹ thuật local trên fixture**, chưa là kiểm định accuracy hoặc quality gate R6. D-03/04/09/10/14/18/19 và người duyệt thật vẫn mở đúng phạm vi. Z-score giữ điều kiện 5 mẫu/.25 của core không là detector readiness. Graph canonical profile hiện bank-only; các cột legacy không đủ nguồn chưa bật. Replay tham chiếu theo từng nhóm có thể chi phí bậc hai, cần benchmark/worker orchestration trước dữ liệu lớn.

Chưa nối Portal identity, file UI/CSV/Excel, model/preprocess registry/fit/score R2 hoặc active queue; pipeline_ready/active_delivery vẫn false. Lưu tiền/chứng từ gốc và độ tin cậy timestamp còn cần nghiệp vụ/nguồn thật. R1 lên READY_FOR_REVIEW, cần reviewer người thật ghi DONE nếu chấp nhận; dừng tại đây, không tự chuyển R2.
