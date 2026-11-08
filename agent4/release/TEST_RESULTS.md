# Test results

Environment: Python 3.13.11, pytest 9.2.0, DuckDB 2.0.0, local Linux
development container. Results observed 2026-11-04.

- Pack integrity: `python .../verify_pack.py` → `PACK VALIDATED` (66 metrics,
  108 intent seeds, 18 security seeds, 26 balanced fixture lines).
- Baseline before implementation: `pytest -q` → 38 passed.
- Final `pytest -q --junitxml=reports/tests/junit.xml` → **78 passed, 0 failed,
  0 skipped**.
- `make test-unit` → 52 passed.
- `make test-finance` → 7 passed.
- `make test-integration` → 13 passed.
- `make test-security` → 9 selected passed.
- `make test-e2e` → 6 passed.
- `make lint` → all checks passed.
- `make typecheck` → compileall completed (syntax/import compilation only; a
  static type checker is not installed, so a strict type-analysis claim is not
  made).
- `make eval` → retrieval and 70-query local latency reports generated.
- `make demo` → 8 deterministic scenarios executed successfully.

Finance fixture exact values: net revenue 90, gross profit 30, gross margin
33.3333333333%, net profit 11, cash snapshot 1045 and AR snapshot 10. The SQL
path reads seeded rows; expected JSON is not returned directly.

Real DB grants/RLS/provider tests: **BLOCKED**, not skipped-as-pass.
