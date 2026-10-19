# LỘ TRÌNH TRIỂN KHAI: TRỢ LÝ PHÁT HIỆN GIAN LẬN NỘI BỘ CHO DN VỪA VÀ NHỎ (SME) TẠI VIỆT NAM

> **Quy mô dự án:** 18 tháng (chia thành 5 giai đoạn)  
> **Nguồn lực giả định:** Đội ngũ tinh gọn gồm 5–7 thành viên (1 Lead/PM, 2 Data/Backend, 1–2 ML/AI, 1 Frontend/Product, 1 Chuyên viên Kế toán/Kiểm toán)  
> **Phương pháp quản lý:** Agile/Scrum theo chu kỳ Sprint 2–4 tuần

---

## 1. NGUYÊN TẮC CỐT LÕI (CORE PRINCIPLES)

1. **Tránh quá tải cảnh báo (Alert Fatigue):** Mọi giai đoạn phải vượt qua một *Cổng chất lượng (Quality Gate)* khắt khe. Tỷ lệ cảnh báo sai (False Positive) phải được kiểm soát trước khi mở rộng phạm vi.
2. **Khả năng giải thích quan trọng hơn độ phức tạp:** Doanh nghiệp nhỏ cần hiểu *tại sao* một nghiệp vụ bị nghi ngờ. Lớp quy tắc tất định luôn đóng vai trò nòng cốt, học máy (ML/GNN) chỉ đóng vai trò bổ trợ và xếp hạng ưu tiên.
3. **Cơ chế chạy im lặng (Shadow Mode):** Dữ liệu kế toán SME tại Việt Nam có dung lượng nhỏ (vài trăm đến vài nghìn bút toán/tháng) và dễ lẫn lỗi nhập liệu. Các thuật toán học máy (Autoencoder, GNN) bắt buộc phải chạy ngầm từ 2–3 tháng để học mẫu chuẩn trước khi được phép phát cảnh báo ra giao diện người dùng.
4. **Bảo mật và an toàn dữ liệu:** Tuân thủ chặt chẽ Nghị định 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân; thông tin lương, nhân sự và đối tác phải được mã hóa và ẩn danh hóa phù hợp.

---

## 2. MA TRẬN TỔNG QUAN CÁC GIAI ĐOẠN

| Giai đoạn | Thời gian | Mục tiêu trọng tâm | Cổng chất lượng chuyển tiếp (Quality Gate) |
| :--- | :---: | :--- | :--- |
| **Giai đoạn 0: Nền tảng & Bản địa hóa** | Tháng 0–2 (8 tuần) | Hiểu quy trình thực tế, thiết kế lược đồ CDM, bộ dữ liệu mô phỏng | Pipeline ETL nạp mượt mà dữ liệu của 3–5 DN; tỷ lệ thiếu dữ liệu $< 3\%$ |
| **Giai đoạn 1: MVP Quy tắc & Hàng đợi** | Tháng 2–5 (14 tuần) | Lớp tất định (ISA 240), đồ thị NetworkX, UI Case Management | Kế toán trưởng pilot xác nhận $\ge 70\%$ cảnh báo mẫu là hữu ích |
| **Giai đoạn 2: Học máy bổ trợ & Điều phối** | Tháng 5–8 (13 tuần) | Autoencoder (Shadow mode), SHAP giải thích tiếng Việt, Ensemble | Giảm $\ge 25\%$ cảnh báo giả so với chỉ dùng quy tắc đơn lẻ |
| **Giai đoạn 3: Pilot thực tế & Tối ưu** | Tháng 8–12 (17 tuần) | Triển khai thực địa với 3–5 DN, hoàn thiện onboarding tự động | Người dùng xử lý thường xuyên ($> 60\%$ retention); Precision $\ge 40\%$ |
| **Giai đoạn 4: GNN & Mở rộng quy mô** | Tháng 12–18 (26 tuần) | GraphSAGE/GAT (có điều kiện), chống trôi dữ liệu (Drift), SaaS | GNN chứng minh cải thiện $\ge 15\%$ Recall so với đồ thị tất định |

---

## 3. CHI TIẾT CÁC SPRINT TRIỂN KHAI

### Giai đoạn 0: Nền tảng & Bản địa hóa dữ liệu (Tháng 0 – 2)

```
[Tuần 1-2: Khảo sát & CDM] ──> [Tuần 3-4: ETL & Parsing] ──> [Tuần 5-6: Synthetic Data] ──> [Tuần 7-8: Pilot Onboarding]
```

#### Sprint 0.1: Khảo sát thực địa, khung pháp lý & Lược đồ dữ liệu chuẩn (CDM)
* **Thời gian:** Tuần 1 – Tuần 2
* **Nhiệm vụ:**
  - [ ] Phỏng vấn 5–10 kế toán trưởng và chủ doanh nghiệp SME về quy trình duyệt chi, hạn mức và các hành vi thông đồng phổ biến.
  - [ ] Xây dựng lược đồ bảng dữ liệu chuẩn **Common Data Model (CDM)**: Bảng Sổ nhật ký chung (General Ledger), Danh mục Khách hàng/Nhà cung cấp, Bảng lương/Nhân viên, Hóa đơn điện tử.
  - [ ] Rà soát pháp lý: Soạn thảo Thỏa thuận bảo mật (NDA) và quy định xử lý dữ liệu theo Nghị định 13/2023/NĐ-CP (quy định về ẩn danh thông tin CCCD, mức lương).
* **Phân công:**
  - *Lead + Kế toán:* Phỏng vấn, tài liệu hóa nghiệp vụ, soạn NDA.
  - *Data/Backend:* Thiết kế schema cơ sở dữ liệu CDM (PostgreSQL).
* **Đầu ra (Deliverables):** Tài liệu đặc tả CDM v1.0; 01 mẫu NDA tiêu chuẩn; Báo cáo phân tích 10 kẽ hở kiểm soát nội bộ phổ biến.

#### Sprint 0.2: Bộ chuyển đổi ETL & Làm sạch dữ liệu kế toán Việt Nam
* **Thời gian:** Tuần 3 – Tuần 4
* **Nhiệm vụ:**
  - [ ] Xây dựng parser đọc và chuẩn hóa file Excel/CSV xuất từ phần mềm kế toán phổ biến: MISA, FAST, Bravo.
  - [ ] Xây dựng module đọc hóa đơn điện tử định dạng XML (chuẩn Thông tư 78 / Tổng cục Thuế).
  - [ ] Xử lý tiếng Việt: Chuẩn hóa unicode dựng sẵn/tổ hợp, loại bỏ khoảng trắng, chuẩn hóa định dạng Mã số thuế (MST) và số tài khoản ngân hàng.
* **Phân công:**
  - *Data/Backend:* Xây dựng pipeline ingest, bộ lọc regex làm sạch dữ liệu.
  - *Frontend:* Màn hình tải file dữ liệu kéo-thả và hiển thị danh sách lỗi định dạng.
* **Đầu ra:** Pipeline ETL nạp và chuyển đổi dữ liệu thô từ 3 phần mềm kế toán sang CDM.

#### Sprint 0.3: Xây dựng bộ dữ liệu tổng hợp (Synthetic Dataset)
* **Thời gian:** Tuần 5 – Tuần 6
* **Nhiệm vụ:**
  - [ ] Viết script sinh dữ liệu mô phỏng gồm $50.000$ đến $100.000$ bút toán nền thông thường.
  - [ ] Cài cắm 6 kịch bản gian lận có nhãn mặt đất (Ground Truth):
    1. *Nhà cung cấp ma:* Đối tác nhận tiền trùng thông tin tài khoản/SĐT/địa chỉ với nhân viên nội bộ.
    2. *Chia nhỏ chứng từ:* Các khoản chi sát dưới hạn mức phê duyệt lập trong khoảng thời gian ngắn.
    3. *Thanh toán trùng lặp:* Cùng số tiền, cùng nhà cung cấp, lặp lại hóa đơn thanh toán.
    4. *Bút toán điều chỉnh cuối kỳ:* Người lập đồng thời là người duyệt, ghi nhận vào ngày lễ/cuối tuần.
    5. *Hóa đơn rủi ro:* Doanh nghiệp phát hành hóa đơn thuộc diện ngưng hoạt động hoặc bỏ trốn.
    6. *Tạm ứng kéo dài:* Các khoản tạm ứng không hoàn ứng đúng hạn hoặc xóa sổ nợ mập mờ.
* **Phân công:**
  - *ML/AI:* Xây dựng generator sinh dữ liệu chuỗi thời gian bút toán kèm nhiễu thực tế.
  - *Kế toán:* Kiểm tra tính hợp lý của các cặp định khoản Nợ/Có theo Thông tư 200/133.
* **Đầu ra:** File dataset tổng hợp chuẩn hóa phục vụ đo kiểm thuật toán (`synthetic_fraud_v1.parquet`).

#### Sprint 0.4: Pilot Onboarding ban đầu & Đánh giá Cổng chất lượng 0
* **Thời gian:** Tuần 7 – Tuần 8
* **Nhiệm vụ:**
  - [ ] Ký thỏa thuận hợp tác thử nghiệm (Pilot Agreement) với 3–5 doanh nghiệp đối tác.
  - [ ] Tiếp nhận dữ liệu lịch sử (12–24 tháng) đã ẩn danh từ các đơn vị này và chạy kiểm thử pipeline ETL.
* **Cổng chất lượng 0 (Gate 0):**
  - [x] ETL xử lý thành công $100\%$ các file xuất mẫu của 3 DN pilot mà không bị treo lỗi hệ thống.
  - [x] Tỷ lệ dữ liệu bị thiếu trường bắt buộc sau khi chuẩn hóa $< 3\%$.

---

### Giai đoạn 1: MVP Lớp quy tắc tất định & Hàng đợi xử lý (Tháng 2 – 5)

#### Sprint 1.1: Xây dựng Rule Engine tất định (Ánh xạ ISA/VSA 240)
* **Thời gian:** Tuần 9 – Tuần 11
* **Nhiệm vụ:**
  - [ ] Xây dựng thư viện gồm 15–20 quy tắc cứng độc lập:
    - Bút toán ghi ngoài giờ làm việc, cuối tuần hoặc các dịp nghỉ lễ lớn.
    - Vi phạm phân tách nhiệm vụ (Segregation of Duties): Người tạo bút toán kiêm người duyệt.
    - Hóa đơn đầu vào từ doanh nghiệp thuộc danh sách rủi ro cao của cơ quan thuế.
    - Chi tiền mặt vượt hạn mức quy định (ví dụ các khoản trên 20 triệu đồng theo quy định khấu trừ thuế GTGT).
    - Chuỗi giao dịch lặp lại có số tiền sát ngưỡng thẩm quyền phê duyệt.
* **Phân công:**
  - *Data/Backend:* Phát triển Rule Engine module hóa theo cơ chế plugin.
  - *Kế toán:* Biên soạn tài liệu chi tiết về cơ sở kế toán cho từng quy tắc vi phạm.
* **Đầu ra:** Module `RuleEngine` trả về mã lỗi, mức độ nghiêm trọng và metadata kèm theo.

#### Sprint 1.2: Đồ thị quan hệ thực thể tất định bằng NetworkX
* **Thời gian:** Tuần 12 – Tuần 14
* **Nhiệm vụ:**
  - [ ] Xây dựng đồ thị đa phân: Các nút gồm `Nhân viên`, `Nhà cung cấp`, `Tài khoản ngân hàng`, `SĐT`, `Địa chỉ`, `MST`.
  - [ ] Viết thuật toán truy vấn thành phần liên thông và đường đi:
    - Phát hiện nhà cung cấp có cùng tài khoản thụ hưởng hoặc số điện thoại với nhân viên.
    - Phát hiện mạng lưới các nhà cung cấp khác nhau nhưng dùng chung địa chỉ đăng ký kinh doanh hoặc chung tài khoản ngân hàng.
* **Phân công:**
  - *ML/AI:* Thiết kế cấu trúc đồ thị NetworkX trong bộ nhớ và module trích xuất mạng lưới liên quan.
  - *Backend:* Đồng bộ dữ liệu quan hệ vào đồ thị theo lô định kỳ.
* **Đầu ra:** Module trích xuất đồ thị quan hệ trả về định dạng JSON hỗ trợ hiển thị trực quan.

#### Sprint 1.3: Thống kê ngưỡng động (Dynamic Thresholds)
* **Thời gian:** Tuần 15 – Tuần 17
* **Nhiệm vụ:**
  - [ ] Thay thế ngưỡng tĩnh cứng nhắc bằng chỉ số thống kê thích nghi theo từng doanh nghiệp:
    - Ngưỡng giao dịch bất thường tính theo phân vị (ví dụ 95th, 99th) hoặc độ lệch chuẩn $\mu + k\sigma$ dựa trên lịch sử từng tài khoản chi phí cụ thể.
    - Tính toán ngưỡng dao động dựa trên chu kỳ tháng (ngày chốt lương, ngày thanh toán công nợ).
* **Phân công:**
  - *ML/AI:* Viết module tính toán phân phối thống kê theo cửa sổ trượt (Rolling Window 30/60/90 ngày).
* **Đầu ra:** Bảng tham số ngưỡng động tự cập nhật riêng biệt cho từng doanh nghiệp.

#### Sprint 1.4: Giao diện Hàng đợi (Case Management UI) & Kênh thông báo
* **Thời gian:** Tuần 18 – Tuần 20
* **Nhiệm vụ:**
  - [ ] Phát triển giao diện web Case Management:
    - Thẻ hồ sơ nghi vấn hiển thị tóm tắt tình huống bằng ngôn ngữ kế toán dễ hiểu.
    - Sơ đồ tương tác đồ thị trực quan (sử dụng Cytoscape.js hoặc D3.js).
    - Thao tác một chạm: "Xác nhận nghi vấn" / "Bỏ qua, hợp lệ" kèm lý do nhanh.
  - [ ] Thiết lập *Ngân sách cảnh báo (Alert Budget)*: Khống chế tối đa 5–10 trường hợp ưu tiên nhất/ngày để tránh quá tải người dùng.
  - [ ] Tích hợp Zalo OA và Email: Gửi thông báo tóm tắt tuần hoặc thông báo khi có case mức độ cao.
* **Phân công:**
  - *Frontend:* Thiết kế giao diện Case Management và trực quan hóa sơ đồ mạng lưới.
  - *Backend:* Tích hợp Webhook Zalo OA, dịch vụ gửi email và logic điều phối ngân sách cảnh báo.
* **Đầu ra:** Giao diện Web tương tác hoàn chỉnh kết nối với luồng thông báo Zalo/Email.

#### Sprint 1.5: Kiểm thử khô trên dữ liệu Pilot & Cổng chất lượng 1
* **Thời gian:** Tuần 21 – Tuần 22
* **Nhiệm vụ:**
  - [ ] Nạp toàn bộ dữ liệu lịch sử của 3–5 DN pilot vào hệ thống và kích hoạt toàn bộ lớp quy tắc + đồ thị ở môi trường nội bộ.
  - [ ] Tổ chức buổi làm việc với Kế toán trưởng các đơn vị để rà soát danh sách cảnh báo.
* **Cổng chất lượng 1 (Gate 1):**
  - [x] Kế toán trưởng xác nhận ít nhất $70\%$ cảnh báo sinh ra là hợp lý và cần kiểm tra lại nghiệp vụ.
  - [x] Không phát sinh bất kỳ lỗi logic cơ bản nào về cân đối kế toán (Nợ = Có).

---

### Giai đoạn 2: Lớp học máy bổ trợ & Tích hợp điều phối (Tháng 5 – 8)

#### Sprint 2.1: Triển khai Autoencoder ở chế độ im lặng (Shadow Mode)
* **Thời gian:** Tuần 23 – Tuần 25
* **Nhiệm vụ:**
  - [ ] Xây dựng mô hình Autoencoder phát hiện bất thường bút toán (theo Schreyer et al.):
    - Vector hóa các trường: Tài khoản Nợ/Có (Embedding/One-hot), log-transform số tiền, chu kỳ ngày/tháng.
    - Cấu trúc mạng Encoder-Decoder nén và tái tạo vector bút toán; dùng sai số tái tạo (Reconstruction Error) làm điểm bất thường.
  - [ ] Thiết lập **Shadow Mode**: Hệ thống chạy ngầm đánh giá bút toán hàng ngày, ghi nhận điểm số nhưng chưa gửi cảnh báo tới người dùng.
* **Phân công:**
  - *ML/AI:* Xây dựng mô hình và pipeline huấn luyện trên dữ liệu tổng hợp + dữ liệu lịch sử sạch.
  - *Backend:* Thiết lập hàng đợi xử lý ngầm (Celery/Redis) chạy batch inference định kỳ ban đêm.
* **Đầu ra:** Service Autoencoder chạy ổn định ở chế độ ngầm và sinh log điểm số bất thường.

#### Sprint 2.2: Bộ tổng hợp điểm số (Ensemble Scoring)
* **Thời gian:** Tuần 26 – Tuần 28
* **Nhiệm vụ:**
  - [ ] Xây dựng công thức tính điểm tổng hợp đa tầng:
    $$\text{Score} = w_1 \cdot \text{Rule\_Score} + w_2 \cdot \text{Graph\_Score} + w_3 \cdot \text{AE\_Score}$$
  - [ ] Thiết lập cơ chế cộng hưởng tín hiệu:
    - *Ưu tiên 1:* Bút toán vi phạm quy tắc nghiêm trọng (phát cảnh báo ngay lập tức).
    - *Ưu tiên 2:* Bút toán vi phạm quy tắc mức nhẹ nhưng có điểm bất thường từ Autoencoder hoặc liên đới đồ thị cao.
* **Phân công:**
  - *ML/AI + PM:* Tinh chỉnh trọng số và phân loại ngưỡng rủi ro (Thấp, Trung bình, Cao, Khẩn cấp).
* **Đầu ra:** Điểm rủi ro tổng hợp phản ánh chính xác thứ tự ưu tiên xử lý trong Case Management.

#### Sprint 2.3: Bộ giải thích nguyên nhân bằng SHAP sang tiếng Việt
* **Thời gian:** Tuần 29 – Tuần 31
* **Nhiệm vụ:**
  - [ ] Trích xuất các thuộc tính đóng góp lớn nhất vào sai số tái tạo bằng thư viện SHAP.
  - [ ] Xây dựng từ điển mẫu câu diễn đạt tự nhiên bằng thuật ngữ kế toán quen thuộc:
    - *Đầu vào SHAP:* `Feature: Amount > P99 (+0.32)`, `Account: 642 (+0.25)`, `Time: Sunday (+0.21)`
    - *Câu diễn đạt:* "Khoản chi thuộc TK 642 (Chi phí quản lý) có giá trị cao bất thường so với mức trung bình và được lập vào ngày Chủ Nhật."
  - [ ] Ẩn toàn bộ thuật ngữ chuyên sâu về AI/ML khỏi giao diện người dùng cuối.
* **Phân công:**
  - *ML/AI:* Trích xuất SHAP values theo từng bản ghi.
  - *Kế toán + Frontend:* Xây dựng mẫu câu diễn giải và giao diện hiển thị lý do vi phạm.
* **Đầu ra:** Khung giải thích lý do gồm 2–3 gạch đầu dòng rõ ràng, dễ hiểu cho người làm kế toán.

#### Sprint 2.4: Vòng phản hồi một chạm & Cổng chất lượng 2
* **Thời gian:** Tuần 32 – Tuần 35
* **Nhiệm vụ:**
  - [ ] Ghi nhận hành vi tương tác khi người dùng bấm "Bỏ qua / Báo động sai" kèm lựa chọn nguyên nhân nhanh (ví dụ: "Đã có duyệt phê chuẩn riêng", "Nghiệp vụ mùa vụ").
  - [ ] Thiết lập cơ chế tự động hạ trọng số cảnh báo (Dampening): Giảm nhẹ điểm số đối với các trường hợp tương tự tại riêng doanh nghiệp đó, giới hạn mức giảm tối đa $30\%$ để tránh làm mất độ nhạy phát hiện.
* **Cổng chất lượng 2 (Gate 2):**
  - [x] Trên bộ dữ liệu có nhãn: Lớp Ensemble giúp giảm ít nhất $25\%$ số lượng cảnh báo sai so với khi chỉ chạy lớp quy tắc đơn thuần.
  - [x] Giữ nguyên khả năng phát hiện $100\%$ các tình huống gian lận trọng yếu đã được gài sẵn.

---

### Giai đoạn 3: Triển khai Pilot thực tế & Đo lường hiệu quả (Tháng 8 – 12)

```
Tuần 36-39: Bật Alert thật ──> Tuần 40-44: Review & Tinh chỉnh ──> Tuần 45-48: Gán nhãn thực địa ──> Tuần 49-52: Tự động Onboarding
```

#### Sprint 3.1: Kích hoạt cảnh báo thực tế tại DN Pilot
* **Thời gian:** Tuần 36 – Tuần 39
* **Nhiệm vụ:**
  - [ ] Mở luồng gửi cảnh báo tự động thực tế hàng ngày tới Zalo/Email của Kế toán trưởng hoặc Chủ doanh nghiệp.
  - [ ] Phân công kỹ sư trực kỹ thuật, hỗ trợ trực tiếp 1-1 trong 2 tuần đầu qua nhóm trao đổi riêng.
* **Phân công:** Cả đội phối hợp trực vận hành và xử lý phản ánh dữ liệu.

#### Sprint 3.2: Rà soát định kỳ & Tối ưu ngưỡng cảnh báo
* **Thời gian:** Tuần 40 – Tuần 44
* **Nhiệm vụ:**
  - [ ] Tổ chức họp rà soát định kỳ 2 tuần/lần với từng doanh nghiệp pilot để phân tích các hồ sơ bị gắn nhãn "Bỏ qua".
  - [ ] Tự động thắt chặt ngưỡng lọc cảnh báo nếu doanh nghiệp nhận quá 15 thông báo/tuần và tỷ lệ xử lý thực tế dưới $20\%$.
* **Phân công:** PM và Chuyên viên Kế toán ghi nhận phản hồi, ML Engineer điều chỉnh lại phân vị ngưỡng lọc.

#### Sprint 3.3: Thu thập dữ liệu thực tế đã gán nhãn
* **Thời gian:** Tuần 45 – Tuần 48
* **Nhiệm vụ:**
  - [ ] Tổng hợp phản hồi từ thao tác của người dùng thành kho dữ liệu chuẩn: Phân loại thành "Gian lận/Thất thoát thật", "Lỗi nhập liệu vô ý", "Giao dịch ngoại lệ hợp lệ".
  - [ ] Sử dụng tập dữ liệu này để tái đánh giá độ chính xác thực tế của hệ thống.
* **Đầu ra:** Bộ dữ liệu kiểm chuẩn từ thực tế doanh nghiệp SME Việt Nam (`realworld_benchmark.parquet`).

#### Sprint 3.4: Tự phục vụ Onboarding & Đánh giá Cổng chất lượng 3
* **Thời gian:** Tuần 49 – Tuần 52
* **Nhiệm vụ:**
  - [ ] Tự động hóa quy trình kết nối dữ liệu: Doanh nghiệp chỉ cần tải lên file sao kê/sổ nhật ký mẫu, hệ thống tự động nhận diện cột và ánh xạ về CDM trong vòng 15 phút mà không cần can thiệp kỹ thuật.
* **Cổng chất lượng 3 (Gate 3):**
  - [x] Tỷ lệ người dùng duy trì mở và xử lý cảnh báo sau 3 tháng đạt $> 60\%$.
  - [x] Tỷ lệ cảnh báo được xác nhận là "bất thường thực sự cần xem xét" (Precision) đạt $\ge 40\%$.
  - [x] Thời gian xử lý trung bình cho mỗi hồ sơ cảnh báo dưới 3 phút.

---

### Giai đoạn 4: Đồ thị nâng cao (GNN), Chống trôi dữ liệu & Thương mại hóa (Tháng 12 – 18)

#### Sprint 4.1: Nghiên cứu đối đầu mạng nơ-ron đồ thị (GraphSAGE / GAT)
* **Thời gian:** Tuần 53 – Tuần 57
* **Nhiệm vụ:**
  - [ ] Thử nghiệm mô hình GraphSAGE / GAT để phát hiện các mối liên hệ lòng vòng qua nhiều tầng trung gian.
  - [ ] **Tiêu chí đối đầu bắt buộc:** So sánh hiệu quả giữa GNN và thuật toán duyệt đường đi của NetworkX trên tập dữ liệu thực tế thu thập từ giai đoạn Pilot.
  - [ ] *Quy tắc dừng (Kill-switch):* Nếu GNN không tăng được ít nhất $15\%$ độ bao phủ (Recall) hoặc khiến thời gian xử lý tăng quá 5 lần, nhóm sẽ dừng áp dụng GNN và tiếp tục duy trì đồ thị tất định để tiết kiệm chi phí tính toán.
* **Phân công:** ML/AI Engineer nghiên cứu và chạy benchmark mô hình trên PyTorch Geometric/DGL.

#### Sprint 4.2: Tích hợp GNN vào hệ thống & Cài đặt cờ tắt/bật (Feature Flag)
* **Thời gian:** Tuần 58 – Tuần 62
* **Nhiệm vụ:**
  - [ ] Nếu GNN vượt qua tiêu chí ở Sprint 4.1: Đưa mô hình vào hệ thống như một lớp tín hiệu bổ trợ (không thay thế đồ thị tất định).
  - [ ] Thiết lập cơ chế ngắt khẩn cấp (Kill-switch): Cho phép tắt tính toán GNN ngay lập tức bằng cờ cấu hình (`ENABLE_GNN=False`) khi tài nguyên máy chủ vượt ngưỡng hoặc phát sinh lỗi suy luận.
* **Đầu ra:** Pipeline dự đoán kết hợp có cơ chế ngắt dự phòng an toàn.

#### Sprint 4.3: Giám sát trôi dữ liệu (Data Drift) & Tự thích nghi
* **Thời gian:** Tuần 63 – Tuần 68
* **Nhiệm vụ:**
  - [ ] Thiết lập module cảnh báo trôi phân phối dữ liệu (sử dụng chỉ số PSI - Population Stability Index hoặc kiểm định KS):
    - Nhận biết các biến động theo mùa (ví dụ: giai đoạn chi thưởng Tết, đợt quyết toán thuế cuối năm).
    - Tự động nới lỏng tạm thời các ngưỡng cảnh báo trong giai đoạn cao điểm để tránh gây phiền hà.
  - [ ] Xây dựng quy trình tự động cập nhật trọng số (Retraining Pipeline) định kỳ hàng quý dựa trên các phản hồi đã được phê duyệt.
* **Đầu ra:** Dashboard giám sát độ ổn định dữ liệu và lịch trình tự động tái huấn luyện mô hình.

#### Sprint 4.4: Hoàn thiện giải pháp SaaS đa khách hàng & Tích hợp kênh phân phối
* **Thời gian:** Tuần 69 – Tuần 78
* **Nhiệm vụ:**
  - [ ] Hoàn thiện kiến trúc Multi-tenant: Cách ly hoàn toàn dữ liệu giữa các doanh nghiệp khách hàng.
  - [ ] Thiết kế các gói dịch vụ linh hoạt theo tháng:
    - *Gói Cơ bản:* Lớp quy tắc tất định + Phân tích đồ thị cơ bản.
    - *Gói Nâng cao:* Bao gồm mô hình học máy bổ trợ + Giải thích bằng SHAP + Tự thích nghi ngưỡng.
  - [ ] Xây dựng cổng phân quyền dành riêng cho các Công ty dịch vụ kế toán / Đại lý thuế (cho phép quản lý nhiều khách hàng trên một giao diện thống nhất).
* **Đầu ra:** Sản phẩm thương mại hoàn chỉnh sẵn sàng cung cấp qua kênh đại lý thuế và dịch vụ kế toán.

---

## 4. MA TRẬN PHÂN CÔNG NGUỒN LỰC (RACI THEO VAI TRÒ)

| Vai trò | Giai đoạn 0 (Nền tảng) | Giai đoạn 1 (MVP Quy tắc) | Giai đoạn 2 (Học máy bổ trợ) | Giai đoạn 3 (Pilot thực tế) | Giai đoạn 4 (GNN & Scale) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Tech Lead / PM (1 người)** | Thiết kế kiến trúc tổng thể, ký kết NDA | Giám sát tiến độ, kiểm duyệt logic quy tắc | Đánh giá ma trận trọng số Ensemble | Điều phối pilot, làm việc với DN | Đánh giá Benchmark GNN, chốt roadmap kinh doanh |
| **Data / Backend (2 người)** | Xây dựng pipeline ETL, chuẩn hóa CDM | Phát triển Rule Engine, tích hợp NetworkX | Pipeline chạy ngầm ban đêm, tính SHAP | Tối ưu bảo mật, tự động hóa onboarding | Hoàn thiện kiến trúc Multi-tenant SaaS |
| **ML / AI Engineer (1–2 người)** | Sinh dữ liệu mô phỏng 6 kịch bản | Tính toán ngưỡng động thống kê | Huấn luyện Autoencoder, ánh xạ SHAP | Phân tích dữ liệu phản hồi thực tế | Thử nghiệm đối đầu GNN, chống trôi dữ liệu |
| **Frontend / Product (1 người)** | Giao diện nạp file, kiểm tra lỗi dữ liệu | Màn hình Case Management, hiển thị đồ thị | Thẻ tóm tắt SHAP, nút phản hồi 1-chạm | Tối ưu trải nghiệm thao tác trên di động | Dashboard dành riêng cho đại lý kế toán |
| **Kế toán / Kiểm toán (1 người)** | Khảo sát thực địa, chuẩn hóa tài khoản | Biên soạn logic 20 quy tắc theo VSA 240 | Xây dựng bộ mẫu câu giải thích nghiệp vụ | Tham gia họp review, thẩm định hồ sơ nghi vấn | Rà soát cập nhật theo quy định thuế mới |

---

## 5. QUẢN TRỊ RỦI RO VÀ GIẢI PHÁP ỨNG PHÓ

```
                    ┌─────────────────────────┐
                    │  Nguy cơ báo động giả?  │
                    └────────────┬────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
       [Ngắn hạn: Alert Budget]        [Dài hạn: Ngưỡng động &]
       [Chỉ gửi tối đa 5-10 case/ngày]  [Học từ phản hồi người dùng]
```

1. **Rủi ro quá nhiều báo động giả (False Alarms):**
   * *Giải pháp:* Áp dụng ngân sách cảnh báo (Alert Budget); chạy ngầm Autoencoder (Shadow mode); tự động điều chỉnh ngưỡng dựa trên tương tác thực tế của người dùng.
2. **Dữ liệu kế toán SME thiếu chuẩn hóa, nhiều lỗi nhập tay:**
   * *Giải pháp:* Đầu tư bộ chuyển đổi ETL mạnh mẽ ngay từ Giai đoạn 0; cung cấp báo cáo đo lường "Độ sạch của dữ liệu" trước khi kích hoạt quét gian lận.
3. **Cảnh báo gây hiểu lầm hoặc ảnh hưởng tiêu cực tới nhân viên:**
   * *Giải pháp:* Sử dụng câu từ trung tính mang tính gợi mở nghiệp vụ (ví dụ: *"Bút toán cần đối chiếu chứng từ gốc"* thay vì kết luận *"Hành vi gian lận"*); lưu lại vết truy cập và xử lý hồ sơ.
4. **Nguy cơ rò rỉ dữ liệu tài chính nhạy cảm:**
   * *Giải pháp:* Mã hóa dữ liệu ở trạng thái lưu trữ và truyền tải; phân quyền truy cập chi tiết; thông báo qua Zalo chỉ mang tính chất nhắc việc, không đính kèm chi tiết số tiền hay danh tính cá nhân.
5. **Chính chủ doanh nghiệp hoặc lãnh đạo là đối tượng thực hiện gian lận:**
   * *Giải pháp:* Cung cấp tùy chọn cấu hình kênh gửi thông báo trực tiếp tới Ban kiểm soát, Cổ đông lớn hoặc Hội đồng quản trị.