"""Enterprise-only verification of explicit labels, independent of review feedback."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import os
import re
import sqlite3

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from finance_input.json_io import loads
from .import_files import canonical, digest, fail
from .snapshots import SnapshotStore

VERSION = 'enterprise-label-packet/1.0.0'
TARGET = 'verified-fraud/1.0.0'
OUTCOMES = (None, 'verified_fraud', 'verified_non_fraud')
APP_ID = 1279414321


def checked(ok, code, message, action='Tải lại danh sách và kiểm tra phiên bản trước khi thử lại.', status=409):
    if not ok:
        fail(status, code, message, action)


def source_packet(snapshots, scope, request, recheck=None):
    """Use the same immutable selection and cutoff as the HE training adapter.

    Predictors are never displayed as evidence of fraud. Missing predictors do
    not preclude human verification, but remain ineligible for this HE circuit.
    """
    from experiments.he_training.snapshot_adapter import prepare_snapshot_training
    from .rule_snapshot_features import build_from_rule_snapshot, SOURCE_CONTRACT
    from .snapshot_features import build_from_snapshot
    plan = prepare_snapshot_training(snapshots, scope, request, recheck)
    checked(all('event_at' in r for r in plan['rows']), 'LABEL_SOURCE_UNAVAILABLE',
            'Có giao dịch chưa được biết tại thời điểm đã chọn.', status=422)
    checked(type(plan['simulated']) is bool, 'LABEL_SOURCE_MODE',
            'Chưa xác định được nguồn thật hay mô phỏng; không trộn hai loại nguồn.', status=422)
    sid = request['snapshot_id']
    raw = loads(snapshots.get_snapshot(scope, sid, recheck, data=True))
    native = plan['snapshot']['contract_version'] == SOURCE_CONTRACT
    frame = (build_from_rule_snapshot(snapshots, scope, sid, request['as_of'], recheck,
                candidates_only=False, require_exact_source_cutoff=False) if native else
             build_from_snapshot(snapshots, scope, sid, request['as_of'], recheck))
    tables = raw['source']['tables'] if native else raw
    by_hash = {digest(canonical(r)): (table, r) for table, rows in tables.items()
               if isinstance(rows, list) for r in rows}
    by_ref = {(t, r.get('record_id'), r.get('revision')): r for t, rows in tables.items()
              if isinstance(rows, list) for r in rows}
    index = {(r['record_id'], r['revision']): (r, e) for r, e in zip(frame['rows'], frame['evidence'])}
    cases = []
    for wanted in request['rows']:
        meta, evidence = index[wanted['record_id'], wanted['revision']]
        items = []
        for ref in evidence['records']:
            native_item = by_hash.get(ref.get('source_sha256'), (None, None))
            record = (native_item[1] if native_item[0] == ref['table'] else None) if native else by_ref.get((ref['table'], ref['record_id'], ref['revision']))
            checked(record is not None and record['company_id'] == plan['company_id'],
                    'LABEL_EVIDENCE_BINDING', 'Căn cứ không khớp snapshot.', status=503)
            items.append(dict(evidence_id='lev_' + digest(canonical(dict(table=ref['table'], record=record))),
                              table=ref['table'], record=record, simulated=plan['simulated'] if native else record['source']['is_simulated'],
                              original_verified=False))
        cases.append(dict(**wanted, event_at=meta['event_at'], knowledge_at=meta['as_of'],
                          evidence=items, missing_sources=evidence['missing_reasons']))
    binding = dict(snapshot=plan['snapshot'], source_plan_sha256=plan['plan_sha256'],
                   mapping_fingerprint=plan['mapping']['fingerprint'], request=request,
                   simulated=plan['simulated'], feature_status=plan['status'])
    return dict(version=VERSION, target=TARGET, tenant_id=scope.tenant_id,
                company_id=next(iter(scope.company_ids)), binding=binding, cases=cases)


class LabelStore:
    """Append-only AEAD revisions; company sharing, optimistic writes and retries."""
    @classmethod
    def from_state_key(cls,path,key_file):
        """Open the same protected store as Portal, without opening its job DB."""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from experiments.he_inference.key_manager import load_key,PROVIDER
        material=load_key(key_file,required_provider=PROVIDER).material
        keys=HKDF(algorithm=hashes.SHA256(),length=64,salt=b'he-node-jobs-v1',info=b'enterprise-storage-and-idempotency').derive(material)
        key=HKDF(algorithm=hashes.SHA256(),length=32,salt=b'agent2-labels-v1',info=b'enterprise-verified-labels').derive(keys[32:])
        return cls(path,key)

    def __init__(self, path, key, clock=None):
        if not isinstance(key, bytes) or len(key) != 32:
            raise ValueError('32-byte enterprise label key required')
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.aes = AESGCM(key)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        with self.transaction() as conn:
            app = conn.execute('PRAGMA application_id').fetchone()[0]
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if not tables and app == 0:
                conn.execute(f'PRAGMA application_id={APP_ID}')
                conn.execute('CREATE TABLE meta (nonce BLOB, payload BLOB)')
                nonce = os.urandom(12)
                conn.execute('INSERT INTO meta VALUES (?,?)', (nonce, self.aes.encrypt(nonce, VERSION.encode(), b'label-key-check')))
                conn.execute('CREATE TABLE packets (owner TEXT, id TEXT, revision INTEGER, nonce BLOB, payload BLOB, PRIMARY KEY(owner,id,revision))')
                conn.execute('CREATE TABLE receipts (owner TEXT, id TEXT, request_id TEXT, request_hash TEXT, revision INTEGER, PRIMARY KEY(owner,id,request_id))')
            elif app != APP_ID:
                raise ValueError('foreign label database')
            row = conn.execute('SELECT * FROM meta').fetchone()
            if not row or self.aes.decrypt(row['nonce'], row['payload'], b'label-key-check') != VERSION.encode():
                raise ValueError('label database key/version mismatch')
            for table in ('packets', 'receipts', 'meta'):
                for op in ('UPDATE', 'DELETE'):
                    conn.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_{op.lower()} BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT,'append-only labels'); END")

    @contextmanager
    def transaction(self):
        conn = sqlite3.connect(self.path, timeout=20, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA synchronous=FULL')
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def owner(scope):
        tenant, company, _ = SnapshotStore._scope(scope)
        return digest(canonical([tenant, company]))

    @staticmethod
    def guard(scope, recheck=None, write=False):
        SnapshotStore._scope(scope)
        checked(not write or 'evidence.verify' in scope.permissions, 'LABEL_VERIFICATION_DENIED',
                'Bạn chưa có quyền xác minh nhãn tại doanh nghiệp.', 'Nhờ quản lý cấp quyền evidence.verify đúng doanh nghiệp.', 403)
        checked(recheck is None or recheck() == scope, 'AUTH_CONTEXT_CHANGED', 'Quyền đã thay đổi.', status=403)

    def _open(self, row):
        try:
            return loads(self.aes.decrypt(row['nonce'], row['payload'], canonical([VERSION, row['owner'], row['id'], row['revision']])))
        except (InvalidTag, ValueError):
            fail(503, 'LABEL_STORAGE_INTEGRITY', 'Kho nhãn không khớp khóa hoặc đã bị thay đổi.', 'Kiểm tra bản sao lưu và khóa tại doanh nghiệp.')

    def _read(self, conn, owner, pid, revision=None):
        row = conn.execute('SELECT * FROM packets WHERE owner=? AND id=?' +
            (' AND revision=?' if revision is not None else ' ORDER BY revision DESC LIMIT 1'),
            (owner, pid, revision) if revision is not None else (owner, pid)).fetchone()
        checked(row is not None, 'LABEL_PACKET_NOT_FOUND', 'Không tìm thấy bộ nhãn trong doanh nghiệp này.', status=404)
        return self._open(row)

    def _put(self, conn, owner, value):
        nonce = os.urandom(12)
        conn.execute('INSERT INTO packets VALUES (?,?,?,?,?)', (owner, value['packet_id'], value['revision'], nonce,
            self.aes.encrypt(nonce, canonical(value), canonical([VERSION, owner, value['packet_id'], value['revision']]))))

    def create(self, scope, source, recheck=None):
        self.guard(scope, recheck, write=True)
        checked(source['tenant_id'] == scope.tenant_id and source['company_id'] == next(iter(scope.company_ids)),
                'LABEL_SOURCE_SCOPE', 'Nguồn không thuộc doanh nghiệp này.', status=403)
        pid = 'lbl_' + digest(canonical(source))
        owner = self.owner(scope)
        with self.transaction() as conn:
            row = conn.execute('SELECT 1 FROM packets WHERE owner=? AND id=?', (owner, pid)).fetchone()
            if row:
                value = self._read(conn, owner, pid)
            else:
                value = dict(source, packet_id=pid, revision=1, locked=False, lock_sha256=None,
                    labels=[dict(record_id=c['record_id'], revision=c['revision'], outcome=None,
                                 explanation='', evidence_ids=[], verified_by=None, verified_at=None) for c in source['cases']],
                    history=[dict(action='create', actor_id=scope.actor_id, at=self.clock().isoformat())])
                self._put(conn, owner, value)
            self.guard(scope, recheck, write=True)
            return value

    def list(self, scope, recheck=None):
        self.guard(scope, recheck)
        with self.transaction() as conn:
            rows = conn.execute('SELECT p.* FROM packets p JOIN (SELECT id,MAX(revision) rev FROM packets WHERE owner=? GROUP BY id) n ON p.id=n.id AND p.revision=n.rev WHERE p.owner=? ORDER BY p.rowid DESC', (self.owner(scope), self.owner(scope))).fetchall()
            values = [self._open(r) for r in rows]
            self.guard(scope, recheck)
            return [dict(packet_id=v['packet_id'], revision=v['revision'], locked=v['locked'],
                         snapshot_id=v['binding']['snapshot']['snapshot_id'], labelled=sum(r['outcome'] is not None for r in v['labels']),
                         row_count=len(v['labels']), simulated=v['binding']['simulated']) for v in values]

    def get(self, scope, pid, recheck=None, revision=None):
        self.guard(scope, recheck)
        with self.transaction() as conn:
            value = self._read(conn, self.owner(scope), pid, revision)
            self.guard(scope, recheck)
            return value

    def change(self, scope, pid, action, body, recheck=None):
        self.guard(scope, recheck, write=True)
        keys = {'expected_revision', 'request_id'} | ({'label'} if action == 'save' else set())
        checked(isinstance(body, dict) and set(body) == keys and type(body['expected_revision']) is int and
                isinstance(body['request_id'], str) and re.fullmatch(r'[A-Za-z0-9_-]{16,100}', body['request_id']),
                'LABEL_REQUEST', 'Yêu cầu chưa đúng định dạng.', status=400)
        checked(action in ('save', 'lock', 'reopen'), 'LABEL_ACTION', 'Thao tác không hợp lệ.', status=400)
        owner = self.owner(scope)
        request_hash = digest(canonical(dict(actor=scope.actor_id, action=action, body=body)))
        with self.transaction() as conn:
            receipt = conn.execute('SELECT * FROM receipts WHERE owner=? AND id=? AND request_id=?', (owner, pid, body['request_id'])).fetchone()
            if receipt:
                checked(receipt['request_hash'] == request_hash, 'LABEL_RETRY_CONFLICT', 'Mã gửi lại đã được dùng cho nội dung khác.')
                value = self._read(conn, owner, pid, receipt['revision'])
                self.guard(scope, recheck, write=True)
                return value
            old = self._read(conn, owner, pid)
            checked(old['revision'] == body['expected_revision'], 'LABEL_REVISION_CONFLICT', 'Có người đã sửa bộ nhãn. Nhãn của bạn chưa được ghi đè lên bản mới.')
            checked(old['locked'] if action == 'reopen' else not old['locked'], 'LABEL_LOCKED', 'Bộ nhãn đã khóa; mở phiên bản mới để sửa.')
            value = deepcopy(old)
            event = dict(action=action, actor_id=scope.actor_id, at=self.clock().isoformat())
            if action == 'save':
                label = body['label']
                checked(isinstance(label, dict) and set(label) == {'record_id', 'revision', 'outcome', 'explanation', 'evidence_ids', 'documents_checked'}, 'LABEL_FIELDS', 'Thông tin nhãn chưa đúng định dạng.', status=400)
                idx = next((i for i, r in enumerate(value['labels']) if (r['record_id'], r['revision']) == (label['record_id'], label['revision'])), None)
                checked(idx is not None and type(label['revision']) is int, 'LABEL_ROW_BINDING', 'Giao dịch/phiên bản không thuộc bộ nhãn.', status=422)
                checked(label['outcome'] in OUTCOMES and isinstance(label['explanation'], str) and len(label['explanation']) <= 2000 and type(label['documents_checked']) is bool,
                        'LABEL_OUTCOME', 'Chỉ chọn gian lận/không gian lận đã xác minh hoặc để trống.', status=422)
                refs = label['evidence_ids']
                allowed = {e['evidence_id'] for e in value['cases'][idx]['evidence']}
                checked(isinstance(refs, list) and all(isinstance(r, str) for r in refs) and len(refs) == len(set(refs)) and set(refs) <= allowed,
                        'LABEL_EVIDENCE_BINDING', 'Chỉ được dùng căn cứ đã khóa trong giao dịch này.', status=422)
                checked(label['outcome'] is None or value['binding']['simulated'] or not any(e['simulated'] for e in value['cases'][idx]['evidence'] if e['evidence_id'] in refs),
                        'LABEL_SIMULATED_EVIDENCE', 'Căn cứ mô phỏng không dùng để xác nhận nhãn gian lận thực tế.', 'Đối chiếu nguồn thật; thiếu căn cứ thì để nhãn trống.', 422)
                checked(label['outcome'] is None or (len(label['explanation'].strip()) >= 10 and refs and label['documents_checked']),
                        'LABEL_EVIDENCE_REQUIRED', 'Cần giải thích, chọn căn cứ và xác nhận đã đối chiếu chứng từ; chưa rõ thì để trống.', status=422)
                event.update(record_id=label['record_id'], record_revision=label['revision'], previous_outcome=value['labels'][idx]['outcome'], outcome=label['outcome'])
                value['labels'][idx] = {k: label[k] for k in ('record_id', 'revision', 'outcome', 'explanation', 'evidence_ids')}
                value['labels'][idx].update(verified_by=scope.actor_id if label['outcome'] is not None else None,
                                          verified_at=event['at'] if label['outcome'] is not None else None)
            value.update(revision=old['revision'] + 1, locked=action == 'lock', lock_sha256=None)
            value['history'].append(event)
            if value['locked']:
                value['lock_sha256'] = digest(canonical(value))
            self.guard(scope, recheck, write=True)
            self._put(conn, owner, value)
            conn.execute('INSERT INTO receipts VALUES (?,?,?,?,?)', (owner, pid, body['request_id'], request_hash, value['revision']))
            self.guard(scope, recheck, write=True)
            return value

    def export(self, scope, pid, revision, lock_sha256, recheck=None):
        """An exact locked revision; null labels stay null and cannot train."""
        value = self.get(scope, pid, recheck, revision=revision)
        checked(value['locked'] and value['lock_sha256'] == lock_sha256, 'LABEL_LOCK_MISMATCH', 'Không khớp phiên bản bộ nhãn đã khóa.')
        hashed = deepcopy(value)
        hashed['lock_sha256'] = None
        checked(digest(canonical(hashed)) == lock_sha256, 'LABEL_LOCK_INTEGRITY', 'Checksum bộ nhãn không khớp.', status=503)
        labelled = [r for r in value['labels'] if r['outcome'] is not None]
        return dict(version=VERSION, target=TARGET, packet_id=pid, revision=revision, lock_sha256=lock_sha256,
                    binding=value['binding'], labels=value['labels'], tenant_id=value['tenant_id'], company_id=value['company_id'],
                    verification_mode='synthetic_expected' if value['binding']['simulated'] else 'human_verified',
                    training_ready=len(labelled) == len(value['labels']) and {r['outcome'] for r in labelled} == set(OUTCOMES[1:]) and value['binding']['feature_status'] == 'ready',
                    identity_assurance='authenticated_principal; individual_identity_not_attested', training_started=False)
