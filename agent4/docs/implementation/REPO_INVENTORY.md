# Repository inventory — WO-00

Inventory date: 2026-11-04 (Asia/Ho_Chi_Minh). Baseline Git HEAD:
`5d87115ab60c4431fc782fe96e0543ab5e6eb37f`. The worktree was already dirty
before this implementation; no pre-existing change was discarded or reset.

## Existing system

- Python 3.11+ package, FastAPI, Pydantic v2, DuckDB, NumPy/Pandas and PyYAML.
- Canonical catalog: `agent4/engine/metrics.py`, 66 unique IDs: 26 flow, 15
  snapshot, 5 ratio and 20 custom.
- Catalog SHA-256 is
  `b9cee5a9bfb0711e21ecb4e311d330448278e1843fa2b5014d2dd031f122556a`,
  exactly equal to the engineering-pack reference snapshot. Neither file was
  overwritten.
- Existing metric-selection subsystem contains lexical/hash-dense retrieval,
  RRF, expansion, reranking, few-shot selection, Ollama adapter, offline mock,
  benchmarks and 38 passing baseline tests.
- Synthetic warehouse `data/cfo_warehouse.duckdb` reports data version v2.1,
  as-of 2026-10-14, last closed month 2026-08 and 140,583 GL lines. It contains
  GL, AR/AP invoices and payments, inventory, payroll, budgets, fixed assets,
  loans and governed `v_mgmt`/`v_tax` views.

## Actual data boundary

The warehouse is a single-company synthetic file. It has no `tenant_id`, no
database user/grant model and no RLS. DuckDB is opened with `read_only=True`
for every request and a fresh connection prevents pooled session leakage, but
this is not evidence of production tenant isolation. Real-data integration is
therefore BLOCKED. Exact synthetic mapping is in
`integration/DATABASE_MAPPING.yaml`.

Opening rows are identified by `source_document_type='OPENING'`; closing rows
by `is_closing`. Flow compilation excludes both. Snapshot compilation includes
opening rows and accumulates through the as-of date. `v_tax` filters on
`tax_deductible`; this is a synthetic design, not a signed tax policy.

## Architecture adaptation

The existing metric-selection engine is preserved. `agent4/text2sql/` adds a
modular application boundary: strict plan models, deterministic validator,
allowlisted parameterized compiler, read-only executor, conservative offline
selector, grounded renderer and v1 API. No user or LLM SQL enters the compiler.

## Baseline evidence

- `pytest -q` before implementation: 38 passed.
- Pack verification initially BLOCKED because the existing environment lacked
  `jsonschema`; dependency has been added to project requirements.
- Real DB credentials, external LLM credentials, competition rubric and human
  finance/security approvers were not present.
