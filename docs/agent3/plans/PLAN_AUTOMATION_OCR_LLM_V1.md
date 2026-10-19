# OCR, diễn giải và tự động hóa — lát cắt triển khai 18/10/2026

Đây là nhánh củng cố PLAN_06 và PLAN_12, không phải nghiệm thu PLAN_14. Giữ PLAN_OCR_EXTRACTION_V2 làm kế hoạch đầy đủ; không đánh dấu xong các hạng mục chưa được thử nghiệm.

| Công việc | Trạng thái / bằng chứng |
|---|---|
| Đóng băng đầu vào phát triển | Đọc lại 10 artifact OCR cũ bằng DB read-only; input và extractor hashes, nhóm dev đã dùng sửa code; không giả làm holdout |
| Sửa mất bảng đã chẩn đoán | Giữ dòng chữ chạm mép header; không nuốt phần mô tả xuống dòng vào STT; fallback khi VAT footer bị chọn làm header |
| Recovery trên web | Trích xuất lại từ OCR bất biến; tạo hồ sơ riêng nếu code đã đổi, cache chống tạo bản vô hạn; giữ revision/đối chiếu cũ |
| Diễn giải tự nhiên | NATURAL_DRAFT có nguồn, thêm tóm tắt đã đọc/thiếu/việc cần làm; thiếu căn cứ thì chỉ diễn giải chất lượng dữ liệu với scope DATA_REVIEW, không kết luận thuế |
| Luồng tự chạy | Opt-in: phục hồi bảng nếu cần → chẩn đoán và đọc lại vùng theo ngân sách → kiểm tra bản đã lưu → diễn giải. Có cache, lease và giới hạn lượt thử qua phiên web; gợi ý chỉ vào bản nháp khi người dùng chọn |
| Bật auto-accept | **CHƯA BẬT**: thiếu calibration/holdout và nghiệm thu chất lượng |
| Duyệt luật / mapping hàng thật | **PENDING**: không đổi DRAFT thành approved bằng code |
| OCR lại vùng nguồn — 19/10 | Đã có nút đọc lại tên/địa chỉ/mô tả hàng từ tối đa 4 block dòng đã có evidence. VietOCR beam search chạy riêng, giữ observation cũ/mới và cache; ứng viên chỉ vào bản nháp khi người dùng chọn. [Runbook và giới hạn](evidence/region_recovery_20261019_v1/REPORT.md) |
| Vùng chưa detect / render DPI mới / layout mới | **CHƯA TRIỂN KHAI**: đọc lại vùng hiện dùng render đã giữ, không tìm lại chữ chưa có box hoặc tự chọn vùng/bố cục bằng model mới |
| Job bền vững khi đóng browser | Capture worker hiện có tiếp tục chạy; chuỗi UI mới chỉ chạy khi trang mở. Durable orchestration/production còn thuộc PLAN_14 |
| Dữ liệu mở rộng, fine-tune và nghiệm thu readability | **PENDING**; không suy chất lượng tổng quát từ fixture/dev đã sửa |

## Thứ tự kiểm chứng

1. Hồi quy geometry/field binding và Decimal; không mất evidence hoặc tự suy thuế từ tổng tiền.
2. API recovery: auth, tenant, revision, idempotency qua extractor cache, concurrency, giữ hồ sơ cũ.
3. LLM: schema local thật, số liệu/nguồn/cảnh báo, fallback, mode draft bắt buộc; không nhận JSON hợp lệ là đã đúng ngữ nghĩa.
4. Browser: chạy theo lựa chọn của người dùng, cache đúng phiên bản, lưu → kiểm tra lại, không gửi POST khi có bản nháp, phục hồi 0 dòng một lần và tiếp tục.
5. Đo dev và model thật, tách khỏi fixture và giữ dữ liệu chứng từ ngoài Git.

Xem [báo cáo và runbook](evidence/automation_20261018_v1/REPORT.md).

## Bổ sung 19/10 — đọc lại vùng, vẫn trong PLAN_06

Luồng thủ công: **Xem nguồn → Đọc lại vùng chữ → đối chiếu ứng viên → Đưa vào bản nháp → Lưu dữ liệu hóa đơn**. Với dòng hàng, mở **Chi tiết** trước để thấy nút Xem nguồn. Không tự sửa reviewer correction và không bật auto-accept. Đợt đầu chưa tự gọi model vùng; đợt tự động có giới hạn được bổ sung bên dưới.

Thử nghiệm trên một hóa đơn dev có lỗi lặp từ cuối dòng: greedy vẫn lặp, beam search trên cùng crop đã bỏ lỗi lặp; đã xác minh lại qua Chrome với model thật trên bản sao DB. Đây là bằng chứng sửa một lỗi, không phải accuracy holdout. Các bước mở rộng dataset, layout, recognizer khác và tự động chọn kết quả vẫn giữ trạng thái chưa nghiệm thu.

## Đợt tự động hóa tiếp theo — 19/10

Đã triển khai bốn phần kỹ thuật được chọn:

1. Chấm riêng từng nhóm field trên native PDF đọc lại bằng reader hiện tại và các artifact OCR scan/hybrid đã giữ; báo số mẫu, wrong-present và phần chưa có nhãn. Mẫu đào tạo báo riêng, không giả làm hóa đơn độc lập hoặc holdout.
2. Trigger theo lặp hậu tố, ký tự lỗi, trạng thái missing/ambiguous và xung đột nguồn. Chỉ đọc lại trường được adapter hỗ trợ và có geometry hợp lệ; tối đa 2 trường/4 crop mỗi lượt. Lease và số lượt được giữ ở SQLite, không mất giới hạn khi tải lại web.
3. Policy chỉ đề xuất sửa lặp khi chuỗi đọc lại khớp chính xác giá trị bỏ một hậu tố lặp (NFC/khoảng trắng/hoa thường). Thay số, đổi tên khác hoặc xung đột đều giữ REVIEW; HUMAN_CONFIRMED được bỏ qua. Không sửa CFR hoặc tạo xác nhận bằng model. Người dùng đưa các đề xuất vào bản nháp rồi đối chiếu/lưu.
4. UI diễn giải có ba phần dễ hiểu; Qwen chỉ nhận fact tối thiểu, không nhận tên/MST/raw OCR. Khi căn cứ pháp lý chưa dùng được, context DATA_REVIEW chỉ chứa tình trạng dữ liệu và bước xử lý, không đưa kết quả thuế vào lời model. Giữ nguyên report/core replay và cảnh báo bản nháp.

Xem [runbook, kiểm thử và giới hạn của đợt này](evidence/automation_20261019_v2/REPORT.md). Vẫn thuộc PLAN_06/PLAN_12. Chưa bật auto-accept, chưa hoàn tất OCR V2 toàn bộ hoặc nghiệm thu production/pháp lý.

## Mở rộng độ phủ trường — 19/10, round 3

Đã mở rộng bộ đọc vùng cho MST, số/ký hiệu, ngày lập, currency và totals; tìm lại vùng từ quan sát không parse được khi CFR thiếu evidence, giữ vai trò và giới hạn ngân sách. Cải thiện địa chỉ/MST dưới nhãn, nhãn song ngữ và thứ tự crop. Gợi ý tên loại nhãn/anchor trước khi đưa vào draft; số/ngày phải qua parser và dùng đúng định dạng UI.

Model thật đã đọc lại 8 lỗi được chọn từ 3 hóa đơn dev: cứu đúng cả 4 trường từng trống; tên còn lỗi nên vẫn review, không tự xác nhận. Không dùng phép đo này như holdout hoặc kết quả tự điền CFR. Chi tiết, số liệu và cách chạy ở [báo cáo round 3](evidence/field_coverage_round3/REPORT.md). Vẫn còn chữ không được detect, ảnh mờ và bảng khó ngoài phạm vi đợt này.
