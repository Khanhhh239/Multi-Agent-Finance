CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE taxpayer_masters(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, revision INTEGER NOT NULL,
 payload TEXT NOT NULL, PRIMARY KEY(tenant_id,taxpayer_id,revision));
CREATE TABLE sources(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, source_id TEXT NOT NULL,
 master_revision INTEGER NOT NULL, sha256 TEXT NOT NULL, raw BLOB NOT NULL, envelope TEXT NOT NULL,
 PRIMARY KEY(tenant_id,taxpayer_id,source_id),
 FOREIGN KEY(tenant_id,taxpayer_id,master_revision) REFERENCES taxpayer_masters(tenant_id,taxpayer_id,revision));
CREATE TABLE records(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, record_id TEXT NOT NULL,
 source_id TEXT NOT NULL, head INTEGER NOT NULL CHECK(head >= 1),
 PRIMARY KEY(tenant_id,taxpayer_id,record_id),
 FOREIGN KEY(tenant_id,taxpayer_id,source_id) REFERENCES sources(tenant_id,taxpayer_id,source_id));
CREATE TABLE revisions(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, record_id TEXT NOT NULL,
 revision INTEGER NOT NULL CHECK(revision >= 1), payload TEXT NOT NULL, sha256 TEXT NOT NULL,
 PRIMARY KEY(tenant_id,taxpayer_id,record_id,revision),
 FOREIGN KEY(tenant_id,taxpayer_id,record_id) REFERENCES records(tenant_id,taxpayer_id,record_id));
CREATE TABLE events(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, event_id TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(tenant_id,taxpayer_id,event_id));
CREATE TABLE artifacts(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, artifact_id TEXT NOT NULL,
 record_id TEXT NOT NULL, record_revision INTEGER NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(tenant_id,taxpayer_id,artifact_id),
 FOREIGN KEY(tenant_id,taxpayer_id,record_id,record_revision) REFERENCES revisions(tenant_id,taxpayer_id,record_id,revision));
CREATE TABLE jobs(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, job_id TEXT NOT NULL,
 source_id TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(tenant_id,taxpayer_id,job_id),
 FOREIGN KEY(tenant_id,taxpayer_id,source_id) REFERENCES sources(tenant_id,taxpayer_id,source_id));
CREATE TRIGGER sources_no_update BEFORE UPDATE ON sources BEGIN SELECT RAISE(ABORT,'immutable source'); END;
CREATE TRIGGER sources_no_delete BEFORE DELETE ON sources BEGIN SELECT RAISE(ABORT,'immutable source'); END;
CREATE TRIGGER revisions_no_update BEFORE UPDATE ON revisions BEGIN SELECT RAISE(ABORT,'append-only revision'); END;
CREATE TRIGGER revisions_no_delete BEFORE DELETE ON revisions BEGIN SELECT RAISE(ABORT,'append-only revision'); END;
CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'append-only event'); END;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'append-only event'); END;
CREATE TRIGGER masters_no_update BEFORE UPDATE ON taxpayer_masters BEGIN SELECT RAISE(ABORT,'append-only master'); END;
CREATE TRIGGER masters_no_delete BEFORE DELETE ON taxpayer_masters BEGIN SELECT RAISE(ABORT,'append-only master'); END;
CREATE TRIGGER artifacts_no_update BEFORE UPDATE ON artifacts BEGIN SELECT RAISE(ABORT,'append-only artifact'); END;
CREATE TRIGGER artifacts_no_delete BEFORE DELETE ON artifacts BEGIN SELECT RAISE(ABORT,'append-only artifact'); END;
CREATE TRIGGER jobs_no_update BEFORE UPDATE ON jobs BEGIN SELECT RAISE(ABORT,'job snapshots are immutable'); END;
CREATE TRIGGER jobs_no_delete BEFORE DELETE ON jobs BEGIN SELECT RAISE(ABORT,'job snapshots are immutable'); END;
INSERT INTO schema_migrations VALUES(1,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
PRAGMA application_id=1128353876;
PRAGMA user_version=1;
