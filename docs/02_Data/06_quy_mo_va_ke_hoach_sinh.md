# 6. Quy mô dữ liệu và kế hoạch sinh dữ liệu lớn

## 6.1 Quy mô hiện có

| Thế giới | Công ty | Khách | Hoá đơn | Thanh toán | Giao dịch NH | Lời hứa | Chi | Giai đoạn |
|---|---|---|---|---|---|---|---|---|
| `src` | 40 | 3.427 | 193.469 | 202.810 | 188.260 | 44.327 | 35.217 | 2019-01 → 2025-12 |
| `tgt` | 14 | 617 | 41.762 | 43.778 | 39.512 | 13.255 | 12.164 | cùng |
| `sens_uk` | 12 | 772 | 89.031 | 93.290 | 82.959 | 16.350 | 10.767 | cùng |
| `sens_coface` | 12 | 594 | 70.583 | 72.280 | 65.346 | 15.631 | 10.542 | cùng |
| **Tổng** | **78** | **5.410** | **394.845** | 412.158 | 376.077 | 89.563 | 68.690 | |

Dữ liệu thật đã chuẩn hoá: ~0,9 triệu dòng (BPI 211k + Customer Invoices 50k + SBA 638k) và 0,4 triệu tài khoản-tuần
(Berka), 7.738 điểm chuỗi tuần (Online Retail).

Số liệu mô tả của từng thế giới: tỷ lệ nợ xấu theo số HĐ 2,2% (src), 2,8% (tgt); tranh chấp 1,5% / 2,2%; trả một phần
6,5% / 6,9%; cực trễ 0,48% / 0,42% (coface 2,49%); COD 50% / 38% (theo số lượng).

## 6.2 Mức cần thiết theo mục đích

| Mục đích | Số công ty | Số hoá đơn | Lý do |
|---|---|---|---|
| Phát triển nhanh / CI | 3–6 | ~10–20k | chạy dưới 1 phút |
| Huấn luyện nguồn tốt | 150–300 | 1–3 triệu | học tương tác đặc trưng × tuần × ngành; đa dạng đuôi/ghi sổ |
| Tiền huấn luyện mô hình nền tảng nhỏ cho T1 (nếu làm) | 1.000–5.000 | 20–100 triệu | |
| Kiểm định thống kê (độ phủ, bootstrap theo công ty) | ≥60 công ty đích | ≥300k | CI hẹp cho chỉ số theo công ty |
| Stress/phép thử đuôi | 12 × mỗi giả định | 70–100k | đã có |
| Hard-case chuyên biệt (H13–H16, H28–H29, H46) | 10–20 mỗi hard case | 20–50k mỗi cái | tách riêng để đo năng lực |

## 6.3 Tốc độ và cách mở rộng

Đo thực tế: 3 công ty / 17.825 hoá đơn ≈ 20 giây (gồm nạp lịch). Ước tính tuyến tính (chưa đo ở quy mô lớn):
~1 triệu hoá đơn ≈ 20–30 phút trên 1 tiến trình; bộ nhớ chủ yếu ở mảng thanh khoản `khách × tuần` (≈ 0,5 MB/100 khách).
Điểm nghẽn: vòng lặp Python trong `bank_ledger` (nhóm theo lệnh chuyển) và `promises` — tối ưu bằng vector hoá.

**Kế hoạch sinh lớn (shard):**

```
for shard in 0..N-1:
    cfg = WorldConfig(name=f"big_{shard:03d}", seed=10_000+shard, n_firms=50, industry_mix=..., tail=<chọn>, ...)
    generate(cfg)             # độc lập, chạy song song theo shard (mỗi shard 1 tiến trình)
gộp: concat parquet theo `firm_id` có tiền tố shard (F{shard}-{id}); tái dùng `customers`, `events`, `macro`
```

Lưu ý bắt buộc khi sinh lớn:
1. **Macro dùng chung** (F_w, OxCGRT) hay riêng? Dùng *chung* trong cùng một thế giới để giữ tương quan thực; khác thế giới
   thì khác seed → tạo "đa vũ trụ" kiểm tra độ bền.
2. **Phân tầng tham số**: lấy mẫu `tail ∈ {atradius, uk, coface}`, `posting_mode_p`, `late_scale ∈ [0,8; 1,4]`,
   `dispute_scale ∈ [0,5; 2]`, `memo_invoice_no_p` theo lưới/Sobol để bao phủ không gian domain; ghi tham số vào `config.json`.
3. **Giữ tỷ lệ marginal sau mỗi shard**: chạy `fidelity.report` và loại shard lệch >3 điểm phần trăm so với Atradius (nếu
   không phải shard cố ý lệch).
4. **Niêm phong**: bộ đích `tgt_*` dùng seed riêng, không tham gia chọn siêu tham số.
5. **Dung lượng**: ~15 MB/100k hoá đơn (parquet) → 1 triệu HĐ ≈ 150 MB; XML hoá đơn chỉ sinh mẫu 200–2.000 (mỗi XML ~1,5 KB).

## 6.4 Kết hợp thật + tổng hợp ở quy mô lớn

| Giai đoạn huấn luyện | Dữ liệu | Mục đích |
|---|---|---|
| Tiền huấn luyện | N shard tổng hợp (1–3 triệu HĐ) | Học cấu trúc: lịch, ngày chạy, tương tác đặc trưng, đuôi |
| Hiệu chỉnh nhẹ | Customer Invoices / BPI (thật) với trọng số | Chống lệch miền "quá sạch" |
| Thích nghi đích | 3–12 tháng dữ liệu DN đích (thật hoặc `tgt`) | Hành vi riêng của DN |
| Hiệu chỉnh khoảng | Cửa sổ gần nhất của DN đích (CQR/ACI) | Độ phủ đúng |

## 6.5 Kiểm tra chất lượng bắt buộc sau mỗi lần sinh

1. `fidelity_report.json`: tỷ trọng đích Atradius; dấu hiệu cấu trúc so bộ ERP thật.
2. Kiểm tra bất biến: tổng thanh toán ≤ giá trị HĐ (trừ thu hồi); không thanh toán trước ngày lập; không thanh toán cuối tuần (>1,5%); mọi MST hợp lệ.
3. Kiểm tra rò rỉ: nhãn không xuất hiện trong bảng quan sát (`customers` có thuộc tính tiềm ẩn — cấm đưa vào đặc trưng).
4. `pytest tests` (T0/T5) vẫn đạt.
