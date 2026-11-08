# KHUNG QUY TẮC CẢNH BÁO RỦI RO & GIAN LẬN NỘI BỘ

> Tài liệu tham chiếu theo mốc ghi trong tiêu đề. Xem [trạng thái hiện tại](../STATUS.md) trước khi dùng số liệu hoặc kế hoạch cũ.

## 1. Mức ưu tiên điều tra & Thời hạn xử lý (SLA)

| Mức ưu tiên | Thời hạn xử lý (SLA) | Định hướng hành động |
| :--- | :--- | :--- |
| **Cao nhất / Cao** | **24 – 48 giờ** | Kích hoạt điều tra thủ công ngay lập tức, ngăn chặn rủi ro thoát tiền hoặc lừa đảo trực tiếp. |
| **Trung bình** | **Trong tuần** | Thu thập thêm chứng từ đối chiếu, phân tích kết hợp cùng các cờ rủi ro khác. |
| **Thấp** | **Định kỳ / Hàng tháng** | Theo dõi xu hướng, gộp vào báo cáo rủi ro định kỳ, phục vụ làm sạch dữ liệu. |

---

## 2. Danh mục quy tắc kiểm soát chi tiết

### Nhóm A: Vi phạm hạn mức
*Mục tiêu: Phát hiện hành vi chia nhỏ giao dịch (smurfing) hoặc làm tròn số tiền nhằm né các mốc thẩm quyền phê duyệt.*

| Mã | Quy tắc (Rule) | Logic phát hiện | Ngưỡng đề xuất | Mức ưu tiên | Ghi chú vận hành |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A1** | Xé nhỏ giao dịch — cửa sổ ngắn | Quét giao dịch đến cùng người nhận trong cửa sổ trượt 1–3 ngày. | Tổng $\ge 85\%$ ngưỡng duyệt, từ $\ge 2$ giao dịch | **Cao** | Ngưỡng gắn theo cấp duyệt thực tế của người tạo, không dùng một số cố định toàn công ty. |
| **A2** | Xé nhỏ giao dịch — cửa sổ dài | Chạy song song cửa sổ trượt 7–30 ngày cho cùng cặp người tạo – người nhận. | Tổng $\ge$ ngưỡng duyệt / 30 ngày, $\ge 3$ giao dịch | **Trung bình** | Bắt các trường hợp cố tình giãn cách thời gian để né rule cửa sổ ngắn. |
| **A3** | Xé nhỏ theo mạng lưới người nhận | Gộp người nhận theo SĐT / địa chỉ / số tài khoản trùng nhau, tính tổng theo cụm liên kết. | Tương tự A1/A2 nhưng áp dụng trên toàn cụm | **Cao** | Bắt buộc chuẩn hoá dữ liệu chủ trước (G3) để tránh bỏ sót biến thể. |
| **A4** | Tần suất cận ngưỡng theo người tạo | Đếm số giao dịch của 1 người tạo/duyệt nằm sát mốc phê duyệt (80–99% ngưỡng). | $\ge 3$ lần / tháng | **Trung bình** | Tín hiệu độc lập, đo theo hành vi người tạo thay vì người nhận. |
| **A5** | Làm tròn số — baseline động | So số tiền với phân phối lịch sử theo từng danh mục chi phí / nhà cung cấp (NCC). | Kết thúc $\ge 3$ số 0 và lệch $> 2\sigma$ so với baseline | **Trung bình** | Các chi phí định kỳ (thuê nhà, lương) vốn tròn tự nhiên — cần baseline để giảm cảnh báo giả. |
| **A6** | Đối chiếu thanh toán vs hoá đơn gốc | So khớp số tiền thanh toán thực tế với số tiền trên hoá đơn / báo giá gốc. | Hoá đơn gốc lẻ nhưng số tiền chuyển khoản làm tròn cao hơn hẳn | **Cao** | Dấu hiệu rút ruột phần tiền chênh lệch — trọng số rủi ro mạnh hơn A5. |

---

### Nhóm B: Xung đột lợi ích & Đối tượng mờ ám
*Mục tiêu: Nhận diện quan hệ ngầm giữa nhân viên và NCC, cùng các pháp nhân vỏ bọc hoặc tài khoản bị xâm nhập.*

| Mã | Quy tắc (Rule) | Logic phát hiện | Ngưỡng đề xuất | Mức ưu tiên | Ghi chú vận hành |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **B1** | Khớp chéo TK / CCCD nhân viên $\leftrightarrow$ NCC | Đối chiếu số tài khoản ngân hàng và CCCD trên bảng lương với thông tin thụ hưởng/MST của NCC. | Bất kỳ điểm trùng khớp nào | **Cao nhất** | Cờ đỏ nghiêm trọng nhất toàn khung — điều tra thủ công 100% trường hợp. |
| **B2** | Khớp chéo SĐT / địa chỉ / người đại diện | Mở rộng B1 sang SĐT cá nhân, địa chỉ thường trú, người đại diện pháp luật của NCC. | Trùng $\ge 1$ trường: Cờ TB<br>Trùng $\ge 2$ trường: Cờ Cao | **Cao** | Bắt trường hợp nhờ người thân đứng tên pháp nhân hoặc dùng chung đầu mối liên hệ. |
| **B3** | NCC mới thành lập sát giao dịch lớn | So ngày cấp GPKD của NCC với ngày phát sinh đơn hàng / giao dịch thanh toán đầu tiên. | Cách nhau $< 90$ ngày, giao dịch đầu tiên có giá trị lớn | **Cao** | Dấu hiệu điển hình của công ty "vỏ bọc" lập vội để hứng hợp đồng chỉ định thầu. |
| **B4** | Xác minh MST qua cổng đăng ký DN | Đối chiếu MST NCC với cơ sở dữ liệu công khai về tình trạng hoạt động và mã ngành. | MST ngừng hoạt động / đóng mã số thuế / ngành nghề không liên quan | **Cao** | Quét định kỳ hàng quý trên toàn bộ Master Data NCC, không chỉ quét lúc tạo mới. |
| **B5** | Nhiều NCC trùng địa chỉ / SĐT / đại diện | Gộp NCC theo các định danh liên hệ; đếm số lượng pháp nhân độc lập trong cùng một cụm. | $\ge 2$ mã NCC khác nhau trong cùng cụm liên kết | **Trung bình** | Một cá nhân dựng nhiều công ty "quân xanh quân đỏ" để hợp thức hóa chào giá cạnh tranh. |
| **B6** | Tài khoản "ngủ đông" đột ngột giao dịch lớn | Theo dõi NCC không phát sinh giao dịch trong 6–12 tháng đột ngột có phát sinh thanh toán dồn dập. | Giá trị giao dịch $>$ Percentile 90 lịch sử của chính NCC đó | **Cao** | Đo lường mức độ bất thường tương đối theo lịch sử riêng của từng NCC, không dùng số tuyệt đối. |
| **B7** | Đổi TK ngân hàng sát kỳ thanh toán | Gắn cờ khi tài khoản nhận tiền của NCC bị thay đổi ngay trước một đợt giải ngân lớn. | Đổi trong vòng $\le 14$ ngày trước thanh toán (đặc biệt qua email) | **Cao nhất** | Mẫu hình lừa đảo qua email doanh nghiệp (BEC) — nguy cơ mất tiền trực tiếp. |

---

### Nhóm C: Bất thường thời gian & Phân quyền
*Mục tiêu: Đánh giá sự vi phạm nguyên tắc tách biệt nhiệm vụ (SoD) và các can thiệp bất thường ngoài quy trình chuẩn.*

| Mã | Quy tắc (Rule) | Logic phát hiện | Ngưỡng đề xuất | Mức ưu tiên | Ghi chú vận hành |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **C1** | Bút toán ngoài giờ hành chính | Gắn cờ bút toán tạo/duyệt sau 22h, trước 8h, hoặc vào ngày nghỉ, lễ tết. | Ngoài khung 8h–19h các ngày làm việc tiêu chuẩn | **Trung bình** | Chỉ phát huy tác dụng khi kết hợp cùng các rule khác qua chấm điểm rủi ro (G1). |
| **C2** | Vi phạm SoD: Cùng người tạo & duyệt | Đối chiếu `user_id` người lập chứng từ với `user_id` người phê duyệt trên cùng một giao dịch. | Trùng `user_id` (bất kể giá trị lớn hay nhỏ) | **Cao nhất** | Vi phạm nguyên tắc kiểm soát phân quyền cơ bản — cần chặn cứng ở tầng hệ thống ERP. |
| **C3** | Thời gian duyệt quá ngắn | Đo khoảng cách thời gian giữa thời điểm tạo yêu cầu và thời điểm bấm nút phê duyệt. | $< 60$ giây đối với giao dịch yêu cầu duyệt cấp cao | **Cao** | Dấu hiệu duyệt hình thức, không mở chứng từ đính kèm để thẩm định thực tế. |
| **C4** | Hoạt động từ tài khoản đang nghỉ phép | Đối chiếu nhật ký hoạt động hệ thống với lịch nghỉ phép đã được phê duyệt trên hệ thống HR. | Có log tạo/duyệt trong thời gian nghỉ phép | **Cao** | Nghi vấn chia sẻ tài khoản trái quy định hoặc tài khoản bị chiếm đoạt. |

---

### Nhóm D: Phân tích Benford
*Mục tiêu: Công cụ sàng lọc thống kê số học nhằm khoanh vùng các tập dữ liệu có dấu hiệu bị can thiệp nhân tạo.*

| Mã | Quy tắc (Rule) | Logic phát hiện | Ngưỡng đề xuất | Mức ưu tiên | Ghi chú vận hành |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **D1** | Chữ số đầu tiên (First digit) | So sánh tần suất xuất hiện số 1–9 ở vị trí đầu với phân phối lý thuyết Benford. | Kiểm định $\chi^2$ (Chi-square) hoặc Z-stat, $p < 0.05$ | **Trung bình** | Cần cỡ mẫu tối thiểu từ 300 đến 1.000 bản ghi để kết quả có ý nghĩa thống kê. |
| **D2** | Chữ số thứ hai (Second digit) | Kiểm định tần suất chữ số ở vị trí thứ hai tương tự D1. | Z-stat, $p < 0.05$ | **Thấp** | Chỉ dùng hỗ trợ củng cố tín hiệu từ D1, không kết luận độc lập. |
| **D3** | Hai chữ số đầu — né ngưỡng phê duyệt | Kiểm tra tần suất bất thường ở các cặp số nằm ngay dưới mốc tròn (ví dụ: 19, 49, 99...). | Tần suất thực tế vượt Benford lý thuyết $> 20\%$ | **Cao** | Tín hiệu rõ nhất về hành vi cố tình ghìm giá trị giao dịch dưới mốc xét duyệt. |
| **D4** | Lặp số cuối (000, 500, 999) | Thống kê tỷ lệ giao dịch có các số đuôi tròn hoặc số lặp bất thường. | Tỷ lệ thực tế vượt $> 2$ lần so với kỳ vọng ngẫu nhiên | **Trung bình** | Giao dịch thương mại thực tế thường có đuôi số lẻ do đơn giá và thuế. |
| **D5** | Độ lệch MAD & Khóa chu trình | Đo lường độ lệch tuyệt đối trung bình (MAD) so với ngưỡng thực nghiệm của Nigrini. | • $0.000 - 0.006$: Tốt<br>• $0.006 - 0.012$: Chấp nhận<br>• $0.012 - 0.015$: Biên<br>• $> 0.015$: Khóa điều tra | **Cao** | Đánh giá độc lập cho kiểm định 1 chữ số và 2 chữ số, không dùng chung một mốc. |
| **D6** | Phân tách theo nhân viên / NCC | Chạy bộ kiểm định D1–D5 trên từng tập dữ liệu con (theo phòng ban, người tạo, NCC). | Áp dụng ngưỡng D1–D5 cho từng nhóm riêng lẻ | **Cao** | Gộp dữ liệu toàn công ty sẽ làm loãng tín hiệu; gian lận thường tập trung ở nhóm nhỏ. |

---

### Nhóm E: Nhân sự ma & NCC ma
*Mục tiêu: Rà soát tính toàn vẹn của danh mục đối tác và nhân sự nhằm triệt tiêu thất thoát chi phí gián tiếp.*

| Mã | Quy tắc (Rule) | Logic phát hiện | Ngưỡng đề xuất | Mức ưu tiên | Ghi chú vận hành |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **E1** | Nhận lương nhưng không chấm công | Đối chiếu dữ liệu máy chấm công / log làm việc với danh sách chi lương thực tế. | 0 lượt chấm công trong kỳ nhưng vẫn phát sinh bút toán lương | **Cao nhất** | Dấu hiệu kinh điển của "nhân viên ma" (ghost employee). |
| **E2** | Chi trả lương sau ngày nghỉ việc | Đối chiếu ngày chấm dứt HĐLĐ trên HR với ngày chi trả lương của kế toán. | Bút toán lương phát sinh sau ngày nghỉ việc chính thức | **Cao nhất** | Lệch pha quy trình offboarding giữa HR và Kế toán bị lợi dụng để rút ruột quỹ. |
| **E3** | So khớp mờ tên NCC (Fuzzy matching) | Dùng thuật toán so khớp chuỗi (Levenshtein / Jaro-Winkler) tìm NCC có tên gần giống nhau. | Điểm tương đồng $> 85\%$ nhưng mang mã NCC khác nhau | **Trung bình** | Phát hiện cố tình tạo nhiều mã đối tác để phân tán chi tiêu hoặc gian lận chào thầu. |
| **E4** | NCC dùng chung thông tin liên hệ | Quét toàn bộ danh mục đối tác nhằm tìm các trường hợp trùng lặp SĐT, địa chỉ, tài khoản. | $\ge 2$ mã NCC trùng $\ge 1$ trường thông tin cơ bản | **Trung bình** | Định kỳ rà soát như một quy trình vệ sinh dữ liệu hệ thống (Master Data Scrubbing). |

---

### Nhóm F: Rủi ro báo cáo tài chính
*Mục tiêu: Giám sát nguy cơ thao túng kết quả tài chính, ghi khống doanh thu và can thiệp quản trị theo khung COSO / ISA 240.*

| Mã | Quy tắc (Rule) | Logic phát hiện | Ngưỡng đề xuất | Mức ưu tiên | Ghi chú vận hành |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **F1** | Bút toán thủ công cuối kỳ | Lọc các bút toán sổ nhật ký thủ công (Manual Journal Entries) sát thời điểm đóng sổ. | Tạo trước ngày chốt sổ 3–5 ngày, giá trị $>$ ngưỡng trọng yếu | **Cao** | Cờ đỏ kinh điển của gian lận thổi phồng doanh thu hoặc che giấu chi phí. |
| **F2** | Can thiệp quản trị (Management Override) | Lọc các bút toán do tài khoản cấp quản lý can thiệp vượt quyền kiểm soát chuẩn. | Bất kỳ bút toán ghi đè/vượt quyền nào ngoài quy trình | **Cao** | Rủi ro trọng yếu hàng đầu theo chuẩn mực kiểm toán ISA 240. |
| **F3** | Khoảng trống / Trùng số chứng từ | Kiểm tra tính liên tục của dãy số hóa đơn, phiếu thu, phiếu chi nội bộ. | Tồn tại khoảng trống (gap) hoặc số bị trùng không giải trình | **Trung bình** | Cần đối chiếu với danh sách hủy số hợp lệ trước khi đưa ra kết luận. |
| **F4** | Doanh thu ghi nhận vs Dòng tiền thực | So khớp doanh thu ghi nhận trên sổ với dòng tiền thực tế về tài khoản ngân hàng. | Chênh lệch công nợ kéo dài $> 60$ ngày không có giải trình hợp lý | **Trung bình** | Phát hiện doanh thu ảo được ghi nhận để làm đẹp chỉ tiêu tăng trưởng. |

---

## 3. Khung vận hành hệ thống cảnh báo (Nhóm G)

### G1. Mô hình tính điểm rủi ro tổng hợp (Risk Scoring Model)
* **Triết lý vận hành:** Không sử dụng từng rule đơn lẻ để đưa ra kết luận hoặc khóa luồng nghiệp vụ nhằm hạn chế tình trạng **Alert Fatigue** (quá tải cảnh báo giả khiến đội ngũ kiểm soát bỏ qua rủi ro thực tế).
* **Cơ chế cộng dồn:** Mỗi rule đóng góp một số điểm rủi ro cụ thể ($10 - 100$ điểm). Giao dịch hoặc nhân sự chỉ được nâng lên mức ưu tiên **Cao** hoặc kích hoạt điều tra chuyên sâu khi tổng điểm vượt ngưỡng cảnh báo thông qua sự kết hợp của nhiều cờ độc lập (ví dụ: vừa cận ngưỡng phê duyệt, vừa tạo ngoài giờ, vừa được duyệt thần tốc).

### G2. Quy trình xử lý cảnh báo (Case Management)
* **Xác định chủ sở hữu (Ownership):** Mỗi cảnh báo khi phát sinh phải được tự động định tuyến đến một chuyên viên kiểm soát chịu trách nhiệm thụ lý chính.
* **Thời hạn xử lý (SLA):** Ràng buộc thời gian đóng vụ việc theo đúng mức độ nghiêm trọng:
  * *Mức Cao/Cao nhất:* Hoàn thành phân tích sơ bộ trong 24–48 giờ.
  * *Mức Trung bình:* Hoàn thành trong 5–7 ngày làm việc.
  * *Mức Thấp:* Tổng hợp đánh giá theo kỳ báo cáo tháng/quý.
* **Chuẩn hóa kết luận:** Mọi case xử lý xong đều phải gắn 1 trong 3 trạng thái kết luận để lưu vết kiểm toán:
  1. *Gian lận / Vi phạm thực tế (Confirmed Fraud / Non-compliance).*
  2. *Cảnh báo giả (False Positive) kèm lý do nghiệp vụ.*
  3. *Cần bổ sung hồ sơ chứng minh (Inconclusive / Pending documentation).*

### G3. Chuẩn hoá dữ liệu chủ (Master Data Management)
* Trước khi chạy các quy tắc so khớp chéo (B1, B2, B5, E3, E4), dữ liệu phải đi qua đường ống tiền xử lý (Data Cleansing Pipeline):
  * **Số điện thoại:** Đưa về chuẩn E.164 hoặc một định dạng chuẩn chung (ví dụ: đồng nhất mã quốc tế, bỏ dấu cách và ký tự đặc biệt).
  * **Địa chỉ:** Tách bạch các trường đơn vị hành chính (Tỉnh/Thành phố, Quận/Huyện, Xã/Phường), chuẩn hóa các từ viết tắt phổ biến.
  * **Tên cá nhân / Doanh nghiệp:** Chuyển toàn bộ về chữ in hoa không dấu, loại bỏ tiền tố pháp nhân (ví dụ: `CTY TNHH`, `CONG TY CO PHAN`, `DNTN`) trước khi thực hiện thuật toán so khớp mờ.

### G4. Thử nghiệm quá khứ (Back-testing) & Hiệu chỉnh định kỳ
* **Kiểm định lại hồ sơ cũ:** Định kỳ hàng quý, áp dụng toàn bộ bộ quy tắc vào tập dữ liệu lịch sử chứa các vụ việc gian lận đã được kết luận để đo lường độ nhạy.
* **Đo lường chỉ số hiệu năng:**
  * *Tỷ lệ phát hiện thực (Recall):* Đảm bảo hệ thống bắt được các trường hợp gian lận cốt lõi.
  * *Tỷ lệ cảnh báo chính xác (Precision):* Giảm thiểu tối đa số lượng cảnh báo giả.
* **Tinh chỉnh tham số:** Các ngưỡng khởi tạo (cửa sổ trượt, tỷ lệ %, độ lệch chuẩn $\sigma$, ngưỡng Benford MAD) cần được điều chỉnh linh hoạt theo từng đặc thù ngành và quy mô dữ liệu sau mỗi 1–2 chu kỳ vận hành thực tế.