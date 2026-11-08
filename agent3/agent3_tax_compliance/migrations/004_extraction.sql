CREATE TABLE cfr_extractions(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, ingestion_id TEXT NOT NULL,
 ocr_config_key TEXT NOT NULL, extraction_key TEXT NOT NULL, artifact_id TEXT NOT NULL,
 payload TEXT NOT NULL, sha256 TEXT NOT NULL,
 PRIMARY KEY(tenant_id,taxpayer_id,ingestion_id,ocr_config_key,extraction_key),
 UNIQUE(tenant_id,taxpayer_id,artifact_id),
 FOREIGN KEY(tenant_id,taxpayer_id,ingestion_id,ocr_config_key)
 REFERENCES ocr_jobs(tenant_id,taxpayer_id,ingestion_id,config_key));
CREATE TRIGGER cfr_extraction_no_update BEFORE UPDATE ON cfr_extractions BEGIN SELECT RAISE(ABORT,'immutable extraction'); END;
CREATE TRIGGER cfr_extraction_no_delete BEFORE DELETE ON cfr_extractions BEGIN SELECT RAISE(ABORT,'immutable extraction'); END;
INSERT INTO schema_migrations VALUES(4,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
PRAGMA user_version=4;
