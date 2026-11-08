# Gate PLAN_08 — ZEN, Decimal, trace và aggregation

Ngày: **15/10/2026**. **PASS gate kỹ thuật theo validator `passed=true`; phát hành pháp lý/production còn PENDING.**

Theo yêu cầu người dùng tiếp tục từ PLAN_07, triển khai engine và invariants bằng fixture tổng hợp. PLAN_07 chưa duyệt rule/mapping thực tế; không tự coi gate pháp lý đã đạt. OCR V2 tiếp tục thuộc PLAN_06.

## Bằng chứng

[Kế hoạch thực hiện](plan08/implementation_plan.md), [runbook](plan08/runbook.md), [validation summary](plan08/validation_summary.json), [money decision](plan08/money_boundary_decision.md), [SDK probes](plan08/money_boundary_probe.json), [truth tables](plan08/model_truth_tables.json), [sample end-to-end](plan08/synthetic_compliance_result.json).

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\validate_plan08.py
```

**293/293 test PASS**, gồm 65 test rules mới và 228 test hồi quy capture/planning, không có test skipped. Ngoài số test có 128 tổ hợp precedence, 16 tổ hợp boolean có REVIEW, 500 cặp Decimal đối chiếu Fraction và 20 tổ hợp của 7 bảng DRAFT. API/SQLite integration, hai worker tranh execution, worker bị thay lease, timeout và worker native được kiểm trên máy Windows, không chỉ mock engine.

## Trạng thái công việc

| Task | Kết quả kỹ thuật |
|---|---|
| T01 | ZEN 0.53.0 pinned; Decimal adapter → boolean facts, reject ngoài miền; probe bất an toàn và oracle độc lập |
| T02 | Typed eligible context, pinned model/package, response/trace validation, bounded native worker |
| T03 | 7 DRAFT JDM theo ba họ và timeline; truth tables explicit PASS/no-hit ERROR. Chưa đủ legal coverage |
| T04 | Raw trace immutable/hash; condition origin ADAPTER, matched row ENGINE; không giả condition-level SDK observations |
| T05 | Independent units, bounded retries, durable attempt store, terminal dedupe, idempotent runs, lease/fencing/resume |
| T06 | Unit/rule counters riêng, source-scoped coverage, precedence và review/error preservation |
| T07 | Duplicate/stale/foreign/non-eligible/trace/version violations làm processing ERROR/verdict null |
| T08 | Real-runtime tables, synthetic reviewed capture → planning → ZEN → persistence → replay; hồi quy tám suite |

Migration DB 008. API POST execution, GET result và GET attempt pages; CLI local. Chưa thay UI hoặc tự gọi engine khi upload. Các dependency/model/hash/schema nằm trong repository; PDF/DB/token/model OCR không đưa Git.

## Giới hạn còn mở

1. Rule/model thực tế DRAFT; content mới kiểm observation MST người bán, VAT mới có bảng nhánh reduction minh họa. Chưa chứng nhận mọi nội dung hóa đơn/VAT/non-cash hoặc ngoại lệ/chuyển tiếp pháp luật.
2. PaymentProof chỉ là interface backend tin cậy có scope/hash/proof; chưa có nạp và đối chiếu chứng từ ngân hàng thật. Thiếu proof trả ERROR blocker, không tự suy từ invoice payment label. Cần nối dependency này vào planning/source integration trước publish non-cash.
3. Chưa có legal approval, mappings hàng thật, calibration/accuracy release hay performance/load nghiệm thu. Không cam kết không có lỗi trên mọi hóa đơn từ kết quả unit test.
4. Snapshot PLAN_07 support kết thúc 15/10/2026 exclusive; dữ liệu ngoài phạm vi phải cập nhật legal snapshot có rà soát.
5. Chưa có scheduler tự phục hồi lease hoặc UI compliance; synchronous API có unit budget nhưng chưa là thiết kế production tải lớn. PLAN_09 nhận nhiệm vụ tích hợp.

**Bàn giao:** PLAN_09 có thể dùng engine/aggregate contracts và fixtures đã kiểm. Legal release vẫn chặn cho đến khi nguồn/rule/model/mapping và các gate dữ liệu liên quan được duyệt; không đổi DRAFT để làm kết quả có vẻ thành công.
