# Mở rộng đọc lại các trường hóa đơn — 19/10/2026

Vẫn thuộc PLAN_06, củng cố OCR/extraction; không chuyển trạng thái duyệt luật hay nghiệm thu production. Mục tiêu của đợt này là cứu trường có vùng chữ nhưng parser từ chối, không điền mọi ô bằng suy đoán.

## Thay đổi thực tế

- Đọc lại thêm MST bên bán/bên mua, số/ký hiệu hóa đơn, ngày lập, tiền tệ và ba tổng tiền. Tên, địa chỉ, mô tả hàng vẫn được hỗ trợ; chưa hỗ trợ đọc lại từng ô số lượng/đơn giá/thuế trong bảng.
- Trường MISSING thường không có candidate/evidence trong CFR vì raw value không parse được. Bộ phục hồi nay tìm lại block từ `UNPARSEABLE_FIELD` và quan sát nhãn/vai trò của extractor. Không dùng tọa độ template cố định hoặc nhặt số gần nhất trên toàn trang. Nhánh native/OCR được xét riêng; nhiều vùng cạnh tranh hoặc vượt ngân sách vẫn cần đối chiếu.
- Giữ dấu vết ngày có thêm chữ OCR ở cuối để có thể đọc lại đúng vùng. Parser chính vẫn từ chối phần thừa; không cắt bỏ chữ/số để làm ngày hoặc MST có vẻ hợp lệ.
- Nhận MST/địa chỉ nằm ngay dưới nhãn, nhãn song ngữ không có dấu hai chấm, và hai biến thể OCR `Addres`/`Addrass` trong chú thích nhãn địa chỉ. Không sửa tên/địa chỉ thực tế theo fuzzy match.
- Sắp crop theo dòng và vị trí trái→phải thay vì tin thứ tự detector. Gợi ý tên bỏ nhãn cùng anchor MST của chính bên đó; không ghép nhãn vào tên và không ghép tên người mua vào người bán.
- Kết quả số/ngày dùng parser hiện có: Decimal, lịch hợp lệ, MST đủ chuỗi, ký hiệu không bị cắt ký tự thừa. Nhiều giá trị hoặc locale mơ hồ → `NEEDS_REVIEW`, `parse_status=REJECTED`; raw response vẫn được giữ.
- UI dùng chung hàm định dạng với form: ngày `DD/MM/YYYY`, tiền Việt Nam và số lớn giữ nguyên độ chính xác. API trả `value_format=CANONICAL`. Chỉ thao tác rõ ràng của người dùng mới đưa gợi ý vào bản nháp, rồi lưu qua correction service.

Policy vùng: `region-fields-v2`; policy chẩn đoán: `recovery-policy-v2`. Cache gắn mã nguồn/parser/model/runtime/revision mới. Giữ tối đa 2 field/4 crop cho tự động, tối đa 4 crop cho một trường thủ công, 2 lượt tự động trên cùng binding, auth/tenant/revision/lease và giới hạn worker cũ. Model vẫn là VietOCR beam search qua adapter riêng; detector PP-OCRv6 và cấu hình OCR toàn trang mặc định không đổi.

## Model thật, dữ liệu thật trong phạm vi dev

Runner [benchmark_field_recovery.py](../../../../../scripts/benchmark_field_recovery.py) lấy **8 trường lỗi đã biết của 3 hóa đơn**, cắt từ render có SHA-256 khớp artifact OCR đã giữ, rồi chạy model cục bộ thật. Không ghi CFR hoặc DB người dùng. Raw response/crop nằm trong `agent3_tax_compliance/data/field_coverage_round3`, được gitignore. Bản công khai chỉ có ID, số đếm và hash trong [model_runs.json](model_runs.json).

- 4 trường từng trống: 2 MST, 1 ký hiệu, 1 ngày → cả 4 ứng viên đọc lại khớp nhãn theo phép so nghiêm ngặt.
- 4 tên từng sai: 1 khớp nghiêm ngặt; 2 đúng chữ nhưng khác hoa/thường; 1 vẫn thêm một ký tự ở cuối tên doanh nghiệp.
- Tổng: **5/8 exact**, **7/8 nếu bỏ phân biệt hoa/thường**. Hai thước đo được báo riêng; không đổi thước đo chính để gọi tên còn khác là đúng hoàn toàn.
- Model vẫn trả một tên sai dù chuỗi nhìn có vẻ hợp lệ. Do đó gợi ý này giữ REVIEW; không tự chọn tên/MST mới dựa vào confidence hoặc chỉ vì parser qua.

Đây là các lỗi được chọn trên tập dev đã dùng sửa code, nhãn do agent đối chiếu; không phải 8 hóa đơn độc lập, không phải holdout và không phải accuracy tổng quát. Số trên đo **ứng viên phục hồi**, không giả là mọi CFR đã được tự điền/sửa. Policy chỉ RECOMMENDED cho trường hợp sửa hậu tố lặp đã được quy định; các thay đổi khác cần người dùng xét.

Chạy lại baseline trên 15 biến thể/9 nhóm bằng [evaluate_automation_pilot.py](../../../../../scripts/evaluate_automation_pilot.py): các nhóm field có nhãn không giảm so với đợt trước. [pilot_score.json](pilot_score.json) là extraction từ native text/OCR artifact cũ, **không cộng kết quả đọc lại vùng** vào accuracy baseline. Địa chỉ và toàn bộ ô bảng chưa có nhãn đầy đủ để báo accuracy.

## Kiểm thử và sử dụng

Kết quả cuối được ghi trong [validation_summary.json](validation_summary.json). Runner tạo thư mục evidence mới, giữ nguyên các báo cáo lịch sử:

**487 test Python, 56 nhóm kiểm tra Chrome, 9 kiểm tra JavaScript đều qua.** Lượt đầy đủ đầu tiên có một lỗi đồng bộ trong bài test Chrome tự động: kiểm tra apply đã ẩn ngay lúc record-loading rồi thao tác trước khi GET chẩn đoán hoàn tất. Đã sửa bước chờ của test và chạy lại riêng suite này: 7/7 qua. Các suite còn lại của lượt đầy đủ đều qua; mã runtime không đổi sau lượt đó. Summary ghi rõ follow-up, không giấu lần kiểm tra thất bại.

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/validate_field_coverage.py
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/benchmark_field_recovery.py
```

Test gồm identifier không mất số 0, MST chi nhánh, không salvage MST sai; ngày không tồn tại/đuôi thừa/ngày chữ ký; Decimal vượt 2^53, số tiền cạnh tranh và locale mơ hồ; giữ đúng vai trò và block nguồn của field MISSING; nhãn/value đảo thứ tự detector; địa chỉ dưới nhãn và không nuốt trường tiếp theo; đọc lại chỉ tạo ứng viên, không sửa CFR. Chrome kiểm tra thêm gợi ý ngày/tiền vào draft đúng định dạng và số lớn không qua float; giữ kiểm tra stale response, XSS, cache, auth, browser/mobile cũ.

Trên web: khởi động lại STOP/OPEN, Ctrl+F5. Bật luồng tự kiểm tra để chạy trong ngân sách; hoặc chọn trường → **Xem nguồn → Đọc lại vùng chữ → đối chiếu → Đưa vào bản nháp → Lưu dữ liệu hóa đơn**. Trường không có candidate cũ vẫn có thể đọc lại nếu tìm được block lỗi có căn cứ. Không tìm được block thì UI giữ yêu cầu đối chiếu toàn trang/xử lý riêng.

## Giới hạn còn lại

Không bảo đảm mọi trường trên mọi ảnh. Đợt này chưa tìm chữ detector bỏ sót, chưa render DPI mới, chưa sửa ảnh mờ/mất nét, chưa bổ sung recognizer/VLM thứ hai và chưa giải quyết mọi cấu trúc bảng. Trường không in trên nguồn không thể được OCR tạo ra. Những phần đó tiếp tục theo PLAN_OCR_EXTRACTION_V2, cần thêm ảnh thật, nhãn và benchmark riêng; không bật auto-accept bằng kết quả dev này.
