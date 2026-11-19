# Lộ trình di trú cloud — milestones, issues và tasks

Ngày lập kế hoạch: 2026-11-19
Trạng thái: planning/feasibility only. Chưa triển khai migration, chưa đổi business logic/UI, chưa xóa database.

## Nguyên tắc

- Local deployment hiện tại vẫn là baseline và phải tiếp tục chạy.
- Mọi thay đổi cloud nằm sau config/feature flag hoặc adapter; không rewrite business logic khi chưa có regression evidence.
- Không commit secret, không copy secret vào Neon/object storage, không xóa SQLite/DuckDB.
- Full application chỉ được chuyển sang cloud sau khi đóng NO-GO gates trong docs/cloud-evaluation.md.
- Mỗi issue có test và rollback riêng; issue không được coi là complete chỉ vì build pass.
- Render Free được xem là preview/conditional slice, không phải production durability tier.

## Milestone M0 — Feasibility và regression baseline

### Issue CM-000 — Chốt phạm vi cloud slice và NO-GO boundary

**Objective**

Chốt chính xác phần nào chạy trên free tier và phần nào giữ local/paid; tránh tuyên bố full application tương thích khi chưa có benchmark.

**Scope**

- Agent 4 health/metrics/query slice.
- Portal static frontend.
- Neon control-plane tối thiểu.
- Object storage artifact flow.
- Explicit exclusions: Agent 2 HE4, Agent 1 forecast training, Agent 3 full OCR/law sync và full 2.3 GB warehouse.

**Affected files**

- docs/cloud-migration-architecture.md
- docs/cloud-evaluation.md
- docs/cloud-resource-budget.md
- README.md và docs/DEPLOY_SERVER.md chỉ được cập nhật ở issue documentation sau khi quyết định được duyệt.

**Dependencies**

- Kết quả benchmark M0.
- Product owner xác nhận chấp nhận hybrid.

**Implementation strategy**

Tạo capability matrix và cloud feature flags; giữ local launcher untouched. Không disable feature local.

**Acceptance criteria**

- Có bảng feature-to-runtime.
- Mỗi excluded feature có lý do tài nguyên/security.
- Có owner và gate để reconsider sau khi nâng tier.

**Test commands**

- git diff --check
- rg -n "create_demo_app|AGENT4_DEMO_MODE|run_web.ps1" docs agent4 README.md

**Rollback strategy**

Xóa hoặc đảo documentation decision trong branch kế hoạch; không chạm source/runtime.

### Issue CM-001 — Thiết lập clean dependency/build matrix

**Objective**

Tạo một build contract có thể tái lập cho cloud slice và phát hiện dependency conflict trước khi refactor.

**Scope**

- Agent 4 và Gateway dependencies.
- Shared finance_input nếu cloud slice cần.
- Lock/constraints và Python version.
- Không gom Agent 1-3 heavy dependencies vào free image nếu chưa cần.

**Affected files**

- agent4/pyproject.toml
- agent4/requirements.txt
- agent4/uv.lock
- shared/finance_input/pyproject.toml
- dependency manifest mới ở cloud build directory, nếu được phê duyệt

**Dependencies**

CM-000.

**Implementation strategy**

Chọn một package manager/lock source; build từ clean checkout trong CI; import health slice; scan package sizes. Agent 1-3 vẫn có environment riêng cho local.

**Acceptance criteria**

- Clean image cài được trong CI.
- agent4.api và Gateway import pass.
- Không có runtime dependency ẩn.
- Có output lock/image digest.

**Test commands**

- uv sync --frozen hoặc command lock tương đương
- python -c "import agent4.api"
- python -m pytest -q agent4/tests/contracts/test_remote_metric_selection.py
- pip check hoặc uv pip check trong clean image

**Rollback strategy**

Giữ lock/image cũ; revert build manifest only. Không sửa agent runtime manifests trong cùng issue.

### Issue CM-002 — Benchmark matrix và functional baselines

**Objective**

Đo cold start, peak RSS, CPU time, query latency, response size và behavior regression bằng production-like fixtures.

**Scope**

- Agent 4 slice.
- Portal static load.
- Auth/policy denial.
- One small immutable warehouse.
- Mock provider và external provider contract.

**Affected files**

- agent4/tests/
- portal/static/
- benchmark scripts/test fixtures trong test-only directory
- docs/cloud-resource-budget.md
- docs/cloud-evaluation.md

**Dependencies**

CM-001; a small warehouse fixture; no real secrets.

**Implementation strategy**

Chạy 3 cold starts x concurrency 1/5/10; đo p50/p95; tách provider latency khỏi app latency; lưu JSON benchmark artifact không chứa financial raw data.

**Acceptance criteria**

- Peak RSS < 400 MiB target trên 512 MB.
- Health p95 < 250 ms.
- Query p95 < 60 s và hard timeout < 90 s.
- Auth denial không gọi model/SQL.
- Mọi kết quả có commit/image/fixture fingerprint.

**Test commands**

- /usr/bin/time -v python benchmark_agent4.py
- python -m pytest -q agent4/tests/contracts/test_governed_demo_api.py -k "health or auth"
- curl -fsS /healthz
- curl -fsS /health

**Rollback strategy**

Xóa benchmark artifact chỉ trong test output; không xóa source/database. Nếu gate fail, giữ slice ở NO-GO.

## Milestone M1 — Cloud slice backend

### Issue CM-010 — Tách Gateway khỏi Portal subprocess launcher

**Objective**

Cho phép một backend process gọi route/cloud capability mà không tự spawn Agent 1-4.

**Scope**

- Gateway application boundary.
- Environment-driven PORT/bind/origin.
- Service registry và health contracts.
- Không đổi business logic agent.

**Affected files**

- portal/server.py
- portal/config.example.json
- portal/static/app.js
- portal/static/index.html
- new gateway adapter/module nếu cần
- tests portal security/launch

**Dependencies**

CM-000, CM-001; auth decision.

**Implementation strategy**

Tạo chế độ cloud explicit: no child processes, no localhost URL construction, no random browser-facing service tokens. Reuse existing route handlers through adapters where possible. Local mode remains default for run_web.ps1.

**Acceptance criteria**

- Local launcher behavior unchanged.
- Cloud mode binds 0.0.0.0:$PORT.
- Cloud mode has unauthenticated /healthz and separate /readyz.
- Child process spawning is disabled in cloud mode.
- Agent routes resolve through config/service contract, not hardcoded ports.

**Test commands**

- python -m pytest -q portal/test_portal_security_and_intake.py
- python -m pytest -q portal/test_bank_intake.py portal/test_bank_profile_contract.py
- cloud mode ASGI/HTTP health test
- rg -n "127.0.0.1|localhost|--start-all" portal/server.py portal/static

**Rollback strategy**

Set cloud mode off and continue run_web.ps1; retain previous Portal entry point and local config.

### Issue CM-011 — Agent 4 production vertical slice

**Objective**

Expose a minimal non-demo governed query route compatible with one Render Free instance.

**Scope**

- create_app, not create_demo_app.
- Health, metrics/catalog, query with injected claims/policy.
- Small immutable warehouse artifact.
- External LLM/embedding providers with bounded timeouts.
- Lexical fallback.
- No raw upload, no local model, no demo persona.

**Affected files**

- agent4/agent4/api.py
- agent4/agent4/pipeline.py
- agent4/agent4/metric_selection/config.py
- agent4/config/selection_cloud.yaml
- agent4/tests/contracts/
- docs/cloud-resource-budget.md

**Dependencies**

CM-001, CM-002, Neon/object artifact contract from CM-020/CM-021.

**Implementation strategy**

Keep governed pipeline and safe SQL unchanged unless adapter requires it. Inject idp_claims and server_policy at Gateway boundary. Add concurrency semaphore and explicit timeout. Use artifact manifest instead of a mutable default DB path.

**Acceptance criteria**

- GET /healthz is cheap and auth-free.
- Non-demo query without claims returns 403.
- Claims/policy scope is enforced before model/retrieval/SQL.
- Query does not accept X-Demo-Persona in production mode.
- Small warehouse query matches local golden output.
- No backend secret is returned in health/metrics/query responses.
- Peak RSS/latency gates pass.

**Test commands**

- python -m pytest -q agent4/tests/contracts/test_governed_demo_api.py
- python -m pytest -q agent4/tests/contracts/test_remote_metric_selection.py
- python -m pytest -q agent4/tests/contracts/test_intake_auth_catalog.py
- ASGI smoke with httpx.AsyncClient/ASGITransport
- benchmark concurrency command from CM-002

**Rollback strategy**

Disable cloud Agent 4 route and point Portal to local Agent 4; retain artifact version and database rows.

### Issue CM-012 — Auth, policy, CORS and iframe contract

**Objective**

Preserve existing security guarantees while moving static UI to Vercel and backend to Render.

**Scope**

- User/session identity.
- Tenant/policy injection.
- Same-origin rewrites or explicit CORS.
- CSP frame-src/frame-ancestors.
- CSRF/cookie behavior.
- Remove browser exposure of backend bearer keys.

**Affected files**

- portal/server.py
- portal/static/app.js
- portal/static/index.html
- agent4/agent4/api.py
- portal/test_portal_security_and_intake.py
- agent4/tests/contracts/

**Dependencies**

CM-010, CM-011; chosen identity provider.

**Implementation strategy**

Prefer same-origin Vercel rewrites to one Gateway; do not expose each agent. Use allow-listed production/preview origins and secure cookies. Keep FaceID local/optional until HTTPS/WebAuthn threat model is approved.

**Acceptance criteria**

- Vercel production and preview origins are explicit.
- No wildcard CORS with credentials.
- Iframe routes render without CSP violation.
- Tenant isolation and unauthorized query denial pass.
- Agent 1 key endpoint is absent or server-only.
- CSRF mutation tests pass.

**Test commands**

- python -m pytest -q portal/test_portal_security_and_intake.py
- python -m pytest -q agent4/tests/contracts/test_governed_demo_api.py -k "auth or branch or denial"
- browser smoke through Vercel preview
- security header scan against preview URL

**Rollback strategy**

Switch frontend to prior Portal origin and disable cloud rewrites; revert CSP/CORS config to local mode.

## Milestone M2 — Persistence and artifacts

### Issue CM-020 — Neon schema bootstrap and pgvector decision

**Objective**

Create additive, versioned PostgreSQL schema for cloud control-plane state without deleting local DBs.

**Scope**

- Migration runner.
- Core tenants/users/policies/audit/jobs.
- Source/artifact manifests.
- pgvector extension and bounded embedding table.
- Pooled Neon connection.

**Affected files**

- new database/migrations/
- new database/seed/
- new persistence adapters
- docs/database-migration-plan.md
- CI migration job config

**Dependencies**

CM-000, CM-011, identity decision, connection budget.

**Implementation strategy**

Use expand/contract migrations; create vector extension once; seed only idempotent reference data. Keep JSON payload JSONB first to minimize business changes. Do not store raw documents/warehouse in PostgreSQL.

**Acceptance criteria**

- Migrations run twice without destructive behavior.
- pgvector extension and dimension check pass.
- Pooled connection works under bounded concurrency.
- Neon storage forecast stays below 800 MB.
- Schema is tenant-scoped with constraints/indexes.
- Migration rollback/recovery rehearsal documented.

**Test commands**

- migration runner --dry-run
- migration runner --apply on Neon dev branch
- psql connection command with extension query
- database integration tests
- pg_dump/restore verification

**Rollback strategy**

Stop writes, keep Neon branch/snapshot, switch application to local mode, use forward-fix/expand-contract rather than dropping tables.

### Issue CM-021 — Object storage adapter and manifest

**Objective**

Move uploads/legal artifacts/reports/warehouse blobs off Render ephemeral filesystem.

**Scope**

- S3-compatible adapter for Neon Object Storage or R2.
- Signed upload/download URLs.
- SHA-256 and size verification.
- Retention/private bucket policy.
- Artifact manifests in Neon.

**Affected files**

- new storage adapter
- portal/server.py upload path
- Agent 3 inbox/artifact paths
- Agent 4 warehouse loader
- storage/security tests

**Dependencies**

CM-020; provider bucket/account; auth policy.

**Implementation strategy**

Upload directly from browser when safe; backend validates signed metadata and records object id/hash. No user filename path joins. Make objects immutable/content-addressed.

**Acceptance criteria**

- Upload never depends on Render local disk.
- Hash/size mismatch is rejected.
- Unauthorized tenant cannot get signed URL.
- Object lifecycle/retention and delete policy are explicit.
- Artifact manifest can restore the exact warehouse/legal snapshot.

**Test commands**

- storage adapter unit tests with mock S3
- integration upload/download with test bucket
- checksum tamper test
- signed URL expiry test
- rg -n "write_bytes|write_text|open\\(" portal agent3 agent4

**Rollback strategy**

Keep local path fallback behind local-only flag; stop cloud writes and use existing local database/artifacts. Do not delete cloud objects during rollback.

### Issue CM-022 — SQLite/DuckDB migration rehearsal

**Objective**

Validate row/hash/semantic equivalence before any production cutover.

**Scope**

- Agent 1/2 SQLite export.
- Agent 3 migrations 001-010 mapping.
- Portal JSON/JSONL state mapping.
- Agent 4 artifact manifest/curated aggregate mapping.
- No destructive migration.

**Affected files**

- new export/import tools
- new verification tests
- database/migrations/
- docs/database-migration-plan.md

**Dependencies**

CM-020, CM-021; representative local fixtures.

**Implementation strategy**

Snapshot local DBs read-only; keyset batch export; checksum each source/blob/payload; import to Neon branch; replay golden flows; compare canonical JSON and audit chain.

**Acceptance criteria**

- Counts and hashes match expected fixtures.
- Append-only/update protections hold.
- Tenant isolation holds.
- Import is idempotent and resumable.
- No original database is modified or deleted.
- Rollback from Neon branch to local baseline is tested.

**Test commands**

- sqlite read-only inventory script
- export/import --dry-run
- compare-counts-and-hashes
- golden Agent 1/2/3/4 regression commands
- pg_dump schema-only and restore on temporary branch

**Rollback strategy**

Discard only disposable Neon migration branch; retain source files and original local databases. Production branch is never reset as part of this issue.

## Milestone M3 — Frontend and deploy contract

### Issue CM-030 — Vercel static project and route contract

**Objective**

Deploy Portal static assets without changing UI behavior.

**Scope**

- portal/static as project root/artifact.
- asset paths, iframe routes, API rewrites, security headers.
- no Vercel Functions for financial backend.

**Affected files**

- new vercel.json or equivalent project config
- portal/static/index.html
- portal/static/app.js
- docs/cloud-migration-architecture.md
- deployment CI config

**Dependencies**

CM-010, CM-012, CM-011.

**Implementation strategy**

Use static deployment; rewrite only short API requests to Gateway. Keep uploads/query long jobs asynchronous. Verify all 24 static files and agent4_chat/design assets are included.

**Acceptance criteria**

- Static deployment has no 404 for index/CSS/JS/brand/FaceID assets.
- API base/rewrite works in preview and production.
- CSP/iframe/origin headers pass.
- No secret appears in Vercel environment or artifact.
- Rewrite timeout is not used by long-running job.

**Test commands**

- vercel build or static deploy preview
- curl -fsS preview URL
- asset manifest 404 scan
- Playwright/browser smoke
- route matrix for /api/healthz and /api/agent4/query

**Rollback strategy**

Promote previous Vercel deployment; disable rewrite and point Portal to local/previous backend.

### Issue CM-031 — Render Free backend image and runtime

**Objective**

Build/deploy one reproducible cloud slice with correct PORT/bind/health behavior.

**Scope**

- Dockerfile/build config for Gateway + Agent 4 slice.
- 0.1 CPU/512 MB resource guard.
- health/readiness, logs, graceful shutdown.
- no child processes, no local durable writes.

**Affected files**

- new cloud/Dockerfile
- new cloud/entrypoint
- agent4/pyproject.toml/uv.lock if needed
- Portal Gateway adapter
- CI config

**Dependencies**

CM-001, CM-010, CM-011, CM-020/021.

**Implementation strategy**

Use a small image; do not install torch/transformers/Concrete. Bind 0.0.0.0:$PORT. Use pooled Neon and object storage. Disable demo mode. Add memory/concurrency guard.

**Acceptance criteria**

- Clean image starts within target.
- /healthz works on Render port.
- Peak RSS < 400 MiB target over three cold runs.
- Restart loses no durable state.
- No Render local file is source of truth.
- Logs are structured and secret-free.

**Test commands**

- docker build
- docker run with fake test env only
- curl /healthz and /readyz
- docker stats under benchmark load
- Render preview smoke

**Rollback strategy**

Render rollback to previous deploy/image; no DB destructive action. Disable cloud traffic and use local deployment.

## Milestone M4 — Deferred full-agent work

### Issue CM-040 — Agent 1 forecast worker compatibility

**Objective**

Determine whether Agent 1 ingestion/reconciliation can run cloud and isolate forecasting if not.

**Scope**

- FastAPI ingestion/read paths.
- SQLite-to-Neon adapter.
- Forecast training/inference resource benchmark.
- torch/Chronos optional stack.
- async job/result artifact contract.

**Affected files**

- agent1/agent1_service/
- agent1/agent1/
- agent1/requirements-forecast.txt
- agent1/Dockerfile
- agent1/tests/

**Dependencies**

CM-020/021/022; production-like forecast fixture; worker tier.

**Implementation strategy**

Keep ingest/reconciliation as a separate capability; run training in a paid/background worker or local worker. Do not install forecast extras in Free web image unless benchmark proves fit.

**Acceptance criteria**

- Forecast p95/peak RSS/CPU measured.
- Ingest/reconciliation correctness matches local golden fixtures.
- Job retries/idempotency and artifact checksum work.
- Explicit GO/NO-GO for Free and paid tier.

**Test commands**

- python -m pytest -q agent1/tests/test_ingest_pipeline.py agent1/tests/test_service_security.py
- forecast benchmark with production-like fixture
- memory/time measurement
- golden reconciliation comparison

**Rollback strategy**

Disable cloud forecast route; keep local forecast worker and local state. No model artifact deletion.

### Issue CM-041 — Agent 2 Linux/cloud boundary

**Objective**

Separate portable review/snapshot logic from unsupported HE4/Windows runtime.

**Scope**

- HTTP server bind/auth boundary.
- SQLite-to-Neon metadata mapping.
- HE4/Concrete/DPAPI/WSL compatibility assessment.
- public/private service threat model.

**Affected files**

- agent2/sme_fraud/review_server.py
- agent2/sme_fraud/portal_auth.py
- agent2/requirements*.txt
- agent2/experiments/
- agent2/tests/

**Dependencies**

CM-020/021; cryptography manifest fix; HE owner decision.

**Implementation strategy**

Do not emulate DPAPI or mock HE4. Declare HE4 unsupported on Free; portable snapshot/review can be benchmarked separately. Add cryptography direct dependency and clean image.

**Acceptance criteria**

- Portable path runs in a clean Linux image.
- HE4 path is either proven on supported paid runtime or explicitly excluded.
- Auth no longer requires localhost-only Portal.
- No public unauthenticated agent endpoint.
- Tests cover replay/tenant/auth.

**Test commands**

- clean install from Agent 2 production manifest
- python -m pytest -q agent2/tests/test_portal_auth.py agent2/tests/test_snapshots.py
- HE4 dedicated compatibility test, not run on Free
- security endpoint scan

**Rollback strategy**

Keep Agent 2 local; disable cloud capability. Preserve existing HE artifacts and keys.

### Issue CM-042 — Agent 3 law/OCR cloud boundary

**Objective**

Determine which Agent 3 API paths can fit externalized storage and no local model on free tier.

**Scope**

- Raw XML/ZIP/bank ingestion.
- workspace/artifact adapter.
- legal corpus object snapshot.
- external LLM/embed/rerank.
- OCR/local model and law sync resource budget.

**Affected files**

- agent3/agent3_tax_compliance/src/assistant/
- agent3/agent3_tax_compliance/src/persistence/
- agent3/agent3_tax_compliance/src/lawbase/
- agent3/agent3_tax_compliance/migrations/
- agent3/agent3_tax_compliance/requirements.txt
- tests/

**Dependencies**

CM-020/021/022; provider contracts; legal corpus rights/retention decision.

**Implementation strategy**

Port metadata first; store raw/source blobs in object storage. Keep full lawbase/OCR sync local/paid until peak memory/CPU/latency are measured. No local torch/reranker in Free image.

**Acceptance criteria**

- XML/bank golden fixtures match local output.
- Law citations/source hashes remain identical.
- Workspaces survive restart via object/Neon.
- Provider timeout/retry is bounded.
- Cloud paths have explicit GO/NO-GO separate from local path.

**Test commands**

- python -m pytest -q agent3/agent3_tax_compliance/tests/assistant/test_web.py
- python -m pytest -q agent3/agent3_tax_compliance/tests/lawbase/test_lawbase.py
- ingestion golden replay
- memory/latency benchmark with external providers mocked

**Rollback strategy**

Disable cloud Agent 3 routes; keep local web app and corpus. Never delete local lawbase/workspaces.

## Milestone M5 — Full migration decision

### Issue CM-050 — Full-system go/no-go review

**Objective**

Make an evidence-based decision on full cloud deployment.

**Scope**

- All gates in docs/cloud-evaluation.md.
- Memory/CPU/latency/storage/quota/security/regression.
- 30-day operational simulation.

**Affected files**

- docs/cloud-evaluation.md
- docs/cloud-resource-budget.md
- docs/cloud-migration-architecture.md
- release evidence artifacts

**Dependencies**

CM-002, CM-011, CM-012, CM-020-022, CM-030-042 as applicable.

**Implementation strategy**

Review only signed/traceable benchmark artifacts. A missing benchmark is FAIL, not assumed pass.

**Acceptance criteria**

GO requires every blocker closed, memory margin, query/request budget, persistence/backup, auth/tenant regression, provider failure handling and quota forecast. Otherwise record NO-GO and keep hybrid/local.

**Test commands**

- full CI test matrix
- cloud preview end-to-end
- load benchmark
- security regression suite
- migration restore/replay rehearsal

**Rollback strategy**

No production cutover without a tested rollback. If any gate fails, do not deploy full system; keep local and conditional slice only.

## Suggested order and ownership

1. M0: architecture/product decision and benchmark harness.
2. M1: gateway/Agent 4/auth slice.
3. M2: Neon/object adapters and migration rehearsal.
4. M3: Vercel/Render preview.
5. M4: agent-by-agent feasibility, starting with Agent 1 portable ingest, then Agent 3, then Agent 2 portable path; HE4 last.
6. M5: full-system review.

The first practical milestone is not “deploy four agents”; it is “prove a secure, durable, bounded Agent 4 slice without breaking local deployment.”

## Phase 1 execution status — 2026-11-19

| Issue | Evidence status | Decision |
|---|---|---|
| CM-002 | Deterministic Agent 4 query trace and smoke benchmark pass; external provider/concurrency/container cgroup evidence còn thiếu | Partial; G2/G4 vẫn OPEN |
| CM-011 | Non-demo cloud boundary, deny-by-default claims/policy, readiness, admission and CORS contract pass | Contract complete; Gateway/IdP và external query còn thiếu |
| CM-020 | Additive Neon/pgvector migration, lazy adapter và dry-run pass | Contract complete; Neon apply/restore chưa diễn tập |
| CM-031 | Docker image build, artifact verification, Render health/readiness và static packaging pass | Partial; chưa Render smoke thật, chưa query trong container |
| CM-010/CM-012/CM-030 | Portal cần Gateway state/session/API contract; chưa chọn IdP và chưa có authenticated proxy | Blocked; không được đánh dấu cloud E2E GO |

Các issue tiếp theo không được bỏ qua blocker bằng cách trỏ Vercel trực tiếp vào Agent 4. Tiếp tục local deployment và chỉ mở preview sau khi CM-010/CM-012 chốt boundary xác thực, CORS/CSRF và API route contract.
