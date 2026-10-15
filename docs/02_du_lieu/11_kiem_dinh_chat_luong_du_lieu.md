# Kiểm định chất lượng dữ liệu

Mã: `agent2/validate_v4.py` (hàm `validate_v4`). Chạy tự động sau khi sinh; kết quả ghi vào `validation_v4.json` trong thư mục thế giới. Kiểm thử tự động: `tests_agent2/test_v4_methods.py::test_sealed_world_small_is_valid`.

## 1. Các phép kiểm (V1 đến V9, V11, V12 là `assert` làm sinh dữ liệu thất bại nếu sai; V10 được báo cáo trong `scheme_split_gaps`)

| # | Phép kiểm | Bắt lỗi gì |
|---|---|---|
| V1 | Đủ khóa nối giữa `transactions`, `labels`, `splits`, `features` | Thiếu hoặc thừa dòng |
| V2 | Nhãn không lọt vào `transactions` hay `features` (không có cột `is_fraud`, `fraud_type`, `case_id`, `scheme_group`, `concealment`, ...) | Rò rỉ nhãn |
| V3 | `created_at ≤ approved_at ≤ posted_at` và dòng nằm trong cửa sổ giai đoạn | Sai trình tự thời gian |
| V4 | Khóa ngoại tới nhà cung cấp, khách, nhân viên cùng công ty | Dòng mồ côi |
| V5 | `recorded_at` của danh mục chủ không sau `posted_at` của giao dịch dùng nó | Dữ liệu chủ từ tương lai |
| V6 | Mỗi vụ nằm trọn trong một giai đoạn | Rò rỉ giữa giai đoạn |
| V7 | Mỗi phiếu thu trỏ tới hóa đơn bán trước đó | Quy trình bán sai |
| V8 | Lương sau nghỉ việc chỉ xuất hiện khi có nhãn (quyết toán hợp lệ hoặc gian lận) | Lương sau nghỉ không có nhãn |
| V9 | Sổ kế toán cân Nợ bằng Có, quy tắc của bạn bạn mở rộng cho 5 loại bút toán mới | Sai kế toán |
| V10 | Mỗi kịch bản có vụ ở cả ba giai đoạn (bản phát triển) | Thiếu phủ |
| V11 | Số dòng gian lận trong `truth_cases` khớp `labels` | Sai lệch bảng vụ |
| V12 | **Kiểm tra lối tắt** (mục 2) | Bộ sinh để lại dấu vết vô nghĩa |

## 2. Kiểm tra lối tắt
Huấn luyện LightGBM trên: (a) chỉ loại nghiệp vụ, (b) loại nghiệp vụ cộng các trường **không có ý nghĩa gian lận trong sổ thật**: phút, giây, số thứ tự trong mã giao dịch, chữ số số hóa đơn, số tiền mod 1.000. Đo AUC ở tập kiểm thử. Điều kiện qua: AUC (b) − AUC (a) < 0,05.

| Thế giới | AUC chỉ loại nghiệp vụ | AUC cộng trường vô nghĩa | Mức tăng |
|---|---:|---:|---:|
| w4_s411 | 0,790 | 0,746 | −0,044 |
| w4_s412 | 0,779 | 0,752 | −0,027 |
| w4_s413 | 0,799 | 0,796 | −0,003 |
| s4_s931 | 0,695 | 0,688 | −0,006 |
| s4_s932 | 0,753 | 0,731 | −0,022 |
| s4_s933 | 0,665 | 0,636 | −0,029 |

Mức tăng đều âm hoặc gần không: các trường vô nghĩa không thêm tín hiệu. (AUC cao khoảng 0,8 chỉ do cơ cấu loại nghiệp vụ của gian lận khác nền; vì thế phép đo là mức tăng, không phải AUC tuyệt đối.)

## 3. Thống kê sau sinh (các thế giới phát triển)

| | w4_s411 | w4_s412 | w4_s413 |
|---|---:|---:|---:|
| Dòng gian lận | 800 | 801 | 806 |
| Vụ / kịch bản | 194 / 30 | 196 / 30 | 190 / 30 |
| Công ty có vụ / tổng | 20 / 48 | 28 / 48 | 28 / 48 |
| Mức che giấu L0 / L1 / L2 (vụ) | 35 / 78 / 81 | 34 / 90 / 72 | 26 / 90 / 74 |
| Dòng ca hợp lệ giống gian lận | khoảng 17.900 | | |

Thế giới niêm phong (40 công ty): dòng gian lận 800 / 801 / 807; vụ 154 / 174 / 150; 37 kịch bản; L0 / L1 / L2 là 27 / 69 / 58, 26 / 73 / 75, 24 / 80 / 46.

## 4. Những gì kiểm định **không** bảo đảm
- Không bảo đảm dữ liệu giống thật; chỉ bảo đảm không có lỗi cấu trúc và lối tắt đã biết.
- Không phát hiện lối tắt nằm ở **hành vi** (ví dụ kịch bản nào cũng có đặc trưng chỉ nó có). Cách giảm: bộ kịch bản độc lập (tệp 12) và đối chiếu với dữ liệu ngoài.
