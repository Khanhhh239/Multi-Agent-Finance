# 04 · Quy tắc sinh dữ liệu (bộ mô phỏng sự kiện)

> Mã nguồn: `agent4/datagen/{company.py, ledger.py, simulator.py, build.py}`. Chạy: `python -m agent4.datagen.build --out data/cfo_warehouse.duckdb --seed 20251` (~1 phút).
> Mọi tham số dưới đây là **giả định thiết kế** trừ khi ghi nguồn; chúng nằm tập trung để chỉnh/hiệu chỉnh (xem `06`).

## 1. Kiến trúc bộ sinh (chia để trị)
```
company.py   Dữ liệu chủ: TK TT133, chi nhánh, phòng ban, danh mục hàng, nhà cung cấp, phân khúc khách, tỷ lệ BH/thuế, lịch lễ/Tết
ledger.py    Sổ cái kép: post() từ chối chứng từ lệch (trừ ca cài lỗi), giữ số dư theo TK & đối tượng, đánh số chứng từ
simulator.py Vòng lặp theo ngày: bán/thu/mua/trả/lương/thuế/khấu hao/kết chuyển + kịch bản cài đặt
build.py     Ghi DuckDB (sao + sổ chi tiết + view), bảng ngân sách, đối soát cuối
```
**Vòng lặp ngày** (`Simulator.run`): xử lý việc đến hạn → (ngày làm việc) nhận hàng → bổ sung hàng (thứ Hai) → hóa đơn dịch vụ định kỳ (ngày làm việc đầu tháng) → bán hàng → thu tiền → trả NCC → chi vặt → quản lý tiền → (cuối tháng) lương, khấu hao, phân bổ, điện nước…, thuế, kết chuyển.

## 2. Mô hình nhu cầu & bán hàng
| Thành phần | Quy tắc | Tham số |
|---|---|---|
| Tăng trưởng | Doanh số mục tiêu tháng = nền × mùa vụ × (1+g)^năm | nền 13,0 tỷ/tháng (T1/2025), g = 16%/năm |
| Mùa vụ | Hệ số theo tháng (đỉnh T12 = 1,30; T2 = 0,90) | `SEASON` |
| Cơ quan nhà nước | Mùa vụ riêng: thấp T1–2 (0,45), cao T11–12 (1,5–2,4) — mô phỏng giải ngân cuối năm | `GOV_SEASON` |
| Tết Nguyên đán | Nghỉ −2…+4 ngày; mua dồn trước Tết ×1,25; chậm sau Tết ×0,55 | Tết 29/01/2025, 17/02/2026 |
| Ngày làm việc | Loại thứ 7, CN, lễ; chuyển lịch thu/trả sang ngày làm việc kế tiếp | `PUBLIC_HOLIDAYS` |
| Trong ngày | Mỗi chi nhánh có mục tiêu = ngày × thị phần chi nhánh × lognormal(0,0.18); khách lẻ ~7 (ĐN: 3) giao dịch/ngày; sau đó bốc khách theo trọng số đến khi đủ mục tiêu; **chuyển phần vượt sang ngày sau** (carry) để tháng bám kế hoạch | |
| Trọng số khách | `cơ sở(phân khúc) × min(lognormal(0,0.85), 8)` → đuôi dày nhưng không quá cực đoan | ENT 6 · SME 1 · GOV 3 · ĐL 2,2 |
| Quy mô đơn | Lognormal theo phân khúc (trung vị / σ): ENT 60tr/0,9 · SME 18tr/0,8 · GOV 45tr/1,0 · ĐL 22tr/0,6 · lẻ 2,5tr/0,7 | `ORDER_MEDIAN/SIGMA` |
| Chọn hàng | 1–5 dòng/đơn; nhóm hàng theo hỗn hợp (IT 60%, OFF 22%, CON 18%); chỉ chọn mã có giá ≤ 2,5× giá trị mỗi dòng (tránh đơn 10 tỷ vì 1 máy chủ); mã đắt tiền ≤ 3 cái | |
| Chiết khấu | ENT 5% · GOV 2% · ĐL 8% · SME 1,5% · lẻ 0 | |
| Giá | +2% từ 01/2026; CNTT +1,5% thêm từ 04/2026 | |
| Dịch vụ định kỳ | 58 hợp đồng (bảo trì in/photocopy, helpdesk, thuê máy…) xuất hóa đơn ngày làm việc đầu tháng; số lượng theo hợp đồng | `service_contract` |
| Hàng trả lại | 1,2% hóa đơn bị trả một phần sau 3–20 ngày (ghi Nợ 5111, hoàn kho, hoàn giá vốn) | |
| Chiết khấu thương mại cuối năm | 1% doanh số 2025 cho 6 khách ĐL/ENT lớn nhất (26/12/2025) | |
| Kiểm soát tín dụng | Chặn đơn mới khi dư nợ > 120% hạn mức (**200% cho Hoàng Long** — sale được giám đốc cho vượt) | `_on_credit_hold` |

## 3. Thuế GTGT theo ngày
Hàng thuộc nhóm CNTT chịu 10% đến 30/06/2025 rồi 8%; hàng khác 8% suốt giai đoạn 01/2025–12/2026 (khung giảm 2%). Thuế suất lấy theo **ngày chứng từ**, nên truy vấn một khoảng ngày cắt qua 01/07/2025 có tỷ lệ thuế khác nhau.

## 4. Thu tiền (hành vi thanh toán)
| Phân khúc | Hạn (ngày) | P(đúng hạn) | Trễ trung bình khi trễ |
|---|---|---|---|
| ENT | 45 / 60 | 0,55 | 18 |
| SME | 30 | 0,62 | 12 |
| GOV | 60 | 0,35 | 38 |
| ĐL | 15 / 30 | 0,70 | 8 |
| Lẻ | 0 | 1,0 | 0 |

- **Tính cách khách:** `PROMPT` (90% đúng hạn, trễ TB 6) · `NORMAL` (theo phân khúc) · `CHRONIC_LATE` (12% đúng hạn, trễ ≥ 40).
- **Độ trễ:** nếu đúng hạn: 30% trả sớm 0–5 ngày, còn lại 0–3 ngày sau hạn; nếu trễ: `Gamma(2, trễ_TB/2) + 1` ngày (đuôi dày phải).
- **Thu một phần:** 12% hóa đơn > 30tr trả hai lần (40–70% lần đầu).
- **Hạch toán lô:** 8% khoản thu ngân hàng được kế toán ghi **cuối tháng** (`receipt_date` ≠ `bank_txn_date`; 402 khoản trong dữ liệu).
- **Khách gặp khó khăn (ca A2):** Hoàng Long — tăng mua chịu 02/2026–05/2026 (trọng số ×1,7) rồi **85% hóa đơn đến hạn sau 20/04/2026 không bao giờ được trả** (trong phạm vi dữ liệu).
- **Khách lẻ** trả ngay (tiền mặt nếu < 20 tr).

## 5. Mua hàng & tồn kho
| Quy tắc | Tham số |
|---|---|
| Phương pháp giá xuất | Bình quân gia quyền liên tục (`avg_cost`), xuất hết thì giá trị về 0 |
| Bổ sung hàng | Thứ Hai hàng tuần; đặt khi (tồn + đang về) < 15 ngày nhu cầu; đặt đến 32 ngày nhu cầu |
| Nhu cầu | Trung bình trượt (EWMA 0,985/0,015) theo số lượng bán |
| Thời gian về hàng | 3–7 ngày (+3 nếu NCC ở HCM) |
| Điều khoản NCC | Hàng hóa 15–45 ngày; điện/viễn thông 10–15; thuê mặt bằng trả trước theo quý |
| Tăng giá NCC | 3 NCC thiết bị CNTT tăng +6,5% từ 04/2026 (ca A7) |
| Dự trữ hè 2026 | Đặt thêm ×1,25 hàng CNTT (06–08/2026) — tạo áp lực tiền mặt |
| Quản lý tiền | Nếu tiền gửi < 2,5 tỷ: giãn trả NCC hàng hóa 7 ngày (70% xác suất; luôn nếu < 0,5 tỷ); vay hạn mức |

## 6. Chi phí & nhân sự
| Hạng mục | Quy tắc |
|---|---|
| Lương | Dải theo phòng ban (triệu): BGĐ 35–60 · KD 11–20 · MKT 12–20 · KT 12–20 · Kho 8–11 · TCKT 12–22 · HCNS 9–15; +phụ cấp; **+6% từ 01/2026**; giám đốc HN 75tr |
| Hoa hồng bán hàng | 0,35% doanh thu chi nhánh chia đều NV kinh doanh |
| Bảo hiểm DN đóng | 17,5% BHXH + 3% BHYT + 1% BHTN + 2% KPCĐ (trên lương đóng BH, trần 46,8tr) |
| Bảo hiểm NLĐ | 8% + 1,5% + 1% |
| TNCN | Biểu lũy tiến 7 bậc; giảm trừ bản thân 11tr (2025) / 15,5tr (2026) — **giả định, cần xác minh** |
| Lương tháng 13 | Trích tháng 12, chi trước Tết 12 ngày |
| Khấu hao | Đường thẳng theo tháng, 13 TSCĐ đầu kỳ + 2 mua mới (08/2025, 03/2026) |
| Thuê mặt bằng | Trả trước theo quý → 242 → phân bổ 3 tháng; +5% giá năm 2026 |
| Điện/nước | Cơ sở theo chi nhánh × 1,3 mùa hè; ca A9 (HCM 06/2026 ×1,45) |
| Vận chuyển | 1,6% doanh thu hàng hóa |
| Marketing | 1,2% doanh thu × ngẫu nhiên; ×1,5 trong T10–11; ca A1 (09/2026) |
| Chi tiếp khách | 35%/ngày; 72% có hóa đơn, 28% **không hóa đơn → không được trừ** |
| Tạm ứng công tác | 30%/ngày; thanh toán sau 6–16 ngày, hoàn lại phần dư |

## 7. Tài chính, thuế, kết chuyển
| Hạng mục | Quy tắc |
|---|---|
| Vay | Vay trung hạn 8 tỷ (9,2%/năm, gốc 0,5 tỷ/quý) · hạn mức xoay vòng 20 tỷ (7,8%/năm; rút khi tiền gửi < 2,5 tỷ, trả khi > 10 tỷ) · vay mua xe 0,8 tỷ (8,5%, 36 tháng) |
| Tiền gửi kỳ hạn | 5 tỷ, lãi 4,6%/năm trả mỗi 6 tháng |
| GTGT | Khấu trừ cuối tháng, nộp ngày 20 tháng sau |
| TNDN | Tạm tính quý = 20% × (LNTT + chi phí không được trừ); nộp ngày 28 tháng đầu quý sau; quyết toán 2025 vào 31/03/2026 (+ tiền chậm nộp mô phỏng) |
| Dự phòng nợ khó đòi | Tại 31/12/2025 & 30/06/2026 theo bậc tuổi nợ TT48/2019 (≥6 tháng 30%, ≥1 năm 50%, ≥2 năm 70%, ≥3 năm 100%) |
| Kết chuyển | Với tháng ≤ `last_closed_month`: Nợ/Có 5,6,7,8 → 911 → 4212; cuối năm 4212→4211 |
| Số dư đầu kỳ | Dựng từ AR/AP mở, tồn kho, TSCĐ, tiền, các khoản phải trả; **LNST chưa phân phối là số cân** |

## 8. Kiểm soát chất lượng tại thời điểm sinh
`build._validate` in ra: số dòng, số chứng từ lệch (mong đợi **1** — ca A4 cài sẵn), doanh thu/lãi 2025, **chênh lệch sổ cái ↔ sổ chi tiết = 0** cho AR, AP, kho, số dư tiền gửi nhỏ nhất. Xem thêm `08`.

## 9. Điểm chưa mô phỏng (đã biết)
Đa tiền tệ · bù trừ công nợ · chiết khấu thanh toán sớm · khuyến mại/tặng hàng · tái phân loại chứng từ sau khóa sổ · hóa đơn điều chỉnh/thay thế · nhiều kho · giá vốn FIFO/lô · thuế TNCN bậc mới · định mức chi phí được trừ (xe, quảng cáo, lãi vay) · hành vi nghỉ lễ chi tiết theo vùng.
