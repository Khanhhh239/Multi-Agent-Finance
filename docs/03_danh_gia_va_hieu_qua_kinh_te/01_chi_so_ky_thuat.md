# Chỉ số kỹ thuật

Mã: `agent2/metrics.py`. Mọi chỉ số tính trên **tập kiểm thử** với ngưỡng và tham chiếu chỉ lấy từ tập kiểm định.

## 1. Vì sao không dùng F1 hay ROC-AUC
Tỷ lệ gian lận 0,3 đến 0,4% làm ROC-AUC luôn cao (đọc nhầm là tốt). F1 phụ thuộc ngưỡng mà người dùng không đặt. Người dùng thật có **ngân sách chú ý**: vài cảnh báo mỗi tuần. Vì vậy chỉ số chính đo **trong ngân sách đó**.

## 2. Chỉ số chính

| Chỉ số | Định nghĩa | Đọc thế nào |
|---|---|---|
| **Recall@B3** | Tỷ lệ dòng gian lận nằm trong 3 cảnh báo cao nhất mỗi công ty mỗi tuần | Chỉ số chính của sản phẩm |
| **Precision@B3** | Tỷ lệ cảnh báo là dòng gian lận | Thấp (khoảng 4,5%) vì tỷ lệ nền 0,4% và hơn nửa công ty không có vụ; xem tệp 06 |
| **Recall@B1, Precision@B1** | Như trên với 1 cảnh báo mỗi tuần | Chế độ chặt |
| **Vụ tìm thấy@B3** (case recall) | Tỷ lệ **vụ** có ít nhất một dòng được cảnh báo | Gần với giá trị thật hơn recall dòng, vì phát hiện sớm một dòng là đủ để mở điều tra |
| **AP** (average precision) | Diện tích dưới đường precision-recall | Xếp hạng toàn bộ; nền bằng tỷ lệ dương |
| **R-precision** | Precision ở K bằng số dòng dương | Không phụ thuộc ngân sách |
| **Báo nhầm ca hợp lệ giống gian lận** | Tỷ lệ cảnh báo trên các dòng `hard_negative_type` khác rỗng | Đo khả năng phân biệt ca khó; ràng buộc cổng chọn |
| **Độ trễ** | Số ngày từ dòng gian lận đầu tiên của vụ đến cảnh báo đầu tiên (trung vị) | Chỉ so tương đối (vụ bị nén) |
| **Cảnh báo trên 1.000 dòng** | Tải cảnh báo | Chi phí rà soát |
| **Precision cấp thực thể** | Gộp cảnh báo theo (nhà cung cấp hoặc nhân viên hoặc người lập, tuần): tỷ lệ mục có gian lận | Gần với danh sách mà người dùng mở |
| **Khoảng tin cậy AP** | Bootstrap theo vụ (lấy lại mẫu các vụ và các dòng hợp lệ) | Mẫu dương nhỏ |

## 3. Chỉ số theo năng lực (dùng cùng định nghĩa)

| Câu hỏi | Chỉ số | Mã |
|---|---|---|
| Kịch bản nào khó? | Recall@B3 theo `fraud_type` | `metrics.per_group_recall` |
| Che giấu kỹ thì sao? | Recall@B3 theo `difficulty` (L0, L1, L2) | như trên |
| Kịch bản chưa từng thấy | Recall@B3 và AP khi ẩn nhãn kịch bản hoặc nhánh | `bench.run_leave_family_out`, `eval_v4.p2_unseen_branch` |
| Công ty mới | Recall@B3 khi chỉ dùng lịch sử không nhãn của công ty đích | `eval_v4.p3_new_firm` |
| Học từ phản hồi | Số dòng gian lận tìm được tích lũy sau 52 tuần | `feedback_sim.py` |
| Hiệu chỉnh xác suất | Đường cong isotonic điểm → tỷ lệ trúng (mức thực thể) | `alerting.Confidence` |
| Kiểm soát FDR | p-giá trị conformal + Benjamini–Hochberg | `alerting.conformal_pvalues` |

## 4. Chỉ số cần bổ sung (chưa có)

| Chỉ số | Vì sao cần | Cách làm |
|---|---|---|
| Độ trôi theo tháng | Người gian lận đổi cách làm | Huấn luyện 6 tháng, kiểm thử từng tháng sau đó |
| Độ ổn định theo seed | Phân biệt thật với may rủi | Chạy 5 seed mô hình (đã có ở v3), báo trung bình ± độ lệch chuẩn |
| Kiểm định có ý nghĩa khi so hai phương pháp | Chênh 3 điểm phần trăm có thật không | Bootstrap ghép cặp theo vụ trên cùng tập kiểm thử |
| Độ trung thực của giải thích | Câu lý do phải đúng | Mọi con số trong câu giải thích phải có trong bằng chứng; kiểm tra tự động |
| Độ trễ tính toán | Chạy hằng tuần | Đo giây cho 100.000 dòng |
| Công bằng giữa các nhóm | Không được báo nhầm cao hơn cho một phòng ban hay nhóm nhân sự | Tỷ lệ cảnh báo trên ca hợp lệ theo vai trò, phòng ban |

## 5. Cạm bẫy đã gặp

1. **AP trong cùng phân phối là vòng tròn** khi đặc trưng và bộ sinh cùng tác giả. Số cần nhìn: bỏ-một-họ, chuyển giao thế giới, niêm phong.
2. Luật và bộ chèn của bạn bạn viết cho cùng kịch bản (v2): AP 0,60 sụt còn 0,24 ở v3.
3. Chỉ số "AUC với chỉ loại nghiệp vụ" đã cao 0,7 đến 0,8: AUC không có ý nghĩa ở đây.
4. Precision@B3 gộp bị kéo xuống vì công ty không có vụ; báo cáo thêm theo công ty có vụ nếu cần.
5. Ca hợp lệ giống gian lận chiếm khoảng 9% số dòng; tỷ lệ cảnh báo trên đó 15 đến 20% nghĩa là cứ 5 đến 7 ca khó có một ca bị gắn cờ.
