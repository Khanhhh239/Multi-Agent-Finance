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


def decode_snapshot(row):
    """Read a verified ML snapshot without initializing or writing a workspace."""
    if not row:
        raise ValueError('Cập nhật và kiểm tra dữ liệu trước khi chọn ML.')
    records, x, labels = json.loads(row['records']), load(row['matrix']), json.loads(row['labels'])
    meta = json.loads(row['metadata'])
    if digest([meta, records, hashlib.sha256(row['matrix']).hexdigest(), labels]) != row['revision']:
        raise ValueError('Dữ liệu ML đã thay đổi ngoài luồng cập nhật.')
    return row['revision'], meta, records, x, labels


def labels_csv(text, company, records, now):
    if not isinstance(text, str) or len(text.encode('utf-8')) > 1_500_000:
        raise ValueError('Tệp nhãn quá lớn hoặc không hợp lệ.')
    if not text.strip():
        return {}
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    fields = {'company_id', 'transaction_id', 'label', 'reviewer_id', 'reviewed_at', 'evidence_ref', 'verified'}
    if set(reader.fieldnames or []) != fields or len(reader.fieldnames or []) != len(fields):
        raise ValueError('CSV nhãn cần company_id, transaction_id, label, reviewer_id, reviewed_at, evidence_ref, verified.')
    transactions = {r['transaction_id']: r for r in records}
    result = {}
    for row in reader:
        tid = row.get('transaction_id')
        if (None in row or any(value is None for value in row.values())
            or row.get('company_id') != company or tid not in transactions or tid in result
            or row.get('label') not in {'0', '1'} or row.get('verified') != '1'
            or not row.get('reviewer_id', '').strip() or not row.get('evidence_ref', '').strip()):
            raise ValueError('Nhãn cần đúng công ty/giao dịch, không trùng và có người rà, căn cứ, xác nhận.')
        reviewed = instant(row['reviewed_at'])
        if reviewed < instant(transactions[tid]['posted_at']) or reviewed > now:
            raise ValueError('Thời điểm rà nhãn không hợp lệ.')
        result[tid] = dict(label=int(row['label']), reviewed_at=row['reviewed_at'],
                           reviewer_id=row['reviewer_id'], evidence_ref=row['evidence_ref'])
    return result


def label_plan(existing, incoming):
    """A provenance change needs the same explicit decision as a class change."""
    added, unchanged, conflicts = [], [], []
    for tid, value in sorted(incoming.items()):
        old = existing.get(tid)
        if old is None:
            added.append(tid)
        elif (all(old[key] == value[key] for key in ('label', 'reviewer_id', 'evidence_ref'))
              and instant(old['reviewed_at']) == instant(value['reviewed_at'])):
            unchanged.append(tid)
        else:
            conflicts.append(dict(transaction_id=tid, existing=old, incoming=value))
    return dict(added=added, unchanged=unchanged, conflicts=conflicts)


def reject_label_conflicts(plan):
    if plan['conflicts']:
        ids = ', '.join(row['transaction_id'] for row in plan['conflicts'][:10])
        raise ValueError(f"Có {len(plan['conflicts'])} nhãn xung đột ({ids}). Chưa lưu thay đổi nào. "
                         'Xem trước nhãn và chọn giữ nhãn cũ hoặc xác nhận sửa nhãn kèm lý do.')


def evaluation_partition(records, train_end, calibration_end):
    """One chronological/minimum-size policy for readiness and actual fitting."""
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
    return first, second, train, cal, test


def catboost_training_readiness(records, labels, train, train_end):
    """Labels have already passed labels_csv; count only those known before train_end."""
    first = instant(train_end)
    missing = late = 0
    counts = {'0':0, '1':0}
    for i in train:
        label = labels.get(records[i]['transaction_id'])
        if label is None:
            missing += 1
        elif instant(label['reviewed_at']) >= first:
            late += 1
        else:
            counts[str(label['label'])] += 1
    known = sum(counts.values())
    installed = next(a['installed'] for a in catalog() if a['id']=='catboost')
    reason = ''
    if not installed:
        reason = 'Chưa cài CatBoost; cài requirements-company-ml.txt trong môi trường máy chủ.'
    elif missing or late:
        reason = (f'CatBoost: {known}/{len(train)} dòng train có nhãn đã xác minh và đã biết trước cuối kỳ train; '
                  f'{missing} dòng thiếu nhãn, {late} dòng biết nhãn muộn.')
    elif not counts['0'] or not counts['1']:
        reason = 'CatBoost cần cả hai lớp 0 và 1 đã xác minh trong kỳ train.'
    return dict(eligible=not reason, reason=reason, train_rows=len(train), verified_train_rows=known,
                missing_labels=missing, late_labels=late, class_counts=counts, installed=installed)


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
                CREATE TABLE IF NOT EXISTS company_ml_label_changes(
                    operation_id TEXT PRIMARY KEY, company_id TEXT, data TEXT);
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
            operation_id=value.get('details',{}).get('operation_id') if value['action']=='labels_updated' else None
            if operation_id:
                audit=db.execute('SELECT company_id,data FROM company_ml_label_changes WHERE operation_id=?',(operation_id,)).fetchone()
                if not audit or audit['company_id']!=company or digest(json.loads(audit['data']))!=value['details'].get('changes_sha256'):
                    raise ValueError('Lịch sử thay đổi nhãn không còn khớp.')
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
        return decode_snapshot(row)

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

    def readiness(self, scenario, company, principal, *, train_end='', calibration_end='',
                  expected_revision=None, expected_active=None):
        """Read-only form eligibility; the same guards still run on every POST."""
        self._company(scenario,company,principal)
        evaluation=dict(eligible=False,reason='Cập nhật dữ liệu trước khi đánh giá ML.')
        catboost=dict(eligible=False,reason='Cập nhật dữ liệu và chọn kỳ train để kiểm tra nhãn.',
                      train_rows=0,verified_train_rows=0,missing_labels=0,late_labels=0,class_counts={'0':0,'1':0})
        model=dict(compatible=False,can_keep=False,can_score=False,inference_rows=0,
                   reason='Xác nhận một phiên bản ML trước lần chấm đầu tiên.')
        with self.store.connection() as db:
            db.execute('BEGIN')
            row=db.execute('SELECT * FROM company_ml_data WHERE company_id=?',(company,)).fetchone()
            revision=row['revision'] if row else None
            active=self._active(db,company)
            if ((expected_revision is not None and expected_revision!=(revision or ''))
                    or (expected_active is not None and expected_active!=(active or ''))):
                raise RuntimeError('Dữ liệu hoặc model đã đổi. Tải lại cấu hình trước khi tiếp tục.')
            if row:
                _,data,records,_,labels=decode_snapshot(row)
                if data['scenario']!=scenario:
                    evaluation['reason']=catboost['reason']=model['reason']='Cập nhật dữ liệu cho bộ đang chọn trước khi tiếp tục.'
                else:
                    try:
                        _,_,train,cal,test=evaluation_partition(records,train_end,calibration_end)
                        evaluation=dict(eligible=True,reason='',train_rows=len(train),calibration_rows=len(cal),evaluation_rows=len(test))
                        catboost=catboost_training_readiness(records,labels,train,train_end)
                    except ValueError as error:
                        reason=str(error) if train_end and calibration_end else 'Chọn đủ cuối kỳ train và calibration để kiểm tra điều kiện.'
                        if reason=='Time must be ISO with a timezone':reason='Thời gian không hợp lệ; chọn lại kỳ train và calibration.'
                        evaluation['reason']=catboost['reason']=reason
                    if active:
                        try:
                            _,artifact=self._artifact(db,company,active,data)
                            count=sum(instant(r['posted_at'])>=instant(artifact['calibration_end']) for r in records)
                            model=dict(compatible=True,can_keep=True,can_score=count>0,inference_rows=count,
                                       reason='' if count else 'Không có giao dịch mới ngoài kỳ train/calibration để chấm.')
                        except (ValueError,KeyError,ImportError,TypeError,EOFError,AttributeError) as error:
                            model['reason']=str(error.args[0]) if isinstance(error,KeyError) else str(error)
        return dict(company_id=company,scenario=scenario,data_revision=revision,active_version=active,
                    train_end=train_end,calibration_end=calibration_end,evaluation=evaluation,catboost=catboost,model=model)

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
        incoming = labels_csv(labels_text, company, records, self.store.clock())
        if labels_text.strip() and not incoming:
            raise ValueError('CSV nhãn không có dòng nhãn nào; không thay đổi nhãn hiện có.')
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
            manifest_sha256=manifest_hash, labels_count=0, first_at=records[0]['posted_at'],
            last_at=records[-1]['posted_at'], suggested_windows=defaults)
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT revision FROM company_ml_data WHERE company_id=?', (company,)).fetchone()
            if (current[0] if current else None) != expected_revision:
                raise RuntimeError('Dữ liệu ML vừa được cập nhật ở phiên khác. Tải lại trước khi lưu.')
            labels = {}
            if current:
                _, old_meta, old_records, old_x, old_labels = self._data(db, company)
                by_id = {r['transaction_id']: i for i,r in enumerate(old_records)}
                if old_meta['feature_fingerprint'] == contract['fingerprint'] and old_meta['scenario'] == scenario:
                    for i, record in enumerate(records):
                        tid = record['transaction_id']; old_i = by_id.get(tid)
                        if (tid in old_labels and old_i is not None and record == old_records[old_i]
                            and np.array_equal(x[i], old_x[old_i])):
                            labels[tid] = old_labels[tid]
            plan = label_plan(labels, incoming)
            reject_label_conflicts(plan)
            labels.update({tid: incoming[tid] for tid in plan['added']})
            meta['labels_count'] = len(labels)
            revision = digest([meta, records, hashlib.sha256(blob).hexdigest(), labels])
            db.execute('INSERT OR REPLACE INTO company_ml_data VALUES(?,?,?,?,?,?)',
                       (company, revision, json.dumps(meta), json.dumps(records), blob, json.dumps(labels)))
            self._event(db, company, principal, 'data_updated', revision=revision, active_version=self._active(db, company))
        return self.status(scenario, company, principal)

    def _label_preview(self, scenario, company, revision, existing, incoming):
        plan = label_plan(existing, incoming)
        return dict(company_id=company, scenario=scenario, expected_revision=revision,
                    preview_hash=digest([scenario, company, revision, incoming]),
                    counts=dict(existing=len(existing), incoming=len(incoming), added=len(plan['added']),
                                unchanged=len(plan['unchanged']), conflicts=len(plan['conflicts']),
                                total=len(existing)+len(plan['added'])), conflicts=plan['conflicts'])

    def preview_labels(self, scenario, company, principal, *, expected_revision, labels_text):
        """Read-only conflict inspection, bound to the dataset and complete CSV."""
        self._company(scenario,company,principal,True)
        with self.store.connection() as db:
            revision,meta,records,_,existing=self._data(db,company)
        if revision!=expected_revision or meta['scenario']!=scenario:
            raise RuntimeError('Dữ liệu đã đổi. Tải lại trước khi cập nhật nhãn.')
        incoming=labels_csv(labels_text,company,records,self.store.clock())
        if not incoming:
            raise ValueError('CSV nhãn không có dòng nhãn nào; không thay đổi nhãn hiện có.')
        return self._label_preview(scenario,company,revision,existing,incoming)

    def update_labels(self, scenario, company, principal, *, expected_revision, labels_text,
                      conflict_policy='reject', preview_hash='', acknowledge=False, reason=''):
        """Merge labels atomically; corrections require an explicit reviewed decision."""
        self._company(scenario,company,principal,True)
        if conflict_policy not in ('reject','keep_existing','replace_conflicts'):
            raise ValueError('Chọn cách xử lý nhãn xung đột hợp lệ.')
        if not isinstance(reason,str) or len(reason)>2000:
            raise ValueError('Lý do sửa nhãn phải là văn bản không quá 2.000 ký tự.')
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            revision,meta,records,_,existing=self._data(db,company)
            if revision!=expected_revision or meta['scenario']!=scenario:
                raise RuntimeError('Dữ liệu đã đổi. Tải lại trước khi cập nhật nhãn.')
            incoming=labels_csv(labels_text,company,records,self.store.clock())
            if not incoming:
                raise ValueError('CSV nhãn không có dòng nhãn nào; không thay đổi nhãn hiện có.')
            preview=self._label_preview(scenario,company,revision,existing,incoming)
            plan=label_plan(existing,incoming)
            if (preview_hash or conflict_policy!='reject') and preview_hash!=preview['preview_hash']:
                raise RuntimeError('Nội dung nhãn hoặc dữ liệu đã đổi. Xem trước lại trước khi lưu.')
            if conflict_policy=='reject':
                reject_label_conflicts(plan)
            elif conflict_policy=='replace_conflicts' and plan['conflicts'] and (acknowledge is not True or not reason.strip()):
                raise ValueError('Xác nhận sửa nhãn xung đột và nhập lý do trước khi lưu.')
            changed=plan['added']+([r['transaction_id'] for r in plan['conflicts']] if conflict_policy=='replace_conflicts' else [])
            labels=existing | {tid:incoming[tid] for tid in changed}
            summary=preview['counts'] | dict(updated=len(changed)-len(plan['added']),
                skipped=0 if conflict_policy=='replace_conflicts' else len(plan['conflicts']), policy=conflict_policy)
            if changed:
                blob=db.execute('SELECT matrix FROM company_ml_data WHERE company_id=?',(company,)).fetchone()[0]
                meta=dict(meta,labels_count=len(labels))
                new_revision=digest([meta,records,hashlib.sha256(blob).hexdigest(),labels])
                db.execute('UPDATE company_ml_data SET revision=?,metadata=?,labels=? WHERE company_id=?',
                           (new_revision,json.dumps(meta),json.dumps(labels),company))
                operation_id=uuid.uuid4().hex
                audit=dict(operation_id=operation_id,company_id=company,scenario=scenario,
                    previous_revision=revision,revision=new_revision,actor=principal.user_id,
                    at=self.store.clock().isoformat(),reason=reason.strip(),summary=summary,
                    changes=[dict(transaction_id=tid,previous=existing.get(tid),current=incoming[tid]) for tid in sorted(changed)])
                db.execute('INSERT INTO company_ml_label_changes VALUES(?,?,?)',(operation_id,company,json.dumps(audit)))
                self._event(db,company,principal,'labels_updated',revision=new_revision,labels_count=len(labels),
                            operation_id=operation_id,changes_sha256=digest(audit),summary=summary,
                            active_version=self._active(db,company))
        return self.status(scenario,company,principal) | dict(label_update=summary)

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
            first, second, train, cal, test = evaluation_partition(records,train_end,calibration_end)
            y = None
            if algorithm == 'catboost':
                eligibility=catboost_training_readiness(records,labels,train,train_end)
                if not eligibility['eligible']:
                    raise ValueError(eligibility['reason'])
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
