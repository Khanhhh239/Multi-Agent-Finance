# Phiếu chèn kiểm thử có kiểm soát

**Cần luật sư duyệt. Chỉ thực hiện trong môi trường thử được doanh nghiệp phê duyệt bằng văn bản, không tạo giao dịch thanh toán, hóa đơn hoặc khai thuế thật.**

Mã đợt [ ]; doanh nghiệp [ ]; môi trường [ ]; người phê duyệt [ ]; người thực hiện [ ]; người giữ nhãn mù [ ]; thời gian [ ].

| Ca tổng hợp | Bản ghi thử | Bằng chứng và đối chứng hợp lệ |
|---|---|---|
| Chi tiền mặt sát hạn mức tự duyệt | Các khoản chi thử gần hạn mức cấu hình, cùng người lập và duyệt | Chứng từ thiếu; đối chứng là các khoản có chứng từ và phê duyệt phù hợp |
| Thanh toán trùng hóa đơn | Hai bản ghi thử gắn cùng hóa đơn tổng hợp | Đối chứng là hai khoản có cùng số tiền nhưng hóa đơn khác, hợp lệ |
| Tạm ứng chưa quyết toán | Bản ghi tạm ứng và lịch sử thử vượt hạn tham chiếu | Đối chứng là tạm ứng có gia hạn được ghi nhận và bằng chứng hợp lệ |

Mỗi ca ghi `injection_id`, loại ca, mã giao dịch thử, công ty, thời điểm có thể quan sát, bằng chứng, mức độ, cấu hình dự kiến, ngày được phép đánh giá và cách hủy. Không điền mã hoặc nhãn chèn vào cột mà bộ phát hiện nhìn thấy.

Giữ ngân sách cảnh báo đã chốt; ca chèn phải cạnh tranh với dữ liệu nền. Không chấm riêng ca chèn để làm tăng tỷ lệ phát hiện. Ghi cả cảnh báo hợp lệ bị đẩy khỏi ngân sách. Người đánh giá xác nhận cảnh báo liên quan bằng nhật ký sau khi kết thúc cửa sổ mù.

Điều kiện dừng trước khi chèn: sai môi trường, có kết nối thanh toán thật, thiếu phê duyệt hoặc không có cách phục hồi. Nếu phát hiện tác động thực ngoài phạm vi, dừng và thông báo cho đầu mối phụ trách.

Bản sao lưu hoặc điểm khôi phục [ ]; thao tác hủy [ ]; người xác minh đã hủy [ ]; thời điểm [ ]; chứng cứ hoàn tất [ ]. Không xóa nhật ký đo đã được duyệt. Chữ ký phê duyệt trước đợt [ ]; xác nhận hoàn tất sau đợt [ ].
