# Pha B. Thí nghiệm cải tiến phương pháp

**Điều kiện bắt đầu:** pha A đã xong (niêm phong v4 đã dùng). Từ đây, tập niêm phong v4 **đã lộ** nên chỉ dùng thế giới phát triển. Kết quả pha B chỉ được coi là "phát triển" cho đến khi có tập niêm phong mới (pha D4).

**Quy ước mọi nhiệm vụ B:**
- Đặt tiêu chí thành công **trước** khi chạy, ghi vào nhật ký.
- Mã mới đặt trong `agent2/` (module mới), không sửa các tệp đã đóng băng của pha A trừ khi cần (khi sửa, chạy lại hồi quy E1 và so JSON cũ; chênh quá 2 điểm phần trăm phải giải thích).
- Mỗi nhiệm vụ: 1 module, 1 tệp kiểm thử, 1 tập lệnh thí nghiệm trong `scripts/`, 1 mục nhật ký, 1 JSON kết quả trong `results/v4/`.
- Bảng dưới là thứ tự khuyến nghị, theo giá trị kỳ vọng trên công.

| # | Giả thuyết | Việc | Công | Ưu tiên |
|---|---|---|---:|:-:|
| B1 | H9 bất biến quy mô tiền | Sinh bản nhân tiền, so bộ đặc trưng | 1 ngày | Cao |
| B2 | H5 CUSUM lương | Module `agent2/drift_payroll.py` | 1,5 ngày | Cao |
| B3 | H4 baseline đồng ngành | Module `agent2/peer.py` | 2 ngày | Cao |
| B4 | H6 xu hướng giá và cụm giờ | Module `agent2/trend.py` | 1,5 ngày | Trung bình |
| B5 | H12 đặc trưng đồ thị | Module `agent2/graph_feats.py` | 2 ngày | Trung bình |
| B6 | H13 điểm mức vụ | Module `agent2/case_score.py` | 1 ngày | Trung bình |
| B7 | H8, H2' tham số: đơn điệu, trọng số họ | Mở rộng `hybrid.LGBM` | 1 ngày | Trung bình |
| B8 | H10 đường cong học | Cần 17 thế giới mới (pha D) | 1 ngày + sinh | Trung bình |
| B9 | H3 trí nhớ bằng điểm không nhãn | Mở rộng `hybrid.memory_features` | 1 ngày | Thấp |
| B10 | H7 ngân sách thích ứng | `alerting.adaptive_budget` | 1 ngày | Thấp |
| B11 | H11 meta-learner | `hybrid.Stacker` | 1 ngày | Thấp |
| B12 | H15, H16 PU learning, độ trôi | `feedback_sim.py` mở rộng | 2 ngày | Thấp |

---

## B1. Bất biến quy mô tiền (H9)

**Vì sao:** dữ liệu tổng hợp có tổn thất mỗi vụ rất thấp (tệp dữ liệu 07); mô hình có thể học "khoản trên X đồng" thay vì quan hệ tương đối. Doanh nghiệp thật có quy mô tiền khác.
**Các bước:**
1. Viết `scripts/make_scaled_world.py`: đọc thế giới v4, nhân mọi cột tiền (`amount_vnd`, `invoice_gross_vnd`, `invoice_net_vnd`, `invoice_vat_vnd`, `unit_price_vnd`, `approval_limit_vnd`, `monthly_salary_vnd`, `self_approval_limit_vnd`, `loss_vnd`, các cột tiền trong `journal_lines`, `invoices`, `advances`) với hệ số `k`; lưu thư mục mới `w4_s411_x10`, `w4_s411_x50`. Tính lại `features.csv` bằng mã của bạn bạn (`sme_fraud/rebuild_features.py`; đọc cách dùng trước).
2. Tạo bộ đặc trưng thô và bộ đặc trưng "bất biến": loại các cột tiền thô, giữ tỷ lệ, log-z, hạng (liệt kê cột bằng danh sách tay, ghi trong `agent2/invariant_cols.py`).
3. Huấn luyện L3 trên ×1 (thế giới 411, 412), kiểm thử trên ×1, ×10, ×50 của 413. Đo recall@B3.
**Tiêu chí:** bộ bất biến mất không quá 5 điểm phần trăm; bộ thô mất nhiều hơn. Nếu bộ thô không mất, bỏ nhiệm vụ.
**Đầu ra:** `results/v4/h9_scale.json`; nếu bộ bất biến thắng, ghi quyết định dùng nó thay đặc trưng thô trong pha C.

## B2. CUSUM lương theo nhân viên (H5)

**Vì sao:** `payroll_padding` bị L3 bỏ sót (4%) nhưng EntityDeviation bắt 79%: tín hiệu nằm ở "lương của chính người này tăng", không phải mức tuyệt đối.
**Các bước:**
1. Module `agent2/drift_payroll.py` với hàm `cusum_payroll(df) -> DataFrame[transaction_id, cusum_up, cusum_run_len, ratio_to_ref]` làm việc theo từng nhân viên theo thời gian (chỉ quá khứ): tham chiếu = trung vị của 3 kỳ lương thường xuyên gần nhất (loại tháng thưởng và quyết toán); `s_t = max(0, s_{t-1} + (log(x_t/ref) − k))` với `k = 0,02`; cờ khi `s_t > h`, `h` chọn trên tập huấn luyện sao cho tỷ lệ cờ trên lương hợp lệ không quá 1%.
2. Thêm cột vào `EntityDeviation` (bản mở rộng, **không sửa lớp cũ**: kế thừa thành `EntityDeviationPlus`) và vào bộ đặc trưng L4.
3. Kiểm thử đơn vị: chuỗi lương hằng thì không cờ; tăng 10% kéo dài thì có cờ sau 2 đến 3 kỳ; tháng thưởng không cờ (loại bằng lịch).
4. Đánh giá: recall@B3 của `payroll_padding` ở P1/P2 trên thế giới phát triển; báo nhầm trên `legit_bonus_run`, `tet_bonus_payroll`, `year_end_bonus_payroll`, `legit_final_settlement`.
**Tiêu chí:** `payroll_padding` ≥ 60%; báo nhầm các ca lương hợp lệ tăng không quá 3 điểm.
**Cảnh báo:** niêm phong v4 có kịch bản `overtime_inflation_group`; module này sẽ làm nó không còn "chưa thấy" nếu tập niêm phong được dùng lại. Tập niêm phong v4 đã dùng ở pha A nên không còn vấn đề; vẫn ghi chú.

## B3. Baseline đồng ngành cho ngày đầu (H4)

**Vì sao:** khách mới chưa có lịch sử; EntityDeviation cần ít nhất 20 điểm tham chiếu mỗi bộ phát hiện.
**Các bước:**
1. Module `agent2/peer.py`: hàm `fit_peer(worlds)` tính, theo (ngành, quy mô), phân vị 1, 5, 25, 50, 75, 95, 99 của từng đặc trưng liên tục (đã chuẩn hóa theo `amount_scale` của công ty nếu có); hàm `peer_score(df, peer)` cho điểm đuôi như EntityDeviation nhưng so với nhóm đồng ngành.
2. Chạy P3 với chế độ "không lịch sử": không dùng giai đoạn huấn luyện của công ty đích; chỉ dùng `peer`. So với: Rules, Novelty, L3.
3. Mở rộng: kết hợp khi công ty có ít lịch sử (hạng lai theo độ dài lịch sử).
**Tiêu chí:** ngày đầu recall@B3 ≥ 25% với báo nhầm ≤ 20%.
**Đầu ra:** `results/v4/h4_peer.json`; hồ sơ `cold_day1` trong `pipeline.py` (pha C).

## B4. Xu hướng giá và cụm giờ (H6)

**Các bước:** module `agent2/trend.py`:
1. `price_trend(df)`: với mỗi nhà cung cấp, độ dốc hồi quy của log đơn giá theo thứ tự trên 6 lần mua gần nhất (hoặc thống kê Mann–Kendall), cùng `n` mẫu; chỉ quá khứ.
2. `burst_features(df)`: số khoản thanh toán khác nhà cung cấp của cùng người lập trong 3 giờ, buổi tối, ngày làm việc; số nhà cung cấp khác nhau.
3. Thêm vào bộ phát hiện không nhãn (lớp kế thừa) và L4. Đánh giá `price_creep`, `vendor_burst` trên thế giới phát triển; kiểm ca hợp lệ `legit_price_increase`, `legit_bulk_purchase`.
**Tiêu chí:** kênh không nhãn tăng ít nhất 20 điểm phần trăm cho hai kịch bản này; báo nhầm không tăng quá 2 điểm.

## B5. Đặc trưng đồ thị (H12)

**Các bước:** module `agent2/graph_feats.py` đọc `entity_links.csv`, `bank_account_changes.csv`:
- với mỗi nhà cung cấp: số thực thể (nhân viên, nhà cung cấp khác) dùng chung tài khoản, điện thoại, địa chỉ, người đại diện; khoảng cách ngắn nhất đến một nhân viên; tuổi liên kết (liên kết có từ trước hay sau khi nhà cung cấp bắt đầu);
- với mỗi nhân viên: số nhân viên chung tài khoản; có phải nhân viên có chấm công và có dòng lương đều không.
Tính nhân quả (liên kết quan sát tại `observed_at`). Thêm vào L4. Đánh giá `ghost_employee`, `shell_vendor`, `undisclosed_related_vendor` ở P2.
**Tiêu chí:** tăng ở ít nhất hai trong ba kịch bản; thời gian chạy không tăng hơn 2 lần.

## B6. Chấm điểm mức vụ (H13)

1. `agent2/case_score.py`: điểm vụ theo (công ty, thực thể, tuần) = `1 − ∏(1 − p_i)` với `p_i` là xác suất đã hiệu chỉnh isotonic trên kiểm định, hoặc max; chọn top-3 vụ thay vì top-3 dòng.
2. Đo **số mục người dùng xem** (vụ) và vụ tìm thấy; so với chính sách 2+1 theo dòng.
**Tiêu chí:** vụ tìm thấy ≥ 90% với số mục xem không tăng.

## B7. Ràng buộc đơn điệu và trọng số họ (H8, H2)

Mở rộng `hybrid.LGBM` (tham số mới, mặc định giữ nguyên hành vi cũ để không phá hồi quy): `monotone_features=[...]` (+1 cho các đuôi thực thể và dấu hiệu đỏ), `balance="family_sqrt"`, `weight_cap`. Chạy lưới nhỏ trên P2/P3. Chọn bằng quy tắc điểm đã đăng ký.

## B8. Đường cong học (H10)

Cần 17 thế giới phát triển mới (D2). Huấn luyện trên 1, 2, 4, 8, 16 thế giới (cố định thế giới kiểm thử). Vẽ recall@B3 theo số thế giới. Quyết định số thế giới cần sinh cho mô hình sản phẩm.

## B9 đến B12 (ngắn)
- **B9 (H3):** `memory_features(source="unsupervised")`; cửa sổ 30, 60, 90, 180; đặc trưng "ngày từ dòng đáng ngờ gần nhất"; so L4 ở P1/P2.
- **B10 (H7):** `adaptive_budget`: `B_t = clip(round(c · sqrt(n_t)), 1, 5)`; hoặc dừng khi điểm vụ dưới ngưỡng conformal; đo giảm cảnh báo và mất recall.
- **B11 (H11):** logistic hai đầu vào [điểm L4, hạng Novelty] huấn luyện trên kiểm định; chọn mục theo điểm hợp nhất; so với 2+1.
- **B12 (H15, H16):** mở rộng `feedback_sim.py` (PU learning, nhiễu theo hệ thống) và thử nghiệm độ trôi hằng tháng.

## Báo cáo pha B
Sau mỗi nhiệm vụ: bảng "trước, sau" (P1/P2/P3 recall@B3, báo nhầm, AP), kết luận "giữ" hoặc "bỏ", và cập nhật `METHODS.md` mục so sánh. Tổng hợp cuối pha: cấu hình ứng viên cho vòng niêm phong mới (D4).
