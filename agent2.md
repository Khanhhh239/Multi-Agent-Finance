2.1. Yêu cầu sản phẩm
Người dùng chính là chủ doanh nghiệp hoặc kế toán trưởng tại một doanh nghiệp nhỏ — nơi không có bộ phận kiểm toán nội bộ hay đội điều tra gian lận chuyên trách. Vấn đề cần giải không phải điều tra tội phạm có tổ chức quy mô lớn, mà là phát hiện sớm các dạng gian lận nội bộ ở quy mô nhỏ và vừa: một cá nhân lợi dụng kẽ hở kiểm soát để chiếm đoạt, một bút toán khống, một giao dịch với bên liên quan không được công bố. Đây chính là điểm đã được làm rõ khi rà soát lại bảng minh chứng: nhóm doanh nghiệp quy mô nhỏ dưới một trăm nhân sự có tỷ lệ xảy ra gian lận tham nhũng nội bộ cao nhất trong mọi nhóm quy mô, ở mức bốn mươi bốn phần trăm theo thống kê của ACFE, và kiểm soát nội bộ yếu là đặc điểm phổ biến hơn hẳn ở nhóm tổ chức nhỏ so với tổ chức lớn — đúng là nhóm đối tượng và đúng quy mô mà trợ lý này hướng tới.
Yêu cầu sống còn với trợ lý này không phải là phát hiện được nhiều nhất có thể, mà là không gây quá tải cảnh báo sai. Một doanh nghiệp nhỏ không có nhân lực để rà soát hàng chục cảnh báo mỗi ngày; nếu hệ thống báo động giả quá nhiều, người dùng sẽ tắt thông báo và toàn bộ giá trị của trợ lý biến mất. Đây là hiện tượng đã được ghi nhận rộng rãi trong ngành phòng chống gian lận: nhân sự tại các tổ chức tài chính quy mô vừa và lớn dành tới khoảng bảy mươi phần trăm thời gian làm việc để rà soát các cảnh báo cuối cùng là báo động giả (FluxForce AI, 2025). Với một doanh nghiệp nhỏ hoàn toàn không có nhân sự chuyên trách, hậu quả của hiện tượng này còn nghiêm trọng hơn — nên yêu cầu giảm báo động giả không phải một tiêu chí phụ mà là điều kiện tiên quyết để sản phẩm được sử dụng lâu dài.
2.2. Kiến trúc và luồng vận hành
 [Lớp phát hiện tất định]
Thư viện quy tắc ngưỡng động, ánh xạ theo chuẩn ISA 240 / SAS 99

↓

Phân tích đồ thị quan hệ thực thể tất định (networkx) – lớp chính phát hiện quan hệ tài khoản / pháp nhân dùng chung

↓

Gộp tín hiệu

[Lớp học máy bổ trợ]
Isolation forest phát hiện bút toán bất thường (phương pháp Schreyer et al.)

↓

Mạng nơ-ron đồ thị bổ trợ (GraphSAGE / GAT) – lớp phụ, KHÔNG thay thế lớp đồ thị tất định

↓

(bổ sung phát hiện quan hệ ẩn mà quy tắc tường minh bỏ sót)

[Lớp điều phối và sản phẩm]
Bộ tổng hợp điểm số (ensemble scoring)

↓

Xếp hạng ưu tiên + lý do bằng SHAP

↓

Hàng đợi xử lý kiểu case management

↓

Phản hồi 1-chạm của người dùng → hiệu chỉnh lại ngưỡng
Cấu trúc phân lớp này giữ nguyên quyết định đã chứng minh ở Phần 2: đồ thị quan hệ tất định là lớp chính vì có thể giải thích trực tiếp bằng quan hệ sở hữu hoặc tài khoản dùng chung, còn mạng nơ-ron đồ thị chỉ đóng vai trò bổ trợ do bằng chứng từ bộ dữ liệu Elliptic cho thấy mô hình học máy cổ điển thường vượt trội hơn GNN trên đồ thị giao dịch thưa. Phần bổ sung ở đây là lớp điều phối sản phẩm phía sau bộ tổng hợp điểm số, nơi cảnh báo được đưa vào một hàng đợi có thể thao tác thay vì một nhật ký tĩnh.
2.3. Mô hình và dữ liệu
Thư viện quy tắc mã hoá các dấu hiệu gian lận kinh điển theo chuẩn kiểm toán quốc tế — giao dịch sát ngưỡng phê duyệt, bút toán cuối kỳ bất thường, thanh toán trùng lặp. Autoencoder học biểu diễn "bình thường" của toàn bộ bút toán trong sổ cái và gắn cờ những bút toán có sai số tái tạo cao — tức lệch xa khỏi khuôn mẫu thông thường của chính doanh nghiệp đó, không dựa trên ngưỡng cố định áp dụng chung cho mọi công ty. GraphSAGE hoặc GAT bổ sung khả năng phát hiện các mẫu quan hệ nhiều bước mà quy tắc tường minh khó bao quát hết, ví dụ một chuỗi giao dịch luân chuyển qua nhiều thực thể trung gian. Bộ tổng hợp kết hợp tất cả tín hiệu, và với mỗi cảnh báo cuối cùng, SHAP xuất ra danh sách yếu tố đóng góp nhiều nhất, làm nền cho lời giải thích tự nhiên ở lớp sản phẩm.
Dữ liệu huấn luyện dùng bộ công ty tổng hợp với sáu nhóm kịch bản gian lận được gán nhãn rõ (đã liệt kê chi tiết ở Phần 3), đối chiếu chéo với bộ dữ liệu công khai Elliptic để kiểm chứng khả năng khái quát của lớp mạng nơ-ron đồ thị.
2.4. Trải nghiệm người dùng
Đây là nơi thiết kế sản phẩm có tác động rõ ràng nhất đến việc trợ lý có được dùng lâu dài hay không. Thay vì một danh sách nhật ký cảnh báo đơn thuần, giao diện được tổ chức theo mô hình hàng đợi xử lý — mỗi cảnh báo là một "hồ sơ" chờ xử lý, tương tự cách các nền tảng chống gian lận chuyên nghiệp tổ chức công việc cho đội điều tra, nơi hệ thống lọc và gộp tín hiệu trước khi đưa tới người xem, đính kèm điểm tin cậy và hành động đề xuất cho từng trường hợp thay vì đẩy toàn bộ tín hiệu thô ra một lượt (Swimlane, 2025). Mỗi hồ sơ hiển thị ba phần: một câu giải thích ngắn bằng tiếng Việt tự nhiên nêu lý do bị gắn cờ, được dựng từ danh sách yếu tố SHAP thay vì thuật ngữ mô hình; sơ đồ trực quan thể hiện quan hệ giữa các thực thể liên quan nếu cảnh báo đến từ lớp đồ thị; và một cặp nút phản hồi nhanh — "Xác nhận là bất thường thật" hoặc "Không phải, bỏ qua". Cách trình bày lý do bằng ngôn ngữ tự nhiên đi kèm dấu vết kiểm chứng được là nguyên tắc cốt lõi của AI có thể giải thích trong lĩnh vực tài chính, nơi hệ thống không chỉ chấm điểm rủi ro mà phải nêu rõ yếu tố nào dẫn tới điểm đó theo cách một người kiểm toán có thể đọc và hành động được.
Phản hồi một-chạm của người dùng không chỉ đóng hồ sơ mà được đưa trở lại làm dữ liệu hiệu chỉnh ngưỡng cảnh báo — nếu một loại tín hiệu liên tục bị người dùng đánh dấu là báo động giả, ngưỡng liên quan tự động được nới ra ở lần sau, và ngược lại. Đây là cơ chế sản phẩm trực tiếp giải quyết vấn đề quá tải cảnh báo đã nêu ở mục yêu cầu, biến việc rà soát cảnh báo thành một hành động rèn luyện hệ thống thay vì gánh nặng lặp lại vô ích.
2.5. Con đường đến hoàn thiện
Giai đoạn khởi điểm triển khai đầy đủ lớp quy tắc tất định và autoencoder, vốn đã bao phủ phần lớn các dạng gian lận phổ biến với chi phí vận hành thấp. Lớp mạng nơ-ron đồ thị được bổ sung ở giai đoạn hai khi đã tích luỹ đủ dữ liệu quan hệ thực tế để huấn luyện có ý nghĩa. Giai đoạn hoàn thiện đưa vòng phản hồi từ người dùng vào một quy trình tái huấn luyện định kỳ, giúp ngưỡng cảnh báo và trọng số ensemble tự thích nghi theo đặc điểm vận hành riêng của từng doanh nghiệp thay vì dùng chung một cấu hình tĩnh cho mọi khách hàng.
