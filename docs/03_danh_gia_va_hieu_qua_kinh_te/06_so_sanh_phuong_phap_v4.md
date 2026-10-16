# So sánh phương pháp v4 trên dữ liệu tổng hợp

Ngày 2026-10-16. Ba thế giới phát triển 411, 412, 413; 24 cấu hình; P2 trung bình đều theo 10 nhánh ACFE. Không dùng tập niêm phong để chọn cấu hình.

## Điểm phát triển

Các số trong bảng là phần trăm. P1 là cùng thế giới theo thời gian; P2 bỏ một nhánh; P3 chuyển sang thế giới mới.

| Cấu hình | P1 | P2 | P3 | Điểm | Báo nhầm ca khó P1 | Đủ điều kiện |
|---|---:|---:|---:|---:|---:|:---:|
| Rules+Graph (friend) | 27.05 | 27.28 | 27.05 | 27.13 | 16.22 | Có |
| Novelty max(R,E) | 39.52 | 41.39 | 39.52 | 40.14 | 15.11 | Có |
| Novelty max(R,E,AE) | 44.47 | 53.90 | 44.47 | 47.61 | 24.59 | Không |
| L3 | 77.46 | 51.95 | 83.89 | 71.10 | 16.54 | Có |
| L3-FB | 77.28 | 57.22 | 84.44 | 72.98 | 16.03 | Có |
| L4 | 80.94 | 58.63 | 76.91 | 72.16 | 16.87 | Có |
| L4-FB | 80.81 | 59.06 | 82.62 | 74.16 | 16.62 | Có |
| C-L4 | 78.79 | 54.45 | 74.20 | 69.15 | 15.12 | Có |
| C-L4-FB | 78.06 | 57.79 | 78.79 | 71.55 | 14.59 | Có |
| L3 2+1 Nmax(R,E) | 76.75 | 64.69 | 79.41 | 73.62 | 16.05 | Có |
| L3 2+1 Nmax(R,E,AE) | 76.33 | 64.29 | 79.12 | 73.25 | 20.63 | Không |
| L3-FB 2+1 Nmax(R,E) | 75.56 | 64.90 | 79.39 | 73.28 | 15.70 | Có |
| L3-FB 2+1 Nmax(R,E,AE) | 75.58 | 64.51 | 79.39 | 73.16 | 20.36 | Không |
| L4 2+1 Nmax(R,E) | 77.75 | 66.55 | 72.84 | 72.38 | 16.11 | Có |
| L4 2+1 Nmax(R,E,AE) | 77.03 | 66.51 | 72.70 | 72.08 | 20.91 | Không |
| L4-FB 2+1 Nmax(R,E) | 77.89 | 66.15 | 79.83 | 74.62 | 15.72 | Có |
| L4-FB 2+1 Nmax(R,E,AE) | 77.47 | 66.10 | 79.27 | 74.28 | 20.33 | Không |
| C-L4 2+1 Nmax(R,E) | 78.05 | 65.12 | 73.60 | 72.25 | 15.10 | Có |
| C-L4 2+1 Nmax(R,E,AE) | 77.91 | 66.05 | 73.33 | 72.43 | 19.58 | Có |
| C-L4-FB 2+1 Nmax(R,E) | 76.31 | 64.03 | 77.18 | 72.51 | 14.60 | Có |
| C-L4-FB 2+1 Nmax(R,E,AE) | 75.46 | 65.27 | 76.61 | 72.45 | 19.22 | Có |
| max(L3,max(R,E)) | 77.89 | 63.03 | 80.42 | 73.78 | 14.55 | Có |
| max(L4-FB,max(R,E)) | 79.20 | 64.89 | 80.57 | 74.89 | 14.54 | Có |
| max(C-L4-FB,max(R,E)) | 77.46 | 66.43 | 79.21 | 74.36 | 14.12 | Có |

## Chênh lệch ghép cặp so với L3 ở P1

Bootstrap 2.000 lần, seed 0, lấy lại mẫu toàn bộ vụ theo khóa công ty và vụ, dùng cùng lần lấy cho hai cấu hình. Giữ cố định cờ cảnh báo và ngân sách đã chọn; không chọn lại ngưỡng trong từng lần lấy mẫu. Dòng hợp lệ không ảnh hưởng hai chỉ số recall nên được tích phân bỏ qua chính xác. Khoảng là percentile 95%, không hiệu chỉnh nhiều so sánh.

| Thế giới | Cấu hình trừ L3 | Hiệu recall (điểm phần trăm) | Khoảng 95% | Hiệu số vụ tìm thấy | Khoảng 95% |
|---|---|---:|---|---:|---|
| w4_s411 | L4 | 3.14 | [-2.15; 9.36] | 0 | [0; 0] |
| w4_s411 | L4-FB | 4.04 | [-2.88; 12.25] | 2 | [0; 5] |
| w4_s411 | L3-FB | -2.69 | [-7.21; 2.08] | 0 | [-3; 3] |
| w4_s411 | C-L4 | 2.69 | [-3.67; 10.62] | 0 | [-3; 3] |
| w4_s412 | L4 | 1.71 | [-3.23; 7.11] | 3 | [-1; 8] |
| w4_s412 | L4-FB | 2.14 | [-2.41; 6.70] | 1 | [-3; 5] |
| w4_s412 | L3-FB | -0.85 | [-5.10; 3.23] | 0 | [-5; 5] |
| w4_s412 | C-L4 | -0.85 | [-7.27; 6.67] | -3 | [-9; 3] |
| w4_s413 | L4 | 5.60 | [0.00; 12.10] | 0 | [-3; 3] |
| w4_s413 | L4-FB | 3.88 | [-3.08; 11.43] | 1 | [0; 3] |
| w4_s413 | L3-FB | 3.02 | [-3.49; 11.02] | 3 | [-1; 7] |
| w4_s413 | C-L4 | 2.16 | [-4.15; 9.42] | 0 | [-4; 4] |

## Kết luận theo giả thuyết đã đặt

H1 chưa đạt: L4 và L4-FB tăng P2 trung bình so với L3 nhưng P3 không hơn L3 5 điểm phần trăm; các khoảng P1 không loại trừ 0. Không thể kết luận phương pháp lai vượt L3 chắc chắn.

Cân bằng họ tăng P2 của L3 từ 51,95% lên 57,22%, trong khi P1 giảm 0,18 điểm; đây là tín hiệu phát triển cho H2, chưa đạt đầy đủ tiêu chí H1 về P3 và khoảng tin cậy. Hai tầng C-L4 không cải thiện đồng đều P1, P2, P3 so với L4. Biến thể trí nhớ không nhãn của H3 chưa được thử ở pha này.

Bộ chọn giữ nguyên ràng buộc báo nhầm P1 không quá 20%; nếu chênh điểm nhỏ hơn 0,01 thì chọn ứng viên đứng trước. Vì thế cấu hình được chọn có thể khác ứng viên có điểm số lớn nhất. Kết quả chính thức nằm trong `results/v4/v4_frozen.json` sau A3.

Thực thi ba ứng viên độc lập bằng ba luồng giữ nguyên thứ tự và tham số. Hồi quy P1 411 cho cờ cảnh báo của toàn bộ 24 cấu hình giống hệt bản nối tiếp trên 50.713 dòng; bằng chứng `results/v4/execution_regression.json`. Mọi số liệu chỉ mô tả dữ liệu tổng hợp, không phải độ chính xác thực tế.
