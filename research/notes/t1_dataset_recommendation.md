# T1 — Nghiên cứu dataset và phương án đề xuất

Nguồn được rà soát ngày **18/10/2026**; đề xuất dưới đây đã đối chiếu với [audit toàn bộ hai nguồn Séc](t1_czech_full_dataset_audit.md), nơi duy trì quy mô, chất lượng và các cohort ứng viên. Đây là **đề xuất lựa chọn dữ liệu và thiết kế benchmark**, chưa phải kết quả train.

## 1. Quyết định đề xuất

**Ưu tiên hai nguồn hóa đơn Séc đã tải và audit cho benchmark công khai, đánh giá riêng theo nguồn và cohort. Bước tiếp theo là chốt nhãn, xử lý trùng và dựng adapter. Không chọn BPI làm dataset chính của T1; đồng thời tìm dữ liệu AR của đối tác Việt Nam để kiểm định đúng nhiệm vụ.**

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

**Due date không bắt buộc về mặt toán học đối với survival**, nhưng pipeline notebook tham khảo cần nó. Code T1 mới có thể dùng nguồn thiếu due date nếu chỉ giữ feature/baseline phù hợp; không nên ép dữ liệu cho khớp schema lịch sử.

Để dự báo dòng tiền, cần thêm liên kết payment–invoice. Với hóa đơn trả nhiều lần, ngày tất toán cùng toàn bộ giá trị hóa đơn không tái hiện đúng lịch tiền về. MVP có thể tách nhóm trả một lần có bằng chứng rõ; nhóm còn lại cần mô hình dòng thu/phân bổ, không loại âm thầm.

## 3. Xếp hạng nguồn sau rà soát

Thứ tự dưới đây là **ưu tiên đầu tư công sức**, không phải thứ hạng chất lượng mô hình đã đo.

| Nguồn | Nguồn gốc / truy cập | Sát T1 đến đâu? | Đề xuất |
|---|---|---|---|
| **AR đối tác Việt Nam** | Dữ liệu riêng, cần đối tác cấp quyền; chưa có trong checkout | Gần nhất nếu đúng doanh nghiệp bán chịu và xuất đủ invoice/payment/open items | Nguồn đích cho kiểm định sản phẩm |
| **Bộ Tài chính Séc — hóa đơn đã trả** | Đã tải và audit toàn bộ CSV; có metadata điều kiện sử dụng | Có issue/due/payment và amount; B2G, một bên mua; thiếu bằng chứng danh mục chưa trả đầy đủ | Ưu tiên dựng benchmark sau khi chốt loại chứng từ và xử lý ID lặp/mâu thuẫn |
| **Ngành y tế Séc** | Đã tải và audit toàn bộ API; điều kiện tái sử dụng cụ thể chưa chốt | Nhiều bên mua, có schema phù hợp; chất lượng khác nhau rõ giữa các nhóm | Benchmark riêng theo buyer; tách issue-level và receipt-level, xử lý trùng nghiệp vụ và ý nghĩa thanh toán |
| **DC PASS** | API chính thức truy cập được; cần chốt điều khoản áp dụng cho bảng | Có ngày invoice/payment; thiếu due date được xác minh; grain và schema khác theo giai đoạn | Benchmark bổ trợ về thời gian chi trả, không nạp thẳng pipeline |
| **BPI 2019** | Log doanh nghiệp thật; file gốc truy cập được; CC BY 4.0 trên record phát hành | PO-item, nhiều invoice/case; không có invoice ID/due date trong mẫu đã đọc | Benchmark quy trình; không ưu tiên để dựng invoice-level T1 |
| **Barnet late payments** | Cổng chính quyền, nêu OGL v3; có file XLSX | Chọn các khoản trả trễ, không đại diện toàn bộ invoice | Chỉ phân tích nhóm trễ/đối chiếu, không train mô hình on-time vs late chung |
| **Stemly trong paper Saini et al.** | Dữ liệu nghiên cứu thật nhưng bị hạn chế truy cập | AR gần task hơn các log mua hàng | Hướng xin quyền học thuật; chưa phải dữ liệu tải tự do |
| **SAP/HighRadius/Kaggle hiện được nhắc trong dự án** | Có nhiều bản chia sẻ lại; chưa xác minh publisher gốc và quyền phân phối; file local đang vắng | Schema gần pipeline nhất; nguồn gốc và cách lấy mẫu chưa chắc chắn | Chỉ thực hành khi có quyền; chưa dùng làm bằng chứng dữ liệu thực uy tín |

## 4. Những gì đã kiểm tra trực tiếp

### 4.1. Hai nguồn Séc: đã có audit toàn bộ

Quy mô, gate, lỗi ngày/số tiền, trùng và coverage theo tổ chức được duy trì tại [báo cáo audit đầy đủ](t1_czech_full_dataset_audit.md). Nội dung nguồn, đường dẫn local và giới hạn sử dụng nằm tại [hướng dẫn dữ liệu T1](../../data/T1/README.md). Dùng kết quả toàn bộ snapshot để chọn cohort và chuẩn bị adapter.

**Thiết kế thí nghiệm:** Bộ Tài chính làm benchmark thời gian từ phát hành đến ngày chi trả được ghi nhận và độ trễ so với hạn trên cohort đã quan sát thanh toán. Ngành y tế đánh giá riêng theo buyer; benchmark từ ngày nhận hóa đơn phải tách khỏi benchmark từ ngày phát hành. Cả hai còn cần chốt nhãn và xử lý trùng trước khi train; chưa chứng minh có toàn bộ danh mục chưa trả hoặc ngày tiền khả dụng tại ngân hàng bên bán.

### 4.2. DC PASS: thống kê toàn bảng và profile mẫu

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

### 4.3. BPI: mẫu file gốc xác nhận khó khăn ở cấp invoice

[TU/e mô tả case là purchase document × item](https://research.tue.nl/en/datasets/bpi-challenge-2019/). Đã đọc tiền tố 2 MB của XES gốc, chứa **220 case hoàn chỉnh**, không đọc hết file khoảng 729 MB.

Mẫu có **813 event nhận hóa đơn, 562 event clear**; có case tới **125 event nhận hóa đơn**. Có cả `Vendor creates invoice`, vì vậy nguồn không chỉ có mốc nhận invoice. Tuy nhiên, các event trong mẫu chỉ có tên, timestamp, resource/user và giá trị net tích lũy; chưa có khóa invoice để ghép chắc chắn các event đó.

**Quyết định:** không lấy một case làm một invoice; không lấy lần create/receipt đầu và clear cuối để tạo nhãn T1. Có thể chọn nhóm case đơn giản cho benchmark quy trình với tiêu chí công bố rõ, nhưng không bảo đảm đó là invoice-level hay bank cash-in.

### 4.4. Các nguồn còn lại: vì sao chưa chọn?

- [Barnet](https://open.barnet.gov.uk/dataset/financial-invoices-late-payments-2g58n): có ngày, số tiền và thông tin trả trễ; chưa đọc các workbook trong lần này. Tập chọn theo outcome trễ không dùng để ước lượng tỷ lệ trễ chung.
- [Paper Saini et al. 2024](https://link.springer.com/article/10.1007/s44257-024-00013-2): dữ liệu phải có phép của Stemly; code bổ sung công khai không đồng nghĩa data mở. Paper cũng nêu các ứng dụng dùng invoice đã trả, không có censoring; không coi đó là kiểm chứng đầy đủ danh mục chưa trả.
- [Atomic Common-Day Invoice Clearing](https://data.mendeley.com/datasets/28rbmvwsm9/1): công bố invoice issue/due/amount và debtor/creditor, nhưng chưa xác nhận ngày thực trả. Kết quả clearing của thuật toán không phải nhãn cash payment thực tế. Chưa tải file; không chọn cho T1 timing.
- [Replication “Show Me the Receipts”](https://data.mendeley.com/datasets/b9y47f5skn/2): landing page công bố replication code, chưa xác nhận có microdata từng invoice đủ field. Không coi DOI là bằng chứng sẵn dữ liệu train.
- [Cook County CCP Invoice Register](https://catalog.data.gov/dataset/ccp-invoice-register): metadata chính thức có dữ liệu invoice/payment; endpoint schema và mẫu trả 403 từ môi trường kiểm tra. Chưa xác minh được field/giấy phép đủ để nâng ưu tiên.

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

## 7. Những điểm cần lưu ý nếu tái sử dụng pipeline tham khảo

Đối chiếu [survival_utils.py](../../reference_notebooks/survival_utils.py) và [notebook 01](../../reference_notebooks/01_data_preparation_eda.ipynb):

Bộ này chỉ dùng tham khảo; code T1 mới sẽ được xây riêng. Các mục dưới đây chỉ ra giả định của code lịch sử cần xem xét khi tái sử dụng, không phải yêu cầu phải nối nguồn mới vào pipeline cũ.

1. **Tách adapter theo nguồn**, giữ `source_dataset`, `source_record_id`, buyer/seller, currency và định nghĩa target. Không âm thầm ép PO item thành invoice hoặc supplier thành debtor.
2. **Đưa `observation_end` vào metadata.** `load_pools()` đang lấy `max(paid_date)`; đó không chứng minh dữ liệu đầy đủ đến ngày đó, nhất là với nhiều doanh nghiệp.
3. **Cấu hình cutoff/split theo dataset.** Hiện có ngày cố định năm 2020 và cửa sổ `pre/post shock`; không dùng nguyên cho dữ liệu Séc/DC. Censor nhãn đúng ngày đóng băng train và chặn event nằm ngoài observation end.
4. **Tách feature theo dữ liệu có thật.** Hàm hiện lọc thiếu due date và terms ≤ 0; terms bằng 0 có thể là điều khoản thật. Không loại nhóm đó hay điền terms chỉ để qua bộ lọc mà không có quyết định nghiệp vụ.
5. **Giữ amount gốc và remaining balance riêng**, phân biệt cash settlement với credit/write-off/cancel. Không áp FX USD/CAD cũ cho CZK hoặc VND.
6. **Lưu hai bảng kết quả riêng:** public observed-paid benchmark và partner open-portfolio validation. Không pool score của các nguồn rồi gọi là độ chính xác T1 cho SME Việt Nam.

Các thay đổi trên là đề xuất; **chưa sửa thuật toán hoặc chạy lại notebook** trong lần nghiên cứu này.

## 8. Thứ tự thực hiện cụ thể

1. **Chuẩn bị adapter Bộ Tài chính Séc từ kết quả audit:** chốt loại chứng từ, rà ngày bất thường và quy tắc chọn phiên bản cho ID lặp; giữ nhóm mâu thuẫn để kiểm tra riêng. Chưa coi các ID qua gate là tập train hoàn chỉnh.
2. **Chuẩn bị cohort ngành y tế Séc:** chốt điều kiện sử dụng, xử lý trùng nghiệp vụ và ý nghĩa ngày trả/paid amount; dùng coverage đã audit để chọn buyer/thời gian. Tách thí nghiệm từ ngày phát hành và từ ngày nhận.
3. **Lấy AR đối tác song song:** xuất thử một kỳ, đối chiếu vài invoice từ phát hành đến thanh toán và vài open items, rồi mở rộng lịch sử. Có thể bắt đầu thu snapshot từ bây giờ nếu dữ liệu cũ không có lịch sử sửa.
4. **Xây code T1 mới và chạy benchmark tối giản:** baseline → mô hình ứng viên → đánh giá theo thời gian, bias và calibration; dùng `reference_notebooks/` để tham khảo phương pháp. DC là kiểm tra bổ trợ; BPI chỉ đưa vào nếu có câu hỏi nghiên cứu quy trình riêng.

Nếu chưa lấy được AR đối tác, phạm vi nghiên cứu nên ghi: **“Dự báo thời điểm chi trả trên hóa đơn công khai B2G, kết hợp kiểm thử censoring có kiểm soát; khả năng áp dụng lên công nợ SME Việt Nam chưa được xác nhận.”**

## 9. Bằng chứng và giới hạn

- [Nhật ký truy cập, URL, response hash và thống kê API](../references/data-checks/t1/t1_dataset_deep_checks.json).
- [Profile mẫu lịch sử](../references/data-checks/t1/t1_dataset_sample_profiles.json); các phần BPI/DC hỗ trợ nhận xét ở mục 4, phần mẫu Séc đã được audit toàn bộ thay thế.
- [Script profile mẫu local](../../scripts/data_audit/audit_t1_source_samples.py), chỉ dùng Python standard library; không tự tải mạng. Mẫu BPI/DC còn được giữ tại `data/T1/raw/source_samples/`; script không tái tạo phần profile Séc lịch sử vì các mẫu Séc đã được bộ đầy đủ thay thế.
- Hai nguồn Séc đã tải và audit toàn bộ snapshot; BPI/DC mới có mẫu và các truy vấn tổng hợp đã nêu. Chưa tạo tập train, chưa chốt mọi giấy phép và chưa thử nghiệm khả năng chuyển miền. Tiền tố XES BPI không phải toàn bộ dataset; bảng count DC là aggregate toàn bảng tại thời điểm kiểm tra, không phải audit từng record.

Đọc thêm: [đối chiếu field BPI/DC](t1_bpi_dc_field_audit.md), [rà soát chung T1–T8](t1_t8_verified_data_sources.md).
