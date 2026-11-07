# V0 Issue Index & Synchronization Guide

Thư mục này tách các module plan thành các đơn vị thực thi độc lập (Vertical Slices) cho Codex theo quy trình `issue-loop`.
Các module plan trong `docs/plans/` vẫn là đặc tả tổng và không bị thay thế.

## Quy tắc sử dụng

- Giao cho agent đúng một file Issue tại một thời điểm.
- Agent phải dùng `AGENTS.md` và skill `issue-loop` để hoàn thành Issue (`Implement -> Test -> Benchmark -> Review -> Complete`).
- Chỉ bắt đầu Issue khi dependency đã verified.
- Sau Issue cuối của mỗi module, chạy module gate và review trước khi sang module kế tiếp.
- Các mục `Open decisions` hoặc `Decision Gates` phải được kiểm chứng bằng số liệu trước khi đóng module.

## Thứ tự thực thi (Execution Order)

| Module | Sub-Milestone | Issue | Phụ thuộc | Cổng kiểm thử & Thực nghiệm (Module / Eval Gate) |
| :--- | :--- | :--- | :--- | :--- |
| **M0 — Core & Catalog** | — | [M0.1 Core, errors, context](M0.1_core_errors_context.md) (**Verified**) | — | Sau M0.2 |
|  | — | [M0.2 Metric catalog](M0.2_metric_catalog.md) (**Verified**) | `M0.1` | Contract tests Core/Catalog (`14/14` pass) |
| **M1 — Metric Selection** | **M1-S1: Catalog & Full-Catalog Baseline** | [M1.0 Catalog adapter, Qwen selector, validator & E0 baseline](M1.0_catalog_adapter_and_baseline.md) | `M0.2` | `test_selection_and_metric_validation.py` (`7/7` pass) + **Experiment `E0`** (Full-Catalog Baseline) |
|  | **M1-S2: Embedding & Offline Indexing** | [M1.1a Embedding provider, doc builder & offline `.npz` index](M1.1a_embedding_and_offline_index.md) | `M1.0` | `TestEmbeddingAndDocumentBuilderContracts` (`3/3` pass) + Offline Index tests |
|  | **M1-S3: Hybrid Retrieval** | [M1.1 Online hybrid retrieval, RRF fusion & metadata rerank](M1.1_retrieval_pipeline.md) | `M1.0`, `M1.1a` | `TestMetricRetrievalPipelineContracts` (`5/5` pass) + **Experiments `E1` (Dense) & `E2` (Hybrid)** + Decision Gate G2 |
|  | **M1-S4: Dynamic Few-shot & Ablation** | [M1.2 Dynamic few-shot governance & strategy ablation](M1.2_dynamic_fewshot.md) | `M1.1` | `TestDynamicFewShotContracts` (`3/3` pass) + **Experiments `E3` (Static) & `E4` (Dynamic)** + Decision Gate G3 |
|  | **M1-S5: Recovery & Submission Readiness** | [M1.3 Bounded recovery, E2E selection integration & submission gate](M1.3_selector_validation.md) | `M1.0`, `M1.1a`, `M1.1`, `M1.2` | Toàn bộ `18/18` M1 contract tests + **Experiment `E5`** + Chốt `config/selection.yaml` |
| **M2 — Query Planning** | — | [M2.1 Semantic planner](M2.1_semantic_planner.md) | `M1.3` | Sau M2.2 |
|  | — | [M2.2 Plan validator](M2.2_plan_validator.md) | `M2.1` | Planning/security tests + dev plan eval |
| **M3 — SQL Engine** | — | [M3.1 SQL compiler](M3.1_sql_compiler.md) | `M2.2` | Sau M3.3 |
|  | — | [M3.2 SQL safety](M3.2_sql_safety.md) | `M3.1` | — |
|  | — | [M3.3 DuckDB executor](M3.3_duckdb_executor.md) | `M3.2` | Compiler/safety/execution integration tests |
| **M4 — Answer & E2E** | — | [M4.1 Grounded answer](M4.1_grounded_answer.md) | `M3.3` | Sau M4.3 |
|  | — | [M4.2 Pipeline & API](M4.2_pipeline_api.md) | `M4.1` | — |
|  | — | [M4.3 Full benchmark](M4.3_full_benchmark.md) | `M4.2` | Full regression + benchmark + human go/no-go |

---

## Bảng Phân loại & Ánh xạ Issue Cũ $\rightarrow$ Mới của Module 2 (`M1`)

Các Issue trong repository hiện được quản lý qua **Local Markdown Documents (`docs/issues/*.md`)**. Dưới đây là phân loại chính thức theo chuẩn tái cấu trúc (`Keep`, `Update`, `Split`, `Merge`, `Close as obsolete`, `Create new`) nhằm đảm bảo phát triển hướng thực nghiệm (Benchmark-Driven Development) mà không làm gãy bất kỳ tham chiếu nào của `M0` và `M2`–`M4`:

| Issue Cũ | Phân loại (Action) | Issue Mới Tương ứng | Lý do Kỹ thuật & Thay đổi Chính |
| :--- | :---: | :--- | :--- |
| `M0.1`, `M0.2` | **Keep** (Verified) | `M0.1_core_errors_context.md`, `M0.2_metric_catalog.md` | Đã hoàn thành và có báo cáo xác minh tại `reports/issues/M0.1_verification.md`, `M0.2_verification_vi.md`. |
| *(Chưa có)* | **Create new** | `M1.0_catalog_adapter_and_baseline.md` (**Sub-milestone M1-S1**) | Tạo mới để giải quyết sự lệch cấu trúc giữa `MetricDef` (66 metrics trong `agent4/engine/metrics.py`) và `MetricCatalog` (15 metrics trong `agent4/core/catalog.py`), đồng thời đưa `llm_selector.py`, `validator.py` và **Baseline `E0` (Full Catalog $\rightarrow$ Qwen3:4b $\rightarrow$ Validator)** lên đầu tiên. |
| `M1.1_retrieval_pipeline.md` | **Split & Update** | `M1.1a_embedding_and_offline_index.md` (**M1-S2**)<br/>+<br/>`M1.1_retrieval_pipeline.md` (**M1-S3**) | Tách `M1.1` cũ thành 2 lát cắt dọc độc lập:<br/>- `M1.1a`: Chuyên biệt cho Offline Stage (`EmbeddingProvider`, `build_metric_documents`, và lưu trữ `.npz` `MetricVectorIndex` kèm `stale-index detection`).<br/>- `M1.1`: Chuyên biệt cho Online Hybrid Retrieval (`dense.py`, `lexical.py`, `fusion.py`, `rerank.py`, `orchestrator.py`) và đo đạc thực nghiệm `E1` (Dense) vs `E2` (Hybrid) với chỉ số `Complete Gold Set Recall@K`. |
| `M1.2_dynamic_fewshot.md` | **Update** | `M1.2_dynamic_fewshot.md` (**Sub-milestone M1-S4**) | Mở rộng để chuẩn hóa `data/example_bank.jsonl` sang Contract 12, bổ sung 5 chiến lược (`zero`, `static`, `similarity`, `coverage`, `hybrid`), và yêu cầu chạy Ablation Study `E3` (Static Few-shot) vs `E4` (Dynamic Few-shot). |
| `M1.3_selector_validation.md` | **Split & Update** | `M1.0_catalog_adapter_and_baseline.md` (**M1-S1**)<br/>+<br/>`M1.3_selector_validation.md` (**M1-S5**) | Phần cốt lõi của `llm_selector.py` và `validator.py` được đẩy lên `M1.0` để chạy Baseline `E0` sớm. File `M1.3_selector_validation.md` được giữ nguyên ID ở cuối chuỗi `M1` (bảo toàn phụ thuộc `Depends on: M1.3` của `M2.1`) và cập nhật để phụ trách **Bounded Recovery (`recovery.py`)**, tích hợp toàn bộ Module 2, chạy thực nghiệm `E5` và khóa cấu hình nộp bài `config/selection.yaml`. |
| `M2.1` $\rightarrow$ `M4.3` | **Keep** | `M2.1` $\rightarrow$ `M4.3` | Giữ nguyên không sửa đổi; `M2.1` vẫn phụ thuộc vào `M1.3` (Issue cuối của Milestone M1). |

---

## GitHub Issue Synchronization Checklist

Repository hiện tại chưa gắn Git remote / GitHub Issues trực tuyến (quản lý trực tiếp bằng file Markdown trong `docs/issues/`). Khi đồng bộ lên GitHub Issues hoặc GitHub Project Board, thực hiện theo đúng checklist sau:

- [ ] **Bước 1 (Milestones)**: Tạo hoặc cập nhật 5 Sub-milestones (hoặc Labels) cho Module 2:
  - `M1-S1: Catalog & Full-Catalog Baseline`
  - `M1-S2: Embedding & Offline Indexing`
  - `M1-S3: Hybrid Retrieval`
  - `M1-S4: Dynamic Few-shot & Selector Improvements`
  - `M1-S5: Recovery, Evaluation & Submission Readiness`
- [ ] **Bước 2 (Tạo mới 2 Issues)**:
  - Tạo Issue `M1.0` từ toàn bộ nội dung file `docs/issues/M1.0_catalog_adapter_and_baseline.md` (`Priority: P0`, `Complexity: M`, `Depends on: M0.2`).
  - Tạo Issue `M1.1a` từ toàn bộ nội dung file `docs/issues/M1.1a_embedding_and_offline_index.md` (`Priority: P0`, `Complexity: S`, `Depends on: M1.0`).
- [ ] **Bước 3 (Cập nhật 3 Issues hiện có)**:
  - Cập nhật nội dung Issue `M1.1` từ file `docs/issues/M1.1_retrieval_pipeline.md` (`Depends on: M1.0, M1.1a`).
  - Cập nhật nội dung Issue `M1.2` từ file `docs/issues/M1.2_dynamic_fewshot.md` (`Depends on: M1.1`).
  - Cập nhật nội dung Issue `M1.3` từ file `docs/issues/M1.3_selector_validation.md` (`Depends on: M1.0, M1.1a, M1.1, M1.2`).
- [ ] **Bước 4 (Kiểm tra liên kết)**: Giữ nguyên trạng thái `Closed/Verified` của `M0.1`, `M0.2` và giữ nguyên trạng thái `Planned` của `M2.1` $\rightarrow$ `M4.3`.

---

## Shared Readiness Notes

Trước khi đánh dấu bất kỳ Issue nào trong `M1` là hoàn tất (`Verified`), cần xác nhận:
1. Các bài test trong `tests/contracts/test_retrieval_and_fewshot.py` và `tests/contracts/test_selection_and_metric_validation.py` thuộc phạm vi Issue đó đã được chuyển sang import trực tiếp từ `agent4.metric_selection.*` (không còn gọi `tests.contract_harness`).
2. Các thực nghiệm `E0` $\rightarrow$ `E5` sử dụng `agent4/metric_selection/eval_adapter.py` gọi trực tiếp pipeline thật qua `vals/run_eval.py`.
3. M4.3 đang có xung đột giữa benchmark v1 120 câu trong module plan và benchmark v2 140 câu trong `docs/evaluation.md`; đối với toàn bộ Module 2 (`M1.0` $\rightarrow$ `M1.3`), chuẩn đánh giá chính thức là bộ **140 câu v2 (`data/eval/contract_benchmark_questions.jsonl`)** chạy qua `vals/run_eval.py`, đồng thời vẫn giữ nguyên snapshot v1 để không phá vỡ `tests/benchmark/test_e2e_benchmark_db.py`.
