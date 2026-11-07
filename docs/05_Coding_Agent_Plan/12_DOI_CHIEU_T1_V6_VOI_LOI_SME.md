# Đối chiếu báo cáo T1 V6 với lõi SME · 05/11/2026

**Quyết định.** Giữ V6 làm ứng viên đánh giá song song. Dùng xác suất tất toán ở cả 28 và 91 ngày để rà soát ứng viên cho kế hoạch 13 tuần. Khi có đủ dữ liệu thu từng phần và sao kê, chấm riêng sai số tiền về từng tuần trước khi quyết định triển khai.

## Báo cáo bên gửi đo gì?

Trên 65.221 hóa đơn tại sáu World tổng hợp, tác giả báo cáo Brier trung bình ở 28/91 ngày giảm 1,60% so với HazardGBM mặc định từ commit `70c0ceb` tái huấn luyện. Brier riêng ở 91 ngày giảm 2,33%, ở 365 ngày giảm 26,54%. Đối chứng học 13 tuần rồi ngoại suy. V6 học tới 53 tuần, tách tất toán và xóa nợ, đồng thời đổi đặc trưng và cấu hình. Chưa tách được đóng góp của từng thay đổi. Chỉ số hiệu chỉnh ECE tại 28 ngày tăng nhẹ.

Lõi SME ở `agent1/adaptive/methods.py` học hazard tới 52 tuần **tính từ ngày phát hành**. Ở ngày chốt, dự báo 13 tuần phụ thuộc vào tuổi hiện tại của hóa đơn. Lõi đã nhận ngày xóa nợ và loại công nợ đã xóa ở ngày dự báo. Để ước lượng hai xác suất riêng cho tất toán và xóa nợ, cần lịch sử sự kiện đã xác minh cùng thời điểm doanh nghiệp biết chúng.

## Kiểm tra lại trên sổ công khai

Giữ nguyên đơn vị HR-CA02, ngày 15/01/2020 và hai ứng viên từ benchmark SME trước. Học với thông tin có tới ngày chốt. So trên đúng 72 hóa đơn đang mở thuộc 27 khách. Đây là phép rà soát hồi cứu. Ngày ghi sổ ERP làm đại diện cho ngày tất toán. Biến `is_bad_debt` của bộ nạp Customer Invoices được gán cố định `False`, nên bộ này thiếu nhãn thật cho xóa nợ.

| Hạn tính từ ngày chốt | Tất toán quan sát | Brier mốc lịch sử | Brier neural SME | ECE mốc → neural |
|---|---:|---:|---:|---:|
| 28 ngày | 68/72 | 0,008204 | 0,006513 | 0,01206 → 0,02959 |
| 91 ngày | 72/72 | 0,000082 | 0,000101 | 0,00121 → 0,00247 |

Ở ngày 28, phần giảm sai số lớn nhất đến từ **một hóa đơn quá hạn 31–90 ngày**. Trong 63 hóa đơn chưa quá hạn, mốc lịch sử có Brier bằng 0 còn neural là 0,00244. Tập này không có hóa đơn quá hạn trên 90 ngày. Đến ngày 91, mọi hóa đơn đều đã tất toán. Do đó kỳ này chưa trả lời được mô hình nào nhận diện tốt nợ kéo dài. Dữ liệu ghi sổ chỉ tới 14/05/2020, chưa đủ một năm kể từ ngày chốt.

## Cách chấm V6 khi có dự báo

Trong file người dùng gửi có các bảng tổng hợp. Chưa có dự báo V6 cho 72 hóa đơn của HR-CA02 trong workspace. Để đo trực tiếp cần mô hình V6 cùng builder đặc trưng phù hợp dữ liệu thật, hoặc file dự báo độc lập trên đúng các hóa đơn này. Đặc trưng ngành hoặc ledger thiếu phải có quy ước đã kiểm định từ trước. Kiểm tra nguồn huấn luyện, ngày chốt và thời điểm các đặc trưng sẵn có trước khi dùng file ứng viên.

1. Chạy `python scripts/business/compare_paid_horizons.py` để tái tạo kết quả mốc và neural SME. Kết quả gồm Brier, ECE với 10 bin cố định, tỷ lệ dự báo/thực tế, quy mô từng nhóm quá hạn và CI ghép cặp theo khách.
2. Để chấm ứng viên khác, thêm `--candidate-csv PATH`. CSV gồm `firm_id,invoice_id,cutoff,paid_28,paid_91`, trong đó hai cột cuối là xác suất tích lũy **trả đủ** tính từ ngày chốt. Công cụ ghép theo khóa, từ chối hóa đơn thiếu/thừa/trùng, xác suất ngoài miền hoặc giảm theo thời gian. Kết quả ứng viên ngoài có thư mục riêng, kèm hash file.
3. Ở kỳ pilot tiếp theo, khóa dự báo trước khi biết kết quả. Ưu tiên kỳ có cả hóa đơn còn mở sau 91 ngày và hóa đơn đã tất toán. Với khoản xóa nợ, cần hóa đơn, ngày hiệu lực, ngày ghi nhận và phần dư đã xóa. Với dòng tiền, cần ngày và số tiền từng lần thu, kể cả thu hồi sau xóa nợ.

[Bảng điểm theo hạn và tuổi nợ](../../outputs/business/paid_horizon_audit/scores.csv) · [Giao thức, hash và CI của chỉ số chung](../../outputs/business/paid_horizon_audit/protocol.json)
