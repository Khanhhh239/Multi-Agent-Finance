# Repository Guidelines

## Project Structure & Module Organization

- `agent3_tax_compliance/src/` contains the FastAPI application. Keep ingestion, OCR adapters, extraction, quality, review, planning, rules, and explanation logic in their respective modules.
- `agent3_tax_compliance/src/review/static/` holds the HTML, CSS, and vanilla JavaScript UI.
- `agent3_tax_compliance/tests/` groups tests by subsystem; `tests/fixtures/` contains synthetic documents.
- `agent3_tax_compliance/contracts/`, `configs/`, and `migrations/` hold schemas, versioned configuration, and database migrations.
- `scripts/` contains validation and benchmark entry points. Plans and evidence live in `docs/agent3/plans/`.
- `data invoice/ocr_e2e_workflow/` contains the separate OCR runtime. Preserve `archive/` snapshots needed for historical replay.

## Build, Test, and Development Commands

Run these from the repository root in PowerShell:

```powershell
.\OPEN_AGENT3.cmd
.\STOP_AGENT3.cmd
.\agent3_tax_compliance\.venv\Scripts\python.exe scripts\validate_capture_upgrade.py
```

The launchers start/stop the demo; the validator runs Python, JavaScript, and Chrome regressions and writes evidence. No frontend bundling is required. The demo needs existing environments/models; consult README runtime instructions and dependency lock files.

For focused review tests:

```powershell
cd agent3_tax_compliance
.\.venv\Scripts\python.exe -m unittest discover -s tests/review -v
node --check src/review/static/app.js
```

## Coding Style & Naming Conventions

Use four-space Python indentation, `snake_case` functions/modules, and `PascalCase` classes. Follow adjacent JavaScript conventions and use `textContent` for untrusted text. No repository-wide formatter configuration is currently enforced; avoid unrelated reformatting.

Use Pydantic contracts at boundaries. Preserve exact Decimal arithmetic and evidence provenance; never convert money to floating point. Keep model adapters replaceable and configuration versioned.

## Testing Guidelines

The regression runners use `unittest`; browser checks use Playwright with local Chrome. Name Python tests `test_*.py` and browser runners `scripts/check_*_browser.py`.

Test affected behavior first, then run broader validation for shared-contract or workflow changes. Cover tenant isolation, stale revisions, idempotency, rollback, and evidence ownership. No numeric coverage threshold is enforced. Report synthetic regression results separately from real-invoice accuracy; never call development samples independent holdout data.

## Commit & Pull Request Guidelines

Recent commits use imperative, descriptive subjects such as `Add bounded regional OCR rereads`. Keep commits focused. PRs should explain behavior changes, validation commands/results, contract changes, and remaining limitations. Link relevant plans/issues and include screenshots for UI changes. Do not merge or force-push without authorization.

## Security & Architecture Invariants

Keep tokens, local policies, databases, downloaded invoices, environments, and model weights out of Git. Preserve `.gitignore` exclusions. Corrections create audited revisions; recovery must protect confirmed values. LLM explanations must not override rule results, and code changes must not promote draft legal rules or enable auto-accept without supporting validation.
