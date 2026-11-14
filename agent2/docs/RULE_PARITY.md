# Đối chiếu adapter với engine luật — CR-017

CR-022 bổ sung guard thời gian P1 native đã khai báo, sau finding CR-020. Điểm nghiệp vụ miền đủ nguồn giữ nguyên; nguồn hóa đơn chưa khả dụng tạo information_gap 0 điểm, không là evaluated_no_hit. [Bản sửa và kiểm thử](../../Agent2_Spec_v2_1/evidence/R2/p1_native_fix_20261111/REPORT.md). Các số liệu CR-017 bên dưới là lịch sử kiểm adapter, không thay cho nghiệm thu bản sửa hoặc full pipeline.

Trên cùng nguồn native đủ cho ca kiểm tra và cùng cấu hình, bộ đối chiếu chạy hai đường độc lập: `score_rules` trực tiếp và `native_inputs → score_batch`. Tái sử dụng fixtures nghiệp vụ hiện có, không thay ngưỡng hoặc baseline để làm đẹp kết quả. Đây là kiểm tra giữ nguyên hành vi, không đo độ chính xác phát hiện gian lận.

Mỗi ca kiểm tra:

- Đủ số giao dịch và đúng định danh, gồm dòng điểm 0; không lọc top-K.
- Điểm gốc/tổng, toàn bộ native_score, hard_trigger, operational_alert, priority, admission_basis và các trường quyết định tiếp nhận khác.
- Hit, evidence, suppressed_reason, ngoại lệ 0 điểm và cờ hard_trigger của ngoại lệ.
- Coverage, cấu hình, master findings, evidence findings, dynamic parameters/policy và cảnh báo/ngoại lệ sau khi đóng nhóm giao dịch.
- Checksum nguồn/code và input/engine objects không bị sửa bởi adapter.

Nguồn fixtures gồm tự duyệt hợp lệ/vượt quyền, ma trận quyền đã duyệt, callback ngân hàng biết sau giao dịch, trả góp gắn yêu cầu chi/hóa đơn, nghỉ hưởng lương có căn cứ, nhóm thanh toán đồng thời và các ca noise/spec/tax timing đã có trong repo. Profile legacy và mặc định được đối chiếu đúng cấu hình từng fixture.

## Cảnh báo nhóm từng bị mất

Hai khoản 9 triệu đồng cùng thời điểm, cùng hóa đơn 10 triệu: engine có thể không gắn P1 vào riêng từng dòng vì các dòng đồng thời không nhìn lịch sử của nhau. Sau khi đóng nhóm, engine phát `batch_events` P1 trên tổng 18 triệu. Adapter trước CR-017 bỏ mất phần này.

`method-output/1.1.0` bổ sung top-level optional `native_rule_diagnostics` cho profile native:

```text
native_rule_diagnostics
  input_checksum
  implementation_sha256
  output
    batch_events
    coverage / config
    master_name_quality / master_identity_findings
    evidence_findings
    dynamic_parameters / dynamic_policy
```

Giữ một bản event ở diagnostics, không nhân bản qua mỗi dòng hoặc cộng lại vào điểm giao dịch. Ngoại lệ của batch cũng được giữ nguyên. Diagnostics khác doanh nghiệp hoặc participant ID không thuộc nguồn đã gắn bị chặn. Đầu ra được copy, không chia sẻ object có thể sửa với output engine đầu vào.

Nếu engine thiếu kết quả cho một giao dịch, adapter vẫn giữ dòng đó: rules unavailable, điểm null, reason `rule_result_missing`. Đây là lỗi đầu ra, không phải điểm 0 hoặc giao dịch hợp lệ. ID đầu vào trùng bị từ chối, không tự gộp dòng.

## Chạy đối chiếu

```powershell
& agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/check_rule_parity.py --output agent2/.runtime/native-fixture-parity.json
& agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/run_r1_tests.py --suite test_rule_parity --suite test_method_adapters --suite test_rule_evaluation --suite test_method_jobs --suite test_rule_sources --report agent2/.runtime/parity-tests.json
```

Script đầu chạy các test nghiệp vụ thật và ghi từng lần Case.score qua adapter trên nguồn scoped giống nhau; counts là các lần quan sát fixture, có thể lặp dữ liệu, không phải số giao dịch thật duy nhất hay precision/recall. Thay version output không thay input contract, 33 feature hoặc kernel/weight. Hash adapter mới vẫn cần model tương thích theo guard CR-013; không tự fit hoặc active.

Snapshot canonical hiện mới có evaluator E3 khi đủ nguồn; các luật còn thiếu nguồn vẫn unavailable và tổng incomplete/null. Kết quả đối chiếu native không có nghĩa đã nối đủ luật canonical, hoàn tất benchmark hoặc duyệt toàn R2. Không tạo queue/UI hay nhãn mới.
