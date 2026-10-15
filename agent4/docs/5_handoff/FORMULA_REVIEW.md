# Bảng rà soát công thức (FORMULA_REVIEW)

> Sinh tự động từ `agent4/engine/metrics.py` bằng kỳ mẫu **2026-Q3** (view mặc định). Cột *Kết quả rà soát* để trống cho kế toán/coding agent điền khi thực hiện T0.2 (oracle) và T0.6 (họp kế toán). `P` = ưu tiên Must.

Trạng thái: ĐỒNG Ý / SỬA / BỎ / HỎI THÊM. Khi SỬA ghi định nghĩa mới + commit.

| P | Chỉ số | Nhãn | Loại | Đơn vị | Công thức (trong code) | TK liên quan | Giá trị Q3/2026 (engine) | Oracle độc lập | Kết quả rà soát |
|---|---|---|---|---|---|---|---|---|---|
| **P** | `net_revenue` | Doanh thu thuần | flow | VND | Có 511 − Nợ 511 (giảm trừ theo TT133) − Nợ 521 (nếu có); không tính bút toán kết chuyển 911 | 511, 521 | 55,79 tỷ đồng | _chưa_ | _chưa_ |
|  | `gross_revenue` | Doanh thu bán hàng (trước giảm trừ) | flow | VND | Tổng phát sinh Có 511 (không gồm kết chuyển) | 511 | 55,94 tỷ đồng | _chưa_ | _chưa_ |
|  | `revenue_deductions` | Các khoản giảm trừ doanh thu | flow | VND | Phát sinh Nợ 511 (không gồm kết chuyển) + Nợ 521 | 511, 521 | 145 triệu đồng | _chưa_ | _chưa_ |
|  | `goods_revenue` | Doanh thu bán hàng hóa | flow | VND | Có 5111 − Nợ 5111 | 5111 | 51,26 tỷ đồng | _chưa_ | _chưa_ |
|  | `service_revenue` | Doanh thu dịch vụ | flow | VND | Có 5113 − Nợ 5113 | 5113 | 4,53 tỷ đồng | _chưa_ | _chưa_ |
| **P** | `cogs` | Giá vốn hàng bán | flow | VND | Nợ 632 − Có 632 (không gồm kết chuyển) | 632 | 45,85 tỷ đồng | _chưa_ | _chưa_ |
| **P** | `gross_profit` | Lợi nhuận gộp | flow | VND | Doanh thu thuần − Giá vốn hàng bán | 511, 521, 632 | 9,94 tỷ đồng | _chưa_ | _chưa_ |
| **P** | `gross_margin_pct` | Biên lợi nhuận gộp | ratio | % | (Doanh thu thuần − Giá vốn) / Doanh thu thuần × 100 | 511, 521, 632 | 17,8% | _chưa_ | _chưa_ |
|  | `selling_expenses` | Chi phí bán hàng | flow | VND | Nợ 6421 − Có 6421 (+ 641 nếu dùng TT200) | 6421, 641 | 6,89 tỷ đồng | _chưa_ | _chưa_ |
|  | `admin_expenses` | Chi phí quản lý doanh nghiệp | flow | VND | Nợ 6422 − Có 6422 | 6422 | 3,22 tỷ đồng | _chưa_ | _chưa_ |
| **P** | `operating_expenses` | Chi phí bán hàng và quản lý doanh nghiệp | flow | VND | Nợ 642 − Có 642 (+ 641) | 641, 642 | 10,12 tỷ đồng | _chưa_ | _chưa_ |
|  | `finance_income` | Doanh thu hoạt động tài chính | flow | VND | Có 515 − Nợ 515 | 515 | 2,88 triệu đồng | _chưa_ | _chưa_ |
|  | `finance_cost` | Chi phí tài chính (lãi vay) | flow | VND | Nợ 635 − Có 635 | 635 | 494 triệu đồng | _chưa_ | _chưa_ |
|  | `operating_profit` | Lợi nhuận thuần từ hoạt động kinh doanh | flow | VND | LN gộp − (6421 + 6422) + 515 − 635 | 511, 521, 632, 642, 515, 635 | -666 triệu đồng | _chưa_ | _chưa_ |
|  | `other_income` | Thu nhập khác | flow | VND | Có 711 − Nợ 711 | 711 | 0 đồng | _chưa_ | _chưa_ |
|  | `other_expenses` | Chi phí khác | flow | VND | Nợ 811 − Có 811 | 811 | 0 đồng | _chưa_ | _chưa_ |
| **P** | `profit_before_tax` | Lợi nhuận trước thuế | flow | VND | LN thuần HĐKD + 711 − 811 | 511, 521, 632, 642, 515, 635, 711, 811 | -666 triệu đồng | _chưa_ | _chưa_ |
|  | `income_tax_expense` | Chi phí thuế TNDN | flow | VND | Nợ 821 − Có 821 | 821 | 0 đồng | _chưa_ | _chưa_ |
| **P** | `net_profit` | Lợi nhuận sau thuế | flow | VND | LN trước thuế − Chi phí thuế TNDN (821) | 511, 521, 632, 642, 515, 635, 711, 811, 821 | -666 triệu đồng | _chưa_ | _chưa_ |
|  | `net_margin_pct` | Biên lợi nhuận ròng | ratio | % | LNST / Doanh thu thuần × 100 | 511, 521, 632, 642, 515, 635, 711, 811, 821 | -1,2% | _chưa_ | _chưa_ |
|  | `ebitda` | EBITDA | flow | VND | LN trước thuế + Chi phí lãi vay (635) + Khấu hao (Có 214) | 511, 632, 642, 515, 635, 711, 811, 214 | 199 triệu đồng | _chưa_ | _chưa_ |
|  | `depreciation_expense` | Chi phí khấu hao TSCĐ | flow | VND | Phát sinh Có 214 từ bút toán khấu hao | 214 | 372 triệu đồng | _chưa_ | _chưa_ |
| **P** | `salary_expense` | Chi phí lương nhân viên | flow | VND | Nợ 6421/6422/154 khoản mục Lương + Thưởng (đối ứng Có 334/335) | 642, 154, 334 | 5,25 tỷ đồng | _chưa_ | _chưa_ |
|  | `labor_cost` | Tổng chi phí nhân sự | flow | VND | Nợ 6421/6422/154 khoản mục Lương + Thưởng + Bảo hiểm | 642, 154, 334, 338 | 6,33 tỷ đồng | _chưa_ | _chưa_ |
| **P** | `cash_and_equivalents` | Tiền mặt và tiền gửi ngân hàng | snapshot | VND | Số dư Nợ 111 + 112 lũy kế đến ngày cuối kỳ | 111, 112 | 7,53 tỷ đồng | _chưa_ | _chưa_ |
|  | `term_deposits` | Tiền gửi có kỳ hạn | snapshot | VND | Số dư Nợ 128 | 128 | 5 tỷ đồng | _chưa_ | _chưa_ |
| **P** | `ar_balance` | Phải thu khách hàng | snapshot | VND | Số dư Nợ 131 − Có 131 lũy kế | 131 | 42,13 tỷ đồng | _chưa_ | _chưa_ |
|  | `ar_by_customer` | Công nợ phải thu theo khách hàng | snapshot | VND | Số dư 131 theo đối tượng khách hàng | 131 | 42,13 tỷ đồng | _chưa_ | _chưa_ |
|  | `ar_by_salesperson` | Công nợ phải thu theo nhân viên phụ trách | snapshot | VND | Số dư 131 theo nhân viên phụ trách | 131 | 42,13 tỷ đồng | _chưa_ | _chưa_ |
| **P** | `ap_balance` | Phải trả người bán | snapshot | VND | Số dư Có 331 − Nợ 331 lũy kế | 331 | 20,73 tỷ đồng | _chưa_ | _chưa_ |
|  | `ap_by_vendor` | Công nợ phải trả theo nhà cung cấp | snapshot | VND | Số dư 331 theo nhà cung cấp | 331 | 20,73 tỷ đồng | _chưa_ | _chưa_ |
| **P** | `inventory_value` | Giá trị hàng tồn kho | snapshot | VND | Số dư Nợ 151–157 lũy kế | 152, 153, 154, 155, 156, 157 | 25,11 tỷ đồng | _chưa_ | _chưa_ |
| **P** | `tax_payable` | Thuế và các khoản phải nộp Nhà nước | snapshot | VND | Số dư Có 333 lũy kế | 333 | 59,1 triệu đồng | _chưa_ | _chưa_ |
|  | `debt_balance` | Dư nợ vay | snapshot | VND | Số dư Có 341 lũy kế | 341 | 25,14 tỷ đồng | _chưa_ | _chưa_ |
|  | `fixed_assets_net` | Giá trị còn lại TSCĐ | snapshot | VND | Số dư 211 − 214 | 211, 214 | 5,38 tỷ đồng | _chưa_ | _chưa_ |
|  | `total_assets` | Tổng tài sản | snapshot | VND | Tổng số dư các TK loại 1, 2 (sau dự phòng, hao mòn) | 1, 2 | 85,17 tỷ đồng | _chưa_ | _chưa_ |
|  | `total_liabilities` | Tổng nợ phải trả | snapshot | VND | Tổng số dư Có các TK loại 3 | 3 | 48,01 tỷ đồng | _chưa_ | _chưa_ |
|  | `equity` | Vốn chủ sở hữu | snapshot | VND | Số dư Có loại 4 + kết quả chưa kết chuyển (loại 5–9) | 4 | 37,16 tỷ đồng | _chưa_ | _chưa_ |
|  | `working_capital` | Vốn lưu động ròng | snapshot | VND | TS ngắn hạn (111–157, 229) − Nợ ngắn hạn (331, 333–338, vay ngắn hạn 34111) | 1, 33, 34111 | 36,88 tỷ đồng | _chưa_ | _chưa_ |
| **P** | `current_ratio` | Hệ số thanh toán hiện hành | ratio | ratio | TS ngắn hạn / Nợ ngắn hạn | 1, 33, 34111 | 1,86 lần | _chưa_ | _chưa_ |
|  | `quick_ratio` | Hệ số thanh toán nhanh | ratio | ratio | (TS ngắn hạn − Tồn kho) / Nợ ngắn hạn | 1, 15, 33, 34111 | 1,27 lần | _chưa_ | _chưa_ |
|  | `debt_to_equity` | Hệ số nợ vay / vốn chủ sở hữu | ratio | ratio | Dư nợ 341 / Vốn chủ sở hữu | 341, 4 | 0,68 lần | _chưa_ | _chưa_ |
| **P** | `net_cash_flow` | Dòng tiền thuần trong kỳ | flow | VND | Phát sinh Nợ − Có của 111 + 112 trong kỳ | 111, 112 | 1,62 tỷ đồng | _chưa_ | _chưa_ |
|  | `cash_flow_breakdown` | Dòng tiền theo nhóm thu/chi | custom | VND | Phát sinh 111/112 phân loại theo tài khoản đối ứng của chứng từ (phương pháp trực tiếp) | 111, 112 | 1,62 tỷ đồng | _chưa_ | _chưa_ |
|  | `cash_coverage_days` | Số ngày tiền hiện có đủ chi trả | custom | days | Số dư 111+112 / (Tổng chi tiền 90 ngày trước ÷ 90) | 111, 112 | 11 ngày | _chưa_ | _chưa_ |
| **P** | `ar_aging` | Tuổi nợ phải thu | custom | VND | Sổ chi tiết hóa đơn bán: số còn phải thu theo hạn thanh toán; khoản trả trước/chiết khấu chưa phân bổ cấn trừ hóa đơn cũ nhất | 131 | 42,13 tỷ đồng | _chưa_ | _chưa_ |
| **P** | `overdue_receivables` | Các khoản phải thu quá hạn | custom | VND | Hóa đơn có ngày đến hạn < ngày cuối kỳ − N và còn số phải thu > 0 | 131 | 9,35 tỷ đồng | _chưa_ | _chưa_ |
| **P** | `dso` | Số ngày thu tiền bình quân (DSO) | custom | days | ((Dư 131 đầu kỳ + cuối kỳ) / 2) / Phát sinh Nợ 131 từ hóa đơn bán × số ngày kỳ | 131, 511 | 62 ngày | _chưa_ | _chưa_ |
|  | `dso_actual` | Số ngày thực tế khách thanh toán | custom | days | Σ(số tiền × (ngày thu − ngày hóa đơn)) / Σ số tiền thu | 131 | 63 ngày | _chưa_ | _chưa_ |
|  | `dpo` | Số ngày trả tiền bình quân (DPO) | custom | days | ((Dư 331 đầu + cuối) / 2) / Phát sinh Có 331 từ hóa đơn mua × số ngày | 331 | 37 ngày | _chưa_ | _chưa_ |
|  | `dio` | Số ngày tồn kho bình quân (DIO) | custom | days | ((Tồn kho đầu + cuối) / 2) / Giá vốn hàng bán × số ngày | 156, 632 | 50 ngày | _chưa_ | _chưa_ |
|  | `cash_conversion_cycle` | Chu kỳ chuyển đổi tiền mặt | custom | days | DSO + DIO − DPO | 131, 156, 331 | 75 ngày | _chưa_ | _chưa_ |
| **P** | `ap_due_soon` | Khoản phải trả sắp đến hạn | custom | VND | Sổ chi tiết hóa đơn mua: số còn phải trả có hạn thanh toán ≤ ngày dữ liệu + N | 331 | 7,41 tỷ đồng | _chưa_ | _chưa_ |
| **P** | `upcoming_obligations` | Nghĩa vụ thanh toán sắp tới | custom | VND | Công nợ 331 đến hạn + số dư 333, 338, 334 + lương ước tính + lịch trả nợ vay | 331, 333, 334, 338, 341 | 1,75 tỷ đồng | _chưa_ | _chưa_ |
|  | `expense_by_category` | Chi phí theo khoản mục | flow | VND | Nợ 642 − Có 642 nhóm theo khoản mục chi phí | 642, 641 | 10,12 tỷ đồng | _chưa_ | _chưa_ |
| **P** | `expense_spikes` | Khoản chi phí tăng bất thường | custom | VND | Chi phí khoản mục kỳ này − bình quân 3 tháng liền trước; xếp theo mức tăng | 642, 154 | 2,58 tỷ đồng | _chưa_ | _chưa_ |
|  | `unusual_account_movements` | Tài khoản phát sinh bất thường | custom | count | /Phát sinh tháng − TB 6 tháng trước/ / độ lệch chuẩn ≥ 2,5 và chênh ≥ 50 triệu |  | 2 | _chưa_ | _chưa_ |
|  | `unbalanced_journals` | Chứng từ không cân đối Nợ/Có | custom | count | Nhóm theo số chứng từ: Σ Nợ ≠ Σ Có |  | 1 | _chưa_ | _chưa_ |
|  | `top_sales_transactions` | Giao dịch bán hàng lớn nhất | custom | VND | Hóa đơn bán xếp theo giá trị trước thuế | 511 | 944 triệu đồng | _chưa_ | _chưa_ |
|  | `budget_vs_actual` | Thực hiện so với kế hoạch | custom | VND | Thực tế (511, 642 theo khoản mục) so với bảng ngân sách; tháng dở dang được phân bổ theo số ngày | 511, 642 | -8,18 triệu đồng | _chưa_ | _chưa_ |
|  | `payroll_summary` | Tổng hợp quỹ lương & nhân sự | custom | VND | Bảng lương chi tiết theo nhân viên (đối chiếu 334/338) | 334, 338, 3335 | 6,33 tỷ đồng | _chưa_ | _chưa_ |
| **P** | `taxable_income` | Thu nhập chịu thuế TNDN (ước tính) | flow | VND | Trên view thuế: 511 + 515 + 711 − (632 + 642 + 635 + 811), chỉ gồm dòng được trừ | 511, 515, 711, 632, 642, 635, 811 | -481 triệu đồng | _chưa_ | _chưa_ |
|  | `cit_estimate` | Thuế TNDN phải nộp ước tính | custom | VND | max(0, Thu nhập chịu thuế) × 20% | 511, 632, 642, 821 | 0 đồng | _chưa_ | _chưa_ |
|  | `deductible_expenses` | Chi phí được trừ khi tính thuế | flow | VND | Trên view thuế: 632 + 642 + 635 + 811 (chỉ dòng được trừ) | 632, 642, 635, 811 | 56,28 tỷ đồng | _chưa_ | _chưa_ |
|  | `mgmt_vs_tax_gap` | Chênh lệch khung quản trị và khung thuế | custom | VND | Σ chi phí dòng tax_deductible = FALSE, theo lý do | 6, 8 | 186 triệu đồng | _chưa_ | _chưa_ |
|  | `vat_position` | Thuế GTGT trong kỳ | custom | VND | Đầu ra: Có 33311 từ hóa đơn bán; đầu vào: Nợ 1331 (khung thuế); phải nộp = đầu ra − đầu vào | 33311, 1331 | 499 triệu đồng | _chưa_ | _chưa_ |
