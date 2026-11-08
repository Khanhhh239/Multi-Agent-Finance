-- Structured XML invoices have no rendered document and no OCR job, so extractions can no longer
-- require an ocr_jobs parent. OCR-derived rows keep their config key; XML rows use the sentinel key.
-- Deferred foreign keys let the table be rebuilt in one transaction without disturbing child rows.
PRAGMA defer_foreign_keys=ON;
CREATE TABLE cfr_extractions_new(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, ingestion_id TEXT NOT NULL,
 ocr_config_key TEXT NOT NULL, extraction_key TEXT NOT NULL, artifact_id TEXT NOT NULL,
 payload TEXT NOT NULL, sha256 TEXT NOT NULL,
 PRIMARY KEY(tenant_id,taxpayer_id,ingestion_id,ocr_config_key,extraction_key),
 UNIQUE(tenant_id,taxpayer_id,artifact_id),
 FOREIGN KEY(tenant_id,taxpayer_id,ingestion_id) REFERENCES ingestions(tenant_id,taxpayer_id,ingestion_id));
INSERT INTO cfr_extractions_new SELECT * FROM cfr_extractions;
DROP TABLE cfr_extractions;
ALTER TABLE cfr_extractions_new RENAME TO cfr_extractions;
CREATE TRIGGER cfr_extraction_no_update BEFORE UPDATE ON cfr_extractions BEGIN SELECT RAISE(ABORT,'immutable extraction'); END;
CREATE TRIGGER cfr_extraction_no_delete BEFORE DELETE ON cfr_extractions BEGIN SELECT RAISE(ABORT,'immutable extraction'); END;
INSERT INTO schema_migrations VALUES(10,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
PRAGMA user_version=10;
