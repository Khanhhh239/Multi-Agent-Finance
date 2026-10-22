# Kế hoạch mã hóa R3 v5 (chỉ thực hiện nếu chốt chặn trước niêm phong đạt)

Soạn 2026-10-22 sau khi chốt văn xuôi `scenarios_v5.md` (SHA-256 `3723fb9d...02cc`, xem `handover_v5.md`). Đây là phân tích khả thi của người mã hóa, **chưa phải mã**. Nguyên tắc: mã hóa đúng ý văn xuôi, không chỉnh để dễ hay khó hơn cho bộ phát hiện; mọi quy ước thay cho dữ liệu thiếu phải ghi tại đây, gửi tác giả xác nhận, rồi chốt lại trước khi viết mã.

## 1. Lược đồ thật so với mô tả trong brief

Brief chỉ mô tả lược đồ rút gọn. Bảng giao dịch thật đã có thêm các trường tác giả hỏi ở mục 10 của nhiều phiếu: ngày lập hóa đơn (`invoice_issued_at`), ngày hiệu lực hoặc căn cứ ghi nhận (`effective_date`), kỳ lương (`payroll_period`), chứng từ liên kết (`linked_document_id`), loại đối tượng (`counterparty_type`), dự phòng khi xóa nợ (`writeoff_provision_vnd`), đơn giá và số lượng. Bảng khách hàng có hạn nợ riêng (`credit_terms_days`); bảng nhân viên có ngày nghỉ (`terminated_at`), điện thoại, địa chỉ; bảng nhà cung cấp có điện thoại, địa chỉ, người đại diện.

## 2. Từng kịch bản

| Mã | Ánh xạ vào loại nghiệp vụ có sẵn | Thiếu so với văn xuôi | Quy ước đề xuất (cần tác giả xác nhận) |
|---|---|---|---|
| KB01 | Hóa đơn bán, thu tiền bị thiếu, điều chỉnh giảm giá và chiết khấu, xóa nợ | Người phụ trách khách không có trong bảng khách hàng (bộ sinh có ở dạng nội bộ); trạng thái giải thể của khách; mã mặt hàng | Người lập hóa đơn bán là người phụ trách; bỏ biến thể cần mã mặt hàng hoặc dùng `business_purpose` |
| KB02 | Thanh toán nhà cung cấp ứng trước, thiếu dòng tiền hoàn, điều chỉnh Nợ 811 | Số hợp đồng hoặc đơn đặt hàng để nối cọc với đối trừ | Nối qua `linked_document_id` cho mọi khoản cọc, cả hợp lệ lẫn gian lận |
| KB03 | Tạm ứng, quyết toán tạm ứng theo đơn giá khoán và số lượng | Ngày bắt đầu và kết thúc chuyến; tỉnh của khách; bảng cự ly | Ngày chuyến đặt ở `effective_date` của dòng quyết toán; bỏ đối chiếu tuyến |
| KB04 | Dòng lương trợ cấp thôi việc, đơn giá là lương tính trợ cấp, số lượng là số tháng | Thời gian đóng bảo hiểm thất nghiệp; lý do chấm dứt; lịch sử sửa ngày vào | Giả định đóng từ ngày vào cộng 2 tháng; biến thể sửa ngày vào chỉ còn dấu vết trên số tháng |
| KB05 | Nhà cung cấp cá nhân (cộng tác viên), thanh toán hoa hồng có khấu trừ thuế | Trường nối dòng hoa hồng với khách được giới thiệu | Ghi khách vào `customer_id` của dòng hoa hồng, cho cả hoa hồng hợp lệ |
| KB06 | Khấu hao, điều chỉnh ghi giảm tài sản, hóa đơn bán thanh lý, mua tài sản thay thế | Không có sổ tài sản cố định | Cần bảng tài sản mới hoặc mã tài sản trên dòng; đây là mở rộng bộ sinh lớn nhất |
| KB07 | Mua hàng nhiên liệu theo lít, sửa chữa, lốp; điều chỉnh điều chuyển kho | Biển số xe, lượt đổ nhiên liệu, nhật trình | Một dòng nhiên liệu mỗi lượt đổ cho mọi xe; mã xe ở `project_id` |
| KB08 | Thanh toán nhà cung cấp lệch thứ tự tuổi nợ, điều chỉnh lãi chậm trả, hóa đơn thay thế | Kỳ hạn riêng theo nhà cung cấp; liên kết hóa đơn thay thế | Dùng `vendor_terms_days` của công ty; nối hóa đơn thay thế qua `linked_document_id` |
| KB09 | Mua hàng ghi sổ tháng 1 có ngày lập hóa đơn tháng 12; thiếu trích trước tháng 12 | Quy ước trích lương của bộ sinh nền | Dùng `invoice_issued_at` và `effective_date`; cần kiểm bộ sinh nền có bút toán trích trước hay không |
| KB10 | Hóa đơn bán tiếp tục khi quá hạn, thu nhỏ giọt, xóa nợ | Quan hệ người duyệt với đại lý; hạn mức tiền; lịch sử hạn nợ | Hạn nợ ở `credit_terms_days`; không thêm dấu vết quan hệ (mức khó giữ nguyên không dấu vết) |

## 3. Vấn đề chung phải quyết trước khi mã hóa

1. **Độ dài vụ so với cửa sổ thời gian.** Lịch thế giới là train năm 2024, validation nửa đầu 2025, test nửa cuối 2025; bộ sinh hiện gán mỗi vụ vào một kỳ và giới hạn độ dài trong kỳ đó. Nhiều kịch bản kéo dài 10 đến 30 tháng (KB01, KB02, KB03, KB10), nên trong kỳ test chỉ thể hiện được một phần. Hai cách: cắt vụ trong kỳ (giữ thiết kế hiện tại, phải ghi rõ là mất giai đoạn sau, ví dụ xóa nợ của KB10), hoặc cho vụ bắt đầu trước kỳ test và chỉ chấm dòng trong kỳ test. Cách thứ hai đổi thiết kế chấm nên phải hỏi chủ dự án; không tự chọn.
2. **Trường mới phải có mặt cả ở dòng hợp lệ.** Mọi trường hay bảng thêm cho một kịch bản phải được điền ở các dòng hợp lệ cùng loại với tần suất tự nhiên, nếu không sẽ tạo lối tắt kiểu L11. Thử khô 5199 chạy V13 và dừng nếu có tách biệt mới.
3. **Phần ngoài sổ.** Tiền thu ngoài sổ (KB01, KB02, KB07, KB08) không có dòng giao dịch; tổn thất chỉ ghi ở bảng vụ, không đưa vào bảng giao dịch.
4. **Hai tình huống hợp lệ mỗi kịch bản** thành 20 hàm `decoy_<tên>`, tần suất theo mục Làm rõ thực thi R3 của đăng ký.

## 4. Câu hỏi gửi tác giả (chỉ khi R3 được thực hiện)

Gửi một lần, ghi nguyên văn hỏi và đáp vào `handover_v5.md`, chốt lại băm trước khi mã hóa:
- Xác nhận hoặc sửa từng quy ước ở cột cuối bảng mục 2.
- KB06 và KB07: chấp nhận thêm bảng tài sản cố định và lượt nhiên liệu theo xe, hay chỉ giữ các biến thể thể hiện được bằng lược đồ hiện có.
- Với kịch bản dài hơn 6 tháng: giai đoạn nào là cốt lõi cần có trong kỳ test.

Không hỏi tác giả bất cứ điều gì về bộ phát hiện hay khả năng bị bắt.
