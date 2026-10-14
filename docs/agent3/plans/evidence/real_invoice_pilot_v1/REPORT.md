# Kiểm thử extraction trên hóa đơn công khai — 13/10/2026

Đã thu thập nguồn, đối chiếu bằng mắt và sửa extractor trên một bộ pilot có nhiều bố cục. Kết quả này là bằng chứng phát triển, chưa phải chứng nhận chất lượng OCR hay thay thế gate calibration bằng dữ liệu thực được người độc lập xác nhận.

## Phạm vi và nguồn

Kiểm kê 9 URL; tải được 6 PDF nguồn, 3 URL IMDA không truy cập được. Chỉ các trang được chọn và nhìn trực tiếp mới được đưa vào benchmark; có từ “hóa đơn” trong một trang không đủ để xác định đó là hóa đơn. Không tính các trang tài liệu khác trong PDF dài thành mẫu hóa đơn.

| Nguồn | Trang được chọn | Trường hợp |
|---|---|---|
| [Chứng từ công khai tháng 12/2023](https://hpcmn-bucket.s3.ap-southeast-1.amazonaws.com/Chung_Tu_T12_2023_5e840a3a6b.pdf) | 1, 2 | VNPT song ngữ, font tách mảnh; Viettel viễn thông, tổng đặt trong bảng |
| [Hóa đơn điều chỉnh Viettel được đăng công khai](https://congdongketoan.vn/attachments/k24taa18525-pdf.21737/) | 1 | Điều chỉnh thông tin, tiền bằng 0; có số/ngày hóa đơn cũ trong ghi chú |
| [Hồ sơ năng lực Đại Trường Phúc](https://xaydungdaitruongphuc.com/upload/file/hsnl-2024-7320-1767.pdf) | 69, 118 | CyberBill; hóa đơn trong khung, header/footer ngoài hóa đơn, chữ bị tách từng ký tự, mô tả nhiều dòng, dòng thiếu số lượng/đơn giá |
| [PDF phần mềm trên CDN công khai](https://file.hstatic.net/1000139524/file/20230516667_0fffb8d703ca4bd886d3971797539a44.pdf) | 1 | FAST/Haravan, KCT, bảng rộng có chiết khấu và tiền trước/sau thuế, địa chỉ xuống dòng |
| [Hồ sơ công khai tại Khu Công nghệ cao TP.HCM](https://shtp.hochiminhcity.gov.vn/Portals/0/Uploads/2026/1/20260128133037046.pdf) | 117, 134 | MISA, nước/nước thải, 5%/8%, tên bên bán không có nhãn, chữ ký của cơ quan thuế và người bán |
| [Tài liệu học kế toán](https://hocketoanthuchanh.com/wp-content/uploads/2024/12/HDDT-BCT-DOANH-NGHIEP-Q2.25-CHUAN.pdf) | 2 | Hai dòng có thuế suất 10%/8%, mô tả/địa chỉ xuống dòng, bảng tổng theo thuế suất |

8 trang đầu thuộc nhóm chứng từ trong nguồn công khai; 1 trang từ nguồn học kế toán được báo riêng vì chưa xác minh đó là giao dịch thực hay mẫu được chỉnh phục vụ đào tạo. Không xác minh chữ ký số hay tính hợp pháp của giao dịch trong đợt này.

Hai trang CyberBill và hai trang MISA dùng cùng họ template. Chúng là kiểm tra biến thể cùng template, **không phải holdout độc lập**. Bộ pilot được dùng để tìm lỗi và phát triển, nên không thể dùng accuracy trên bộ này làm ước lượng tổng quát ngoài thực tế.

## Cách kiểm tra

1. Lưu URL, SHA-256, kích thước và số trang của nguồn tại dữ liệu local; tách trang hóa đơn, giữ lớp chữ và render ảnh để nhìn đối chiếu.
2. Gán nhãn chọn lọc bằng cách đọc ảnh: tên hai bên, MST, số/ký hiệu/ngày hóa đơn, tổng tiền in trên chứng từ và tiền tệ khi có ghi. Nhãn được agent chép bằng mắt, **chưa có người độc lập adjudicate**. Địa chỉ không nằm trong metric hiện tại; chỉ được kiểm tra spot-check và regression tổng hợp.
3. Đo `native_only` trước và sau thay đổi bằng cùng profile `number_locale=VI`. Đây là phép đo extractor trên lớp chữ, **không phải pipeline production đầy đủ**, vì production có thể chọn HYBRID và chạy thêm OCR.
4. Chạy worker PP-OCRv6 + VietOCR thực trên 3 ảnh render 150 DPI: VNPT, CyberBill và FAST/KCT. Lưu response/normalized document và tái sử dụng cùng response khi sửa extractor. Báo riêng `scan` và `hybrid`.
5. Ba ảnh là biến thể raster hóa của 3 PDF đã có, không phải 3 hóa đơn mới và không đại diện cho ảnh chụp điện thoại/scan máy thật.
6. Ghép hai trang hóa đơn VNPT/Viettel để kiểm tra tài liệu nhiều hóa đơn: phải trả `REVIEW_SPLIT`, không tạo một CFR gộp.
7. Không chỉnh DB đang chạy UI, không thay đổi nhãn synthetic hay bằng chứng gate lịch sử.

Baseline `before_labeled` được lưu trước các sửa đổi của đợt pilot này, sau bản sửa VNPT ở lượt trước. Báo cáo chấm lại artifact đã lưu theo nhãn độc lập; không chạy lại code cũ trên source mới. Chỉ so sánh trước/sau cho `native_only`: một lượt thử OCR ban đầu diễn ra song song với phát triển nên không được dùng làm baseline OCR. Fingerprint được kiểm tra nhất quán trong từng phase tại [summary.json](summary.json).

## Kết quả trên các trường đã gán nhãn

| Nhóm | Số trang | Đúng trước | Đúng sau | Còn lại sau |
|---|---:|---:|---:|---|
| PDF có lớp chữ, nguồn công khai | 8 | 21/80 | 79/80 | 1 MISSING |
| PDF từ tài liệu học kế toán, báo riêng | 1 | 2/10 | 10/10 | Không còn lỗi trên 10 trường chọn lọc |
| Ảnh render chạy OCR thực | 3 | Không so sánh | 21/31 | 6 MISSING, 4 WRONG |
| HYBRID: lớp chữ + cùng response OCR thực | 3 | Không so sánh | 27/31 | 4 AMBIGUOUS |

`WRONG` là trường có trạng thái PRESENT nhưng giá trị khác nhãn. `AMBIGUOUS`/`MISSING` vẫn là chưa trích xuất thành công; không cộng vào số đúng. Đây là exact match trên trường được chọn; không phải “toàn hóa đơn đúng” hoặc độ chính xác tính thuế.

Số dòng hàng phát hiện đúng với số dòng quan sát trên 7/7 hóa đơn nguồn công khai có nhãn số dòng, và 2 dòng của trang học kế toán. Hóa đơn điều chỉnh thông tin được loại khỏi metric số dòng hàng vì nội dung trong bảng là ghi chú điều chỉnh. **Đúng số dòng không chứng minh đúng mọi ô hoặc đầy đủ hàng hóa.** Dòng chưa có bằng chứng thuế suất vẫn MISSING; `item_discovery_status` không tự chuyển COMPLETE khi không có số dòng tường minh.

## Những lỗi đã sửa

- Ghép font run theo khoảng cách glyph; giữ khoảng trắng gốc và các block ID làm evidence. Trước đây chèn khoảng trắng giữa mọi mảnh làm hỏng cả nhãn lẫn số.
- Nhận các nhãn song ngữ, `Số:`, `Serial No.`, ngày in thành ngày/tháng/năm, ký hiệu nằm dưới nhãn. Không lấy ngày ký hoặc số hóa đơn được nhắc trong ghi chú làm ngày/số của hóa đơn hiện tại.
- Giữ ngữ cảnh bên mua/bán theo vùng; kiểm tra hồi quy cho hai cột đặt song song. Chỉ nhận issuer không có nhãn khi có tiêu đề hóa đơn, ranh giới người mua, một MST hợp lệ và tên tổ chức gần đó.
- Không dùng nhãn `Tên đơn vị:` làm tên doanh nghiệp khi ô họ tên người mua bị trống. Dừng gán thông tin bên mua/bán khi đã đến bảng hàng; không lấy địa chỉ footer của hồ sơ năng lực làm địa chỉ người mua.
- Nối các dòng địa chỉ gần nhau, cùng cột và dừng trước nhãn tiếp theo; giữ evidence của từng dòng.
- Đọc bảng không có cột VAT, bỏ dòng chỉ dẫn cột A/B/C hoặc 1/2/3, ghép mô tả xuống dòng theo tâm hàng có tiền. Không tự suy thuế suất dòng từ thuế suất cuối hóa đơn.
- Đọc tổng theo các tiêu đề cột tài chính tường minh; không lấy số tiền đầu tiên bên phải nhãn làm tổng thanh toán trong bảng có nhiều cột.
- Trích xuất từng modality rồi giữ candidate cạnh tranh. OCR có box gần hơn không được làm mất giá trị native hợp lệ. Ký hiệu hiện đại bị OCR đọc thừa ký tự bị từ chối thay vì PRESENT sai.
- Với bảng HYBRID có cấu trúc native đọc được, giữ cấu trúc native và đánh dấu cần review, tránh nhân đôi dòng do các box OCR chồng lên chữ gốc.
- Worker có `--number-locale VI|EN|AUTO`. Lựa chọn được lưu trong extraction profile/key. Mặc định vẫn AUTO; không âm thầm đổi quy ước số trên mọi đầu vào.

Kiểm tra bố cục hai cột, địa chỉ wrap và các nhánh từ chối dùng regression tổng hợp; **chưa có mẫu hóa đơn thực hai bên đặt song song trong bộ pilot**.

## Lỗi còn lại và giới hạn

- Hóa đơn điều chỉnh Viettel: tổng thanh toán 0 nằm hơi cao hơn nhãn. Parser vẫn để MISSING; người review điền 0 sau khi đối chiếu. Chưa nới khoảng cách để tránh gán nhầm tiền của hàng lân cận.
- OCR-only: có MST/ngày/ký hiệu chưa đọc được và 4 tên doanh nghiệp PRESENT khác nhãn. Các trường PRESENT này vẫn không phải “đã xác nhận”; quality/manual review phải tiếp tục chặn tự động chấp nhận.
- HYBRID: 4 tên còn AMBIGUOUS do native và OCR không khớp. Không tự ưu tiên một tên và che mất xung đột.
- Chưa đo field accuracy đầy đủ của line items/địa chỉ; bảng KCT và đa thuế suất đã đọc được cấu trúc nhưng cần nhãn độc lập cho từng ô.
- Chưa đủ dữ liệu cho ảnh chụp nghiêng, mờ, bị cắt, scan máy thật, đơn hàng nhiều trang của cùng một hóa đơn, ngoại tệ, KKKNT, số tiền âm, chiết khấu có số tiền khác 0 và đa dạng nhà cung cấp/template mới.
- Chưa kiểm tra lại UI bằng trình duyệt thực. Đợt này kiểm tra reader/extractor/OCR worker và hồi quy backend; không tuyên bố visual acceptance.
- Không tự sinh verdict tuân thủ thuế, không dùng bộ này để fit calibration hoặc train OCR, không coi nguồn công khai là giấy phép phân phối/training.

## Chạy lại và thử UI

Từ `D:\financial`, dùng interpreter của app:

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/collect_public_invoices.py
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/benchmark_public_invoices.py --phase replay --ocr
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts/report_public_invoice_pilot.py
```

Benchmark dùng `data invoice/real_invoice_pilot_v1/labels.json` để chấm khi file tồn tại; không có nhãn thì vẫn xuất extraction nhưng không có accuracy. Nhãn và PDF thực nằm trong thư mục local bị gitignore, không được đóng gói thành fixtures public. Script report yêu cầu các snapshot `before_labeled`, `verified_all_fields` và nhãn local; checkout mới không có baseline này và không thể tái tạo nó chỉ bằng code đã sửa.

PDF một trang để upload nằm tại `data invoice/real_invoice_pilot_v1/cases/`. Ảnh đúng kích thước dùng cho OCR nằm tại `normalized/<case>/page-0.png`. `software_kct-p1`, `cyber_construction-p69`, `misa_public_filing-p117` là ba mẫu bổ sung dễ thử sau VNPT. Tránh upload nguyên hồ sơ nguồn có hàng trăm trang/nhiều chứng từ.

Khởi động lại API, upload lại để có job mới. Từ `D:\financial\agent3_tax_compliance`, trong phiên đã cấu hình auth/DB giống server:

```powershell
.\.venv\Scripts\python.exe -m src.jobs.worker --taxpayer-id demo-payer --job-id <job-id-moi> --number-locale VI
```

Chỉ chọn VI khi xác nhận tài liệu dùng quy ước số Việt Nam. Với tài liệu chưa rõ, giữ AUTO và review candidate. Job REVIEW cũ không được worker tự sửa lại; upload mới hoặc dùng luồng review hiện có. Không ghi đè lịch sử.

## Kiểm tra hồi quy

Thêm 10 test bố cục/an toàn vào bộ extraction ngoài 3 test font-fragment ở lượt sửa VNPT trước. Bao gồm nhãn trống, footer, địa chỉ xuống dòng, cột người mua/người bán song song, issuer thiếu bằng chứng, ký hiệu OCR sai, xung đột native/OCR, bảng không cột thuế, mô tả hàng hai dòng và tổng nhiều cột. Kết quả kiểm tra đầy đủ ghi tại `validation.json`.

Việc tiếp theo là người dùng xác nhận kết quả UI trên các file một trang này và bổ sung bộ ảnh scan/chụp thực có nhãn đối chiếu độc lập. Ưu tiên đo/sửa OCR tên doanh nghiệp và từng ô bảng trước khi quyết định fine-tune.
