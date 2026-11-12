# Đồng bộ nghiệp vụ Agent 3, phiên bản 2

## Phạm vi và cách sử dụng

Hồ sơ vẫn do portal quản lý. Thay đổi này không sửa hồ sơ Quàng Sang, hóa đơn Minh Phát, cờ mô phỏng, model hoặc kho luật đang dùng. Khi triển khai, dừng và khởi động lại portal cùng Agent 3, tải lại trình duyệt rồi chạy phân tích. Báo cáo phiên bản cũ được giữ nhưng sẽ báo cần phân tích lại. Không chỉ tải lại tab khi backend còn chạy mã cũ.

- GTGT: tách không kê khai, có nguy cơ, chờ xem xét và chưa phát hiện cảnh báo. Hai kịch bản chênh lệch chưa gồm số chuyển kỳ trước/điều chỉnh; không phải tờ khai hoặc chứng nhận khấu trừ.
- DIRECT: chỉ trình bày số liệu hóa đơn, không đưa ra kết quả tính theo phương pháp khấu trừ.
- Khoản thu R14: mở ngăn chi tiết, ghi bằng chứng và người duyệt; xác nhận không phải doanh thu hoặc chọn hóa đơn bán ra liên quan. Điều này không tự thay số thuế.
- Mẫu sao kê: Quản trị → Cấu hình doanh nghiệp → Nhận dạng cột từ sao kê đã nạp. Cần phiên quản trị khi lưu.
- Bảng kê: Tổng quan → Ngân hàng → Chọn bảng kê cổng thuế đang dùng, hoặc `#/du-lieu`. Nạp CSV/XLSX mới giữ các bản trước và chuyển bản hoạt động sau khi kiểm tra toàn bộ bảng.

Các lỗi chữ ký, tiền bằng chữ và hồ sơ không khớp trên bộ demo vẫn được giữ làm cảnh báo. Tên có chữ “MÔ PHỎNG” không đủ để cấp danh tính mô phỏng tin cậy; backend chỉ công nhận danh tính được cấu hình qua portal.

## Hợp đồng API

- Báo cáo: `meta.schema_version=2`, `report_revision`, `analysis_signature`, `filing_period`, `vat_method`; cảnh báo có `finding_id` và `txn_ids`. Lịch có `obligation`/`period_key`.
- `GET .../vat-summary`: các khoản tiền là chuỗi Decimal. `calculation_status=UNSUPPORTED_DIRECT` có các giá trị tính khấu trừ/chênh lệch là `null`. Kỳ thiếu thuế trên chứng từ có trạng thái `INCOMPLETE`. `scenario_without_review` và `scenario_with_review` là hai kịch bản; `net_min`/`net_max` là biên số học. `input_safe`/`net` là trường tương thích, không dùng trong frontend mới.
- `GET .../decisions`: trả lịch sử sự kiện và ETag. POST quyết định đơn, bulk và xác nhận đề xuất ngân hàng cần `If-Match`, `request_id`, `report_revision`, bằng chứng và người duyệt. Thiếu điều kiện: 428; phiên bản quyết định cũ: 412; báo cáo cũ hoặc mã yêu cầu dùng lại với nội dung khác: 409. Retry cùng mã và nội dung trả lại kết quả, không ghi sự kiện trùng.
- `CONFIRMED_OK` yêu cầu `finding_id`/`finding_ids`; không tự duyệt mọi cảnh báo của hóa đơn. `NOT_CLAIMED` và `PAYMENT_EVIDENCE_ATTACHED` có phạm vi khác nhau. Xác nhận ghép ngân hàng lưu cả mã giao dịch và kiểm tra quyền sở hữu/số tiền/giao dịch đã dùng.
- R14: `CONFIRMED_NON_REVENUE` cần loại `LOAN`, `INTERNAL_TRANSFER`, `CAPITAL`, `REFUND` hoặc `OTHER`. `SALES_EVIDENCE_ATTACHED` cần hóa đơn bán ra tồn tại. Cả hai cần bằng chứng và người duyệt.
- Nếu đã lưu quyết định nhưng xuất báo cáo lỗi, HTTP 200 có `saved=true`, `report_pending=true`; frontend báo đã lưu và yêu cầu chạy lại. Không trình bày đây là thất bại lưu quyết định.
- `POST .../bank/formats` cần quyền quản trị và `If-Match` của pack. Mẫu tự nhận dạng bởi backend được kiểm tra và ghi lịch sử như trước.
- `POST .../inbox/preview`: kiểm tra trên thư mục tạm, không ghi vào workspace. Portal phân biệt kiểm tra cấu trúc/dòng dữ liệu với kết luận hợp lệ thuế.
- `GET .../portal/lists`, `PUT .../portal/active-list`: liệt kê/chọn bản bảng kê. Giữ kiểm tra revision hồ sơ và quyền nhập liệu hiện có.

## Lưu trữ, chuyển đổi và khôi phục

Lần ghi quyết định đầu tiên tạo `decisions_v2.json` bằng thay thế file nguyên tử, chứa sự kiện cũ và mới. `decisions.json` cũ được giữ nguyên. Dữ liệu cũ chỉ chứa những quyết định còn tồn tại, không thể khôi phục lịch sử đã bị ghi đè trước đây. Quyết định mới lưu fingerprint chứng từ; chứng từ thay đổi thì quyết định cũ còn trong lịch sử nhưng không được áp dụng cho chứng từ mới.

Kho mới là nguồn duy nhất sau chuyển đổi. Không sửa tay hoặc đồng bộ ngược hai file. Sao lưu toàn bộ workspace trước khi vận hành bản mới; bản sao phải có hóa đơn, sao kê, pack, cả hai kho quyết định và manifest bảng kê. Không chạy bản phần mềm cũ để ghi quyết định sau khi đã chuyển đổi. Khi khôi phục, dừng Agent 3, khôi phục bộ sao lưu đồng nhất và đối chiếu các sự kiện phát sinh sau bản sao; không chỉ chép lại file quyết định cũ.

`portal/active.json` giữ tên và SHA-256 của bảng kê hoạt động. Workspace cũ có một bảng kê được đọc tương thích. Nhiều bảng khác nội dung mà chưa có manifest phải được chọn rõ ràng; không ưu tiên CSV hay XLSX ngầm. Nguồn cũ không bị xóa.

Chữ ký phân tích dùng các đầu vào hiệu lực, ngày phân tích, nội dung ruleset/danh mục và phiên bản thuật toán. Bản xuất, file tạm, bản sao lưu và sự kiện đã bị thay thế không tự làm số liệu cũ. Luật vẫn ở trạng thái nháp; chưa thay mức thuế hoặc căn cứ pháp lý.

## Kiểm thử và build

Tại `agent3/agent3_tax_compliance`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/assistant tests/lawbase tests/xml_v1 -q
cd webui
npm run build
node scripts/consistency-check.mjs
node scripts/ui-check.mjs
```

Tại thư mục repository:

```powershell
.\agent1\.venv\Scripts\python.exe -m unittest portal.test_bank_intake portal.test_bank_profile_contract -v
```

Các kiểm thử dùng dữ liệu mô phỏng/thư mục tạm, không đo độ chính xác trên hóa đơn thực tế. Kiểm tra giao diện dùng API giả lập; ảnh được lưu vào `webui/.qa/` khi trình duyệt hoạt động. Nếu CDP timeout ở `Page.enable`, không có ảnh mới hay bằng chứng đạt responsive/bàn phím; phải hoàn tất bước này trước nghiệm thu trực quan. Các tiêu chí taste dành riêng cho landing page không áp dụng cho ứng dụng nghiệp vụ.

## Kết quả kiểm tra ngày 12/11/2026

- Assistant, kho luật và XML: 177 ca đạt trong lượt tổng hợp; ca tích hợp portal → preview thực được bổ sung sau đó và chạy riêng đạt. Có 3 cảnh báo sẵn có về FastAPI startup/pytest marker, không phải lỗi kiểm thử.
- Tích hợp sao kê portal: 8 ca đạt bằng môi trường Agent 1 có đủ dependency.
- Build Vite và kiểm tra cú pháp JavaScript: đạt.
- `node scripts/consistency-check.mjs`: đạt phép hiển thị tiền chính xác, sắp xếp Decimal, precondition quyết định, retry cùng request ID, đổi doanh nghiệp, hủy phản hồi cũ; tài nguyên build/font local/mã băm/thứ tự CSS đạt.
- `node scripts/ui-check.mjs`: kiểm tra tài nguyên HTTP đạt, nhưng trình duyệt bị timeout tại `Page.enable`. Chưa có ảnh mới và chưa đạt nghiệm thu trực quan ở các kích thước, sáng/tối, zoom hoặc bàn phím. Không dùng ảnh cũ làm bằng chứng cho bản này.
- Chưa restart backend đang sử dụng, chưa chạy phân tích hay ghi quyết định trên doanh nghiệp hiện tại. Commit/push mã nguồn không tự cập nhật tiến trình backend đang chạy.
