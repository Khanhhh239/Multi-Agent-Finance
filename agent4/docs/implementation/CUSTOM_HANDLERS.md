# Custom metric capability contracts

All 20 canonical custom IDs are registered. “Supported” below means only the
offline synthetic adapter; every real-data status remains BLOCKED pending schema
and domain approval.

Separately, the generic compiler can construct all 46 non-custom catalog
definitions, but only 15 have independent numeric fixture assertions and are
enabled. The other 31 are `EXECUTABLE_UNVERIFIED` and fail closed at validation.

| ID | Synthetic | Required source / handler contract |
|---|---|---|
| ar_aging | SUPPORTED | AR invoice, receipt, adjustment; as-of; five aging buckets |
| overdue_receivables | SUPPORTED | Open AR allocation, due date, 30-day default |
| dso_actual | SUPPORTED | Matched receipt→invoice; amount-weighted payment days |
| ap_due_soon | SUPPORTED | AP bill/payment allocation through validated horizon |
| unbalanced_journals | SUPPORTED | Full GL journal debit/credit grouping |
| top_sales_transactions | SUPPORTED | Non-opening AR invoice subtotal; bounded ranking |
| payroll_summary | SUPPORTED | Payroll amount grouped by branch/department |
| cit_estimate | SUPPORTED | Positive synthetic taxable income ×20%, tax view only |
| mgmt_vs_tax_gap | SUPPORTED | Non-deductible expense lines from management view |
| vat_position | SUPPORTED | 33311 output minus 1331 input on synthetic tax view |
| cash_flow_breakdown | BLOCKED | Counterpart classification/transfer elimination fixture missing |
| cash_coverage_days | BLOCKED | Approved eligible spend/debt-principal policy missing |
| dso | BLOCKED | Opening/closing AR and credit-sales owner policy missing |
| dpo | BLOCKED | Opening/closing AP and credit-purchase owner policy missing |
| dio | BLOCKED | Inventory/COGS period policy and owner approval missing |
| cash_conversion_cycle | BLOCKED | Depends on blocked DSO/DIO/DPO contracts |
| upcoming_obligations | BLOCKED | Tax/BHXH/payroll/loan obligation merge policy missing |
| expense_spikes | BLOCKED | Baseline/zero policy fixture missing |
| unusual_account_movements | BLOCKED | Z-score/calendar fixture and threshold approval missing |
| budget_vs_actual | BLOCKED | Partial-month and line reconciliation approval missing |

Handlers never substitute zero when their source is missing. Permissions for
payroll and tax data require production policy before those metrics can be
advertised outside the demo.
