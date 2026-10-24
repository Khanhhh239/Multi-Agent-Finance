# Yêu cầu tệp xuất từ phần mềm kế toán (gửi đơn vị kế toán)

**Cần luật sư duyệt trước khi gửi. Chưa có thỏa thuận dữ liệu nào được ký; không gửi hoặc nhận dữ liệu thật trước khi có thỏa thuận và xác nhận pháp lý.** Mục đích tệp này: để đơn vị kế toán biết cần xin loại dữ liệu nào, và cho chúng tôi biết phần mềm của họ xuất được đến đâu.

## 1. Chúng tôi cần biết trước (chưa cần gửi dữ liệu)

- Phần mềm kế toán đang dùng (tên, phiên bản) và đơn vị có xuất được sổ chi tiết giao dịch ra Excel hoặc CSV không.
- Số khách hàng dự kiến tham gia, quy mô nhân sự mỗi khách, ngành.
- Khoảng thời gian có dữ liệu (cần ít nhất 12 tháng).
- Chúng tôi **chưa xác nhận** phần mềm nào (kể cả MISA hay phần mềm khác) xuất được đủ các cột dưới đây; câu trả lời của đơn vị quyết định việc làm bộ chuyển đổi.

## 2. Dữ liệu tối thiểu: sổ giao dịch chi tiết

Mỗi dòng là một chứng từ hoặc bút toán, gồm:

| Thông tin | Ghi chú |
|---|---|
| Mã công ty (khách), mã giao dịch không trùng | mã nội bộ, không dùng tên |
| Ngày ghi sổ; ngày lập; ngày duyệt | cần cả ba, kèm giờ nếu phần mềm có; ghi rõ múi giờ |
| Loại nghiệp vụ | thanh toán nhà cung cấp, lương, chi tiền mặt, hóa đơn bán, thu tiền, tạm ứng, điều chỉnh... |
| Số tiền (đồng, số nguyên) | giữ cả số âm của điều chỉnh |
| Tài khoản nợ và có | |
| Người lập; người duyệt | **đổi tên thành mã** (xem mục 4) |
| Đối tượng: nhà cung cấp, khách hàng hoặc nhân viên | dưới dạng mã |
| Số hóa đơn, ngày hóa đơn, số tiền hóa đơn | |
| Số chứng từ kèm theo | số lượng, không cần tệp |
| Tài khoản ngân hàng nhận hoặc trả | đổi thành mã nhất quán |

Không được kèm bất kỳ nhãn hay kết luận về gian lận trong tệp.

## 3. Dữ liệu nên có (tăng độ chính xác, thiếu thì công cụ chạy ở chế độ giảm)

- Danh mục nhân viên: mã, vai trò, ngày vào, ngày nghỉ, mức lương, hạn mức duyệt (không cần số định danh cá nhân).
- Danh mục nhà cung cấp: mã, ngày đăng ký, ngày bắt đầu giao dịch, tài khoản, người đại diện (dưới dạng mã).
- Danh mục khách hàng: mã, hạn nợ.
- Lịch sử đổi tài khoản nhà cung cấp, bảng tạm ứng và quyết toán tạm ứng, bảng chấm công.
- Kỳ hạn công nợ và ngày trả lương của từng công ty.

## 4. Ẩn danh trước khi gửi

1. Đổi tên người, công ty, nhà cung cấp, khách hàng, địa chỉ, số điện thoại, mã số thuế, số tài khoản thành **mã**, cùng một mã cho cùng một đối tượng trong toàn bộ tệp.
2. **Bảng đối chiếu mã giữ lại ở đơn vị kế toán**, không gửi cho chúng tôi và không đưa vào Git.
3. Không gửi số định danh cá nhân, ảnh, tệp scan chứng từ.
4. Gửi qua kênh do hai bên thỏa thuận trong thỏa thuận dữ liệu, không qua email thường nếu thỏa thuận quy định khác.

## 5. Chúng tôi làm gì với tệp

Chạy thử ở chế độ chỉ xem, tối đa 3 câu hỏi đối chiếu mỗi khách mỗi tuần, kèm lý do và chứng từ cần xin. Xem [thỏa thuận dữ liệu](thoa_thuan_du_lieu.md) về mục đích, thời hạn lưu và quyền rút.
