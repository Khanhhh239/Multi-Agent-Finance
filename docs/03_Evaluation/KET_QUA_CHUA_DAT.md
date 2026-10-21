# Kết quả chưa đạt và giới hạn bằng chứng

Sinh bởi `scripts/analyze_results.py`; không dùng chỉ số đích để chọn tham số.

## Dữ liệu thật v2 sau sửa lỗi expand, cập nhật 21/10/2026

- bpi, BLEND(DH-GBM,B1d) w=0.25: pinball 4.4871, cải thiện vs B1d 6.505%, CI [2.144, 11.032]%. w chọn trên calibration rồi refit; bootstrap theo khách, chưa đại diện SME VN.
- ci, BLEND(DH-GBM,B1d) w=0.5: pinball 1.2453, cải thiện vs B1d 14.424%, CI [11.719, 17.432]%. w chọn trên calibration rồi refit; bootstrap theo khách, chưa đại diện SME VN.

Các kết luận v1 bên dưới chỉ để kiểm toán. Lỗi tuần bị cắt, LR ngoại suy và chia dữ liệu bỏ đói đã được xác định trong nhật ký Sprint 1; không dùng v1 để kết luận BLEND v2 thua mốc.

- **LEGACY v1** C_real_bpi2019: pinball ensemble 14.9519, B1d 4.7993; giả thuyết ensemble không thua mốc bị bác bỏ.
- **LEGACY v1** C_real_customer_invoices: pinball ensemble 1.5425, B1d 1.4552; giả thuyết ensemble không thua mốc bị bác bỏ.
- T6 w1-4: cov80=0.7462, CI [0.6565, 0.8223]. Nhãn ở thí nghiệm này là nhãn thật tổng hợp, chưa phải E2E từ nhãn T9 ước lượng.
- T6 w5-13: cov80=0.7521, CI [0.6512, 0.8353]. Nhãn ở thí nghiệm này là nhãn thật tổng hợp, chưa phải E2E từ nhãn T9 ước lượng.
- C2ST src: AUC=0.9964, CI [0.8847, 0.9978]; không đạt mục tiêu <0.75.
- C2ST sens_uk: AUC=0.9957, CI [0.8439, 0.9966]; không đạt mục tiêu <0.75.
- C2ST sens_coface: AUC=0.9968, CI [0.8858, 0.9982]; không đạt mục tiêu <0.75.
- Máy phát: tăng tốc 1.545× trên 29817 HĐ; chưa chứng minh >=5× tại 1M HĐ.

Ngoài lỗi expand/ngoại suy/chia dữ liệu v1 đã xác định ở Sprint 1, không suy nguyên nhân của các kết quả còn lại chỉ từ bảng điểm hoặc tự quy cho domain shift. CSV hazard chưa có fullweek chỉ dùng kiểm toán trong lúc chờ chuỗi chạy lại.

- Tuning cùng ngân sách: thay đổi pinball -1.168%; CI cải thiện [-2.368, -0.039]%. Tham số mới chưa được đưa vào mô hình mặc định.

Home Credit/SEC tạm bỏ theo Q1/Q2; không có dữ liệu người thật, xác minh chuyên môn, UAT ba người hoặc pilot.

- BPI không hạn: thêm hạn ảo/tuổi thay đổi pinball -10.183% (dương là cải thiện), CI [-10.331, 28.072]%; không tự áp dụng. Chỉ có 3 cụm DN; BPI là phải trả, không phải AR Việt Nam.

- T3→T1 nhóm tranh chấp src: cải thiện pinball -1.755%, CI [-3.740, 0.346]%; chưa đưa đặc trưng vào mặc định. Nhãn tranh chấp chỉ dùng phân nhóm chấm điểm, đầu vào là lịch sử đã đóng tại ngày lập.

- T3→T1 nhóm tranh chấp tgt: cải thiện pinball -3.114%, CI [-4.577, -0.744]%; chưa đưa đặc trưng vào mặc định. Nhãn tranh chấp chỉ dùng phân nhóm chấm điểm, đầu vào là lịch sử đã đóng tại ngày lập.

- E2E ACI so Chronos-Bolt Tiny (w1-4): cải thiện IS80 -3.553%, CI [-29.095, 17.850]%. G12 chỉ kiểm bốn đối chứng gốc; không suy từ G12 rằng đã thắng mọi đối chứng bổ sung. Không chọn lại mô hình theo test.

- E2E ACI so Chronos-Bolt Tiny (w5-13): cải thiện IS80 -11.438%, CI [-39.408, 12.533]%. G12 chỉ kiểm bốn đối chứng gốc; không suy từ G12 rằng đã thắng mọi đối chứng bổ sung. Không chọn lại mô hình theo test.

T9 đã có 12/12 thế giới ở kỳ giữ lại 2024-07→2025-06. Kỳ này không bao phủ đợt supply_shock năm 2022; xem ngày sao kê thực tế ở CSV, đặc biệt DN mới chỉ xuất hiện từ 2025.
- T9 lumpy_customer: precision 0.9705, recall 0.6447, F1 0.7747, tự động 0.7433; chưa đạt đồng thời precision >=.95 và F1 >=.80.
- T9 cod_realistic: precision 0.9050, recall 0.5602, F1 0.6920, tự động 0.6242; chưa đạt đồng thời precision >=.95 và F1 >=.80.
- T9 discount_early: precision 0.9394, recall 0.5871, F1 0.7226, tự động 0.6064; chưa đạt đồng thời precision >=.95 và F1 >=.80.
- T9 retention: precision 0.8274, recall 0.4407, F1 0.5751, tự động 0.5144; chưa đạt đồng thời precision >=.95 và F1 >=.80.
- T9 fx: precision 0.9409, recall 0.6414, F1 0.7628, tự động 0.6667; chưa đạt đồng thời precision >=.95 và F1 >=.80.
- T9 verbal: precision 0.9486, recall 0.7130, F1 0.8141, tự động 0.7324; chưa đạt đồng thời precision >=.95 và F1 >=.80.

- SBA cohort trước (drop): cải thiện Brier -0.545%, CI [-0.985, -0.194]%; rejected. Trễ công bố 90 ngày là giả định, không có vintage lịch sử; chưa áp dụng đặc trưng này.

- SBA cohort trước (keep): cải thiện Brier -1.738%, CI [-2.168, -1.270]%; rejected. Trễ công bố 90 ngày là giả định, không có vintage lịch sử; chưa áp dụng đặc trưng này.

- SBA cohort trước (censor): cải thiện Brier -0.545%, CI [-0.985, -0.194]%; rejected. Trễ công bố 90 ngày là giả định, không có vintage lịch sử; chưa áp dụng đặc trưng này.

- T7→T6 2021-07-01: cov80 0.6587, CI [0.5869, 0.7228]; thay đổi độ phủ -0.0009, CI [-0.0024, 0.0000]. Chưa đạt 70%. Ngưỡng chọn trên nguồn; lịch thu lý tưởng, khác E2E T9.

- T7→T6 2022-10-01: cov80 0.6331, CI [0.5951, 0.6751]; thay đổi độ phủ 0.0003, CI [0.0000, 0.0008]. Chưa đạt 70%. Ngưỡng chọn trên nguồn; lịch thu lý tưởng, khác E2E T9.

- Thu nợ q=0.3: P2 so P1 giảm DSO -0.443 ngày, CI [-1.225, 0.109]; not_demonstrated. Mô phỏng phản hồi giả định, chưa phải tác động nhân quả hoặc ROI.

- Thu nợ q=0.5: P2 so P1 giảm DSO -0.279 ngày, CI [-0.794, 0.157]; not_demonstrated. Mô phỏng phản hồi giả định, chưa phải tác động nhân quả hoặc ROI.

- Thu nợ q=0.7: P2 so P1 giảm DSO -0.276 ngày, CI [-0.652, 0.108]; not_demonstrated. Mô phỏng phản hồi giả định, chưa phải tác động nhân quả hoặc ROI.

- Copula phân tầng: IS80 cải thiện 1.068%, CI [0.139, 1.990]% so một nhân tố chọn trên nguồn. Cov80 khoảng thô 0.5758; chưa thay E2E hoặc tự đưa vào dịch vụ.

- IW ngoài công ty tgt, M6: pinball cải thiện -1.921%, CI [-2.944, 0.101]%; not_demonstrated. Ablation thăm dò, không thay DA4 gốc hoặc tự áp dụng. AUC/ESS trong bảng chẩn đoán không xác nhận hai miền chồng lấn.

- IW ngoài công ty sens_uk, M6: pinball cải thiện -2.568%, CI [-4.076, -1.090]%; rejected. Ablation thăm dò, không thay DA4 gốc hoặc tự áp dụng. AUC/ESS trong bảng chẩn đoán không xác nhận hai miền chồng lấn.

- IW ngoài công ty sens_coface, M6: pinball cải thiện -0.220%, CI [-1.049, 0.799]%; not_demonstrated. Ablation thăm dò, không thay DA4 gốc hoặc tự áp dụng. AUC/ESS trong bảng chẩn đoán không xác nhận hai miền chồng lấn.

- DR 20×20 so 1×400 trên tgt: cải thiện pinball 1.238%, CI [-0.692, 3.371]%; ngưỡng định trước 5%, rejected. Cùng số HĐ theo cặp DN; seed nguồn đơn, chưa có bất định qua nhiều lần sinh nguồn.

- DR 20×20 so 1×400 trên sens_uk: cải thiện pinball 1.442%, CI [-0.530, 3.281]%; ngưỡng định trước 5%, rejected. Cùng số HĐ theo cặp DN; seed nguồn đơn, chưa có bất định qua nhiều lần sinh nguồn.

- DR 20×20 so 1×400 trên sens_coface: cải thiện pinball 2.189%, CI [0.034, 4.946]%; ngưỡng định trước 5%, rejected. Cùng số HĐ theo cặp DN; seed nguồn đơn, chưa có bất định qua nhiều lần sinh nguồn.

- DR 20×20 so 1×400 trên real_customer_invoices: cải thiện pinball 34.427%, CI [24.282, 35.312]%; ngưỡng định trước 5%, supported. Cùng số HĐ theo cặp DN; seed nguồn đơn, chưa có bất định qua nhiều lần sinh nguồn.

- T9 sốc cung ứng 2022, nhóm thép, before: precision 1.0000, recall 0.8556, F1 0.9222, CI F1 [0.8764, 0.9542], tự động 0.7566. Mô hình nguồn 2020/calibration 2021; tau=.9 khoá trước; không tự chọn lại hoặc thay G15.

- T9 sốc cung ứng 2022, nhóm thép, shock: precision 0.9903, recall 0.7969, F1 0.8831, CI F1 [0.7949, 0.9403], tự động 0.7083. Mô hình nguồn 2020/calibration 2021; tau=.9 khoá trước; không tự chọn lại hoặc thay G15.

- T9 sốc cung ứng 2022, nhóm thép, after: precision 0.9944, recall 0.7149, F1 0.8318, CI F1 [0.7273, 0.9065], tự động 0.6468. Mô hình nguồn 2020/calibration 2021; tau=.9 khoá trước; không tự chọn lại hoặc thay G15.
