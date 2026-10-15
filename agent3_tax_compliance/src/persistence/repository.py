import hashlib
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from uuid import uuid4

from ..config import Settings
from ..domain.cfr import CanonicalFinancialRecord
from ..domain.envelope import SourceEnvelope
from ..domain.events import AuditEvent
from ..domain.storage import Artifact, Job
from ..domain.taxpayer import AccessContext, TaxpayerMaster

APP_ID = 1128353876
MIGRATION = Path(__file__).resolve().parents[2] / 'migrations/001_foundation.sql'


class RevisionConflict(Exception):
    pass


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class Repository:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.path = settings.database_path.resolve()

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute('PRAGMA foreign_keys=ON')
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            app_id = db.execute('PRAGMA application_id').fetchone()[0]
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if tables:
                if app_id != APP_ID or version not in (1,2,3,4,5,6,7,8,9):
                    raise ValueError('refusing to migrate non-foundation/unknown-version database')
                if version==1:
                    db.executescript('BEGIN IMMEDIATE;\n'+MIGRATION.with_name('002_ingestion.sql').read_text(encoding='utf-8')+'\nCOMMIT;')
                if version<3:
                    db.executescript('BEGIN IMMEDIATE;\n'+MIGRATION.with_name('003_ocr.sql').read_text(encoding='utf-8')+'\nCOMMIT;')
                if version<4:
                    db.executescript('BEGIN IMMEDIATE;\n'+MIGRATION.with_name('004_extraction.sql').read_text(encoding='utf-8')+'\nCOMMIT;')
                if version<5:
                    db.executescript('BEGIN IMMEDIATE;\n'+MIGRATION.with_name('005_quality.sql').read_text(encoding='utf-8')+'\nCOMMIT;')
                if version<6:
                    db.executescript('BEGIN IMMEDIATE;\n'+MIGRATION.with_name('006_review.sql').read_text(encoding='utf-8')+'\nCOMMIT;')
                if version<7:
                    db.executescript('BEGIN IMMEDIATE;\n'+MIGRATION.with_name('007_planning.sql').read_text(encoding='utf-8')+'\nCOMMIT;')
                if version<8:
                    db.executescript('BEGIN IMMEDIATE;\n'+MIGRATION.with_name('008_rules.sql').read_text(encoding='utf-8')+'\nCOMMIT;')
                if version<9:
                    db.executescript('BEGIN IMMEDIATE;\n'+MIGRATION.with_name('009_evaluations.sql').read_text(encoding='utf-8')+'\nCOMMIT;')
                return
            if app_id or version:
                raise ValueError('unrecognized database header')
            db.executescript('BEGIN IMMEDIATE;\n' + MIGRATION.read_text(encoding='utf-8') + '\nCOMMIT;')
            db.executescript('BEGIN IMMEDIATE;\n'+MIGRATION.with_name('002_ingestion.sql').read_text(encoding='utf-8')+'\nCOMMIT;')
            db.executescript('BEGIN IMMEDIATE;\n'+MIGRATION.with_name('003_ocr.sql').read_text(encoding='utf-8')+'\nCOMMIT;')
            db.executescript('BEGIN IMMEDIATE;\n'+MIGRATION.with_name('004_extraction.sql').read_text(encoding='utf-8')+'\nCOMMIT;')
            db.executescript('BEGIN IMMEDIATE;\n'+MIGRATION.with_name('005_quality.sql').read_text(encoding='utf-8')+'\nCOMMIT;')
            db.executescript('BEGIN IMMEDIATE;\n'+MIGRATION.with_name('006_review.sql').read_text(encoding='utf-8')+'\nCOMMIT;')
            db.executescript('BEGIN IMMEDIATE;\n'+MIGRATION.with_name('007_planning.sql').read_text(encoding='utf-8')+'\nCOMMIT;')
            db.executescript('BEGIN IMMEDIATE;\n'+MIGRATION.with_name('008_rules.sql').read_text(encoding='utf-8')+'\nCOMMIT;')
            db.executescript('BEGIN IMMEDIATE;\n'+MIGRATION.with_name('009_evaluations.sql').read_text(encoding='utf-8')+'\nCOMMIT;')

    @staticmethod
    def _audit(db, ctx, tenant, taxpayer, event_type, sha, record=None, reason='foundation write'):
        event = AuditEvent(config_version='foundation-v1', creator='repository', stage='persistence',
                           event_id='event-' + uuid4().hex, tenant_id=tenant, taxpayer_id=taxpayer,
                           actor_id=ctx.actor_id, record_id=record.record_id if record else None,
                           record_revision=record.revision if record else None,
                           event_type=event_type, input_sha256=sha, reason=reason)
        db.execute('INSERT INTO events VALUES(?,?,?,?)', (tenant, taxpayer, event.event_id, event.model_dump_json()))

    def add_taxpayer(self, ctx: AccessContext, master: TaxpayerMaster):
        master = TaxpayerMaster.model_validate_json(master.model_dump_json())
        ctx.require(master.tenant_id, master.taxpayer_id, 'ADMIN')
        with self.connection() as db:
            db.execute('INSERT INTO taxpayer_masters VALUES(?,?,?,?)',
                       (master.tenant_id, master.taxpayer_id, master.revision, master.model_dump_json()))
            self._audit(db, ctx, master.tenant_id, master.taxpayer_id, 'TAXPAYER_STORED',
                        digest(master.model_dump_json().encode()))

    def taxpayer(self, ctx, taxpayer_id, revision):
        ctx.require(ctx.tenant_id, taxpayer_id)
        with self.connection() as db:
            row = db.execute('SELECT payload FROM taxpayer_masters WHERE tenant_id=? AND taxpayer_id=? AND revision=?',
                             (ctx.tenant_id, taxpayer_id, revision)).fetchone()
        if row is None:
            raise KeyError('taxpayer revision not found')
        return TaxpayerMaster.model_validate_json(row[0])

    def store_source(self, ctx: AccessContext, envelope: SourceEnvelope, raw: bytes):
        envelope = SourceEnvelope.model_validate_json(envelope.model_dump_json())
        ctx.require(envelope.tenant_id, envelope.taxpayer_id, 'WRITE')
        if not isinstance(raw, bytes) or len(raw) != envelope.size_bytes or digest(raw) != envelope.sha256:
            raise ValueError('source size/hash mismatch')
        if len(raw) > self.settings.max_upload_bytes:
            raise ValueError('source exceeds configured bound')
        with self.connection() as db:
            db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?)',
                       (envelope.tenant_id, envelope.taxpayer_id, envelope.source_id,
                        envelope.taxpayer_master_revision, envelope.sha256, raw, envelope.model_dump_json()))
            self._audit(db, ctx, envelope.tenant_id, envelope.taxpayer_id, 'SOURCE_STORED', envelope.sha256)

    def source(self, ctx, taxpayer_id, source_id):
        ctx.require(ctx.tenant_id, taxpayer_id)
        with self.connection() as db:
            row = db.execute('SELECT envelope,raw FROM sources WHERE tenant_id=? AND taxpayer_id=? AND source_id=?',
                             (ctx.tenant_id, taxpayer_id, source_id)).fetchone()
        if row is None:
            raise KeyError('source not found')
        envelope = SourceEnvelope.model_validate_json(row[0])
        if digest(row[1]) != envelope.sha256:
            raise ValueError('source integrity failure')
        return envelope, row[1]

    def create_record(self, ctx: AccessContext, record: CanonicalFinancialRecord):
        # Validate even model_copy/model_construct instances at the trust boundary.
        record = CanonicalFinancialRecord.model_validate_json(record.model_dump_json())
        ctx.require(record.tenant_id, record.taxpayer_id, 'WRITE')
        if record.revision != 1:
            raise ValueError('new records start at revision 1')
        with self.connection() as db:
            source = db.execute('SELECT master_revision,envelope FROM sources WHERE tenant_id=? AND taxpayer_id=? AND source_id=?',
                                (record.tenant_id, record.taxpayer_id, record.source_id)).fetchone()
            if source is None or source[0] != record.taxpayer_master_revision:
                raise ValueError('source/master revision mismatch')
            if SourceEnvelope.model_validate_json(source[1]).detected_format != record.source_format:
                raise ValueError('source format mismatch')
            db.execute('INSERT INTO records VALUES(?,?,?,?,?)',
                       (record.tenant_id, record.taxpayer_id, record.record_id, record.source_id, 1))
            self._insert_revision(db, record)
            self._audit(db, ctx, record.tenant_id, record.taxpayer_id, 'RECORD_CREATED',
                        digest(record.model_dump_json().encode()), record)

    @staticmethod
    def _insert_revision(db, record):
        payload = record.model_dump_json()
        db.execute('INSERT INTO revisions VALUES(?,?,?,?,?,?)',
                   (record.tenant_id, record.taxpayer_id, record.record_id, record.revision,
                    payload, digest(payload.encode())))

    def record(self, ctx: AccessContext, taxpayer_id: str, record_id: str, revision: int | None = None):
        ctx.require(ctx.tenant_id, taxpayer_id)
        with self.connection() as db:
            if revision is None:
                row = db.execute('SELECT head FROM records WHERE tenant_id=? AND taxpayer_id=? AND record_id=?',
                                 (ctx.tenant_id, taxpayer_id, record_id)).fetchone()
                if row is None:
                    raise KeyError('record not found')
                revision = row[0]
            row = db.execute('SELECT payload,sha256 FROM revisions WHERE tenant_id=? AND taxpayer_id=? AND record_id=? AND revision=?',
                             (ctx.tenant_id, taxpayer_id, record_id, revision)).fetchone()
        if row is None:
            raise KeyError('record revision not found')
        if digest(row[0].encode()) != row[1]:
            raise ValueError('revision integrity failure')
        return CanonicalFinancialRecord.model_validate_json(row[0])

    def append_revision(self, ctx: AccessContext, record: CanonicalFinancialRecord,
                        expected_revision: int, reason: str):
        record = CanonicalFinancialRecord.model_validate_json(record.model_dump_json())
        ctx.require(record.tenant_id, record.taxpayer_id, 'WRITE')
        if not reason.strip() or type(expected_revision) is not int or expected_revision < 1:
            raise ValueError('expected revision and reason required')
        if record.revision != expected_revision + 1:
            raise ValueError('revision must increment exactly once')
        key = (record.tenant_id, record.taxpayer_id, record.record_id)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT r.head,v.payload FROM records r JOIN revisions v '
                             'ON r.tenant_id=v.tenant_id AND r.taxpayer_id=v.taxpayer_id AND r.record_id=v.record_id AND r.head=v.revision '
                             'WHERE r.tenant_id=? AND r.taxpayer_id=? AND r.record_id=?', key).fetchone()
            if row is None or row[0] != expected_revision:
                raise RevisionConflict('record changed or unavailable')
            previous = CanonicalFinancialRecord.model_validate_json(row[1])
            for name in ('source_id', 'document_id', 'source_format', 'record_type', 'taxpayer_master_revision'):
                if getattr(previous, name) != getattr(record, name):
                    raise ValueError(f'immutable revision identity: {name}')
            if {i.item_id for i in previous.items} != {i.item_id for i in record.items}:
                raise ValueError('foundation revision cannot change item identity set')
            db.execute('UPDATE records SET head=? WHERE tenant_id=? AND taxpayer_id=? AND record_id=? AND head=?',
                       (record.revision, *key, expected_revision))
            self._insert_revision(db, record)
            self._audit(db, ctx, record.tenant_id, record.taxpayer_id, 'RECORD_REVISED',
                        digest(record.model_dump_json().encode()), record, reason)

    def events(self, ctx, taxpayer_id):
        ctx.require(ctx.tenant_id, taxpayer_id)
        with self.connection() as db:
            rows = db.execute('SELECT payload FROM events WHERE tenant_id=? AND taxpayer_id=? ORDER BY rowid',
                              (ctx.tenant_id, taxpayer_id)).fetchall()
        return tuple(AuditEvent.model_validate_json(row[0]) for row in rows)

    def add_artifact(self, ctx: AccessContext, artifact: Artifact):
        artifact = Artifact.model_validate_json(artifact.model_dump_json())
        ctx.require(artifact.tenant_id, artifact.taxpayer_id, 'WRITE')
        with self.connection() as db:
            row = db.execute('SELECT sha256 FROM revisions WHERE tenant_id=? AND taxpayer_id=? AND record_id=? AND revision=?',
                             (artifact.tenant_id, artifact.taxpayer_id, artifact.record_id, artifact.record_revision)).fetchone()
            if row is None or row[0] != artifact.input_sha256:
                raise ValueError('artifact input revision hash mismatch')
            db.execute('INSERT INTO artifacts VALUES(?,?,?,?,?,?)',
                       (artifact.tenant_id, artifact.taxpayer_id, artifact.artifact_id,
                        artifact.record_id, artifact.record_revision, artifact.model_dump_json()))
            self._audit(db, ctx, artifact.tenant_id, artifact.taxpayer_id, 'ARTIFACT_STORED', artifact.input_sha256)

    def artifact(self, ctx, taxpayer_id, artifact_id):
        ctx.require(ctx.tenant_id, taxpayer_id)
        with self.connection() as db:
            row = db.execute('SELECT payload FROM artifacts WHERE tenant_id=? AND taxpayer_id=? AND artifact_id=?',
                             (ctx.tenant_id, taxpayer_id, artifact_id)).fetchone()
        if row is None:
            raise KeyError('artifact not found')
        return Artifact.model_validate_json(row[0])

    def add_job(self, ctx: AccessContext, job: Job):
        job = Job.model_validate_json(job.model_dump_json())
        ctx.require(job.tenant_id, job.taxpayer_id, 'WRITE')
        with self.connection() as db:
            row = db.execute('SELECT sha256 FROM sources WHERE tenant_id=? AND taxpayer_id=? AND source_id=?',
                             (job.tenant_id, job.taxpayer_id, job.source_id)).fetchone()
            if row is None or row[0] != job.input_sha256:
                raise ValueError('job input source hash mismatch')
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',
                       (job.tenant_id, job.taxpayer_id, job.job_id, job.source_id, job.model_dump_json()))
            self._audit(db, ctx, job.tenant_id, job.taxpayer_id, 'JOB_CREATED', job.input_sha256)

    def job(self, ctx, taxpayer_id, job_id):
        ctx.require(ctx.tenant_id, taxpayer_id)
        with self.connection() as db:
            row = db.execute('SELECT payload FROM jobs WHERE tenant_id=? AND taxpayer_id=? AND job_id=?',
                             (ctx.tenant_id, taxpayer_id, job_id)).fetchone()
        if row is None:
            raise KeyError('job not found')
        return Job.model_validate_json(row[0])
