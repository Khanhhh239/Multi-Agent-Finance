# 6. Yêu cầu sản phẩm và phạm vi

## 6.1 Yêu cầu chức năng (FR) ánh xạ nhiệm vụ T

| Mã | Yêu cầu | Nhiệm vụ | Trạng thái (15/10/2026) |
|---|---|---|---|
| FR-01 | Nhập HĐĐT XML (QĐ 1450/1510), sổ ERP, sao kê CSV/Excel về lược đồ chuẩn; cổng chất lượng (MST, cộng tiền, ngày, trùng) | T0 | Có code + kiểm thử |
| FR-02 | Khớp giao dịch ngân hàng với hoá đơn (một-nhiều, trả một phần), lấy ngày tiền về thật | T9 | Có code, đã đo trên miền đích |
| FR-03 | Phân phối thời điểm trả theo tuần cho mỗi hoá đơn mở (13 tuần + đuôi) | T1 | Có code, đã đo (tổng hợp + 2 bộ thật) |
| FR-04 | Xác suất không bao giờ trả / nợ xấu, tổn thất kỳ vọng; đề xuất dự phòng theo TT48/2019 | T2 | Có code + kết quả: tổng hợp PR-AUC 0,97; SBA thật 15,7× nền (nhãn EXEMPT cần xử lý) |
| FR-05 | Xác suất tranh chấp, trả một phần; số tiền kỳ vọng thu | T3 | Có kết quả: EB lịch sử khách thắng LightGBM |
| FR-06 | Dự báo doanh thu mới chưa lập hoá đơn (phân vị 1–13 tuần) | T4 | Có code, đã đo (tổng hợp + thật) |
| FR-07 | Lịch chi tất định: lương, BHXH, GTGT tháng/quý, TNDN tạm nộp, môn bài, thuê, vay; dịch ngày nghỉ/Tết | T5 | Có code + 15 kiểm thử |
| FR-08 | Mô phỏng số dư 13 tuần, P10/P50/P90, P(thiếu hụt), sốc chung, hiệu chỉnh conformal | T6 | Có code, đã chạy trên `tgt` (cov80 0,79–0,81); chưa đo lead time |
| FR-09 | Cảnh báo điểm gãy hành vi theo khách/danh mục, chuyển chế độ thận trọng | T7 | Có code, đã đo |
| FR-10 | Ghi lời hứa trả, độ tin cậy lời hứa theo khách, đưa vào dự báo | T8 | Có trong đặc trưng; giảm MAE 7,2% trên HĐ có lời hứa |
| FR-11 | Giải thích (lý do) + xếp hạng đòi nợ + kịch bản "nếu như" | T10 | Code demo có, chưa chạy |
| FR-12 | Backtest rolling-origin, cổng GO/NO-GO, báo cáo trường hợp sai | T11 | Có cho T1/T4/T7/T9 |
| FR-13 | Máy phát dữ liệu tổng hợp hiệu chỉnh VN | T12 | Xong |
| FR-14 | Thử nghiệm với DN đối tác, giám sát trôi | T13 | Chưa (cần đối tác) |

## 6.2 Yêu cầu phi chức năng (NFR)

| Mã | Yêu cầu | Mục tiêu |
|---|---|---|
| NFR-01 Độ chính xác | Vượt mốc đơn giản trên backtest theo thời gian | xem 03_Evaluation/03 (cổng G1–G9) |
| NFR-02 Hiệu chỉnh | Độ phủ khoảng 80% nằm trong [75, 85]% | CQR/ACI |
| NFR-03 Hiệu năng | Batch đêm ≤5 phút CPU/DN (≤2.000 hoá đơn mở); kịch bản "nếu như" ≤3 giây | MC 1.000 đường |
| NFR-04 Khả dụng | 99,5% cho dashboard; batch có thể chạy lại | |
| NFR-05 Truy vết | Mỗi dự báo lưu phiên bản mô hình, dữ liệu as-of, tham số | MLflow/registry |
| NFR-06 Bảo mật | Dữ liệu theo NĐ 13/2023: đồng ý của chủ dữ liệu, ẩn danh trong môi trường phát triển, mã hoá khi lưu | |
| NFR-07 Giải thích | Mỗi cảnh báo có lý do định lượng; LLM không sinh số | kiểm thử đối chiếu số |
| NFR-08 Bền vững | Chế độ khủng hoảng khi phát hiện điểm gãy: nới khoảng, ưu tiên dữ liệu gần | T7 |

## 6.3 Ngoài phạm vi (giai đoạn này)

- Tự động thực hiện thanh toán, vay, chuyển tiền (vượt quyền; rủi ro pháp lý).
- Tư vấn đầu tư cá nhân hoá.
- Dự báo chi tiết tồn kho / định giá sản phẩm.
- Đa tiền tệ phức tạp (chỉ hỗ trợ quy đổi theo tỷ giá ngày ở bản đầu).

## 6.4 Ràng buộc pháp lý và nghiệp vụ

| Văn bản | Ảnh hưởng |
|---|---|
| NĐ 123/2020, QĐ 1450/QĐ-TCT (sửa đổi 1510) | Định dạng XML hoá đơn điện tử là nguồn đầu vào chuẩn |
| Luật Quản lý thuế 38/2019 (Điều 44, 55), NĐ 126/2020 | Hạn khai/nộp GTGT, TNDN; dịch hạn khi trùng ngày nghỉ |
| NĐ 293/2025 (lương tối thiểu vùng 2026), luật BHXH 2024 | Chi lương, BHXH |
| NQ 198/2025/QH15 | Bỏ lệ phí môn bài từ 2026 |
| NQ giảm thuế GTGT 2% (43/2022 … 204/2025) | Thuế suất 8%/10% theo thời kỳ, loại trừ một số ngành |
| TT 48/2019/TT-BTC | Khung trích lập dự phòng nợ khó đòi theo tuổi quá hạn (30/50/70/100%) — sàn quy tắc cho T2 |
| NĐ 13/2023 | Bảo vệ dữ liệu cá nhân; điều kiện dùng dữ liệu đối tác |

Mọi quy tắc pháp lý trong code là nguồn thứ cấp đã ghi chú — phải đối chiếu văn bản gốc trước khi dùng thật.
