# Nhu cầu người dùng

Nhu cầu dưới đây suy ra từ khoảng trống kiểm soát (tệp 00) và hành vi công việc hợp lý; **chưa phỏng vấn người dùng thật** **[G]**. Phỏng vấn là việc đầu tiên của giai đoạn thí điểm (tệp 08).

## 1. Chân dung

| Người dùng | Mô tả | Mục tiêu | Điều lo ngại |
|---|---|---|---|
| **Chủ doanh nghiệp** (người quyết định mua) | 30 đến 60 tuổi, quản lý 20 đến 100 nhân sự, không đọc được bút toán | Yên tâm tiền không thất thoát; thấy ngay chuyện gì cần hỏi | Nghi oan người có công; sản phẩm rườm rà; chi phí |
| **Kế toán trưởng** (người dùng hằng ngày) | Có chuyên môn, chịu trách nhiệm số liệu | Có công cụ chứng minh sổ sạch; bắt lỗi sớm | Bị coi là đối tượng bị giám sát; cảnh báo sai làm mất thời gian |
| **Đơn vị dịch vụ kế toán** (kênh bán) | Phục vụ nhiều khách nhỏ, phí thấp | Thêm dịch vụ giá trị gia tăng, giữ khách | Phải tự giải thích cảnh báo cho từng khách |
| **Kiểm toán nội bộ hoặc tư vấn thuê ngoài** | Rà soát định kỳ | Khoanh vùng mẫu nhanh | Cần dấu vết chứng cứ có thể xuất ra |

## 2. Việc cần làm (jobs to be done)

1. "Mỗi sáng thứ Hai, cho tôi biết có khoản nào tuần trước đáng hỏi lại, tối đa vài khoản."
2. "Nói rõ vì sao nó đáng hỏi, bằng ngôn ngữ kế toán, kèm chứng từ cần kiểm."
3. "Cho tôi ghi lại kết luận để lần sau hệ thống khỏi hỏi lại và để làm bằng chứng."
4. "Báo cho tôi ngay khi có dấu hiệu nghiêm trọng, đừng đợi đến cuối tháng."
5. "Giúp tôi chứng minh với ngân hàng hoặc kiểm toán rằng công ty có kiểm soát."

## 3. Câu chuyện người dùng (rút gọn)

| Mã | Câu chuyện | Tiêu chí chấp nhận (tóm tắt) |
|---|---|---|
| U1 | Là chủ doanh nghiệp, tôi nhận danh sách cảnh báo tuần, tối đa 3 mục | Không quá 3 cảnh báo mỗi công ty mỗi tuần (có thể cấu hình 1 đến 5) |
| U2 | Là kế toán trưởng, tôi xem lý do bằng tiếng Việt và danh sách giao dịch liên quan | Mỗi cảnh báo có ít nhất một lý do viết bằng ngôn ngữ nghiệp vụ và việc cần làm, kèm hạn xử lý |
| U3 | Là kế toán trưởng, tôi ghi "đã kiểm, hợp lệ" hoặc "nghi vấn" | Kết luận được lưu, ảnh hưởng thứ tự cảnh báo sau, có nhật ký |
| U4 | Là chủ, tôi cần hiểu mọi cảnh báo mà không cần biết kỹ thuật | Không hiện điểm số thô; hiện mức ưu tiên và lý do |
| U5 | Là đơn vị dịch vụ, tôi chạy cho nhiều khách và so sánh | Tách dữ liệu từng công ty; không lộ chéo |
| U6 | Là kiểm toán viên, tôi xuất hồ sơ vụ việc | Xuất CSV hoặc PDF gồm giao dịch, lý do, kết luận, thời điểm |
| U7 | Là doanh nghiệp mới, ngày đầu chưa có lịch sử | Chạy được ở chế độ khởi đầu lạnh (luật cộng so với đồng ngành) |

## 4. Rào cản chấp nhận và cách xử lý

| Rào cản | Cách xử lý trong thiết kế |
|---|---|
| Sợ bị coi là giám sát nhân viên | Chỉ gắn cờ giao dịch và đưa lý do; không xếp hạng người; thông báo theo Nghị định 13/2023/NĐ-CP trước khi bật |
| Cảnh báo sai làm mất lòng tin | Ngân sách cứng 3 cảnh báo mỗi tuần; đo tỷ lệ báo nhầm trên ca hợp lệ giống gian lận; vòng phản hồi |
| Không có dữ liệu sạch | Bộ nhận dữ liệu từ phần mềm kế toán phổ biến và hóa đơn điện tử; kiểm tra chất lượng đầu vào |
| Chủ không muốn cho người ngoài xem sổ | Triển khai chế độ chỉ đọc, ẩn danh khi nghiên cứu, thỏa thuận bằng văn bản |
| Giá | Giá thấp hơn một tháng lương kế toán; gói theo năm |

## 5. Hệ quả cho sản phẩm
Sản phẩm phải **giống một người bạn nhắc việc có chứng cứ** hơn là một hệ thống điều tra. Điều này dẫn tới ngân sách cảnh báo, ngôn ngữ trung tính ("đáng kiểm tra" chứ không phải "gian lận") và vòng phản hồi nhẹ.
