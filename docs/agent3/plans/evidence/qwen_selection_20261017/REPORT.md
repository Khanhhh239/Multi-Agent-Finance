# Khắc phục phản hồi Qwen sai hợp đồng — 17/10/2026

## Lỗi đã tái hiện

Lượt diễn giải revision 2 lưu `CLAIM_VALIDATION_FAILED`. Gọi lại Ollama local với context đã pin bằng SHA cho thấy model trả object chỉ có `error`, thiếu `claims`. Đây là phản hồi không đúng hợp đồng; không chứng minh hóa đơn sai. Không lưu raw input/output vào Git.

## Thay đổi

- Adapter gửi `format` là JSON Schema thay vì chuỗi `json`, theo [hướng dẫn Ollama](https://docs.ollama.com/capabilities/structured-outputs).
- Chỉ gửi các fact có thể chọn, gồm ID và danh sách câu đã cho phép. Bỏ bản sao excerpt, metadata snapshot và refs khỏi payload model.
- Qwen trả `selections` gồm `fact_id` và chỉ số biến thể bắt đầu từ 0. Schema giới hạn ID, độ dài danh sách và không cho thêm key. Validator phía server tiếp tục từ chối thiếu/lặp/thêm ID, bool hoặc chỉ số ngoài miền.
- Ứng dụng dựng lại `claims` từ câu/refs trong context gốc. Trích dẫn pháp lý giữ nguyên và được thêm lại phía server, không yêu cầu Qwen chép lại.
- Validator `validate()` cũ vẫn kiểm đủ toàn bộ facts, exact text và refs. Không tự sửa output không hợp lệ thành PASS; lỗi vẫn dùng template. Deadline 300 giây, model digest pin, ngân sách và giới hạn endpoint local được giữ nguyên.
- Prompt version mới `grounded-index-selection-vi-v2`; public ExplanationArtifact không đổi schema. Report thuế, record revision và dữ liệu lịch sử không bị ghi đè.

## Kết quả

- **51/51 test diễn giải PASS**, gồm HTTP local thực, process deadline, model pin, isolation, injection, lựa chọn thiếu/lặp/sai chỉ số và bảo toàn trích dẫn.
- **5 nhóm Chrome checks PASS**: template/model giả lập, nguồn, mobile, chặn bản nháp và reset revision.
- **Qwen3-8B local thật:** dùng lại context đã pin của trường hợp lỗi, nhận **18/18 claims qua validator** trong **106,078 giây**. Full context 43.942 bytes; nội dung compact 1.577 bytes, giảm khoảng 96,4%; schema khoảng 734 bytes chưa tính system prompt và HTTP envelope.
- Ollama `/api/ps` tại thời điểm kiểm tra báo `size_vram: 0`, `context_length: 4096`. Đây là một lượt đo local, không phải SLA hay bằng chứng chất lượng thuế/readability tổng quát. Không khẳng định mọi hóa đơn sẽ hoàn tất trong 5 phút.

Xem [validation.json](validation.json). Context, raw response và diagnostic snapshot giữ local trong `agent3_tax_compliance/data/qwen_diagnosis/`, không chứa trong commit. Lượt model thử nghiệm không ghi evaluation mới vào DB người dùng.

## Dùng bản sửa

Khởi động lại server từ terminal có `AGENT3_EXPLANATION_POLICY` trỏ tới `configs/explanation/policy.local.json`. Mở bản kết quả đã lưu và bấm **Xem diễn giải chi tiết** để tạo lượt mới. Kết quả template cũ vẫn được giữ trong lịch sử.

Kiểm thử lại từ `agent3_tax_compliance`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests/explanation
.\.venv\Scripts\python.exe ..\scripts\check_explanation_browser.py
```
