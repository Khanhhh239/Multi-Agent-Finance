# PHẦN 6 — DỮ LIỆU CHO AGENT 2 (TRỢ LÝ GIÁM SÁT RỦI RO)

Ngày kiểm chứng: 20/09/2026. Mọi số liệu trích từ tài liệu gốc đã đọc trực tiếp; những gì chưa kiểm chứng được ghi ở mục 7.

Tệp kèm theo: [agent2_data/calibration_fraud.json](agent2_data/calibration_fraud.json) (tham số hiệu chỉnh bộ chèn gian lận, chép từ báo cáo ACFE 2024) và [agent2_data/fetch_agent2_data.py](agent2_data/fetch_agent2_data.py) (tập lệnh thu thập các nguồn tải trực tiếp được).

---

## 0. Kết luận trước

**Danh sách bạn gửi sai ở đâu.** Cả bốn mục đều là dữ liệu gian lận bên ngoài: chuyển tiền di động, mở tài khoản ngân hàng, rửa tiền, giao dịch Bitcoin. Agent 2 phục vụ gian lận nội bộ trong sổ sách của doanh nghiệp nhỏ: nhà cung cấp ma, thanh toán bị chỉnh sửa, chi phí khai khống, nhân sự ma, bút toán khống. Ngoài sai về phạm vi, danh sách còn có những mô tả không đúng với tài liệu gốc (mục 2), và một đường dẫn tôi không xác nhận được.

**Không có bộ dữ liệu công khai nào gán nhãn gian lận nội bộ của doanh nghiệp nhỏ.** Bài báo của nhóm Đại học Würzburg nêu rõ dữ liệu hệ thống ERP nói chung không được công bố, và các nghiên cứu trước thuộc ba nhóm: dữ liệu riêng với gian lận thật, dữ liệu riêng với gian lận chèn thêm, hoặc hoàn toàn tổng hợp. Bộ công khai gần nhất với bài toán của ta là ERP Fraud Data của chính nhóm này.

**Chiến lược dữ liệu đề xuất cho Agent 2 gồm bốn lớp:**

| Lớp | Nội dung | Dùng để | Không dùng để |
|---|---|---|---|
| 1. Nền thật không nhãn | BPI 2019 (mua hàng và thanh toán), BPI 2020 (chi phí công tác, có chuỗi phê duyệt), chi trả nhà cung cấp của chính quyền thành phố | Đo khối lượng cảnh báo mỗi 1.000 giao dịch của từng quy tắc | Đo độ chính xác (không có nhãn) |
| 2. Chèn kịch bản có nhãn | Gian lận chèn vào nền thật và vào công ty tổng hợp; tham số theo ACFE 2024 | Đo tỷ lệ phát hiện theo từng loại gian lận | Kết luận về tần suất gian lận thật |
| 3. Bộ đối chiếu ngoài | ERP Fraud Data (12 kịch bản trên SAP mô phỏng) | Kiểm tra độc lập với bộ chèn của ta | Huấn luyện chính |
| 4. Bộ thử phần mã | Elliptic, IBM AML-Data, SAML-D, BAF | Thử lớp đồ thị, đường ống mất cân bằng lớp, độ trôi theo thời gian | Bằng chứng về gian lận nội bộ |

**Hai điều tôi phải tự đính chính** (đã sửa trong Phần 4):
1. Tôi từng viết rằng nhóm dưới 100 nhân sự có tỷ lệ tham nhũng cao nhất trong mọi nhóm quy mô, ở mức 44%. Bản ACFE gốc ghi 44% ở nhóm dưới 100 nhân sự nhưng 52% ở nhóm từ 100 nhân sự trở lên, và bài viết nói rõ tham nhũng gặp nhiều hơn ở tổ chức lớn. Câu tôi viết sai; nguồn của nó là một đoạn tóm tắt tìm kiếm mà tôi chưa đối chiếu với báo cáo gốc. Số liệu đúng, và cũng có lợi cho lập luận của ta hơn, nằm ở mục 4.
2. Câu "mô hình học máy cổ điển thường vượt trội hơn GNN trên đồ thị thưa" khái quát quá mức từ một bộ dữ liệu. Phát biểu đúng: trên Elliptic, Random Forest đạt F1 lớp bất hợp pháp 0,796 so với 0,628 của GCN (Phần 2 đã ghi đúng các số này).

---

## 1. Agent 2 cần dữ liệu gì

| Khối của Agent 2 | Dữ liệu cần | Nguồn thật không nhãn | Nguồn có nhãn |
|---|---|---|---|
| Thư viện quy tắc (ngưỡng phê duyệt, thanh toán trùng, số tiền tròn, ngày cuối tuần) | Sổ chi trả, hoá đơn, bút toán có ngày, người lập, người duyệt | BPI 2019, BPI 2020, chi trả của thành phố | ERP Fraud Data; bộ chèn của ta |
| Phân tích đồ thị quan hệ tất định (tài khoản, địa chỉ, người đại diện dùng chung) | Đồ thị thực thể có cạnh sở hữu, địa chỉ, tài khoản | ICIJ Offshore Leaks (đồ thị thật, quan hệ pháp nhân) | Bộ chèn (nhà cung cấp ma trùng tài khoản nhân viên); AML-Data, SAML-D cho mẫu vòng và phân tán |
| Autoencoder trên bút toán | Bút toán sổ cái đủ lớn để học "bình thường" | Khó có nguồn thật công khai; nghiên cứu gốc dùng dữ liệu SAP riêng | ERP Fraud Data (bảng tổng hợp sẵn); công ty tổng hợp |
| Mạng nơ-ron đồ thị (lớp bổ trợ) | Đồ thị lớn có nhãn theo thời gian | Elliptic (thử phần mã) | AML-Data, SAML-D |
| Bộ tổng hợp và giải thích | Nhãn theo hồ sơ để hiệu chỉnh ngưỡng | Không có | Bộ chèn; phản hồi người dùng thật sau này |

---

## 2. Đối chiếu từng mục trong danh sách đã gửi

| Mục | Mô tả trong danh sách | Điều đã kiểm chứng | Phù hợp Agent 2? |
|---|---|---|---|
| PaySim | "Dữ liệu tổng hợp dựa trên log thực tế của một nền tảng tài chính; giao dịch Transfer, Cash-out với nhãn gian lận; thích hợp để huấn luyện luật và mô hình ban đầu" | Đúng một phần. Mô phỏng dịch vụ tiền di động, dựa trên mẫu nhật ký một tháng của dịch vụ thật tại một nước châu Phi, chỉ dùng số liệu tổng hợp; khoảng 6,3 triệu giao dịch trong 744 bước thời gian, 8.213 giao dịch gian lận (0,13%); năm loại giao dịch. Bản gốc trên Kaggle là ealaxi/paysim1; đường dẫn trong danh sách (moonknightmarvel) là bản đăng lại, tôi không xác nhận được nguồn gốc. [Bài gốc (EMSS 2016)](https://www.msc-les.org/proceedings/emss/2016/EMSS2016_249.pdf), [kho mã](https://github.com/EdgarLopezPhD/PaySim) | Không. Là gian lận chuyển tiền của người dùng cuối, không có nhà cung cấp, bút toán, phê duyệt hay lương |
| Elliptic | "Bộ dữ liệu mạng lưới giao dịch hơn 200.000 nút; chuẩn mực tốt nhất hiện nay để so sánh GNN" | Số liệu đúng, mô tả quá lời. Đồ thị giao dịch Bitcoin: 203.769 nút, 234.355 cạnh, 166 đặc trưng, 49 bước thời gian cách nhau khoảng hai tuần; 2% (4.545) nhãn bất hợp pháp, 21% (42.019) hợp pháp, còn lại chưa gán nhãn. Trong bài gốc, Random Forest (mọi đặc trưng, kèm nhúng nút) đạt F1 lớp bất hợp pháp 0,796; Skip-GCN 0,705; GCN 0,628; Logistic 0,543; chia 34 bước huấn luyện, 15 bước kiểm tra. Sau khi một chợ đen đóng cửa ở bước 43, mọi mô hình đều giảm, kể cả Random Forest huấn luyện lại sau từng bước. 166 đặc trưng đã gồm đặc trưng tổng hợp từ nút lân cận. Đường dẫn cloud825/can-we-trust-gnn-uncertainty-data không phải bộ gốc và tôi không tìm thấy nó khi tra cứu. [Bài gốc](https://arxiv.org/pdf/1908.02591) | Chỉ để thử lớp mã đồ thị và minh hoạ chia theo thời gian. Không phải dữ liệu kế toán hay gian lận nội bộ |
| Bank Account Fraud (BAF) | "Bộ dữ liệu tổng hợp mới xuất hiện, tập trung mất cân bằng lớp" | Không mới (NeurIPS 2022). Gồm 6 bộ, mỗi bộ 1 triệu đơn mở tài khoản, 30 đặc trưng, tám tháng; tỷ lệ gian lận 0,85% đến 1,5% tuỳ tháng; sinh bằng CTGAN từ một bộ dữ liệu thật đã ẩn danh của ngân hàng, có thêm nhiễu để bảo vệ quyền riêng tư; có thuộc tính nhạy cảm là tuổi, kèm các biến thể cố ý tạo thiên lệch và trôi theo thời gian. Mục đích: đánh giá độ công bằng, mất cân bằng lớp và trôi dữ liệu. [Bài gốc](https://arxiv.org/pdf/2211.13358), [kho mã](https://github.com/feedzai/bank-account-fraud) | Không phải gian lận nội bộ (là gian lận của người xin mở tài khoản). Dùng thử đường ống mất cân bằng lớp và trôi theo thời gian |
| BankSim / IBM AMLSim | "Công cụ mô phỏng cho phép tự định nghĩa hành vi gian lận như giao dịch sát ngưỡng duyệt, chia nhỏ hoá đơn; sinh hàng triệu giao dịch" | Sai. Đường dẫn ealaxi/banksim1 là một bộ dữ liệu tĩnh, không phải công cụ. BankSim mô phỏng thanh toán ngân hàng dựa trên dữ liệu tổng hợp của một ngân hàng Tây Ban Nha (sáu tháng từ 11/2012 đến 04/2013, Madrid và Barcelona). AMLSim của IBM là bộ mô phỏng đa tác tử cho chống rửa tiền, sinh mạng giao dịch có sẵn các mẫu như vòng, gom nhiều vào một, phát tán một ra nhiều, hai phía; không có mẫu sát ngưỡng phê duyệt hay chia nhỏ hoá đơn. [BankSim](http://www.msc-les.org/proceedings/emss/2014/EMSS2014_144.pdf), [AMLSim](https://github.com/IBM/AMLSim) | Không dùng cho gian lận nội bộ. Hành vi sát ngưỡng và chia nhỏ hoá đơn phải do ta tự chèn |

Bản kế thừa tốt hơn của AMLSim là bộ sinh dữ liệu của IBM công bố tại NeurIPS 2023 (Altman và cộng sự), có các bộ dữ liệu sẵn trên [Kaggle](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml); và SAML-D (9.504.852 giao dịch, 12 đặc trưng, 28 kiểu mẫu gồm 11 bình thường và 17 đáng ngờ, tháng 10/2022 đến tháng 8/2023) trên [Kaggle](https://www.kaggle.com/datasets/berkanoztas/synthetic-transaction-monitoring-dataset-aml). Cả hai đều là dữ liệu rửa tiền tổng hợp.

Hai chỗ trong hồ sơ nộp cần soát lại vì cùng lỗi phạm vi:
- Câu "sinh doanh nghiệp ảo 36 tháng, cài sẵn lỗi thuế và kịch bản gian lận theo chuẩn nghiên cứu như IBM AMLSim, SAML-D": hai bộ này là rửa tiền, nên đề xuất viết lại thành "theo phương pháp bộ dữ liệu ERP mô phỏng có gian lận nghề nghiệp đã công bố và tham số theo báo cáo ACFE".
- Câu về Elliptic là "bộ dữ liệu chuẩn cho bài toán phát hiện gian lận": chính xác hơn là bộ chuẩn phát hiện giao dịch bất hợp pháp trên đồ thị Bitcoin; và số Random Forest 0,796 so với GCN 0,628 nên được nêu kèm để câu có căn cứ.

---

## 3. Nguồn nên dùng

Thang độ tin cậy: **A** là nguồn chính thức hoặc đã qua bình duyệt, dữ liệu thật; **B** là nguồn tổng hợp hoặc mô phỏng có tài liệu phương pháp công bố; **C** chưa xác minh được hoặc không rõ nguồn gốc.

### Nhóm A. Nền thật không nhãn

**A1. BPI Challenge 2020 — chi phí công tác (Đại học Công nghệ Eindhoven)** (A)
- Năm bộ dữ liệu con: Domestic Declarations, International Declarations, Prepaid Travel Costs, Request For Payment, Travel Permit. Dữ liệu 2017 (hai khoa) và 2018 (toàn trường). Quy trình: nhân viên nộp yêu cầu, chuyển văn phòng đi lại, chủ ngân sách, rồi người giám sát; khoản lớn cần giám đốc duyệt. Quy mô đã nêu: Prepaid Travel Cost 2.099 hồ sơ, 18.246 sự kiện; International Declarations 6.449 hồ sơ, 72.151 sự kiện; Travel Permit 7.065 hồ sơ, 86.581 sự kiện.
- Truy cập: [tuyển tập 4TU](https://data.4tu.nl/collections/_/5065541/1); các tệp .xes.gz nhỏ (0,37 đến 1,94 MB), tải qua giao diện figshare (đã kiểm tra). **Giấy phép CC BY-NC 4.0: chỉ phi thương mại**, đủ cho đồ án thi nhưng không cho sản phẩm thương mại.
- Cách dùng: nền thật cho quy tắc thanh toán chi phí (số tiền tròn, tách khoản, chu trình duyệt bất thường); đo số cảnh báo trên hồ sơ thật.
- Hạn chế: chi phí công tác của một trường đại học ở Hà Lan, không phải SME Việt Nam.

**A2. BPI Challenge 2019 — mua hàng và thanh toán** (A). Dùng chung với Agent 1: 728,6 MB, CC BY 4.0, 76.349 chứng từ, 251.734 dòng hàng, 42 hoạt động, 627 tác nhân gồm 20 tác nhân theo lô. Đề bài gốc là tuân thủ quy trình (đối chiếu ba bên giữa đơn hàng, phiếu nhận hàng và hoá đơn), nên là nền thật để thử quy tắc kiểm soát mua hàng. Chi tiết ở Phần 5.

**A3. Chi trả nhà cung cấp của chính quyền thành phố** (A về tính thật; chưa kiểm tra trực tiếp)
- [Thành phố Chicago, bộ Payments](https://data.cityofchicago.org/Administration-Finance/Payments/s4vu-giwb): mọi khoản chi trả nhà cung cấp từ 1996 đến nay, cập nhật hằng ngày (theo trang mô tả trong kết quả tìm kiếm; các khoản trước hai năm gần nhất được gộp theo nhà cung cấp và hợp đồng). Cả tải tự động lẫn công cụ tra cứu của tôi đều bị máy chủ từ chối (403), nên tôi chưa xem được danh sách cột và giấy phép.
- [Checkbook NYC](https://www.checkbooknyc.com/api-page) của Văn phòng Kiểm soát Thành phố New York: chi tiêu, hợp đồng, ngân sách; giao diện lập trình công khai, dữ liệu là bản chỉ đọc đã lọc, đã bỏ thông tin bảo mật như tên nhân viên (theo mô tả trong kho mã của cộng đồng; chưa kiểm tra trực tiếp trang chính thức).
- Cách dùng: nền thật lớn về chi trả nhà cung cấp để hiệu chỉnh quy tắc số tiền tròn, tập trung nhà cung cấp, chi sát ngưỡng phê duyệt, thanh toán trùng và kiểm tra Benford.
- Hạn chế: khu vực công; không có nhãn gian lận.

### Nhóm B. Đồ thị thật

**B1. ICIJ Offshore Leaks Database** (A về nguồn; trang chính chặn công cụ tự động lúc kiểm tra)
- Hơn 810.000 pháp nhân ngoài khơi từ các vụ Pandora, Paradise, Bahamas, Panama và Offshore Leaks; bốn loại nút (Entities, Officers, Intermediaries, Addresses) và quan hệ giữa chúng; tải dưới dạng CSV nén hoặc Neo4j. Giấy phép cơ sở dữ liệu Open Database License, nội dung Creative Commons Attribution-ShareAlike (theo các trang tổng hợp; tôi chưa đọc được trang tải chính thức [offshoreleaks.icij.org/pages/database](https://offshoreleaks.icij.org/pages/database) vì máy chủ trả lỗi 405).
- Cách dùng: đồ thị quan hệ thật (địa chỉ chung, người đại diện chung) để thử lớp truy vấn đồ thị tất định, độ phân giải thực thể và độ trễ truy vấn.
- Lưu ý: sự hiện diện trong bộ dữ liệu không có nghĩa là vi phạm pháp luật; không dùng để dán nhãn "gian lận".

### Nhóm C. Bộ có nhãn gian lận nghề nghiệp

**C1. ERP Fraud Data (Đại học Würzburg)** (B: tổng hợp có tài liệu phương pháp)
- Dữ liệu sinh từ trò chơi mô phỏng ERPsim trên hệ thống SAP, năm lần chạy, công ty sản xuất theo kho với các người chơi đóng vai; một người chơi được chuyên gia kiểm toán hướng dẫn thực hiện gian lận. Gồm **12 kịch bản**: Invoice Kickback 1 và 2 (đổi giá mua để nhận hoa hồng nhà cung cấp; sao chép đơn cũ với giá cao), Larceny 1 đến 6 (đổi số lượng đơn mua, ghi phế phẩm để che trộm hàng, mua hàng không cần thiết qua đơn tạo thủ công với thông đồng người duyệt, đổi địa chỉ giao hàng sang địa chỉ riêng, đổi địa chỉ khách hàng trong quy trình bán), Corporate Injury 1 và 2 (mua khối lượng lớn bất thường, hạ giá bán đột ngột), Selling Kickback 1 và 2 (điều kiện bán ưu đãi cho khách chỉ định). Cung cấp cả dữ liệu thô và bảng đã tổng hợp cho học máy; tệp tải 190 MB đặt trên Google Drive.
- Trang dữ liệu: [Đại học Würzburg](https://www.informatik.uni-wuerzburg.de/datascience/projects/machine-learning-for-cyber-security-fraud-detection/deepscan-concluded/erp-fraud-data/); bài phương pháp: [Tritscher và cộng sự, 2022](https://arxiv.org/pdf/2206.04460). Tôi chưa xác nhận giấy phép và chưa tải tệp.
- Cách dùng: bộ đối chiếu ngoài gần lĩnh vực nhất (mua hàng đến thanh toán và bán hàng). Số ca gian lận rất ít so với giao dịch bình thường, phù hợp với thực tế mất cân bằng.
- Hạn chế: dữ liệu công ty sản xuất mô phỏng; có 5 người tham gia có nền tảng hệ thống thông tin, không phải nhân viên kế toán thật; chưa có nhà cung cấp ma, nhân sự ma hay chi phí khai khống.

### Nhóm D. Chuẩn đánh giá tổng quát

**D1. ADBench (NeurIPS 2022)**: chuẩn đánh giá phát hiện bất thường trên 57 bộ dữ liệu bảng với 30 thuật toán, đánh giá theo mức giám sát, kiểu bất thường và dữ liệu nhiễu. [Kho mã](https://github.com/Minqi824/ADBench). Dùng để kiểm tra Isolation Forest và Autoencoder của ta so với nhóm thuật toán chuẩn; không phải dữ liệu kế toán.

**D2. Các bộ công cụ sinh dữ liệu sổ cái mã nguồn mở** (C): trong kết quả tìm kiếm có vài kho cá nhân (ví dụ SyntheticData, PhantomLedger). Tôi mở thử kho SyntheticData và nhận lỗi 404, nên không khuyến nghị dựa vào; nếu muốn dùng, cần tự kiểm tra giấy phép, kiểm thử và mức độ duy trì.

### Nhóm E. Bối cảnh Việt Nam

| Nguồn | Điều đã xác nhận | Dùng cho | Lưu ý |
|---|---|---|---|
| [Cổng công bố bản án của Tòa án nhân dân tối cao](https://congbobanan.toaan.gov.vn/) | Công bố các bản án, quyết định có hiệu lực theo Nghị quyết 03/2017/NQ-HĐTP, trong đó có vụ án hình sự | Chất liệu định tính về thủ đoạn thật tại doanh nghiệp (ví dụ kế toán chiếm đoạt tiền) để đặt tên và mô tả kịch bản chèn; kiểm chứng lại Phần 1 | Chưa kiểm tra điều khoản khai thác tự động; bản án có thông tin cá nhân nên phải tuân thủ Nghị định 13/2023/NĐ-CP; không suy ra tần suất |
| [Tra cứu người nộp thuế của Tổng cục Thuế](http://tracuunnt.gdt.gov.vn/) | Trạng thái mã số thuế công khai, kể cả "không hoạt động tại địa chỉ đã đăng ký" (trạng thái 06), có mã xác nhận | Quy tắc "nhà cung cấp không còn hoạt động" | Không tự động hoá: trang dùng mã xác nhận và tôi không thực hiện vượt mã xác nhận. Cần kênh chính thức (chưa xác minh có giao diện lập trình công khai) |
| PwC, Global Economic Crime and Fraud Survey | Số liệu công khai tìm được ở mức Đông Nam Á, không phải riêng Việt Nam | Không dùng làm giá trị đích | Đông Nam Á: 31% tổ chức gặp biển thủ tài sản (khảo sát 2022, theo bản tóm tắt tìm kiếm) |

---

## 4. Hiệu chỉnh bộ chèn gian lận từ ACFE 2024

Đã đọc bản gốc [Occupational Fraud 2024: A Report to the Nations](https://www.acfe.com/-/media/files/acfe/pdfs/rttn/2024/2024-report-to-the-nations.pdf) (106 trang): 1.921 vụ tại 138 quốc gia, tổn thất trung vị 145.000 đô la, một vụ điển hình kéo dài 12 tháng trước khi bị phát hiện. Toàn bộ số liệu dưới đây có trong [calibration_fraud.json](agent2_data/calibration_fraud.json).

**Tỷ lệ theo quy mô tổ chức** (tỷ lệ vụ có loại gian lận đó; một vụ có thể gồm nhiều loại nên không cộng lại thành 100%):

| Loại gian lận | Dưới 100 nhân sự | Từ 100 nhân sự |
|---|---|---|
| Thanh toán hoá đơn (billing) | 31% | 22% |
| Làm giả hoặc chỉnh sửa séc, lệnh thanh toán | 23% | 9% |
| Chiếm đoạt tiền thu trước khi ghi sổ (skimming) | 19% | 9% |
| Thanh toán chi phí cho nhân viên | 20% | 12% |
| Lấy trộm tiền mặt (cash larceny) | 17% | 9% |
| Lấy tiền mặt tại quỹ | 16% | 10% |
| Bảng lương | 14% | 9% |
| Gian lận báo cáo tài chính | 8% | 4% |
| Tham nhũng | 44% | 52% |
| Trộm tài sản không phải tiền | 20% | 23% |

Báo cáo nêu rõ tham nhũng và trộm tài sản không phải tiền gặp nhiều hơn ở tổ chức lớn, còn các loại còn lại gặp nhiều hơn ở tổ chức nhỏ. Tổn thất trung vị ở nhóm dưới 100 nhân sự là 141.000 đô la, mức lớn thứ hai trong các nhóm quy mô.

**Biện pháp kiểm soát, dưới 100 nhân sự so với từ 100 nhân sự:** kiểm toán nội bộ 40% so với 90%; đường dây tố giác 27% so với 82%; giám sát dữ liệu chủ động 19% so với 53%; kiểm toán đột xuất 17% so với 49%; luân chuyển công việc hoặc nghỉ phép bắt buộc 10% so với 27%; rà soát của quản lý 39% so với 79%. Đây là căn cứ tốt nhất cho lập luận "thiếu kiểm soát nên cần giám sát tự động".

**Thông số cho từng kịch bản chèn** (tổn thất trung vị là của mọi quy mô, tính theo vụ):

| Mã | Kịch bản chèn | Loại ACFE | Tỷ lệ nhóm nhỏ | Tổn thất trung vị | Kéo dài điển hình |
|---|---|---|---|---|---|
| F1 | Nhà cung cấp ma, hoá đơn khống, trùng tài khoản hoặc địa chỉ với nhân viên | Billing | 31% | 100.000 đô la | 18 tháng |
| F2 | Đổi người nhận tiền, thanh toán trùng, thanh toán cho người không có trong danh mục | Check and payment tampering | 23% | 155.000 đô la | 18 tháng |
| F3 | Chi phí khai khống, trùng, tách khoản dưới ngưỡng chứng từ | Expense reimbursements | 20% | 50.000 đô la | 18 tháng |
| F4 | Nhân sự ma, sửa giờ công | Payroll | 14% | 50.000 đô la | 18 tháng |
| F5 | Tiền thu không ghi sổ, huỷ hoặc giảm giá bất thường, che bằng thu chậm | Skimming, cash larceny | 19%, 17% | 43.000, 50.000 đô la | 18 tháng, 12 tháng |
| F6 | Điều chỉnh tồn kho, xoá sổ hàng để che trộm | Noncash | 20% | 66.000 đô la | 12 tháng |
| F7 | Hoa hồng từ nhà cung cấp, giá cao hơn thị trường, xung đột lợi ích | Corruption | 44% | 200.000 đô la | không đọc chắc chắn từ báo cáo |
| F8 | Bút toán khống cuối kỳ, do lãnh đạo thực hiện | Financial statement fraud | 8% | 766.000 đô la | 18 tháng |

Ngoài ra ACFE cho các tín hiệu hành vi có thể dùng làm quy tắc phụ ở tầng con người (không phải dữ liệu sổ sách): sống vượt khả năng thu nhập (39% số vụ), quan hệ thân thiết bất thường với nhà cung cấp hoặc khách hàng (20%). Gian lận do chủ sở hữu hoặc lãnh đạo gây tổn thất lớn hơn hơn 7 lần so với nhân viên; gian lận có từ ba người trở lên lớn hơn hơn 4 lần so với một người, đây là căn cứ cho các kịch bản thông đồng (như Larceny 4 trong bộ ERP Fraud Data).

**Những gì bộ chèn phải là giả định của người thiết kế** (ACFE không cung cấp, nên nêu rõ trong hồ sơ và chạy dưới dạng khoảng nhạy cảm):
- Tỷ lệ giao dịch gian lận trong một công ty. ACFE nêu tổn thất và thời gian kéo dài của các vụ đã phát hiện, không nêu tỷ lệ theo giao dịch; con số 5% doanh thu là ước tính của các chuyên gia được khảo sát. Đề xuất chạy lưới 0,01%, 0,1% và 1% số giao dịch.
- Kỹ thuật che giấu như sát ngưỡng phê duyệt, chia nhỏ hoá đơn, số tiền tròn: là dấu hiệu cảnh báo kiểm toán, ACFE không cho tần suất của từng kỹ thuật.
- Ngưỡng phê duyệt tiền đồng của công ty giả lập.

---

## 5. Thiết kế đánh giá

1. **Khối lượng cảnh báo trên nền thật.** Chạy thư viện quy tắc trên BPI 2019, BPI 2020 và bộ chi trả của thành phố; báo cáo số cảnh báo trên mỗi 1.000 giao dịch của từng quy tắc, cùng kết quả xem thủ công một mẫu nhỏ. Vì không có nhãn, không được gọi kết quả này là độ chính xác.
2. **Tỷ lệ phát hiện theo từng kịch bản.** Chèn F1 đến F8 vào nền thật và vào công ty tổng hợp; báo cáo tỷ lệ phát hiện riêng cho từng loại thay vì một con số gộp, và độ chính xác trong K cảnh báo đầu tiên với ngân sách cảnh báo cố định (giả định thiết kế: không quá 5 cảnh báo mỗi tuần, dựa trên yêu cầu ở Phần 4 rằng doanh nghiệp nhỏ không có nhân lực rà soát hàng chục cảnh báo).
3. **Độ sớm.** ACFE cho thấy gian lận điển hình kéo dài 12 đến 18 tháng trước khi bị phát hiện; đo số tháng từ lúc gian lận bắt đầu đến lúc hệ thống đưa cảnh báo đầu tiên, so với mốc này.
4. **Độ trôi theo thời gian.** Tách theo thời gian (huấn luyện các tháng đầu, kiểm tra các tháng sau) và đổi kiểu chèn giữa hai giai đoạn, vì người gian lận thay đổi cách làm; bài BAF và hiện tượng sụt giảm sau bước 43 của Elliptic đều cho thấy việc này làm giảm hiệu quả.
5. **Đối chiếu ngoài.** Chạy trên ERP Fraud Data và báo cáo riêng kết quả, kể cả khi kém hơn kết quả trên dữ liệu ta tự chèn; chênh lệch cho biết bộ chèn của ta dễ hơn thực tế đến mức nào.
6. **Công bằng và quyền riêng tư.** Giám sát ở mức nhân viên chạm tới dữ liệu cá nhân, nên phải có căn cứ pháp lý và thông báo theo Nghị định 13/2023/NĐ-CP; hệ thống chỉ gắn cờ giao dịch và đưa ra lý do, không kết luận về cá nhân (con người quyết định cuối cùng, như thiết kế chung của hệ thống).

---

## 6. Thu thập

| Ưu tiên | Nguồn | Cách lấy | Dung lượng | Ghi chú |
|---|---|---|---|---|
| 1 | calibration_fraud.json | Đã tạo | nhỏ | Chép từ ACFE |
| 2 | BPI 2020 (năm bộ) | Tập lệnh (bpi2020) | khoảng 5,5 MB | CC BY-NC 4.0 |
| 3 | BPI 2019 | Tập lệnh Phần 5 (bpi2019) | 728,6 MB | CC BY 4.0 |
| 4 | ERP Fraud Data | Thủ công, Google Drive | 190 MB | Chưa xác nhận giấy phép |
| 5 | ICIJ Offshore Leaks | Thủ công qua trang chính thức | chưa xác định | Đọc điều khoản trước |
| 6 | Chi trả của thành phố Chicago, Checkbook NYC | Thủ công hoặc giao diện lập trình | tuỳ phạm vi | Thử lại bằng trình duyệt |
| 7 | Elliptic, AML-Data, SAML-D, BAF | Thủ công qua Kaggle | theo bộ | Chỉ để thử phần mã |

Tôi chưa chạy việc tải nào. Lệnh thử:

```bash
python agent2_data/fetch_agent2_data.py --list
python agent2_data/fetch_agent2_data.py --only bpi2020
```

---

## 7. Những gì tôi chưa kiểm chứng

- Giấy phép của ERP Fraud Data, số dòng và các cột cụ thể của bảng đã tổng hợp.
- Giấy phép, cột và điều kiện tải của bộ Payments Chicago, Checkbook NYC (máy chủ từ chối truy cập tự động), và trang tải của ICIJ.
- Số bản ghi chính xác của BankSim (không nêu trong kết quả tôi tra được) và các bộ dữ liệu tương ứng của AML-Data.
- Đường dẫn cloud825 trong danh sách: không tìm thấy khi tra cứu; nếu bạn còn nguồn gốc của nó, tôi có thể kiểm tra lại.
- Thời gian kéo dài của gian lận tham nhũng và gian lận qua máy tính tiền (register disbursements) trong ACFE: văn bản trích xuất không cho phép ghép nhãn với số một cách chắc chắn.
- Số liệu gian lận nội bộ riêng cho Việt Nam: không tìm thấy nguồn công khai đáng tin.

---

## 8. Nhật ký kiểm chứng ngày 20/09/2026

| Mục | Kết quả |
|---|---|
| Bản PDF ACFE 2024 (acfe.com) | Đã tải để đọc và tách văn bản 106 trang; xác nhận các bảng ở trang 4, 13, 16, 32, 34, 44 |
| Bản PDF Weber và cộng sự 2019 | Đã đọc bảng kết quả (Precision, Recall, F1) |
| Bản PDF Tritscher và cộng sự 2022, bản PDF BAF | Đã đọc phần dữ liệu và kịch bản |
| Giao diện figshare, năm bộ BPI 2020 | Hoạt động; giấy phép CC BY-NC 4.0; tên và kích thước tệp |
| Trang ERP Fraud Data | Hoạt động (mô tả và dung lượng 190 MB) |
| Chicago Payments, trang ICIJ | Bị từ chối (403, 405) khi truy cập tự động |
| Kho mã SyntheticData | Lỗi 404 |
| Các đường dẫn Kaggle trong danh sách | Trang Kaggle trả mã 200 kể cả với đường dẫn cloud825 mà tôi không xác nhận được, nên mã 200 không dùng làm bằng chứng tồn tại của bộ dữ liệu |

---

## 9. Nguồn chính

- [ACFE, Occupational Fraud 2024: A Report to the Nations (PDF)](https://www.acfe.com/-/media/files/acfe/pdfs/rttn/2024/2024-report-to-the-nations.pdf)
- [Weber và cộng sự 2019, Anti-Money Laundering in Bitcoin](https://arxiv.org/pdf/1908.02591)
- [Tritscher và cộng sự 2022, Open ERP System Data For Occupational Fraud Detection](https://arxiv.org/pdf/2206.04460)
- [Đại học Würzburg, ERP Fraud Data](https://www.informatik.uni-wuerzburg.de/datascience/projects/machine-learning-for-cyber-security-fraud-detection/deepscan-concluded/erp-fraud-data/)
- [Jesus và cộng sự 2022, Bank Account Fraud (NeurIPS)](https://arxiv.org/pdf/2211.13358)
- [Lopez-Rojas và cộng sự 2016, PaySim](https://www.msc-les.org/proceedings/emss/2016/EMSS2016_249.pdf)
- [Lopez-Rojas và Axelsson 2014, BankSim](http://www.msc-les.org/proceedings/emss/2014/EMSS2014_144.pdf)
- [IBM AMLSim](https://github.com/IBM/AMLSim)
- [Altman và cộng sự 2023, Realistic Synthetic Financial Transactions for Anti-Money Laundering Models](https://arxiv.org/abs/2306.16424)
- [SAML-D, Oztas và cộng sự 2023](https://eprints.bournemouth.ac.uk/40982/)
- [BPI Challenge 2020, 4TU](https://data.4tu.nl/collections/_/5065541/1)
- [BPI Challenge 2019, 4TU](https://data.4tu.nl/articles/dataset/BPI_Challenge_2019/12715853)
- [ADBench, NeurIPS 2022](https://github.com/Minqi824/ADBench)
- [Thành phố Chicago, Payments](https://data.cityofchicago.org/Administration-Finance/Payments/s4vu-giwb)
- [Checkbook NYC, API](https://www.checkbooknyc.com/api-page)
- [ICIJ Offshore Leaks Database](https://offshoreleaks.icij.org/pages/database)
- [Cổng công bố bản án, Tòa án nhân dân tối cao](https://congbobanan.toaan.gov.vn/)
- [Tra cứu người nộp thuế, Tổng cục Thuế](http://tracuunnt.gdt.gov.vn/)
