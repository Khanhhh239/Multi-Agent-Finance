CREATE TABLE quality_assessments(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, extraction_artifact_id TEXT NOT NULL,
 replay_key TEXT NOT NULL, assessment_id TEXT NOT NULL, payload TEXT NOT NULL, sha256 TEXT NOT NULL,
 inputs TEXT NOT NULL, inputs_sha256 TEXT NOT NULL,
 PRIMARY KEY(tenant_id,taxpayer_id,replay_key), UNIQUE(tenant_id,taxpayer_id,assessment_id),
 FOREIGN KEY(tenant_id,taxpayer_id,extraction_artifact_id) REFERENCES cfr_extractions(tenant_id,taxpayer_id,artifact_id));
CREATE TRIGGER quality_no_update BEFORE UPDATE ON quality_assessments BEGIN SELECT RAISE(ABORT,'immutable quality assessment'); END;
CREATE TRIGGER quality_no_delete BEFORE DELETE ON quality_assessments BEGIN SELECT RAISE(ABORT,'immutable quality assessment'); END;
INSERT INTO schema_migrations VALUES(5,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
PRAGMA user_version=5;
