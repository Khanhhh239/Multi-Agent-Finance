# Agent 1: Khanh đã cải tiến gì so với Thắng?

> **Phạm vi lịch sử:** báo cáo dưới đây đối chiếu hai commit ngày 17/10/2026. Checkout đang sắp xếp thuộc nhánh `agent1-Thắng`; mã, dữ liệu và các tài liệu của nhánh `agent1-Khanh` được nhắc tới không mặc định có tại đây. Đường dẫn trong lệnh Git và mô tả cây file tại hai commit giữ nguyên để tra cứu lịch sử. Xem [hướng dẫn checkout này](../getting-started.md) và [bảng đổi đường dẫn](../reference/repository-structure.md).

Ngày đối chiếu: **17/10/2026**. Báo cáo dựa trên mã, tài liệu và kết quả CSV đang có trong repository; không chạy lại huấn luyện hoặc tải thêm dữ liệu.

Trong checkout hiện tại, bộ `notebooks/` được nhắc theo tên lịch sử bên dưới đã chuyển sang [reference_notebooks/](../../reference_notebooks/README.md), chỉ dùng tham khảo khi xây code T1 mới.

## 1. Phạm vi và kết luận chính

Tên “agent-Thắng” trong yêu cầu được hiểu là nhánh **`agent1-Thắng`**. Hai phiên bản được so sánh:

| Phiên bản | Commit | Nội dung commit |
|---|---|---|
| `agent1-Thắng` | `9457777` | `some stuff` |
| `agent1-Khanh` | `618e7cc` | `Agent 1 (dong tien): code, du lieu tong hop VN, ket qua do va bo tai lieu 5 phan` |

Hai nhánh cùng xuất phát từ `add038a` và mỗi nhánh có một commit riêng sau mốc này. Vì vậy, đây là **so sánh hai phiên bản song song**, không phải lịch sử Khanh sửa tuần tự trên commit của Thắng. Không thể quy toàn bộ khác biệt thành đóng góp cá nhân chỉ từ tên nhánh.

**Thay đổi lớn nhất:** bản Thắng có hệ thống notebook thử nghiệm và thiết kế Cash Forecast tương đối sâu; bản Khanh xây thêm package Python theo module, bộ sinh dữ liệu SME Việt Nam, thí nghiệm trên nhiều miền và bộ tài liệu phục vụ cả nghiên cứu lẫn phát triển sản phẩm.

**Chưa đủ bằng chứng để nói “Khanh dự báo chính xác hơn Thắng X%”.** Các kết quả hiện có không phải phép thử hai nhánh trên cùng dữ liệu, cùng điểm cắt và cùng giao thức đánh giá. Cải tiến rõ nhất là phạm vi triển khai, khả năng tái lập và cách tổ chức bằng chứng.

## 2. Những phần Thắng đã có sẵn

Không nên xem toàn bộ kỹ thuật ở bản Khanh là ý tưởng mới. Nhánh Thắng đã có:

- Notebook `01`–`12`, cùng `invoice_forecast.ipynb`, bao gồm EDA, baseline, LightGBM, calibration, Monte Carlo, stress test, evaluation, survival, collection và dashboard thử nghiệm.
- LightGBM phân vị, CQR/Mondrian, survival, thử nghiệm OOF và Survival-Boost; có mã `.py` cho notebook mở rộng.
- Thiết kế snapshot as-of chống rò rỉ, mô phỏng có phụ thuộc, cảnh báo regime và cổng GO/NO-GO.
- Tài liệu kiến trúc T0 và nghiên cứu T2/T3/T5/T8, mô tả reconciliation, nghĩa vụ chi, xác suất không trả và lời hứa trả.
- Báo cáo cả kết quả bất lợi: trong `method/AGENT1_TONG_HOP.md` ở nhánh Thắng, cash wMAPE của LightGBM+CQR+MC là **23,21%**, kém B1 điểm **10,46%**; CRPS **0,1431**, kém B1+bootstrap **0,1293**. Việc công bố mô hình chưa thắng ở cấp dòng tiền đã có từ bản này.

Các file trên được đọc từ Git của `agent1-Thắng`; nhiều file không còn nằm trong cây mã được theo dõi của nhánh hiện tại.

## 3. Các cải tiến và phần bổ sung ở bản Khanh

| Hạng mục | Bản Thắng | Bản Khanh bổ sung/thay đổi | Ý nghĩa và giới hạn |
|---|---|---|---|
| **Tổ chức mã** | Chủ yếu notebook và thư viện hỗ trợ notebook | Package `agent1/`, tách `data`, `models`, `synth`, `eval`, `text`; có script chạy từng nhóm thí nghiệm | Thuận tiện tái sử dụng và kiểm tra từng module; chưa đồng nghĩa đã thành ứng dụng hoàn chỉnh |
| **Dữ liệu và nguồn** | Có danh mục nguồn và dữ liệu phục vụ notebook | Có script tải dữ liệu, loader, data card và manifest cho 8 nguồn; thêm bộ sinh synthetic nhiều bảng | T1/T2/T4 có kết quả trên dữ liệu ngoài bộ sinh; T3/T6/T7/T8/T9 chủ yếu đo trên synthetic. Chi tiết nguồn chính thức, bản sao và vai trò từng T ở mục 5.1; dữ liệu lớn không có đầy đủ trong checkout hiện tại |
| **T12 — sinh dữ liệu** | T12 nằm trong backlog ở bản tổng hợp trạng thái | Bộ sinh nhiều bảng, bốn miền `src`, `tgt`, `sens_uk`, `sens_coface`; cấu hình và báo cáo fidelity | Có nhãn để đo các tình huống khó; dữ liệu tổng hợp vẫn phụ thuộc giả định |
| **Bối cảnh Việt Nam** | Đã có thiết kế và đặc trưng lịch VN | Mã hóa lịch, kỳ nghĩa vụ chi, tên/MST, mẫu nội dung chuyển khoản, XML hóa đơn; mô phỏng Tết, ghi sổ theo lô, FIFO sai, thanh toán gộp | Mở rộng khả năng thử nghiệm nghiệp vụ; không thay thế kiểm định với doanh nghiệp thật |
| **T0 — chất lượng dữ liệu** | Kiến trúc Medallion, ERD, as-of đã được thiết kế | `schema.py`, hợp đồng 10 bảng, kiểm tra khóa/tham chiếu/tiền/số dư, chặn cột đặc trưng bị cấm | Có mã kiểm tra cụ thể; không có nghĩa toàn bộ Bronze/Silver/Gold và kết nối ERP đã hoàn tất |
| **T1 — thời điểm trả** | LightGBM phân vị, CQR và survival/ensemble trong notebook | Đối chứng có hệ thống B0/B1/B1d, HazardGBM, HazardLR, QuantileLGBM, XGB-AFT và ensemble; rolling-origin và dữ liệu thật | Dễ so nhiều lựa chọn; survival là hướng đã có ở bản Thắng |
| **T2 — có trả không** | Nghiên cứu hazard/default và kế hoạch triển khai | Có `CureGBM`, script T2 và CSV đánh giá trên tổng hợp/SBA | Tiến từ thiết kế sang thí nghiệm; nhãn SBA `EXEMPT` vẫn cần xử lý |
| **T3 — tranh chấp/trả một phần** | Có nghiên cứu và thiết kế | Có thí nghiệm đối chiếu lịch sử khách với LightGBM | Kết quả hiện có ủng hộ phương pháp đơn giản hơn; chưa phải bộ phân loại tranh chấp hoàn chỉnh cho dữ liệu thực tế |
| **T4 — doanh thu mới** | Để trong backlog | Có mô hình doanh thu tuần, baseline, Chronos, đánh giá trên tổng hợp và Online Retail II | Bổ sung nguồn tiền từ doanh thu tương lai thay vì chỉ công nợ đang mở |
| **T5 — nghĩa vụ chi** | Đã thiết kế rule engine và lịch hạn | Có `calendar_vn.py`, `obligation_schedule` và kiểm thử ngày hạn | Chuyển một phần thiết kế thành mã; quy tắc pháp lý trong repo chưa được xác minh lại trong báo cáo này |
| **T6 — mô phỏng số dư** | Đã có Monte Carlo, phụ thuộc và stress test | Có module riêng, copula Student-t, ACI hiệu chỉnh khoảng và nhiều đối chứng | Bổ sung thí nghiệm hiệu chỉnh độ phủ; còn thiếu đo cảnh báo sớm và báo giả |
| **T7 — điểm gãy** | Đã có phân tích regime và thiết kế detector | Module CUSUM, Page–Hinkley, BOCPD; thêm đồng thuận detector và điều khiển regime | Có mã và CSV; mức báo giả vẫn chưa đạt trọn tiêu chí |
| **T8 — lời hứa trả** | Thiết kế Beta–Binomial, 5 chiều, trọng số gần đây | Có `PromiseReliability`, chỉ dùng lời hứa đủ điều kiện xác minh tại cutoff; có thống kê độ tin cậy, trễ và độ nhạy số tiền | Cụ thể hóa thiết kế sẵn có; chưa thấy bằng chứng luồng thu thập lời hứa từ Zalo/email đã hoàn chỉnh |
| **T9 — đối soát** | Có thiết kế nhiều tầng, T9 nằm trong backlog ở bản trạng thái | Có ML reconciler; thêm pipeline quy tắc → ML/subset → hàng chờ xử lý; tạo ngày trả ước lượng từ phân bổ tiền | Có triển khai và đánh giá; số CSV hiện có thuộc ML reconciler, chưa chứng minh pipeline lai đã đạt chuẩn |
| **T10 — giải thích/hành động** | Đã có notebook collection/dashboard và thiết kế SHAP | Có module đóng góp đặc trưng, xếp hạng theo thay đổi rủi ro thiếu hụt, what-if, thư viện stress và kiểm tra số trong diễn giải | Có hàm và kiểm thử; demo đầu ra hiện tại vẫn lỗi, chưa có bằng chứng sản phẩm đầu cuối hoàn chỉnh |
| **Tái lập và kiểm thử** | Có notebook lưu đầu ra, mã `.py` mở rộng | `requirements*.txt`, script PowerShell, giới hạn luồng, snapshot cache có dấu vết và bộ `tests/` chia theo chức năng | Có nền tảng tái chạy tốt hơn; báo cáo này không xác nhận toàn bộ test đang pass trên máy hiện tại |

Nguồn mã chính: agent1/ (`agent1`, nhánh `agent1-Khanh`), scripts/ (`scripts`, nhánh `agent1-Khanh`), tests/ (`tests`, nhánh `agent1-Khanh`). Bản đồ chi tiết: hiện trạng và quy ước (`docs/05_Coding_Agent_Plan/01_hien_trang_va_quy_uoc.md`, nhánh `agent1-Khanh`).

### Các sửa đổi về chống rò rỉ và cách đo

Nhật ký triển khai (`docs/05_Coding_Agent_Plan/TIEN_DO_TRIEN_KHAI.md`, nhánh `agent1-Khanh`) ghi nhận các vấn đề được phát hiện và sửa trong quá trình xây bản Khanh:

1. **Trung vị tiền dùng dữ liệu tương lai:** chuyển sang hóa đơn đã biết tại từng cutoff và cửa sổ onboarding.
2. **Cửa sổ train và calibration chưa tách đúng:** tách train trước cửa sổ calibration; thêm baseline phân vị khách theo lịch sử as-of.
3. **Phân phối của ensemble/CQR không khớp phân vị đã thay đổi:** tính lại CDF từ phân vị thực tế; thêm lưới 9 phân vị và nội suy PCHIP cho QLGBM.
4. **Kiểm tra dữ liệu và cache:** bổ sung hợp đồng bảng, kiểm tra đặc trưng bị cấm, cache có dấu vết nguồn/tham số/mã.

Đây là các sửa đổi được ghi nhận **trong bản Khanh**, không phải bằng chứng mọi lỗi trên đều tồn tại ở mã Thắng. CSV cũ chưa được tự động xem là hợp lệ sau khi thay cách đo.

## 4. Kết quả hiện có: tiến bộ đến đâu?

**Các số dưới đây là kết quả lưu trong repo của bản Khanh, so với baseline trong từng thí nghiệm. Chúng không đo mức tăng so với nhánh Thắng.** Tài liệu hiện tại cảnh báo các bảng A/B/E–F/T6 được tạo trước sửa giao thức as-of/CDF; không dùng chúng làm bằng chứng nghiệm thu mới cho mã đã sửa.

| Bài toán | Kết quả được lưu | Cách hiểu đúng |
|---|---|---|
| **T1, tổng hợp `src`, gốc 2024-07-01** | DH-GBM: WAPE thu tuần 1–4 **0,403** so với B1 **1,080**; pinball **4,922** so với **17,026** | Tín hiệu tốt trên bộ tổng hợp ở lần đo cũ; cần chạy lại theo giao thức đã sửa |
| **T1, Customer Invoices** | Ensemble: MAE **2,29 ngày** so với B1 **2,77 ngày**; cov80 **83,7%** | MAE giảm khoảng **17,4%** so với baseline; dữ liệu AR tương tự, chưa phải hóa đơn SME Việt Nam |
| **T1, BPI 2019** | Ensemble pinball khoảng **5,10**, baseline B1d khoảng **5,07** | Chưa thắng baseline phân vị khách; không thể kết luận mô hình mạnh trên mọi miền |
| **T2, SBA** | Báo cáo ghi PR-AUC **0,214**, khoảng **15,7 lần** tỷ lệ nền | Có tín hiệu trên dữ liệu vay thật; vẫn phải xử lý `EXEMPT`, hiệu chỉnh theo năm và khả năng chuyển sang công nợ hóa đơn |
| **T4** | LGBM+CQR giảm SPL khoảng **10%** so với TB13 ở `tgt`; Chronos-Bolt tốt nhất trên Online Retail II | Bổ sung bài toán và đối chứng; mô hình riêng chưa luôn thắng trên dữ liệu thật |
| **T6, tổng hợp** | Copula-t+ACI: cov80 **79,4%** ở tuần 1–4 và **80,6%** ở tuần 5–13 | Độ phủ gần mục tiêu; IS80 dài hạn vẫn kém MC độc lập, chưa đo đủ giá trị cảnh báo sớm |
| **T7** | CUSUM phát hiện **52,4%** điểm gãy, báo giả **0,63/khách-năm** | Phát hiện đạt mức đề xuất nhưng báo giả vượt ngưỡng **0,5** |
| **T8** | MAE trên hóa đơn có lời hứa giảm **7,2%** | Chưa đạt cổng yêu cầu giảm ít nhất **10%** |
| **T9, ML reconciler** | F1 **0,689** so với quy tắc số tiền **0,632**; MAE ngày trả **1,97 ngày** so với ngày ghi sổ **12,59 ngày** | Cải thiện F1 và ngày trả; precision **78,1%**, thấp hơn quy tắc khoảng **98,9%**, chưa phù hợp tự động nhận toàn bộ liên kết |
| **Hợp đồng dữ liệu** | CSV WP0 ghi **68/68** kiểm tra đạt ở mỗi thế giới, tổng **272/272** | Bằng chứng kiểm tra đã lưu; chưa phải kết quả chạy lại trong lần lập báo cáo này |

Nguồn trực tiếp: T1-A (`outputs/t1/A_rolling_origin_src.csv`, nhánh `agent1-Khanh`), T1 dữ liệu thật (`outputs/t1/C_real_domains.csv`, nhánh `agent1-Khanh`), T6 (`outputs/t6/t6_interval_metrics.csv`, nhánh `agent1-Khanh`), T9 (`outputs/t9/t9_reconciliation_tgt.csv`, nhánh `agent1-Khanh`), hợp đồng dữ liệu (`outputs/wp0/world_contract_summary.csv`, nhánh `agent1-Khanh`). Diễn giải và các số còn lại: kết quả hiện có (`docs/03_Evaluation/04_ket_qua_hien_co.md`, nhánh `agent1-Khanh`), cổng nghiệm thu (`docs/03_Evaluation/03_cong_nghiem_thu.md`, nhánh `agent1-Khanh`).

## 5. Những thay đổi khác ngoài mô hình AI

### 5.1 Bộ dữ liệu và hồ sơ nguồn

#### Phân biệt nguồn gốc và cách thu thập

**“Nguồn chính gốc”, “crawl” và “synthetic” không phải ba nhóm loại trừ nhau.** Một bộ dữ liệu thật từ nguồn chính thức vẫn có thể được tải bằng crawler.

- **Nguồn gốc:** cơ quan/nhóm công bố hoặc nơi phân phối chính thức, hay bản sao của bên thứ ba.
- **Cách lấy:** tải CSV/ZIP/XES qua HTTP, gọi API, hoặc nhập tham số tham khảo vào cấu hình. `crawl.py` chủ yếu tự động tải file và gọi API; không phải mọi nguồn đều được cào từ HTML.
- **Bản chất dữ liệu:** bản ghi quan sát/thống kê công bố, hoặc bản ghi synthetic do chương trình tạo ra. Synthetic được hiệu chỉnh bằng thống kê thật vẫn là synthetic.

#### Tám nguồn có hồ sơ tải trong repo

Bảng dưới đối chiếu script tải (`scripts/crawl.py`, nhánh `agent1-Khanh`), manifest đã lưu (`docs/02_Data/MANIFEST.json`, nhánh `agent1-Khanh`), loader (`agent1/data/real_loaders.py`, nhánh `agent1-Khanh`) và các script thí nghiệm. Manifest ghi tên file, thời điểm tải, dung lượng và SHA-256; không chứng minh các file raw vẫn đang có trên máy này.

| Nguồn | Dữ liệu gì? | Nơi tải trong mã / chính gốc hay bản sao? | Cách lấy và bản chất | Dùng cho T nào, đến mức nào? |
|---|---|---|---|---|
| **BPI Challenge 2019** | Nhật ký sự kiện mua hàng–hóa đơn–thanh toán; chuẩn hóa thành khoảng 211.142 dòng hóa đơn/PO | File XES qua Figshare, bộ BPI công bố qua 4TU; kênh phân phối bộ dữ liệu nghiên cứu | Tải tự động, kiểm MD5; **log thật**, phía phải trả của doanh nghiệp châu Âu | **T1:** đã có CSV kết quả. **T9:** tham khảo hiện tượng ghi sổ theo lô, chưa phải bộ ground truth đối soát được dùng trong CSV T9 |
| **Customer Invoices** | Khoảng 49.998 hóa đơn AR sau chuẩn hóa, hạn trả, số tiền, `clear_date` ERP | `SkywalkerHub/Payment-Date-Prediction` trên GitHub; **bản sao bên thứ ba**, được repo mô tả là từ Kaggle/HighRadius | Tải CSV; mã có fallback sang file local. **AR giống ERP, nguồn gốc chưa xác minh**, không nên khẳng định là hóa đơn thật được doanh nghiệp xác nhận | **T1:** đã có CSV kết quả. **T12:** tham chiếu kiểm tra cấu trúc bộ sinh. Không có sao kê hay nhãn vỡ nợ thật |
| **SBA 7(a)** | Khoản vay doanh nghiệp nhỏ Mỹ, thông tin phê duyệt và charge-off; hồ sơ ghi khoảng 638.249 khoản sau chuẩn hóa ở phiên bản đã báo cáo | `data.sba.gov`, **nguồn chính thức SBA** | Tải CSV và từ điển XLSX; **dữ liệu hành chính thật về khoản vay** | **T2:** đã có CSV kết quả; là bài toán khoản vay tương tự, không phải nhãn mất khả năng thu hồi hóa đơn SME VN |
| **Online Retail II** | Khoảng 1,07 triệu dòng bán hàng; gom thành 73 chuỗi doanh thu tuần theo hồ sơ | `archive.ics.uci.edu`, **kho lưu trữ phân phối UCI** | Tải ZIP, loader đọc và gom theo tuần; **giao dịch bán hàng thật** | **T4:** đã có CSV kết quả. Vai trò “T1 nhịp mua” xuất hiện trong mô tả crawler nhưng chưa thấy thí nghiệm T1 tương ứng |
| **Berka / PKDD’99** | Tài khoản, khách, giao dịch, lệnh thanh toán và khoản vay ngân hàng; loader tạo chuỗi tài khoản-tuần | `github.com/jlacko/berka-dataset`; **bản sao cộng đồng**, không phải endpoint ngân hàng gốc | Tải các file `.asc`; bộ giao dịch ngân hàng lịch sử, không phải dữ liệu do bộ sinh dự án tạo | Có loader để phục vụ **T6/T7**, thêm loader khoản vay cho **T2**. Chưa thấy CSV hiện có chứng minh đã đánh giá T6/T7/T2 trên Berka; không ghi là benchmark thật đã hoàn thành |
| **UK Payment Practices** | Khoảng 115.490 báo cáo doanh nghiệp: phân bố thời gian trả và tỷ lệ tranh chấp | `check-payment-practices.service.gov.uk`, **cổng chính thức Chính phủ Anh** | Tải CSV; **thống kê/báo cáo công bố**, không phải từng hóa đơn | **T12:** tham chiếu/kiểm tra họ phân phối trễ; **T3:** tham khảo tỷ lệ tranh chấp. Không phải bộ hóa đơn có nhãn để train T3 trực tiếp |
| **OxCGRT Việt Nam** | Chỉ số chính sách COVID theo ngày, lọc Việt Nam rồi gom tuần | GitHub của tổ chức **OxCGRT**, kho do nhóm công bố quản lý | Tải CSV; **chỉ số chính sách quan sát thật** | **T12:** chèn tín hiệu sốc COVID vào thế giới synthetic; **T7:** bối cảnh/mốc sốc. Nhãn điểm gãy khách hàng dùng trong đánh giá T7 vẫn do bộ sinh chèn |
| **WDI Việt Nam** | 6 chuỗi vĩ mô như tăng trưởng, lạm phát, lãi suất, tỷ giá và tín dụng | `api.worldbank.org`, **API chính thức World Bank** | Gọi API, ghi CSV; **thống kê vĩ mô công bố** | **T12:** loader dùng lãi suất cho chi phí vay trong thế giới sinh; hỗ trợ bối cảnh/kịch bản **T6** gián tiếp. Không phải dữ liệu dòng tiền cấp doanh nghiệp |

Theo endpoint trong mã: **6 nguồn tải từ cơ quan/nhóm công bố hoặc nơi phân phối chính thức; 2 nguồn tải qua bản sao GitHub (Berka, Customer Invoices)**. Phân loại này phản ánh kênh tải, không phải xác nhận mọi bộ dữ liệu đều cùng domain hoặc được kiểm toán. Phần đánh giá bên dưới bổ sung đối chiếu website nguồn ngày 17/10/2026.

#### Dữ liệu đang phục vụ từng mục T

“Có dữ liệu” dưới đây phân biệt **đã có mã/kết quả được lưu** với **mới có nguồn/loader hoặc kế hoạch**. “Ground truth synthetic” là đáp án do bộ sinh biết sẵn, không phải bản ghi quan sát từ doanh nghiệp.

| Mục T | Dữ liệu đang dùng/được chuẩn bị | Bản chất và nguồn | Trạng thái bằng chứng |
|---|---|---|---|
| **T0 — chất lượng dữ liệu** | XML hóa đơn mẫu, các bảng thế giới và lỗi được chèn bằng `inject_errors` | **Synthetic + ca kiểm thử tự dựng** | Có mã kiểm tra/CSV hợp đồng; chưa phải bộ XML ERP sản xuất được doanh nghiệp cung cấp |
| **T1 — ngày trả** | `invoices`, `payments`, `promises` trong `src/tgt`; Customer Invoices; BPI 2019 | **Synthetic + dữ liệu ngoài bộ sinh** (một bộ AR chưa rõ nguồn gốc, một bộ log nghiên cứu thật) | Có CSV thí nghiệm A/B/C. Ngày trả synthetic biết từ bộ sinh; Customer Invoices dùng `clear_date`, BPI dùng sự kiện `Clear Invoice`, không phải ngày tiền về ngân hàng đã đối soát |
| **T2 — không trả/nợ xấu** | Nhãn nợ xấu synthetic; khoản vay và charge-off SBA | **Synthetic + dữ liệu vay thật từ SBA** | Có kết quả tổng hợp và SBA; Berka có loader khoản vay nhưng chưa thấy kết quả tương ứng |
| **T3 — trả một phần/tranh chấp** | Cờ `partial`, `dispute`, lịch sử khách trong `src/tgt` | **Synthetic**; UK PPR là thống kê tham khảo | Có CSV thí nghiệm tổng hợp; chưa có bộ nhãn tranh chấp/trả một phần hóa đơn thật được dùng để xác nhận kết quả |
| **T4 — doanh thu mới** | Doanh thu tuần từ hóa đơn synthetic và Online Retail II | **Synthetic + giao dịch bán hàng thật qua UCI** | Có CSV cho cả hai loại |
| **T5 — lịch chi cố định** | Cấu hình lương, thuế, BHXH, lịch nghỉ và lịch nghĩa vụ do rule engine tạo | **Quy tắc nhập vào mã + đầu vào/đầu ra synthetic**, không phải dataset train ML | Có kiểm thử ví dụ ngày hạn; chưa có bảng lương/tờ khai/nghĩa vụ thực tế của đối tác. Tham số pháp lý được tài liệu ghi là cần đối chiếu văn bản gốc |
| **T6 — số dư/xác suất thiếu hụt** | Đầu ra T1/T4/T5, `outflows`, `daily_cash` của thế giới synthetic | Kết quả đánh giá hiện có chủ yếu là **synthetic**; có hỗ trợ WDI/OxCGRT ở bộ sinh | Có CSV tổng hợp. Berka có nguồn/loader để làm kiểm tra thật nhưng chưa thấy kết quả Berka trong các CSV hiện có |
| **T7 — điểm gãy** | Phần dư theo khách, `events`, `macro` trong các thế giới | **Synthetic**, có chỉ số OxCGRT thật làm tín hiệu nền | Có CSV phát hiện điểm gãy được chèn; không đồng nghĩa đã có bộ sự kiện khủng hoảng được doanh nghiệp xác nhận |
| **T8 — lời hứa trả** | `promises` và ngày thanh toán synthetic | **Synthetic**, độ tin cậy/lời hứa do bộ sinh tạo | Có thí nghiệm; chưa có tập lời hứa thật từ Zalo/email/cuộc gọi của đối tác |
| **T9 — khớp sao kê** | `bank_txns`, `invoices`, `customers`, `payments` của `src/tgt` | **Synthetic**, gồm cả nội dung chuyển khoản giả lập và liên kết chuẩn do bộ sinh biết | Có CSV; chưa phải bộ sao kê–hóa đơn thật đã được kế toán gán nhãn |
| **T10 — giải thích/hành động** | Snapshot, dự báo rủi ro, đóng góp đặc trưng và kịch bản trên `tgt` | **Đầu ra mô hình từ synthetic + fixture kiểm thử** | Có mã/demo; chưa có bộ đánh giá người dùng/kế toán thực tế, demo JSON hiện tại còn lỗi |
| **T11 — đánh giá/cổng chất lượng** | Các tập test và CSV/metric của T1–T10 | **Kế thừa bản chất của từng bộ được chấm**, không có nguồn dữ liệu độc lập thứ chín | Có metric và tài liệu cổng; không biến kết quả synthetic thành bằng chứng trên DN thật |
| **T12 — bộ sinh** | Tạo `firms`, `customers`, `invoices`, `payments`, `bank_txns`, `promises`, `outflows`, `events`, `macro`, `daily_cash` và XML mẫu | **Synthetic có hiệu chỉnh/tham chiếu thống kê thật** | Có mã, cấu hình, fidelity report; bộ sinh không phải crawler lấy hóa đơn Việt Nam thật |
| **T13 — pilot** | Cần hóa đơn, sao kê, nghĩa vụ chi, lời hứa và phản hồi của doanh nghiệp đối tác | **Dữ liệu doanh nghiệp thật cần thu thập** | Chưa có bằng chứng bộ pilot này trong repo |

#### Thống kê thật dùng để dựng synthetic có được crawl không?

Không phải tất cả. Ngoài tám nguồn trên, cấu hình/tài liệu còn tham khảo:

- **Atradius Việt Nam 2025:** các tỷ lệ bán chịu, đúng hạn/quá hạn/nợ xấu và kỳ hạn được nhập vào `calibration_vn.json`/cấu hình rồi dùng hiệu chỉnh máy phát. `crawl.py` không có tác vụ tải tự động báo cáo này; không có dữ liệu từng hóa đơn từ Atradius.
- **JPMorgan Chase Institute:** thống kê đệm tiền mặt dùng làm giả định số dư đầu kỳ; không phải dữ liệu tài khoản khách hàng được tải vào dự án.
- **Coface:** tham chiếu đuôi trễ dài cho kiểm tra độ nhạy; tài liệu ghi dựa trên số liệu/tóm tắt thứ cấp. `sens_coface` vẫn là thế giới synthetic, không phải bộ hóa đơn của Coface.
- **Quy tắc pháp luật/lịch VN:** nhập và mã hóa trong bộ lịch/nghĩa vụ; không có pipeline crawl tự động toàn bộ văn bản luật trong phần dữ liệu này.

Bốn thế giới synthetic được hồ sơ báo cáo có **78 công ty, 5.410 khách hàng, 394.845 hóa đơn, 376.077 giao dịch ngân hàng và 89.563 lời hứa trả**. Các tên `sens_uk`/`sens_coface` chỉ cách chọn giả định phân phối, không có nghĩa đó là giao dịch thật của Anh/Coface.

**Trạng thái file ở checkout hiện tại:** có `config.json`, `fidelity_report.json`, báo cáo hiệu chỉnh, mã và CSV kết quả; chưa có `data/raw/`, `data/interim/` hoặc đầy đủ bảng Parquet của các thế giới được nêu trong hồ sơ. Vì vậy, “đã có” ở đây có thể là **đã có hồ sơ tải/kết quả trong lịch sử**, chưa phải “file dữ liệu gốc đang sẵn để chạy trên máy này”. Hai CSV ở gốc `data/` đang untracked; chưa xác minh nguồn gốc nên không tự gộp vào tám nguồn trên.

**Nguồn mới chỉ chuẩn bị/chờ tải:** Home Credit có loader nhưng chưa có bộ raw hoặc kết quả benchmark tương ứng trong checkout; M5, Payment Times Úc, Freddie Mac, SEC và UNU-WIDER nằm trong danh sách cần thao tác/điều kiện riêng, không được tính là dữ liệu đã thu thập.

Xem thêm Data Card (`docs/DATA_CARD.md`, nhánh `agent1-Khanh`), hồ sơ dữ liệu ngoài bộ sinh (`docs/02_Data/02_du_lieu_that_dung.md`, nhánh `agent1-Khanh`), nguồn chưa dùng (`docs/02_Data/03_du_lieu_khong_dung.md`, nhánh `agent1-Khanh`), bộ đánh giá từng T (`docs/02_Data/07_bo_danh_gia.md`, nhánh `agent1-Khanh`), quy mô dữ liệu (`docs/02_Data/06_quy_mo_va_ke_hoach_sinh.md`, nhánh `agent1-Khanh`).

#### Đánh giá: chính thống, uy tín và cùng domain đến đâu?

**Kết luận: phần lớn có nguồn công bố đáng tin, nhưng chưa có bộ dữ liệu nào được xác nhận là công nợ–sao kê cấp SME Việt Nam đúng bài toán đích.** Riêng Customer Invoices gần nghiệp vụ phải thu hơn nhưng chưa xác minh được xuất xứ doanh nghiệp. “Thật”, “uy tín” và “cùng domain” cần được chấm riêng.

Domain đích của dự án được hiểu là: **hóa đơn bán chịu B2B của SME Việt Nam, liên kết với tiền thực nhận ở ngân hàng và nghĩa vụ chi, để dự báo dòng tiền 13 tuần**. Cùng ngành tài chính hoặc cùng có cột ngày/số tiền chưa đủ: còn phải xét đơn vị quan sát, phía phải thu/phải trả, nhãn, quốc gia, quy mô doanh nghiệp và giai đoạn dữ liệu. Các mức phù hợp dưới đây là nhận định của báo cáo dựa trên mô tả nguồn và cách dùng trong mã, không phải kết quả đo khoảng cách miền.

| Bộ | Chính thống/uy tín | Mức phù hợp với mục T liên quan | Khoảng lệch domain và kết luận được phép rút ra |
|---|---|---|---|
| **BPI 2019** | Nguồn nghiên cứu có tác giả, cơ quan và nơi phát hành rõ ràng | **Gần một phần T1**: có quy trình hóa đơn và sự kiện thanh toán/clear | Tập đoàn đa quốc gia ngành sơn tại Hà Lan, phía **mua/phải trả**, không phải SME VN phía bán/phải thu; `Clear Invoice` không tự chứng minh ngày tiền thực vào tài khoản bên bán. Dùng kiểm tra phương pháp trên quy trình thanh toán khác miền. [Nguồn TU/e](https://research.tue.nl/en/datasets/bpi-challenge-2019/) |
| **Customer Invoices** | **Chưa đủ cơ sở xác nhận chính gốc hoặc dữ liệu doanh nghiệp thật**; repo cộng đồng có mô tả trường nhưng chưa cung cấp chuỗi xuất xứ đủ để kết luận | **Gần T1 về cấu trúc bài toán**: khách, hóa đơn, hạn, ngày clear | Gần nghiệp vụ không bù được thiếu xuất xứ; chưa biết tính đại diện, biến đổi/ẩn danh hay quyền cung cấp. Không khẳng định đây là dữ liệu HighRadius chính thức. Kết quả chỉ nên ghi là thử trên bộ AR công khai chưa xác minh. [Repo nguồn tải](https://github.com/SkywalkerHub/Payment-Date-Prediction), [mô tả trường](https://github.com/SkywalkerHub/Payment-Date-Prediction/blob/main/Dataset-info.md) |
| **SBA 7(a)** | **Chính thức, nguồn gốc rõ:** U.S. Small Business Administration, FOIA, có từ điển dữ liệu | **Liên quan T2 ở mức mô hình rủi ro tín dụng**, không cùng nhãn nghiệp vụ hóa đơn | Đơn vị là **khoản vay SME Mỹ**, nhãn trong mã là **charge-off trong 3 năm**; khác việc một hóa đơn bán chịu ở VN có thu được trong chân trời dự báo. Thắng benchmark SBA chưa chứng minh xác suất mất công nợ hóa đơn được hiệu chỉnh đúng. [SBA FOIA](https://data.sba.gov/dataset/7a-504-foia) |
| **Online Retail II** | UCI công bố, có tác giả/DOI và mô tả giao dịch thật | **Khá phù hợp để benchmark T4 doanh thu**, ít phù hợp để xác nhận T1/T2 | Bán hàng trực tuyến tại Anh giai đoạn 2009–2011, có nhiều khách bán buôn; khác thị trường/ngành/quy mô và thời kỳ. Danh sách trường công bố không có cặp hạn trả–ngày tiền về để đo độ trễ thu nợ. Dự báo doanh thu tốt chưa đồng nghĩa dự báo dòng tiền thu tốt. [UCI](https://archive.ics.uci.edu/dataset/502/online+retail+ii) |
| **Berka** | Bộ nghiên cứu PKDD’99 theo README của bản sao; bản tải trong dự án qua bên thứ ba. **Chưa đối chiếu được file với bản gốc trong lần kiểm tra này** | Liên quan **T6 về chuỗi ngân hàng**, không đủ cho toàn bộ hệ thống công nợ | Mã nạp giao dịch/tài khoản/khoản vay, không có bộ hóa đơn B2B–khách–nghĩa vụ SME VN được liên kết. Chỉ nên dùng làm benchmark bổ trợ; không xếp bản sao ngang mức bảo đảm nguồn gốc với SBA/API World Bank. [README bản sao](https://github.com/jlacko/berka-dataset) |
| **UK Payment Practices** | Cổng Chính phủ Anh chính thức; dữ liệu do doanh nghiệp báo cáo, không đồng nghĩa từng quan sát đã được kiểm toán độc lập | **Gần chủ đề thanh toán B2B**, thích hợp tham chiếu phân phối | Báo cáo tổng hợp của doanh nghiệp lớn ở Anh, không phải bản ghi hóa đơn SME VN. Dùng kiểm tra giả định phân phối/tranh chấp; không dùng như bộ nhãn từng hóa đơn. [GOV.UK](https://www.gov.uk/government/collections/large-businesses-payment-practices-and-performance-statistics) |
| **OxCGRT** | Nhóm nghiên cứu Oxford công bố; uy tín về **chính sách ứng phó COVID** | Đúng bối cảnh VN khi lọc Việt Nam, nhưng chỉ là **biến ngoại sinh cho T7/T12** | Chỉ số chính sách không phải đo thiếu thanh khoản, ngày trả hoặc vỡ nợ của từng khách. Chỉ số thật đưa vào bộ sinh không làm các nhãn dòng tiền synthetic trở thành nhãn thật. [Kho chính thức OxCGRT](https://github.com/OxCGRT/covid-policy-dataset) |
| **WDI Việt Nam** | **World Bank chính thức**, tổng hợp chỉ tiêu từ các nguồn được công nhận | Đúng quốc gia cho **bối cảnh vĩ mô/giả định T12**, hỗ trợ T6 gián tiếp | Dữ liệu vĩ mô cấp quốc gia, không phải dòng tiền hay lãi vay thực tế của từng SME. Cần kiểm tra định nghĩa, tần suất và thời điểm công bố trước khi dùng làm đặc trưng as-of. [World Bank DataBank](https://databank.worldbank.org/) |

**Đọc đúng các CSV đang mở trong IDE:**

- t2_t3_results.csv (`outputs/t2_t3/t2_t3_results.csv`, nhánh `agent1-Khanh`): `T2 SBA 7(a) charge-off<=3y (REAL)` là benchmark **khoản vay Mỹ**. ROC-AUC khoảng 0,955/PR-AUC khoảng 0,214 không phải chất lượng dự báo nợ xấu hóa đơn VN. Các dòng T3 ghi rõ `synthetic tgt`. Ngoài lệch domain, tài liệu còn cảnh báo phiên bản CSV cũ có vấn đề xử lý `EXEMPT`; mã mới đã có lựa chọn xử lý nhưng cần kết quả chạy lại tương ứng.
- D_t2_cure.csv (`outputs/t1/D_t2_cure.csv`, nhánh `agent1-Khanh`): các thế giới `src`/`tgt` là **synthetic**; PR-AUC khoảng 0,965–0,976 không phải kết quả trên doanh nghiệp thật.
- EF_t8_t9.csv (`outputs/t1/EF_t8_t9.csv`, nhánh `agent1-Khanh`): thí nghiệm lời hứa/nhãn sổ–ngân hàng dùng dữ liệu thế giới tổng hợp; không phải lời hứa và sao kê do doanh nghiệp đối tác cung cấp.

Để báo cáo nghiên cứu chính xác, nên viết: **“Đánh giá trên dữ liệu tổng hợp có hiệu chỉnh và các bộ công khai liên quan nhưng khác miền; chưa xác nhận hiệu quả trên SME Việt Nam.”** Không gộp tất cả thành “đã kiểm chứng bằng dữ liệu thật cùng domain”.

Khoảng trống cần bù là dữ liệu từ doanh nghiệp mục tiêu có liên kết **hóa đơn ↔ phân bổ tiền ↔ sao kê**, nhãn ngày tiền về/thu hồi thật và thông tin nghĩa vụ chi. Đánh giá cần giữ riêng doanh nghiệp và giai đoạn kiểm tra, so baseline, kiểm tra độ phủ/hiệu chỉnh và sai số dòng tiền. Đây mới là bằng chứng trực tiếp cho domain đích; nguồn công khai hiện tại vẫn hữu ích để phát triển và kiểm tra phương pháp.

### 5.2 Tài liệu BA, đánh giá và bàn giao

Tài liệu mới được chia thành **5 nhóm** có mục lục chung (`docs/00_INDEX.md`, nhánh `agent1-Khanh`):

1. **Business Analyst:** vấn đề, nhu cầu, thị trường, phạm vi, mô hình kinh doanh và rủi ro.
2. **Data:** chiến lược nguồn, bộ sinh, hard cases, bộ đánh giá và kế hoạch mở rộng.
3. **Evaluation:** metric kỹ thuật/kinh tế, cổng nghiệm thu, kết quả, chi phí và ROI.
4. **AI Methods:** phương pháp từng nhiệm vụ, thích nghi miền, tham số và giả thuyết cần thử.
5. **Coding Agent Plan:** gói công việc WP, phụ thuộc, thứ tự và nhật ký triển khai.

Tài liệu chi phí ước tính đầu tư năm đầu khoảng **2,7 tỷ đồng**; kịch bản ROI cơ sở ước lợi ích khoảng **193,5 triệu đồng/năm/SME**. Đây là **giả định lập kế hoạch**, chưa phải chi phí thực chi hoặc lợi ích đã đo ở khách hàng. Có script tính ROI (`scripts/roi_calc.py`, nhánh `agent1-Khanh`) và kịch bản đầu ra (`outputs/roi_scenarios.json`, nhánh `agent1-Khanh`).

### 5.3 Các file bị thay thế hoặc không còn được theo dõi

Theo `git diff --name-status agent1-Thắng agent1-Khanh`, với nhận diện đổi tên mặc định: **152 file thêm, 35 file xóa, 1 file sửa và 1 file đổi tên**; tổng **189 mục thay đổi**. Đây là thống kê file được Git theo dõi, không bao gồm file untracked.

- Không còn trong cây Git của nhánh Khanh: `SUMMARY_PROJECT_STATUS.md`, `invoice_forecast.ipynb`, bộ notebook cũ, `method/AGENT1_TONG_HOP.md`, `method/CASH_FORECAST_ARCHITECTURE.md`, `method/wbs.md`, các ghi chú `research/T*_note.md`, `research/T1_DATA_SOURCES.md` và nhiều PDF/R tham khảo.
- Git nhận diện `research/invoice_prediction.tex` chuyển thành `reference/invoice_prediction/report_GO.tex`; có thêm README và các bảng kết quả tham chiếu trong thư mục này.
- Những notebook/dashboard và ghi chú ở bản Thắng vẫn có thể đọc từ nhánh đó. Không nên hiểu việc bỏ khỏi nhánh hiện tại là đã di chuyển đầy đủ hoặc bảo toàn toàn bộ tính năng tương ứng.
- Tại thời điểm kiểm tra, `notebooks/`, `data/dataset.csv` và `data/dataset_closed_invoices.csv` là **untracked**. Chúng không được dùng để quy kết đóng góp giữa hai commit; báo cáo này không sửa các file đó.

## 6. Những việc vẫn chưa hoàn tất

| Việc còn lại | Bằng chứng/trạng thái hiện có | Bước tiếp theo |
|---|---|---|
| **Chốt lại kết quả sau sửa cách đo** | Tài liệu cảnh báo CSV A/B/E–F/T6 cũ; `A_rolling_origin_src.v1.csv` được giữ làm bản cũ | Chạy lại, lưu giao thức/phiên bản và cập nhật bảng nghiệm thu |
| **T6 cảnh báo sớm — G13** | Chưa đo đủ lead time và báo giả | Đánh giá theo sự kiện thiếu hụt, tránh chỉ dùng độ phủ/AUC |
| **Demo T10** | `outputs/t6/demo_whatif.json` bị dừng sau trường `scenario`, không phải JSON hoàn chỉnh; có giá trị base bằng 1,0 cần kiểm tra | Sửa xuất file và kiểm tra kịch bản với dòng tiền đầu vào |
| **T9 tự động đối soát** | ML precision thấp; có mã pipeline lai nhưng CSV cũ chưa xác nhận hiệu quả pipeline đó | Đo riêng độ chính xác liên kết tự động và tỷ lệ đưa vào hàng chờ |
| **T2 và dữ liệu thật** | SBA có vấn đề nhãn/kiểm duyệt; nhiều nguồn chỉ là dữ liệu tương tự | Sửa giao thức và bổ sung đánh giá phù hợp nghiệp vụ hóa đơn |
| **T7/T8/thích nghi miền** | Một số tiêu chí chưa đạt; fine-tune chưa đạt mức cải thiện 10% kỳ vọng | Ưu tiên hướng có lợi ích đo được, giữ baseline khi mô hình phức tạp không thắng |
| **Sản phẩm dùng thực tế** | Có mã thử nghiệm và kế hoạch; chưa thấy bằng chứng dashboard/API/kết nối ERP–ngân hàng được triển khai đầy đủ | Hoàn thiện tích hợp, giao diện, giám sát và luồng duyệt |
| **Pilot T13** | Chưa có bằng chứng hiệu quả trên doanh nghiệp đối tác | Đo lại chất lượng dự báo, giá trị cảnh báo, tác động hành động và ROI thực tế |

**Đánh giá tổng thể:** bản Khanh mở rộng Agent 1 thành một nền tảng thử nghiệm và bộ tài liệu bàn giao có cấu trúc hơn. Thành quả rõ nhất là mã module hóa, dữ liệu tổng hợp nhiều miền, thí nghiệm rộng hơn và kiểm soát chất lượng cụ thể hơn. Độ chính xác vượt bản Thắng và mức sẵn sàng triển khai vẫn cần được chứng minh bằng đánh giá chung và pilot thực tế.

## 7. Cách kiểm tra lại phép so sánh

```powershell
git log --oneline agent1-Thắng..agent1-Khanh
git log --oneline agent1-Khanh..agent1-Thắng
git diff --stat agent1-Thắng agent1-Khanh
git diff --name-status agent1-Thắng agent1-Khanh
git show agent1-Thắng:SUMMARY_PROJECT_STATUS.md
git show agent1-Thắng:method/AGENT1_TONG_HOP.md
```

Phạm vi báo cáo chỉ là **Agent 1**; không đánh giá các nhánh Agent 2/3/4. Phần uy tín/domain tại mục 5.1 đã bổ sung đối chiếu website nguồn ngày 17/10/2026; không tải lại và đối chiếu hash các file dữ liệu lớn. Các phát biểu pháp luật, chi phí và những thông tin bên ngoài còn lại được mô tả theo tài liệu trong repo, chưa xác minh độc lập.
