# T2 — Khả Năng Trả Và Vỡ Nợ: Ghi Chú Nghiên Cứu


**Mục tiêu:** Dự báo **khả năng vỡ nợ** (probability of default — PD) cho từng hoá đơn / từng khách hàng B2B.
Input: thông tin khách hàng + lịch sử thanh toán + macro.
Output: P(default) tại mỗi thời điểm, có calibration và khoảng tin cậy.
---


## 1. Thực tế doanh nghiệp Việt Nam hiện nay


### 1.1. Cách SME quản lý rủi ro vỡ nợ hiện tại


| Phương pháp | Ai dùng | Hạn chế |
|---|---|---|
| **Aging report** (0-30, 31-60, 61-90, 91-180, >180 ngày) | >70% SME, qua Excel hoặc MISA/FAST | Phản ứng muộn — DN biết khách *đã* trễ, không biết khách *sẽ* trễ |
| **Hạn mức tín dụng nội bộ** (ngưỡng tĩnh, ví dụ VIP 500 triệu) | DN lớn hơn (VinGroup, FPT, THACO) | Rule-based thủ công, không có PD scoring định lượng |
| **Tra CIC** (Trung tâm Thông tin Tín dụng Quốc gia) | Ngân hàng bắt buộc; B2B gần như chưa dùng | Chi phí mỗi lần tra không rẻ, quy trình chưa thân thiện SME |


### 1.2. Khung pháp lý hiện hành


| Văn bản | nội dung chính |
|---|---|
| **Thông tư 48/2019/TT-BTC** | Hướng dẫn kế toán DN nhỏ và vừa — tỷ lệ trích lập dự phòng theo tuổi nợ |
| **Thông tư 11/2021/TT-NHNN** | Phân loại nợ ngân hàng (5 nhóm: từ đủ tiêu chuẩn → có khả năng mất vốn), tiêu chí chính là số ngày quá hạn |
| **Thông tư 41/2016/TT-NHNN** (Basel II) | Yêu cầu ngân hàng xây dựng mô hình PD, LGD, EAD theo IRB |
| **IFRS 9 / Thông tư 03/2023/TT-BTC** | ECL 3 bước (PD × LGD × EAD) — mới áp dụng cho DN niêm yết, SME chưa bắt buộc |


### 1.3. Cách ngân hàng làm PD (IRB / Basel II)


Ngân hàng TMCP (Agribank, BIDV, VCB) xây dựng mô hình rating nội bộ:
- **PD model**: logistic hoặc scorecard, input gồm lịch sử nợ, tỷ lệ đòn bẩy, doanh thu, ngành nghề
- **CIC score**: bắt buộc tra trước khi cấp tín dụng, nhưng **hoàn toàn vô dụng cho B2B trade credit** — đây là khoảng trống lớn nhất mà dự án T2 nhắm vào


### 1.4. Hạn chế cốt lõi → cơ hội cho T2


| Hạn chế | Hệ quả |
|---|---|
| **Backward-looking hoàn toàn** — aging chỉ phản ánh quá khứ | Phản ứng muộn, tăng tỷ lệ mất nợ thật |
| **Aging buckets quá thô** — 90 ngày vs 91 ngày nằm cùng nhóm nhưng rủi ro rất khác | Classification loss, provisioning sai |
| **Không có forward-looking macro** — không link GDP, PMI, lãi suất | Không phân biệt được rủi ro systemic vs idiosyncratic |
| **CIC chỉ phục vụ ngân hàng**, B2B trade credit không có bureau | Khoảng trống rất lớn cho PD scoring trong thương mại |
| **Dữ liệu lịch sử nợ xấu SME rất ít** (thường <5% default rate) | Sample imbalance nghiêm trọng |


---


## 2. Phương pháp chuẩn (Baseline)


### 2.1. Binary classification — Logistic Regression / LightGBM


**Baseline chấp nhận được trong thực tế 2024–2026:**
- Logistic regression: interpretable, regulatory acceptance (Basel II/IFRS 9)
- LightGBM: thường cải thiện AUC 3–8% trên benchmark credit scoring (Butaru et al., 2016; Xia et al., 2017)


**Label definition (cho SBA / Home Credit):**
- SBA: `default` = charged off hoặc >60 ngày quá hạn trong 12 tháng đầu
- Home Credit: `default` = có payment difficulty trong bất kỳ installment nào
- **Cho VN**: `default` = quá hạn >90 ngày hoặc write-off (theo Thông tư 48)


### 2.2. Calibration — quan trọng không kém discrimination


> **Cảnh báo (da Silva & Alvares, 2026):** Nhiều mô hình survival-ML "fails a formal calibration test at p < 0.001" dù C-index tốt. Discrimination ≠ Calibration.


```python
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.metrics import brier_score_loss


# Platt Scaling (sigmoid) — tốt khi mẫu nhỏ
calibrated = CalibratedClassifierCV(model, method='sigmoid', cv=5)
calibrated.fit(X_train, y_train)


# Isotonic — tốt khi mẫu lớn hơn
calibrated_iso = CalibratedClassifierCV(model, method='isotonic', cv=5)


# Đánh giá calibration
prob_true, prob_pred = calibration_curve(y_test, proba, n_bins=10)
brier = brier_score_loss(y_test, proba)  # target: < 0.1
```


### 2.3. Đánh giá


| Metric | Ý nghĩa | Target |
|---|---|---|
| AUC-ROC | Khả năng phân biệt default / non-default | > 0.80 |
| Brier Score | Độ chính xác xác suất (calibration) | < 0.10 |
| Recall @ specificity 0.95 | Phát hiện bao nhiêu % default thực sự khi false alarm ≤ 5% | > 0.60 |
| PSI (Population Stability Index) | Đo concept drift theo thời gian | < 0.10 stable |
| Rolling-origin backtest | Chia theo thời gian, không shuffle | — |


---


## 3. Cải tiến hiện đại (2024–2026)


### 3.1. Discrete-Time Hazard Model — thay thế binary classification


Đây là **cải tiến quan trọng nhất** cho PD term-structure theo IFRS 9. Thay vì predict binary default tại một horizon cố định, survival model ước tính **hazard rate** tại mỗi kỳ, cho phép xây dựng PD curve.


**Tham khảo mới nhất:**
- Botha & Verster (2025): tutorial discrete-time hazard model cho lifetime PD dưới IFRS 9 ([arXiv:2507.15441](https://arxiv.org/abs/2507.15441))
- Botha et al. (2026): so sánh discrete-time hazard với survival tree và logistic, nhúng vào two-stage LGD framework ([arXiv:2603.11897](https://arxiv.org/abs/2603.11897))
- Lee & Lee (2025): behavioral scorecard using monthly hazard-rate model ([arXiv:2503.05023](https://arxiv.org/abs/2503.05023))


Dưới đây là tóm tắt 4 bước cốt lõi định hình mô hình này:


**1. Ý tưởng trọng tâm: Hazard Rate**
Thay vì dự báo một cục cho 12 tháng, mô hình đi tìm $h(t)$: **Xác suất khách hàng vỡ nợ tại đúng tháng $t$**, với điều kiện bắt buộc là họ đã "sống sót" (trả nợ tốt) cho đến hết tháng $t-1$.


**2.Person-Period format**
Để các thuật toán như LightGBM hiểu được yếu tố thời gian, một hóa đơn/khoản vay sẽ được nhân bản thành nhiều dòng, mỗi dòng đại diện cho một kỳ (period).


* Tháng 1: Sống sót $\rightarrow$ Nhãn `0`
* Tháng 2: Sống sót $\rightarrow$ Nhãn `0`
* Tháng 3: Vỡ nợ $\rightarrow$ Nhãn `1` (Dừng lại, không tạo dữ liệu cho tháng 4 trở đi).
Nhờ biến `period`, mô hình học được quỹ đạo suy thoái của dòng tiền.


**3. PD Curve**
Khi dự phóng tương lai cho một khoản nợ mới, mô hình thực hiện phép toán:


* Dự báo $h(t)$ liên tiếp từ kỳ 1 đến kỳ 12 (hoặc xa hơn).
* Quy đổi thành Xác suất sống sót từng kỳ: $1 - h(t)$.
* Nhân dồn tất cả xác suất sống sót lại với nhau để ra Tỷ lệ sống sót tổng thể.
* **Xác suất vỡ nợ lũy kế (Cumulative PD) = 1 - [Tích xác suất sống sót]**.


**4. Ưu thế tuyệt đối cho IFRS 9**
Kết quả đầu ra không phải là một con số tĩnh, mà là một đường cong rủi ro liên tục. Chỉ cần xây dựng **đúng 1 mô hình**, bạn có thể lấy giá trị PD tại tháng 12 (cho Quỹ dự phòng Stage 1 - Nợ bình thường) hoặc bốc giá trị PD tại tháng 36 (cho Quỹ dự phòng Stage 2 - Lifetime PD khi khoản nợ suy giảm chất lượng), đảm bảo sự nhất quán tuyệt đối về toán học.


**Ưu điểm so với binary classification:**
- Cho PD tại **mọi horizon** (30/60/90/180 ngày) từ cùng 1 model
- Tự nhiên phù hợp IFRS 9 Stage 1 (12-month PD) và Stage 2 (lifetime PD)
- Captured được thời điểm default rõ nhất trong chu kỳ


### 3.2. Feature Engineering hiện đại


| Nhóm feature | Ví dụ | Tại sao quan trọng |
|---|---|---|
| **DSO & Aging** | `DSO_rolling_3m`, `pct_overdue_30/60/90`, `aging_bucket_current` | Behavioral signal mạnh nhất — xu hướng trả chậm hơn/nhanh hơn | -> khách hàng có kẹt tiền hay không
| **Payment behavior** | `payment_speed_trend`, `early_payment_ratio`, `avg_delay_std` | Đo độ ổn định và xu hướng | -> hành vi thanh toán và độ tin cậy 
| **Macroeconomic** | `cpi_yoy` (lạm phát), `pmi` (chỉ số quản trị mua hàng), `interbank_rate`, `vnd_usd_vol` | Forward-looking — phân biệt systemic (rủi ro toàn thị trường) vs idiosyncratic (rủi ro cục bộ) | 
| **Invoice-level** | `amount_vs_avg`, `line_items_count`, `has_contract`, `payment_terms` | Context của từng hoá đơn | -> bản thân hóa đơn này có gì quá sức hay rủi ro pháp lí hay không


### 3.3. Concept Drift & Regime Change


#### The Model Pool


* **Tập hợp mô hình ($M_1, M_2, ..., M_n$):** Sử dụng chung lõi thuật toán LightGBM Discrete-Time Hazard.
* **Đại diện chu kỳ kinh tế:** Mỗi mô hình là một "trí nhớ" được huấn luyện trên các bối cảnh vĩ mô khác nhau (bình thường, lạm phát cao, đứt gãy chuỗi cung ứng).


#### Local Region Identification


* **Clustering:** Tìm 500 - 1000 khách hàng trong quá khứ có đặc điểm tài chính và bối cảnh vĩ mô (FLI) giống hệt khách hàng đang xét.
* **Hình thành Vùng cục bộ ($\theta$):** Nhóm khách hàng này bắt buộc phải là các khoản vay đã biết kết quả (trưởng thành) hoặc đã có tín hiệu trễ hạn rõ ràng.


#### Dynamic Selection


* **Đo lường năng lực:** Đưa toàn bộ mô hình trong Hội đồng vào dự báo thử trên Vùng cục bộ $\theta$.
* **Ra quyết định:** Mô hình dự báo sát thực tế nhất sẽ chiến thắng và được dùng để vẽ Đường cong PD 12 tháng cho khách hàng mới.


### Pool Evolution


* **Giám sát định kỳ:** Đo lường độ trôi dạt (PSI) hàng tháng.
* **Xử lý "Thiên nga đen":** Nếu xuất hiện cú sốc kinh tế mới lạ khiến toàn bộ mô hình cũ dự báo sai (Brier Score đồng loạt tăng cao).
* **Cập nhật tự động (Online Learning):** Hệ thống lấy dữ liệu của cú sốc mới này để huấn luyện ra một chuyên gia mới ($M_{n+1}$) và nạp thêm vào Hội đồng để sử dụng về sau.




- **Adaptive SHAP (Shivogo, 2025)**: static SHAP "becomes unstable when concept drift occurs" — dùng reweighting hoặc online Ridge surrogates ([arXiv:2511.03807](https://arxiv.org/abs/2511.03807))


### 3.4. Conformal Prediction — khoảng tin cậy thống kê


Thay vì point estimate, output **prediction interval** với coverage guarantee:


```python
from mapie.classification import MapieClassifier


mapie = MapieClassifier(model, method='score', cv=5)
mapie.fit(X_train, y_train)
y_pred, y_set = mapie.predict(X_test, alpha=0.1)  # 90% coverage


# Nếu prediction set = {0, 1} → model không chắc chắn → flag cho human review
```


---


## 4. Dữ liệu huấn luyện & Transfer Learning


### 4.1. Đánh giá 2 bộ dữ liệu đề xuất


#### SBA Loan Data (US Small Business Administration)


| Thuộc tính | Chi tiết |
|---|---|
| Kích thước | ~900K khoản vay, ~30 features |
| Label | `MIS_Status`: Paid in Full (PIF) vs Charged Off (CHGOFF) |
| Strengths | Rất phù hợp domain SME, quy mô tương đương, label rõ ràng |
| Weaknesses | US-specific (macro, regulation, industry mix khác VN); thiếu payment-level granularity |
| Domain shift: feature mapping | US NAICS → VN ISIC/Ma ngành; US macro → VN CPI/PMI/LIBOR→SHIBOR |
| Transfer strategy | Pre-train trên SBA → fine-tune trên VN data (feature alignment cần xử lý) |


#### Home Credit Default Risk (Kaggle)


| Thuộc tính | Chi tiết |
|---|---|
| Kích thước | ~300K applications, 122 features + bureau + previous applications |
| Label | `TARGET`: 1 = paymentDifficulty, 0 = on-time |
| Strengths | Multi-table relational data (giống ERP); rich behavioral features; competition solutions rất tốt |
| Weaknesses | **Tín dụng tiêu dùng** (CSPC/POS loans), không phải B2B; default rate ~8% (cao hơn VN) |
| Domain shift | Consumer credit → trade credit; individual → corporate |
| Transfer strategy | Học feature engineering patterns (aggregation, bureau join) → áp dụng lên ERP VN |


### 4.2. Tổng hợp: điểm khác biệt cốt lõi giữa dataset công khai và bài toán VN


| Chiều | SBA | Freddie Mac | Home Credit | **B2B SME VN** |
|---|---|---|---|---|
| Borrower type | Doanh nghiệp nhỏ | Cá nhân (mortgage) | Cá nhân (consumer) | **Doanh nghiệp B2B** |
| Data granularity | Khoản vay | Khoản vay + monthly performance | Application + bureau | **Hóa đơn + payment allocation** |
| Default definition | Charged off | 60+ days delinq | Payment difficulty | **Quá hạn >90 ngày hoặc write-off** |
| Macro integration | Có sẵn | Có sẵn | Không | **Cần tự build** |
| Sample size | 900K | 30M | 300K | **Thường <10K (SME vừa)** |


### 4.3. Chiến lược Transfer Learning cho SME VN


```python
# Stage 1: Pre-train trên SBA (lớn, domain gần nhất)
pretrain_model = lgb.LGBMClassifier(n_estimators=1000, learning_rate=0.05)
pretrain_model.fit(X_sba, y_sba)


# Stage 2: Fine-tune trên SME VN dataset (nhỏ)
finetune_model = lgb.LGBMClassifier(
    n_estimators=200, learning_rate=0.01,
    min_child_samples=10
)
finetune_model.fit(X_vn, y_vn, init_model=pretrain_model)


# Stage 3: Calibrate trên VN data (quan trọng — Platt hoặc isotonic)
final_model = CalibratedClassifierCV(finetune_model, method='isotonic', cv=5)
final_model.fit(X_vn_cal, y_vn_cal)
```


### 4.4. Xử lý Class Imbalance (default rate <5%)


| Phương pháp | Ưu điểm | Khi nào dùng |
|---|---|---|
| `is_unbalance=True` trong LightGBM | Đơn giản, built-in | Luôn bật làm default |
| SMOTE + Tomek Links | Tăng mẫu minority, clean boundary | Dataset >1K samples |
| Cost-sensitive learning | Không tạo synthetic data | Mẫu rất nhỏ (<500 default cases) |
| Bayesian priors từ SBA | Thu nhỏ uncertainty | Kết hợp transfer learning |
| Focal loss | Focus vào hard cases | Khi hard-to-distinguish cases nhiều |


---


## 5. Explainability & Quy định


### 5.1. SHAP — industry standard


```python
import shap
explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_test)


# Global: feature importance
shap.summary_plot(shap_values, X_test)


# Local: giải thích từng hoá đơn cụ thể
shap.waterfall_plot(shap.Explanation(
    values=shap_values[0],
    base_values=explainer.expected_value,
    data=X_test.iloc[0]
))
# → "PD cao vì: DSO_3m = 65 ngày (cao hơn trung bình), dispute_rate = 0.15"
```


### 5.2. IFRS 9 ECL mapping


| Stage | PD requirement | Model phù hợp |
|---|---|---|
| Stage 1 (12-month PD) | PD tích lũy trong 12 tháng tới | Hazard model → PD(0, 12) |
| Stage 2 (Lifetime PD) | PD toàn bộ thời hạn hợp đồng | Hazard model → PD(0, H) |
| Stage 3 (Impaired) | PD = 100%, chỉ tính LGD | Không cần model |


### 5.3. Fairness & Bias


Zandi et al. (2026) kết luận: "the binding constraint on explanation quality is the evidence representation, not the model used" — cải thiện features/data representation quan trọng hơn đổi model architecture.


---


## 6. Ưu Điểm và Hạn Chế


### Ưu điểm
- Discrete-time hazard model phù hợp IFRS 9, cho PD term-structure
- Transfer learning từ SBA/Freddie Mac giải quyết được phần nào vấn đề mẫu nhỏ
- Calibration + conformal prediction đảm bảo xác suất đáng tin cậy
- SHAP cho giải thích từng hoá đơn cụ thể
- Tích hợp tự nhiên vào pipeline T6 Monte Carlo


### Hạn chế
- **Domain shift lớn** giữa dataset công khai (US, consumer) và B2B SME VN
- **Sample size VN rất nhỏ** — Transfer learning giúp nhưng không giải quyết hoàn toàn
- **Cần macro features** (PMI, CPI, lãi suất) — cần build pipeline riêng
- **Concept drift**: mô hình cần retrain định kỳ, PSI monitoring bắt buộc


---


## 7. Lộ Trình Triển Khai


### Phase 1 (Tuần 1–3): Baseline
- [ ] Xây dựng feature pipeline từ T0 Gold layer
- [ ] Train LightGBM binary classification baseline + Platt calibration
- [ ] Đánh giá AUC, Brier score, calibration plot trên SBA dataset
- [ ] Rolling-origin backtest


### Phase 2 (Tuần 4–6): Discrete-Time Hazard
- [ ] Chuyển đổi dataset thành hazard format (multi-row per invoice)
- [ ] Train hazard model, xây dựng PD curve function
- [ ] So sánh performance với binary baseline
- [ ] Implement isotonic calibration + PSI monitoring


### Phase 3 (Tuần 7–9): Transfer Learning & Calibration
- [ ] Pre-train trên SBA → fine-tune trên data VN (nếu có)
- [ ] Thêm macro features (PMI, CPI, lãi suất)
- [ ] Implement conformal prediction cho uncertainty interval
- [ ] SHAP explainer integration


### Phase 4 (Tuần 10–12): Production
- [ ] Tích hợp T2 output vào T6 Monte Carlo
- [ ] Real-time drift monitoring (PSI, KS test)
- [ ] A/B test: control (aging report) vs treatment (T2 model)
- [ ] Dashboard: PD alert + SHAP explanation cho kế toán


---


## 8. Tài Liệu Tham Khảo


1. **Thông tư 48/2019/TT-BTC** — Hướng dẫn kế toán DN nhỏ và vừa
2. **Thông tư 11/2021/TT-NHNN** — Phân loại nợ tổ chức tín dụng
3. **Thông tư 41/2016/TT-NHNN** — Basel II
4. **IFRS 9 / Thông tư 03/2023/TT-BTC** — Expected Credit Losses
5. Botha & Verster (2025). "Approaches for modelling the term-structure of default risk under IFRS 9." [arXiv:2507.15441](https://arxiv.org/abs/2507.15441)
6. Botha et al. (2026). "Deriving the term-structure of loan write-off risk under IFRS 9." [arXiv:2603.11897](https://arxiv.org/abs/2603.11897)
7. Lee & Lee (2025). "A Behavioral Scorecard Model Using Survival Analysis." [arXiv:2503.05023](https://arxiv.org/abs/2503.05023)
8. da Silva & Alvares (2026). "The C-index illusion: discrimination without calibration in published survival models." [arXiv:2607.19526](https://arxiv.org/abs/2607.19526)
9. Zandi et al. (2025). "A Multimodal Approach to SME Credit Scoring." [arXiv:2510.09407](https://arxiv.org/abs/2510.09407)
10. Zhang et al. (2025). "Credit Risk Analysis for SMEs Using GNN in Supply Chain." [arXiv:2507.07854](https://arxiv.org/abs/2507.07854)
11. Shivogo (2025). "Fair and Explainable Credit-Scoring under Concept Drift." [arXiv:2511.03807](https://arxiv.org/abs/2511.03807)
12. Zandi et al. (2026). "Communicating Credit Risk with Large Language Models." [arXiv:2608.17715](https://arxiv.org/abs/2608.17715)


---

