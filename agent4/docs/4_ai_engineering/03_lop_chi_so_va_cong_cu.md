# 03 · Lớp chỉ số (semantic metric layer) và bộ công cụ cho LLM

## 1. Lớp chỉ số — đã xây (`agent4/engine`)
### 1.1 Cấu trúc một chỉ số (`metrics.MetricDef`)
| Trường | Ý nghĩa |
|---|---|
| `id`, `label`, `description` | Định danh, tên hiển thị, mô tả cho người và cho retriever |
| `kind` | `flow` (dòng chảy trong kỳ) · `snapshot` (số dư tại ngày cuối) · `ratio` (tỷ số 2 thành phần) · `custom` (cần sổ chi tiết) |
| `terms` / `num`+`den` | Các `Term(prefixes, coef, measure, where)`: tài khoản (tiền tố), hệ số, phép đo (`net_debit`/`net_credit`/`debit`/`credit`) |
| `unit` | `VND`, `%`, `days`, `ratio`, `count` |
| `views` / `default_view` | Khung dữ liệu được phép (`mgmt`, `tax`) |
| `group_bys` | Chiều phân rã hỗ trợ |
| `synonyms`, `accounts`, `formula`, `better` | Đồng nghĩa (cho retrieval), tài khoản liên quan, công thức văn bản, chiều "tốt hơn" |

### 1.2 Danh mục 66 chỉ số (theo nhóm)
| Nhóm | Chỉ số |
|---|---|
| **P&L (18)** | `net_revenue`, `gross_revenue`, `revenue_deductions`, `goods_revenue`, `service_revenue`, `cogs`, `gross_profit`, `gross_margin_pct`, `finance_income`, `finance_cost`, `operating_profit`, `other_income`, `other_expenses`, `profit_before_tax`, `net_profit`, `net_margin_pct`, `ebitda`, `top_sales_transactions` |
| **Chi phí (8)** | `selling_expenses`, `admin_expenses`, `operating_expenses`, `expense_by_category`, `salary_expense`, `labor_cost`, `depreciation_expense`, `payroll_summary` |
| **Tiền & thanh khoản (10)** | `cash_and_equivalents`, `term_deposits`, `net_cash_flow`, `cash_flow_breakdown`, `cash_coverage_days`, `working_capital`, `current_ratio`, `quick_ratio`, `upcoming_obligations`, `cash_conversion_cycle` |
| **Công nợ phải thu (7)** | `ar_balance`, `ar_by_customer`, `ar_by_salesperson`, `ar_aging`, `overdue_receivables`, `dso`, `dso_actual` |
| **Phải trả (4)** | `ap_balance`, `ap_by_vendor`, `ap_due_soon`, `dpo` |
| **Tồn kho (2)** | `inventory_value`, `dio` |
| **Bảng cân đối/nợ vay (6)** | `fixed_assets_net`, `total_assets`, `total_liabilities`, `equity`, `debt_balance`, `debt_to_equity` |
| **Thuế (7)** | `tax_payable`, `income_tax_expense`, `taxable_income`, `cit_estimate`, `deductible_expenses`, `mgmt_vs_tax_gap`, `vat_position` |
| **Bất thường & kế hoạch (4)** | `expense_spikes`, `unusual_account_movements`, `unbalanced_journals`, `budget_vs_actual` |

### 1.3 API lõi (`ExecutionEngine`)
| Hàm | Mô tả |
|---|---|
| `query(metric, period, compare_to, group_by, filters, view, top_k, params)` | Điểm vào duy nhất cho agent |
| `explain(metric, period, filters, view, limit)` | "Xem cách tính": công thức, tổng theo TK, chứng từ lớn nhất |
| `resolve_entity(kind, text)` | Tên/mã → mã; ném `FilterError(candidates)` khi nhiều ứng viên |
| `list_metrics()` | Danh mục cho công cụ `list_metrics` |
| `get_metric(id, start, end)` | Hợp đồng v0 (giữ tương thích test cũ) |
| Lỗi có kiểu | `MetricNotFoundError`, `InvalidDateRangeError`, `FilterError`, `ViewNotAllowedError`, `MetricUnavailableError` — thông điệp tiếng Việt, an toàn để trả cho LLM/người dùng |

### 1.4 Bộ lọc & chiều
`filters`: `customer`, `vendor`, `branch`, `product_line`, `item`, `cost_category`, `department`, `salesperson`, `exclude_customers`, `exclude_top_customers`(N). Mỗi giá trị chấp nhận mã **hoặc tên mờ** ("Hoàng Long", "Hà Nội", "marketing").
`group_by`: `month`, `quarter`, `year`, `branch`, `product_line`, `customer`, `vendor`, `item`, `cost_category`, `department`, `salesperson`, `account` (tùy chỉ số).

### 1.5 Kiểu kỳ & so sánh
`periods.resolve_period` hiểu token (`this_month`, `last_quarter`, `ytd`, `last_6_months`, `next_15_days`, `2026-Q3`, `2026-05`, `2026-05-01..2026-05-31`) và cụm tiếng Việt (có/không dấu). So sánh `previous_period` | `same_period_last_year`; **kỳ dở dang so cùng số ngày** (ví dụ 01–14/10 so 01–14/09) và nêu cả giá trị kỳ đầy đủ.

### 1.6 Điểm cần rà soát công thức với kế toán (đã biết)
| Chỉ số | Lưu ý |
|---|---|
| `salary_expense`, `labor_cost` | Bao gồm kỹ thuật viên hạch toán qua 154 (sau đó vào giá vốn dịch vụ) |
| `dso` | Dùng phải thu bình quân (đầu + cuối)/2 và doanh số bán chịu **gồm VAT**; khác biệt với DSO theo tháng của `metrics-v0.md` (chia bình quân các tháng) |
| `ar_aging`, `overdue_receivables` | Khoản trả trước/chiết khấu chưa gắn hóa đơn cấn FIFO vào hóa đơn cũ nhất |
| `cash_coverage_days` | Chi tiền 90 ngày gần nhất, không gồm trả gốc vay và chuyển nội bộ |
| `taxable_income`, `cit_estimate` | Ước tính; khung thuế chỉ loại dòng cờ `tax_deductible=FALSE` |
| `budget_vs_actual` | Ngân sách sinh từ thực tế 2025 (không độc lập) |
| `equity` | Gồm kết quả chưa kết chuyển của các tháng mở |
| `metrics-v0.md` `cash_and_equivalents` | Bản gốc có lỗi ưu tiên toán tử (`OR`/`AND` thiếu ngoặc) — bản mới đã sửa |

## 2. Công cụ LLM nhìn thấy (≤ 8) — **hợp đồng cho coding agent**
> Tên và lược đồ dưới đây là đề xuất; giữ ổn định vì bộ E1/E2 dùng chúng làm nhãn.

### T1 `query_metric`
```json
{"name":"query_metric",
 "description":"Tra một chỉ số tài chính đã kiểm định. Không tự tính số.",
 "parameters":{"type":"object","required":["metric"],"properties":{
   "metric":{"type":"string","enum":["<tập ứng viên ≤ 8 từ retrieval>"]},
   "period":{"type":"string","description":"Token hoặc cụm thời gian người dùng nói: this_month, last_quarter, ytd, 'quý 2/2026', 'tháng 5'…"},
   "compare_to":{"type":"string","enum":["previous_period","same_period_last_year"]},
   "group_by":{"type":"string","enum":["month","quarter","branch","product_line","customer","vendor","item","cost_category","department","salesperson","account"]},
   "filters":{"type":"object","properties":{"customer":{"type":"string"},"vendor":{"type":"string"},"branch":{"type":"string"},
              "product_line":{"type":"string"},"cost_category":{"type":"string"},"salesperson":{"type":"string"},
              "exclude_top_customers":{"type":"integer"},"exclude_customers":{"type":"array","items":{"type":"string"}}}},
   "view":{"type":"string","enum":["mgmt","tax"]},
   "top_k":{"type":"integer"},
   "params":{"type":"object","description":"min_days (quá hạn), days (sắp đến hạn)…"}}}}
```
### T2 `explain_metric` — tham số như `query_metric` (không cần `compare_to`); trả công thức, tổng theo TK, chứng từ lớn nhất.
### T3 `find_entity` — `{"kind":"customer|vendor|branch|item|cost_category|department|salesperson","text":"…"}` → danh sách ứng viên (mã, tên).
### T4 `list_metrics` — `{"category":"pnl|ar|cash|…"}` → danh mục rút gọn (cho câu "bạn trả lời được gì").
### T5 `ask_clarification` (công cụ ảo) — `{"question":"…","options":[{"label":"Lợi nhuận gộp","patch":{"metric":"gross_profit"}},…]}`; `options` 2–3 phần tử; mỗi `patch` là bản vá tham số để lượt sau nhấn là chạy.
### T6 `refuse` (công cụ ảo) — `{"reason":"out_of_scope|unsafe_action|no_permission|no_data","message":"…","suggest":["…"]}`.
### T7 `propose_action` — `{"action_type":"record_payment_promise|set_credit_hold|flag_for_review","params":{…},"rationale":"…"}` → ghi `pending_approvals`, **không thực thi**.
### T8 `orchestrate_agents` — `{"agents":["cashflow","risk","tax"],"question":"…"}` → gọi song song adapter A1/A2/A3 (hiện mock).
### (cờ) `run_readonly_sql` — `{"sql":"SELECT …"}`; chỉ bật khi không có chỉ số phù hợp; qua AST validator (whitelist bảng/cột, chỉ `SELECT`, `LIMIT ≤ 200`, timeout 5 s).

## 3. Bảng ánh xạ ý định → công cụ (làm cơ sở E1)
| Mẫu câu | Công cụ | Ghi chú |
|---|---|---|
| "… bao nhiêu?" (số đơn) | T1 | |
| "so với … tăng/giảm" | T1 + `compare_to` | |
| "theo từng …" | T1 + `group_by` | |
| "nếu loại/bỏ khách …" | T1 + `filters.exclude_*` | |
| "vì sao …" | T1 nhiều lần (gọi ≥ 2 chỉ số) hoặc T8 | agent nêu *yếu tố có số* |
| "tính thế nào/ lấy số ở đâu" | T2 | dùng `lineage_id` lượt trước |
| "tình hình/ có gì bất thường" | T8 + `expense_spikes` + `overdue_receivables` | bản tin |
| "chặn/ghi nhận/ nhắc …" | T7 | không thực thi |
| thiếu thông tin | T5 | |
| ngoài phạm vi | T6 | |

## 4. Mô tả công cụ cho model nhỏ — nguyên tắc
1. Mô tả ≤ 40 từ, **động từ đầu câu**, nêu *khi nào dùng / khi nào không*.
2. Tên chỉ số trong enum là `id` (tiếng Anh ngắn) nhưng retrieval dựa trên đồng nghĩa tiếng Việt; phần mô tả trong prompt hiển thị `id — nhãn tiếng Việt` để model nối được cả hai.
3. Không đưa công thức/tài khoản vào prompt (tốn token, không giúp chọn).
4. Mỗi cặp chỉ số dễ nhầm có một *câu phân biệt* (ví dụ "`ar_balance`: tổng một con số · `ar_by_customer`: danh sách theo khách").
