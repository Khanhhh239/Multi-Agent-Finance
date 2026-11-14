# R2 — đối chiếu điểm, cảnh báo và ngoại lệ, CR-017

- spec_version: 2.1; ngày 11/11/2026 (Asia/Saigon).
- Subtask parity/sửa mất diagnostics hoàn thành kỹ thuật; R2 tổng thể **PARTIAL**, chưa duyệt nghiệp vụ/release.
- Người thực hiện: Codex; commit nền `f203b39828f567171916b5b4744728ed4b63d17f`, workspace có thay đổi chưa commit. Hash nguồn thực tại provenance/artifact_manifest; HEAD không đại diện toàn bộ mã thử.
- Input contract 1.0.0, feature 33 cột/fingerprint và 6 core kernels giữ nguyên. Không đổi trọng số, ngưỡng, config active, labels hoặc D-03/04/09.

## Phát hiện và sửa

Hai khoản 9 triệu đồng cùng lúc cho hóa đơn 10 triệu: engine giữ điểm dòng riêng theo causal history trước nhóm, rồi phát cảnh báo nhóm P1 trên tổng 18 triệu. Adapter trước đây chỉ trả scores/hits, bỏ mất batch_events. Test tái hiện đã fail đúng vì diagnostics bị mất: [JSON](reproduction_tests.json), [log](reproduction_tests.log). [Sau sửa](batch_fix_tests.json) pass.

Nâng method-output lên **1.1.0**, thêm optional top-level native_rule_diagnostics cho nguồn retained-native: input_checksum, implementation_sha256, output giữ toàn bộ engine output ngoài scores/hits. Bao gồm batch_events/ngoại lệ nhóm, coverage/config, master findings, evidence findings, dynamic parameters/policy. Không cộng điểm batch vào dòng, không nhân bản event qua từng dòng, không tạo alert queue mới.

Adapter copy output để tránh alias với engine object; chặn diagnostics khác DN và participant ID ngoài nguồn đã gắn. Vẫn giữ đủ dòng khi engine thiếu một kết quả: dòng đó rules unavailable, score/raw_score null, reason rule_result_missing. Duplicate ID bị reject, không tự gộp hay lọc. Schema 1.0.0 cũ được lưu đúng checksum lịch sử: prior_method_scores.schema.json.

## Đối chiếu cùng nguồn/cấu hình

[Audit fixtures nghiệp vụ](native_fixture_parity.json), [log](native_fixture_parity.log): **209 lần đối chiếu**, **696 lượt giao dịch → 696 kết quả**, tất cả checks khớp. Script chạy 123 test nghiệp vụ có sẵn (0 fail/error/skip), instrument Case.score nhưng trả nguyên kết quả cho assertion nghiệp vụ cũ; baseline độc lập và adapter cùng dùng một bản nguồn scoped và config thực của fixture.

- 410 hits giữ nguyên toàn bộ evidence/ngoại lệ; 70 hit có suppressed_reason vẫn giữ điểm/cờ/căn cứ đúng.
- 135 cờ operational_alert, priority/admission/hard_trigger và toàn bộ native_score khớp.
- 4 batch events, gồm 3 event dương và 1 ngoại lệ nhóm, giữ nguyên; 515 dòng điểm 0 không bị loại. Điểm 0 không tự xác nhận không trúng/hợp lệ.
- Coverage, config, master_name_quality/master_identity_findings, evidence_findings, dynamic parameters/policy khớp toàn bộ. Source checksums/code bindings và input/engine output không bị sửa.

Các count là lượt fixture lặp, không phải 696 giao dịch thật duy nhất hoặc precision/recall. Profile legacy và default giữ đúng config của từng ca; nguồn native đủ cho luật đang thử không chứng minh mọi nguồn của 35 luật đều đủ hoặc đã nối canonical đầy đủ.

## Hồi quy và ví dụ

**597 tests pass**, 0 skip/failure/error, exit 0, **303.568 giây**: [JSON](native_tests.json), [log](native_tests.log). Thêm 13 tests; [70 focused](focused_tests.json) pass. Các ca mới có self-approval hợp lệ/vượt quyền, authority matrix, trả góp gắn yêu cầu chi, callback biết sau, nghỉ hưởng lương, đồng thời/batch exception, deep-copy và scope/participant guard, ID trùng, engine thiếu dòng.

Ví dụ đầu ra đối chiếu được lưu cùng baseline thật:

- [Nhóm vượt hóa đơn](batch_overpayment_output.json): 2 vào/2 ra, 2 batch events; có P1 dương, giữ điểm dòng gốc.
- [Ngoại lệ nhóm trả góp](batch_installment_exception_output.json): 2 vào/2 ra, 1 event có ngoại lệ.
- [Tự duyệt 5 dòng](self_approval_output.json): giữ cả C2 được phép và C2 vượt quyền, 5 vào/5 ra.
- [5 dòng mặc định](five_default_output.json): giữ đủ dòng điểm 0 và hit/ngữ cảnh nếu engine có.

[Numeric/native parity](parity_report.json): 5 phương pháp số sai số tuyệt đối tối đa 0 theo D-13; native scores/hits/diagnostics và 5 graph rows khớp. Core rule/graph/ML/statistics SHA256 trùng evidence CR-013; R1 fingerprint không đổi. Không phải benchmark hiệu quả.

[Demo company models](company_demo/summary.json): C001/IF và C002/ECOD nạp artifact current-code qua process score mới, mỗi bên 5/5 dòng mới khả dụng. SQL read-only đã kiểm payload checksum/full contract/code versions. Artifact fit mới trong kho demo, không đổi active; model code hash cũ vẫn bị chặn và inference không tự fit. Số dòng chấm được không là accuracy.

## Thay đổi và chạy lại

Mã liên quan: method_adapters.py, method_scores.schema.json, tests/test_rule_parity.py + rule_parity_support.py; script check_rule_parity.py và check_method_outputs.py. [Hướng dẫn](../../../../agent2/docs/RULE_PARITY.md).

```powershell
agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/check_rule_parity.py --output agent2/.runtime/native-fixture-parity.json
agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/run_r1_tests.py --report Agent2_Spec_v2_1/evidence/R2/rule_parity_20261111/native_tests.json
```

## Phạm vi còn lại

Snapshot canonical hiện đánh giá E3 khi đủ nguồn; luật thiếu nguồn/evaluator vẫn unavailable và tổng rules_incomplete/null theo CR-016. Native parity không giả đủ bridge canonical, benchmark E1–E2 hoặc full R2 gate. Chưa mở UI, queue, active/recovery hay chuyển R3. Không gán DONE/READY_FOR_REVIEW toàn R2 hoặc duyệt dữ liệu thật.
