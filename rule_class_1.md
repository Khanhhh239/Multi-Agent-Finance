# Khung Kiểm Soát & Phát Hiện Gian Lận Nội Bộ (Fraud Detection & Internal Control Matrix)

Phạm vi thực thi hiện tại: [định nghĩa đợt 3](reports/rule_repairs_phase3.md), `spec_policy=phase3`, và [nguồn/đối chứng đợt 4](reports/rule_repairs_phase4.md), `evidence_policy=phase4`. Mức ưu tiên trong bảng là định hướng rà soát; điểm và điều kiện vào hàng đợi áp dụng theo mục III.1 bên dưới. Snapshot/fixture lịch sử giữ cấu hình của phiên bản đã chấm.

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
| **A1** | Xé nhỏ giao dịch — cửa sổ ngắn | Quét giao dịch đến cùng một người nhận trong cửa sổ trượt $1 - 3$ ngày. | Tổng $\ge 85\%$ ngưỡng duyệt, từ $\ge 2$ giao dịch | **Cao** | Nghĩa vụ độc lập chỉ được loại khi liên kết đúng giao dịch–yêu cầu chi–PO–hóa đơn đã xác minh; cùng nghĩa vụ và tổng toàn lịch sử vẫn bị kiểm tra. Thiếu nguồn giữ cảnh báo hiện tại. [Chính sách bằng chứng](reports/rule_payment_evidence.md). |
| **A2** | Xé nhỏ giao dịch — cửa sổ dài | Chạy song song cửa sổ trượt $7 - 30$ ngày cho cùng cặp người tạo – người nhận. | Tổng $\ge$ ngưỡng duyệt / $30$ ngày, từ $\ge 3$ giao dịch | **Trung bình** | Hợp đồng trả nhiều đợt cần agreement đã duyệt, hóa đơn typed và tổng hóa đơn/hợp đồng chưa vượt trần. Đổi request nhưng dùng chung PO không tạo ngoại lệ độc lập. [Chính sách bằng chứng](reports/rule_payment_evidence.md). |
| **A3** | Xé nhỏ theo mạng lưới người nhận | Trên `vendor_payment`, gom liên kết TK có định danh ngân hàng, SĐT hoặc đại diện còn hiệu lực trong nguồn đã quan sát tại giao dịch; cần ít nhất hai NCC. Địa chỉ đơn lẻ không đủ để gom. | ≥2 khoản trong 3 ngày, tổng ≥85% hạn mức; hoặc ≥3 khoản trong 30 ngày, tổng ≥hạn mức. Từng khoản dưới hạn mức của người lập tương ứng. | **Cao** | Tổng so với hạn mức giao dịch hiện tại; gom cả nhiều người lập. Cửa sổ tính thời lượng, quan sát đồng thời không nhìn thấy nhau. Đổi/xóa thông tin phải tách lại cụm; lưu nhánh và đường liên kết tại lúc phát hiện. [Chính sách lịch sử](reports/rule_graph_history.md). |
| **A4** | Tần suất cận ngưỡng theo người lập | Đếm khoản chi tiền/ngân hàng của cùng người lập ở mức 80%–99% hạn mức từng khoản. | ≥3 lần trong **tháng lịch** theo giờ Việt Nam; tùy chọn `near_period=rolling_30d` phải khai báo riêng. | **Trung bình** | Loại đúng khoản có yêu cầu/hợp đồng/hóa đơn hoặc lịch định kỳ đã duyệt. Lịch tuần/tháng/quý/năm phải đúng đối tượng và tổng kỳ chưa vượt trần; chỉ chia đợt khi `allow_partial=1`. Không loại theo nhãn payroll/rent đơn lẻ. [Chính sách bằng chứng](reports/rule_payment_evidence.md). |
| **A5** | Khoản tròn bất thường ở đuôi cao | Số tiền chia hết 1.000 và **cao hơn** baseline cùng nghiệp vụ/thực thể/danh mục; không dùng độ lệch tuyệt đối. | Mặc định log/MAD, z>3,5 đã chọn trên validation; raw mean/SD với z>+2 chỉ dùng đối chiếu. Tối thiểu 20 mẫu. | **Trung bình** | Chỉ đuôi cao, mục tiêu khoản chi tăng bất thường. Nguồn chi định kỳ đã duyệt có thể loại; A5 là ngữ cảnh cần bằng chứng độc lập, không tự mở hồ sơ. |
| **A6** | Đối chiếu thanh toán với hoá đơn gốc | So khớp số tiền thanh toán thực tế với giá trị ghi trên hóa đơn/báo giá gốc đính kèm. | Hóa đơn gốc là số lẻ nhưng lệnh thanh toán được làm tròn | **Cao** | Dấu hiệu rút ruột phần chênh lệch hoặc nâng khống giá trị thanh toán. |

---

### Nhóm B: Xung Đột Lợi Ích & Đối Tượng Mờ Ám (Conflicts of Interest & Shell Entities)
*Mục tiêu: Nhận diện mối quan hệ ngầm giữa nhân sự nội bộ và đối tác bên ngoài, ngăn chặn công ty sân sau và rủi ro gian lận thanh toán.*

| Mã | Tên Rule | Logic phát hiện | Ngưỡng đề xuất | Mức ưu tiên | Ghi chú & Khuyến nghị |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **B1** | Khớp chéo TK / CCCD nhân viên ↔ NCC | Đối chiếu toàn master **đã biết/as-of** thành hồ sơ riêng, không cộng điểm giao dịch. Cảnh báo khi khoản chi NCC (Có 111/112, tiền/ngân hàng), gồm thuê/chi bán hàng, nhận vào TK nhân viên hoặc NCC trùng CCCD/CMND. | TK+số định danh ngân hàng trùng, hoặc national_id 9/12 chữ số trùng; giữ số 0 đầu. | **Cao nhất** | Dùng `bank_code`, `recipient_bank_code`, `national_id` khi có nguồn. TK thực thiếu mã ngân hàng chỉ chẩn đoán 0 điểm; BANK_SYN là namespace mô phỏng duy nhất. Bên liên quan đã công bố hạ điểm/không hard trigger, vẫn lưu bằng chứng. |
| **B2** | Khớp chéo SĐT / địa chỉ / người đại diện | Mở rộng B1 sang số điện thoại cá nhân, địa chỉ thường trú/tạm trú, người đại diện pháp luật của NCC; dùng phiên bản master và liên kết hiện hành đã quan sát. | Trùng $\ge 1$ trường: cờ Vàng<br>Trùng $\ge 2$ trường: cờ Đỏ | **Cao** | Liên kết đổi/xóa không tiếp tục tạo đường dẫn; bằng chứng khác còn hiệu lực được giữ. Dữ liệu tương lai không sửa cảnh báo quá khứ. Phạm vi thẩm tra và ngoại lệ bên liên quan theo [chính sách lịch sử](reports/rule_graph_history.md). |
| **B3** | NCC mới thành lập sát nghiệp vụ kinh tế lớn đầu tiên | Lần phát sinh **bút toán tài chính gắn NCC đầu tiên trong lịch sử quan sát**, gồm mua ghi công nợ trước khi trả tiền. | Thành lập <90 ngày; khoản đầu ≥hạn mức hoặc vượt baseline loại nghiệp vụ mean+2SD khi đủ 20 mẫu. | **Cao** | Thiếu lịch sử trước đầu dữ liệu thì không khẳng định lần đầu suốt đời NCC. Cùng timestamp là nhóm quan sát đầu đồng thời. Ngoại lệ cần hóa đơn+đơn mua/hợp đồng+giao nhận/nghiệm thu đã xác minh/as-of. Chỉ là ngữ cảnh khi chưa có bằng chứng độc lập. |
| **B4** | Xác minh MST qua cổng dữ liệu DN | Đối chiếu MST của nhà cung cấp với cơ sở dữ liệu thuế/đăng ký kinh doanh quốc gia. | MST ngừng hoạt động, đóng mã số thuế hoặc ngành nghề không khớp | **Cao** | Cần tích hợp API hoặc chạy quét định kỳ hàng quý, không chỉ kiểm tra khi tạo mới NCC. |
| **B5** | Cụm NCC trùng thông tin định danh | Gom nhóm nhà cung cấp theo địa chỉ, SĐT, người đại diện; đếm số NCC độc lập trong cùng cụm. | $\ge 2$ mã NCC khác nhau trong cùng một cụm liên kết | **Trung bình** | Nhận diện thủ đoạn lập nhiều pháp nhân "quân xanh quân đỏ" để thông thầu hoặc né hạn mức NCC duy nhất. |
| **B6** | Tài khoản "ngủ đông" đột ngột giao dịch lớn | Theo dõi NCC không phát sinh thanh toán ít nhất 180 ngày, sau đó nhận khoản vượt P90 trên tối thiểu 20 khoản lịch sử. | Idle ≥180 ngày và giá trị >P90 của chính NCC | **Cao** | Loại đúng khoản có lịch năm/mùa đã duyệt, đúng cửa sổ–NCC–nghiệp vụ–hợp đồng/người nhận và tổng kỳ chưa vượt trần; lịch năm trong `recurring_payments` cũng được dùng. Thiếu lịch giữ cảnh báo hiện tại. [Chính sách nguồn](reports/rule_authority_dormancy.md). |
| **B7** | Đổi thông tin ngân hàng sát kỳ thanh toán | Gắn cờ khi tài khoản thụ hưởng của NCC bị thay đổi ngay trước đợt thanh toán giá trị lớn. | Đổi trong vòng $\le 14$ ngày trước thanh toán, đặc biệt nếu nhận qua email | **Cao nhất** | Mẫu hình tấn công giả mạo email doanh nghiệp (BEC - Business Email Compromise); rủi ro thất thoát trực tiếp. |

---

### Nhóm C: Bất Thường Thời Gian & Phân Quyền (Segregation of Duties & Access Control)
*Mục tiêu: Đánh giá rủi ro thao túng hệ thống, vi phạm nguyên tắc bất kiêm nhiệm (SoD) và lạm dụng tài khoản.*

| Mã | Tên Rule | Logic phát hiện | Ngưỡng đề xuất | Mức ưu tiên | Ghi chú & Khuyến nghị |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **C1** | Thao tác ngoài lịch vận hành | Xét riêng giờ lập và giờ duyệt với phiên bản `operating_schedules` đã duyệt/biết **tại lúc thao tác**, gồm lịch ca/cuối tuần. | Ngoài lịch áp dụng; thiếu lịch ca dùng 08:00–19:00 ngày làm việc và `saturday_operations` của công ty. | **Trung bình** | Vận hành thứ Bảy được cấp quyền là hợp lệ; không quy mọi cuối tuần thành vi phạm. Hit ngoài lịch là ngữ cảnh cần bằng chứng độc lập để góp điểm. Lịch lễ hiện là nguồn minh họa của dataset. |
| **C2** | Tự duyệt vượt quyền đã cấp | So sánh Maker–Checker với ma trận theo nhân viên/vai trò, nghiệp vụ, phòng ban, dự án, khoảng tiền và ủy quyền còn hiệu lực. | Cùng người nhưng không có quyền `self_approval_allowed` khớp phạm vi. | **Cao nhất** | Chỉ thay hạn mức master khi coverage xác nhận ma trận đầy đủ. Quyền/ủy quyền phải được người khác duyệt và biết trước hành động; nguồn mơ hồ không cấp ngoại lệ. Thiếu coverage giữ fallback `self_approval_limit_vnd`. [Chính sách nguồn](reports/rule_authority_dormancy.md). |
| **C3** | Tốc độ phê duyệt siêu tốc | Đo thời gian tạo–duyệt và đọc `authority_level` của đúng người duyệt trong ma trận có coverage. | <60 giây với `high` hoặc `executive`. | **Cao** | Khi có coverage, không suy cấp cao từ số tiền; khoản lớn thuộc cấp chuẩn không tự bị bắt. Thiếu coverage mới dùng `high_approval_vnd` làm proxy tương thích. [Chính sách nguồn](reports/rule_authority_dormancy.md). |
| **C4** | Thao tác trong nghỉ phép đã duyệt | Log maker/checker gắn đúng người/giao dịch/thời điểm; leave theo khoảng giờ đã biết trước thao tác. | Thao tác trong `[starts_at, ends_at)` và không có quyền làm việc trong nghỉ phép hợp lệ. | **Cao** | 8 điểm; ngoại lệ phải có người duyệt độc lập, gắn đúng leave/action/khoảng giờ và đã biết trước thao tác. Tổng ngày nghỉ tháng không đủ; chưa hỗ trợ mọi loại truy cập hệ thống. |

---

### Nhóm D: Phân Tích Thống Kê Benford (Benford’s Law Analytics)
*Mục tiêu: Sàng lọc diện rộng các tập dữ liệu kế toán lớn nhằm khoanh vùng các cụm số liệu bị can thiệp nhân tạo.*

| Mã | Tên Rule | Logic phát hiện | Ngưỡng đề xuất | Mức ưu tiên | Ghi chú & Khuyến nghị |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **D1** | Phân phối chữ số đầu (First-Digit) | So sánh tần suất xuất hiện của chữ số đầu tiên ($1 - 9$) với hàm phân phối xác suất Benford. | Kiểm định Chi-square hoặc Z-statistic với $p < 0.05$ | **Trung bình** | Yêu cầu tập mẫu tối thiểu $\ge 300 - 1.000$ bản ghi để đảm bảo tính chuẩn xác về mặt thống kê. |
| **D2** | Phân phối chữ số thứ hai (Second-Digit) | Kiểm định tương tự D1 đối với chữ số ở vị trí thứ hai ($0 - 9$). | Z-statistic với $p < 0.05$ | **Thấp** | Chỉ mang tính chất xác thực bổ sung cho D1, không dùng làm căn cứ kết luận độc lập. |
| **D3** | Cặp hai chữ số đầu cận ngưỡng | Trong definition phase4, kiểm hai chữ số đầu trên tập đủ mẫu/hạn mức đồng nhất; excess phải đến từ số tiền thực ở mức 80%–dưới 100% hạn mức. | Excess >20% kỳ vọng và kiểm định toàn cặp có p-value được điều chỉnh <0,05. | **Cao** | Chẩn đoán cấp cửa sổ, 0 điểm giao dịch; cặp 98/99 ở số tiền rất thấp không tự là cận ngưỡng. Không chứng minh ý định né duyệt; giữ min_rows/kiểm ô kỳ vọng. |
| **D4** | Tỷ lệ lặp đuôi số đặc biệt | Đo lường tỷ lệ các giao dịch kết thúc bằng các chuỗi lặp như `000`, `500`, `999`. | Tần suất xuất hiện vượt $> 2$ lần kỳ vọng ngẫu nhiên | **Trung bình** | Trong thương mại thông thường (bao gồm thuế, chiết khấu), phần đuôi thường phân bổ ngẫu nhiên và có số lẻ. |
| **D5** | Độ lệch chuẩn tuyệt đối (MAD) | Tính chỉ số Mean Absolute Deviation giữa tần suất thực tế và lý thuyết Benford. | $\text{MAD} > 0.015$ (Ngưỡng Nigrini) | **Cao** | Phân loại: $0.000 - 0.006$ (Tốt), $0.006 - 0.012$ (Chấp nhận), $0.012 - 0.015$ (Biên), $> 0.015$ (Khóa chu trình để kiểm tra). |
| **D6** | Benford theo phân đoạn | Phase4 chạy chữ số đầu theo creator, department và project_id có nguồn. | ≥300 mẫu, đủ độ rộng/đa dạng/ô kỳ vọng và p-value đã điều chỉnh <0,05. | **Cao** | Không hạ min_rows để ép các phân đoạn nhỏ đủ điều kiện. D1/D2/D3/D6 phase4 dùng BY cùng cutoff; D4/D5 là chẩn đoán mô tả riêng. Không gán nhãn dòng gian lận thành nhãn cửa sổ. |

---

### Nhóm E: Nhân Sự Ma & Nhà Cung Cấp Ma (Ghost Payroll & Fictitious Vendors)
*Mục tiêu: Rà soát toàn bộ danh mục đối tượng nhận tiền nhằm triệt tiêu các kênh chi trả sai quy định hoặc thất thoát quỹ lương.*

| Mã | Tên Rule | Logic phát hiện | Ngưỡng đề xuất | Mức ưu tiên | Ghi chú & Khuyến nghị |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **E1** | Lương phát sinh không kèm chấm công | Đối chiếu danh sách nhận lương hàng tháng với dữ liệu chấm công thực tế (vân tay, thẻ, GPS). | $0$ lượt ghi nhận chấm công nhưng vẫn có bút toán chi lương | **Cao nhất** | Dấu hiệu đặc trưng của "nhân viên ma" (Ghost Employee) được cài cắm để chiếm đoạt ngân sách. |
| **E2** | Lương thường cho kỳ sau chấm dứt HĐLĐ | Employment events termination/rehire và quyền chi theo kỳ/loại/số tiền/giao dịch có nguồn đã duyệt/as-of. | Chi sau ngày nghỉ và regular_salary cho kỳ công bắt đầu sau ngày nghỉ, chưa có tái tuyển dụng có hiệu lực đã biết. | **Cao nhất** | 20 điểm/hard trigger khi đủ nguồn. Quyết toán/truy lĩnh/trợ cấp/thưởng cho kỳ trước nghỉ, đúng hồ sơ/số tiền: loại. Thiếu loại chi/kỳ công hoặc kỳ giao thời: information gap, 0 điểm. |
| **E3** | So khớp mờ danh xưng NCC (Fuzzy Match) | Ứng dụng thuật toán Levenshtein Distance hoặc Jaro-Winkler để quét các tên NCC tương đồng. | Độ tương đồng $> 85\%$ nhưng tồn tại hai mã đối tác khác nhau | **Trung bình** | Phát hiện thủ thuật thay đổi dấu chấm, khoảng trắng (VD: `ABC Co., Ltd` vs `A.B.C Co., Ltd`) để lập nhiều mã đối tác. |
| **E4** | Trùng lặp thông tin định danh toàn danh mục | Quét định kỳ toàn bộ bảng dữ liệu Vendor Master để tìm các điểm giao thoa về SĐT, số tài khoản, địa chỉ. | $\ge 2$ mã đối tác chia sẻ chung ít nhất $1$ trường định danh | **Trung bình** | Vận hành như một quy trình dọn dẹp và làm sạch dữ liệu chủ định kỳ của hệ thống ERP. |

---

### Nhóm F: Rủi Ro Báo Cáo Tài Chính (Financial Reporting Risks & ISA 240)
*Mục tiêu: Nhận diện các hành vi can thiệp số liệu thủ công, ghi nhận doanh thu thiếu căn cứ hoặc che giấu chi phí cuối niên độ.*

| Mã | Tên Rule | Logic phát hiện | Ngưỡng đề xuất | Mức ưu tiên | Ghi chú & Khuyến nghị |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **F1** | Bút toán thủ công cận khóa sổ và trọng yếu | `journal_audit_log` xác nhận manual/entered_at; `closing_periods` xác định khóa thực của kỳ; `materiality_policies` cấp mức trọng yếu kế toán đã duyệt/as-of. Không giới hạn loại adjustment. | Nhập thủ công từ 0 đến 5 ngày trước khóa thực (bao gồm biên), amount>mức trọng yếu có hiệu lực. | **Cao** | Cần đủ ba nguồn, dấu vết và thời điểm quan sát. Adjustment/cuối tháng/hạn mức người lập chỉ là proxy 0 điểm; không thay lịch khóa sổ hoặc trọng yếu đã duyệt. Hồ sơ trong quyền tự duyệt không tự miễn F1 đã xác nhận. |
| **F2** | Override ngoài workflow được cấp | Log bypass của từng control và policy có hiệu lực/được duyệt trước thao tác, vai trò/hạn mức của actor đã biết. | Bypass control bắt buộc ngoài quyền override; quy trình chưa hoàn thành. | **Cao** | 8 điểm; thiếu policy là information gap, 0 điểm. Ngoại lệ hợp lệ cho một control không miễn control khác; không coi mọi tài khoản đặc quyền là vi phạm. |
| **F3** | Số chứng từ trùng/khoảng trống có nguồn | Sổ phát hành theo company/series/type/year và nhật ký hủy. Gap chỉ trên dải đã khai báo khóa và xác nhận log hủy đầy đủ. | Chứng từ vật lý khác nhau còn hiệu lực trùng số; hoặc số thiếu chưa được giải trình/hủy hợp lệ. | **Trung bình** | Duplicate là context 3 điểm cần anchor độc lập. Gap là source finding riêng, 0 điểm; thiếu coverage hủy là unknown. Không dùng transaction_id hoặc ép số hóa đơn mọi NCC thành một dãy. |
| **F4** | Công nợ hóa đơn quá hạn chưa giải trình | Ghép AR invoice–customer–receipt thực–allocation đã xác minh, hạn trả, coverage sổ thu tiền và giải trình đã duyệt/as-of. | Dư nợ >0, quá hạn >60 ngày từ due_at, chưa có giải trình còn hiệu lực và đủ coverage đến cutoff. | **Trung bình** | Source finding để rà soát thu hồi công nợ, 0 điểm giao dịch. Thiếu coverage/sai ghép/overallocated receipt là information gap. Không tự kết luận doanh thu giả; có CLI cutoff độc lập khi không có giao dịch mới. |

---

## III. Khung Vận Hành Hệ Thống Cảnh Báo (Section G - Operations)

### 1. Cơ Chế Chấm Điểm Rủi Ro Tổng Hợp (Composite Risk Scoring)
*   **Nguyên tắc không cô lập:** Tránh xử lý từng rule cảnh báo một cách độc lập hoặc kích hoạt điều tra tràn lan với các rule đơn lẻ.
*   **Vai bằng chứng và điểm:** E3/B5/E4 và đối chiếu B1 master là chẩn đoán riêng, 0 điểm; B5 giữ alias E4 để truy vết. C1/A5/B3 và F3 duplicate cần bằng chứng giao dịch độc lập đủ ngưỡng 7 để góp điểm. A5 không góp cùng anchor A nếu chỉ lặp nguồn số tiền. F1 proxy 0 điểm; F1/F2 đủ nguồn có 8 điểm. C4 có 8 điểm, E2 có 20 điểm/hard trigger khi đã xác nhận nguồn. F3 gaps/F4 aging và D1–D6 là chẩn đoán nguồn/tập, 0 điểm giao dịch. Dataset thiếu nguồn được đánh dấu not_evaluable/information_gap; đối chứng đạt không đồng nghĩa đã nghiệm thu trên SME thật.
*   **Tổng điểm hiện tại:** Lấy điểm lớn nhất trong mỗi nhóm A/B/C/E/F và mỗi nhóm phụ P/T, rồi cộng các nhóm. Giao dịch có điểm nền ≥7 nhận thêm tối đa 3 điểm tái diễn từ cảnh báo **trước đó** cùng thực thể/công ty trong 30 ngày; không cộng tất cả điểm giao dịch trong cả cửa sổ. Giao dịch đồng thời không nhìn thấy nhau.
*   **Ưu tiên và hàng đợi:** Ngưỡng điểm vận hành 7; điểm ≥14 là Cao. A2/A4 có mẫu còn hit sau kiểm tra ngoại lệ được nhận riêng để rà soát với ưu tiên Trung bình dù chỉ có 4/3 điểm; không nâng thành hard trigger hoặc cộng trùng họ A. Dòng đơn và đóng lô dùng cùng chính sách [tiếp nhận mẫu chia nhỏ](reports/rule_split_pattern_admission.md). B1/B7/C2/E1/E2/P1/T2 có hard trigger khi điều kiện và nguồn được đáp ứng, không có ngoại lệ hợp lệ. Hit bị loại và hit chẩn đoán vẫn lưu bằng chứng; chưa có tự động đóng băng giao dịch. Các SLA/thao tác điều tra ở tài liệu này là định hướng quy trình, không phải tất cả đã được triển khai.

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

### 5. Cổng nghiệm thu rule phụ thuộc nguồn

F1/C4/E2/F2/F3/F4 chỉ được coi là nghiệm thu khi chạy quy trình chấm mù trên bản xuất SME thật, có coverage nguồn theo công ty và cutoff, người rà soát/phân xử độc lập và đạt ngưỡng đã phê duyệt. Fixture mô phỏng chỉ kiểm tra đặc tả. Chi tiết và lệnh chạy tại [reports/rule_source_acceptance.md](reports/rule_source_acceptance.md).
