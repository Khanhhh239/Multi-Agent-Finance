# PLAN_09 — Tích hợp compliance, giải thích bằng template và nghiệm thu

> Trạng thái triển khai: **NOT_STARTED**. Tài liệu là công việc dự kiến, không chứng nhận code đã hoàn thành.

[Lộ trình tổng](README.md) · Trước theo thứ tự đọc: [PLAN_08](PLAN_08_ZEN_RULES_AGGREGATION.md) · Sau: [PLAN_10](PLAN_10_INVOICE_XML.md)

## 1. Kết quả cần đạt và điều kiện bắt đầu

Nối OCR/PDF đã review với planning/rules; có demo kết luận theo phạm vi cùng bằng chứng, chưa cần LLM.

- Phụ thuộc bắt buộc: PLAN_06–08 đạt gate.
- Ước lượng: **4–6 ngày công**, một người làm tập trung; chưa bao gồm thời gian chờ dữ liệu/hạ tầng/nghiệp vụ.
- Đối chiếu [NEW_PLAN](../NEW_PLAN.md): mục 10, 11, 12, 13, 17.
- Đầu vào: Capture MVP, RulePlan, typed outcomes, aggregate, legal excerpt map.

Không bắt đầu phần phụ thuộc khi gate đầu vào chưa qua. Có thể chuẩn bị fixture/tài liệu độc lập, nhưng không ghi cả chặng DONE vì đã tạo scaffold.

## 2. Tài sản hiện có và cách tái sử dụng

Không dùng mô hình RAG cũ để bù metadata thiếu. OCR-only nhiều trường hợp chưa đủ chứng minh non-cash; dùng fixture/context hợp lệ có nguồn riêng để demo rule này và công khai thiếu evidence ở luồng OCR độc lập.

Kiểm tra lại tính tồn tại/phiên bản khi triển khai; kết quả kiểm kê là bằng chứng tham khảo, không thay nghiệm thu runtime đích.

## 3. Module và hợp đồng cần xây

Các đường dẫn sau là **đích dự kiến**, chưa hàm ý file đã tồn tại:

`agent3_tax_compliance/src/orchestration/; src/explanation/templates/; src/api/v1/{evaluations,rule_results}.py; tests/e2e_v1/`

Evaluation snapshot pin record revision + ruleset/capability/legal/taxonomy/master/calibration versions. API rule_results pagination theo evaluation_id và unit key. ExplanationTemplate nhận aggregate và validated evidence, không tự tính verdict; contract error không có câu kết luận thuế.

Mọi artifact phải có schema/config version, input hash hoặc record revision, creator/stage và timestamp. Artifact chứa dữ liệu thật lưu ngoài git theo policy; tài liệu chỉ ghi metadata đã che dữ liệu.

## 4. Công việc chi tiết theo thứ tự

### P09-T01 — Orchestrator theo revision

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Nối canonicalize→quality→planning→eligible execution→aggregate; stage artifacts persist, resume không trộn revision. Reevaluate tạo evaluation_id mới.
- Đầu ra: workflow.py + snapshot store.
- Kiểm chứng: Correction revision mới không đọc outcomes cũ; failure resume không lặp external side effect.

### P09-T02 — API evaluation và pagination

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: POST /v1/records/{id}/evaluations, GET /v1/evaluations/{id}, GET /v1/evaluations/{id}/rule-results?cursor=... và /attempts. Pin request idempotency với content/versions.
- Đầu ra: OpenAPI + API tests.
- Kiểm chứng: Rule results page stable khi attempts tăng; client biết unit vs distinct rule counts.

### P09-T03 — Template explanation v1

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Viết câu cho PASS/FAIL/REVIEW/NO_VERDICT/PASS_WITHIN_SCOPE, coverage, exclusions và next actions; link legal/evidence đúng selected version.
- Đầu ra: template pack.
- Kiểm chứng: PASS chỉ trong ruleset/revision đã nêu; thiếu data không diễn thành vi phạm; lỗi contract không tạo kết luận.

### P09-T04 — Hiển thị quality và compliance rõ

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Màn kết quả hiển thị dữ liệu cần sửa, rule đủ/chưa đủ input, kết quả rule và căn cứ. Giữ capture export dùng được nếu compliance chưa có coverage.
- Đầu ra: result view/client.
- Kiểm chứng: Review_required vẫn hiện khi verdict FAIL; ngoài source scope được giải thích bằng khả năng nguồn.

### P09-T05 — Bộ acceptance scenarios

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Triển khai ca NEW_PLAN 11.3: mixed outcomes, all-pass scoped, unknown direction/date, low confidence, source limitation, empty/incomplete items, processing errors.
- Đầu ra: tests/e2e_v1 + expected JSON.
- Kiểm chứng: Mỗi ca có raw→CFR→plan→outcome→aggregate→template; assertions kiểm semantics thay snapshot toàn bộ.

### P09-T06 — Nghiệm thu cùng dữ liệu thật

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Chạy functional set và frozen eval; đối chiếu expected legal result trên ca đã được gán nhãn căn cứ. Đo quality riêng, planning đúng riêng, engine đúng riêng.
- Đầu ra: compliance_mvp_report.md.
- Kiểm chứng: Không lấy overall OCR accuracy làm tax accuracy; báo sample size và chưa đủ evidence.

### P09-T07 — Runbook demo và phục hồi

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Chuẩn bị happy path, review correction, missing payment và timeout; nêu dữ liệu giả lập so với thật. Quy trình operator retry không sửa raw/outcome bằng tay.
- Đầu ra: demo_runbook.md + recovery.md.
- Kiểm chứng: Demo chạy offline với templates/fixtures khi LLM không có; lỗi engine thể hiện đúng ERROR.

### P09-T08 — Chốt mốc M2

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Lập release manifest gồm source/model/config/schema/rules/legal/taxonomy versions và gate evidence. Chưa đạt nhóm nào thì giảm phạm vi có ghi rõ, không đánh dấu cả chặng done.
- Đầu ra: release_capture_compliance_v1.json + gate_09.md.
- Kiểm chứng: Có replay được một evaluation từ artifacts; mọi blocker bắt buộc được xử lý hoặc phạm vi bị loại minh bạch.

## 5. Tiến độ bên trong chặng

- Ngày 1: orchestration + evaluation API.
- Ngày 2: templates/result view và pagination.
- Ngày 3–4: acceptance cases + real-data evaluation.
- Ngày 5–6: recovery, demo và release manifest.

Cuối mỗi ngày cập nhật task IDs đã làm, bằng chứng và blocker vào bảng tiến độ tổng. Khi phát hiện phụ thuộc mới hoặc scope tăng, ghi lại estimate còn lại; không cố giữ lịch bằng cách bỏ invariant.

## 6. Ca kiểm thử và tình huống bắt buộc

- [ ] Correction seller MST rồi evaluate không dùng direction cũ.
- [ ] OCR không có bank evidence trả hướng bổ sung, không PASS toàn diện.
- [ ] FAIL cùng REVIEW/ERROR vẫn giữ mọi cờ/blockers.
- [ ] Contract error → verdict null, template chỉ mô tả lỗi xử lý.
- [ ] Thay ruleset version với cùng record tạo evaluation mới.

Dùng fixture tổng hợp nhỏ cho contract/recovery tests, dữ liệu có nhãn cho accuracy và sandbox thật cho connector. Không thay accuracy evaluation bằng unit test parser. Chỉ chạy phần test phù hợp chặng và integration qua ranh giới vừa thay đổi.

## 7. Gate hoàn thành và bàn giao

**Điều kiện gate:** M2: capture→review→planning→ZEN→template chạy end-to-end; invariant và legal fixture expectations qua; báo cáo phạm vi, chất lượng, latency và unresolved inputs đầy đủ.

- [ ] Mỗi task bắt buộc có artifact và cách tái hiện kiểm chứng.
- [ ] Không còn lỗi vi phạm hợp đồng dữ liệu, tiền, tenant hoặc version trong phạm vi chặng.
- [ ] Có bảng giới hạn hỗ trợ, ca chưa đạt và next action; quality target thiếu dữ liệu không được đánh dấu đạt.
- [ ] Ghi `evidence/gate_09.md`: input versions, test/eval command, ngày chạy, kết quả, số mẫu, lỗi còn lại và quyết định gate.
- [ ] Bàn giao: PLAN_10–11 mở rộng source; PLAN_12 cải thiện explanation tùy chọn; PLAN_14 nhận release manifest để hardening.

## 8. Khi chưa đạt hoặc bị chặn

Ghi blocker cụ thể, task bị ảnh hưởng, điều kiện gỡ và người/nguồn cần cung cấp. Tiếp tục các task độc lập. Không biến thiếu dữ liệu, thiếu môi trường hoặc lỗi runtime thành kết quả thành công; không ghi DONE khi chỉ có mock mà gate yêu cầu dữ liệu thật.

Lệnh triển khai/test sẽ được ghi cùng artifact khi module đã tồn tại. Quy ước lệnh và cách cập nhật tiến độ nằm trong [README lộ trình](README.md); tài liệu này không yêu cầu chạy benchmark hoặc cài dependency ngay lúc chia kế hoạch.
