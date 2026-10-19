# CASH FORECAST — Pipeline & Architecture 

> **Thiết kế mục tiêu.** Phạm vi đã có mã và khả năng chạy hiện tại được ghi tại [project overview](../project-overview.md).

> **Phạm vi:** tài liệu này vẽ lại **toàn bộ pipeline và kiến trúc của phần dự báo dòng tiền (cash forecast)** 
>
> **Quy ước màu vẽ trong mọi sơ đồ:**
> - 🟦 **CHUNG** — hạ tầng dùng chung cho mọi phân hệ, vẽ ở mức độ "tầng"
> - 🟧 **Riêng của Cash Forecast** — pipeline/model/logic riêng cho phần này, vẽ chi tiết tới bước.
> - ⬜ **Đầu vào** · ⬛ **Đầu ra** · 🟨 **Con người / Approval gate**
>

---

## MỤC LỤC

- [A. Nguyên tắc phân tách CHUNG / RIÊNG](#a)
- [B. SƠ ĐỒ TOÀN CẢNH — Cash Forecast trên 5 tầng](#b)
- [C. PHẦN CHUNG — hạ tầng](#c)
  - [C.1 CHUNG-1 — T0: Medallion pipeline (Bronze → Silver → Gold)](#c1)
  - [C.2 CHUNG-2 — Reconciliation engine](#c2)
  - [C.3 CHUNG-3 — Anti-leakage cutoff snapshot](#c3)
- [D. PHẦN RIÊNG CỦA CASH FORECAST](#d)
  - [D.1 RIÊNG-1 — T1: dự báo ngày trả từng hóa đơn](#d1)
  - [D.2 RIÊNG-2 — T2: khả năng trả / vỡ nợ (PD)](#d2)
  - [D.3 RIÊNG-3 — T3: tỷ lệ trả & tranh chấp](#d3)
  - [D.4 RIÊNG-4 — T5: chi cố định & lịch nghĩa vụ (cash out)](#d4)
  - [D.5 RIÊNG-5 — T8: lời hứa trả (PTP)](#d5)
  - [D.6 RIÊNG-6 — T6: lõi Monte Carlo cash forecast](#d6)
  - [D.7 RIÊNG-7 — T7: điểm gãy & chế độ khủng hoảng](#d7)
  - [D.8 RIÊNG-8 — T11 backtest gate → T10 giải thích & hành động](#d8)
- [E. TÍCH HỢP — Pipeline end-to-end của Cash Forecast](#e)

---

<a name="a"></a>
## A. Nguyên tắc phân tách CHUNG / RIÊNG

Quyết định "vẽ phần nào chung, phần nào riêng" theo đúng tiêu chí: **module nào phục vụ riêng cash forecast → vẽ RIÊNG; module nào ≥2 phân hệ cùng dùng → vẽ CHUNG.**

| Mã | Phần | Loại | Lý do chung/riêng | Nguồn |
|---|---|---|---|---|
| CHUNG-1 | T0 Medallion (Bronze/Silver/Gold) | 🟦 CHUNG | Cả T1–T10 đều đọc từ Gold | `t0_data_foundation_reconciliation.md` |
| CHUNG-2 | Reconciliation engine | 🟦 CHUNG | Cung cấp ngày trả thật (T1), nhãn PTP (T8), đối soát (N6) | `t0_data_foundation_reconciliation.md`, `t8_promise_to_pay.md` |
| CHUNG-3 | Anti-leakage cutoff snapshot | 🟦 CHUNG | Mọi model học theo as-of $T$ | `invoice_payment_cash_in_report.tex` §2.2 |
| RIÊNG-1 | T1 quantile + CQR + survival classifier | 🟧 RIÊNG | Đầu vào trực tiếp của T6 | `invoice_payment_cash_in_report.tex` §3 |
| RIÊNG-2 | T2 PD / discrete-time hazard | 🟧 RIÊNG | Tham số hoá đuôi T6 | `t2_default_risk.md` |
| RIÊNG-3 | T3 ratio regression + dispute | 🟧 RIÊNG | "Trả bao nhiêu" trước "bao giờ" | `t3_payment_allocation_disputes.md` |
| RIÊNG-4 | T5 rule engine nghĩa vụ | 🟧 RIÊNG | Cash **out** cố định cho T6 | `t5_fixed_outflows_obligations.md` |
| RIÊNG-5 | T8 Beta-Binomial PTP | 🟧 RIÊNG | Feature + override cho T1/T6 | `t8_promise_to_pay.md` |
| RIÊNG-6 | **T6 Monte Carlo copula (lõi)** | 🟧 RIÊNG | Chính là "cash forecast" | `invoice_payment_cash_in_report.tex` §3.4 |
| RIÊNG-7 | T7 change-point | 🟧 RIÊNG | Chế độ khủng hoảng cho T6 | `DIGITAL_ACCOUNTING` §3.2.W4 |
| RIÊNG-8 | T11 backtest gate → T10 giải thích | 🟧 RIÊNG | Chặn model NO-GO, rồi mới trình kết quả | `DIGITAL_ACCOUNTING` §2.1 |

---

<a name="b"></a>
## B. SƠ ĐỒ TOÀN CẢNH — Cash Forecast trên 5 tầng

```
══════════════════════════════════════════════════════════════════════════════
 L4 — GIAO DIỆN & QUYẾT ĐỊNH
══════════════════════════════════════════════════════════════════════════════
   ⬛ Dashboard dòng tiền 13 tuần · ⬛ Điều khiển rủi ro · 🟨 Approval gate
        ▲                                    ▲
        │                                    │
══════════════════════════════════════════════════════════════════════════════
 L3 — TỔNG HỢP & CẢNH BÁO  🟧 RIÊNG-6 (T6 MC) · 🟧 RIÊNG-8 (T11 → T10)
══════════════════════════════════════════════════════════════════════════════
   ┌──────────────────────────────────────────────────────────────────┐
   │  🟧 T6  MONTE CARLO COPULA — 10.000 kịch bản                    │
   │      U = ρ_m·M + ρ_c·C + √(1-ρ_c²-ρ_m²)·Z   (ρ_c,ρ_m)=(0.25;0.75)│
   │      tail risk-weighted 5% → P10/P50/P90 theo tuần              │
   │  ┌────────────────────────────────────────────────────────────┐  │
   │  │ 🟧 T11 GATE GO:  luật chấm R1 · R2 · R4 · Action · S      │  │
   │  │    ⚠ chạy TRƯỚC T10 — NO-GO = user không thấy output   │  │
   │  └──────────────────────┬─────────────────────────────────────┘  │
   │                         │ GO                                   │
   │  🟧 T10  SHAP + reason code + hành động thu nợ                   │
   └──────────────────────────────────────────────────────────────────┘
          ▲            ▲            ▲            ▲            ▲
          │            │            │            │            │
══════════════════════════════════════════════════════════════════════════════
 L2 — MÔ HÌNH DỰ BÁO 🟧 RIÊNG-1..5, RIÊNG-7
══════════════════════════════════════════════════════════════════════════════
  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
  │🟧 T1 "bao giờ"│ │🟧 T2 "có trả"│ │🟧 T3 "bao nhiêu"│ │🟧 T5 "chi ra"│
  │ LGBM Q10/50/90│ │ hazard N=30/60│ │ ratio∈(0,1]    │ │ rule engine │
  │ + CQR         │ │ /90          │ │ + dispute cls  │ │ + lịch tất định│
  │ + survival clf │ │              │ │               │ │ (không ML)  │
  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
         │               │               │               │
  🟧 T8 Beta-Binomial ──►│ (feature)      │               │
  🟧 T7 CUSUM/BOCPD ──────────────────────┼─── (chế độ) ──►│
                                          │               │
══════════════════════════════════════════════════════════════════════════════
 L1 — NỀN DỮ LIỆU  🟦 CHUNG-1, CHUNG-2, CHUNG-3
══════════════════════════════════════════════════════════════════════════════
  ⬜ ERP (MISA/FAST) ⬜ Bank API/JetPay ⬜ CSV/Excel ⬜ HR/payroll ⬜ QĐ pháp luật
        │
        ▼
  🟦 BRONZE (raw, append-only) → 🟦 SILVER (SCD2, event-sourced, dbt+GX)
        → 🟦 Reconciliation Engine (Exact→Window→Fuzzy→Optimal→Manual)
        → 🟦 GOLD star schema (fct_invoices, dim_customer SCD2, fct_bank_txns)
        → 🟦 Anti-leakage snapshot 
══════════════════════════════════════════════════════════════════════════════
```

---

<a name="c"></a>
## C. PHẦN CHUNG — hạ tầng

<a name="c1"></a>
### C.1 CHUNG-1 — T0: Medallion pipeline

*🟦 Phần chung — vẽ ở mức tầng, không đào nội bộ từng module riêng.*

```
 ┌─────────────────────────────────────────────────────────────────────┐
 │ ⬜ SOURCES                                                          │
 │  ERP (MISA/FAST) ─┬─ Bank API / JetPay ─┬─ CSV/Excel upload         │
 └────────────────────┼─────────────────────┼──────────────────────────┘
                      ▼                     ▼
           ┌───────────────────────────────────────┐
           │ 🟦 BRONZE (Raw) — ELT, append-only    │ ← source of truth
           │    raw_invoices, raw_bank_txns        │   lỗi tầng sau → chạy lại
           └──────────────────┬────────────────────┘
                              ▼  dbt / GX tests
           ┌───────────────────────────────────────┐
           │ 🟦 SILVER (Cleaned, Normalized)       │ ← event-sourced, SCD2
           │    invoices, payments,                │
           │    bank_transactions, allocations     │
           │    + reconciliation engine (CHUNG-2)  │
           └──────────────────┬────────────────────┘
                              ▼  dbt marts
           ┌───────────────────────────────────────┐
           │ 🟦 GOLD (Star Schema) — không tính toán│
           │    fct_invoices · dim_customer (SCD2) │
           │    fct_bank_txns · fixed_obligations  │
           └──────────────────┬────────────────────┘
                              ▼
                🟧 Cash Forecast (T1–T3, T5, T8, T6, T7, T10, T11)
                + ⬛ Dashboard dòng tiền 13 tuần
```

**ERD (CHUNG-1):**
```
customers 1──N invoices 1──N invoice_lines
    │              │
    │              ├──N payment_allocations N──1 payments
    │              │                              │
    │              │                    bank_transactions (khớp qua reconciliation, KHÔNG FK trực tiếp)
    │              └──N── credit_terms
    └──1──N customer_payment_history

fixed_obligations (độc lập, nguồn cho T5)
bank_accounts 1──N bank_transactions

raw_promises → promises → promise_outcomes → trust_scores → fct_customer_trust (T8, "thêm vào T0")
```

**SCD2 (vì sao bắt buộc):** hạn mức khách đổi theo thời gian — ghi đè mất `valid_from/valid_to` thì model sẽ "nhìn nhầm" hạn mức của quá khứ khi backtest theo cutoff.

---

<a name="c2"></a>
### C.2 CHUNG-2 — Reconciliation engine

*🟦 Phần chung — nối giao dịch ngân hàng với hóa đơn; là nguồn "ngày trả thật" cho T1 & nhãn PTP cho T8.*

```
bank_transaction ──┬─► Tầng 1 (80%): Exact match (Regex mã HĐ + số tiền)        ─► auto
                   │
                   ├─► Tầng 2 (15%): Heuristic & Combinatorics
                   │    ├─ Fuzzy text (Levenshtein) — chấp nhận 1 ngưỡng sai
                   │    ├─ Filter theo customer + date window
                   │    └─ Subset Sum (DP) tìm tổ hợp HĐ = amount ± tolerance
                   │         → ≥2 hợp lệ → fallback Tầng 3
                   │
                   └─► Tầng 3 (5%): AI Fallback & Optimization
                        ├─ LLM Extractor: bóc tách nội dung mập mờ → JSON sạch
                        ├─ LightGBM Scoring: xác suất khớp (giao dịch, hóa đơn)
                        ├─ Greedy Match: xếp hạng · khớp từ cao → thấp · dừng < 85%
                        └─ 🟨 Human-in-the-loop: điểm thấp → Kế toán duyệt
                              → label → retrain LightGBM
                                              │
                                              ▼
                              payment_allocations → invoices.balance
                                              │
                              ┌───────────────┴────────────────┐
                              ▼                                ▼
                    🟧 label day_paid cho T1         🟧 outcome kept/broken cho T8
                    (ưu tiên bank_txn_date           (T9 reconciliation detect tiền
                     thay vì posted_date)             về → cập nhật reliability)
```

- Tolerance **adaptive theo khách** (không hardcode): `tolerance = f(customer_size, avg_bank_fee)`; chênh lệch tách `bank_fee` / `fx_gain_loss` riêng.
- Batch payment: 1 giao dịch → N allocations (subset-sum). Reverse: N giao dịch → 1 journal entry (min-cost flow ngược).

---

<a name="c3"></a>
### C.3 CHUNG-3 — Anti-leakage snapshot

*🟦 Phần chung — mọi model T1–T3/T6 đều phải đọc theo lối này*

```
  🟦 Nguyên tắc: point-in-time snapshot — mọi model (T1–T3, T6) đều học theo lối này
        │
        ├─ Mỗi cutoff T (thứ Sáu): chụp toàn bộ state tại thời điểm T
        │    ├─ Hóa đơn đang mở tại T: còn bao nhiêu ngày đến due, đã quá hạn bao lâu
        │    ├─ Customer attributes (CHUNG-1 dim_customer SCD2): lấy record valid_from ≤ T < valid_to
        │    └─ Payment history: CHỈ tính HĐ đã trả TRƯỚC hoặc ĐÚNG T
        │
        ├─ Features lịch sử tính as-of-T:
        │    • median delay khách   • recency 5 HĐ gần nhất   • thống kê term/sector/toàn cục
        │    ⇒ không dùng bất kỳ thông tin nào sau T (chống future leakage)
        │
        └─ Split theo THỜI GIAN (không shuffle)
   ⬛ rolling_snapshot_features.csv     
   ⬛ current_open_invoice_features.csv 
```

**Vì sao đây là "chung":**
- **Chống leakage:** split theo thời gian, không shuffle → model không nhìn thấy kết quả tương lai.
- **Backtest trung thực:** mô phỏng đúng cách hệ thống chạy live — tại thời điểm `T` chỉ biết quá khứ ≤ `T`.
- **SCD2_customer (CHUNG-1) phối hợp:** mỗi `T` lấy đúng hạn mức/thuật toán trả đang có hiệu lực lúc đó (khách tháng 6 nợ 500tr, tháng 9 lên 1 tỉ → snapshot tháng 6 vẫn là 500tr).
- **Làm một lần, dùng nhiều nơi:** cùng một `rolling_snapshot_features.csv` là nguồn feature duy nhất cho T1/T2/T3 → tránh mỗi model tự build feature riêng và lệch định nghĩa as-of-`T`.

---

<a name="d"></a>
## D. PHẦN RIÊNG CỦA CASH FORECAST

<a name="d1"></a>
### D.1 RIÊNG-1 — T1: dự báo ngày trả từng hóa đơn

*🟧 Nguồn: `invoice_payment_cash_in_report.tex` §3.1–3.3.*

```
  🟦 snapshot (CHUNG-3) 
        │
        ├─► B1  = days_until_due + median_delay_khách (fallback term/global)
        │
        ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │ 🟧 T1a — QUANTILE ENSEMBLE VOTE                                      │
 │                                                                      │
 │   LightGBM ×3 (Q10/Q50/Q90)  +  CatBoost no-stack                   │
 │   features + meta-feature = pred_B1                                 │
 │   num_leaves=31, lr=0.05, ES=100 · tune 3 configs                     │
 │   rearrangement P10≤P50≤P90 · chặn ≥0 · bagging 3 seeds             │
 │                                                                      │
 │   → Vote: mean(LGBM, CatBoost) → ngày trả dự kiến                    │
 │   → CatBoost no-stack để giảm overfitting                           │
 └──────────────────────────────┬───────────────────────────────────────┘
                                │
                                ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │ 🟧 T1b — CQR (Conformalized Quantile Regression)                    │
 │                                                                      │
 │   Hiệu chỉnh trên validation · qhat điều chỉnh độ rộng dải          │
 │   Coverage target 75–85% · P50 giữ nguyên                            │
 └──────────────────────────────┬───────────────────────────────────────┘
                                │
                                ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │ 🟧 T1c — Survival classifier (3 model LightGBM)                     │
 │                                                                      │
 │   P(trả trong N | sống tới T), N = 30/60/90                         │
 │   ▸ CHỈ nới dải ở HĐ rủi ro cao                                    │
 │   → tránh mất độ sắc trên HĐ bình thường                           │
 └──────────────────────────────┬───────────────────────────────────────┘
                                │
                                ▼
        ⬛ remaining_days_at_T = (P10, P50, P90) hiệu chỉnh
        ⬛ survival_prob_{30/60/90} → T6 / T2
```

**Đầu vào từ các module khác:**
- 🟧 **T8** → feature `reliability` / `broken-promise rate` cho LightGBM
- 🟦 **CHUNG-3** → toàn bộ feature as-of-`T`

---

<a name="d2"></a>
### D.2 RIÊNG-2 — T2: khả năng trả / vỡ nợ (PD)

*🟧 Nguồn: `t2_default_risk.md`.*

```
 ⬜ input: khách + lịch sử thanh toán + macro (CPI/PMI/interbank/VND-USD vol)
        │
        ├─ Baseline: Logistic / LightGBM binary classification
        │            (label VN: quá hạn >90 ngày hoặc write-off — TT48)
        │            → Platt (mẫu nhỏ) / Isotonic (mẫu lớn)
        │
        ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │ 🟧 T2a — DISCRETE-TIME HAZARD MODEL (phương án chính)                │
 │   person-period format: 1 HĐ → nhiều dòng (mỗi kỳ 1 dòng)            │
 │   h(t) = P(vỡ nợ tại kỳ t | sống tới t-1)                           │
 │   → sống sót ∏(1-h(t)) → cumulative PD = 1 − ∏(1-h(t))              │
 │   ▸ 1 model → PD tại MỌI horizon (30/60/90/180)                     │
 │   ▸ khớp IFRS 9 Stage 1 (12 tháng) / Stage 2 (lifetime)             │
 └──────────────────────────────┬───────────────────────────────────────┘
                                ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │ 🟧 T2b — MODEL POOL + LOCAL REGION (regime shift)                    │
 │   M1..Mn huấn luyện trên các bối cảnh vĩ mô khác nhau                │
 │   → clustering tìm 500–1000 KH quá khứ giống KH đang xét (FLI)      │
 │   → dynamic selection: mô hình nào dự báo sát nhất trên θ thắng     │
 │   → PSI hàng tháng + online learning thêm M(n+1) khi có "thiên nga"  │
 └──────────────────────────────┬───────────────────────────────────────┘
                                ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │ 🟧 T2c — Conformal prediction (MAPPIE)                               │
 │   prediction set = {0,1} → không chắc chắn → 🟨 flag human review   │
 │   + SHAP (global / local)                                           │
 │   + class imbalance: is_unbalance / SMOTE+Tomek / focal / Bayesian   │
 └──────────────────────────────┬───────────────────────────────────────┘
                                ▼
      ⬛ PD(t) · ⬛ risk-weight cho T6  (widen P10–P90 · ⬛ early warning nợ xấu)
```

**Metric (target):** AUC > 0.80 · Brier < 0.10 · Recall@spec0.95 > 0.60 · PSI < 0.10.

---

<a name="d3"></a>
### D.3 RIÊNG-3 — T3: tỷ lệ trả & tranh chấp

*🟧 Nguồn: `t3_payment_allocation_disputes.md`.*

```
 ⬜ input: dispute_notes, email_thread (LLM embedding), HĐ lines, macro (shock từ T7)
        │
        ├─ 🟧 T3a — PAYMENT RATIO REGRESSION:  ratio ∈ (0,1]
        │     features: customer(avg_ratio, dispute_rate, days_late, industry,
        │                credit_limit) · invoice(amount, age, has_contract, term)
        │     eval: MAE / MAPE / calibration curve
        │
        ├─ 🟧 T3b — DISPUTE CLASSIFICATION (multi-label)
        │     labels: pricing · shortage · quality · compliance · allowance · noise
        │
        │     ┌─ Agent 1 (Data Extractor): OCR/Regex (retailer cố định ~0 cost)
        │     │   → fallback Vision-LLM (email lộn xộn/PDF phi cấu trúc)
        │     │
        │     ├─ Agent 2 (Linker): parse ref_codes → SQL/ES (BM25) / Vector Search
        │     │   
        │     │
        │     └─ Agent 3 (Reasoning Judge): LLM lớn phân loại + evidence chain
        │
        │     Metrics (target): F1-macro · cost/claim <$2 · time-to-resolution <3d
        │              · auto-resolve >80%
        │
        └─ 🟧 T3c — XỬ LÝ TRANH CHẤP & GIẢM TRỪ:
              Short pay → Classify reason → dispute | accept
                    ├─ dispute → Investigation → valid: reverse / invalid: write-off
                    └─ accept  → credit memo → update balance → reconcile
              + HĐ tách HĐ con (parent_invoice_id, split_reason)
              + Overpayment: unallocated_amount → hoàn trả / cấn trừ HĐ sau
              + Tạm ứng: advance payment (invoice_id=NULL) → allocation khi HĐ phát sinh
```

---

<a name="d4"></a>
### D.4 RIÊNG-4 — T5: chi cố định & lịch nghĩa vụ (cash OUT)

*🟧 Nguồn: `t5_fixed_outflows_obligations.md`. **Không dùng ML** — rule tất định để audit được.*

```
 ⬜ Dữ liệu T0 (kế toán, nhân sự, ERP) + ⬜ nhập tay (thưởng, ước tính)
        │
        ▼
  🟧 Chuẩn hóa → Canonical Record
        │
        ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │ 🟧 RULE ENGINE (GoRules ZEN) — tất định, auditable                    │
 │  ├─ Rule Nhân sự     → Lương thực nhận & BHXH                        │
 │  ├─ Rule Thuế TNCN   → bậc thang 5–35%, gia cảnh 11tr / 4,4tr       │
 │  ├─ Rule Thuế GTGT   → VAT đầu ra − VAT đầu vào                      │
 │  └─ Rule Thuế TNDN   → lợi nhuận ròng × 20% (17% SME)               │
 └──────────────────────────────┬───────────────────────────────────────┘
                                ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │ 🟧 SCHEDULER + Date-Shifting                                         │
 │  1. Lễ/CN → dời về ngày làm việc liền TRƯỚC                          │
 │  2. 31 nhưng tháng 30/28 → ngày cuối tháng                           │
 │  3. Tết → dời lương lên 5–7 ngày, BHXH lên 3–5 ngày                 │
 │  4. Lương tháng 13 / thưởng → nhập tay, gán T12/T1                   │
 └──────────────────────────────┬───────────────────────────────────────┘
                                ▼
      ⬛ payment_schedule(week_id='2026-W42', scheduled_date, amount, status)
        │
        ├─ 🟦 phân quyền: Tự động 100% (BHXH, TNCN) · Bán tự động (TNDN, GTGT)
        │                · Thủ công 100% (thưởng, T13, chi bất thường)
        │
        └─► 🟧 T6 (cash out theo tuần)
            🟨 Sandbox "hoãn chi": gạt toggle → T6 render lại chart ngay
```

**Bảng nghĩa vụ (nguồn `t5_fixed_outflows_obligations.md`):** Lương mùng 5/10 · VAT & TNCN ngày 20 tháng sau (kỳ tháng) · TNDN tạm nộp đầu quý sau, quyết toán ≤31/03 · BHXH/BHYT/BHTN 21,5% DN / 10,5% NLĐ trước ngày 15 · Công đoàn 2%.

---

<a name="d5"></a>
### D.5 RIÊNG-5 — T8: lời hứa trả (Promise-to-Pay)

*🟧 Nguồn: `t8_promise_to_pay.md`.*

```
  ⬜ Zalo msg · ⬜ phone note · ⬜ email (Bronze)
        │
        ▼
  🟧 promises (Silver: ngày hứa, số tiền, channel)
        │
  🟧 promise_outcomes (Silver: kept / broken, days_late)  ◄─── 🟦 tự động từ
        │                                                     CHUNG-2 (tiền về → kept/broken)
        ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │ 🟧 trust_scores — Beta-Binomial Bayesian Update                      │
 │   Reliability = số lần giữ lời / tổng số lần hứa                     │
 │   Beta(α + kept, β + broken)                                         │
 │                                                                      │
 │   MULTI-DIMENSIONAL SCORE (5 chiều):                                 │
 │   1. fulfillment_rate        — tỷ lệ giữ lời                        │
 │   2. avg_delay_when_broken   — delay_score = max(0, 1-avg_delay/30)  │
 │   3. amount_sensitivity      — tách reliability(HĐ nhỏ) vs (HĐ lớn) │
 │   4. recency_score           — exponential decay, half-life 180 ngày │
 │   5. promise_volatility      — thất thường → uncertainty cao        │
 └──────────────────────────────┬───────────────────────────────────────┘
                                ▼
      🟦 fct_customer_trust (Gold)
        │
        ├─► 🟧 T1  : reliability = feature cho LightGBM
        ├─► 🟧 T2  : trust giảm đột ngột → early warning nợ xấu
        ├─► 🟧 T6  : khách không tin cậy → WIDEN khoảng P10–P90
        └─► 🟧 T10 : "tuần này thiếu vì Cty B phá lời lần 3"

  Mức tự động hóa:
   P0 Form 5s trên AR aging (bắt buộc ghi) ─┐
   P1 Auto-outcome từ T9 reconciliation ────┤  >70% capture · >80% auto
   P2 NLP/Zalo bot extract → draft          ┘
```

**Cách T8 can thiệp vào T6:** không chỉ là feature — nếu có PTP thì **phân phối dự báo của HĐ bị ghi đè quanh `promised_date`**, dashboard ghi "theo cam kết, không phải theo model".

---

<a name="d6"></a>
### D.6 RIÊNG-6 — T6: lõi Monte Carlo cash forecast (TRUNG TÂM)

*🟧 Nguồn chính: `invoice_payment_cash_in_report.tex` §3.4 + `DIGITAL_ACCOUNTING` §3.2.Bước1.4.*

#### D.6.1 — Cấu trúc mô phỏng

```
 ⬛ INPUTS ────────────────────────────────────────────────────────────
 │  🟧 từ T1 : (P10, P50, P90)_i cho các HĐ đang mở
 │  🟧 từ T1c: survival_prob P(trả trong N) — trọng số straggler
 │  🟧 từ T2 : P(default)         → sample trạng thái "mất trắng"
 │  🟧 từ T3 : ratio ∈ (0,1]      → thực thu = amount × ratio
 │  🟧 từ T5 : payment_schedule   → cash OUT cố định theo tuần
 │  🟧 từ T8 : PTP override + reliability widen
 │  ⬜ số dư đầu kỳ · ⬜ ngưỡng kế hoạch (proxy)
 └─────────────────────────────────────────────────────────────────────
        ▼
 ┌──────────────────────────────────────────────────────────────────────┐
 │ 🟧 T6 — MONTE CARLO COPULA                                          │
 │                                                                       │
 │  N-dependency (KHÔNG giả độc lập):                                   │
 │    U = ρ_m·M + ρ_c·C + √(1 − ρ_c² − ρ_m²)·Z                        │
 │    (ρ_c, ρ_m) = (0,25; 0,75)   ← quét lưới xác nhận                 │
 │    (M = shock macro chung, C = shock nhóm KH, Z = idiosyncratic)    │
 │                                                                       │
 │  Residual bootstrap theo nhóm AGING                                  │
 │  + ĐUÔI MŨ  Exp((Q90 − Q50)/2)  với p = 5% có trọng số survival     │
 │    cho stragglers (risk-weighted tail)                               │
 │                                                                       │
 │  ⇒ 10.000 kịch bản (live: 2.000)                                     │
 └──────────────────────────────┬───────────────────────────────────────┘
                                ▼
        ⬛ amount = invoice_amount × ratio × (1 − I_default) × I_{day ≤ horizon}
                   gom theo tuần (13 tuần / 91 ngày)
                                ▼
        ⬛ P10 / P50 / P90 của SỐ DƯ theo tuần
        ⬛ xác suất P(cash < ngưỡng an toàn) trong tuần t
        ⬛ "tuần đầu tiên P10 < ngưỡng"
```

#### D.6.2 — Thiết kế mô phỏng phụ thuộc

Copula Gauss để mô hình hoá phụ thuộc giữa các HĐ:
- N-dependency: `U = ρ_m·M + ρ_c·C + √(1 − ρ_c² − ρ_m²)·Z`
- Residual bootstrap theo nhóm AGING
- Đuôi mũ `Exp((Q90 − Q50)/2)` với risk-weighted tail cho stragglers

#### D.6.3 — Gia cống thực địa (4 điểm yếu khi chạm doanh nghiệp thật)

```
 W1 Nhiễu "hạch toán theo lô"
    ├─ label ngày trả = bank_txn_date (không phải posted_date)
    ├─ thiếu sao kê → interval-censored (discrete-time survival)
    └─ detector nhiễu lô trước khi train

 W2 Thỏa thuận ngoài hệ thống
    └─ PTP là thực thể hạng nhất (→ module T8)

 W3 "trả cực chậm" ≠ "mất trắng"
    └─ two-part: P(default) trước (T2), phân phối thời điểm sau → không còn "ảo tưởng P90"
       + neo TT48/2019: 6–12T 30% · 1–2N 50% · 2–3N 70% · >3N 100%

 W4 Thiên nga đen / đứt gãy cấu trúc
    ├─ shock Gaussian → Student-t (df≈3, đuôi dày)
    ├─ thư viện kịch bản stress tất định (khách trễ 30/60 ngày, top-1 default,
    │   doanh thu −30% 3 tháng, tái hiện 2022)
    └─ change-point (→ RIÊNG-7) → chế độ khủng hoảng
```

---

<a name="d7"></a>
### D.7 RIÊNG-7 — T7: điểm gãy & chế độ khủng hoảng

*🟧 Nguồn: `DIGITAL_ACCOUNTING` §2.1 (T7) + §3.2.W4 · `invoice_forecast_full_pipeline.ipynb` ô 124–152 · `regime_status.csv` + `changepoint_segments.csv`.*

```
 ⬜ OxCGRT  ⬜ macro (PMI/CPI/interbank/VND-USD vol)  ⬜ bot search web/news
 │
 ▼
 ┌─ SIGNALS NỘI BỘ (từ dataset AR) ─────────────────────────────────────┐
 │ 🟧 CUSUM · Page–Hinkley · BOCPD  trên forecast error                 │
 │ 🟧 PSI phân phối delay            (train vs live, 9 features)        │
 │ 🟧 Binary Segmentation            trên late_rate · weekly_cash        │
 └──────────────────────────────────────────────────────────────────────┘
 ┌─ SIGNALS BÊN NGOÀI (không cần dataset AR) ──────────────────────────┐
 │ 🟧 OxCGRT — Oxford COVID Gov. Response Tracker:                     │
 │    stringency_index tăng >15pt trong 2 tuần → xác nhận cú sốc        │
 │    bên ngoài, không phải noise; dùng làm CONFIRM, không tự trigger│
 │ 🟧 Macro drift — PSI trên CPI/PMI/interbank/VND-USD vol              │
 │    (giống PSI nội bộ nhưng trên chuỗi vĩ mô, source: FRED/TCBS)    │
 │ 🟧 Bot web/news — RSS crawl hàng tuần:                               │
 │    tin "đóng băng BĐS", "khách lớn phá sản", "lệnh cấm xuất khẩu"  │
 │    → LLM classify severity → feed vào T10 giải thích "VÌ SAO"        │
 └──────────────────────────────────────────────────────────────────────┘
    target: phát hiện ≤ 3 tuần · báo động giả thấp
 │
 ├─ NORMAL ──► model đầy đủ, dải chuẩn
 │
 ├─ WATCH ───► ⬛ "đang theo dõi drift" · tăng recency weighting ·
 │              mở stress scenario cạnh base forecast
 │
 └─ CRISIS ──► 🟧 CHẾ ĐỘ KHỦNG HOẢNG
        ├─ dải dự báo NỚI RỘNG: Student-t (df≈3, đuôi dày) thay Gaussian
        │   (biến động cực đoan có mặt trong dải mô phỏng — W4)
        ├─ ⬛ Student-t shock thay vì Gaussian trong copula T6
        ├─ ⬛ nhãn "độ tin cậy thấp — chế độ hậu đứt gãy" in đậm
        ├─ 🟨 review người hàng ngày · KHÔNG cam kết với bên thứ ba
        └─ retrain recency weighting (suy giảm mũ, half-life 4–8 tuần)
```

**Bảng tín hiệu hợp nhất — 2 loại: nội bộ + bên ngoài:**

| # | Tín hiệu | Nguồn | Đo gì | Khi TRIGGER | Vai trò |
|---|---|---|---|---|---|
| S1 | CUSUM/PH/BOCPD | Dataset AR (backtest residual) | sai số tích lũy theo tuần | ≥2/3 phương pháp alarm | Bắt drift MEAN nhỉnh, tích lũy chậm |
| S2 | PSI phân phối | Dataset AR (train vs live, 9 features) | lệch phân phối `days_late`/`amount`/`customer_delay` | PSI ≥ 0,25 | Bắt dịch chuyển TOÀN CỤC, không cần nhãn |
| S3 | Binary Segmentation | Dataset AR (chuỗi tuần) | breakpoint trên `late_rate`/`weekly_cash` | breakpoint ≤ 8 tuần | Tìm TUẦN cụ thể, source cho shock S5 |
| **S4** | **OxCGRT stringency** | **Oxford (public)** | **stringency index Δ >15pt/2wk** | **Có + S1–S3** | **Xác nhận cú sốc-policy, KHÔNG tự trigger** |
| **S5** | **Macro PSI** | **FRED/TCBS (public)** | **PSI trên CPI/PMI/interbank/VND-USD vol** | **PSI_macro ≥ 0,25** | **Bắt drift vĩ mô trước khi vào AR** |
| **S6** | **Bot web/news** | **RSS crawl + LLM** | **tin tức nghiêm trọng (severity ≥ threshold)** | **≥2 tin/week** | **Feed vào T10 "VÌ SAO" + confirm trigger** |

`crisis ← ≥2/3 internal (S1–S3) TRIGGER + PSI ≥ 0,25 + breakpoint ≤ 8 tuần` · `watch ← 1/3` · `normal ← còn lại` → `regime_status.csv` → T6/T10/T11 đọc.


---

<a name="d8"></a>
### D.8 RIÊNG-8 — T11 GATE (backtest) → T10 giải thích & hành động

*🟧 Nguồn: `DIGITAL_ACCOUNTING` §2.1 (T10/T11).*

> **Thứ tự bắt buộc: T11 chạy TRƯỚC T10.**
> T11 là cổng kiểm soát chất lượng nội bộ, chạy trên **test set đã đóng băng** (không dùng để train).
> T6 sinh ra dự báo trên test set → T11 so với **baseline** → chỉ khi GO thì T10 mới diễn giải và
> xuất danh sách hành động cho người dùng. **T10 không chạy trên output của một model NO-GO.**

#### D.8.1 — T11 GATE GO/NO-GO (chạy trước, chặn "tự lừa")

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🟧 T11 — `python run.py go` → outputs/go_decision.csv                       │
│      Chạy trên TEST SET đã đóng băng · KHÔNG dùng test để train hay chọn M │
├──────────────────────────────────┬───────────┬──────────┬────────────────────┤
│ Rule                             │ Target    │ Vai trò  │ Ghi chú            │
├──────────────────────────────────┼───────────┼──────────┼────────────────────┤
│ R1a cash wMAPE ≤ B1              │ ≤ baseline│ gate     │ ngưỡng             │
│ R1b cash CRPS ≤ B1-dist          │ ≤ baseline│ gate     │ ngưỡng             │
│ R2  invoice MAE cải thiện ≥10%   │ ≥ +10%    │ gate     │ ngưỡng             │
│ R4  coverage invoice (CQR) 75–85%│ 75–85%    │ gate     │ ngưỡng             │
│ Action value-precision@100       │ ≥ baseline│ gate     │ ngưỡng             │
│ S1  unique-invoice cải thiện     │ ≥ +10%    │ nhạy    │ cảnh báo           │
│ S3  không stacking (nostack)     │ ≥ +10%    │ nhạy    │ cảnh báo           │
└──────────────────────────────────┴───────────┴──────────┴────────────────────┘
                                 │
        PASS/FAIL → GO/NO-GO trước khi đưa model vào live
```

**Baseline (B1) là gì:** mô hình đơn giản, không ML — lịch sử `days_late` trung bình theo nhóm
aging, dự báo theo trung bình lịch sử. Đây là mức "làm được bao nhiêu" tối thiểu; model T1–T6
phải **đánh bại B1** mới được coi là có giá trị.

**Khi GO — model đạt chuẩn:**

| Bước | Hệ thống làm gì |
|---|---|
| 1 | Chốt phiên bản model + ghi `model_version` vào registry |
| 2 | Deploy sang môi trường live, chạy T6 trên dữ liệu hiện tại (không phải test set) |
| 3 | T10 diễn giải output của model **đã được GO** → xuất dashboard + danh sách thu hồi |

**Khi NO-GO — model bị chặn, user KHÔNG thấy output nào:**

| Bước | Hệ thống làm gì |
|---|---|
| 1 | **Không deploy.** Không chạy T6 live, không sinh dashboard cho user |
| 2 | Ghi `go_decision.csv` với đầy đủ: rule FAIL, giá trị thực tế, ngưỡng, chênh lệch |
| 3 | Báo cáo chẩn đoán cho data scientist: rule nào đỏ và gợi ý hướng xử lý |
| 4 | Quay lại vòng train tiếp theo (thêm feature / đổi hyperparam / thu thập thêm dữ liệu) |

**File `go_decision.csv` (schema):**

```
version,evaluated_at,rule,metric,actual_value,threshold,baseline_value,result,diagnosis,next_action
v3.2, 2026-08-31,   R1a, cash_wMAPE,        0.187,  0.220,   0.220,  PASS,
v3.2, 2026-08-31,   R1b, cash_CRPS,         0.041,  0.055,   0.055,  PASS,
v3.2, 2026-08-31,   R2,  invoice_MAE_delta, 0.183,  0.100,   0.000,  PASS,
v3.2, 2026-08-31,   R4,  cqr_coverage,      0.801,  0.850,   0.800,  PASS,
v3.2, 2026-08-31,   ACT, value_precision@100, 0.62, 0.55,   0.55,   PASS,
v3.2, 2026-08-31,   SUM, go_no_go,          5/5,   5/5,          ,   GO,
```

#### D.8.2 — T10 Giải thích & hành động (chạy sau, chỉ khi T11 = GO)

```
 ⬛ Output của model ĐÃ ĐƯỢC GO: P10/P50/P90 + xác suất thiếu hụt + ngày đứt
        │
        ▼
 🟧 SHAP / reason code    →  "Vì sao tuần đó bị đánh giá thiếu tiền?"
 🟧 Xếp hạng theo GIẢM XÁC SUẤT THIẾU HỤT  (không phải xếp theo số tiền)
        │
        ▼
 ⬛ Danh sách thu hồi 100 HĐ/tuần  ──►  🟨 nút "tạo đề xuất thu nợ"
        │                                 (LLM soạn email/cuộc gọi → approval gate)
        │
        └─ (target: value-precision@100 — xếp hạng theo giảm xác suất thiếu hụt)

 ⚠ Điều kiện tiên quyết: T11 = GO. Nếu NO-GO, nhánh này không được render.
```

---

<a name="e"></a>
## E. TÍCH HỢP — Pipeline end-to-end của Cash Forecast

```
═══════════════════════════════════════════════════════════════════════════════
 KHỐI CHUNG (🟦) ════════════════════════════════════════════════════════════
═══════════════════════════════════════════════════════════════════════════════
 ⬜ ERP MISA/FAST ─┐
 ⬜ Bank/JetPay  ──┼─► 🟦 BRONZE ─► 🟦 SILVER (SCD2, dbt/GX) ─► 🟦 Reconciliation
 ⬜ CSV/Excel    ──┘                                            │
                                                                ▼
                                              🟦 GOLD (star schema)
                                                                │
                                              🟦 Cutoff snapshot (47T, 3 split)
═══════════════════════════════════════════════════════════════════════════════
 KHỐI RIÊNG (🟧) ════════════════════════════════════════════════════════════
═══════════════════════════════════════════════════════════════════════════════
                    ┌────────────────────────────────────────────┐
                    │                                            │
    ┌───────────────┼─────────────────┬──────────────────┬───────┴──────┐
    ▼               ▼                 ▼                  ▼              ▼
 🟧 T8 PTP    🟧 T1 ngày trả    🟧 T2 PD          🟧 T3 ratio    🟧 T5 nghĩa vụ
 Beta-Binom   LGBM Q + CQR      hazard N=30/60     regression     rule engine
 5 chiều      + survival clf    /90 + model pool   + dispute      + date-shift
    │               │                 │                  │              │
    └──feature──────┤                 │                  │              │
                    │                 │                  │              │
 🟧 T7 change-point ┤ (chế độ khủng hoảng)               │              │
                    │                 │                  │              │
                    └────────┬────────┴─────────┬────────┴──────┬───────┘
                             ▼                  ▼              ▼
                     ⬛ (P10,P50,P90)     ⬛ P(default)    ⬛ cash OUT
                     ⬛ survival prob     ⬛ ratio         theo tuần
                             │                  │              │
                             └────────────┬─────┴──────────────┘
                                          ▼
═══════════════════════════════════════════════════════════════════════════════
 🟧 T6 — MONTE CARLO COPULA · 10.000 kịch bản · tail 5% risk-weighted
═══════════════════════════════════════════════════════════════════════════════
                                          │
        ┌─────────────────────────────────┼──────────────────────────┐
        ▼                                 ▼                          ▼
 ⬛ P10/P50/P90 theo tuần      ⬛ P(cash < ngưỡng)         ⬛ ngày P10 < ngưỡng
        │                                 │                          │
        └────────────────┬────────────────┴──────────────────────────┘
                         ▼
═══════════════════════════════════════════════════════════════════════════════
 🟧 T11 GATE GO/NO-GO (luật chấm R1 · R2 · R4 · Action · S)
 ⚠ chạy trên TEST SET · so với BASELINE · GO mới xuất output cho user
═══════════════════════════════════════════════════════════════════════════════
                         │
           ┌─────────────┴─────────────┐
           ▼                           ▼
     ✅ GO                          ❌ NO-GO
           │                            │
           ▼                            └─► Không deploy
        🟧 T10 SHAP + reason code         Không xuất dashboard
              + xếp hạng                  Không chạy T10
              │                           Báo cáo chẩn đoán cho DS
              ▼                           Quay lại train
 ⬛ Dashboard 13 tuần · ⬛ Danh sách thu hồi 100 HĐ/tuần
        │                                │
        ├─── 🟨 Approval gate         ───┘
        └─── 🟨 Sandbox "hoãn chi" (T5) → T6 render lại
```

**Câu trả lời cho N1–N7 (bản đồ nhu cầu → module):**

| Nhu cầu | Câu hỏi | Module trả lời |
|---|---|---|
| **N1** | Tuần nào thiếu tiền, xác suất bao nhiêu? | 🟧 **T6** + 🟧 T5 |
| **N2** | Khoản nào trễ → đòi trước? | 🟧 **T1** + 🟧 T8 + 🟧 T10 |
| **N3** | Khách nào không trả, bao nhiêu tiền rủi ro? | 🟧 **T2** |
| **N4** | Thử kịch bản (khách lớn trễ 2 tuần, hoãn chi)? | 🟧 **T6** + 🟧 T5 (sandbox) |
| **N5** | Vì sao hệ thống cảnh báo? | 🟧 **T10** (SHAP/reason code) |
| **N6** | Số liệu khớp sổ? | 🟦 **CHUNG-1/CHUNG-2** |
| **N7** | Báo khi hoàn cảnh đổi? | 🟧 **T7** |

---
