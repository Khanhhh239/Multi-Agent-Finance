# Hướng dẫn gán nhãn — annotation v1

Mục tiêu: ground truth mô tả thứ tài liệu thể hiện, độc lập prediction và luật thuế. Mỗi document giữ mọi trang cùng ID/split; nhiều chứng từ trong file cần nhãn boundaries riêng trước field extraction.

## 1. Bốn trạng thái nhãn

| Status | Ý nghĩa | Giá trị/evidence | Tính accuracy |
|---|---|---|---|
| OBSERVED | Người gán đọc được giá trị và vai trò | raw_text + normalized_value + evidence bắt buộc | Có, nếu semantic field/annotation scope được xác nhận |
| ABSENT_CONFIRMED | Đã xem đủ tài liệu và xác nhận field không hiện diện | raw/normalized null; evidence vùng/tài liệu + reason | Đo phát hiện absence riêng; không tính value exact match |
| UNREADABLE | Có vùng/field nhưng không thể đọc chắc | raw/normalized null; bbox và reason | Báo coverage/readability riêng; không coi đoán đúng là ground truth |
| NOT_ANNOTATED | Chưa được gán hoặc không thuộc phạm vi nhãn | raw/normalized null; reason | Loại khỏi value accuracy; không được coi là nguồn thiếu |

Đây là trạng thái **annotation**, không phải enum FieldObject runtime. Không chuyển NOT_ANNOTATED thành MISSING trong CFR. Không coi ABSENT_CONFIRMED của receipt là vi phạm nghĩa vụ hóa đơn thuế.

## 2. Quy tắc từng field

- Seller/buyer: đọc role label và vùng bố cục; MST đối tác nào gắn đúng bên đó. Tài liệu có MST 10/13 số giữ nguyên, không cắt hoặc sửa checksum.
- Số hóa đơn: giữ leading zero, dấu phân cách và series riêng; không dùng số giao dịch/PO làm invoice number. Không rõ loại số thì đưa tranh chấp vào review.
- Ngày: raw giữ cách viết; normalized ISO chỉ khi xác định được lịch/locale. Không đổi transaction timestamp thành invoice issue date. Trường mơ hồ chưa phân xử không có normalized value chính thức.
- Tiền: normalized string Decimal, không float. Dấu phân cách phải phù hợp ngữ cảnh; có currency nhãn riêng. Tổng thanh toán khác subtotal, tendered và change.
- VAT: raw nhãn rate/treatment, normalized TAXABLE_RATE/KCT/KKKNT; rate 0% là "0", rate 8% là "0.08". KCT/KKKNT không có numeric rate; nhãn rate không được biến thành legal vat_category.
- Bảng hàng: row có immutable annotation item ID; description/quantity/unit price/net/VAT từng field có evidence. Row continuation nhiều trang giữ ID nếu xác nhận cùng row. Không bịa hàng thiếu chỉ để khớp totals.
- Derived fields: direction/counterparty/totals derived cần bảng input/master/version riêng; không gán bằng suy đoán từ filename hoặc tenant.

## 3. Evidence geometry

`page_index` bắt đầu từ 0. Bbox `[x0,y0,x1,y1]` chuẩn hóa [0,1], origin góc trên trái, theo trang gốc sau xử lý orientation hiển thị đã ghi rõ. PDF fixture dùng page 595×842 points, ảnh dùng cùng frame chuẩn hóa. Giữ transform khi crop/deskew/rotate; không dùng bbox render để giả bbox gốc.

Field tách nhiều dòng có nhiều evidence. OBSERVED trỏ vùng **giá trị**; role/context label có thể bổ sung evidence riêng ở schema sau. UNREADABLE trỏ vùng không đọc được. ABSENT_CONFIRMED cần reason và bằng chứng đã xem đủ pages; không phải chỉ OCR không tìm thấy token.

## 4. Quy trình hai lượt

1. Annotator A đọc raw, gán status/value/role/evidence và ghi version. Không xem prediction làm đáp án.
2. Annotator B đọc lại độc lập ít nhất 5 mẫu ban đầu, toàn bộ critical MST/date/money/roles của bộ nghiệm thu trước đóng băng; ghi disagreement theo field.
3. Phân xử dựa raw, lưu A/B/final và lý do; không xóa dấu vết bất đồng.
4. Sau khi thống nhất hướng dẫn, đóng băng annotation version/hash. Nếu đổi quy tắc thì version mới, giữ labels cũ để replay.

Hiện có [5 ví dụ tổng hợp](annotation_examples.json) được generator và parser đối chiếu text/bbox. **Chưa có annotator B**, không coi đó là independent human review. Mẫu tranh chấp được chuẩn bị ở [review_disagreements.csv](review_disagreements.csv).

## 5. Lưu dữ liệu

Nhãn thật có thể chứa tên/MST/account, lưu local restricted metadata ngoài git. Báo cáo chung chỉ có counts/hashes và opaque IDs. Fixture CI dùng dữ liệu do project sinh có dòng cảnh báo giả lập; không copy receipt thật vào CI. Dataset public vẫn phải tuân thủ điều kiện nguồn, không mặc định được tái phân phối vì đã tải được.
