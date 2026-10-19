# Mổ xẻ hậu kiểm v4 trên dữ liệu tổng hợp

Ngày 2026-10-19. **Hậu kiểm, không phải niêm phong.** Chủ dự án đã cho phép dùng ba thế giới v4 đã lộ để chẩn đoán. Mọi số đo trong tài liệu là trên **dữ liệu tổng hợp**. Kết luận **v4 không đạt G5 và kích hoạt M2** giữ nguyên; không dùng bất kỳ biến thể nào dưới đây để viết lại kết quả v4 hoặc làm bằng chứng xác nhận v5.

## Các kết quả chính của hậu kiểm

- Can thiệp biết trước loại dòng mới chỉ khỏi huấn luyện làm recall L4-FB thay đổi **5,59 [1,41; 9,91] điểm phần trăm**, trung bình đều ba thế giới. Đây là can thiệp dùng nhãn thật tổng hợp, không phải kết quả triển khai.
- Giảm trọng số mọi nhãn 0 xuống 0,2 làm recall L4-FB thay đổi **10,07 [6,86; 13,40] điểm phần trăm**. Không chọn một hệ số khác sau kết quả này.
- Chênh S1 L4-FB giữa trung bình 931, 932 và seed 933 là 19,19 điểm; phần cơ cấu họ là 7,05, phần tỷ lệ phát hiện trong họ là 12,13. Đây là phân rã mô tả, không phải chứng minh nhân quả.
- Tổng tụt P1 trừ S1 của L4-FB là **39,50 [32,55; 45,34] điểm**; năm thành phần tại mục 5 cộng đúng về tổng này. V4 vẫn không đạt G5.

## Phạm vi và kiểm chứng

Ba phương pháp: L3, L4-FB và `Novelty max(R,E)`; tên Novelty trong giao việc được hiểu là cấu hình khởi đầu lạnh đã chọn ở v4. Giữ nguyên sáu tệp khóa, các đặc trưng, hai cấu hình cây, seed, thời gian và ngân sách ba dòng mỗi công ty mỗi tuần. Dùng đúng bộ đệm đặc trưng v4 lịch sử, không dựng lại bằng bộ luật khác.

Đã tái lập chỉ số S1 và S2 gốc cho cả ba phương pháp ở cả ba thế giới, đối chiếu các trường số ngoài AP, gồm cảnh báo, recall, vụ, ca khó và từng kịch bản với `results/v4/sealed_v4.json`, dung sai tuyệt đối 0,000000000001. Mọi phép đối chiếu qua trước khi thực hiện can thiệp của thế giới tương ứng. Tệp kết quả, khóa và báo cáo niêm phong v4 không đổi băm.

Hai lượt đầu dừng vì AP L3 S1 931 lệch 0,00000000075098569 trong khi các chỉ số ngân sách khớp. Đã kiểm lại bằng đúng hàm thực thi gốc và vẫn thấy cùng sai khác. Từ lượt 3, chốt giữ nguyên dung sai cho toàn bộ trường ngoài AP, còn AP gốc, AP chạy lại và hiệu được lưu công khai dưới `original_baseline_check.ap_diagnostic_only` của từng JSON. AP không dùng trong R0 để chọn gì hoặc phân rã recall. Nguyên nhân chính xác của sai khác AP chưa xác định; không tuyên bố điểm thô trùng bit. Đây là sửa phạm vi kiểm tái lập, ghi trước mọi can thiệp, không phải thay mô hình hoặc cổng v4.

Báo cáo niêm phong gốc không lưu cờ cảnh báo từng dòng. Vì vậy đối chiếu trên đây chứng minh các chỉ số tổng hợp và theo họ khớp, không chứng minh từng dòng được chọn giống hệt. Bootstrap R0 dùng cờ của lượt hậu kiểm; cờ P1 phát triển lấy từ NPZ gốc đã lưu.

Mã: `agent2/postmortem_v4.py`. Kết quả hoàn chỉnh: `results/v5/postmortem_v4/run3/`; `manifest.json` ghi băm mã, CSV, bộ đệm, cờ P1 và tệp v4 được bảo vệ. JSON được lưu sau từng giao thức; tổng hợp tại `summary.json`. Hai manifest lần dừng trước được giữ ở thư mục cha và `run2`, không được dùng như kết quả hoàn chỉnh.

AP so sánh toàn bộ thứ hạng, không phải recall tại ngân sách. Bảng dưới dùng thang AP từ 0 đến 1, ghi đủ chữ số để đối chiếu sai khác; không thay số lịch sử.

| Thế giới | Giao thức | Phương pháp | AP lịch sử | AP hậu kiểm | Hiệu |
|---|---|---|---:|---:|---:|
| s4_s931 | S1 gốc | L3 | 0,164222356150 | 0,164222356150 | 0,000e+00 |
| s4_s931 | S1 gốc | L4-FB | 0,325074872246 | 0,325074872246 | 0,000e+00 |
| s4_s931 | S1 gốc | Novelty max(R,E) | 0,053109451508 | 0,053109451508 | 0,000e+00 |
| s4_s931 | S2 gốc | L3 | 0,510706010772 | 0,510706010772 | 0,000e+00 |
| s4_s931 | S2 gốc | L4-FB | 0,534889722663 | 0,534889722663 | 0,000e+00 |
| s4_s931 | S2 gốc | Novelty max(R,E) | 0,053109451508 | 0,053109451508 | 0,000e+00 |
| s4_s932 | S1 gốc | L3 | 0,341719212392 | 0,341719212392 | 0,000e+00 |
| s4_s932 | S1 gốc | L4-FB | 0,302350884078 | 0,302350884078 | 0,000e+00 |
| s4_s932 | S1 gốc | Novelty max(R,E) | 0,075901534551 | 0,075901534551 | 0,000e+00 |
| s4_s932 | S2 gốc | L3 | 0,517585108410 | 0,517585108410 | 0,000e+00 |
| s4_s932 | S2 gốc | L4-FB | 0,577996564202 | 0,577996564202 | 0,000e+00 |
| s4_s932 | S2 gốc | Novelty max(R,E) | 0,075901534551 | 0,075901534551 | 0,000e+00 |
| s4_s933 | S1 gốc | L3 | 0,116332740177 | 0,116332740177 | 0,000e+00 |
| s4_s933 | S1 gốc | L4-FB | 0,193038417757 | 0,193038417757 | 0,000e+00 |
| s4_s933 | S1 gốc | Novelty max(R,E) | 0,067050392994 | 0,067050392994 | 0,000e+00 |
| s4_s933 | S2 gốc | L3 | 0,433891112655 | 0,433891112655 | 0,000e+00 |
| s4_s933 | S2 gốc | L4-FB | 0,443010182045 | 0,443010182045 | 0,000e+00 |
| s4_s933 | S2 gốc | Novelty max(R,E) | 0,067050392994 | 0,067050392994 | 0,000e+00 |

Ở lượt hoàn chỉnh, chênh AP tuyệt đối lớn nhất của 18 cặp là 0. Hai sai khác của lượt đã dừng vẫn được giữ trong lịch sử; không vì lượt cuối khớp mà xóa dấu vết đó.

## 1. Độ nhạy với nhãn chưa biết

S1 gốc giữ dòng của bảy kịch bản mới trong lịch sử và đặt nhãn thành 0. Hai can thiệp loại bỏ dùng nhãn thật của dữ liệu tổng hợp để biết phải loại dòng nào: đây là đối chiếu biết trước, không phải cách xử lý khả thi khi vận hành. Biến thể trọng số giữ nguyên mọi dòng, nhân trọng số của **mọi dòng nhãn 0** trong huấn luyện với 0,2; không thử hệ số khác. Nhãn và AP kiểm định của biến thể này giữ nguyên. Cân bằng trọng số họ dương của L4-FB giữ nguyên.

Tham chiếu của kênh Novelty và các đầu ra không nhãn đã tính sẵn giữ nguyên trong mọi biến thể; do đó Novelty là đối chứng không bị tác động trực tiếp bởi nhãn. Loại dòng huấn luyện cũng thay đổi số dòng và hệ số cân bằng lớp; hiệu ứng quan sát không được gọi là tác động nhân quả thuần của nhiễu nhãn.

Trung bình đều ba thế giới, đơn vị phần trăm. Cột cuối là hiệu so với S1 gốc và khoảng bootstrap 95%, đơn vị điểm phần trăm.

| Phương pháp | Giao thức | Recall chung | Đã biết | Mới | Báo nhầm ca khó | Hiệu recall so S1 gốc [95%] |
|---|---|---:|---:|---:|---:|---:|
| L3 | S1 gốc | 44,53 | 54,22 | 27,67 | 10,95 | Không áp dụng |
| L3 | S2 gốc | 61,18 | 83,48 | 23,06 | 14,16 | Không áp dụng |
| L3 | S1 loại khỏi huấn luyện | 39,22 | 45,82 | 27,90 | 12,81 | -5,31 [-9,74; -1,07] |
| L3 | S1 loại khỏi huấn luyện và kiểm định | 41,07 | 47,62 | 29,79 | 12,45 | -3,46 [-7,83; 0,50] |
| L3 | S1 trọng số nhãn 0 bằng 0,2 | 41,42 | 51,64 | 24,20 | 12,70 | -3,10 [-7,75; 1,11] |
| L4-FB | S1 gốc | 41,31 | 53,54 | 20,32 | 10,37 | Không áp dụng |
| L4-FB | S2 gốc | 63,87 | 83,25 | 31,22 | 11,39 | Không áp dụng |
| L4-FB | S1 loại khỏi huấn luyện | 46,90 | 58,29 | 27,28 | 10,96 | 5,59 [1,41; 9,91] |
| L4-FB | S1 loại khỏi huấn luyện và kiểm định | 47,38 | 58,73 | 27,86 | 10,93 | 6,07 [1,88; 10,54] |
| L4-FB | S1 trọng số nhãn 0 bằng 0,2 | 51,38 | 66,17 | 26,21 | 12,86 | 10,07 [6,86; 13,40] |
| Novelty max(R,E) | S1 gốc | 28,08 | 37,44 | 12,07 | 13,34 | Không áp dụng |
| Novelty max(R,E) | S2 gốc | 28,08 | 37,44 | 12,07 | 13,34 | Không áp dụng |
| Novelty max(R,E) | S1 loại khỏi huấn luyện | 28,08 | 37,44 | 12,07 | 13,34 | 0,00 [0,00; 0,00] |
| Novelty max(R,E) | S1 loại khỏi huấn luyện và kiểm định | 28,08 | 37,44 | 12,07 | 13,34 | 0,00 [0,00; 0,00] |
| Novelty max(R,E) | S1 trọng số nhãn 0 bằng 0,2 | 28,08 | 37,44 | 12,07 | 13,34 | 0,00 [0,00; 0,00] |

Hiệu theo từng thế giới giúp tránh che mất bất ổn giữa các seed. Mọi khoảng dưới đây ghép cặp nguyên vụ trên cùng tập kiểm thử, không khớp lại mô hình.

| Thế giới | Phương pháp | Loại huấn luyện [95%] | Loại cả kiểm định [95%] | Trọng số 0,2 [95%] |
|---|---|---:|---:|---:|
| s4_s931 | L3 | -0,62 [-8,16; 6,98] | -0,62 [-8,16; 6,98] | 0,62 [-6,23; 7,10] |
| s4_s931 | L4-FB | 5,00 [-2,22; 11,95] | 5,00 [-2,87; 12,70] | 13,75 [8,21; 19,36] |
| s4_s931 | Novelty max(R,E) | 0,00 [0,00; 0,00] | 0,00 [0,00; 0,00] | 0,00 [0,00; 0,00] |
| s4_s932 | L3 | -5,90 [-12,37; 0,00] | 0,00 [-5,53; 5,13] | -8,49 [-17,62; 0,32] |
| s4_s932 | L4-FB | 9,59 [1,88; 17,56] | 9,59 [1,88; 17,56] | 9,96 [4,84; 15,47] |
| s4_s932 | Novelty max(R,E) | 0,00 [0,00; 0,00] | 0,00 [0,00; 0,00] | 0,00 [0,00; 0,00] |
| s4_s933 | L3 | -9,39 [-18,80; -1,83] | -9,75 [-18,98; -2,37] | -1,44 [-9,18; 5,70] |
| s4_s933 | L4-FB | 2,17 [-5,20; 9,89] | 3,61 [-3,52; 11,31] | 6,50 [0,92; 13,19] |
| s4_s933 | Novelty max(R,E) | 0,00 [0,00; 0,00] | 0,00 [0,00; 0,00] | 0,00 [0,00; 0,00] |

JSON còn giữ riêng hiệu trên kịch bản đã biết và mới; không chọn biến thể tốt nhất làm cấu hình v5 từ bảng hậu kiểm này.

## 2. Lịch lương và quy mô công ty

Nhóm đổi lịch là các lịch ngày 1, ngày 20 hoặc ngày 7 và 22, đúng phép thay lịch trong bộ sinh v4 niêm phong; các lịch này không xuất hiện trong danh mục lịch phát triển. Nhóm quy mô lấy trực tiếp `size_class`, không phân nhóm lại theo kết quả. Chỉ tính dòng gian lận của các kịch bản **đã biết**. Các ô là recall phần trăm và khoảng bootstrap 95%.

| Thế giới | Giao thức | Nhóm | Dòng gian lận | Vụ | L3 [95%] | L4-FB [95%] | Novelty [95%] |
|---|---|---|---:|---:|---:|---:|---:|
| s4_s931 | S1 gốc | pay_shift: changed | 81 | 19 | 39,51 [18,46; 60,01] | 49,38 [29,85; 66,67] | 48,15 [29,47; 67,13] |
| s4_s931 | S1 gốc | pay_shift: unchanged | 119 | 24 | 57,14 [37,41; 74,24] | 61,34 [44,95; 76,70] | 38,66 [25,19; 52,22] |
| s4_s931 | S1 gốc | size_class: micro | 91 | 19 | 46,15 [23,47; 68,52] | 63,74 [45,78; 80,00] | 51,65 [35,62; 70,37] |
| s4_s931 | S1 gốc | size_class: small | 109 | 24 | 53,21 [34,78; 70,11] | 50,46 [34,29; 68,00] | 34,86 [21,49; 49,52] |
| s4_s931 | S2 gốc | pay_shift: changed | 81 | 19 | 74,07 [56,16; 88,89] | 76,54 [58,44; 92,11] | 48,15 [29,47; 67,13] |
| s4_s931 | S2 gốc | pay_shift: unchanged | 119 | 24 | 89,92 [82,30; 96,12] | 83,19 [70,23; 93,75] | 38,66 [25,19; 52,22] |
| s4_s931 | S2 gốc | size_class: micro | 91 | 19 | 91,21 [82,35; 97,22] | 92,31 [82,95; 98,10] | 51,65 [35,62; 70,37] |
| s4_s931 | S2 gốc | size_class: small | 109 | 24 | 77,06 [63,71; 88,78] | 70,64 [55,43; 84,96] | 34,86 [21,49; 49,52] |
| s4_s932 | S1 gốc | pay_shift: changed | 65 | 16 | 55,38 [36,00; 72,62] | 60,00 [41,51; 75,71] | 43,08 [23,91; 63,49] |
| s4_s932 | S1 gốc | pay_shift: unchanged | 118 | 31 | 73,73 [60,00; 86,67] | 63,56 [50,98; 77,06] | 34,75 [23,39; 47,01] |
| s4_s932 | S1 gốc | size_class: medium † | 3 | 1 | 0,00 [0,00; 0,00] | 0,00 [0,00; 0,00] | 0,00 [0,00; 0,00] |
| s4_s932 | S1 gốc | size_class: micro | 83 | 21 | 72,29 [58,33; 86,37] | 73,49 [61,72; 85,90] | 44,58 [30,26; 60,30] |
| s4_s932 | S1 gốc | size_class: small | 97 | 25 | 64,95 [47,42; 80,00] | 54,64 [39,16; 69,00] | 32,99 [18,39; 47,25] |
| s4_s932 | S2 gốc | pay_shift: changed | 65 | 16 | 84,62 [67,15; 98,08] | 83,08 [66,03; 96,43] | 43,08 [23,91; 63,49] |
| s4_s932 | S2 gốc | pay_shift: unchanged | 118 | 31 | 87,29 [78,95; 94,66] | 89,83 [80,39; 96,83] | 34,75 [23,39; 47,01] |
| s4_s932 | S2 gốc | size_class: medium † | 3 | 1 | 0,00 [0,00; 0,00] | 0,00 [0,00; 0,00] | 0,00 [0,00; 0,00] |
| s4_s932 | S2 gốc | size_class: micro | 83 | 21 | 91,57 [81,82; 100,00] | 95,18 [84,81; 100,00] | 44,58 [30,26; 60,30] |
| s4_s932 | S2 gốc | size_class: small | 97 | 25 | 84,54 [73,00; 93,48] | 83,51 [70,73; 92,59] | 32,99 [18,39; 47,25] |
| s4_s933 | S1 gốc | pay_shift: changed | 115 | 29 | 39,13 [25,98; 52,85] | 41,74 [27,54; 57,15] | 30,43 [20,31; 41,67] |
| s4_s933 | S1 gốc | pay_shift: unchanged | 50 | 13 | 60,00 [46,94; 73,33] | 42,00 [23,21; 65,71] | 36,00 [16,95; 59,19] |
| s4_s933 | S1 gốc | size_class: medium | 95 | 22 | 46,32 [30,12; 61,35] | 46,32 [29,81; 64,13] | 25,26 [14,29; 37,12] |
| s4_s933 | S1 gốc | size_class: micro † | 26 | 8 | 50,00 [34,21; 76,19] | 57,69 [42,10; 77,79] | 38,46 [17,39; 66,67] |
| s4_s933 | S1 gốc | size_class: small | 44 | 12 | 40,91 [21,27; 62,16] | 22,73 [7,41; 43,90] | 43,18 [21,95; 66,67] |
| s4_s933 | S2 gốc | pay_shift: changed | 115 | 29 | 83,48 [71,79; 93,58] | 82,61 [71,30; 92,23] | 30,43 [20,31; 41,67] |
| s4_s933 | S2 gốc | pay_shift: unchanged | 50 | 13 | 74,00 [57,62; 91,11] | 80,00 [59,61; 96,55] | 36,00 [16,95; 59,19] |
| s4_s933 | S2 gốc | size_class: medium | 95 | 22 | 83,16 [71,42; 92,63] | 84,21 [72,29; 93,18] | 25,26 [14,29; 37,12] |
| s4_s933 | S2 gốc | size_class: micro † | 26 | 8 | 88,46 [70,00; 100,00] | 92,31 [84,21; 100,00] | 38,46 [17,39; 66,67] |
| s4_s933 | S2 gốc | size_class: small | 44 | 12 | 70,45 [47,36; 92,45] | 70,45 [45,95; 93,11] | 43,18 [21,95; 66,67] |

† Ít hơn 10 vụ; khoảng bootstrap có thể rất hẹp hoặc suy biến khi chỉ có một vụ. Đây không phải bằng chứng chắc chắn về nhóm doanh nghiệp thật. JSON giữ cả nhóm chéo lịch lương và quy mô để kiểm tra nhiễu do cơ cấu.

Riêng các kịch bản lương đã biết:

| Thế giới | Giao thức | Lịch | Dòng | Vụ | L3 [95%] | L4-FB [95%] | Novelty [95%] |
|---|---|---|---:|---:|---:|---:|---:|
| s4_s931 | S1 gốc | changed | 4 | 2 | 50,00 [0,00; 100,00] | 0,00 [0,00; 0,00] | 25,00 [0,00; 50,00] |
| s4_s931 | S1 gốc | unchanged | 13 | 4 | 23,08 [0,00; 50,00] | 38,46 [0,00; 83,33] | 46,15 [16,67; 71,43] |
| s4_s931 | S2 gốc | changed | 4 | 2 | 50,00 [0,00; 100,00] | 50,00 [0,00; 100,00] | 25,00 [0,00; 50,00] |
| s4_s931 | S2 gốc | unchanged | 13 | 4 | 84,62 [71,43; 100,00] | 76,92 [50,00; 100,00] | 46,15 [16,67; 71,43] |
| s4_s932 | S1 gốc | changed | 4 | 2 | 50,00 [50,00; 50,00] | 50,00 [0,00; 100,00] | 75,00 [50,00; 100,00] |
| s4_s932 | S1 gốc | unchanged | 9 | 4 | 77,78 [33,33; 100,00] | 66,67 [22,22; 100,00] | 55,56 [10,00; 100,00] |
| s4_s932 | S2 gốc | changed | 4 | 2 | 100,00 [100,00; 100,00] | 75,00 [50,00; 100,00] | 75,00 [50,00; 100,00] |
| s4_s932 | S2 gốc | unchanged | 9 | 4 | 77,78 [33,33; 100,00] | 77,78 [33,33; 100,00] | 55,56 [10,00; 100,00] |
| s4_s933 | S1 gốc | changed | 13 | 4 | 30,77 [0,00; 75,00] | 46,15 [0,00; 100,00] | 30,77 [0,00; 75,00] |
| s4_s933 | S1 gốc | unchanged | 5 | 2 | 80,00 [50,00; 100,00] | 80,00 [50,00; 100,00] | 60,00 [0,00; 100,00] |
| s4_s933 | S2 gốc | changed | 13 | 4 | 61,54 [25,00; 100,00] | 61,54 [25,00; 100,00] | 30,77 [0,00; 75,00] |
| s4_s933 | S2 gốc | unchanged | 5 | 2 | 100,00 [100,00; 100,00] | 100,00 [100,00; 100,00] | 60,00 [0,00; 100,00] |

Lịch lương không được can thiệp ngẫu nhiên độc lập với toàn bộ hồ sơ công ty trong hậu kiểm này. Khác biệt nhóm chỉ là liên hệ; không dùng nó để kết luận riêng lịch lương gây ra mức tụt.

## 3. Tụt theo từng kịch bản đã biết

Mỗi tỷ lệ là trung bình đều ba thế giới của giao thức tương ứng. Hiệu dương nghĩa là recall ở đích thấp hơn P1 phát triển; bảng được xếp theo hiệu giảm lớn nhất, riêng từng phương pháp và giao thức. Tất cả 30 kịch bản đều được giữ, kể cả hiệu âm. Số vụ trong bảng là tổng ba thế giới đích.

### L3, P1 so với S1 gốc

| Kịch bản | P1 phát triển | Đích | Giảm (điểm) | Vụ ở đích | Dòng ở đích |
|---|---:|---:|---:|---:|---:|
| `receivable_lapping` | 89,58 | 24,06 | 65,53 | 10 | 47 |
| `advance_unsettled` | 83,33 | 33,33 | 50,00 | 3 | 3 |
| `undisclosed_related_vendor` | 95,65 | 51,85 | 43,80 | 3 | 24 |
| `bid_rotation` | 83,09 | 41,39 | 41,70 | 5 | 36 |
| `period_end_adjustment` | 91,67 | 50,00 | 41,67 | 4 | 7 |
| `fake_bonus_list` | 57,62 | 16,67 | 40,95 | 3 | 9 |
| `bank_detail_switch` | 72,22 | 33,33 | 38,89 | 3 | 7 |
| `altered_payee` | 96,67 | 58,33 | 38,33 | 4 | 12 |
| `split_payments` | 55,00 | 16,67 | 38,33 | 4 | 11 |
| `owner_override_transfer` | 93,33 | 57,78 | 35,56 | 5 | 10 |
| `unrecorded_sales_skimming` | 100,00 | 66,67 | 33,33 | 3 | 15 |
| `personal_purchase` | 50,91 | 21,57 | 29,34 | 5 | 23 |
| `duplicate_payment` | 83,33 | 55,56 | 27,78 | 3 | 9 |
| `cash_larceny` | 100,00 | 72,71 | 27,29 | 7 | 41 |
| `invoice_mill` | 90,48 | 64,29 | 26,19 | 4 | 15 |
| `inventory_theft` | 96,00 | 70,83 | 25,17 | 6 | 31 |
| `terminated_still_paid` | 100,00 | 76,19 | 23,81 | 6 | 17 |
| `expense_padding` | 62,79 | 40,00 | 22,79 | 5 | 27 |
| `false_refund` | 85,56 | 63,70 | 21,85 | 7 | 48 |
| `ghost_employee` | 77,78 | 61,11 | 16,67 | 3 | 8 |
| `vendor_burst` | 26,67 | 11,11 | 15,56 | 3 | 15 |
| `expense_fictitious` | 96,33 | 84,72 | 11,61 | 4 | 22 |
| `shell_vendor` | 88,20 | 78,70 | 9,50 | 8 | 32 |
| `overbilling_excess_payment` | 100,00 | 91,67 | 8,33 | 4 | 15 |
| `price_creep` | 39,39 | 33,33 | 6,06 | 4 | 19 |
| `payroll_padding` | 4,17 | 0,00 | 4,17 | 3 | 7 |
| `kickback_overpricing` | 47,78 | 55,00 | -7,22 | 3 | 14 |
| `fictitious_revenue_cutoff` | 58,33 | 66,67 | -8,33 | 4 | 8 |
| `off_cycle_payroll` | 52,38 | 61,11 | -8,73 | 3 | 7 |
| `expense_duplicate_claim` | 46,67 | 83,33 | -36,67 | 3 | 9 |

### L3, P1 so với S2 gốc

| Kịch bản | P1 phát triển | Đích | Giảm (điểm) | Vụ ở đích | Dòng ở đích |
|---|---:|---:|---:|---:|---:|
| `receivable_lapping` | 89,58 | 52,84 | 36,74 | 10 | 47 |
| `cash_larceny` | 100,00 | 78,39 | 21,61 | 7 | 41 |
| `expense_fictitious` | 96,33 | 81,94 | 14,38 | 4 | 22 |
| `vendor_burst` | 26,67 | 17,78 | 8,89 | 3 | 15 |
| `split_payments` | 55,00 | 50,00 | 5,00 | 4 | 11 |
| `terminated_still_paid` | 100,00 | 95,24 | 4,76 | 6 | 17 |
| `payroll_padding` | 4,17 | 0,00 | 4,17 | 3 | 7 |
| `overbilling_excess_payment` | 100,00 | 100,00 | 0,00 | 4 | 15 |
| `unrecorded_sales_skimming` | 100,00 | 100,00 | 0,00 | 3 | 15 |
| `shell_vendor` | 88,20 | 88,89 | -0,69 | 8 | 32 |
| `altered_payee` | 96,67 | 100,00 | -3,33 | 4 | 12 |
| `inventory_theft` | 96,00 | 100,00 | -4,00 | 6 | 31 |
| `undisclosed_related_vendor` | 95,65 | 100,00 | -4,35 | 3 | 24 |
| `duplicate_payment` | 83,33 | 88,89 | -5,56 | 3 | 9 |
| `owner_override_transfer` | 93,33 | 100,00 | -6,67 | 5 | 10 |
| `period_end_adjustment` | 91,67 | 100,00 | -8,33 | 4 | 7 |
| `invoice_mill` | 90,48 | 100,00 | -9,52 | 4 | 15 |
| `false_refund` | 85,56 | 96,67 | -11,11 | 7 | 48 |
| `ghost_employee` | 77,78 | 88,89 | -11,11 | 3 | 8 |
| `bid_rotation` | 83,09 | 95,69 | -12,60 | 5 | 36 |
| `advance_unsettled` | 83,33 | 100,00 | -16,67 | 3 | 3 |
| `personal_purchase` | 50,91 | 67,97 | -17,06 | 5 | 23 |
| `expense_padding` | 62,79 | 86,67 | -23,87 | 5 | 27 |
| `fictitious_revenue_cutoff` | 58,33 | 83,33 | -25,00 | 4 | 8 |
| `fake_bonus_list` | 57,62 | 83,33 | -25,71 | 3 | 9 |
| `kickback_overpricing` | 47,78 | 75,00 | -27,22 | 3 | 14 |
| `bank_detail_switch` | 72,22 | 100,00 | -27,78 | 3 | 7 |
| `price_creep` | 39,39 | 83,33 | -43,94 | 4 | 19 |
| `expense_duplicate_claim` | 46,67 | 91,67 | -45,00 | 3 | 9 |
| `off_cycle_payroll` | 52,38 | 100,00 | -47,62 | 3 | 7 |

### L4-FB, P1 so với S1 gốc

| Kịch bản | P1 phát triển | Đích | Giảm (điểm) | Vụ ở đích | Dòng ở đích |
|---|---:|---:|---:|---:|---:|
| `advance_unsettled` | 83,33 | 0,00 | 83,33 | 3 | 3 |
| `receivable_lapping` | 83,33 | 22,77 | 60,56 | 10 | 47 |
| `payroll_padding` | 50,00 | 0,00 | 50,00 | 3 | 7 |
| `undisclosed_related_vendor` | 97,10 | 50,00 | 47,10 | 3 | 24 |
| `bid_rotation` | 91,14 | 49,31 | 41,84 | 5 | 36 |
| `period_end_adjustment` | 91,67 | 50,00 | 41,67 | 4 | 7 |
| `expense_padding` | 80,47 | 39,72 | 40,76 | 5 | 27 |
| `off_cycle_payroll` | 73,81 | 33,33 | 40,48 | 3 | 7 |
| `ghost_employee` | 77,78 | 38,89 | 38,89 | 3 | 8 |
| `inventory_theft` | 98,67 | 61,11 | 37,56 | 6 | 31 |
| `cash_larceny` | 100,00 | 65,75 | 34,25 | 7 | 41 |
| `unrecorded_sales_skimming` | 97,62 | 63,89 | 33,73 | 3 | 15 |
| `overbilling_excess_payment` | 100,00 | 66,67 | 33,33 | 4 | 15 |
| `expense_fictitious` | 81,75 | 48,61 | 33,13 | 4 | 22 |
| `personal_purchase` | 57,07 | 26,14 | 30,93 | 5 | 23 |
| `duplicate_payment` | 83,33 | 55,56 | 27,78 | 3 | 9 |
| `bank_detail_switch` | 55,56 | 33,33 | 22,22 | 3 | 7 |
| `altered_payee` | 96,67 | 75,00 | 21,67 | 4 | 12 |
| `false_refund` | 85,56 | 65,37 | 20,19 | 7 | 48 |
| `split_payments` | 36,11 | 16,67 | 19,44 | 4 | 11 |
| `terminated_still_paid` | 100,00 | 80,95 | 19,05 | 6 | 17 |
| `fake_bonus_list` | 73,57 | 55,56 | 18,02 | 3 | 9 |
| `fictitious_revenue_cutoff` | 66,67 | 50,00 | 16,67 | 4 | 8 |
| `owner_override_transfer` | 100,00 | 86,67 | 13,33 | 5 | 10 |
| `shell_vendor` | 88,20 | 75,00 | 13,20 | 8 | 32 |
| `invoice_mill` | 92,46 | 90,48 | 1,98 | 4 | 15 |
| `vendor_burst` | 23,33 | 23,33 | 0,00 | 3 | 15 |
| `price_creep` | 51,52 | 55,00 | -3,48 | 4 | 19 |
| `kickback_overpricing` | 43,33 | 53,33 | -10,00 | 3 | 14 |
| `expense_duplicate_claim` | 63,33 | 75,00 | -11,67 | 3 | 9 |

### L4-FB, P1 so với S2 gốc

| Kịch bản | P1 phát triển | Đích | Giảm (điểm) | Vụ ở đích | Dòng ở đích |
|---|---:|---:|---:|---:|---:|
| `payroll_padding` | 50,00 | 0,00 | 50,00 | 3 | 7 |
| `receivable_lapping` | 83,33 | 43,92 | 39,42 | 10 | 47 |
| `expense_fictitious` | 81,75 | 55,56 | 26,19 | 4 | 22 |
| `cash_larceny` | 100,00 | 85,53 | 14,47 | 7 | 41 |
| `overbilling_excess_payment` | 100,00 | 91,67 | 8,33 | 4 | 15 |
| `vendor_burst` | 23,33 | 17,78 | 5,56 | 3 | 15 |
| `terminated_still_paid` | 100,00 | 95,24 | 4,76 | 6 | 17 |
| `undisclosed_related_vendor` | 97,10 | 96,30 | 0,81 | 3 | 24 |
| `ghost_employee` | 77,78 | 77,78 | 0,00 | 3 | 8 |
| `owner_override_transfer` | 100,00 | 100,00 | 0,00 | 5 | 10 |
| `shell_vendor` | 88,20 | 88,89 | -0,69 | 8 | 32 |
| `inventory_theft` | 98,67 | 100,00 | -1,33 | 6 | 31 |
| `unrecorded_sales_skimming` | 97,62 | 100,00 | -2,38 | 3 | 15 |
| `altered_payee` | 96,67 | 100,00 | -3,33 | 4 | 12 |
| `false_refund` | 85,56 | 91,67 | -6,11 | 7 | 48 |
| `expense_padding` | 80,47 | 86,67 | -6,20 | 5 | 27 |
| `invoice_mill` | 92,46 | 100,00 | -7,54 | 4 | 15 |
| `period_end_adjustment` | 91,67 | 100,00 | -8,33 | 4 | 7 |
| `bid_rotation` | 91,14 | 100,00 | -8,86 | 5 | 36 |
| `off_cycle_payroll` | 73,81 | 83,33 | -9,52 | 3 | 7 |
| `fake_bonus_list` | 73,57 | 83,33 | -9,76 | 3 | 9 |
| `split_payments` | 36,11 | 50,00 | -13,89 | 4 | 11 |
| `advance_unsettled` | 83,33 | 100,00 | -16,67 | 3 | 3 |
| `duplicate_payment` | 83,33 | 100,00 | -16,67 | 3 | 9 |
| `fictitious_revenue_cutoff` | 66,67 | 83,33 | -16,67 | 4 | 8 |
| `personal_purchase` | 57,07 | 75,82 | -18,75 | 5 | 23 |
| `bank_detail_switch` | 55,56 | 83,33 | -27,78 | 3 | 7 |
| `price_creep` | 51,52 | 87,50 | -35,98 | 4 | 19 |
| `expense_duplicate_claim` | 63,33 | 100,00 | -36,67 | 3 | 9 |
| `kickback_overpricing` | 43,33 | 91,67 | -48,33 | 3 | 14 |

### Novelty max(R,E), P1 so với S1 gốc

| Kịch bản | P1 phát triển | Đích | Giảm (điểm) | Vụ ở đích | Dòng ở đích |
|---|---:|---:|---:|---:|---:|
| `payroll_padding` | 79,17 | 16,67 | 62,50 | 3 | 7 |
| `invoice_mill` | 46,43 | 4,76 | 41,67 | 4 | 15 |
| `duplicate_payment` | 83,33 | 44,44 | 38,89 | 3 | 9 |
| `receivable_lapping` | 59,58 | 26,15 | 33,43 | 10 | 47 |
| `price_creep` | 59,19 | 34,44 | 24,75 | 4 | 19 |
| `undisclosed_related_vendor` | 67,08 | 47,04 | 20,04 | 3 | 24 |
| `bank_detail_switch` | 44,44 | 27,78 | 16,67 | 3 | 7 |
| `ghost_employee` | 16,67 | 0,00 | 16,67 | 3 | 8 |
| `period_end_adjustment` | 100,00 | 83,33 | 16,67 | 4 | 7 |
| `personal_purchase` | 9,70 | 0,00 | 9,70 | 5 | 23 |
| `expense_fictitious` | 35,52 | 33,33 | 2,18 | 4 | 22 |
| `cash_larceny` | 11,11 | 9,71 | 1,40 | 7 | 41 |
| `advance_unsettled` | 100,00 | 100,00 | 0,00 | 3 | 3 |
| `altered_payee` | 100,00 | 100,00 | 0,00 | 4 | 12 |
| `overbilling_excess_payment` | 100,00 | 100,00 | 0,00 | 4 | 15 |
| `bid_rotation` | 14,37 | 15,00 | -0,63 | 5 | 36 |
| `owner_override_transfer` | 71,11 | 75,56 | -4,44 | 5 | 10 |
| `fake_bonus_list` | 31,19 | 36,11 | -4,92 | 3 | 9 |
| `expense_padding` | 21,11 | 26,21 | -5,10 | 5 | 27 |
| `false_refund` | 50,00 | 55,56 | -5,56 | 7 | 48 |
| `shell_vendor` | 55,58 | 63,89 | -8,31 | 8 | 32 |
| `fictitious_revenue_cutoff` | 16,67 | 25,00 | -8,33 | 4 | 8 |
| `kickback_overpricing` | 55,56 | 65,00 | -9,44 | 3 | 14 |
| `unrecorded_sales_skimming` | 16,45 | 28,33 | -11,88 | 3 | 15 |
| `inventory_theft` | 4,00 | 21,73 | -17,73 | 6 | 31 |
| `vendor_burst` | 10,00 | 31,11 | -21,11 | 3 | 15 |
| `expense_duplicate_claim` | 0,00 | 22,22 | -22,22 | 3 | 9 |
| `split_payments` | 33,89 | 58,33 | -24,44 | 4 | 11 |
| `terminated_still_paid` | 63,89 | 90,48 | -26,59 | 6 | 17 |
| `off_cycle_payroll` | 14,29 | 50,00 | -35,71 | 3 | 7 |

### Novelty max(R,E), P1 so với S2 gốc

| Kịch bản | P1 phát triển | Đích | Giảm (điểm) | Vụ ở đích | Dòng ở đích |
|---|---:|---:|---:|---:|---:|
| `payroll_padding` | 79,17 | 16,67 | 62,50 | 3 | 7 |
| `invoice_mill` | 46,43 | 4,76 | 41,67 | 4 | 15 |
| `duplicate_payment` | 83,33 | 44,44 | 38,89 | 3 | 9 |
| `receivable_lapping` | 59,58 | 26,15 | 33,43 | 10 | 47 |
| `price_creep` | 59,19 | 34,44 | 24,75 | 4 | 19 |
| `undisclosed_related_vendor` | 67,08 | 47,04 | 20,04 | 3 | 24 |
| `bank_detail_switch` | 44,44 | 27,78 | 16,67 | 3 | 7 |
| `ghost_employee` | 16,67 | 0,00 | 16,67 | 3 | 8 |
| `period_end_adjustment` | 100,00 | 83,33 | 16,67 | 4 | 7 |
| `personal_purchase` | 9,70 | 0,00 | 9,70 | 5 | 23 |
| `expense_fictitious` | 35,52 | 33,33 | 2,18 | 4 | 22 |
| `cash_larceny` | 11,11 | 9,71 | 1,40 | 7 | 41 |
| `advance_unsettled` | 100,00 | 100,00 | 0,00 | 3 | 3 |
| `altered_payee` | 100,00 | 100,00 | 0,00 | 4 | 12 |
| `overbilling_excess_payment` | 100,00 | 100,00 | 0,00 | 4 | 15 |
| `bid_rotation` | 14,37 | 15,00 | -0,63 | 5 | 36 |
| `owner_override_transfer` | 71,11 | 75,56 | -4,44 | 5 | 10 |
| `fake_bonus_list` | 31,19 | 36,11 | -4,92 | 3 | 9 |
| `expense_padding` | 21,11 | 26,21 | -5,10 | 5 | 27 |
| `false_refund` | 50,00 | 55,56 | -5,56 | 7 | 48 |
| `shell_vendor` | 55,58 | 63,89 | -8,31 | 8 | 32 |
| `fictitious_revenue_cutoff` | 16,67 | 25,00 | -8,33 | 4 | 8 |
| `kickback_overpricing` | 55,56 | 65,00 | -9,44 | 3 | 14 |
| `unrecorded_sales_skimming` | 16,45 | 28,33 | -11,88 | 3 | 15 |
| `inventory_theft` | 4,00 | 21,73 | -17,73 | 6 | 31 |
| `vendor_burst` | 10,00 | 31,11 | -21,11 | 3 | 15 |
| `expense_duplicate_claim` | 0,00 | 22,22 | -22,22 | 3 | 9 |
| `split_payments` | 33,89 | 58,33 | -24,44 | 4 | 11 |
| `terminated_still_paid` | 63,89 | 90,48 | -26,59 | 6 | 17 |
| `off_cycle_payroll` | 14,29 | 50,00 | -35,71 | 3 | 7 |

## 4. Vì sao seed 933 thấp nhất

Bảng cấu trúc dưới đây giữ số vụ và cơ cấu che giấu; không coi ít dòng hoặc nhiều vụ L2 là nguyên nhân đủ để giải thích kết quả. Số dòng dương đã biết trong lịch sử là lượng nhãn dương S1 thật sự còn dùng được, trong khi S2 có nguồn học từ ba thế giới phát triển.

| Thế giới | Dương đã biết train | Dương mới train | Dương đã biết validation | Vụ test | Dòng test | Dòng mới test | Vụ L0 test | Vụ L1 test | Vụ L2 test | Tỷ lệ L2 test (%) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| s4_s931 | 127 | 155 | 79 | 66 | 320 | 120 | 14 | 35 | 17 | 25,76 |
| s4_s932 | 161 | 184 | 74 | 62 | 271 | 88 | 7 | 26 | 29 | 46,77 |
| s4_s933 | 114 | 187 | 101 | 57 | 277 | 112 | 10 | 29 | 18 | 31,58 |

933 chỉ có 114 dòng dương đã biết ở train, thấp nhất trong ba thế giới, trong khi có 187 dòng mới bị đặt nhãn 0, cao nhất trong ba thế giới. Tập test có 57 vụ và 40,43% dòng gian lận thuộc kịch bản mới. Tuy vậy, 933 có 18 vụ L2 ở test, ít hơn 29 vụ của 932; không có bằng chứng rằng chỉ nhiều vụ che giấu khó hơn đã đủ giải thích thứ hạng. Số dòng, số vụ, tỷ trọng họ và chất lượng nguồn nhãn đều cùng thay đổi, nên phải đọc cùng các can thiệp và phân rã dưới đây.

Đối chiếu 933 với trung bình đều 931 và 932 của cả ba phương pháp. Phân rã theo họ giữ đúng tổng: phần cơ cấu dùng tỷ trọng dòng theo họ; phần trong họ là khác biệt tỷ lệ phát hiện khi giữ tỷ trọng 933. Hai phần chỉ là mô tả, không chứng minh nguyên nhân. Các bảng đóng góp từng họ bên dưới tập trung cấu hình đã chọn L4-FB; JSON giữ đủ ba phương pháp.

| Phương pháp | Giao thức | Recall 931 và 932 | Recall 933 | Chênh tổng (điểm) | Phần cơ cấu | Phần trong họ |
|---|---|---:|---:|---:|---:|---:|
| L3 | S1 gốc | 50,54 | 32,49 | 18,05 | 9,46 | 8,59 |
| L4-FB | S1 gốc | 47,71 | 28,52 | 19,19 | 7,05 | 12,13 |
| Novelty max(R,E) | S1 gốc | 30,75 | 22,74 | 8,01 | -0,41 | 8,42 |
| L3 | S2 gốc | 64,52 | 54,51 | 10,00 | 7,13 | 2,88 |
| L4-FB | S2 gốc | 67,47 | 56,68 | 10,79 | 5,10 | 5,69 |
| Novelty max(R,E) | S2 gốc | 30,75 | 22,74 | 8,01 | -0,41 | 8,42 |

Các họ đóng góp chênh lệch lớn nhất ở S1 gốc:

| Họ | Phần cơ cấu (điểm) | Phần trong họ (điểm) | Tổng (điểm) |
|---|---:|---:|---:|
| `shell_vendor` | 3,75 | 0,27 | 4,01 |
| `inventory_theft` | 0,83 | 2,75 | 3,58 |
| `bid_rotation` | 2,18 | 0,78 | 2,96 |
| `phantom_sales_real_dealers` | 1,57 | 1,11 | 2,69 |
| `overbilling_excess_payment` | 1,02 | 1,08 | 2,10 |
| `expense_padding` | 1,13 | 0,66 | 1,80 |
| `undisclosed_related_vendor` | -0,52 | 2,23 | 1,70 |
| `invoice_mill` | 1,26 | -0,12 | 1,14 |
| `unrecorded_sales_skimming` | -0,56 | 1,59 | 1,03 |
| `underpriced_sales_kickback` | 0,31 | 0,66 | 0,97 |
| `altered_payee` | 0,72 | 0,22 | 0,95 |
| `fake_tax_payment` | 0,77 | 0,08 | 0,85 |

Các họ đóng góp chênh lệch lớn nhất ở S2 gốc:

| Họ | Phần cơ cấu (điểm) | Phần trong họ (điểm) | Tổng (điểm) |
|---|---:|---:|---:|
| `shell_vendor` | 3,59 | -0,12 | 3,47 |
| `bid_rotation` | 3,46 | 0,00 | 3,46 |
| `phantom_sales_real_dealers` | 1,76 | 1,69 | 3,44 |
| `expense_padding` | 2,00 | 0,72 | 2,72 |
| `receivable_lapping` | 1,38 | 0,93 | 2,31 |
| `fake_tax_payment` | 1,27 | 0,60 | 1,88 |
| `invoice_mill` | 1,51 | 0,00 | 1,51 |
| `altered_payee` | 0,90 | 0,00 | 0,90 |
| `inventory_theft` | 0,88 | 0,00 | 0,88 |
| `overbilling_excess_payment` | 0,94 | -0,08 | 0,86 |
| `overtime_inflation_group` | -3,48 | 4,09 | 0,61 |
| `vendor_burst` | 0,12 | 0,40 | 0,53 |

Cơ cấu toàn bộ kịch bản, số dòng và số vụ theo train, validation, test của từng thế giới có đầy đủ trong `summary.json`. Bảng hiệu can thiệp ở mục 1 cho biết mức hồi phục của 933 khi xử lý nhãn; phần còn lại không thể tự quy hết cho nhãn, lịch lương hoặc che giấu. Chỉ ba thế giới và vài vụ mỗi họ không đủ nhận diện một nguyên nhân duy nhất.

## 5. Phân rã mức tụt 39,5 điểm và bootstrap theo vụ

Chuỗi đối chiếu A đến F: A là recall P1 phát triển từ cờ gốc; B dùng tỷ lệ P1 theo họ nhưng tái trọng số theo cơ cấu họ đã biết ở đích; C là recall S2 trên kịch bản đã biết; D là recall S2 chung; E là recall S1 chỉ loại dòng mới khỏi huấn luyện; F là recall S1 gốc. Lấy hiệu liên tiếp A trừ B đến E trừ F nên tổng cộng đúng A trừ F. Dấu âm nghĩa là phần đó bù lại mức giảm theo thứ tự này.

Đây là **đồng nhất thức mô tả phụ thuộc thứ tự**, không phải phân bổ nhân quả duy nhất. Phần D trừ E còn gộp nguồn, số lượng và cơ cấu huấn luyện, cùng khác biệt lịch sử kiểm định. Phần E trừ F là can thiệp loại dòng biết trước, bao gồm thay đổi số dòng và cân bằng lớp. Không đặt tên các phần này là tác động thuần của dịch chuyển hoặc nhiễu nhãn.

### L3

| Thành phần | Điểm phần trăm [95%] |
|---|---:|
| A trừ B: cơ cấu họ đã biết | -1,94 [-5,85; 3,00] |
| B trừ C: chuyển giao có điều kiện trong họ đã biết | -4,08 [-9,91; 1,21] |
| C trừ D: đưa kịch bản mới vào hỗn hợp S2 | 22,30 [15,30; 28,89] |
| D trừ E: nguồn huấn luyện và lịch sử còn gộp | 21,96 [15,75; 28,61] |
| E trừ F: can thiệp loại dòng mới khỏi huấn luyện | -5,31 [-9,68; -0,93] |
| Tổng A trừ F | **32,93 [25,59; 39,52]** |

Mức recall tại từng điểm A đến F: A_dev = 77,46%; B_reweighted_dev = 79,40%; C_S2_known = 83,48%; D_S2_all = 61,18%; E_drop_train = 39,22%; F_S1 = 44,53%.

Sai số cộng số học: 0.000000000000 theo thang recall.

### L4-FB

| Thành phần | Điểm phần trăm [95%] |
|---|---:|
| A trừ B: cơ cấu họ đã biết | -0,63 [-4,19; 3,81] |
| B trừ C: chuyển giao có điều kiện trong họ đã biết | -1,81 [-7,35; 3,32] |
| C trừ D: đưa kịch bản mới vào hỗn hợp S2 | 19,38 [12,41; 26,13] |
| D trừ E: nguồn huấn luyện và lịch sử còn gộp | 16,98 [11,42; 22,80] |
| E trừ F: can thiệp loại dòng mới khỏi huấn luyện | 5,59 [1,37; 9,82] |
| Tổng A trừ F | **39,50 [32,55; 45,34]** |

Mức recall tại từng điểm A đến F: A_dev = 80,81%; B_reweighted_dev = 81,44%; C_S2_known = 83,25%; D_S2_all = 63,87%; E_drop_train = 46,90%; F_S1 = 41,31%.

Sai số cộng số học: 0.000000000000 theo thang recall.

### Novelty max(R,E)

| Thành phần | Điểm phần trăm [95%] |
|---|---:|
| A trừ B: cơ cấu họ đã biết | -1,26 [-6,95; 4,09] |
| B trừ C: chuyển giao có điều kiện trong họ đã biết | 3,34 [-3,34; 9,26] |
| C trừ D: đưa kịch bản mới vào hỗn hợp S2 | 9,36 [5,98; 13,48] |
| D trừ E: nguồn huấn luyện và lịch sử còn gộp | 0,00 [0,00; 0,00] |
| E trừ F: can thiệp loại dòng mới khỏi huấn luyện | 0,00 [0,00; 0,00] |
| Tổng A trừ F | **11,44 [5,18; 16,83]** |

Mức recall tại từng điểm A đến F: A_dev = 39,52%; B_reweighted_dev = 40,78%; C_S2_known = 37,44%; D_S2_all = 28,08%; E_drop_train = 28,08%; F_S1 = 28,08%.

Sai số cộng số học: 0.000000000000 theo thang recall.

Bootstrap 2.000 lần, seed 20261019, lấy nguyên vụ. Phát triển tái lấy mẫu trong từng thế giới và họ để các tỷ lệ theo họ luôn xác định; đích tái lấy mẫu trong từng thế giới, cùng mẫu vụ cho các giao thức. Không khớp lại mô hình hoặc chọn lại ngân sách trong bootstrap. Các khoảng có điều kiện trên ba thế giới, số vụ theo họ phát triển và mô hình cố định; không bao gồm phương sai huấn luyện, lựa chọn phương pháp hoặc sinh thế giới mới. Khoảng mô tả không được hiểu là mức đảm bảo trên doanh nghiệp thật.

P1 trong tệp khóa v4 đã làm tròn bốn chữ số thập phân; phép phân rã dùng cờ P1 gốc để cộng chính xác, nên có thể khác vài phần rất nhỏ của một điểm so với phép trừ trên số đã làm tròn. Các giới hạn từng thành phần không cộng được bằng cách cộng hai đầu khoảng; khoảng của tổng được tính trực tiếp trên cùng mẫu bootstrap.

## Kết luận và giới hạn vòng mới

V4 **không đạt G5**, giữ nguyên kết luận M2. Các kiểm nhãn trong R0 không phải giải pháp vận hành đã được kiểm chứng; không chọn ứng viên theo bảng hậu kiểm hoặc dùng ba seed v4 để xác nhận v5. Cần đăng ký giao thức v5 trước R2, chọn theo thế giới phát triển tệ nhất và đánh giá một lần trên kịch bản v5 chưa từng được nhóm phương pháp đọc khi phát triển.

Bản đăng ký trước tại `docs/05_ke_hoach_giao_viec/08_dang_ky_truoc_v5.md` là đề xuất để chủ dự án duyệt. **Dừng sau R0 và R1; không bắt đầu R2 khi chưa nhận “duyệt”.** Chưa tải dữ liệu ngoài, chưa sinh hoặc chạy niêm phong v5, chưa có dữ liệu doanh nghiệp thật.

## Tái lập hậu kiểm

Yêu cầu dữ liệu, bộ đệm và cờ P1 lịch sử còn tồn tại, đúng băm. Dùng một thư mục ra mới để giữ nguyên báo cáo đã bàn giao. Lệnh dưới chỉ chạy lại hậu kiểm v4 đã lộ, không phải một lượt niêm phong mới và không phải R2.

```powershell
$env:PYTHONPATH = (Get-Location).Path
$env:PYTHONIOENCODING = 'utf-8'
.venv/Scripts/python.exe -m agent2.postmortem_v4 --out work/reproduce_postmortem_v4
```

Khoảng bootstrap can thiệp riêng và khoảng trong chuỗi phân rã dùng cách tổ chức mẫu khác nhau với cùng 2.000 lần lặp; biên có thể khác nhẹ do Monte Carlo. Trong mỗi chuỗi phân rã, mọi thành phần và tổng dùng chung mẫu.
