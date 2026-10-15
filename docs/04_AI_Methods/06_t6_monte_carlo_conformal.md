# 6. T6 — Mô phỏng số dư 13 tuần, sốc chung và hiệu chỉnh khoảng

Mã: `agent1/models/t6_cash.py` (`simulate`, `collection_kernel`, `ACI`); thí nghiệm: `scripts/run_t6.py`. **Kết quả đã chạy** (03_Evaluation/04 §4.9c): ACI cov80 0,794 (tuần 1–4) / 0,806 (5–13), IS80 tốt nhất tuần 1–4; Brier P(thiếu hụt) 0,014/0,033; lead time và báo giả chưa tính; demo T10 còn lỗi.

## 6.1 Tại sao không cộng độc lập

Trễ thanh toán của các khách *cùng phụ thuộc* thanh khoản thị trường (47% nguyên nhân trễ ở VN là thanh khoản của khách — Atradius). Nếu mô phỏng độc lập,
tổng dòng thu hội tụ về kỳ vọng (luật số lớn), P10 quá cao ⇒ **đánh giá thấp xác suất thiếu hụt** đúng ở tuần nguy hiểm. Mô phỏng cần
*cấu trúc phụ thuộc đuôi dày*.

## 6.2 Mô hình mô phỏng (một đường)

```
g ~ t(ν=4) chuẩn hoá                       # sốc thanh khoản chung toàn danh mục
cho mỗi hoá đơn mở i:
    e_i ~ N(0,1)                           # riêng
    u_i = Φ(√ρ · g + √(1−ρ) · e_i)         # copula t một nhân tố (u cao = trả muộn)
    tuần_i = F_i^{-1}(u_i) , F_i = CDF tuần của hazard T1 (0..12; 13 = ngoài chân trời)
    thu_i  = số tiền mở_i tại tuần_i
doanh thu mới R_j (j=1..13): u = Φ(−0,7·g + √(1−0,49)·z_j) → nội suy phân vị T4 (P10/P50/P90)
    thu theo nhân tử kernel_d (phân bố thời gian thu của HĐ lập 12 tháng gần nhất của DN)
chi: known_out (T5 + NCC đã có HĐ đầu vào 4 tuần đầu, TB 13 tuần sau đó) + capex ~ Poisson(λ lịch sử) × kích cỡ bootstrap
số dư_k = B0 + Σ_{j≤k}(thu − chi)
```

- **ρ** chọn bằng interval score trên miền nguồn (lưới {0; 0,1; 0,2; 0,35; 0,5}) — không đặt tay. **ν=4** là giả định (ước lượng từ SEC: WP-6.4).
- Doanh thu mới tương quan **âm** với sốc chung (sốc thanh khoản cũng làm giảm doanh thu).
- Hoá đơn nợ xấu: T2 gán xác suất; mô phỏng đưa vào nhánh "không trả" (một phần thu hồi).

## 6.3 ACI — hiệu chỉnh khoảng thích nghi (Gibbs & Candès 2021)

Với chân trời k, giữ mức `α_k` (khởi tạo 0,2). Mỗi tuần khi tiền về thực tế lộ diện: `α_k ← α_k + γ(α − 1[y ∉ [lo,hi]])`, γ=0,01;
khoảng = các phân vị `α_k/2` và `1−α_k/2` của mẫu mô phỏng (kẹp [0,005; 0,6]). Lý thuyết: độ phủ dài hạn bảo đảm dù chuỗi vi phạm giả định hoán đổi được.
Giám sát: `α_k` trôi dài hạn xuống thấp ⇒ mô hình quá tự tin ⇒ kích hoạt T7 chế độ khủng hoảng.

## 6.4 Đối chứng (bắt buộc ở `run_t6.py`)

| Mô hình | Vai trò |
|---|---|
| **MC-copula-t (T1+T4+T5)** | chính |
| MC-copula-t **+ ACI** | chính + hiệu chỉnh |
| MC độc lập (ρ=0) | chứng minh giá trị của sốc chung |
| MC ngày điểm B1 (mọi HĐ trả vào tuần B1) | chứng minh giá trị phân phối T1 |
| LightGBM phân vị trực tiếp trên `(số dư_k − B0)/chi tuần` (đặc trưng: công nợ theo nhóm đáo hạn, thu 4/13 tuần gần nhất, chi biết trước luỹ kế) | đối chứng học máy trực tiếp |
| Naive: chi biết trước + thu = trung bình 13 tuần; phần dư thực nghiệm của chính DN | đối chứng sàn |

## 6.4b Xác suất thiếu hụt và lead time
`P_4w = P(min_{k≤4} số dư_k < 0)`, `P_13w` tương tự. Lead time = số tuần từ lần đầu `P_13w ≥ ngưỡng` đến khi thiếu hụt thật. Ngưỡng cảnh báo chọn theo
chi phí: `c_miss·P ≥ c_false·(1−P)` (ví dụ c_miss/c_false = 5 ⇒ ngưỡng 17%). Cần báo cáo đường ROC/PR theo ngưỡng.

## 6.5 T10 gắn với T6
- **Giá trị đòi sớm** của HĐ *j*: chạy lại MC với `tuần_j = 1` ⇒ `ΔP(thiếu hụt)`. Chi phí O(m·n_sim) nên chỉ làm cho top-50 hoá đơn theo số tiền × xác suất trễ (WP-6.3).
- **Kịch bản "nếu như":** dịch phân phối khách X sang phải 2 tuần; hoãn/thêm khoản chi; sốc −30% doanh thu 3 tháng. MC được tái chạy ≤3 giây (1.000 đường).
- **Kịch bản tất định** (không cần phân phối): "toàn bộ khách trễ 30/60 ngày", "khách top-1 vỡ nợ", "doanh thu −30%": hiển thị *runway* dưới từng kịch bản.

## 6.6 Điểm yếu đã biết
1. Phần chi NCC từ tuần 5 chỉ là trung bình ⇒ khoảng dưới đánh giá thấp bất định chi; cần dự báo mua hàng từ pipeline bán.
2. ρ một giá trị cho cả DN; thực tế khác theo khách lớn/nhỏ ⇒ cần copula phân tầng (ρ_khách=0,25, ρ_danh mục=0,75 như nhánh `agent1-Thắng`).
3. Chưa mô hình phụ thuộc giữa sốc thu và sốc chi (ví dụ lãi vay tăng).
4. Hiệu chỉnh ACI giả định mức độ lộ diện nhãn theo chân trời k — phải cài đúng trễ lộ diện (nhãn tuần k chỉ có sau k tuần).
