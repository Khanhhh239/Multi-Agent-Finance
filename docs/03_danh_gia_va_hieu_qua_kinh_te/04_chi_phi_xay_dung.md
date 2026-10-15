# Chi phí xây dựng

Mọi đơn giá là **giả định [G]** (chi phí toàn phần mỗi người mỗi tháng, đã gồm bảo hiểm và thiết bị); thay bằng số thật của đơn vị. Đơn vị: triệu đồng.

## 1. Chi phí xây dựng một lần (đến mức sẵn sàng thí điểm 3 đến 5 doanh nghiệp)

| Hạng mục | Người-tháng | Đơn giá | Chi phí | Phần đã làm trong dự án hiện tại |
|---|---:|---:|---:|---|
| Data scientist, ML: bộ sinh dữ liệu, đặc trưng, mô hình, đánh giá | 6 | 45 | 270 | Phần lớn đã có (khoảng 4 trên 6 người-tháng tương đương): bộ sinh v3, v4, niêm phong; 46 đặc trưng; mô hình; benchmark |
| Kỹ sư dữ liệu và backend: bộ nhận dữ liệu từ phần mềm kế toán và hóa đơn điện tử, API, lập lịch, triển khai | 4 | 40 | 160 | Chưa (có `pipeline.py` chạy tệp CSV) |
| Giao diện và trải nghiệm: hàng đợi vụ, phản hồi, xuất hồ sơ | 2 | 35 | 70 | Một phần (`review_ui`, `review_page.py`) |
| QA và BA: kiểm thử, tài liệu, phỏng vấn | 3 | 30 | 90 | Tài liệu và kiểm thử đơn vị đã có; UAT chưa |
| Tư vấn pháp lý Nghị định 13/2023/NĐ-CP, hợp đồng dữ liệu | | | 30 | Chưa |
| Vận hành thí điểm (đào tạo, đi lại, hỗ trợ 3 đến 5 doanh nghiệp) | | | 40 | Chưa |
| Hạ tầng, công cụ, giấy phép dữ liệu | | | 40 | Một phần |
| **Tổng** | **15** | | **700** | |

Phần còn lại cần chi khoảng **430 đến 480 triệu đồng** (tổng trừ phần data science đã làm, khoảng 4 người-tháng quy ra 180 triệu và một phần giao diện 20 đến 40 triệu); ước lượng thô.

## 2. Chi phí vận hành cố định hằng năm (bên cung cấp)

| Hạng mục | Cách tính | Chi phí |
|---|---|---:|
| Bảo trì mô hình và dữ liệu (0,2 người) | 0,2 × 12 × 45 | 108 |
| Bảo trì kỹ thuật (0,2 người) | 0,2 × 12 × 40 | 96 |
| Pháp lý, tuân thủ | | 20 |
| Hạ tầng nền | | 26 |
| **Tổng** | | **250** |

## 3. Chi phí biến đổi mỗi khách hàng mỗi năm

| Hạng mục | Chi phí |
|---|---:|
| Máy chủ, lưu trữ | 2 |
| Hỗ trợ, vận hành dữ liệu | 4 |
| Bán hàng, thanh toán (20% giá gói 24 triệu) | 4,8 |
| Nối dữ liệu ban đầu (một lần, khấu hao 3 năm) | 1,7 |

## 4. Chi phí cơ hội và rủi ro chi phí
- **Làm lại vì sai giả định dữ liệu:** nếu dữ liệu thật khác dữ liệu sinh nhiều (rủi ro A10), phải huấn luyện lại và có thể đổi bộ đặc trưng: cộng thêm khoảng 1 đến 2 người-tháng.
- **Nối nhiều phần mềm kế toán:** mỗi bộ nối khoảng 0,5 đến 1 người-tháng kỹ sư (45 đến 90 triệu).
- **Dữ liệu dòng hàng hóa đơn XML** (cần cho phát hiện theo đơn giá mặt hàng): thêm khoảng 1 đến 1,5 người-tháng.

## 5. Chi phí so với mốc thị trường
Chi phí xây dựng 700 triệu đồng bằng khoảng 47 tháng lương của một kế toán tổng hợp (15 triệu đồng/tháng); bằng khoảng 100 gói phần mềm kế toán Enterprise một năm (6,95 triệu đồng). Hòa vốn cần khoảng 37 khách ở giá 24 triệu đồng (tệp BA 07).
