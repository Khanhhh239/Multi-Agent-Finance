# Bag v3: lựa chọn theo doanh nghiệp — cập nhật 06/11/2026

## Phạm vi
T1, T2, T4/T6 và ưu tiên thu hồi T10. T13 không nằm trong đợt này.
Không thay expand, HazardLR._prep hoặc run_real_v2.py của pipeline nghiên cứu.

## Khung chọn phương pháp
- T1: quy tắc/lịch sử/survival, logistic, spline, RF, ExtraTrees, HistGBM, LightGBM, XGBoost; neural MLP 32–16, 64–32, 64–32–16. Thêm cấu hình regularization logistic, độ sâu forest, regularization HistGBM.
- Các cấu hình là một lưới tuning hữu hạn, không phải tìm kiếm vô hạn. MLP cần tối thiểu 1.000 hóa đơn học, 200 tất toán, 20 khách. Thiếu dữ liệu/phụ thuộc được ghi unavailable; không ghi là đã validation.
- Chọn ba ứng viên tốt nhất trên validation để tạo thêm ứng viên trung bình phân phối; xét từng ứng viên và blend với lịch sử khách ở trọng số 0/.25/.5/.75/1.
- Chọn theo Brier 28 ngày ở cửa sổ validation; audit ở cửa sổ sau. Audit thất bại thì về baseline. Sau đó mới refit. Chưa chuyển cổng này thành mục tiêu số dư 13 tuần.
- Chuỗi tiền: seasonal, boosting, GRU 12, GRU 24, LSTM 12 và Chronos local nếu có. Neural recurrent dùng Gaussian likelihood, không gọi là triển khai DeepAR chuẩn. Chọn bằng MAE trên ba cửa sổ 13 tuần; thêm ensemble trung bình ba ứng viên tốt nhất; audit 13 tuần riêng; thất bại về seasonal.
- Tự xét nhánh học mở rộng khi có 156 tuần sao kê liên tục đã đối soát. Job lớn yêu cầu RAM trống 3 GiB, worker không giới hạn tổng thời gian, có giới hạn RAM. Không tự tải trọng số Chronos. Ngưỡng đủ lịch sử không phải bằng chứng mô hình sẽ thắng.

## T2 — nhãn và giới hạn
Nhãn là đã ghi nhận xóa nợ trong 365 ngày kể từ phát hành. Không dùng nhãn “chưa trả” để thay nhãn xóa nợ, không gọi đây là xác suất không bao giờ trả.
Chỉ lấy cohort đủ 365 ngày, có ngày biết dữ liệu. Chia theo ngày phát hành, chừa khoảng 365 ngày để nhãn train đã quan sát trước validation và validation đã quan sát trước audit.
So sánh prior, logistic hai cấu hình, boosting và MLP nếu đủ mẫu/lớp. Chọn Brier trên validation; audit không kém prior mới giữ ứng viên; refit sau audit.
Nếu thiếu nhãn hoặc cửa sổ đủ dài: status insufficient_labels, xác suất trả về null, không bịa số. Đầu ra write_off_probability_365d_at_issue là rủi ro lúc phát hành; không phải xác suất có điều kiện theo tuổi hiện tại, chưa dùng để trừ dòng thu T1 lần nữa. Chưa học LGD nên chưa gọi là tổn thất kỳ vọng đã hiệu chỉnh.
Doanh nghiệp cần cung cấp đầy đủ lịch sử xóa nợ; không có sự kiện trong dữ liệu thiếu không chứng minh không phát sinh nợ xấu.

## Ưu tiên thu hồi
Mục tiêu: trong ngân sách 10 khoản, bao phủ giá trị dư nợ vẫn còn mở sau 28 ngày.
Metric chọn = tổng dư nợ tương lai của top 10 / tổng dư nợ tương lai của top 10 lý tưởng (normalized value@10). Báo thêm amount capture (tỷ lệ trên toàn danh mục) và precision@10.
Ba chính sách: số tiền còn mở; xác suất chưa trả; số tiền nhân xác suất chưa trả. Xác suất dùng baseline lịch sử khách được fit tại từng gốc để giữ cùng cách tính giữa backtest và vận hành.
Hai gốc T−84, T−56 để chọn; T−28 để audit (nhãn đến T). Tính số dư sau thanh toán từng phần bằng các snapshot thực tế; không dùng toàn bộ tiền hóa đơn để thay số dư. Audit kém cách xếp theo tiền thì quay về cách đó. Thiếu 20 hóa đơn mở ở mỗi gốc thì dùng baseline, ghi thiếu lịch sử.
Đây là đánh giá phân bổ sự chú ý vào công nợ rủi ro, không phải causal uplift hoặc tiền tăng thu do liên hệ. Luồng thực tế vẫn loại khoản được hoãn/liên hệ gần đây. Cần kiểm định thêm khi áp ràng buộc ngân sách theo khách thay vì hóa đơn.

## Web và bảo mật phương pháp
Web không trả đối tượng model, tên model được chọn, thành viên ensemble hay bảng tuning. Chỉ hiển thị kết quả nghiệp vụ, trạng thái đủ dữ liệu, chất lượng và phiên bản. Chi tiết nằm trong artifact nội bộ đã mã hóa. Đây là ranh giới API; việc giao toàn bộ mã nguồn cho khách không phải biện pháp giữ bí mật mã nguồn.

## Bằng chứng
outputs/business/selection_v3_tests.xml: kiểm thử cơ chế, gồm fit/predict GRU/LSTM, ensemble, metric giá trị, nhãn xóa nợ và chống rò rỉ ngày ghi nhận.
Kiểm thử synthetic chỉ chứng minh cơ chế chạy, không tuyên bố model tốt nhất trên dữ liệu thật. Các kết quả Customer Invoices/Chronos cũ không tự động trở thành kết quả của v3.

Kết quả thực thi 06/11/2026: 411 tests passed (108,64 giây). Lượt smoke toàn bag trên 1.400 hóa đơn synthetic bị hoãn trước khi train vì RAM trống 1,46 GiB <3 GiB; không có kết quả chất lượng cho lượt này.
