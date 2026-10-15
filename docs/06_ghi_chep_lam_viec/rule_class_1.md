# Khung Kiểm Soát & Phát Hiện Gian Lận Nội Bộ (Fraud Detection & Internal Control Matrix)

---

## I. Phân Cấp Mức Độ Ưu Tiên & SLA Điều Tra

| Mức ưu tiên | Thời hạn xử lý (SLA) | Định hướng hành động |
| :--- | :--- | :--- |
| **Cao nhất** | Ngay lập tức ($< 24\text{h}$) | Dấu hiệu vi phạm trực tiếp / Rủi ro thất thoát tức thì; đóng băng giao dịch hoặc kích hoạt điều tra khẩn cấp. |
| **Cao** | $24 - 48\text{h}$ | Cờ đỏ trọng yếu; thẩm định hồ sơ, chứng từ và phỏng vấn các bên liên quan. |
| **Trung bình** | Trong tuần làm việc | Rà soát mẫu hình bất thường; đối chiếu log hệ thống và quy trình phê duyệt. |
| **Thấp** | Định kỳ (Tháng / Quý) | Theo dõi xu hướng, tổng hợp báo cáo định kỳ hoặc dùng làm trọng số tính điểm rủi ro. |

---

## II. Danh Mục Kịch Bản Kiểm Soát (Rule Engine)

### Nhóm A: Vi Phạm Hạn Mức (Split Transactions & Threshold Evasion)
*Mục tiêu: Phát hiện hành vi chia nhỏ, gom cụm hoặc làm tròn giao dịch nhằm né tránh các tầng phê duyệt thẩm quyền.*

| Mã | Tên Rule | Logic phát hiện | Ngưỡng đề xuất | Mức ưu tiên | Ghi chú & Khuyến nghị |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **A1** | Xé nhỏ giao dịch — cửa sổ ngắn | Quét giao dịch đến cùng một người nhận trong cửa sổ trượt $1 - 3$ ngày. | Tổng $\ge 85\%$ ngưỡng duyệt, từ $\ge 2$ giao dịch | **Cao** | Ngưỡng phải gắn theo hạn mức phê duyệt thực tế của người tạo/duyệt, không áp dụng một con số cố định toàn công ty. |
| **A2** | Xé nhỏ giao dịch — cửa sổ dài | Chạy song song cửa sổ trượt $7 - 30$ ngày cho cùng cặp người tạo – người nhận. | Tổng $\ge$ ngưỡng duyệt / $30$ ngày, từ $\ge 3$ giao dịch | **Trung bình** | Bắt các trường hợp cố tình giãn cách thời gian để né rule kiểm tra ngắn hạn. |
| **A3** | Xé nhỏ theo mạng lưới người nhận | Gộp người nhận theo SĐT, địa chỉ, hoặc số tài khoản trùng nhau; tính tổng giá trị theo cụm. | Tương tự A1/A2 nhưng tính trên toàn bộ cụm liên kết | **Cao** | Bắt buộc phải chuẩn hóa dữ liệu chủ (Master Data) trước để tránh bỏ lọt trường hợp dùng nhiều tên khác nhau. |
| **A4** | Tần suất cận ngưỡng theo người tạo | Đếm số giao dịch của một người tạo/duyệt nằm sát mốc phê duyệt (khoảng $80\% - 99\%$ hạn mức). | $\ge 3$ lần / tháng | **Trung bình** | Tín hiệu độc lập, đo lường hành vi theo người tạo thay vì theo đơn vị thụ hưởng. |
| **A5** | Làm tròn số — baseline động | So sánh giá trị giao dịch với phân phối lịch sử theo từng danh mục chi phí / NCC cụ thể. | Đuôi $\ge 3$ chữ số $0$ và lệch $> 2\sigma$ so với baseline danh mục | **Trung bình** | Các chi phí tự nhiên như thuê văn phòng, lương khoán vốn dĩ tròn số; cần baseline động để tránh báo động giả. |
| **A6** | Đối chiếu thanh toán với hoá đơn gốc | So khớp số tiền thanh toán thực tế với giá trị ghi trên hóa đơn/báo giá gốc đính kèm. | Hóa đơn gốc là số lẻ nhưng lệnh thanh toán được làm tròn | **Cao** | Dấu hiệu rút ruột phần chênh lệch hoặc nâng khống giá trị thanh toán. |

---

### Nhóm B: Xung Đột Lợi Ích & Đối Tượng Mờ Ám (Conflicts of Interest & Shell Entities)
*Mục tiêu: Nhận diện mối quan hệ ngầm giữa nhân sự nội bộ và đối tác bên ngoài, ngăn chặn công ty sân sau và rủi ro gian lận thanh toán.*

| Mã | Tên Rule | Logic phát hiện | Ngưỡng đề xuất | Mức ưu tiên | Ghi chú & Khuyến nghị |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **B1** | Khớp chéo TK / CCCD nhân viên $\leftrightarrow$ NCC | Đối chiếu số tài khoản ngân hàng và số CCCD/CMND trên bảng lương với hồ sơ NCC. | Bất kỳ trường hợp trùng khớp nào | **Cao nhất** | Cờ đỏ nghiêm trọng nhất; điều tra thủ công $100\%$ trường hợp phát hiện. |
| **B2** | Khớp chéo SĐT / địa chỉ / người đại diện | Mở rộng B1 sang số điện thoại cá nhân, địa chỉ thường trú/tạm trú, người đại diện pháp luật của NCC. | Trùng $\ge 1$ trường: cờ Vàng<br>Trùng $\ge 2$ trường: cờ Đỏ | **Cao** | Phát hiện trường hợp nhờ người thân, gia đình đứng tên doanh nghiệp sân sau. |
| **B3** | NCC mới thành lập sát ngày giao dịch lớn | So sánh ngày cấp GPKD của nhà cung cấp với ngày phát sinh giao dịch đầu tiên. | Thành lập $< 90$ ngày, phát sinh giao dịch đầu tiên giá trị lớn | **Cao** | Dấu hiệu đặc trưng của công ty vỏ bọc (shell company) thành lập riêng để nhận gói thầu. |
| **B4** | Xác minh MST qua cổng dữ liệu DN | Đối chiếu MST của nhà cung cấp với cơ sở dữ liệu thuế/đăng ký kinh doanh quốc gia. | MST ngừng hoạt động, đóng mã số thuế hoặc ngành nghề không khớp | **Cao** | Cần tích hợp API hoặc chạy quét định kỳ hàng quý, không chỉ kiểm tra khi tạo mới NCC. |
| **B5** | Cụm NCC trùng thông tin định danh | Gom nhóm nhà cung cấp theo địa chỉ, SĐT, người đại diện; đếm số NCC độc lập trong cùng cụm. | $\ge 2$ mã NCC khác nhau trong cùng một cụm liên kết | **Trung bình** | Nhận diện thủ đoạn lập nhiều pháp nhân "quân xanh quân đỏ" để thông thầu hoặc né hạn mức NCC duy nhất. |
| **B6** | Tài khoản "ngủ đông" đột ngột giao dịch lớn | Theo dõi NCC/tài khoản không phát sinh thanh toán $6 - 12$ tháng, bất ngờ có giao dịch lớn hoặc dồn dập. | Giá trị vượt Percentile $90$ lịch sử của chính NCC đó | **Cao** | Đánh giá độ bất thường dựa trên lịch sử riêng của từng NCC, tránh dùng một ngưỡng giá trị tuyệt đối. |
| **B7** | Đổi thông tin ngân hàng sát kỳ thanh toán | Gắn cờ khi tài khoản thụ hưởng của NCC bị thay đổi ngay trước đợt thanh toán giá trị lớn. | Đổi trong vòng $\le 14$ ngày trước thanh toán, đặc biệt nếu nhận qua email | **Cao nhất** | Mẫu hình tấn công giả mạo email doanh nghiệp (BEC - Business Email Compromise); rủi ro thất thoát trực tiếp. |

---

### Nhóm C: Bất Thường Thời Gian & Phân Quyền (Segregation of Duties & Access Control)
*Mục tiêu: Đánh giá rủi ro thao túng hệ thống, vi phạm nguyên tắc bất kiêm nhiệm (SoD) và lạm dụng tài khoản.*

| Mã | Tên Rule | Logic phát hiện | Ngưỡng đề xuất | Mức ưu tiên | Ghi chú & Khuyến nghị |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **C1** | Giao dịch ngoài giờ hành chính | Quét các chứng từ được tạo hoặc phê duyệt vào ban đêm, ngày nghỉ cuối tuần hoặc dịp lễ. | Ngoài khung $08:00 - 19:00$ các ngày làm việc | **Trung bình** | Tín hiệu bổ trợ; cần phối hợp với các rule khác qua mô hình chấm điểm rủi ro (Risk Scoring). |
| **C2** | Vi phạm SoD: Cùng người tạo và duyệt | Đối chiếu `user_id` người tạo (Maker) với `user_id` người phê duyệt (Checker) trên cùng một bút toán. | Trùng khớp `user_id` ở cả hai bước | **Cao nhất** | Vi phạm nghiêm trọng nguyên tắc kiểm soát nội bộ; nên thiết lập chặn cứng trên hệ thống ERP thay vì chỉ cảnh báo. |
| **C3** | Tốc độ phê duyệt siêu tốc | Đo khoảng thời gian chênh lệch giữa thời điểm tạo chứng từ và thời điểm phê duyệt thành công. | $< 60\text{s}$ đối với các giao dịch thuộc thẩm quyền cấp cao | **Cao** | Dấu hiệu phê duyệt chiếu lệ, thiếu thẩm định thực tế hoặc thao túng tài khoản tự duyệt. |
| **C4** | Hoạt động trong kỳ nghỉ phép | Đối chiếu log thao tác hệ thống với dữ liệu lịch nghỉ phép đã được phê duyệt trên hệ thống nhân sự (HRM). | Có phát sinh giao dịch/phê duyệt trong thời gian nghỉ chính thức | **Cao** | Nguy cơ chia sẻ mật khẩu, dùng chung tài khoản trái phép hoặc tài khoản bị chiếm đoạt. |

---

### Nhóm D: Phân Tích Thống Kê Benford (Benford’s Law Analytics)
*Mục tiêu: Sàng lọc diện rộng các tập dữ liệu kế toán lớn nhằm khoanh vùng các cụm số liệu bị can thiệp nhân tạo.*

| Mã | Tên Rule | Logic phát hiện | Ngưỡng đề xuất | Mức ưu tiên | Ghi chú & Khuyến nghị |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **D1** | Phân phối chữ số đầu (First-Digit) | So sánh tần suất xuất hiện của chữ số đầu tiên ($1 - 9$) với hàm phân phối xác suất Benford. | Kiểm định Chi-square hoặc Z-statistic với $p < 0.05$ | **Trung bình** | Yêu cầu tập mẫu tối thiểu $\ge 300 - 1.000$ bản ghi để đảm bảo tính chuẩn xác về mặt thống kê. |
| **D2** | Phân phối chữ số thứ hai (Second-Digit) | Kiểm định tương tự D1 đối với chữ số ở vị trí thứ hai ($0 - 9$). | Z-statistic với $p < 0.05$ | **Thấp** | Chỉ mang tính chất xác thực bổ sung cho D1, không dùng làm căn cứ kết luận độc lập. |
| **D3** | Cặp hai chữ số đầu cận ngưỡng | Đo lường sự đột biến tần suất ở các cặp số sát dưới mốc tròn/mốc thẩm quyền ($18, 19, 48, 49, 98, 99\dots$). | Tần suất thực tế vượt phân phối Benford $> 20\%$ | **Cao** | Bằng chứng định lượng rõ nét cho hành vi cố ý điều chỉnh giá trị để né mốc phê duyệt. |
| **D4** | Tỷ lệ lặp đuôi số đặc biệt | Đo lường tỷ lệ các giao dịch kết thúc bằng các chuỗi lặp như `000`, `500`, `999`. | Tần suất xuất hiện vượt $> 2$ lần kỳ vọng ngẫu nhiên | **Trung bình** | Trong thương mại thông thường (bao gồm thuế, chiết khấu), phần đuôi thường phân bổ ngẫu nhiên và có số lẻ. |
| **D5** | Độ lệch chuẩn tuyệt đối (MAD) | Tính chỉ số Mean Absolute Deviation giữa tần suất thực tế và lý thuyết Benford. | $\text{MAD} > 0.015$ (Ngưỡng Nigrini) | **Cao** | Phân loại: $0.000 - 0.006$ (Tốt), $0.006 - 0.012$ (Chấp nhận), $0.012 - 0.015$ (Biên), $> 0.015$ (Khóa chu trình để kiểm tra). |
| **D6** | Phân tích phân đoạn (Data Segmentation) | Chạy kiểm định Benford theo từng phòng ban, dự án hoặc từng cá nhân phụ trách mua sắm. | Tương tự D1–D5 áp dụng trên từng tập dữ liệu con | **Cao** | Phân tích trên toàn công ty dễ làm loãng dữ liệu; gian lận thường tập trung tại các mắt xích cụ thể. |

---

### Nhóm E: Nhân Sự Ma & Nhà Cung Cấp Ma (Ghost Payroll & Fictitious Vendors)
*Mục tiêu: Rà soát toàn bộ danh mục đối tượng nhận tiền nhằm triệt tiêu các kênh chi trả sai quy định hoặc thất thoát quỹ lương.*

| Mã | Tên Rule | Logic phát hiện | Ngưỡng đề xuất | Mức ưu tiên | Ghi chú & Khuyến nghị |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **E1** | Lương phát sinh không kèm chấm công | Đối chiếu danh sách nhận lương hàng tháng với dữ liệu chấm công thực tế (vân tay, thẻ, GPS). | $0$ lượt ghi nhận chấm công nhưng vẫn có bút toán chi lương | **Cao nhất** | Dấu hiệu đặc trưng của "nhân viên ma" (Ghost Employee) được cài cắm để chiếm đoạt ngân sách. |
| **E2** | Trả lương sau ngày chấm dứt HĐLĐ | Đối chiếu ngày nghỉ việc chính thức trên hệ thống HR với ngày hạch toán các khoản lương, thưởng. | Phát sinh bút toán lương sau ngày chấm dứt hợp đồng hợp lệ | **Cao nhất** | Thường bắt nguồn từ sự thiếu đồng bộ trong quy trình bàn giao (Offboarding) giữa HR và Kế toán. |
| **E3** | So khớp mờ danh xưng NCC (Fuzzy Match) | Ứng dụng thuật toán Levenshtein Distance hoặc Jaro-Winkler để quét các tên NCC tương đồng. | Độ tương đồng $> 85\%$ nhưng tồn tại hai mã đối tác khác nhau | **Trung bình** | Phát hiện thủ thuật thay đổi dấu chấm, khoảng trắng (VD: `ABC Co., Ltd` vs `A.B.C Co., Ltd`) để lập nhiều mã đối tác. |
| **E4** | Trùng lặp thông tin định danh toàn danh mục | Quét định kỳ toàn bộ bảng dữ liệu Vendor Master để tìm các điểm giao thoa về SĐT, số tài khoản, địa chỉ. | $\ge 2$ mã đối tác chia sẻ chung ít nhất $1$ trường định danh | **Trung bình** | Vận hành như một quy trình dọn dẹp và làm sạch dữ liệu chủ định kỳ của hệ thống ERP. |

---

### Nhóm F: Rủi Ro Báo Cáo Tài Chính (Financial Reporting Risks & ISA 240)
*Mục tiêu: Nhận diện các hành vi can thiệp số liệu thủ công, ghi nhận doanh thu thiếu căn cứ hoặc che giấu chi phí cuối niên độ.*

| Mã | Tên Rule | Logic phát hiện | Ngưỡng đề xuất | Mức ưu tiên | Ghi chú & Khuyến nghị |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **F1** | Bút toán thủ công cận ngày khóa sổ | Thống kê các bút toán điều chỉnh bằng tay (Manual Journal Entries) ngay trước thời điểm kết thúc kỳ kế toán. | Phát sinh trong $3 - 5$ ngày trước khóa sổ; giá trị $>$ mức trọng yếu | **Cao** | Rủi ro điển hình về việc xào xáo báo cáo, đẩy doanh thu khống hoặc điều chuyển chi phí dở dang. |
| **F2** | Bút toán Override bởi quản lý cấp cao | Giám sát các bút toán được tạo/duyệt thông qua tài khoản đặc quyền (vượt qua các cổng kiểm soát chuẩn). | Bất kỳ bút toán Override nào nằm ngoài quy trình vận hành | **Cao** | Rủi ro ghi đè của ban điều hành (Management Override of Controls) theo chuẩn mực ISA 240 / COSO. |
| **F3** | Kiểm tra chuỗi số chứng từ liên tục | Rà soát tính toàn vẹn của dãy số hóa đơn tài chính, phiếu thu, phiếu chi, lệnh thanh toán. | Xuất hiện khoảng trống (gaps) hoặc trùng lặp số chứng từ | **Trung bình** | Cần đối chiếu với nhật ký hủy chứng từ có phê duyệt để loại trừ các nghiệp vụ sai sót thông thường. |
| **F4** | Doanh thu ghi nhận lệch dòng tiền thực tế | So khớp doanh thu bán hàng ghi nhận với dòng tiền thực tế giải ngân về tài khoản theo từng khách hàng. | Chênh lệch công nợ kéo dài $> 60$ ngày không có giải trình | **Trung bình** | Ngăn ngừa việc ghi nhận doanh thu ảo (chỉ hạch toán trên sổ sách nhưng không thể thu hồi dòng tiền). |

---

## III. Khung Vận Hành Hệ Thống Cảnh Báo (Section G - Operations)

### 1. Cơ Chế Chấm Điểm Rủi Ro Tổng Hợp (Composite Risk Scoring)
*   **Nguyên tắc không cô lập:** Tránh xử lý từng rule cảnh báo một cách độc lập hoặc kích hoạt điều tra tràn lan với các rule đơn lẻ.
*   **Mô hình tính điểm:** Mỗi rule vi phạm đóng góp một trọng số điểm tương ứng ($W_i$):
    *   *Trọng số Thấp:* $1 - 2$ điểm (VD: D2, C1)
    *   *Trọng số Trung bình:* $3 - 5$ điểm (VD: A2, A5, B5, F3)
    *   *Trọng số Cao:* $7 - 10$ điểm (VD: A1, A6, B3, C3, F1)
    *   *Kích hoạt khẩn cấp (Hard Trigger):* Trực tiếp chuyển trạng thái điều tra (VD: B1, B7, C2, E1).
*   **Gộp cụm rủi ro:** Chỉ nâng mức độ ưu tiên điều tra lên cấp **Cao/Cao nhất** khi một giao dịch, một nhân sự hoặc một nhà cung cấp tích lũy tổng điểm vượt ngưỡng trong cùng một khung thời gian (cửa sổ trượt 30 ngày). Điều này giúp triệt tiêu hiện tượng "Alert Fatigue" (kiệt sức vì cảnh báo ảo).

### 2. Quy Trình Quản Lý & Xử Lý Hồ Sơ (Case Management & SLA)
Mỗi cảnh báo phát sinh từ hệ thống phải được chuẩn hóa thành một "Case" độc lập với các yêu cầu vận hành sau:
*   **Xác định đầu mối (Case Owner):** Phân công cụ thể kiểm soát viên hoặc chuyên viên kiểm toán nội bộ chịu trách nhiệm chính.
*   **Cam kết thời gian phản hồi (SLA Enforcement):**
    *   *Mức Cao nhất / Cao:* Bắt buộc tiếp nhận trong $2 - 4\text{h}$, hoàn tất đánh giá sơ bộ trong $24 - 48\text{h}$.
    *   *Mức Trung bình:* Hoàn thành rà soát và xác minh hồ sơ trong tuần làm việc.
*   **Chuẩn hóa kết luận:** Mọi hồ sơ đóng lại đều phải lưu vết kiểm toán (Audit Trail) với một trong ba trạng thái:
    1.  *Confirmed Fraud / Non-Compliance:* Xác nhận gian lận hoặc vi phạm; chuyển hồ sơ xử lý kỷ luật/pháp lý.
    2.  *False Positive:* Báo động giả; ghi nhận lý do nghiệp vụ đặc thù để tối ưu hóa rule.
    3.  *Information Gap:* Cần thu thập thêm bằng chứng hoặc chờ chu kỳ thanh toán tiếp theo.

### 3. Chuẩn Hóa Dữ Liệu Chủ (Master Data Normalization)
Trước khi khởi chạy các logic quét chéo (đặc biệt là B1, B2, B5, E3, E4), dữ liệu phải đi qua đường ống chuẩn hóa (ETL Data Pipeline):
*   **Định dạng văn bản:** Chuyển đổi toàn bộ chuỗi ký tự về dạng chữ in hoa không dấu (`UPPERCASE`), loại bỏ khoảng trắng thừa (`TRIM`) và các ký tự đặc biệt (`.`, `,`, `-`, `/`).
*   **Số điện thoại & Căn cước:** Chuẩn hóa mã quốc gia, đồng nhất về định dạng 10 chữ số (đối với SĐT) và 12 chữ số (đối với CCCD gắn chip).
*   **Địa chỉ cư trú / Trụ sở:** Phân tách và cấu trúc hóa theo 3 cấp hành chính chuẩn (Tỉnh/Thành phố — Quận/Huyện — Phường/Xã) để giảm thiểu sai số khi ghép nối.

### 4. Kiểm Thử Hồi Cứu & Tinh Chỉnh Định Kỳ (Back-Testing & Calibration)
*   **Đo lường tính chính xác:** Chạy thử nghiệm bộ rule trên tập dữ liệu lịch sử chứa các vụ việc gian lận đã được phát hiện trong quá khứ nhằm tính toán hai chỉ số:
    *   *Tỷ lệ phát hiện đúng (Hit Rate / True Positive Rate).*
    *   *Tỷ lệ báo động giả (False Alarm Rate / False Positive Rate).*
*   **Chu kỳ hiệu chỉnh:**
    *   Rà soát và tinh chỉnh ngưỡng kích hoạt (Thresholds) theo chu kỳ **hàng quý**.
    *   Đối với các đơn vị kinh doanh hoặc danh mục chi phí có tính biến động cao, thiết lập lại baseline động sau mỗi 6 tháng vận hành.