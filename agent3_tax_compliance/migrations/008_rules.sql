CREATE TABLE rule_execution_runs(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, execution_id TEXT NOT NULL,
 evaluation_id TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('RUNNING','COMPLETE')),
 lease_token TEXT NOT NULL, lease_until REAL NOT NULL, created_at TEXT NOT NULL,
 inputs TEXT NOT NULL, inputs_sha256 TEXT NOT NULL,
 PRIMARY KEY(tenant_id,taxpayer_id,execution_id),
 FOREIGN KEY(tenant_id,taxpayer_id,evaluation_id) REFERENCES rule_plans(tenant_id,taxpayer_id,evaluation_id));
CREATE TABLE rule_execution_attempts(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, execution_id TEXT NOT NULL,
 attempt_id TEXT NOT NULL, payload TEXT NOT NULL, sha256 TEXT NOT NULL,
 PRIMARY KEY(tenant_id,taxpayer_id,execution_id,attempt_id),
 FOREIGN KEY(tenant_id,taxpayer_id,execution_id) REFERENCES rule_execution_runs(tenant_id,taxpayer_id,execution_id));
CREATE TABLE compliance_results(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, execution_id TEXT NOT NULL,
 payload TEXT NOT NULL, sha256 TEXT NOT NULL,
 PRIMARY KEY(tenant_id,taxpayer_id,execution_id),
 FOREIGN KEY(tenant_id,taxpayer_id,execution_id) REFERENCES rule_execution_runs(tenant_id,taxpayer_id,execution_id));
CREATE TRIGGER rule_attempts_no_update BEFORE UPDATE ON rule_execution_attempts BEGIN SELECT RAISE(ABORT,'immutable rule attempt'); END;
CREATE TRIGGER rule_attempts_no_delete BEFORE DELETE ON rule_execution_attempts BEGIN SELECT RAISE(ABORT,'immutable rule attempt'); END;
CREATE TRIGGER compliance_no_update BEFORE UPDATE ON compliance_results BEGIN SELECT RAISE(ABORT,'immutable compliance result'); END;
CREATE TRIGGER compliance_no_delete BEFORE DELETE ON compliance_results BEGIN SELECT RAISE(ABORT,'immutable compliance result'); END;
CREATE TRIGGER execution_inputs_no_update BEFORE UPDATE ON rule_execution_runs
 WHEN NEW.inputs != OLD.inputs OR NEW.inputs_sha256 != OLD.inputs_sha256 OR NEW.created_at != OLD.created_at
 OR NEW.tenant_id != OLD.tenant_id OR NEW.taxpayer_id != OLD.taxpayer_id OR NEW.execution_id != OLD.execution_id
 OR NEW.evaluation_id != OLD.evaluation_id
 BEGIN SELECT RAISE(ABORT,'immutable execution inputs'); END;
INSERT INTO schema_migrations VALUES(8,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
PRAGMA user_version=8;
