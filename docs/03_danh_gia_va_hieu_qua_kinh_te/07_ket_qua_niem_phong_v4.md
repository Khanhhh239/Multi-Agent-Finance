# Kết quả niêm phong v4 trên dữ liệu tổng hợp

Ngày 2026-10-17. Đây là báo cáo hoàn chỉnh đầu tiên của ba seed 931 đến 933, sau khi đóng băng và thử khô seed 939 thành công. Lần thực thi trước dừng do lỗi cấp phát bộ nhớ, chưa ghi tệp kết quả hoặc in chỉ số từng phần; chạy lại theo ngoại lệ hạ tầng của A5. Không điều chỉnh phương pháp hoặc chọn lại cấu hình theo kết quả này.

Cấu hình đã chọn: **L4-FB**. Khởi đầu lạnh: **Novelty max(R,E)**. Ngân sách ba dòng mỗi công ty mỗi tuần. S1 ẩn nhãn bảy kịch bản mới trong lịch sử của công ty; S2 học có giám sát từ ba thế giới phát triển và dùng lịch sử không nhãn của công ty đích.

## Cấu hình đã chọn

Đơn vị phần trăm. Số vụ được thể hiện bằng tỷ lệ vụ tìm thấy; số dòng gian lận kiểm thử và dòng mới có trong JSON gốc.

| Thế giới | Giao thức | Recall chung | Đã biết | Mới | Vụ tìm thấy | Báo nhầm ca mới | Báo nhầm toàn bộ ca khó | Giảm so P1 (điểm) | G5 |
|---|---|---:|---:|---:|---:|---:|---:|---:|:---:|
| s4_s931 | S1 | 43.75 | 56.50 | 22.50 | 65.15 | 6.84 | 7.09 | 37.06 | Không đạt |
| s4_s931 | S2 | 61.88 | 80.50 | 30.83 | 83.33 | 6.84 | 10.67 | 18.94 | Không đạt |
| s4_s932 | S1 | 51.66 | 62.30 | 29.55 | 80.65 | 6.45 | 13.48 | 29.15 | Không đạt |
| s4_s932 | S2 | 73.06 | 87.43 | 43.18 | 87.10 | 13.82 | 12.53 | 7.75 | Đạt |
| s4_s933 | S1 | 28.52 | 41.82 | 8.93 | 59.65 | 5.51 | 10.54 | 52.29 | Không đạt |
| s4_s933 | S2 | 56.68 | 81.82 | 19.64 | 85.96 | 12.50 | 10.98 | 24.13 | Không đạt |
| Trung bình đều | S1 | 41.31 | 53.54 | 20.32 | 68.48 | 6.27 | 10.37 | 39.50 | Xem từng thế giới |
| Trung bình đều | S2 | 63.87 | 83.25 | 31.22 | 85.47 | 11.05 | 11.39 | 16.94 | Xem từng thế giới |

## Kết luận cổng

G5 không đạt theo trung bình đều ba thế giới, kiểm riêng S1 và S2, cùng cách tổng hợp các thế giới ở G1. Bảng phía trên giữ cả kết quả từng thế giới; toàn bộ sáu cặp riêng lẻ không đồng loạt đạt. Bảng kiểm máy đọc được ở `results/v4/sealed_gates.json`. P1 phát triển của cấu hình chọn là 80.81%; chênh so với niêm phong là khác biệt phân phối tổng hợp, không đo mức suy giảm trên doanh nghiệp thật.

**Điều kiện dừng toàn dự án đã kích hoạt.** Dừng phát triển và triển khai tiếp; báo chủ dự án xem lại bài toán theo mục điều kiện dừng của kế hoạch.

Theo quy tắc G5, quay lại phát triển và cần tập niêm phong mới cho vòng sau. Không chỉnh mô hình trên ba seed này rồi chạy lại. Mô hình hoặc công cụ cục bộ sau A5 chỉ là hiện vật nghiên cứu, chưa được chấp nhận để thí điểm.

Trong lần này, điều kiện dừng M2 được ưu tiên: không tự bắt đầu vòng phát triển mới, huấn luyện v2 hoặc tiếp tục thí điểm. Chủ dự án cần xem lại bài toán trước khi xác định hướng công việc mới. Không có mô hình v2 hoặc cấu hình triển khai chính thức được tạo từ lượt chạy này.

## Bảy kịch bản mới, tất cả ứng viên

Các ô là recall phần trăm, trung bình đều theo ba thế giới. JSON gốc giữ số từng thế giới. Bảng chỉ phục vụ chẩn đoán; cấu hình đã chọn không thay đổi.

### S1

| Cấu hình | advance_kiting | cash_withdrawal_skim | fake_lease_vendor | fake_tax_payment | overtime_inflation_group | phantom_sales_real_dealers | underpriced_sales_kickback |
|---|---:|---:|---:|---:|---:|---:|---:|
| Rules+Graph (friend) | 0.0 | 8.3 | 72.2 | 0.0 | 0.0 | 4.6 | 3.0 |
| Novelty max(R,E) | 0.0 | 8.3 | 27.8 | 0.0 | 22.6 | 15.7 | 3.0 |
| Novelty max(R,E,AE) | 0.0 | 8.3 | 61.1 | 0.0 | 20.2 | 14.6 | 2.0 |
| L3 | 60.0 | 50.0 | 66.7 | 69.3 | 2.6 | 36.2 | 12.1 |
| L3-FB | 60.0 | 20.8 | 33.3 | 69.4 | 5.9 | 30.4 | 5.9 |
| L4 | 53.3 | 25.0 | 66.7 | 68.3 | 9.0 | 32.7 | 5.6 |
| L4-FB | 53.3 | 26.4 | 27.8 | 43.9 | 5.9 | 27.0 | 6.6 |
| C-L4 | 26.7 | 25.0 | 72.2 | 61.7 | 9.6 | 29.3 | 10.3 |
| C-L4-FB | 53.3 | 29.2 | 38.9 | 55.0 | 2.6 | 28.4 | 11.1 |
| L3 2+1 Nmax(R,E) | 60.0 | 45.8 | 50.0 | 69.3 | 7.2 | 31.8 | 3.0 |
| L3 2+1 Nmax(R,E,AE) | 60.0 | 45.8 | 88.9 | 69.3 | 7.2 | 29.5 | 3.0 |
| L3-FB 2+1 Nmax(R,E) | 56.7 | 25.0 | 33.3 | 63.9 | 11.8 | 30.5 | 3.0 |
| L3-FB 2+1 Nmax(R,E,AE) | 56.7 | 25.0 | 72.2 | 63.9 | 11.8 | 28.2 | 2.0 |
| L4 2+1 Nmax(R,E) | 50.0 | 25.0 | 66.7 | 64.6 | 10.4 | 27.1 | 3.6 |
| L4 2+1 Nmax(R,E,AE) | 50.0 | 25.0 | 77.8 | 64.6 | 10.4 | 25.9 | 2.6 |
| L4-FB 2+1 Nmax(R,E) | 53.3 | 25.0 | 27.8 | 40.2 | 8.5 | 28.2 | 6.1 |
| L4-FB 2+1 Nmax(R,E,AE) | 53.3 | 25.0 | 72.2 | 40.2 | 8.5 | 25.9 | 5.1 |
| C-L4 2+1 Nmax(R,E) | 26.7 | 25.0 | 66.7 | 58.0 | 11.6 | 25.9 | 10.7 |
| C-L4 2+1 Nmax(R,E,AE) | 26.7 | 25.0 | 77.8 | 58.0 | 11.6 | 24.8 | 9.7 |
| C-L4-FB 2+1 Nmax(R,E) | 53.3 | 27.8 | 38.9 | 51.3 | 8.5 | 26.1 | 8.1 |
| C-L4-FB 2+1 Nmax(R,E,AE) | 53.3 | 27.8 | 83.3 | 51.3 | 8.5 | 23.8 | 7.1 |
| max(L3,max(R,E)) | 60.0 | 45.8 | 72.2 | 62.6 | 13.1 | 26.1 | 6.1 |
| max(L4-FB,max(R,E)) | 53.3 | 25.0 | 38.9 | 33.7 | 10.9 | 21.5 | 6.1 |
| max(C-L4-FB,max(R,E)) | 53.3 | 27.8 | 55.6 | 52.2 | 12.4 | 23.9 | 7.1 |

### S2

| Cấu hình | advance_kiting | cash_withdrawal_skim | fake_lease_vendor | fake_tax_payment | overtime_inflation_group | phantom_sales_real_dealers | underpriced_sales_kickback |
|---|---:|---:|---:|---:|---:|---:|---:|
| Rules+Graph (friend) | 0.0 | 8.3 | 72.2 | 0.0 | 0.0 | 4.6 | 3.0 |
| Novelty max(R,E) | 0.0 | 8.3 | 27.8 | 0.0 | 22.6 | 15.7 | 3.0 |
| Novelty max(R,E,AE) | 0.0 | 8.3 | 61.1 | 0.0 | 20.2 | 14.6 | 2.0 |
| L3 | 28.3 | 29.2 | 72.2 | 66.1 | 5.5 | 35.9 | 0.0 |
| L3-FB | 10.0 | 29.2 | 50.0 | 55.0 | 5.2 | 34.8 | 0.0 |
| L4 | 66.7 | 47.2 | 83.3 | 52.2 | 14.1 | 27.0 | 10.6 |
| L4-FB | 60.0 | 47.2 | 100.0 | 63.3 | 17.5 | 27.0 | 15.1 |
| C-L4 | 56.7 | 29.2 | 66.7 | 55.0 | 14.3 | 29.2 | 6.6 |
| C-L4-FB | 60.0 | 25.0 | 100.0 | 54.1 | 9.2 | 29.2 | 9.6 |
| L3 2+1 Nmax(R,E) | 10.0 | 29.2 | 55.6 | 54.1 | 11.5 | 33.8 | 2.0 |
| L3 2+1 Nmax(R,E,AE) | 10.0 | 29.2 | 72.2 | 54.1 | 11.5 | 30.3 | 0.0 |
| L3-FB 2+1 Nmax(R,E) | 10.0 | 29.2 | 50.0 | 48.5 | 13.7 | 30.4 | 2.0 |
| L3-FB 2+1 Nmax(R,E,AE) | 10.0 | 29.2 | 66.7 | 48.5 | 13.7 | 26.9 | 0.0 |
| L4 2+1 Nmax(R,E) | 63.3 | 36.1 | 83.3 | 44.8 | 16.8 | 25.9 | 11.6 |
| L4 2+1 Nmax(R,E,AE) | 63.3 | 36.1 | 100.0 | 44.8 | 16.8 | 22.5 | 9.6 |
| L4-FB 2+1 Nmax(R,E) | 60.0 | 30.6 | 100.0 | 51.3 | 13.7 | 28.2 | 10.6 |
| L4-FB 2+1 Nmax(R,E,AE) | 60.0 | 30.6 | 100.0 | 51.3 | 13.7 | 24.8 | 8.5 |
| C-L4 2+1 Nmax(R,E) | 53.3 | 20.8 | 66.7 | 47.6 | 13.0 | 28.2 | 6.0 |
| C-L4 2+1 Nmax(R,E,AE) | 53.3 | 20.8 | 66.7 | 47.6 | 13.0 | 24.7 | 5.0 |
| C-L4-FB 2+1 Nmax(R,E) | 60.0 | 25.0 | 83.3 | 34.4 | 12.4 | 30.4 | 9.6 |
| C-L4-FB 2+1 Nmax(R,E,AE) | 60.0 | 25.0 | 100.0 | 34.4 | 12.4 | 27.0 | 8.6 |
| max(L3,max(R,E)) | 13.3 | 25.0 | 66.7 | 63.3 | 7.6 | 24.8 | 1.0 |
| max(L4-FB,max(R,E)) | 60.0 | 30.6 | 100.0 | 60.6 | 17.0 | 24.8 | 10.6 |
| max(C-L4-FB,max(R,E)) | 51.7 | 25.0 | 100.0 | 47.4 | 16.5 | 24.8 | 8.6 |

## Hạn chế

Bộ sinh, kịch bản và phương pháp do cùng nhóm phát triển, nên niêm phong v4 chưa độc lập tuyệt đối. `overtime_inflation_group` gần `payroll_padding`; chưa thêm CUSUM hoặc đặc trưng nhắm vào kịch bản mới trước niêm phong. Kết quả có thể thuận lợi hơn thực tế vì cùng người thiết kế đặc trưng và dữ liệu.

Mọi số liệu là tổng hợp. Nhãn ẩn mô phỏng gian lận chưa được phát hiện, không thay thế điều tra nghiệp vụ. Chưa có dữ liệu doanh nghiệp, xác nhận độc lập, đánh giá người dùng hoặc hiệu quả kinh tế thật.
