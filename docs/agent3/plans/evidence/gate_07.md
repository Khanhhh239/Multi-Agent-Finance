# Gate PLAN_07 — Rule Planning

Ngày: 14/10/2026. **PASS phần kỹ thuật; PENDING nghiệm thu pháp lý/taxonomy và dữ liệu thực. Không phải gate phát hành compliance.**

Tiếp tục từ PLAN_06 theo phạm vi kỹ thuật được người dùng chọn. OCR V2 và nghiệm thu PLAN_05–06 giữ nguyên trạng thái mở; không lấy kết quả unit test PLAN_07 để đóng các gate đó.

## Đã triển khai

- Legal Registry có URL, hash, locator được đối chiếu, lịch hiệu lực và quan hệ thay thế có scope. Catalog thực tế vẫn DRAFT.
- Timeline selector, immutable capability profiles, taxonomy interface, tri-state applicability, evaluation units, eligibility/observations.
- Ngưỡng non-cash ở planning; daily completeness là bằng chứng bắt buộc khi một hóa đơn chưa đạt ngưỡng. Decimal, KCT/KKKNT/0, direction unknown và unit-discovery blockers được giữ đúng semantics.
- RulePlan pin CFR/master revision, quality/context/legal/taxonomy/ruleset/capability và implementation hash; `engine_calls=0`.
- SQLite migration 007, artifact/snapshot bất biến, idempotency, replay, audit transaction và API có kiểm quyền scope; CLI local.

## Bằng chứng và tái hiện

[Runbook](plan07/runbook.md), [test summary](plan07/validation_summary.json), [ma trận quyết định](plan07/planning_matrix_report.md), [đối chiếu nguồn](plan07/legal_source_review.md), [artifact tổng hợp](plan07/synthetic_rule_plan.json), [catalog DRAFT trên cùng fixture](plan07/draft_catalog_plan.json).

```powershell
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\validate_plan07.py
```

Bộ test có **228 test: 22 contracts, 23 ingestion, 28 OCR, 50 extraction, 34 quality, 32 review, 39 planning**, dùng fixture/integration local. Không chạy lại benchmark accuracy hay claim thống kê hóa đơn thực. API integration dùng TestClient và SQLite tạm, không thay dữ liệu demo đang mở trên UI.

## Trạng thái task

| Task | Trạng thái và giới hạn |
|---|---|
| T01 | Registry/evidence kỹ thuật có; rà luật toàn bộ/chữ ký/ngoại lệ PENDING |
| T02 | Timeline và boundary fixtures PASS; rule lịch sử chưa publish |
| T03 | Profiles immutable PASS; XML/bank metadata chuẩn bị, adapter thuộc PLAN_10–11 |
| T04 | Taxonomy service/mapping version/provenance PASS; mapping hàng thật chưa có |
| T05–T08 | Tri-state, selector, units, eligibility và observation tests PASS |
| T09 | Ma trận kỹ thuật PASS; đối chiếu rule với người phụ trách nghiệp vụ PENDING |

## Điều kiện còn mở và bàn giao

Không có rule thuế thực tế approved. Chưa có mapping hàng hóa/dịch vụ đã duyệt; chưa hỗ trợ tự xác minh chữ ký, mọi ngoại lệ/thời kỳ chuyển tiếp, FX conversion hoặc ledger được nạp từ API người dùng. Chưa có nút planning trên UI, chưa tự gọi sau upload. Catalog hiện support đến 15/10/2026 exclusive.

PLAN_08 có thể triển khai ZEN/Decimal/trace với rule tổng hợp, dùng RulePlan immutable làm đầu vào; chỉ chạy entries đủ eligibility. Trước bật kết luận thuế thực tế, phải duyệt từng rule/locator/sửa đổi/chuyển tiếp, cung cấp taxonomy/ledger tin cậy đúng scope và hoàn tất nghiệm thu dữ liệu liên quan. Không sửa DRAFT thành APPROVED chỉ để vượt gate.
