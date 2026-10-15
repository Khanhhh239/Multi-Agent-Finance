# Triển khai PLAN_12 — giải thích có kiểm soát

Ngày bắt đầu: 15/10/2026. Phạm vi được người dùng chọn: PDF/ảnh hiện tại; hoãn PLAN_10, PLAN_11 và PLAN_13. Không mở rộng khả năng kiểm chứng thanh toán hoặc đối soát.

## Điều kiện đầu vào

PLAN_09 PASS tích hợp kỹ thuật, còn P09-T06/M2 pháp lý PENDING. Có thể triển khai và kiểm thử các hợp đồng kỹ thuật độc lập bằng fixture; không phát hành giải thích pháp lý thực tế dựa trên luật chưa được duyệt. Corpus trích đoạn mặc định trống, không biến dữ liệu tổng hợp thành luật thật.

## Thứ tự và quyết định thiết kế

1. Giữ nguyên `src/explanation/service.py` và report/replay của PLAN_09. Tạo `src/explanation_v2/` bên ngoài tập implementation được V1 pin hash. Thêm API và DB sidecar `*.explanations.sqlite3`, không migrate foundation DB và không thay lịch sử.
2. Corpus typed theo văn bản/hash/locator/effective interval, text hash, registry version; BM25 chuẩn hóa Unicode NFC. Filter theo selected legal basis trước khi rank; top-k riêng mỗi locator. Không lấy latest cho hóa đơn cũ, không fallback tìm toàn corpus khi thiếu căn cứ.
3. Context chỉ có facts đã xuất từ report, nguồn CFR có ID và trích đoạn đã duyệt. Không gửi raw OCR, tên/MST người bán/người mua, token hoặc tenant ID. Snapshot report và revision là nguồn sự thật.
4. Adapter Ollama localhost, `qwen3:8b`, `think=false`, structured JSON; pin digest từ manifest local. Chưa có digest/model thì không promote. Parent subprocess giới hạn thời gian; payload/response/token có budget; không gọi cloud/proxy/redirect.
5. Validator đầu tiên là **grounded selection**, không nhận diễn giải tự do: model chỉ sắp xếp các fact đã xác nhận, copy một variant được phép và đúng refs; phải giữ đủ facts, cảnh báo và phạm vi. Không tuyên bố đây là hoàn tất mục tiêu cải thiện văn phong bằng LLM. Nếu muốn paraphrase, cần nhánh kiểm chứng ngữ nghĩa và dữ liệu đánh giá riêng trước khi mở.
6. API/UI cho tạo và đọc giải thích theo evaluation; lưu artifact/config/corpus/prompt/implementation hashes và model revision. Artifact hiện có không bị ghi đè. Đổi config cần request key mới; sửa chứng từ xóa hiển thị explanation cũ.
7. Kiểm thử retrieval, tampering, dates, model transport/deadline, citations, omission, tenant, revision, idempotency, replay; DOM và Chrome desktop/mobile; chạy lại suite nền tảng đến PLAN_09.
8. Gate tách rõ kiểm chứng kỹ thuật, corpus/quality và inference model thật. Sau validation, commit và push `team-finance/agent3-caoban` theo chỉ dẫn người dùng.

## Tiêu chí phát hành còn mở

- Trích đoạn văn bản thật có provenance được đối chiếu với source hash và locator đã duyệt.
- Bộ query/expected locator theo phiên bản luật, có mẫu số và holdout; báo recall và citation correctness theo văn bản/nhóm trường hợp.
- Ollama/Qwen thật, digest khóa, cold/warm latency và resource đo trên máy đích.
- Người dùng so sánh template và giải thích có model hỗ trợ; chưa có dữ liệu thì không tuyên bố dễ hiểu hơn.
- Unsupported claims, fallback rate và chi phí review được báo trên cùng tập; unit tests không thay accuracy evaluation.

PLAN_14 nhận chính sách model local, retention sidecar, timeout/cancel/resource monitoring, rate limits và backup/restore. Chưa có production release.
