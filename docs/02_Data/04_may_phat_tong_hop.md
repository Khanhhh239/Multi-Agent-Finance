# 4. Máy phát dữ liệu tổng hợp SME Việt Nam (T12)

**Cập nhật 27/10/2026:** runner phát hành nội bộ hiện dùng RNG v3; AP nhà cung
cấp có nhóm trả ngay theo xác suất mô phỏng 20%, ngày đến hạn và ngày trả riêng;
baseline/stress được gán trước khi sinh. Cohort đã khóa và giới hạn đối chiếu
SME thực được ghi ở [báo cáo 23](23_BO_TRAIN_SYNTHETIC_CUOI_2026-10-27.md).

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

Số khách tiềm năng/công ty: logNormal(trung vị 60, σ=0,6) kẹp [8, 400]. Trọng số doanh thu Pareto(α=1,5)+1; tỷ trọng top-10 ≈54% (src cũ), ≈70% (tgt cũ) là số đo lịch sử, không là mục tiêu đã hiệu chỉnh lại. Khoảng 72% pool hoạt động từ đầu. Mỗi tuần, khách có thể gia nhập, tạm rời hoặc quay lại theo thanh khoản hiện tại, tăng trưởng công ty và stress cầu; xem [kiểm toán sau sửa](15_SUA_VONG_DOI_KHACH_VA_HARD_CASE_2026-10-26.md). `start_day`/`end_day` trong bảng xuất là biên đầu/cuối tham gia thực hiện; các khoảng gián đoạn nằm trong `events`.

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
idio_c,t  : AR(1) phương sai 1, hệ số ρ_c; a_c = clip(idio_sd_c/0,165; 0,4; 1,6)
L_c,t = (a_c·idio_c,t + β_c · F_t / sd(F)) / sqrt(a_c² + β_c²)  −  1,2 · β_c · S_t  −  các kênh sốc tiếp xúc,   S_t = covid_sens·covid_t + crunch_sens·crunch_t
hazard tuần  h_c,t = h0_ngành · frailty_c · exp(0,7·max(−L_c,t, 0) + 1,0·S_t)   (kẹp 0,2; không rút sự kiện trong 26 tuần đầu thế giới; chỉ ở khách đang hoạt động)
h0_ngành = 1 − (1 − 0,06·pd_mult·bad_ngành/0,03)^{1/52}
```

Việc ngừng nhận đơn bán chịu dùng **tín hiệu tín dụng quan sát ở tuần hiện tại** (thanh khoản khách cộng nhiễu đo lường): hai tuần liên tiếp dưới −1,4 thì giữ bán; hai tuần liên tiếp trên −0,6 thì mở lại. Sự kiện vỡ nợ giữa tuần khiến bên bán giữ đơn trong 26 tuần kế tiếp; sau đó chỉ mở lại nếu tín hiệu tín dụng cho phép. Khách có thể vỡ nợ lần nữa sau thời gian hồi phục. Các thay đổi được ghi vào `events`; `customers.default_date` giữ lần đầu để tương thích. Tuần vỡ nợ tương lai không được dùng để dừng bán trước sự kiện. `pd_mult` là hệ số hiệu chỉnh tự động.

## 4.5 L3 — Hoá đơn

- **Doanh thu tuần** `R_t = (doanh thu/52)·e^{g·t/52}·mùa_vụ_ngành[tháng]·hệ_số_Tết·e^{AR(1)}·(1 − 0,6·covid_sens·covid_t)·(1 − 0,35·crunch_sens·crunch_t)`.
  Hệ số Tết theo tuần: −2: ×1,15; −1: ×1,25; tuần nghỉ: ×0,35; tuần cuối nghỉ: ×0,45; +1: ×0,7.
  Mùa vụ theo ngành (12 hệ số/ngành), ví dụ thép đỉnh tháng 12 (1,4), đáy tháng 7 (0,8).
- **Đơn được nhận** đầu tuần t lấy từ `R_t` cùng nhiễu đơn hiện tại và trọng số các khách chưa bị giữ bán. Cùng lượng đơn này quyết định cường độ sinh hóa đơn theo khách và mức bổ sung hàng tồn; hóa đơn riêng lẻ vẫn có nhiễu giá trị. **Giá trị** mỗi hóa đơn v1 = `ticket_c · logNormal(0; 0,75)`, làm tròn 1.000đ.
- **Ngày lập**: thứ 2–6 mỗi ngày 19%, thứ 7 5% (60% được giữ); không lập vào ngày nghỉ lễ; khách gộp cuối tháng dồn về ngày làm việc cuối tháng.
- **VAT**: 10%; 8% khi nằm trong các đợt giảm thuế (trừ ngành kim loại). Số hoá đơn đánh theo ký hiệu năm (`C25TAA`),
  MST hợp lệ (chữ số kiểm tra), tên pháp nhân kiểu VN.

## 4.6 L4 — Thanh toán (cốt lõi)

Với mỗi hoá đơn, theo thứ tự:

1. Khả năng trả đúng hạn vẫn lấy `ontime_logit_c + 0,6·L_c(due) − 1,2·S(due)`; lịch trả sớm, Tết, ngày chạy thanh toán và COD áp dụng cho khoản được trả ngay.
2. Hóa đơn còn mở sau hạn đi vào quá trình **mỗi tuần**. Khi lịch chạy thanh toán của khách rơi trong tuần, xác suất trả là `1 − exp[−7·exp(0,7·L_c,t − 0,25·S_t)/max(late_med_c,3)]` (kẹp 0,95). Đuôi cực trễ nhân cường độ với `0,18`. Nếu tuần `t` chưa trả, tuần `t+1` đọc thanh khoản mới; ngày trả không được cố định ở ngày đến hạn.
3. Nếu trả một phần (xác suất phụ thuộc thanh khoản tuần trả), phần còn lại cũng đi qua cơ hội trả theo tuần từ ít nhất bảy ngày sau. 15% đợt cuối có thể trả thiếu; phần dư vẫn mở.
4. Khi khách vỡ nợ đã xảy ra hoặc tranh chấp còn treo sau 180 ngày, không sinh khoản trả thông thường sau mốc đó. Có thể thu hồi 20–50% phần chưa trả sau 30–120 ngày; xóa sổ phần còn lại sau 180–300 ngày nếu ngày này nằm trong cửa sổ quan sát.
5. Tại `observation_end`, chỉ hóa đơn đã trả đủ, đóng bằng credit note hoặc đã xóa sổ mới có kết cục xác nhận. Hóa đơn còn mở nhận `outcome_status_at_end="censored"`; `is_bad_debt` chỉ đúng khi xóa sổ đã xảy ra. T1 kiểm duyệt theo `label_end`, không dùng khoản chưa biết kết cục làm nhãn nợ xấu. Ngày credit note được quyết định từ ngày lập/đến hạn, không lấy ngày trả tương lai.

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

**Lời hứa trả (T8).** Tại mốc 7/21/45/75 ngày sau hạn, chỉ gọi khi hóa đơn vẫn còn công nợ theo thanh toán và credit note **đã xảy ra** ở ngày gọi. Ngày hứa lấy từ độ tin cậy, mức trễ thường lệ của khách và nhiễu mới, không đọc ngày trả thật. Kết quả `kept` được đối chiếu sau đó với tiền trả và công nợ còn lại trong cửa sổ ±3 ngày; credit note/xóa nợ đơn thuần không được tính là giữ lời hứa trả tiền. Chế độ `noisy` vẫn thêm nhiễu ngày và kiểu hứa.

**Chi (T5, qua `calendar_vn.py`).** NCC: `inventory_weekly` lưu đơn đã nhận ở đầu tuần, tồn đầu, mua vào, giá vốn đơn được thực hiện và tồn cuối. Mua tuần `t` dùng đơn tuần `t`, tồn đầu tuần và trung bình đơn đã biết; không đọc `R[t+2]`. Đơn là proxy tổng hợp theo tuần, có chung nguồn với lượng hóa đơn nhưng chưa liên kết từng hóa đơn hay SKU. Giá vốn = 1 − biên − 1,3×tỷ lệ lương − chi phí chung; kỳ hạn NCC
{0,15,30,45,60}; ngày chạy chi theo 4 mẫu); lương ròng (gross × 89,5%), BHXH (32%) hạn cuối tháng; VAT (tháng nếu
doanh thu >50 tỷ, quý nếu không; hạn 20 tháng sau / cuối tháng đầu quý sau, dịch ngày nghỉ); TNDN tạm nộp (20% × biên ×
doanh thu quý, hạn 30 tháng đầu quý sau); môn bài 30/01 (bỏ từ 2026); thuê; lãi vay; tiện ích; thưởng tháng 13 trước Tết;
capex bất thường ~Poisson(1,5/năm). Các ngày đều dịch về ngày làm việc.

**Nhãn tất toán và công nợ.** `paid_date_true` là ngày dòng tiền đã trả đủ `amount_gross − credit_note`
sau khi credit note có hiệu lực. Tên đợt trả `kind="final"` không tự tạo nhãn trả đủ: nếu vẫn thiếu tiền,
`remaining_amount > 0` và hóa đơn còn mở. Credit note đóng hết công nợ mà không có tiền vào được gắn
`closure_type="credit_note"`, không có `paid_date_true`; phần còn thiếu bị xóa nợ được ghi riêng ở
`writeoff_amount`, `closure_type="writeoff"`. `paid_amount` đo tiền quy về giá trị nghĩa vụ hóa đơn; khi có
FX, `cash_received_amount` giữ số tiền chuyển trước phí, còn `payments.fx_adjustment` ghi chênh lệch tỷ giá.
`WorldConfig.accounting_version=6` đánh dấu đường sốc tích hợp và metadata công bố vĩ mô trên phiên bản nhãn, quyết định nhân quả và kiểm duyệt; các kết quả trên thế giới cũ phải được
đánh giá lại sau khi sinh dữ liệu mới.

**Episode sốc tích hợp.** `WorldConfig.shock_schedule` nhận các `ShockEpisode(family, start,
rise_weeks, peak_weeks, recovery_weeks, severity, industries, regions, reference_event)`;
`family` thuộc `demand`, `supply`, `price`, `credit`. Ngày bắt đầu là thứ Hai. Mỗi episode có
tuần thường, tăng, đỉnh và hồi phục; nhiều episode có thể chồng lấn trong **một thế giới**.
`shock_truth.parquet` lưu đường tuần, loại, pha và phạm vi để kiểm toán, không phải đầu vào mô hình.
`firms` và `customers` có bốn mức phơi nhiễm ẩn riêng, rút bằng luồng RNG tách khỏi giao dịch;
ngành/vùng ngoài phạm vi nhận tác động 0. Hệ số cường độ và truyền dẫn là **giả định synthetic**,
chưa phải ước lượng nhân quả từ dữ liệu Việt Nam.

- Cầu: giảm lượng đơn qua phơi nhiễm của bên bán và từng bên mua; bên mua thiếu đơn suy giảm thanh khoản.
- Cung: giảm phần đơn có thể đáp ứng, tăng giá đầu vào và gây áp lực thanh khoản bên mua.
- Giá: tăng giá bán trên hóa đơn và giá mua nhà cung cấp theo hệ số khác nhau; độ nhạy giá của khách giảm số lượng đặt.
- Tín dụng: giảm thanh khoản khách, tăng ngưỡng bên bán quyết định giữ đơn, tăng chi phí phục vụ khoản vay và giảm giải ngân nhiễu.

`inventory_weekly` lưu `demand_orders`, `supply_capacity`, `sale_price_index`,
`input_cost_index`; mua hàng tuần dùng đơn đã đặt, giá bán và giá đầu vào **trong tuần đó**.
Thanh khoản khách tuần đi vào xác suất trả của hóa đơn còn mở; thu tiền và chi phí đi vào
`daily_cash.balance`. `shock_truth` và phơi nhiễm ẩn chỉ phục vụ sinh dữ liệu, kiểm toán.
Mặc định `shock_schedule=[]` giữ thế giới không có episode mới; cần đặt lịch rõ ràng khi sinh bộ tích hợp.

**Ranh giới đặc trưng tại ngày dự báo `T`.** `SnapshotBuilder.model_snapshot(T)` chỉ trả
về các cột trong `MODEL_VISIBLE_COLUMNS` (`agent1/models/features.py`): khóa hóa đơn/công ty/khách,
`cutoff`, ngày lập/hạn, số tiền gốc và còn mở tính từ giao dịch **đến T**, `top1`/`top2`
cho lịch thanh toán, `BASELINE_QUANTILES` và danh sách `FEATURES` T1. Khóa và cột ngữ cảnh
phục vụ ghép, tính tiền và lịch tuần; chỉ `FEATURES` được đưa vào estimator mặc định.
Các ablation `f_resid_7d`, `no_due`, `c_disp_eb` phải chọn rõ ở pipeline nghiên cứu;
chúng không tự xuất hiện trong view T1 mặc định. Mọi tên đặc trưng mới ngoài allowlist bị từ chối,
kể cả tên chưa từng có trong danh sách cấm. Bảng nhãn huấn luyện vẫn chứa `label_date`,
`writeoff_date`, kết cục và cửa sổ kiểm duyệt để tạo `y`; phép chiếu đầu vào `X` loại các cột đó.
Không nối bảng `shock_truth`, phơi nhiễm bên mua/bán, ngày trả tương lai hoặc kết cục vào view.

`macro.parquet` có `week`, `published_date` và `covid_source`. Máy sinh đặt ngày công bố giả định
**14 ngày sau đầu tuần**; đó là quy ước synthetic thận trọng, không phải ngày công bố lịch sử
được kiểm chứng. `published_macro_as_of(macro, T)` chỉ trả chỉ báo `covid_stress` của tuần đã
công bố tại `T` khi nguồn là OxCGRT; không trả `common_factor`, `credit_crunch` (trạng thái ẩn),
episode hoặc giá trị từ `synthetic_fallback`. T1 mặc định hiện không dùng macro làm feature;
muốn đưa chỉ báo thật vào model cuối phải kiểm tra ngày công bố/vintage từ nguồn trước.

**Số dư.** `daily_cash.balance` là số dư của **tài khoản ngân hàng vận hành được quan sát**, không phải
tổng tiền hợp nhất của doanh nghiệp. Mỗi giao dịch sao kê có `cash_flow_class`, `in_balance_window` và
`balance_effect`; đây là cột kiểm toán, không phải đặc trưng mô hình. Thu khách sau phí vào `inflow_ar`;
`opening_balance` và ngưỡng rút vốn dùng `buffer_days × opening_daily_outflow`. Mức chi/ngày ban đầu tính từ quy mô doanh thu đầu kỳ, giá vốn, nhân sự, thuê và lãi vay đã biết khi mở kỳ; không dùng trung bình các khoản chi thực hiện đến hết 2025.
lãi/hoàn cọc/giao dịch chưa phân loại vào thu khác;
giải ngân vay vào `inflow_financing`. Chuyển nội bộ và nộp tiền mặt làm tăng **tài khoản này** nhưng không
được xem là doanh thu hay tăng tổng tiền toàn doanh nghiệp; chúng có cột riêng trong `daily_cash`.
Các giao dịch sau ngày kết thúc thế giới chỉ phục vụ nhãn thanh toán về sau, không thuộc cửa sổ số dư T6.
Chi NCC, lương, thuế và rút vốn chủ nằm ở `outflows`/`owner_draw`. Bộ kiểm tra đối chiếu từng
`balance_effect` với giao dịch gốc, tổng theo ngày/loại với `daily_cash`, và đường số dư lũy kế.
Lịch trả gốc/lãi của **các lần giải ngân nhiễu mới** và tài khoản nguồn của chuyển nội bộ/nộp tiền mặt
chưa được sinh thành sổ đối ứng; không diễn giải `balance` là thanh khoản hợp nhất của công ty.

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
