# Bộ rule GoRules ZEN từ Luật 67/2025/QH15

## Phạm vi

`LUAT67_ARTICLE9_v1.json` là decision model dự thảo cho **Điều 9 – Các khoản
chi được trừ và không được trừ khi xác định thu nhập chịu thuế**. Bộ rule có
hiệu lực kỹ thuật từ `2025-10-01`, đúng ngày Luật 67/2025/QH15 có hiệu lực.

Model hiện chứa 22 nhánh kết quả:

- 20 nhánh `FAIL` cho các trường hợp được nêu rõ tại Điều 9;
- một nhánh `REVIEW` khi thiếu dữ liệu;
- một nhánh `REVIEW` khi điều kiện, mức hoặc ngoại lệ phải đối chiếu Nghị định
  320/2025/NĐ-CP.

Đây là bản `DRAFT_REQUIRES_TAX_EXPERT_REVIEW`, chưa phải rule được phép dùng để
tự động quyết toán thuế.

## Nguồn

- PDF gốc: `data/legal_sources/Luat_Thue_TNDN_67-2025-QH15.pdf`;
- SHA-256: `AE706468190AFE8D111DD0FCCF240E7A980EB002C5D0B5CB1CFE127D92F9C1CD`;
- toàn văn OCR có mốc trang: `data/corpus/LUAT_67_2025_QH15_TNDN.txt`;
- ảnh từng trang để đối chiếu: `data/legal_sources/Luat_67_pages/`.

PDF là bản scan. OCR chỉ phục vụ tìm kiếm và tạo bản nháp. `legal_ref`, nội dung
rule và hướng xử lý phải được đối chiếu với ảnh trang 7–9 và được chuyên gia thuế
duyệt trước khi đổi trạng thái phát hành.

## Hợp đồng đầu vào

ZEN nhận một object có trường `checks`. Tất cả trường boolean cần được bộ
extractor hoặc lớp chuẩn hóa nghiệp vụ xác định rõ. Không được tự gán `false`
cho dữ liệu chưa biết.

```json
{
  "checks": {
    "input_complete": true,
    "is_business_related": true,
    "has_legal_invoice_documents": true,
    "is_administrative_penalty": false,
    "is_reimbursed_from_other_source": false,
    "provision_compliant": true,
    "depreciation_compliant": true,
    "accrual_compliant": true,
    "is_disallowed_owner_salary": false,
    "is_founder_remuneration": false,
    "founder_directly_manages": true,
    "employee_expense_unpaid": false,
    "employee_expense_has_documents": true,
    "interest_for_missing_charter_capital": false,
    "interest_already_capitalized": false,
    "non_credit_interest_exceeds_civil_code_limit": false,
    "vat_input_already_deducted": false,
    "is_corporate_income_tax": false,
    "corresponds_to_taxable_revenue": true,
    "article9_1b_exception": false,
    "is_sponsorship": false,
    "sponsorship_allowed_under_1_b5": false,
    "is_capex_creating_fixed_asset": false,
    "is_direct_equity_reduction_cost": false,
    "requires_government_detail": false
  }
}
```

Khi một trường bắt buộc chưa xác định, lớp chuẩn hóa phải đặt
`input_complete=false`. Decision model sẽ trả `REVIEW`.

## Chạy model

```python
from src.rule_engine.zen_engine import ZenTaxRuleEngine

engine = ZenTaxRuleEngine("config/zen/LUAT67_ARTICLE9_v1.json")
result = engine.evaluate(context, "2026-01-15")
```

Kết quả có dạng:

```json
{
  "verdict": "FAIL",
  "hits": [
    {
      "rule_id": "CIT67-A9-2B",
      "verdict": "FAIL",
      "reason_code": "ADMINISTRATIVE_PENALTY",
      "legal_ref": "Điểm b khoản 2 Điều 9 Luật 67/2025/QH15",
      "source_page": 8
    }
  ],
  "ruleset": "CIT-LAW-67-2025-ARTICLE-9",
  "version": "1.0.0"
}
```

ZEN dùng hit policy `collect`, vì một giao dịch có thể vi phạm nhiều điều kiện.
Adapter tổng hợp kết luận theo ưu tiên `FAIL > REVIEW > PASS` và không chạy bộ
rule trước ngày hiệu lực.

## Việc còn lại trước khi tích hợp API

1. Trích và mã hóa Nghị định 320/2025/NĐ-CP để xác định các mức, hồ sơ và ngoại lệ.
2. Chuyên gia thuế duyệt từng hàng và ký phiên bản rule.
3. Viết mapper từ kết quả LLM/PhoBERT và dữ liệu kế toán sang `checks`.
4. Chạy bộ tình huống vàng, gồm trường hợp vi phạm, hợp lệ, biên và ngoại lệ.
5. Chỉ sau đó mới thay rule engine Python hiện tại trong `src/main.py`.
