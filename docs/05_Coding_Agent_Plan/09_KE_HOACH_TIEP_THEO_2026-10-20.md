# Kế hoạch tiếp theo cho Agent 1 (rà soát ngày 20/10/2026)

> **Kế hoạch lịch sử.** Các số cổng và mục “hiện tại” là ảnh chụp ngày 20/10; đọc [cổng hiện hành](../03_Evaluation/GATES_CURRENT.md) và [tiến độ](TIEN_DO_TRIEN_KHAI.md) trước khi giao việc mới.

Người rà soát: agent1-Khanh (kiến trúc). Đầu vào: `TIEN_DO_TRIEN_KHAI.md`, `03_Evaluation/GATES_CURRENT.md`,
`03_Evaluation/KET_QUA_CHUA_DAT.md`, các CSV trong `outputs/`. File này **thay thứ tự ưu tiên** của `08_thu_tu_va_lich.md`
cho giai đoạn tới; các gói việc cũ vẫn là tham chiếu.

## 1. Chẩn đoán

### 1.1 Trạng thái
- 295 kiểm thử đạt ở hai môi trường; E2E đủ 14 DN × 52 tuần; 3,5 triệu hoá đơn nguồn lớn; dịch vụ local có.
- Cổng: **đạt 8/18** (G1, G2, G4, G9, G10, G12, G16, G18); **chưa đạt 10** (G3, G5, G6, G7, G8, G11, G13, G14, G15, G17). Pilot: NO-GO.

### 1.2 Bốn vấn đề lớn (theo mức nghiêm trọng)

| # | Vấn đề | Bằng chứng | Vì sao nghiêm trọng |
|---|---|---|---|
| **V1** | **Trên dữ liệu thật, mô hình thua mốc đơn giản B1d** (sau khi sửa as-of/CDF) | Customer Invoices: pinball DH-GBM 1,501 / ensemble 1,543 vs B1d **1,455**. BPI: DH-GBM **15,09** vs B1d **4,80**, cov80 0,10 | Luận điểm sản phẩm "hơn cách làm hiện tại trên dữ liệu thật" hiện **sai**. Mọi kết quả thắng đều chỉ trên tổng hợp |
| **V2** | **Có dấu hiệu lỗi, không phải chỉ mô hình yếu** | DH-LR trên Customer Invoices: MAE **105 ngày**, cov80 **0,0001**; DH-GBM BPI xấu đi từ 8,78 (v1) lên 15,09 (v3) | Kết quả không hợp lý ⇒ phải sửa trước mọi thí nghiệm mới |
| **V3** | **Khoảng cách tổng hợp → thật** | C2ST AUC 0,996 (đặc trưng phân biệt chính: `term_days` ≫ `late_days` > `log_amount_rel`); mô hình học trên tổng hợp đạt 2,20–3,34 trên Customer Invoices vs B1d 1,40 | Tiền huấn luyện tổng hợp chưa chuyển được sang dữ liệu thật; DR 20 thế giới giúp rõ (3,34 → 2,20) nhưng chưa đủ |
| **V4** | **Cảnh báo thiếu hụt chưa dùng được** (G13) | 4 tuần: chỉ bắt 25% sự kiện trước ≥4 tuần, báo giả 2,4/DN-năm; 13 tuần: bắt 94% nhưng báo giả 2,65/DN-năm | Đây là đầu ra người dùng thấy; báo giả >1/DN-năm sẽ làm người dùng tắt cảnh báo |

### 1.3 Nhận xét về cách làm
Phiên trước đã chạy rất nhiều ablation (~60 bảng CSV), đa số kết luận "not_demonstrated" với cải thiện ±1–2%. **Lợi ích biên đã
cạn**; tiếp tục mở rộng ablation sẽ không đưa sản phẩm tới GO. Giai đoạn tới tập trung **sửa lỗi, đứng vững trên dữ liệu thật,
cảnh báo dùng được**, mỗi sprint có **luật dừng**.

### 1.4 Phân loại 10 cổng chưa đạt

| Loại | Cổng | Ai xử lý |
|---|---|---|
| A. Sửa được bằng kỹ thuật | G3, G5, G6, G13, G15, G14 | Coding agent (Sprint 1–4) |
| B. Giả thuyết đã bị bác bỏ — cần chủ dự án quyết định có viết lại cổng không | G7 (fine-tune ≥10%), G17 (lời hứa ≥10%), G8 (SBA) | Người giao việc (mục 4) |
| C. Cần con người / bên ngoài | G11 (chuyên gia xác minh 27 quy tắc), UAT 3 người, pilot, Docker daemon | Người giao việc |

## 2. Kế hoạch theo sprint

Quy tắc chung (giữ nguyên): không dùng `tgt`/test để chọn tham số; chọn trên nguồn hoặc trên **quá khứ của chính DN đích trước
ngày cắt**; mọi thay đổi phép đo phải tăng `measurement_version` và chạy lại toàn bộ mốc; báo cáo CI bootstrap theo công ty.

---

### Sprint 1 (P0) — Sửa lỗi và đứng vững trên dữ liệu thật (V1, V2) — cổng G5, G6

> **ĐÃ XONG 21/10/2026 (agent1-Khanh)** — xem [NHAT_KY_SPRINT1_2026-10-20.md](NHAT_KY_SPRINT1_2026-10-20.md). Nguyên nhân gốc: lỗi
> `expand` + ngoại suy LR + thiết kế bỏ đói dữ liệu. BLEND(DH-GBM,B1d) thắng B1d: CI +14,4% [11,7; 17,4], BPI +6,5% [2,1; 11,0].
> Việc tiếp theo cho agent khác: [PROMPT_GIAO_VIEC_2026-10-21.md](PROMPT_GIAO_VIEC_2026-10-21.md).

**1.1 Sửa DH-LR trên Customer Invoices.**
- Tái hiện trên mẫu nhỏ (`snap_real_customer_invoices`, 2.000 hàng). Nghi: chuẩn hoá `_prep` (log1p dấu, median NaN) sau khi đổi đặc trưng; cột `k` không còn đúng vị trí; tràn số.
- Thêm `tests/test_t1_real_regression.py`: DH-LR trên mẫu này phải có MAE P50 < 2× B1 và cov80 > 0,3.

**1.2 Điều tra hồi quy BPI (8,78 → 15,09; cov80 0,10).**
- So `A_rolling_origin_src.v1.csv` / `v2_before_point_fix.csv` / bản hiện tại và hai phiên bản `features.py`/`run_t1.py::exp_C` (BPI không có hạn).
- Kiểm: nhãn `remaining` có bị cắt ở 120 trong khi BPI có trung vị 64 ngày, P90 106 ngày (gần K=13 tuần = 91 ngày)? `due_date = issue_date` có làm `dtd_k` mang tín hiệu sai sau sửa as-of? hazard đuôi sau tuần 13?
- Sản phẩm: một ghi chú nguyên nhân + kiểm thử hồi quy; chỉ sau đó mới chạy lại C.

**1.3 T1 neo vào mốc ("không bao giờ tệ hơn B1d").**
- Thêm vào snapshot các đặc trưng as-of `b1d_q10, b1d_q50, b1d_q90` (phân vị trễ của khách tính từ lịch sử ≤T, co về công ty) — mô hình học **phần hiệu chỉnh** quanh mốc.
- Thêm `blend(w)`: `Q = w·Q_model + (1−w)·Q_B1d` (Vincentization). **w chọn theo từng DN** bằng pinball trên cửa sổ hiệu chỉnh nằm **trước** ngày cắt test của chính DN đó (dữ liệu DN đã có lúc onboard — hợp lệ). Lưới w ∈ {0; 0,25; 0,5; 0,75; 1}.
- Đánh giá trên Customer Invoices, BPI, `src`, `tgt` với CI theo công ty/cụm.
- **Tiêu chí:** blend không thua B1d trên cả hai bộ thật (CI của chênh lệch chứa 0 hoặc dương) và không làm xấu `src`/`tgt` quá 2%.
- **Luật dừng:** nếu sau 1.1–1.3 vẫn thua B1d trên Customer Invoices với CI loại trừ 0 ⇒ ghi kết luận: *"với AR kiểu ERP kỳ hạn ngắn, dùng B1d + CQR; hazard chỉ bật khi DN có hạn thanh toán và nhịp trả rõ"*, cập nhật docs, chuyển Sprint 2.

---

### Sprint 2 (P0) — Hiệu chỉnh khoảng T1 và cảnh báo dùng được (G3, G13, V4)

**2.1 G3 — độ phủ T1.** CQR hai phía cho phép thu hẹp (đích 80%, hiện 86–89%) và **Mondrian CQR theo nhóm tuần đáo hạn** (hạn trong tuần 1–2 / 3–6 / >6 / đã quá hạn), hiệu chỉnh trên cửa sổ nguồn. Tiêu chí: cov80 ∈ [75, 85]% ở cả hai gốc, IS80 không xấu đi.

**2.2 G13 — chính sách cảnh báo.** Hiện tại ngưỡng 0,02–0,12 quá thấp ⇒ báo giả nhiều.
1. Hiệu chỉnh xác suất thiếu hụt (isotonic) trên backtest **nguồn** theo chân trời 4 và 13 tuần; vẽ reliability.
2. Thêm **trễ xác nhận** (cảnh báo khi vượt ngưỡng 2 tuần liên tiếp) và **mức độ** (thiếu hụt ≥ X% chi tuần) — đăng ký trước định nghĩa sự kiện mới, giữ song song định nghĩa cũ.
3. Ngưỡng theo chi phí lấy trên nguồn; báo cáo đường *tỷ lệ bắt ≥4 tuần — báo giả/DN-năm* cho từng mô hình.
- Tiêu chí G13: ≥70% sự kiện bắt trước ≥4 tuần với báo giả ≤1/DN-năm (13 tuần). Nếu không đạt với 16 sự kiện hiện có ⇒ sinh thêm DN đích (seed mới, niêm phong) để có ≥60 sự kiện trước khi kết luận.

---

### Sprint 3 (P1) — Khớp sao kê đạt G15

Hiện tại hybrid: precision 0,940, recall 0,610, F1 0,740, tự động 0,70. Cần precision ≥0,95, F1 ≥0,80.
1. Phân tích lỗi theo loại trên **nguồn** (`source_allocation_diagnostics.csv`): sai khách / sai tập HĐ / trả một phần / phí / gộp nhiều HĐ.
2. Xử lý hai hard case tệ nhất: `retention` (F1 0,58) — tách khoản giữ lại thành nghĩa vụ riêng; `cod_realistic` (F1 0,69) — khớp theo ngày lập + số tiền khi COD.
3. Phân bổ bằng tối ưu có prior hazard T1 (xác suất HĐ được trả vào ngày giao dịch) thay vì subset-sum "đầu tiên khớp".
4. Hiệu chỉnh `tau` và hàng chờ trên nguồn; báo đường precision–coverage.
- Luật dừng: nếu precision ≥0,95 chỉ đạt khi coverage <0,6 ⇒ đề xuất chủ dự án hạ yêu cầu tự động xuống 0,5 (kèm hàng chờ người duyệt).

---

### Sprint 4 (P1) — Giảm khoảng cách tổng hợp → thật (V3)

1. **Tách C2ST hai phần** (đăng ký trước): (a) *đặc trưng thiết kế khác có chủ đích* (`term_days` theo luật/Atradius VN khác hệ SAP Mỹ); (b) *đặc trưng hành vi có điều kiện* — trễ so với kỳ hạn, độ phân tán theo khách, nhịp ngày trả, quan hệ số tiền–trễ. Mục tiêu <0,75 chỉ áp cho (b); (a) báo cáo minh bạch, không dùng để "sửa cho giống Mỹ".
2. Sửa máy phát theo đặc trưng (b) mạnh nhất: tăng dị biệt khách (phương sai do khách hiện 0,20 vs 0,60 ở ERP thật), phân phối `late_days` có khối lớn quanh 0 và trả sớm, tương quan số tiền–trễ.
3. Chạy lại DR (20 thế giới) với máy phát mới; đo zero-shot và blend (1.3) trên Customer Invoices.
- Tiêu chí: C2ST(b) <0,75; mô hình tổng hợp zero-shot trên Customer Invoices ≤1,2× pinball của B1d (hiện 1,57×).

---

### Sprint 5 (P2) — T7 và dọn dẹp
- G14: bằng chứng cụm/danh mục (`t7_portfolio.py`) đã có — chạy lại với ngưỡng nguồn; nếu vẫn >0,5 báo giả thì giữ CUSUM-PIT ở chế độ "chỉ hiển thị", không đẩy cảnh báo.
- Việc còn trong `TIEN_DO`: nhãn khoảng từ `last_seen_open`, DA5 M3 (cần cửa sổ hiệu chỉnh hợp lệ), tích hợp lịch nghĩa vụ mở rộng vào T6 (tránh đếm trùng), tốc độ máy phát ≥5× tại 1M HĐ, chuỗi HĐ gốc–thay thế–huỷ–điều chỉnh.
- **Không mở thêm ablation mới** ngoài danh sách này trừ khi nó gỡ một cổng.

---

### Sprint 6 — Đóng gói và đồng bộ
1. Chốt `measurement_version` cuối; chạy `scripts/run_plan.py` toàn chuỗi; `make_report.py`.
2. Khi lập kế hoạch, dự kiến rút gọn `03_Evaluation/04_ket_qua_hien_co.md` và chuyển bảng chi tiết sang file riêng. Hiện bảng chi tiết được giữ ngay trong `04_ket_qua_hien_co.md`; bản sao `RESULTS_TABLES.md` đã bỏ.
3. Cập nhật `00_INDEX.md`: bỏ các con số cũ (v1) đã bị thay, đặc biệt dòng "ensemble giảm MAE 17% trên dữ liệu thật" (không còn đúng).
4. Commit + push lên nhánh `agent1-Khanh` (không đưa dữ liệu thô, parquet, `.state`, token).

## 3. Thứ tự và ước lượng

| Sprint | Thời lượng | Gỡ cổng | Điều kiện bắt đầu |
|---|---|---|---|
| 1 | 2–3 ngày | G5, G6 (+ sửa V2) | ngay |
| 2 | 2–3 ngày | G3, G13 | song song với 1 (khác file) |
| 3 | 2 ngày | G15 | sau 1.1 (dùng chung T1) |
| 4 | 3–4 ngày | (V3, gián tiếp G5/G6) | sau 1.3 |
| 5 | 1–2 ngày | G14 | bất kỳ |
| 6 | 0,5 ngày | — | cuối |

Nếu có hai agent: A làm Sprint 1 → 3 → 4 (`features.py`, `t1.py`, `t9_recon.py`, `synth/`); B làm Sprint 2 → 5 (`t6_cash.py`, `run_t6.py`, `t7_*`). Không để hai agent sửa cùng file.

## 4. Quyết định cần chủ dự án (không để agent tự quyết)

| # | Câu hỏi | Khuyến nghị |
|---|---|---|
| D1 | G7 (fine-tune ≥10%) đã bị bác bỏ. Viết lại thành "chính sách onboarding không tệ hơn zero-shot (CI)"? | Đồng ý, ghi rõ là cổng **viết lại sau khi xem kết quả** |
| D2 | G17 (lời hứa ≥10%) chưa đạt (−7,2% sạch). Giữ cổng, hay chuyển T8 thành tính năng "không bắt buộc cho pilot"? | Chuyển sang không bắt buộc; đo lại trên lời hứa thật ở pilot |
| D3 | G8 SBA: dữ liệu cho vay Mỹ có còn là cổng pilot? | Giữ làm bằng chứng phương pháp, bỏ khỏi điều kiện GO |
| D4 | Chấp nhận kết luận "B1d + CQR cho AR kỳ hạn ngắn" nếu Sprint 1 không thắng? | Chấp nhận — trung thực hơn và vẫn có giá trị sản phẩm (T6, T9, T5) |
| D5 | G11: ai là chuyên gia kế toán/thuế xác minh 27 quy tắc? | Cần người thật; agent chỉ chuẩn bị bảng đối chiếu |
| D6 | UAT 3 người, đối tác pilot, bật Docker daemon | Việc của người giao việc |

## 5. Lời nhắn chuyển cho coding agent (dán nguyên văn)

> Đọc `docs/05_Coding_Agent_Plan/09_KE_HOACH_TIEP_THEO_2026-10-20.md`. Làm theo thứ tự Sprint 1 → 2 → 3 → 4 → 5 → 6.
> Bắt đầu bằng 1.1 và 1.2 (lỗi DH-LR MAE 105 ngày trên Customer Invoices; DH-GBM BPI xấu đi 8,78 → 15,09, cov80 0,10):
> tái hiện trên mẫu nhỏ, tìm nguyên nhân, viết kiểm thử hồi quy, rồi mới chạy lại thí nghiệm C. Không mở ablation mới ngoài
> danh sách. Không dùng `tgt`/test để chọn tham số; blend w chọn trên quá khứ của chính DN trước ngày cắt. Mỗi sprint kết thúc:
> CSV mới, `make_report.py`, cập nhật `GATES_CURRENT.md`, ghi rõ luật dừng nào đã kích hoạt. Các quyết định D1–D6 để chủ dự án trả lời.
