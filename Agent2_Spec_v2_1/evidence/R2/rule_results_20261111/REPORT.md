# R2 — kết quả từng luật đủ/thiếu nguồn, CR-016

- spec_version: 2.1; ngày 11/11/2026 (Asia/Saigon).
- Phần giao thêm hoàn thành kỹ thuật; R2 tổng thể **PARTIAL**, chưa nghiệm thu nghiệp vụ/production.
- Người thực hiện: Codex; commit nền `f203b39828f567171916b5b4744728ed4b63d17f`. Workspace có thay đổi chưa commit; hash thực trong provenance/artifact_manifest, không coi HEAD là toàn bộ nguồn thử.
- Input contract 1.0.0 và feature contract 33 cột giữ nguyên. Không đổi trọng số, active, queue hoặc tự quyết D-03/04/09.

## Kết quả

`methods.rules.details.rule_results` có một RuleResult cho mỗi trong 35 luật, theo `rule-results/1.0.0` và schema mới. Hiện E3 được chạy bằng helper/policy mặc định giữ lại khi đủ nguồn; các luật còn thiếu nguồn có status unavailable và lý do, không giả chạy đủ bộ.

| Trạng thái | matched | Điểm | Căn cứ |
|---|---|---|---|
| evaluated_hit | true | intrinsic_points và score theo policy | evidence_refs, cặp đối chiếu, similarity, threshold |
| evaluated_no_hit | false | 0 | Căn cứ và phạm vi nguồn đã so, không kết luận hợp lệ |
| unavailable | null | null | reason + bảng/trường/reference thiếu trong gaps |
| not_applicable | null | null | Loại giao dịch ngoài phạm vi luật |

E3 hit: intrinsic=3, contribution=0 vì master_quality. Giữ matched=true và bằng chứng; không diễn giải score 0 thành no-hit. Tên không đủ thông tin để chuẩn hóa là unavailable/name_content_insufficient, không bỏ qua rồi kết luận không trùng. Nguồn ready nhưng chưa có evaluator được kiểm chứng trả rule_evaluator_unavailable. Tổng canonical giữ rules_incomplete/null, không cộng tổng một phần.

Source producer rule_inputs vẫn có marker not_evaluated của bước chuẩn bị; rule_results là kết quả cuối. RuleInputs patch 1.0.1 chỉ lan truyền gap theo role: lỗi liên kết hóa đơn không chặn E3 nếu nguồn tên vẫn đủ. Kiểm scope, cutoff, source checksum và evidence bindings trước kết quả. Không dùng DTO placeholder, không fit khi chấm hoặc bỏ dòng theo hit luật.

## Đường dẫn

- `agent2/sme_fraud/rule_evaluation.py`: dispatcher, evaluator E3, checked source/evidence và trạng thái kết quả.
- `rule_results.schema.json`: bắt buộc unavailable/not_applicable có điểm/matched null; evaluated có số và căn cứ/lý do phù hợp.
- `method_adapters.py`: nối vào snapshot/CLI, reason tổng rules_incomplete.
- `rule_sources.py`: sửa role dependency, version 1.0.1.
- `tests/test_rule_evaluation.py`: 12 test mới; test adapter sẵn có cập nhật reason tổng và kiểm reason C2 riêng.
- [Hướng dẫn](../../../../agent2/docs/RULE_RESULTS.md), [catalog nguồn hiện hành](rule_source_catalog.json).

## Kiểm thử

**584 tests pass**, 0 skip/failure/error, 219.024 giây, exit 0: [JSON](native_tests.json), [log](native_tests.log). [57 focused](focused_tests.json) pass, gồm 12 evaluator mới, 13 nguồn và 32 adapter/job hiện hành.

Các ca mới kiểm hit/no-hit/missing/not-applicable, E3 parity với engine mặc định thực, strict threshold trước làm tròn, tên không đủ thông tin, revision tương lai, gap hóa đơn không lan sang E3, scope/cutoff/payload/evidence giả, schema chặn unavailable=0/false, output đủ dòng và không fit. [Checks từ test records](evaluation_checks.json).

[Ba demo snapshot](demo/summary.json): mỗi snapshot đúng 5 giao dịch, trả 5 kết quả, mỗi giao dịch đủ 35 RuleResults. HIT E3=true/3/0; NO_HIT=false/0/0; thiếu nội dung tên=null/null/null. C2 thiếu ma trận quyền luôn unavailable/null với gaps. Chỉ là dữ liệu mô phỏng, không accuracy/gian lận.

[Demo company models](company_demo/summary.json): C001/IF và C002/ECOD fit/score bằng process riêng, mỗi bên 5/5 dòng mới khả dụng, RuleResult hiện diện. Artifact DB checksum/full contract/code versions đã đối chiếu read-only; không đổi active. Manifest hiện hành tại `../fit_manifest.json`, manifest trước tại prior_R2_fit_manifest.json.

[Parity](parity_report.json): 5 phương pháp số sai số tối đa 0; 5 dòng native có rule score/hits/graph giữ nguyên. Core ML/statistics, preprocessing và fingerprint R1 không đổi. Đây không phải benchmark hiệu quả ML.

## Các lần chưa đạt được giữ lại

Import đầu có lỗi dư dấu ngoặc, sửa trước chạy: [log](initial_import_failure.log). Lần focused đầu còn 1 failure do fixture Case.score chạy profile audit legacy (E3 cộng 3), trong khi evaluator dùng policy mặc định phase2 (master quality đóng góp 0). Đã đối chiếu lại bằng score_rules mặc định trên nguồn/features thật; không sửa trọng số/baseline để làm đẹp điểm. [JSON](initial_focused_tests.json), [log](initial_focused_tests.log). Bản cuối 57 focused và 584 regression pass.

## Chạy lại và giới hạn

```powershell
agent2/.venv/Scripts/python.exe -X utf8 -u -B agent2/scripts/run_r1_tests.py --report Agent2_Spec_v2_1/evidence/R2/rule_results_20261111/native_tests.json
```

Chạy demo: `agent2/scripts/demo_rule_results.py --output-dir <thư_mục_mới>`. Cần Python venv hiện hành. Code adapter có hash mới nên artifact hash cũ bị từ chối theo guard CR-013, không tự refit; demo đã fit artifact mới riêng. Nguồn còn thiếu cần mở rộng hợp đồng/adapter đúng phiên bản rồi evaluator/parity tương ứng, không điền proxy.

Chưa hoàn tất evaluator cho toàn bộ bộ luật canonical, benchmark E1–E2, active/recovery/UI hoặc full R2 gate. Không gán DONE/READY_FOR_REVIEW toàn R2 hoặc chuyển R3. Không tạo nhãn, xác suất gian lận hoặc phê duyệt dữ liệu thật.
