# T8 — Lời Hứa Trả: Tóm Tắt Executive
---


## Vấn đề


**Hiện tại:** ERP chỉ biết `due_date`, không biết khách có **hứa** trả ngày nào và **có giữ lời** không.


**Thực tế VN:**
- 80% lời hứa qua Zalo/phone/gặp mặt → không ai track
- Khách A luôn giữ lời, khách B hay phá lời → nhưng hệ thống không phân biệt được
- Kế toán chỉ nhớ bằng đầu, mất context khi nhân viên mới vào


---


## Thuật toán gốc
**Beta-Binomial Bayesian Update:**
```
Reliability = số lần giữ lời / tổng số lần hứa
Update: Beta(α + kept, β + broken)
```


**Ví dụ:**
- Khách A: 5 lần hứa, 5 lần giữ → reliability = 100%
- Khách B: 5 lần hứa, 1 lần giữ → reliability = 20%
- → Dự báo: A trả đúng hạn, B cần thêm 2 tuần buffer


---


## Multi-Dimensional Score


Thay vì 1 con số, track **5 chiều:**


- **Tỷ lệ giữ lời (fulfillment_rate):** Đúng Beta-Binomial ở trên. Khách giữ lời bao nhiêu %?
- **Mức trễ khi phá lời (avg_delay_when_broken):** Không phải ai cũng như nhau. Khách X phá lời nhưng chỉ trễ 2 ngày; khách Y phá lời trễ 30 ngày. Cả hai đều reliability 50%, nhưng Y nguy hiểm hơn cho dòng tiền tuần.
  ```
  delay_score = max(0, 1 - avg_delay / 30)
  ```
- **Nhạy cảm với số tiền (amount_sensitivity):** Khách có phân biệt hóa đơn lớn/không? VD: khách nhỏ hứa 10tr trả, hứa 200tr không trả → ratio cao với HĐ nhỏ, ratio thấp với HĐ lớn. Nếu chỉ tính trung bình 1 reliability sẽ overestimate cho HĐ lớn → cần tách: `reliability(HĐ nhỏ)` vs `reliability(HĐ lớn)`.
- **Xu hướng gần đây (recency_score):** Lời hứa 2 năm trước weight thấp hơn tuần trước. VD: Khách A: 2 năm trước 10/10 giữ, tháng này 0/3 phá hết → đang xấu đi. Chỉ nhìn tổng 10/13 = 77% sẽ bỏ sót tín hiệu xấu. → Dùng exponential decay: `weight = 0.5^(days/half_life)`, half-life 180 ngày.
- **Độ ổn định / biến động (promise_volatility):** Thất thường hay nhất quán? Khách G: giữ, giữ, giữ, giữ, giữ → ổn định. Khách H: giữ, phá, giữ, phá, giữ → 50%, thất thường. Cùng 1 trung bình nhưng dự báo hoàn toàn khác nhau: G bạn yên tâm, H không thể dự đoán → uncertainty cao → T6 cần widen khoảng.




---


## Schema (thêm vào T0)


```
raw_promises      → Zalo msg, phone notes, email (Bronze)
    ↓
promises          → Normalized: ngày hứa, số tiền, channel (Silver)
promise_outcomes  → Kết quả: giữ/phá, trễ mấy ngày (Silver)
    ↓
trust_scores      → Beta-Binomial + 5 chiều (Silver)
    ↓
fct_customer_trust → Gold, feed vào T1/T6/T10
```


---


## Tích hợp pipeline


| Module | Nhận gì từ T8 | Làm gì |
|--------|---------------|--------|
| **T1** | `reliability` score | Feature cho LightGBM → dự báo chính xác hơn |
| **T2** | Trust giảm đột ngột | Early warning nợ xấu |
| **T6** | Uncertainty interval | Khách không tin cậy → widen P10-P90 |
| **T10** | Promise history | Giải thích: "Tuần này thiếu vì Cty B phá lời lần 3" |


---


## Cách thu thập lời hứa (Promise Collection)


### Nguyên tắc thiết kế
**Ghi lời hứa phải nằm ngay trong lúc đòi nợ** — không mở màn hình khác, không quay lại form riêng.


### 3 mức độ tự động hóa


#### **P0 — Bắt buộc ghi (không tự động được)**
Lời hứa miệng/gặp mặt/Zalo voice → kế toán **phải ghi tay**. Giảm friction:


- **Form 5 giây trên AR aging:**
  ```
  ┌─────────────────────────────────────┐
  │ Cty A — INV-123 (250,000,000đ)      │
  │                                     │
  │ Hứa trả ngày: [__/__/____] [ +7d ] │
  │ Channel:       [Zalo] [Phone]  │
  │ Mức độ:        [Chắc] [BT] []│
  │                                     │
  │ [Lưu]                               │
  └─────────────────────────────────────┘
  ```


- **Hotkey trong lúc gọi:** đang ở customer screen → bấm phím tắt → popup ghi ngay


- **Bắt buộc log outcome trước khi đóng task:** như CRM bắt ghi call note (không ghi → không đóng được)


#### **P1 — Tự động detect outcomes **
Kết quả của lời hứa tự phát hiện, không cần ai nhập:


| Trigger | Action |
|---|---|
| **T9 reconciliation** thấy tiền về | → Match với promise đang mở → ghi `kept/broken` + `days_late` |
| **ERP due_date slip** (khách dời hạn) | → Cũng là 1 dạng promise → tạo promise record |
| **Bank statement import** | → Parse "trả HĐ INV-123" → match promise |


#### **P2 — Bán tự động (NLP extract)**
- **Zalo bot:** Kế toán gửi nhắc nợ qua bot → khách reply "tuần sau trả" → parse text ra ngày → draft promise → kế toán xác nhận
- **Email template:** Khách reply có ngày → extract (regex/LLM) → draft promise


### Vị trí đặt capture trong workflow


```
Tuần việc kế toán (với T8):
  [1] Mở AR aging → lọc overdue
  [2] Gọi khách → khách hứa "đầu tháng 10"
  [3] ✓ Bấm "＋ Lời hứa" ngay trên dòng invoice → lưu
        ↓
  [4] Tự động: T9 thấy tiền về → update outcome → update reliability
```


### Ưu tiên triển khai


| Phase | Cách | Lý do |
|---|---|---|
| **P0** | Form ghi tay gắn trên AR aging | Đủ data chạy Beta-Binomial ngay |
| **P1** | Auto-outcome từ T9 reconciliation | Không tốn công ghi kết quả |
| **P2** | Zalo/email parse → draft | Giảm friction, cần NLP |




**Với AR Aging Dashboard:**
- Mỗi dòng invoice overdue → button `＋ Ghi lời hứa`
- Sidebar: lịch sử lời hứa của khách này (5 lần gần nhất)


---


**TL;DR:** Ghi tay 5 giây/ngày + auto-detect từ reconciliation = đủ data chạy Beta-Binomial.


## Đánh giá thành công


| Metric | Target | Ý nghĩa |
|--------|--------|---------|
| **Promise capture rate** | >70% | Có ghi nhận đủ lời hứa không? |
| **Auto-detection rate** | >80% | Tự động detect kết quả qua T9 |
| **MAPE giảm** | -15% | Dự báo T1 chính xác hơn bao nhiêu |
| **Avg days to collect** | -10 ngày | Thu được nợ nhanh hơn |


---


## Quick Start


**1. Capture lời hứa:**
```
Khách: Cty A
HĐ: INV-123
Hứa trả: 15/03
Channel: Zalo
Mức độ: Chắc chắn
→ [Lưu]
```


**2. Hệ thống tự động:**
- T9 detect tiền về ngày 15/03 → ghi "giữ lời"
- Update Beta(α+1, β) → reliability tăng
- T1 dùng reliability cao → dự báo chính xác


**3. Dashboard:**
```
Cty A: ⭐⭐⭐⭐⭐ 100% (5/5) — Gold tier
Cty B: ⭐⭐ 40% (2/5) — Risk tier
Cty C: 🆕 New (dùng sector prior 60%)
```


---


## ROI ước tính


| Lợi ích | Giá trị |
|---------|---------|
| Dự báo chính xác hơn | MAPE giảm 15% → better cash planning |
| Đòi nợ hiệu quả | Ưu tiên khách reliability thấp → thu nhanh 10 ngày |
| Giảm bad debt | Early warning → can thiệp sớm → giảm 5% write-off |
| Context cho team | Nhân viên mới biết ngay lịch sử interactions |


---


## Sources chính


- [QJE Vietnam research](https://chriswoodruff.qeh.ox.ac.uk/wp-content/uploads/2019/10/VN_QJE.pdf) — trust-based credit VN
- [Bill Gosling AI PTP](https://www.billgosling.com/blog/how-ai-insights-optimizes-promise-to-pay-recovery-rates/) — industry practice
- [Beta-Binomial guide](https://metricgate.com/docs/beta-binomial-conjugate-updating/) — Bayesian method
- [Springer 2025](https://link.springer.com/article/10.1186/s40537-025-01252-0) — smart debt collection


---



