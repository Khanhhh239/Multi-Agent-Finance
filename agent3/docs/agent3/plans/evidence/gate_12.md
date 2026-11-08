# Gate PLAN_12 — giải thích có kiểm soát

Ngày: **15/10/2026**. Trạng thái: **IMPLEMENTED_TECHNICAL_PARTIAL; chưa hoàn tất nghiệm thu toàn PLAN_12**.

**Cập nhật 16/10/2026:** [corpus nguồn tối thiểu](plan12/legal_corpus_20261016/REPORT.md) đã có 11 trích đoạn runtime từ 4 văn bản và 6 đoạn chỉ tham khảo; 11 PDF tải lại khớp hash. Corpus đã có dữ liệu, nhưng coverage mới đủ locator cho 2/7 rule versions; pháp lý/model/readability vẫn PENDING. Nội dung trạng thái 15/10 bên dưới là bằng chứng của mốc trước, không phải cấu hình corpus mặc định mới.

Kiểm chứng cuối: **343/343 Python tests PASS** (310 hồi quy + 33 PLAN_12), 3 JavaScript syntax checks và 2 DOM harness PASS. Chrome PLAN_12 có 5 nhóm kiểm tra desktop/mobile PASS; chạy lại Chrome PLAN_09 có 6 nhóm PASS, không có page errors. Hash implementation replay V1 khớp manifest PLAN_09: `f7f54d632a83f15e22d30662ce65dcd6a8180bfecabe55b8fb58633cacc18dd7`.

[Kế hoạch thực hiện](plan12/implementation_plan.md) · [Runbook/UI/API/model](plan12/runbook.md) · [Validation](plan12/validation_summary.json) · [Config/corpus/runtime manifest](plan12/configuration_manifest.json).

## Đã triển khai

- `src/explanation_v2/`: corpus/chunk contracts, SHA-256, registry/version/locator/date filters, BM25 NFC; không tìm rộng sang văn bản hoặc phiên bản khác khi thiếu căn cứ.
- Context chỉ lấy facts từ evaluation snapshot và nguồn đã chọn. Không gửi raw OCR, thông tin seller/buyer hoặc secrets vào model.
- Ollama loopback adapter cho ứng viên `qwen3:8b`, `think=false`, JSON, kiểm local model digest/response identity, giới hạn context/token/response và subprocess deadline. Không gửi hóa đơn lên cloud.
- Claim validator chặn text/refs ngoài fact variants, bỏ cảnh báo/phạm vi, duplicate/missing claims và extra top-level fields. Provider tắt/lỗi/timeout hoặc corpus không đáp ứng → template.
- Explanation artifact riêng, config/corpus/implementation/context/evaluation hashes, timestamp và model revision; lưu SQLite sidecar scoped tenant/payer/evaluation/revision, idempotent request key. Không sửa V1 reports, foundation schema hoặc replay implementation.
- API POST/GET và UI **Diễn giải và nguồn tham chiếu**; textContent, draft guard, reset khi correction, stale-response guard, loading/error/fallback.

## Trạng thái từng task

| Task | Kết quả và phần còn mở |
|---|---|
| P12-T01 | Corpus schema/version/hash/inspection có code; **trích đoạn thực đã đối chiếu chưa có, PENDING**. Corpus mặc định rỗng |
| P12-T02 | BM25/filter/Unicode/date/historical tests có; **retrieval accuracy trên labeled legal corpus chưa đo** |
| P12-T03 | Context builder và data boundary có; không lấy raw OCR làm instructions |
| P12-T04 | Adapter local/structured output/pin/budgets/fallback có; **Ollama/Qwen chưa cài và chưa suy luận weights thật** |
| P12-T05 | Validator strict fact/variant/refs có; **chỉ finite wording/selection, chưa mở paraphrase tự do** |
| P12-T06 | Technical regression/API/native ZEN/local HTTP/Chrome có; **readability, citation accuracy trên luật thật, model cold/warm và fallback rate thực chưa nghiệm thu** |

## Phạm vi bằng chứng

Số test và kết quả thực nằm trong validation JSON, không dùng unit tests làm độ chính xác pháp lý/model. Chrome dùng fixture tổng hợp với ZEN thật, LLM test double. HTTP transport dùng server mô phỏng local protocol, không gọi model thật. Có test supervisor deadline, digest mismatch, invalid JSON, oversized response, citations sai, trường hợp lịch sử, tenant/revision/idempotency và replay V1 sau khi tạo explanation.

Máy hiện tại kiểm tra được khoảng 15,5 GiB RAM, GPU Intel Arc tích hợp; Ollama không có trong PATH/vị trí cài thông thường và probe localhost trả unavailable. Không suy ra Qwen chạy tốt trên máy chỉ từ cấu hình. Không tải/cài model trong chặng này; runtime inference vẫn PENDING và LLM mặc định tắt.

## Điều kiện đóng gate sản phẩm

1. Hoàn tất căn cứ/mappings/expected legal labels còn mở ở P09-T06; không promote pháp lý từ kết quả kỹ thuật.
2. Corpus thực được kiểm nguồn, selected locator và phiên bản, có bộ query/nhãn/holdout phù hợp.
3. Cài runtime/model local, pin digest và benchmark weights thật; đo cold/warm, tài nguyên, timeout/fallback trên máy đích.
4. So sánh readability và citation correctness với template trên bộ ca có nhãn; không chứng minh được lợi ích thì giữ LLM optional/tắt.
5. PLAN_14 bổ sung retention/backup sidecar, rate limits/in-flight lease, monitoring và deployment/resource policy trước production.

XML/Excel/ERP chưa triển khai; hoãn theo lựa chọn người dùng. PLAN_12 không mở rộng scope payment/reconciliation hoặc thay kết quả GoRules.


> 2026-10-16 V2 update: source-linked registry/ruleset/corpus revised; 384 regression tests PASS. All real models remain DRAFT; product mapping is unapproved. Current status: [legal revision V2](legal_revision_20261016_v2/REPORT.md). Earlier results below remain historical evidence.
