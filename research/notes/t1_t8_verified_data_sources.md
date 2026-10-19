# Nguồn dữ liệu thật cho T1–T8: khả năng lấy và mức sát domain

> **Riêng T1:** dùng [đề xuất dataset](t1_dataset_recommendation.md) và [audit toàn bộ hai nguồn Séc](t1_czech_full_dataset_audit.md) để chọn nguồn và cohort. BPI/DC là hướng bổ trợ.

Kiểm tra ngày **18/10/2026**. Domain đích: **SME Việt Nam bán chịu B2B, có liên kết hóa đơn–phân bổ tiền–sao kê, dự báo dòng tiền 13 tuần**. Nhiệm vụ được hiểu theo [bản đồ T0–T13](../../docs/explanation/user-needs-and-tasks.md).

Đây là rà soát nguồn có chọn lọc, gồm metadata của nhà phát hành và một số kiểm tra HTTP/API nhỏ. [Nhật ký kiểm tra truy cập](../references/data-checks/t1-t8/data_sources_t1_t8_access_checks.json) ghi phần kiểm tra ban đầu; bằng chứng tải và audit toàn bộ nguồn Séc nằm trong báo cáo T1 liên kết trên. Các mức gần domain và khuyến nghị bên dưới là đánh giá nguồn, chưa phải kết quả train.

## 1. Kết luận theo từng task

**Có thể bắt đầu chắc nhất với T4; T1 và T2 có benchmark thật khác miền; T7 có dữ liệu thật để thử detector và biến ngoại sinh. T5 có nguồn quy tắc Việt Nam. T3, T6 và T8 vẫn cần dữ liệu đối tác để kiểm chứng đúng toàn bộ task.** Trong các nguồn đã kiểm tra, chưa xác minh được một dataset công khai đáp ứng đầy đủ domain đích cho cả chuỗi.

| Task | Nguồn nên ưu tiên | Dùng được vào việc gì? | Mức gần domain và giới hạn |
|---|---|---|---|
| **T1 — thời điểm trả** | Hai nguồn hóa đơn Bộ Tài chính và ngành y tế Séc đã tải/audit | Chuẩn bị benchmark thời gian phát hành/nhận hóa đơn → ngày trả và độ trễ so với hạn, sau khi chốt nhãn và xử lý trùng | B2G Séc; chưa chứng minh có toàn bộ danh mục chưa trả hoặc ngày tiền thực vào ngân hàng bên bán |
| **T2 — không trả/vỡ nợ** | SBA 7(a) & 504 FOIA | Benchmark rủi ro khoản vay doanh nghiệp nhỏ | Gần đối tượng SME, khác sản phẩm, quốc gia và chân trời; không phải nhãn nợ xấu từng hóa đơn |
| **T3 — trả một phần/tranh chấp** | Chưa có nguồn mở đã xác minh đủ nhãn; UK Payment Practices làm tham chiếu | Tham chiếu hành vi thanh toán/chính sách; nghiên cứu đối soát qua BPI | Thiếu allocation và nhãn tranh chấp cấp hóa đơn; không đủ train và test đầy đủ T3 |
| **T4 — doanh thu mới** | UCI Online Retail II | Chuỗi doanh thu/giao dịch theo tuần, khách, sản phẩm | Lựa chọn công khai tốt trong nhóm đã kiểm tra; có nhiều khách bán buôn. Khác Việt Nam/ngành/thời kỳ; thiếu lịch thu nợ |
| **T5 — lịch chi cố định** | Văn bản chính thức Việt Nam + lịch/hợp đồng/bảng lương của đối tác | Mã hóa quy tắc và đối chiếu lịch nghĩa vụ | Sát quốc gia/nghiệp vụ khi đầu vào của DN là thật; văn bản luật không phải dataset train ML hoặc lịch chi thực tế của một DN |
| **T6 — mô phỏng dòng tiền** | Sao kê + AR/AP + nghĩa vụ của DN; nguồn công khai chỉ bổ trợ | Đo đường số dư, dòng thu/chi và sự kiện thiếu tiền | Chưa có nguồn mở đã xác minh đủ liên kết và tần suất cho kiểm định SME VN 13 tuần |
| **T7 — điểm gãy/chế độ** | TCPD cho detector; OxCGRT Việt Nam, WDI cho bối cảnh | Benchmark change point; biến ngoại sinh/stress | Dữ liệu thật, nhưng nhãn điểm gãy tổng quát hoặc chính sách/vĩ mô không phải nhãn khủng hoảng thanh toán của DN |
| **T8 — lời hứa trả** | Nhật ký hứa trả gắn với allocation/sao kê của đối tác | Học và đánh giá lời hứa có được thực hiện đúng ngày/số tiền | Chưa xác minh được nguồn mở đủ lời hứa, thời điểm ghi nhận và kết quả thực trả cho B2B SME VN |

Không nên gộp “dữ liệu thật”, “nguồn uy tín”, “tải được”, “được phép dùng” và “cùng domain” thành một thuộc tính. Ví dụ, dữ liệu báo cáo tài chính SEC là thật nhưng không đủ nhãn số dư tiền tuần; một file có schema giống SAP chưa chứng minh nó là dữ liệu doanh nghiệp thật.

## 2. Các nguồn có thể đưa vào kế hoạch lấy dữ liệu

Hai nguồn Séc được mô tả tại [hướng dẫn dữ liệu T1](../../data/T1/README.md). Các mục BPI/DC dưới đây là hướng bổ trợ; [đối chiếu field với pipeline](t1_bpi_dc_field_audit.md) giải thích vì sao chưa thể dùng chúng thay trực tiếp dữ liệu AR.

### S1. BPI Challenge 2019 — T1, bổ trợ T3/T0

- **Nguồn:** [TU/e, mô tả của người công bố](https://research.tue.nl/en/datasets/bpi-challenge-2019/); [record 4TU](https://data.4tu.nl/articles/_/12715853/1); DOI `10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1`.
- **Bản chất:** log purchase-to-pay thật đã ẩn danh của tập đoàn sơn/chất phủ hoạt động từ Hà Lan. Case là **purchase document × line item**, không mặc định một invoice. Mô tả nguồn có trường hợp nhiều hóa đơn/receipt trên một item.
- **Lấy và sử dụng:** record DOI trả HTTP 200 khi kiểm tra trực tiếp; metadata của record ghi **CC BY 4.0**. Có thể lấy file từ record, ghi citation và phiên bản. Chưa tải file log đầy đủ trong lần này.
- **Đề xuất:** thử time-to-clear/process completion và ảnh hưởng ghi sổ theo lô; giữ đúng case grain khi dựng benchmark.
- **Không kết luận:** sự kiện `Clear Invoice` là tiền đã khả dụng ở ngân hàng bên bán; dữ liệu này đủ nhãn invoice default hoặc dispute. Không tự điền `due_date` chưa được nguồn cung cấp.

### S2. DC PASS Payments — T1; ứng viên nghiên cứu allocation cho T3

- **Nguồn chính thức:** [ArcGIS REST của District of Columbia](https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Government_Operations/MapServer/17).
- **Bằng chứng kiểm tra:** thống kê aggregate toàn bảng và profile mẫu theo fiscal year được duy trì tại [đề xuất dataset T1](t1_dataset_recommendation.md). Schema gồm `INVOICENUMBER`, `SUPPLIERNAME`, `INVOICEDATE`, `PAYMENTDATE`, `ESTPAYMENTDATE`, `VOUCHERAMOUNT`, `PAYMENTAMOUNT`, `PAYMENTNUMBER`.
- **Đề xuất:** benchmark `PAYMENTDATE - INVOICEDATE` và thời gian còn lại tại cutoff trên dữ liệu đã thanh toán. Đây là dữ liệu **chính quyền trả nhà cung cấp, B2G Mỹ**.
- **Giới hạn cần xử lý:** không coi `ESTPAYMENTDATE` là hạn trả hợp đồng; payment date chưa chứng minh ngày tài khoản bên bán được ghi có. Tập payments không tự chứa toàn bộ hóa đơn chưa trả, nên không đủ để suy ra xác suất không trả hay dựng risk set survival đầy đủ. Cần xác minh grain, adjustment, duplicate và ý nghĩa voucher trước khi suy ra partial payment.
- **Quyền dùng:** API công khai có thể đọc được; `copyrightText` trong schema đang null. Điều đó không tương đương một giấy phép mở. **Cần chốt điều khoản sử dụng của bộ dữ liệu trước khi phát hành lại/đưa vào bộ dữ liệu chính.**

### S3. SBA 7(a) & 504 FOIA — T2

- **Nguồn:** [SBA Open Data](https://data.sba.gov/dataset/7a-504-foia), có CSV và data dictionary; cổng ghi cập nhật theo quý và license **U.S. Government Works**. Đường dẫn dictionary trả HTTP 200 trong lần kiểm tra.
- **Đề xuất:** thử mô hình rủi ro khoản vay SME, calibration và thiết kế đánh giá theo thời gian. Lấy dữ liệu trực tiếp từ SBA, giữ ngày phát hành/quan sát.
- **Giới hạn:** nhãn charge-off khoản vay không đồng nhất với default/mất tiền của hóa đơn. Không phân loại khoản chưa đủ follow-up thành không default; trạng thái bị che/không rõ không được tự coi là nhãn âm. Chi tiết code nhãn phải theo dictionary của đúng phiên bản.

Đây là benchmark phương pháp ngoài miền, không phải nguồn để khẳng định PD hóa đơn Việt Nam được hiệu chỉnh đúng. Không mặc định pretrain trên SBA rồi fine-tune sẽ tốt hơn baseline chỉ dùng dữ liệu hóa đơn đích.

### S4. Online Retail II — T4

- **Nguồn:** [UCI](https://archive.ics.uci.edu/dataset/502/online+retail+ii), DOI `10.24432/C5CG6D`; **CC BY 4.0**, có nút tải XLSX. Đường dẫn ZIP chính thức trả HTTP 200 khi kiểm tra HEAD.
- **Bản chất:** giao dịch thật của nhà bán lẻ trực tuyến tại Anh giai đoạn 2009–2011; UCI nêu **nhiều khách là wholesalers**. Không nên gắn nhãn toàn bộ là B2C thuần.
- **Đề xuất:** tổng hợp doanh thu theo tuần, khách và sản phẩm từ số lượng/đơn giá, xử lý cancellation/return, rồi rolling-origin cho T4. Tách hóa đơn hiện có ở cutoff khỏi giao dịch phát sinh sau cutoff.
- **Giới hạn:** dữ liệu phát hành hóa đơn/bán hàng không đồng nghĩa tiền đã thu. Không có bộ ngày hạn–ngày thực thu để đánh giá T1 hoặc chuyển doanh thu thành cash-in mà không có giả định thêm.

Đây là lựa chọn nên tải và dùng đầu tiên cho benchmark T4 trong nhóm nguồn đã kiểm tra. Tính đại diện cho bán chịu B2B SME VN vẫn cần dữ liệu đích.

### S5. UK Payment Practices — tham chiếu T1/T3

- **Nguồn chính phủ:** [giới thiệu dịch vụ](https://www.gov.uk/check-when-businesses-pay-invoices), [trang export CSV toàn bộ báo cáo](https://check-payment-practices.service.gov.uk/export/). Trang export ghi OGL v3, trừ nội dung có quy định khác.
- **Dữ liệu:** các câu trả lời thống kê và yes/no do doanh nghiệp báo cáo; phần narrative xem tại URL từng report. Có thời gian trả trung bình và tỷ lệ thanh toán không đúng hạn.
- **Đề xuất:** tham chiếu phân phối hành vi chi trả B2B của doanh nghiệp lớn, đối chiếu giả định synthetic và xem chính sách xử lý thanh toán/tranh chấp được công bố.
- **Giới hạn:** **report doanh nghiệp/kỳ, không phải invoice/payment/allocation row**. Cổng nhà nước không có nghĩa từng quan sát doanh nghiệp tự báo cáo đã được kiểm toán. Không dùng để train supervised classifier tranh chấp từng hóa đơn.

### S6. Australian Payment Times Register — nguồn dự phòng tham chiếu

[Hướng dẫn chính thức](https://paymenttimes.gov.au/register/how-to-use-the-register) được công cụ tìm kiếm ghi nhận có dataset tải miễn phí về payment times/terms. Tuy nhiên, mở trực tiếp đường dẫn này và `/register` trong phiên kiểm tra trả 404. **Chưa xếp là đường tải đã xác nhận hoạt động.** Nếu truy cập được cổng mới, cần kiểm tra license và schema trước khi lấy.

Ưu điểm nghiệp vụ là chủ đề doanh nghiệp lớn trả nhà cung cấp nhỏ. Tuy vậy, báo cáo tổng hợp theo kỳ vẫn không phải bộ hóa đơn SME Việt Nam hoặc nhãn allocation/dispute cấp giao dịch.

## 3. Nguồn sát Việt Nam nhưng không thay thế bảng giao dịch

### S7. Viet Nam SME database — UNU-WIDER/CIEM/ILSSA/UCPH

[Trang cơ sở dữ liệu chính thức](https://www.wider.unu.edu/database/viet-nam-sme-database) mô tả khảo sát lặp lại doanh nghiệp nhỏ và vừa, có module economic accounts về doanh thu, chi phí, tài sản, nợ. Trang công bố các đợt dữ liệu lịch sử và yêu cầu hoàn thành form để truy cập một số bộ enterprise/employee.

**Nên dùng:** đặc điểm doanh nghiệp đích, quy mô/ngành, kiểm tra mức hợp lý của giả định mô phỏng. **Không đủ:** chuỗi invoice–payment–bank theo ngày/tuần hoặc lời hứa trả. Dữ liệu khá cũ; cần đọc thiết kế mẫu và không coi là đại diện đầy đủ cho SME VN hiện nay. Chưa nộp form hay tải microdata trong phiên này; điều kiện dùng theo nhà cung cấp.

### S8. Viet Nam World Bank Enterprise Survey 2023

[Metadata chính thức](https://microdata.worldbank.org/catalog/6477/study-description), mã `VNM_2023_WBES_v01_M`, có đường **Get Microdata** và [questionnaire/implementation report](https://microdata.worldbank.org/catalog/6477/related-materials). Phạm vi gồm doanh nghiệp nhỏ/vừa/lớn; formal establishments từ 5 lao động, có nội dung sales, finance và commercial disputes.

**Nên dùng:** đối chiếu đặc điểm VN và phân tích thương mại/tranh chấp **cấp cơ sở kinh doanh**, sau khi kiểm tra câu hỏi và điều kiện truy cập. Không tự giả định toàn bộ mẫu là SME hoặc các biến “commercial disputes” chính là tranh chấp không trả từng hóa đơn. Không có cơ sở biến khảo sát này thành lịch cash-in 13 tuần. Chưa đăng ký hoặc lấy file microdata trong lần này.

Đây là hai nguồn nên ưu tiên tìm hiểu khi cần **sát đối tượng Việt Nam**. Mức sát đối tượng không bù được thiếu nhãn, grain và tần suất cần cho T1/T3/T6/T8.

## 4. T5, T6, T7 và T8 cần loại dữ liệu nào?

### T5 — nguồn quy tắc thật, còn đầu vào doanh nghiệp cần thu thập

Dùng [hệ thống văn bản Chính phủ](https://chinhphu.vn/he-thong-van-ban?classid=1&orggroupid=1), [CSDL văn bản pháp luật](https://vbpl.moj.gov.vn/vanphongchinhphu/Pages/vbpq-toanvan.aspx?ItemID=175027&Keyword=) để tìm văn bản gốc, lịch sử hiệu lực và văn bản hợp nhất. Link thứ hai là ví dụ record có metadata hiệu lực, **không phải khẳng định văn bản đó đang áp dụng cho mọi kỳ**.

Lưu rule cùng nguồn, phiên bản và khoảng hiệu lực. Lịch chi thực còn cần hợp đồng, payroll, hồ sơ thuế/bảo hiểm và thông báo nghĩa vụ của chính DN. Vì T5 là rule engine, đánh giá bằng ca quy tắc và lịch nghĩa vụ thực; không cần tìm “dataset train ML” cho mọi khoản chi. Bản rà soát này không chốt mức thuế hay thời hạn nộp cụ thể.

### T6 — cần chuỗi tiền thực, không có dataset riêng thay cho T1–T5

Để đo số dư và rủi ro thiếu tiền 13 tuần, cần tối thiểu opening balance, cash-in/out theo ngày, liên kết công nợ và lịch nghĩa vụ, trên các cửa sổ có đủ follow-up. Chính xác dòng thu từ AR và chính xác số dư toàn doanh nghiệp là hai phạm vi đánh giá khác nhau.

- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) là nguồn báo cáo tài chính thật, API không cần key. Nhưng cash flow quý/năm không cung cấp đường tiền tuần để chấm đúng T6; không nội suy thành “ground truth” 13 tuần.
- [Small Firm Diaries của NYU FAI](https://www.smallfirmdiaries.org/) mô tả nghiên cứu thật về dòng tài chính tần suất cao của doanh nghiệp nhỏ. Đây là ứng viên gần SME hơn báo cáo công ty niêm yết; **chưa xác minh được đường tải microdata và điều kiện cấp quyền** trong lần này. Có publication không đồng nghĩa có raw data mở.
- Berka thường được đề xuất cho giao dịch ngân hàng; bản rà soát này chưa xác minh được bản tải với nhà cung cấp gốc/giấy phép, nên không nâng bản mirror lên nhóm nguồn đã xác nhận. Giao dịch tài khoản không có liên kết hóa đơn–nghĩa vụ cũng chưa đủ T6 đích.

Khuyến nghị: giữ synthetic cho kiểm thử có kiểm soát; việc kiểm định cash balance thật cần dữ liệu đối tác. Không ghép SBA, retail và sao kê không cùng doanh nghiệp rồi gọi đó là bộ dữ liệu thực tích hợp.

### T7 — hai mục đích khác nhau

1. **Kiểm tra thuật toán điểm gãy:** [TCPD](https://github.com/alan-turing-institute/TCPD) và [TCPDBench](https://github.com/alan-turing-institute/TCPDBench) do nhóm Alan Turing Institute công bố; có chuỗi thực và annotation. Truy cập annotation JSON trả 200. License MIT của code không bao phủ mọi data file: README yêu cầu kiểm tra điều kiện riêng từng chuỗi.
2. **Biến ngoại sinh VN:** [OxCGRT chính thức](https://github.com/OxCGRT/covid-policy-dataset), CC BY 4.0, chứa chính sách COVID giai đoạn 2020–2022 và có thể lọc Việt Nam. [World Bank Indicators API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392) không cần key; thử query CPI Việt Nam đã trả JSON. [Điều khoản World Bank](https://data.worldbank.org/summary-terms-of-use) mặc định CC BY 4.0 với ngoại lệ theo metadata nguồn/chỉ tiêu.

TCPD phù hợp kiểm tra detector tổng quát, không tự kiểm chứng cảnh báo công nợ. OxCGRT không đo khách hàng chậm trả; WDI nhiều chỉ tiêu theo năm, không phải tín hiệu tuần. Khi backtest online, dùng dữ liệu/phiên bản đã công bố tại cutoff, không lấy bản sửa cuối cùng làm thông tin đã biết trong quá khứ.

### T8 — cần promise và kết quả thanh toán được liên kết

Trong các nguồn đã kiểm tra, **chưa xác nhận được dataset mở, có xuất xứ và quyền dùng rõ, chứa đồng thời lời hứa B2B, thời điểm ghi nhận, số tiền/ngày đã hứa và kết quả tiền thực nhận**. Đây là kết luận giới hạn trong phạm vi rà soát, không khẳng định loại dữ liệu này không tồn tại ở bất cứ đâu.

[DebtBench/DebtGPT, ACL 2026](https://aclanthology.org/2026.acl-long.232/) công bố benchmark đàm phán đòi nợ và code/data. Mô tả công khai này chưa chứng minh có longitudinal promises gắn với giao dịch ngân hàng để chấm T8. Không dùng chất lượng hội thoại hoặc nhãn “promise_to_pay” cuối cuộc gọi thay cho việc thực hiện lời hứa sau đó.

Nguồn đúng nhiệm vụ nên lấy từ ERP/CRM hoặc form ghi lời hứa của đối tác: `promise_id`, customer/invoice, thời điểm ghi nhận, ngày/số tiền hứa, kênh, lịch sử sửa, allocation thực nhận và outcome sau khi đủ thời gian quan sát. Promise chưa đến hạn không phải promise bị phá. Không cần lưu nguyên văn Zalo/cuộc gọi nếu các trường cấu trúc đã đáp ứng mô hình.

## 5. Các nguồn không nên coi là “sẵn dùng đúng domain”

| Nguồn/nhận định | Cách xử lý |
|---|---|
| File gọi là SAP/HighRadius/Customer Invoices trong repo cộng đồng | Chưa xác minh publisher gốc, real/synthetic, quyền cung cấp và license thì chỉ xem là dữ liệu thực hành chưa rõ xuất xứ; USD không xác định quốc gia |
| Home Credit Default Risk | [Cổng competition gốc](https://www.kaggle.com/competitions/home-credit-default-risk/data) là hướng dữ liệu tín dụng tiêu dùng; cần đăng nhập/rules và kiểm tra dictionary. Có thể thử phương pháp installment/repayment ngoài miền; chưa dùng làm bằng chứng dispute hoặc B2B invoice VN |
| M5/Favorita | Benchmark doanh số bán lẻ có thể bổ sung T4 sau khi kiểm tra điều kiện; không thay nhãn T1/T2/T8 |
| Dữ liệu hóa đơn OCR/XML | Giúp extraction/schema; không mặc định có ngày thực trả, allocation hoặc outcome lời hứa |
| Danh sách nợ thuế/cảnh báo doanh nghiệp | Sự kiện thuế/pháp lý không đồng nhất với việc một hóa đơn bán chịu bị mất khả năng thu hồi |
| Báo cáo Atradius/Coface | Tham chiếu thống kê khi nguồn/điều kiện rõ; không tự trở thành microdata từng hóa đơn |

Đặc biệt, không tự dựng nhãn tranh chấp từ “quá hạn”, không xem `clear_date` là ngân hàng ghi có khi chưa đối soát, và không lấy một khoản trả thiếu tại một thời điểm làm khoản mất vĩnh viễn.

## 6. Kế hoạch lấy dữ liệu đề xuất

| Ưu tiên | Việc cụ thể | Đầu ra được phép kỳ vọng |
|---|---|---|
| **1** | Lấy UCI Online Retail II từ nhà phát hành; lưu license/citation/hash | Benchmark T4 thực, ngoài miền |
| **2** | Chốt nhãn, xử lý trùng và dựng adapter cho hai nguồn Séc đã audit | Benchmark timing T1 riêng theo nguồn/buyer; chưa phải kiểm định danh mục AR mở |
| **3** | Lấy SBA CSV + dictionary đúng phiên bản | Benchmark T2 khoản vay SME, tách khỏi nhãn hóa đơn |
| **4** | Lấy UK PPR; chọn chuỗi TCPD có quyền dùng phù hợp; lọc OxCGRT VN | Thống kê tham chiếu và đánh giá T7 theo phạm vi cụ thể |
| **5** | Khi cần benchmark bổ trợ, chốt quyền dùng/audit DC PASS; chỉ mở rộng BPI khi có câu hỏi quy trình riêng | Benchmark ngày thanh toán B2G hoặc process/clear, theo giới hạn grain và nhãn từng nguồn |
| **6** | Theo quy trình truy cập UNU-WIDER/WBES; không tự nộp hồ sơ thay người dùng | Tham chiếu đối tượng VN và các giả định |
| **7** | Xin bộ xuất ẩn danh của đối tác gồm invoice, allocation, sao kê, nghĩa vụ và promises | Nền tảng kiểm chứng T1/T3/T5/T6/T8 đúng domain |

Đề xuất phạm vi công bố nghiên cứu: **“Benchmark theo từng thành phần trên dữ liệu thực công khai khác miền, kết hợp kiểm thử synthetic; hiệu quả đầu cuối trên SME Việt Nam cần dữ liệu doanh nghiệp có liên kết.”** Dữ liệu công khai đủ để bắt đầu nghiên cứu nhiều phần, nhưng chưa lấp được khoảng trống đánh giá sản phẩm đầu cuối.
