# T3 — Phân bổ thanh toán, trả một phần và tranh chấp

## 1. Payment allocation mechanics


### Partial payment
```
allocations.allocated_amount < total
→ invoice.status = partially_paid
→ balance = total - SUM(allocated)
```
**VD:** HĐ 100tr, khách chuyển 30tr  
→ Hệ thống "đắp" 30tr vào HĐ (allocated)  
→ Status = partially_paid, balance = 70tr


### Overpayment
```
payment_amount > invoice_amount
→ unallocated_amount trong payments / credit_memo
```
Xử lý: hoàn trả hoặc cấn trừ HĐ sau.


### Tạm ứng (Advance payment)
```
payments: invoice_id = NULL, type = 'advance'
```
Khi HĐ phát sinh → tạo `allocation` nối advance payment → invoice.


### Batch payment — 1 CK trả nhiều HĐ (Phân tầng tối ưu)


```
1 bank_transaction → N payment_allocations


```


**Thuật toán matching:**


1. **Rule-based & Exact match (Tầng 1 - xử lý 80%):** Quét mã HĐ bằng Regex. Nếu khớp mã và đúng số tiền → gạch nợ ngay. **Heuristic & Combinatorics (Tầng 2 - xử lý 15%):**
* Fuzzy text (Levenshtein -> k/c biến chuỗi này thành chuỗi khác) cho các mã HĐ gõ sai. -> chấp nhận 1 ngưỡng nếu gõ sai
* Filter theo customer + date window.
* Chạy Subset Sum (Quy hoạch động) tìm tổ hợp HĐ có tổng = amount ± tolerance. -> nếu có >= 2 hợp lệ thì fallback


3. **AI Fallback & Optimization (Tầng 3 - xử lý 5% khó nhất):**
* LLM Extractor: Dùng LLM nhẹ bóc tách nội dung mập mờ thành chuỗi JSON sạch.
* LightGBM Scoring: Tính điểm xác suất khớp cho từng cặp Giao dịch → Hóa đơn.
* Greedy Match: Xếp hạng cặp theo điểm số. Khớp và trừ lùi tiền từ cao xuống thấp. Dừng khi hết tiền hoặc khi điểm số rớt xuống dưới ngưỡng an toàn (vd: < 85%).
Human-in-the-loop: Đẩy ra giao diện Kế toán duyệt tay nếu điểm khớp quá thấp. Dữ liệu Kế toán chọn sẽ được lưu làm nhãn (label) để retrain LightGBM.




* Fallback cuối cùng: Bắn ra giao diện Kế toán duyệt tay nếu độ tự tin thấp, lấy kết quả retrain mô hình.




### Phí ngân hàng & tỷ giá
```
|received - invoice_amount| ≤ tolerance → coi như paid đủ
```
**Tolerance adaptive (không hardcode):**
- Học từ lịch sử per customer: `tolerance = f(customer_size, avg_bank_fee)`
- VD: khách lớn ±200k, khách nhỏ ±20k, retailer ±0 (luôn exact)
- Chênh lệch → tách vào `bank_fee` riêng


**Tỷ giá VND/USD:**
```
invoice USD → payment VND
→ tách phần chênh lệch: fx_gain_loss (không vào bank_fee)
```


### Nhiều giao dịch → 1 bút toán (reverse aggregation)
```
N bank_txn → 1 journal_entry
VD: N giao dịch lương nhỏ → 1 bút toán "Trả lương tháng 9"
```
Thuật toán: min-cost flow reverse (1 sink, N sources) — giống batch payment nhưng ngược hướng.


## 2. Deduction & tranh chấp 


### Quy mô
- Global chargeback 2026: ~337M giao dịch; mỗi $1 fraud tốn $5.13 all-in (phí + overhead).




### Phân loại tranh chấp (taxonomy thực tế)


| Loại | Ví dụ | Xử lý |
|------|-------|-------|
| Pricing | Sai đơn giá, thiếu chiết khấu | Credit memo / HĐ điều chỉnh |
| Shortage | Thiếu hàng so với HĐ (Home Depot auto-deduct) | Giao bù hoặc chấp nhận |
| Quality | Hàng lỗi, sai spec | Return / credit memo |
| Compliance | Sai packaging, labeling (Walmart) | Chargeback tự động |
| Allowance / Rebate | Markdown, trade promotion | Credit memo theo HĐ |
| Noise (nhiễu) | Viện cớ để kéo dài | Dispute + escalation |


-> credit memo là biên bản giảm trừ công nợ cho buyer


### Workflow xử lý
```
Short pay detected → Classify reason → Quyết định: dispute hay accept
  ├─ dispute → Investigation → Valid: reverse deduction / Invalid: write-off
  └─ accept  → Issue credit memo → Update balance → Reconcile allocations
```
## 3. HĐ tách thành HĐ con (1 HĐ → nhiều HĐ)


**Khi nào:** 1 HĐ nhiều dòng hàng, tranh chấp chỉ 1 phần; hoặc hợp đồng milestone.


**Schema:**
```
invoices: parent_invoice_id (NULL nếu là gốc), split_reason (dispute_partial / milestone)
```


## 4. Thuật toán — stack hiện đại


### 4a. Hồi quy tỷ lệ trả (payment ratio regression)


**Bài toán:** Dự báo `ratio ∈ (0, 1]` — HĐ sẽ thu được bao nhiêu %.


**Features:**
```
Customer: avg_ratio, dispute_rate, days_late, industry, credit_limit
Invoice:  amount, age, line_items[], has_contract, payment_terms
Macro:    month_end_flag, holiday_proximity, shock_signal (từ T7)
Text:     dispute_notes, email_thread -> LLM embedding
```


**Eval:** MAE, MAPE, calibration curve.




### 4b. Phân loại tranh chấp (dispute classification)


**Bài toán:** Multi-label classification — 1 HĐ có thể có nhiều lý do tranh chấp.


**Labels:** `pricing`, `shortage`, `quality`, `compliance`, `allowance`, `noise`


**1. Tầng lọc 1 (Standard OCR + Rule-based)**


* **Xử lý luồng chính (80% volume):** Áp dụng cho các đối tác bán lẻ khổng lồ (như Walmart, Target) luôn gửi chứng từ theo biểu mẫu cố định. Sử dụng OCR truyền thống + Regex để trích xuất với chi phí gần như bằng 0.
* **Fallback:** Chỉ kích hoạt Vision-LLM đắt đỏ khi gặp các email diễn giải lộn xộn hoặc PDF phi cấu trúc.


**2. Thay thế GNN bằng Search Engine**


* **Cơ chế:** Khi Agent 1 bóc tách được mã tham chiếu (`ref_codes`, ví dụ: PO#12345), không dùng mạng đồ thị (GNN) để truy vết. Thay vào đó, gọi trực tiếp từ cơ sở dữ liệu quan hệ (SQL) hoặc dùng Elasticsearch (BM25) / Vector Search.
* **Lợi ích:** Tốc độ phản hồi tính bằng mili-giây, giảm hàng trăm lần chi phí vận hành và bảo trì hạ tầng mà vẫn giữ nguyên độ chính xác.


**3. Phân cấp sức mạnh LLM (Tiered LLM Strategy)**


* **Agent 1 (Data Extractor):** Chỉ giao nhiệm vụ đọc và bóc tách dữ liệu thô cho các LLM nhỏ, tốc độ cao và giá rẻ
* **Agent 3 (Reasoning Judge):** Dồn ngân sách cho các LLM lớn, có tư duy suy luận sâu để thực hiện các tác vụ phức tạp: lập luận logic, phân loại lý do tranh chấp và trích dẫn bằng chứng (evidence chain).




**Metrics:** F1-macro, cost/claim (target <$2), time-to-resolution (target <3 days), auto-resolve rate (target >80%).


**Production impact (2026 real-world):**
- Cost: $6 → $2 per claim (touchless resolution)
- Volume: 3× without adding headcount
- Recovery: +30% net recovery rate
- Aggregation: 90% backup docs auto-matched


### 4c. Tích hợp vào T6 (Monte Carlo)


```
T1: day_paid       ~ survival model        (khi nào)
T2: P(default)     ~ binary classifier     (có trả không)
T3: ratio          ~ ratio model           (trả bao nhiêu)
              ↓
T6: amount = invoice_amount × ratio × (1 - I_default) × I_{day ≤ horizon}
    → P10 / P50 / P90 cash position
```






**Explainability:**
- SHAP values → "ratio thấp vì: dispute_rate cao, days_late trung bình 15d"
- Evidence chain → "Shortage dispute: PO#123 yêu cầu 100 thùng, shipment#456 chỉ 95 thùng"

