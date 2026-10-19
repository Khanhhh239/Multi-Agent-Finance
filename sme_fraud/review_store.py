"""Read-only detection snapshot cache and daily review admission for the local UI."""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .feedback import DECISIONS, feedback_lock, read_audit, write_review_states
from .case_identity import (digest, scope_hash, values, load_lineage, write_lineage,
                            plan_lineage, queue_hash, resolve, feedback_view)

TZ = timezone(timedelta(hours=7))
SCHEMA_VERSION = '4'
PRIORITIES = {'cao_nhat': 3, 'cao': 2, 'trung_binh': 1, 'thap': 0}
BUDGET_MINUTES = {5: 120, 10: 240}


def csv_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        yield from csv.DictReader(stream)


def compact(row):
    return json.dumps(row, ensure_ascii=False, separators=(',', ':'))


def source_fingerprint(data, report):
    names = [data / name for name in ('transactions.csv', 'companies.csv', 'employees.csv', 'vendors.csv',
                                      'journal_documents.csv', 'journal_lines.csv')]
    names += [report / name for name in ('case_queue.csv', 'rule_hits.jsonl', 'rule_coverage.json', 'case_events.csv')]
    names += [path for path in (data/'customers.csv', report/'evidence_findings.jsonl', report/'batch_events.jsonl') if path.is_file()]
    digest = hashlib.sha256(SCHEMA_VERSION.encode())
    for path in names:
        digest.update(str(path.resolve()).encode())
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
    return digest.hexdigest()


class ReviewStore:
    def __init__(self, data_root, reports_root, database, scenarios=None, clock=None):
        self.data_root, self.reports_root, self.database = Path(data_root), Path(reports_root), Path(database)
        self.clock = clock or (lambda: datetime.now(TZ))
        self.scenarios = scenarios or [tag for tag in ('001', '003', '005')
                                      if (self.reports_root / f'sme_fraud_{tag}' / 'case_queue.csv').is_file()]
        if not self.scenarios or any(tag not in ('001', '003', '005') for tag in self.scenarios):
            raise ValueError('No supported detection snapshots found')
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._schema()

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.database, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _schema(self):
        with self.connection() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS metadata(scenario TEXT PRIMARY KEY, fingerprint TEXT, prepared_at TEXT);
                CREATE TABLE IF NOT EXISTS companies(scenario TEXT, company_id TEXT, data TEXT, PRIMARY KEY(scenario,company_id));
                CREATE TABLE IF NOT EXISTS entities(scenario TEXT, entity_id TEXT, kind TEXT, data TEXT, PRIMARY KEY(scenario,entity_id));
                CREATE TABLE IF NOT EXISTS cases(scenario TEXT, case_id TEXT, company_id TEXT, priority INTEGER,
                    score INTEGER, opened_at TEXT, data TEXT, PRIMARY KEY(scenario,case_id));
                CREATE INDEX IF NOT EXISTS cases_queue ON cases(scenario,company_id,priority DESC,score DESC,opened_at);
                CREATE TABLE IF NOT EXISTS members(scenario TEXT,case_id TEXT,transaction_id TEXT, PRIMARY KEY(scenario,case_id,transaction_id));
                CREATE TABLE IF NOT EXISTS transactions(scenario TEXT,transaction_id TEXT,data TEXT,PRIMARY KEY(scenario,transaction_id));
                CREATE TABLE IF NOT EXISTS hits(scenario TEXT,transaction_id TEXT,rule_id TEXT,data TEXT);
                CREATE INDEX IF NOT EXISTS hit_lookup ON hits(scenario,transaction_id);
                CREATE TABLE IF NOT EXISTS documents(scenario TEXT,document_id TEXT,data TEXT,PRIMARY KEY(scenario,document_id));
                CREATE TABLE IF NOT EXISTS lines(scenario TEXT,document_id TEXT,data TEXT);
                CREATE INDEX IF NOT EXISTS line_lookup ON lines(scenario,document_id);
                CREATE TABLE IF NOT EXISTS admissions(day TEXT,scenario TEXT,company_id TEXT,case_id TEXT,admitted_at TEXT,
                    work_minutes INTEGER DEFAULT 0,work_type TEXT DEFAULT 'initial_review',
                    PRIMARY KEY(day,scenario,case_id));
                CREATE TABLE IF NOT EXISTS source_findings(scenario TEXT,case_id TEXT,data TEXT,PRIMARY KEY(scenario,case_id));
                CREATE TABLE IF NOT EXISTS batch_events(scenario TEXT,event_id TEXT,data TEXT,PRIMARY KEY(scenario,event_id));
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
                INSERT OR IGNORE INTO settings VALUES('daily_budget','5');
                INSERT OR IGNORE INTO settings VALUES('daily_capacity_minutes','120');
            ''')
            admission_columns = {r[1] for r in db.execute('PRAGMA table_info(admissions)')}
            if 'work_minutes' not in admission_columns:
                db.execute("ALTER TABLE admissions ADD COLUMN work_minutes INTEGER DEFAULT 0")
            if 'work_type' not in admission_columns:
                db.execute("ALTER TABLE admissions ADD COLUMN work_type TEXT DEFAULT 'initial_review'")
            current_budget = int(db.execute("SELECT value FROM settings WHERE key='daily_budget'").fetchone()[0])
            db.execute("UPDATE settings SET value=? WHERE key='daily_capacity_minutes'",
                       (str(BUDGET_MINUTES.get(current_budget, BUDGET_MINUTES[5])),))

    def report(self, scenario):
        if scenario not in self.scenarios:
            raise ValueError('Unknown snapshot')
        return self.reports_root / f'sme_fraud_{scenario}'

    def prepare(self):
        for scenario in self.scenarios:
            report = self.report(scenario)
            data = self.data_root / f'sme_fraud_{scenario}'
            fingerprint = source_fingerprint(data, report)
            with feedback_lock(report), self.connection() as db:
                current = db.execute('SELECT fingerprint FROM metadata WHERE scenario=?', (scenario,)).fetchone()
                required_mapping = db.execute('SELECT value FROM settings WHERE key=?', ('case_identity_required:' + scenario,)).fetchone()
                if required_mapping and not (report / 'case_identity.json').is_file():
                    raise ValueError('Case identity mapping missing; restore it before rebuilding review state')
                lineage = load_lineage(report, allow_stale=True)
                if current and current['fingerprint'] == fingerprint and lineage.get('queue_sha256') == queue_hash(report):
                    print(f'Cached review snapshot {scenario}', flush=True)
                    continue
                print(f'Preparing review snapshot {scenario}...', flush=True)
                previous = [json.loads(r[0]) for r in db.execute('SELECT data FROM cases WHERE scenario=?', (scenario,))]
                if not previous:
                    previous = list(lineage['current'].values())
                for case in previous:
                    if not case.get('evidence_digest'):
                        case['evidence_digest'] = self._evidence_digest(db, scenario, case)
                audit = read_audit(report / 'feedback_audit.jsonl')
                # This cache can be rebuilt; human decisions remain in the source report audit log.
                for table in ('metadata', 'companies', 'entities', 'cases', 'members', 'transactions', 'hits', 'documents', 'lines', 'source_findings', 'batch_events'):
                    db.execute(f'DELETE FROM {table} WHERE scenario=?', (scenario,))
                companies = list(csv_rows(data / 'companies.csv'))
                db.executemany('INSERT INTO companies VALUES(?,?,?)', [(scenario, r['company_id'], compact(r)) for r in companies])
                for filename, identifier, kind in [('employees.csv', 'employee_id', 'employee'), ('vendors.csv', 'vendor_id', 'vendor')]:
                    latest, revisions = {}, {}
                    for row in csv_rows(data / filename):
                        version = row[identifier], row['recorded_at']
                        if version in revisions and revisions[version] != row:
                            raise ValueError('Conflicting review entity revision')
                        revisions[version] = row
                        if row[identifier] not in latest or row['recorded_at'] > latest[row[identifier]]['recorded_at']:
                            latest[row[identifier]] = row
                    db.executemany('INSERT INTO entities VALUES(?,?,?,?)',
                        [(scenario, r[identifier], kind, compact(r)) for r in latest.values()])
                if (data/'customers.csv').is_file():
                    db.executemany('INSERT INTO entities VALUES(?,?,?,?)',
                        [(scenario, r['customer_id'], 'customer', compact(r)) for r in csv_rows(data/'customers.csv')])
                required, members = set(), set()
                source_case_keys = {}
                batch_case_keys = {}
                for case in csv_rows(report / 'case_queue.csv'):
                    identifiers = json.loads(case['transaction_ids'])
                    case_type = case.get('case_type', 'transaction') or 'transaction'
                    batch_ids = json.loads(case.get('batch_event_ids') or '[]')
                    if len(batch_ids) != len(set(batch_ids)) or (case_type == 'batch' and not batch_ids):
                        raise ValueError('Invalid batch case binding')
                    if (case_type != 'source' and not identifiers) or len(set(identifiers)) != len(identifiers):
                        raise ValueError('Invalid case membership')
                    case.update(max_score=int(case['max_score']), observation_count=int(case['observation_count']),
                                estimated_minutes=int(case.get('estimated_minutes', 20) or 20),
                                requires_rereview=int(case.get('requires_rereview', 0) or 0),
                                case_type=case_type, transaction_ids=identifiers, batch_event_ids=batch_ids,
                                rule_ids=case['rule_ids'].split('|'))
                    for event_id in batch_ids:
                        batch_case_keys.setdefault(event_id, []).append(case)
                    db.execute('INSERT INTO cases VALUES(?,?,?,?,?,?,?)',
                        (scenario, case['case_id'], case['company_id'], PRIORITIES[case['priority']], case['max_score'], case['opened_at'], compact(case)))
                    db.executemany('INSERT INTO members VALUES(?,?,?)', [(scenario, case['case_id'], i) for i in identifiers])
                    required.update(identifiers)
                    members.update(identifiers)
                    if case_type == 'source':
                        if len(case['rule_ids']) != 1 or not case.get('source_scope'):
                            raise ValueError('Invalid source case binding')
                        source_case_keys[(case['company_id'], case['rule_ids'][0],
                                          case['source_scope'], case['last_seen_at'])] = case['case_id']
                if source_case_keys:
                    findings_path = report/'evidence_findings.jsonl'
                    if not findings_path.is_file():
                        raise ValueError('Source cases require evidence_findings.jsonl')
                    found_source = set()
                    with findings_path.open(encoding='utf-8') as stream:
                        for line in stream:
                            finding = json.loads(line)
                            key = (finding.get('company_id'), finding.get('rule_id'),
                                   finding.get('scope'), finding.get('cutoff_at'))
                            case_id = source_case_keys.get(key)
                            if case_id:
                                db.execute('INSERT OR REPLACE INTO source_findings VALUES(?,?,?)',
                                           (scenario, case_id, compact(finding)))
                                found_source.add(case_id)
                    if found_source != set(source_case_keys.values()):
                        raise ValueError('Missing latest evidence for a source case')
                if batch_case_keys:
                    batch_path = report/'batch_events.jsonl'
                    if not batch_path.is_file():
                        raise ValueError('Batch cases require batch_events.jsonl')
                    found_batch = {}
                    with batch_path.open(encoding='utf-8') as stream:
                        for line in stream:
                            event = json.loads(line)
                            event_id = event['event_id']
                            if event_id not in batch_case_keys:
                                continue
                            if event_id in found_batch and found_batch[event_id] != event:
                                raise ValueError('Conflicting batch evidence')
                            if event.get('phase') != 'batch_closed' or any(
                                    event['company_id'] != case['company_id'] or
                                    not case['opened_at'] <= event['detected_at'] <= case['last_seen_at']
                                    for case in batch_case_keys[event_id]):
                                raise ValueError('Invalid batch evidence scope or time')
                            found_batch[event_id] = event
                            required.update(event['transaction_ids'])
                            required.update(event['related_transaction_ids'])
                            db.execute('INSERT OR REPLACE INTO batch_events VALUES(?,?,?)',
                                       (scenario, event_id, compact(event)))
                    if set(found_batch) != set(batch_case_keys):
                        raise ValueError('Missing evidence for a batch case')
                with (report / 'rule_hits.jsonl').open(encoding='utf-8') as stream:
                    for line in stream:
                        hit = json.loads(line)
                        if hit['transaction_id'] in members:
                            db.execute('INSERT INTO hits VALUES(?,?,?,?)',
                                       (scenario, hit['transaction_id'], hit['rule_id'], compact(hit)))
                            required.update(hit['related_transaction_ids'])
                documents, found = set(), set()
                for row in csv_rows(data / 'transactions.csv'):
                    if row['transaction_id'] in required:
                        row['amount_vnd'] = int(row['amount_vnd'])
                        row['approval_limit_vnd'] = int(row['approval_limit_vnd'])
                        db.execute('INSERT INTO transactions VALUES(?,?,?)', (scenario, row['transaction_id'], compact(row)))
                        found.add(row['transaction_id'])
                        documents.update(x for x in (row['journal_document_id'], row['linked_document_id']) if x)
                if found != required:
                    raise ValueError('Missing evidence transaction in source dataset')
                for row in csv_rows(data / 'journal_documents.csv'):
                    if row['document_id'] in documents:
                        db.execute('INSERT INTO documents VALUES(?,?,?)', (scenario, row['document_id'], compact(row)))
                for row in csv_rows(data / 'journal_lines.csv'):
                    if row['document_id'] in documents:
                        row.update(debit_vnd=int(row['debit_vnd']), credit_vnd=int(row['credit_vnd']))
                        db.execute('INSERT INTO lines VALUES(?,?,?)', (scenario, row['document_id'], compact(row)))
                incoming = [json.loads(r[0]) for r in db.execute('SELECT data FROM cases WHERE scenario=?', (scenario,))]
                for case in incoming:
                    case['evidence_digest'] = self._evidence_digest(db, scenario, case)
                lineage, equivalent_pairs = plan_lineage(previous, incoming, lineage, audit, queue_hash(report))
                for old_id, new_id in equivalent_pairs:
                    if old_id == new_id:
                        continue
                    for admission in db.execute('SELECT * FROM admissions WHERE scenario=? AND case_id=?', (scenario, old_id)).fetchall():
                        occupied = db.execute('SELECT * FROM admissions WHERE scenario=? AND case_id=? AND day=?',
                                              (scenario, new_id, admission['day'])).fetchone()
                        if occupied:
                            raise ValueError('Conflicting review admissions during case ID migration')
                    db.execute('UPDATE admissions SET case_id=? WHERE scenario=? AND case_id=?', (new_id, scenario, old_id))
                for case in incoming:
                    db.execute('UPDATE cases SET data=? WHERE scenario=? AND case_id=?', (compact(case), scenario, case['case_id']))
                write_lineage(report, lineage)
                write_review_states(report, lineage['current'], audit, lineage)
                db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('case_identity_required:' + scenario, '1'))
                db.execute('INSERT INTO metadata VALUES(?,?,?)', (scenario, fingerprint, self.clock().isoformat()))
            print(f'Ready {scenario}: {len(members):,} alerts, {len(required):,} evidence observations', flush=True)

    @staticmethod
    def _evidence_digest(db, scenario, case):
        payload, identifiers, documents = [], set(values(case.get('transaction_ids'))), set()
        for tid in values(case.get('transaction_ids')):
            hits = [json.loads(r[0]) for r in db.execute('SELECT data FROM hits WHERE scenario=? AND transaction_id=?', (scenario, tid))]
            payload.append([tid, sorted(hits, key=digest)])
            for hit in hits:
                identifiers.update(hit['related_transaction_ids'])
        for event_id in values(case.get('batch_event_ids')):
            event = db.execute('SELECT data FROM batch_events WHERE scenario=? AND event_id=?', (scenario, event_id)).fetchone()
            event = json.loads(event[0]) if event else None
            payload.append([event_id, event])
            if event:
                identifiers.update(event['transaction_ids'])
                identifiers.update(event['related_transaction_ids'])
        for tid in sorted(identifiers):
            tx = db.execute('SELECT data FROM transactions WHERE scenario=? AND transaction_id=?', (scenario, tid)).fetchone()
            tx = json.loads(tx[0]) if tx else None
            payload.append([tid, tx])
            if tx:
                documents.update(value for value in (tx.get('journal_document_id'), tx.get('linked_document_id')) if value)
        for document_id in sorted(documents):
            document = db.execute('SELECT data FROM documents WHERE scenario=? AND document_id=?', (scenario, document_id)).fetchone()
            lines = [json.loads(r[0]) for r in db.execute('SELECT data FROM lines WHERE scenario=? AND document_id=?', (scenario, document_id))]
            payload.append([document_id, json.loads(document[0]) if document else None, sorted(lines, key=digest)])
        finding = db.execute('SELECT data FROM source_findings WHERE scenario=? AND case_id=?', (scenario, case['case_id'])).fetchone()
        if finding:
            payload.append(json.loads(finding[0]))
        return digest(payload)

    def audit_events(self, scenario):
        directory = self.report(scenario)
        with feedback_lock(directory):
            try:
                return read_audit(directory / 'feedback_audit.jsonl')
            except (ValueError, KeyError) as error:
                raise ValueError('Nhật ký kết luận không còn đầy đủ hoặc đã bị thay đổi. Kiểm tra bản lưu trước khi tiếp tục rà soát.') from error

    def feedback_state(self, scenario):
        events = self.audit_events(scenario)
        lineage = self.identity_state(scenario)
        return feedback_view(events, lineage['current'], lineage)

    def identity_state(self, scenario):
        directory = self.report(scenario)
        with self.connection() as db:
            required = db.execute('SELECT value FROM settings WHERE key=?', ('case_identity_required:' + scenario,)).fetchone()
        if required and not (directory / 'case_identity.json').is_file():
            raise ValueError('Case identity mapping missing; restore it before reading review state')
        return load_lineage(directory)

    @staticmethod
    def status(feedback):
        return 'awaiting_information' if feedback and feedback['decision'] == 'information_gap' else 'closed' if feedback else 'new'

    def budget(self):
        with self.connection() as db:
            return int(db.execute("SELECT value FROM settings WHERE key='daily_budget'").fetchone()[0])

    def set_budget(self, value):
        if value not in (5, 10):
            raise ValueError('Daily review budget must be 5 or 10')
        with self.connection() as db:
            db.execute("UPDATE settings SET value=? WHERE key='daily_budget'", (str(value),))
            db.execute("UPDATE settings SET value=? WHERE key='daily_capacity_minutes'", (str(BUDGET_MINUTES[value]),))
        return value

    def capacity_minutes(self):
        with self.connection() as db:
            return int(db.execute("SELECT value FROM settings WHERE key='daily_capacity_minutes'").fetchone()[0])

    def metadata(self):
        scenario = '003' if '003' in self.scenarios else self.scenarios[0]
        with self.connection() as db:
            companies = [json.loads(r[0]) for r in db.execute('SELECT data FROM companies WHERE scenario=? ORDER BY company_id', (scenario,))]
        return dict(scenarios=self.scenarios, default_scenario=scenario, companies=companies, daily_budget=self.budget(),
                    daily_capacity_minutes=self.capacity_minutes(),
                    review_day=self.clock().astimezone(TZ).date().isoformat(), dataset_period='2024–2025',
                    synthetic=True, review_scope='cases_and_minutes_per_company_per_snapshot_per_local_day')

    def admissions(self, scenario):
        today = self.clock().astimezone(TZ).date().isoformat()
        with self.connection() as db:
            rows = db.execute('SELECT case_id,company_id,work_minutes,work_type FROM admissions WHERE scenario=? AND day=?', (scenario, today)).fetchall()
        admitted = {r['case_id']: dict(work_minutes=r['work_minutes'], work_type=r['work_type']) for r in rows}
        used_cases = dict(Counter(r['company_id'] for r in rows))
        used_minutes = {company: sum(r['work_minutes'] for r in rows if r['company_id'] == company)
                        for company in {r['company_id'] for r in rows}}
        return admitted, used_cases, used_minutes

    def list_cases(self, scenario, company='', status='active', priority='', rule='', query='', offset=0, limit=30):
        self.report(scenario)
        if status not in {'active', 'new', 'awaiting_information', 'closed', 'all'} or priority and priority not in PRIORITIES:
            raise ValueError('Invalid queue filter')
        if offset < 0 or not 1 <= limit <= 100 or len(query) > 200:
            raise ValueError('Invalid pagination/search')
        latest, history = self.feedback_state(scenario)
        lineage = self.identity_state(scenario)
        reviewed_ids = {r['case_id'] for r in history}
        changed = {r['resolved_case_id'] for r in history if not r['applies_to_current_scope']}
        changed.update(r['new_case_id'] for r in lineage['relations']
                       if r['relation'] != 'equivalent' and r['old_case_id'] in reviewed_ids)
        admitted, used, used_minutes = self.admissions(scenario)
        budget = self.budget()
        capacity = self.capacity_minutes()
        with self.connection() as db:
            records = db.execute('SELECT data FROM cases WHERE scenario=? ORDER BY priority DESC,score DESC,opened_at,case_id', (scenario,)).fetchall()
            entities = {r['entity_id']: json.loads(r['data']) for r in db.execute('SELECT entity_id,data FROM entities WHERE scenario=?', (scenario,))}
        output, counts = [], dict(new=0, awaiting_information=0, closed=0, high_priority=0,
                                  source=0, backlog=0, backlog_minutes=0, rereview=0)
        for record in records:
            row = json.loads(record[0])
            if company and row['company_id'] != company:
                continue
            feedback = latest.get(row['case_id'])
            row['status'] = self.status(feedback)
            row['requires_rereview'] = int(bool(row.get('requires_rereview')) or row['case_id'] in changed and not feedback)
            counts[row['status']] += 1
            counts['high_priority'] += row['status'] != 'closed' and row['priority'] in {'cao', 'cao_nhat'}
            counts['source'] += row.get('case_type') == 'source'
            if row['status'] != 'closed':
                counts['backlog'] += 1
                counts['backlog_minutes'] += int(row.get('estimated_minutes', 20))
                counts['rereview'] += row['status'] == 'awaiting_information' or bool(row['requires_rereview'])
            if status == 'active' and row['status'] == 'closed' or status not in {'active', 'all'} and row['status'] != status:
                continue
            if priority and row['priority'] != priority or rule and rule not in row['rule_ids']:
                continue
            # Entity names and IDs are searchable; labels/ground truth are never loaded.
            member_ids = [node.split(':', 1)[-1] for node in values(row.get('cluster_members'))]
            related = [entities.get(i, {}) for i in member_ids or row['entity'].split(':')[-1:]]
            if query and query.casefold() not in (' '.join(str(row[k]) for k in ('case_id', 'explanation_vi', 'entity'))
                                                  + ' ' + row.get('source_scope', '')
                                                  + ' '.join(r.get('name', r.get('full_name', '')) for r in related)).casefold():
                continue
            row['admitted_today'] = row['case_id'] in admitted
            row['work_type_today'] = admitted.get(row['case_id'], {}).get('work_type', '')
            row['budget_remaining'] = max(0, budget - used.get(row['company_id'], 0))
            row['minutes_remaining'] = max(0, capacity - used_minutes.get(row['company_id'], 0))
            row['owner_name'] = entities.get(row['owner_id'], {}).get('full_name', row['owner_id'])
            row.pop('transaction_ids')
            output.append(row)
        return dict(items=output[offset:offset + limit], total=len(output), offset=offset, limit=limit, counts=counts,
                    budget=dict(limit=budget, capacity_minutes=capacity, used_by_company=used,
                                used_minutes_by_company=used_minutes,
                                day=self.clock().astimezone(TZ).date().isoformat()))

    def admit(self, scenario, case_id):
        self.report(scenario)
        lineage = self.identity_state(scenario)
        case_id = resolve(case_id, lineage['aliases'])
        now = self.clock().astimezone(TZ)
        day = now.date().isoformat()
        latest, _ = self.feedback_state(scenario)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            saved = db.execute('SELECT company_id,data FROM cases WHERE scenario=? AND case_id=?', (scenario, case_id)).fetchone()
            if not saved:
                raise KeyError('Unknown case')
            case = json.loads(saved['data'])
            feedback = latest.get(case_id)
            budget = int(db.execute("SELECT value FROM settings WHERE key='daily_budget'").fetchone()[0])
            capacity = int(db.execute("SELECT value FROM settings WHERE key='daily_capacity_minutes'").fetchone()[0])
            if self.status(feedback) == 'closed':
                return dict(case_id=case_id, used=0, limit=budget, day=day,
                            work_minutes=0, work_type='read_only', used_minutes=0,
                            capacity_minutes=capacity)
            existing = db.execute('SELECT work_minutes,work_type FROM admissions WHERE day=? AND scenario=? AND case_id=?', (day, scenario, case_id)).fetchone()
            used = db.execute('SELECT COUNT(*) FROM admissions WHERE day=? AND scenario=? AND company_id=?', (day, scenario, saved['company_id'])).fetchone()[0]
            used_minutes = db.execute('SELECT COALESCE(SUM(work_minutes),0) FROM admissions WHERE day=? AND scenario=? AND company_id=?', (day, scenario, saved['company_id'])).fetchone()[0]
            prior = db.execute('SELECT COUNT(*) FROM admissions WHERE scenario=? AND case_id=?', (scenario, case_id)).fetchone()[0]
            if feedback and feedback['decision'] == 'information_gap':
                work_type = 'rereview'
            elif prior:
                work_type = 'continued_review'
            else:
                work_type = 'source_initial' if case.get('case_type') == 'source' else 'initial_review'
            base_minutes = int(case.get('estimated_minutes', 20))
            work_minutes = base_minutes if work_type in {'initial_review', 'source_initial'} else max(10, (base_minutes+1)//2)
            if not existing and (used >= budget or used_minutes + work_minutes > capacity):
                raise OverflowError(f'Không còn đủ ngân sách hôm nay cho công ty này ({used}/{budget} hồ sơ, {used_minutes}/{capacity} phút).')
            if not existing:
                db.execute('INSERT INTO admissions(day,scenario,company_id,case_id,admitted_at,work_minutes,work_type) VALUES(?,?,?,?,?,?,?)',
                           (day, scenario, saved['company_id'], case_id, now.isoformat(), work_minutes, work_type))
                used += 1
                used_minutes += work_minutes
            else:
                work_minutes, work_type = existing['work_minutes'], existing['work_type']
        return dict(case_id=case_id, used=used, limit=budget, day=day,
                    work_minutes=work_minutes, work_type=work_type,
                    used_minutes=used_minutes, capacity_minutes=capacity)

    def detail(self, scenario, case_id):
        self.report(scenario)
        latest, events = self.feedback_state(scenario)
        lineage = load_lineage(self.report(scenario))
        case_id = resolve(case_id, lineage['aliases'])
        relations = [r for r in lineage['relations'] if case_id in (r['old_case_id'], r['new_case_id'])]
        predecessors = {r['old_case_id'] for r in relations if r['new_case_id'] == case_id}
        with self.connection() as db:
            saved = db.execute('SELECT data FROM cases WHERE scenario=? AND case_id=?', (scenario, case_id)).fetchone()
            if not saved:
                archives = [r for r in lineage['archives'].values() if r['case_id'] == case_id]
                if not archives:
                    raise KeyError('Unknown case')
                archived = max(archives, key=lambda r: (r['last_seen_at'], scope_hash(r)))
                old_latest, old_events = feedback_view(self.audit_events(scenario), {case_id: archived}, lineage)
                archived = dict(archived, archived=True, status=self.status(old_latest.get(case_id)),
                                feedback=old_latest.get(case_id), owner_name=archived.get('owner_id', ''))
                return dict(case=archived, transactions=[], hits=[], documents=[], graph_edges=[], entities={},
                            source_finding=None, batch_events=[], case_events=[],
                            feedback_history=[r for r in old_events if r['resolved_case_id'] == case_id],
                            related_feedback_history=[], case_lineage=relations,
                            archive_notice='Hồ sơ lịch sử chỉ đọc. Phạm vi đã thay đổi; mở hồ sơ kế thừa để rà soát. Bằng chứng thuộc snapshot cũ chưa được nạp trong cache hiện tại.',
                            audit_integrity='passed', audit_note='Nhật ký gốc được giữ nguyên.')
            case = json.loads(saved[0])
            source_row = db.execute('SELECT data FROM source_findings WHERE scenario=? AND case_id=?',
                                    (scenario, case_id)).fetchone()
            source_finding = json.loads(source_row[0]) if source_row else None
            batch_events = [json.loads(db.execute('SELECT data FROM batch_events WHERE scenario=? AND event_id=?',
                                                  (scenario, event_id)).fetchone()[0])
                            for event_id in case.get('batch_event_ids', [])]
            transactions, hits, documents = [], [], {}
            for tid in case['transaction_ids']:
                tx = json.loads(db.execute('SELECT data FROM transactions WHERE scenario=? AND transaction_id=?', (scenario, tid)).fetchone()[0])
                transactions.append(tx)
                hits.extend(json.loads(r[0]) for r in db.execute('SELECT data FROM hits WHERE scenario=? AND transaction_id=?', (scenario, tid)))
                for document_id in (tx['journal_document_id'], tx['linked_document_id']):
                    if document_id and document_id not in documents:
                        document = db.execute('SELECT data FROM documents WHERE scenario=? AND document_id=?', (scenario, document_id)).fetchone()
                        if document:
                            documents[document_id] = dict(document=json.loads(document[0]),
                                lines=[json.loads(r[0]) for r in db.execute('SELECT data FROM lines WHERE scenario=? AND document_id=?', (scenario, document_id))])
            entities = {}
            for record in db.execute('SELECT entity_id,data FROM entities WHERE scenario=?', (scenario,)):
                entity = json.loads(record['data'])
                if (entity['company_id'] == case['company_id'] and
                        entity.get('recorded_at', '') <= case['last_seen_at']):
                    entities[record['entity_id']] = entity
        case['status'] = self.status(latest.get(case_id))
        case['feedback'] = latest.get(case_id)
        case['requires_rereview'] = int(bool(case.get('requires_rereview')) or not latest.get(case_id) and any(
            r['resolved_case_id'] == case_id and not r['applies_to_current_scope'] or r['case_id'] in predecessors for r in events))
        case['owner_name'] = entities.get(case['owner_id'], {}).get('full_name', case['owner_id'])
        hits.sort(key=lambda h: (-h['hard_trigger'], -h['points'], h['detected_at'], h['rule_id']))
        for tx in transactions:
            tx['vendor_name'] = entities.get(tx['vendor_id'], {}).get('name', '')
            tx['employee_name'] = entities.get(tx['employee_id'], {}).get('full_name', '')
            tx['creator_name'] = entities.get(tx['creator_id'], {}).get('full_name', tx['creator_id'])
            tx['approver_name'] = entities.get(tx['approver_id'], {}).get('full_name', tx['approver_id'])
        paths = [edge for hit in [*hits, *batch_events] for edge in hit['graph_path']]
        case_events = [r for r in csv_rows(self.report(scenario) / 'case_events.csv') if r['case_id'] == case_id]
        return dict(case=case, transactions=sorted(transactions, key=lambda r: r['posted_at']), hits=hits,
                    documents=list(documents.values()), graph_edges=paths, entities=entities,
                    source_finding=source_finding, batch_events=batch_events,
                    feedback_history=[r for r in events if r['resolved_case_id'] == case_id], case_events=case_events,
                    related_feedback_history=[r for r in events if r['case_id'] in predecessors and r['resolved_case_id'] != case_id],
                    case_lineage=relations,
                    audit_integrity='passed', audit_note='Chuỗi hash kiểm tra tính liên tục; không phải chữ ký số.')

    def transaction(self, scenario, transaction_id):
        self.report(scenario)
        with self.connection() as db:
            row = db.execute('SELECT data FROM transactions WHERE scenario=? AND transaction_id=?', (scenario, transaction_id)).fetchone()
        if not row:
            raise KeyError('Evidence transaction is not in this review snapshot')
        return json.loads(row[0])

    def save_feedback(self, scenario, case_id, decision, reviewer, reason, expected_hash=None):
        self.report(scenario)
        lineage = load_lineage(self.report(scenario))
        case_id = resolve(case_id, lineage['aliases'])
        if (decision not in DECISIONS or not isinstance(reviewer, str) or not isinstance(reason, str)
                or not reviewer.strip() or not reason.strip() or len(reviewer) > 100 or len(reason) > 2000):
            raise ValueError('Người rà soát tối đa 100 ký tự; lý do tối đa 2.000 ký tự.')
        self.admit(scenario, case_id)
        # Same source log/lock as CLI. Optimistic checks avoid overwriting another reviewer.
        directory = self.report(scenario)
        from .feedback import _record_feedback
        with feedback_lock(directory):
            lineage = load_lineage(directory)
            case_id = resolve(case_id, lineage['aliases'])
            latest, _ = feedback_view(read_audit(directory / 'feedback_audit.jsonl'), lineage['current'], lineage)
            actual_hash = latest[case_id]['event_hash'] if case_id in latest else ''
            if expected_hash != actual_hash:
                raise RuntimeError('Hồ sơ vừa có kết luận mới. Tải lại hồ sơ trước khi lưu.')
            return _record_feedback(directory, case_id, decision, reviewer, reason, self.clock().isoformat(timespec='seconds'))
