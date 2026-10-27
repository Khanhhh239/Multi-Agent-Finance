# T0–T10: hệ thống làm gì và đã đạt gì trên dữ liệu tổng hợp?

**Trạng thái ngày 25/10/2026 · branch `agent1-Khanh` · commit `70c0ceb`.** Đây là bản giải thích kết quả đã có, không phải chứng nhận hệ thống dùng được cho doanh nghiệp thật. Những số đo từ thí nghiệm cũ được đánh dấu rõ.

## 1. Đọc nhanh toàn bộ hệ thống

Một doanh nghiệp cung cấp hoá đơn, sao kê ngân hàng, sổ kế toán và các khoản chi đã biết. Hệ thống xử lý theo luồng:

`T0 kiểm tra dữ liệu → T9 ghép tiền ngân hàng với hoá đơn → T1/T2/T3/T8 ước lượng khoản phải thu → T4 dự báo doanh thu mới + T5 xếp lịch chi → T6 dự báo số dư 13 tuần → T7 theo dõi thay đổi → T10 giải thích và thử kịch bản.`

### Các từ dùng trong tài liệu

| Từ | Hiểu đơn giản |
|---|---|
| `src` / `tgt` | Bộ doanh nghiệp giả lập dùng để học và chọn cấu hình / bộ doanh nghiệp giả lập khác dùng để kiểm tra. |
| `zero-shot` / `fine-tune` | Đem mô hình học ở `src` sang `tgt` dùng ngay / học bổ sung từ quá khứ của `tgt`. |
| Nhãn thật / nhãn T9 | Ngày tiền về do máy phát biết chắc / ngày T9 suy ra từ sao kê bị nhiễu. Trong thực tế không có cột “nhãn thật” do máy phát cung cấp. |
| E2E | Đánh giá cả chuỗi từ nhập dữ liệu, đối soát đến dự báo tiền mặt; khó hơn thử từng T bằng nhãn thật. |
| MAE, pinball, Brier, SPL, IS80 | Các thước đo sai số: **càng thấp càng tốt**. MAE ở đây thường tính bằng ngày; mỗi chỉ số đo một loại đầu ra khác nhau. |
| `cov80` | Trong 100 kết quả, khoảng dự báo “80%” chứa kết quả thật bao nhiêu lần. Mục tiêu thường gần 80%. |
| Precision / recall / F1 | Khi ghép giao dịch: precision đo phần ghép đã làm mà đúng; recall đo phần liên kết thật tìm được; F1 cân bằng hai mặt. **Càng cao càng tốt**. |
| CI | Khoảng bất định của một số đo, thường được lấy mẫu lại theo doanh nghiệp. Một điểm vừa qua ngưỡng chưa chắc vững nếu CI còn rộng. |

Khi dự báo tại ngày `T`, mô hình chỉ thấy dữ liệu đã có đến ngày đó. Dữ liệu huấn luyện, chọn tham số và kiểm tra được tách theo thời gian; nhiều phép thử đợi ít nhất 120 ngày để biết kết cục của hoá đơn. Số liệu cũ có lỗi “cắt tuần chưa đủ” chỉ giữ để đối chiếu lịch sử, không thay kết quả chạy lại sau sửa.

## 2. Dữ liệu tổng hợp được tạo như thế nào?

Máy phát tạo một thế giới doanh nghiệp theo **thứ tự nguyên nhân rồi mới đến dữ liệu quan sát**, thay vì lấy ngẫu nhiên từng bảng độc lập:

1. **Lịch và môi trường:** ngày làm việc, Tết, mùa vụ, COVID, sốc tín dụng 2022–2023 và biến động thanh khoản chung.
2. **Doanh nghiệp và khách:** ngành, quy mô, số dư đệm, cách ghi sổ; từng khách có kỳ hạn, thói quen trả, ngày chuyển khoản quen thuộc và mức nhạy với sốc.
3. **Hoá đơn:** doanh thu từng tuần tạo ra số lượng và giá trị hoá đơn; có ngày lập, hạn trả và thuế.
4. **Việc trả tiền:** khách có thể trả sớm, đúng hạn, trễ, trả một phần, gộp nhiều hoá đơn, tranh chấp hoặc vỡ nợ. Máy phát biết **ngày tiền thực về**.
5. **Những gì kế toán nhìn thấy:** sao kê có tên viết tắt, nội dung thiếu số hoá đơn, phí chuyển khoản và giao dịch không liên quan; sổ cái có thể gạch nợ theo lô nên ngày sổ khác ngày tiền về. Máy phát còn tạo lời hứa, các khoản chi và số dư ngân hàng.

Vì máy phát biết cả sự thật lẫn bản ghi bị nhiễu, ta đo được T9 đã ghép đúng bao nhiêu và dự báo T1/T6 lệch thế nào. Trong dữ liệu doanh nghiệp thật, sự thật này phải được kế toán kiểm tra; không thể lấy điểm synthetic làm kết quả pilot.

| Bộ dữ liệu | Vai trò | Quy mô |
|---|---|---:|
| `src` | Học mô hình và chọn cấu hình | 40 doanh nghiệp, 193.469 hoá đơn |
| `tgt` | Kiểm tra trên nhóm doanh nghiệp giả lập khác | 14 doanh nghiệp, 41.762 hoá đơn |
| `sens_uk`, `sens_coface` | Thử thời gian trả có đuôi ngắn/dài khác bộ gốc | 12 doanh nghiệp mỗi bộ |
| `tgt2`, `tgt3`, `tgt5`, `tgt6` | Những lần kiểm tra tiếp theo, mỗi bộ có seed và giao thức riêng | Không gộp điểm với `tgt` |

### Các tình huống khó đã sinh

Có **12 thế giới hard-case**, thường 12 doanh nghiệp mỗi thế giới. Mỗi thế giới nhấn mạnh một vấn đề:

| Tình huống | Hệ thống bị thử ở đâu? |
|---|---|
| Khách lớn trả theo lô; khách mới ít lịch sử; mùa vụ cực mạnh; sốc nguồn cung riêng ngành | T1/T6 phải dự báo khi tiền về dồn cục hoặc hành vi đột ngột thay đổi. |
| Một đầu mối trả hộ nhiều khách; COD; thoả thuận miệng không được ghi lại | T9 phải tìm đúng hoá đơn; T8 không được quá tin lời hứa đang có. |
| Chiết khấu trả sớm; giữ lại 5% tiền bảo hành; ngoại tệ; hoá đơn điều chỉnh | Số tiền sao kê khác số tiền ghi trên hoá đơn nhưng T9 vẫn phải phân bổ đúng. |
| Khách hàng có hành vi rất khác nhau | Kiểm tra máy phát và mô hình có biểu diễn được sự khác biệt giữa khách. |

Ba thế giới khách trả theo lô, chiết khấu sớm và sốc nguồn cung đã có bản v2 sửa cách sinh. **12/12 thế giới qua kiểm tra cấu trúc dữ liệu**, nhưng phép kiểm tra nghiệp vụ chỉ đạt **14/16 tiêu chí**. Hai điểm còn thiếu: sự khác nhau về độ trễ *giữa các khách* là **0,380**, dưới mục tiêu **0,55–0,65**; chuỗi tham chiếu hoá đơn gốc–thay thế–huỷ–điều chỉnh chưa đầy đủ. T9 có F1 từ **0,575** ở tình huống giữ lại bảo hành đến **0,924** ở tình huống doanh nghiệp mới: kết quả trên một kịch bản không đại diện cho mọi kịch bản.

### Benchmark hiện tại của máy phát

| Kiểm tra | Đã đo được | Kết luận |
|---|---|---|
| Tốc độ trên 29.817 hoá đơn | Cách sinh mới **8,657 giây**, cách cũ **13,375 giây**; nhanh **1,545 lần**, dữ liệu tạo ra bằng nhau | Chưa chứng minh mục tiêu nhanh ít nhất 5 lần khi sinh 1 triệu hoá đơn. |
| Bốn bộ lớn `big_000`–`big_003` | Tổng **600 doanh nghiệp, 3.500.679 hoá đơn**; cả bốn qua kiểm tra cấu trúc | Số đo thời gian sinh ban đầu có lỗi, đã vô hiệu hoá. Chưa có thời gian sinh bộ lớn đáng tin cậy. |
| Độ giống dữ liệu AR thật tham chiếu | Bộ phân loại phân biệt rất dễ khi nhìn cả kỳ hạn và cấu trúc (AUC **0,996–0,997**). Chỉ nhìn hành vi và so cùng cửa sổ 15 tháng: `src` **0,785**, bản thử v2 **0,697** | Bộ thật chỉ có 6 “công ty”; khoảng bất định rộng. Chưa đủ căn cứ chọn phiên bản máy phát theo mức chênh này. Bản v2 chưa thay thế các bộ gốc. |
| Huấn luyện T1 với 1/3/10 triệu **hàng huấn luyện**, không phải hoá đơn | Thời gian **12,3/51,2/116,0 giây**; pinball khi dùng ngay trên `tgt` **6,28/6,31/6,33** | Tăng số hàng chưa cho thấy lợi ích rõ trên phép thử này. Đây là thời gian học T1, không phải tốc độ sinh dữ liệu. |

### Những giới hạn của cách sinh hiện tại cần nhớ khi đọc benchmark

- Thế giới nền có COVID, căng thẳng tín dụng 2022–2023, Tết, mùa vụ và các biến động riêng khách. Mười hai hard case được sinh **tách từng case**; bốn `big_*` vẫn dùng cùng cơ chế nền với seed và giả định đuôi trễ khác, chưa phải bộ stress thị trường đa dạng đã tích hợp.
- Tiền mua nhà cung cấp tuần này lấy từ doanh thu kế hoạch **hai tuần sau**; số dư đầu kỳ cũng dùng trung bình chi của toàn giai đoạn. Hóa đơn đang mở được rút lịch trả chủ yếu từ trạng thái **ngày đến hạn**, nên cú sốc mới xảy ra sau hạn khó tác động tự nhiên lên khoản nợ đó. `supply_shock` chỉ sửa thanh khoản khách ngành thép, không mô phỏng thiếu hàng/giá vốn, và không tính lại vỡ nợ sau khi sửa thanh khoản.
- `src` đã lưu có **58,88% doanh số bán chịu**, **42,43% giá trị hóa đơn bán chịu quá hạn**, so với mốc khảo sát Atradius 2025 là **65%** và **39%**. Đây là độ lệch so với **mốc hiệu chỉnh**; `src` gộp 2019–2025 và sáu ngành, còn khảo sát là nửa đầu 2025 ở ba ngành, nên chưa thể gọi đó là sai số của toàn thị trường Việt Nam.
- Một số kiểm nghiệp vụ chưa đạt dù contract của thế giới đạt: phương sai thời gian trả giữa khách trong `heterogeneity` **0,380** so mục tiêu nội bộ **0,55–0,65**; chuỗi tham chiếu hoá đơn điều chỉnh trong `credit_note` **0%** so mục tiêu **100%**. Điểm benchmark của T1–T10 vì thế cần hiểu là kết quả **trên chính máy phát hiện tại**, không là bằng chứng model thích nghi tốt với cú sốc tương lai thực.

## 3. Phương pháp đang dùng ở từng T và kết quả hiện tại

Các đoạn **Phương pháp hiện tại** mô tả cách tính đã có trong mã hoặc phép thử nêu ở đây. Nhánh thử, đối chứng và tính năng chưa đưa vào luồng mặc định được ghi riêng; không coi chúng là khả năng đã được kiểm chứng trong pilot thật.

### T0 — Kiểm tra đầu vào

**Phương pháp hiện tại:** Bộ nạp đọc XML hoá đơn điện tử (phiên bản 2.0.0/2.0.1/2.1.0), bảng kế toán và sao kê; chuẩn hoá định danh, ngày, tiền trước khi chuyển cho các T sau. Với hoá đơn, `quality_gate` kiểm từng dòng bằng quy tắc, không học máy: thiếu trường bắt buộc; chữ số kiểm tra MST người bán/người mua; ngày lập không hợp lệ, hạn trước ngày lập; `tiền trước thuế + VAT ≠ tổng tiền` (dung sai 1.000đ); thuế suất ngoài tập cho phép; tiền không dương; trùng bộ `(MST người bán, ký hiệu, số hoá đơn)`; tiền tệ không hỗ trợ. Kết quả là bảng cờ lỗi theo dòng để chặn hoặc yêu cầu sửa đầu vào. XML còn bị giới hạn kích thước và chặn DTD/thực thể; thông tin hoá đơn thay thế/điều chỉnh được đọc ra, nhưng chuỗi tham chiếu chưa được kiểm tra đầy đủ.

**Kết quả:** Với 200 lỗi được cố ý chèn vào dữ liệu thử, T0 nhận ra đủ và không báo nhầm trong bộ sạch: precision **1,00**, recall **1,00**, tỷ lệ báo lỗi sạch **0,00**. Cổng G16 đạt. Đây là điểm trên các lỗi đã thiết kế để thử, chưa đo mọi dạng lỗi trong file doanh nghiệp thật.

### T1 — Dự báo khi nào hoá đơn mở sẽ được trả

**Phương pháp hiện tại:** Ở mỗi ngày cắt, tạo một bản ghi cho từng hoá đơn đã lập nhưng còn dư; chỉ dùng thanh toán, lời hứa và lịch sử khách đã biết đến ngày đó. Đặc trưng gồm tuổi nợ, khoảng cách tới hạn, tỷ lệ đã thu, số tiền so với mức thường của doanh nghiệp, độ trễ và nhịp trả quen thuộc của khách, công nợ đang mở, tín hiệu trễ chung và Tết. `DH-GBM` (LightGBM hazard rời rạc) khai triển mỗi bản ghi thành tối đa 13 hàng, mỗi hàng ứng với một tuần còn khả năng được trả; hoá đơn còn mở vẫn đóng góp các tuần đã quan sát mà không bị gán nhầm là “đã trả”. Mỗi hàng còn có thông tin biết trước của tuần tương lai như hạn trả, số ngày làm việc, ngày khách thường chuyển khoản và ngày đã hứa. Hazard có điều kiện từng tuần được nhân với xác suất còn chưa trả để ra xác suất thu ở từng tuần; từ đó suy ra phân vị ngày trả và phần xác suất ngoài 13 tuần. `B1d` dùng phân vị thời gian trả trong lịch sử khách làm mốc so sánh; CQR và fine-tune là các nhánh đánh giá riêng, chưa thay mô hình chính.

**Kết quả trên `src`:**

| Ngày bắt đầu phép thử | Sai số pinball B1d | Sai số DH-GBM | Giảm so B1d | Sai số ngày dự báo giữa | `cov80` |
|---|---:|---:|---:|---:|---:|
| 03/07/2023 | 19,33 | **5,90** | **69,5%** | 19,87 ngày | 0,877 |
| 01/07/2024 | 14,38 | **5,18** | **64,0%** | 16,52 ngày | 0,851 |

Đem mô hình `src` sang `tgt` dùng ngay, khi chưa có lịch sử tại đích, pinball là **6,44** so B1d **13,70**. Học bổ sung từ 12 tháng `tgt` cho **7,11**, kém mức **6,55** của bản dùng ngay trong phép thử cùng lịch sử. Một số phép hiệu chỉnh khoảng và xác suất bốn tuần còn trượt cổng G3/G4; nhánh fine-tune trượt G7. Mô hình chính không tự đổi theo các nhánh thử đó.

### T2 — Ước lượng khả năng không thu được nợ

**Phương pháp hiện tại:** Chọn các hoá đơn còn mở và đã quá hạn tại ngày cắt. `CureGBM` là bộ phân loại LightGBM ước lượng `P(nợ xấu | thông tin biết tại ngày cắt)` từ tuổi nợ, đặc trưng khách và doanh nghiệp cùng loại đặc trưng của T1; khi huấn luyện chỉ lấy trường hợp đã biết kết cục trả hết hoặc xoá nợ trước ngày kết thúc nhãn, không tự gán hoá đơn còn mở là nợ xấu. Trong mô phỏng có bật T2, T6 lấy mẫu nhánh không trả theo xác suất này và dùng phân phối tuần T1 cho nhánh có trả; mã còn có phép kiểm tra khi xác suất nợ xấu mâu thuẫn với xác suất còn chưa trả của T1. Lịch trích lập theo tuổi nợ là mốc quy tắc để so sánh, không phải nhãn huấn luyện.

**Kết quả cũ trên synthetic:** Cure-GBM có PR-AUC **0,965** và Brier **0,048** ở `src`; khi chuyển sang `tgt` là **0,976/0,053**. Bảng này **chưa được chạy xác nhận sau khi sửa cách lấy dữ liệu theo ngày và tuần dự báo**. Vì vậy đây là lịch sử tham khảo, chưa phải bằng chứng nghiệm thu mới. G8 là một phép kiểm khác trên dữ liệu SBA thật và hiện chưa đạt.

### T3 — Nhận diện tranh chấp hoặc trả một phần
Vâ
**Phương pháp hiện tại:** Tại ngày lập hoá đơn, đếm các hoá đơn trước của cùng khách đã biết kết cục; tính riêng tỷ lệ tranh chấp và tỷ lệ trả một phần. Mỗi tỷ lệ được co về tỷ lệ nền bằng tiền nghiệm tương đương 20 quan sát để khách mới không nhận dự báo  cực đoan. Các biến số tiền tương đối, kỳ hạn và tỷ lệ trả trễ được tạo để thử LightGBM, nhưng phương pháp giữ lại là tỷ lệ lịch sử khách đã co (EB). T3 trả hai xác suất ở cấp hoá đơn; nhánh đưa thêm tín hiệu tranh chấp vào T1 đã thử nhưng chưa dùng mặc định.

**Kết quả trên 4.536 hoá đơn `tgt`:** Với tranh chấp, EB đạt AUC **0,667**, LightGBM **0,526**; với trả một phần, EB **0,718**, LightGBM **0,678**. Thêm đặc trưng tranh chấp từ T3 vào T1 còn làm pinball của nhóm tranh chấp `tgt` **xấu 3,11%**. Vì vậy nhánh này chưa được đưa vào T1 mặc định.

### T4 — Dự báo doanh thu chưa có hoá đơn

**Phương pháp hiện tại:** Gom doanh thu đã quan sát thành chuỗi tuần. `GlobalQuantileLGBM` học chung nhiều doanh nghiệp, tạo một hàng cho mỗi chân trời 1–13 tuần; doanh thu và 13 độ trễ gần nhất được chia cho trung bình 13 tuần của chính doanh nghiệp để mô hình dùng chung các quy mô tiền. Đầu vào còn có xu hướng 4/26 tuần, tuần cùng kỳ năm trước, mùa, Tết và chân trời `h`; ba mô hình LightGBM phân vị cho P10/P50/P90, sau đó CQR dùng cửa sổ hiệu chỉnh tách khỏi huấn luyện để chỉnh khoảng P10–P90. Chronos-Bolt zero-shot và trung bình phân vị với LightGBM là các cấu hình đã so, nên bảng kết quả ghi rõ cấu hình thắng ở từng bộ. T6 không coi toàn bộ doanh thu dự kiến là tiền về ngay: doanh thu mới được trải theo phân bố độ trễ thu tiền ước lượng từ lịch sử hoá đơn doanh nghiệp.

**Kết quả:**

| Bộ synthetic | Sai số SPL tốt nhất | `cov80` của LightGBM sau CQR | Mốc trung bình 13 tuần |
|---|---:|---:|---:|
| `src` | **0,2563** (kết hợp LightGBM + Chronos) | 0,837 | 0,2701 |
| `tgt` | **0,3474** (LightGBM + CQR) | 0,795 | 0,3861 |

Sai số SPL càng thấp càng tốt. G9/G10 đạt theo các phép kiểm đã đăng ký.

### T5 — Xếp lịch các khoản chi đã biết

**Phương pháp hiện tại:** Bộ quy tắc chọn phiên bản có hiệu lực tại kỳ cần tính, rồi tạo lịch ngày và số tiền từ hồ sơ doanh nghiệp: lương/BHXH theo kỳ lương; VAT và TNDN theo kỳ kê khai và **số thuế đã cung cấp**; thuê, lãi và gốc vay theo điều khoản/hợp đồng. Ngày rơi vào ngày nghỉ được dời tới ngày làm việc kế tiếp hoặc trước đó theo từng quy tắc; ví dụ BHXH dùng ngày làm việc trước. Phần nghĩa vụ mở rộng giữ `known_at`, nguồn hồ sơ, trạng thái xác minh và ngày đến hạn: chỉ đưa khoản đã biết tại ngày cắt vào lịch, hoàn VAT chỉ là dòng thu khi đã có quyết định phê duyệt. Lịch mở rộng đã được kiểm thử riêng nhưng chưa tự động cộng vào T6 vì cần đối chiếu khoản trùng và xác minh quy tắc.

**Kết quả:** **18/18** tình huống nghĩa vụ mở rộng và **54** ca nghiệp vụ cho **27** phiên bản quy tắc chạy đúng theo cấu hình kiểm thử. Tuy nhiên **27/27 quy tắc chưa được chuyên gia xác minh**; lịch mở rộng cũng chưa được cộng mặc định vào T6 vì có nguy cơ tính trùng. G11 được để ngoài phạm vi giai đoạn chỉ dữ liệu tổng hợp; pilot thật vẫn cần xác minh.

### T6 — Dự báo số dư và nguy cơ thiếu tiền 13 tuần

**Phương pháp hiện tại:** Mỗi đường Monte Carlo lấy tuần thu của từng hoá đơn mở từ phân phối 13 tuần T1; một nhân tố sốc Student-t chung và nhiễu riêng làm các khoản thu có thể cùng trễ, với mức tương quan chọn trên bộ nguồn theo điểm khoảng dự báo. Nếu có xác suất nợ xấu T2, mô phỏng có thể rẽ nhánh không thu trong chân trời. Với doanh thu mới T4, lấy mẫu theo P10/P50/P90 rồi trải tiền thu bằng phân bố thời gian thu của hoá đơn doanh nghiệp trong 365 ngày đã biết; phần chi gồm lịch đã biết T5 và khoản chi bất thường lấy mẫu từ tần suất/giá trị lịch sử. Cộng dòng thu trừ chi vào số dư đầu kỳ cho từng tuần, lấy P10/P50/P90 của các đường và tỷ lệ đường có `min(số dư tuần) < 0` làm rủi ro thiếu tiền. `ACI` cập nhật mức cắt khoảng riêng theo chân trời **sau khi** số dư thật của chân trời đó lộ diện; đây là hiệu chỉnh dải, không sửa các khoản thu/chi gốc.

**Hai mức kiểm tra cần tách:**

| Phép thử trên `tgt` | `cov80` tuần 1–4 / 5–13 | Ý nghĩa |
|---|---:|---|
| Cho T6 ngày thu **thật của máy phát** | **0,746 / 0,752** sau ACI | Kiểm tra phần mô phỏng T6 khi đầu vào thuận lợi. |
| Chạy cả chuỗi, ngày thu do **T9 ước lượng** | **0,754 / 0,767** sau ACI | Gần luồng sản phẩm hơn: 14 doanh nghiệp × 52 ngày cắt, G12 đạt. |

Ở phép E2E, điểm IS80 tuần 1–4/5–13 là **12,00/20,95**, tốt hơn mốc dự báo trực tiếp **12,48/22,41** và mốc đơn giản **13,62/31,04**. Nhưng cảnh báo thiếu tiền vẫn báo sai **2,08 lần/doanh nghiệp/năm**, cao hơn ngưỡng **1,0** dù phát hiện sớm **93,8%** trong 16 sự kiện; G13 chưa đạt.

Một thử nghiệm tiếp theo cho kế toán duyệt tối đa 5 giao dịch/tuần trước khi dự báo: báo sai **0,970** trên `tgt6` nhưng **1,371** trên `tgt3`. Người duyệt trong mô phỏng luôn chọn đúng. Vì kết quả không đạt ở cả hai bộ, nhóm đã dừng việc tiếp tục tối ưu G13 trên dữ liệu sinh.

### T7 — Phát hiện khách đổi thói quen trả tiền

**Phương pháp hiện tại:** Với từng khách, chỉ sau ít nhất 8 lần trả, so độ trễ của khoản mới với tối đa 40 khoản trước đó; đổi thứ hạng thực nghiệm của độ trễ thành điểm chuẩn hoá `z` (PIT), để các khách có phân phối trả đúng hạn/trả trễ khác nhau vẫn so được. `CUSUM` một phía cộng dồn các `z` dương sau khi trừ độ lệch cho phép, báo khi vượt ngưỡng rồi đặt lại; ngưỡng chọn trên `src`. Page–Hinkley, BOCPD và trung bình trượt là đối chứng. Tín hiệu báo động chỉ là dấu hiệu khách đổi hành vi; nhánh dùng nó để điều khiển T6 đã thử riêng, chưa chứng minh cải thiện độ phủ.

**Kết quả:** CUSUM phát hiện **52,4%** điểm gãy trong 180 ngày, trễ trung vị **50 ngày**, nhưng báo nhầm **0,633 lần/khách/năm**, vượt giới hạn **0,5**. Phương pháp Page–Hinkley báo nhầm ít hơn (**0,424**) nhưng chỉ phát hiện **42,9%**. Nhánh điều khiển T6 gần như không cải thiện độ phủ trong hai giai đoạn khủng hoảng đã thử (**0,659** và **0,633**). G14 chưa đạt.

### T8 — Đánh giá lời hứa trả tiền

**Phương pháp hiện tại:** API lưu lời hứa gắn với hoá đơn/khách, ngày ghi nhận, ngày hứa và số tiền; khi dự báo tại `T`, chỉ lấy bản ghi đã có tới `T`. Đặc trưng độ tin cậy đang đưa vào T1 là `(số lần giữ lời + 4)/(số lời hứa đã xác minh + 6)` cho từng khách (tiền nghiệm Beta(4,2)); chỉ đếm lời hứa đã qua ngày hứa cộng 3 ngày và đã biết kết cục, nên khách chưa có lịch sử nhận mức dự phòng 4/6. T1 còn dùng cờ có lời hứa, khoảng cách tới ngày hứa, trạng thái quá hẹn và biến `promised_in_k` để điều chỉnh xác suất thu từng tuần. Mô hình `PromiseReliability` có trọng số gần đây (nửa đời 90 ngày) và co về tỷ lệ doanh nghiệp là phép đánh giá độ tin cậy riêng, chưa phải công thức `c_promise_rel` của T1. Quy trình trích lời hứa từ chat và cho người duyệt xác nhận mới ở mức đặc tả, chưa có giao diện trích xuất chat; phép thử sáu đặc trưng bổ sung cũng chưa đạt G17 chắc chắn.

**Kết quả:** Với lời hứa synthetic sạch, dùng lời hứa làm sai số ngày của nhóm có lời hứa giảm từ **13,85** xuống **11,24** ngày (**18,8%**). Khi lời hứa bị làm nhiễu, sai số giảm từ **13,90** xuống **12,85** ngày (**7,6%**), thấp hơn ngưỡng cải thiện 10% của G17. Nhánh thử thêm sáu đặc trưng đạt **10,83%** theo điểm ước lượng, nhưng khoảng bất định **8,16–13,01%** còn cắt qua ngưỡng; G17 chính thức vẫn chưa đạt. Chưa có lời hứa người thật để kiểm tra.

### T9 — Ghép giao dịch ngân hàng với hoá đơn

**Phương pháp hiện tại:** Xử lý giao dịch tiền vào theo ngày trên sao kê, đồng thời chỉ xét hoá đơn đã lập, còn dư và các bút toán/điều chỉnh đã biết tới ngày giao dịch. Trước tiên tự ghép nếu nội dung chỉ rõ nhóm số hoá đơn có tổng dư khớp, hoặc chỉ có một hoá đơn khớp số tiền (dung sai 25.000đ). Với phần còn lại, sinh ứng viên khách từ tên/nội dung đã chuẩn hoá, số hoá đơn và mức khớp tiền; LightGBM chấm xác suất đúng khách rồi thử nhóm hoá đơn có tổng dư bằng tiền chuyển. Nếu điểm thấp hoặc nhiều cách phân bổ hợp lệ, giữ giao dịch trong hàng chờ duyệt; liên kết tự động được trừ dần khỏi dư nợ, ngày tất toán ước lượng chỉ xuất hiện khi tổng phân bổ đủ tiền. Bản v2 đã chọn trên `src` giới hạn nhóm hoá đơn **đoán** tối đa 2 và tắt nhánh phân bổ có trọng số hazard/FIFO; hàng chờ duyệt tối đa 5 lượt/tuần mới là phép mô phỏng với người duyệt luôn đúng, chưa phải năng suất người thật.

**Kết quả:** Bản lai quy tắc + mô hình trên `tgt` ghép đúng **94,0%** các liên kết đã tự làm (precision), nhưng chỉ tìm được **61,0%** liên kết thật (recall), F1 **0,740**. Sai số ngày thu ước lượng **1,45 ngày**, so **12,6 ngày** nếu dùng ngày gạch sổ. Bản T9 v2 chọn trước trên `src` có kết quả:

| Bộ thử | Precision | Recall | F1 | Tỷ lệ giao dịch xử lý tự động |
|---|---:|---:|---:|---:|
| `tgt` | 0,972 | 0,643 | 0,774 | 0,726 |
| `tgt2` | 0,966 | 0,636 | 0,767 | 0,715 |
| `tgt3` | 0,962 | 0,557 | 0,706 | 0,689 |

T9 v2 chưa đạt đồng thời precision ≥0,95 và F1 ≥0,80 của G15. Hàng chờ giả định người duyệt luôn đúng: trên công ty nguồn giữ lại, tối đa 5 lượt/tuần, thực dùng **2,81 lượt**, nâng độ phủ hoá đơn đã trả từ **90,9%** lên **95,2%**. Dùng nhãn T9 để học T1 thu hẹp khoảng cách sai số so với dùng ngày sổ khoảng **70,7%/73,0%** ở hai chân trời (điểm ước lượng, chân trời xa còn bất định). Sau khi ẩn danh HMAC tại lúc nạp, F1 T9 trên `tgt3` giảm nhẹ **0,706→0,700**.

### T10 — Giải thích và thử phương án hành động

**Phương pháp hiện tại:** Với một hoá đơn tại ngày cắt, lấy đóng góp đặc trưng từ LightGBM hazard T1 cho tuần đầu và diễn đạt các yếu tố tăng/giảm khả năng thu sớm. Để xếp thứ tự thu nợ, chọn trước tối đa 50 hoá đơn theo `dư nợ × P(chưa thu trong 2 tuần)`, rồi chạy lại T6 với từng hoá đơn giả định **thu đủ ngay tuần đầu**; `ΔP(thiếu tiền)` là chênh lệch so với cùng mô phỏng gốc, có thể chia cho giờ công nếu dữ liệu có sẵn. Chức năng “nếu như” thay độ trễ của một khách, dịch khoản chi hoặc giảm doanh thu rồi lấy lại dải số dư/rủi ro; thư viện stress test còn có tất cả khách trễ 30/60 ngày, khách lớn nhất không trả và doanh thu giảm 30% theo kịch bản tất định. Các chênh lệch này là tác động **giả định trong mô hình**, chưa phải hiệu quả gọi nợ ngoài đời.

**Kết quả:** Đã tạo được ví dụ dải số dư, danh sách hoá đơn và kịch bản. Trong ví dụ F001 ngày 18/11/2024, rủi ro thiếu tiền đã là **1,0** cả trước lẫn sau kịch bản, nên chênh lệch rủi ro của các hoá đơn ưu tiên bằng **0**; ví dụ này không đo hiệu quả toàn hệ thống. Mô phỏng chính sách thu nợ cho thay đổi DSO khoảng **−0,44/−0,28/−0,28 ngày** ở ba giả định phản hồi, nhưng các khoảng bất định đều chứa 0. Chưa chứng minh giảm thiếu tiền, tác động nhân quả hoặc lợi nhuận đầu tư.

## 4. Kết luận sử dụng

- **Pilot thật vẫn NO-GO.** Trong 18 cổng G1–G18: 9 đạt, 8 chưa đạt, 1 ngoài phạm vi giai đoạn synthetic. Dịch vụ local mặc định không mở dự báo thương mại.
- Điểm của T2 trên synthetic là kết quả cũ chưa xác nhận lại. Điểm T6 dùng ngày thu thật của máy phát không được lẫn với đánh giá E2E dùng ngày T9 ước lượng.
- Mỗi bộ synthetic kiểm tra một giả định cụ thể; các số không chứng minh mô hình sẽ đúng trên doanh nghiệp Việt Nam thật. Bước cần thiết tiếp theo là nạp dữ liệu thật có kiểm soát, chạy bóng nhiều tuần và so dự báo với tiền thực về.
