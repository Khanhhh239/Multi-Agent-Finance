CREATE TABLE ingestions(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, ingestion_id TEXT NOT NULL,
 idempotency_key TEXT NOT NULL, fingerprint TEXT NOT NULL, source_id TEXT NOT NULL,
 document_id TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('STORED','QUEUED','PROCESSING','SUCCEEDED','FAILED')),
 attempts INTEGER NOT NULL DEFAULT 0, lease_until REAL, lease_token TEXT,
 issue TEXT, created_at TEXT NOT NULL,
 PRIMARY KEY(tenant_id,taxpayer_id,ingestion_id), UNIQUE(tenant_id,taxpayer_id,idempotency_key),
 FOREIGN KEY(tenant_id,taxpayer_id,source_id) REFERENCES sources(tenant_id,taxpayer_id,source_id));
CREATE TABLE ingestion_events(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, event_id TEXT NOT NULL,
 ingestion_id TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(tenant_id,taxpayer_id,event_id),
 FOREIGN KEY(tenant_id,taxpayer_id,ingestion_id) REFERENCES ingestions(tenant_id,taxpayer_id,ingestion_id));
CREATE TABLE documents(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, ingestion_id TEXT NOT NULL,
 payload TEXT NOT NULL, sha256 TEXT NOT NULL,
 PRIMARY KEY(tenant_id,taxpayer_id,ingestion_id),
 FOREIGN KEY(tenant_id,taxpayer_id,ingestion_id) REFERENCES ingestions(tenant_id,taxpayer_id,ingestion_id));
CREATE TABLE page_renders(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, ingestion_id TEXT NOT NULL,
 page_index INTEGER NOT NULL, png BLOB NOT NULL, sha256 TEXT NOT NULL,
 PRIMARY KEY(tenant_id,taxpayer_id,ingestion_id,page_index),
 FOREIGN KEY(tenant_id,taxpayer_id,ingestion_id) REFERENCES documents(tenant_id,taxpayer_id,ingestion_id));
CREATE TABLE extraction_outbox(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, ingestion_id TEXT NOT NULL,
 document_sha256 TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'QUEUED',
 PRIMARY KEY(tenant_id,taxpayer_id,ingestion_id),
 FOREIGN KEY(tenant_id,taxpayer_id,ingestion_id) REFERENCES documents(tenant_id,taxpayer_id,ingestion_id));
CREATE INDEX ingestion_pending ON ingestions(tenant_id,taxpayer_id,status,lease_until);
CREATE TRIGGER documents_no_update BEFORE UPDATE ON documents BEGIN SELECT RAISE(ABORT,'immutable document'); END;
CREATE TRIGGER documents_no_delete BEFORE DELETE ON documents BEGIN SELECT RAISE(ABORT,'immutable document'); END;
CREATE TRIGGER renders_no_update BEFORE UPDATE ON page_renders BEGIN SELECT RAISE(ABORT,'immutable render'); END;
CREATE TRIGGER renders_no_delete BEFORE DELETE ON page_renders BEGIN SELECT RAISE(ABORT,'immutable render'); END;
CREATE TRIGGER ingestion_events_no_update BEFORE UPDATE ON ingestion_events BEGIN SELECT RAISE(ABORT,'append-only ingestion event'); END;
CREATE TRIGGER ingestion_events_no_delete BEFORE DELETE ON ingestion_events BEGIN SELECT RAISE(ABORT,'append-only ingestion event'); END;
INSERT INTO schema_migrations VALUES(2,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
PRAGMA user_version=2;
