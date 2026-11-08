# PLAN_12 — RAG và LLM giải thích có kiểm soát — tùy chọn

> Trạng thái triển khai: **IMPLEMENTED_TECHNICAL_PARTIAL — cập nhật 16/10/2026**. Đã triển khai sidecar BM25/context/adapter Ollama/claim validator/API/UI/template fallback và corpus nguồn tối thiểu; nghiệm thu pháp lý toàn bộ corpus, inference Qwen thật và đánh giá readability còn **PENDING**. [Gate](evidence/gate_12.md) · [Runbook](evidence/plan12/runbook.md) · [Quyết định triển khai](evidence/plan12/implementation_plan.md).

[Lộ trình tổng](README.md) · Trước theo thứ tự đọc: [PLAN_11](PLAN_11_EXCEL_BANK.md) · Sau: [PLAN_13](PLAN_13_ERP_CONNECTOR.md)

## 1. Kết quả cần đạt và điều kiện bắt đầu

Cải thiện khả năng đọc giải thích, giữ nguyên quyết định deterministic và luôn có template fallback.

- Phụ thuộc bắt buộc: PLAN_09 đạt gate; legal corpus được version hóa.
- Ước lượng: **3–5 ngày công**, một người làm tập trung; chưa bao gồm thời gian chờ dữ liệu/hạ tầng/nghiệp vụ.
- Đối chiếu [NEW_PLAN](../NEW_PLAN.md): mục 10, 13, 16.
- Đầu vào: Typed aggregate/outcomes, selected legal basis, official corpus metadata, retrieval baseline.

Không bắt đầu phần phụ thuộc khi gate đầu vào chưa qua. Có thể chuẩn bị fixture/tài liệu độc lập, nhưng không ghi cả chặng DONE vì đã tạo scaffold.

## 2. Tài sản hiện có và cách tái sử dụng

vilegalbert_test có báo cáo BM25 tốt hơn raw zero-shot reranker trên tập nhỏ 14 chunks/22 queries; chỉ dùng làm baseline, không kết luận chung. Không cần chặn MVP để thêm hybrid/reranker/LLM.

Kiểm tra lại tính tồn tại/phiên bản khi triển khai; kết quả kiểm kê là bằng chứng tham khảo, không thay nghiệm thu runtime đích.

## 3. Module và hợp đồng cần xây

Các đường dẫn sau là **đích dự kiến**, chưa hàm ý file đã tồn tại:

`agent3_tax_compliance/src/explanation/{retrieval,context_builder,llm,validator}.py; configs/explanation/; tests/explanation/`

**Đường dẫn thực tế:** `src/explanation_v2/` thay cho sửa `src/explanation/`, nhằm giữ hash implementation/template replay của report PLAN_09. Config ở `configs/explanation/`, tests ở `tests/explanation/`, schema ở `contracts/explanation-v1/`. Giải thích mở rộng là artifact riêng theo evaluation/revision, không sửa aggregate/outcome.

**Model được chọn làm ứng viên:** Ollama local `qwen3:8b` (Qwen3-8B), `think=false`, pin digest manifest trước khi bật. Mặc định `enabled=false`, chưa cài/tải weights trong đợt triển khai này. Retrieval dùng BM25; BGE-M3/reranker chưa được thêm vì chưa có bộ đánh giá chứng minh lợi ích.

**Giới hạn validator bản đầu:** chỉ nhận fact/variant/refs do code cung cấp và yêu cầu giữ đủ facts; model có thể sắp xếp và chọn cách diễn đạt hữu hạn đã định nghĩa. Chưa nhận paraphrase tự do, chưa tuyên bố tốt hơn template. Corpus nguồn mặc định đã có bản tối thiểu ngày 16/10; thiếu căn cứ được duyệt thì fallback, không dùng kiến thức có sẵn của model thay luật.

**Cập nhật 16/10/2026:** [corpus nguồn đã chuẩn bị](evidence/plan12/legal_corpus_20261016/REPORT.md), mặc định `corpus_20261016_v1.json`, gồm 11 đoạn runtime/4 văn bản và 6 đoạn tham khảo riêng. Có ngày áp dụng riêng khoản/điểm và giữ bắt buộc các đoạn ngoại lệ. Không đổi source approval/ruleset v1; coverage toàn bộ pháp lý và model vẫn chưa được nghiệm thu. Bản rỗng trước đây được giữ nguyên để truy lịch sử.

ExplanationContext chỉ gồm evaluation snapshot hợp lệ, rule outcomes, evidence và legal excerpts đúng selected document/article/version. LLMOutput có structured claims với refs; verdict/coverage/counts là read-only từ system result. Validation failure → deterministic template.

Mọi artifact phải có schema/config version, input hash hoặc record revision, creator/stage và timestamp. Artifact chứa dữ liệu thật lưu ngoài git theo policy; tài liệu chỉ ghi metadata đã che dữ liệu.

## 4. Công việc chi tiết theo thứ tự

### P12-T01 — Corpus theo legal versions

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Chunk theo điều/khoản, document ID/effective interval/hash; giữ superseded sources cho historical evaluation.
- Đầu ra: corpus manifest + index versions.
- Kiểm chứng: Không thay văn bản lịch sử bằng latest khi query invoice cũ.

### P12-T02 — Retrieval baseline ràng buộc

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Filter selected legal basis trước retrieval; chạy BM25 baseline rồi chỉ thêm reranker nếu cải thiện trên labeled eval đủ scope.
- Đầu ra: retrieval_eval_report.
- Kiểm chứng: Legal version recall đúng; report tập nhỏ không được quảng bá chất lượng tổng thể.

### P12-T03 — Context builder tối thiểu

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Cấp facts/decisions/evidence đã validate, không raw tài liệu không cần thiết; chống prompt injection trong OCR/legal text bằng data boundary.
- Đầu ra: context_builder.py.
- Kiểm chứng: Chuỗi OCR yêu cầu đổi verdict không ảnh hưởng system decisions.

### P12-T04 — LLM output và limits

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Structured response, timeout/token/cost budget, model/prompt version; không gửi tenant secrets/PII ngoài scope cấu hình.
- Đầu ra: llm.py + prompt cards.
- Kiểm chứng: Không có provider/timeout vẫn trả template đúng; output không overwrite evaluation.

### P12-T05 — Claim validator

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: So verdict/counts/amounts/scope và citations với context; unsupported statement hoặc legal basis sai → reject/fallback.
- Đầu ra: validator.py.
- Kiểm chứng: Hallucinated article/tax eligibility bị chặn; không chỉ kiểm JSON shape.

### P12-T06 — Đánh giá thực dụng

- [ ] Hoàn thành và đính kèm bằng chứng.
- Thực hiện: Đo citation correctness, unsupported claims, user readability và fallback rate so với template.
- Đầu ra: explanation_release_report.
- Kiểm chứng: Giữ LLM optional nếu không cải thiện; không ảnh hưởng latency/chất lượng core quyết định.

## 5. Tiến độ bên trong chặng

- Ngày 1: corpus/index baseline.
- Ngày 2: context builder, prompt và provider wrapper.
- Ngày 3: validator/fallback + adversarial cases.
- Ngày 4–5: evaluation, budget và release decision.

Cuối mỗi ngày cập nhật task IDs đã làm, bằng chứng và blocker vào bảng tiến độ tổng. Khi phát hiện phụ thuộc mới hoặc scope tăng, ghi lại estimate còn lại; không cố giữ lịch bằng cách bỏ invariant.

## 6. Ca kiểm thử và tình huống bắt buộc

- [ ] Invoice lịch sử nhưng retrieval trả luật hiện tại.
- [ ] OCR chứa chỉ dẫn bỏ qua rule và công bố PASS.
- [ ] LLM sửa tổng fail hoặc bỏ scope exclusions.
- [ ] Provider timeout, thiếu key, invalid JSON.

Dùng fixture tổng hợp nhỏ cho contract/recovery tests, dữ liệu có nhãn cho accuracy và sandbox thật cho connector. Không thay accuracy evaluation bằng unit test parser. Chỉ chạy phần test phù hợp chặng và integration qua ranh giới vừa thay đổi.

## 7. Gate hoàn thành và bàn giao

**Điều kiện gate:** LLM không thay facts/verdict; citation/version checks và fallback qua; nếu gate không đạt thì tiếp tục template, không chặn M2/M3.

- [ ] Mỗi task bắt buộc có artifact và cách tái hiện kiểm chứng.
- [ ] Không còn lỗi vi phạm hợp đồng dữ liệu, tiền, tenant hoặc version trong phạm vi chặng.
- [ ] Có bảng giới hạn hỗ trợ, ca chưa đạt và next action; quality target thiếu dữ liệu không được đánh dấu đạt.
- [ ] Ghi `evidence/gate_12.md`: input versions, test/eval command, ngày chạy, kết quả, số mẫu, lỗi còn lại và quyết định gate.
- [ ] Bàn giao: PLAN_14 nhận model/provider data policy, budgets, monitoring và template fallback runbook.

## 8. Khi chưa đạt hoặc bị chặn

Ghi blocker cụ thể, task bị ảnh hưởng, điều kiện gỡ và người/nguồn cần cung cấp. Tiếp tục các task độc lập. Không biến thiếu dữ liệu, thiếu môi trường hoặc lỗi runtime thành kết quả thành công; không ghi DONE khi chỉ có mock mà gate yêu cầu dữ liệu thật.

Lệnh triển khai/test sẽ được ghi cùng artifact khi module đã tồn tại. Quy ước lệnh và cách cập nhật tiến độ nằm trong [README lộ trình](README.md); tài liệu này không yêu cầu chạy benchmark hoặc cài dependency ngay lúc chia kế hoạch.
