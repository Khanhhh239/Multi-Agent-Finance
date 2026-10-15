# 8. Thí nghiệm đề xuất (giả thuyết → thiết kế → tiêu chí)

Phần "tôi nghĩ vậy nhưng chưa chứng minh". Mỗi mục có: **Giả thuyết**, **Lý do tin**, **Thiết kế**, **Tiêu chí**, **Ưu tiên** (P0 phải làm trước pilot; P1 nên; P2 thăm dò).
Mã gói việc tương ứng ở 05_Coding_Agent_Plan.

## Nhóm A — Đánh giá và hạ rủi ro của kết quả hiện có (P0)

| # | Giả thuyết | Lý do tin | Thiết kế | Tiêu chí |
|---|---|---|---|---|
| X1 | Nhãn SBA bị bóp méo bởi `EXEMPT`; sau khi loại/xử lý, AUC giảm nhưng PR-AUC vẫn ≥5× nền | 144.908 khoản y=0 giả; AUC 0,955 quá cao | (a) bỏ EXEMPT; (b) giữ EXEMPT nhưng chỉ đánh giá trong nhóm kỳ hạn ≤120 tháng; (c) coi EXEMPT như kiểm duyệt (cure model) | PR-AUC/nền ≥5 ở (b) |
| X2 | Hàng "+CQR" của DH-GBM giống hệt hàng gốc vì q̂≈0 → cho phép hiệu chỉnh hai phía (thu hẹp được) cải thiện IS80 | cov80 0,86–0,89 > 0,8 | CQR không đối xứng (α_lo, α_hi riêng), cho q̂ âm | cov80 ∈ [78, 82]% và IS80 giảm |
| X3 | Lợi thế IBS/WAPE của hazard so với phân vị bị phóng đại bởi cách xấp xỉ CDF từ 3 phân vị | CDF nội suy từ 3 điểm là thô | Dựng QLGBM với 19 phân vị (5%…95%) rồi tính IBS/WAPE | Hiệu IBS còn ≥20% nếu kết luận bền |
| X4 | Tính ổn định theo seed: chênh <0,5% | LightGBM bagging | 3 seed × 2 gốc | CV chỉ số <0,5% |
| X5 | Kết quả A có thể bị ảnh hưởng bởi snapshot 2 tuần/lần (cách lấy mẫu train) | | So tần suất 1/2/4 tuần | không đổi kết luận |

## Nhóm B — T1 mạnh hơn (P0/P1)

| # | Giả thuyết | Thiết kế | Tiêu chí |
|---|---|---|---|
| X10 | Ràng buộc đơn điệu (hazard tăng theo `c_late_share`, `c_delay_eb`; giảm theo `days_to_due`) cải thiện ngoài miền (`tgt`, `sens_coface`) | `monotone_constraints` LightGBM; so zero-shot | IBS `tgt` giảm ≥3% |
| X11 | Early stopping theo pinball cửa sổ hiệu chỉnh + tối ưu siêu tham số (Optuna, 50 trials) tốt hơn mặc định | lưới leaves/min_data/λ₂/ff | pinball giảm ≥3% không tăng overfit |
| X12 | Hazard theo ngày ở 28 ngày đầu (28 bin) tốt hơn theo tuần cho WAPE tuần 1–2 | thêm tầng "ngày" cho k≤4 | WAPE w1–2 giảm ≥10% |
| X13 | Mixture "đúng hạn + trễ" (hai thành phần) tốt hơn trên khách kỷ luật | hazard = π·đỉnh quanh ngày hạn + (1−π)·hazard trễ | pinball giảm trên nhóm kỷ luật |
| X14 | Hierarchical Bayes cho khách (thay EB cố định k=4) giúp khách mới (c_n<5) | `k` học theo ngành/khối lượng | MAE khách mới giảm ≥8% |
| X15 | Mô hình đa nhiệm (trả/không, tranh chấp, trả một phần) chia sẻ lớp ẩn tốt hơn từng mô hình | mạng MLP nhỏ trên cùng đặc trưng | AUC T3 tăng và pinball T1 không giảm |
| X16 | DeepHit/DeepSurv không vượt GBM trên bảng cỡ này | PyTorch nhỏ 3 lớp | nếu không vượt ⇒ giữ GBM, ghi lại |
| X17 | TabPFN v2 (ngữ cảnh ≤10k hàng) mạnh ở M nhỏ (3–6 tháng) | dùng làm bộ thích nghi cho DN ít dữ liệu | thắng fine-tune tại M=3 |

## Nhóm C — Domain adaptation (P0)

Xem 05_domain_adaptation.md (DA1–DA7). Thêm:

| # | Giả thuyết | Thiết kế |
|---|---|---|
| X20 | Domain randomization (huấn luyện trên ≥20 thế giới tham số khác nhau) giảm sụt giảm zero-shot ở `tgt`/`sens_*` hơn tăng quy mô một thế giới | 20 thế giới × 20 công ty vs 1 thế giới × 400 công ty cùng số hoá đơn |
| X21 | Kết quả chuyển miền tổng hợp→thật: huấn luyện `src`, kiểm tra Customer Invoices zero-shot và sau fine-tune 3 tháng | thêm dòng "src→HR" vào exp C |
| X22 | Đo khoảng cách miền: bộ phân loại miền AUC giữa `src` và `tgt` | AUC >0,9 ⇒ shift lớn ⇒ cần IW |

## Nhóm D — T4/T6/T7 (P0/P1)

| # | Giả thuyết | Thiết kế | Tiêu chí |
|---|---|---|---|
| X30 | MC copula-t + ACI đạt cov80 ∈ [75,85]%, thắng 4 đối chứng về IS80 | `run_t6.py` | G12 |
| X31 | Copula phân tầng (ρ_khách 0,25; ρ_danh mục 0,75) tốt hơn một ρ | 2 nhân tố | IS80 giảm ≥3% |
| X32 | df của t ước lượng từ SEC (Q2/Q3 2020) khác 4 đáng kể | fit t trên dòng tiền hoạt động theo quý | df̂ ± CI; thay giả định |
| X33 | Dùng **số dư thật** của Berka để đo độ phủ của khoảng dự báo (dòng ròng tuần) | phân vị trực tiếp + ACI trên 1.478 tài khoản | cov80 ∈ [75,85]% |
| X34 | CUSUM danh mục (toàn DN) phát hiện sốc chung trước khi cov80 sụt | chạy trên OxCGRT + `src` | lead ≥2 tuần |
| X35 | Giảm báo giả T7 bằng quy tắc xác nhận 2/3 (cùng cụm khách) | | FA ≤0,5, detection ≥50% |
| X36 | Dự báo chi NCC từ doanh thu tuần trước (mua trước bán 2 tuần) thay vì TB 13 tuần | hồi quy đơn giản | WAPE chi NCC tuần 5–13 giảm |
| X37 | Chronos fine-tune nhẹ trên chuỗi tổng hợp tốt hơn zero-shot | LoRA/head tuning | SPL giảm ≥5% trên `tgt` |

## Nhóm E — Dữ liệu thật bổ sung (P1)

| # | Thí nghiệm | Mục tiêu |
|---|---|---|
| X40 | Home Credit `installments_payments` (Kaggle) | Trả một phần/T3, hazard trên dữ liệu thật có hạn rõ ràng |
| X41 | M5 — tái lập WSPL của LightGBM đa chân trời | Chứng minh quy trình T4 đúng chuẩn |
| X42 | UNU-WIDER/Tổng điều tra → phân bố quy mô SME VN | Thay giả định logNormal(40 tỷ) |
| X43 | SEC → df cho T6 | |
| X44 | Báo cáo tài chính niêm yết VN → DSO/DPO theo ngành | Kiểm tra độc lập máy phát (không dùng chỉnh) |
| X45 | Khảo sát 5–10 văn phòng kế toán: tỷ lệ ghi sổ lô, FIFO sai, nội dung CK | Thay giả định H20–H22 bằng số thật |

## Nhóm F — Sản phẩm và con người (P1/P2)

| # | Thí nghiệm | Thiết kế | Tiêu chí |
|---|---|---|---|
| X50 | Người dùng hiểu dải xác suất? | 10 người dùng thử trong 15 phút | ≥8/10 chỉ đúng tuần nguy hiểm |
| X51 | Lý do SHAP có được kế toán gật đầu? | 30 cảnh báo × 3 kế toán | ≥70% "hợp lý" |
| X52 | LLM trung thực với số liệu | 200 cảnh báo; regex đối chiếu | 0 số sai |
| X53 | Chính sách đòi nợ ưu tiên | mô phỏng `tgt` 3 chính sách | ΔDSO ≥ 2 ngày so với "to nhất trước" |
| X54 | Ngưỡng cảnh báo theo chi phí | ROC/PR theo c_miss/c_false | điểm vận hành chọn bởi DN |

## Nhóm G — Giả thuyết kinh tế cần xác nhận ở pilot (P0 cho T13)

Xem 03_Evaluation/06 §6.8: giảm 2 ngày trễ, giảm 20% đệm, 70% sự kiện bắt được, 10% giảm nợ xấu, 568 giờ công.
