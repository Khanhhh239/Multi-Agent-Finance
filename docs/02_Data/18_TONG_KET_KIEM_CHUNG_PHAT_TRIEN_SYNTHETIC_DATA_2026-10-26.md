# Tổng kết và kiểm chứng máy phát dữ liệu synthetic — Agent 1

**Cập nhật 27/10/2026:** bộ cuối `v3_final_20261027` đã sinh 320 doanh nghiệp,
1.424.342 hóa đơn trong 8 World, khóa split, train và evaluate. **GO kỹ thuật
cho train synthetic theo giả định**, chưa xác nhận độ sát AR/AP với SME Việt Nam
vì không có ledger độc lập. Xem [báo cáo 23](23_BO_TRAIN_SYNTHETIC_CUOI_2026-10-27.md)
để dùng kết luận mới nhất. [Báo cáo 22](22_COHORT_SYNTHETIC_DA_KHOA_2026-10-27.md)
ghi cohort ứng viên đã kiểm trước khi sinh toàn bộ; các bảng dưới đây là lịch
sử kiểm chứng các phiên bản trước.

## 1. Cách đọc và phạm vi kiểm chứng

Một **World** là một lần mô phỏng hoàn chỉnh: có doanh nghiệp, khách hàng, hóa đơn, thanh toán, khoản chi, sao kê và các tuần thị trường biến động. **Seed** là số khởi tạo ngẫu nhiên; đổi seed cho một kết quả mô phỏng khác. **Hard case** là tình huống khó được tạo riêng để thử thuật toán. **Manifest** là bản kê cấu hình và mã kiểm tra SHA-256 của dữ liệu. **Censoring** nghĩa là đến ngày kết thúc quan sát vẫn chưa biết hóa đơn cuối cùng sẽ được trả hay xóa nợ; không được tự gọi nó là nợ xấu.

Một **episode** là một đợt sốc có ngày bắt đầu và thời gian hồi phục. **Train / validation / test** lần lượt là phần dữ liệu để học, để chọn mô hình và để đánh giá sau cùng; **held-out** nghĩa là giữ một kiểu episode ngoài phần train. **As-of** nghĩa là tại ngày dự báo chỉ dùng thông tin đã có vào ngày đó. **Credit note** là chứng từ giảm hoặc hủy số tiền hóa đơn; **write-off** là xóa khoản nợ không thu được.

Đợt rà soát này đọc mã, công thức kiểm toán và các CSV/JSON đã lưu. SHA-256 của **192/192 tệp Parquet trong 16 World** liên quan khớp manifest; hash của ba nguồn calibration, OxCGRT và WDI cũng khớp manifest v5. Việc khớp hash cho biết tệp chưa đổi so với lúc lập manifest. Nó **không** chứng minh dữ liệu giống giao dịch thật. Môi trường lệnh không có Python, nên các bài test và phép tính từ Parquet **chưa được chạy lại** trong đợt này; chỗ nào dùng kết quả test cũ sẽ ghi rõ [S4], [S8], [S13]–[S15].

## 2. Máy phát hiện làm gì?

Máy phát đi theo chuỗi sau [S1]–[S7]:

1. Tạo lịch tuần, môi trường chung và các cú sốc thị trường.
2. Tạo doanh nghiệp và nhóm khách hàng. Mỗi bên có mức chịu tác động riêng.
3. Mỗi tuần quyết định khách nào còn mua, người bán có giữ bán chịu hay không, có bao nhiêu đơn và hàng mua vào.
4. Tạo hóa đơn, các lần trả một phần hoặc trả đủ, lời hứa trả và giao dịch ngân hàng.
5. Tính lại công nợ, khoản chi, tồn kho và số dư của **một tài khoản ngân hàng vận hành**.

Bốn kênh sốc mới là **cầu** (đơn hàng), **cung** (khả năng giao hàng), **giá** và **tín dụng**. Chúng dùng chung lịch trong một World. Bảng shock_truth lưu diễn biến mà máy phát biết để kiểm toán; bảng này không được đưa thẳng vào đặc trưng dự báo. Một World tích hợp chứa cả tuần bình thường, tuần chịu sốc và giai đoạn hồi phục. Các hard case riêng vẫn chủ yếu thử từng tình huống một [S1], [S2], [S6].

## 3. Quá trình sửa theo phiên bản

| Giai đoạn | Điều đã xảy ra | Cách hiểu |
|---|---|---|
| Máy phát cũ, trước 25/10 | Phát hiện quyết định mua hàng/số dư/lời hứa biết trước tương lai; nhãn trả đủ và credit note có lỗi; cú sốc đến sau hạn khó đổi ngày trả. | Báo cáo 12 kiểm toán mã cũ. Parquet giao dịch của một số World cũ không còn để tính lại mọi số [S16]. |
| Kế hoạch 11 ngày 25/10 | Đề xuất các hình mẫu xuất khẩu 2008–09, lạm phát–tín dụng 2011–12, hạn mặn 2015–16 và năng lượng 2026. | Đây là **kế hoạch tham chiếu**, chưa phải bốn kịch bản lịch sử đã hiệu chỉnh và chạy trong máy phát [S18]. |
| v3, trước sửa vòng đời khách | Có thanh toán theo tuần, đối soát tiền, bốn kênh sốc, manifest và cổng train. Nhưng World không có episode sốc mới vẫn giảm mạnh doanh thu/khách. | Kết quả v3 giải thích vì sao phải sửa tiếp; không dùng làm số liệu của v5 [S13], [S17]. |
| v5 và hard case v9 | Thêm khách mới, rời đi, quay lại; có thể mở lại bán chịu sau 26 tuần nếu tín hiệu cho phép; sửa hai hard case heterogeneity và lumpy_customer. | Ba World v5 và hai hard case v9 có dữ liệu/manifest để kiểm [S3], [S6], [S14], [S15]. |
| v6 và pilot held-out | Thêm bảy seed đối chứng và thử hai kịch bản dành riêng cho test. | Pilot chỉ kiểm pipeline; chưa có model cuối hoặc đánh giá khả năng dự báo [S20]. |

## 4. Lỗi cũ đã được xử lý đến đâu?

**“Đã sửa”** dưới đây chỉ nói mã hiện tại có cơ chế sửa và có bằng chứng kiểm tra nội bộ. Nó không có nghĩa hành vi đã được đo đúng trên thị trường Việt Nam.

Để đọc nhanh bảng, xem cột **Trạng thái** trước. Cột **Mã chính** chỉ nơi kiểm tra cách sửa; đường dẫn đầy đủ và số dòng có ở mục 8.

| Lỗi cũ | Nguyên nhân | Cách sửa hiện tại | Mã chính | Bằng chứng | Trạng thái |
|---|---|---|---|---|---|
| Tiền mua hàng tuần này biết doanh thu hai tuần sau | Bản cũ dùng doanh thu của tuần t+2 | Mua theo đơn đã nhận và tồn kho hiện tại | decisions.py:8–39; world.py:831–879 | Test thay đơn tương lai mà mua hàng quá khứ không đổi; kiểm tồn kho [S7], [S8] | **Đã sửa lỗi nhìn trước.** Vẫn mua/giao trong cùng tuần, chưa có thời gian vận chuyển. |
| Tiền đầu kỳ phụ thuộc chi phí tương lai; sao kê không khớp số dư | Dùng trung bình chi cả kỳ và bỏ sót một số dòng tiền | Tiền đầu kỳ dựa trên quy mô ban đầu; các khoản vào sao kê được cộng vào tài khoản vận hành | world.py:838–843,1117–1168; accounting.py:9–27 | Test phản thực và hợp đồng đối soát sao kê–số dư [S7], [S8] | **Đã sửa trong phạm vi tài khoản này.** Chưa có sổ vay và tổng tiền toàn doanh nghiệp. |
| Lời hứa trả quá “biết trước” | Ngày hứa dựa vào ngày trả thật sau đó | Sinh lời hứa từ thông tin có tại ngày hứa; sau này mới chấm giữ lời | world.py:758–829 | Test đổi ngày trả tương lai không làm đổi lời hứa ban đầu [S8] | **Đã sửa đường rò rỉ trực tiếp.** Chưa kiểm độ tin cậy lời hứa bằng dữ liệu thật. |
| Hóa đơn còn thiếu tiền bị ghi là trả đủ; credit note và xóa nợ bị lẫn với tiền thu | Tin vào tên đợt trả “final” thay vì cộng tiền thực trả | Tính lại số dư và ngày trả đủ từ các khoản trả/điều chỉnh có ngày; phân biệt trả tiền, credit note, write-off | accounting.py:30–109 | Test kế toán và kiểm nhãn/số tiền/ngày [S5], [S7] | **Đã sửa bất biến nội bộ.** Chưa đối chiếu sổ kế toán thật. |
| Cú sốc sau hạn không tác động khoản nợ đang mở | Bản cũ rút ngày trả một lần tại ngày đến hạn | Khoản trễ còn mở được thử thanh toán lại mỗi tuần; tiền trả một phần cũng có đợt tiếp theo; cuối kỳ chưa rõ kết cục thì censored | decisions.py:169–220; world.py:550–651 | Test sốc sau hạn và test censor [S8] | **Sửa một phần.** Quyết định đúng hạn/trễ ban đầu vẫn rút tại hạn; hệ số trả tuần chưa hiệu chỉnh. |
| Khách vỡ nợ khiến doanh thu giảm kéo dài | Khách bị ngừng bán nhưng thiếu khách thay thế/quay lại | Có khách gia nhập, rời tạm, quay lại; giữ bán do default 26 tuần rồi xem lại tín hiệu tín dụng | decisions.py:42–166; world.py:407–455 | v3 giảm còn 0,338; v5 tăng lên 1,173/1,443 ở hai seed, seed còn lại 0,886 [S14] | **Đã bỏ xu hướng sụp đổ bắt buộc trong mẫu đã kiểm.** Xác suất các hành vi vẫn là giả định. |
| Khách hàng trả tiền quá giống nhau | Mức khác biệt giữa khách quá yếu | Tạo bốn nhóm thói quen trả khác nhau trước khi sinh hóa đơn | hard_cases.py:40–47; world.py:620–628 | Chỉ số nội bộ tăng từ 0,303 (v3) lên 0,614 (v9) [S15], [S19] | **Đạt dải thử nội bộ**, chưa có mốc Việt Nam. |
| Khách lớn được ép chiếm 40–60% doanh thu bằng cách nhìn cả kỳ | Hậu xử lý sau khi đã sinh hóa đơn | Chọn khách lớn và trọng số trước đơn đầu tiên | hard_cases.py:32–39 | 12/12 công ty v9 nằm trong dải 40–60% [S15] | **Đã bỏ cách nhìn doanh thu tương lai.** Kết quả không được bảo đảm cho mọi seed. |
| credit_note đứt chuỗi hóa đơn; supply_shock không thực sự giảm nguồn cung | Case cũ đổi mã thiếu hóa đơn gốc; chỉ sửa khả năng trả của khách | Giữ hóa đơn gốc đã hủy và tham chiếu từ hóa đơn thay thế; sốc cung đổi công suất/giá vốn trước khi sinh đơn | hard_cases.py:21–25,144–178 | 100% tham chiếu tìm được ở v3; ba công ty thép có tám tuần giảm công suất/tăng giá [S19] | **Đã sửa nghĩa cơ bản.** Khi tính doanh thu phải loại/bù hóa đơn hủy; chưa có chuỗi cung ứng thật. |
| Các cú sốc và hard case chưa nằm trong cùng một thế giới | Case cũ được sinh riêng, khách chủ yếu chịu sốc theo ngành bên bán | Bốn kênh sốc dùng lịch chung, khách và người bán có mức phơi nhiễm riêng | shocks.py:14–66; world.py:264–515 | Test bốn kênh trong một World, đối chứng trước/sau sốc [S2], [S8], [S17] | **Đã tích hợp cơ chế chính.** Chưa có mạng mua bán, tỉnh nguồn hàng hoặc mọi tổ hợp hard case. |
| Feature/train có thể lộ kết quả tương lai; thiếu manifest và split cố định | Cột cấm kiểu danh sách, script cũ gắn tên World | Chỉ cho phép cột feature đã duyệt, cắt dữ liệu tại ngày dự báo; hash World và khóa vai trò train/validation/test | features.py:44–118; world_manifest.py:36–182; build_final_train.py:21–199 | Test cột ẩn, thời điểm công bố, sửa manifest và shock lọt train [S9]–[S11] | **Có cổng kỹ thuật.** Macro as-of chưa là feature T1 mặc định; chưa có cohort final. |
| Chưa biết phân phối có giống SME Việt Nam không | Tham số phần lớn là giả định hoặc neo theo khảo sát khác mẫu | Mới lập kế hoạch hiệu chỉnh và kiểm số theo năm/ngành/seed | audit_existing_world_metrics.py:27–95 | Bảng v5 và 10 seed là kiểm nội bộ [S12], [S14], [S18] | **Chưa giải quyết.** |

## 5. Các con số nói gì?

### 5.1. Doanh thu và số khách trước/sau sửa

**Doanh thu 2025/2019** lấy tổng doanh thu hóa đơn thuần phát hành năm 2025 chia cho năm 2019. Ví dụ 0,338 nghĩa là năm 2025 chỉ bằng **33,8%** năm 2019; 1,173 nghĩa là **cao hơn 17,3%**. “Số khách” là số khách có ít nhất một hóa đơn trong năm. Mỗi World đối chứng có 24 doanh nghiệp và quan sát 2019–2025 [S13].

| Phiên bản và seed | Doanh thu 2025/2019 | Khách có hóa đơn 2019 → 2025 | Ghi chú |
|---|---:|---:|---|
| v3, 94317 | **0,338** | **752 → 294** | Không có episode sốc mới, đã dùng nguồn OxCGRT/WDI có hash; **trước sửa vòng đời**. |
| v5, 94317 | **1,173** | **1.017 → 958** | Sau sửa vòng đời, không episode mới. |
| v5, 94318 | **1,443** | **1.215 → 1.277** | Cùng cấu hình, seed khác. |
| v5, 94319 | **0,886** | **1.109 → 889** | Vẫn giảm, cần kiểm riêng. |

Bản v3 dùng nguồn vĩ mô dự phòng có tỷ số **0,322**, khách **752 → 312**; đó là một World khác, không gộp với dòng v3 ở bảng. Bản v3 tích hợp bốn episode có **34.490 hóa đơn**, tỷ lệ bán chịu cả kỳ **73,46%**, **38,77%** ngày tài khoản vận hành âm và **20,61%** giá trị hóa đơn bán chịu năm 2025 chưa biết kết cục cuối kỳ. Đây cũng là số **v3**, không phải v5 [S13], [S17].

Hard case v9 cho chỉ số khác biệt thời gian trả giữa khách **0,614**, so với **0,303** ở v3. Chỉ số này tính trên hóa đơn **đã trả đủ**, theo công thức trong script; dải 0,55–0,65 là mục tiêu thử nội bộ, không phải thống kê Việt Nam. Trong case khách lớn, **12/12 công ty** có khách chính chiếm 40–60% giá trị hóa đơn; phần nhỏ nhất/trung vị/lớn nhất là **44,09% / 47,82% / 58,32%** [S6], [S15], [S19].

### 5.2. Mười seed và trường hợp 94319

Mười World không có episode mới gồm **ba World v5** (94317–94319) và **bảy World v6** (94320–94326). Cấu hình chỉ khác tên/seed, ba nguồn đầu vào có cùng hash. Tuy nhiên, hash của **toàn bộ mã Python** khác giữa hai đợt, nên chưa xem đây là một bộ phát hành mã bất biến chung [S14], [S20].

- **1/10** World có doanh thu 2025 thấp hơn 2019; **0/10** thấp hơn mốc 0,6 của cổng phát hiện sụp đổ.
- **4/10** có ít khách phát sinh hóa đơn hơn năm 2019; **4/10** có doanh thu 2025 thấp hơn 2024.
- Tỷ số doanh thu 2025/2019 nhỏ nhất, trung vị, lớn nhất là **0,886 / 1,579 / 1,886**. Mười seed chưa đủ để ước xác suất sụt giảm trên thị trường.

Seed **94319** đặc biệt đáng kiểm tra: doanh thu 2025 chỉ bằng **39,5%** năm 2024. CSV năm/ngành cho thấy cả **6 ngành** đều giảm, với tỷ số khoảng **0,33–0,43**; mỗi ngành chỉ có 2–5 công ty. Báo cáo 17 còn ghi trung vị tỷ số theo công ty khoảng 0,424 và nhân tố thị trường chung năm 2025 là −1,114; hai con số cuối **chưa tính lại trực tiếp từ Parquet** trong lượt rà soát này. Hiện chưa đủ bằng chứng để gọi đó là lỗi cấu trúc hay một kịch bản biến động hợp lý. Cần giữ nguyên công ty/khách rồi đổi riêng đường nhân tố chung, và xem kết quả theo từng công ty/tuần [S1], [S15], [S20].

### 5.3. Tình hình bán chịu, thu nợ và tiền mặt năm 2025

Bảng này chỉ dùng **ba World v5 không có episode sốc mới**. “Bán chịu” là **giá trị** hóa đơn có kỳ hạn trên tổng giá trị hóa đơn phát hành năm 2025. “Kỳ hạn” là bình quân theo giá trị của nhóm bán chịu. “Thu đủ P50” là số ngày **trung vị** từ lập hóa đơn đến nhận đủ tiền của các hóa đơn bán chịu **đã tất toán trong năm**; khoản còn mở không nằm trong mẫu này. “Nợ quá hạn” là **số dư đã quá hạn tại 31/12/2025** chia cho toàn bộ công nợ còn mở cùng ngày. “Ngày tài khoản âm” tính theo ngày × doanh nghiệp của tài khoản vận hành mô phỏng. P90 là mốc mà 90% quan sát nằm dưới hoặc bằng; P90 tuổi nợ ở dưới được tính theo trọng số số dư [S12], [S15].

| Seed v5 | Bán chịu theo giá trị | Kỳ hạn bình quân | Thu đủ P50 | Nợ quá hạn / công nợ mở | Ngày tài khoản âm |
|---|---:|---:|---:|---:|---:|
| 94317 | 71,4% | 42,8 ngày | 42 ngày | 33,6% | 19,3% |
| 94318 | 67,7% | 45,3 ngày | 43 ngày | 41,1% | 6,6% |
| 94319 | 68,5% | 37,9 ngày | 44 ngày | 55,6% | 13,6% |

Trong hóa đơn đã thu đủ trong năm, tỷ lệ **giá trị trả trễ** lần lượt là **37,1% / 40,5% / 48,5%**. P90 tuổi nợ quá hạn, có trọng số theo số dư, là **259 / 234 / 424 ngày**. Ở mức ngành, mỗi seed chỉ có khoảng 2–5 doanh nghiệp/ngành; các phân vị theo ngành vì thế dễ dao động [S12], [S15].

Khảo sát Atradius Việt Nam 2025 nêu **65%** doanh số B2B bán chịu và kỳ hạn bình quân **45 ngày**, nhưng chỉ phỏng vấn **300 người thuộc ba ngành thép, dệt may, nhựa/cao su** trong nửa cuối quý II. Khảo sát không cung cấp cùng mẫu hóa đơn, ngày chốt và cách tính nợ quá hạn như bảng v5. Sự gần nhau về vài con số **chưa xác nhận dữ liệu synthetic đại diện cho SME Việt Nam**. Cuối 2025, **21,5–26,2% giá trị hóa đơn bán chịu phát hành trong năm** ở ba World v5 vẫn chưa có kết cục cuối cùng; nhóm đó không được tự coi là nợ xấu hoặc là đã trả đúng hạn [S13]–[S15], [S18].

## 6. Các cú sốc thị trường đã được thử ra sao?

| Giai đoạn | Thiết kế thực tế | Giới hạn |
|---|---|---|
| Máy phát cũ | Có đường COVID và căng tín dụng 2022–2023; các hard case tách riêng. | Sốc đến sau hạn khó tác động khoản còn mở; case “đứt cung” cũ chưa làm giảm hàng có thể bán [S16]. |
| v3 tích hợp | Bốn kênh cầu/cung/giá/tín dụng cùng đi qua một World, với mức chịu sốc riêng của khách và người bán. | Cường độ, thời gian và mức truyền sang thanh toán là **giả định synthetic**, chưa rút từ vi dữ liệu Việt Nam [S1], [S2], [S17]. |
| Pilot dành riêng cho test | Train/validation có episode cầu, cung, giá. Test A chỉ có episode siết tín dụng; Test B ghép tăng giá với siết tín dụng. | Đây là kiểm tra tách kịch bản trong pipeline, chưa đo model dự báo tốt hơn [S10], [S20]. |

Báo cáo 14 so một World v3 có sốc với World cùng seed không có episode mới. Trong 13 tuần sốc hoạt động, tỷ số **đơn đã nhận** theo thứ tự cầu/cung/giá/tín dụng là **0,563 / 0,657 / 1,000 / 0,510** so với đối chứng; tỷ số **mua vào** là **0,539 / 0,738 / 1,339 / 0,454**. Điều này cho thấy mã có phản ứng theo bốn kênh. Các tỷ số **không phải** mức tác động từng xảy ra ở Việt Nam [S17].

Hai lịch test được ghi cụ thể trong runner: **Test A** tín dụng, tăng 1 tuần, giữ đỉnh 6 tuần, hồi 9 tuần, mức 1,3; **Test B** giá + tín dụng, tăng 3 tuần, giữ đỉnh 4 tuần, hồi 10 tuần, mức 0,9 và 1,1. Pilot chỉ gồm **1 World train, 1 validation, 2 test; 2 công ty/World; giai đoạn 2023–2024**. Cổng kỹ thuật báo PASS, có 10 và 6 tuần tín dụng hoạt động trong cửa sổ đánh giá. Nhưng pilot **không bao phủ 2019–2025**, chưa kiểm phân phối đủ kỳ và chưa có tệp đánh giá model [S10], [S20].

Mức “giữ riêng” hiện áp dụng cho **episode tín dụng mới**. Train vẫn có đường căng tín dụng nền 2022–2023; Test B còn dùng lại họ tín dụng của Test A. Vì vậy hai test này chưa chứng minh khả năng xử lý một loại khủng hoảng hoàn toàn chưa từng thấy. Kế hoạch 11 về các sự kiện xuất khẩu 2008–09, lạm phát 2011–12, hạn mặn 2015–16 và năng lượng 2026 vẫn là **nguồn tham chiếu để thiết kế**, chưa được mã hóa thành bốn template đã hiệu chỉnh. Mã cũng chưa có tỉnh nguồn hàng, tỷ trọng xuất khẩu hay mạng giao dịch giữa doanh nghiệp; vùng 1–4 hiện là **vùng lương**, không phải bản đồ thiên tai. Lãi vay nền lấy suất của năm đầu mô phỏng rồi điều chỉnh khoản trả theo stress tín dụng, chưa mô phỏng đầy đủ dư nợ và lãi thả nổi [S1], [S10], [S18].

## 7. Nguồn tham chiếu trong repository (số dòng tại thời điểm rà soát)

| Mã | File và dòng thực tế | Dùng để xác minh |
|---|---|---|
| S1 | [`agent1/synth/world.py`](../../agent1/synth/world.py):294–310, 377–405, 407–455, 457–651, 758–929, 959–1002, 1117–1169 | Macro, phơi nhiễm, vòng đời, hóa đơn, thanh toán, lời hứa, mua hàng, số dư. |
| S2 | [`agent1/synth/shocks.py`](../../agent1/synth/shocks.py):14–66 | Bốn họ, đường episode và exposure. |
| S3 | [`agent1/synth/decisions.py`](../../agent1/synth/decisions.py):8–39, 42–166, 169–220 | Mua hàng, giữ tín dụng, khách hoạt động, default kế tiếp, hazard tuần. |
| S4 | [`agent1/data/world_manifest.py`](../../agent1/data/world_manifest.py):14–20, 36–59, 62–116, 119–182 | Hash nguồn/code, 12 bảng, manifest/cohort. |
| S5 | [`agent1/data/accounting.py`](../../agent1/data/accounting.py):9–27, 30–109 | Nhãn kế toán, censoring và phân loại sao kê. |
| S6 | [`agent1/synth/hard_cases.py`](../../agent1/synth/hard_cases.py):21–47, 144–179 | Hard case lumpy/heterogeneity/credit note/supply. |
| S7 | [`agent1/data/contracts.py`](../../agent1/data/contracts.py):12–36, 169–217, 220–283 | Schema và đối soát hợp đồng dữ liệu. |
| S8 | [`tests/test_synthetic_causality.py`](../../tests/test_synthetic_causality.py):11–195; [`tests/test_synthetic_accounting.py`](../../tests/test_synthetic_accounting.py):8–82; [`tests/test_hard_case_semantics.py`](../../tests/test_hard_case_semantics.py):10–82; [`tests/test_shock_episodes.py`](../../tests/test_shock_episodes.py):13–89 | Bằng chứng kiểm thử có trong code; **không chạy lại lượt này**. |
| S9 | [`agent1/models/features.py`](../../agent1/models/features.py):44–118, 127–164; [`tests/test_features.py`](../../tests/test_features.py):82–127 | Feature allowlist, snapshot và publication gate. |
| S10 | [`scripts/build_final_train.py`](../../scripts/build_final_train.py):21–120, 138–201; [`scripts/train_manifest.py`](../../scripts/train_manifest.py):20–119; [`tests/test_final_pipeline.py`](../../tests/test_final_pipeline.py):34–154 | Held-out, cổng readiness, split, T1 train/eval, các ca test. |
| S11 | [`scripts/world_registry.py`](../../scripts/world_registry.py):13–40 | Registry kiểm bảng, contract và manifest. |
| S12 | [`scripts/audit_existing_world_metrics.py`](../../scripts/audit_existing_world_metrics.py):27–95; [`outputs/data/v5_existing_world_metrics_20261026.csv`](../../outputs/data/v5_existing_world_metrics_20261026.csv):2–148 | Công thức và bảng năm/ngành; 147 hàng dữ liệu. |
| S13 | [`scripts/audit_train_readiness.py`](../../scripts/audit_train_readiness.py):21–69; [`outputs/data/v3_readiness_public_macro_20261026.json`](../../outputs/data/v3_readiness_public_macro_20261026.json); [`outputs/data/v3_readiness_20261026.json`](../../outputs/data/v3_readiness_20261026.json) | Mẫu số xu hướng, v3 public/fallback và tích hợp. JSON dùng khóa đối tượng, không gán số dòng bất ổn. |
| S14 | [`outputs/data/v5_lifecycle_audit_20261026.json`](../../outputs/data/v5_lifecycle_audit_20261026.json); [`outputs/data/v6_lifecycle_audit_20261026.json`](../../outputs/data/v6_lifecycle_audit_20261026.json); [`outputs/data/v6_multiseed_trend_20261026.csv`](../../outputs/data/v6_multiseed_trend_20261026.csv):2–11 | Ba + bảy seed, nguồn metric theo năm. |
| S15 | [`scripts/audit_lifecycle_fix.py`](../../scripts/audit_lifecycle_fix.py):42–83; [`outputs/data/v9_lifecycle_audit_20261026.json`](../../outputs/data/v9_lifecycle_audit_20261026.json); [`docs/02_Data/15_SUA_VONG_DOI_KHACH_VA_HARD_CASE_2026-10-26.md`](15_SUA_VONG_DOI_KHACH_VA_HARD_CASE_2026-10-26.md):5–37; [`docs/02_Data/16_KIEM_TOAN_CHI_SO_V5_TU_DU_LIEU_HIEN_CO_2026-10-26.md`](16_KIEM_TOAN_CHI_SO_V5_TU_DU_LIEU_HIEN_CO_2026-10-26.md):3–45 | Hard case v9, cách đo và giới hạn audit v5. |
| S16 | [`docs/02_Data/12_KIEM_TOAN_KICH_BAN_SINH_DU_LIEU_CU_2026-10-25.md`](12_KIEM_TOAN_KICH_BAN_SINH_DU_LIEU_CU_2026-10-25.md):5–93; [`docs/04_AI_Methods/T0_T10_PHUONG_PHAP_VA_KET_QUA_SYNTHETIC_2026-10-25.md`](../04_AI_Methods/T0_T10_PHUONG_PHAP_VA_KET_QUA_SYNTHETIC_2026-10-25.md):56–72 | Lỗi và benchmark lịch sử, không dùng làm kết quả World mới. |
| S17 | [`docs/02_Data/14_KIEM_TOAN_SAU_SUA_VA_QUYET_DINH_TRAIN_2026-10-26.md`](14_KIEM_TOAN_SAU_SUA_VA_QUYET_DINH_TRAIN_2026-10-26.md):7–75 | Kiểm toán v3 trước sửa vòng đời, sốc và hard case. |
| S18 | [`docs/02_Data/11_KE_HOACH_SOC_THI_TRUONG_TICH_HOP_2026-10-25.md`](11_KE_HOACH_SOC_THI_TRUONG_TICH_HOP_2026-10-25.md):3–18, 90–119, 123–153 | Kế hoạch nguồn Việt Nam, template, tiêu chí thực tế và giới hạn. |
| S19 | [`outputs/data/hard_case_fidelity_v3_full.csv`](../../outputs/data/hard_case_fidelity_v3_full.csv):2–20; [`outputs/data/hard_cases_v3.csv`](../../outputs/data/hard_cases_v3.csv):2–13; [`docs/02_Data/14_KIEM_TOAN_SAU_SUA_VA_QUYET_DINH_TRAIN_2026-10-26.md`](14_KIEM_TOAN_SAU_SUA_VA_QUYET_DINH_TRAIN_2026-10-26.md):36–75 | Điểm v3 và hạn chế đã báo cáo. |
| S20 | [`outputs/data/v3_heldout_pilot_20261026/readiness.json`](../../outputs/data/v3_heldout_pilot_20261026/readiness.json); [`data/synthetic/v3_heldout_pilot_20261026_cohort.json`](../../data/synthetic/v3_heldout_pilot_20261026_cohort.json); [`docs/02_Data/17_HELDOUT_SHOCK_VA_KIEM_TRA_NHIEU_SEED_2026-10-26.md`](17_HELDOUT_SHOCK_VA_KIEM_TRA_NHIEU_SEED_2026-10-26.md):3–37 | Pilot held-out, 10 seed và cảnh báo 94319. |

**Cách đọc đường dẫn dữ liệu:** CSV có số dòng vật lý (header ở dòng 1); JSON và Parquet được tham chiếu theo tên tệp/khóa vì số dòng JSON có thể đổi khi định dạng lại và Parquet không có dòng văn bản. Các số dòng mã/tài liệu nêu trên là vị trí thực tế của working tree khi lập báo cáo.
