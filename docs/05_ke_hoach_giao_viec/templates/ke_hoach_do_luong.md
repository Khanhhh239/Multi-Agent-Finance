# Kế hoạch đo lường thí điểm

**Cần luật sư duyệt phạm vi thu thập. Chưa có số liệu thực tế.**

Mã thí điểm [ ]; số doanh nghiệp mục tiêu [ ]; thời gian [ ]; người chịu trách nhiệm đo [ ]; phiên bản mô hình và cấu hình [ ]. Chốt kế hoạch trước khi xem kết quả; lưu mọi sửa đổi và lý do.

| KPI | Tử số, mẫu số hoặc phép đo | Ngưỡng đăng ký |
|---|---|---|
| K1 | Số dòng cảnh báo mỗi công ty mỗi tuần; ghi thêm số vụ sau gộp | Không quá ngân sách đã chốt, mặc định ba dòng |
| K2 | Số vụ người rà soát đánh dấu đáng kiểm tra chia số vụ đã rà soát | Từ 15%; báo cả số chưa rà soát |
| K3 | Phát hiện có giá trị đã được chủ hoặc kế toán trưởng xác minh | Ít nhất một trên hai doanh nghiệp |
| K4 | Ca chèn có kiểm soát được cảnh báo chia tổng ca chèn đủ điều kiện đánh giá | Từ 50%; ghi cả mức dòng và mức vụ |
| K5 | Tổng phút rà soát cảnh báo mỗi công ty mỗi tuần | Không quá 30 phút |
| K6 | Doanh nghiệp chấp nhận mức giá cụ thể được đề xuất trước phỏng vấn | Ba trên năm; nếu cỡ mẫu khác phải chốt tiêu chí trước |
| K7 | Sự cố hoặc phát hiện pháp lý đã được người có thẩm quyền đánh giá | Không có phát hiện nghiêm trọng; chưa đánh giá không tính là đạt |
| K8 | AUC phân biệt dữ liệu thật và tổng hợp trên các trường không nhãn chung | Mục tiêu dưới 0,8; trên 0,9 cần xem lại khả năng chuyển giao |

Không coi dữ liệu chưa rà soát là hợp lệ. Không coi nghi vấn là gian lận đã xác nhận. Không dùng K2 thay cho độ chính xác gian lận thật. Không dùng số tiền tổn thất tổng hợp để suy ra tiền tiết kiệm thực tế.

## Dữ liệu ghi hằng tuần

`company_id`, `week`, `model_version`, `config_hash`, `alert_rows`, `alert_cases`, `reviewed_cases`, `worth_review_cases`, `valuable_findings`, `review_minutes`, `days_to_decision_median`, `injection_cases`, `injection_found_cases`, `incident_count`, `serious_incident_count`, `legal_review_complete`.

Lưu phản hồi mức vụ theo mẫu riêng; không đưa tên người vào báo cáo tổng hợp. Ghi số thiếu hoặc chưa đo dưới dạng trống, không dùng số không. Cách tính tuần và múi giờ: [ ]. Cách xác định hoàn tất một lần rà soát: [ ].

## Kiểm tra chất lượng và phân tích

Người đối chiếu số liệu [ ]; lịch đối chiếu [ ]. Chỉ tính tỷ lệ khi mẫu số lớn hơn không; mẫu số không có thì ghi chưa đo. Báo số tuyệt đối cùng tỷ lệ, theo từng doanh nghiệp và tổng hợp, tránh công ty có nhiều giao dịch lấn át các công ty còn lại.

Ca chèn giữ nhãn riêng ngoài dữ liệu đưa vào bộ phát hiện. K8 dùng tập kiểm tra riêng, tránh lặp thực thể hoặc bản ghi giữa huấn luyện và kiểm tra. Ghi rõ cỡ mẫu và hạn chế nếu số doanh nghiệp nhỏ.

Hệ số suy giảm: tỷ lệ phát hiện ca chèn thực tế chia tỷ lệ trên dữ liệu tổng hợp của cùng loại ca, chỉ tính nếu mẫu số khác không. Kinh tế cập nhật bằng giờ rà soát thực, mức giá đã hỏi và phát hiện đã xác minh; các đại lượng chưa đo vẫn giữ nhãn giả định.

Người ra quyết định đi tiếp hoặc dừng [ ]; ngày đánh giá tuần bốn [ ]; tuần mười hai [ ]. So với G7 và điều kiện dừng pha E, có giải thích bằng văn bản khi kết quả chưa đủ bằng chứng.
