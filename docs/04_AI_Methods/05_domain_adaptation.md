# 5. Domain adaptation — từ dữ liệu nguồn sang doanh nghiệp đích

## 5.1 Bài toán

Sản phẩm sẽ gặp DN mới chỉ có **M tháng** lịch sử (HĐĐT bắt buộc từ 07/2022 ⇒ phổ biến 12–36 tháng; khi mới onboard có thể chỉ 3–6 tháng).
Mô hình huấn luyện trên miền **nguồn** (tổng hợp + dữ liệu thật tương tự) phải *nhanh chóng khớp hành vi riêng* của DN đích mà không cần
hàng nghìn hoá đơn. Đây là nhu cầu "domain adaptation" của đề bài.

Phân loại dịch chuyển (covariate/label/concept shift) trong bài toán này:

| Loại | Ví dụ ở miền đích `tgt` |
|---|---|
| Covariate shift p(x) | SME nhỏ hơn, cơ cấu ngành khác, nhiều khách tập trung, ghi sổ theo lô nhiều hơn |
| Prior/label shift p(y) | trễ dài hơn 25%, tranh chấp ×1,5 |
| Concept shift p(y\|x) | khách trả theo lịch khác; ít ghi số HĐ trong CK |

## 5.2 Thiết kế bất biến miền (làm trước, rẻ nhất)

1. **Đặc trưng tương đối:** ngày so với hạn, tiền chia trung vị công ty, tỷ lệ/thứ hạng thay vì giá trị tuyệt đối.
2. **Thống kê khách co về công ty (EB, k=4):** khi ít lịch sử, dự đoán tiến về trung bình của DN đích — tự động thích nghi tốc độ trễ của DN.
3. **Đặc trưng sốc chung đo trực tiếp (`f_resid_28d`):** thay vì giả định sốc, đo xem tuần gần nhất khách trả chậm hơn kỳ vọng bao nhiêu.
4. **Biến tuần k tất định:** không phụ thuộc miền.

## 5.3 Năm chiến lược thích nghi (đã cài trong `scripts/run_t1.py::exp_B`)

| # | Chiến lược | Cách làm | Khi nào mạnh | Rủi ro |
|---|---|---|---|---|
| S0 | **Zero-shot** | Dùng mô hình nguồn nguyên trạng | M=0, DN mới | lệch miền |
| S1 | **TGT-only** | Huấn luyện chỉ trên M tháng đích (leaves 31, min_data 50, 300 vòng) | M lớn | thiếu dữ liệu khi M nhỏ |
| S2 | **POOLED (tgt-upweighted)** | Gộp nguồn + đích; trọng số đích `max(1, 0,3·|src|/|tgt|)` | M vừa | chọn trọng số |
| S3 | **FINE-TUNE** | Tiếp tục boosting từ mô hình nguồn trên dữ liệu đích (lr 0,02; +150 vòng) | M nhỏ–vừa; ít dữ liệu | quên phân phối nguồn nếu quá nhiều vòng |
| S4 | **IW-POOLED (density-ratio)** | Trọng số mẫu nguồn `w(x)=p_tgt(x)/p_src(x)` từ bộ phân loại miền, kẹp [0,05; 20] (Shimodaira 2000; Bickel 2009), gộp với đích | covariate shift rõ | phương sai trọng số lớn |
| +CQR | **Hiệu chỉnh khoảng ở đích** | CQR trên cửa sổ đích gần nhất đã quan sát đủ (≥120 ngày) | luôn | cần cửa sổ đủ dài |

Thiết kế thí nghiệm B: gốc O = 2024-07-01; nguồn = `src` snapshot 14 ngày/lần đến O; đích = `tgt` với lịch sử nhìn thấy M ∈ {0, 3, 6, 12, 24}
tháng trước O (`visible_from`); test = 52 tuần sau O với nhãn kiểm duyệt tại 2025-12-31. So với B1/B1d (mốc theo khách). 
Chỉ số: pinball, MAE, cov80, IBS, ECE, WAPE thu 1–4 và 5–13 tuần — **tại từng M**, tạo "đường cong học".

## 5.4 Giả thuyết cần kiểm (và tiêu chí)

| # | Giả thuyết | Tiêu chí chấp nhận |
|---|---|---|
| DA1 | Zero-shot (M=0) đã tốt hơn B1 ≥20% về WAPE thu 4 tuần | G7 một phần |
| DA2 | Fine-tune ở M=3 tốt hơn zero-shot ≥10% pinball | G7 |
| DA3 | Fine-tune ≥ TGT-only khi M ≤ 6, TGT-only bắt kịp khi M ≥ 24 | đường cong cắt nhau |
| DA4 | IW-POOLED > POOLED thường khi covariate shift lớn (so `tgt` với `sens_*`) | CI bootstrap theo công ty không chứa 0 |
| DA5 | CQR đích khôi phục cov80 ∈ [75, 85]% ngay cả khi M=3 | |
| DA6 | Tiền huấn luyện nguồn lớn hơn (×5) giảm nhu cầu M (scaling) | M* (tháng để đạt ngưỡng) giảm |
| DA7 | Đặc trưng sốc chung đo trực tiếp giúp ở giai đoạn khủng hoảng | A/B trên 2021-07→10 và 2022-10→2023-06 |

Trạng thái hiện hành lấy từ `outputs/t1/DA_hypotheses.csv` và
[04_ket_qua_hien_co.md](../03_Evaluation/04_ket_qua_hien_co.md). Các kết luận cũ trước sửa
as-of/CDF được giữ trong bản lịch sử. `scripts/run_da_paired.py` bổ sung phép xác nhận
DA1–DA4 với CI cặp trên ngân sách nguồn/đích tối đa 40k snapshot và 300 vòng (FT thêm 150),
lưu riêng với bảng B cũ. Scaling và DA7 có bảng riêng; trạng thái hoàn tất đọc từ metadata
và sổ tiến độ. Không dùng số trên miền đích để xây chính sách onboarding.
WAPE của T1 dồn số dư hoá đơn đang mở vào tuần tất toán theo giao thức gốc;
đây là chỉ số proxy cho tiền thu, không thay E2E hoặc phép đo T9→T1 dùng từng khoản tiền thực nhận.

## 5.5 Phương án nâng cao (nếu S0–S4 chưa đủ)

| Hướng | Ý | Chi phí | Khi nào |
|---|---|---|---|
| Hierarchical Bayes theo ngành/DN/khách | `delay_c ~ N(μ_firm, τ²)`, `μ_firm ~ N(μ_ngành, σ²)`: chia sẻ sức mạnh tự nhiên | trung bình | khi có dữ liệu DN thật nhiều |
| Meta-learning (MAML nhẹ cho GBM không phù hợp) → dùng **mô hình mạng nhỏ + FiLM theo DN** | tối ưu "khởi tạo nhanh thích nghi" | cao | nếu dữ liệu >100 DN |
| Adversarial/IRM đặc trưng bất biến | loại đặc trưng không bền giữa các thế giới | trung bình | khi có ≥10 thế giới huấn luyện |
| **Domain randomization** | huấn luyện trên nhiều thế giới tham số (đuôi, ghi sổ, memo) | thấp (đã có máy phát) | **nên làm trước** (WP-D2) |
| Test-time adaptation | cập nhật thống kê đặc trưng theo cửa sổ gần nhất | thấp | có thể dùng ngay: `f_resid_28d` là dạng đơn giản |
| Thích nghi dòng (online) | cập nhật boosting hằng tuần với trọng số suy giảm theo thời gian | thấp | giai đoạn vận hành |

## 5.6 Rủi ro và cách phát hiện

- *Negative transfer:* mô hình nguồn tệ hơn mốc B1d ở đích → theo dõi S0 vs B1d tại M nhỏ; nếu thua thì rơi về B1d + CQR.
- *Quá khớp M nhỏ:* dùng min_data cao, early stopping theo cửa sổ hiệu chỉnh đích; không tune trên test.
- *Rò rỉ miền đích:* `tgt` niêm phong; siêu tham số chọn trên `src`.
- *Giả thuyết "tổng hợp → thật":* kết quả trên `tgt` chỉ là tầng 3; muốn kết luận tầng 1 phải chạy S0/S3 trên Customer Invoices/BPI (đã có S0 ở
  thí nghiệm C) và trên DN thật (T13).
