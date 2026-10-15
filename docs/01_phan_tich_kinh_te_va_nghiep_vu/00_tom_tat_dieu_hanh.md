# Tóm tắt điều hành

## Vấn đề
Doanh nghiệp nhỏ và vừa (DNNVV) Việt Nam thường để một vài người giữ cả tiền, chứng từ và sổ sách. Khi một người trong số đó gian lận, không có kiểm toán nội bộ hay đường dây tố giác để phát hiện sớm. Gian lận trung bình kéo dài 12 tháng trước khi bị phát hiện (ACFE 2024 [Đ]); ở nhóm dưới 100 nhân sự, tổn thất trung vị là 141.000 đô la, tương đương khoảng 3,7 tỷ đồng ở tỷ giá giả định 26.000 đồng một đô la [Đ, G].

## Khoảng trống kiểm soát
Ở tổ chức dưới 100 nhân sự so với từ 100 nhân sự trở lên [Đ, ACFE 2024]:

| Biện pháp kiểm soát | Dưới 100 nhân sự | Từ 100 nhân sự |
|---|---:|---:|
| Kiểm toán nội bộ | 40% | 90% |
| Đường dây tố giác | 27% | 82% |
| Giám sát dữ liệu chủ động | 19% | 53% |
| Kiểm toán đột xuất | 17% | 49% |
| Luân chuyển công việc hoặc nghỉ phép bắt buộc | 10% | 27% |

Giám sát dữ liệu chủ động ở nhóm nhỏ chỉ bằng khoảng một phần ba nhóm lớn: đây là chỗ sản phẩm lấp vào.

## Giải pháp
Agent 2 đọc sổ giao dịch của doanh nghiệp (thanh toán nhà cung cấp, lương, chi tiền mặt, tạm ứng, bán hàng, thu tiền, hoàn tiền, hủy hàng) và mỗi tuần đưa ra **không quá 3 cảnh báo cho mỗi công ty**, mỗi cảnh báo kèm lý do bằng tiếng Việt và việc cần làm. Con người quyết định.

## Giá trị kỳ vọng (xem tính toán ở thư mục 03)
- Sản phẩm hòa vốn nếu tổn thất gian lận kỳ vọng của một công ty quy mô nhỏ (60 tỷ đồng doanh thu) đạt khoảng **0,14% doanh thu mỗi năm** [G, tính toán]. ACFE cho rằng tổ chức mất khoảng 5% doanh thu mỗi năm, nhưng đó là ước tính của chuyên gia được khảo sát, không phải tần suất đo được.
- Thời gian rà soát của người dùng: khoảng 26 giờ mỗi năm mỗi công ty (3 cảnh báo mỗi tuần, 10 phút một cảnh báo) [G].

## Điều đã chứng minh được và chưa
| Đã chứng minh | Chưa chứng minh |
|---|---|
| Bài toán có thật và có số liệu quốc tế (ACFE) cùng vụ án Việt Nam | Tần suất gian lận thật ở DNNVV Việt Nam |
| Hệ thống chạy đầu-cuối trên dữ liệu tổng hợp; mô hình có giám sát bắt khoảng 77% dòng gian lận ở ngân sách 3 cảnh báo mỗi tuần [M] | Hiệu năng trên dữ liệu thật; tỷ lệ báo nhầm thật |
| Luật tay một mình chỉ bắt khoảng 27% trên dữ liệu khó [M] | Khả năng chi trả của DNNVV |

## Đề xuất quyết định
Đi tiếp theo hai bước: (1) hoàn tất so sánh phương pháp và chạy tập niêm phong v4 (kế hoạch ở thư mục 05); (2) tìm 3 đến 5 doanh nghiệp chạy chế độ chỉ xem để đo tỷ lệ báo nhầm thật và khả năng chi trả. Không bán sản phẩm khi chưa có bước (2).
