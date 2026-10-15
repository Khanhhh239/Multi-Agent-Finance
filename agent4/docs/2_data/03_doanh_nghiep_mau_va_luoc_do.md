# 03 · Doanh nghiệp mẫu "Minh Phát" và lược đồ kho dữ liệu

## 1. Hồ sơ doanh nghiệp (hư cấu)
| Mục | Giá trị |
|---|---|
| Tên | Công ty Cổ phần Thương mại và Dịch vụ Minh Phát |
| Ngành | Phân phối thiết bị CNTT, thiết bị văn phòng, vật tư tiêu hao + dịch vụ kỹ thuật (bảo trì, lắp đặt, cho thuê máy) |
| Chế độ kế toán | TT133/2016/TT‑BTC; VND; thuế TNDN 20% |
| Chi nhánh | Hà Nội (trụ sở, ~46% doanh thu) · TP.HCM (~39%) · Đà Nẵng (~15%) |
| Nhân sự | 90 người đang làm (92 hồ sơ, có 2 người nghỉ & thay), 7 phòng ban |
| Danh mục | 82 mã (38 hàng CNTT + 20 thiết bị văn phòng + 16 vật tư + 8 dịch vụ) trong 4 nhóm: IT / OFF / CON / SVC |
| Đối tác | 185 đối tác: 155 khách (23 DN lớn, 97 SME, 20 cơ quan nhà nước/trường học, 12 đại lý, 3 khách lẻ) + 30 nhà cung cấp |
| Thời gian | Số dư đầu kỳ 31/12/2024; giao dịch 01/01/2025 → **14/10/2026**; khóa sổ đến 08/2026 |
| Quy mô | Doanh thu 2025: **185,6 tỷ**; 2026 (đến 14/10): **169,0 tỷ**; biên gộp ≈ 19%; LNST 2025: 1,57 tỷ |
| Cấu trúc khách | DN lớn 54% doanh thu 2025; GOV 21%; SME 14%; lẻ 9%; đại lý 3%. Top‑10 khách ≈ 49% |
| Tài chính | Tiền & tiền gửi 3,19 tỷ (+5 tỷ tiết kiệm kỳ hạn); phải thu 47,6 tỷ; tồn kho 22,9 tỷ; phải trả 19,2 tỷ; vay 25,1 tỷ |

> Các con số ở đây lấy trực tiếp từ kho dữ liệu đã sinh (seed 20251). Xem tái lập: `5_handoff/04`.

## 2. Kho DuckDB (`data/cfo_warehouse.duckdb`, ~28 MB)

### 2.1 Sơ đồ khối
```
                       dim_period  dim_account  dim_branch  dim_department
                             \          |           /          /
 dim_partner ──────────────► gl_entry (FACT, 140.583 dòng) ◄── dim_item
 dim_employee ─────────────►   │  (journal_id → gl_journal)  ◄── dim_cost_category
                               │                                dim_product_line
   Sổ chi tiết (liên kết bằng journal_id)               Views
   ar_invoice ─ ar_invoice_line ─ ar_receipt ─ ar_adjustment     gl_wide (phi chuẩn hóa)
   ap_bill ─ ap_payment                                          v_gl ← gl_wide
   inventory_txn · payroll · fixed_asset · loan · loan_schedule  v_mgmt = v_gl
   service_contract · budget · period_close · company_info        v_tax  = v_gl WHERE tax_deductible
   ground_truth (nhãn sự thật)
```

### 2.2 Bảng chính và số dòng
| Bảng | Dòng | Vai trò |
|---|---|---|
| `gl_entry` | 140.583 | **Fact** sổ cái ở cấp dòng bút toán; CHECK Nợ/Có XOR, ≥ 0 |
| `gl_journal` | 39.481 | Chứng từ (loại, số, module nguồn, người lập, giờ lập, cờ kết chuyển) |
| `ar_invoice` / `_line` | 12.860 / 26.170 | Hóa đơn bán & dòng hàng (kèm giá vốn) |
| `ar_receipt` | 12.530 | Thu tiền, có `bank_txn_date` ≠ `receipt_date` (hạch toán lô) |
| `ar_adjustment` | 60 | Trả hàng, chiết khấu thương mại |
| `ap_bill` / `ap_payment` | 968 / 933 | Hóa đơn mua / thanh toán |
| `inventory_txn` | 26.158 | Nhập/xuất/tiêu hao/trả hàng theo mã |
| `payroll` | 1.890 | Bảng lương theo nhân viên × tháng |
| `fixed_asset`, `loan`, `loan_schedule` | 15 / 3 / 39 | TSCĐ, khoản vay, lịch trả gốc |
| `budget` | 824 | Ngân sách tháng × chi nhánh × khoản mục |
| `period_close` | 22 | Trạng thái khóa sổ từng tháng |
| `ground_truth` | 20 | Ca cài chủ đích (xem `05`) |

### 2.3 Các cột nghiệp vụ quan trọng trên `gl_entry`
| Cột | Ý nghĩa | Dùng bởi |
|---|---|---|
| `account_key` → `account_code` | TK TT133 (60 tài khoản, có cấp 1/2/3) | mọi chỉ số |
| `partner_key` | khách/NCC/(nhân viên) | công nợ |
| `branch_key`, `department_key`, `employee_key` | chiều quản trị | phân rã, phân quyền |
| `product_line`, `item_key` | nhóm/mã hàng | biên lợi nhuận theo SP |
| `cost_category` | **khoản mục chi phí** (19 loại: lương, thuê, marketing…) | `expense_by_category`, `expense_spikes` |
| `is_closing` | bút toán kết chuyển 911 | bị loại khi tính dòng chảy |
| `tax_deductible`, `tax_note` | cờ & lý do chi phí không được trừ | `v_tax`, `mgmt_vs_tax_gap` |
| `source_module`, `source_document_type`, `created_by`, `created_at` | nguồn, loại chứng từ, người & giờ lập | bất thường (giờ ngoài hành chính, ...) |

## 3. Đặc thù TT133 trong dữ liệu
| Điểm | Cách thể hiện |
|---|---|
| Không có TK 521 | Hàng trả lại/chiết khấu ghi **Nợ 511** (`revenue_deductions`) |
| Chi phí bán hàng / quản lý | **6421 / 6422** (cha 642) |
| TK vay | `34111` ngắn hạn (hạn mức xoay vòng), `34112` dài hạn |
| Dự phòng phải thu khó đòi | 2293 theo bậc TT48/2019 (30%/50%/70%/100%) — trích tại 31/12/2025 & 30/06/2026 |
| Thuế GTGT | `33311` đầu ra, `1331` đầu vào; khấu trừ cuối tháng, nộp ngày 20 |
| Kết chuyển | 911/4212 chỉ cho các tháng **đã khóa sổ**; tháng 09–10/2026 mở |

## 4. Hai khung nhìn
- `v_mgmt`: 100% dòng sổ cái (kể cả chi phí không hợp lệ thuế).
- `v_tax`: chỉ dòng `tax_deductible = TRUE`. Lý do không được trừ được sinh có chủ đích: chi không hóa đơn (`NO_VALID_INVOICE`), thanh toán tiền mặt ≥ 5 triệu cho hóa đơn VAT (`CASH_OVER_THRESHOLD`), tiền phạt (`ADMIN_PENALTY`), tiền chậm nộp thuế (`LATE_PAYMENT_INTEREST`).
- **Giới hạn:** `v_tax` hiện chỉ lọc theo cờ, chưa mô phỏng quy tắc "chi vượt định mức" (ví dụ khấu hao xe trên 1,6 tỷ, trích lập dự phòng...) — mở rộng trong `5_handoff`.

## 5. Dữ liệu có chủ đích **không** thật (hạn chế)
- Tên DN, MST, nhân viên là hư cấu; tên ngẫu nhiên có thể trùng thương hiệu thật ngoài ý muốn → đã đổi các tên giống thương hiệu thật.
- Biểu thuế TNCN trong bộ sinh dùng **7 bậc**; luật mới có thể áp dụng biểu khác từ giữa 2026 (🔎 cần xác minh và cập nhật).
- Giảm trừ gia cảnh 11 triệu (2025) / 15,5 triệu (2026) là giả định cần xác minh.
- Mới có **1 công ty** và **1 tiền tệ**; chưa có liên công ty, ngoại tệ, đóng cửa kỳ lùi ngày.
