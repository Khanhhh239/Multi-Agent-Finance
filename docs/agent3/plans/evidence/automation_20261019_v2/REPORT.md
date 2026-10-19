# Tự phục hồi OCR và diễn giải cho người sử dụng — 19/10/2026

Đây là đợt củng cố PLAN_06/PLAN_12. Đã nối bốn phần: đánh giá field theo nhóm, trigger tự đọc lại vùng, chọn ứng viên có giới hạn và diễn giải dễ hiểu. Auto-accept vẫn tắt; rule thật và nghiệm thu pháp lý/production không đổi.

## Người dùng thao tác thế nào

1. Khởi động lại bằng STOP_AGENT3 rồi OPEN_AGENT3, nhấn Ctrl+F5.
2. Mở hóa đơn, bật **Tự kiểm tra và diễn giải sau khi tải / lưu**. Mặc định chưa bật, token và quyền WRITE vẫn được yêu cầu.
3. Hệ thống thử trích xuất lại nếu bản cũ không có dòng; sau đó tự chẩn đoán, đọc lại vùng đủ điều kiện, kiểm tra bản đã lưu và tạo diễn giải. Trong **Tự kiểm tra lỗi OCR**, xem lý do, giá trị cũ và chữ đọc lại.
4. Nếu có gợi ý được policy chọn, bấm **Đưa các gợi ý được chọn vào bản nháp**, đối chiếu ảnh nguồn rồi **Lưu dữ liệu hóa đơn**. Model không tự xác nhận hoặc thay giá trị đã lưu. Khi có bản nháp, luồng không gửi thêm yêu cầu phục hồi/kiểm tra cho bản chưa lưu.
5. Các trường khác vẫn cần review. Có thể dùng **Xem trường và nguồn**, hoặc đọc lại vùng thủ công. Nếu lượt đọc lỗi, nút **Thử lại lượt bị lỗi** dùng ngân sách retry còn lại; không lặp vô hạn khi bấm/chuyển phiên web.

Diễn giải thuộc đúng evaluation/revision đã lưu. Khi đang có bản nháp, kết quả cũ không được coi là kết quả của thay đổi chưa lưu. Tắt tự chạy sẽ dừng các bước tiếp theo; request đã gửi có thể hoàn tất và được giữ để xem lại. Chuỗi kiểm tra/diễn giải còn phụ thuộc browser đang mở; đây chưa là durable orchestration của PLAN_14.

## Policy phục hồi và chọn ứng viên

`recovery-policy-v1` chẩn đoán lặp từ/cụm từ ở cuối, ký tự thay thế Unicode, MISSING/AMBIGUOUS và conflict của block nguồn. Không xem điểm detection là confidence đọc chữ. Field HUMAN_CONFIRMED được bỏ qua, kể cả khi người dùng đã chủ động xóa giá trị.

Chỉ adapter tên/địa chỉ/mô tả hàng có thể đọc lại ở đợt này. Field số/ngày/MST còn cần đối chiếu hoặc adapter sau; lỗi chuẩn hóa của chúng không được biến thành suy đoán số mới. Không có box, vùng rời nhau, box nhiều dòng/quá lớn hoặc vượt ngân sách thì giữ REVIEW/DEFERRED thay vì đọc thiếu một phần.

Mỗi lượt tối đa **2 field, tổng 4 crop**. Ưu tiên lỗi lặp; giữ timeout/memory/output bound của regional worker. Sidecar `.automation.sqlite3` giữ reservation với lease 240 giây và tối đa **2 lượt** cho cùng record/revision/policy/code/runtime; lỗi được giữ, chỉ thử lại khi người dùng chọn retry. `BEGIN IMMEDIATE` và unique key ngăn hai phiên cùng chạy một lượt; tiến trình chết thì reservation hết lease, không tự phát sinh vô hạn lượt mới.

Chọn `RECOMMENDED` chỉ khi kết quả đọc lại đầy đủ và khớp đúng giá trị sau khi bỏ một hậu tố chữ lặp, theo NFC + whitespace + casefold. Không đề xuất bỏ hậu tố số hoặc token ngắn; không chọn khi có conflict. Kết quả đổi thành tên khác/số khác, chỉ đồng thuận hoặc đọc chưa đủ đều chưa chứng minh đúng. `RECOMMENDED` là lựa chọn ứng viên để người dùng xét, không phải calibration hoặc xác nhận độ chính xác.

Report, model observation và giá trị đã lưu là ba đối tượng riêng. Lý do lưu draft chứa run ID; quan hệ tới recovery ID, bbox/transform/crop hash và raw response được giữ trong các sidecar. UI bảo vệ đổi field/record/revision/tenant và response đến muộn. Không ghi trực tiếp vào CFR hoặc sửa reviewer correction; việc lưu dùng correction service/re-derive hiện có.

API:

```text
GET  /v1/records/{id}/automation-review?taxpayer_id=...
POST /v1/records/{id}/automation-review?taxpayer_id=...
```

```json
{"expected_record_revision": 1, "retry_failed": false}
```

GET trả chẩn đoán và queue hiện có, không gọi model. POST cần quyền WRITE; không nhận bbox, tên model, paths hay giá trị chọn từ client. Scope, strict revision, cache integrity, active lease và ngân sách đều kiểm tra ở backend. Sửa revision/config/runtime sẽ tạo binding mới, không tái dùng gợi ý từ bản trước.

## Diễn giải đã đọc / còn thiếu / cần làm gì

`UserGuide` lấy từ CFR trong snapshot evaluation, gồm số trường đã trích, số trường PRESENT đã được người dùng xác nhận, field thiếu/mơ hồ, tình trạng dòng hàng và bước đối chiếu. Không coi PRESENT là đã đúng; không coi 0 dòng là hóa đơn không có hàng. Guide luôn có cả khi model tắt hoặc fallback.

- **EVALUATION:** giữ gating corpus/citation/date, trích đoạn và kết quả engine gốc. Prompt dùng cách nói về phạm vi dễ hiểu, giữ ID kỹ thuật trong references thay vì đoạn diễn giải.
- **DATA_REVIEW:** nếu căn cứ pháp lý chưa dùng được và policy chọn NATURAL_DRAFT, chỉ đưa fact về tình trạng dữ liệu vào model. Không đưa kết quả PASS/FAIL hoặc trích đoạn pháp lý chưa phù hợp vào context này. `legal_context_reason` ghi nguyên nhân; UI ghi rõ chưa diễn giải kết quả thuế.

Controlled selection vẫn giữ hành vi cũ khi thiếu căn cứ; không dùng nhánh data-only để mở khóa diễn giải thuế. Qwen chỉ nhận fact tối thiểu, không nhận tên người bán/người mua, MST, raw OCR, token hoặc tenant IDs. Đầu ra cần JSON schema/refs/giới hạn số liệu, không có URL/markup/ID kỹ thuật trong prose. Nhánh data-only chặn thêm khẳng định pháp lý/thanh toán không có phủ định. Đây là kiểm tra cơ học, **không chứng minh toàn bộ ngữ nghĩa**; NATURAL_DRAFT luôn yêu cầu review, warnings/guide gốc vẫn được hiển thị độc lập. Core evaluation và replay không bị thay đổi.

## Đánh giá nhiều bố cục và giới hạn số liệu

Runner đọc lại 9 PDF native bằng reader hiện tại và chấm thêm 6 artifact scan/hybrid đã giữ, tổng **15 biến thể / 9 nhóm chứng từ-trang**. Trong đó **8 nhóm từ tài liệu công khai** và **1 nhóm tài liệu đào tạo chưa xác nhận**, báo riêng theo `dataset_groups`. Raster/hybrid của cùng chứng từ, cùng nguồn và cùng template có tương quan, không là 15 hóa đơn độc lập.

Chấm theo field có nhãn: MST, số/ký hiệu, ngày, tiền, tên và currency. Chuẩn hóa NFC/khoảng trắng; so tiền theo Decimal; tên chấm có phân biệt hoa/thường. Không biến địa chỉ/ô bảng chưa gán nhãn thành lỗi model. Item count chỉ chấm khi có nhãn; chưa có cell/row exact-match đầy đủ.

[pilot_score.json](pilot_score.json) lưu mẫu số, wrong-present, thiếu/mơ hồ, nhóm bố cục, input hash và khoảng Wilson tham khảo. Các khoảng này không dùng làm release gate vì field/variant có tương quan và nhãn do agent đối chiếu, chưa có kiểm chứng độc lập. Score là baseline extraction hiện tại trên retained OCR/native replay, không giả là OCR model vừa chạy lại trên mọi trang hoặc accuracy sau tự sửa.

Tên doanh nghiệp vẫn có wrong-present trên một số bản scan/hybrid. Policy không tự sửa tên chỉ vì ô đã được điền hoặc recognizer thứ hai trả chữ khác. Do đó chưa bật auto-accept, chưa đạt mục tiêu accuracy holdout hoặc chứng minh tỷ lệ lỗi gần 0.

Nhóm nguồn công khai, 14 biến thể của 8 nhóm chứng từ/trang (mẫu đào tạo không nằm trong bảng này):

| Field | Đúng / có nhãn | Điền sai / đã điền | Thiếu hoặc mơ hồ |
|---|---:|---:|---:|
| MST | 26/28 | 0/26 | 2 |
| Số/ký hiệu | 27/28 | 0/27 | 1 |
| Ngày | 13/14 | 0/13 | 1 |
| Tổng tiền | 41/41 | 0/41 | 0 |
| Tên | 20/28 | 4/24 | 4 |
| Currency có nhãn | 3/3 | 0/3 | 0 |

Mẫu số trên là field-variants có tương quan, không phải số hóa đơn độc lập; nhãn và độ lớn tập chưa đủ để xác nhận release gate. Nhiều field đúng trong native PDF không chứng minh model OCR đọc ảnh đạt cùng tỷ lệ.

## Model thật và hồi quy

Đã thử Chrome/HTTP/SQLite trên bản sao DB với hóa đơn từng mất dòng và lặp từ: luồng tự chẩn đoán → regional VietOCR → queue → evaluation → Qwen DATA_REVIEW; chọn một gợi ý và đưa vào draft, giá trị đã lưu không đổi. Raw text, DB và screenshots giữ local, không đưa lên Git. [model_runs.json](model_runs.json) chứa metadata của các lượt model thật và giới hạn nhãn; đây là self-check kỹ thuật trên dev, không phải nghiệm thu độc lập.

Lượt DATA_REVIEW đầu khoảng 87 giây, lượt xác minh sau khoảng **101 giây**; một gợi ý được chọn và chỉ đưa vào draft. Lượt Qwen **EVALUATION** với citation dùng được khoảng **96 giây**, trả NATURAL_DRAFT và giữ nguyên evaluation gốc. Đây là các lượt trên máy hiện tại trong lúc kiểm thử, không phải SLA. Cả hai chế độ vẫn cần đối chiếu nội dung; JSON hợp lệ và refs đầy đủ không chứng minh model đã bảo toàn mọi ý nghĩa.

Các bài test gồm trigger/false-positive, bảo vệ HUMAN_CONFIRMED, không tự đổi số/tên, cache/retry qua phiên, lease đang chạy, stale revision, auth/strict contract, trường quá nhiều crop; thêm guide không lộ danh tính và nhánh data-only từ chối kết luận thuế. Chrome kiểm tra đọc queue không gọi model khi chưa bật, opt-in chain, draft/apply, giữ CFR, late response và mobile/desktop. Các suite ingestion/extraction/review/planning/ZEN/legal/explanation cũ vẫn được chạy; reader/provider doubles trong browser tách khỏi model thật.

Chạy từ root:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/validate_automation_v2.py
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/evaluate_automation_pilot.py --output agent3_tax_compliance/data/automation_v2/pilot_score.json
```

Kết quả hồi quy ở [validation_summary.json](validation_summary.json), các report browser cùng thư mục. Bộ dữ liệu được gitignore; lệnh chấm pilot cần dữ liệu local có sẵn. Máy clone mới vẫn chạy được các unit/browser fixture tests sau khi cài môi trường, không tự tải hay gửi hóa đơn tới dịch vụ ngoài.

Hồi quy đầy đủ: **473 test Python**, **53 nhóm kiểm tra Chrome**, **7 JavaScript syntax checks + 2 client harness checks** qua. Bổ sung một check Chrome về hết ngân sách retry sau đó (tổng 54), chạy lại các browser tự động hóa và JS liên quan sau khi gọn queue; chạy lại 64 test explanation sau khi bổ sung cách diễn đạt scope cho người dùng. Core workflow/replay thuế giữ nguyên hash.

## Phần còn lại

Chưa có holdout/calibration đủ lớn để auto-accept; chưa tự phát hiện mọi trường tên đọc sai. Chưa render lại DPI khác, tìm chữ detector bỏ sót, fine-tune, gán nhãn đầy đủ địa chỉ/ô bảng, hoặc thay toàn bộ OCR pipeline. Chưa có catalog hàng thật/nghiệm thu rule và production hardening. Những phần đó vẫn theo kế hoạch riêng, không được đánh dấu hoàn tất bởi đợt này.
