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
        with closing(self._conn()) as c:
            c.executescript(
                'CREATE TABLE IF NOT EXISTS contributions(company TEXT PRIMARY KEY, rows TEXT NOT NULL, source TEXT NOT NULL, updated_at TEXT NOT NULL);'
                'CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, state TEXT NOT NULL, doc TEXT NOT NULL, updated_at TEXT NOT NULL);')

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

    def _rows(self, company):
        with closing(self._conn()) as c:
            row = c.execute('SELECT * FROM contributions WHERE company=?', (company,)).fetchone()
        return (json.loads(row['rows']), row['source'], row['updated_at']) if row else (None, None, None)

    def company_view(self, company):
        rows, source, at = self._rows(company)
        cfg = self.lr._discover_runtime_cfg()
        enrolled = any(g.get('company_id') == company and g.get('active') for g in cfg.get('_worker_grants', []))
        view = dict(company_id=company, enrolled=enrolled, rows=0, source=source, updated_at=at)
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
        """scopes_for(company) -> AccessScope with model.fit; raises if the caller may not train for that company."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                fail(409, 'FED_RUN_ACTIVE', 'Đang có một lần huấn luyện chung chạy.', 'Chờ lần hiện tại hoàn tất.')
            cfg = self.lr._discover_runtime_cfg()
            enrolled = {g['company_id'] for g in cfg.get('_worker_grants', []) if g.get('active')}
            wanted = body.get('companies')
            companies = sorted(set(wanted) if isinstance(wanted, list) and wanted else enrolled)
            companies = [c for c in companies if c in enrolled]
            rounds = int(body.get('rounds') or 2)
            if not 1 <= rounds <= MAX_ROUNDS:
                fail(400, 'FED_ROUNDS_INVALID', f'Số vòng phải từ 1 đến {MAX_ROUNDS}.', 'Chọn số vòng hợp lệ.')
            if len(companies) < 2:
                fail(409, 'FED_PARTICIPANTS_REQUIRED', 'Cần ít nhất 2 doanh nghiệp đã đăng ký khóa.', 'Chạy thiết lập HE huấn luyện rồi thử lại.')
            data, scopes = {}, {}
            for cid in companies:
                rows, _, _ = self._rows(cid)
                if not rows:
                    fail(409, 'FED_NO_DATA', f'Doanh nghiệp {cid} chưa nạp dữ liệu huấn luyện.', 'Nạp CSV hoặc dùng dữ liệu mô phỏng cho từng doanh nghiệp.')
                scopes[cid] = scopes_for(cid)
                data[cid] = _split(rows)
            doc = dict(run_id='fed_' + secrets.token_hex(8), state='running', stage='prepare', created_at=_now(), rounds=rounds,
                       companies=companies, events=[], features=list(FEATURES), result=None, simulated=all(self._rows(c)[1] == 'simulated' for c in companies))
            self._event(doc, 'prepare', f'Khởi tạo: {len(companies)} doanh nghiệp, {rounds} vòng. Chia 9:1 cục bộ tại từng doanh nghiệp.')
            self._thread = threading.Thread(target=self._run, args=(doc, cfg, scopes, data), daemon=True)
            self._thread.start()
            return doc

    def _run(self, doc, cfg, scopes, data):
        work = Path(cfg['enterprise_root']).resolve().parent / 'runs' / doc['run_id']
        try:
            self._execute(doc, cfg, scopes, data, work)
        except Exception as error:
            doc['state'] = 'failed'
            doc['error'] = f'{type(error).__name__}: {error}'[:400]
            self._event(doc, 'failed', 'Huấn luyện dừng: ' + doc['error'])
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _execute(self, doc, cfg, scopes, data, work):
        from experiments.he_training import federated_r4 as r4
        companies = doc['companies']
        build = Path(cfg['build']).resolve()
        executors, parts = {}, {}
        for i, cid in enumerate(companies, 1):
            scope = scopes[cid]
            executors[cid] = ConcreteFHEEnterpriseExecutor(
                tenant_id=scope.tenant_id, company_id=cid, enterprise_base_dir=Path(cfg['enterprise_root']) / cid, session_work_dir=work / cid,
                build_dir=build, worker_url=cfg['worker_url'], worker_verify_key=cfg['worker_verify_key'],
                linux_python=cfg.get('linux_python'), distro=cfg.get('distro'), scope=scope)
            e = executors[cid]
            parts[cid] = FederatedEnterpriseParticipant(
                tenant_id=scope.tenant_id, company_id=cid, key_epoch=e.key_epoch, evaluation_keys_sha256=e.evaluation_keys_sha256,
                signing_key=e.signing_key, participant_index=i, fhe_executor=e)
            self._event(doc, 'keys', f'{cid}: khóa bí mật riêng nằm trên máy doanh nghiệp (epoch {e.key_epoch[:10]}…); cloud chỉ nhận khóa đánh giá công khai.')
        first = executors[companies[0]]
        policy = FederationPolicy(
            session_id=doc['run_id'], tenant_id=scopes[companies[0]].tenant_id, min_participants=len(companies), worker_verify_key=cfg['worker_verify_key'],
            weight_scale=first.profile_spec['weight_scale'], bias_scale=first.profile_spec['bias_scale'],
            weight_domain=tuple(first.profile_spec['weight_domain']), bias_domain=tuple(first.profile_spec['bias_domain']))
        coord = FederatedCloudCoordinator(policy, [p.enrollment for p in parts.values()])
        last = {}
        t0 = time.monotonic()
        for rnd in range(1, doc['rounds'] + 1):
            init = list(coord.global_weights_code)
            fhe = {}
            for cid in companies:
                train = data[cid][0]
                # rotate through the company's training rows: one encrypted round = up to 4 batches of 4 rows
                start = ((rnd - 1) * BATCH * 4) % max(1, len(train))
                window = [train[(start + k) % len(train)] for k in range(BATCH * 4)]
                batches = [dict(index=b, row_ids=[r['record_id'] + f'#r{rnd}' for r in window[b * BATCH:(b + 1) * BATCH]],
                                x=[r['x'] for r in window[b * BATCH:(b + 1) * BATCH]], y=[r['y'] for r in window[b * BATCH:(b + 1) * BATCH]]) for b in range(4)]
                hold = data[cid][1]
                eval_rows = [hold[k % len(hold)] for k in range(BATCH)]
                eval_batches = [dict(index=0, row_ids=[r['record_id'] + f'#e{rnd}{k}' for k, r in enumerate(eval_rows)], x=[r['x'] for r in eval_rows], y=[r['y'] for r in eval_rows])]
                self._event(doc, 'encrypt', f'Vòng {rnd} · {cid}: mã hóa 16 dòng cục bộ và gửi bản mã lên worker cloud…', round=rnd, company=cid)
                s = time.monotonic()
                fhe[cid] = executors[cid].run_fhe_round(round_id=rnd, train_batches=batches, eval_batches=eval_batches, initial_weights_code=init, epochs=1)
                if not fhe[cid]['native_fhe_executed']:
                    raise RuntimeError('Worker không chạy Concrete FHE thật; không chấp nhận chế độ dự phòng.')
                self._event(doc, 'fhe', f'Vòng {rnd} · {cid}: cloud tính SGD trên bản mã xong ({time.monotonic() - s:.1f} giây); {cid} giải mã riêng trọng số của mình.',
                            round=rnd, company=cid, seconds=round(time.monotonic() - s, 1), delta=fhe[cid]['delta_float'])
            self._event(doc, 'secagg', f'Vòng {rnd}: các doanh nghiệp che bản cập nhật bằng mặt nạ cặp (secure aggregation) rồi gửi lên bộ điều phối.', round=rnd)
            for cid in companies:
                coord.accept_key_advertisement(rnd, parts[cid].advertise_round_keys(policy.session_id, rnd))
            ads = coord.get_round_advertisements(rnd)
            for cid in companies:
                parts[cid].generate_encrypted_shamir_shares(session_id=policy.session_id, round_id=rnd, verified_peer_ads=ads, enrollments=coord.enrollments, threshold=coord.shamir_threshold)
            for cid in companies:
                packet = parts[cid].create_masked_update_packet(
                    session_id=policy.session_id, round_id=rnd, delta_float=fhe[cid]['delta_float'], sample_count=fhe[cid]['sample_count'],
                    max_delta_linf=policy.max_delta_linf, use_double_mask=False,
                    fhe_proof={'signed_worker_result': fhe[cid]['signed_worker_result'], 'model_cipher_sha256': fhe[cid]['model_cipher_sha256']})
                coord.accept_masked_update(rnd, packet)
            record = coord.finalize_round(rnd)
            last = fhe
            self._event(doc, 'aggregate', f'Vòng {rnd}: trọng số chung = {[round(v, 3) for v in coord.global_weights_float]}.', round=rnd,
                        weights=list(coord.global_weights_float), record={k: record[k] for k in record if k in ('status', 'participants', 'total_samples')})
        weights = list(coord.global_weights_float)
        self._event(doc, 'evaluate', 'Đánh giá trên tập kiểm định 10% gộp từ các doanh nghiệp (không dùng để huấn luyện).')
        pooled = [r for cid in companies for r in data[cid][1]]
        untrained = [0.0, 0.0, 0.0]
        base = _metrics(untrained, pooled, 0.5)
        raw = evaluate_model_on_rows(weights, pooled)
        tau = select_validation_threshold([{'y_true': r['y'], 'score': p} for r, p in zip(pooled, raw['per_sample_probs'])])
        trained = _metrics(weights, pooled, tau['threshold'])
        per_company = {}
        for cid in companies:
            per_company[cid] = dict(holdout_rows=len(data[cid][1]), untrained=_metrics(untrained, data[cid][1], 0.5), trained=_metrics(weights, data[cid][1], tau['threshold']))
        audit = None
        if len(companies) >= 2:
            a, b = companies[0], companies[1]
            probe = executors[a].attempt_decrypt_foreign_ciphertext(last[b]['model_cipher'], last[b]['model_cipher_sha256'])
            audit = dict(company_reads_other=f'{a} → {b}', rejected=bool(probe.get('rejected')) or probe.get('decrypted_value') != last[b]['updated_weights_code'])
        summary = dict(recall=trained['recall'], precision=trained['precision'], f1=trained['f1'], accuracy=trained['accuracy'],
                       untrained_recall=base['recall'], untrained_precision=base['precision'], untrained_bce=base['bce_loss'], bce=trained['bce_loss'],
                       threshold=tau['threshold'], target_recall=TARGET_RECALL, recall_target_met=trained['recall'] >= TARGET_RECALL,
                       holdout_rows=len(pooled), train_rows=sum(len(data[c][0]) for c in companies), seconds=round(time.monotonic() - t0, 1))
        doc['result'] = dict(weights=dict(w=weights[:2], b=weights[2], codes=list(coord.global_weights_code), features=list(FEATURES)), summary=summary,
                             untrained=base, trained=trained, per_company=per_company, threshold=tau, privacy=dict(
                                 cloud_holds_secret_keys=False, cloud_saw_plaintext=False, individual_updates_visible_to_cloud=False, cross_company_decrypt=audit,
                                 execution='Concrete TFHE 2.11.0 native', secure_aggregation='X25519 pairwise masking + Shamir', worker_url=cfg['worker_url']),
                             approval=None, simulated=doc['simulated'])
        doc['state'] = 'completed'
        self._event(doc, 'completed', f'Hoàn tất: recall {trained["recall"]:.0%} (chưa huấn luyện {base["recall"]:.0%}, độ chính xác {trained["precision"]:.0%}). Mục tiêu recall ≥ {TARGET_RECALL:.0%}: {"đạt" if summary["recall_target_met"] else "chưa đạt"}.')

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
