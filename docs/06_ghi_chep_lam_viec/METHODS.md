# METHODS.md — Phương pháp và mô hình của Agent 2: tài liệu tham khảo, cách chọn so sánh, kết quả

Quy ước: **[Đ]** đã đọc tài liệu gốc trong phiên làm việc; **[T]** chỉ đọc tóm tắt / kết quả tìm kiếm; **[K]** tài liệu kinh điển tôi dùng theo hiểu biết, chưa đọc lại trong phiên này; **[N]** thiết kế của tôi. Mọi số đo là trên dữ liệu tổng hợp (xem [DATA.md](DATA.md)).

---

## 1. Bài toán và ràng buộc đã quyết định cách chọn phương pháp

Người dùng là chủ doanh nghiệp hoặc kế toán trưởng của doanh nghiệp nhỏ, không có kiểm toán nội bộ. Điều quan trọng nhất là **không quá tải cảnh báo**, nên: (1) đo theo **ngân sách cảnh báo** (1–3 cảnh báo mỗi công ty mỗi tuần), không theo F1; (2) mọi cảnh báo phải **giải thích được bằng tiếng Việt**; (3) không có nhãn thật ngày đầu, nên phải có chế độ **không cần nhãn**; (4) kiểu gian lận mới sẽ xuất hiện, nên phải đo trên **họ gian lận chưa thấy**.

## 2. Tài liệu tham khảo và điều rút ra

### 2.1. Phát hiện bất thường trên bút toán và ERP
| Tài liệu | Điều dùng | Điều rút ra cho thiết kế |
|---|---|---|
| Schreyer và cộng sự 2017, autoencoder trên sổ cái, arXiv 1709.05254 [Đ] | Điểm = α·lỗi tái tạo + (1−α)·xác suất giá trị hiếm; mỗi sổ cái một mô hình | Autoencoder phải huấn luyện riêng từng doanh nghiệp; F1 chỉ 0,33 và 0,17 dù bất thường chèn là loại dễ nhất; bất thường thống kê ≠ gian lận (đa số cảnh báo là nhà cung cấp hiếm, lỗi hạch toán) |
| Schultz và Tropmann-Frick 2020, HICSS (autoencoder từng tài khoản) [T] | Huấn luyện theo tài khoản vẫn chạy với dữ liệu nhỏ | Hướng đáng thử cho SME; chưa cài |
| Bakumenko và Elragal 2022, *Systems* 10(5):130 [T qua trích dẫn] | So sánh Isolation Forest và autoencoder trên sổ cái | Isolation Forest thường ít báo nhầm hơn |
| Gronewald và cộng sự, arXiv 2609.18228 [Đ] | Kết hợp phép thử bút toán (JET) với học máy: giao hai danh sách hoặc dùng kết quả JET làm đặc trưng | Danh sách JET một mình gắn cờ 20,7% bút toán; giao hai danh sách giảm báo sai 88% nhưng bỏ sót 3%; **bài chèn bất thường đúng trong danh sách JET nên độ phủ 100% là vòng tròn** |
| AuditCopilot, arXiv 2512.02726 [T] | Mô hình ngôn ngữ nhắc lệnh trên sổ cái | F1 từ 0,28 đến 0,83 tuỳ mô hình, nhãn là nhãn giả; chưa đánh giá độ trung thực của giải thích → chỉ để diễn giải, không để phát hiện |
| Tritscher và cộng sự 2022 (arXiv 2206.04460) và 2023 (Kernel SHAP cho autoencoder) [Đ/T] | Bộ dữ liệu ERP có nhãn; giải thích bằng SHAP | Dùng bộ dữ liệu làm kiểm tra ngoài; giải thích gốc của mô hình (đuôi từng đặc trưng) ưu tiên hơn SHAP |
| Baader và Krcmar 2018, IJAIS (cờ đỏ + khai phá quy trình giảm báo sai) [T] | Kết hợp quy tắc với quy trình | Ủng hộ hướng hybrid; chưa cài khai phá quy trình |

### 2.2. Chuẩn so sánh và lý thuyết
| Tài liệu | Điều rút ra |
|---|---|
| ADBench, Han và cộng sự, NeurIPS 2022, arXiv 2206.09426 [Đ] | 57 bộ, 30 thuật toán: không phương pháp không giám sát nào vượt trội có ý nghĩa thống kê; học sâu không giám sát (DeepSVDD, DAGMM) kém phương pháp nông; chỉ 1% nhãn đủ để bán giám sát vượt phương pháp không giám sát tốt nhất; HBOS, COPOD, ECOD, NB nhanh nhất → **không chọn một phương pháp "tốt nhất", phải đo** |
| ECOD, Li và cộng sự, TKDE 2023, arXiv 2201.00382 [T] | Không tham số, đuôi ECDF từng chiều, giải thích được → ứng viên cho khởi đầu lạnh |
| Isolation Forest, Liu, Ting, Zhou 2008 [K]; HBOS, Goldstein và Dengel 2012 [K] | Đường cơ sở không giám sát chuẩn |
| LightGBM, Ke và cộng sự 2017 [K] | Mô hình có giám sát cho dữ liệu bảng; ADBench ghi nhận cây tổng hợp mạnh |
| GADBench, Tang và cộng sự, NeurIPS 2023, arXiv 2306.12251 [T] | Cây tổng hợp với đặc trưng láng giềng có thể thắng mạng nơ-ron đồ thị → **không dùng GNN ở giai đoạn một**; lớp đồ thị là truy vấn tất định |
| Egressy và cộng sự, AAAI 2024, arXiv 2306.11586 [T] | GNN chỉ giúp rõ ở mẫu rửa tiền nhiều bước, không phải gian lận nội bộ SME |
| Das và cộng sự 2016, *Active Anomaly Discovery*, ICDM [T] | Học lại trọng số từ phản hồi với ngân sách xem hữu hạn → nền tảng của vòng phản hồi |
| Bates, Candès và cộng sự, *Testing for Outliers with Conformal p-values*, Annals of Stat. 2023, arXiv 2104.08279 [T]; Barber và cộng sự 2023, arXiv 2202.13415 [T] | p-giá trị conformal + Benjamini–Hochberg kiểm soát FDR; cần dạng có trọng số khi dữ liệu trôi. Chỉ kiểm soát "giống bình thường của chính doanh nghiệp", không phải precision gian lận |
| Goix 2016, arXiv 1607.01152 [T] | Chỉ số không cần nhãn (Mass–Volume, Excess–Mass) cho dữ liệu thật chưa có nhãn |
| Durtschi, Hillison, Pacini 2004; Barney và Schulzke 2016; Cerasa và cộng sự 2022 [T] | Benford dễ báo nhầm ở mẫu nhỏ → chỉ dùng làm chẩn đoán, không cộng điểm cho giao dịch lẻ (bạn bạn đã làm đúng) |
| Palguta và Pertold; Italy, Thụy Điển, Mỹ: dồn giá trị ngay dưới ngưỡng [T] | Căn cứ cho luật sát ngưỡng; chỉ chứng minh thao túng, không chứng minh gian lận |
| ACFE 2024 [Đ] | Loại gian lận và tỷ lệ theo quy mô → danh sách họ gian lận mô phỏng |

### 2.3. Không dùng và lý do
Mạng nơ-ron đồ thị (GraphSAGE, GAT): đồ thị SME quá nhỏ, GADBench cho thấy không thắng cây; TabPFN và mô hình nền cho dữ liệu bảng: chưa có bằng chứng trên sổ cái, cần kiểm tra giấy phép thương mại [T]; mô hình ngôn ngữ làm bộ phát hiện: kết quả không ổn định, rủi ro tiêm lệnh qua văn bản tự do; autoencoder LSTM/VAE: chưa đọc đủ.

## 3. Các phương pháp đã cài và cách chọn đưa vào so sánh

Mỗi phương pháp có cùng giao diện `fit(train, valid)` / `score(df)` (`agent2/methods.py`). Chọn theo nguyên tắc: một đại diện cho mỗi họ có lý do trong tài liệu, cộng đường cơ sở của bạn bạn.

| Chế độ | Phương pháp | Nguồn ý tưởng | Cần nhãn / huấn luyện riêng? |
|---|---|---|---|
| R | **31 luật + đồ thị quan hệ** (bạn bạn) | Phép thử bút toán theo chuẩn kiểm toán; ACFE | Không; trọng số đặt tay |
| R→S | **Luật học lại trọng số** (logistic L2 trên 34 cột hit luật) | Hiệu chỉnh luật bằng dữ liệu | Cần nhãn từ thế giới khác; chỉ ~34 trọng số |
| U | Isolation Forest (190 đặc trưng = đường cơ sở của họ; bộ đặc trưng liên tục) | [K] | Khớp trên lịch sử chính doanh nghiệp, không nhãn |
| U | ECOD, HBOS (cài lại) | [T], [K] | Như trên; không tham số |
| U | Autoencoder MLP nhỏ trên đặc trưng chuẩn hóa phân vị | Schreyer 2017 [Đ] | Như trên; nặng nhất |
| U | **EntityDeviation** (12 bộ phát hiện một phía: giá, lương, người lập, gần trùng, tự duyệt tiền mặt…; điểm = max của −log xác suất đuôi) | [N], dựa trên ý "baseline theo thực thể" | Không nhãn; khớp trên chính doanh nghiệp |
| H | Cổng Gate(luật, ECOD); hợp nhất max-xếp hạng(luật, thực thể); Blend 80/20 của họ | Sửa lỗi blend | Không nhãn |
| S | LightGBM trên 190 / +30 thực thể / +hit luật | ADBench [Đ] | Cần nhãn |
| S→H | **CES** (chồng bằng chứng hiệu chỉnh): logistic 13 trọng số + hằng số trên [điểm luật học, 12 điểm đuôi thực thể], chính quy hoá L2 quanh tiên nghiệm đơn điệu | [N] | Học trước trên thế giới khác; điểm thực thể đo trên lịch sử của chính doanh nghiệp |
| H | **Khe thăm dò:** mỗi công ty–tuần, 2 khe cho CES/LightGBM + 1 khe cho kênh "mới lạ" (max xếp hạng luật, thực thể) | exploit/explore [N] | Kênh mới lạ không cần nhãn |

**Vì sao thêm CES và khe thăm dò:** thử nghiệm cho thấy mô hình học trước có xu hướng bỏ qua bộ phát hiện chưa từng giúp ở họ đã học, nên mù trước họ mới; kênh không học giữ cửa cho kiểu gian lận mới.

## 4. Giao thức so sánh (đã quyết định để tránh tự lừa mình)

| Giao thức | Cách làm | Mục đích |
|---|---|---|
| Theo thời gian | huấn luyện 2024, kiểm định nửa đầu 2025, kiểm thử nửa cuối 2025; ngưỡng chỉ lấy từ kiểm định; nhãn kiểm thử không dùng để chọn gì | Giống triển khai thật |
| Bỏ một họ | huấn luyện không có họ F, kiểm thử trên F cùng mọi dòng hợp lệ | Đo khả năng chuyển giao sang kiểu gian lận chưa thấy |
| Bỏ một công ty | huấn luyện 7 công ty, kiểm thử công ty thứ 8 | Công ty chưa thấy |
| Chéo thế giới | học trước trên 4 thế giới (seed khác), kiểm thử thế giới thứ 5; thực thể và hệ quy chiếu chỉ khớp trên chính thế giới đích, không dùng nhãn | Gần với "học trước rồi áp vào doanh nghiệp mới" |
| Tập niêm phong | 3 thế giới, 3 họ mới, cấu hình đóng băng trước, chạy một lần | Kiểm thử cuối không bị tinh chỉnh |
| Dữ liệu ngoài | DFKI, ERP Fraud Data | Kiểm tra chéo trên dữ liệu của người khác |

**Chỉ số** (`agent2/metrics.py`): AP (nền 0,003) và R-precision; precision, recall, vụ tìm thấy và hồ sơ theo thực thể ở **ngân sách theo công ty–tuần B1, B2, B3**; tỷ lệ báo nhầm trên **ca hợp lệ giống gian lận**; độ trễ phát hiện; bootstrap theo vụ; 5 seed cho trung bình ± độ lệch chuẩn. Không dùng ROC-AUC làm tiêu chí (luôn cao khi dương 0,3%).

## 5. Kết quả so sánh (tóm tắt; chi tiết ở [AGENT2_REPORT_VI.md](AGENT2_REPORT_VI.md))

**Theo thời gian, 5 seed, B3 (≈ 26 cảnh báo/1.000 dòng):**

| Phương pháp | AP | Recall@B3 | Báo nhầm ca giống gian lận |
|---|---:|---:|---:|
| 31 luật (tay) | 0,240 ± 0,019 | 31% | 2,9% |
| Isolation Forest 190 đặc trưng | 0,021 ± 0,013 | 10% | 13,1% |
| ECOD / HBOS | 0,005 / 0,004 | 5% / 4% | 5% |
| Autoencoder | 0,065 ± 0,020 | 33% | 20,3% |
| EntityDeviation | 0,012 ± 0,002 | 17% | 7,8% |
| Ensemble 80/20 của họ | 0,163 ± 0,023 | 34% | 7,7% |
| Luật học lại trọng số | 0,387 ± 0,019 | 48% | 3,7% |
| LightGBM 190 đặc trưng | 0,633 ± 0,046 | 75% | 11,9% |
| LightGBM + thực thể + luật | 0,817 ± 0,022 | 89% | 16,1% |

**Họ gian lận chưa thấy (recall@B3, TB 9 họ):** LightGBM thuần 16%; luật 34%; LightGBM + luật + thực thể 51%; max(luật, thực thể) 43%; EntityDeviation 19% (nhưng 80% với "mua đắt", 82% với "nâng lương").

**Chéo thế giới và ngân sách:** CES 2+1 ở B3: precision 7,8%, recall 68%, báo nhầm 6,3%, recall họ chưa thấy 32%; LightGBM 2+1: 10,4%, 90%, 12,6%, 49%. B1: CES precision 18,0%; LightGBM 24,8%.

**Tập niêm phong (một lần):** CES 2+1 recall 53% (họ mới 17,5%), báo nhầm 7,0%; LightGBM 2+1 recall 83% (họ mới 58,7%), báo nhầm 10,9%; luật tay 29%.

**Dữ liệu ngoài:** ERP Fraud Data, không giám sát: ECOD AP 0,495 / 0,059 / 0,147, IF 0,459 / 0,050 / 0,117, autoencoder 0,144 / 0,147 / 0,212 — không phương pháp nào thắng ổn định. DFKI: JET một mình AP 0,083; ECOD 0,097; autoencoder 0,122; LightGBM 0,80–0,85 (vòng tròn).

**Vòng phản hồi (52 tuần, 5 seed, số dòng gian lận tìm được):** không học 58; nới ngưỡng 58 → 52 → 48 (nhiễu 0 → 15 → 30%); học lại trọng số kiểu AAD 83 → 79 → 54.

## 6. Cách đọc kết quả một cách trung thực
1. AP 0,8 của mô hình có giám sát là **số trong cùng phân phối**, là vòng tròn; số cần nhìn là bỏ một họ, chéo thế giới và niêm phong.
2. Mô hình học trước (CES, LightGBM) chỉ tốt bằng mức thế giới tổng hợp giống thực tế; trên họ mới của tập niêm phong, phần thắng của LightGBM một phần do bộ sinh chia sẻ cơ chế (lương luôn ngày 28).
3. Tiêu chí chọn cấu hình đặt trước (trung bình recall trong phân phối và họ chưa thấy, ràng buộc báo nhầm ≤ 10%) chọn CES 2+1; LightGBM thắng về recall nhưng báo nhầm 11–13%.
4. Ba họ `expense_padding`, `kickback_overpricing`, `payroll_padding` đã được xem khi thiết kế EntityDeviation nên không còn là "chưa thấy"; chỉ ba họ niêm phong là kiểm thử thật.
5. Chưa đo được: độ chính xác trên doanh nghiệp thật, thời gian xem mỗi cảnh báo, hiệu quả của giải thích bằng tiếng Việt với người dùng thật.

## 7. Mã và cách chạy lại
`agent2/methods.py` (phương pháp), `metrics.py`, `bench.py`, `final_eval.py`, `aggregate.py` (giao thức), `alerting.py` (chọn cảnh báo, lý do, conformal), `feedback_sim.py`, `external.py`, `pipeline.py`. Kết quả thô: `results/`. Lệnh: xem [AGENT2_README.md](AGENT2_README.md).

## 8. Vòng v4 tiếp nhận ngày 2026-10-16 và 2026-10-17

Các kết quả ở mục 5 và tiêu chí ở mục 6 thuộc vòng nghiên cứu trước. Vòng v4 mới dùng đúng đăng ký trước tại nhật ký mục 14: trung bình ba giao thức P1, P2 theo 10 nhánh ACFE và P3, trên ba thế giới phát triển, trần báo nhầm P1 là 20%; chênh dưới 0,01 ưu tiên cấu hình đứng trước.

Đã hoàn tất 24 cấu hình trên cả ba thế giới, kèm bootstrap ghép cặp theo vụ 2.000 lần. Chọn **L4-FB**, khởi đầu lạnh **Novelty max(R,E)**; tệp khóa `results/v4/v4_frozen.json`. Điểm chọn 0,7416, recall P1 80,81%, P2 59,06%, P3 82,62%, báo nhầm ca khó P1 16,62%. H1 chưa đạt vì khoảng tin cậy P1 của L4 trừ L3 chứa hoặc chạm 0. Xem [báo cáo phát triển v4](../03_danh_gia_va_hieu_qua_kinh_te/06_so_sanh_phuong_phap_v4.md).

Thử khô seed 939 đã qua. Thực thi giới hạn một ứng viên đồng thời và thu nhỏ kiểu lưu số nguyên cho toàn bộ kết quả thử khô giống chính xác lần trước; hồi quy P3 413 có 1.020 chỉ số giống chính xác. Không đổi sáu tệp, tham số hoặc chính sách đã khóa. A5 hoàn tất sau khôi phục hạ tầng chưa từng lộ chỉ số từng phần.

Kết quả niêm phong tổng hợp của L4-FB, trung bình đều ba thế giới: S1 recall chung **41,31%**, kịch bản mới **20,32%**, báo nhầm toàn bộ ca khó **10,37%**; S2 tương ứng **63,87%**, **31,22%**, **11,39%**. G5 không đạt; S1 dưới 50% kích hoạt **dừng toàn dự án tại M2**. Không chọn lại ứng viên từ bảng chẩn đoán, không huấn luyện v2, không tiếp tục pha B hoặc thí điểm. Xem [báo cáo niêm phong](../03_danh_gia_va_hieu_qua_kinh_te/07_ket_qua_niem_phong_v4.md). Chủ dự án cần xem lại bài toán trước hướng công việc mới; ba seed này đã dùng và không được tái sử dụng làm kiểm thử niêm phong.

Đường ống vận hành mới nhận bảng thô theo công ty và tuần, không đọc nhãn hay đặc trưng lưu sẵn. Đối chiếu 273 cột số trên 2.113 dòng với đường ống nghiên cứu có chênh lớn nhất bằng không. Điều này kiểm tính tương đương đặc trưng; chưa xác nhận hiệu năng trên dữ liệu thật. Bộ API, hàng đợi và phản hồi đã có kiểm thử kỹ thuật, chưa có đánh giá thí điểm. Hướng dẫn tại [vận hành cục bộ](../05_ke_hoach_giao_viec/huong_dan_van_hanh.md).
