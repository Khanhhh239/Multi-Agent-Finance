# 4. Máy phát dữ liệu tổng hợp SME Việt Nam (T12)

Mã: `agent1/synth/world.py` (+ `names.py`, `einvoice.py`, `fidelity.py`, `agent1/calendar_vn.py`).
Dựng: `scripts/build_worlds.py`. Đây là **mô phỏng tác tử có cấu trúc nhân quả**, không phải bộ lấy mẫu độc lập từ các
phân phối biên — thì mới tạo được tương quan thật (cùng sốc thanh khoản, cùng chạy lương, cùng Tết).

## 4.1 Kiến trúc: sáu lớp sinh theo thứ tự nhân quả

```
L0 Lịch + vĩ mô   → nhân tố thanh khoản chung F_w, sốc COVID (OxCGRT VN), sốc tín dụng 2022–23, Tết, nghỉ lễ
L1 Công ty        → ngành, quy mô, lương, đệm tiền, thói quen ghi sổ, mức đòi nợ
L2 Khách hàng     → điều khoản, kỷ luật trả, đuôi trễ, ngày chạy thanh toán, độ nhạy sốc, điểm gãy
L3 Hoá đơn        → doanh thu tuần có mùa vụ/Tết → số hoá đơn, giá trị, ngày lập, VAT 8/10%
L4 Thanh toán     → thời điểm trả (đúng hạn/trễ/cực trễ/tranh chấp/một phần/vỡ nợ)
L5 Quan sát       → sao kê ngân hàng, sổ cái (nhiễu lô), lời hứa trả, chi cố định, số dư tiền
```

Mỗi lớp lưu **cả thuộc tính tiềm ẩn (nhãn gốc)** lẫn **thuộc tính quan sát được** — để đánh giá được cả khả năng suy
ra thuộc tính tiềm ẩn từ quan sát.

## 4.2 L0 — Lịch và vĩ mô

| Thành phần | Quy tắc | Nguồn |
|---|---|---|
| Nhân tố thanh khoản chung `F_w` | AR(1) hệ số 0,93; nhiễu **Student-t df=4** chuẩn hoá, hệ số 0,22/tuần | df=4 là *giả định* — T6 cần ước lượng từ SEC (chưa làm) |
| Sốc COVID | `s = clip((StringencyIndex−55)/35, 0, 1) × (0,5 + 0,25·C6M)` theo tuần từ **OxCGRT Việt Nam thật** | OxCGRT |
| Đóng băng tín dụng 10/2022–06/2023 | Gauss đỉnh tuần thứ 16 sau 01/10/2022, độ rộng 9 tuần | giả định theo bối cảnh TPDN/BĐS |
| Tết | Mùng 1 và kỳ nghỉ chính thức 2018–2027 (có nghỉ bù/hoán đổi); dồn trả trước, đóng băng trong kỳ nghỉ, khởi động chậm sau | `calendar_vn.py` |
| Ngày nghỉ | python-holidays (VN) ∪ kỳ nghỉ Tết | holidays 0.106 |
| Lãi suất vay | WDI `FR.INR.LEND` theo năm (mặc định 8% nếu thiếu) | WDI |

## 4.3 L1 — Công ty

| Thuộc tính | Phân phối | Ghi chú |
|---|---|---|
| Ngành | 6 ngành: thép–kim loại, dệt may, nhựa–cao su (3 ngành Atradius), bán buôn, chế biến thực phẩm, dịch vụ (3 ngành sau dùng số toàn mẫu làm tiền nghiệm) | tỷ lệ ngành theo cấu hình thế giới |
| Doanh thu năm | logNormal, trung vị 40 tỷ (src), 20 tỷ (tgt), σ=0,8, kẹp [3 tỷ, 600 tỷ] | giả định; nên thay bằng phân bố từ UNU-WIDER/Tổng điều tra |
| Số lao động | doanh thu ÷ (doanh thu/lao động ngành × e^{N(0,0,3)}) | |
| Hệ số lương | U(1,5; 2,6) × lương tối thiểu vùng | |
| Vùng lương | I 45%, II 30%, III 15%, IV 10% | |
| Biên lợi nhuận | N(4,5%; 2,5%) kẹp [−1%; 12%] | |
| Tăng trưởng | N(7%; 8%)/năm | |
| Thuê, vay | thuê = doanh thu×U(0,4;1,2)%/12; vay gốc = doanh thu×U(0; 25%), trả lãi theo WDI | |
| **Đệm tiền mặt đầu kỳ** | logNormal(ln 27, σ=1,08) *ngày chi* | khớp trung vị 27 ngày, phần tư dưới ≈ 13 ngày (JPMorgan Chase Institute) |
| Ghi sổ | hằng ngày 45% / hằng tuần (thứ Sáu) 30% / cuối tháng 25% | giả định (tgt: 25/35/40) |
| Cường độ đòi nợ | U(0,25; 0,8) | quyết định số lời hứa ghi nhận |
| Ngày lương | 5 (25%), 10 (45%), cuối tháng (20%), 15 (10%); 80% trả lương tháng trước vào tháng sau | |
| Rút lợi nhuận | quý cuối: nếu số dư > max(60 ngày chi, 1,5×đệm) thì rút về mức đệm | để thiếu hụt chỉ xảy ra khi có sốc, không trôi lên vô hạn |

## 4.4 L2 — Khách hàng (đơn vị hành vi)

Số khách/công ty: logNormal(trung vị 60, σ=0,6) kẹp [8, 400]. Trọng số doanh thu Pareto(α=1,5)+1 → top-10 khách chiếm
≈54% (src), ≈70% (tgt). Thời gian quan hệ: 55% có từ đầu, còn lại bắt đầu ngẫu nhiên; tuổi thọ ~Exp(6 năm)+180 ngày.

| Thuộc tính | Phân phối / quy tắc | Ý nghĩa |
|---|---|---|
| Kỳ hạn | rời rạc theo ngành (ví dụ thép: 15/30/45/60/90 = 6/38/30/20/6%); khách nhỏ có xác suất COD (kỳ hạn 0) cao hơn | kỳ hạn là biến rời rạc, không liên tục |
| Kỷ luật trả | `on-time base ~ Beta(2,4; 1,5)` → logit + **độ lệch hiệu chỉnh theo ngành** | tham số hiệu chỉnh tự động (§4.8) |
| Trễ trung vị | logNormal quanh trung bình hình học của khoảng đuôi (σ=0,55 trên log) | đuôi `atradius` 18–36 ngày; `uk` 8–20; `coface` 30–60 |
| Độ phân tán trễ | `σ_log ~ U(...)` theo đuôi | |
| P(trễ cực dài) | `ultra_p = P_tail × logNormal(0; 0,8)`; trễ cộng 90 + 60·Pareto(2,2) ngày | Coface: 3% (src atradius 0,6%) |
| Ngày chạy thanh toán | 10 mẫu: tuỳ hứng 34%; thứ 2/3/4/5 cố định; ngày 10 & 25; 5 & 20; 15 & cuối tháng; cuối tháng; 25 | **thói quen** giúp đặc trưng "ngày chạy rơi vào tuần k" |
| Độ nhạy sốc chung | `β_F ~ U(0,3; 1,6)` | khách nhạy với thanh khoản thị trường |
| Độ bền thanh khoản | `ρ ~ U(0,85; 0,97)` (AR(1) tuần) | |
| Dễ vỡ nợ | `pd_frailty ~ logNormal(−0,4; 0,9)` | |
| Tranh chấp | `logNormal(ln 1,2%; 0,7)` | tiền nghiệm ~1,2%/hoá đơn (UK PPR trung vị 0% nên không dùng làm đích) |
| Trả một phần | `Beta(1; 12)` (trung bình 7,7%) | |
| Trả theo lô | 55% khách gộp nhiều HĐ cùng ngày thành 1 lệnh chuyển | |
| Ghi số HĐ trong CK | `Beta(2;2)` (tgt: Beta(1,5; 3)) | quyết định độ khó khớp sao kê |
| Độ tin cậy lời hứa | `Beta(4; 2)` | |
| Chốt nợ trước Tết | `Beta(3; 3)` | |
| Gộp HĐ cuối tháng | 12% khách có kỳ hạn | |
| **Điểm gãy** | 10% khách: từ ngày U(200, cuối) mọi HĐ chậm thêm U(8; 25) ngày × U(0,6; 1,4) | nhãn T7 |
| Ticket | `ticket_ngành × (w·n)^0,35 × logNormal(0; 0,4) × (doanh thu/40 tỷ)^0,5` | |

### Thanh khoản và vỡ nợ của khách

```
idio_c,t  : AR(1) phương sai 1, hệ số ρ_c
L_c,t = (idio_c,t + β_c · F_t / sd(F)) / sqrt(1 + β_c²)  −  1,2 · β_c · S_t,   S_t = covid_sens·covid_t + crunch_sens·crunch_t
hazard tuần  h_c,t = h0_ngành · frailty_c · exp(0,7·max(−L_c,t, 0) + 1,0·S_t)   (kẹp 0,2; 0 trong 26 tuần đầu quan hệ)
h0_ngành = 1 − (1 − 0,06·pd_mult·bad_ngành/0,03)^{1/52}
```

Khách vỡ nợ **ngừng phát sinh hoá đơn 14 ngày trước** sự kiện (DN ngừng bán chịu). `pd_mult` là hệ số hiệu chỉnh tự động.

## 4.5 L3 — Hoá đơn

- **Doanh thu tuần** `R_t = (doanh thu/52)·e^{g·t/52}·mùa_vụ_ngành[tháng]·hệ_số_Tết·e^{AR(1)}·(1 − 0,6·covid_sens·covid_t)·(1 − 0,35·crunch_sens·crunch_t)`.
  Hệ số Tết theo tuần: −2: ×1,15; −1: ×1,25; tuần nghỉ: ×0,35; tuần cuối nghỉ: ×0,45; +1: ×0,7.
  Mùa vụ theo ngành (12 hệ số/ngành), ví dụ thép đỉnh tháng 12 (1,4), đáy tháng 7 (0,8).
- **Số hoá đơn** khách c tuần t ~ Poisson(`share_c · R_t / ticket_c`); **giá trị** `ticket_c · logNormal(0; 0,75)`, làm tròn 1.000đ.
- **Ngày lập**: thứ 2–6 mỗi ngày 19%, thứ 7 5% (60% được giữ); không lập vào ngày nghỉ lễ; khách gộp cuối tháng dồn về ngày làm việc cuối tháng.
- **VAT**: 10%; 8% khi nằm trong các đợt giảm thuế (trừ ngành kim loại). Số hoá đơn đánh theo ký hiệu năm (`C25TAA`),
  MST hợp lệ (chữ số kiểm tra), tên pháp nhân kiểu VN.

## 4.6 L4 — Thanh toán (cốt lõi)

Với mỗi hoá đơn, theo thứ tự:

1. **Đúng hạn?** `logit = ontime_logit_c + 0,6·L_c(due) − 1,2·S(due)`.
2. **Sớm**: nếu đúng hạn và `early_p` → trả sớm `U(0,2; 0,9)×min(kỳ hạn, 40)` ngày; ngược lại trả 0–3 ngày trước hạn.
3. **Trễ**: `exp(log(med_c · e^{−0,25 L}·(1 + 0,8 S)) + σ_c·N(0,1)) + 1` ngày; **cực trễ** (xác suất `ultra_p·(1+2S+max(−L,0))`).
4. **Điểm gãy riêng khách**, **tranh chấp** (+U(15,75) ngày, 60% có giảm trừ 5–30% giá trị), **COD** (0–3 ngày).
5. **Suy giảm trước vỡ nợ**: HĐ đáo hạn trong 120 ngày trước sự kiện chậm thêm U(10,40) ngày.
6. **Bám lịch trả của khách**: nếu "đúng hạn" → ngày chạy thanh toán gần nhất *trước* hạn (nếu còn sau ngày lập, ≤16 ngày); ngược lại ngày chạy kế tiếp; luôn dịch về ngày làm việc.
7. **Tết**: nếu hạn rơi vào cửa sổ Tết, với xác suất `tet_settle_p·clip(1+L, 0,2; 1,5)·0,6` chốt trước kỳ nghỉ 1–6 ngày; ngược lại nếu rơi sau kỳ nghỉ thì lùi 0–5 ngày.
8. **Thứ Bảy** (Napas 24/7): 1,2% lệnh chuyển về thứ Bảy.
9. **Vỡ nợ**: HĐ chưa trả khi khách vỡ nợ → nợ xấu; thêm 12% HĐ tranh chấp không giải quyết → xoá nợ; **25%** nợ xấu thu hồi
   20–50% sau 120–360 ngày; ngày xoá sổ sau 180–400 ngày.
10. **Trả một phần**: xác suất `partial_p·(1 + 1,5·max(−L,0))` (kẹp 0,6): đợt 1 = 30–70% (làm tròn), đợt 2 sau 10–45 ngày,
    15% số đợt 2 trả thiếu 1–10%.

## 4.7 L5 — Quan sát: sao kê, sổ cái, lời hứa, chi

**Sao kê ngân hàng.** Mỗi lệnh chuyển có `value_date`, `amount` (trừ phí 11.000/22.000đ ở 5% giao dịch), `counterparty`
(không dấu, viết tắt, cắt 50 ký tự, 4% để trống) và `memo` kiểu VN:
`MBVCB.123456.654321.CTY ABC TT HD 123,124` · `FT12345ABCDE ...` · `{TÊN} THANH TOAN TIEN HANG` ·
`HD{số}` …; tỷ lệ ghi số HĐ theo khách (`Beta(2,2)`), số HĐ bỏ số 0 đầu 45% số lần, tối đa 5 HĐ/lệnh, 4% có lỗi gõ,
cắt 70/140/210 ký tự. Thêm giao dịch nhiễu (12% số giao dịch + 24/công ty): lãi, nộp tiền mặt, chuyển nội bộ, hoàn cọc,
giải ngân vay, "CK" không rõ.

**Sổ cái (nhiễu lô, W1).** Ngày ghi sổ: hằng ngày (+0–1 ngày 90%, +2–5 ngày 10%) / thứ Sáu hằng tuần / cuối tháng
(30% sang tháng sau 0–3 ngày). Khi không hằng ngày, 50% khách có **phân bổ FIFO sai**: các ngày ghi sổ được gán cho hoá
đơn theo thứ tự lập. Kết quả: ngày ghi sổ lệch ngày tiền về trung bình 12,6 ngày (tgt).

**Lời hứa trả (T8).** Tại mốc 7/21/45/75 ngày sau hạn, với xác suất = cường độ đòi nợ của công ty, ghi lời hứa: nếu khách
"giữ lời" (xác suất = độ tin cậy) và còn ≤60 ngày nữa mới trả → ngày hứa = ngày trả thật + N(0; 1,5); ngược lại ngày hứa
sớm hơn thực tế (lời hứa không thực hiện). Lời hứa được giữ khi |hứa − thật| ≤ 3 ngày.

**Chi (T5, qua `calendar_vn.py`).** NCC (mua trước bán 2 tuần, giá vốn = 1 − biên − 1,3×tỷ lệ lương − chi phí chung; kỳ hạn NCC
{0,15,30,45,60}; ngày chạy chi theo 4 mẫu); lương ròng (gross × 89,5%), BHXH (32%) hạn cuối tháng; VAT (tháng nếu
doanh thu >50 tỷ, quý nếu không; hạn 20 tháng sau / cuối tháng đầu quý sau, dịch ngày nghỉ); TNDN tạm nộp (20% × biên ×
doanh thu quý, hạn 30 tháng đầu quý sau); môn bài 30/01 (bỏ từ 2026); thuê; lãi vay; tiện ích; thưởng tháng 13 trước Tết;
capex bất thường ~Poisson(1,5/năm). Các ngày đều dịch về ngày làm việc.

**Số dư.** `balance = đệm + Σ(thu − chi) − rút lợi nhuận` mỗi ngày → ground truth T6.

## 4.8 Hiệu chỉnh tự động (`scripts/build_worlds.py::calibrate`)

Vòng lặp 5 lần × 24 công ty: sinh thế giới `calib`, đo tỷ trọng **theo giá trị** (đúng hạn / quá hạn / nợ xấu) từng ngành, rồi
`shift_ngành += 0,8·(logit(đích) − logit(đạt))` và `pd_mult *= (đích/đạt)^0,8`. Đích: quá hạn và nợ xấu theo ngành của
Atradius (thép 35/2%, dệt 34/4%, nhựa 47/4%; ngành còn lại 39/3%). Kết quả: `data/synthetic/calibration_fit.json`.
Sai số còn lại (xem `docs/DATA_CARD.md`): đúng hạn 54–57% (đích 58%), nợ xấu 3,2–3,8% (đích 3%).

## 4.9 Giả định không có nguồn (phải kiểm chứng ở T13)

| Giả định | Rủi ro nếu sai | Cách kiểm |
|---|---|---|
| Hình dạng đuôi trễ (3 lựa chọn) | Khoảng dự báo lệch | Chạy cả 3 (`sens_*`), báo cáo độ nhạy |
| df=4 của sốc chung | Đuôi thiếu hụt sai | Ước lượng từ SEC |
| Tỷ lệ ghi sổ theo lô, FIFO sai | Tác hại nhãn bị phóng đại/thu nhỏ | Khảo sát văn phòng kế toán |
| Độ tin cậy lời hứa Beta(4,2) | Giá trị T8 | Thu thập thật |
| Khách đồng nhất hơn thật (phương sai do khách 0,20 vs 0,60 ở bộ ERP tham chiếu) | Mô hình tổng hợp đánh giá thấp lợi ích đặc trưng khách | Tăng dị biệt giữa khách (kế hoạch 05) |
| ~50% hoá đơn là COD (theo số lượng; 41% theo giá trị) | Quá nhiều hoá đơn tức thời | Giảm `cod_mult`, hiệu chỉnh đúng tỷ trọng theo số lượng |
