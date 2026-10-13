# Phạm vi capture MVP — v1

> Quyết định 11/10/2026: [technical-functional-v1](technical_scope_decision.md) là phạm vi bàn giao PLAN_00 → PLAN_01. Bảng dưới mô tả sản phẩm đích; chưa chứng nhận hỗ trợ/accuracy thực tế. DQ-01–05 phải được kiểm tại nghiệm thu PLAN_05–06.

Chốt kỹ thuật ngày 11/10/2026 theo hướng OCR/PDF trước. Người dùng chính: kế toán nhập và kiểm tra chứng từ của một taxpayer trong tenant. Một tenant có thể quản lý nhiều taxpayer; mỗi lần xử lý chọn đúng taxpayer/master revision, không tự dùng tenant làm người mua.

## Đầu vào và đầu ra

Đầu vào đích: PDF có text, PDF scan, ảnh PNG/JPEG hóa đơn; một hoặc nhiều trang. PDF mixed được nhận diện theo từng trang; nhiều hóa đơn trong một file cần tách/confirm trước khi tạo record. Không tuyên bố đã hỗ trợ các format này trước khi PLAN_02–06 nghiệm thu.

Đầu ra mốc M1: CFR có field statuses, provenance/candidates, review tasks, correction audit và JSON export. Người dùng xem vùng bằng chứng cạnh dữ liệu, sửa rồi hệ thống rederive các field phụ thuộc trước đánh giá quality lại. M1 không kết luận tuân thủ thuế, không chứng minh thanh toán, không tự phân loại legal VAT category.

## Field × document family

| Field | Hóa đơn thuế đích | Receipt MC-OCR hiện có | Bằng chứng và xử lý khi không đọc được |
|---|---|---|---|
| seller.name | Cốt lõi | Có nhãn SELLER ở một phần tập | Text vùng người bán; nhiều ứng viên → AMBIGUOUS/review |
| seller.tax_id | Cốt lõi | Chưa có nhãn tương ứng | MST cạnh đúng seller; không chọn MST đầu tiên; không có nhãn → NOT_ANNOTATED ở ground truth |
| buyer.name/tax_id | Cốt lõi nếu nguồn thể hiện | Chưa có nhãn | Vùng buyer riêng; không suy từ taxpayer; không thấy trên OCR chưa chứng minh absent |
| invoice.number/series | Number cốt lõi; series tùy profile | Chưa có nhãn | Label/giá trị đúng hóa đơn, không dùng số giao dịch receipt thay thế |
| invoice.issue_date | Cốt lõi | TIMESTAMP receipt không đồng nghĩa ngày lập invoice | Giữ raw/date locale, mơ hồ → candidates/review |
| currency | Cốt lõi khi chuẩn hóa tiền | Không có nhãn riêng | Quan sát trực tiếp hoặc profile có provenance; không tự VND vì tài liệu tiếng Việt |
| totals.gross | Cốt lõi | TOTAL_COST có nhãn | Phân tổng thanh toán với tiền khách đưa/tiền thừa; Decimal string |
| totals.net/vat | Khi hóa đơn thể hiện | Chưa có nhãn riêng | Giữ observed totals, derived sums riêng; không sửa nguồn khi lệch |
| items.description/quantity/unit_price/net | Trích khi có bảng; review nếu không đủ | Không có row labels trong GT field hiện hữu | Page/row evidence, immutable item_id; bảng mất/trang thiếu → discovery incomplete/unknown |
| items.vat_treatment/vat_rate | Khi được thể hiện | Chưa có nhãn | TAXABLE_RATE/KCT/KKKNT; 0% khác KCT; nhãn không rõ → review |
| seller.address | Tùy chọn | ADDRESS receipt không bảo đảm role seller | Chỉ map seller address sau kiểm vai trò; baseline lưu như receipt address |
| invoice_direction/counterparty | Derived, không raw OCR | Không có ground truth chuẩn | Derive theo seller/buyer + taxpayer master; unknown → AMBIGUOUS/null |
| vat_category | Chưa tự sinh ở M1 | Không có nhãn | PLAN_07 taxonomy evidence, không suy từ rate |
| payment evidence | Ngoài scope M1 | Receipt có ghi cách trả chưa chứng minh bank | Yêu cầu nguồn phù hợp ở chặng sau |

“Cốt lõi” là field cần có trạng thái rõ và review được, không buộc parser tự điền đủ mọi chứng từ. Field thiếu hoặc không đọc được vẫn xuất CFR partial, không tạo dữ liệu giả.

## Giới hạn release đầu

- Chưa có dữ liệu hóa đơn thuế Việt Nam thực tế để chứng minh accuracy; chỉ có receipt legacy và fixture tổng hợp.
- PDF scan tổng hợp không mô phỏng đủ ảnh chụp lệch, mờ, bóng, dấu mộc hoặc handwriting thực tế.
- Đối soát invoice/payment/ledger, chữ ký số, XML/Excel/ERP/bank nằm ngoài capture M1.
- MST demo trong fixture cố ý không hợp lệ nội dung; test đọc đúng khác test xác nhận MST tồn tại/hợp pháp.
- Không auto-accept field theo confidence trước calibration; human confirmation có audit, không gán xác suất 1.0.

## Quyết định và điều kiện mở rộng

Scope kỹ thuật v1 được dùng làm input cho contracts PLAN_01. Khi bổ sung dataset, ghi nguồn/license/version và label coverage trước khi import. Chỉ thêm family vào tuyên bố hỗ trợ sau khi có nhãn được đối chiếu và kết quả PLAN_03–06 tương ứng. Chưa có baseline thực tế thì target accuracy giữ TBD, auto acceptance tắt.
