# Nhu cầu người dùng và bản đồ nhiệm vụ T0–T13

> Bản đồ phạm vi thiết kế; cột trạng thái/phương pháp bên dưới phản ánh kế hoạch và ghi chú gốc. Dùng [project overview](../project-overview.md) để xác định trạng thái checkout và nghiên cứu nguồn mới nhất trong [mục lục](../README.md).

## 1. Nhu cầu người dùng

| Mã | Nhu cầu của chủ doanh nghiệp, kế toán kiêm nhiệm | Câu hỏi cụ thể |
| :---- | :---- | :---- |
| N1 | Biết tuần, ngày nào sẽ thiếu tiền và khả năng xảy ra | "Bốn đến mười ba tuần tới có tuần nào tiền mặt xuống dưới mức an toàn không, xác suất bao nhiêu?" |
| N2 | Biết khoản phải thu nào sẽ trễ để đòi trước | "Trong số hoá đơn đang mở, khoản nào nhiều khả năng trễ, và đòi khoản nào trước thì hiệu quả nhất?" |
| N3 | Biết rủi ro nợ xấu | "Khách nào có khả năng không trả, tổng giá trị đang rủi ro bao nhiêu?" |
| N4 | Thử kịch bản | "Nếu khách lớn nhất trả chậm hai tuần, hoặc tôi hoãn một khoản chi thì dòng tiền thế nào?" |
| N5 | Hiểu vì sao hệ thống cảnh báo | "Vì sao tuần đó bị đánh giá thiếu tiền?" |
| N6 | Không mất công nhập liệu, số liệu khớp sổ sách | "Số dư và công nợ hệ thống dùng có đúng với sổ của tôi không?" |
| N7 | Được báo khi hoàn cảnh thay đổi | "Khách hàng đang chậm hơn thường lệ, có phải có chuyện gì không?" |

Các hạn chế thực địa mà Phần 1 và Phần 3 đã nêu (ghi sổ theo lô cuối kỳ, thoả thuận miệng ngoài hệ thống, khách trả chậm khác với khách không trả, cú sốc phá vỡ quy luật quá khứ) là ràng buộc cho các nhiệm vụ dưới đây, không phải phần phụ.

---

## 2. Bản đồ nhiệm vụ

### 2.1. Tổng hợp nhiệm vụ

| Mã | Nhiệm vụ | Công dụng cho người dùng | Thuật toán chính | Dữ liệu huấn luyện | Dữ liệu đánh giá | Đáp ứng |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| T0 | Nền dữ liệu và lược đồ chuẩn  | Số liệu khớp sổ sách, không nhập tay (Kiếm API ERP(Misa, Fast), API ngân hàng) |  | Dữ liệu tổng hợp theo lược đồ hoá đơn điện tử | Kiểm thử lược đồ, tỷ lệ khớp sổ | N6 |
| T1 | Thời điểm thanh toán của từng hoá đơn \-\> đã làm  | Biết khoản nào về khi nào | \-LightGBM (contest ML hay sài) \-Ensemble (tunning ) \-Phân tích sống sót thời gian rời rạc | Tổng hợp hiệu chỉnh theo Việt Nam; bộ thật tương tự để thử phương pháp | Chia theo thời gian; điểm cắt kiểm duyệt nhân tạo | N1, N2 |
| T2 | Khả năng trả và vỡ nợ | Biết khoản nào có nguy cơ không thu được |  | SBA, Freddie Mac, Home Credit; tổng hợp | Chia theo thời gian; hiệu chỉnh xác suất | N3 |
| T3 | Trả một phần và tranh chấp (hợp đồng sẽ có,  1 hóa đơn tách ra hóa đơn con), tranh chấp nhiễu…  (advanced) | Số tiền về đúng chứ không chỉ ngày về | Hồi quy tỷ lệ trả; phân loại tranh chấp | Home Credit; tổng hợp | Chia theo thời gian | N1, N2 |
| T4 | Doanh thu mới chưa lập hoá đơn (mock hóa đơn start day \> cut-off day) | Dự báo thu từ hoá đơn sẽ phát sinh | LightGBM phân vị, so với chuỗi thời gian cổ điển. Time-series : Chronos (ko train đc trên internal data) | Online Retail II; M5; tổng hợp | Rolling-origin; chuẩn M5 | N1 |
| T5 | Chi cố định và lịch nghĩa vụ | Chi lương, thuế, bảo hiểm chính xác | Bộ máy quy tắc và lịch tất định | Văn bản pháp luật | Kiểm thử đơn vị theo điều khoản | N1 |
| T6 | Tổng hợp Monte Carlo và hiệu chỉnh khoảng \-\> đã làm  | Dải P10, P50, P90 và xác suất thiếu hụt đáng tin | Mô phỏng có sốc chung đuôi dày; hồi quy phân vị có hiệu chỉnh conformal | Đầu ra T1 đến T5; Berka; SEC | Độ phủ khoảng, điểm khoảng | N1, N4 |
| T7 | Phát hiện điểm gãy và chế độ khủng hoảng. (develop bot search web, news —\> update data) | Được báo khi hành vi khách đổi | CUSUM, Page-Hinkley, BOCPD | Tổng hợp có chèn điểm gãy; OxCGRT | Độ trễ phát hiện, báo động giả | N7 |
| T8 | Lời hứa trả và thoả thuận ngoài hệ thống | Đưa thông tin người đòi nợ vào dự báo | Cập nhật Beta-Binomial độ tin cậy lời hứa. Para \= số lần hứa làm/số lần hứa | Tổng hợp; nhật ký thử nghiệm sau này | Mô phỏng; A/B thật | N2 |
| T9 | Khớp sao kê với hoá đơn (optional) | Biết ngày trả thật khi kế toán ghi theo lô | Sinh ứng viên, chấm điểm, gán tối ưu | Cặp sao kê và sổ tổng hợp có nhiễu lô | Độ chính xác khớp, sai số ngày | N6 |
| T10 | Giải thích và khuyến nghị hành động | Hiểu vì sao và nên đòi khoản nào | Đóng góp đặc trưng; xếp hạng theo giảm xác suất thiếu hụt | Đầu ra T1, T2, T6 | Đánh giá người dùng; mô phỏng chính sách | N2, N5 |
| T11 | Đánh giá và kiểm thử ngược (optional) | Chứng minh chất lượng, chặn tự lừa | Giao thức rolling-origin, đối chứng | Toàn bộ | Toàn bộ | tất cả |
| T12 | Máy phát dữ liệu tổng hợp (optional) | Có dữ liệu để phát triển | Máy phát mô-đun, hiệu chỉnh theo Phần 5 | Số liệu Atradius, Anh, Úc | Kiểm định độ trung thực | nền |
| T13 | Thử nghiệm với đối tác thật (optional) | Kiểm chứng ngoài thực tế | A/B, giám sát trôi | Dữ liệu đối tác (đồng ý, ẩn danh) | Chỉ số thật | tất cả |
