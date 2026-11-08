# 6. T6 — Mô phỏng số dư 13 tuần, sốc chung và hiệu chỉnh khoảng

> **Phạm vi sau gộp 06/11/2026:** T6 copula/ACI gốc, E2E dùng nhãn T9, copula hai nhân tố và unified v2 là những phép thử riêng. Không tráo điểm/coverage giữa chúng. Các đầu vào `src/tgt` cũ đã xóa; lệnh tái lập cần đúng dữ liệu và phiên bản mã.

Mã: `agent1/models/t6_cash.py` (`simulate`, `collection_kernel`, `ACI`); thí nghiệm: `scripts/run_t6.py`. **Số đo trong bản đặc tả ban đầu, khác giao thức E2E sau đó** (03_Evaluation/04 §4.9c): ACI cov80 0,794 (tuần 1–4) / 0,806 (5–13), IS80 tốt nhất tuần 1–4; Brier P(thiếu hụt) 0,014/0,033; lead time và báo giả chưa tính; demo T10 còn lỗi.

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


<a id="copula-hierarchy"></a>

## 6.7 Copula hai nhân tố — giao thức bổ sung

Gộp giao thức từ tài liệu ablation bổ sung ngày 06/11/2026. Đây là mô tả
của các lần chạy đã lưu, không phải lần đo mới hoặc yêu cầu chạy hiện nay.

`scripts/run_copula_hierarchy.py` chọn rho danh mục trong {0,.15,.3} và rho
khách trong {0,.1,.25} bằng IS80 nguồn. Mô hình nguồn chốt nhãn cuối 2022;
hiệu chỉnh bốn DN×13 tuần đầu 2023, kết quả chân trời cuối trong tháng 6/2023,
cách test 2024-07 hơn 120 ngày. Chọn riêng một nhân tố và lưới chung; mốc
rho=.15 vẫn chạy. df=4, 512 đường, lịch thu lý tưởng, doanh thu phân vị lịch
sử, khoảng thô không ACI. Không suy ra chất lượng E2E T9 từ phép đo này.

Tuần không có AR vẫn có số dư, doanh thu mới, chi và rút vốn nên phải chấm.
`scripts/complete_copula_cohort.py` sửa lượt v1 bằng cùng mô hình đã đóng
băng và seed tuần: giữ dự báo có AR, đối chiếu replay, bổ sung đúng 14 tuần
rỗng. Hiệu chỉnh nguồn v1 đã đủ mọi tuần; không chọn lại tham số từ đích.
Mã chỉ chấp nhận đúng phiên bản/hash đã biết, kiểm input/model và cohort
14×52×3×13. Protocol giữ hash/provenance cả lượt gốc và phần bổ sung.
Lệnh bổ sung chỉ áp dụng cho v1 đúng hash đã lưu; chạy lại cần khôi phục đúng dữ liệu nguồn và phiên bản mã, không suy ra đầu vào hiện vẫn còn.


<a id="cash-baselines"></a>

## 6.8 Đối chứng ETS, ARIMA, B0 và Chronos Tiny

`scripts/run_cash_baselines.py` chạy ETS, ARIMA và bảng tính đến hạn trên cùng
14 công ty × 52 cutoff với E2E dùng nhãn T9 ước lượng. Script kiểm tra số dư thật,
cohort và mẫu số chuẩn hoá khớp từng tuần trước khi ghép bảng.

- ETS: xu thế cộng có damping, không mùa vụ; bootstrap phần dư fit để mô phỏng 1.000 đường dòng ròng.
- ARIMA: cố định (1,0,1), có hằng số; mô phỏng đường có điều kiện từ trạng thái cuối lịch sử.
- Cả hai chỉ nhận 52 tuần dòng ròng tới cutoff. Fit không hội tụ hoặc đường không hữu hạn dùng mốc dự phòng
  đã khai báo: trung bình lịch sử cộng phần dư bootstrap iid. Số lần dự phòng và cảnh báo ghi trong
  `outputs/t6/traditional/fit_diagnostics.csv`; đây không phải kết quả của một ARIMA/ETS thuần nếu có dự phòng.
- B0: hoá đơn mở theo nhãn quan sát, thu đúng hạn (nợ quá hạn ở tuần 1), lịch chi ước lượng đã biết,
  doanh thu mới bằng trung bình lịch sử qua kernel thu tiền. Dự báo điểm có P10=P50=P90;
  chưa thêm capex không dự kiến và rút vốn chủ DN.

`scripts/run_chronos_baseline.py` chạy **Chronos-Bolt Tiny zero-shot** trên 52 số dư cuối tuần
đã quan sát, không fine-tune và không nhận nghĩa vụ chi tương lai. Revision cố định:
`a0e552de83495b5c28c14c71c374f3e33280b340`. Chạy CPU, float32, batch 32;
trọng số safetensors, hash checkpoint và phiên bản thư viện lưu trong metadata.
API và giấy phép được đối chiếu tại [model card của Amazon](https://huggingface.co/amazon/chronos-bolt-tiny).
Kết quả chỉ áp dụng cho bản Tiny và giao thức đầu vào này.

```powershell
.\.venv\Scripts\python.exe scripts/run_cash_baselines.py
# Cần phụ thuộc tuỳ chọn trong requirements-forecast.txt và tải checkpoint công khai lần đầu.
.\.venv\Scripts\python.exe scripts/run_chronos_baseline.py
.\.venv\Scripts\python.exe scripts/compare_cash_baselines.py
.\.venv\Scripts\python.exe scripts/make_report.py
```

So sánh cặp từ dự báo đã lưu nằm ở `outputs/t6/additional_baseline_comparisons.csv`.
Chiều cải thiện: dương nghĩa là E2E ACI tốt hơn đối chứng; CI bootstrap theo công ty, 300 lượt.
Không chọn lại tham số hoặc mô hình theo bảng test. G12 giữ tiêu chí bốn đối chứng gốc;
đạt G12 không đồng nghĩa thắng mọi đối chứng bổ sung. Mọi điểm và CI trong báo cáo được sinh từ CSV.
