"""Multi-company encrypted logistic-regression training driven from the Agent 2 UI.

Each contributing company keeps its own Concrete TFHE key domain.  A run encrypts that company's mini-batches locally,
the cloud worker (port 8870) executes the encrypted SGD steps without any secret key, the company decrypts only its own
update, and the per-company updates are combined with pairwise-masked secure aggregation (experiments.he_training.federated_r4).
Data rows are stored on the company side only; the cloud never receives plaintext rows, labels or weights.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import secrets
import shutil
import sqlite3
import threading
import time

from experiments.he_training.federated_r4 import (
    ConcreteFHEEnterpriseExecutor, FederatedCloudCoordinator, FederatedEnterpriseParticipant, FederationPolicy,
    evaluate_model_on_rows, evaluate_privacy_and_mia_risk,
)
from .import_files import fail
from .lr_inference import select_validation_threshold

FEATURES = ('round_million', 'creator_equals_approver')
FEATURE_LABELS_VI = {
    'round_million': 'Số tiền làm tròn bội số triệu đồng',
    'creator_equals_approver': 'Người lập đồng thời là người phê duyệt',
}
BATCH = 4
EPOCHS_PER_ROUND = 20
LEARNING_RATE = 2.0
MIN_ROWS = 20
TARGET_RECALL = 0.90
MAX_ROUNDS = 4
SIMULATED_PROFILES = {
    # (P(f1|risk), P(f2|risk), P(f1|ok), P(f2|ok), risk share): each company has a different but overlapping risk pattern
    'MPX10': (0.80, 0.55, 0.12, 0.10, 0.30),
    'C001': (0.85, 0.30, 0.10, 0.08, 0.28),
    'C002': (0.40, 0.85, 0.12, 0.12, 0.32),
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _split(rows):
    """Deterministic stratified 9:1 split: the holdout never reaches the encrypted training step."""
    train, hold = [], []
    for label in (0, 1):
        part = sorted((r for r in rows if r['y'] == label), key=lambda r: hashlib.sha256(r['record_id'].encode()).hexdigest())
        cut = max(1, round(len(part) * 0.1))
        hold += part[:cut]
        train += part[cut:]
    return train, hold


def _metrics(weights, rows, threshold):
    m = evaluate_model_on_rows(weights, rows, threshold=threshold)
    return {k: m[k] for k in ('sample_count', 'threshold', 'bce_loss', 'accuracy', 'precision', 'recall', 'f1', 'tp', 'fp', 'tn', 'fn')}


class FederatedLRService:
    def __init__(self, db_path, lr_service, authorizer=None):
        self.path = Path(db_path)
        self.lr = lr_service
        self.authorizer = authorizer
        self._lock = threading.RLock()
        self._thread = None
        self.key_root = self.path.with_name('he-training-companies')
        with closing(self._conn()) as c:
            c.executescript(
                'CREATE TABLE IF NOT EXISTS contributions(company TEXT PRIMARY KEY, rows TEXT NOT NULL, source TEXT NOT NULL, updated_at TEXT NOT NULL);'
                'CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, state TEXT NOT NULL, doc TEXT NOT NULL, updated_at TEXT NOT NULL);'
                'CREATE TABLE IF NOT EXISTS submissions(company TEXT PRIMARY KEY, submitted_at TEXT NOT NULL, rows INTEGER NOT NULL, label_1 INTEGER NOT NULL);'
                'CREATE TABLE IF NOT EXISTS models(version INTEGER PRIMARY KEY, run_id TEXT NOT NULL, doc TEXT NOT NULL, accepted_at TEXT NOT NULL);'
                'CREATE TABLE IF NOT EXISTS syncs(company TEXT PRIMARY KEY, version INTEGER NOT NULL, synced_at TEXT NOT NULL);'
                'CREATE TABLE IF NOT EXISTS packages(company TEXT PRIMARY KEY, doc TEXT NOT NULL, created_at TEXT NOT NULL);')

    def _conn(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    # ---- data contribution (company side, local) -------------------------------------------------------------
    def contribute(self, company, body):
        rows = body.get('rows')
        if not isinstance(rows, list):
            fail(400, 'FED_ROWS_REQUIRED', 'Cần danh sách dòng huấn luyện.', 'Nạp tệp CSV có cột record_id, hai đặc trưng 0/1 và nhãn 0/1.')
        clean, seen = [], set()
        for r in rows:
            rid = str(r.get('record_id') or '').strip()
            x = r.get('x')
            y = r.get('y')
            if not rid or rid in seen or not isinstance(x, list) or len(x) != 2 or any(type(v) is not int or v not in (0, 1) for v in x) or type(y) is not int or y not in (0, 1):
                fail(400, 'FED_ROW_INVALID', f'Dòng "{rid or "?"}" không hợp lệ hoặc bị trùng.', 'Mỗi dòng cần record_id duy nhất, 2 đặc trưng nhị phân 0/1 và nhãn 0/1.')
            seen.add(rid)
            clean.append(dict(record_id=rid, x=x, y=y))
        if len(clean) < MIN_ROWS or {r['y'] for r in clean} != {0, 1}:
            fail(409, 'FED_ROWS_INSUFFICIENT', f'Cần ít nhất {MIN_ROWS} dòng và đủ cả hai nhãn 0 và 1.', 'Bổ sung dữ liệu rồi nạp lại.')
        self._save_rows(company, clean, str(body.get('source') or 'upload'))
        return self.company_view(company)

    def simulate(self, company, count=48):
        prof = SIMULATED_PROFILES.get(company) or (0.7, 0.5, 0.12, 0.1, 0.3)
        rng = random.Random(int(hashlib.sha256(('fed-sim:' + company).encode()).hexdigest()[:8], 16))
        rows = []
        for i in range(max(MIN_ROWS, int(count))):
            risk = 1 if rng.random() < prof[4] else 0
            p1, p2 = (prof[0], prof[1]) if risk else (prof[2], prof[3])
            rows.append(dict(record_id=f'{company}-SIM-{i:04d}', x=[int(rng.random() < p1), int(rng.random() < p2)], y=risk))
        if {r['y'] for r in rows} != {0, 1}:
            rows[0]['y'], rows[1]['y'] = 0, 1
        self._save_rows(company, rows, 'simulated')
        return self.company_view(company)

    def _save_rows(self, company, rows, source):
        with closing(self._conn()) as c, c:
            c.execute('INSERT OR REPLACE INTO contributions VALUES(?,?,?,?)', (company, json.dumps(rows), source, _now()))
            c.execute('DELETE FROM submissions WHERE company=?', (company,))  # new data must be sent again

    # ---- company -> station ------------------------------------------------------------------------------------
    def submit(self, company):
        """Company encrypts its rows with its own CKKS key and sends ciphertexts + labels to the station."""
        from .he_lr_ckks import CompanyNode, package
        rows, _, _ = self._rows(company)
        if not rows:
            fail(409, 'FED_NO_DATA', 'Chưa nạp dữ liệu huấn luyện.', 'Nạp tệp CSV có nhãn trước khi gửi lên trạm.')
        train, hold = _split(rows)
        node = CompanyNode(self.key_root, company)
        pkg = package(node, train, hold, FEATURES)
        with closing(self._conn()) as c, c:
            c.execute('INSERT OR REPLACE INTO packages VALUES(?,?,?)', (company, json.dumps(pkg), _now()))
            c.execute('INSERT OR REPLACE INTO submissions VALUES(?,?,?,?)', (company, _now(), len(rows), sum(r['y'] for r in rows)))
        return self.company_status(company)

    def current_model(self):
        with closing(self._conn()) as c:
            row = c.execute('SELECT version, run_id, doc, accepted_at FROM models ORDER BY version DESC LIMIT 1').fetchone()
        return dict(version=row['version'], run_id=row['run_id'], accepted_at=row['accepted_at'], **json.loads(row['doc'])) if row else None

    def company_status(self, company):
        with closing(self._conn()) as c:
            sub = c.execute('SELECT * FROM submissions WHERE company=?', (company,)).fetchone()
            syn = c.execute('SELECT * FROM syncs WHERE company=?', (company,)).fetchone()
        model = self.current_model()
        view = self.company_view(company)
        view.update(submitted_at=sub['submitted_at'] if sub else None, synced_version=syn['version'] if syn else None,
                    synced_at=syn['synced_at'] if syn else None,
                    station_model=None if model is None else dict(version=model['version'], accepted_at=model['accepted_at'],
                                                                  summary=model['summary'], companies=model['companies']))
        return view

    def sync(self, company, scope):
        model = self.current_model()
        if model is None:
            fail(409, 'FED_NO_MODEL', 'Trạm chưa có mô hình chung nào được chấp nhận.', 'Chờ trạm huấn luyện xong rồi đồng bộ.')
        record = self.lr.install_federated_model(scope, model)
        with closing(self._conn()) as c, c:
            c.execute('INSERT OR REPLACE INTO syncs VALUES(?,?,?)', (company, model['version'], _now()))
        out = self.company_status(company)
        out['installed_model'] = dict(model_id=record['model_id'], version_tag=record['version_tag'], threshold=record['threshold'])
        return out

    # ---- station view --------------------------------------------------------------------------------------------
    def station_status(self):
        with closing(self._conn()) as c:
            subs = {r['company']: dict(r) for r in c.execute('SELECT * FROM submissions')}
            enrolled = sorted({r['company'] for r in c.execute('SELECT company FROM contributions')} | set(subs))
            models = [dict(version=r['version'], run_id=r['run_id'], accepted_at=r['accepted_at'], summary=json.loads(r['doc'])['summary'])
                      for r in c.execute('SELECT * FROM models ORDER BY version DESC LIMIT 10')]
            latest = c.execute('SELECT doc FROM runs ORDER BY updated_at DESC LIMIT 1').fetchone()
            history = [json.loads(r['doc']) for r in c.execute('SELECT doc FROM runs ORDER BY updated_at DESC LIMIT 10')]
        return dict(enrolled_companies=enrolled, worker=dict(status='ok', scheme='CKKS (TenSEAL)'),
                    contributions=[dict(company_id=cid, submitted=cid in subs, submitted_at=subs.get(cid, {}).get('submitted_at'),
                                        rows=subs.get(cid, {}).get('rows', 0), label_1=subs.get(cid, {}).get('label_1', 0)) for cid in enrolled],
                    current_model=self.current_model(), models=models, latest=json.loads(latest['doc']) if latest else None,
                    history=[dict(run_id=h['run_id'], state=h['state'], created_at=h.get('created_at'), accepted=(h.get('result') or {}).get('accepted'),
                                  summary=(h.get('result') or {}).get('summary')) for h in history],
                    limits=dict(batch_size=BATCH, max_rounds=MAX_ROUNDS, holdout_share=0.1, target_recall=TARGET_RECALL))

    def submitted_companies(self):
        with closing(self._conn()) as c:
            return sorted(r['company'] for r in c.execute('SELECT company FROM submissions'))

    def _rows(self, company):
        with closing(self._conn()) as c:
            row = c.execute('SELECT * FROM contributions WHERE company=?', (company,)).fetchone()
        return (json.loads(row['rows']), row['source'], row['updated_at']) if row else (None, None, None)

    def company_view(self, company):
        rows, source, at = self._rows(company)
        view = dict(company_id=company, enrolled=True, has_key=(self.key_root / company / 'ckks-secret.ctx').is_file(), rows=0, source=source, updated_at=at)
        if rows:
            train, hold = _split(rows)
            view.update(rows=len(rows), label_1=sum(r['y'] for r in rows), label_0=sum(1 - r['y'] for r in rows), train_rows=len(train), holdout_rows=len(hold))
        return view

    # ---- status ------------------------------------------------------------------------------------------------
    def status(self):
        cfg = self.lr._discover_runtime_cfg()
        grants = [g for g in cfg.get('_worker_grants', []) if g.get('active')]
        with closing(self._conn()) as c:
            latest = c.execute('SELECT doc FROM runs ORDER BY updated_at DESC LIMIT 1').fetchone()
            history = [json.loads(r['doc']) for r in c.execute('SELECT doc FROM runs ORDER BY updated_at DESC LIMIT 8')]
        return dict(
            version='federated-lr/1.0.0',
            features=[dict(name=f, label_vi=FEATURE_LABELS_VI[f], domain=[0, 1]) for f in FEATURES],
            enrolled_companies=sorted(g['company_id'] for g in grants),
            companies=[self.company_view(g['company_id']) for g in sorted(grants, key=lambda g: g['company_id'])],
            worker=self.lr.probe_worker_health(),
            limits=dict(batch_size=BATCH, max_rounds=MAX_ROUNDS, min_rows=MIN_ROWS, holdout_share=0.1, target_recall=TARGET_RECALL,
                        circuit_updates_per_round=4, circuit_features=len(FEATURES)),
            latest=json.loads(latest['doc']) if latest else None,
            history=[dict(run_id=h['run_id'], state=h['state'], created_at=h.get('created_at'), metrics=(h.get('result') or {}).get('summary')) for h in history],
        )

    def job(self, run_id):
        with closing(self._conn()) as c:
            row = c.execute('SELECT doc FROM runs WHERE run_id=?', (run_id,)).fetchone()
        if row is None:
            fail(404, 'FED_RUN_NOT_FOUND', 'Không tìm thấy lần huấn luyện chung.', 'Chọn lần huấn luyện có trong lịch sử.')
        return json.loads(row['doc'])

    def _store(self, doc):
        with closing(self._conn()) as c, c:
            c.execute('INSERT OR REPLACE INTO runs VALUES(?,?,?,?)', (doc['run_id'], doc['state'], json.dumps(doc), _now()))

    def _event(self, doc, stage, message, **extra):
        doc['events'].append(dict(at=_now(), stage=stage, message=message, **extra))
        doc['stage'] = stage
        self._store(doc)

    # ---- run -------------------------------------------------------------------------------------------------
    def start(self, scopes_for, body):
        """Station starts a joint run on every company that has sent its encrypted package."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                fail(409, 'FED_RUN_ACTIVE', 'Đang có một lần huấn luyện chung chạy.', 'Chờ lần hiện tại hoàn tất.')
            with closing(self._conn()) as c:
                pkgs = {r['company']: json.loads(r['doc']) for r in c.execute('SELECT company, doc FROM packages')}
            companies = sorted(pkgs)
            rounds = int(body.get('rounds') or 2)
            if not 1 <= rounds <= MAX_ROUNDS:
                fail(400, 'FED_ROUNDS_INVALID', f'Số vòng phải từ 1 đến {MAX_ROUNDS}.', 'Chọn số vòng hợp lệ.')
            if len(companies) < 2:
                fail(409, 'FED_PARTICIPANTS_REQUIRED', 'Cần ít nhất 2 doanh nghiệp đã gửi dữ liệu.', 'Chờ các doanh nghiệp gửi dữ liệu lên trạm.')
            doc = dict(run_id='fed_' + secrets.token_hex(8), state='running', stage='prepare', created_at=_now(), rounds=rounds,
                       companies=companies, events=[], features=list(FEATURES), result=None,
                       simulated=all(self._rows(c)[1] in ('simulated', 'upload') for c in companies))
            self._event(doc, 'prepare', f'Khởi tạo: {len(companies)} doanh nghiệp, {rounds} vòng × {EPOCHS_PER_ROUND} lượt. Trạm chỉ có bản mã và nhãn.')
            self._thread = threading.Thread(target=self._run, args=(doc, None, scopes_for, pkgs), daemon=True)
            self._thread.start()
            return doc

    def _run(self, doc, cfg, scopes_for, pkgs):
        try:
            self._execute(doc, pkgs)
        except Exception as error:
            doc['state'] = 'failed'
            doc['error'] = f'{type(error).__name__}: {error}'[:400]
            self._event(doc, 'failed', 'Huấn luyện dừng: ' + doc['error'])

    def _execute(self, doc, pkgs):
        import math
        from .he_lr_ckks import CompanyNode, StationView
        companies = doc['companies']
        views = {c: StationView(pkgs[c]) for c in companies}          # station side: public context + ciphertexts only
        nodes = {c: CompanyNode(self.key_root, c) for c in companies}  # company side: secret key, decrypt aggregates only
        for c in companies:
            self._event(doc, 'keys', f'{c}: trạm nhận {len(pkgs[c]["train_y"])} dòng đã mã hóa + nhãn; khóa giải mã vẫn ở doanh nghiệp.', company=c)
        d = len(FEATURES)
        w, b = [0.0] * d, 0.0
        n_total = sum(len(pkgs[c]['train_y']) for c in companies)
        t0 = time.monotonic()
        for rnd in range(1, doc['rounds'] + 1):
            for ep in range(EPOCHS_PER_ROUND):
                grad = [0.0] * (d + 1)
                for c in companies:
                    enc = views[c].gradient(w, b)                       # computed on ciphertext at the station
                    dec = nodes[c].decrypt_aggregate(enc, d + 1)        # company returns only the summed gradient
                    grad = [g + x for g, x in zip(grad, dec)]
                w = [w[j] - LEARNING_RATE * grad[j] / n_total for j in range(d)]
                b = b - LEARNING_RATE * grad[d] / n_total
            self._event(doc, 'fhe', f'Vòng {rnd}: tính gradient trên bản mã của {len(companies)} doanh nghiệp ({EPOCHS_PER_ROUND} lượt). '
                                    f'Trọng số = {[round(v, 3) for v in w]}, b = {round(b, 3)}.', round=rnd, weights=list(w) + [b])
        self._event(doc, 'evaluate', 'Đánh giá trên tập kiểm định 10% của từng doanh nghiệp (không dùng để huấn luyện).')
        scored = []
        for c in companies:
            z = nodes[c].decrypt_aggregate(views[c].holdout_scores(w, b), 1)[:len(pkgs[c]['holdout_y'])]
            scored += [(c, 1.0 / (1.0 + math.exp(-zi)), y) for zi, y in zip(z, pkgs[c]['holdout_y'])]
        weights = list(w) + [b]
        pooled = [dict(x=None, y=y) for _, _, y in scored]
        # Threshold: the strictest cut that still keeps recall >= target on validation (fewest false alerts); best F1 otherwise.
        cands = sorted({round(p, 6) for _, p, _ in scored} | {0.5}, reverse=True)
        def rec_prec(t):
            tp = sum(1 for _, p, y in scored if p >= t and y == 1); fp = sum(1 for _, p, y in scored if p >= t and y == 0)
            pos = sum(1 for _, _, y in scored if y == 1)
            return tp / max(1, pos), tp / max(1, tp + fp)
        ok = [t for t in cands if rec_prec(t)[0] >= TARGET_RECALL]
        if ok:
            chosen, basis = max(ok, key=lambda t: (rec_prec(t)[1], t)), 'max_precision_at_target_recall'
        else:
            chosen, basis = max(cands, key=lambda t: (lambda r, pr: 2 * r * pr / (r + pr) if r + pr else 0)(*rec_prec(t))), 'best_f1'
        tau = dict(threshold=chosen, selection_basis=basis, target_recall=TARGET_RECALL)

        def metrics(rows, threshold):
            tp = sum(1 for p, y in rows if p >= threshold and y == 1)
            fp = sum(1 for p, y in rows if p >= threshold and y == 0)
            fn = sum(1 for p, y in rows if p < threshold and y == 1)
            tn = len(rows) - tp - fp - fn
            eps = 1e-12
            bce = sum(-(y * math.log(max(eps, p)) + (1 - y) * math.log(max(eps, 1 - p))) for p, y in rows) / max(1, len(rows))
            prec, rec = tp / max(1, tp + fp), tp / max(1, tp + fn)
            return dict(sample_count=len(rows), threshold=threshold, bce_loss=round(bce, 6), accuracy=round((tp + tn) / max(1, len(rows)), 4),
                        precision=round(prec, 4), recall=round(rec, 4), f1=round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0, tp=tp, fp=fp, tn=tn, fn=fn)
        trained_rows = [(p, y) for _, p, y in scored]
        untrained_rows = [(0.5, y) for _, _, y in scored]
        trained, base = metrics(trained_rows, tau['threshold']), metrics(untrained_rows, 0.5)
        per_company = {c: dict(holdout_rows=len(pkgs[c]['holdout_y']), untrained=metrics([(0.5, y) for cc, _, y in scored if cc == c], 0.5),
                               trained=metrics([(p, y) for cc, p, y in scored if cc == c], tau['threshold'])) for c in companies}
        summary = dict(recall=trained['recall'], precision=trained['precision'], f1=trained['f1'], accuracy=trained['accuracy'],
                       untrained_recall=base['recall'], untrained_precision=base['precision'], untrained_bce=base['bce_loss'], bce=trained['bce_loss'],
                       threshold=tau['threshold'], target_recall=TARGET_RECALL, recall_target_met=trained['recall'] >= TARGET_RECALL,
                       holdout_rows=len(scored), train_rows=n_total, seconds=round(time.monotonic() - t0, 1))
        codes = [int(round(v * 16)) for v in w] + [int(round(b * 16))]
        doc['result'] = dict(weights=dict(w=list(w), b=b, codes=codes, features=list(FEATURES)), summary=summary, untrained=base, trained=trained,
                             per_company=per_company, threshold=tau, privacy=dict(
                                 cloud_holds_secret_keys=False, cloud_saw_plaintext_features=False, labels_visible_to_station=True,
                                 company_sees=f'chỉ tổng gradient {d + 1} số của chính mình', execution='CKKS (TenSEAL 0.3.18), N=16384'),
                             approval=None, simulated=doc['simulated'])
        current = self.current_model()
        better = current is None or (summary['f1'], summary['recall']) > (current['summary']['f1'], current['summary']['recall'])
        doc['result']['accepted'] = better
        if better:
            with closing(self._conn()) as c, c:
                version = (c.execute('SELECT COALESCE(MAX(version), 0) FROM models').fetchone()[0] or 0) + 1
                c.execute('INSERT INTO models VALUES(?,?,?,?)', (version, doc['run_id'], json.dumps(dict(
                    weights=doc['result']['weights'], summary=summary, threshold=tau['threshold'], companies=companies)), _now()))
            doc['result']['model_version'] = version
            self._event(doc, 'accepted', f'Mô hình mới tốt hơn trên tập kiểm định nên được cập nhật thành phiên bản v{version}.')
        else:
            self._event(doc, 'kept', 'Mô hình mới chưa tốt hơn phiên bản v%d nên trạm giữ trọng số cũ.' % current['version'])
        doc['state'] = 'completed'
        self._event(doc, 'completed', f'Hoàn tất: recall {trained["recall"]:.0%}, precision {trained["precision"]:.0%} (mô hình chưa huấn luyện: recall {base["recall"]:.0%}, precision {base["precision"]:.0%}). Mục tiêu recall ≥ {TARGET_RECALL:.0%}: {"đạt" if summary["recall_target_met"] else "chưa đạt"}.')

    def approve(self, run_id, actor, reason):
        doc = self.job(run_id)
        if doc['state'] != 'completed':
            fail(409, 'FED_RUN_NOT_COMPLETED', 'Chỉ phê duyệt lần huấn luyện đã hoàn tất.', 'Chờ lần huấn luyện kết thúc.')
        reason = str(reason or '').strip()
        if len(reason) < 8:
            fail(400, 'FED_APPROVAL_REASON', 'Cần nêu lý do phê duyệt (tối thiểu 8 ký tự).', 'Ghi rõ căn cứ phê duyệt.')
        doc['result']['approval'] = dict(by=actor, reason=reason, at=_now(), scope='shadow_evaluation_only')
        self._event(doc, 'approved', f'{actor} phê duyệt mô hình chung cho chạy song song (shadow); chưa kích hoạt thật.')
        return doc
