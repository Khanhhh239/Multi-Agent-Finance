# Giả thuyết cần thí nghiệm thêm

Mỗi giả thuyết có: **lý do**, **thí nghiệm**, **tiêu chí thành công** (đặt trước), **mã cần viết**. Quy tắc chung: chỉ dùng 3 thế giới phát triển v4 (411 đến 413) hoặc các thế giới phát triển mới; **không xem thế giới niêm phong** (931 đến 933) khi chưa đóng băng. Giao việc chi tiết: [thư mục 05](../05_ke_hoach_giao_viec/README.md).

| ID | Giả thuyết | Ưu tiên |
|---|---|:-:|
| H1 | L4 hoặc L4-FB tốt hơn L3 ở P2 và P3, không kém ở P1 | Cao |
| H2 | Cân bằng trọng số theo họ tăng recall chưa thấy mà P1 giảm không quá 2 điểm | Cao |
| H3 | Trí nhớ theo thực thể hữu ích nếu dùng điểm không nhãn thay cho điểm tầng 1 | Trung bình |
| H4 | Baseline theo nhóm đồng ngành cho bậc 1 (ngày đầu) bắt được kịch bản lộ rõ | Cao |
| H5 | Bộ phát hiện chuỗi thời gian theo nhân viên (CUSUM) bắt `payroll_padding` và `overtime_inflation_group` | Cao |
| H6 | Xu hướng giá nhà cung cấp và cụm giờ bắt `price_creep` và `vendor_burst` | Trung bình |
| H7 | Ngân sách thích ứng theo công ty giảm gánh nặng mà không giảm nhiều recall | Trung bình |
| H8 | Ràng buộc đơn điệu trong LightGBM cải thiện chuyển giao | Trung bình |
| H9 | Dùng tỷ lệ và log-z (bất biến quy mô tiền) thay cho số tiền thô giữ hiệu năng khi nhân tiền ×10, ×50 | Cao |
| H10 | Nhiều thế giới huấn luyện hơn cải thiện P3 (đường cong học) | Trung bình |
| H11 | Bộ hợp nhất học (meta-learner) tốt hơn khe cố định 2+1 | Thấp |
| H12 | Đặc trưng đồ thị cho mô hình học (số lân cận chung, tiền qua tài khoản chung) cải thiện `ghost_employee`, `shell_vendor`, `undisclosed_related_vendor` | Trung bình |
| H13 | Chấm điểm mức vụ (noisy-or các dòng trong thực thể-tuần) tăng vụ tìm thấy ở cùng thời gian rà soát | Trung bình |
| H14 | Lý do mẫu câu giữ 100% độ trung thực; mô hình ngôn ngữ chỉ làm mượt | Cao (trước thí điểm) |
| H15 | Học bán giám sát từ phản hồi (PU learning) cải thiện sau 12 tuần | Thấp |
| H16 | Huấn luyện lại định kỳ giảm suy giảm theo tháng | Thấp |

## Thiết kế chi tiết

### H1. L4 và L4-FB so với L3
- **Lý do:** điểm không nhãn cho mô hình thông tin "lạ so với chính thực thể" mà 190 đặc trưng không có; P2 sơ bộ (thế giới 411) cho 63 đến 70% so với 52%.
- **Thí nghiệm:** hoàn tất `eval_v4` với P1, P2, P3 trên 3 thế giới; so ghép cặp theo vụ (bootstrap) cho chênh P1.
- **Thành công:** P2 trung bình nhánh và P3 hơn L3 ít nhất 5 điểm phần trăm, P1 không thấp hơn quá 2 điểm, khoảng bootstrap loại trừ 0.
- **Mã:** không (chạy lại `eval_v4`, `select_v4`); thêm kiểm định ghép cặp trong `agent2/stats_v4.py` (mới).

### H2. Cân bằng họ
- **Lý do:** các họ hiếm (2 đến 10 dòng) bị họ phổ biến lấn át khi tối ưu logloss.
- **Thí nghiệm:** biến thể trọng số: `1/n_f`, `1/sqrt(n_f)`, cân bằng nhánh ACFE thay vì họ. Chạy P1, P2.
- **Thành công:** như H1.
- **Rủi ro:** quá khớp họ hiếm khi 2 dòng; cần trần trọng số (ví dụ không quá 20 lần trọng số trung bình).

### H3. Trí nhớ theo thực thể
- **Lý do:** vụ nhiều dòng; hai tầng hiện tại không giúp.
- **Thí nghiệm:** thay hạng tầng 1 bằng `u_entity_r` (không nhãn); thêm đặc trưng "số ngày kể từ dòng đáng ngờ gần nhất của cùng thực thể" và "xu hướng điểm 30, 60, 90 ngày"; thử cửa sổ 30, 60, 90, 180 ngày.
- **Thành công:** AP và vụ tìm thấy hơn L4 hai điểm phần trăm trên P1 và không kém P2.
- **Mã:** mở rộng `hybrid.memory_features` thêm chế độ `source="unsupervised"`.

### H4. Baseline đồng ngành (bậc 1)
- **Lý do:** ngày đầu công ty chưa có lịch sử; cần so với nhóm đồng ngành và quy mô.
- **Thí nghiệm:** từ các thế giới huấn luyện, tính phân vị của từng đặc trưng theo (ngành, quy mô); chấm công ty đích bằng phân vị này (không dùng lịch sử công ty). So với Novelty. Chạy P3 với chế độ "không lịch sử".
- **Thành công:** recall@B3 ≥ 25% với báo nhầm ≤ 20% ở chế độ không lịch sử.
- **Mã:** `agent2/peer.py` (mới).

### H5. CUSUM theo nhân viên cho lương
- **Lý do:** `payroll_padding` bị L3 bỏ sót (4%) nhưng EntityDeviation bắt 79%; kịch bản "nâng ít" thích hợp phát hiện đổi bậc.
- **Thí nghiệm:** với mỗi nhân viên, thống kê CUSUM hai phía của `log(lương) − log(lương tham chiếu)`; thêm vào EntityDeviation; đánh giá **chỉ** trên `payroll_padding` của các thế giới phát triển (411 đến 413) và trên ca hợp lệ `legit_bonus_run`, `tet_bonus_payroll`.
- **Thành công:** recall@B3 `payroll_padding` ≥ 60% (cả L3 và Novelty) và không tăng báo nhầm lương thưởng hợp lệ quá 3 điểm phần trăm.
- **Cảnh báo quy tắc niêm phong:** thế giới niêm phong có kịch bản `overtime_inflation_group` (nâng lương cả nhóm) rất gần với `payroll_padding`. Nếu bộ phát hiện này được thêm **trước** khi chạy niêm phong, kết quả niêm phong của kịch bản đó **không còn là chưa thấy**: phải ghi chú rõ trong nhật ký và báo cáo riêng kịch bản đó. Cách sạch nhất là chạy niêm phong trước khi thêm H5, hoặc làm tập niêm phong mới sau đó.

### H6. Xu hướng giá và cụm giờ
- **Thí nghiệm:** kiểm định xu hướng (Mann–Kendall hoặc độ dốc hồi quy) trên 6 lần mua gần nhất của nhà cung cấp; đếm số thanh toán khác nhà cung cấp của cùng người lập trong cửa sổ 3 giờ, buổi tối.
- **Thành công:** `price_creep` và `vendor_burst` tăng ít nhất 20 điểm phần trăm ở kênh không nhãn.

### H7. Ngân sách thích ứng
- **Thí nghiệm:** B thay đổi theo tuần theo số giao dịch của công ty (ví dụ `B = clip(round(c × sqrt(n_tuần)), 1, 5)`); hoặc dừng sớm khi điểm dưới ngưỡng conformal.
- **Thành công:** giảm số cảnh báo 20% với mất recall không quá 3 điểm phần trăm.

### H8. Ràng buộc đơn điệu
- **Thí nghiệm:** `monotone_constraints = +1` cho các dấu hiệu đỏ và đuôi thực thể; so với L4 ở P2 và P3.
- **Thành công:** P3 tốt hơn ít nhất 2 điểm hoặc ổn định hơn qua seed.

### H9. Bất biến quy mô tiền
- **Thí nghiệm:** sinh bản của 3 thế giới với `amount_scale ×10` và `×50`; huấn luyện trên ×1, kiểm thử trên ×10, ×50; so bộ đặc trưng thô và bộ đặc trưng chỉ tỷ lệ/log-z.
- **Thành công:** bộ bất biến mất không quá 5 điểm phần trăm; bộ thô mất nhiều hơn.

### H10. Đường cong học theo số thế giới
- **Thí nghiệm:** huấn luyện trên 1, 2, 4, 8, 16 thế giới; kiểm thử P3 trên 4 thế giới chưa dùng.
- **Thành công:** vẽ được đường cong; xác định điểm bão hòa; quyết định số thế giới cần sinh.

### H11. Bộ hợp nhất học
- **Thí nghiệm:** logistic hai đầu vào [điểm L4 chuẩn hóa, hạng Novelty] huấn luyện trên kiểm định; so với 2+1 và max-rank. Chọn khe trong từng công ty-tuần theo điểm hợp nhất.
- **Thành công:** hơn 2+1 ít nhất 2 điểm ở P2 mà không tăng báo nhầm.

### H12. Đặc trưng đồ thị
- **Thí nghiệm:** với mỗi nhà cung cấp và nhân viên, tính số thực thể chung tài khoản, điện thoại, địa chỉ; tiền chảy qua tài khoản chung 90 ngày; khoảng cách trong đồ thị đến nhân viên. Thêm vào L4.
- **Thành công:** `ghost_employee`, `shell_vendor`, `undisclosed_related_vendor` tăng ở P2; kiểm tra không tăng thời gian chạy hơn 2 lần.

### H13. Chấm điểm mức vụ
- **Thí nghiệm:** điểm vụ = `1 − ∏(1 − p_i)` hoặc max; chọn các vụ top-3 mỗi công ty-tuần thay vì dòng; đo vụ tìm thấy và số dòng người dùng phải xem.
- **Thành công:** vụ tìm thấy ≥ 90% ở cùng số mục rà soát.

### H14. Độ trung thực của lý do
- **Thí nghiệm:** tạo lý do bằng mẫu câu; kiểm tự động mọi con số trong câu có trong bằng chứng; thử làm mượt bằng mô hình ngôn ngữ và kiểm tra lại.
- **Thành công:** 100% câu qua kiểm tra; 0 số bịa.
- **Mã:** `agent2/explain_check.py` (mới).

### H15. Học bán giám sát từ phản hồi (PU)
- **Thí nghiệm:** mô phỏng 52 tuần: nhãn "xác nhận" là dương, nhãn "hợp lệ" là âm, chưa xem là không biết; huấn luyện lại L4 định kỳ với ước lượng tiên nghiệm lớp (Elkan–Noto).
- **Thành công:** vượt học lại trọng số kiểu AAD ở nhiễu 15%.

### H16. Độ trôi
- **Thí nghiệm:** huấn luyện 2024, kiểm thử từng tháng 2025; đổi kịch bản giữa các giai đoạn (một nửa kịch bản chỉ xuất hiện ở 2025); so huấn luyện lại hằng quý.
- **Thành công:** xác định mức suy giảm và chu kỳ huấn luyện lại.
