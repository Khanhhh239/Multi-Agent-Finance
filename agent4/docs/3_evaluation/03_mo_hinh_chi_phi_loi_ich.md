# 03 · Mô hình chi phí – lợi ích (trước và sau khi có sản phẩm)

> **Đọc kỹ:** đây là mô hình **minh họa có công thức**, dùng số của doanh nghiệp mẫu (dữ liệu tổng hợp) và **giả định có gắn nhãn**. Các giả định (G) phải được thay bằng số đo ở pilot (`02`). Phép tính chạy lại được: bảng dưới là đầu ra của một đoạn Python 15 dòng — mọi số đã đối chiếu.

## 1. Đầu vào
### 1.1 Từ dữ liệu doanh nghiệp mẫu (đo được)
| Ký hiệu | Giá trị | Nguồn |
|---|---|---|
| Doanh thu thuần 2026 đến 14/10 | 169,02 tỷ (287 ngày) | `net_revenue` |
| Doanh thu quy năm `R` | 169,02 / 287 × 365 = **215,0 tỷ** | tính |
| Tỷ trọng bán lẻ (trả ngay) | 17,5 / 186,5 ≈ 9,4% (2025) | `ar_invoice` theo phân khúc |
| Doanh số bán chịu trước VAT `Rc` | 215,0 × (1 − 0,094) = **194,7 tỷ** | tính |
| Doanh số bán chịu/ngày gồm VAT 8% `Sd` | 194,7 × 1,08 / 365 = **0,576 tỷ/ngày** | tính |
| DSO hiện tại | 62 ngày (Q3/2026) | `dso` |
| Lương TCKT trung bình (gross) | 18,1 triệu/tháng (9 nhân sự) | `payroll` 09/2026 |
| Chi phí DN/giờ `c` | 18,1 tr × (1 + 0,235) / 176 giờ = **127.000 đ/giờ** | 23,5% = BH DN 21,5% + KPCĐ 2% |
| Lãi suất vay `r` | 8,5% (khoản vay 7,8–9,2%) | `loan` |

### 1.2 Giả định hành vi (G) — **cần đo ở pilot**
| Ký hiệu | Giá trị | Ghi chú |
|---|---|---|
| G1 | 60 yêu cầu ad‑hoc/tuần × 25 phút | CEO, 3 GĐ chi nhánh, trưởng KD… hỏi kế toán lấy số |
| G2 | Gói báo cáo tháng 48 giờ; báo cáo công nợ–tiền hằng tuần 4 giờ × 2 người | |
| G3 | Nợ xấu nền = **0,5% doanh số bán chịu**/năm = 0,97 tỷ | trung bình thấp cho DN phân phối |
| G4 | Giờ tiết kiệm: 40% / 60% / 80% | còn lại vẫn cần người (kiểm tra, đối chiếu, việc không tự động hóa) |
| G5 | Giảm DSO: 1 / 3 / 5 ngày | nhờ nhìn thấy sớm nợ quá hạn & khách vượt hạn mức |
| G6 | Giảm nợ xấu: 10% / 25% / 40% | cảnh báo sớm + giữ hàng |

### 1.3 Giả định chi phí xây (G‑build)
| Mục | Giá trị |
|---|---|
| Thời gian | 20 tuần = 4,62 tháng |
| Nhân lực (tháng‑người) | AI/ML lead 1,0 · Dev 2,0 · BA/kế toán tư vấn 0,5 · QA 0,25 |
| Lương gross/tháng | 50 · 30 · 35 · 25 triệu; chi phí DN = ×1,235 |
| Hạ tầng một lần | GPU workstation/server 16 GB: 60 triệu |
| Khác (dữ liệu, tool, kiểm thử, pháp lý) | 40 triệu; đào tạo/pilot 30 triệu |
| Vận hành/năm | Hosting + điện 3 triệu/tháng; bảo trì 0,2 dev; rà soát kế toán 0,1 người |

## 2. Chi phí
| Khoản | Công thức | Số tiền |
|---|---|---|
| Nhân lực xây | Σ (lương × 1,235 × tháng‑người × 4,62) | 284 + 342 + 100 + 36 ≈ **762 triệu** |
| Hạ tầng | | 60 triệu |
| Khác + pilot | | 70 triệu |
| **CAPEX (một lần)** | | **≈ 892 triệu** |
| Vận hành/năm | (3 tr + 30 tr×1,235×0,2 + 35 tr×1,235×0,1) × 12 | **≈ 177 triệu/năm** |

## 3. Lợi ích hằng năm theo kịch bản
**Công thức:**
- Tiết kiệm giờ = (108,3 + 48 + 34,7) giờ/tháng × 12 × `G4` × 127.000 đ  *(tổng 191 giờ/tháng = 2.292 giờ/năm = 291 triệu/năm trước tiết kiệm)*
- Lãi vay tiết kiệm = `G5` × `Sd` × `r`  *(giải phóng vốn lưu động một lần = G5 × 0,576 tỷ)*
- Nợ xấu tránh được = 0,97 tỷ × `G6`

| | Thận trọng | **Cơ sở** | Lạc quan |
|---|---|---|---|
| Giờ tiết kiệm | 40% → 917 giờ → **116 tr** | 60% → 1.375 giờ → **175 tr** | 80% → 1.834 giờ → **233 tr** |
| Giảm DSO | 1 ngày → giải phóng 0,58 tỷ → lãi **49 tr** | 3 ngày → 1,73 tỷ → lãi **147 tr** | 5 ngày → 2,88 tỷ → lãi **245 tr** |
| Nợ xấu tránh được | 10% → **97 tr** | 25% → **243 tr** | 40% → **389 tr** |
| **Tổng lợi ích/năm** | **263 tr** | **565 tr** | **867 tr** |
| Vận hành/năm | 177 tr | 177 tr | 177 tr |
| **Lợi ích ròng/năm** | **86 tr** | **388 tr** | **690 tr** |
| Hoàn vốn (CAPEX/ròng) | **10,4 năm** | **2,3 năm** | **1,3 năm** |
| NPV 3 năm (chiết khấu 12%) | −686 tr | **+40 tr** | +766 tr |
| ROI 3 năm | −71% | +30% | +132% |

## 4. Trước và sau (so sánh trực quan, kịch bản cơ sở)
| Chỉ tiêu (năm) | Trước | Sau | Chênh |
|---|---|---|---|
| Giờ kế toán cho báo cáo & ad‑hoc | 2.292 giờ (291 tr) | 917 giờ (116 tr) | −1.375 giờ (−175 tr) |
| DSO | 62 ngày | 59 ngày | −3 ngày |
| Phải thu | 47,6 tỷ | ≈ 45,9 tỷ | −1,73 tỷ vốn lưu động |
| Lãi vay do vốn bị chiếm | — | — | −147 tr |
| Nợ xấu | 0,97 tỷ | 0,73 tỷ | −243 tr |
| Chi phí sản phẩm | 0 | 177 tr vận hành + 892 tr đầu tư | +177 tr/năm |
| **Lợi ích ròng** | | | **+388 tr/năm (sau năm 1)** |

## 5. Phân tích độ nhạy & điểm hòa vốn
- **Hòa vốn 3 năm (đường thẳng, giữ G4=60%, G6=25%)**: cần giảm DSO ≈ **1,15 ngày**. Mỗi 1 ngày DSO ≈ 49 triệu lãi/năm + 576 triệu tiền mặt giải phóng.
- **Biến nhạy nhất**: `G5` (DSO) và `G6` (nợ xấu) — chiếm ~70% lợi ích cơ sở; tiết kiệm giờ là phần *chắc chắn nhất nhưng nhỏ*.
- **Đòn bẩy sự kiện đơn lẻ** (không đưa vào kỳ vọng hằng năm): ca Hoàng Long — dư nợ 3,1 → 8,1 tỷ trong 2 tháng; nếu cảnh báo sớm 6 tuần giúp giữ mức ≤ 4,8 tỷ (120% hạn mức), nợ có rủi ro giảm ≈ 3,3 tỷ; ngay cả với xác suất mất 20% thì kỳ vọng tránh được ≈ 0,66 tỷ ≈ **74% CAPEX (0,66 / 0,892) chỉ từ một sự kiện**.

## 6. Mô hình đa khách hàng (nếu bán dạng sản phẩm)
Chi phí/khách/năm = CAPEX / (N × 3 năm) + chi phí biên/khách (hosting + hỗ trợ ≈ 60 triệu).

| Số khách N | 1 | 5 | 10 | 20 | 50 |
|---|---|---|---|---|---|
| Chi phí phân bổ / khách / năm | 474 tr | 119 tr | 90 tr | 75 tr | 66 tr |

**Hệ quả định giá (giả thuyết cần thử):** giá thuê bao phải ≥ chi phí biên (~60 tr/khách/năm trong mô hình này) cộng phần phân bổ CAPEX. Định giá theo giá trị ≈ 15–20% lợi ích cơ sở (565 tr) ≈ **85–113 triệu/khách/năm** cho DN cỡ ~215 tỷ doanh thu cho biên dương từ N ≈ 10–20; với DN nhỏ hơn (lợi ích thấp hơn) cần giảm chi phí biên (tự động hóa onboarding, dùng chung GPU) xuống dưới ~15 triệu/khách/năm mới bán được mức 24–36 triệu/năm. Nghiên cứu mức sẵn sàng chi trả ở `1_business_analyst/03` và `07`.

## 7. Kết luận
1. Với **một** DN doanh thu ~215 tỷ, tự xây từ đầu **chưa chắc có lời** nếu chỉ tính giờ kế toán; giá trị nằm ở **vốn lưu động và nợ xấu**.
2. Cần **chứng minh bằng pilot** rằng việc nhìn thấy sớm làm đổi hành vi thu hồi nợ (G5, G6); đây là giả thuyết kinh tế số 1 (`4_ai_engineering/05`, H‑biz).
3. Cách làm kinh tế nhất: **dùng lại lõi** cho nhiều khách hàng (SaaS/OEM), model nhỏ tại chỗ giữ chi phí biên thấp.
