# Phiếu duyệt phép so sánh ML — chưa phê duyệt

Ngày chuẩn bị: 19/10/2026. Trạng thái: **chờ dữ liệu thật và chủ nghiệp vụ duyệt thiết kế**. Đây là kế hoạch, không phải cấu hình được production sử dụng và chưa phải kết quả pilot.

Mục tiêu đầu tiên là kiểm tra Isolation Forest có giúp sắp thứ tự các hồ sơ giao dịch hiện có để kế toán xử lý hiệu quả hơn không. Hồ sơ nguồn/lô/mẫu ngoài phạm vi ban đầu giữ baseline và được báo độ phủ riêng. Phạm vi ban đầu không mở thêm hồ sơ chỉ do ML, không tự kết luận gian lận hoặc thay đổi hàng đợi vận hành.

Hai phương án phải dùng cùng doanh nghiệp, thời điểm chốt, phạm vi hồ sơ và ngân sách phút/lượt. Baseline giữ rules/graph/A5 hiện hành. Phương án ML giữ các suất bắt buộc của baseline; trong các suất còn lại, chỉ đổi thứ tự theo IF trong cùng mức ưu tiên. Cách tổng hợp điểm giao dịch vào hồ sơ và cách xử lý hòa điểm phải được khóa trước khi xem kết quả.

| Người nghiệp vụ cần chốt | Giá trị hiện tại |
|---|---|
| SME, quy trình và chủ nguồn | Chưa có |
| Quyền dùng nguồn, coverage và mapping | Chưa có |
| Khoảng train, calibration và đánh giá tương lai | Chưa có |
| Ngân sách chính: 5 hoặc 10 hồ sơ/công ty/ngày; số phút | Chưa chọn; không chọn lại theo kết quả |
| Chính sách suất bắt buộc và chuyển tồn sang ngày sau | Chưa duyệt cho pilot |
| Số ngày, số mẫu review và mẫu tham chiếu ngẫu nhiên | Chưa duyệt |
| Mức lợi ích tối thiểu, chi phí thời gian chấp nhận được | Chưa duyệt |
| Mức thiếu chứng từ cho phép và cách xử lý chưa kết luận | Chưa duyệt |
| Người rà độc lập, người phân xử | Chưa chỉ định |
| Cách báo độ bất định theo ngày/doanh nghiệp/vụ liên quan | Chưa duyệt |
| Người ký, lý do, thời điểm và phiên bản được duyệt | Chưa có |

Sau khi có nguồn thật và hợp đồng feature/model hợp lệ: khóa model, nguồn, algorithm, phiên bản rules/A5, tham số, scope và prediction theo từng cutoff. Phát phiếu nguồn có ID ẩn danh và ngữ cảnh thời gian cho người rà; không đưa điểm ML, thứ hạng hoặc nhánh chọn vào phiếu. Rà hợp của hai tập chọn, cộng mẫu tham chiếu ngẫu nhiên đã định trước để không chỉ học từ hồ sơ được cảnh báo. Báo riêng chi phí review tham chiếu và phân xử.

Không gọi “cần kiểm tra”, “vi phạm điều kiện”, “xác nhận nghi vấn” hoặc “thiếu thông tin” là nhãn gian lận. Không dùng nhận xét của trợ lý hoặc kỳ vọng fixture làm kết luận thật. Khi chưa có kết luận độc lập, chỉ báo độ phủ, khác biệt thứ tự và mức giao nhau giữa hai phương án; không báo ML cải thiện precision/recall gian lận.

Điểm IF của hồ sơ thiếu dữ kiện không được điền 0; giữ thứ tự baseline và ghi trạng thái chưa chấm. Tổng hợp bằng max có thể ưu ái hồ sơ nhiều dòng, nên phải báo phân bố kích thước hồ sơ. Những hồ sơ liên quan cùng vụ và dữ liệu lặp theo ngày có tương quan; không coi chúng là các mẫu độc lập khi báo độ bất định.

Theo dõi trạng thái xử lý riêng cho từng nhánh trong sổ nghiên cứu, không ghi vào phản hồi production. Không cộng hồ sơ đã xử lý với scope không đổi thành lợi ích mới ở ngày sau. Hồ sơ chờ thông tin vẫn phải được ghi riêng; scope thay đổi cần rà lại, không tự chuyển kết luận cũ sang. Cách chuyển tồn phải được chốt trước để phép so sánh thứ tự không bị méo bởi đếm lặp.

Chỉ đưa ML vào vận hành nếu đạt các tiêu chí đã duyệt trên giai đoạn giữ kín và có cách quay về baseline. Nếu không đạt, tiếp tục baseline; không tăng độ phức tạp hoặc hạ ngưỡng chỉ để làm đẹp kết quả.

[Protocol máy đọc](comparison_protocol.draft.json) · [Phiếu review để trống](independent_review_template.json).
