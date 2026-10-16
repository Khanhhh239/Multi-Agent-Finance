# Bàn giao kịch bản niêm phong v5 cho người viết độc lập

Trạng thái: chưa có kịch bản độc lập đã được tiếp nhận và duyệt. Không coi mẫu dưới đây là kịch bản thử nghiệm.

Người viết cần là kiểm toán viên hoặc kế toán trưởng có kinh nghiệm, không thuộc nhóm phát triển phương pháp. Chỉ gửi tài liệu này và mẫu trống cho người viết; không gửi mã đặc trưng, kết quả hoặc bảng sai sót của mô hình. Đề nghị 8 đến 12 kịch bản dựa trên kinh nghiệm hoặc nguồn có thể dẫn lại, không sao chép thông tin định danh của người thật.

## Phiếu kịch bản

1. Mã, tên và ngày soạn:
2. Người viết, vai trò và xác nhận chưa xem mã hoặc kết quả:
3. Nguồn nghiệp vụ hoặc tình huống đã ẩn danh:
4. Ai có thể thực hiện, quyền hạn cần có và có thông đồng hay không:
5. Thủ đoạn, mục đích và chuỗi hành động theo thời gian:
6. Bảng và trường dữ liệu bị thay đổi hoặc thiếu; thời điểm thông tin thực sự có thể quan sát:
7. Số giao dịch, thời gian kéo dài, khoảng tiền và cách xác định tổn thất:
8. Biến thể dễ, vừa và khó; cách che giấu thực tế:
9. Hai tình huống hợp lệ có biểu hiện gần giống và bằng chứng để phân biệt:
10. Điều kiện làm kịch bản không thể sinh đúng hoặc cần hỏi lại:
11. Tiêu chí người viết dùng để duyệt 10 dòng mẫu:

## Quy trình tiếp nhận

Coding agent chỉ chuyển đúng mô tả thành mã sinh. Khi mơ hồ, hỏi lại người viết, không tự điều chỉnh để thuận lợi cho bộ phát hiện. Dùng dòng số ngẫu nhiên riêng; kiểm định dữ liệu, khóa ngoại, kế toán và thời điểm quan sát. Người viết xem 10 dòng mẫu mỗi kịch bản và ghi nhận duyệt hoặc yêu cầu sửa trước khi khóa.

Sau khi duyệt, sinh ba seed mới, lưu băm và kiểm định; chưa chạy bộ phát hiện. Chỉ chạy một lần khi có cấu hình phát triển mới đã đóng băng. Giữ nhật ký người viết, thời điểm tiếp nhận, mã phiên bản, băm dữ liệu và lần đánh giá. Không gắn nhãn độc lập nếu người viết đã biết phương pháp hoặc do chính coding agent tự viết.
