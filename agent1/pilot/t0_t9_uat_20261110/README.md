# Bộ test tay T0/T9 — 10/11/2026

Bắt đầu bằng bộ nhỏ `01_core`, sau đó mới thử dữ liệu lớn. Toàn bộ dữ liệu trong thư mục này là **mô phỏng**, có đáp án kiểm tra, không phải hóa đơn/sao kê thật. CSV dùng UTF-8 BOM, ngày `yyyy-mm-dd`, tiền VND nguyên không dấu phân nhóm. Hóa đơn có đủ MST mô phỏng, ký hiệu/số, version và các cột tiền thỏa `tiền trước thuế + VAT = tổng`; thuế 0 ở ca cơ bản chỉ là giả định test. Giữ nguyên số 0 đầu của tài khoản; nên nạp tệp gốc trực tiếp, tránh mở rồi lưu lại bằng Excel.

## Mở môi trường test riêng

Từ thư mục gốc repository, chạy:

```powershell
.\agent1\pilot\t0_t9_uat_20261110\Start-Uat.ps1 -Suite core
```

Mở `http://127.0.0.1:8021/workspace#data`. Nhập khóa từ đường dẫn script in ra. Script dùng Python đã có trong repo, tạo kho và khóa riêng cho UAT, phục hồi biến môi trường khi thoát. Nhấn Ctrl+C để dừng. Muốn chạy lại từ đầu, đổi `-RunId run2`; dữ liệu lần trước vẫn được giữ. Không cần huấn luyện để test T0/T9.

Nếu test cùng Portal, tạo doanh nghiệp **test mới** trong **Hồ sơ doanh nghiệp**, chọn ngày **ISO / yyyy-mm-dd**, tiền **plain**. Trong khung Agent 1, mục **Dữ liệu** được ẩn vì Portal quản lý nạp gói chung. Bấm **Mở tab riêng** ở đầu khung Agent 1, rồi vào **Dữ liệu** của tab mới để nạp trực tiếp các CSV của bộ core. Để kiểm tra đường nhập sao kê chung của Portal, dùng riêng mục P01 bên dưới; luồng đó yêu cầu cả Agent 1 và Agent 3 sẵn sàng. Không nạp cùng một sao kê qua hai đường trong một doanh nghiệp test.

## Nạp và kiểm T0

Trong `01_core`, nạp lần lượt và xác nhận từng tệp:

1. `01_invoices.csv`: chọn bảng **Hóa đơn**.
2. `02_bank.csv`: chọn **Sao kê ngân hàng**.
3. `03_payments.csv`: chọn **Tiền khách trả / thanh toán**.
4. `04_statements.csv`: chọn **Kỳ sao kê / số dư**.

Kiểm tra ghép cột trước khi ghi. Tên cột khớp schema nên hệ thống tự ghép được. Hóa đơn core có đủ trường kế toán mô phỏng; kiểm thêm thay thế, điều chỉnh và hủy bằng bộ `03_lifecycle`.

| Mốc sau khi nạp đủ 4 tệp | Đáp án |
|---|---:|
| Hóa đơn / dòng bank / payment / kỳ sao kê | 13 / 14 / 1 / 1 |
| Tổng giá trị hóa đơn | 112.000.000 |
| Đã thu có liên kết hóa đơn trước T9 | 2.000.000 |
| Dư nợ trước T9 | 110.000.000 |
| Tổng tiền vào ngân hàng | 97.990.000 |
| Tiền ra ngân hàng | 2.000.000 |
| Số dư đầu kỳ | 100.000.000 |
| Số dư cuối kỳ | 195.990.000 |

Tiền vào ngân hàng khác với tiền đã phân bổ công nợ. Ban đầu API trả **11 khoản / 83.990.000** trong hàng chờ AR. Khoản vay `B_LOAN` 9 triệu vẫn nằm trong tổng tiền vào ngân hàng và trong ca đề xuất bị loại `non_ar_bank_movement`, nhưng không nằm trong KPI chờ ghép. Dòng bán thu ngay 3 triệu và dòng tiền ra không cần ghép công nợ.

**Chạy 14 ca âm ngay sau bước nạp ban đầu, trước khi duyệt T9.** Mỗi lần chọn một tệp trong `negative/`, chọn loại bảng ở cuối tên tệp, rồi xem trước. Mọi tệp phải có lỗi, không được ghi; số bản ghi và số dư phải giữ nguyên.

| Tệp | Điều phải bị chặn |
|---|---|
| N01 | Trùng mã trong cùng tệp |
| N02 | Thiếu customer_id |
| N03 | Ngày 30/02 |
| N04 | VND có phần lẻ |
| N05 | Ngoại tệ USD trong luồng chỉ VND |
| N06 | Payment tham chiếu hóa đơn chưa có |
| N07 | Payment ghép chéo khách hàng |
| N08 | Phân bổ vượt tiền nhận / dư nợ |
| N09 | Chiều `credit` không thuộc in/out, thu/chi |
| N10 | Lệch số dư sao kê 1 VND |
| N11 | Thiếu tài khoản |
| N12 | Bán thu ngay bị gán vào công nợ |
| N13 | MST không hợp lệ trong hóa đơn đủ trường kế toán |
| N14 | Tổng tiền khác trước thuế + VAT |

Thử nạp lại nguyên tệp hóa đơn hợp lệ: không được nhân đôi 13 hóa đơn. Thử xem trước hai tệp hợp lệ, ghi tệp thứ nhất rồi ghi bản xem trước cũ của tệp thứ hai: phải yêu cầu xem trước lại nếu dataset đã thay đổi.

## Kiểm T9 trên UI

Nhập **Người xử lý** là tên test, bấm **Tìm đề xuất đối soát**. Trước khi bấm duyệt, công nợ phải giữ nguyên. `auto` trong kết quả API nghĩa là có đề xuất xác định được; vẫn phải có người duyệt.

| Giao dịch | Đề xuất ban đầu / kết quả khi duyệt |
|---|---|
| B_EXACT | I_EXACT: 10 triệu; dư nợ hóa đơn về 0 |
| B_PART | I_PART: 8 triệu; còn 12 triệu |
| B_GROUP | I_GROUP1: 3 triệu + I_GROUP2: 7 triệu; cả hai về 0 |
| B_MULTI1, B_MULTI2 | I_MULTI: lần lượt 5 và 7 triệu; sau cả hai về 0 |
| B_EXISTING | Chỉ ghép thêm 8 triệu; 2 triệu P_EXISTING vẫn giữ, không thu trùng |
| B_FEE | Chỉ ghi 9.990.000; I_FEE còn 10.000. Không tự gọi phần thiếu là phí hoặc tự xóa nợ |
| B_OVER | Ghép tối đa 10 triệu; giữ 1 triệu chưa phân bổ |
| B_AMB | Hai hóa đơn cùng khách, cùng 6 triệu; phải chờ kiểm tra, không ép FIFO |
| B_UNKNOWN | Thiếu khách/người chuyển/tham chiếu: chờ kiểm tra |
| B_EARLY | Tiền về trước ngày lập hóa đơn: không đề xuất phân bổ |
| B_LOAN | financing: không được đề xuất trừ I_LOAN và không xuất hiện trong hàng chờ AR |
| B_CASH | cash_sale: không trừ công nợ |
| B_OUT | Tiền ra: không đưa vào phân bổ AR |

Sau **mỗi lần duyệt một giao dịch**, chạy **Tìm đề xuất đối soát** lại trước khi duyệt giao dịch tiếp theo. Thao tác này có chủ đích: quyết định mới làm bản đề xuất cũ hết hiệu lực.

Các ca thao tác cần làm thêm:

- T01: Để trống tên người xử lý, thử duyệt. UI phải chặn.
- T02: Duyệt B_EXACT. Tải lại trang: chỉ có một phân bổ 10 triệu, có đúng tên người xử lý trong lịch sử.
- T03: Trên tab thứ hai đang giữ đề xuất cũ, thử duyệt B_PART. Phải báo đề xuất đã cũ; không ghi thêm payment.
- T04: Từ chối B_UNKNOWN với lý do `TEST: chưa có xác nhận người chuyển`. Công nợ/tiền bank không đổi, lịch sử có người xử lý và lý do. Chạy lại đề xuất: không tự duyệt khoản đã từ chối.
- T05: Với B_AMB, mở ứng viên, chọn I_AMB2, phân bổ thủ công 6 triệu với ghi chú `TEST: bảng kê giả lập xác nhận I_AMB2`. I_AMB2 về 0, I_AMB1 vẫn 6 triệu. Thử để trống bằng chứng trước: UI và API đều phải chặn; lịch sử không được tự điền tên/bằng chứng.
- T06: Thử phân bổ B_AMB sang I_PART hoặc vượt số tiền. Hệ thống phải chặn, giữ số dư.
- T07: Mở lịch sử B_EXACT → đảo quyết định, nhập lý do. I_EXACT mở lại 10 triệu, B_EXACT chờ lại 10 triệu, giao dịch bank vẫn là 10 triệu; quyết định cũ còn trong lịch sử.
- T08: Duyệt lại B_EXACT bằng đề xuất mới. Mở **Sửa dữ liệu nguồn / bản ghi nhập nhầm**: tải bank B_EXACT và statements S_OCT vào cùng bản sửa. Đổi amount bank thành `11000000`, closing_balance kỳ thành `196990000`, nhập người xử lý và bằng chứng test. Xem trước phải nêu một quyết định bị ảnh hưởng. Xác nhận: đảo quyết định đó, bank chỉ tính bản mới một lần, tổng tiền vào `98990000`, số dư cuối kỳ `196990000`. Tìm đề xuất mới trước khi phân bổ lại.
- T09: Thử chỉ sửa bank thêm 1 triệu, giữ nguyên kỳ sao kê. Xem trước phải bị chặn do lệch số dư. Thử đổi giá trị sau khi đã xem trước: nút xác nhận phải yêu cầu xem trước lại.
- T10: Thử thiếu lý do khi từ chối/đảo/sửa nguồn. UI phải chặn.

## Các bộ độc lập

Dừng server rồi chạy lại launcher với `-Suite large`, `lifecycle` hoặc `pagination`. Mỗi suite dùng kho riêng. Nếu cần test trong Portal, dùng doanh nghiệp test mới cho mỗi bộ.

| Bộ | Cách dùng và đáp án |
|---|---|
| `02_large_vnd` | Nạp hóa đơn rồi bank trực tiếp vào Agent 1. Hóa đơn **9007199254741010**, bank **9007199254741009**. Đối soát và duyệt: còn đúng **1 VND**. Không dùng đường sao kê chung Portal cho ca này: đường đó có giới hạn 2^53−1. |
| `03_lifecycle` | Nạp lần lượt 01 → 05; tệp 03/04 vẫn chọn bảng hóa đơn, 05 chọn sự kiện hủy hóa đơn. Sau 01/02 còn 6 triệu; sau thay thế vẫn 6 triệu trên L_REPLACEMENT, không cộng thêm L_ORIGINAL; sau điều chỉnh còn 500.000; sau hủy không còn hóa đơn này trong hàng chờ T9. Hủy/điều chỉnh không tạo tiền bank. |
| XML tùy chọn | Dùng một kho lifecycle mới: nạp `optional_original.xml` vào Agent 1/Hóa đơn. Mapping phải khóa, tổng 11 triệu. XML này mô phỏng cấu trúc, không chứng minh chữ ký hay tính xác thực hóa đơn thật. Nếu nạp CSV cùng chứng từ sau đó, phải hợp nhất nguồn thay vì tạo hai khoản nợ. |
| `04_pagination` | Nạp 105 hóa đơn rồi 105 bank. Bảng khoản chờ ban đầu hiện 100/105. Tìm đề xuất, tìm PAGE_B105 trong phần đề xuất, chọn/duyệt khoản này. Phải xử lý được giao dịch thứ 105; không ép người dùng chỉ làm 100 dòng đầu. |

Với lifecycle, kiểm lịch sử tại các cutoff bằng luồng dự báo có sẵn hoặc API quan sát trong bộ xác minh: 19/10 là L_ORIGINAL còn 6 triệu; 24/10 là L_REPLACEMENT còn 6 triệu; 25/10 còn 500.000; 31/10 vẫn 500.000 vì chưa biết sự kiện hủy; từ 01/11 mới không còn. UI T9 dùng ngày hiện tại, không có bộ chọn snapshot lịch sử.

**P01 — sao kê chung qua Portal:** tạo doanh nghiệp test mới, ISO/plain. Nạp hóa đơn core trực tiếp vào Agent 1, rồi nạp `05_portal_shared/bank_statement.csv` qua ô nạp chung của Portal, kiểm tra Agent 1/Agent 3 và ghi theo quy trình. Ba khoản có description và tên đối tác ở nguồn. Bản chiếu sang Agent 1 phải giữ `memo`/`counterparty`, rồi ghép B_EXACT 10 triệu, B_PART 8 triệu, B_GROUP 3 + 7 triệu đúng bảng đáp án. Sau khi nạp, xem lại từng dòng sao kê và phần đề xuất trên UI; bài kiểm API đã chạy, thao tác trình duyệt vẫn cần thực hiện.

## Ghi kết quả và chạy lại kiểm chứng

Dùng [TEST_LOG.md](TEST_LOG.md) để ghi Pass/Fail, ảnh trước/sau, mã giao dịch và lỗi. Dừng ca ngay nếu thấy thu trùng, trừ công nợ sai khách, làm mất lịch sử hoặc sửa nguồn không đảo phân bổ liên quan.

Từ root repository, chạy xác minh bằng Python có sẵn:

```powershell
$env:PYTHONPATH='agent1;portal'
.\.venv\Scripts\python.exe -X utf8 -m pytest agent1/tests/adaptive/test_t0_t9_uat_pack.py -q
```

Lệnh đọc chính các CSV/XML đã giao và đáp án trong `expected_proposals.json`, tạo kho tạm để kiểm API; không nối tới doanh nghiệp đang chạy. Danh sách hash trong `manifest.json` giúp nhận ra tệp đã bị sửa. Ảnh chụp và kết quả chạy UI trong `agent1/outputs/ui_checks/` chỉ lưu ở máy kiểm thử, không đưa vào Git.

## Chuẩn kiểm tra của dữ liệu mẫu

Bộ mẫu dùng hợp đồng dữ liệu trong [adaptive/data.py](../../agent1/adaptive/data.py), bộ kiểm tra chứng từ [ingest/invoices.py](../../agent1_service/ingest/invoices.py) và các ràng buộc phân bổ T9. Kiểm chứng gồm schema, định danh duy nhất, ngày nghiệp vụ/ngày ghi nhận, VND nguyên, mã số thuế hợp lệ theo bộ kiểm tra, tổng trước thuế + VAT, bảo toàn tiền ngân hàng và dư nợ, cân đối kỳ sao kê, lịch sử thay thế/điều chỉnh/hủy.

Đây là chuẩn chấp nhận của sản phẩm để kiểm thử chức năng. Bộ mẫu không chứng minh chữ ký hóa đơn, tính xác thực doanh nghiệp hoặc độ chính xác dự báo trên dữ liệu thật; không dùng làm bộ benchmark doanh nghiệp độc lập.
