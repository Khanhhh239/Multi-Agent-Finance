# BPI 2019 và DC PASS: có đủ field cho T1 không?

Đối chiếu field ngày **18/10/2026** với metadata nguồn, schema DC, [notebook chuẩn hóa dữ liệu](../../reference_notebooks/01_data_preparation_eda.ipynb) và [survival_utils.py](../../reference_notebooks/survival_utils.py). Thống kê DC toàn bảng và profile mẫu BPI/DC nằm tại [đề xuất dataset T1](t1_dataset_recommendation.md); chưa audit toàn bộ bản ghi BPI/DC hoặc dựng bộ train từ hai nguồn này.

**Kết luận: cả hai chưa đủ để thay trực tiếp dữ liệu T1 hiện tại. DC có thể phục vụ một benchmark rút gọn về thời gian từ hóa đơn đến lần chi trả được ghi nhận; BPI phù hợp benchmark thời gian xử lý/clear theo quy trình, cần định nghĩa lại đơn vị dự báo.** Không có đủ bằng chứng để dùng chúng xác nhận đầy đủ T1 trên danh mục hóa đơn phải thu đang mở của SME Việt Nam.

## 1. Hai nguồn thực chất ghi nhận gì?

**BPI Challenge 2019** là log purchase-to-pay thật của một tập đoàn sơn/chất phủ hoạt động từ Hà Lan. Một case là `Purchasing Document + Item`, tức dòng hàng trong chứng từ mua. Một case có thể có nhiều lần nhận hàng và nhiều hóa đơn; nguồn nêu ví dụ một item tiền thuê gắn với 12 hóa đơn. Vì vậy, case ID không thể mặc định dùng làm invoice ID. [Mô tả của người công bố tại TU/e](https://research.tue.nl/en/datasets/bpi-challenge-2019/).

Các bước `Record Invoice Receipt` và `Clear Invoice` cho phép nghiên cứu thời gian giữa các sự kiện. Ngày nhận hóa đơn ở bên mua không mặc định là ngày bên bán phát hành; clear kế toán không mặc định là lúc tiền khả dụng trong tài khoản bên bán. Việc ghép một receipt với một clear trong case có nhiều hóa đơn cần quy tắc và kiểm chứng, không chỉ lấy event đầu và cuối. [Báo cáo phân tích dữ liệu BPI tại ICPM](https://icpmconference.org/2019/wp-content/uploads/sites/6/2019/07/BPI-Challenge-Student-Submission-1.pdf).

**DC PASS Payments** là dữ liệu chính quyền District of Columbia, Mỹ, chi trả cho nhà cung cấp. Đây là B2G, nhìn từ phía bên trả. [Schema API chính thức](https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Government_Operations/MapServer/17) có invoice, voucher, payment, supplier và agency. Thống kê aggregate và profile mẫu chưa xác nhận độ đầy đủ hay tính duy nhất của toàn bộ bảng.

## 2. T1 và pipeline notebook tham khảo yêu cầu gì?

Code T1 mới chưa được triển khai. Notebook 01 trong `reference_notebooks/` dùng schema chuẩn hóa sau; đây là đầu vào lịch sử để đối chiếu:

```text
invoice_id, customer_id, issue_date, due_date,
paid_date, amount, payment_terms, is_open
```

`paid_date` được phép thiếu với hóa đơn đang mở nếu có đủ thông tin kết thúc quan sát. T1 landmark dự báo thời gian còn lại từ cutoff T; một nhãn trên hóa đơn trả sau T là `paid_date - T`. Các cột aging, overdue, customer history và baseline được dựng từ dữ liệu gốc, không phải tất cả đều cần tồn tại sẵn trong nguồn.

Về toán học, dự báo thời gian đến sự kiện có thể bỏ due date. **Pipeline tham khảo sử dụng due date/payment terms**; nếu tái sử dụng nó cho nguồn thiếu các field này, phải thiết kế lại feature/baseline và phạm vi đánh giá. `load_pools()` trong `survival_utils.py` lọc bỏ hóa đơn thiếu `due_date` hoặc payment terms không hợp lệ. Bộ lọc này không phải yêu cầu mặc định cho code T1 mới.

## 3. Đối chiếu field và ý nghĩa

| Yêu cầu | BPI 2019 | DC PASS | Đánh giá |
|---|---|---|---|
| Định danh hóa đơn | Case là purchase document × item, có thể chứa nhiều invoice | `INVOICENUMBER`, kèm agency/supplier/voucher/PO | BPI chưa có mapping invoice 1–1 được xác minh. DC cần audit khóa ghép và grain; không mặc định một row = một invoice |
| Bên có nghĩa vụ trả | Có `Company`, `Vendor`; cần xác định đúng vai trò | Có `AGENCYCODE`, `AGENCY_NAME`, `SUPPLIERNAME` | Vendor/supplier là bên nhận tiền. Không đổi thẳng thành AR `customer_id` |
| Ngày phát hành | Event nhận hóa đơn chỉ là mốc thay thế | Có `INVOICEDATE` | DC có field trực tiếp theo tên/alias; BPI cần gọi đúng mốc nhận hóa đơn nếu dùng |
| Hạn trả hợp đồng | Chưa xác minh được field đáp ứng | Có `ESTPAYMENTDATE`, chưa có field hạn hợp đồng được xác minh | Không lấy ngày thanh toán dự kiến thay cho contractual due date mà không đổi định nghĩa |
| Payment terms | Chưa xác minh được | Chưa thấy trong schema đã kiểm tra | Không tự gán net-30 rồi coi là dữ liệu thật |
| Ngày thanh toán | Event `Clear Invoice` là mốc clear | Có `PAYMENTDATE` | Có thể làm event target theo định nghĩa nguồn; chưa chứng minh ngày ngân hàng bên bán ghi có/khả dụng |
| Giá trị hóa đơn biết tại cutoff | Có giá trị gắn với các sự kiện/item; cần xử lý nhiều invoice và thay đổi | Có `VOUCHERAMOUNT`, `PAYMENTAMOUNT` | Không mặc định giá trị PO/voucher bằng tổng invoice; payment amount có thể chỉ là số thực chi của một lần |
| Danh mục invoice mở và kết thúc quan sát | Không thấy clear chưa chứng minh invoice còn mở: có thể hủy, consignment, thiếu lịch sử hoặc nhiều invoice | Bảng payments chưa chứng minh bao gồm toàn bộ invoice chưa thanh toán | Chưa đủ để dựng risk set survival đại diện danh mục thực tế |
| Lịch sử thông tin khả dụng | Timestamp sự kiện chưa tự cung cấp đầy đủ lịch sử biết/sửa | Có created/updated timestamps của record | Chưa đủ chứng minh trạng thái mọi field đã được biết tại cutoff; cần audit riêng |

Đây là đánh giá theo metadata/schema đã đối chiếu, không phải khẳng định đã kiểm tra mọi file liên quan của nhà cung cấp.

## 4. Hai lỗi ánh xạ dễ làm sai T1

### Supplier không phải khách hàng có nghĩa vụ trả

Trong AR của một SME bán hàng, `customer_id` đại diện bên mua phải thanh toán. Trong DC, `SUPPLIERNAME` là bên cung cấp đang nhận tiền; agency là thông tin về phía mua/chi trả. BPI cũng phân biệt company mua và vendor bán.

Nếu quyết định dự báo hành vi chi trả theo supplier từ góc nhìn AP, đó là một benchmark hợp lệ với phạm vi đã đổi. Nếu giữ góc nhìn AR, phải xác định doanh nghiệp bán, bên mua có nghĩa vụ trả và quan hệ giữa họ. Không tạo “customer history” bằng cách đổi tên cột sai vai trò.

### Số tiền thực trả có thể chỉ xuất hiện sau cutoff

`PAYMENTAMOUNT` là thông tin về payment. Không được mặc định dùng số tiền thực trả trong tương lai làm feature “giá trị hóa đơn hiện tại”. Chọn amount đã biết tại T và xác minh ý nghĩa invoice/voucher; giữ actual payment amount cho outcome khi phù hợp.

Tương tự, ngày dự kiến thanh toán được cập nhật sau đó không thể đưa ngược vào feature lịch sử. Ghép với bản mới nhất của record không tự tái lập thông tin đã biết tại ngày dự báo.

## 5. Có thể thực hiện thí nghiệm nào?

**DC — benchmark rút gọn, có điều kiện theo các khoản chi quan sát được:**

```text
Mục tiêu: số ngày từ INVOICEDATE đến PAYMENTDATE được ghi nhận.
Đơn vị: invoice/payment sau khi xác minh grain và xử lý nhiều lần chi trả.
Đối chứng: trung vị lịch sử và mô hình dùng feature biết được tại mốc dự báo.
Đánh giá: chia thời gian; MAE/pinball/coverage trên cùng tập hợp lệ.
```

Một hóa đơn có payment trong tương lai có thể được xem là đang mở trước payment đó trong tập đã chọn. Tuy nhiên, tập payments có thể loại mất các hóa đơn chưa từng trả/chưa trả tại ngày trích xuất. Tái dựng trạng thái trong tập các khoản cuối cùng đã trả không khắc phục được selection bias/right truncation của danh mục ban đầu.

**BPI — benchmark thời gian quy trình:** chọn loại case thích hợp và định nghĩa rõ sự kiện đích tại cấp case, hoặc xây mapping invoice–event trước khi chuyển sang T1 invoice-level. Đo thời gian tới một clear/completion được định nghĩa rõ; báo kết quả như process/payment-clearing benchmark. Không mặc định lấy mọi case làm một hóa đơn.

**Để chạy T1 đầy đủ như thiết kế hiện tại:** cần nguồn invoice có định danh ổn định, bên trả, ngày phát hành/hạn hợp đồng, số tiền còn phải thu tại cutoff, các lần thu/phân bổ, các invoice đang mở, mốc kết thúc quan sát và lịch sử khả dụng. Khi đó mới đánh giá được cả aging, censored survival, các khoảng dự báo và khả năng áp dụng lên danh mục đang mở.

## 6. Quyết định đề xuất

Nguồn benchmark T1 được ưu tiên hiện tại là [hai bộ hóa đơn Séc đã audit](t1_czech_full_dataset_audit.md). BPI/DC chỉ là các hướng bổ trợ:

- Dùng **DC** làm ứng viên benchmark rút gọn sau audit grain, chất lượng và quyền sử dụng; không nạp thẳng vào pipeline hiện tại.
- Dùng **BPI** cho nghiên cứu process/clearing và xử lý nhiều invoice trong một case; chỉ chuyển thành invoice-level khi chứng minh được mapping.
- Giữ **T1 trên dữ liệu AR của đối tác** làm kiểm định đúng task. Kết quả tốt trên BPI/DC là bằng chứng phương pháp ở miền khác.

Chưa sửa thuật toán hoặc tạo adapter trong lần đối chiếu này. Ngoài mapping dữ liệu, cấu hình cutoff/split và các giả định của pipeline hiện tại cũng cần thay theo bộ dữ liệu mới.
