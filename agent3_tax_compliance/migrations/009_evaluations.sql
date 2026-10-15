CREATE TABLE evaluations(
 tenant_id TEXT NOT NULL,taxpayer_id TEXT NOT NULL,evaluation_id TEXT NOT NULL,
 record_id TEXT NOT NULL,revision INTEGER NOT NULL,idempotency_key TEXT NOT NULL,command_sha256 TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('RUNNING','FAILED','COMPLETED')),stage TEXT NOT NULL,
 lease_token TEXT NOT NULL,lease_until REAL NOT NULL,created_at TEXT NOT NULL,
 snapshot TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,error TEXT,
 PRIMARY KEY(tenant_id,taxpayer_id,evaluation_id),UNIQUE(tenant_id,taxpayer_id,idempotency_key),
 FOREIGN KEY(tenant_id,taxpayer_id,record_id,revision) REFERENCES revisions(tenant_id,taxpayer_id,record_id,revision));
CREATE INDEX evaluation_record_scope ON evaluations(tenant_id,taxpayer_id,record_id,revision);
CREATE TABLE evaluation_reports(
 tenant_id TEXT NOT NULL,taxpayer_id TEXT NOT NULL,evaluation_id TEXT NOT NULL,
 payload TEXT NOT NULL,sha256 TEXT NOT NULL,
 PRIMARY KEY(tenant_id,taxpayer_id,evaluation_id),
 FOREIGN KEY(tenant_id,taxpayer_id,evaluation_id) REFERENCES evaluations(tenant_id,taxpayer_id,evaluation_id));
CREATE TRIGGER evaluation_reports_no_update BEFORE UPDATE ON evaluation_reports BEGIN SELECT RAISE(ABORT,'immutable evaluation report'); END;
CREATE TRIGGER evaluation_reports_no_delete BEFORE DELETE ON evaluation_reports BEGIN SELECT RAISE(ABORT,'immutable evaluation report'); END;
CREATE TRIGGER evaluation_snapshot_no_update BEFORE UPDATE ON evaluations
 WHEN NEW.snapshot!=OLD.snapshot OR NEW.snapshot_sha256!=OLD.snapshot_sha256 OR NEW.command_sha256!=OLD.command_sha256
 OR NEW.created_at!=OLD.created_at OR NEW.evaluation_id!=OLD.evaluation_id OR NEW.record_id!=OLD.record_id OR NEW.revision!=OLD.revision
 OR NEW.tenant_id!=OLD.tenant_id OR NEW.taxpayer_id!=OLD.taxpayer_id OR NEW.idempotency_key!=OLD.idempotency_key
 BEGIN SELECT RAISE(ABORT,'immutable evaluation snapshot'); END;
INSERT INTO schema_migrations VALUES(9,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
PRAGMA user_version=9;
