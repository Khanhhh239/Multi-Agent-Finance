# Rà soát công thức — kết quả kỹ thuật và hồ sơ T0.6

Ngày đo: 16/10/2026. Dữ liệu tổng hợp seed 20251; không phải xác nhận tính đúng pháp lý hay phê duyệt kế toán.
Oracle độc lập: **396/396** ô, 66 chỉ số × 6 kỳ. Oracle đọc bảng gốc, không import engine.
p95 truy vấn trong lượt đối chiếu: 38.56 ms trên 140,583 dòng; chưa đại diện tải đồng thời.

**G0.7: CHỜ DUYỆT.** Người duyệt: ______. Chức danh: ______. Ngày: ______. Chữ ký/xác nhận: ______.

Các kỳ: tháng khóa 08/2026; tháng dở dang 10/2026; Q3/2026; năm 2025; YTD; 15/06–15/07/2025.

| Ưu tiên | Chỉ số | Nhãn | Công thức | Engine Q3 | Oracle Q3 | Đối chiếu | Câu hỏi kế toán | Duyệt |
|---|---|---|---|---:|---:|---|---|---|
| **Must — cần duyệt trước pilot** | `net_revenue` | Doanh thu thuần | Có 511 − Nợ 511 (giảm trừ theo TT133) − Nợ 521 (nếu có); không tính bút toán kết chuyển 911 | 55792824000.0 | 55792824000.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `gross_revenue` | Doanh thu bán hàng (trước giảm trừ) | Tổng phát sinh Có 511 (không gồm kết chuyển) | 55937533000.0 | 55937533000.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `revenue_deductions` | Các khoản giảm trừ doanh thu | Phát sinh Nợ 511 (không gồm kết chuyển) + Nợ 521 | 144709000.0 | 144709000.0 | KHỚP | Xác nhận Nợ 511 TT133 + net Nợ 521 TT200. | CHỜ |
|  | `goods_revenue` | Doanh thu bán hàng hóa | Có 5111 − Nợ 5111 | 51258071000.0 | 51258071000.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `service_revenue` | Doanh thu dịch vụ | Có 5113 − Nợ 5113 | 4534753000.0 | 4534753000.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `cogs` | Giá vốn hàng bán | Nợ 632 − Có 632 (không gồm kết chuyển) | 45852513186.0 | 45852513186.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `gross_profit` | Lợi nhuận gộp | Doanh thu thuần − Giá vốn hàng bán | 9940310814.0 | 9940310814.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `gross_margin_pct` | Biên lợi nhuận gộp | (Doanh thu thuần − Giá vốn) / Doanh thu thuần × 100 | 17.81646832216272 | 17.81646832216272 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `selling_expenses` | Chi phí bán hàng | Nợ 6421 − Có 6421 (+ 641 nếu dùng TT200) | 6893216857.0 | 6893216857.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `admin_expenses` | Chi phí quản lý doanh nghiệp | Nợ 6422 − Có 6422 | 3222722866.0 | 3222722866.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `operating_expenses` | Chi phí bán hàng và quản lý doanh nghiệp | Nợ 642 − Có 642 (+ 641) | 10115939723.0 | 10115939723.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `finance_income` | Doanh thu hoạt động tài chính | Có 515 − Nợ 515 | 2879000.0 | 2879000.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `finance_cost` | Chi phí tài chính (lãi vay) | Nợ 635 − Có 635 | 493638000.0 | 493638000.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `operating_profit` | Lợi nhuận thuần từ hoạt động kinh doanh | LN gộp − (6421 + 6422) + 515 − 635 | -666387909.0 | -666387909.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `other_income` | Thu nhập khác | Có 711 − Nợ 711 | 0.0 | -0.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `other_expenses` | Chi phí khác | Nợ 811 − Có 811 | 0.0 | 0.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `profit_before_tax` | Lợi nhuận trước thuế | LN thuần HĐKD + 711 − 811 | -666387909.0 | -666387909.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `income_tax_expense` | Chi phí thuế TNDN | Nợ 821 − Có 821 | 0.0 | 0.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `net_profit` | Lợi nhuận sau thuế | LN trước thuế − Chi phí thuế TNDN (821) | -666387909.0 | -666387909.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `net_margin_pct` | Biên lợi nhuận ròng | LNST / Doanh thu thuần × 100 | -1.1943971665603448 | -1.1943971665603448 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `ebitda` | EBITDA | LN trước thuế + Chi phí lãi vay (635) + Khấu hao (Có 214) | 199119141.0 | 199119141.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `depreciation_expense` | Chi phí khấu hao TSCĐ | Phát sinh Có 214 từ bút toán khấu hao | 371869050.0 | 371869050.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `salary_expense` | Chi phí lương nhân viên | Nợ 6421/6422/154 khoản mục Lương + Thưởng (đối ứng Có 334/335) | 5250914000.0 | 5250914000.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `labor_cost` | Tổng chi phí nhân sự | Nợ 6421/6422/154 khoản mục Lương + Thưởng + Bảo hiểm | 6326001323.0 | 6326001323.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `cash_and_equivalents` | Tiền mặt và tiền gửi ngân hàng | Số dư Nợ 111 + 112 lũy kế đến ngày cuối kỳ | 7532938209.0 | 7532938209.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `term_deposits` | Tiền gửi có kỳ hạn | Số dư Nợ 128 | 5000000000.0 | 5000000000.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `ar_balance` | Phải thu khách hàng | Số dư Nợ 131 − Có 131 lũy kế | 42130662400.0 | 42130662400.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `ar_by_customer` | Công nợ phải thu theo khách hàng | Số dư 131 theo đối tượng khách hàng | 42130662400.0 | 42130662400.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `ar_by_salesperson` | Công nợ phải thu theo nhân viên phụ trách | Số dư 131 theo nhân viên phụ trách | 42130662400.0 | 42130662400.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `ap_balance` | Phải trả người bán | Số dư Có 331 − Nợ 331 lũy kế | 20726235400.0 | 20726235400.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `ap_by_vendor` | Công nợ phải trả theo nhà cung cấp | Số dư 331 theo nhà cung cấp | 20726235400.0 | 20726235400.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `inventory_value` | Giá trị hàng tồn kho | Số dư Nợ 151–157 lũy kế | 25112419304.0 | 25112419304.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `tax_payable` | Thuế và các khoản phải nộp Nhà nước | Số dư Có 333 lũy kế | 59114716.0 | 59114716.0 | KHỚP | Khung mặc định tax có phù hợp với số dư nghĩa vụ pháp lý? | CHỜ |
|  | `debt_balance` | Dư nợ vay | Số dư Có 341 lũy kế | 25144444446.0 | 25144444446.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `fixed_assets_net` | Giá trị còn lại TSCĐ | Số dư 211 − 214 | 5381715262.0 | 5381715262.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `total_assets` | Tổng tài sản | Tổng số dư các TK loại 1, 2 (sau dự phòng, hao mòn) | 85170662508.0 | 85170662508.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `total_liabilities` | Tổng nợ phải trả | Tổng số dư Có các TK loại 3 | 48011853003.0 | 48011853003.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `equity` | Vốn chủ sở hữu | Số dư Có loại 4 + kết quả chưa kết chuyển (loại 5–9) | 37158309505.0 | 37158309505.0 | KHỚP | Xác nhận gồm kết quả chưa kết chuyển loại 5–9. | CHỜ |
|  | `working_capital` | Vốn lưu động ròng | TS ngắn hạn (111–157, 229) − Nợ ngắn hạn (331, 333–338, vay ngắn hạn 34111) | 36880705356.0 | 36880705356.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `current_ratio` | Hệ số thanh toán hiện hành | TS ngắn hạn / Nợ ngắn hạn | 1.860343710932757 | 1.860343710932757 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `quick_ratio` | Hệ số thanh toán nhanh | (TS ngắn hạn − Tồn kho) / Nợ ngắn hạn | 1.2745275827987579 | 1.2745275827987579 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `debt_to_equity` | Hệ số nợ vay / vốn chủ sở hữu | Dư nợ 341 / Vốn chủ sở hữu | 0.6766842943330503 | 0.6766842943330503 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `net_cash_flow` | Dòng tiền thuần trong kỳ | Phát sinh Nợ − Có của 111 + 112 trong kỳ | 1623124499.0 | 1623124499.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `cash_flow_breakdown` | Dòng tiền theo nhóm thu/chi | Phát sinh 111/112 phân loại theo tài khoản đối ứng của chứng từ (phương pháp trực tiếp) | 1623124499.0 | 1623124499.0 | KHỚP | Một chứng từ nhiều tài khoản đối ứng hiện được phân vào một nhóm ưu tiên: cần xác nhận. | CHỜ |
|  | `cash_coverage_days` | Số ngày tiền hiện có đủ chi trả | Số dư 111+112 / (Tổng chi tiền 90 ngày trước ÷ 90) | 11.152788819392805 | 11.152788819392805 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `ar_aging` | Tuổi nợ phải thu | Sổ chi tiết hóa đơn bán: số còn phải thu theo hạn thanh toán; khoản trả trước/chiết khấu chưa phân bổ cấn trừ hóa đơn cũ nhất | 42130662400.0 | 42130662400.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `overdue_receivables` | Các khoản phải thu quá hạn | Hóa đơn có ngày đến hạn < ngày cuối kỳ − N và còn số phải thu > 0 | 9350058600.0 | 9350058600.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `dso` | Số ngày thu tiền bình quân (DSO) | ((Dư 131 đầu kỳ + cuối kỳ) / 2) / Phát sinh Nợ 131 từ hóa đơn bán × số ngày kỳ | 61.59576498120317 | 61.59576498120317 | KHỚP | Xác nhận doanh số bán chịu gồm VAT, bình quân dư đầu/cuối và cách xử lý mẫu số 0. | CHỜ |
|  | `dso_actual` | Số ngày thực tế khách thanh toán | Σ(số tiền × (ngày thu − ngày hóa đơn)) / Σ số tiền thu | 62.80498988783955 | 62.80498988783955 | KHỚP | Xác nhận ngày ghi sổ hoặc ngày tiền về; mặc định receipt; bỏ khách lẻ RET. | CHỜ |
|  | `dpo` | Số ngày trả tiền bình quân (DPO) | ((Dư 331 đầu + cuối) / 2) / Phát sinh Có 331 từ hóa đơn mua × số ngày | 36.95503472112565 | 36.95503472112565 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `dio` | Số ngày tồn kho bình quân (DIO) | ((Tồn kho đầu + cuối) / 2) / Giá vốn hàng bán × số ngày | 49.905063510644624 | 49.905063510644624 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `cash_conversion_cycle` | Chu kỳ chuyển đổi tiền mặt | DSO + DIO − DPO | 74.54579377072213 | 74.54579377072213 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `ap_due_soon` | Khoản phải trả sắp đến hạn | Sổ chi tiết hóa đơn mua: số còn phải trả có hạn thanh toán ≤ ngày dữ liệu + N | 7413093000.0 | 7413093000.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `upcoming_obligations` | Nghĩa vụ thanh toán sắp tới | Công nợ 331 đến hạn + số dư 333, 338, 334 + lương ước tính + lịch trả nợ vay | 1746666626.0 | 1746666626.0 | KHỚP | Xác nhận ước tính lương/lãi và các nghĩa vụ quá hạn; đây là dự báo. | CHỜ |
|  | `expense_by_category` | Chi phí theo khoản mục | Nợ 642 − Có 642 nhóm theo khoản mục chi phí | 10115939723.0 | 10115939723.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `expense_spikes` | Khoản chi phí tăng bất thường | Chi phí khoản mục kỳ này − bình quân 3 tháng liền trước; xếp theo mức tăng | 2584507333.333333 | 2584507333.333333 | KHỚP | Bình quân 3 tháng so với tổng kỳ nhiều tháng có ý nghĩa? Hiện giữ định nghĩa cũ. | CHỜ |
|  | `unusual_account_movements` | Tài khoản phát sinh bất thường | /Phát sinh tháng − TB 6 tháng trước/ / độ lệch chuẩn ≥ 2,5 và chênh ≥ 50 triệu | 2.0 | 2.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `unbalanced_journals` | Chứng từ không cân đối Nợ/Có | Nhóm theo số chứng từ: Σ Nợ ≠ Σ Có | 1.0 | 1.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `top_sales_transactions` | Giao dịch bán hàng lớn nhất | Hóa đơn bán xếp theo giá trị trước thuế | 943920000.0 | 943920000.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `budget_vs_actual` | Thực hiện so với kế hoạch | Thực tế (511, 642 theo khoản mục) so với bảng ngân sách; tháng dở dang được phân bổ theo số ngày | -8176000.0 | -8176000.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `payroll_summary` | Tổng hợp quỹ lương & nhân sự | Bảng lương chi tiết theo nhân viên (đối chiếu 334/338) | 6326001323.0 | 6326001323.0 | KHỚP | Bảng lương theo tháng đầy đủ khi truy vấn cắt giữa tháng: cần chốt ngữ nghĩa. | CHỜ |
| **Must — cần duyệt trước pilot** | `taxable_income` | Thu nhập chịu thuế TNDN (ước tính) | Trên view thuế: 511 + 515 + 711 − (632 + 642 + 635 + 811), chỉ gồm dòng được trừ | -480778168.0 | -480778168.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `cit_estimate` | Thuế TNDN phải nộp ước tính | max(0, Thu nhập chịu thuế) × 20% | 0.0 | 0.0 | KHỚP | 20% là giả định mô phỏng; xác nhận ưu đãi/lỗ chuyển kỳ trước dùng thật. | CHỜ |
|  | `deductible_expenses` | Chi phí được trừ khi tính thuế | Trên view thuế: 632 + 642 + 635 + 811 (chỉ dòng được trừ) | 56276481168.0 | 56276481168.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `mgmt_vs_tax_gap` | Chênh lệch khung quản trị và khung thuế | Σ chi phí dòng tax_deductible = FALSE, theo lý do | 185609741.0 | 185609741.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |
|  | `vat_position` | Thuế GTGT trong kỳ | Đầu ra: Có 33311 từ hóa đơn bán; đầu vào: Nợ 1331 (khung thuế); phải nộp = đầu ra − đầu vào | 499200159.0 | 499200159.0 | KHỚP | Xác nhận công thức, dấu và khung trong định nghĩa. | CHỜ |

**công thức chưa được kế toán duyệt (G0.7 mở)** — G0.7 CHƯA ĐẠT.

## Ngoại lệ và giới hạn cần giữ minh bạch

- A4: chứng từ lệch Nợ/Có 500.000 đồng ngày 31/07/2026 là hard case có chủ đích. Phương trình kế toán nguyên trạng lệch đúng khoản này sau ngày đó; test đối chiếu và tách ngoại lệ, không sửa dữ liệu để làm xanh.
- Ngân sách dùng random() DuckDB không seed trong bản dữ liệu cũ; tái lập sổ cái được kiểm chứng riêng, không tuyên bố toàn kho tái lập.
- Các kết quả này kiểm chứng hiện thực so với định nghĩa; chưa thay thế phê duyệt độc lập của kế toán.
- P1/P2 chưa chạy vì handoff yêu cầu qua G0 trước. Không dùng seed val/test hay chạy Qwen để báo thành tích khi G0 chưa được duyệt.
