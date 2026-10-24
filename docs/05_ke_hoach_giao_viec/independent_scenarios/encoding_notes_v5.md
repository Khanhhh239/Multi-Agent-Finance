# Ghi chú mã hóa kịch bản độc lập v5 (gửi tác giả để biết, không để sửa kịch bản)

Mã hóa tại `agent2/world_v5_scenarios.py`, theo quyết định v6.2: không thêm bảng hay trường mới; vụ được cắt trong kỳ test. Văn xuôi gốc không bị thay đổi (SHA-256 `3723fb9d4820f1db2411acdd6c1b8bc79d8f4219447e2db7858e2625159a02cc`). Mọi dữ liệu là **dữ liệu tổng hợp**.

## 1. Quy ước chung của mã hóa

| Điều | Cách xử lý |
|---|---|
| Khoản tiền thu hoặc hoàn ngoài sổ (KB01, KB02, KB07, KB08) | Không có dòng giao dịch; tổn thất chỉ ghi ở bảng vụ |
| Vụ dài hơn kỳ test | Cắt trong kỳ. Giai đoạn sau kỳ không được sinh (ví dụ xóa nợ cuối cùng của KB10) |
| Nhãn tổn thất | Cộng số tiền các dòng bị gán nhãn, không phải tổn thất kinh tế thật |
| Trường lối tắt của bộ sinh | `applied_invoice_id` và `collector_id` không bao giờ được điền ở dòng gian lận mới (bài học R1 v1.3) |
| Hai tình huống hợp lệ mỗi kịch bản | Có hàm sinh riêng; tần suất 0,5 mỗi công ty và kỳ, 1 đến 2 lượt, bù đủ ít nhất 3 dòng ở kỳ test |
| Ca hợp lệ ghi nhãn | Mỗi dòng mang `hard_negative_type` tên riêng, `is_fraud = 0` |

## 2. Từng kịch bản: điều đã thể hiện và điều đã bỏ

| Mã | Đã thể hiện | Đã bỏ hoặc đổi vì lược đồ hiện tại |
|---|---|---|
| KB01 | Hóa đơn bán không có phiếu thu; che bằng xóa nợ không dự phòng (dễ), giảm giá do lỗi (vừa), chiết khấu thanh toán rồi xóa nợ có hồ sơ (khó) | Trạng thái giải thể của khách và cấn trừ giữa hai khách (không có trường); mã mặt hàng; người phụ trách khách lấy theo người lập hóa đơn |
| KB02 | Đặt cọc nhà cung cấp, rồi dòng điều chỉnh "mất cọc" hoặc "phí giảm số lượng" | Dòng đặt cọc vẫn có hóa đơn mặc định, vì lớp kế toán của bộ sinh yêu cầu hóa đơn cho thanh toán nhà cung cấp; số hợp đồng để nối cọc với đối trừ |
| KB03 | Tạm ứng công tác và quyết toán theo đơn giá khoán nhân số ngày; kê tăng thêm 1 đến 2 ngày, ngày Chủ nhật | Quãng đường, tỉnh của khách, bảng cự ly, ngày bắt đầu và kết thúc chuyến (chỉ còn số ngày trên dòng quyết toán) |
| KB04 | Dòng trợ cấp thôi việc của nhân viên đã nghỉ bị nâng số tiền (dễ và vừa); khó chỉ sai lý do nên số tiền gần như đúng công thức | Thời gian đóng bảo hiểm thất nghiệp, lý do chấm dứt, lịch sử sửa ngày vào (không có trường). Mức khó không thể quan sát từ số tiền, đúng ý tác giả |
| KB05 | Nhà cung cấp cá nhân mới và hoa hồng hằng tháng | Trường nối hoa hồng với khách được giới thiệu; thuế thu nhập cá nhân khấu trừ; vẫn có hóa đơn mặc định như KB02. Mức khó không có dấu vết quan hệ, đúng ý tác giả |
| KB06 | Hóa đơn bán thanh lý giá thấp cho khách, dòng ghi giảm tài sản và lỗ; khấu hao nâng mạnh trước đó (mức vừa) | **Không có sổ tài sản cố định**: giá trị còn lại là tham số ngẫu nhiên, không tra được; thanh lý theo lô; người mua mới tạo gần ngày bán (chỉ chọn khách có sẵn) |
| KB07 | Dòng đổ nhiên liệu theo lít (Chủ nhật, thêm 30 đến 50 phần trăm, hoặc gần bình thường kèm cặp điều chuyển kho) | Biển số xe, nhật trình km, phí đường bộ, lốp và sửa chữa (không có trường). Một xe được tính chung với nhiên liệu của công ty |
| KB08 | Thanh toán chậm với lãi chậm trả, hóa đơn thay thế, thanh toán sớm không chiết khấu kèm đơn giá tăng 2 đến 3 phần trăm | Kỳ hạn riêng theo nhà cung cấp (dùng kỳ hạn chung của công ty); liên kết hóa đơn thay thế với hóa đơn bị thay |
| KB09 | Chi phí kỳ trước ghi sổ 3 đến 10 ngày sau cuối kỳ với ngày hóa đơn kỳ trước; thiếu bút toán trích trước cuối kỳ | **Cuối kỳ là cuối quý (31/3, 30/6, 30/9, 31/12), không phải cuối năm**: kỳ test (7 đến 12/2025) kết thúc đúng cuối năm nên không có "tháng 1 năm sau" trong kỳ. Đây là đổi khác lớn nhất so với văn xuôi |
| KB10 | Khách có hạn nợ 30, 90 hoặc 120 ngày; hóa đơn lớn hơn thường lệ tiếp tục khi chưa thu; thu một phần muộn (dễ) | Xóa nợ cuối cùng ở tháng 18 đến 30 (vượt kỳ test); người duyệt tín dụng có quan hệ; hạn mức tiền; phụ lục gia hạn từng hóa đơn |

## 3. Điều tác giả nên biết khi đọc kết quả

- Các kịch bản được thể hiện bằng **dấu vết quan sát được trong sổ**, nên mức "khó" của KB04, KB05, KB09, KB10 gần như không phân biệt được với hoạt động bình thường bằng từng dòng. Nếu bộ phát hiện không bắt được chúng, đó là hệ quả mong đợi, không phải lỗi mã hóa.
- Không điều gì ở trên được chỉnh để dễ hay khó hơn cho bộ phát hiện. Không có số đo nào của bộ phát hiện được dùng khi mã hóa.
- Kiểm tra máy trên thế giới thử (chưa phải thế giới niêm phong): V1 đến V12 đạt; kiểm V13 không phát hiện trường nào tách được gian lận mới so với các thế giới phát triển.
