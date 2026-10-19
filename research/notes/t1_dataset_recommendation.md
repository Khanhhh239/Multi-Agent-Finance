# T1 — Nghiên cứu dataset và phương án đề xuất

> **Đã tải và audit toàn bộ hai nguồn Séc:** xem [kết quả kiểm tra đầy đủ](t1_czech_full_dataset_audit.md). Bộ Tài chính có 120.753 ID khác nhau trong các dòng tổng; y tế có 289.698 ID record. Số liệu mẫu trong tài liệu này được giữ để giải thích quá trình chọn nguồn, không phải quy mô toàn dataset.

Rà soát ngày **18/10/2026**. Đối chiếu yêu cầu dự án, mã dựng snapshot, nguồn công bố gốc và mẫu dữ liệu tải trực tiếp. Đây là **đề xuất lựa chọn dữ liệu**, chưa phải kết quả train hay audit toàn bộ các bộ dữ liệu.

**Làm rõ quy mô:** 1.956 hóa đơn Bộ Tài chính và 4.698 record y tế là **phần đã đọc để kiểm tra**, không phải toàn bộ dataset. File Bộ Tài chính có header dung lượng khoảng 399 MB nhưng chưa đếm tổng invoice; API y tế báo 289.698 record. 925 record y tế chỉ qua bộ lọc ngày/số tiền sơ bộ, không phải toàn bộ số invoice có thể dùng của nguồn. Có thể dùng phần phù hợp để train thử sau kiểm tra nghiệp vụ; chưa có căn cứ loại nguồn y tế vì “chỉ còn 925 dòng”.

## 1. Quyết định đề xuất

**Không chọn BPI làm dataset chính của T1. Ưu tiên kiểm tra toàn bộ dữ liệu hóa đơn Bộ Tài chính Séc cho benchmark công khai; bổ sung ngành y tế Séc nếu các nhóm dữ liệu đạt chất lượng. Đồng thời tìm dữ liệu AR của đối tác Việt Nam để kiểm định đúng nhiệm vụ.**

Hai loại bằng chứng phải được báo cáo riêng:

- **Benchmark công khai:** dự báo thời gian thanh toán/ghi nhận chi trả trên tập hóa đơn quan sát được, chủ yếu B2G ngoài Việt Nam. Chứng minh phương pháp ở phạm vi này.
- **Kiểm định đúng T1:** dự báo các hóa đơn phải thu đang mở của SME, gồm cả hóa đơn chưa trả tại ngày kết thúc quan sát. Cần danh mục invoice đầy đủ và lịch sử thanh toán của doanh nghiệp.

Trong phạm vi nguồn đã rà soát, **chưa xác nhận được bộ công khai đáp ứng đồng thời B2B SME Việt Nam, invoice-level, hạn trả, lịch sử thu tiền và toàn bộ công nợ chưa tất toán**. Không suy rộng thành khẳng định dữ liệu đó không tồn tại.

## 2. Dataset phải đáp ứng câu hỏi nào?

T1 hiện tại dự báo từ ngày chạy **T**: với hóa đơn còn mở, xác suất thu được tiền trong 7/30/60/91 ngày tới và thời gian còn lại đến sự kiện thanh toán.

| Thành phần | Tối thiểu cần có | Lý do |
|---|---|---|
| Đơn vị dự báo | Invoice ID ổn định; seller ID và buyer ID đúng vai trò | Không nhầm dòng PO, payment hay dòng phân bổ ngân sách thành một hóa đơn |
| Mốc bắt đầu | Ngày phát hành; ngày hệ thống biết hóa đơn nếu khác | Chỉ đưa hóa đơn vào tập dự báo khi nó đã tồn tại và khả dụng |
| Hạn thanh toán | Due date theo nguồn/hợp đồng; lịch sử sửa nếu có | Tính aging và baseline. Không tự gán net-30 hoặc lấy ngày dự kiến trả thay thế |
| Giá trị | Giá trị gốc, tiền tệ và số dư tại T | Số tiền thực chi trong tương lai không phải feature đã biết tại T |
| Sự kiện đích | Ngày thu lần đầu, thu đủ hoặc clear — chọn và ghi rõ | Các ngày này khác nhau khi trả một phần, bù trừ, ghi giảm hoặc đảo giao dịch |
| Công nợ chưa trả | Toàn bộ invoice thuộc phạm vi, gồm khoản chưa tất toán | Không chỉ chọn hóa đơn cuối cùng đã trả rồi coi đó là toàn bộ danh mục |
| Kết thúc quan sát | Ngày dữ liệu đầy đủ đến đâu, theo doanh nghiệp/nguồn | Xác định censoring; không suy ra từ ngày thanh toán lớn nhất |
| Thông tin khả dụng | Timestamp tạo/sửa, phiên bản hoặc giới hạn tái lập đã công bố | Backtest không sử dụng trạng thái cuối cùng như thể đã biết trong quá khứ |

**Due date không bắt buộc về mặt toán học đối với survival**, nhưng pipeline hiện tại cần nó. Một bộ thiếu due date vẫn làm được benchmark khác nếu bỏ feature và baseline phụ thuộc hạn trả; không nên ép dữ liệu cho khớp schema.

Để dự báo dòng tiền, cần thêm liên kết payment–invoice. Với hóa đơn trả nhiều lần, ngày tất toán cùng toàn bộ giá trị hóa đơn không tái hiện đúng lịch tiền về. MVP có thể tách nhóm trả một lần có bằng chứng rõ; nhóm còn lại cần mô hình dòng thu/phân bổ, không loại âm thầm.

## 3. Xếp hạng nguồn sau rà soát

Thứ tự dưới đây là **ưu tiên đầu tư công sức**, không phải thứ hạng chất lượng mô hình đã đo.

| Nguồn | Nguồn gốc / truy cập | Sát T1 đến đâu? | Đề xuất |
|---|---|---|---|
| **AR đối tác Việt Nam** | Dữ liệu riêng, cần đối tác cấp quyền; chưa có trong checkout | Gần nhất nếu đúng doanh nghiệp bán chịu và xuất đủ invoice/payment/open items | Nguồn đích cho kiểm định sản phẩm |
| **Bộ Tài chính Séc — hóa đơn đã trả** | Nhà công bố chính thức; CSV truy cập được; có metadata điều kiện sử dụng | Có issue/due/payment và amount; B2G, một bên mua; thiếu bằng chứng danh mục chưa trả đầy đủ | **Ứng viên công khai nên làm trước**, sau audit toàn bộ |
| **Ngành y tế Séc** | API chính thức truy cập được; điều kiện tái sử dụng cụ thể chưa chốt | Nhiều bên mua, có schema phù hợp; chất lượng khác nhau rõ giữa các nhóm | Nguồn bổ sung có điều kiện, chọn nhóm chất lượng và công bố phần loại |
| **DC PASS** | API chính thức truy cập được; cần chốt điều khoản áp dụng cho bảng | Có ngày invoice/payment; thiếu due date được xác minh; grain và schema khác theo giai đoạn | Benchmark bổ trợ về thời gian chi trả, không nạp thẳng pipeline |
| **BPI 2019** | Log doanh nghiệp thật; file gốc truy cập được; CC BY 4.0 trên record phát hành | PO-item, nhiều invoice/case; không có invoice ID/due date trong mẫu đã đọc | Benchmark quy trình; không ưu tiên để dựng invoice-level T1 |
| **Barnet late payments** | Cổng chính quyền, nêu OGL v3; có file XLSX | Chọn các khoản trả trễ, không đại diện toàn bộ invoice | Chỉ phân tích nhóm trễ/đối chiếu, không train mô hình on-time vs late chung |
| **Stemly trong paper Saini et al.** | Dữ liệu nghiên cứu thật nhưng bị hạn chế truy cập | AR gần task hơn các log mua hàng | Hướng xin quyền học thuật; chưa phải dữ liệu tải tự do |
| **SAP/HighRadius/Kaggle hiện được nhắc trong dự án** | Có nhiều bản chia sẻ lại; chưa xác minh publisher gốc và quyền phân phối; file local đang vắng | Schema gần pipeline nhất; nguồn gốc và cách lấy mẫu chưa chắc chắn | Chỉ thực hành khi có quyền; chưa dùng làm bằng chứng dữ liệu thực uy tín |

## 4. Những gì đã kiểm tra trực tiếp

### 4.1. Bộ Tài chính Séc: ứng viên ưu tiên cho benchmark công khai

[Hướng dẫn của nhà công bố](https://data.mf.gov.cz/stories/navod-faktury.html) phân biệt dòng tổng hóa đơn `souhrnný` với dòng ngân sách `položkový`; phải chọn đúng grain để tránh cộng trùng. [CSV gốc](https://data.mf.gov.cz/exports/faktury/faktury.csv) truy cập được, header báo khoảng **399 MB**. Chỉ đọc tiền tố 2 MB, không tải toàn bộ.

Trong phần đã đọc: **5.322 dòng**, gồm **1.956 dòng tổng hóa đơn**. Có 1.949 dòng tổng parse được cả ngày phát hành, hạn trả và ngày trả. Đây là kết quả trên tiền tố, **không phải tỷ lệ chất lượng toàn corpus**. Chưa xác minh đầy đủ uniqueness, sửa dữ liệu, phân bổ thanh toán và ý nghĩa mọi mã chứng từ.

[Metadata điều kiện sử dụng](https://data.mf.gov.cz/katalog/cs/dataset/prehled-faktur-ministerstva-financi-cr/resource/649107b9-e2d8-4b47-92c5-024c6a200c0a) ghi không có bảo hộ tác phẩm/quyền cơ sở dữ liệu được liệt kê, đồng thời báo có dữ liệu cá nhân. Không tự gán nhãn CC BY. Bản công bố mang tên hóa đơn **đã trả**; chưa đủ cơ sở đánh giá survival trên toàn danh mục mở.

**Thiết kế thí nghiệm:** thời gian từ phát hành đến ngày chi trả được ghi nhận, và độ trễ so với due date, trên cohort đã quan sát thanh toán. Buyer là bộ; supplier là bên bán. Lịch sử theo cặp seller–buyer có thể khác nhau, nhưng không được biến supplier thành customer có nghĩa vụ trả. Thắng baseline trên bộ này chưa chứng minh hiệu quả với nhiều khách mua của một SME.

### 4.2. Ngành y tế Séc: schema tốt hơn, chất lượng chưa đồng đều

[Tài liệu API chính thức](https://faktury.mzcr.cz/site/otevrena-data) có invoice ID, buyer/supplier, ngày phát hành/nhận/hạn trả/ngày trả, tiền hóa đơn và tiền đã trả. Endpoint `/rest/invoices` trả HTTP 200, không cần đăng nhập trong lần kiểm tra; header cho biết **289.698 bản ghi**. Đây là số record API, chưa phải số invoice nghiệp vụ duy nhất.

Đã đọc các trang 1/73/145/218/290, tổng **4.698 record**, không lấy mẫu ngẫu nhiên:

| Kiểm tra trên mẫu | Kết quả |
|---|---:|
| Số buyer / supplier ID khác nhau | 12 / 1.285 |
| Thiếu/không parse được ngày phát hành | 3.026 |
| Thiếu/không parse được due date | 1.266 |
| Thiếu ngày trả và đồng thời thiếu due date | 540 |
| Ngày trả là năm 1970, cần kiểm tra giá trị mặc định | 114 |
| Dòng tiền dương, đủ issue/due/paid hợp lệ từ năm 2000, paid ≥ issue | 925 |

925 dòng qua kiểm tra sơ bộ thuộc **3 buyer**; chưa phải tập train đã làm sạch. Trùng tham chiếu invoice cần kiểm tra theo buyer/supplier/import, dù ID record không trùng. Không xem 540 dòng thiếu ngày trả là 540 invoice đang mở: chúng đồng thời thiếu due date, có thể do chất lượng xuất dữ liệu. Ngày nhận có thể làm mốc thay thế trong thí nghiệm riêng, không điền vào issue date mà che mất khác biệt.

Kiểm tra tiếp cho thấy 925 dòng này chia thành các nhóm 413/450/62 dòng theo buyer, với khoảng ngày phát hành lần lượt 12/2018–07/2020, 05–08/2023 và 07–08/2026. Vì vậy, không coi chúng là chuỗi liên tục đại diện cho nhiều năm của cùng một danh mục. Bộ lọc sơ bộ chưa xác nhận paid date là thu đủ tiền, due ≥ issue, khóa invoice nghiệp vụ duy nhất hay amount đã biết tại cutoff. Không ngoại suy tỷ lệ 925/4.698 sang toàn bộ 289.698 record vì mẫu không ngẫu nhiên.

**Quyết định:** audit theo tổ chức × đợt import × thời gian, xác minh quyền tái sử dụng, rồi mới chọn nhóm làm benchmark đa bên mua. Không train bằng cách `dropna()` toàn bộ và bỏ qua các nhóm bị loại.

### 4.3. DC PASS: đã có thống kê toàn bảng, không chỉ 5 dòng mẫu

Truy vấn tổng hợp trên [API chính thức](https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Government_Operations/MapServer/17) trả **1.578.639 dòng** thuộc fiscal year 2017–2027. Fiscal year không đồng nghĩa năm dương lịch; FY2027 không tự là dữ liệu tương lai. Tất cả các dòng được đếm có `PAYMENTDATE`.

| Fiscal year | Dòng toàn bảng | Thiếu INVOICEDATE |
|---|---:|---:|
| 2020 | 197.343 | 11.955, khoảng 6,06% |
| 2023 | 97.252 | 402, khoảng 0,41% |
| 2024 | 85.317 | 0 |
| 2025 | 76.917 | 0 |
| 2026 | 70.164 | 0 |

Đọc thêm 1.000 dòng đầu theo OBJECTID cho mỗi FY2020/2024/2026. Mẫu FY2020 có 286 dòng dư trên khóa agency–supplier–invoice–voucher–payment; FY2024/2026 không trùng khóa này trong mẫu. 656/1.000 và 660/1.000 dòng FY2024/2026 có payment amount khác voucher amount. **Chưa xác định đây là partial payment, tổng payment gộp hay ý nghĩa khác; chưa được cộng/đổi tên tùy ý.**

**Quyết định:** nếu dùng DC, ưu tiên audit FY2024–2026 và so sánh schema theo giai đoạn. Thiếu contractual due date và tập invoice chưa trả vẫn là vấn đề chính. Không lấy `ESTPAYMENTDATE` làm due date. Không dùng created/updated của bản ghi hiện tại làm bằng chứng đầy đủ về mọi giá trị đã biết tại cutoff.

### 4.4. BPI: mẫu file gốc xác nhận khó khăn ở cấp invoice

[TU/e mô tả case là purchase document × item](https://research.tue.nl/en/datasets/bpi-challenge-2019/). Đã đọc tiền tố 2 MB của XES gốc, chứa **220 case hoàn chỉnh**, không đọc hết file khoảng 729 MB.

Mẫu có **813 event nhận hóa đơn, 562 event clear**; có case tới **125 event nhận hóa đơn**. Có cả `Vendor creates invoice`, vì vậy nguồn không chỉ có mốc nhận invoice. Tuy nhiên, các event trong mẫu chỉ có tên, timestamp, resource/user và giá trị net tích lũy; chưa có khóa invoice để ghép chắc chắn các event đó.

**Quyết định:** không lấy một case làm một invoice; không lấy lần create/receipt đầu và clear cuối để tạo nhãn T1. Có thể chọn nhóm case đơn giản cho benchmark quy trình với tiêu chí công bố rõ, nhưng không bảo đảm đó là invoice-level hay bank cash-in.

### 4.5. Các nguồn còn lại: vì sao chưa chọn?

- [Barnet](https://open.barnet.gov.uk/dataset/financial-invoices-late-payments-2g58n): có ngày, số tiền và thông tin trả trễ; chưa đọc các workbook trong lần này. Tập chọn theo outcome trễ không dùng để ước lượng tỷ lệ trễ chung.
- [Paper Saini et al. 2024](https://link.springer.com/article/10.1007/s44257-024-00013-2): dữ liệu phải có phép của Stemly; code bổ sung công khai không đồng nghĩa data mở. Paper cũng nêu các ứng dụng dùng invoice đã trả, không có censoring; không coi đó là kiểm chứng đầy đủ danh mục chưa trả.
- [Atomic Common-Day Invoice Clearing](https://data.mendeley.com/datasets/28rbmvwsm9/1): công bố invoice issue/due/amount và debtor/creditor, nhưng chưa xác nhận ngày thực trả. Kết quả clearing của thuật toán không phải nhãn cash payment thực tế. Chưa tải file; không chọn cho T1 timing.
- [Replication “Show Me the Receipts”](https://data.mendeley.com/datasets/b9y47f5skn/2): landing page công bố replication code, chưa xác nhận có microdata từng invoice đủ field. Không coi DOI là bằng chứng sẵn dữ liệu train.
- [Cook County CCP Invoice Register](https://catalog.data.gov/dataset/ccp-invoice-register): metadata chính thức có dữ liệu invoice/payment; endpoint schema và mẫu trả 403 từ môi trường kiểm tra. Chưa xác minh được field/giấy phép đủ để nâng ưu tiên.
- Kaggle/IBM/HighRadius: trang Kaggle được mở nhưng không đọc được data card đầy đủ; bản notebook cộng đồng có thể dùng dữ liệu private dù code có license mở. Không suy ra quyền data từ license code hoặc số bài báo trích lại nó.
- Home Credit/LendingClub/SBA/UCI retail: không ưu tiên cho T1 invoice timing. Có thể học phương pháp ở miền khác; chưa có bằng chứng transfer learning từ khoản vay giúp task này. Không ghép các bộ không cùng doanh nghiệp thành một ledger thật.

## 5. Dữ liệu nên xin từ đối tác

**Bắt đầu với một SME bán chịu có xuất dữ liệu ổn định**, ưu tiên ngành bán buôn/phân phối hoặc dịch vụ B2B phù hợp use case. Một đối tác đúng domain và xuất đủ lịch sử có giá trị kiểm định hơn nhiều dòng dữ liệu sai nhiệm vụ.

| Bảng | Trường đề nghị |
|---|---|
| Invoice | tenant/seller ID, invoice ID, buyer ID, issue date, posting/available date, due date, currency, giá trị gốc, loại chứng từ, canceled/void và timestamp |
| Payment và allocation | payment ID, invoice ID, số tiền phân bổ, ngày thanh toán/thu, ngày hệ thống biết, loại cash/credit/write-off, reversal và timestamp |
| Trạng thái/điều chỉnh | Các lần sửa due date, giá trị, số dư; credit note, hủy, bù trừ; ngày hiệu lực và ngày ghi nhận |
| Phạm vi trích xuất | Từ ngày nào, đầy đủ đến ngày nào, gồm cả open items, quy tắc lọc và các tháng bị thiếu |
| Đối soát nếu dự báo cash-in | Ngày tiền thực nhận và liên kết payment–bank; không cần chuyển toàn bộ nội dung sao kê để thử T1 nếu các trường cấu trúc đã đủ |

Mục tiêu lập kế hoạch: **12–24 tháng** để có nhiều chu kỳ, nếu có thể có từ hai mùa Tết thì tốt hơn; **3–6 tháng tiếp theo** để theo dõi ngoài mẫu. Đây là gợi ý thu thập, không phải ngưỡng đủ dữ liệu được chứng minh. Quy mô cần đánh giá bằng learning curve, số buyer độc lập, số sự kiện, tỷ lệ censoring và độ ổn định ở các cửa sổ kiểm thử; không đặt cứng “phải 50.000 invoice”.

Giữ ID giả danh ổn định giữa các lần xuất. Tách ngày thanh toán ERP và ngày ngân hàng nhận; nếu chỉ có ERP thì đặt tên target là ERP settlement. Không dịch ngày tùy ý rồi vẫn dùng lịch Việt Nam/Tết như dữ liệu gốc. Chưa liên hệ hay gửi yêu cầu dữ liệu thay người dùng.

## 6. Cách chạy thí nghiệm phù hợp từng loại dữ liệu

| Chế độ | Tập đánh giá | Kết luận được phép |
|---|---|---|
| **Observed-paid benchmark** | Các invoice có thanh toán được quan sát và mapping hợp lệ | So sánh timing trong cohort này; có selection bias, không đại diện toàn bộ công nợ |
| **Artificial censoring** | Cắt lịch sử của cohort có outcome biết sau đó để kiểm tra cách xử lý censoring | Kiểm tra phương pháp trên cohort đã chọn; không tạo thêm các invoice chưa từng xuất hiện trong nguồn |
| **Open-portfolio validation** | Toàn bộ invoice đang mở tại T của doanh nghiệp; event hoặc censor tại observation end | Đánh giá dự báo trên danh mục thực, trong phạm vi doanh nghiệp và kỳ quan sát |

Trên dữ liệu công khai đã trả, dùng baseline trung vị lịch sử và due-date baseline, rồi so với LightGBM/quantile hoặc discrete survival. Thiếu due date thì chỉ giữ baseline thời gian sống và feature hợp lệ. Không thêm độ phức tạp trước khi chứng minh có cải thiện ngoài mẫu.

Chia train → validation → test theo thời gian và rolling origin. Mô hình đóng băng ở ngày F chỉ được dùng nhãn/sự kiện đã khả dụng đến F; invoice chưa trả tại F phải được censor tại F. Không train bằng nhãn trả sau F rồi dự báo các mốc nằm trước ngày biết nhãn. Snapshot lặp của cùng invoice không phải các quan sát độc lập; báo thêm kết quả theo invoice, buyer và tuần, tách khách đã có lịch sử/khách mới.

Với các nguồn công khai chỉ xuất sau thanh toán, backtest ở ngày phát hành là **mô phỏng góc nhìn ERP nội bộ**, dựa trên giả định các trường gốc đã biết và chưa bị sửa; cần công bố giả định này. Nó không chứng minh có thể dự báo thời gian thực từ chính API công khai trước khi invoice được công bố.

**Đo gì:** MAE/pinball/coverage trên cohort có outcome phù hợp; Brier/calibration theo horizon với cách xử lý censoring có giả định được kiểm tra cho danh mục đầy đủ. Báo tỷ lệ và nguyên nhân loại record, sai số theo giá trị invoice, nhóm amount/aging/terms và cold-start. Chỉ chấm cash-in tuần khi có payment/allocation đúng grain; không dùng tổng giá trị invoice ở ngày tất toán làm ground truth dòng tiền nếu đã thu từng phần.

## 7. Những chỗ pipeline hiện tại cần đổi trước khi đổi dataset

Đối chiếu [survival_utils.py](../../notebooks/survival_utils.py) và [notebook 01](../../notebooks/01_data_preparation_eda.ipynb):

1. **Tách adapter theo nguồn**, giữ `source_dataset`, `source_record_id`, buyer/seller, currency và định nghĩa target. Không âm thầm ép PO item thành invoice hoặc supplier thành debtor.
2. **Đưa `observation_end` vào metadata.** `load_pools()` đang lấy `max(paid_date)`; đó không chứng minh dữ liệu đầy đủ đến ngày đó, nhất là với nhiều doanh nghiệp.
3. **Cấu hình cutoff/split theo dataset.** Hiện có ngày cố định năm 2020 và cửa sổ `pre/post shock`; không dùng nguyên cho dữ liệu Séc/DC. Censor nhãn đúng ngày đóng băng train và chặn event nằm ngoài observation end.
4. **Tách feature theo dữ liệu có thật.** Hàm hiện lọc thiếu due date và terms ≤ 0; terms bằng 0 có thể là điều khoản thật. Không loại nhóm đó hay điền terms chỉ để qua bộ lọc mà không có quyết định nghiệp vụ.
5. **Giữ amount gốc và remaining balance riêng**, phân biệt cash settlement với credit/write-off/cancel. Không áp FX USD/CAD cũ cho CZK hoặc VND.
6. **Lưu hai bảng kết quả riêng:** public observed-paid benchmark và partner open-portfolio validation. Không pool score của các nguồn rồi gọi là độ chính xác T1 cho SME Việt Nam.

Các thay đổi trên là đề xuất; **chưa sửa thuật toán hoặc chạy lại notebook** trong lần nghiên cứu này.

## 8. Thứ tự thực hiện cụ thể

1. **Audit đầy đủ Bộ Tài chính Séc:** tải streaming có version/hash; chỉ chọn dòng tổng; kiểm tra khóa, các năm có dữ liệu, loại chứng từ, ngày bất hợp lý, amount/currency và selection theo khoản đã trả. Qua bước này mới dựng adapter benchmark.
2. **Bổ sung ngành y tế Séc nếu cần nhiều buyer:** chốt điều kiện sử dụng; đo coverage theo tổ chức/tháng/import; xác minh thiếu ngày, giá trị năm 1970, các bản ghi lặp và ý nghĩa ngày trả/paid amount.
3. **Lấy AR đối tác song song:** xuất thử một kỳ, đối chiếu vài invoice từ phát hành đến thanh toán và vài open items, rồi mở rộng lịch sử. Có thể bắt đầu thu snapshot từ bây giờ nếu dữ liệu cũ không có lịch sử sửa.
4. **Chạy benchmark tối giản, sau đó mới mở rộng:** baseline → mô hình hiện có → đánh giá theo thời gian, bias và calibration. DC là kiểm tra bổ trợ; BPI chỉ đưa vào nếu có câu hỏi nghiên cứu quy trình riêng.

Nếu chưa lấy được AR đối tác, phạm vi nghiên cứu nên ghi: **“Dự báo thời điểm chi trả trên hóa đơn công khai B2G, kết hợp kiểm thử censoring có kiểm soát; khả năng áp dụng lên công nợ SME Việt Nam chưa được xác nhận.”**

## 9. Bằng chứng và giới hạn

- [Nhật ký truy cập, URL, response hash và thống kê API](../references/data-checks/t1/t1_dataset_deep_checks.json).
- [Profile các mẫu đã đọc](../references/data-checks/t1/t1_dataset_sample_profiles.json).
- [Script tính lại profile từ mẫu local](../../scripts/data_audit/audit_t1_source_samples.py), chỉ dùng Python standard library; không tự tải mạng.
- Mẫu BPI/DC được lưu local trong `data/T1/raw/source_samples/`, thuộc đường dẫn đã ignore của repo; JSON evidence không chứa tên supplier hay từng giao dịch. Mẫu Séc cũ đã xóa sau khi tải bộ đầy đủ; xem `data/T1/raw/czech/2026-10-18/`. Tiền tố XES BPI không phải toàn bộ dataset.
- Chưa tải đầy đủ corpus, chưa tạo tập train, chưa chốt mọi giấy phép và chưa thử nghiệm khả năng chuyển miền. Các tỷ lệ trên mẫu có ghi rõ phạm vi; chỉ bảng count DC là aggregate từ toàn bảng hiện có tại endpoint.

Đọc thêm: [audit BPI/DC trước đây](t1_bpi_dc_field_audit.md), [rà soát chung T1–T8](t1_t8_verified_data_sources.md). Kết luận ưu tiên trong tài liệu này cập nhật các ghi chú T1 cũ.
