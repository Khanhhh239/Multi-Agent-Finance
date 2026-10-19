# T1 — Kiểm tra toàn bộ hai dataset hóa đơn Séc

Snapshot tải ngày **18/10/2026**, hoàn tất tải và kiểm tra toàn bộ file/trang API. **Các con số dưới đây thay thế kết luận về quy mô từ mẫu 2 MB và 5 trang API trước đây. Chưa train mô hình.**

## 1. Kết luận

**Cả hai nguồn đều có quy mô đáng dùng để bắt đầu benchmark T1.** Bộ Tài chính có 120.753 ID hóa đơn khác nhau trong các dòng tổng; ngành y tế có 289.698 ID record khác nhau. Vấn đề chính là chất lượng nhãn, trùng hóa đơn và phạm vi đánh giá, không phải thiếu vài nghìn dòng.

- **Bộ Tài chính:** có **114.326 ID khác nhau** vượt bộ lọc sơ bộ và không nằm trong nhóm cùng ID nhưng mâu thuẫn trường tài chính đã kiểm tra. Có thể làm benchmark thời gian từ phát hành đến ngày trả được ghi nhận, sau khi chốt loại chứng từ và cách xử lý bản ghi lặp.
- **Ngành y tế:** có **64.775 dòng** thuộc các tên loại hóa đơn thông thường, vượt bộ lọc sơ bộ có tham chiếu invoice. Đây là ứng viên hữu ích hơn mẫu 925 dòng trước đây; cần tiếp tục kiểm tra trùng nghiệp vụ và ý nghĩa thanh toán.
- Có **197.569 dòng y tế** phù hợp bộ lọc theo **ngày nhận hóa đơn**. Đây là một thí nghiệm riêng, không thay ngày nhận vào ngày phát hành rồi giữ nguyên định nghĩa task.

## 2. Đã tải gì và lưu ở đâu?

| Nguồn | Dung lượng dữ liệu gốc | Quy mô |
|---|---:|---|
| Bộ Tài chính | 398.969.432 byte, khoảng 399 MB | 1.271.087 dòng CSV: 194.372 dòng tổng và 1.076.715 dòng ngân sách |
| Ngành y tế | 502.048.560 byte, khoảng 502 MB | Đủ 290 trang, tổng 289.698 record invoice, gồm cả các item lồng bên trong |

Đường dẫn từ gốc repo:

```text
data/T1/raw/czech/2026-10-18/
  finance/faktury.csv                 # File CSV gốc đầy đủ
  health/pages/page_0001.json ...     # 290 trang JSON gốc đầy đủ
  health/imports_before.json         # Metadata các đợt nhập
  health/organizations_before.json   # Metadata đơn vị công bố
  download_manifest.json             # URL, số trang, hash và trạng thái tải

data/T1/interim/czech/2026-10-18/
  finance_invoice_audit.csv           # 194.372 dòng tổng, giữ cờ chất lượng/trùng
  health_invoice_audit.csv            # 289.698 record dạng phẳng, giữ cờ chất lượng/trùng
  finance_monthly_coverage.csv
  health_monthly_coverage.csv
  health_by_organization.csv
```

Các file gốc và bảng audit nằm trong đường dẫn đã ignore. Bảng audit giữ nguyên dòng ứng viên, có ngày nguồn và ngày parse riêng, **không phải bộ train đã được chứng nhận**. Không tự điền ngày thiếu hay bỏ bản ghi trùng.

Bản gốc trong `raw` cần giữ để đối chiếu và tạo lại audit vì bảng `interim` đã chọn cột, chỉ lấy dòng tổng của nguồn tài chính và làm phẳng JSON y tế. Tám file mẫu Séc/metadata trong `data/T1/raw/source_samples/` đã được xóa sau khi xác nhận nội dung trùng với bộ đầy đủ; đã thu hồi 10.034.976 byte, không xóa dữ liệu nguồn duy nhất.

Ngày **19/10/2026**, dữ liệu được gom vào `data/T1/`. Đã gộp thông tin 296 file metadata HTTP vào `download_manifest.json` và xóa các sidecar đó cùng 3 payload kiểm tra trùng nội dung (tổng 299 file, 1.867.988 byte). Manifest giữ URL, thời điểm tải, headers, SHA256 và kết quả so sánh; dữ liệu hóa đơn và bảng audit không đổi. Xem [hướng dẫn dữ liệu T1](../../data/T1/README.md) về mục đích từng nguồn và khả năng dùng lại cho task khác.

Đã xác minh SHA256 file tài chính và từng trang y tế. Số trang và số record khớp tổng API; ID record y tế không trùng. Metadata imports, organizations và trang đầu không đổi giữa đầu/cuối phiên tải. Đây là kiểm tra tính nhất quán trong phiên tải, không phải bảo đảm mọi trường nghiệp vụ của nguồn chính xác.

## 3. Quy tắc kiểm tra dùng trong báo cáo

`gate_issue_due_paid` yêu cầu:

1. Có ngày phát hành, due date và ngày trả parse được.
2. Ngày phát hành/ngày trả trong khoảng 1990 đến ngày snapshot; due date từ 1990 đến snapshot + 5 năm. Đây là ngưỡng chẩn đoán công khai, không phải điều khoản hợp đồng.
3. Due date và ngày trả không trước ngày phát hành.
4. Amount dương, mã tiền tệ dạng ba chữ cái, có buyer/seller và ID record.

`gate_with_invoice_reference` yêu cầu thêm tham chiếu invoice không trống/placeholder. Các gate chưa xác nhận thời điểm thông tin khả dụng, trả đủ, bank cash-in, loại chứng từ đúng task hay danh mục open items đầy đủ. Mã tiền tệ đúng dạng cũng chưa chứng minh mọi mã đều hợp lệ theo dictionary.

## 4. Bộ Tài chính: quy mô thật và vấn đề trùng

| Kiểm tra | Kết quả |
|---|---:|
| Dòng tổng hóa đơn | 194.372 |
| ID hóa đơn khác nhau | **120.753** |
| ID xuất hiện hai lần | 73.619 |
| ID có mâu thuẫn ít nhất một trường tài chính được chọn | **2.220** |
| Dòng vượt bộ lọc issue/due/paid | 187.877 |
| ID khác nhau vượt bộ lọc, không có mâu thuẫn trường đã chọn | **114.326** |
| Supplier ID khác nhau, không tính trống | 4.238 |

**Không lấy 194.372 làm số hóa đơn độc lập.** Trước tiên chỉ dùng dòng `souhrnný`; sau đó mới xử lý các ID tổng bị lặp. Trùng dòng ngân sách và trùng dòng tổng là hai vấn đề khác nhau.

2.220 ID mâu thuẫn được xác định theo buyer/seller, tham chiếu, ngày, amount, tiền tệ, paid amount và loại chứng từ trong bảng audit; chưa xác minh nguyên nhân là sửa dữ liệu, xung đột khóa hay lỗi xuất. Không lấy tùy ý dòng đầu/cuối làm ground truth. Việc không mâu thuẫn ở các trường này cũng không chứng minh toàn bộ metadata khác giống nhau.

Một số lỗi cần xử lý: thiếu ngày phát hành **866 dòng**, thiếu seller ID **5.097 dòng**, due trước issue **476 dòng**, paid trước issue **197 dòng**, mã tiền tệ thiếu/sai dạng **46 dòng**. Có giá trị bất thường trong cột loại chứng từ; các dòng đó vẫn được giữ để tra lại nguồn.

Ngày trả quan sát từ **08/01/2007 đến 04/05/2026**. Một số ngày phát hành rất cũ hoặc thời gian sống cực dài cần đối chiếu, không tự coi toàn bộ khoảng đó là lịch sử liên tục và không cắt đuôi theo outcome để làm đẹp điểm.

**Lưu ý amount:** audit lấy `částka_v_měně` cùng `měna` làm số tiền theo nguyên tệ. `částka` là giá trị nội tệ theo hướng dẫn nguồn. `částka_k_úhradě_v_měně` không được gán thành actual cash paid. Vì vậy, gate khớp paid amount ở nguồn tài chính bằng 0 do **không có actual-paid-amount đã xác minh**, không phải toàn bộ hóa đơn không dùng được.

Nguồn có một buyer là bộ, nhiều supplier bán hàng cho bộ. Khi dựng history, dùng đúng vai trò buyer/seller và cặp quan hệ. Phạm vi nguồn là hóa đơn được công bố đã trả; chưa có bằng chứng về toàn bộ danh mục chưa trả.

## 5. Ngành y tế: số dòng dùng được lớn hơn nhiều mẫu ban đầu

| Mức kiểm tra | Số dòng |
|---|---:|
| Toàn bộ record; ID record duy nhất | **289.698** |
| Qua gate issue/due/paid | 66.163 |
| Qua gate trên và có tham chiếu invoice | 65.826 |
| Qua gate tham chiếu, thuộc tên loại hóa đơn thông thường | **64.775** |
| Qua gate tham chiếu, paid amount cùng currency và khớp gross trong 0,01 | 32.136 |
| Qua cả gate khớp amount và tên loại hóa đơn thông thường | 32.018 |
| Qua gate từ ngày nhận đến ngày trả, có due date | **197.569** |

“Tên loại hóa đơn thông thường” trong phép đếm này là `Běžná faktura`, `Faktura přijatá`, `Faktury přijaté`, `Přijatá faktura`. Đây là lựa chọn thận trọng theo tên nguồn; vẫn cần xác nhận theo tổ chức, vì nhà công bố nêu mã loại chứng từ không thống nhất. Các loại credit note, advance hoặc settlement khác được báo riêng; amount dương chưa đủ loại hết credit note.

**Không lấy 32.136 làm số dòng duy nhất dùng được.** Gate so sánh amount chỉ áp dụng khi cả tiền tệ thanh toán và invoice có đủ, trùng nhau. Một số tổ chức thiếu tiền tệ của paid amount nên không qua gate này dù còn có ngày trả và amount invoice. Ngược lại, hai amount bằng nhau chưa chứng minh có duy nhất một lần thu tiền hay ngày ngân hàng ghi có.

Các nhóm có issue/due/paid vượt gate:

| Buyer ID trong nguồn | Dòng qua gate issue/due/paid | Số tháng phát hành có dòng qua gate | Khoảng tháng đầu–cuối |
|---|---:|---:|---|
| 2 | 27.345 | 100 | 08/2013–08/2026 |
| 2936 | 19.519 | 81 | 09/2018–05/2025 |
| 1752 | 5.490 | 88 | 05/2019–08/2026 |
| 2554 | 5.481 | 25 | 01/2018–07/2020 |
| 2484 | 4.420 | 46 | 10/2018–03/2023 |
| 1816 | 3.895 | 34 | 02/2017–07/2021 |
| 6813 | 13 | 8 | 04/2018–10/2024 |

Số tháng có dữ liệu không đồng nghĩa mọi tháng trong khoảng đều đầy đủ. Toàn nguồn có 27 buyer và 11.977 supplier; tập issue-level qua gate chỉ đại diện 7 buyer.

Các vấn đề lớn:

- **212.473 record thiếu ngày phát hành**, 89.556 thiếu due date, 77.861 thiếu ngày trả. Không tự điền ngày nhận thay issue.
- **77.856 record của một buyer** đồng thời thiếu paid amount và nhiều trường khác; không có cơ sở xem toàn bộ là unpaid/censored thật.
- **319 record có ngày trả năm 1970**; có ngày phát hành/hạn trả ghi năm bất thường. Cần tra lại import, không xem là ngày thanh toán thật.
- 7.951 nhóm buyer–seller–tham chiếu có nhiều record. Khi yêu cầu thêm các trường ngày, amount, tiền tệ và loại chứng từ giống nhau, vẫn có **4.852 nhóm lặp**, tương ứng **5.072 dòng dư** trên toàn nguồn có tham chiếu hợp lệ. Đây là ứng viên trùng nghiệp vụ, chưa được tự động khử trùng.
- Có 4.156 record với paid amount dương thấp hơn gross dương khi cùng tiền tệ; còn có các trường hợp paid vượt gross. Cần tách partial payment, điều chỉnh và lỗi dữ liệu trước khi suy ra full-settlement target.
- Có 1.039 record không tìm thấy import tương ứng trong metadata tải về; 210.798 record có ngày nhập công khai sau ngày trả. Backtest từ issue là mô phỏng góc nhìn ERP với giả định đã nêu, không phải bằng chứng API công khai cung cấp thông tin trước payment.

## 6. Đề xuất dùng cho T1

**Nên dùng cả hai làm benchmark riêng.** Bộ Tài chính cung cấp cohort lớn với due/issue/paid; ngành y tế cung cấp nhiều bên mua và lịch sử dài ở một số nhóm. Không gộp thành một doanh nghiệp hoặc mặc định mô hình chuyển được sang SME Việt Nam.

Thứ tự chuẩn bị thí nghiệm:

1. **Bộ Tài chính:** dùng 114.326 ID qua gate và không mâu thuẫn trường đã kiểm tra làm phạm vi ứng viên; chốt loại chứng từ, rà các ngày bất thường và quy tắc chọn một phiên bản/ID. Giữ nhóm mâu thuẫn trong quarantine.
2. **Y tế issue-level:** bắt đầu từ nhóm 64.775 dòng có tên loại phù hợp; audit các nhóm trùng, lịch sử import và amount. Ưu tiên các buyer có lịch sử dài như 2/2936/1752; tách kết quả từng buyer và đo coverage theo tháng.
3. **Y tế receipt-level:** làm benchmark riêng trên nhóm từ ngày nhận, mở rộng đến các buyer thiếu issue date. Gọi đúng target là `paid_date - received_date`.
4. Sau khi chốt nhãn, so baseline với mô hình đơn giản theo rolling origin; mọi phiên bản/snapshot của cùng invoice phải được quản lý để không rò rỉ outcome tương lai. Đánh giá censoring trên cohort đã chọn không tự bổ sung danh mục unpaid bị thiếu.

Chưa có invoice–payment allocation và bank links đầy đủ, nên **chưa chấm được chính xác lịch tiền thu từng phần hoặc toàn danh mục AR mở của SME Việt Nam**. Đây là giới hạn nhãn và domain, không phủ nhận giá trị benchmark của hai nguồn.

## 7. Tái lập và nguồn

Từ gốc repo, với Python có pandas/numpy:

```powershell
python scripts/data_download/download_czech_t1_datasets.py --snapshot 2026-10-18 --workers 3
python scripts/data_audit/audit_czech_t1_datasets.py --snapshot 2026-10-18
```

Lệnh download dùng cache các file đã tải, tải lại trang đầu/metadata để kiểm tra; không phải công cụ lưu giữ mọi phiên bản lịch sử. Muốn snapshot mới, dùng ngày thư mục mới. Audit không gọi mạng, không train, không sửa file gốc; các gate có trong script và từng dòng CSV xuất ra.

- [Kết quả aggregate đầy đủ](../references/data-checks/t1/czech_t1_full_audit.json), bao gồm missing fields, trùng, coverage, số dòng theo buyer/loại chứng từ.
- [Script tải](../../scripts/data_download/download_czech_t1_datasets.py) và [script audit](../../scripts/data_audit/audit_czech_t1_datasets.py).
- [Hướng dẫn Bộ Tài chính](https://data.mf.gov.cz/stories/navod-faktury.html), [CSV gốc](https://data.mf.gov.cz/exports/faktury/faktury.csv), [metadata điều kiện sử dụng](https://data.mf.gov.cz/katalog/cs/dataset/prehled-faktur-ministerstva-financi-cr/resource/649107b9-e2d8-4b47-92c5-024c6a200c0a).
- [Tài liệu API ngành y tế](https://faktury.mzcr.cz/site/otevrena-data). Đã tải được không đồng nghĩa mọi điều kiện tái phân phối đã được chốt; chưa tự gán license chưa xác minh cho bản data mới.
- [Đề xuất lựa chọn nguồn và thiết kế benchmark T1](t1_dataset_recommendation.md), gồm đối chiếu BPI/DC và các thay đổi pipeline còn cần thực hiện.
