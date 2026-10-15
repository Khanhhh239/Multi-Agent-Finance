# Mô hình có giám sát và phương pháp lai

Mã: `agent2/methods.py` (L3, CES), `agent2/hybrid.py` (L4, cân bằng họ, hai tầng, Novelty), `agent2/eval_v4.py` (danh sách ứng viên).

## 1. L3: LightGBM trên đặc trưng gốc + baseline + luật
**Đầu vào:** 190 đặc trưng gốc + 31 baseline thực thể + 15 dấu hiệu đỏ v4 + 34 cột hit luật và 3 điểm luật.

**Huấn luyện (`Supervised`, `hybrid.LGBM`):**

| Tham số | Giá trị | Lý do |
|---|---|---|
| Số cây tối đa | 600, dừng sớm 60 vòng theo AP trên kiểm định | Chọn số cây bằng kiểm định, không dùng kiểm thử |
| Số lá | thử 7 và 15; chọn theo AP kiểm định | Mẫu dương nhỏ: cây nông |
| Tốc độ học | 0,05 | |
| `min_child_samples` | 10 | Cho phép nhóm dương nhỏ |
| `subsample`, `colsample_bytree` | 0,8; 0,6 | Giảm quá khớp |
| `reg_lambda` | 2,0 | |
| `scale_pos_weight` | `sqrt(âm / dương)` | Lấy căn để tránh quá cân bằng |
| Ngân sách chọn | AP trên kiểm định (nửa đầu 2025) | |

**Vì sao LightGBM:** ADBench [Đ]: chỉ 1% nhãn đủ để bán giám sát vượt phương pháp không giám sát tốt nhất; cây tổng hợp mạnh trên dữ liệu bảng; GADBench [T]: cây cộng đặc trưng láng giềng thường thắng GNN.

## 2. Các biến thể lai (mới trong phiên này; kết quả một phần)

| Mã | Ý tưởng | Cơ sở lập luận [N] | Trạng thái |
|---|---|---|---|
| **L4** | L3 + đầu ra của các bộ phát hiện không nhãn làm đặc trưng: từng đuôi EntityDeviation (cắt ở 12), hạng EntityDeviation, hạng autoencoder, hạng Isolation Forest, tất cả so với phân phối huấn luyện của công ty | Mô hình học khi nào tin từng bộ phát hiện; tương tự XGBOD (Zhao và Hryniewicki 2018 [K]) và "kết quả JET làm đặc trưng" (Gronewald và cộng sự [Đ]) | Chưa kết luận: P1 +2 đến 4 điểm so với L3 (trong sai số); P2 tốt hơn trên thế giới 411 |
| **-FB** (cân bằng họ) | Mỗi họ gian lận trong nhãn huấn luyện có tổng trọng số bằng nhau; dòng hợp lệ trọng số 1 | Họ phổ biến không lấn át họ hiếm; kỳ vọng tăng độ phủ kịch bản chưa thấy | P2 411: L3 52% → L3-FB 63%; P1 giảm nhẹ (2 đến 3 điểm ở 411) |
| **C-** (hai tầng, "trí nhớ") | Tầng 1 chấm từng dòng. Tầng 2 thêm, cho mỗi dòng, thống kê của 90 ngày trước của cùng người lập, người duyệt, nhà cung cấp, nhân viên, khách (hạng tối đa, số dòng hạng ≥ 0,99, hạng ≥ 0,95, số dòng) rồi chấm lại. Điểm tầng 1 trên tập huấn luyện được sinh bằng chéo gập theo khối thời gian (4 khối) để tầng 2 không học từ điểm trong mẫu | Gian lận lặp lại (ACFE: kéo dài hàng tháng); dòng thứ hai của một vụ nên bị nghi hơn dòng thứ nhất | **Chưa có lợi**: AP giảm 0,03 đến 0,12 so với L3; recall không đổi |
| **Novelty** | Kênh không nhãn: `max(hạng luật, hạng EntityDeviation)` (có biến thể thêm hạng autoencoder) | Giữ cửa cho kiểu mới | Có |
| **Chính sách 2+1** | Mỗi công ty mỗi tuần: 2 khe cho mô hình chính, 1 khe cho Novelty | Mô hình học trước bỏ qua bộ phát hiện chưa từng giúp ở họ đã học nên mù trước họ mới | Có (v3) |
| **max-rank** | Điểm = `max(hạng mô hình, hạng Novelty)` | Hợp nhất mềm | Có |

## 3. CES: chồng bằng chứng đã hiệu chỉnh [N]
**Mục đích.** Mô hình cực nhỏ, kiểm tra được, huấn luyện trên thế giới khác, áp cho công ty mới.
**Đầu vào (13 đặc trưng + hằng số):** giá trị quyết định của logistic L2 học trọng số luật (`RuleLogit`, `C = 0,3`, cân bằng lớp, huấn luyện **bỏ-một-thế-giới** để tầng trên không thấy điểm luật trong mẫu) và 12 điểm đuôi EntityDeviation đã cắt trong [0, 12], đo trên lịch sử không nhãn của chính công ty đích.
**Học:** logistic cân bằng lớp với chính quy hóa L2 **quanh một tiên nghiệm đơn điệu** (`fit_prior_logistic`): trọng số luật tiên nghiệm 1,0; mỗi đuôi thực thể 0,25; `λ = 0,02`; tối ưu L-BFGS-B. Lý do: mọi bộ phát hiện đều đơn điệu (lệch lớn hơn không bao giờ an toàn hơn), nên trọng số bắt đầu dương và dữ liệu có thể dịch nhưng không dễ ép về 0 như L2 thường.
**Kết quả [M] (chéo thế giới v3):** CES 2+1 ở B3: precision 7,8%, recall 68%, báo nhầm ca khó 6,3%, recall họ chưa thấy 32%; LightGBM 2+1: 10,4%, 90%, 12,6%, 49%. Tiêu chí chọn đặt trước chọn CES (báo nhầm thấp); LightGBM thắng về recall.
**Chưa làm:** huấn luyện lại trên v4 (`models/pretrained_v1.joblib` là v3).

## 4. Hợp nhất so với học hợp nhất
- Hợp nhất bằng hạng (`RankFusion`, Novelty): không cần nhãn, đơn giản, giải thích được, nhưng không tối ưu.
- Học hợp nhất (L4, CES): tối ưu theo nhãn nhưng phụ thuộc phân phối nhãn tổng hợp.
- Đề xuất: giữ cả hai trong chính sách 2+1; để kênh không học làm bảo hiểm.

## 5. Quy tắc chọn cấu hình (đăng ký trước, `AGENT2_WORKLOG.md` mục 14)
```
điểm(c) = trung bình trên 3 thế giới của (Recall@B3 P1 + trung bình Recall@B3 theo nhánh P2 + Recall@B3 P3) / 3
ràng buộc: báo nhầm ca khó P1 ≤ 20%
chọn cấu hình có điểm lớn nhất; chênh dưới 0,01 chọn cái đứng trước trong danh sách
chọn riêng cấu hình khởi đầu lạnh trong ba ứng viên không nhãn
```
Thực hiện bởi `agent2/select_v4.py` (chưa chạy).
