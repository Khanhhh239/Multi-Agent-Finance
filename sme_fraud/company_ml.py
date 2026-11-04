"""Versioned, company-scoped ML workspace; detection snapshots remain read-only."""
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
import platform
import threading
import time
import uuid

import joblib
import numpy as np
import sklearn

from .feature_contract import digest, sha, validate_cache
from .ml_estimators import CompanyEstimator, ALGORITHMS, catalog
from .review_roles import require_permission
from .shadow_scoring import guarded, instant, selected_matrix, source_checks

VERSION = 'company-ml-v1'


def runtime(algorithm=None):
    from pathlib import Path
    result = dict(python=platform.python_version(), numpy=np.__version__, sklearn=sklearn.__version__, joblib=joblib.__version__,
                  implementation=sha(Path(__file__).with_name('ml_estimators.py')))
    if algorithm == 'catboost':
        try:
            import catboost
            result['catboost'] = catboost.__version__
        except ImportError:
            result['catboost'] = 'not_installed'
    return result


def dump(value):
    stream = io.BytesIO(); np.save(stream, value, allow_pickle=False)
    return stream.getvalue()


def load(value):
    return np.load(io.BytesIO(value), allow_pickle=False)


def labels_csv(text, company, records, now):
    if not isinstance(text, str) or len(text.encode('utf-8')) > 1_500_000:
        raise ValueError('Tệp nhãn quá lớn hoặc không hợp lệ.')
    if not text.strip():
        return {}
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    fields = {'company_id', 'transaction_id', 'label', 'reviewer_id', 'reviewed_at', 'evidence_ref', 'verified'}
    if set(reader.fieldnames or []) != fields:
        raise ValueError('CSV nhãn cần company_id, transaction_id, label, reviewer_id, reviewed_at, evidence_ref, verified.')
    transactions = {r['transaction_id']: r for r in records}
    result = {}
    for row in reader:
        tid = row.get('transaction_id')
        if (row.get('company_id') != company or tid not in transactions or tid in result
            or row.get('label') not in {'0', '1'} or row.get('verified') != '1'
            or not row.get('reviewer_id', '').strip() or not row.get('evidence_ref', '').strip()):
            raise ValueError('Nhãn cần đúng công ty/giao dịch, không trùng và có người rà, căn cứ, xác nhận.')
        reviewed = instant(row['reviewed_at'])
        if reviewed < instant(transactions[tid]['posted_at']) or reviewed > now:
            raise ValueError('Thời điểm rà nhãn không hợp lệ.')
        result[tid] = dict(label=int(row['label']), reviewed_at=row['reviewed_at'],
                           reviewer_id=row['reviewer_id'], evidence_ref=row['evidence_ref'])
    return result


class CompanyML:
    def __init__(self, store):
        self.store = store
        self.training_lock = threading.Lock()
        with store.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS company_ml_data(
                    company_id TEXT PRIMARY KEY, revision TEXT, metadata TEXT, records TEXT, matrix BLOB, labels TEXT);
                CREATE TABLE IF NOT EXISTS company_ml_versions(
                    version_id TEXT PRIMARY KEY, company_id TEXT, number INTEGER, metadata TEXT, artifact BLOB,
                    UNIQUE(company_id,number));
                CREATE TABLE IF NOT EXISTS company_ml_bindings(company_id TEXT PRIMARY KEY, version_id TEXT);
                CREATE TABLE IF NOT EXISTS company_ml_events(
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, company_id TEXT, data TEXT);
                CREATE TABLE IF NOT EXISTS company_ml_runs(
                    run_id TEXT PRIMARY KEY, company_id TEXT, metadata TEXT, scores TEXT);
            ''')

    def _company(self, scenario, company, principal, write=False):
        if scenario == '005':
            raise ValueError('Không sử dụng holdout 005 trong cấu hình ML.')
        self.store.report(scenario)
        if not isinstance(company, str) or not company or len(company) > 100:
            raise ValueError('Chọn doanh nghiệp cần cấu hình.')
        if write:
            require_permission(principal, 'ml_manage', company)
        elif principal is None or company not in principal.company_ids:
            raise PermissionError('Đăng nhập bằng tài khoản thuộc doanh nghiệp để xem cấu hình ML.')
        with self.store.connection() as db:
            if not db.execute('SELECT 1 FROM companies WHERE scenario=? AND company_id=?', (scenario, company)).fetchone():
                raise KeyError('Không tìm thấy doanh nghiệp trong bộ dữ liệu.')

    @staticmethod
    def _active(db, company):
        row = db.execute('SELECT version_id FROM company_ml_bindings WHERE company_id=?', (company,)).fetchone()
        return row[0] if row else None

    @staticmethod
    def _events(db, company):
        previous = ''; result = []
        for row in db.execute('SELECT data FROM company_ml_events WHERE company_id=? ORDER BY sequence', (company,)):
            value = json.loads(row[0]); checksum = value.pop('event_hash')
            if value['previous_hash'] != previous or digest(value) != checksum:
                raise ValueError('Lịch sử cấu hình ML không còn khớp.')
            value['event_hash'] = checksum; result.append(value); previous = checksum
        return result

    def _event(self, db, company, principal, action, **details):
        events = self._events(db, company)
        value = dict(action=action, company_id=company, actor=principal.user_id,
                     at=self.store.clock().isoformat(), details=details,
                     previous_hash=events[-1]['event_hash'] if events else '')
        value['event_hash'] = digest(value)
        db.execute('INSERT INTO company_ml_events(company_id,data) VALUES(?,?)', (company, json.dumps(value)))

    def _data(self, db, company):
        row = db.execute('SELECT * FROM company_ml_data WHERE company_id=?', (company,)).fetchone()
        if not row:
            raise ValueError('Cập nhật và kiểm tra dữ liệu trước khi chọn ML.')
        records, x, labels = json.loads(row['records']), load(row['matrix']), json.loads(row['labels'])
        meta = json.loads(row['metadata'])
        if digest([meta, records, hashlib.sha256(row['matrix']).hexdigest(), labels]) != row['revision']:
            raise ValueError('Dữ liệu ML đã thay đổi ngoài luồng cập nhật.')
        return row['revision'], meta, records, x, labels

    def overview(self, principal, scenario=None):
        scenario = scenario or self.store.metadata()['default_scenario']
        if scenario == '005':
            raise ValueError('Không sử dụng holdout 005 trong cấu hình ML.')
        self.store.report(scenario)
        with self.store.connection() as db:
            companies = [json.loads(r[0]) for r in db.execute('SELECT data FROM companies WHERE scenario=? ORDER BY company_id', (scenario,))]
        return dict(algorithms=catalog(), companies=[r for r in companies if principal and r['company_id'] in principal.company_ids],
                    can_manage=bool(principal and principal.role in {'chief_accountant', 'director'}), mode='shadow',
                    source='connected_attested_feature_cache')

    def status(self, scenario, company, principal):
        self._company(scenario, company, principal)
        with self.store.connection() as db:
            row = db.execute('SELECT revision,metadata FROM company_ml_data WHERE company_id=?', (company,)).fetchone()
            versions = [json.loads(r[0]) for r in db.execute(
                'SELECT metadata FROM company_ml_versions WHERE company_id=? ORDER BY number DESC', (company,))]
            active = self._active(db, company)
            events = self._events(db, company)
            runs = [json.loads(r[0]) for r in db.execute(
                'SELECT metadata FROM company_ml_runs WHERE company_id=? ORDER BY rowid DESC LIMIT 10', (company,))]
        return dict(company_id=company, data=None if not row else json.loads(row['metadata']) | dict(revision=row['revision']),
                    active_version=active, versions=versions, history=events, runs=runs, mode='shadow')

    def update_data(self, scenario, company, principal, *, expected_revision, labels_text=''):
        self._company(scenario, company, principal, True)
        dataset = guarded(self.store.data_root / ('sme_fraud_' + scenario))
        if not (dataset/'manifest.json').is_file() or not (dataset/'features.csv').is_file():
            raise ValueError('Nguồn kết nối cần manifest và features.csv đúng hợp đồng trước khi cập nhật ML.')
        manifest_hash = sha(dataset/'manifest.json')
        metadata = json.loads((dataset/'manifest.json').read_text(encoding='utf-8-sig'))
        contract = validate_cache(metadata)
        checks = source_checks(dataset, metadata)
        records, x = selected_matrix(dataset, contract['columns'], dict(company_ids=[company]),
                                      datetime.min.replace(tzinfo=timezone.utc), datetime.max.replace(tzinfo=timezone.utc))
        if len(records) > 100_000:
            raise ValueError('Bản web giới hạn 100.000 giao dịch mỗi doanh nghiệp/lần cập nhật.')
        order = sorted(range(len(records)), key=lambda i: (instant(records[i]['posted_at']), records[i]['transaction_id']))
        records = [records[i] for i in order]; x = x[order]
        labels = labels_csv(labels_text, company, records, self.store.clock())
        if not labels_text.strip():
            with self.store.connection() as db:
                previous = db.execute('SELECT 1 FROM company_ml_data WHERE company_id=?', (company,)).fetchone()
                if previous:
                    _, old_meta, old_records, old_x, old_labels = self._data(db, company)
                    by_id = {r['transaction_id']: i for i,r in enumerate(old_records)}
                    if old_meta['feature_fingerprint'] == contract['fingerprint'] and old_meta['scenario'] == scenario:
                        for i, record in enumerate(records):
                            tid = record['transaction_id']; old_i = by_id.get(tid)
                            if (tid in old_labels and old_i is not None and record == old_records[old_i]
                                and np.array_equal(x[i], old_x[old_i])):
                                labels[tid] = old_labels[tid]
        if sha(dataset/'manifest.json') != manifest_hash or source_checks(dataset, metadata) != checks:
            raise RuntimeError('Nguồn đổi trong lúc đọc; hãy cập nhật lại dữ liệu.')
        times = sorted({r['posted_at'] for r in records}, key=instant)
        defaults = None
        if len(times) >= 7:
            defaults = dict(train_end=times[min(len(times)-3, max(2, int(len(times)*.6)))],
                            calibration_end=times[min(len(times)-2, max(3, int(len(times)*.8)))])
        blob = dump(x)
        meta = dict(company_id=company, scenario=scenario, rows=len(records), columns=contract['columns'],
            feature_fingerprint=contract['fingerprint'], dataset_version=metadata.get('version'),
            manifest_sha256=manifest_hash, labels_count=len(labels), first_at=records[0]['posted_at'],
            last_at=records[-1]['posted_at'], suggested_windows=defaults)
        revision = digest([meta, records, hashlib.sha256(blob).hexdigest(), labels])
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT revision FROM company_ml_data WHERE company_id=?', (company,)).fetchone()
            if (current[0] if current else None) != expected_revision:
                raise RuntimeError('Dữ liệu ML vừa được cập nhật ở phiên khác. Tải lại trước khi lưu.')
            db.execute('INSERT OR REPLACE INTO company_ml_data VALUES(?,?,?,?,?,?)',
                       (company, revision, json.dumps(meta), json.dumps(records), blob, json.dumps(labels)))
            self._event(db, company, principal, 'data_updated', revision=revision, active_version=self._active(db, company))
        return self.status(scenario, company, principal)

    def evaluate(self, scenario, company, principal, *, expected_revision, algorithm, train_end, calibration_end, alert_budget):
        self._company(scenario, company, principal, True)
        if (algorithm not in ALGORITHMS or type(alert_budget) not in (int, float)
            or not np.isfinite(alert_budget) or not 0 < alert_budget <= .2):
            raise ValueError('Chọn thuật toán và tỷ lệ cảnh báo lớn hơn 0, không quá 20%.')
        if not self.training_lock.acquire(blocking=False):
            raise RuntimeError('Máy chủ đang đánh giá model khác; chờ hoàn tất rồi thử lại.')
        try:
            with self.store.connection() as db:
                revision, data, records, x, labels = self._data(db, company)
            if revision != expected_revision:
                raise RuntimeError('Dữ liệu đã đổi; tải lại trước khi huấn luyện.')
            if data['scenario'] != scenario:
                raise ValueError('Cập nhật dữ liệu cho bộ đang chọn trước khi đánh giá ML.')
            first, second = instant(train_end), instant(calibration_end)
            if not first < second:
                raise ValueError('Cuối kỳ train phải trước cuối kỳ calibration.')
            times = [instant(r['posted_at']) for r in records]
            train = np.asarray([i for i,t in enumerate(times) if t < first], dtype=int)
            cal = np.asarray([i for i,t in enumerate(times) if first <= t < second], dtype=int)
            test = np.asarray([i for i,t in enumerate(times) if t >= second], dtype=int)
            if len(train) < 5 or len(cal) < 2 or len(test) < 2:
                raise ValueError('Cần ít nhất 5 dòng train, 2 calibration và 2 evaluation theo thời gian.')
            if len(train) > 20_000:
                raise ValueError('Lượt huấn luyện trên web giới hạn 20.000 dòng train; chọn lại kỳ train hoặc chạy offline.')
            y = None
            if algorithm == 'catboost':
                if any(records[i]['transaction_id'] not in labels or
                       instant(labels[records[i]['transaction_id']]['reviewed_at']) >= first for i in train):
                    raise ValueError('CatBoost cần nhãn đã xác minh và đã biết trước cuối kỳ train cho mọi dòng train.')
                y = np.asarray([labels[records[i]['transaction_id']]['label'] for i in train])
            started = time.perf_counter()
            estimator = CompanyEstimator(algorithm).fit(x[train], y)
            calibration_scores = estimator.score(x[cal])
            threshold = float(np.quantile(calibration_scores, 1-alert_budget, method='higher'))
            scores = estimator.score(x[test]); predicted = scores > threshold
            elapsed = time.perf_counter() - started
            known = [(j, labels[records[i]['transaction_id']]['label']) for j,i in enumerate(test)
                     if records[i]['transaction_id'] in labels]
            precision = recall = None
            if known:
                tp = sum(bool(predicted[j]) and label == 1 for j,label in known)
                flagged = sum(bool(predicted[j]) for j,_ in known); positives = sum(label for _,label in known)
                precision = tp/flagged if flagged else None; recall = tp/positives if positives else None
            version_id = uuid.uuid4().hex
            artifact = dict(format=VERSION, company_id=company, algorithm=algorithm, estimator=estimator,
                            feature_fingerprint=data['feature_fingerprint'], columns=data['columns'],
                            dataset_version=data['dataset_version'], threshold=threshold, runtime=runtime(algorithm),
                            calibration_end=calibration_end)
            buffer = io.BytesIO(); joblib.dump(artifact, buffer); payload = buffer.getvalue()
            # Reload our own trusted bytes and verify inference before exposing a candidate.
            restored = joblib.load(io.BytesIO(payload))
            if not np.allclose(restored['estimator'].score(x[test]), scores, rtol=1e-10, atol=1e-10):
                raise ValueError('Artifact nạp lại không tái hiện được kết quả; ứng viên chưa được lưu.')
            meta = dict(version_id=version_id, company_id=company, algorithm=algorithm, data_revision=revision,
                created_at=self.store.clock().isoformat(), created_by=principal.user_id, mode='shadow',
                feature_fingerprint=data['feature_fingerprint'], dataset_version=data['dataset_version'],
                runtime=artifact['runtime'], artifact_sha256=hashlib.sha256(payload).hexdigest(), threshold=threshold,
                train_end=train_end, calibration_end=calibration_end, requested_alert_budget=alert_budget,
                train_rows=len(train), calibration_rows=len(cal), evaluation_rows=len(test),
                evaluation_alerts=int(predicted.sum()), evaluation_alert_rate=float(predicted.mean()),
                labelled_evaluation_rows=len(known), precision=precision, recall=recall, seconds=round(elapsed, 3),
                converged=getattr(estimator, 'converged_', True),
                training_ids_sha256=digest([records[i]['transaction_id'] for i in train]))
            with self.store.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                if self._data(db, company)[0] != revision:
                    raise RuntimeError('Nguồn đã cập nhật khi đang train; kết quả chưa được lưu hoặc kích hoạt.')
                meta['number'] = db.execute('SELECT COALESCE(MAX(number),0)+1 FROM company_ml_versions WHERE company_id=?', (company,)).fetchone()[0]
                db.execute('INSERT INTO company_ml_versions VALUES(?,?,?,?,?)',
                           (version_id, company, meta['number'], json.dumps(meta), payload))
                self._event(db, company, principal, 'evaluated', version_id=version_id, data_revision=revision)
            return self.status(scenario, company, principal)
        finally:
            self.training_lock.release()

    def _artifact(self, db, company, version_id, data):
        row = db.execute('SELECT metadata,artifact FROM company_ml_versions WHERE company_id=? AND version_id=?',
                         (company, version_id)).fetchone()
        if not row:
            raise KeyError('Không tìm thấy phiên bản ML của doanh nghiệp.')
        meta = json.loads(row['metadata'])
        if (meta['feature_fingerprint'] != data['feature_fingerprint'] or meta['dataset_version'] != data['dataset_version']):
            raise ValueError('Nguồn mới khác hợp đồng feature/định dạng; cần đánh giá phiên bản ML mới.')
        if meta['runtime'] != runtime(meta['algorithm']) or hashlib.sha256(row['artifact']).hexdigest() != meta['artifact_sha256']:
            raise ValueError('Model hoặc môi trường chạy đã thay đổi; chưa thể sử dụng phiên bản này.')
        artifact = joblib.load(io.BytesIO(row['artifact']))
        if (artifact['format'] != VERSION or artifact['company_id'] != company
            or artifact['algorithm'] != meta['algorithm'] or artifact['estimator'].algorithm != meta['algorithm']
            or artifact['columns'] != data['columns'] or artifact['feature_fingerprint'] != data['feature_fingerprint']
            or artifact['dataset_version'] != data['dataset_version'] or artifact['threshold'] != meta['threshold']
            or artifact['calibration_end'] != meta['calibration_end'] or artifact['runtime'] != meta['runtime']):
            raise ValueError('Artifact ML sai phạm vi hoặc không khớp cấu hình phiên bản.')
        return meta, artifact

    def activate(self, scenario, company, principal, *, version_id, expected_active, expected_revision, rollback=False):
        self._company(scenario, company, principal, True)
        if type(rollback) is not bool:
            raise ValueError('Thao tác quay lại phiên bản không hợp lệ.')
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            revision, data, _, _, _ = self._data(db, company)
            if data['scenario'] != scenario:
                raise ValueError('Cập nhật dữ liệu cho bộ đang chọn trước khi kích hoạt ML.')
            if self._active(db, company) != expected_active or revision != expected_revision:
                raise RuntimeError('Cấu hình hoặc dữ liệu vừa đổi; tải lại trước khi xác nhận.')
            meta, _ = self._artifact(db, company, version_id, data)
            history = self._events(db, company)
            was_active = any(e['action'] in {'activated','rolled_back'} and e['details']['version_id'] == version_id for e in history)
            if rollback and not was_active:
                raise ValueError('Chỉ quay lại phiên bản đã từng được kích hoạt cho doanh nghiệp này.')
            if not rollback and meta['data_revision'] != revision:
                raise ValueError('Ứng viên được đánh giá trên dữ liệu cũ; đánh giá lại trước khi kích hoạt.')
            db.execute('INSERT OR REPLACE INTO company_ml_bindings VALUES(?,?)', (company, version_id))
            self._event(db, company, principal, 'rolled_back' if rollback else 'activated',
                        version_id=version_id, previous_version=expected_active, data_revision=revision)
        return self.status(scenario, company, principal)

    def score(self, scenario, company, principal, *, expected_active, expected_revision):
        self._company(scenario, company, principal, True)
        with self.store.connection() as db:
            revision, data, records, x, _ = self._data(db, company)
            if data['scenario'] != scenario:
                raise ValueError('Cập nhật dữ liệu cho bộ đang chọn trước khi chạy ML.')
            active = self._active(db, company)
            if not active:
                raise ValueError('Xác nhận một phiên bản ML trước lần chấm đầu tiên.')
            if active != expected_active or revision != expected_revision:
                raise RuntimeError('Cấu hình hoặc dữ liệu đã đổi; tải lại trước khi chấm.')
            meta, artifact = self._artifact(db, company, active, data)
        indices = [i for i,r in enumerate(records) if instant(r['posted_at']) >= instant(artifact['calibration_end'])]
        if not indices:
            raise ValueError('Không có giao dịch mới ngoài kỳ train/calibration để chấm.')
        scores = artifact['estimator'].score(x[indices])
        result = [dict(transaction_id=records[i]['transaction_id'], company_id=company, posted_at=records[i]['posted_at'],
                       anomaly_score=float(score), flagged=bool(score > artifact['threshold'])) for i,score in zip(indices,scores)]
        run = dict(run_id=uuid.uuid4().hex, company_id=company, version_id=active, algorithm=meta['algorithm'],
                   number=meta['number'], data_revision=revision, rows=len(result), flagged=sum(r['flagged'] for r in result),
                   scored_at=self.store.clock().isoformat(), mode='shadow', scores_sha256=digest(result))
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if self._active(db, company) != active or self._data(db, company)[0] != revision:
                raise RuntimeError('Cấu hình hoặc dữ liệu đã đổi trong lúc chấm; hãy thử lại.')
            db.execute('INSERT INTO company_ml_runs VALUES(?,?,?,?)', (run['run_id'], company, json.dumps(run), json.dumps(result)))
            self._event(db, company, principal, 'scored', **run)
        return dict(run=run, items=result[:100], total=len(result))

    def keep(self, scenario, company, principal, *, expected_active, expected_revision):
        self._company(scenario, company, principal, True)
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            revision, data, _, _, _ = self._data(db, company)
            if data['scenario'] != scenario:
                raise ValueError('Cập nhật dữ liệu cho bộ đang chọn trước khi giữ model.')
            if not expected_active or self._active(db, company) != expected_active or revision != expected_revision:
                raise RuntimeError('Dữ liệu hoặc model vừa đổi; tải lại cấu hình trước khi giữ phiên bản.')
            self._artifact(db, company, expected_active, data)
            self._event(db, company, principal, 'kept', version_id=expected_active, data_revision=revision)
        return self.status(scenario, company, principal)
