# OCR, diễn giải và tự động hóa — lát cắt triển khai 18/10/2026

Đây là nhánh củng cố PLAN_06 và PLAN_12, không phải nghiệm thu PLAN_14. Giữ PLAN_OCR_EXTRACTION_V2 làm kế hoạch đầy đủ; không đánh dấu xong các hạng mục chưa được thử nghiệm.

| Công việc | Trạng thái / bằng chứng |
|---|---|
| Đóng băng đầu vào phát triển | Đọc lại 10 artifact OCR cũ bằng DB read-only; input và extractor hashes, nhóm dev đã dùng sửa code; không giả làm holdout |
| Sửa mất bảng đã chẩn đoán | Giữ dòng chữ chạm mép header; không nuốt phần mô tả xuống dòng vào STT; fallback khi VAT footer bị chọn làm header |
| Recovery trên web | Trích xuất lại từ OCR bất biến; tạo hồ sơ riêng nếu code đã đổi, cache chống tạo bản vô hạn; giữ revision/đối chiếu cũ |
| Diễn giải tự nhiên | Chế độ NATURAL_DRAFT thử nghiệm, nguồn fact ID, JSON Schema; giữ nguyên thông tin gốc và nhãn cần đối chiếu |
| Luồng tự chạy | Opt-in trong browser; một lượt phục hồi bảng theo source/phiên, kiểm tra bản đã lưu, giải thích có cache; chặn bản nháp, bỏ kết quả UI cũ khi đổi record/revision |
| Bật auto-accept | **CHƯA BẬT**: thiếu calibration/holdout và nghiệm thu chất lượng |
| Duyệt luật / mapping hàng thật | **PENDING**: không đổi DRAFT thành approved bằng code |
| OCR lại vùng, crop/recognizer/layout mới | **CHƯA TRIỂN KHAI trong lát cắt này**; chọn nhánh tiếp theo bằng error inventory và benchmark riêng |
| Job bền vững khi đóng browser | Capture worker hiện có tiếp tục chạy; chuỗi UI mới chỉ chạy khi trang mở. Durable orchestration/production còn thuộc PLAN_14 |
| Dữ liệu mở rộng, fine-tune và nghiệm thu readability | **PENDING**; không suy chất lượng tổng quát từ fixture/dev đã sửa |

## Thứ tự kiểm chứng

1. Hồi quy geometry/field binding và Decimal; không mất evidence hoặc tự suy thuế từ tổng tiền.
2. API recovery: auth, tenant, revision, idempotency qua extractor cache, concurrency, giữ hồ sơ cũ.
3. LLM: schema local thật, số liệu/nguồn/cảnh báo, fallback, mode draft bắt buộc; không nhận JSON hợp lệ là đã đúng ngữ nghĩa.
4. Browser: chạy theo lựa chọn của người dùng, cache đúng phiên bản, lưu → kiểm tra lại, không gửi POST khi có bản nháp, phục hồi 0 dòng một lần và tiếp tục.
5. Đo dev và model thật, tách khỏi fixture và giữ dữ liệu chứng từ ngoài Git.

Xem [báo cáo và runbook](evidence/automation_20261018_v1/REPORT.md).
