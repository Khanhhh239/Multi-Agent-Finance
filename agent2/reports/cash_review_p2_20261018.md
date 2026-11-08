# P2: phân loại bằng chứng, điểm và hàng đợi — 18/10/2026

**Đã áp dụng chính sách mặc định `cash_review_policy=evidence_v2`.** Thiếu dữ liệu được giữ thành yêu cầu bổ sung có bằng chứng, tách khỏi cảnh báo giao dịch dựa trên điểm. Giữ nguyên chính sách ngưỡng đối chiếu tiền mặt hiện có; không điều chỉnh A5, model hoặc nguồn mô phỏng.

[Tổng hợp pipeline](cash_review_20261018_v2/summary.json), [so sánh với lượt trước](cash_review_20261018_v2/p2_comparison.json), [đối soát artifact](cash_review_20261018_v2/artifact_validation.json), [cấu hình đã khóa](cash_review_20261018_v2/evaluation_plan.json).

## Chính sách tiếp nhận

| Bằng chứng | Điểm P2 | Ưu tiên khi đứng riêng | Cách xử lý |
| --- | ---: | --- | --- |
| Thiếu/không hợp lệ thông tin hóa đơn, số tiền VND hoặc xác minh hạn mức | 0 | Thấp | Giữ hit và yêu cầu bổ sung; trạng thái chờ bổ sung |
| Đủ thông tin hóa đơn để đối chiếu chứng từ thanh toán/VAT | 8 | Trung bình | Vào hàng đợi rà soát nghiệp vụ |
| Vượt hạn mức nội bộ có xác minh được khai báo và còn hiệu lực lúc chi | 14 | Cao | Vào hàng đợi rà soát nghiệp vụ, không hard trigger |

Điểm 14 sử dụng ngưỡng ưu tiên cao đang có của engine, không phải trọng số đã hiệu chỉnh từ nhãn gian lận. Hạn mức nội bộ chỉ được coi là đã xác minh khi có nguồn, người xác minh, số tiền khớp cấu hình và mốc thời gian hợp lệ. Một con số hạn mức đơn lẻ không đủ. Nếu đồng thời vượt hạn mức đã xác minh và thiếu hóa đơn, bằng chứng về hạn mức vẫn có thể mở hồ sơ; các trường hóa đơn thiếu tiếp tục được liệt kê.

Nguồn xác minh là khai báo có cấu trúc của người phụ trách; module không đọc tài liệu gốc hoặc xác thực chữ ký. Dữ liệu xác minh sau thời điểm chi không được dùng làm bằng chứng đã biết lúc chi. Cấu hình mẫu hiện biểu diễn một chính sách/công ty/snapshot. [Mẫu và hợp đồng cấu hình](../examples/cash_review/README.md).

001/003 chưa có thông tin hóa đơn đầy đủ cho các hit P2 và chưa khai báo hạn mức nội bộ có nguồn xác minh. Vì vậy hai bộ này chỉ kiểm chứng chuyển nhóm thiếu dữ kiện; các nhánh 8/14 điểm được kiểm chứng bằng tình huống đối chứng riêng trong kiểm thử, chưa phải trường hợp thực tế của SME.

## Kết quả chạy lại 001/003

| Hạng mục | 001 | 003 |
| --- | ---: | ---: |
| Hồ sơ giao dịch trước sửa | 412 | 450 |
| Hồ sơ giao dịch sau sửa | 112 | 163 |
| Yêu cầu bổ sung P2 mới | 328 | 320 |
| Hồ sơ nguồn sau sửa | 144 | 144 |
| Tổng hồ sơ trước sửa | 556 | 594 |
| Tổng hồ sơ sau sửa | 584 | 627 |
| Hit P2 giữ nguyên | 1.217 | 1.192 |
| Giao dịch P2 trong nhóm yêu cầu bổ sung | 1.206 | 1.180 |
| Giao dịch P2 nằm trong hồ sơ nghiệp vụ độc lập | 11 | 12 |

Tổng 41.082 giao dịch được chạy từ nguồn qua rules, NetworkX, ngưỡng động, hàng đợi, API kết luận, restart và thông báo giả lập. **Toàn bộ 2.409 hit P2 cũ được giữ, đều chuyển từ 8 xuống 0 điểm do thiếu hóa đơn.** Không tự xem các giao dịch này là hợp lệ hoặc kết luận cảnh báo sai.

Tổng hồ sơ không phải chỉ số cảnh báo rủi ro: các yêu cầu bổ sung được gộp riêng theo công ty–thực thể và cửa sổ 30 ngày, nên có thể làm tổng hồ sơ tăng. Giao dịch đã thuộc hồ sơ nghiệp vụ được giữ hit P2 tại hồ sơ đó, không mở thêm yêu cầu trùng. Số hồ sơ giao dịch giảm phản ánh chính sách tiếp nhận mới; chưa chứng minh precision/recall tốt hơn.

Đối chiếu giữ nguyên số hit từng rule, ma trận đặc trưng, fingerprint đồ thị và bảng ngưỡng động so với lượt diễn tập trước. Các điểm ngữ cảnh C1/A5/B3 có thể mất điểm hỗ trợ khi P2 không còn làm bằng chứng neo; điểm lặp lại và nhóm hồ sơ được tính lại theo engine. 1216/1216 điều kiện nguồn khớp kỳ vọng, không có mismatch. Đây là điều kiện nguồn mô phỏng, không phải nhãn gian lận độc lập.

## Hàng đợi, UI và thông báo

- Thêm loại hồ sơ `information_request`: 0 điểm, ưu tiên thấp, chờ bổ sung ngay từ đầu; không tạo kết luận bot để giả trạng thái này.
- Bộ lọc **Yêu cầu bổ sung P2** và mức ưu tiên **Thấp**; khi chọn nhóm này, UI bỏ lọc ưu tiên hôm nay để thấy cả tồn đọng. API và xuất CSV dùng cùng bộ lọc.
- Bằng chứng P2 hiển thị nhóm xử lý, số tiền, hóa đơn, hạn mức, nguồn/người/thời điểm xác minh, các trường còn thiếu và hành động tiếp theo.
- Yêu cầu bổ sung không tự làm neo cộng điểm cho ngữ cảnh. Khi có rule độc lập đủ điều kiện, hồ sơ nghiệp vụ và bằng chứng đó vẫn được giữ.
- Mở yêu cầu bổ sung vẫn dùng chung ngân sách hồ sơ/phút xử lý. Có thể xuất hiện trong tóm tắt tuần; không tự sinh job thông báo ưu tiên cao.

Lượt chạy lưu 6 kết luận **giả lập**, giữ qua restart. Outbox có 128 job: 120 simulated và 8 cancelled. Đã kiểm ngân sách 5/5/10 qua ba ngày đồng hồ giả lập; **0 lần gọi transport ngoài, 0 tin gửi ra ngoài, 0 job ưu tiên cao gắn yêu cầu bổ sung P2**.

[Outbox](cash_review_20261018_v2/notification_outbox.mock.json), [phân bổ ngày](cash_review_20261018_v2/notification_allocations.mock.csv), [kiểm tra API/restart](cash_review_20261018_v2/review_notification_checks.json).

Đọc lại API thực tế trên hai snapshot xác nhận 648 yêu cầu bổ sung có trạng thái chờ bổ sung và ưu tiên thấp, phân trang/xuất CSV khớp toàn bộ ID. Kiểm tra này không ghi thêm phản hồi hay phân bổ lượt. [Kết quả API theo nhóm](cash_review_20261018_v2/api_category_validation.json).

## Kiểm chứng và phạm vi

- Hồi quy: **558/558**, không failure/error. [Kết quả](../.runtime/cash_review_20261018/final.json), [log](../.runtime/cash_review_20261018/final.log).
- Tập trung P2/API/pipeline: 39/39; JavaScript 7/7. Hai nhóm kiểm thử Python có giao nhau, không cộng số lượng. [P2](../.runtime/cash_review_20261018/focused.json), [JavaScript](../.runtime/cash_review_20261018/ui_checks.json).
- Đối soát sau chạy: 229 tệp nguồn/báo cáo cũ giữ nguyên, 522 phân phối ngưỡng tính lại khớp, 8.433 ID nút đúng phạm vi. Các file WAL/SHM/lock đang sống không nằm trong fingerprint.
- Các file dự đoán đã khóa và audit của lượt `pipeline_rehearsal_20261018_v2` cũng giữ nguyên.
- Holdout `data/synthetic_sources_20261017_v2/sme_fraud_005` chưa nạp/chấm/giải mã oracle; chỉ đối chiếu hash opaque. Chưa fit/chấm model.
- Chưa nghiệm thu trực quan browser, dữ liệu SME thật hoặc dịch vụ gửi thật. Reviewer độc lập = 0; Gate nguồn thật vẫn `awaiting_real_data`.

Lượt hồi quy đầu phát hiện snapshot lịch sử có thể chỉ chứa bảng điểm mà không có danh sách hit. Đã sửa tương thích, thêm đối chứng và chạy lại bộ hồi quy cùng pipeline vào output `_v2`. [Bản đầu giữ để truy vết](./cash_review_20261018/SUPERSEDED.md).

Kiểm thử phân biệt ba nhóm, biên ngưỡng, chi trả một phần, hóa đơn tương lai, thiếu hóa đơn, ngoại tệ, phạm vi công ty, hạn mức thiếu xác minh, xác minh tương lai, hết hiệu lực, metadata không hợp lệ, neo điểm ngữ cảnh, gộp yêu cầu và chống trùng với hồ sơ nghiệp vụ. Các tình huống được khai báo trong kiểm thử, không thay đổi nguồn/nhãn của 001/003/005.

## File nên đọc và mở kết quả

1. [cash_controls.py](../sme_fraud/cash_controls.py): bằng chứng, phân loại, thời gian xác minh và metadata hạn mức.
2. [rules.py](../sme_fraud/rules.py): điểm P2, vai trò và coverage.
3. [case_queue.py](../sme_fraud/case_queue.py): yêu cầu bổ sung và phân biệt thành viên cảnh báo nghiệp vụ.
4. [review_store.py](../sme_fraud/review_store.py), [review_server.py](../sme_fraud/review_server.py), [app.js](../review_ui/app.js): trạng thái ban đầu, lọc/xuất và trình bày bằng chứng.
5. [test_cash_controls.py](../tests/test_cash_controls.py), [test_cash_review_flow.py](../tests/test_cash_review_flow.py): đối chứng nghiệp vụ và luồng API/outbox.

```powershell
& 'C:\Users\Technical Support\AppData\Local\Programs\Python\Python312\python.exe' -B -m sme_fraud.review_server --data-root data/synthetic_sources_20261017_v2 --reports-root reports/cash_review_20261018_v2 --database reports/cash_review_20261018_v2/review.sqlite3 --port 8765 --qa
```

Chạy tại thư mục dự án với Python đã cài dependencies; dừng server cũ nếu đang dùng cùng cổng. Database mới chứa kết luận bot và các ngày phân bổ giả lập, không phải database vận hành. Tái lập chạy vào thư mục trống bằng `python -B -m sme_fraud.run_pipeline_rehearsal --output reports/cash_review_repeat`. Khi cần hành vi P2 cũ, ghim `cash_review_policy=legacy_v1` trong cấu hình chấm riêng.
