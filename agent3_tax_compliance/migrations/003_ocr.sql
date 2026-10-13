CREATE TABLE ocr_jobs(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, ingestion_id TEXT NOT NULL,
 config_key TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 lease_token TEXT, lease_until REAL, payload TEXT, sha256 TEXT, issue TEXT,
 PRIMARY KEY(tenant_id,taxpayer_id,ingestion_id,config_key),
 FOREIGN KEY(tenant_id,taxpayer_id,ingestion_id) REFERENCES extraction_outbox(tenant_id,taxpayer_id,ingestion_id));
CREATE TABLE ocr_page_cache(
 tenant_id TEXT NOT NULL, taxpayer_id TEXT NOT NULL, cache_key TEXT NOT NULL,
 payload TEXT NOT NULL, sha256 TEXT NOT NULL,
 PRIMARY KEY(tenant_id,taxpayer_id,cache_key));
CREATE TRIGGER ocr_cache_no_update BEFORE UPDATE ON ocr_page_cache BEGIN SELECT RAISE(ABORT,'immutable OCR cache'); END;
CREATE TRIGGER ocr_cache_no_delete BEFORE DELETE ON ocr_page_cache BEGIN SELECT RAISE(ABORT,'immutable OCR cache'); END;
CREATE TRIGGER ocr_result_no_update BEFORE UPDATE ON ocr_jobs WHEN OLD.payload IS NOT NULL BEGIN SELECT RAISE(ABORT,'immutable OCR result'); END;
CREATE TRIGGER ocr_result_no_delete BEFORE DELETE ON ocr_jobs WHEN OLD.payload IS NOT NULL BEGIN SELECT RAISE(ABORT,'immutable OCR result'); END;
INSERT INTO schema_migrations VALUES(3,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
PRAGMA user_version=3;
