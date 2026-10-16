# Metrics v0

Tất cả template dùng tham số `:start_date`, `:end_date`; số dư tài khoản dùng phát sinh lũy kế đến `:end_date`. Quy ước số dư: Nợ dương, Có âm (`debit_amount - credit_amount`). Tài khoản chi tiết được gom bằng `account_code` và có thể mở rộng bằng tiền tố.

## 1. `net_revenue`
- **Label:** Doanh thu thuần
- **Description:** Doanh thu bán hàng/cung cấp dịch vụ sau giảm trừ.
- **TT133:** Có 511; trừ Nợ 521 (hoặc tài khoản giảm trừ doanh thu được doanh nghiệp mở chi tiết).
- **Aggregation Logic:** `SUM(Có 511) - SUM(Nợ 521)`.
- **SQL Template:** `SELECT SUM(CASE WHEN a.account_code LIKE '511%' THEN g.credit_amount-g.debit_amount ELSE 0 END)-SUM(CASE WHEN a.account_code LIKE '521%' THEN g.debit_amount-g.credit_amount ELSE 0 END) AS net_revenue FROM gl_entry g JOIN dim_account a USING(account_key) WHERE g.posting_date BETWEEN :start_date AND :end_date;`

## 2. `cogs`
- **Label:** Giá vốn hàng bán
- **Description:** Giá trị hàng hóa/dịch vụ đã tiêu thụ trong kỳ.
- **TT133:** Nợ 632, Có 154/156.
- **Aggregation Logic:** `SUM(Nợ 632 - Có 632)`.
- **SQL Template:** `SELECT SUM(g.debit_amount-g.credit_amount) AS cogs FROM gl_entry g JOIN dim_account a USING(account_key) WHERE a.account_code LIKE '632%' AND g.posting_date BETWEEN :start_date AND :end_date;`

## 3. `gross_profit`
- **Label:** Lợi nhuận gộp
- **Description:** Phần còn lại sau doanh thu thuần trừ giá vốn.
- **TT133:** 511, 521, 632.
- **Aggregation Logic:** `net_revenue - cogs`.
- **SQL Template:** `WITH x AS (SELECT SUM(CASE WHEN a.account_code LIKE '511%' THEN g.credit_amount-g.debit_amount WHEN a.account_code LIKE '521%' THEN -(g.debit_amount-g.credit_amount) ELSE 0 END) revenue, SUM(CASE WHEN a.account_code LIKE '632%' THEN g.debit_amount-g.credit_amount ELSE 0 END) cogs FROM gl_entry g JOIN dim_account a USING(account_key) WHERE g.posting_date BETWEEN :start_date AND :end_date) SELECT revenue-cogs AS gross_profit FROM x;`

## 4. `operating_expenses`
- **Label:** Chi phí quản lý & bán hàng
- **Description:** Chi phí bán hàng và quản lý doanh nghiệp.
- **TT133:** Nợ 641, 642; Có 111/112/331/334/214...
- **Aggregation Logic:** `SUM(Nợ 641 + Nợ 642 - Có 641 - Có 642)`.
- **SQL Template:** `SELECT SUM(g.debit_amount-g.credit_amount) AS operating_expenses FROM gl_entry g JOIN dim_account a USING(account_key) WHERE (a.account_code LIKE '641%' OR a.account_code LIKE '642%') AND g.posting_date BETWEEN :start_date AND :end_date;`

## 5. `operating_profit`
- **Label:** Lợi nhuận thuần hoạt động kinh doanh
- **Description:** Lợi nhuận từ hoạt động kinh doanh trước thu nhập khác và thuế.
- **TT133:** 511/521/632/641/642/515/635.
- **Aggregation Logic:** `gross_profit - operating_expenses + finance_income - finance_cost`.
- **SQL Template:** `WITH m AS (SELECT SUM(CASE WHEN a.account_code LIKE '511%' THEN g.credit_amount-g.debit_amount WHEN a.account_code LIKE '521%' THEN -(g.debit_amount-g.credit_amount) WHEN a.account_code LIKE '632%' OR a.account_code LIKE '641%' OR a.account_code LIKE '642%' OR a.account_code LIKE '635%' THEN -(g.debit_amount-g.credit_amount) WHEN a.account_code LIKE '515%' THEN g.credit_amount-g.debit_amount ELSE 0 END) v FROM gl_entry g JOIN dim_account a USING(account_key) WHERE g.posting_date BETWEEN :start_date AND :end_date) SELECT v AS operating_profit FROM m;`

## 6. `net_profit`
- **Label:** Lợi nhuận sau thuế
- **Description:** Kết quả cuối kỳ sau chi phí thuế TNDN.
- **TT133:** 911 kết chuyển từ 821 và các TK doanh thu/chi phí.
- **Aggregation Logic:** `operating_profit + other_income - other_expense - income_tax`.
- **SQL Template:** `SELECT SUM(CASE WHEN a.account_code LIKE '511%' OR a.account_code LIKE '515%' THEN g.credit_amount-g.debit_amount WHEN a.account_code LIKE '632%' OR a.account_code LIKE '635%' OR a.account_code LIKE '641%' OR a.account_code LIKE '642%' OR a.account_code LIKE '811%' OR a.account_code LIKE '821%' THEN -(g.debit_amount-g.credit_amount) ELSE 0 END) AS net_profit FROM gl_entry g JOIN dim_account a USING(account_key) WHERE g.posting_date BETWEEN :start_date AND :end_date;`

## 7. `cash_and_equivalents`
- **Label:** Tiền mặt và tiền gửi ngân hàng
- **Description:** Số dư cuối kỳ của tiền mặt và tiền gửi.
- **TT133:** 111, 112.
- **Aggregation Logic:** `SUM(Nợ - Có)` lũy kế.
- **SQL Template:** `SELECT SUM(g.debit_amount-g.credit_amount) AS cash_and_equivalents FROM gl_entry g JOIN dim_account a USING(account_key) WHERE a.account_code LIKE '111%' OR a.account_code LIKE '112%' AND g.posting_date <= :end_date;`

## 8. `ar_balance`
- **Label:** Tổng công nợ phải thu khách hàng
- **Description:** Phải thu khách hàng còn chưa thu tại cuối kỳ.
- **TT133:** 131 (dư Nợ).
- **Aggregation Logic:** `SUM(Nợ 131 - Có 131)` đến ngày cuối.
- **SQL Template:** `SELECT SUM(g.debit_amount-g.credit_amount) AS ar_balance FROM gl_entry g JOIN dim_account a USING(account_key) WHERE a.account_code LIKE '131%' AND g.posting_date <= :end_date;`

## 9. `ar_by_customer`
- **Label:** Công nợ phải thu theo từng khách hàng
- **Description:** Số phải thu phân rã theo khách hàng.
- **TT133:** 131.
- **Aggregation Logic:** Gom `partner_key`, `SUM(Nợ-Có)`.
- **SQL Template:** `SELECT p.partner_code,p.partner_name,SUM(g.debit_amount-g.credit_amount) balance FROM gl_entry g JOIN dim_account a USING(account_key) JOIN dim_partner p USING(partner_key) WHERE a.account_code LIKE '131%' AND p.partner_type='CUSTOMER' AND g.posting_date <= :end_date GROUP BY 1,2 ORDER BY balance DESC;`

## 10. `ap_balance`
- **Label:** Tổng công nợ phải trả người bán
- **Description:** Phải trả nhà cung cấp còn chưa thanh toán.
- **TT133:** 331 (dư Có).
- **Aggregation Logic:** `SUM(Có 331 - Nợ 331)` đến cuối kỳ.
- **SQL Template:** `SELECT SUM(g.credit_amount-g.debit_amount) AS ap_balance FROM gl_entry g JOIN dim_account a USING(account_key) WHERE a.account_code LIKE '331%' AND g.posting_date <= :end_date;`

## 11. `ap_by_vendor`
- **Label:** Công nợ phải trả theo từng nhà cung cấp
- **Description:** Số phải trả phân rã theo nhà cung cấp.
- **TT133:** 331.
- **Aggregation Logic:** Gom `partner_key`, `SUM(Có-Nợ)`.
- **SQL Template:** `SELECT p.partner_code,p.partner_name,SUM(g.credit_amount-g.debit_amount) balance FROM gl_entry g JOIN dim_account a USING(account_key) JOIN dim_partner p USING(partner_key) WHERE a.account_code LIKE '331%' AND p.partner_type='VENDOR' AND g.posting_date <= :end_date GROUP BY 1,2 ORDER BY balance DESC;`

## 12. `net_cash_flow`
- **Label:** Dòng tiền thuần trong kỳ
- **Description:** Biến động tiền mặt và tiền gửi trong kỳ.
- **TT133:** 111, 112.
- **Aggregation Logic:** `SUM(Nợ tiền - Có tiền)` trong kỳ.
- **SQL Template:** `SELECT SUM(g.debit_amount-g.credit_amount) AS net_cash_flow FROM gl_entry g JOIN dim_account a USING(account_key) WHERE (a.account_code LIKE '111%' OR a.account_code LIKE '112%') AND g.posting_date BETWEEN :start_date AND :end_date;`

## 13. `dso`
- **Label:** Số ngày thu hồi nợ bình quân
- **Description:** Số ngày doanh thu bình quân bị giữ trong phải thu.
- **TT133:** 131 và 511/521.
- **Aggregation Logic:** `AR bình quân / doanh thu thuần kỳ * số ngày kỳ`.
- **SQL Template:** `WITH ar AS (SELECT AVG(v) v FROM (SELECT SUM(g.debit_amount-g.credit_amount) v FROM gl_entry g JOIN dim_account a USING(account_key) WHERE a.account_code LIKE '131%' AND g.posting_date <= :end_date GROUP BY date_trunc('month',g.posting_date)) s), rev AS (SELECT SUM(g.credit_amount-g.debit_amount) v FROM gl_entry g JOIN dim_account a USING(account_key) WHERE a.account_code LIKE '511%' AND g.posting_date BETWEEN :start_date AND :end_date) SELECT ar.v/NULLIF(rev.v,0)*(DATE_DIFF('day',CAST(:start_date AS DATE),CAST(:end_date AS DATE))+1) dso FROM ar,rev;`

## 14. `salary_expense`
- **Label:** Chi phí lương nhân viên
- **Description:** Chi phí tiền lương, tiền công phát sinh.
- **TT133:** Nợ 641/642 (hoặc 154), Có 334.
- **Aggregation Logic:** Tổng Nợ chi phí đối ứng Có 334; bản v0 dùng phát sinh Nợ 641/642.
- **SQL Template:** `SELECT SUM(g.debit_amount-g.credit_amount) salary_expense FROM gl_entry g JOIN dim_account a USING(account_key) WHERE (a.account_code LIKE '641%' OR a.account_code LIKE '642%') AND g.posting_date BETWEEN :start_date AND :end_date;`

## 15. `tax_payable`
- **Label:** Thuế và các khoản phải nộp Nhà nước
- **Description:** Nghĩa vụ thuế còn phải nộp cuối kỳ.
- **TT133:** 333 (đặc biệt 3331, 3334).
- **Aggregation Logic:** `SUM(Có 333 - Nợ 333)` lũy kế.
- **SQL Template:** `SELECT SUM(g.credit_amount-g.debit_amount) tax_payable FROM gl_entry g JOIN dim_account a USING(account_key) WHERE a.account_code LIKE '333%' AND g.posting_date <= :end_date;`

## 16. `inventory_value`
- **Label:** Giá trị hàng tồn kho
- **Description:** Giá trị tồn kho cuối kỳ.
- **TT133:** 152, 153, 154, 155, 156, 157.
- **Aggregation Logic:** `SUM(Nợ-Có)` lũy kế các TK tồn kho.
- **SQL Template:** `SELECT SUM(g.debit_amount-g.credit_amount) inventory_value FROM gl_entry g JOIN dim_account a USING(account_key) WHERE LEFT(a.account_code,3) IN ('152','153','154','155','156','157') AND g.posting_date <= :end_date;`

