# 5. Thị trường, cạnh tranh và cách thị trường đánh giá

> **Ảnh chụp nghiên cứu tại thời điểm lập tài liệu.** TAM/SAM/SOM, giá và các
> nhận định về đối thủ bên dưới gồm giả định hoặc thông tin có thể thay đổi;
> kiểm nguồn và ngày công bố trước khi dùng cho quyết định thương mại.

## 5.1 Quy mô thị trường (top-down, ghi rõ giả định)

| Tầng | Cách tính | Ước lượng |
|---|---|---|
| Tổng DN đang hoạt động có kết quả SXKD (2025) | Cục Thống kê, sơ bộ | 859.048 |
| DNNVV | ~97–98% | ~835.000 |
| **TAM** — DNNVV có bán chịu B2B (sản xuất, bán buôn, dịch vụ B2B) | giả định 40–50% | ~335.000–420.000 DN |
| **SAM** — đã số hoá (HĐĐT bắt buộc từ 07/2022 + dùng phần mềm kế toán/ngân hàng số), ≥10 lao động | giả định 30–35% của TAM | ~100.000–150.000 DN |
| **SOM 3 năm** | 1–2% SAM qua kênh đối tác phần mềm kế toán/ngân hàng | ~1.500–3.000 DN |

Doanh thu SOM ở giá 750.000–1.500.000đ/tháng: **13,5–54 tỷ đồng/năm** (giả định giá — xem 07). Kênh ngân hàng
(dự báo dòng tiền dùng cho thẩm định hạn mức) có thể mở rộng thêm theo mô hình B2B2B.

## 5.2 Bản đồ cạnh tranh

| Nhóm | Ví dụ | Có gì | Thiếu gì so với Agent 1 |
|---|---|---|---|
| Phần mềm kế toán VN | MISA AMIS/SME, Fast, Bravo | Sổ sách, HĐĐT, báo cáo dòng tiền **quá khứ**, công nợ theo tuổi | Không dự báo xác suất theo hành vi khách; không sốc chung; không khớp sao kê theo hành vi |
| Quản trị vận hành VN | Base.vn, KiotViet, Sapo | Bán hàng, kho, thu chi | Không phải công nợ B2B; không dự báo |
| Ngân hàng số doanh nghiệp | Cash management của các NHTM | Số dư thời gian thực, sao kê | Chỉ thấy tiền, không thấy hoá đơn mở và hành vi khách |
| Dự báo dòng tiền quốc tế cho SME | Float (£79–295/tháng, [nguồn](https://floatapp.com/blog/cash-flow-forecasting-software-cost)), Agicap (báo giá theo yêu cầu) | Kết nối Xero/QuickBooks/ngân hàng, kịch bản | Không có HĐĐT VN, luật thuế/BHXH VN, Tết; phần lớn dự báo theo quy tắc/trung bình, không phân phối xác suất theo hoá đơn |
| AR doanh nghiệp lớn | HighRadius, Billtrust | Dự báo ngày trả, đối soát tự động | Giá và quy trình cho DN lớn; không cho SME VN |

**Khoảng trống thị trường:** chưa có sản phẩm nào cho SME VN kết hợp (1) phân phối xác suất theo từng hoá đơn,
(2) lịch nghĩa vụ đúng luật VN, (3) khớp sao kê ngân hàng VN, (4) giải thích bằng tiếng Việt qua kênh quen thuộc (Zalo).

## 5.3 Cách thị trường đánh giá sản phẩm

### Người mua (SME) đánh giá theo

| Tiêu chí mua | Trọng số (giả định từ phỏng vấn cần làm) | Agent 1 đáp ứng bằng |
|---|---|---|
| Không tốn công nhập liệu | Rất cao | Đọc HĐĐT XML + sao kê, khớp tự động (T0, T9) |
| Tin được con số | Rất cao | Dải xác suất có kiểm định độ phủ; lý do đi kèm; nhãn "theo cam kết/ theo mô hình" |
| Đúng luật VN | Cao | Bộ máy quy tắc có phiên bản theo ngày hiệu lực (T5) |
| Giá so với phần mềm kế toán đang trả | Cao | Định giá dưới hoặc ngang gói kế toán (MISA AMIS Kế toán 2,45–3,95 triệu/năm theo [bảng giá công bố](https://amis.misa.vn/20355/bao-gia-phan-mem-ke-toan-online-misa-amis/), cần kiểm chứng ngày cập nhật) hoặc tích hợp như add-on |
| Bảo mật dữ liệu | Cao | NĐ 13/2023, ẩn danh khi phát triển, không gửi dữ liệu thô cho LLM bên ngoài |

### Nhà đầu tư / đối tác đánh giá theo

| Chỉ số | Mục tiêu năm 1–2 (giả định) |
|---|---|
| ARR, tăng trưởng | 1–5 tỷ → 15+ tỷ |
| Giữ chân doanh thu ròng (NRR) | ≥100% (bán thêm kênh ngân hàng, đa pháp nhân) |
| Churn tháng | ≤2% |
| CAC payback | ≤12 tháng qua kênh đối tác |
| Biên gộp | ≥80% (mô hình cây + mô phỏng chạy CPU, chi phí suy luận thấp) |
| Bằng chứng tác động | Giảm DSO, giảm sự kiện thiếu hụt, độ phủ khoảng thật (T13) |

### Ngân hàng (kênh B2B2B) đánh giá theo

Tỷ lệ nợ quá hạn của danh mục SME dùng sản phẩm, độ chính xác dự báo dòng tiền dùng cho hạn mức, chi phí thẩm định
giảm. Cần dữ liệu đối tác thật để chứng minh (T13).

## 5.4 Định vị

> "Radar dòng tiền cho SME Việt Nam: biết trước 13 tuần tuần nào thiếu tiền, vì sao, và đòi ai trước — từ chính hoá
> đơn điện tử và sao kê của bạn, không nhập tay."

Lợi thế khó sao chép: (1) mô hình hành vi trả tiền hiệu chỉnh cho VN + thích nghi miền theo từng DN; (2) bộ dữ liệu
tổng hợp có nhãn cho các tình huống thực địa (lô, lời hứa, Tết, sốc) mà đối thủ không có; (3) bộ quy tắc luật VN có
phiên bản; (4) vòng phản hồi dữ liệu thật tích luỹ theo thời gian.
