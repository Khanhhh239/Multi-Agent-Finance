# Lát cắt OCR + LLM + tự chạy — 18/10/2026

## Người dùng thấy gì mới?

- **Trích xuất lại dữ liệu**: dùng OCR đã lưu với extractor hiện tại. Nếu có phiên bản trích xuất mới, mở hồ sơ riêng và giữ hồ sơ đã đối chiếu trong danh sách. Đây chưa phải nút chạy lại model OCR hoặc render/crop vùng ảnh.
- **Tự kiểm tra và diễn giải sau khi tải / lưu**: bật một lần trong phiên web để chạy chuỗi sau khi dữ liệu đã được lưu. Khi mở hồ sơ 0 dòng, thử recovery tối đa một lần theo source trong phiên, rồi tiếp tục đánh giá bản mới hoặc báo cần review. Không tự tick xác nhận trường/đủ hàng.
- **Chạy tiếp**: thử tiếp trên bản đã lưu; nếu đang có bản nháp thì dừng. Tắt checkbox ngăn các bước tiếp theo, nhưng request đã gửi lên server có thể vẫn hoàn tất.
- **Diễn giải tự nhiên**: ba mục tình trạng, lý do, việc cần làm, có fact references và thông tin gốc. Nhãn màu cảnh báo **cần đối chiếu** vì đây là bản nháp ngôn ngữ tự nhiên, chưa xác minh đầy đủ ý nghĩa.

Khởi động lại launcher và Ctrl+F5 để tải mã mới. `OPEN_AGENT3.cmd` tự chọn policy.local.json nếu file có sẵn và chưa có biến môi trường override. Máy hiện tại đã được đặt local `style: "NATURAL_DRAFT"`; có thể đổi lại `"CONTROLLED_SELECTION"`. Config dùng chung mặc định controlled selection và vẫn disabled. Không đưa policy.local.json hoặc DB/model weights lên Git.

## Vì sao sửa được trường hợp mất bảng?

Hóa đơn đã chẩn đoán có OCR đọc được tên hàng, số lượng và tiền nhưng extraction loại dòng tên do box bắt đầu ngay tại đáy header; phần tên xuống dòng bị xếp vào cột STT. Bản sửa dùng tâm chữ để xác định vùng thân bảng và chỉ chuyển phần chữ không phải STT ở phía phải cột STT vào mô tả. Nếu một nhãn VAT ở footer làm header bị lệch, chuyển sang fallback spatial có giới hạn vùng.

Không tự xóa chữ OCR trùng, tự điền giá trị thiếu hoặc suy KCT từ dòng tổng. Chữ đọc sai vẫn cần đối chiếu. ID/evidence của dòng mới do allocator sinh, không giả là xác nhận của người dùng.

Dev replay từ 10 artifact OCR cũ: ba trường hợp trước có 0 dòng nay có 1 dòng; các trường hợp trước có dòng giữ nguyên số dòng. Đây là **đếm cấu trúc trên dev đã dùng sửa code**, không phải accuracy. Một số ô tiền ở trường hợp cũ vẫn chưa rõ/xung đột; không ép thành PRESENT hoặc COMPLETE. Không có holdout mới và nhãn toàn bộ ô độc lập.

## Hợp đồng và giới hạn

- API `POST /v1/records/{record_id}/reextract?taxpayer_id=...` nhận `expected_record_revision` và `reason`. Yêu cầu WRITE, giữ scope và chặn revision cũ. Cùng OCR/profile/master/code dùng lại cache, không tạo vô hạn hồ sơ khi retry. Kết quả có link record cũ/mới; không chuyển UI nếu bản đang xem đã có thay đổi. Sửa field hoặc hồ sơ nghiệp vụ của record cũ không được chép thành chứng cứ xác nhận của record mới.
- Capture job cũ không được gắn nhầm vào record recovery để hoàn tất nhầm hồ sơ.
- Chuỗi UI chỉ hoạt động khi web mở, chưa phải durable background job; có generation fencing khi đổi record/payer/revision, không tự discard bản nháp. Capture worker hiện có vẫn xử lý upload độc lập.
- Cache diễn giải bind evaluation/revision, policy, corpus và implementation. Khi đổi style/model/config phải tạo lượt mới. Timeout/lỗi provider hoặc validation không được coi là cache model dùng lại lâu dài.
- `NATURAL_DRAFT` giữ claims/template gốc; phần tự viết có refs, chặn một số lỗi số/điều luật/kết luận không có căn cứ và buộc giữ tham chiếu scope/cảnh báo/hành động. Những ràng buộc này **không chứng minh entailment hoặc citation correctness của mọi câu**; `semantic_review_required=true` không được bỏ. Chưa có API duyệt bản nháp thành lời giải thích đã nghiệm thu.
- Auto-accept vẫn tắt. Rule thật vẫn DRAFT. Corpus/nhãn/calibration pháp lý và doanh nghiệp chưa được nghiệm thu. Đây là lát cắt kỹ thuật của PLAN_06/12, chưa hoàn thành toàn bộ kế hoạch nâng cấp OCR hoặc PLAN_14.

## Model thật và kiểm thử

**Kết quả cuối: 448/448 Python tests, 40 nhóm kiểm tra Chrome, 6 JavaScript syntax checks và 2 client harness checks PASS.** Chrome đã phát hiện và kiểm tra lại lỗi thao tác recovery khi snapshot còn đang tải; UI hiện khóa editor/recovery trong lúc tải và chỉ chạy chuỗi sau khi lưu đã hoàn tất. Sau chỉnh riêng phần hiển thị nguồn của bản nháp, hai bộ Chrome liên quan và client/syntax được chạy lại. Các phần Python không đổi chức năng sau hồi quy, chỉ chuẩn hóa dòng trống cuối file.

Lượt Qwen local đầu với schema generic bỏ sót bốn notice, bị từ chối. Schema chốt refs theo ba mục; thử schema với `items: false` phát hiện runtime Ollama không hỗ trợ boolean schema ở vị trí đó, sửa sang schema object kèm độ dài cố định. Sau sửa, Qwen3-8B local tạo ba đoạn qua kiểm tra cơ học trong **152,657 giây**, payload fact/section khoảng **1.745 bytes**. Đây là một lượt chạy, không phải SLA hoặc nghiệm thu readability/pháp lý.

Chạy toàn bộ từ root:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/validate_automation_v1.py
```

Kết quả suite, số test, hash mã và browser nằm ở [validation_summary.json](validation_summary.json). Các bài browser dùng Chrome/HTTP/SQLite thật với fixture tổng hợp và provider giả lập, tách khỏi lượt Qwen thật. Không dùng DB demo người dùng để chạy test ghi dữ liệu.

Nhóm kiểm tra trọng tâm:

1. Dòng hàng chạm header, mô tả nhiều dòng, evidence và các bố cục cũ.
2. Recovery cùng code không tạo hồ sơ; code mới tạo một hồ sơ ngay cả khi có request đồng thời; dữ liệu reviewer cũ không đổi.
3. Auth/tenant/WRITE, bool thay revision, stale revision và read-only denied.
4. Natural JSON/nguồn/số liệu/điều luật/markup/cảnh báo, schema HTTP, bắt buộc mode draft; fallback khi thiếu căn cứ hoặc phản hồi không hợp lệ.
5. Tự chạy sau lưu, một lần recovery 0 dòng rồi tiếp tục, cache, chặn bản nháp và source/record cũ vẫn tồn tại.
6. Browser mobile/desktop, nguồn, export, lịch sử và xung đột nghiệp vụ cũ.

Phát lại OCR dev bằng DB read-only:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/evaluate_cached_extraction.py --database "data invoice/plan06_local/demo.sqlite3" --output agent3_tax_compliance/data/missing_rows_diagnosis/dev_replay_20261018.json
```

Raw OCR/context/model output và ảnh chụp giữ local; báo cáo Git chỉ lưu metadata đã bỏ thông tin doanh nghiệp. [Kế hoạch tổng hợp và phần còn chờ](../../PLAN_AUTOMATION_OCR_LLM_V1.md).
