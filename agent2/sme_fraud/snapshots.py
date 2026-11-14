"""Immutable import revisions/reports/snapshots, atomic commits and retry receipts."""
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sqlite3
import uuid

from finance_input import AccessScope
from finance_input.json_io import loads
from finance_input.validation import stamp
from .import_files import canonical, context, digest, fail, mapping_contract, parse_file, MAX_BYTES, PROTOCOL_VERSION

APPLICATION_ID = 1093817137
COMMIT_FIELDS = {"expected_revision", "preview_id", "source_hash", "mapping_hash", "report_hash", "context_hash", "acknowledge"}
HASH = re.compile(r"[a-f0-9]{64}\Z")


class SnapshotStore:
    def __init__(self, path, clock=None, preview_ttl=900):
        self.path = Path(path).resolve()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        if not isinstance(preview_ttl, int) or not 1 <= preview_ttl <= 86400:
            raise ValueError("preview_ttl must be 1..86400 seconds")
        self.preview_ttl = preview_ttl
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            app = conn.execute("PRAGMA application_id").fetchone()[0]
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
            if (app == 0 and tables) or app not in {0, APPLICATION_ID} or (app == APPLICATION_ID and version != 1):
                fail(503, "STORAGE_VERSION", "Đường dẫn DB không phải kho snapshot phiên bản được hỗ trợ.", "Chọn DB snapshot mới riêng; không dùng hoặc tự migrate DB Agent2 cũ.")
            conn.execute("PRAGMA journal_mode=WAL")
            sql = Path(__file__).with_name("snapshot_storage.sql").read_text("utf-8")
            # All historical artifacts are append-only, including drafts' old revisions.
            for table in ("source_blobs", "import_revisions", "previews", "snapshots", "request_receipts", "import_audit"):
                for action in ("UPDATE", "DELETE"):
                    sql += f"\nCREATE TRIGGER IF NOT EXISTS {table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable artifact'); END;\n"
            conn.executescript("BEGIN IMMEDIATE;\n"+sql+"\nCOMMIT;")

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def _now(self):
        return self.clock().astimezone(timezone.utc)

    @staticmethod
    def _scope(scope):
        if not isinstance(scope, AccessScope) or len(scope.company_ids) != 1 or "data.import" not in scope.permissions or not scope.actor_id:
            fail(403, "ACCESS_DENIED", "Không có quyền nhập trong phạm vi một doanh nghiệp.", "Dùng quyền data.import đúng tenant và doanh nghiệp.")
        return scope.tenant_id, next(iter(scope.company_ids)), scope.actor_id

    @contextmanager
    def _transaction(self, scope, recheck=None):
        self._scope(scope)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            # Recheck after waiting for a concurrent writer, before domain queries.
            if recheck is not None and recheck() != scope:
                fail(409, "AUTH_CONTEXT_CHANGED", "Quyền đã thay đổi trong lúc xử lý.", "Tải lại kết quả kiểm tra theo quyền hiện hành.")
            yield conn
            # A long parse/read must not bypass revocation before COMMIT/return.
            if recheck is not None and recheck() != scope:
                fail(409, "AUTH_CONTEXT_CHANGED", "Quyền đã thay đổi trước khi hoàn tất.", "Tải lại kết quả kiểm tra theo quyền hiện hành.")
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def _audit(self, conn, scope, import_id, action, detail):
        tenant, company, actor = self._scope(scope)
        conn.execute("INSERT INTO import_audit VALUES (?,?,?,?,?,?,?,?)",
            ("evt_"+uuid.uuid4().hex, tenant, company, actor, import_id, action, canonical(detail), self._now().isoformat()))

    def _receipt(self, conn, scope, operation, key, request_hash, value=None):
        tenant, company, actor = self._scope(scope)
        if not isinstance(key, str) or re.fullmatch(r"[A-Za-z0-9_.:-]{8,128}", key) is None:
            fail(400, "IDEMPOTENCY_KEY", "Thiếu hoặc sai Idempotency-Key.", "Giữ một khóa 8–128 ký tự cho mỗi yêu cầu; retry dùng lại đúng khóa và nội dung.")
        row = conn.execute("SELECT * FROM request_receipts WHERE tenant_id=? AND company_id=? AND actor_id=? AND operation=? AND idempotency_key=?",
                           (tenant, company, actor, operation, key)).fetchone()
        if row:
            if row["request_hash"] != request_hash:
                fail(409, "IDEMPOTENCY_CONFLICT", "Khóa gửi lại đã dùng cho nội dung khác.", "Giữ nội dung cũ khi retry hoặc tạo khóa mới cho yêu cầu mới.")
            if self._stored_hash(row["response_json"]) != row["response_hash"]:
                self._integrity()
            return self._stored_json(row["response_json"])
        if value is not None:
            content = canonical(value)
            conn.execute("INSERT INTO request_receipts VALUES (?,?,?,?,?,?,?,?,?)",
                (tenant, company, actor, operation, key, request_hash, content, digest(content), self._now().isoformat()))
        return None

    @staticmethod
    def _integrity():
        fail(500, "ARTIFACT_INTEGRITY", "Checksum dữ liệu lưu không khớp; chưa trả dữ liệu hoặc tạo snapshot.", "Người vận hành đối chiếu kho/backup; không tự bỏ qua kiểm tra checksum.")

    def _stored_hash(self, content):
        if not isinstance(content, bytes):
            self._integrity()
        return digest(content)

    def _stored_json(self, content):
        self._stored_hash(content)
        try:
            value = loads(content)
            if not isinstance(value, dict):
                self._integrity()
            canonical(value)
            return value
        except (ValueError, UnicodeError, RecursionError, OverflowError):
            self._integrity()

    def _draft(self, conn, scope, import_id):
        row = conn.execute("SELECT * FROM imports WHERE import_id=? AND tenant_id=? AND company_id=? AND actor_id=?", (import_id, *self._scope(scope))).fetchone()
        if row is None:
            fail(404, "IMPORT_NOT_FOUND", "Không có lần nhập trong phạm vi được phép.", "Chọn đúng doanh nghiệp và lần nhập của người thao tác.")
        return row

    def _revision(self, conn, draft):
        row = conn.execute("SELECT * FROM import_revisions WHERE import_id=? AND revision=?", (draft["import_id"], draft["revision"])).fetchone()
        if row is None or self._stored_hash(row["mapping_json"]) != row["mapping_hash"]:
            self._integrity()
        return row

    def _source(self, conn, revision):
        row = conn.execute("SELECT content FROM source_blobs WHERE tenant_id=? AND company_id=? AND source_hash=?",
            (revision["tenant_id"], revision["company_id"], revision["source_hash"])).fetchone()
        if row is None or self._stored_hash(row["content"]) != revision["source_hash"]:
            self._integrity()
        return row["content"]

    def _info(self, conn, draft):
        row = self._revision(conn, draft)
        return dict(protocol_version=PROTOCOL_VERSION, import_id=draft["import_id"], company_id=draft["company_id"],
            revision=draft["revision"], status=draft["status"], source_hash=row["source_hash"], mapping_hash=row["mapping_hash"],
            filename=row["filename"], mapping=self._stored_json(row["mapping_json"]), active_preview_id=draft["active_preview_id"], snapshot_id=draft["snapshot_id"])

    @staticmethod
    def _expected(draft, expected):
        if type(expected) is not int or expected < 1:
            fail(400, "EXPECTED_REVISION", "Thiếu revision đang xem.", "Gửi expected_revision là số nguyên từ kết quả server.")
        if draft["revision"] != expected:
            fail(409, "STALE_REVISION", "Tệp hoặc mapping đã đổi sau lần xem trước.", "Lấy revision hiện hành và kiểm tra lại trước khi xác nhận lưu.")
        if draft["status"] == "committed":
            fail(409, "IMPORT_COMMITTED", "Lần nhập đã tạo snapshot bất biến.", "Tạo lần nhập mới nếu cần sửa dữ liệu; không ghi đè snapshot.")

    @staticmethod
    def _filename(filename, raw):
        if not isinstance(filename, str) or not 1 <= len(filename) <= 200 or any(c in filename for c in "/\\:\r\n\x00") or not filename.lower().endswith((".json",".csv",".xlsx")):
            fail(415, "FILE_FORMAT", "Nhận CSV UTF-8, Excel .xlsx hoặc JSON theo hợp đồng đầu vào.", "Dùng tệp theo mẫu, tên không chứa đường dẫn; không nhận .xls hoặc macro.")
        if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
            fail(413, "FILE_SIZE", "Tệp phải có dữ liệu và không vượt 10 MB.", "Chọn tệp JSON hợp lệ trong giới hạn.")

    def _put_revision(self, conn, scope, draft, raw, filename, mapping):
        tenant, company, actor = self._scope(scope)
        source_hash = digest(raw); mapping_bytes = canonical(mapping)
        revision = draft["revision"] if draft["status"] == "initial" else draft["revision"]+1
        conn.execute("INSERT OR IGNORE INTO source_blobs VALUES (?,?,?,?,?)", (tenant, company, source_hash, raw, self._now().isoformat()))
        conn.execute("INSERT INTO import_revisions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (draft["import_id"], revision, tenant, company, source_hash, filename, mapping_bytes, digest(mapping_bytes), self._now().isoformat(), actor))
        conn.execute("UPDATE imports SET revision=?,status='uploaded',active_preview_id=NULL WHERE import_id=?", (revision, draft["import_id"]))

    def upload(self, scope, raw, filename, key, recheck=None):
        self._filename(filename, raw)
        request_hash = digest(canonical(dict(filename=filename, source_hash=digest(raw))))
        with self._transaction(scope, recheck) as conn:
            prior = self._receipt(conn, scope, "upload", key, request_hash)
            if prior is not None:
                return prior
            tenant, company, actor = self._scope(scope)
            import_id = "imp_"+uuid.uuid4().hex
            conn.execute("INSERT INTO imports VALUES (?,?,?,?,1,'uploaded',NULL,NULL,NULL,?)", (import_id, tenant, company, actor, self._now().isoformat()))
            self._put_revision(conn, scope, dict(import_id=import_id, revision=1, status="initial"), raw, filename, {})
            value = self._info(conn, self._draft(conn, scope, import_id))
            self._audit(conn, scope, import_id, "uploaded", dict(revision=1, source_hash=digest(raw)))
            self._receipt(conn, scope, "upload", key, request_hash, value)
            return value

    def revise(self, scope, import_id, expected, key, *, raw=None, filename=None, mapping=None, recheck=None):
        operation = "source" if raw is not None else "mapping"
        if operation == "source":
            self._filename(filename, raw)
            payload = dict(source_hash=digest(raw), filename=filename)
        else:
            mapping = mapping_contract(mapping)
            payload = dict(mapping=mapping)
        request_hash = digest(canonical(dict(import_id=import_id, expected_revision=expected, **payload)))
        with self._transaction(scope, recheck) as conn:
            self._draft(conn, scope, import_id)  # scopes every receipt replay too
            prior = self._receipt(conn, scope, operation, key, request_hash)
            if prior is not None:
                return prior
            draft = self._draft(conn, scope, import_id); self._expected(draft, expected)
            old = self._revision(conn, draft)
            data = raw if raw is not None else self._source(conn, old)
            name = filename if raw is not None else old["filename"]
            columns = mapping if mapping is not None else loads(old["mapping_json"])
            if digest(data) != old["source_hash"] or digest(canonical(columns)) != old["mapping_hash"] or name != old["filename"]:
                self._put_revision(conn, scope, draft, data, name, columns)
                self._audit(conn, scope, import_id, operation+"_changed", dict(previous_revision=expected, revision=expected+1))
            value = self._info(conn, self._draft(conn, scope, import_id))
            self._receipt(conn, scope, operation, key, request_hash, value)
            return value

    def get_import(self, scope, import_id, recheck=None):
        with self._transaction(scope, recheck) as conn:
            return self._info(conn, self._draft(conn, scope, import_id))

    def _verified_report(self, row):
        if row is None:
            fail(409, "PREVIEW_REQUIRED", "Chưa có kết quả kiểm tra hiện hành.", "Chạy bước xem kết quả kiểm tra trước khi xác nhận lưu.")
        value = self._stored_json(row["report_json"])
        checksum = value.pop("report_hash", None)
        if checksum != row["report_hash"] or digest(canonical(value)) != checksum:
            self._integrity()
        value["report_hash"] = checksum
        if row["parsed_json"] is not None and self._stored_hash(row["parsed_json"]) != row["data_checksum"]:
            self._integrity()
        return value

    def preview(self, scope, import_id, expected, recheck=None):
        with self._transaction(scope, recheck) as conn:
            draft = self._draft(conn, scope, import_id); self._expected(draft, expected)
            revision = self._revision(conn, draft); raw = self._source(conn, revision)
            versions, context_hash = context(scope)
            fingerprint = digest(canonical(dict(revision=expected, source_hash=revision["source_hash"], mapping_hash=revision["mapping_hash"], context_hash=context_hash)))
            cached = conn.execute("SELECT * FROM previews WHERE import_id=? AND revision=? AND fingerprint=? ORDER BY created_at DESC LIMIT 1", (import_id, expected, fingerprint)).fetchone()
            if cached is not None and stamp(cached["expires_at"]) > self._now():
                value = self._verified_report(cached)
            else:
                parsed, report = parse_file(raw, loads(revision["mapping_json"]), scope,revision['filename'])
                now = self._now(); preview_id = "prv_"+uuid.uuid4().hex
                value = dict(report, protocol_version=PROTOCOL_VERSION, import_id=import_id, preview_id=preview_id,
                    company_id=draft["company_id"], revision=expected, source_hash=revision["source_hash"],
                    mapping_hash=revision["mapping_hash"], context_hash=context_hash, versions=versions,
                    data_checksum=digest(parsed) if parsed is not None else None,
                    created_at=now.isoformat(), expires_at=(now+timedelta(seconds=self.preview_ttl)).isoformat())
                value["report_hash"] = digest(canonical(value))
                conn.execute("INSERT INTO previews VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (preview_id, import_id, expected,
                    *self._scope(scope), fingerprint, canonical(value), value["report_hash"], parsed, value["data_checksum"], value["created_at"], value["expires_at"]))
                self._audit(conn, scope, import_id, "previewed", dict(revision=expected, preview_id=preview_id, report_hash=value["report_hash"], status=value["status"]))
            status = "rejected" if value["status"] == "rejected" else "validated"
            conn.execute("UPDATE imports SET status=?,active_preview_id=? WHERE import_id=?", (status, value["preview_id"], import_id))
            return value

    def get_report(self, scope, import_id, recheck=None):
        with self._transaction(scope, recheck) as conn:
            draft = self._draft(conn, scope, import_id)
            row = conn.execute("SELECT * FROM previews WHERE preview_id=? AND import_id=?", (draft["active_preview_id"], import_id)).fetchone()
            return self._verified_report(row)

    def _read_snapshot(self, conn, scope, snapshot_id):
        tenant, company, _ = self._scope(scope)
        row = conn.execute("SELECT * FROM snapshots WHERE snapshot_id=? AND tenant_id=? AND company_id=?", (snapshot_id, tenant, company)).fetchone()
        if row is None:
            fail(404, "SNAPSHOT_NOT_FOUND", "Không có snapshot trong phạm vi được phép.", "Chọn đúng doanh nghiệp và mã snapshot.")
        manifest = self._stored_json(row["manifest_json"])
        data = row["data_json"]
        if self._stored_hash(data) != row["data_checksum"] or digest(canonical(dict(manifest=manifest, data_checksum=digest(data)))) != row["checksum"]:
            self._integrity()
        if manifest.get("snapshot_id") != snapshot_id or manifest.get("tenant_id") != tenant or manifest.get("company_id") != company or manifest.get("data_checksum") != row["data_checksum"]:
            self._integrity()
        return dict(manifest, checksum=row["checksum"]), data

    def get_snapshot(self, scope, snapshot_id, recheck=None, *, data=False):
        with self._transaction(scope, recheck) as conn:
            manifest, raw = self._read_snapshot(conn, scope, snapshot_id)
            return raw if data else manifest

    def commit(self, scope, import_id, request, key, recheck=None):
        if not isinstance(request, dict) or set(request) != COMMIT_FIELDS or request.get("acknowledge") is not True:
            fail(400, "COMMIT_CONFIRMATION", "Cần xác nhận lưu và đầy đủ revision/preview/hash đã xem.", "Gửi acknowledge=true cùng đúng các trường từ preview; client không được tự tạo report.")
        if any(not isinstance(request.get(name), str) or HASH.fullmatch(request[name]) is None for name in ("source_hash", "mapping_hash", "report_hash", "context_hash")):
            fail(400, "COMMIT_HASH", "Hash xác nhận không hợp lệ.", "Lấy nguyên các checksum từ kết quả kiểm tra của server.")
        if type(request["expected_revision"]) is not int or request["expected_revision"] < 1 or not isinstance(request["preview_id"], str) or re.fullmatch(r"prv_[a-f0-9]{32}", request["preview_id"]) is None:
            fail(400, "COMMIT_FIELDS", "Revision hoặc mã preview không hợp lệ.", "Lấy đúng expected_revision và preview_id từ kết quả kiểm tra của server.")
        request_hash = digest(canonical(dict(import_id=import_id, **request)))
        with self._transaction(scope, recheck) as conn:
            draft = self._draft(conn, scope, import_id)
            prior = self._receipt(conn, scope, "commit", key, request_hash)
            if prior is not None:
                self._read_snapshot(conn, scope, prior["snapshot"]["snapshot_id"])
                return prior
            if draft["status"] == "committed":
                if draft["commit_request_hash"] != request_hash:
                    fail(409, "IMPORT_COMMITTED", "Lần nhập đã được chốt với nội dung khác.", "Đọc snapshot đã tạo hoặc tạo lần nhập mới; không ghi đè.")
                manifest, _ = self._read_snapshot(conn, scope, draft["snapshot_id"])
                value = dict(status="committed", import_id=import_id, snapshot=manifest)
                self._receipt(conn, scope, "commit", key, request_hash, value)
                return value
            self._expected(draft, request["expected_revision"])
            revision = self._revision(conn, draft)
            row = conn.execute("SELECT * FROM previews WHERE preview_id=? AND import_id=?", (draft["active_preview_id"], import_id)).fetchone()
            report = self._verified_report(row)
            versions, context_hash = context(scope)
            expected_fields = dict(preview_id=draft["active_preview_id"], source_hash=revision["source_hash"],
                mapping_hash=revision["mapping_hash"], report_hash=report["report_hash"], context_hash=context_hash)
            if any(request[name] != value for name, value in expected_fields.items()) or report["context_hash"] != context_hash or report["versions"] != versions or report["revision"] != draft["revision"]:
                fail(409, "STALE_PREVIEW", "Tệp, mapping, quyền hoặc bộ kiểm tra không còn khớp preview.", "Kiểm tra lại rồi xác nhận đúng revision và các hash mới.")
            if stamp(report["expires_at"]) <= self._now():
                fail(409, "PREVIEW_EXPIRED", "Kết quả kiểm tra đã hết hạn.", "Chạy preview lại rồi xác nhận lưu.")
            if report["status"] == "rejected":
                fail(409, "VALIDATION_REJECTED", "Dữ liệu còn lỗi nên chưa thể tạo snapshot.", "Sửa tệp/mapping và kiểm tra lại; không bỏ qua lỗi hoặc gửi report tự tạo.")
            parsed, fresh = parse_file(self._source(conn, revision), loads(revision["mapping_json"]), scope,revision['filename'])
            if parsed is None or digest(parsed) != report["data_checksum"] or any(fresh[k] != report[k] for k in fresh):
                fail(409, "VALIDATION_CHANGED", "Kết quả kiểm tra lại không khớp preview đã khóa.", "Chạy preview mới; chưa tạo snapshot từ dữ liệu đã đổi.")
            if stamp(report["expires_at"]) <= self._now():
                fail(409, "PREVIEW_EXPIRED", "Preview đã hết hạn trong lúc kiểm tra lại.", "Chạy preview mới rồi xác nhận lưu; chưa có snapshot được tạo.")
            tenant, company, actor = self._scope(scope)
            fingerprint = digest(canonical(dict(data_checksum=digest(parsed), source_hash=revision["source_hash"], mapping_hash=revision["mapping_hash"], versions=versions)))
            existing = conn.execute("SELECT snapshot_id FROM snapshots WHERE tenant_id=? AND company_id=? AND fingerprint=?", (tenant, company, fingerprint)).fetchone()
            if existing:
                manifest, _ = self._read_snapshot(conn, scope, existing["snapshot_id"])
            else:
                snapshot_id = "snp_"+uuid.uuid4().hex
                manifest = dict(snapshot_version=PROTOCOL_VERSION, snapshot_id=snapshot_id, tenant_id=tenant, company_id=company,
                    contract_version=loads(parsed)['contract_version'], data_checksum=digest(parsed), source_hash=revision["source_hash"], mapping_hash=revision["mapping_hash"],
                    versions=versions, origin_import_id=import_id, origin_revision=draft["revision"], origin_preview_id=report["preview_id"],
                    origin_report_hash=report["report_hash"], created_at=self._now().isoformat(), created_by=actor)
                checksum = digest(canonical(dict(manifest=manifest, data_checksum=digest(parsed))))
                conn.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?)", (snapshot_id, tenant, company, fingerprint, canonical(manifest), parsed, checksum, digest(parsed)))
                manifest = dict(manifest, checksum=checksum)
            self._audit(conn, scope, import_id, "committed", dict(snapshot_id=manifest["snapshot_id"], checksum=manifest["checksum"], revision=draft["revision"], acknowledge=True))
            conn.execute("UPDATE imports SET status='committed',snapshot_id=?,commit_request_hash=? WHERE import_id=?", (manifest["snapshot_id"], request_hash, import_id))
            value = dict(status="committed", import_id=import_id, snapshot=manifest)
            self._receipt(conn, scope, "commit", key, request_hash, value)
            return value
