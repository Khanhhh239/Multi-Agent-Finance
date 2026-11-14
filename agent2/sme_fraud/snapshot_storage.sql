PRAGMA application_id = 1093817137;
PRAGMA user_version = 1;
CREATE TABLE IF NOT EXISTS source_blobs (
  tenant_id TEXT NOT NULL, company_id TEXT NOT NULL, source_hash TEXT NOT NULL,
  content BLOB NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (tenant_id, company_id, source_hash)
);
CREATE TABLE IF NOT EXISTS imports (
  import_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, company_id TEXT NOT NULL, actor_id TEXT NOT NULL,
  revision INTEGER NOT NULL CHECK(revision > 0),
  status TEXT NOT NULL CHECK(status IN ('uploaded','validated','rejected','committed')),
  active_preview_id TEXT, snapshot_id TEXT, commit_request_hash TEXT, created_at TEXT NOT NULL,
  UNIQUE(import_id, tenant_id, company_id)
);
CREATE TABLE IF NOT EXISTS import_revisions (
  import_id TEXT NOT NULL, revision INTEGER NOT NULL, tenant_id TEXT NOT NULL, company_id TEXT NOT NULL,
  source_hash TEXT NOT NULL, filename TEXT NOT NULL, mapping_json BLOB NOT NULL, mapping_hash TEXT NOT NULL,
  created_at TEXT NOT NULL, actor_id TEXT NOT NULL,
  PRIMARY KEY(import_id, revision),
  FOREIGN KEY(import_id, tenant_id, company_id) REFERENCES imports(import_id, tenant_id, company_id),
  FOREIGN KEY(tenant_id, company_id, source_hash) REFERENCES source_blobs(tenant_id, company_id, source_hash)
);
CREATE TABLE IF NOT EXISTS previews (
  preview_id TEXT PRIMARY KEY, import_id TEXT NOT NULL, revision INTEGER NOT NULL,
  tenant_id TEXT NOT NULL, company_id TEXT NOT NULL, actor_id TEXT NOT NULL,
  fingerprint TEXT NOT NULL, report_json BLOB NOT NULL, report_hash TEXT NOT NULL,
  parsed_json BLOB, data_checksum TEXT, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
  FOREIGN KEY(import_id, revision) REFERENCES import_revisions(import_id, revision)
);
CREATE INDEX IF NOT EXISTS preview_lookup ON previews(import_id, revision, fingerprint, created_at);
CREATE TABLE IF NOT EXISTS snapshots (
  snapshot_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, company_id TEXT NOT NULL,
  fingerprint TEXT NOT NULL, manifest_json BLOB NOT NULL, data_json BLOB NOT NULL,
  checksum TEXT NOT NULL, data_checksum TEXT NOT NULL,
  UNIQUE(tenant_id, company_id, fingerprint)
);
CREATE TABLE IF NOT EXISTS request_receipts (
  tenant_id TEXT NOT NULL, company_id TEXT NOT NULL, actor_id TEXT NOT NULL,
  operation TEXT NOT NULL, idempotency_key TEXT NOT NULL, request_hash TEXT NOT NULL,
  response_json BLOB NOT NULL, response_hash TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY(tenant_id, company_id, actor_id, operation, idempotency_key)
);
CREATE TABLE IF NOT EXISTS import_audit (
  event_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, company_id TEXT NOT NULL, actor_id TEXT NOT NULL,
  import_id TEXT NOT NULL, action TEXT NOT NULL, detail_json BLOB NOT NULL, created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS committed_import_update BEFORE UPDATE ON imports
WHEN OLD.status = 'committed' BEGIN SELECT RAISE(ABORT, 'committed import immutable'); END;
CREATE TRIGGER IF NOT EXISTS import_delete BEFORE DELETE ON imports
BEGIN SELECT RAISE(ABORT, 'import history immutable'); END;
