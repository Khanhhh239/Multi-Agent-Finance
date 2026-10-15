# Tài liệu tham khảo

Nhãn: **[Đ]** đã đọc nguồn gốc ở các phiên trước; **[T]** chỉ đọc tóm tắt hoặc trích dẫn; **[K]** kinh điển, dùng theo hiểu biết, chưa đọc lại. Chi tiết đối chiếu: [Phần 8](../07_tai_lieu_tham_khao/DIGITAL_ACCOUNTING_PART8_AGENT2_METHODS.md) và [METHODS.md](../06_ghi_chep_lam_viec/METHODS.md).

## 1. Phát hiện bất thường trên bút toán và ERP

| Tài liệu | Điều rút ra cho thiết kế |
|---|---|
| Schreyer và cộng sự 2017, *Detection of Anomalies in Large Scale Accounting Data using Deep Autoencoder Networks*, arXiv 1709.05254 [Đ] | Autoencoder trên bút toán, mỗi sổ cái một mạng; F1 chỉ 0,33 và 0,17 dù bất thường chèn là loại dễ nhất; bất thường thống kê không bằng gian lận |
| Gronewald và cộng sự (DFKI), *Data in Brief*, Zenodo 10.5281/zenodo.22014653 [Đ] | Kết hợp phép thử bút toán (JET) với học máy; JET một mình gắn cờ 20,7% bút toán; bất thường chèn nằm trong danh sách JET nên độ phủ 100% là vòng tròn; JET làm đặc trưng cho L4 |
| Tritscher và cộng sự 2022, ERP Fraud Data, arXiv 2206.04460 [Đ] | Bộ đối chiếu ngoài gần nhất |
| Bakumenko, Elragal 2022, *Systems* 10(5):130 [T] | So sánh IF và AE trên sổ cái; IF thường ít báo nhầm hơn |
| Baader, Krcmar 2018, *IJAIS* [T] | Cờ đỏ cộng khai phá quy trình giảm báo sai (ủng hộ hybrid; chưa cài khai phá quy trình) |
| AuditCopilot, arXiv 2512.02726 [T] | Mô hình ngôn ngữ trên sổ cái: nhãn giả, chưa đánh giá độ trung thực giải thích → chỉ để diễn giải, không để phát hiện |

## 2. Chuẩn đánh giá và lý thuyết

| Tài liệu | Điều rút ra |
|---|---|
| Han và cộng sự, **ADBench**, NeurIPS 2022, arXiv 2206.09426 [Đ] | 57 bộ, 30 thuật toán: không phương pháp không giám sát nào vượt trội; học sâu không giám sát kém phương pháp nông; 1% nhãn đủ để bán giám sát vượt |
| Li và cộng sự, **ECOD**, TKDE 2023, arXiv 2201.00382 [T] | Không tham số, đuôi ECDF, giải thích được |
| Liu, Ting, Zhou 2008 (Isolation Forest); Goldstein, Dengel 2012 (HBOS) [K] | Đường cơ sở |
| Ke và cộng sự 2017 (LightGBM) [K] | Mô hình có giám sát |
| Zhao, Hryniewicki 2018 (XGBOD) [K] | Dùng điểm không giám sát làm đặc trưng cho mô hình có giám sát (cơ sở của L4) |
| Tang và cộng sự, **GADBench**, NeurIPS 2023, arXiv 2306.12251 [T] | Cây tổng hợp với đặc trưng láng giềng thường thắng GNN → không dùng GNN giai đoạn đầu |
| Egressy và cộng sự, AAAI 2024, arXiv 2306.11586 [T] | GNN chỉ giúp ở mẫu rửa tiền nhiều bước |
| Das và cộng sự 2016, *Active Anomaly Discovery*, ICDM [T] | Học lại trọng số từ phản hồi với ngân sách hữu hạn |
| Bates, Candès và cộng sự 2023, *Testing for Outliers with Conformal p-values*, Annals of Statistics, arXiv 2104.08279 [T]; Barber và cộng sự 2023, arXiv 2202.13415 [T] | p-giá trị conformal cộng Benjamini–Hochberg kiểm soát FDR; cần dạng có trọng số khi trôi |
| Elkan, Noto 2008 (PU learning) [K] | Cơ sở H15 |
| Goix 2016, arXiv 1607.01152 [T] | Chỉ số không nhãn (Mass–Volume, Excess–Mass) cho dữ liệu thật chưa có nhãn |
| Durtschi, Hillison, Pacini 2004; Barney, Schulzke 2016; Cerasa và cộng sự 2022 [T] | Benford dễ báo nhầm ở mẫu nhỏ → chỉ chẩn đoán |
| Palguta, Pertold (mua sắm công, dồn giá trị dưới ngưỡng) [T] | Căn cứ luật sát ngưỡng; chỉ chứng minh thao túng |

## 3. Gian lận nghề nghiệp
- ACFE, *Occupational Fraud 2024: A Report to the Nations* [Đ].
- ACFE Fraud Tree (phân loại: tham nhũng, biển thủ tài sản, gian lận báo cáo tài chính) [T].

## 4. Pháp lý và chuẩn mực Việt Nam
- Nghị định 13/2023/NĐ-CP về bảo vệ dữ liệu cá nhân [T]: chưa đọc nội dung điều khoản; cần thẩm định pháp lý.
- Nghị định 80/2021/NĐ-CP tiêu chí DNNVV [T].
- Thông tư 133/2016/TT-BTC và Thông tư 200/2014/TT-BTC (chế độ kế toán) [K].
- Thông tư 96/2015/TT-BTC (chi phí được trừ, thanh toán không tiền mặt từ 20 triệu đồng) [T].

## 5. Không dùng và lý do
GNN (GraphSAGE, GAT): đồ thị SME nhỏ, GADBench không ủng hộ; TabPFN và mô hình nền cho dữ liệu bảng: chưa có bằng chứng trên sổ cái, chưa kiểm tra giấy phép; mô hình ngôn ngữ làm bộ phát hiện: kết quả không ổn định, rủi ro tiêm lệnh qua văn bản tự do; autoencoder LSTM, VAE: chưa đọc đủ.
