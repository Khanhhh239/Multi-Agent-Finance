# V0 Issue Index

Thư mục này tách các module plan thành các đơn vị thực thi độc lập cho Codex.
Các module plan trong `docs/plans/` vẫn là đặc tả tổng và không bị thay thế.

## Quy tắc sử dụng

- Giao cho agent đúng một file Issue tại một thời điểm.
- Agent phải dùng `AGENTS.md` và skill `issue-loop` để hoàn thành Issue.
- Chỉ bắt đầu Issue khi dependency đã verified.
- Sau Issue cuối của mỗi module, chạy module gate và review trước khi sang module kế tiếp.
- Các mục `Open decisions` phải được chốt trước khi Issue được coi là execution-ready.

## Thứ tự thực thi

| Module | Issue | Phụ thuộc | Module gate |
| --- | --- | --- | --- |
| M0 — Core & Catalog | [M0.1 Core, errors, context](M0.1_core_errors_context.md) | — | Sau M0.2 |
|  | [M0.2 Metric catalog](M0.2_metric_catalog.md) | M0.1 | Contract tests Core/Catalog |
| M1 — Metric Selection | [M1.1 Retrieval pipeline](M1.1_retrieval_pipeline.md) | M0.2 | Sau M1.3 |
|  | [M1.2 Dynamic few-shot](M1.2_dynamic_fewshot.md) | M1.1 | — |
|  | [M1.3 Qwen selector & validation](M1.3_selector_validation.md) | M1.1, M1.2 | Contract tests + dev selection eval |
| M2 — Query Planning | [M2.1 Semantic planner](M2.1_semantic_planner.md) | M1.3 | Sau M2.2 |
|  | [M2.2 Plan validator](M2.2_plan_validator.md) | M2.1 | Planning/security tests + dev plan eval |
| M3 — SQL Engine | [M3.1 SQL compiler](M3.1_sql_compiler.md) | M2.2 | Sau M3.3 |
|  | [M3.2 SQL safety](M3.2_sql_safety.md) | M3.1 | — |
|  | [M3.3 DuckDB executor](M3.3_duckdb_executor.md) | M3.2 | Compiler/safety/execution integration tests |
| M4 — Answer & E2E | [M4.1 Grounded answer](M4.1_grounded_answer.md) | M3.3 | Sau M4.3 |
|  | [M4.2 Pipeline & API](M4.2_pipeline_api.md) | M4.1 | — |
|  | [M4.3 Full benchmark](M4.3_full_benchmark.md) | M4.2 | Full regression + benchmark + human go/no-go |

## Shared readiness notes

Việc tách file chưa tự động làm mọi Issue trở thành execution-ready. Trước khi
giao agent cần xác nhận:

1. Contract tests gọi production implementation, không chỉ gọi
   `tests/contract_harness.py`.
2. Issue có evaluation về AI/system behavior phải có adapter gọi production,
   baseline tương thích và quality gates cụ thể.
3. M4.3 đang có xung đột giữa benchmark v1 120 câu trong module plan và benchmark
   v2 140 câu trong `docs/evaluation.md`; phải chốt một protocol trước execution.
