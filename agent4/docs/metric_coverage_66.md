# Coverage của 66 metric canonical

Báo cáo sinh bởi `python -m scripts.metric_coverage`.
Catalog runtime `catalog-ed5bd0d53bc9`.

Web demo liệt kê 66/66 ID trong registry.
Metric hiển thị bổ sung nằm ngoài registry gồm `budget_amount`.

- **Nguồn** ghi binding hiện có của pipeline governed. `metadata` là mô tả registry.
- **Chiều** và **view** ghi khai báo của catalog. Từng tổ hợp chiều, filter và kỳ
  vẫn cần fixture thực thi để xác nhận hỗ trợ.
- **Synthetic** là trạng thái của adapter Text-to-SQL đời trước trên fixture riêng.
- **MPX10** đếm cặp metric/view từ catalog baseline đóng băng. `legacy` dùng ID
  tương thích và có thể khác đơn vị. Cột này ghi bằng chứng hồi quy catalog.
- **Dev** đếm số câu có ID trong nhãn. **Số liệu đã duyệt** đếm `expected_result`
  đã review độc lập trong bộ dev hiện tại.

| Metric | Kiểu | Nhãn EN / alias | Nguồn | View | Chiều | Web | Synthetic | MPX10 | Dev | Số liệu đã duyệt |
|---|---|---:|---|---|---|---|---|---:|---:|---:|
| `net_revenue` | flow/flow | có / 7 | view | mgmt, tax, gl | month, quarter, year, branch_code, product_line, partner_code, segment | có | SUPPORTED | 3 | 33 | 0 |
| `gross_revenue` | flow/flow | có / 4 | view | mgmt, tax | month, quarter, year, branch_code | có | SUPPORTED | 0 | 0 | 0 |
| `revenue_deductions` | flow/flow | có / 5 | view | mgmt | month, quarter, year, branch_code | có | SUPPORTED | 0 | 0 | 0 |
| `goods_revenue` | flow/flow | có / 3 | view | mgmt, tax | month, quarter, year, branch_code | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `service_revenue` | flow/flow | có / 4 | view | mgmt, tax | month, quarter, year, branch_code | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `cogs` | flow/flow | có / 5 | view | mgmt, tax, gl | month, quarter, year, branch_code, product_line | có | SUPPORTED | 3 | 6 | 0 |
| `gross_profit` | flow/flow | có / 3 | view | mgmt, tax, gl | month, quarter, year, branch_code, product_line | có | SUPPORTED | 3 | 15 | 0 |
| `gross_margin_pct` | ratio/flow | có / 5 | view | mgmt, tax | month, quarter, year, branch_code, product_line | có | SUPPORTED | 2 legacy | 13 | 0 |
| `selling_expenses` | flow/flow | có / 2 | view | mgmt, tax | month, quarter, year, branch_code, department_code, cost_category, partner_code | có | EXECUTABLE_UNVERIFIED | 0 | 1 | 0 |
| `admin_expenses` | flow/flow | có / 4 | view | mgmt, tax | month, quarter, year, branch_code, department_code, cost_category, partner_code | có | EXECUTABLE_UNVERIFIED | 0 | 3 | 0 |
| `operating_expenses` | flow/flow | có / 10 | view | mgmt, tax, gl | month, quarter, year, branch_code, department_code, cost_category, partner_code | có | SUPPORTED | 3 legacy | 24 | 0 |
| `finance_income` | flow/flow | có / 3 | view | mgmt, tax | month, quarter, year | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `finance_cost` | flow/flow | có / 4 | view | mgmt, tax | month, quarter, year | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `operating_profit` | flow/flow | có / 6 | view | mgmt, tax | month, quarter, year, branch_code, department_code | có | SUPPORTED | 0 | 1 | 0 |
| `other_income` | flow/flow | có / 2 | view | mgmt, tax | — | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `other_expenses` | flow/flow | có / 3 | view | mgmt, tax | — | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `profit_before_tax` | flow/flow | có / 4 | view | mgmt, tax | month, quarter, year, branch_code, department_code | có | SUPPORTED | 0 | 1 | 0 |
| `income_tax_expense` | flow/flow | có / 3 | view | mgmt, tax | month, quarter, year, branch_code, department_code | có | SUPPORTED | 0 | 1 | 0 |
| `net_profit` | flow/flow | có / 5 | view | mgmt, tax | month, quarter, year, branch_code | có | SUPPORTED | 2 | 11 | 0 |
| `net_margin_pct` | ratio/flow | có / 4 | view | mgmt, tax | month, quarter, year, branch_code | có | SUPPORTED | 2 legacy | 9 | 0 |
| `ebitda` | flow/flow | có / 2 | view | mgmt | month, quarter, year | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `depreciation_expense` | flow/flow | có / 2 | view | mgmt | month, quarter, year | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `salary_expense` | flow/flow | có / 6 | view | mgmt, tax | month, quarter, year, branch_code, department_code, cost_category | có | EXECUTABLE_UNVERIFIED | 0 | 1 | 0 |
| `labor_cost` | flow/flow | có / 6 | view | mgmt, tax | month, quarter, year, branch_code, department_code | có | EXECUTABLE_UNVERIFIED | 2 legacy | 9 | 0 |
| `cash_and_equivalents` | snapshot/snapshot | có / 5 | view | mgmt, gl | branch_code | có | SUPPORTED | 2 legacy | 8 | 0 |
| `term_deposits` | snapshot/snapshot | có / 3 | view | mgmt | — | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `ar_balance` | snapshot/snapshot | có / 6 | view | mgmt, gl | branch_code, partner_code, segment | có | SUPPORTED | 2 | 8 | 0 |
| `ar_by_customer` | snapshot/snapshot | có / 5 | metric_query | mgmt | partner_code | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `ar_by_salesperson` | snapshot/snapshot | có / 4 | metric_query | mgmt | salesperson_code | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `ap_balance` | snapshot/snapshot | có / 6 | view | mgmt, gl | branch_code, partner_code | có | EXECUTABLE_UNVERIFIED | 2 | 6 | 0 |
| `ap_by_vendor` | snapshot/snapshot | có / 4 | metric_query | mgmt | partner_code | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `inventory_value` | snapshot/snapshot | có / 7 | view | mgmt | — | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `tax_payable` | snapshot/snapshot | có / 5 | view | mgmt, tax | — | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `debt_balance` | snapshot/snapshot | có / 6 | view | mgmt, gl | branch_code | có | EXECUTABLE_UNVERIFIED | 2 legacy | 4 | 0 |
| `fixed_assets_net` | snapshot/snapshot | có / 3 | view | mgmt | — | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `total_assets` | snapshot/snapshot | có / 2 | view | mgmt | — | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `total_liabilities` | snapshot/snapshot | có / 3 | view | mgmt | — | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `equity` | snapshot/snapshot | có / 4 | view | mgmt | — | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `working_capital` | snapshot/snapshot | có / 3 | view | mgmt | — | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `current_ratio` | ratio/snapshot | có / 4 | view | mgmt | month, quarter, year, branch_code | có | EXECUTABLE_UNVERIFIED | 0 | 1 | 0 |
| `quick_ratio` | ratio/snapshot | có / 3 | view | mgmt | month, quarter, year, branch_code | có | EXECUTABLE_UNVERIFIED | 0 | 1 | 0 |
| `debt_to_equity` | ratio/snapshot | có / 4 | view | mgmt | month, quarter, year, branch_code | có | EXECUTABLE_UNVERIFIED | 0 | 1 | 0 |
| `net_cash_flow` | flow/flow | có / 7 | view | mgmt | month, quarter, year | có | SUPPORTED | 0 | 0 | 0 |
| `cash_flow_breakdown` | custom/flow | có / 5 | metric_query | mgmt | component | có | BLOCKED | 0 | 0 | 0 |
| `cash_coverage_days` | custom/snapshot | có / 5 | metric_query | mgmt | — | có | BLOCKED | 0 | 0 | 0 |
| `ar_aging` | custom/snapshot | có / 5 | metric_query | mgmt | aging_bucket | có | SUPPORTED | 0 | 0 | 0 |
| `overdue_receivables` | custom/snapshot | có / 7 | metric_query | mgmt | — | có | SUPPORTED | 0 | 0 | 0 |
| `dso` | custom/flow | có / 6 | metric_query | mgmt | — | có | BLOCKED | 0 | 0 | 0 |
| `dso_actual` | custom/flow | có / 4 | metric_query | mgmt | — | có | SUPPORTED | 0 | 0 | 0 |
| `dpo` | custom/flow | có / 3 | metric_query | mgmt | — | có | BLOCKED | 0 | 0 | 0 |
| `dio` | custom/flow | có / 4 | metric_query | mgmt | — | có | BLOCKED | 0 | 0 | 0 |
| `cash_conversion_cycle` | custom/flow | có / 4 | metric_query | mgmt | — | có | BLOCKED | 0 | 0 | 0 |
| `ap_due_soon` | custom/flow | có / 5 | metric_query | mgmt | — | có | SUPPORTED | 0 | 0 | 0 |
| `upcoming_obligations` | custom/flow | có / 5 | metric_query | mgmt | — | có | BLOCKED | 0 | 0 | 0 |
| `expense_by_category` | flow/flow | có / 6 | view | mgmt, tax | cost_category | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `expense_spikes` | custom/flow | có / 6 | metric_query | mgmt | cost_category | có | BLOCKED | 0 | 0 | 0 |
| `unusual_account_movements` | custom/flow | có / 4 | metric_query | mgmt | — | có | BLOCKED | 0 | 0 | 0 |
| `unbalanced_journals` | custom/flow | có / 5 | metric_query | mgmt | — | có | SUPPORTED | 0 | 0 | 0 |
| `top_sales_transactions` | custom/flow | có / 4 | metric_query | mgmt | transaction_id | có | SUPPORTED | 0 | 0 | 0 |
| `budget_vs_actual` | custom/flow | có / 7 | metric_query | mgmt | component | có | BLOCKED | 0 | 0 | 0 |
| `payroll_summary` | custom/flow | có / 6 | metric_query | mgmt | component, component_unit | có | SUPPORTED | 0 | 0 | 0 |
| `taxable_income` | flow/flow | có / 4 | view | tax | month, quarter, year | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `cit_estimate` | custom/flow | có / 4 | view | tax | — | có | SUPPORTED | 0 | 0 | 0 |
| `deductible_expenses` | flow/flow | có / 3 | view | tax | month, quarter | có | EXECUTABLE_UNVERIFIED | 0 | 0 | 0 |
| `mgmt_vs_tax_gap` | custom/flow | có / 5 | metric_query | tax | component | có | SUPPORTED | 0 | 0 | 0 |
| `vat_position` | custom/flow | có / 5 | metric_query | tax | component | có | SUPPORTED | 0 | 0 | 0 |
