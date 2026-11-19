# Kế hoạch di trú database và artifact storage

Ngày lập kế hoạch: 2026-11-19
Mục tiêu: chuyển durable mutable state khỏi SQLite/DuckDB/local files mà không xóa database hiện có, không làm mất append-only/security guarantees và không đổi business logic ngoài persistence adapter.

## Quyết định lưu trữ

### Neon PostgreSQL là system of record cho

- Tenant/company/profile metadata.
- User identity mapping, roles, policy versions và session/job metadata.
- Portal intake manifests, source metadata, SHA-256, audit chain metadata.
- Agent 1 mutable operational state và forecast/reconciliation metadata.
- Agent 2 snapshots/reviews/case/remediation metadata.
- Agent 3 transactional metadata, ingestion/job leases, records, revisions, results và audit events.
- Agent 4 query audit, metric catalog version, provider/model version, policy/claims references và bounded retrieval metadata.
- Bounded embedding chunks có tenant/visibility/version filters.

### Object storage là system of record cho

- Raw uploaded documents, XML/ZIP/PDF/CSV/XLSX.
- Rendered pages, reports, Excel exports và immutable model/data artifacts.
- Legal corpus snapshot, source packages và DuckDB warehouse artifacts.
- Large Agent 1/2/3 outputs không phù hợp PostgreSQL row.
- Checksummed backup exports.

Ứng viên:

1. Neon Object Storage: 5 GB/project, S3-compatible, cùng branch theo tài liệu hiện hành.
2. Cloudflare R2: 10 GB-month, 1M Class A, 10M Class B miễn phí/tháng; dùng nếu cần tách quota hoặc Neon Object Storage chưa sẵn sàng trong account.

### DuckDB được giữ lại ở đâu

- Giữ read-only cho Agent 4 analytical workload nếu warehouse là immutable artifact, kích thước nhỏ và một process đọc.
- Không dùng DuckDB file làm mutable multi-instance database.
- Không tải warehouse 2.3 GB từ object storage vào mỗi cold start Render Free.
- Full warehouse nên chạy local/paid worker hoặc được chuyển thành curated aggregate tables trong PostgreSQL nếu thật sự cần query cloud.
- Bất kỳ artifact DuckDB nào cũng phải có manifest: artifact_id, tenant_id, schema_version, generated_at, source_revision, sha256, size_bytes, provider/model version và retention.

## Evidence schema hiện tại

### Agent 3 foundation SQLite

Migrations 001-010 trong agent3/agent3_tax_compliance/migrations gồm:

- schema_migrations, taxpayer_masters, sources, records, revisions, events, artifacts, jobs.
- ingestions, ingestion_events, documents, page_renders, extraction_outbox.
- ocr_jobs, ocr_page_cache, cfr_extractions, quality_assessments.
- review_tasks, review_events, review_secrets, capture_jobs.
- rule_plans, rule_execution_runs, rule_execution_attempts, compliance_results.
- evaluations, evaluation_reports.
- Append-only triggers và PRAGMA application_id/user_version.
- BLOB raw/page data và JSON payload được lưu trực tiếp trong SQLite.

### Agent 1

agent1/agent1_service/api.py tạo Store trên agent1.db, token file, encryption key và pseudonym key. Business state không chỉ là database row; key lifecycle phải nằm ngoài Neon schema và không được random lại khi Render restart.

### Agent 2

review_server.py và các store tạo snapshot, model, review, comparison, case queue, remediation, release, batch-training SQLite databases. Một số artifact/model được mở read-only, một số workflow là mutable/idempotent. HE4 key/DPAPI/WSL không được migrate bằng cách copy tùy tiện.

### Agent 4

DuckDB schema hiện có 46 objects trong smoke warehouse, gồm gl_entry/gl_wide, dimensions, AR/AP, payroll, budget, views v_gl/v_mgmt/v_tax và ground_truth. Pipeline dùng SQL/VIEW semantics và read-only query guard; port sang PostgreSQL phải preserve numeric/date/sign semantics, không chỉ copy table names.

### Portal

portal/server.py dùng workspace/pending/logs và JSON/JSONL state cho security, audit, batch và company. Những file này phải tách thành relational metadata và object blobs; không bind vào local current working directory.

## Target schema logical

Tên dưới đây là logical names để thiết kế migration; chưa phải code thay đổi.

### Control plane

- tenants
- tenant_members
- roles
- user_identities
- auth_sessions hoặc session_references
- companies
- company_profile_revisions
- policy_versions
- service_capabilities
- deployment_artifacts

### Intake và audit

- intake_batches
- intake_items
- source_objects
- source_revisions
- source_hashes
- audit_events
- audit_chain_heads
- idempotency_receipts
- async_jobs
- job_attempts
- job_events

### Agent 1

- cash_invoices
- invoice_events
- bank_transactions
- customers
- payment_promises
- outflows
- cash_balances
- reconciliation_proposals
- reconciliation_decisions
- forecast_runs
- forecast_artifacts

Giữ tenant_id/firm_id ở mọi bảng; giữ available_on/known_at và immutable transaction semantics. Forecast artifact lớn để object storage; database lưu manifest/version/URI/hash.

### Agent 2

- transaction_snapshots
- snapshot_rows hoặc source_object reference
- analysis_runs
- analysis_findings
- method_artifacts
- review_cases
- case_revisions
- case_audit_events
- delivery_outbox
- remediation_tasks
- release_metadata

Không lưu raw source blob nhiều lần trong Neon; dùng source_objects và content-addressed object keys. Không lưu HE secret trong database.

### Agent 3

Port các bảng logical từ migrations 001-010, giữ:

- composite tenant_id + taxpayer_id scope.
- revision/append-only constraints.
- idempotency_key unique per tenant/taxpayer.
- leases với server-side timestamp và guarded state transitions.
- payload JSON thành JSONB ở giai đoạn đầu để giảm business rewrite.
- raw/page bytes chuyển thành object URI + sha256; chỉ giữ small derived metadata trong DB.
- event/audit append-only.
- policy/ruleset version và inputs_sha256.

Trigger SQLite sẽ được thay bằng PostgreSQL constraints, trigger hoặc service-layer transaction; phải test equivalence trước cutover.

### Agent 4

- metric_catalog
- metric_relationships
- retrieval_documents
- retrieval_chunks
- retrieval_embeddings
- query_audits
- provider_call_summaries
- warehouse_artifacts
- access_policies
- clarification_sessions

Embedding table tối thiểu:

- chunk_id UUID/ULID
- tenant_id
- corpus_id
- source_object_id
- content_hash
- content_text hoặc object_uri nếu text lớn
- embedding VECTOR(d)
- model_id
- model_version
- visibility
- created_at

Bắt buộc filter tenant/corpus/version trước vector similarity. Không dùng embedding index để thay auth policy.

## PostgreSQL và pgvector

Bootstrap migration cần idempotent:

1. CREATE EXTENSION IF NOT EXISTS vector;
2. CREATE EXTENSION IF NOT EXISTS pgcrypto nếu UUID/hash helper cần và policy cho phép.
3. Tạo schema/migration_version.
4. Tạo roles/privileges tối thiểu.
5. Tạo tables/constraints/indexes.
6. Tạo vector column với dimension chốt theo provider.
7. Chỉ tạo HNSW/IVFFlat sau khi có số lượng vector và benchmark query.

Neon docs xác nhận pgvector có trên mọi plan và bật bằng CREATE EXTENSION IF NOT EXISTS vector. Tuy nhiên Neon Free chỉ có 1 GB database storage; không nạp embedding/legal corpus đầy đủ trước khi có budget.

### Vector budget

Cần ghi lại:

- embedding model/version.
- dimension.
- số chunk.
- bytes raw vector ước tính khoảng 4 x dimension mỗi vector trước overhead/index.
- HNSW/IVFFlat index size.
- text/token metadata size.
- expected monthly writes/deletes.

Gate ban đầu: dùng lexical/hashing retrieval hoặc bounded top-k cloud index; full legal corpus tiếp tục đọc từ object artifact/local/paid worker cho tới khi pgvector storage benchmark pass.

## Artifact object key convention

Đề xuất:

- tenants/{tenant_id}/sources/{sha256}/original
- tenants/{tenant_id}/sources/{sha256}/render/{page}.png
- tenants/{tenant_id}/reports/{report_id}/{revision}.json
- tenants/{tenant_id}/warehouses/{artifact_id}/warehouse.duckdb
- corpora/{corpus_id}/{revision}/manifest.json
- corpora/{corpus_id}/{revision}/legal_corpus.sqlite3

Object metadata:

- content_sha256
- size_bytes
- mime_type
- tenant_id
- source_id/artifact_id
- schema_version
- created_at
- encryption/key reference
- retention_until
- immutable flag

Không dùng user-supplied filename làm object key. Dùng signed URL ngắn hạn; service chỉ nhận object_id/hash đã được authorize.

## Migration stages

### Stage 0 — Freeze và inventory

- Tạo release tag/backup copy của mọi SQLite/DuckDB hiện có.
- Không delete/overwrite database.
- Xuất table counts, schema fingerprint, file SHA-256 và row-level sample checksums.
- Chốt migration version và local compatibility flag.

### Stage 1 — Bootstrap Neon

- Chạy migrations trong branch Neon dev.
- Enable pgvector.
- Tạo schemas/constraints/indexes.
- Cấu hình pooled connection string cho web runtime; không mở connection per request.
- Tạo seed reference data idempotent; không seed demo company vào production.

### Stage 2 — Object copy

- Copy raw blobs/corpus/warehouse artifacts theo content-addressed key.
- Verify size/hash sau upload.
- Ghi source_objects/artifact manifest vào Neon.
- Giữ file local nguyên vẹn làm rollback source.

### Stage 3 — Immutable data backfill

- Backfill Agent 3 masters/sources/records/revisions/events/artifacts/jobs.
- Backfill Agent 2 snapshots and model metadata.
- Backfill Agent 1 immutable invoices/bank snapshots.
- Backfill Agent 4 artifact manifests/catalog/version metadata.
- Dùng keyset pagination, batch nhỏ và retry idempotent; không load toàn bộ DB vào memory.

### Stage 4 — Mutable state backfill

- Backfill job statuses, leases, review/case state, session metadata và portal intake state.
- Map local file state thành row + object reference.
- Giữ actor/tenant/idempotency key.
- Không copy secrets/API keys vào data rows.

### Stage 5 — Verification

- Compare row counts by tenant/table.
- Compare sha256 for source/object/payload.
- Check foreign keys, unique/idempotency constraints and append-only behavior.
- Replay representative local fixtures and compare canonical JSON outputs.
- Query Agent 4 same questions against DuckDB and target representation where applicable.
- Confirm no cross-tenant result.

### Stage 6 — Controlled cutover

- Feature flag read path: local or Neon.
- Start read-only cloud verification.
- Enable writes for one synthetic tenant.
- Enable one non-sensitive pilot tenant only after audit/security pass.
- Keep local deployment authoritative until rollback window closes.

## Rollback

- Application rollback: switch read/write mode to local source without deleting Neon rows.
- Data rollback: stop writes, retain Neon branch/snapshot, restore from object manifest/local copy.
- Schema rollback: use expand/contract migrations; never DROP production tables to undo a release.
- Artifact rollback: point artifact_id to previous manifest/version; object data remains immutable.
- Secrets rollback: rotate provider/service credentials independently; never restore a leaked value.
- If a migration has partially committed batches, rerun idempotently from last successful checkpoint.

## Data integrity and security guarantees to preserve

- Append-only source/revision/event semantics.
- SHA-256 content/addressing and audit chain.
- Tenant/company/taxpayer scope in every query.
- Idempotency keys and replay prevention.
- Exact signed VND amounts; do not convert to binary float.
- Policy check before Agent 4 retrieval/SQL.
- Read-only DuckDB and safe SELECT validation.
- No browser exposure of backend bearer keys.
- Raw financial files never in logs or public buckets.

## Free-tier storage decision

**Do not put the current legal corpus, full Agent 4 warehouse or all raw uploaded documents into Neon PostgreSQL.**

Use Neon for bounded metadata/control-plane and optionally a small pgvector index. Use Neon Object Storage or R2 for blobs. Keep full local/large analytical artifacts outside Render Free until paid/worker capacity exists.

## Phase 1 implementation evidence — CM-020 bootstrap

Ngày đo: 2026-11-19

Đã tạo migration additive `database/migrations/001_agent4_cloud_control_plane.sql` và runner `agent4/scripts/migrate_neon.py`.

- Migration bật `vector`, tạo schema `cloud` và các bảng tenant/member, catalog, policy, warehouse manifest, query audit, provider summary, clarification và bounded retrieval metadata/embeddings.
- `retrieval_embeddings` chốt `vector(4096)` theo `config/selection_cloud.yaml`; chưa nạp legal corpus hoặc full warehouse vào Neon Free.
- Mọi warehouse chỉ lưu object key/hash/size/version trong Neon; bytes vẫn ở object storage hoặc artifact source.
- Runner có `--dry-run` secret-free, checksum migration và từ chối checksum mismatch bằng forward-fix; apply dùng transaction, idempotent `CREATE IF NOT EXISTS` và không có destructive DDL/DML.
- `agent4/agent4/persistence/neon.py` lazy-loads `psycopg_pool`, pool mặc định bounded 1–2 connections và chỉ ghi metadata đã giới hạn; không nhận prompt, SQL, rows hoặc credential.

Evidence offline:

    ./.venv/bin/pytest -q tests/contracts/test_neon_persistence.py
    python scripts/migrate_neon.py --dry-run

Kết quả: `4 passed`, dry-run liệt kê migration `001` và SHA-256. Chưa chạy apply trên Neon branch vì workspace không có Neon credential/driver; do đó connection pool, pgvector extension thực tế, storage usage và restore rehearsal vẫn là acceptance gates OPEN. Không database local nào bị sửa/xóa.
