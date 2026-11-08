# Giảm nhiễu A1/A2/A4 bằng bằng chứng nghĩa vụ chi

Ngày kiểm tra: 14/10/2026. Bản sửa giữ nguyên ngưỡng, trọng số và chính sách hàng đợi. Theo quyết định nghiệp vụ, **thiếu hồ sơ vẫn giữ cách cảnh báo hiện tại**; chỉ bằng chứng hợp lệ, gắn đúng khoản chi mới cấp ngoại lệ.

## Chính sách đã triển khai

### A1/A2

Engine vẫn phát hiện mẫu số tiền/thời gian hiện tại. Khi nguồn ràng buộc đã được quan sát tại công ty, một khoản chỉ được loại khỏi cụm hoặc được xác nhận là trả theo nghĩa vụ hợp lệ khi:

- `procurement_links` gắn đúng `transaction_id`, NCC, `request_id` và `purchase_order_id`, đã được người khác xác minh;
- `payment_requests` đã duyệt trước lúc lập giao dịch, đúng NCC, nghiệp vụ, PO và các ràng buộc hợp đồng/hóa đơn/tài khoản nhận tiền nếu nguồn khai báo;
- `transaction_documents` có hóa đơn đã xác minh, đúng NCC, số hóa đơn và gross;
- tổng đã trả trên **toàn lịch sử quan sát**, gồm cả giao dịch cùng thời điểm, không vượt gross hóa đơn hoặc trần yêu cầu chi;
- nhiều request khác nhau không dùng chung một PO để giả thành các nghĩa vụ độc lập.

Hợp đồng trả nhiều đợt là nhánh thay thế: cần đúng một `supplier_payment_agreements` hiện hành đã duyệt cho hợp đồng, hóa đơn đã xác minh cho từng khoản, tổng từng hóa đơn và tổng hợp đồng đều chưa vượt trần. Nhiều agreement hiện hành cho cùng hợp đồng được xem là mơ hồ và không cấp ngoại lệ.

Các nghĩa vụ độc lập có đủ hồ sơ được loại khỏi phạm vi tính của giao dịch hiện tại. Cùng request/PO/hợp đồng vẫn được tính chung. Mã tự khai, số lượng chứng từ, nguồn thu hồi, nguồn tương lai, sai NCC, sai người nhận hoặc bằng chứng do chính người lập xác nhận không cấp ngoại lệ.

### A4

Khoản cận hạn mức không tham gia bộ đếm A4 nếu có một trong các quyền chi hợp lệ ở trên, hoặc một lịch chi định kỳ đã duyệt:

- đúng NCC/nhân viên, nghiệp vụ, hợp đồng, hóa đơn và tài khoản nhận tiền khi các trường đó được khai báo;
- chỉ một lịch phù hợp; nhiều lịch mơ hồ không được chọn có lợi;
- hỗ trợ tuần, tháng, quý và năm theo lịch; `allow_partial=1` mới cho phép chia số tiền kỳ thành nhiều đợt;
- tổng mọi khoản cùng kỳ, kể cả cùng timestamp và ngoài cửa sổ A4, không vượt `expected_amount_vnd + tolerance_vnd`;
- hóa đơn có trên giao dịch vẫn bị ràng buộc bởi gross và tổng đã trả.

Ngoại lệ lương theo `payroll_entitlements` của đợt 3 được giữ. Một quyền chi không được dùng lại cho các khoản vượt trần.

## Phiên bản và thời gian quan sát

Mỗi nguồn có ID ổn định. Revision giữ nguyên liên kết nghiệp vụ và dùng `observed_at` mới; revision `revoked` thay thế trạng thái trước từ thời điểm được quan sát. Phê duyệt phải có trước lúc lập giao dịch. Nguồn tương lai không đổi điểm hoặc ngoại lệ quá khứ. Hai revision mâu thuẫn cùng ID/thời điểm bị từ chối.

Khi công ty chưa có `payment_requests` hoặc hóa đơn typed đã quan sát, A1/A2 giữ cơ chế cũ. Khi nguồn ràng buộc đã xuất hiện, dòng thiếu bằng chứng hợp lệ không được suy là hợp lệ. Đây là cách thực thi lựa chọn “giữ cảnh báo như hiện tại khi thiếu hồ sơ”.

## Nguồn dữ liệu

[Schema máy đọc](../sme_fraud/payment_evidence.schema.json) và [các CSV mẫu](../examples/payment_evidence_sources/README.md) mô tả:

- `payment_requests.csv`
- `procurement_links.csv`
- `transaction_documents.csv`
- `supplier_payment_agreements.csv`
- `recurring_payments.csv`
- `vendor_payment_schedules.csv` (B6 theo mùa/năm)

Các CSV có trong dataset phải được khai báo checksum trong `manifest.json`. Số tài khoản thực cần `recipient_bank_code`; chuỗi tài khoản trùng nhưng thiếu ngân hàng không được coi là cùng định danh.

## Kiểm chứng

Có 18 đối chứng mới cho A1/A2/A4: cùng nghĩa vụ hợp lệ, nghĩa vụ độc lập, đổi request nhưng cùng PO, vượt trần request/hóa đơn/hợp đồng, khoản ngoài cửa sổ, hợp đồng mơ hồ, nguồn sai/thu hồi/tương lai, nhiều hợp đồng định kỳ, giới hạn kỳ, khoản cùng timestamp, phân biệt hóa đơn với loại chứng từ khác và giữ hành vi khi thiếu nguồn. Toàn bộ 169 kiểm thử của dự án đều đạt; [kết quả máy đọc](../.runtime/payment_evidence_test_result.json) và [log chi tiết](../.runtime/payment_evidence_tests.log) được lưu cùng lần kiểm tra này.

Chấm lại 37.500 dòng train/validation của seed `2026101401`, tỷ lệ toàn dataset 0,3%. Snapshot này không có các nguồn trên, nên theo chính sách đã chọn toàn bộ tập candidate, hit góp điểm và hàng đợi giữ nguyên. Không đọc/chấm split test và không dùng ML.

| Split | Rule/hàng đợi | TP | FP | Thêm | Loại |
| --- | --- | ---: | ---: | ---: | ---: |
| Train | A1 | 7 | 292 | 0 | 0 |
| Train | A2 | 6 | 98 | 0 | 0 |
| Train | A4 | 3 | 281 | 0 | 0 |
| Train | Hàng đợi | 63 | 332 | 0 | 0 |
| Validation | A1 | 3 | 148 | 0 | 0 |
| Validation | A2 | 4 | 38 | 0 | 0 |
| Validation | A4 | 0 | 150 | 0 | 0 |
| Validation | Hàng đợi | 30 | 169 | 0 | 0 |

TP/FP trong bảng dùng nhãn ý đồ gian lận mô phỏng, không phải kết luận độc lập rằng predicate đúng/sai. Kết quả không đổi là kiểm tra chống hồi quy khi thiếu nguồn; chưa chứng minh mức giảm FP trên SME thật. [Kết quả cuối, replay và checksum](rule_repairs/payment_evidence_release/seed_2026101401/sme_fraud_003/comparison.json).

## Giới hạn còn lại

Nguồn hiện giả định một binding bất biến cho mỗi ID. Nếu một request/PO có nhiều NCC hoặc một lịch định kỳ có nhiều người nhận hợp lệ, phải tách thành các ID/quyền chi riêng. Việc sửa dữ liệu bằng xóa vật lý làm mất lịch sử as-of; phải gửi revision thu hồi.

Bản sửa không tự OCR hóa đơn, xác minh chữ ký hoặc kiểm tra nhà cung cấp bên ngoài. Không có nguồn thật thì engine không thể biết một giao dịch nền là nghĩa vụ độc lập; do đó FP trong snapshot hiện tại không tự giảm. Bước nghiệm thu nghiệp vụ vẫn cần dữ liệu ERP/AP thật và kết luận kế toán độc lập.

Các feature ML hiện tại chưa chứa trạng thái quyền chi mới. Chưa đưa bằng chứng này vào ML trước khi lớp luật được nghiệm thu.
