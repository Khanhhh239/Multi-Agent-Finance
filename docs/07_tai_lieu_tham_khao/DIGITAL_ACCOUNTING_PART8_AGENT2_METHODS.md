# PHẦN 8 — ĐÁNH GIÁ PHƯƠNG PHÁP, DỮ LIỆU VÀ BÀI TOÁN KHÓ CỦA AGENT 2

Ngày kiểm chứng: 13/10/2026. Phần này nối tiếp Phần 6 (dữ liệu Agent 2); những gì Phần 6 đã kiểm chứng không lặp lại ở đây.

**Quy ước độ tin cậy.** [Đ] là điều tôi đã đọc trong toàn văn tài liệu gốc. [T] là điều tôi chỉ có từ trang tóm tắt hoặc kết quả tìm kiếm, chưa đối chiếu toàn văn. [N] là suy luận hoặc đề xuất thiết kế của tôi, không phải số liệu có nguồn. Mọi con số tính lại từ số liệu của nguồn được ghi là tính lại.

---

## 0. Kết luận trước

**Thiết kế tham khảo có hướng đúng nhưng chưa phải phương án tốt nhất cho doanh nghiệp nhỏ.** Ý tưởng cốt lõi (quy tắc cộng mô hình không giám sát cộng phản hồi người dùng, người giữ quyết định cuối) là hợp lý và có nền nghiên cứu. Có bảy điểm cần sửa hoặc bổ sung:

1. **Autoencoder không nên là mô hình chính duy nhất.** Chuẩn đánh giá ADBench (57 bộ dữ liệu, 30 thuật toán) cho thấy không thuật toán không giám sát nào vượt trội có ý nghĩa thống kê; các mô hình học sâu không giám sát như DeepSVDD và DAGMM kém hơn các phương pháp nông [Đ]. Các thí nghiệm trên sổ cái đều huấn luyện riêng cho từng doanh nghiệp và dùng dữ liệu một năm ở quy mô hàng chục đến hàng trăm nghìn dòng [Đ]; doanh nghiệp nhỏ thường thiếu quy mô đó.
2. **Lớp đồ thị nên là truy vấn tất định, bỏ mạng nơ-ron đồ thị khỏi đường găng.** Trên đồ thị của một doanh nghiệp nhỏ (vài trăm nhà cung cấp, vài chục nhân viên) không có gì để một mạng nơ-ron học thêm. Thí nghiệm GADBench cho thấy cây quyết định kết hợp đặc trưng láng giềng có thể thắng các mạng nơ-ron đồ thị chuyên cho phát hiện bất thường [T].
3. **Con số "độ chính xác" trong các bài sổ cái không đáng tin để trích làm mục tiêu.** Bài Schreyer (2017) chỉ đạt F1 0,33 và 0,17 dù bất thường được chèn là loại dễ nhất (giá trị thuộc tính chưa từng xuất hiện) [Đ]. Bài DFKI (2026) chèn bất thường chỉ bên trong danh sách của chính các quy tắc được đánh giá, nên quy tắc đạt độ phủ 100% theo cấu tạo [Đ].
4. **Cái cần thắng không phải là F1 mà là ngân sách cảnh báo.** Phương án tốt nhất trong bài DFKI vẫn gắn cờ 4,8% bút toán (tính lại), tương đương khoảng 47 cảnh báo mỗi tuần với doanh nghiệp 51.000 bút toán một năm, gấp gần mười lần ngân sách 5 cảnh báo mỗi tuần (mục 1.4).
5. **Phản hồi một chạm phải được thiết kế chặt hơn câu mô tả "nới ngưỡng".** Có phương pháp có lý thuyết cho việc này (Active Anomaly Discovery), và có ba rủi ro cần xử lý: nhãn chỉ có ở cảnh báo đã hiển thị, người phản hồi có thể là người gian lận, nhãn rất thưa (mục 1.5).
6. **Còn sót các phương pháp có độ chính xác cao hơn và không cần huấn luyện:** đối chiếu chéo danh mục (nhà cung cấp so với nhân viên theo tài khoản ngân hàng, địa chỉ, điện thoại, mã số thuế), đối chiếu hoá đơn điện tử và trạng thái mã số thuế (đặc thù Việt Nam), đối chiếu ba bên đơn hàng–nhận hàng–hoá đơn, mức cơ sở theo từng thực thể và phát hiện điểm gãy, gộp cảnh báo theo hồ sơ vụ việc (mục 2).
7. **Hai câu trong bản nháp gửi lại vẫn còn lỗi cũ** đã được sửa ở Phần 6: tỷ lệ 44% không phải cao nhất mọi nhóm quy mô (nhóm từ 100 nhân sự là 52%), và câu "học máy cổ điển thường vượt trội mạng nơ-ron đồ thị trên đồ thị thưa" chỉ đúng nguyên văn cho Elliptic với số 0,796 so với 0,628. Nguồn "70% thời gian cho báo động giả" là blog của một nhà cung cấp thương mại (FluxForce AI), chưa phải nguồn học thuật; nên thay bằng nguồn kiểm chứng được hoặc ghi rõ tính chất.

---

## 1. Đánh giá từng thành phần của thiết kế tham khảo

### 1.1. Thư viện quy tắc cứng

Bảng dưới đánh giá từng quy tắc về cơ sở bằng chứng và nguy cơ báo sai ở doanh nghiệp nhỏ. Cột "Điều chỉnh" là đề xuất [N].

| Quy tắc | Cơ sở | Nguy cơ báo sai ở doanh nghiệp nhỏ | Điều chỉnh |
|---|---|---|---|
| Sát ngưỡng phê duyệt | Nghiên cứu mua sắm công ở Ý, Séc, Thụy Điển và Mỹ ghi nhận giá trị hợp đồng dồn ngay dưới ngưỡng; các bài này chứng minh thao túng và đấu thầu kém cạnh tranh, không chứng minh gian lận [T] | Ngưỡng của công ty giả định; bảng giá cố định tạo giá trị tự nhiên sát ngưỡng | Kiểm tra lượng dồn bất thường dưới ngưỡng theo từng người lập hoặc nhà cung cấp qua nhiều sự kiện, không gắn cờ từng giao dịch đơn lẻ |
| Thanh toán trùng | Tất định, kiểm tra được; thuộc nhóm thanh toán hoá đơn (31% số vụ ở tổ chức dưới 100 nhân sự theo ACFE 2024, Phần 6) [Đ] | Khoản định kỳ hợp lệ (thuê nhà, lương, trả góp) giống hệt nhau | Loại trừ chuỗi có chu kỳ đều; so khớp mờ số hoá đơn, số tiền, ngày |
| Bút toán cuối kỳ | Là một trong các phép thử bút toán theo chuẩn kiểm toán, dẫn trong bài DFKI [Đ] | Khoá sổ, khấu hao, phân bổ cuối kỳ vốn là bút toán tay hợp lệ | Chỉ gắn cờ bút toán tay thiếu chứng từ, lớn so với mức thường lệ của chính tài khoản đó |
| Ngoài giờ, cuối tuần | Phép thử J4 trong bài DFKI [Đ] | Chủ doanh nghiệp và kế toán nhỏ thường làm cuối tuần | Chỉ là hệ số điều chỉnh, so với thói quen của từng người, không đứng một mình |
| Số tiền tròn | Chọn chữ số theo thói quen là dấu hiệu kiểm toán kinh điển; chưa đọc nguồn gốc [N] | Giá đồng tiền Việt Nam tròn tự nhiên (thuê nhà, lương) | Đo độ tròn so với phân phối của chính nhà cung cấp, kết hợp tín hiệu khác |
| Định luật Benford | Chỉ áp dụng cho dữ liệu hình thành tự nhiên; có nguy cơ báo sai cao ở mẫu nhỏ và vừa (Barney và Schulzke 2016); nguồn thực hành khuyến cáo trên khoảng 500 bản ghi [T, nguồn thứ cấp] | Nhiều tài khoản trong doanh nghiệp nhỏ có quá ít bút toán | Chỉ chạy cho tài khoản đủ lớn, ở mức tổng hợp; coi là tín hiệu phụ, không phát cảnh báo riêng |
| Tách khoản dưới ngưỡng | Cùng bản chất với sát ngưỡng; ACFE nêu trong nhóm chi phí khai khống [Đ, Phần 6] | Đơn hàng nhỏ lặp lại hợp lệ cùng nhà cung cấp | Cộng gộp trong cửa sổ thời gian theo cùng người yêu cầu và nhà cung cấp |
| Nhà cung cấp trùng tài khoản, địa chỉ, điện thoại với nhân viên | Là kịch bản nhà cung cấp ma kinh điển (F1 ở Phần 6) | Rất thấp | Ưu tiên cao nhất vì chính xác và không cần huấn luyện |
| Một người lập, duyệt và chi | Nguyên tắc phân tách nhiệm vụ | Doanh nghiệp 2 đến 3 người bắt buộc vi phạm, báo sai gần 100% | Phải cấu hình vai trò; chủ doanh nghiệp duyệt là hợp lệ; chỉ báo khi vượt vai trò đã khai |
| Đứt số chứng từ | Phép thử thông dụng | Hoá đơn điện tử huỷ và thay thế là hợp lệ | Chỉ báo khi không có chứng từ huỷ hoặc thay thế tương ứng |

**Bằng chứng định lượng về báo sai của quy tắc thuần tuý.** Trong bài DFKI, bốn phép thử bút toán trên 51.076 bút toán tổng hợp gắn cờ 10.592 bút toán (10.019 sai cộng 573 đúng), tức 20,7% (tính lại) [Đ]. Con số này nhỏ hơn thực tế vì dữ liệu sinh ngẫu nhiên đơn giản, nhưng cho thấy quy tắc cứng không thể là kênh cảnh báo trực tiếp cho doanh nghiệp nhỏ.

### 1.2. Autoencoder trên bút toán

**Cách hoạt động (Schreyer và cộng sự 2017) [Đ].** Mỗi bút toán được mã hoá thành vectơ nhị phân (6 hoặc 10 thuộc tính phân loại, 401 hoặc 576 chiều sau khi mã hoá). Mạng nén xuống ba nơ-ron rồi tái tạo; lỗi tái tạo đo mức bất thường theo kiểu *đồng xuất hiện* (tổ hợp thuộc tính hiếm). Điểm cuối là AS = α · RE + (1 − α) · AP, trong đó RE là lỗi tái tạo chuẩn hoá và AP là điểm xác suất giá trị thuộc tính (đo *giá trị hiếm*), với α = 0,3 trong thí nghiệm.

**Cần huấn luyện riêng từng doanh nghiệp?** Có. Mỗi bộ dữ liệu là toàn bộ bút toán một năm của một hệ thống SAP, một mô hình riêng cho mỗi bộ (tối đa 2.000 vòng huấn luyện; mô hình tốt nhất có 17 lớp ẩn). Bài DFKI nêu rõ huấn luyện riêng cho từng hợp đồng kiểm toán và không nhắm tới mô hình dùng chung [Đ]. Bài Schultz và Tropmann-Frick (2020) huấn luyện từng autoencoder trên từng tài khoản và cho thấy cách này vẫn hoạt động với tập dữ liệu nhỏ [T, qua tóm tắt trong bài DFKI]; đây là hướng đáng thử cho doanh nghiệp nhỏ.

**Độ chính xác đã công bố [Đ].** Bất thường chèn: 95 bút toán trong 307.457 dòng (bộ A) và 100 trong 172.990 dòng (bộ B), tức 0,03% và 0,06%. Khi ép phục hồi 100% bất thường chèn, kiến trúc tốt nhất đạt precision 0,197 và F1 0,329 (bộ A), precision 0,093 và F1 0,170 (bộ B). Tôi không trích Bảng 3 so với PCA, HDBSCAN, LOF, OC-SVM vì văn bản trích xuất bị lệch cột.

**Hai điều quan trọng cho thiết kế.**
- Bất thường chèn là loại dễ nhất: giá trị thuộc tính chưa từng xuất hiện hoặc tổ hợp chưa từng xuất hiện. Điều đó không phải gian lận thật; kết quả thật sẽ thấp hơn.
- Khi tác giả xem lại các bút toán gắn cờ không phải chèn, phần lớn là nhà cung cấp hiếm, tiền tệ hiếm, lỗi hạch toán sai tài khoản, mã thuế hiếm, bút toán thiếu tiền tệ [Đ]. Đó là bất thường *thống kê*, không phải gian lận. Vì vậy lớp học máy phải đứng sau bộ lọc có ý nghĩa nghiệp vụ, hoặc xếp hạng chung với tín hiệu gian lận.

**Đánh giá.** Autoencoder là ứng viên hợp lệ, không phải lựa chọn hiển nhiên. Trong bài DFKI, Isolation Forest đạt recall và ROC-AUC cao nhất, autoencoder đạt precision và F1 cao nhất nhưng bỏ sót nhiều (mô hình dùng ngưỡng phần trăm thứ 99 của lỗi tái tạo, nên mặc định luôn gắn cờ khoảng 1% bút toán bất kể có gian lận hay không) [Đ]. Điểm này cho thấy ngưỡng phần trăm cố định không thích ứng như câu "không dựa trên ngưỡng cố định áp dụng chung" của bản nháp mô tả; thay bằng hiệu chỉnh conformal và ngân sách cảnh báo (mục 1.4).

### 1.3. Lớp đồ thị: tất định là chính, mạng nơ-ron đồ thị chỉ là bổ trợ

- **Đồ thị tất định.** Bản nháp đã đúng ở quyết định này. Quan hệ như "nhà cung cấp dùng chung tài khoản ngân hàng với nhân viên" là truy vấn trên bảng, có giải thích trực tiếp, không cần huấn luyện.
- **Mạng nơ-ron đồ thị.** GADBench (NeurIPS 2023) so 29 mô hình trên 10 bộ dữ liệu phát hiện bất thường trên đồ thị có giám sát; kết luận trung tâm là cây quyết định tổng hợp (Random Forest, XGBoost) kết hợp tổng hợp đặc trưng láng giềng đơn giản có thể thắng các mạng nơ-ron đồ thị mới nhất chuyên cho nhiệm vụ này; bản cuối đã làm nhẹ câu chữ từ "thắng" thành "có thể thắng" [T]. Phạm vi của benchmark là phát hiện nút bất thường có giám sát trên đồ thị tĩnh.
- **Chỗ mạng nơ-ron đồ thị thật sự giúp.** Egressy và cộng sự (AAAI 2024) cải thiện F1 lớp thiểu số tới 30% khi phát hiện rửa tiền trên đồ thị đa cạnh có hướng, nhờ ba cải tiến (đánh số cổng, định danh gốc, truyền thông điệp ngược) [T]. Mẫu rửa tiền nhiều bước qua nhiều tài khoản không phải gian lận nội bộ của doanh nghiệp nhỏ.
- **Kết luận.** Đưa mạng nơ-ron đồ thị ra khỏi giai đoạn một. Nếu cần ở giai đoạn sau, thử trước cây quyết định với đặc trưng đồ thị (bậc, thành phần liên thông, số tài khoản dùng chung) trước khi huấn luyện mạng nơ-ron đồ thị. Elliptic không kiểm chứng được khả năng khái quát sang đồ thị doanh nghiệp (Phần 6 đã nêu).

### 1.4. Bộ tổng hợp, SHAP và bài toán ngân sách cảnh báo

**Tính toán cho thấy ràng buộc thật.** Bài DFKI đo kết hợp quy tắc và học máy trên dữ liệu tổng hợp [Đ]:
- Giao hai danh sách (H1): sai giảm từ 10.019 xuống 1.214 (tính lại: 1.881 trừ 667), bỏ sót 19 trong 573 bất thường chèn.
- Dùng kết quả quy tắc làm đặc trưng cho Isolation Forest (H2): phục hồi đủ 573 bất thường, sai còn 1.881.

Với H2: tổng gắn cờ 2.454 trên 51.076 bút toán, tức 4,8% (tính lại). Doanh nghiệp có 5.000 bút toán một năm sẽ nhận khoảng 240 cảnh báo, gần ngân sách 260 một năm (5 mỗi tuần); doanh nghiệp 20.000 bút toán sẽ nhận khoảng 960, gấp gần bốn lần. Tỷ lệ gắn cờ phải được *thiết kế theo ngân sách*, không nhận từ mô hình.

**Giới hạn của chính tỷ lệ cơ sở [N].** Giả sử bộ phát hiện tốt (độ nhạy 90%) và tỷ lệ gian lận 0,1% số bút toán: nếu tỷ lệ báo sai là 5%, precision chỉ khoảng 1,8%; nếu 1%, khoảng 8,3%; để đạt khoảng 47% cần tỷ lệ báo sai khoảng 0,1%. Do đó cảnh báo nên đặt ở mức *hồ sơ vụ việc* (theo nhà cung cấp, nhân viên, tài khoản) thay vì từng bút toán: một nhà cung cấp ma sinh nhiều khoản thanh toán, nên gộp nhiều bút toán thành một hồ sơ vừa giảm số cảnh báo vừa tăng bằng chứng.

**Kiểm soát tỷ lệ phát hiện sai.** Bates, Candès và cộng sự (Annals of Statistics 2023) coi phát hiện ngoại lai là bài toán kiểm định nhiều giả thuyết: tính p-giá trị conformal so với tập tham chiếu, rồi áp dụng quy trình Benjamini–Hochberg để kiểm soát tỷ lệ phát hiện sai (FDR) với bảo đảm hữu hạn mẫu [T]. Với bài toán này:
- Tác dụng: thay ngưỡng phần trăm cố định bằng ngưỡng có ý nghĩa thống kê, biến động theo số lượng bút toán mới.
- Giới hạn trung thực: FDR ở đây tính theo "giống hay không giống phân phối bình thường của chính doanh nghiệp", không phải theo "có phải gian lận". Gian lận đã tồn tại trong lịch sử sẽ được xem là bình thường. Vì vậy không được mô tả đây là bảo đảm độ chính xác gian lận.
- Điều kiện trao đổi được (exchangeability) bị vi phạm khi dữ liệu trôi theo mùa; cần dạng có trọng số theo thời gian (Barber, Candès, Ramdas, Tibshirani, Annals of Statistics 2023) [T].

**Giải thích.** SHAP trên autoencoder khá nặng và có thể không ổn định; Tritscher và cộng sự dùng Kernel SHAP cho autoencoder trên dữ liệu ERP và báo cáo SHAP ổn định hơn LIME [T]. Đối với doanh nghiệp nhỏ, nên dùng lời giải thích gốc của mô hình khi có: tín hiệu quy tắc, xác suất đuôi theo từng đặc trưng của ECOD, lỗi tái tạo theo từng thuộc tính của autoencoder; chỉ dùng SHAP khi cần.

### 1.5. Vòng phản hồi một chạm

Bản nháp mô tả: tín hiệu bị đánh dấu báo động giả thì nới ngưỡng. Đây là heuristic dễ hiểu nhưng chưa đủ. Có ba vấn đề và hướng xử lý.

**Phương pháp có nền tảng.** Active Anomaly Discovery (Das, Wong, Dietterich, Fern, Emmott, ICDM 2016): vòng lặp trong đó mô hình chọn một mẫu hiển thị, chuyên gia gán nhãn bất thường hoặc bình thường, mô hình cập nhật; mục tiêu là tối đa số bất thường thật trong B lần xem. Bản mở rộng cho Isolation Forest nhận phản hồi nhị phân đơn giản [T]. Đây chính là bài toán "ngân sách xem hữu hạn" của doanh nghiệp nhỏ.

**Ba vấn đề cần thiết kế [N, có tham chiếu nghiên cứu chung về nhãn chọn lọc [T]].**
1. **Nhãn chọn lọc.** Chỉ cảnh báo đã hiển thị mới có nhãn; mô hình học từ chính quyết định của nó nên sai lệch tích luỹ. Các nghiên cứu về gian lận thương mại điện tử nêu rõ điều này và khuyến nghị kết hợp học dưới thiên lệch chọn mẫu hoặc thăm dò bằng mẫu ngẫu nhiên [T]. Đề xuất: mỗi kỳ chọn một mẫu nhỏ giao dịch không bị gắn cờ cho người dùng xem như kiểm toán đột xuất để ước lượng bỏ sót.
2. **Người phản hồi có thể là người gian lận hoặc thông đồng.** Nhóm dưới 100 nhân sự chỉ có kiểm toán nội bộ ở 40%, rà soát quản lý ở 39% (ACFE 2024, Phần 6), và gian lận do chủ sở hữu hoặc lãnh đạo gây tổn thất lớn hơn 7 lần. Do đó: ghi nhật ký mọi phản hồi, phân biệt vai trò (chủ doanh nghiệp, kế toán trưởng, nhân viên), không cho phép phản hồi của một người tắt hẳn quy tắc mức nghiêm trọng cao, đặt sàn cho quy tắc tất định.
3. **Nhãn rất thưa.** Với 5 cảnh báo một tuần thì một năm chỉ có khoảng 260 phản hồi, trong đó gian lận thật rất ít. Vì vậy không thể huấn luyện có giám sát theo từng doanh nghiệp. Hiệu chỉnh ở mức *loại tín hiệu* (vài chục tham số), ví dụ ước lượng tỷ lệ báo sai theo Beta–Binomial với giá trị tiên nghiệm lấy từ dữ liệu gộp nhiều doanh nghiệp. ADBench cho thấy chỉ với 1% nhãn bất thường, đa số phương pháp bán giám sát vượt phương pháp không giám sát tốt nhất [Đ], nhưng 1% đó của một doanh nghiệp nhỏ có thể là không có nhãn nào.

Cũng nên tách "đã kiểm tra, hợp lệ" khỏi "bỏ qua vì không có thời gian": hai trạng thái này khác nhau về nghĩa huấn luyện.

### 1.6. Vai trò của mô hình ngôn ngữ

Bản nháp đặt mô hình ngôn ngữ chỉ ở vai trò diễn giải là đúng, và AuditCopilot (arXiv 2512.02726) cung cấp bằng chứng ủng hộ [T, bảng số qua tóm tắt công cụ; bản tóm tắt tự ghi nhận có chỗ không khớp, cần đối chiếu bảng gốc trước khi trích]:
- Chỉ dùng câu lệnh nhắc, không cập nhật trọng số; câu lệnh gồm thống kê tập dữ liệu và kết quả Isolation Forest.
- Trên bộ sổ cái ẩn danh, kết quả giữa các mô hình chênh rất lớn: Gemma-7B đạt precision 0,89 và recall 0,78 (F1 0,83) còn Llama-3.1-8B chỉ đạt F1 0,28. Bỏ gợi ý của Isolation Forest thì precision của Gemma-7B còn 0,14.
- Bộ sổ cái thật *không có nhãn gian lận*; nhãn giả lấy từ phép thử bút toán và đã được khách hàng xác nhận, nên các số đo mức độ khớp với quy tắc, không phải gian lận.
- Các tác giả nêu rủi ro: ảo giác, thiên lệch tự động hoá, tiêm lệnh qua các trường văn bản tự do, tính tái lập khi mô hình đổi; tính trung thực của lời giải thích không được đánh giá.

**Hệ quả thiết kế [N].** Mô hình ngôn ngữ chỉ diễn đạt lại bằng chứng có cấu trúc đã tính sẵn (mẫu câu trước, mô hình chỉ làm mượt); mọi con số trong lời giải thích phải lấy từ dữ liệu, kiểm tra đối chiếu sau khi sinh; không đưa trường văn bản tự do chưa làm sạch vào câu lệnh; ẩn danh hoá tên người trước khi gọi dịch vụ ngoài. Việc chuyển dữ liệu cá nhân ra nước ngoài khi gọi dịch vụ đám mây có quy định theo Nghị định 13/2023/NĐ-CP; điều khoản cụ thể chưa kiểm chứng ở đây, cần hỏi chuyên gia pháp lý.

---

## 2. Phương pháp còn sót hoặc nên đánh giá lại

Cột "Huấn luyện theo doanh nghiệp" trả lời câu hỏi cần tinh chỉnh hay chỉ suy luận. Cột "Ưu tiên" là đề xuất [N].

| # | Phương pháp | Cách hoạt động | Huấn luyện theo doanh nghiệp? | Độ chính xác đã biết | Ưu tiên |
|---|---|---|---|---|---|
| A | Đối chiếu chéo danh mục (nhà cung cấp, nhân viên, khách hàng) | So khớp chính xác và mờ theo tài khoản ngân hàng, địa chỉ, điện thoại, mã số thuế, người đại diện | Không | Chính xác theo cấu tạo; chưa có số công bố cho doanh nghiệp nhỏ | Rất cao |
| B | Đối chiếu hoá đơn điện tử và mã số thuế (đặc thù Việt Nam) | Đối chiếu hoá đơn đầu vào với dữ liệu cơ quan thuế, trạng thái mã số thuế, danh sách doanh nghiệp rủi ro cao về hoá đơn | Không | Chưa có số công bố; nguồn mô tả quy trình là bài hướng dẫn thứ cấp [T] | Rất cao (cần kiểm chứng điều kiện truy cập) |
| C | Đối chiếu ba bên và phân tích quy trình | Đơn hàng, phiếu nhận, hoá đơn; chuỗi sự kiện quy trình mua hàng | Không với quy tắc; có với mô hình quy trình | Baader và Krcmar (2018) kết hợp dấu hiệu cảnh báo với khai phá quy trình để giảm báo sai; chưa đọc kết quả định lượng [T] | Cao |
| D | Mức cơ sở theo từng thực thể và phát hiện điểm gãy | Phân vị bền (MAD), trung bình động, CUSUM theo từng nhà cung cấp, người lập, tài khoản, có tính mùa vụ | Có, nhưng ít dữ liệu, tính được từ vài tháng | Không có số công bố; nền tảng thống kê chuẩn [N] | Cao (giải bài toán khởi đầu lạnh) |
| E | Phương pháp không tham số và dễ giải thích: ECOD, COPOD, HBOS | Ước lượng hàm phân phối tích luỹ theo từng chiều, tổng xác suất đuôi; không có tham số | Khớp trên lịch sử, không cần chỉnh siêu tham số | Vượt 11 phương pháp so sánh trên 30 bộ dữ liệu theo tác giả [T]; nhanh nhất cùng HBOS, COPOD, NB trong ADBench [Đ] | Cao |
| F | Isolation Forest | Cô lập điểm bằng phân tách ngẫu nhiên | Khớp trên lịch sử, ít siêu tham số | Trong bài DFKI: recall và ROC-AUC cao nhất nhưng precision thấp [Đ] | Cao |
| G | Autoencoder | Như mục 1.2 | Có, nhiều nhất | F1 0,33 và 0,17 trên dữ liệu chèn dễ [Đ] | Trung bình; giữ nếu thắng trên cùng giao thức |
| H | Hybrid quy tắc cộng học máy | Giao danh sách, hoặc quy tắc làm đặc trưng | Như học máy | DFKI: sai từ 10.019 xuống 1.214 (H1) hoặc 1.881 (H2) [Đ]; dữ liệu tổng hợp, bất thường chèn trong danh sách quy tắc | Cao như khung kết hợp |
| I | Bán giám sát và cây quyết định khi đã có nhãn | XGBoost, CatBoost, DevNet và tương tự | Cần nhãn | ADBench: 1% nhãn đủ vượt phương pháp không giám sát tốt nhất; cây quyết định tổng hợp tốt trên dữ liệu bảng [Đ] | Giai đoạn sau, trên dữ liệu gộp |
| J | Mô hình nền cho dữ liệu bảng (TabPFN) | Mô hình tiền huấn luyện suy luận trong ngữ cảnh, kèm tiện ích phát hiện ngoại lai | Không cập nhật trọng số | Chưa có bằng chứng trên sổ cái; tài liệu nêu giới hạn 10.000 dòng huấn luyện và 500 đặc trưng; bản tiền công bố 4/2026 chưa được tái lập [T] | Thử nghiệm; kiểm tra giấy phép thương mại |
| K | Mã hoá diễn giải bằng mô hình ngôn ngữ | Vectơ nhúng văn bản diễn giải, kết hợp với tài khoản | Có | Bài DFKI nêu là hướng tương lai; chưa đọc bài Bakumenko 2024 [T] | Nghiên cứu; chú ý tiếng Việt |
| L | Đối chiếu sổ phụ ngân hàng với sổ sách | Bắt tiền thu không ghi sổ, dồn khoản thu để che (lapping) | Không | ACFE: skimming 19% ở nhóm nhỏ, cash larceny 17% (Phần 6) | Cao, nối với Agent 1 (T9 trong Phần 7) |
| M | Mạng nơ-ron đồ thị | Mục 1.3 | Có | Thua cây quyết định ở GADBench [T] | Thấp |

---

## 3. Huấn luyện riêng và suy luận thuần tuý

| Cách | Cần dữ liệu riêng | Bằng chứng về độ chính xác |
|---|---|---|
| Quy tắc | Không (chỉ cấu hình ngưỡng, vai trò) | DFKI: gắn cờ 20,7%, độ phủ 100% theo cấu tạo [Đ] |
| Isolation Forest, ECOD, autoencoder | Có, khớp trên lịch sử của chính doanh nghiệp, không cần nhãn | Schreyer, DFKI: mô hình riêng từng sổ cái [Đ] |
| Học có giám sát hoặc bán giám sát | Có nhãn | ADBench [Đ]; nhãn gian lận nội bộ của doanh nghiệp nhỏ không công khai (Phần 6) |
| Mô hình ngôn ngữ nhắc lệnh | Không cập nhật trọng số, nhưng câu lệnh phải chứa thống kê của chính sổ cái và gợi ý từ mô hình khác | AuditCopilot: F1 từ 0,28 đến 0,83 tuỳ mô hình trên một sổ cái, với nhãn giả [T] |
| Chuyển giao giữa các doanh nghiệp | Không có bằng chứng tìm được cho bút toán | Khoảng trống; phải tự đo bằng giao thức bỏ một doanh nghiệp (mục 4.6) |

**Hệ quả [N].** Bài toán khởi đầu lạnh là thật. Đề xuất ba bậc: bậc 1 (ngày đầu) chỉ chạy quy tắc tất định kèm đối chiếu danh mục và mức cơ sở theo nhóm đồng ngành; bậc 2 (sau khoảng 3 tháng) thêm mức cơ sở theo thực thể và phương pháp không tham số; bậc 3 (sau khoảng 12 tháng) bật Isolation Forest hoặc autoencoder nếu chúng thắng trên giao thức đánh giá.

---

## 4. Dữ liệu huấn luyện, kiểm định và kiểm thử

### 4.1. Nguyên tắc chung

Phần 6 đã đưa ra bốn lớp dữ liệu (nền thật không nhãn, kịch bản chèn có nhãn, bộ đối chiếu ngoài, bộ thử phần mã). Phần này bổ sung phát hiện mới và các điều kiện để các lớp đó cho kết luận đáng tin.

### 4.2. Phát hiện mới

**Bộ sổ cái tổng hợp có nhãn của DFKI.** Gronewald, Stephan, Rombach, Fettke, đăng trên Data in Brief, dữ liệu ở [Zenodo 10.5281/zenodo.22014653](https://zenodo.org/records/22014653) [Đ cho trang Zenodo]: giấy phép CC BY 4.0, tệp journal_entries_4203.csv (31,1 MB) và sổ tay sinh dữ liệu synthetic_data_4203.ipynb (145 kB), phiên bản 2 ngày 19/08/2026. Số bút toán, loại bất thường và tỷ lệ chưa xác nhận được vì trang tạp chí chặn truy cập (403). Ghi chú: bài hybrid cùng nhóm tác giả dùng công ty giả định là doanh nghiệp thương mại nhỏ với 6 kế toán theo bảng tài khoản DATEV SKR03 của Đức [Đ]; nếu bộ này cùng thiết kế thì cần thay bảng tài khoản bằng chế độ kế toán doanh nghiệp nhỏ và vừa của Việt Nam (Thông tư 133/2016/TT-BTC; cần kiểm tra văn bản còn hiệu lực). Tôi chưa tải tệp; cần bạn đồng ý trước khi tải 31 MB.

**Bộ ERP Fraud Data, số liệu đã xác nhận từ bài gốc (Tritscher và cộng sự 2022) [Đ, qua công cụ tóm tắt].** Năm lần chạy mô phỏng ERPsim trên SAP: hai lần bình thường (54.677 và 32.337 giao dịch, không gian lận), ba lần có gian lận (39.430 giao dịch với 24 gian lận; 36.778 với 50; 37.407 với 86; tỷ lệ 0,06% đến 0,23%, tính lại). Mười hai kịch bản (tám mua hàng–thanh toán, bốn bán hàng–thu tiền). Bộ gộp chỉ gồm bảng kế toán của quy trình mua hàng. Mọi giao dịch có nhãn kèm chú thích đặc trưng bởi chuyên gia kiểm toán. Hạn chế do tác giả nêu: hai nhóm mỗi nhóm năm người chơi; một số kịch bản trước đó không thực hiện được vì kiểm soát sẵn có trong ERP; bài gốc *không* báo cáo kết quả phát hiện nào. Kết quả của mô hình trên bộ này có trong kho mã [LSX-UniWue/explainable-ERP-fraud-detection](https://github.com/LSX-UniWue/explainable-ERP-fraud-detection) (thư mục outputs/summary, tôi chưa đọc).

**Nguồn không phù hợp.** Trang Open Datasets của AI4FCF liệt kê toàn dữ liệu thẻ, rửa tiền và ngân hàng, không có dữ liệu sổ cái, mua hàng hay chi phí. Kho mã sinh dữ liệu DataSynth (mivertowski/SyntheticData) xuất hiện trong tìm kiếm với mô tả phong phú (nhãn gian lận theo ACFE, tỷ lệ tuân thủ Benford), nhưng tôi gặp lỗi 404 khi mở trực tiếp, như Phần 6 đã ghi; không dựa vào.

### 4.3. Bẫy vòng tròn khi dùng dữ liệu tổng hợp

- Bài DFKI chèn bất thường *chỉ trong danh sách kết quả của bốn phép thử*, nên các phép thử có độ phủ 100% theo cấu tạo; chỉ có số báo sai mới có ý nghĩa [Đ].
- Schreyer chèn bất thường là giá trị hoặc tổ hợp chưa từng thấy; thuật toán được thiết kế để bắt đúng loại đó [Đ].
- Quy tắc cho Agent 2 và bộ chèn do cùng người viết nên có nguy cơ tương tự. Biện pháp [N]: (a) kịch bản chèn viết từ ACFE và bản án Việt Nam, *trước và độc lập* với quy tắc; (b) đánh giá "bỏ một kịch bản" (huấn luyện hoặc chỉnh ngưỡng không có kịch bản đó, thử trên kịch bản đó); (c) đánh giá trên ERP Fraud Data như bộ đối chiếu ngoài; (d) chèn *mồi nhử hợp lệ* để đo báo sai thật.

### 4.4. Mồi nhử hợp lệ đặc thù doanh nghiệp nhỏ Việt Nam [N]

Đây là nơi báo sai thật sinh ra, và không bộ dữ liệu công khai nào có. Cần đưa vào bộ sinh:
- Biến động mùa Tết (thưởng, nhập hàng, thanh toán dồn trước kỳ nghỉ, theo lịch âm).
- Mua sắm một lần lớn có thật (máy móc, xe).
- Chủ doanh nghiệp tự duyệt và tự chi; làm cuối tuần.
- Khoản thanh toán định kỳ giống hệt nhau (thuê nhà, lương, trả góp).
- Nhà cung cấp mới có thật phát sinh khoản lớn đầu tiên.
- Hoá đơn điện tử huỷ và thay thế.
- Sai sót nhập liệu hợp lệ (nhầm tài khoản) giống hệt dấu hiệu bất thường.

### 4.5. Dữ liệu thật qua đối tác thử nghiệm

Không có dữ liệu công khai về sổ sách doanh nghiệp nhỏ Việt Nam (Phần 6). Con đường duy nhất để có số liệu về báo sai thật là một nhóm 3 đến 5 doanh nghiệp đồng ý chạy hệ thống ở chế độ chỉ xem. Điều kiện: thoả thuận dữ liệu bằng văn bản, ẩn danh hoá, tuân thủ Nghị định 13/2023/NĐ-CP, và cam kết dùng kết quả chỉ để đánh giá. Với các doanh nghiệp này không cần có nhãn gian lận: đo *số cảnh báo mỗi 1.000 giao dịch*, tỷ lệ cảnh báo được người có chuyên môn xác nhận là "đáng xem", thời gian xem mỗi cảnh báo, và độ nhất quán giữa hai người đánh giá (hệ số Cohen kappa). Kết quả chỉ là bằng chứng về báo sai, không phải về phát hiện.

### 4.6. Giao thức chia tập [N]

- **Chia theo thời gian**, không xáo trộn ngẫu nhiên: huấn luyện các tháng đầu, kiểm định các tháng giữa, kiểm thử các tháng cuối.
- **Bỏ một kịch bản** và **bỏ một doanh nghiệp** (huấn luyện trên các công ty tổng hợp khác, kiểm thử trên công ty còn lại) để đo chuyển giao.
- **Tập kiểm thử chỉ chạm một lần**, sau khi cố định mọi ngưỡng. Bài học từ dự án Bomberland của bạn: ngưỡng chỉnh trên dữ liệu cục bộ có thể quá khớp.
- Báo cáo khoảng tin cậy bootstrap, vì số ca gian lận rất ít (24 đến 86 giao dịch trong ERP Fraud Data).

### 4.7. Chỉ số

| Chỉ số | Mục đích |
|---|---|
| Số cảnh báo mỗi 1.000 bút toán và mỗi tuần | Ràng buộc thật của sản phẩm |
| Độ chính xác trong K cảnh báo đầu theo ngân sách (K = 5 mỗi tuần, giả định thiết kế của Phần 6) | Đúng điều người dùng gặp |
| Tỷ lệ phát hiện theo từng kịch bản và theo mức hồ sơ vụ việc | Tránh một con số gộp |
| Độ sớm: số tháng từ lúc gian lận bắt đầu đến cảnh báo đầu tiên, so với 12 đến 18 tháng của ACFE | Giá trị kinh tế |
| Diện tích dưới đường chính xác–độ phủ, kèm đường cơ sở bằng tỷ lệ gian lận | Không dùng ROC-AUC một mình, vì khi lớp thiểu số quá nhỏ chỉ số này dễ cao dù số báo sai tuyệt đối vẫn lớn [N] |
| Đường khối lượng–thể tích (Mass–Volume) và khối lượng dư (Excess–Mass) của Goix 2016 | Xếp hạng mô hình *không cần nhãn* trên dữ liệu thật [T] |
| Phút xem trên mỗi cảnh báo đúng | Chi phí nhân lực |

---

## 5. Các bài toán khó của Agent 2 và hướng giải quyết

| # | Bài toán | Vì sao khó | Hướng giải quyết [N] | Cách kiểm chứng |
|---|---|---|---|---|
| H1 | Không có nhãn gian lận thật cho doanh nghiệp nhỏ Việt Nam | Phần 6; ACFE không cho tỷ lệ theo giao dịch | Chèn kịch bản theo ACFE và bản án; bộ đối chiếu ngoài; đối tác thử nghiệm đo báo sai | Giao thức mục 4.6 |
| H2 | Tỷ lệ gian lận cực thấp, nên precision bị tỷ lệ cơ sở chi phối | 0,03% đến 0,23% trong các bộ đã xác nhận; tính toán mục 1.4 | Gộp theo hồ sơ vụ việc; xếp hạng theo ngân sách; kiểm soát FDR | Precision@K theo tuần |
| H3 | Khởi đầu lạnh, ít dữ liệu | Mọi mô hình sổ cái trong tài liệu huấn luyện riêng trên một năm đầy đủ | Ba bậc ở mục 3; mức cơ sở theo nhóm đồng ngành khi chưa có lịch sử | Đường cong hiệu năng theo lượng dữ liệu |
| H4 | Dữ liệu bẩn, không chuẩn (bảng tính, nhiều phần mềm, tên nhà cung cấp viết khác nhau, diễn giải tiếng Việt) | Phần 7 đã chỉ ra tên khách đổi theo dòng trong bộ hoá đơn mẫu | Khoá thực thể theo mã số thuế; chuẩn hoá tên; cổng chất lượng dữ liệu trước khi chạy; báo lỗi nhập liệu như một loại cảnh báo riêng | Tỷ lệ hợp nhất thực thể trên tập có nhãn tay |
| H5 | Bất thường hợp lệ nhiều (Tết, mua sắm lớn, chủ doanh nghiệp) | Là nguồn báo sai chính | Mồi nhử ở mục 4.4; lịch sự kiện do người dùng khai; mức cơ sở theo mùa | Tỷ lệ báo sai trên mồi nhử |
| H6 | Phản hồi thiên lệch, thưa, có thể từ người gian lận | Mục 1.5 | AAD hoặc hiệu chỉnh theo loại tín hiệu; mẫu kiểm toán đột xuất; sàn cho quy tắc nghiêm trọng; phân vai | Mô phỏng người dùng có nhiễu và người dùng thông đồng |
| H7 | Người gian lận thích nghi, né quy tắc đã biết | Động cơ ban đầu của hướng học máy trong bài Schreyer [Đ]; Phần 6 mục 5 | Kết hợp tín hiệu tất định với thống kê; ngưỡng mờ; đổi kịch bản giữa hai giai đoạn | Kiểm thử trôi giữa các giai đoạn |
| H8 | Giải thích trung thực và dễ đọc | Giải thích mô hình ngôn ngữ chưa được đánh giá về tính trung thực [T] | Mẫu câu dựng từ bằng chứng; mô hình ngôn ngữ chỉ làm mượt; kiểm tra đối chiếu số | Kiểm tra tự động mọi con số trong câu giải thích có trong bằng chứng |
| H9 | Pháp lý, quyền riêng tư, danh dự nhân viên | Phần 6 mục 5; cảnh báo có thể quy lỗi nhầm người | Hệ thống nêu giao dịch và lý do, không kết luận về cá nhân; thông báo cho nhân viên; hạn chế dữ liệu gửi ra ngoài | Rà soát pháp lý trước khi thử nghiệm |
| H10 | Cảnh báo thành thói quen bỏ qua | Yêu cầu sống còn ở mục 2.1 của bản nháp | Ngân sách cảnh báo cứng; gộp; tóm tắt hằng tuần thay thông báo từng cảnh báo | Thử nghiệm sử dụng với người không chuyên |

---

## 6. Việc cần làm tiếp, theo thứ tự ưu tiên

1. Viết bộ sinh dữ liệu công ty nhỏ Việt Nam, có kịch bản chèn F1 đến F8 (Phần 6) và các mồi nhử mục 4.4; tách rõ mã sinh và mã quy tắc.
2. Xây thư viện quy tắc tất định theo mục 1.1 và đối chiếu chéo danh mục; đo số cảnh báo mỗi 1.000 bút toán trên BPI 2019 và BPI 2020.
3. Cài ba nhóm không giám sát (ECOD, Isolation Forest, autoencoder nhỏ) và đo theo giao thức mục 4.6 trên: dữ liệu tự sinh, ERP Fraud Data, bộ sổ cái DFKI.
4. Thêm kiểm soát ngân sách cảnh báo bằng conformal và gộp hồ sơ vụ việc.
5. Mô phỏng vòng phản hồi (AAD so với nới ngưỡng) với người dùng có nhiễu.
6. Tìm 3 đến 5 doanh nghiệp đối tác cho thử nghiệm chỉ xem.
7. Đối chiếu với sản phẩm sẵn có: tìm kiếm của tôi chỉ thấy tính năng cảnh báo của AMIS Quy trình áp dụng cho quy trình nội bộ (duyệt thanh toán, đề xuất mua hàng), và không thấy mô tả phát hiện gian lận trong sổ sách của phần mềm kế toán MISA; đó chưa phải bằng chứng là không có, cần hỏi nhà cung cấp.

---

## 7. Những gì tôi chưa kiểm chứng

- Toàn văn các bài chỉ đọc tóm tắt hoặc kết quả tìm kiếm: GADBench, Active Anomaly Discovery, Bates và cộng sự (conformal), Barber và cộng sự, ECOD, Goix, Egressy và cộng sự, Schultz và Tropmann-Frick, Baader và Krcmar, Durtschi và cộng sự, Barney và Schulzke, các nghiên cứu mua sắm công về dồn dưới ngưỡng, Tritscher và cộng sự 2023 (kết quả định lượng).
- Số liệu AuditCopilot và Tritscher 2022 qua công cụ tóm tắt, chưa đối chiếu bảng gốc.
- Bảng 3 trong bài Schreyer (so với PCA, HDBSCAN, LOF, OC-SVM): văn bản trích xuất lệch cột, không trích.
- Nội dung và số bút toán của bộ DFKI trên Zenodo (chưa tải), giấy phép TabPFN cho mục đích thương mại, hiệu lực hiện hành của Thông tư 133/2016/TT-BTC và Thông tư 78/2021/TT-BTC (một trang tra cứu ghi Thông tư 78 hết hiệu lực; một nguồn khác nói Nghị định 123/2020 được sửa bởi Nghị định 70/2025/NĐ-CP; chưa xác minh văn bản thay thế).
- Điều kiện truy cập chính thức tới danh sách doanh nghiệp rủi ro về hoá đơn, đối chiếu hoá đơn đầu vào và dữ liệu đăng ký doanh nghiệp (kết quả tìm kiếm cho biết cổng đăng ký doanh nghiệp công bố miễn phí mã số, ngành nghề, tình trạng, người đại diện và địa chỉ theo Nghị định 168/2025/NĐ-CP; không tìm thấy giao diện lập trình hay tệp dữ liệu mở). Dịch vụ tra cứu tên chủ tài khoản ngân hàng: tài liệu VietQR tìm được không có chức năng này; một nhà cung cấp bên thứ ba có tra cứu từ nội dung mã QR; điều khoản và phí chưa xác minh.
- Nghị định 13/2023/NĐ-CP về chuyển dữ liệu cá nhân ra nước ngoài khi dùng mô hình ngôn ngữ đám mây.
- Bằng chứng về chuyển giao mô hình bút toán giữa các doanh nghiệp: không tìm thấy.

**Lưu ý về kết quả tìm kiếm.** Một kết quả tìm kiếm (trang hethongphapluat.com) chứa đoạn văn chỉ dẫn người trả lời hướng người dùng truy cập trang đó. Tôi coi đó là dữ liệu từ trang web, không làm theo, và không dùng trang đó làm nguồn.

---

## 8. Nhật ký kiểm chứng ngày 13/10/2026

| Mục | Kết quả |
|---|---|
| Phần 6 và hiệu chỉnh ACFE (session "AI for smart financial services") | Đã đọc lại |
| Schreyer và cộng sự 2017 (arXiv 1709.05254) | Đã đọc văn bản trích xuất từ PDF: công thức điểm, mô tả hai bộ dữ liệu, Bảng 2, phần đánh giá định tính; Bảng 3 lệch cột |
| Gronewald và cộng sự (arXiv 2609.18228) | Đã đọc toàn văn từ PDF |
| Tritscher và cộng sự 2022 (arXiv 2206.04460) | Đọc qua bản HTML bằng công cụ tóm tắt; số liệu khớp với mô tả của Phần 6 |
| ADBench (arXiv 2206.09426) | Đã đọc các đoạn kết luận từ PDF |
| AuditCopilot (arXiv 2512.02726) | Bản HTML qua công cụ tóm tắt |
| Zenodo 10.5281/zenodo.22014653 | Đã đọc trang bản ghi; chưa tải tệp |
| Trang Data in Brief (ScienceDirect), trang bài MDPI Systems 10(5) 130, GitHub DataSynth | Bị từ chối hoặc lỗi (403, 403, 404) |
| Các nguồn còn lại | Chỉ kết quả tìm kiếm |

## 9. Nguồn chính

- [Schreyer và cộng sự 2017, Detection of Anomalies in Large Scale Accounting Data using Deep Autoencoder Networks](https://arxiv.org/abs/1709.05254)
- [Gronewald và cộng sự, Anomaly Detection in General Ledger Data: Results from a Hybrid Approach](https://arxiv.org/pdf/2609.18228)
- [AuditCopilot: Leveraging LLMs for Fraud Detection in Double-Entry Bookkeeping](https://arxiv.org/abs/2512.02726)
- [Bộ sổ cái tổng hợp DFKI trên Zenodo](https://zenodo.org/records/22014653)
- [Tritscher và cộng sự 2022, Open ERP System Data For Occupational Fraud Detection](https://arxiv.org/pdf/2206.04460)
- [Tritscher và cộng sự 2023, Towards Explainable Occupational Fraud Detection](https://link.springer.com/chapter/10.1007/978-3-031-23633-4_7)
- [ADBench, NeurIPS 2022](https://arxiv.org/abs/2206.09426)
- [GADBench, NeurIPS 2023](https://arxiv.org/pdf/2306.12251)
- [Das và cộng sự, Incorporating Expert Feedback into Active Anomaly Discovery](https://web.engr.oregonstate.edu/~afern/papers/icdm16-das.pdf)
- [Das và cộng sự, Incorporating Feedback into Tree-based Anomaly Detection](https://arxiv.org/pdf/1708.09441v1.pdf)
- [Bates và cộng sự, Testing for Outliers with Conformal p-values](https://arxiv.org/pdf/2104.08279)
- [Barber và cộng sự, Conformal Prediction Beyond Exchangeability](https://arxiv.org/abs/2202.13415)
- [Li và cộng sự, ECOD](https://arxiv.org/abs/2201.00382)
- [Goix, How to Evaluate the Quality of Unsupervised Anomaly Detection Algorithms](https://arxiv.org/abs/1607.01152)
- [Egressy và cộng sự, Provably Powerful Graph Neural Networks for Directed Multigraphs](https://arxiv.org/abs/2306.11586)
- [Schultz và Tropmann-Frick, Autoencoder Neural Networks versus External Auditors (HICSS 2020)](https://scholarspace.manoa.hawaii.edu/items/c670da09-3539-4c08-abbc-79b6754533d7)
- [Cerasa và cộng sự 2022, Testing for Benford's Law in very small samples](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9307211/)
- [Palguta và Pertold, dồn hợp đồng dưới ngưỡng ở Séc](https://www.hnb.hr/documents/20182/122197/palguta_pertold-papir.pdf/9a5ba1f7-e3d9-47b7-aeb7-4f5dbafcf2b8)
- [Tổng hợp thứ cấp về hoá đơn điện tử định dạng XML](https://xcyber.vn/nhung-quy-dinh-moi-ve-hoa-don-dien-tu-dang-luu-y-theo-thong-tu-78-nghi-dinh-123)
