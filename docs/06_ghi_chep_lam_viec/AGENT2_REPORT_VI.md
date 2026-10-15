# Báo cáo Agent 2 — phát hiện gian lận nội bộ cho doanh nghiệp nhỏ và vừa Việt Nam

Ngày: 14/10/2026. Mã: `agent2_fraud/agent2/`. Nhật ký chi tiết: [AGENT2_WORKLOG.md](AGENT2_WORKLOG.md). Hướng dẫn chạy: [AGENT2_README.md](AGENT2_README.md).

**Đọc trước.** Mọi con số dưới đây đo trên dữ liệu tổng hợp (cộng hai bộ dữ liệu công khai của nước ngoài). Không có con số nào là bằng chứng về hiệu quả trên doanh nghiệp thật. Giá trị của đợt này nằm ở: (1) bộ so sánh có giao thức đúng; (2) các lỗi của thiết kế cũ được đo rõ; (3) một đường ống chạy được từ bảng kế toán đến hồ sơ rà soát bằng tiếng Việt; (4) danh sách dữ liệu thật cần thu thập tiếp.

---

## 1. Kết luận

1. **Số "độ chính xác" cũ không tin được.** Trên bộ dữ liệu của bạn bạn, bộ 31 luật đạt AP 0,60 vì luật được viết đúng theo sáu kịch bản mà bộ sinh chèn vào. Trên thế giới dữ liệu mới (v3: nhiều mức khó, mồi hợp lệ, họ gian lận không luật nào viết sẵn) cùng bộ luật chỉ đạt **AP 0,24** (5 seed). Isolation Forest 190 đặc trưng, đường cơ sở của họ, chỉ đạt AP 0,02.
2. **Mô hình có giám sát rất mạnh trong cùng phân phối và không đáng tin ngoài nó.** LightGBM đạt AP 0,82 khi kiểm thử trên cùng kiểu kịch bản đã học. Khi bỏ một họ gian lận khỏi huấn luyện, recall trên họ đó chỉ còn 16% (LightGBM thuần) đến 51% (có đặc trưng luật và thực thể). Vì vậy AP 0,8 không phải năng lực phát hiện, mà là khả năng nhớ mẫu của bộ sinh.
3. **Không có phương pháp không giám sát nào thắng ổn định.** ECOD, HBOS, Isolation Forest gần như ngẫu nhiên trên sổ sách SME mô phỏng (AP 0,004–0,02); autoencoder khá hơn (AP 0,065) nhưng báo nhầm 20% các ca hợp lệ giống gian lận. Kết quả khớp với ADBench và với hai bộ dữ liệu ngoài (mục 5.5).
4. **Điều giúp nhiều nhất không phải thuật toán mới mà là cách kết hợp và dữ liệu đầu vào:** (a) trọng số luật học lại thay cho trọng số đặt tay: AP 0,24 lên 0,39; (b) đặc trưng lệch theo từng thực thể (đơn giá từng nhà cung cấp, lương từng nhân viên): bắt được 80% "mua đắt" và "nâng lương" mà không cần nhãn; (c) cấp một phần khe cảnh báo cho kênh không học để không mù trước kiểu gian lận mới; (d) **đơn giá và số lượng từng dòng hàng của hóa đơn điện tử**: không có hai cột này thì "mua đắt" gần như không thấy được từ tổng tiền thanh toán.
5. **Tập niêm phong (3 thế giới, 3 họ chưa từng dùng khi phát triển, chạy đúng một lần):** hồ sơ mặc định "chính xác" bắt 53% dòng gian lận với 3 cảnh báo/công ty/tuần, báo nhầm 7% các ca hợp lệ giống gian lận; hồ sơ "phủ rộng" 83% nhưng báo nhầm 11%. Với ngân sách 1 cảnh báo/công ty/tuần, độ chính xác lên 16,5% và 27%.
6. **Phản hồi một chạm có ích nhưng dễ gây hại:** học lại trọng số từ phản hồi tăng số gian lận tìm được từ 58 lên 83 trên 52 tuần (người duyệt đúng), còn 54 khi người duyệt sai 30%; cách "nới ngưỡng" của thiết kế tham khảo không bao giờ giúp và giảm kết quả khi có nhiễu.

**Khuyến nghị triển khai.** Bắt đầu bằng hồ sơ `cold` (luật + lệch thực thể, giải thích được, không dựa vào dữ liệu tổng hợp) ở ngân sách 1–3 cảnh báo/công ty/tuần; thu phản hồi từ 3–5 doanh nghiệp đối tác; huấn luyện lại CES/L3 trên hồ sơ thật đã được người có chuyên môn kết luận; chỉ khi đó mới bật `precision` hoặc `wide`.

---

## 2. Đánh giá dự án nhận được

**Điểm tốt, giữ nguyên:** đặc trưng chỉ dùng dữ liệu quá khứ (kiểm tra bằng test chống rò rỉ, tôi tái lập cả 64 test); sổ cái TT133/TT200 cân Nợ = Có; hàng đợi hồ sơ có SLA và nhật ký phản hồi có chuỗi hash; có hard negatives; ghi `not_evaluable` thay vì coi thiếu dữ liệu là "không vi phạm".

| Vấn đề | Bằng chứng đã đo | Xử lý |
|---|---|---|
| Nhà cung cấp nền cùng ngày onboard 01/01/2023 | 400/400 NCC nền; tuổi NCC là đặc trưng quan trọng thứ 2 của LightGBM | Bộ sinh v3: NCC onboard rải 2018–2025, độ phổ biến kiểu Zipf |
| Tên NCC cùng tiền tố, số tiền không phụ thuộc NCC, không mùa vụ | Luật E3 báo 100% dòng (12.625 FP) | v3: tên đa dạng + chi nhánh gần giống, đơn giá theo NCC, Tết, cuối tháng |
| Đánh giá vòng tròn: luật viết đúng theo kịch bản chèn; 1 seed; 5 công ty gần giống | AP luật 0,60 xuống 0,24 trên thế giới khó hơn | v3: 3 mức khó, 3 họ không luật, 8 công ty, 5 seed, tập niêm phong |
| Chỉ thử Isolation Forest (190 đặc trưng, đa số one-hot) | AP 0,02–0,03 | Thêm ECOD, HBOS, autoencoder, thực thể, LightGBM, hợp nhất |
| Ensemble 80% luật + 20% IF làm kết quả xấu đi | AP 0,61 xuống 0,45 trên bộ dữ liệu của chính họ | Sửa trong `sme_fraud/run_rules.py`: luật quyết định thứ tự, IF chỉ phá hòa; AP 0,665 |
| Ngưỡng vận hành 7 sinh ~900–1.000 cảnh báo/25.000 dòng (3,6%) | gấp hơn 12 lần ngân sách 75 | Ngân sách theo công ty–tuần, khe thăm dò, tuỳ chọn conformal/BH |
| "Nới ngưỡng khi bị đánh dấu báo sai" | 5 seed: không bao giờ tăng kết quả; giảm khi có nhiễu | Học lại trọng số (AAD) có làm mịn nhãn và cảnh báo rủi ro nhiễu |
| Mô tả khác triển khai ở A2, A3, A4, A5, B1, B3, B7, E1 | bảng đối chứng 43/51 của họ | Họ đã sửa B7, E1, A2; A3, A4, A5, B1, B3 vẫn mở |
| Hash chain trong nhật ký phản hồi không phải chữ ký | Họ đã ghi rõ | Không đổi |

Lỗi tôi gây ra và đã sửa: thanh toán của NCC ma có thể vượt ra ngoài cửa sổ thời gian (tìm thấy khi sinh tập niêm phong); vá không đổi dữ liệu của các seed đã dùng.

---

## 3. Dữ liệu

| Bộ | Quy mô | Dùng để |
|---|---|---|
| v2 của bạn bạn (`sme_fraud_001/003/005`) | 100.000 quan sát × 3, 5 công ty | Tái lập; chứng minh các lỗi ở mục 2 |
| **World v3** `w3_s201..205` | 100.000 quan sát × 5 seed, 8 công ty, 300 gian lận (0,3%), 9 họ × 3 mức khó, 17 loại mồi hợp lệ | Phát triển và so sánh |
| **Tập niêm phong** `sealed_s901..903` | 3 thế giới, 12 họ (thêm `price_creep`, `off_cycle_payroll`, `vendor_burst`), 360 gian lận mỗi bộ | Chạy đúng một lần với cấu hình đã đóng băng |
| DFKI General Ledger | 256.232 dòng, 102.429 bút toán, 850 bất thường chèn, CC BY 4.0, MD5 khớp Zenodo | Kiểm tra bên ngoài |
| ERP Fraud Data (Würzburg) | 5 lần chạy ERPsim/SAP, nhãn từng dòng, 12 kịch bản, 190 MB (chỉ giải nén CSV) | Kiểm tra bên ngoài |

Thế giới v3 sửa các lỗi ở mục 2 và thêm **đơn giá từng NCC** (mô phỏng dòng hàng của hóa đơn điện tử XML) để kiểm tra có phát hiện được "mua đắt" hay không. Cố ý để các họ khó: chi tiền mặt lặp lại sát hạn mức tự duyệt (luật và kênh không học: 0%; chỉ mô hình đã thấy họ này mới bắt được, 76–90%), cụm thanh toán buổi tối nhiều NCC (19% với phương pháp tốt nhất).

Không tải: PaySim, BankSim, BAF, Elliptic (gian lận bên ngoài hoặc rửa tiền, ngoài phạm vi Agent 2; Phần 6 và 8 đã giải thích), BPI 2019/2020 (không có nhãn; lược đồ khác).

---

## 4. Phương pháp và giao thức

**Chế độ:** U không giám sát; R chỉ luật; H hợp nhất không nhãn; S giám sát (có nhãn từ thế giới khác).

**Phương pháp so sánh (cùng giao diện `fit/score`):** 31 luật (tay), luật học trọng số, Isolation Forest (190 đặc trưng / bộ đặc trưng liên tục), ECOD, HBOS, autoencoder, EntityDeviation (12 bộ phát hiện một phía lệch so với lịch sử thực thể), cổng luật+ECOD, ensemble 80/20 của họ, hợp nhất max-xếp hạng, LightGBM (190 / +thực thể / +luật), **CES** (chồng bằng chứng đã hiệu chỉnh: 13 trọng số và 1 hằng số, tiên nghiệm đơn điệu), các cấu hình khe 2+1 và 1+2.

**Giao thức:** (a) theo thời gian: huấn luyện 2024, kiểm thử nửa cuối 2025; (b) bỏ một họ gian lận khi huấn luyện, kiểm thử trên họ đó; (c) bỏ một công ty; (d) chéo thế giới: học trước trên 4 thế giới, kiểm thử thế giới thứ 5; (e) niêm phong.

**Chỉ số:** AP (nền 0,003), R-precision, precision/recall/vụ-tìm-thấy ở **ngân sách theo công ty–tuần** (B1, B2, B3), tỷ lệ báo nhầm trên các ca hợp lệ giống gian lận, độ trễ phát hiện, precision ở mức hồ sơ theo thực thể, bootstrap theo vụ. ROC-AUC chỉ ghi để cảnh báo: luôn 0,85–0,99 dù AP thấp.

---

## 5. Kết quả

### 5.1. Giao thức theo thời gian, 5 seed (B3 ≈ 26 cảnh báo/1.000 dòng)

| Phương pháp | Chế độ | AP | Recall@B3 | Vụ tìm thấy | Báo nhầm ca giống gian lận |
|---|:-:|---:|---:|---:|---:|
| 31 luật (tay) | R | 0,240 ± 0,019 | 31% | 43% | 2,9% |
| Isolation Forest 190 đặc trưng (đường cơ sở) | U | 0,021 ± 0,013 | 10% | 15% | 13,1% |
| ECOD / HBOS | U | 0,005 / 0,004 | 5% / 4% | 4–5% | 5% |
| Autoencoder | U | 0,065 ± 0,020 | 33% | 46% | 20,3% |
| Lệch thực thể | U | 0,012 ± 0,002 | 17% | 11% | 7,8% |
| Ensemble 80/20 (của họ) | H | 0,163 ± 0,023 | 34% | 49% | 7,7% |
| max(luật, thực thể) | H | 0,190 ± 0,058 | 38% | 46% | 6,1% |
| Trọng số luật học lại | S | 0,387 ± 0,019 | 48% | 64% | 3,7% |
| LightGBM 190 đặc trưng | S | 0,633 ± 0,046 | 75% | 87% | 11,9% |
| LightGBM + thực thể + hit luật | S | 0,817 ± 0,022 | 89% | 95% | 16,1% |

### 5.2. Họ gian lận chưa thấy khi huấn luyện (recall@B3, trung bình 9 họ × 5 seed)

LightGBM thuần 16% · luật 34% · LightGBM + luật + thực thể 51% · lệch thực thể 19% · max(luật, thực thể) 43% · max(LightGBM, luật, thực thể) 58%. Lệch thực thể một mình đạt 80% với "mua đắt" và 82% với "nâng lương" và 0% với các họ còn lại.

### 5.3. Chéo thế giới và ngân sách (5 thế giới × học trước trên 4 thế giới còn lại)

| Cấu hình | Cảnh báo | Precision | Recall | Vụ tìm thấy | Báo nhầm ca giống gian lận | Recall họ chưa thấy |
|---|---:|---:|---:|---:|---:|---:|
| Luật tay, B3 | 648 | 3,8% | 32,5% | 45% | 3,1% | 33% |
| Kênh mới lạ (không học), B3 | 648 | 4,4% | 38,4% | 45% | 6,2% | 40% |
| CES, B3 | 648 | 8,3% | 71,7% | 76% | 6,2% | 24% |
| **CES 2+1, B3 (mặc định)** | 648 | 7,8% | 67,7% | 75% | 6,3% | 32% |
| CES 1+2, B3 | 648 | 6,9% | 59,2% | 71% | 6,3% | 37% |
| LightGBM, B3 | 648 | 10,9% | 94,1% | 98% | 15,6% | 44% |
| LightGBM 2+1, B3 | 648 | 10,4% | 89,6% | 96% | 12,6% | 49% |
| CES, B1 | 216 | **18,0%** | 51,7% | 66% | 2,4% | 21% |
| LightGBM, B1 | 216 | **24,8%** | 71,5% | 85% | 4,7% | 30% |

(Mỗi tập kiểm thử có 25.000 dòng, 75 gian lận; B1 = 1 cảnh báo/công ty/tuần ≈ 8,6 cảnh báo/1.000 dòng. Precision tối đa có thể là 75/216 = 35% ở B1 và 75/648 = 12% ở B3.)

CES chỉ có 13 trọng số và 1 hằng số, đọc được: luật học 1,04; lệch lương 0,62; chi tiền mặt tự duyệt sát hạn mức 0,77; tự duyệt thiếu chứng từ lặp lại 0,45; lệch đơn giá (z) 0,31; NCC ngủ đông 0,24; các bộ khác dưới 0,1.

### 5.4. Tập niêm phong (chạy một lần, trung bình 3 thế giới)

| Cấu hình | Precision | Recall tất cả họ | Recall 9 họ đã biết | **Recall 3 họ mới** | Báo nhầm ca giống gian lận |
|---|---:|---:|---:|---:|---:|
| Luật tay, B3 | 4,0% | 28,9% | 34,5% | 6,3% | 3,5% |
| Kênh mới lạ, B3 | 4,4% | 31,9% | 33,8% | 23,8% | 6,5% |
| CES, B3 | 7,8% | 56,3% | 68,0% | 17,5% | 7,0% |
| **CES 2+1, B3 (mặc định)** | 7,4% | 53,3% | 64,0% | 17,5% | 7,0% |
| LightGBM 2+1, B3 | 11,6% | 83,3% | 90,9% | 58,7% | 10,9% |
| CES, B1 | 16,5% | 39,6% | 48,5% | 7,9% | 2,5% |
| LightGBM, B1 | 27,2% | 65,2% | 72,4% | 41,3% | 3,7% |

Theo từng họ mới (recall ở CES 2+1 / LightGBM 2+1): `price_creep` 43% / 76%; `off_cycle_payroll` 0% / 81%; `vendor_burst` 10% / 19%.

**Giải thích trung thực.** Tiêu chí chọn đặt trước (trung bình recall trong phân phối và họ chưa thấy, ràng buộc báo nhầm ≤ 10%) chọn CES 2+1. Tập niêm phong cho thấy LightGBM thắng về recall, kể cả trên họ mới, đổi lại báo nhầm 11–13% ở B3. Hai điều làm giảm giá trị của chiến thắng đó: (1) LightGBM và bộ sinh dữ liệu dùng chung cơ chế (ví dụ lương luôn trả ngày 28 nên mọi khoản lương lệch ngày dễ thấy; `off_cycle_payroll` 81% là điều này, không phải "hiểu gian lận"); (2) cả hai chỉ học từ dữ liệu tổng hợp. `vendor_burst` không phương pháp nào thấy (tối đa 19%).

### 5.5. Dữ liệu bên ngoài

- **DFKI** (nửa cuối 2024): danh sách phép thử bút toán một mình AP 0,083; ECOD 0,097; IF 0,064; autoencoder 0,122; IF + cờ phép thử 0,190; LightGBM 0,80–0,85 (vòng tròn: nhãn được chèn trong danh sách phép thử). ROC-AUC 0,85–0,99 trong khi AP thấp.
- **ERP Fraud Data** (huấn luyện không giám sát chỉ trên 2 lần chạy bình thường): AP ECOD 0,495 / 0,059 / 0,147; IF 0,459 / 0,050 / 0,117; autoencoder 0,144 / 0,147 / 0,212 (fraud_1/2/3). Có giám sát từ các lần chạy khác: 0,556 / 0,249 / 0,397. Bỏ kịch bản Invoice Kickback: AP 0,00–0,05. Không phương pháp nào thắng ổn định.

### 5.6. Vòng phản hồi (52 tuần, 5 seed; số dòng gian lận được cảnh báo trong 3 khe/công ty/tuần)

| Người duyệt sai | Không học | Nới ngưỡng (thiết kế cũ) | Học lại trọng số | + mẫu kiểm toán |
|---|---:|---:|---:|---:|
| 0% | 57,7 | 57,7 | **83,4** | 83,1 |
| 15% | 57,7 | 51,6 | **78,7** | 73,7 |
| 30% | 57,7 | 47,7 | 54,0 | 46,9 |

Học lại trọng số hữu ích tới khoảng 15% nhiễu; ở 30% nó tệ hơn không học vì khoảng 95% cảnh báo vốn là báo sai nên đảo nhãn tạo ra nhiều "gian lận giả" hơn gian lận thật. Mẫu kiểm toán ngẫu nhiên không giúp trong mô phỏng (chỉ làm tăng nhiễu), nên không bật mặc định. Khuyến nghị: nhãn dương cần hai người xác nhận; tách "cần thêm thông tin" khỏi "báo sai"; theo dõi bản học lại trên mẫu giữ riêng.

### 5.7. Đường ống đầu–cuối (thế giới 205, học trước trên 201–204)

| Hồ sơ | Cảnh báo | Hồ sơ theo thực thể | Precision | Recall | Vụ tìm thấy | Báo nhầm ca giống gian lận |
|---|---:|---:|---:|---:|---:|---:|
| `cold` | 642 | 475 | 4,0% | 34,7% | 44% | 5,4% |
| `precision` | 641 | 608 | 8,0% | 68,0% | 77% | 6,0% |
| `wide` | 640 | 617 | 9,8% | 84,0% | 92% | 12,4% |

Ví dụ hồ sơ đầu ra (rút gọn): *"Thông tin hoặc người đại diện NCC liên kết nhân viên | Tài khoản hoặc căn cước NCC trùng nhân viên — Dừng chi/kiểm tra ngay trong 24 giờ: đối chiếu hợp đồng, hóa đơn, người nhận tiền."* Lý do được xếp theo trọng số luật học, nên luật nhiễu (số tiền tròn, giờ lập) không đứng đầu hồ sơ có luật mạnh.

---

## 6. Điều không được tuyên bố

- Không tuyên bố bất kỳ precision/recall nào cho doanh nghiệp thật. Tần suất gian lận 0,3%, các họ, các mức khó, số tiền, mùa vụ đều là giả định của người thiết kế.
- Không tuyên bố CES hoặc LightGBM "phát hiện gian lận mới". Chúng chỉ chuyển giao trong phạm vi thế giới tổng hợp chia sẻ cơ chế.
- Các họ đã xem khi phát triển bộ phát hiện (`expense_padding`, `kickback_overpricing`, `payroll_padding`) không còn là "chưa thấy" đối với phần thiết kế EntityDeviation; chỉ ba họ niêm phong là kiểm thử thật.
- Tỷ lệ phát hiện sai bằng conformal/BH kiểm soát mức "giống bình thường của chính doanh nghiệp", không phải precision gian lận; gian lận có sẵn trong lịch sử bị coi là bình thường.

## 7. Dữ liệu thật cần thu thập (theo thứ tự ưu tiên)

1. **Hóa đơn điện tử XML theo dòng hàng** (mã hàng, đơn giá, số lượng, MST người bán) cho 3–5 doanh nghiệp đối tác: điều kiện cần để thấy mua đắt và leo thang giá.
2. Danh mục NCC và nhân viên có tài khoản ngân hàng, địa chỉ, điện thoại (đã chuẩn hóa) để chạy đối chiếu chéo.
3. Lịch lương, hợp đồng, ngày nghỉ việc (để chạy E1, E2, C4).
4. Nhật ký ai lập, ai duyệt, giờ duyệt từ phần mềm kế toán.
5. Sao kê ngân hàng (đối chiếu thu–chi, bắt khoản thu không ghi sổ).
6. Kết luận của người có chuyên môn cho một mẫu cảnh báo, để đo precision thật và huấn luyện lại.

## 8. Việc tiếp theo đề xuất

- Nối `review.html` với dữ liệu thật của đối tác và đo số phút xem mỗi cảnh báo.
- Thêm vào bộ sinh: ngày trả lương biến thiên (bỏ dấu hiệu lương luôn ngày 28), nhiều nhà cung cấp dịch vụ định kỳ, đơn hàng nhiều dòng hàng.
- Viết thêm họ niêm phong mới với seed mới trước mỗi lần phát hành.
- Giải quyết các luật còn mở của bạn bạn: A3, A4, A5, B1, B3 (mô tả khác triển khai) và C4, E2, F2, F3, F4 (thiếu nguồn dữ liệu).
- Kiểm tra pháp lý theo Nghị định 13/2023/NĐ-CP trước khi gắn cảnh báo với từng cá nhân.

## 9. Cần bạn xác nhận

- Tôi dùng `zipp.zip` (544 MB, tải 14/10), không phải `zip.zip` (39 KB, 13/08, là một ứng dụng web AI Studio không liên quan). Nếu bạn muốn tệp khác, cho tôi biết.
- Hồ sơ mặc định: `precision` hay `wide`? (xem mục 5.4).
- Có muốn tôi nối `review.html` vào giao diện duyệt của bạn bạn (`review_ui/`) hay giữ trang riêng?
