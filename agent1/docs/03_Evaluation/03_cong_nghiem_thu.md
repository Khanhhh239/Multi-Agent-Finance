# 3. Cổng nghiệm thu (GO / NO-GO)

> **Bảng trạng thái lịch sử ngày 15/10/2026.** Giữ ngưỡng và kết quả tại thời điểm lập; không dùng cột trạng thái bên dưới để kết luận hiện nay. Đọc [GATES_CURRENT.md](GATES_CURRENT.md) và CSV bằng chứng tương ứng.

Ngưỡng là **đề xuất thiết kế** (không có nguồn bên ngoài), đặt trước khi xem kết quả tập kiểm tra giữ lại. Trạng thái
cập nhật ngày 15/10/2026 từ `outputs/` — "CHƯA ĐO" nghĩa là mã có, thí nghiệm chưa chạy xong.

Kí hiệu: ✅ đạt · 🟡 đạt một phần/biên · ❌ không đạt · ⏳ chưa đo.

| Cổng | Nhiệm vụ | Điều kiện | Bằng chứng | Trạng thái |
|---|---|---|---|---|
| **G1** | T1 | WAPE dòng thu 1–4 tuần ≤ 0,70 × B1 (giảm ≥30%) trên ≥2 điểm gốc rolling | `src`: 0,444 vs 1,408 (−68%); 0,403 vs 1,080 (−63%) | ✅ [Tổng hợp] |
| **G2** | T1 | IBS_13w ≤ 0,80 × B1 | 0,121 vs 0,345; 0,105 vs 0,267 | ✅ [Tổng hợp] |
| **G3** | T1 | cov80 ∈ [75%, 85%] | 88,5% và 85,7% (quá thận trọng) | 🟡 lệch dương |
| **G4** | T1 | ECE@4w ≤ 0,05 | 0,061 (2023-07), 0,013 (2024-07) | 🟡 |
| **G5** | T1 thật | MAE P50 ≤ 0,90 × B1 trên AR thật | Customer Invoices: 2,29 vs 2,77 (−17%) bằng ensemble; DH-GBM đơn 2,53 (−9%) | ✅ [Thật] |
| **G6** | T1 thật | Pinball ≤ B1d (mốc phân vị theo khách) trên ≥2 bộ thật | Customer Invoices ✅ (0,82 vs 0,98); BPI 2019: 5,10 vs 5,07 (hoà); DH-GBM đơn 8,78 ❌ | 🟡 |
| **G7** | T1 đích | Fine-tune (M=12 tháng) ≤ 0,90 × zero-shot về pinball trên `tgt` | Zero-shot đã thấp hơn B1 60% pinball; fine-tune M=3 kém zero-shot (6,83 vs 6,28); IW/POOLED hơn zero-shot ~1,5–2% ở M≥12 ⇒ DA2 bị bác bỏ | ❌ (tiêu chí −10%) |
| **G8** | T2 | PR-AUC ≥ 2× tỷ lệ nền và ECE ≤0,02 trên SBA FY2018–22; tổn thất kỳ vọng/thực ∈ [0,8; 1,25] | thí nghiệm T2 | ⏳ |
| **G9** | T4 | SPL ≤ min(naive mùa vụ, TB 13 tuần) trên `src` và `tgt` | src 0,2596 vs 0,2701 (−3,9%); tgt zero-shot 0,3474 (có CQR) vs 0,3861 (−10%) | ✅ [Tổng hợp] |
| **G10** | T4 thật | Như G9 trên Online Retail II | Mô hình riêng LGBM+CQR 0,2875 vs TB13 0,2823 ❌; tiền huấn luyện tổng hợp + CQR 0,2794 ✅ nhẹ; Chronos-Bolt 0,2641 tốt nhất | 🟡 |
| **G11** | T5 | 100% ví dụ luật | 15/15 kiểm thử | ✅ |
| **G12** | T6 | cov80 số dư ∈ [75, 85]%; IS80 thấp hơn cả 4 đối chứng; Brier P(thiếu hụt) tốt hơn naive | cov80 ACI 0,794/0,806; IS80 tốt nhất tuần 1–4, thua MC độc lập 1% tuần 5–13; Brier P(thiếu hụt) tốt nhất | 🟡 đạt biên [Tổng hợp] |
| **G13** | T6 | Lead time trung vị ≥4 tuần cho ≥70% sự kiện thiếu hụt; báo giả ≤1/DN-năm | chưa tính (cần WP-6.7) | ⏳ |
| **G14** | T7 | Phát hiện ≥50% trong 180 ngày với báo giả ≤0,5/khách-năm trên miền giữ lại | CUSUM 52,4% nhưng 0,63 báo giả; Page–Hinkley 42,9%/0,42 | 🟡 |
| **G15** | T9 | F1 liên kết > mốc quy tắc tốt nhất; MAE ngày trả ≤ 3 ngày (so với sổ 12,6) | F1 0,689 vs 0,632; MAE 1,97 ngày; **precision 0,78 < 0,99 của quy tắc** | ✅ F1 / ❌ precision |
| **G16** | T0 | recall & precision cổng chất lượng ≥95% | kiểm thử đạt | ✅ |
| **G17** | T8 | Giảm MAE P50 trên HĐ có lời hứa ≥10% | MAE trên HĐ có lời hứa −7,2% (12,21→11,33) | ❌ (cần ≥10%) |
| **G18** | Chung | Nhãn từ sao kê tốt hơn nhãn từ sổ cái (WAPE thu 1–4 tuần giảm ≥10%) | WAPE thu 4 tuần: nhãn ngân hàng 0,405 vs sổ 0,429 (−5,6%) | ❌ (cần ≥10%) |

## Quy tắc quyết định

- **GO sang pilot** khi: G1, G2, G5, G9, G11, G12, G13, G15 (F1 và MAE), G16 đạt; G3/G4 ≤ ±5 điểm; không có nhóm phân tầng
  nào có cov80 <60%.
- **NO-GO** nếu G12 hoặc G13 không đạt: dừng, không đưa dải xác suất cho người dùng (chỉ cho kịch bản căng thẳng tất định).
- **Điều kiện đóng pilot**: thay các cổng [Tổng hợp] bằng đo trên DN thật (T13) — cổng G1/G2/G12/G13 phải đạt lại.

## Đối chứng bắt buộc (không giữ mô hình phức tạp nếu không thắng)

| Khối | Mốc đơn giản | Mô hình phức tạp phải thắng |
|---|---|---|
| T1 | B0 đúng hạn · B1 trung vị khách · B1d phân vị khách | hazard LightGBM, ensemble |
| T2 | tỷ lệ nền · quy tắc tuổi nợ TT48 · logistic | cure-GBM |
| T4 | naive mùa vụ 52 tuần · trung bình 13 tuần | LGBM toàn cục · Chronos · ensemble |
| T6 | MC độc lập · MC ngày điểm · LGBM-Q trực tiếp · naive | MC copula-t + ACI |
| T7 | trung bình trượt · CUSUM-MAD | CUSUM-PIT, PH, BOCPD |
| T9 | khớp đúng số tiền · regex số HĐ | ML reconciler |
