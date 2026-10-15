# Lịch sử phiên bản dữ liệu

| Phiên bản | Ai, khi nào | Đặc điểm | Vấn đề đã tìm ra | Trạng thái |
|---|---|---|---|---|
| **v2** | Bạn bạn (`sme_fraud/generate.py`) | 8 công ty; 6 họ gian lận; 31 luật viết cho đúng 6 họ đó | (1) mọi nhà cung cấp nền được tạo cùng ngày 2023-01-01; (2) một tiền tố tên chung cho nhà cung cấp nền; (3) 31 luật viết cho 6 kịch bản chèn: **vòng tròn**, nên luật đạt AP 0,60 | Giữ nguyên bản sao `friend_zipp/` để tái lập |
| **v3** | Tôi (`agent2/world_v3.py`) kế thừa v2 | Độ khó phân bậc; 3 họ không có luật viết sẵn; ca hợp lệ giống gian lận; ngày onboard nhà cung cấp trải dài | Ngày lương luôn là ngày 28 và các bộ sinh chia sẻ cơ chế, làm kịch bản như `off_cycle_payroll` quá dễ; chỉ 8 công ty; gian lận sinh từ công thức cố định | Dùng làm tập niêm phong v3 (3 họ mới, chạy một lần) |
| **v4 phát triển** | Tôi (`agent2/world_v4.py`, `world_v4_schemes.py`) | 48 công ty ngẫu nhiên hóa; quy trình nền có liên kết; 30 kịch bản; bảng `truth_cases`; kiểm tra lối tắt; 5 loại bút toán mới | Xem DATA_V4.md mục 1: các điểm phản biện (ví dụ `put(dict(r))`, `payroll_padding` chỉnh dòng sẵn có, tràn cửa sổ thời gian) đã kiểm chứng trong mã và sửa | Dùng để chọn phương pháp |
| **v4 niêm phong** | Tôi (`agent2/world_v4_sealed.py`) | 40 công ty; 7 kịch bản mới; 5 loại ca hợp lệ mới; 35% công ty đổi lịch trả lương | — | Đã sinh, **chưa chạy bộ phát hiện** |

## Sai sót phát sinh khi làm v4 và cách sửa (để người sau không lặp lại)

| Lỗi | Nguyên nhân | Sửa |
|---|---|---|
| Người lập lương hoặc bán hàng là nhân viên thay thế chưa vào làm | Luân chuyển nhân sự áp cho cả nhóm đầu | Chỉ áp cho nhân sự thứ 10 trở đi; vụ phải do người còn làm việc từ đầu đến cuối vụ |
| Dữ liệu chủ tương lai trong tạm ứng | Mã của bạn bạn chọn nhân viên chưa vào làm | Ghi đè `advance`, `inject_normal_advances`, `context`, chọn nhân viên đang làm |
| `StopIteration` khi kiểm tra kế toán | `put` trả về chỉ số dòng thay vì mã giao dịch | `put` trả về `transaction_id` |
| Cấp người thực hiện lệch (68/23/9) | Chọn theo vai trò chứ không theo trọng số ACFE | Chọn cấp theo 37/41/19 trong số ứng viên khả dụng; kết quả thực khoảng 40/51/9 |
| Kiểm tra lối tắt AUC 0,57 | Cơ cấu loại nghiệp vụ của gian lận khác nền | Đổi cách đo: mức tăng AUC khi thêm trường vô nghĩa so với chỉ dùng loại nghiệp vụ |
| Thanh toán nhà cung cấp ma vượt cửa sổ thời gian (phát hiện khi sinh tập niêm phong v3) | `9 ngày × j` không bị chặn | Giới hạn trong cửa sổ, không đổi dãy số ngẫu nhiên; các bộ phát triển vẫn hợp lệ |
