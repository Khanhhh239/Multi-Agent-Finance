# Từ điển dữ liệu (một thế giới v4)

Mỗi thế giới là một thư mục gồm 21 bảng CSV (UTF-8 có BOM) cùng `manifest.json` và `validation_v4.json`. Khóa chính của giao dịch là `transaction_id`. **Quy tắc cách ly:** mô hình chỉ được đọc các bảng ở nhóm A và B; nhóm C là nhãn, chỉ dùng để đánh giá.

## Nhóm A. Danh mục chủ (master data), có thời điểm ghi nhận

| Bảng | Khóa | Cột chính |
|---|---|---|
| `companies` | `company_id` | `industry`, `size_class`, `amount_scale`, `pay_days`, `vendor_terms_days`, `customer_terms_days`, `self_approval_limit_vnd`, `saturday_operations` |
| `employees` | `employee_id` | `company_id`, `role`, `department`, `hired_at`, `terminated_at`, `termination_recorded_at`, `monthly_salary_vnd`, `bank_account`, `phone`, `address`, `approval_limit_vnd`, `self_approval_limit_vnd`, `recorded_at` |
| `vendors` | `vendor_id` | `company_id`, `name`, `tax_code`, `bank_account`, `phone`, `address`, `registered_at`, `onboarded_at`, `recorded_at`, `representative_id`, `related_party_disclosed_at` |
| `customers` | `customer_id` | `company_id`, `name`, `tax_code`, `bank_account`, `credit_terms_days`, `recorded_at` |
| `vendor_status_history` | (`vendor_id`, `effective_at`) | `status`, `observed_at` (trạng thái "không còn hoạt động" có độ trễ) |
| `bank_account_changes` | `change_id` | `vendor_id`, `old_account`, `new_account`, `effective_at`, `observed_at`, `verified_at`, `callback_verified`, `approver_id` |
| `entity_links` | | Quan hệ thực thể: tài khoản, điện thoại, địa chỉ, người đại diện dùng chung (đồ thị) |
| `attendance` | | `days_worked_observed` theo kỳ |
| `calendar` | `date` | Ngày lễ minh họa |
| `advances`, `advance_events` | `advance_id`, `event_id` | Tạm ứng và sự kiện gia hạn, quyết toán, xóa nợ |

## Nhóm B. Giao dịch và kế toán (đầu vào của mô hình)

| Bảng | Nội dung |
|---|---|
| `transactions` (55 cột) | Mỗi dòng một giao dịch: `posted_at`, `created_at`, `approved_at`, `txn_type` (26 loại), `amount_vnd`, `debit_account`, `credit_account`, `vendor_id`, `customer_id`, `employee_id`, `recipient_account`, `creator_id`, `approver_id`, `support_doc_count`, `goods_receipt_verified`, `unit_price_vnd`, `quantity`, `invoice_*`, `applied_invoice_id`, `payer_account`, `collector_id`, `payroll_period`, `advance_id`, `accounting_framework`, `journal_document_id`, `vat_rate`, ... |
| `invoices` | Hóa đơn: số, ngày, tiền, thuế |
| `journal_documents`, `journal_lines` | Chứng từ nhật ký và dòng nợ có (cân) |
| `document_links` | Liên kết chứng từ (đơn hàng, phiếu nhận, hóa đơn) |
| `account_flow_edges` | Cạnh dòng tiền giữa tài khoản |
| `features` (191 cột) | 190 đặc trưng của bạn bạn (theo loại nghiệp vụ, tài khoản, giờ, người lập) + `transaction_id`. Chỉ dùng quá khứ |

26 loại nghiệp vụ: `payroll`, `vendor_payment`, `cash_expense`, `sales_invoice`, `customer_receipt`, `stock_purchase`, `selling_expense`, `cogs`, `material_purchase`, `advance_issue`, `rent`, `cash_withdrawal`, `adjustment`, `material_issue`, `advance_settlement`, `depreciation`, `tools_purchase`, `tax_payment`, `advance_writeoff`, `advance_review`, `bad_debt_writeoff`, `sales_return`, `vat_offset`, `inventory_writeoff`, `customer_refund`, `equipment_purchase`.

## Nhóm C. Nhãn và chia tập (không đưa vào mô hình)

| Bảng | Cột |
|---|---|
| `labels` | `transaction_id`, `is_fraud`, `fraud_type`, `variant`, `case_id`, `case_role` (`fraud`, `support`, `hard_negative`, `background`), `hard_negative_type`, `difficulty` (L0, L1, L2), `observability`, `scheme_group`, `perpetrator_level`, `collusion`, `concealment` |
| `splits` | `transaction_id`, `split` (`train`, `validation`, `test`) |
| `truth_cases` | `case_id`, `company_id`, `scheme`, `acfe_branch`, `reference_vi`, `perpetrator_id`, `perpetrator_role`, `perpetrator_level`, `accomplice_ids`, `collusion`, `concealment`, `split`, `start_at`, `end_at`, `fraud_rows`, `loss_vnd` |

## Nhóm D. Đặc trưng suy ra bởi mã `agent2` (không lưu trong thế giới; lưu `_cache/`)

| Tập | Số cột | Mã |
|---|---:|---|
| `ENGINEERED` | 31: baseline theo thực thể (giá nhà cung cấp, lương nhân viên, người lập), gần trùng, cặp người lập và người duyệt, tự duyệt tiền mặt, mùa Tết | `agent2/feats.py` |
| `V4_FEATURES` | 15 dấu hiệu đỏ: lệch người trả tiền, trễ thu, nhà cung cấp ngoài danh mục, lương sau nghỉ, lương ngoài lịch, xóa nợ quá hạn, hoàn tiền sang tài khoản lạ, ... | `agent2/feats_v4.py` |
| Luật | 31 luật, khoảng 34 cột `hit_*`, `rule_graph`, `rule_direct`, `rule_hard`, `rule_ids`, `explanation_vi` | `sme_fraud/rules.py` qua `agent2/data.py` |
| Không nhãn `u_*` | các đuôi EntityDeviation, hạng AE và IF | `agent2/hybrid.py` |

## Quy ước kiểu dữ liệu
Thời gian ISO 8601 với múi giờ `+07:00`; tiền là số nguyên đồng; mã định danh dạng chuỗi (`T000000001`, `V...`, `CU...`, `C001`); các trường định danh cá nhân và tài khoản đều là mã tổng hợp (`BANK_SYN_`, `PHONE_SYN_`, `ADDRESS_SYN_`).

