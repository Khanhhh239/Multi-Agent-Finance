"""Verified, read-only P2 fixtures and a separate append-only UAT journal."""
from collections import Counter
import csv
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3

from .feature_contract import sha, digest
from .run_p2_controls import verify_sources, compare, PROTECTED
from .cash_controls import vat_policy,local_day

PROJECT = Path(__file__).resolve().parents[1]
GROUPS = dict(full_invoice='Hóa đơn đầy đủ', missing_documents='Thiếu chứng từ',
              installments='Trả nhiều đợt', refund_reversal='Hoàn / đảo giao dịch',
              recurring='Chi định kỳ', internal_limit='Hạn mức nội bộ')
VERDICTS = dict(passed='Đạt', needs_fix='Cần sửa', needs_information='Cần bổ sung')
CATEGORIES = dict(no_p2='Không phát sinh P2', information_request='Thiếu bằng chứng · 0 điểm',
                  vat_document_review='Đối chiếu chứng từ / VAT · 8 điểm',
                  verified_internal_breach='Vượt hạn mức đã xác minh · 14 điểm')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def read_scores(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:
        return list(csv.DictReader(stream))


def artifact_files(root, files):
    root = Path(root).resolve()
    for name, checksum in files.items():
        path = (root/name).resolve()
        if root not in path.parents or sha(path) != checksum:
            raise ValueError('P2 control artifact checksum/scope mismatch: '+name)


class P2Controls:
    def __init__(self, source, report, database, *, readonly=False):
        self.source, self.report, self.database = (Path(p).resolve() for p in (source, report, database))
        if type(readonly) is not bool:
            raise ValueError('readonly must be a boolean')
        self.readonly = readonly
        if readonly and not self.database.is_file():
            raise FileNotFoundError(self.database)
        # Review notes must never be written inside an input or locked report.
        locked = [self.source, self.report, *PROTECTED,
                  PROJECT/'reports/a5_coverage_20261018_v2']
        if any(self.database == root or root in self.database.parents for root in locked):
            raise ValueError('UAT database must be separate from frozen sources and reports')
        manifest = verify_sources(self.source)
        commitment = read(self.report/'predictions_frozen.json')
        if (commitment.get('expectations_joined') is not False
                or commitment.get('source_manifest_sha256') != sha(self.source/'manifest.json')
                or commitment.get('plan_sha256') != sha(self.report/'evaluation_plan.json')):
            raise ValueError('P2 frozen prediction commitment does not match its source/plan')
        artifact_files(self.report, commitment['files'])
        self.snapshot_id = digest(dict(source=sha(self.source/'manifest.json'), predictions=sha(self.report/'predictions_frozen.json')))
        self.provenance = dict(snapshot_id=self.snapshot_id, source_manifest_sha256=sha(self.source/'manifest.json'),
            predictions_frozen_sha256=sha(self.report/'predictions_frozen.json'),
            expected_sha256=manifest['files']['expected_outcomes.json'])
        index = read(self.source/'control_index.json')
        identifiers = [r['control_id'] for r in index]
        if (len(set(identifiers)) != len(index) or len(index) != manifest['controls']
                or any(not re.fullmatch('[A-Z0-9_]+', value) for value in identifiers)):
            raise ValueError('Invalid P2 control index')
        expected = read(self.source/'expected_outcomes.json')
        expected_by_key = {(r['control_id'], r['transaction_id']): r for r in expected}
        if len(expected_by_key) != len(expected):
            raise ValueError('Duplicate declared P2 expectation')
        global_predictions = read(self.report/'predictions.json')
        predicted = {(r['control_id'], r['transaction_id']): r for r in global_predictions}
        if len(predicted) != len(global_predictions) or set(predicted) != set(expected_by_key):
            raise ValueError('Incomplete or duplicate P2 predictions')
        self.controls = {}
        for item in index:
            identity = item['control_id']
            if item['group'] not in GROUPS:
                raise ValueError('Unknown P2 control group')
            # All displayed detector artifacts must belong to the commitment.
            for filename in ('predictions.json', 'rule_hits.json', 'case_queue.json', 'case_events.json', 'rule_config.json','rule_scores.csv'):
                if identity+'/'+filename not in commitment['files']:
                    raise ValueError('Missing committed P2 artifact')
            tables = read(self.source/identity/'tables.json')
            hits = read(self.report/identity/'rule_hits.json')
            cases = read(self.report/identity/'case_queue.json')
            actual = read(self.report/identity/'predictions.json')
            transactions = tables['transactions']
            tx = {row['transaction_id']: row for row in transactions}
            if len(tx) != len(transactions) or len(actual) != len(tx) or {r['transaction_id'] for r in actual} != set(tx):
                raise ValueError('Invalid P2 transaction scope')
            if any(h['transaction_id'] not in tx or h['company_id'] != tx[h['transaction_id']]['company_id'] for h in hits):
                raise ValueError('P2 hit is outside its transaction scope')
            for case in cases:
                if any(tid not in tx or tx[tid]['company_id'] != case['company_id'] for tid in json.loads(case['transaction_ids'])):
                    raise ValueError('P2 case is outside its control scope')
            joined = []
            for outcome in actual:
                key = identity, outcome['transaction_id']
                if predicted[key] != dict(control_id=identity, **outcome):
                    raise ValueError('Control and aggregate P2 predictions differ')
                wanted = expected_by_key[key]
                joined.append(dict(transaction_id=key[1], expected=wanted, actual=outcome,
                                   differences=compare(wanted, outcome)))
            self.controls[identity] = dict(**item, group_label=GROUPS[item['group']],
                transactions=transactions, hits=hits, cases=cases, comparisons=joined,
                documents=tables.get('journal_documents', []), lines=tables.get('journal_lines', []),
                invoices=tables.get('invoices', []), document_links=tables.get('document_links', []),
                recurring_payments=tables.get('recurring_payments', []),
                invoice_versions=tables.get('invoice_versions', []),
                supplier_payment_agreements=tables.get('supplier_payment_agreements', []),
                transaction_documents=tables.get('transaction_documents', []),
                payment_requests=tables.get('payment_requests', []),
                rule_scores=read_scores(self.report/identity/'rule_scores.csv'),
                policy_context={r['transaction_id']:dict(threshold_vnd=min(vat_policy(local_day(r['posted_at']))[0],
                    vat_policy(local_day(r['invoice_issued_at']))[0] if r.get('invoice_issued_at') and
                    datetime.fromisoformat(r['invoice_issued_at'])<=datetime.fromisoformat(r['posted_at']) else vat_policy(local_day(r['posted_at']))[0]),
                    purpose='display_policy_reference_only_no_rescoring') for r in transactions},
                config=read(self.report/identity/'rule_config.json'),
                case_events=read(self.report/identity/'case_events.json'),
                matched=all(not r['differences'] for r in joined))
        if len(expected) != manifest['observations'] or sum(len(c['transactions']) for c in self.controls.values()) != len(expected):
            raise ValueError('P2 declared population does not reconcile')
        if not readonly:
            self.database.parent.mkdir(parents=True, exist_ok=True)
            with self.connect() as db:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('''CREATE TABLE IF NOT EXISTS reviews(
                    id INTEGER PRIMARY KEY, snapshot_id TEXT, control_id TEXT, verdict TEXT,
                    reviewer TEXT, reason TEXT, reviewed_at TEXT, previous_hash TEXT, event_hash TEXT)''')
        self.history()  # Fail closed on a broken audit journal before serving UI.

    @contextmanager
    def connect(self):
        db = (sqlite3.connect(self.database.as_uri()+'?mode=ro', uri=True, timeout=15)
              if self.readonly else sqlite3.connect(self.database, timeout=15))
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA trusted_schema=OFF')
        try:
            with db:
                yield db
        finally:
            db.close()

    def _history(self, db):
        previous, rows = '', []
        for item in db.execute('SELECT * FROM reviews ORDER BY id'):
            row = dict(item)
            event_hash = row.pop('event_hash')
            if row['previous_hash'] != previous or digest(row) != event_hash:
                raise ValueError('Nhật ký nghiệm thu không còn khớp chuỗi hash; cần kiểm tra trước khi tiếp tục.')
            row['event_hash'] = event_hash
            rows.append(row)
            previous = event_hash
        return rows

    def history(self):
        with self.connect() as db:
            return self._history(db)

    def current_reviews(self):
        latest = {}
        for row in self.history():
            if row['snapshot_id'] == self.snapshot_id:
                latest[row['control_id']] = row
        return latest

    def metadata(self):
        reviews = self.current_reviews()
        return dict(application='p2-control-uat', snapshot_id=self.snapshot_id, provenance=self.provenance,
            controls=len(self.controls), transactions=sum(len(c['transactions']) for c in self.controls.values()),
            matched_controls=sum(c['matched'] for c in self.controls.values()),
            matched_transactions=sum(not r['differences'] for c in self.controls.values() for r in c['comparisons']),
            reviewed_controls=len(reviews), verdict_counts=dict(Counter(r['verdict'] for r in reviews.values())),
            groups=GROUPS, verdicts=VERDICTS, categories=CATEGORIES,
            category_counts=dict(Counter(r['actual']['category'] or 'no_p2' for c in self.controls.values() for r in c['comparisons'])),
            notifications='disabled', review_scope='UAT only; no operational conclusions or fraud labels')

    def list_controls(self, group='', category='', verdict='', q=''):
        if group and group not in GROUPS or category and category not in CATEGORIES or verdict and verdict not in {*VERDICTS, 'unreviewed'}:
            raise ValueError('Bộ lọc nghiệm thu không hợp lệ.')
        if len(q) > 200:
            raise ValueError('Nội dung tìm kiếm quá dài.')
        reviews, rows = self.current_reviews(), []
        for identity, case in self.controls.items():
            review = reviews.get(identity)
            categories = Counter(row['actual']['category'] or 'no_p2' for row in case['comparisons'])
            if group and case['group'] != group or category and category not in categories:
                continue
            if verdict and (review['verdict'] if review else 'unreviewed') != verdict:
                continue
            if q and q.casefold() not in (identity+' '+case['title_vi']+' '+case['group_label']).casefold():
                continue
            rows.append(dict(control_id=identity, group=case['group'], group_label=case['group_label'],
                title_vi=case['title_vi'], transactions=len(case['transactions']), matched=case['matched'],
                categories=dict(categories), review=review))
        return dict(items=rows, total=len(rows))

    def detail(self, identity):
        if identity not in self.controls:
            raise KeyError('Không có tình huống đối chứng này.')
        result = deepcopy(self.controls[identity])
        events = [r for r in self.history() if r['snapshot_id'] == self.snapshot_id and r['control_id'] == identity]
        result.update(snapshot_id=self.snapshot_id, history=events, review=events[-1] if events else None)
        return result

    def save_review(self, body):
        if self.readonly:
            raise PermissionError('Bản nghiệm thu này chỉ đọc.')
        if body.get('snapshot_id') != self.snapshot_id:
            raise RuntimeError('Bộ đối chứng đã thay đổi. Tải lại trang trước khi lưu.')
        identity = body.get('control_id')
        verdict, reviewer, reason = (body.get(key) for key in ('verdict', 'reviewer', 'reason'))
        if identity not in self.controls or verdict not in VERDICTS:
            raise ValueError('Tình huống hoặc kết quả nghiệm thu không hợp lệ.')
        if (not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 100
                or not isinstance(reason, str) or not reason.strip() or len(reason) > 2000):
            raise ValueError('Nhập người nghiệm thu (tối đa 100 ký tự) và lý do (tối đa 2.000 ký tự).')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            history = self._history(db)
            current = [r for r in history if r['snapshot_id'] == self.snapshot_id and r['control_id'] == identity]
            if body.get('expected_hash') != (current[-1]['event_hash'] if current else ''):
                raise RuntimeError('Tình huống vừa có kết quả nghiệm thu mới. Tải lại trước khi lưu.')
            event = dict(id=history[-1]['id']+1 if history else 1, snapshot_id=self.snapshot_id,
                control_id=identity, verdict=verdict, reviewer=reviewer.strip(), reason=reason.strip(),
                reviewed_at=datetime.now(timezone.utc).isoformat(), previous_hash=history[-1]['event_hash'] if history else '')
            event['event_hash'] = digest(event)
            db.execute('INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?,?)', tuple(event.values()))
        return event
