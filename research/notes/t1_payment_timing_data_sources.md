# T1 — Dữ liệu để huấn luyện: Dự báo ngày trả hoá đơn

> **Dữ liệu đã tải đầy đủ:** [audit Bộ Tài chính và y tế Séc](t1_czech_full_dataset_audit.md) có quy mô thực, chất lượng, vấn đề trùng và đường dẫn file local. Đây là kết quả mới nhất cho hai nguồn này.

> **Đề xuất mới nhất:** đọc [nghiên cứu dataset T1 và phương án lựa chọn](t1_dataset_recommendation.md), đã kiểm tra mẫu gốc BPI/DC và bổ sung nguồn hóa đơn chính thức của Séc. Các khuyến nghị cũ bên dưới về “SAP thật/công khai”, file local “đã có” và ưu tiên transfer từ Home Credit/LendingClub **không còn là khuyến nghị hiện hành**; chưa có bằng chứng nguồn gốc hoặc hiệu quả chuyển miền để khẳng định như vậy.

> Rà soát nguồn ngày 18/10/2026: xem [kiểm tra dữ liệu thật T1–T8](t1_t8_verified_data_sources.md). Khẳng định “SAP ERP sample thật/công khai” bên dưới chưa có chuỗi xuất xứ và giấy phép được xác minh. UCI mô tả Online Retail II có nhiều khách bán buôn; không nên gọi toàn bộ là B2C thuần hoặc suy ra đã thu tiền ngay. Khi có khác biệt, dùng kết luận nguồn đã đối chiếu trong bản rà soát mới.

---

## 1. Dữ liệu hiện có trong project

**File:** `data/dataset.csv` + `data/dataset_closed_invoices.csv`

| Thuộc tính | Chi tiết |
|-----------|---------|
| **Nguồn** | SAP ERP sample (khách hàng Mỹ, công khai) |
| **Quy mô** | 50.000 invoices, trong đó 39.152 closed, 9.681 open |
| **Thời gian** | 2018–2019 |
| **Domain** | B2B, ngoài Mỹ (currency USD) |
| **Cột chính** | `invoice_id`, `customer_id`, `posting_date` (issue), `due_date`, `clear_date` (paid), `amount_open` |
| **Label** | Continuous: `days_late = clear_date - due_date`; Binary: `is_overdue = days_late > 0` |
| **Ưu điểm** | Domain gần nhất, có sẵn, structured, multi-year |
| **Hạn chế** | Nhỏ (50K), chỉ 1 khách hàng, chỉ USD, không có feature hành vi khách |

**Sử dụng:** Train T1 baseline OK; để benchmark. Không đủ để production.

---

## 2. Dữ liệu công khai lớn khác — cho T1

### Dự báo tiền thanh toán & days-to-payment

#### 2.1. **Favorita** (Ecuador, e-commerce aggregator)

| Thuộc tính | Chi tiết |
|-----------|---------|
| **Liên kết** | [Kaggle Favorita Sales Forecasting](https://www.kaggle.com/competitions/favorita-grocery-sales-forecasting) |
| **Quy mô** | ~125 triệu dòng × 5 năm (2013–2017) |
| **Mục đích** | Dự báo doanh số bán hàng hàng ngày (T4, không phải T1) |
| **Domain** | ❌ **Retail B2C, không phải B2B invoice** — dòng tiền từ khách lẻ, không hóa đơn |
| **Tính chất** | Bán lẻ, cash-on-delivery → ngày mua ≈ ngày thanh toán → **không phải T1** |
| **Adaptation** | ❌ **Không khuyến nghị** — không có ngày hạn thanh toán / payment terms |

#### 2.2. **Olist Brazilian E-Commerce** (Công ty Olist, Brazil)

| Thuộc tính | Chi tiết |
|-----------|---------|
| **Liên kết** | [Kaggle Olist Public Dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) |
| **Quy mô** | ~100K đơn hàng (2016–2018); 5 bảng: orders, payments, items, customers, reviews |
| **Cột thanh toán** | `payment_type`, `payment_installments`, `payment_value`, `order_purchase_timestamp`, `order_delivered_customer_date` |
| **Domain** | ❌ **Retail B2C, không phải B2B** — consumer electronics, small average |
| **Label** | Time-to-delivery, không phải time-to-payment |
| **Adaptation** | 🟡 **Có khó:** Dùng `order_purchase_timestamp` - `order_delivered_date` = delivery lag; ánh xạ vào payment_installments → estimate payment lag. Nhưng không có `due_date`, chỉ có `payment_value` (đã thanh toán) ➝ **bị rò rỉ label**. |
| **Khuyến nghị** | 🟡 **Học feature engineering** (aggregation theo customer, item type, region), không dùng trực tiếp |

#### 2.3. **Home Credit Default Risk** (Home Credit company)

| Thuộc tính | Chi tiết |
|-----------|---------|
| **Liên kết** | [Kaggle Home Credit](https://www.kaggle.com/competitions/home-credit-default-risk) |
| **Quy mô** | ~300K applications; 122 features; liên kết: bureau (credit history), previous applications, installments_payments |
| **Bảng chính** | `application_*.csv` (app-level); `installments_payments.csv` (~13M dòng) |
| **Cột thanh toán** | `installments_payments`: `NUM_INSTALMENT_NUMBER` (thứ mấy), `INSTALMENT_STATUS` (0=OK/1=paid early/2=late/3=disputed), `DAYS_INSTALMENT` (ngày kỳ hạn), `DAYS_ENTRY_PAYMENT` (ngày thực tế trả) |
| **Domain** | ❌ **Consumer finance, không phải B2B** — vay cá nhân, tín dụng tiêu dùng, cố định số kỳ |
| **Label** | Continuous: `DAYS_ENTRY_PAYMENT - DAYS_INSTALMENT` = ngày trễ; Binary: `INSTALMENT_STATUS == 2` = late |
| **Ưu điểm** | Rất lớn, multi-table (như ERP), kỳ hạn cố định |
| **Hạn chế** | Cá nhân không phải công ty, amount nhỏ (POS/CSPC), số kỳ cố định (không như hóa đơn) |
| **Adaptation** | 🟡 **Khó – Domain shift lớn** <br> • Cá nhân (individual) → B2B (corporate): khác credit pattern, khác tài chính <br> • Kỳ hạn cố định (monthly installment) → Không fixed (invoice due in 30/45/60 days từ issue) <br> • Tín dụng tiêu dùng → trade credit → khách hàng khác <br> • **Có thể dùng:** Feature engineering ideas (rolling aggregation, recency weighting, behavioral flags) <br> • **Cẩn thận:** Mô hình train trên installment structure sẽ overfit |
| **Khuyến nghị** | 🟡 **Phần lớn feature patterns; không dùng mô hình trực tiếp** |

#### 2.4. **LendingClub** (P2P lending platform, Mỹ)

| Thuộc tính | Chi tiết |
|-----------|---------|
| **Liên kết** | [Kaggle LendingClub Loan Data](https://www.kaggle.com/datasets/wordsforthewise/lending-club) hoặc [LendingClub.com Direct](https://www.lendingclub.com/info/download-data.action) |
| **Quy mô** | ~2.2 triệu khoản vay; ~150 features; 2007–2018 |
| **Cột thanh toán** | `issue_d` (issue date), `expected_maturity` (kỳ hạn, cố định 3/5 năm), `last_payment_d` (ngày trả cuối), `last_payment_amnt`, `total_rec_prncp` (tổng tiền gốc nhận), `recoveries` (tiền recovery sau default) |
| **Domain** | ❌ **Consumer P2P lending, không phải B2B invoice** — vay dài hạn (36–60 tháng), cố định lãi suất + công nợ |
| **Label** | Continuous: `last_payment_d - expected_payment_schedule` tại mỗi kỳ; Binary: `loan_status` (Fully Paid / Charged Off / Late / Default / In Grace Period) |
| **Ưu điểm** | Tập lớn, bảng lệch lạm phát, có expected schedule |
| **Hạn chế** | Kỳ hạn dài (36–60 tháng) ≠ hóa đơn (20–120 ngày), cố định payment schedule ≠ hóa đơn không cố định |
| **Adaptation** | 🟡 **Trung bình** <br> • Cấu trúc tương tự: issue_date, expected_date, actual_date, status <br> • **NHƯNG** kỳ hạn lâu → pattern trễ khác (seasonality, long-term drift) <br> • Có thể extract: dự báo **recency** (ngày hôm nay, khoản nào sẽ trả kỳ này), không phải tổng thể <br> • **Cẩn thận:** Regressor train trên dài hạn sẽ không match ngắn hạn (20–120 ngày) |
| **Khuyến nghị** | 🟡 **Phần lớn không dùng trực tiếp; học methodology (rolling window, expected schedule matching)** |

#### 2.5. **Freddie Mac Single Family Loan-Level Dataset** (Mortgage, Mỹ)

| Thuộc tính | Chi tiết |
|-----------|---------|
| **Liên kết** | [Freddie Mac Data](https://www.freddiemac.com/research/datasets/sf-loan-performance-data) (cần đăng ký free) |
| **Quy mô** | **~50 triệu loan-months** (1.2M loans × 420+ tháng) |
| **Cột thanh toán** | `Monthly_Reporting_Period` (tháng báo cáo), `Current_Loan_Delinquency_Status` (0=on-time, 1-11=tháng trễ), `Historical_Coupon` (lãi suất) |
| **Domain** | ❌ **Mortgage (bất động sản), không phải B2B** — kỳ hạn 30 năm, payment fixed |
| **Label** | Monthly delinquency: `Current_Delinquency_Status ∈ {0,1,2,..,11}` = tháng trễ bao nhiêu |
| **Ưu điểm** | **Quá lớn** (50M rows), many years (2003–present), stable |
| **Hạn chế** | Kỳ hạn siêu dài (360 tháng), payment cố định → không giống hóa đơn B2B |
| **Adaptation** | ❌ **Khó** — monthly pattern không áp dụng cho "day-to-payment" (20–120 ngày). Chỉ có thể học *concept* delinquency bucket nhưng không applicable. |
| **Khuyến nghị** | ❌ **Không khuyến nghị cho T1** |

#### 2.6. **SBA 7(a) & 504 Loan Data** (US Small Business Admin)

| Thuộc tính | Chi tiết |
|-----------|---------|
| **Liên kết** | [Kaggle SBA Loans](https://www.kaggle.com/datasets/mirbektuncer/sba-loans) hoặc [SBA.gov direct](https://www.sba.gov/about-sba/what-we-do/history-archives/sba-7a-historical-data) |
| **Quy mô** | ~900K loans, ~50 features, 1990–2014 |
| **Cột chính** | `DisbursementDate` (ngày giải ngân), `ApprovalFiscalYear`, `Term` (kỳ hạn tháng), `Status` (PIF=Paid in Full, CHGOFF=Charged Off, CANCLD=Cancelled) |
| **Domain** | 🟡 **B2B adjacent** — doanh nghiệp nhỏ (SME), nhưng là khoản vay dài hạn (không phải hóa đơn 30–120 ngày) |
| **Label** | Binary: `Status == 'PIF'` vs `Status == 'CHGOFF'`; không có "ngày trả thực tế" → **không phải T1** |
| **Ưu điểm** | Domain SME gần; nhiều feature nhân khẩu doanh nghiệp |
| **Hạn chế** | Không có dữ liệu payment-level (ngày trả), chỉ trạng thái cuối cùng sau vài năm |
| **Adaptation** | ❌ **Không phù hợp T1** — chỉ phù hợp T2 (PD/default) hoặc T11 (backtest) |
| **Khuyến nghị** | **Dùng cho T2 không phải T1** |

#### 2.7. **Bondora P2P Loan Data** (Estonia)

| Thuộc tính | Chi tiết |
|-----------|---------|
| **Liên kết** | [Kaggle Bondora](https://www.kaggle.com/datasets/bondora/bondora-ld-dataset) hoặc [Bondora.com Research](https://www.bondora.com/research) |
| **Quy mô** | ~200K khoản vay; 2009–2020 |
| **Cột** | `LoanDate`, `MaturityDate_Original`, `MaturityDate_Last`, `LastPaymentOn`, `LoanStatus` |
| **Domain** | ❌ **P2P consumer, không phải B2B** — kỳ hạn cố định (5 năm), monthly payment |
| **Label** | Status: Repaid, Late, Defaulted, Current; có time-to-repayment |
| **Adaptation** | 🟡 **Có thể học** — structure tương tự (issue → maturity → actual payment), nhưng kỳ hạn lâu |
| **Khuyến nghị** | 🟡 **Phần lớn feature engineering ideas; không dùng model trực tiếp** |

#### 2.8. **Online Retail II** (UCI ML Repository)

| Thuộc tính | Chi tiết |
|-----------|---------|
| **Liên kết** | [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii) |
| **Quy mô** | ~1 triệu giao dịch; 2009–2011 (2 năm) |
| **Cột** | `InvoiceDate`, `InvoiceNo`, `CustomerID`, `Quantity`, `UnitPrice`, `Country` |
| **Domain** | ❌ **Retail B2C, không phải B2B** — online store, payment tức thời hoặc credit card |
| **Label** | Không có payment date → **không phù hợp** |
| **Adaptation** | ❌ **Không** |
| **Khuyến nghị** | ❌ **Không khuyến nghị cho T1** |

---

## 3. Tóm tắt: Dataset nào dùng cho T1?

| Dataset | Quy mô | Domain | Phù hợp T1? | Ghi chú |
|---------|--------|--------|:---:|---|
| **SAP (project)** | 50K | B2B (Mỹ) | ✅ **BEST** | Dùng ngay để train baseline |
| **Favorita** | 125M | Retail B2C | ❌ | Không có due_date / payment terms |
| **Olist** | 100K | Retail B2C | 🟡 | Học feature patterns; rò rỉ label |
| **Home Credit installments** | 13M | Consumer P2P | 🟡 | Khó domain shift (cá nhân → B2B, fixed kỳ → flex) |
| **LendingClub** | 2.2M | Consumer P2P | 🟡 | Kỳ hạn dài; learn schedule matching |
| **Freddie Mac** | 50M | Mortgage | ❌ | Kỳ hạn siêu dài (30 năm); monthly pattern |
| **SBA 7(a)** | 900K | B2B SME | ❌ | Không có payment date; dùng cho T2 |
| **Bondora** | 200K | Consumer P2P | 🟡 | Học methodology; kỳ hạn lâu |
| **Online Retail II** | 1M | Retail B2C | ❌ | Không có payment tracking |

---

## 4. Chiến lược sử dụng từng bộ data

### ✅ **Chiến lược 1: Dùng SAP project data + transfer learning từ Home Credit / LendingClub** (Khuyến nghị)

1. **Train T1 baseline trên SAP** (~50K invoices)
   - Direct LightGBM quantile regression
   - CQR calibration
   - Target: `days_late = clear_date - due_date`

2. **Làm phong phú feature bằng Home Credit patterns**
   - Cách aggregation: rolling median, rolling percentile per customer
   - Cách handling payment terms: `remaining_days_at_T`, `observed_age_days`
   - Recency weighting: exponential decay cho dữ liệu cũ
   - **Không dùng mô hình Home Credit trực tiếp**, chỉ extract feature engineering recipes

3. **Validation strategy**
   - Rolling-origin backtest trên SAP (tuần 1–4 train, tuần 5 test; rồi dịch cửa sổ)
   - Không shuffle → respect temporal order
   - Measure: MAPE, calibration (Brier score)

### 🟡 **Chiến lược 2: Pre-train trên LendingClub, fine-tune trên SAP** (Advanced)

```python
# Stage 1: Pre-train trên LendingClub (2.2M)
lgb_pretrain = LGBMQuantileRegressor(
    n_estimators=1000, 
    target_column='days_late_at_month_X'  # Mỗi kỳ là 1 row
)
lgb_pretrain.fit(X_lendingclub, y_lendingclub)

# Stage 2: Fine-tune trên SAP (50K)
lgb_final = LGBMQuantileRegressor(
    n_estimators=200,
    learning_rate=0.01
)
lgb_final.fit(X_sap, y_sap, init_model=lgb_pretrain)
```

**Cạm bẫy:**
- LendingClub kỳ hạn dài → early stopping có thể trigger sớm
- **Phải kiểm tra:** Feature distribution (domain shift)
  ```python
  psi = calculate_psi(X_lendingclub, X_sap)  # Nếu PSI > 0.2 → domain shift lớn
  ```
- Calibration cần retrain trên SAP alone

### ❌ **Chiến lược 3: Dùng Favorita / Olist / Freddie trực tiếp** (Không khuyến nghị)
- Mất thời gian vì domain shift quá lớn
- Không có `due_date` → phải tự sinh → rò rỉ label
- Feature không match

---

## 5. Adaptation checklist — khi dùng data khác domain

Trước khi train trên data ngoài domain, **PHẢI check:**

### ❌ **Data leak?**
```python
# Cảnh báo: feature lộ label
if 'actual_payment_date' in features:
    raise ValueError("Rò rỉ label!")
```

### ❌ **Domain shift quá lớn?**
```python
from scipy.stats import ks_2samp

# KS test: so sánh distribution
for col in features:
    stat, p_value = ks_2samp(X_pretrain[col], X_finetune[col])
    if p_value < 0.05:
        print(f"{col}: domain shift detected (p={p_value})")
        
# PSI test (Population Stability Index)
psi = sum(
    (p_finetune[col] - p_pretrain[col]) * ln(p_finetune[col] / p_pretrain[col])
    for col in features
)
if psi > 0.2:
    print(f"PSI={psi} > 0.2: HIGH domain shift")
```

### ❌ **Temporal leakage?** (train set có dữ liệu từ test period)
```python
# Cảnh báo: train date > test date
assert max(X_train['cutoff_date']) <= min(X_test['cutoff_date'])
```

### ❌ **Imbalanced label?**
```python
# Cảnh báo: quá nhiều on-time vs late
print(f"On-time: {(y_train == 0).sum()}; Late: {(y_train == 1).sum()}")
if imbalance_ratio > 10:
    print("Severe imbalance — cần reweighting or SMOTE")
```

### ✅ **Feature engineering pattern mất hiệu lực?**
Ví dụ: Home Credit có `NUM_INSTALMENT_NUMBER` (kỳ 1/2/3...) → fixed payment schedule.  
SAP hóa đơn không có → phải tạo synthetic feature như `invoice_sequence_within_customer`.

---

## 6. Đẩu quy vào hạn chế: Giải pháp cho T1

| Vấn đề | Nguyên nhân | Giải pháp |
|--------|-----------|----------|
| **Dataset SAP nhỏ (50K)** | Chỉ 1 khách hàng, 2 năm | Transfer learning từ LendingClub; Synthetic data (T12); Xin khách thêm data |
| **Không có feature khách** | SAP raw có `customer_id` nhưng không giải thích | Tìm tiền sử (rolling_snapshot_features.csv đã có 78 feature) |
| **Không có macro feature** | Freddie/SBA có nhưng SAP không | Blend FRED macro (CPI, unemployment rate US) by date |
| **Domain shift LendingClub** | Kỳ hạn khác (dài), payment cố định | Retrain calibration; Check PSI weekly |
| **Dữ liệu Mỹ ≠ VN** | Currency, business culture, regulation | Dùng chỉ để learn methodology; **MUST fine-tune trên VN data sau** |

---

## 7. Link tải & hướng dẫn

| Dataset | Link | Cách tải | Format |
|---------|------|---------|--------|
| **SAP (project)** | Local: `data/dataset.csv` | Đã có | CSV |
| **Home Credit** | [Kaggle](https://www.kaggle.com/competitions/home-credit-default-risk) | Đăng ký free Kaggle + `kaggle competitions download` | ZIP (~7GB unpacked) |
| **LendingClub** | [Kaggle](https://www.kaggle.com/datasets/wordsforthewise/lending-club) | Free; hoặc [direct](https://www.lendingclub.com/info/download-data.action) | CSV (~1GB) |
| **Freddie Mac** | [Official](https://www.freddiemac.com/research/datasets/sf-loan-performance-data) | Đăng ký free → FTP link | Text (~50GB compressed) |
| **SBA** | [Kaggle](https://www.kaggle.com/datasets/mirbektuncer/sba-loans) hoặc [SBA.gov](https://www.sba.gov/about-sba/what-we-do/history-archives/sba-7a-historical-data) | Free | CSV |
| **Bondora** | [Kaggle](https://www.kaggle.com/datasets/bondora/bondora-ld-dataset) | Free | CSV |
| **Olist** | [Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) | Free | ZIP (5 CSV) |

---

## 8. Kết luận: T1 cần dữ liệu gì?

**Dùng ngay:** `data/dataset.csv` từ project (đủ train baseline).

**Transfer từ đâu:**
- **Best:** Home Credit installments (cấu trúc payment schedule tương tự)
- **Backup:** LendingClub (lớn, nhiều feature)
- **Research only:** Freddie (quá lớn, quá lâu)

**Không dùng:** Favorita, Olist, Online Retail II, Freddie mortgage (quá khác domain).

**Tiếp theo:** Nếu muốn model production-ready, **PHẢI xin khách data AR thực (T13)** — không có dataset công khai nào capture "trade credit B2B VN" đầy đủ.

---

**Sources:**
- [Kaggle Competitions](https://www.kaggle.com/competitions)
- [Kaggle Datasets](https://www.kaggle.com/datasets)
- [SBA Historical Data](https://www.sba.gov/about-sba/what-we-do/history-archives/sba-7a-historical-data)
- [Freddie Mac Data](https://www.freddiemac.com/research/datasets/sf-loan-performance-data)
- [UCI ML Repository](https://archive.ics.uci.edu/dataset/502/online+retail+ii)
