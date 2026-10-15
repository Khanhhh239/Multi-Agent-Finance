# Chạy và kiểm tra giải thích PLAN_12

Phần giải thích bổ sung hoạt động độc lập với kết quả thuế PLAN_09. Mặc định dùng template; model/corpus thực tế chưa được nghiệm thu.

## Trên giao diện

1. Dừng phiên web cũ rồi mở lại `OPEN_AGENT3.cmd`; launcher có thể tái sử dụng server đang chạy nên cần restart để nạp route mới.
2. Kết nối, mở chứng từ, đối chiếu và lưu bản sửa.
3. Bấm **Kiểm tra bản đã lưu** trong **Kiểm tra phạm vi thuế**.
4. Mở **Diễn giải và nguồn tham chiếu**, bấm **Xem diễn giải chi tiết**.
5. Xem trạng thái template/model, từng phát biểu và phần **Tham chiếu nguồn**. Khi chưa có corpus duyệt hoặc model local, vẫn có giải thích bằng mẫu; không hiện là Qwen đã chạy.

Giải thích thuộc evaluation/revision đã lưu. Bản nháp chưa lưu bị chặn. Khi lưu correction, phần giải thích cũ được xóa khỏi màn hình; lịch sử vẫn nằm trong sidecar. Xem nguồn chứng từ bằng các nút **Xem nguồn** hiện có trong chi tiết kiểm tra.

## API và storage

```text
POST /v1/evaluations/{evaluation_id}/explanations?taxpayer_id=...
Authorization: Bearer ...
Idempotency-Key: <new request key>
{"expected_record_revision": 2}

GET /v1/evaluations/{evaluation_id}/explanations?taxpayer_id=...
```

POST cần WRITE; GET cùng auth/tenant/taxpayer scope với evaluation. GET trả explanation và current-revision flag. POST cho phép tạo giải thích lịch sử nếu revision khớp evaluation; không gọi đó là giải thích của record head. Đổi policy/corpus/implementation với cùng key trả 409. Các request key khác nhau tạo artifact riêng; retry cùng key dùng bản đã commit. Request đồng thời có thể gọi inference trùng trước khi commit; PLAN_14 cần lease/rate limit khi bật tải thực.

Sidecar nằm cạnh foundation DB, ví dụ `capture.explanations.sqlite3`, chứa thông tin chứng từ và phải được bảo vệ/backup/retention cùng dữ liệu tài chính. Không đưa DB hoặc raw inference vào Git. Export compliance V1 giữ nguyên; export explanation bằng JSON của API trên. Chưa có endpoint gộp hai artifact hoặc pagination lịch sử explanation.

## Kiểm tra cấu hình và model

Từ thư mục `agent3_tax_compliance`:

```powershell
.\.venv\Scripts\python.exe -m src.explanation_v2.cli --probe
```

Lệnh kiểm hash/registry/corpus và đọc manifest localhost; không gửi hóa đơn. Config mặc định ở `configs/explanation/policy_v1.json`, corpus ở `configs/explanation/corpus_v1.json`. Override bằng đường dẫn tuyệt đối trong `AGENT3_EXPLANATION_POLICY` và `AGENT3_EXPLANATION_CORPUS`; nên dùng file `*.local.json` bị gitignore. Khởi động server từ terminal có các env này; không thay bằng request từ browser.

Adapter gọi **Ollama local**, model ứng viên **Qwen3-8B**, tag `qwen3:8b`. [Tài liệu Windows](https://docs.ollama.com/windows), [chat API](https://docs.ollama.com/api/chat), [manifest model/digest](https://docs.ollama.com/api/tags). Không cài Ollama hoặc tải weights tự động khi mở web.

Khi môi trường local đã có Ollama và đủ tài nguyên, tải model bằng `ollama pull qwen3:8b`. `--probe` trả digest của model đã cài; copy digest vào `model_revision` của policy local, đặt `enabled=true`, giữ endpoint loopback. Mỗi inference kiểm digest và model response. Mặc định 20 giây, tối đa 60 giây; hết deadline chuyển template. CPU/cold load có thể vượt budget, chưa có SLA.

**Chỉ có model vẫn chưa đủ:** mỗi căn cứ đã chọn phải có trích đoạn đúng registry/hash/locator và interval. Thiếu bất kỳ locator nào thì không gửi context vào LLM. Bật model không đổi trạng thái legal approval của rules.

## Chuẩn bị corpus

Schema nằm ở `contracts/explanation-v1/Corpus.schema.json`. Mỗi chunk có `chunk_id`, `document_id`, `locator`, `document_sha256`, `text`, SHA-256 của UTF-8 text, effective interval và `reviewed=true`. Metadata phải khớp pinned LegalRegistry; document phải `PDF_REVIEWED` và locator nằm trong `verified_locators`. `reviewed=true` là lời xác nhận của quy trình biên tập, code không chứng minh người đối chiếu đã đọc đúng đoạn nguồn. Không đưa fixture pháp luật tổng hợp vào corpus thực.

Giữ phiên bản corpus cũ và cấu hình tương ứng khi cần giải thích evaluation lịch sử. Không tự thay corpus theo latest. CLI hiện validate manifest; chưa tự crawl/chunk PDF hoặc xác nhận sự đúng đắn của phần trích đoạn.

## Tái hiện kiểm thử

Từ `D:\financial`:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\check_explanation_browser.py
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\validate_plan12.py
```

Browser test dùng DB và chứng từ tổng hợp tạm, ZEN thật, Chrome thật; LLM là test double. HTTP tests chạy local server mô phỏng Ollama protocol, không phải suy luận Qwen. Chạy browser trước validator để báo cáo lấy kết quả UI mới nhất. Screenshot local ở `agent3_tax_compliance/data/plan12/browser/`, không đưa chứng từ thật vào Git.

## Phục hồi và giới hạn

- Model tắt/chưa pin, không có server, timeout, output sai hoặc corpus không phù hợp → template với reason code. Không đổi verdict/counts/outcomes.
- Config/corpus JSON sai schema hoặc sidecar bị sửa payload/hash → API từ chối; kết quả compliance V1 vẫn giữ nguyên, không bỏ qua lỗi integrity để hiển thị như hợp lệ.
- Không dùng dữ liệu OCR như instructions. Validator chỉ nhận đầy đủ approved facts/refs, không chấp nhận văn bản mới dù JSON đúng shape.
- V1 replay implementation không thay do module mới nằm ngoài `src/explanation/`; không sửa report cũ để bổ sung explanation.
- Model chỉ sắp xếp/copy approved facts trong bản đầu. Chưa có kết quả đo cải thiện readability, retrieval trên luật thật hoặc latency model thật. Không công bố hoàn tất toàn PLAN_12.
- Deadline dừng tiến trình client và đóng kết nối; chưa chứng minh Ollama đã hủy inference phía server ngay lập tức. Token budget vẫn giới hạn lượt sinh; RAM/GPU của server, concurrency và cơ chế hủy cần hardening/đo riêng trước khi bật production.
