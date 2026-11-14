PRAGMA application_id=1093817138;
PRAGMA user_version=1;
CREATE TABLE IF NOT EXISTS fit_jobs (
 job_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, company_id TEXT NOT NULL,
 actor_id TEXT NOT NULL, idempotency_key TEXT NOT NULL, request_hash TEXT NOT NULL,
 request_json BLOB NOT NULL, status TEXT NOT NULL CHECK(status IN ('running','succeeded','failed')),
 artifact_id TEXT, failure_code TEXT, created_at TEXT NOT NULL, finished_at TEXT,
 protocol_version INTEGER NOT NULL CHECK(protocol_version=1),
 UNIQUE(tenant_id,company_id,actor_id,idempotency_key)
);
CREATE TABLE IF NOT EXISTS method_artifacts (
 artifact_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, company_id TEXT NOT NULL,
 method_id TEXT NOT NULL, job_id TEXT NOT NULL REFERENCES fit_jobs(job_id),
 manifest_json BLOB NOT NULL, payload BLOB NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS models_scope ON method_artifacts(tenant_id,company_id,method_id);
CREATE TABLE IF NOT EXISTS fit_events (
 event_id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL REFERENCES fit_jobs(job_id),
 tenant_id TEXT NOT NULL, company_id TEXT NOT NULL, actor_id TEXT NOT NULL,
 event TEXT NOT NULL, created_at TEXT NOT NULL, detail_json BLOB NOT NULL
);
CREATE TRIGGER IF NOT EXISTS fit_job_request_immutable
 BEFORE UPDATE OF job_id,tenant_id,company_id,actor_id,idempotency_key,request_hash,request_json,created_at,protocol_version
 ON fit_jobs BEGIN SELECT RAISE(ABORT,'immutable fit request'); END;
CREATE TRIGGER IF NOT EXISTS fit_job_no_delete BEFORE DELETE ON fit_jobs
 BEGIN SELECT RAISE(ABORT,'immutable fit history'); END;
CREATE TRIGGER IF NOT EXISTS fit_job_terminal BEFORE UPDATE ON fit_jobs WHEN OLD.status!='running'
 BEGIN SELECT RAISE(ABORT,'terminal fit job'); END;
