# Nguồn danh sách rủi ro thuế và kiểm soát tiền mặt

Thư mục chỉ có header/config mẫu; không chứa danh sách doanh nghiệp thật hoặc dữ liệu gán là của cơ quan thuế.

## Nhập danh sách

Map bản công bố của cơ quan thuế sang các cột trong `tax_risk_mapped.csv`. MST là chuỗi 10 hoặc 13 chữ số, giữ số 0 đầu; MST chi nhánh không tự ghép với MST công ty mẹ. Mỗi dòng gắn một `company_id` trong phạm vi dataset. `record_id` ổn định cho các phiên bản của cùng kết luận nguồn; `status` nhận `high_risk` hoặc `removed`. Khoảng ngày hiệu lực là `[effective_from, effective_to)`, để trống ngày cuối nếu chưa có kết thúc.

Giữ bản gốc PDF/CSV đã tải. Ví dụ lệnh sau dùng đường dẫn và mã tài liệu cần thay bằng dữ liệu thực:

```powershell
python -m sme_fraud.tax_risk --source mapped.csv --source-document tax_notice.pdf --source-url https://www.gdt.gov.vn/duong-dan-ban-cong-bo --document-id MA_VAN_BAN --observed-at 2026-10-17T10:00:00+07:00 --output staging/tax_risk_history.csv
```

Importer kiểm tra schema, MST, khoảng hiệu lực, thời điểm công bố/quan sát, URL HTTPS thuộc `.gov.vn` và lưu SHA-256 tài liệu gốc. Đường dẫn và hash cung cấp truy vết, chưa tự chứng thực nội dung PDF hoặc đối chiếu nội dung từng dòng mapping. Không tự truy cập cổng thuế, gửi dữ liệu doanh nghiệp hoặc ghi đè file đã tồn tại.

Pipeline nhận bảng tùy chọn `tax_risk_history.csv` theo [schema](../../sme_fraud/tax_risk_sources.schema.json). Khi tích hợp, đưa bảng vào bản dataset mới và khai báo checksum trong `manifest.json`; `feature_contract.input_fingerprint` phải gắn đúng bộ file nguồn mới. Việc chuẩn bị dataset phải đi qua bước dựng cache/manifest của pipeline tích hợp; chép thêm CSV vào một cache đã khóa sẽ bị từ chối. Unit/integration test có ví dụ dựng manifest/cache và nạp qua `load_inputs`.

Giao dịch có thể cung cấp `invoice_issuer_tax_code`; nếu không có, B4 dùng MST của phiên bản NCC đã quan sát. Chỉ nguồn đã công bố và được quan sát tại cutoff mới được đọc. Mỗi hit lưu mã văn bản, URL, hash và khoảng hiệu lực. Danh sách trống/thiếu không xác nhận NCC an toàn; chưa có cơ chế attestation coverage hoặc cập nhật nguồn định kỳ.

## Chính sách tiền mặt

P2 bật mặc định qua `cash_payment_policy=vn_vat_v1`. `cash_policy.json` là config có thể truyền vào `sme_fraud.run_rules --config ...` với đường dẫn dữ liệu/model tương thích và output mới.

Ngưỡng sàng lọc VAT gồm cả biên: 20.000.000 VND trước 01/07/2025; 5.000.000 VND từ ngày đó. Hạn mức nội bộ tùy chọn, ví dụ `"cash_limit_vnd_by_company": {"C001": 20000000}`, dùng điều kiện **vượt** hạn mức nội bộ và được kiểm tra đồng thời với ngưỡng VAT. Đặt `cash_payment_policy=disabled` khi cần tái hiện chính sách lịch sử chưa có P2.

P2 xét khoản chi mua thực bằng tiền mặt và cả trường hợp trả một phần hóa đơn có tổng giá trị đạt ngưỡng. Thiếu hóa đơn vẫn có cảnh báo trên số tiền chi, kèm trạng thái thiếu hồ sơ. Giao dịch qua hai chế độ thời gian được ghi cần rà điều khoản chuyển tiếp; ngoại tệ thiếu giá trị quy đổi chỉ tạo information gap 0 điểm. Chưa tổng hợp nhiều hóa đơn cùng NCC/ngày, chưa xử lý mọi hình thức bù trừ/ủy quyền hoặc tự quyết định quyền khấu trừ thuế.
