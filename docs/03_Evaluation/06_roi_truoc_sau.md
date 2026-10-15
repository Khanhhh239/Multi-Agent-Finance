# 6. ROI trước/sau — phép tính cho một SME mẫu

Mã tái tính: `scripts/roi_calc.py` (đổi tham số ở đầu file, chạy lại). Kết quả: `outputs/roi_scenarios.json`.

> **Trung thực:** đây là mô hình kinh tế với tham số *giả định có lý do*, không phải đo thực tế. Chỉ các mối liên hệ
> kỹ thuật (WAPE, IBS…) đã đo trên dữ liệu tổng hợp/thật tương tự; chuyển sang tiền cần xác nhận ở T13.

## 6.1 SME mẫu

| Thông số | Giá trị | Nguồn |
|---|---|---|
| Doanh thu | 40 tỷ/năm (SME vừa; trung vị `src`) | giả định |
| Tỷ trọng bán chịu | 65% → 26 tỷ/năm → **71,2 tr/ngày** | Atradius VN 2025 |
| Hoá đơn quá hạn | 39% giá trị, trễ ~30 ngày → **trễ bình quân theo giá trị 11,7 ngày** | Atradius |
| Nợ xấu | 3% doanh số bán chịu → **780 tr/năm** | Atradius |
| Chi phí hoạt động | 40 tỷ × (1 − 4,5% biên) = 38,2 tỷ → **104,7 tr/ngày** | giả định |
| Đệm tiền mặt | 27 ngày chi = **2,83 tỷ** | JPMorgan Chase Institute (Mỹ) |
| Chi phí vốn | 9%/năm | gần lãi suất cho vay VN (WDI) — cần cập nhật |
| Khách hàng thấy 2 sự kiện thiếu hụt/năm | mỗi sự kiện ≈ 17,5 tr (lãi vay nóng ~12, phạt chậm nộp ~2, mất chiết khấu/phí NCC ~1,5, khác 2) | giả định |
| Rủi ro đuôi (trễ lương, mất NCC, NH từ chối) | 3%/năm × 300 tr | giả định |
| Công kế toán | 30 giờ/tháng đối chiếu tiền + 4 giờ/tuần dự báo Excel = **568 giờ/năm**; 80.000đ/giờ | benchmark quốc tế 20–50 giờ/tháng; lương kế toán 14 tr/176 giờ |

## 6.2 Trước và sau (kịch bản cơ sở)

| Chỉ số | Trước | Sau | Thay đổi | Cơ chế |
|---|---|---|---|---|
| Trễ bình quân theo giá trị (ngày) | 11,7 | 9,7 | −2,0 | đòi khoản có tác động lớn nhất trước (T10) |
| Vốn lưu động khách giữ hộ | 833 tr | 691 tr | −142 tr | = 71,2 tr × 2 ngày |
| Đệm tiền mặt duy trì | 2.826 tr (27 ngày) | 2.261 tr (21,6 ngày) | −565 tr (−20%) | đệm theo P10 số dư dự báo thay vì "cho chắc" |
| Sự kiện thiếu hụt khẩn cấp/năm | 2,0 | 0,6 | −1,4 | cảnh báo ≥4 tuần cho 70% sự kiện → xử lý có kế hoạch |
| Chi phí tài chính do thiếu hụt | 35 tr | 16,6 tr | −18,4 tr | chi phí vay kế hoạch = 25% khẩn cấp |
| Nợ xấu | 780 tr (3,0%) | 702 tr (2,7%) | −78 tr | phát hiện sớm khách xấu, dừng giao/đòi sớm (hành vi của DN) |
| Giờ công kế toán | 568 | 206 | −362 giờ | T9 tự khớp 60% đối chiếu, dự báo tự động 70% |
| Rủi ro đuôi kỳ vọng | 9,0 tr/năm | 4,5 tr/năm | −4,5 tr | cảnh báo giảm 50% xác suất sự kiện nặng |

## 6.3 Quy đổi ra tiền (triệu đồng/năm)

| Nguồn lợi ích | Công thức | Thấp | **Cơ sở** | Cao |
|---|---|---|---|---|
| B1 Giải phóng đệm → trả nợ vay/tiền gửi | đệm × %giảm × 9% | 25,4 | **50,9** | 76,3 |
| B2 Giảm trễ → vốn lưu động | 71,2 tr × ngày giảm × 9% | 6,4 | **12,8** | 19,2 |
| B3a Giảm chi phí thiếu hụt khẩn cấp | số sự kiện × 17,5 × tỷ lệ bắt được × (1 − 25%) | 5,2 | **18,4** | 31,5 |
| B3b Giảm rủi ro đuôi | xác suất × 300 × giảm | 0 | **4,5** | 10,5 |
| B4 Giảm nợ xấu | 780 × % giảm | 39,0 | **78,0** | 156,0 |
| B5 Tiết kiệm công | giờ tiết kiệm × 80.000đ | 19,8 | **28,9** | 36,4 |
| **Tổng lợi ích/năm** | | **95,9** | **193,5** | **329,9** |

Tham số kịch bản: Thấp (đệm −10%, trễ −1 ngày, bắt 40% của 1 sự kiện, nợ xấu −5%, tự động 40%/50%); Cơ sở (−20%, −2 ngày,
70% của 2 sự kiện, −10%, 60%/70%, giảm đuôi 50%); Cao (−30%, −3 ngày, 80% của 3 sự kiện, −20%, 80%/80%, đuôi 5%×70%).

## 6.4 ROI của khách hàng

| Chỉ tiêu | Thấp | Cơ sở | Cao |
|---|---|---|---|
| Lợi ích/năm (tr) | 95,9 | 193,5 | 329,9 |
| Chi phí sở hữu năm 1 (gói Growth) (tr) | 20,6 | 20,6 | 20,6 |
| Lợi ích ròng (tr) | 75,3 | 172,9 | 309,3 |
| Tỷ suất lợi ích/chi phí (theo giá thuê bao 18 tr) | 5,3× | **10,7×** | 18,3× |
| Hoàn vốn (tháng) | 2,6 | **1,3** | 0,7 |

Ngay cả khi **bỏ hẳn B4** (giảm nợ xấu, khoản phụ thuộc hành vi DN nhiều nhất), kịch bản cơ sở còn **115,5 tr/năm = 6,4×** giá thuê bao.

## 6.5 Độ nhạy (một chiều, quanh kịch bản cơ sở 193,5 tr)

| Tham số | Khoảng | Lợi ích (tr) | Biên độ |
|---|---|---|---|
| % giảm nợ xấu | 5% → 20% | 154,5 → 271,5 | **117,0** |
| Chi phí vốn | 6% → 14% | 172,3 → 228,9 | 56,6 |
| Tỷ lệ nợ xấu nền | 2% → 4% | 167,5 → 219,5 | 52,0 |
| % giảm đệm | 10% → 30% | 168,1 → 218,9 | 50,9 |
| Tỷ trọng bán chịu | 50% → 75% | 172,5 → 207,5 | 34,9 |
| Số sự kiện thiếu hụt/năm | 1 → 3 | 184,3 → 202,7 | 18,4 |
| Ngày giảm trễ | 1 → 3 | 187,1 → 199,9 | 12,8 |
| Tỷ lệ bắt sự kiện | 40% → 80% | 185,6 → 196,1 | 10,5 |

**Nhận xét:** kết quả nhạy nhất với *nợ xấu* (cần DN hành động) và *chi phí vốn*; ít nhạy với tham số cảnh báo. Điều đó
nghĩa là giá trị lớn nhất nằm ở **vòng quyết định** (đòi ai, dừng giao ai), không chỉ ở dự báo — và cần thiết kế
sản phẩm (T10) để biến dự báo thành hành động.

## 6.6 Khi nào kết quả này SAI

1. DN không đổi hành vi (không đòi theo danh sách, không điều chỉnh đệm) → B1, B2, B4 ≈ 0; chỉ còn B5.
2. DN đã giữ đệm gần tối ưu hoặc không có hạn mức vay rẻ → B1 nhỏ.
3. Dữ liệu thật quá bẩn (khớp sao kê <40%) → T9 kém, nhãn sai, dự báo mất lợi thế.
4. Giai đoạn sốc ngoài mẫu → khoảng quá hẹp; chỉ T7 + ACI cứu một phần.
5. DN rất nhỏ (<5 tỷ): giá trị tuyệt đối thấp hơn nhiều, chi phí cố định không đổi → gói Starter cần kênh đối tác để có lãi.

## 6.7 ROI của nhà cung cấp (liên kết file 05)

Giá trị tạo ra cho khách (cơ sở) 193,5 tr vs giá 9–18 tr → khoảng cách giá trị/giá ≈ 10×: dư địa để tăng giá hoặc bán
gói bổ sung (kênh ngân hàng, đa pháp nhân) mà vẫn có ROI >3× cho khách. Đầu tư 2,7 tỷ năm 1; hoà vốn vận hành ≈ 188 khách;
thu hồi 14–26 tháng khi có 300–400 khách (05 §5.3).

## 6.8 Cách đo thật để thay giả định (T13)

| Giả định | Đo bằng | Khi nào |
|---|---|---|
| Giảm 2 ngày trễ | K1 trước/sau, DiD | tháng 6 pilot |
| Giảm 20% đệm | K3 (P10 số dư) và đệm DN tự chọn | tháng 6 |
| 2 sự kiện thiếu hụt/năm, 17,5 tr/sự kiện | nhật ký khẩn cấp + sổ chi phí tài chính 24 tháng trước | onboard |
| Tỷ lệ bắt 70% | lead time trên sự kiện thật | tháng 6–12 |
| 10% giảm nợ xấu | bảng chuyển trạng thái nợ trước/sau | tháng 12 |
| 568 giờ công | khảo sát + log hệ thống | tháng 3 |
