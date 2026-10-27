# WP-4 T9 · WP-5 T5 · WP-7 T7 · WP-8 T8

> **Hồ sơ kế hoạch từ 15/10/2026.** Các trạng thái, lệnh và danh sách việc dưới đây phản ánh thời điểm lập; đọc [tiến độ hiện hành](TIEN_DO_TRIEN_KHAI.md) trước khi dùng.

---

## WP-4 · T9 khớp sao kê — thiết kế lai quy tắc + ML (P0)

**Hiện trạng** (`agent1/models/t9_recon.py`, `scripts/run_t9.py`): ML F1 0,689 (precision 0,78, recall 0,62), R1 precision 0,99/recall 0,47, R2 0,99/0,31, MAE ngày trả 1,97 vs ngày sổ 12,6. Mục tiêu: **F1 ≥0,80, precision ≥0,95, ≥60% giao dịch tự động, phần còn lại đưa vào hàng chờ**.

### WP-4.1 Tách đánh giá hai bước
- **File**: `scripts/run_t9.py`.
- **Việc**: báo cáo riêng (a) độ chính xác chọn **khách** (`txn_customer_recall`, precision) và (b) độ chính xác **phân bổ vào hoá đơn** khi đã biết đúng khách (oracle) — để biết lỗi nằm ở bước nào.
- **Giả thuyết**: lỗi chính ở (b) khi một khách có nhiều HĐ cùng số tiền hoặc trả theo lô/FIFO.

### WP-4.2 Phân bổ tốt hơn (b)
- **File**: thay `Reconciler.allocate` bằng `allocate_ilp`.
- **Làm**: với mỗi giao dịch đã biết khách, giải bài toán chọn tập HĐ `S` (≤6) sao cho `|Σ remain_i − amt| ≤ TOL` và cực tiểu hoá chi phí `Σ cost_i`, `cost_i = −log p_i`, `p_i` từ mô hình xác suất HĐ *i* được trả ở ngày này (hazard T1 tại ngày giao dịch) + thưởng cho HĐ đã quá hạn lâu nhất (FIFO) + thưởng số HĐ trong nội dung. Giải bằng DP (subset-sum với trọng số) trên ≤15 HĐ; hoặc `scipy.optimize.milp` / `OR-Tools CP-SAT` (thêm gói nếu cần).
- **Tiêu chí**: precision phân bổ khi oracle khách ≥0,95.

### WP-4.3 Hàng chờ người duyệt và ngưỡng
- **File**: `Reconciler.assign_customers` → trả thêm `confidence`; **tạo** `reconcile(bank, inv, cust, tau_auto=0.9)` trả `auto_links`, `review_queue`.
- **Làm**: hiệu chỉnh `p` bằng isotonic trên cặp (giao dịch, ứng viên) ở cửa sổ hiệu chỉnh; đo đường cong *precision–coverage* (tỷ lệ tự động vs precision).
- **Tiêu chí**: tại `tau_auto` chọn sao cho precision ≥0,95, coverage tự động ≥60%.

### WP-4.4 Lai (R1∪R2 trước, ML sau)
- Thứ tự: (1) R2 (số HĐ rõ ràng); (2) R1 (đúng số tiền duy nhất); (3) ML cho phần còn lại; không ghi đè kết quả bước trước. Đo từng tầng đóng góp.

### WP-4.5 Hard case T9 (liên kết WP-D2)
- Người trả ≠ khách (nhóm công ty), gộp nhiều khách một lệnh, phí lớn, số tiền làm tròn, CK không có tên, nội dung bằng tiếng Anh/viết tắt khác. Mỗi hard case = một thế giới `hc_*`; đo recall riêng.

### WP-4.6 Dùng ngày NH thay nhãn sổ trong pipeline
- Hàm `build_bank_labels(inv, links)` tạo `paid_date_est` từ `links` (ngày tất toán hoá đơn) thay `ledger_clear_date` — **đây là nhãn thật khi chạy sản phẩm** (không có `paid_date_true`). Chạy exp F với nhãn từ `links` (không phải `true`) để đo tác động chuỗi sai số T9 → T1 (error propagation).
- **Tiêu chí**: WAPE T1 với nhãn từ T9 gần nhãn thật hơn nhãn sổ ≥50% khoảng cách.

**Chạy**: `AGENT1_THREADS=4 python scripts/run_t9.py` (cache ứng viên trong `outputs/t9/cand_*.parquet`; xoá khi đổi đặc trưng ứng viên).

---

## WP-5 · T5 mở rộng và quy trình pháp lý

**Hiện trạng**: `agent1/calendar_vn.py` + 15 kiểm thử. Đã có VAT, TNDN tạm nộp/quyết toán, BHXH, lương tối thiểu vùng, môn bài, giảm VAT 8%.

### WP-5.1 Bộ quy tắc có phiên bản
- **Tạo** `agent1/rules/` : `rules_2019.yaml … rules_2026.yaml` (hoặc JSON) mô tả hạn/tỷ lệ/ngưỡng với `effective_from`, `effective_to`, `source` (số văn bản + điều), `verified` (bool). `calendar_vn` đọc từ đó thay vì hằng số trong mã.
- **Làm**: `load_rules(date)`; `calendar_vn` gọi `load_rules`; giữ hành vi hiện tại (15 kiểm thử vẫn xanh).
- **Tạo** `tests/test_rules_regression.py`: mỗi quy tắc có ≥2 ca (trước/sau ngày hiệu lực).

### WP-5.2 Mở rộng nghĩa vụ
- Thuế TNCN khấu trừ (tháng/quý), thuế nhà thầu, tiền thuế GTGT hoàn, lương thưởng (thưởng 13), tiền thuê theo hợp đồng nhiều mức, lãi vay theo lịch tin dụng (không chỉ lãi), trả gốc vay.
- Nguồn: TT 80/2021/TT-BTC, TT 111/2013 (TNCN), NĐ 126/2020 — **đối chiếu văn bản gốc**; đánh dấu `verified=false` đến khi người có chuyên môn xác nhận.

### WP-5.3 Nhật ký thay đổi luật
- Tạo `docs/legal_changelog.md`: ngày kiểm, văn bản, thay đổi, hành động; script `scripts/check_rules.py` liệt kê quy tắc `verified=false` hoặc quá 12 tháng chưa kiểm.

### WP-5.4 Dự phòng nợ khó đòi (nối T2 → Agent 3)
- `agent1/rules/provisioning.py`: bracket TT48/2019 theo tuổi nợ (30/50/70/100%); hàm `suggest_provision(invoices, T)`. Mô hình T2 chỉ nâng cảnh báo *sớm hơn* sàn.

**DoD WP-5**: mọi hằng số luật nằm trong `rules/*.yaml`; ≥40 ca kiểm thử; script check_rules; tài liệu nguồn.

---

## WP-7 · T7 điểm gãy (G14)

**Hiện trạng**: CUSUM-PIT: phát hiện 52% / báo giả 0,63 (giữ lại); cổng cần ≤0,5.

### WP-7.1 Bằng chứng cụm (X35)
- **File**: **tạo** `agent1/models/t7_portfolio.py`.
- **Làm**:
  1. Phần dư PIT của *mọi khách* trong DN theo tuần ⇒ chuỗi tổng hợp `Z_w = mean(z)` (hoặc Stouffer: `Σz/√n`).
  2. CUSUM/BOCPD trên `Z_w` ⇒ cảnh báo **danh mục** (sốc chung).
  3. Khách-level: báo động chỉ được xác nhận nếu ≥2 trong 3 (CUSUM, PH, BOCPD) cùng báo trong 30 ngày **hoặc** ≥2 khách cùng ngành/cùng nhịp thanh toán cùng báo.
- **Tiêu chí**: phát hiện ≥50% tại báo giả ≤0,5 trên giữ lại.

### WP-7.2 Điều kiện hoá theo sốc vĩ mô
- Bỏ phần sốc chung đã giải thích bằng `f_resid_28d` khỏi phần dư khách để báo động khách phản ánh thay đổi *riêng*: `z_cust = PIT(trễ − E[trễ | sốc chung])`.

### WP-7.3 Đánh giá trên dữ liệu thật
- Berka: chuỗi dòng ròng tuần của 1.478 tài khoản; chèn dịch chuyển nhân tạo (+X%) vào 50% tài khoản ở thời điểm ngẫu nhiên ⇒ đo tỷ lệ phát hiện/báo giả; ngoài ra kiểm tra phát hiện tại thời điểm tháng 1/1993…(không có nhãn thật ⇒ chỉ báo cáo số báo động).
- OxCGRT VN: kiểm tra phát hiện sốc vĩ mô ở danh mục `src` quanh 4/2020, 7/2021 (T7 danh mục phải báo trước hoặc cùng tuần với covid_stress >0,25).

### WP-7.4 Cơ chế chuyển chế độ
- `RegimeController`: trạng thái {normal, alert, crisis}; khi `crisis`: (a) T1/T6 dùng cửa sổ 8–12 tuần với trọng số suy giảm (huấn luyện lại nhanh hoặc đặt `ewm_halflife=30`); (b) ACI γ×3; (c) nhãn UI.
- **Tiêu chí**: trong giai đoạn 2021-07→10 và 2022-10→2023-06 cov80 của T6 ≥70% với bộ điều khiển (so với không có).

---

## WP-8 · T8 lời hứa trả

### WP-8.1 Máy phát thực tế hơn (L12)
- **File**: `agent1/synth/world.py::promises`.
- **Việc**: thêm các kiểu lời hứa: (i) hứa mơ hồ ("cuối tháng", "tuần sau"): khoảng 7 ngày; (ii) hứa một phần; (iii) hứa lặp (khất nhiều lần, mỗi lần dời 7–14 ngày); (iv) lời hứa không ghi (thoả thuận miệng, `H29`) ⇒ chỉ lộ ra qua kết quả. Tham số độ tin cậy `Beta(4,2)` → phân tầng theo khách.
- **Kiểm**: phân phối |hứa−thật| có đuôi dày hơn.

### WP-8.2 Mô hình độ tin cậy
- **Tạo** `agent1/models/t8_promise.py`: `PromiseReliability` (Beta–Binomial theo khách với tiền nghiệm phân tầng, 5 chiều: reliability, delay, amount_sensitivity, recency, volatility — xem nhánh `agent1-Thắng/research/T8_note.md`).
- **Đo**: Brier của "lời hứa được giữ" so với tỷ lệ nền khách.

### WP-8.3 Thí nghiệm E (đã viết trong `exp_EF`)
- Chạy; thêm biến thể "lời hứa nhiễu" (WP-8.1) để chắc rằng lợi ích T8 không phụ thuộc vào máy phát quá sạch.
- **Tiêu chí G17**: giảm MAE P50 trên HĐ có lời hứa ≥10% *cả với lời hứa nhiễu*.

### WP-8.4 Công cụ thu thập
- Đặc tả (không cần UI đầy đủ): bảng `payment_promises`, API `POST /promises` (xem WP-9), ánh xạ từ chat: "khách A xin khất 5 tỷ sang 15/8" → JSON {customer, amount, date} + cổng duyệt.
