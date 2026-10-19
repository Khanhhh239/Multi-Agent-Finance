# Tóm Tắt Dự Án: Chuẩn Bị — Đã Làm — Ý Tưởng Hiện Tại

> **Ảnh chụp trạng thái lịch sử:** giữ nội dung tại thời điểm viết; không cập nhật như bảng tiến độ hiện hành. Xem [project overview](../project-overview.md) cho trạng thái checkout và [tổng kết ngày 24/09/2026](../reports/agent1-implementation-review.md) cho kết quả được báo cáo trước đây.

> Đường dẫn `notebooks/` bên dưới là tên tại thời điểm chụp trạng thái; bộ này hiện đã chuyển sang [reference_notebooks/](../../reference_notebooks/README.md), chỉ dùng tham khảo.

---

## 1. NHỮNG GÌ CHUẨN BỊ LÀM

### Nền tảng & Kiến trúc

| Task | Phạm vi | Tình trạng |
|------|--------|-----------|
| **T0** — Nền dữ liệu Medallion | Bronze (raw ERP/Bank/CSV) → Silver (SCD2, event-sourced, reconciliation) → Gold (star schema) | ✅ **Đã thiết kế** (t0_data_foundation_reconciliation.md) |
| **CHUNG-1** — ERD & schema | `customers 1-N invoices 1-N invoice_lines`, `payments`, `payment_allocations`, `bank_transactions`, `fixed_obligations` | ✅ **Đã thiết kế** |
| **CHUNG-2** — Reconciliation engine | 3 tầng: Exact match (80%) → Fuzzy + Subset Sum (15%) → LLM/LightGBM + Human review (5%) | ✅ **Đã thiết kế** (t3_payment_allocation_disputes.md) |
| **CHUNG-3** — Anti-leakage snapshot | As-of cutoff, tránh data leakage khi train model T1–T11 | ✅ **Đã thiết kế** |

### Mô hình dự báo

| Task | Input | Output | Thuật toán chính | Tình trạng |
|------|-------|--------|------------------|-----------|
| **T1** — Khi nào | Lịch sử invoice + customer + macro | P(day_paid) quantile 0.1/0.5/0.9 | LightGBM quantile + CQR + survival classifier | ✅ **Đã code & bảo vệ** (invoice_payment_cash_in_report.tex) |
| **T2** — Có trả không | Invoice + customer + aging | P(default) tại tháng 1/3/6/12 | Discrete-time hazard + calibration + conformal prediction | 🟡 **Thiết kế xong** (t2_default_risk.md §3.1–3.4) |
| **T3** — Trả bao nhiêu + tranh chấp | Invoice + payment history + dispute notes | Ratio ∈(0,1], multi-label tranh chấp | Regression + multi-label classification + tiered LLM | 🟡 **Thiết kế xong** (t3_payment_allocation_disputes.md §4a–4b) |
| **T5** — Chi cố định | HR data + pháp luật | Lịch chi lương/thuế/BHXH 13 tuần | Rule engine tất định + lịch nghỉ lễ API | 🟡 **Thiết kế xong** (t5_fixed_outflows_obligations.md) |
| **T8** — Lời hứa trả | Raw promises (Zalo/phone/email) | Reliability score (5 chiều) | Beta-Binomial Bayesian update + recency weighting | 🟡 **Thiết kế xong** (t8_promise_to_pay.md) |

### Tích hợp & Giải thích

| Task | Input | Output | Thuật toán chính | Tình trạng |
|------|-------|--------|------------------|-----------|
| **T6** — Monte Carlo | T1/T2/T3/T5 outputs | Cash position P10/P50/P90 theo tuần + xác suất thiếu hụt | 3-tier Gaussian copula (customer ρ=0.25, portfolio ρ=0.75) + bootstrap | ✅ **Đã code** (invoice_payment_cash_in_report.tex §3.4) |
| **T7** — Điểm gãy & chế độ khủng hoảng | Time series cash/PD/ratio | Regime signal: CUSUM/BOCPD/self-implemented binary segmentation | Change-point detection | 🟡 **Thiết kế xong** (t5_fixed_outflows_obligations.md) |
| **T10** — Giải thích & hành động | T6/T11 outputs + SHAP values | Dashboard, reason code, rank khách hàng đòi | SHAP TreeExplainer + reason chain | 🟡 **Thiết kế xong** |

---

## 2. NHỮNG GÌ ĐÃ LÀM

### Các file & code sản phẩm tồn tại

| Vị trí | Tên file | Nội dung | Dòng | Trạng thái |
|--------|----------|---------|------|-----------|
| `notebooks/01_*.ipynb` — `10_*.ipynb` | Toàn bộ notebooks T0–T6 | Các pipeline ELT, model training, evaluation | 10 notebooks, tổng 178 cell | ✅ Chạy thành công, outputs lưu |
| `notebooks/11_extended_window_retraining.py` | OOF training survival-boost | Chia theo cutoff, không theo row; xây dựng feature out-of-fold | ~300 dòng | ✅ Code xong, định dạng `.py` để git diff |
| `notebooks/12_oof_survival_boost.py` | Survival-Boost ensemble | Kết hợp T1 LightGBM với hazard model | ~200 dòng | ✅ Code xong |
| `docs/reports/agent1-implementation-review.md` | Tổng hợp thiết kế & bảo vệ | Lịch sử pipeline, 11 tầng, 9 điểm mạnh, bảng trạng thái Đ1–Đ19, hồ sơ nộp vòng 1 | 518 dòng | ✅ Gộp 4 file gốc, xóa duplicates & outdated |
| `research/notes/t0_data_foundation_reconciliation.md` | Architecture dữ liệu | Medallion, SCD2, reconciliation, ERD | 93 dòng | ✅ Đọc & confirm |
| `research/notes/t2_default_risk.md` | Phương pháp PD & IFRS 9 | Discrete-time hazard, transfer learning, calibration, conformal prediction | 437 dòng | ✅ Đọc & confirm |
| `research/notes/t3_payment_allocation_disputes.md` | Partial payment & dispute | Tầng matching (rule/fuzzy/AI), payment ratio, multi-label | 216 dòng | ✅ Đọc & confirm |
| `research/notes/t5_fixed_outflows_obligations.md` | Lịch nghĩa vụ cố định | Rule engine (không ML), VAT/TNCN/TNDN/BHXH, kỳ hạn, dịch ngày Tết | 280 dòng | ✅ Đọc & confirm |
| `research/notes/t8_promise_to_pay.md` | Lời hứa trả (PTP) | Beta-Binomial + 5 chiều (reliability, delay, amount_sensitivity, recency, volatility) | 248 dòng | ✅ Đọc & confirm |

---

## 3. Ý TƯỞNG HIỆN TẠI

### Chiến lược ưu tiên từng task

#### **Giai đoạn 1: Hoàn chỉnh nền tảng & consolidation (Tuần 1)**

| Task | Việc cần làm | Output | Ưu tiên |
|------|------------|--------|--------|
| **T0** | Xây dựng dbt models + GX tests; test Medallion pipeline trên dữ liệu thật (nếu có) | `dbt run` + `gx cloud init` | 🔴 CRITICAL — gate cho mọi task sau |
| **CHUNG-2** | Code reconciliation engine (3 tầng) | Python module `reconciliation.py` | 🔴 CRITICAL |
| **Tạo T0 snapshot export** | Sinh AS-OF cutoff bảng fct_invoices + fct_bank_txns + fixed_obligations | Pickle / Parquet | 🔴 CRITICAL |

#### **Giai đoạn 2: Thực hiện mô hình T1–T5 (Tuần 2-4)**

| Task | Việc cần làm | Output | Ưu tiên |
|------|------------|--------|--------|
| **T2** | Code discrete-time hazard (person-period expand) + Platt calibration + PSI monitoring | `02_hazard_model.py` | 🟠 HIGH — IFRS 9 compliance |
| **T3** | Code ratio regression (LightGBM) + multi-label dispute classifier (tiered LLM) | `03_ratio_dispute.py` | 🟠 HIGH — P(cash in) |
| **T5** | Code rule engine (QuickRules / GoRules ZEN) + holiday calendar API + date-shift logic | `05_schedule_obligations.py` | 🟠 HIGH — P(cash out) cố định |
| **T8** | Code Beta-Binomial updater + promise capture UI (embed vào AR aging dashboard) | `08_promise_tracking.py` | 🟡 MEDIUM — feature cho T1, T6 |

#### **Giai đoạn 3: Tích hợp & giải thích (Tuần 5)**

| Task | Việc cần làm | Output | Ưu tiên |
|------|------------|--------|--------|
| **T6 refinement** | Nhúng T2/T3/T5/T8 output vào copula; test tail behavior; widen P10/P90 khi concept drift | `06_monte_carlo_refined.py` | 🔴 CRITICAL — là cash forecast |
| **T7** | Code CUSUM/Page-Hinkley; auto-detect regime changes; feed chế độ vào T6 | `07_changepoint.py` | 🟡 MEDIUM — monitoring |
| **T11 gate enforcement** | Kiểm tra 4 rule (R1–R4) backtest; block T10 nếu NO-GO | `11_backtest_gate.py` | 🟠 HIGH — chặn bad model |

#### **Giai đoạn 4: Sản phẩm & bảo vệ (Tuần 6)**

| Task | Việc cần làm | Output | Ưu tiên |
|------|------------|--------|--------|
| **T10 dashboard** | SHAP explainer + reason code + action ranking (đòi khoản nào trước) | Streamlit/Plotly UI | 🟠 HIGH — end-user |
| **Hồ sơ bảo vệ vòng 2** | Cập nhật design doc, số liệu thực chạy T1–T11, giải thích 5 quyết định CONDITIONAL | Markdown + PDF | 🔴 CRITICAL |
| **A/B test ngoài thực tế** | Deploy T1–T6 vào 1 doanh nghiệp thực; so sánh với cách cũ (aging report); đo MAPE improvement | 📊 Real-world signal | 🟡 OPTIONAL (nếu có client) |

---

### Khoảng trống & risks cần xử lý

| Vấn đề | Rủi ro | Giải pháp |
|-------|--------|----------|
| **T0: Dữ liệu thiếu** | Không có API ERP/Bank thật → không thể lấy raw data | |
| **T2: Sample imbalance** | Default rate <5% → mô hình có thể bias | `is_unbalance=True` LightGBM + SMOTE + cost-sensitive learning + transfer learning từ SBA |
| **T3: Tranh chấp dữ liệu** | Không có labeled dispute history → multi-label classifier không có ground truth | Seed từ Home Credit tranh chấp taxonomy; crowdsource labeling từ SME |
| **T5: Thay đổi luật** | Thông tư thuế cập nhật hàng năm → rule engine lỗi thời | Build versioned rule store; monthly auto-check các thông tư liên quan + alert |
| **T8: Lời hứa rải rác** | Lời hứa chỉ lưu trong Zalo/phone → thiếu label để train → Beta-Binomial chỉ có 100–500 record | Retroactive capture: đặt form capture UI lên AR aging; yêu cầu kế toán back-fill 3 tháng gần nhất |
| **Concept drift** | Thị trường VN biến động; customer behavior thay đổi → mô hình cũ mất giá | PSI monitoring hàng tuần; retrain auto nếu PSI >0.1; maintain model pool M1…Mn |

---

### Timeline tổng thể & Milestones

```
Backlog (ngoài 13 tuần):
  - T4 (revenue forecast) — dùng Chronos/M5 benchmark (nếu có)
  - T9 (optional: auto bank statement match)
  - T12/T13 (synthetic data gen + real-world A/B test)
```

---

