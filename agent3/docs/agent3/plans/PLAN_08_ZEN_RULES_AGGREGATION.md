# PLAN_08 — GoRules ZEN, Decimal, trace và tổng hợp kết quả

> Trạng thái triển khai: **IMPLEMENTED_TECHNICAL — 15/10/2026**. [Gate](evidence/gate_08.md), [runbook](evidence/plan08/runbook.md), [test report](evidence/plan08/validation_summary.json). Legal release còn PENDING; models thực tế DRAFT.

[Lộ trình tổng](README.md) · Trước theo thứ tự đọc: [PLAN_07](PLAN_07_LEGAL_TAXONOMY_PLANNING.md) · Sau: [PLAN_09](PLAN_09_COMPLIANCE_MVP.md)

## 1. Kết quả cần đạt và điều kiện bắt đầu

Chạy mọi unit đủ điều kiện, giữ tiền chính xác, trace có nguồn và tổng hợp theo hợp đồng mà không tạo false PASS.

- Phụ thuộc bắt buộc: PLAN_07 đạt gate; spike money boundary là chốt đầu tiên.
- Ước lượng: **4–6 ngày công**, một người làm tập trung; chưa bao gồm thời gian chờ dữ liệu/hạ tầng/nghiệp vụ.
- Đối chiếu [NEW_PLAN](../NEW_PLAN.md): mục 9, 11, 13.
- Đầu vào: RulePlan, contract spike, legal/taxonomy mappings, rule fixtures.

Theo yêu cầu người dùng, tiếp tục kỹ thuật từ PLAN_07 bằng models/fixtures tổng hợp; không tự đóng legal approval/taxonomy gate còn mở. Chưa phát hành rule thuế thực tế hoặc nối tự động vào UI/job.

## 2. Tài sản hiện có và cách tái sử dụng

scripts/spike_zen_contract.py và docs/research/ZEN_CONTRACT_SPIKE_2026_10_11.md đã quan sát ZEN 0.53: Decimal object không nhận, string-number lỗi, số lớn mất chính xác. Trace gốc không tự có normalized boolean conditions. Legacy wrapper có nhánh no-hit→PASS; không copy semantics đó sang contract mới.

Kiểm tra lại tính tồn tại/phiên bản khi triển khai; kết quả kiểm kê là bằng chứng tham khảo, không thay nghiệm thu runtime đích.

## 3. Module và hợp đồng cần xây

Các module sau đã được triển khai kỹ thuật; xem trạng thái từng task và giới hạn trong gate:

`agent3_tax_compliance/src/rules/{zen_adapter,money_boundary,trace,outcomes,aggregator}.py; rules/models/; tests/rules_v1/`

SUCCEEDED có result PASS/FAIL/REVIEW và error=null; ERROR có result=null + reason/retry/next_action. Output key phải khớp planned unit và record revision. Rule execution không trả NOT_APPLICABLE; đó là planning. Raw trace bất biến, normalized conditions ghi origin ENGINE/ADAPTER/NOT_OBSERVED.

Mọi artifact phải có schema/config version, input hash hoặc record revision, creator/stage và timestamp. Artifact chứa dữ liệu thật lưu ngoài git theo policy; tài liệu chỉ ghi metadata đã che dữ liệu.

## 4. Công việc chi tiết theo thứ tự

### P08-T01 — Chốt money boundary bằng spike

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Pin engine version; thử fixed-scale integer trong miền đã chứng minh, decimal string với so sánh ngoài engine hoặc decimal-safe path thực tế. Chọn một phương án có proof fixtures, reject overflow/scale unsupported.
- Đầu ra: money_boundary_decision.md + executable spike.
- Kiểm chứng: Không chấp nhận numeric transport mất chính xác; không có phương án an toàn thì dừng money rules và giữ operational blocker.

### P08-T02 — Adapter input/output typed

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Chỉ nhận ELIGIBLE context, JSON serialize theo money contract, pin model hash/version. Validate response shape và timeout.
- Đầu ra: zen_adapter.py.
- Kiểm chứng: Non-eligible bị từ chối; malformed response/timeout ra ERROR, không REVIEW/PASS.

### P08-T03 — Tạo rule models MVP

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Tách content, VAT treatment/rate/category và non-cash theo registry; điều kiện planning không lặp ngưỡng 5 triệu trong engine. Ghi hit policy/pass path/no-hit behavior rõ từng model.
- Đầu ra: model files + truth tables.
- Kiểm chứng: No hit không mặc định PASS; mẫu thiếu input bị planning giữ lại trước engine.

### P08-T04 — Trace normalization trung thực

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Lưu engine raw trace rồi map rule/unit/condition IDs. Nếu engine không quan sát condition cụ thể thì NOT_OBSERVED hoặc instrument bằng deterministic adapter có origin/version.
- Đầu ra: trace.py, normalized_trace schema.
- Kiểm chứng: Không gán condition=true từ việc row match nếu không đủ chứng minh; replay raw và normalized cùng model version.

### P08-T05 — Chạy độc lập và retry đúng key

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Executor chạy mọi eligible unit dù unit khác FAIL/ERROR; outcome attempt có attempt_id, canonical outcome dedupe theo evaluation key. Retry bounded, không đổi revision.
- Đầu ra: executor.py + attempt store.
- Kiểm chứng: Một unit lỗi không nuốt unit hợp lệ khác; retry không nhân đôi số evaluated.

### P08-T06 — Aggregator theo unit và rule riêng

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Đếm eligible/evaluated/pass/fail/review/error theo unit, distinct rules riêng. Scope exclusions, unknown applicability, discovery và missing outcomes là blockers.
- Đầu ra: aggregator.py.
- Kiểm chứng: ERROR không tính evaluated thành công; no in-scope → coverage NONE/NO_VERDICT; precedence FAIL>REVIEW>NO_VERDICT>PASS_WITHIN_SCOPE>PASS.

### P08-T07 — Reject contract violations

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Chặn duplicate/stale/unexpected/non-eligible outcomes, thiếu trace bắt buộc và version mismatch. Processing ERROR có verdict null, không gửi câu kết luận hợp lệ sang explainer.
- Đầu ra: outcome validator + error fixtures.
- Kiểm chứng: Thiếu eligible outcome không biến thành no-rules PASS; không lọc bỏ outcome xấu rồi công bố phần còn lại.

### P08-T08 — Nghiệm thu truth tables

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Test boundary money/date/treatment cùng legal model fixtures đã kiểm. So expected aggregate từng scenario với output, lưu model hashes và runtime.
- Đầu ra: rules_contract_report + gate_08.md.
- Kiểm chứng: FAIL vẫn giữ review_required/errors; FULL chỉ khi không còn blockers theo scope; model chưa có legal evidence không phát hành.

## 5. Tiến độ bên trong chặng

- Ngày 1: money spike/decision; đây là gate nội bộ trước rule implementation.
- Ngày 2–3: typed adapter, models và truthful trace.
- Ngày 4: execution/retry/aggregation.
- Ngày 5–6: negative contract tests, truth tables và replay.

Cuối mỗi ngày cập nhật task IDs đã làm, bằng chứng và blocker vào bảng tiến độ tổng. Khi phát hiện phụ thuộc mới hoặc scope tăng, ghi lại estimate còn lại; không cố giữ lịch bằng cách bỏ invariant.

## 6. Ca kiểm thử và tình huống bắt buộc

- [x] 9007199254740992 + 1 không được mất đơn vị.
- [x] Một eligible unit bị timeout, unit khác FAIL: giữ FAIL và error.
- [x] Duplicate outcome hoặc revision cũ → contract error.
- [x] Items discovery incomplete nhưng mọi item thấy được PASS.
- [x] Không có in-scope rule → NO_VERDICT, không PASS.
- [x] Engine no-hit/malformed output phải đúng explicit policy.

Dùng fixture tổng hợp nhỏ cho contract/recovery tests, dữ liệu có nhãn cho accuracy và sandbox thật cho connector. Không thay accuracy evaluation bằng unit test parser. Chỉ chạy phần test phù hợp chặng và integration qua ranh giới vừa thay đổi.

## 7. Gate hoàn thành và bàn giao

**Điều kiện gate:** Money boundary được chứng minh trong supported domain; outcome/trace/aggregate invariants qua; không có auto-PASS do no hit, unknown hoặc missing outcome.

- [ ] Mỗi task bắt buộc có artifact và cách tái hiện kiểm chứng.
- [ ] Không còn lỗi vi phạm hợp đồng dữ liệu, tiền, tenant hoặc version trong phạm vi chặng.
- [ ] Có bảng giới hạn hỗ trợ, ca chưa đạt và next action; quality target thiếu dữ liệu không được đánh dấu đạt.
- [ ] Ghi `evidence/gate_08.md`: input versions, test/eval command, ngày chạy, kết quả, số mẫu, lỗi còn lại và quyết định gate.
- [ ] Bàn giao: PLAN_09 nhận ComplianceResult typed, coverage/scope/next_actions và trace; PLAN_12 chỉ đọc các kết quả này.

## 8. Khi chưa đạt hoặc bị chặn

Ghi blocker cụ thể, task bị ảnh hưởng, điều kiện gỡ và người/nguồn cần cung cấp. Tiếp tục các task độc lập. Không biến thiếu dữ liệu, thiếu môi trường hoặc lỗi runtime thành kết quả thành công; không ghi DONE khi chỉ có mock mà gate yêu cầu dữ liệu thật.

Lệnh triển khai/test sẽ được ghi cùng artifact khi module đã tồn tại. Quy ước lệnh và cách cập nhật tiến độ nằm trong [README lộ trình](README.md); tài liệu này không yêu cầu chạy benchmark hoặc cài dependency ngay lúc chia kế hoạch.
