# Tổng quan và nguyên tắc dữ liệu

## 1. Vì sao phải sinh dữ liệu
1. Sổ sách của doanh nghiệp nhỏ là dữ liệu nội bộ, không công bố. Bài báo của nhóm Đại học Würzburg cũng nói dữ liệu hệ thống ERP nói chung không được công bố [Đ, Phần 6].
2. Nhãn gian lận nội bộ càng hiếm: vụ bị phát hiện mới có nhãn, còn lại là "không biết".
3. Cần dữ liệu có **độ khó điều chỉnh được** và **kịch bản biết trước** để đo từng năng lực (bắt kịch bản đã thấy, chưa thấy, che giấu kỹ, doanh nghiệp mới).

## 2. Chiến lược bốn lớp

| Lớp | Nội dung | Dùng để | Không dùng để | Trạng thái |
|---|---|---|---|---|
| 1. Nền thật không nhãn | BPI 2019, BPI 2020, chi trả nhà cung cấp của thành phố | Đo số cảnh báo mỗi 1.000 giao dịch của từng luật | Đo độ chính xác | **Chưa chạy** |
| 2. Thế giới tổng hợp có nhãn | v3, v4, niêm phong (tự sinh) | Huấn luyện, chọn phương pháp, đo tỷ lệ phát hiện theo kịch bản | Kết luận tần suất gian lận thật | **Đã làm** |
| 3. Bộ đối chiếu ngoài | ERP Fraud Data (Würzburg), sổ cái DFKI | Kiểm tra độc lập với bộ sinh của ta | Huấn luyện chính | **Đã chạy** |
| 4. Bộ thử phần mã | Elliptic, AMLSim, SAML-D, BAF | Thử đồ thị, mất cân bằng, trôi dữ liệu | Bằng chứng gian lận nội bộ | Không dùng |

## 3. Tám nguyên tắc sinh dữ liệu

| # | Nguyên tắc | Vì sao | Cách thực hiện |
|---|---|---|---|
| P1 | Nền sinh từ **quy trình kinh doanh có liên kết**, không rút ngẫu nhiên từng dòng | Dòng rời rạc để lại dấu vết thống kê giả | Bán chịu → thu tiền → xóa nợ; mua hàng → thanh toán theo kỳ hạn; lương theo ngày chốt của công ty |
| P2 | **Ngẫu nhiên hóa từng công ty** | Mô hình không được thuộc một mẫu chung | Ngành, quy mô, ngày trả lương, kỳ hạn công nợ, hạn mức tự duyệt khác nhau |
| P3 | Gian lận sinh theo **vụ** (nhiều dòng, một người, một khoảng thời gian), không theo dòng | Đo cả mức dòng lẫn mức vụ | Bảng `truth_cases`, nhãn `case_id` |
| P4 | Mỗi kịch bản có **ba mức che giấu** L0, L1, L2 | Đo độ khó tăng dần | Tỷ lệ 15%, 45%, 40% theo ACFE (89% có che giấu) |
| P5 | Mỗi kịch bản có **ca hợp lệ giống hệt** | Đo báo nhầm trên ca khó | Ví dụ lương thưởng thật, hủy hàng kiểm kê có biên bản |
| P6 | **Không có thông tin tương lai** | Tránh rò rỉ thời gian | Kiểm tra thứ tự: tạo ≤ duyệt ≤ ghi sổ; người lập đã vào làm; không dữ liệu chủ tương lai |
| P7 | **Không có lối tắt** | Mô hình không được đoán từ trường vô nghĩa | Kiểm tra: phút, giây, số thứ tự ID, chữ số hóa đơn không thêm tín hiệu |
| P8 | Mỗi vụ nằm **trong một giai đoạn** (huấn luyện, kiểm định hoặc kiểm thử) | Tránh rò rỉ giữa các giai đoạn | Ràng buộc trong bộ sinh và trong kiểm định |

## 4. Quy tắc nhãn
- Chỉ dòng **chính nó là hành vi gian lận** mới có `is_fraud = 1`. Dòng hỗ trợ (ví dụ hóa đơn thật sau đó bị thanh toán trùng) có `case_role = support` và `is_fraud = 0`.
- Nhãn, `case_id`, kịch bản, mức che giấu **không** nằm trong `transactions.csv` hay `features.csv`; chỉ ở `labels.csv` và `truth_cases.csv`. Bộ kiểm định kiểm tra điều này.
- Dòng `hard_negative_type` khác rỗng là ca hợp lệ giống gian lận; dùng để đo báo nhầm.
