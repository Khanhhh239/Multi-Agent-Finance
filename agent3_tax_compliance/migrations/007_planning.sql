CREATE TABLE rule_plans(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, evaluation_id TEXT NOT NULL,
 record_id TEXT NOT NULL, revision INTEGER NOT NULL, replay_key TEXT NOT NULL,
 payload TEXT NOT NULL, sha256 TEXT NOT NULL, inputs TEXT NOT NULL, inputs_sha256 TEXT NOT NULL,
 PRIMARY KEY(tenant_id,taxpayer_id,evaluation_id),
 UNIQUE(tenant_id,taxpayer_id,record_id,revision,replay_key),
 FOREIGN KEY(tenant_id,taxpayer_id,record_id,revision) REFERENCES revisions(tenant_id,taxpayer_id,record_id,revision));
CREATE INDEX planning_record_scope ON rule_plans(tenant_id,taxpayer_id,record_id,revision);
CREATE TRIGGER rule_plans_no_update BEFORE UPDATE ON rule_plans BEGIN SELECT RAISE(ABORT,'immutable rule plan'); END;
CREATE TRIGGER rule_plans_no_delete BEFORE DELETE ON rule_plans BEGIN SELECT RAISE(ABORT,'immutable rule plan'); END;
INSERT INTO schema_migrations VALUES(7,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
PRAGMA user_version=7;
