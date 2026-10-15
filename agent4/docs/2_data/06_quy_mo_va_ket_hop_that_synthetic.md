# 06 · Quy mô lớn và cách kết hợp dữ liệu thật + tổng hợp

## 1. Nhu cầu quy mô
| Mục đích | Quy mô cần | Hiện có |
|---|---|---|
| Phát triển, thử prompt | 1 công ty, ~20 tháng, 10⁵ dòng | ✅ 140.583 dòng (28 MB) |
| Đánh giá tổng quát hóa | **Nhiều công ty** khác ngành/quy mô (≥ 30) để agent không "học thuộc" một DN | ❌ |
| Kiểm thử hiệu năng engine | 10⁶–10⁷ dòng sổ cái | ❌ (cần tham số hóa) |
| Tạo dữ liệu tinh chỉnh | 10⁴–10⁵ cặp (câu hỏi → lời gọi) | ❌ |

## 2. Kế hoạch mở rộng bộ sinh (cần làm, xem `5_handoff`)
### 2.1 Tham số hóa hồ sơ doanh nghiệp (`CompanyProfile`)
Tách các hằng trong `company.py`/`simulator.py` thành cấu hình YAML/JSON:
```yaml
profile_id: vap_it_small
seed: 7
horizon: {start: 2024-01-01, end: 2026-10-14, last_closed: 2026-08}
scale: {monthly_goods_vnd: 3.0e9, customers: {ENT: 6, SME: 40, GOV: 5, DLR: 4}, branches: 1, headcount: 28}
industry: {type: distribution|services|manufacturing|retail|construction, gross_margin_target: 0.17, service_share: 0.10}
behavior: {late_mean_days: {ENT: 18, SME: 12}, chronic_late_share: 0.14}
scenarios: [distressed_customer, marketing_spike, duplicate_payment, margin_squeeze, injection]
```
### 2.2 Họ ngành
| Họ | Khác biệt cần mô hình | Tài khoản/Chỉ số khác |
|---|---|---|
| Phân phối/thương mại (đã có) | Tồn kho, bán chịu | 156, 632 |
| **Dịch vụ/ tư vấn** | Không tồn kho; doanh thu theo dự án; lương là chi phí chính | 511 dịch vụ, 642 lớn |
| **Sản xuất nhỏ** | NVL, BTP, giá thành | 152/154/155/621/622/627 |
| **Xây dựng** | Doanh thu theo tiến độ, bảo lãnh, giữ lại bảo hành | 337, 3387 |
| **Bán lẻ/F&B** | Giao dịch lớn số lượng, tiền mặt nhiều | 111 lớn, nhiều chi nhánh |
Mỗi họ có generator con dùng chung `Ledger` và bộ chỉ số.

### 2.3 Quy mô lớn
- Vector hóa vòng bán hàng theo ngày (hiện lặp Python; ~1 phút/140k dòng).
- Mục tiêu: 1 triệu dòng < 10 phút; 10 triệu dòng bằng phân mảnh theo tháng + ghi Parquet → DuckDB.
- Sinh song song theo `profile_id`/`seed` (đa tiến trình), mỗi công ty một file DuckDB; có bảng `registry`.

## 3. Kết hợp dữ liệu thật và dữ liệu tổng hợp
### 3.1 Ba vai trò của dữ liệu thật
1. **Hiệu chỉnh phân phối** (calibration): chọn tham số bộ sinh sao cho thống kê tóm tắt khớp thật.
2. **Xác thực chéo** (validation): chạy cùng bộ chỉ số trên dữ liệu thật ẩn danh → so sánh *hình dạng* kết quả (ví dụ tuổi nợ, mùa vụ).
3. **Benchmark năng lực mô hình** (không phải sổ cái): Spider 2.0/BFCL cho định tuyến & SQL.

### 3.2 Quy trình hiệu chỉnh hành vi thanh toán (ví dụ cụ thể)
```
1. Lấy phân phối độ trễ từ Customer Invoices (Kaggle) sau khi lọc hóa đơn đã đóng:
     d = ngày_thanh_toán − ngày_đến_hạn ; xét P10/P50/P90, tỷ lệ d ≤ 0, đuôi > 60 ngày
2. Khảo sát (Atradius VN): mức trễ trung bình ~ 1 tháng → mức neo cho phân khúc chậm
3. Tối ưu (late_mean, on_time_prob) theo từng phân khúc để  KS-distance(sim, ref) nhỏ nhất,
   với ràng buộc  DSO_sim ∈ khoảng DSO của ngành (từ BCTC niêm yết)
4. Ghi tham số + nguồn + ngày vào  04_quy_tac_sinh_du_lieu.md  và  company_info
```
> Bộ Kaggle không phải bằng chứng "thật" tuyệt đối (xem `02`): chỉ dùng **hình dạng đuôi**, không dùng mức tuyệt đối.

### 3.3 Hiệu chỉnh cơ cấu chi phí & biên
- Từ BCTC công ty niêm yết cùng ngành: tỷ lệ chi phí bán hàng/doanh thu, quản lý/doanh thu, giá vốn/doanh thu, vòng quay tồn kho.
- Từ thống kê DNVVN: tỷ trọng lương/doanh thu cho SME thương mại, dịch vụ.
- Kết quả là **khoảng tham chiếu** (min–max); bộ sinh sample tham số trong khoảng đó cho từng công ty.

### 3.4 Kiểm tra độ tương đồng (fidelity) — phải làm trước khi tin dữ liệu
| Kiểm tra | Cách đo | Ngưỡng đề xuất |
|---|---|---|
| Phân phối độ trễ | KS / Wasserstein so tham chiếu | KS < 0,15 |
| Luật Benford trên số tiền hóa đơn/chi | χ² hoặc MAD | MAD < 0,015 |
| Mùa vụ | Hệ số tự tương quan 12 tháng | tương quan > 0,6 với chuẩn ngành |
| Cơ cấu chi phí | So với khoảng tham chiếu | 100% trong khoảng |
| Quan hệ DSO–tuổi nợ | Nhất quán nội bộ | sai số < 3% |
| Phát hiện bởi bộ phân loại (real vs fake) | AUC phân loại | AUC < 0,75 (càng thấp càng tốt) |

### 3.5 Pilot trên dữ liệu thật ẩn danh (bắt buộc trước go‑live)
1. Xin 1–2 DN xuất sổ cái + công nợ (CSV) dưới thỏa thuận bảo mật; **ẩn danh**: băm mã đối tác, giữ cấu trúc.
2. Viết bộ **ánh xạ** `account_code`/loại chứng từ thực tế → schema `gl_entry` (một lần/DN).
3. Chạy toàn bộ bộ chỉ số, đối chiếu với báo cáo kế toán đã chốt (kỳ đã khóa): sai lệch phải giải thích được.
4. Ghi *danh sách giả định bị vi phạm* (ví dụ: không có `bank_txn_date`, hạch toán lô nặng, TK chi tiết khác) → cập nhật bộ sinh.

## 4. Chiến lược cho từng loại đánh giá
| Mục tiêu đánh giá | Dữ liệu | Lý do |
|---|---|---|
| Đúng/sai tuyệt đối của số | Tổng hợp + SQL độc lập | Biết đáp án chính xác |
| Tổng quát hóa sang DN khác | **Nhiều công ty tổng hợp** (khác seed, ngành, quy mô) | Tránh quá khớp một công ty |
| Chịu nhiễu thực địa | Tổng hợp + chèn nhiễu (lô, trùng, sai chính tả) | Kiểm soát được mức nhiễu |
| Hiệu năng ở quy mô | Tổng hợp 10⁶–10⁷ dòng (+ Checkbook NYC cho AP) | Không cần dữ liệu thật |
| Độ "thật" | Pilot ẩn danh | Duy nhất trả lời được "chạy trên DN thật được không" |
