CREATE TABLE review_tasks(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, task_id TEXT NOT NULL,
 record_id TEXT NOT NULL, revision INTEGER NOT NULL, assessment_id TEXT NOT NULL,
 reason TEXT NOT NULL, field_path TEXT NOT NULL, action TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('OPEN','RESOLVED','SUPERSEDED','WAITING_DATA','OPERATOR')),
 previous_ids TEXT NOT NULL, PRIMARY KEY(tenant_id,taxpayer_id,task_id),
 UNIQUE(tenant_id,taxpayer_id,record_id,revision,reason,field_path,action),
 FOREIGN KEY(tenant_id,taxpayer_id,record_id,revision) REFERENCES revisions(tenant_id,taxpayer_id,record_id,revision));
CREATE INDEX review_task_scope ON review_tasks(tenant_id,taxpayer_id,record_id,revision,status);
CREATE INDEX extraction_record_scope ON cfr_extractions(tenant_id,taxpayer_id,json_extract(payload,'$.record.record_id'));
CREATE TABLE review_events(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, record_id TEXT NOT NULL,
 event_id TEXT NOT NULL, idempotency_key TEXT NOT NULL, command_sha256 TEXT NOT NULL,
 payload TEXT NOT NULL, sha256 TEXT NOT NULL,
 PRIMARY KEY(tenant_id,taxpayer_id,event_id), UNIQUE(tenant_id,taxpayer_id,record_id,idempotency_key));
CREATE TRIGGER review_events_no_update BEFORE UPDATE ON review_events BEGIN SELECT RAISE(ABORT,'immutable review event'); END;
CREATE TRIGGER review_events_no_delete BEFORE DELETE ON review_events BEGIN SELECT RAISE(ABORT,'immutable review event'); END;
CREATE TABLE review_secrets(id INTEGER PRIMARY KEY CHECK(id=1), secret BLOB NOT NULL);
INSERT INTO review_secrets VALUES(1,randomblob(32));
CREATE TABLE capture_jobs(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, job_id TEXT NOT NULL,
 ingestion_id TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 lease_token TEXT, lease_until REAL, payload TEXT NOT NULL,
 PRIMARY KEY(tenant_id,taxpayer_id,job_id), UNIQUE(tenant_id,taxpayer_id,ingestion_id));
INSERT INTO schema_migrations VALUES(6,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
PRAGMA user_version=6;
