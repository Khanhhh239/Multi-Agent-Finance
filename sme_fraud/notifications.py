"""Company-scoped alert budget, durable outbox, weekly digest and delivery receipts."""
from collections import Counter
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import os
import re
from urllib.parse import parse_qs, urlencode, urlsplit

from .case_identity import digest, scope_hash
from .review_store import TZ, PRIORITIES
from .notification_channels import TRANSPORTS, DeliveryError


def notification_config(raw=None):
    raw = raw or {}
    allowed = {'dry_run', 'replay_existing', 'daily_budget', 'weekly_weekday', 'weekly_hour',
               'recipients', 'smtp', 'zalo', 'case_url', 'max_attempts'}
    if not isinstance(raw, dict) or set(raw)-allowed:
        raise ValueError('Unknown notification configuration')
    cfg = dict(dry_run=True, daily_budget=10, weekly_weekday=0, weekly_hour=8,
               recipients={}, smtp={}, zalo={}, case_url='http://127.0.0.1:8765/', max_attempts=4)
    cfg.update(raw)
    cfg.setdefault('replay_existing', cfg['dry_run'])
    for field in ('dry_run', 'replay_existing'):
        if type(cfg[field]) is not bool:
            raise ValueError('Notification switches must be booleans')
    if not cfg['dry_run'] and cfg['replay_existing']:
        raise ValueError('Historical replay is available only in dry-run')
    for field, valid in (('daily_budget', (5, 10)), ('weekly_weekday', range(7)),
                         ('weekly_hour', range(24)), ('max_attempts', range(1, 11))):
        if type(cfg[field]) is not int or cfg[field] not in valid:
            raise ValueError('Invalid notification '+field)
    parsed = urlsplit(cfg['case_url'])
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Invalid case UI base URL')
    if not isinstance(cfg['recipients'], dict):
        raise ValueError('Recipients must be scoped by company')
    for company, channels in cfg['recipients'].items():
        if not isinstance(company, str) or not company or not isinstance(channels, dict) or set(channels)-{'email', 'zalo'}:
            raise ValueError('Invalid notification company/channel')
        for channel, recipients in channels.items():
            if not isinstance(recipients, list) or len(recipients) > 20:
                raise ValueError('Invalid recipient list')
            for recipient in recipients:
                if not isinstance(recipient, str) or not recipient or len(recipient) > 254 or any(c.isspace() for c in recipient):
                    raise ValueError('Invalid notification recipient')
                if channel == 'email' and (recipient.count('@') != 1 or any(c in recipient for c in '<>,;')):
                    raise ValueError('Use one plain email address per recipient')
    if not cfg['dry_run']:
        if not cfg['recipients']:
            raise ValueError('Live notifications require explicit company recipients')
        smtp = cfg['smtp']
        if any(channels.get('email') for channels in cfg['recipients'].values()):
            if not smtp.get('host') or not smtp.get('from_address') or smtp.get('tls', 'starttls') not in {'starttls', 'ssl'}:
                raise ValueError('Live email requires SMTP host, sender and TLS')
            if '\n' in smtp['from_address'] or '\r' in smtp['from_address']:
                raise ValueError('Invalid SMTP sender')
    return cfg


class Notifications:
    def __init__(self, store, config=None, transports=None):
        self.store, self.config = store, notification_config(config)
        self.mode = 'dry_run' if self.config['dry_run'] else 'live'
        self.transports = TRANSPORTS if transports is None else transports
        with store.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS notification_seen(mode TEXT,scenario TEXT,case_id TEXT,scope_hash TEXT,
                    first_seen_at TEXT, PRIMARY KEY(mode,scenario,case_id,scope_hash));
                CREATE TABLE IF NOT EXISTS notification_candidates(mode TEXT,scenario TEXT,case_id TEXT,scope_hash TEXT,
                    discovered_at TEXT, PRIMARY KEY(mode,scenario,case_id,scope_hash));
                CREATE TABLE IF NOT EXISTS notification_allocations(mode TEXT,day TEXT,scenario TEXT,company_id TEXT,
                    case_id TEXT,scope_hash TEXT, PRIMARY KEY(mode,day,scenario,case_id));
                CREATE TABLE IF NOT EXISTS notification_outbox(job_id TEXT PRIMARY KEY,mode TEXT,scenario TEXT,
                    company_id TEXT,kind TEXT,event_key TEXT,channel TEXT,recipient TEXT,payload TEXT,
                    status TEXT,attempts INTEGER DEFAULT 0,next_at TEXT,claimed_at TEXT DEFAULT '',
                    provider_id TEXT DEFAULT '',error_code TEXT DEFAULT '',created_at TEXT);
                CREATE INDEX IF NOT EXISTS notification_due ON notification_outbox(mode,status,next_at);
                CREATE TABLE IF NOT EXISTS notification_receipts(receipt_id TEXT PRIMARY KEY,provider_id TEXT,
                    event_name TEXT,received_at TEXT);
                CREATE TABLE IF NOT EXISTS notification_runs(mode TEXT,scenario TEXT,initialized_at TEXT,
                    PRIMARY KEY(mode,scenario));
            ''')

    def targets(self, company):
        channels = self.config['recipients'].get(company)
        if channels is None and self.config['dry_run'] and not self.config['recipients']:
            channels = {'email':['simulation@example.invalid'], 'zalo':['SIMULATION_GMF']}
        return [(channel, recipient) for channel, recipients in (channels or {}).items() for recipient in sorted(set(recipients))]

    def current(self, scenario, now):
        latest, _ = self.store.feedback_state(scenario)
        with self.store.connection() as db:
            rows = [json.loads(r[0]) for r in db.execute('SELECT data FROM cases WHERE scenario=? ORDER BY priority DESC,score DESC,opened_at,case_id', (scenario,))]
        return [dict(row, notification_scope=scope_hash(row)) for row in rows
                if self.store.status(latest.get(row['case_id'])) != 'closed'
                and datetime.fromisoformat(row['last_seen_at']).astimezone(TZ) <= now]

    def _payload(self, scenario, company, kind, cases, now, total=0):
        subject = ('[GIẢ LẬP] ' if self.config['dry_run'] else '')+'Sổ Soát · '+company+' · '+('Hồ sơ ưu tiên cao' if kind == 'high_priority' else 'Tóm tắt tuần')
        lines = [f'Công ty {company}. '+('Có hồ sơ cần đối chiếu sớm.' if kind == 'high_priority' else f'Đang mở {total} hồ sơ; dưới đây là các hồ sơ trong ngân sách ngày.'),
                 'Dấu hiệu cần rà soát, chưa phải kết luận gian lận.']
        for row in cases:
            link = self.case_link(scenario, row['case_id'])
            lines.append(f"{row['case_id']} · {'cao nhất' if row['priority']=='cao_nhat' else 'cao' if row['priority']=='cao' else 'thông thường'} · {link}")
        body = '\n'.join(lines)
        return dict(subject=subject, body=body, case_refs=[dict(case_id=r['case_id'], scope_hash=r['notification_scope']) for r in cases],
                    as_of=now.isoformat(), total_open=total)

    def case_link(self, scenario, case_id):
        return self.config['case_url']+'#'+urlencode(dict(scenario=scenario, case=case_id))

    def preview_links(self, scenario, job):
        """Rebase dry-run navigation for this UI without rewriting outbox history."""
        if not self.config['dry_run']:
            return
        links = {ref['case_id']: self.case_link(scenario, ref['case_id']) for ref in job['case_refs']}
        def replace(match):
            query = parse_qs(urlsplit(match[0]).fragment)
            case_id = query.get('case', [''])[0]
            if query == {'scenario': [scenario], 'case': [case_id]} and case_id in links:
                return links[case_id]
            return match[0]
        job['preview_body'] = re.sub(r'https?://[^\s]+', replace, job['body'])
        job['case_links'] = [dict(case_id=case_id, url=url) for case_id, url in links.items()]

    def _enqueue(self, db, scenario, company, kind, event_key, cases, now, total=0):
        if not cases and kind == 'high_priority':
            return
        payload = self._payload(scenario,company,kind,cases,now,total)
        for channel, recipient in self.targets(company):
            job_id = digest([self.mode, scenario, company, kind, event_key, channel, recipient])
            db.execute('INSERT OR IGNORE INTO notification_outbox(job_id,mode,scenario,company_id,kind,event_key,channel,recipient,payload,status,next_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (job_id,self.mode,scenario,company,kind,event_key,channel,recipient,json.dumps(payload,ensure_ascii=False),'pending',now.isoformat(),now.isoformat()))

    def plan(self, scenario):
        self.store.report(scenario)
        now = self.store.clock().astimezone(TZ)
        day = now.date().isoformat()
        rows = self.current(scenario, now)
        known = {(r['case_id'],r['notification_scope']):r for r in rows}
        budget = min(self.config['daily_budget'], self.store.budget())
        weekly_date = now.date()-timedelta(days=(now.weekday()-self.config['weekly_weekday'])%7)
        weekly_at = datetime.combine(weekly_date, datetime.min.time(), TZ).replace(hour=self.config['weekly_hour'])
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            initial = db.execute('SELECT 1 FROM notification_runs WHERE mode=? AND scenario=?',(self.mode,scenario)).fetchone() is None
            for row in rows:
                cursor = db.execute('INSERT OR IGNORE INTO notification_seen VALUES(?,?,?,?,?)',
                    (self.mode,scenario,row['case_id'],row['notification_scope'],now.isoformat()))
                if cursor.rowcount and (not initial or self.config['replay_existing']) and PRIORITIES[row['priority']] >= 2:
                    db.execute('INSERT OR IGNORE INTO notification_candidates VALUES(?,?,?,?,?)',
                        (self.mode,scenario,row['case_id'],row['notification_scope'],now.isoformat()))
            db.execute('INSERT OR IGNORE INTO notification_runs VALUES(?,?,?)',(self.mode,scenario,now.isoformat()))
            # Cancel stale pending alerts after a conclusion, split/merge or
            # evidence change. Sent notifications remain an immutable history.
            for job in db.execute("SELECT job_id,payload FROM notification_outbox WHERE mode=? AND scenario=? AND kind='high_priority' AND status='pending'",(self.mode,scenario)).fetchall():
                if any((ref['case_id'],ref['scope_hash']) not in known for ref in json.loads(job['payload'])['case_refs']):
                    db.execute("UPDATE notification_outbox SET status='cancelled',error_code='case_closed_or_changed' WHERE job_id=?",(job['job_id'],))
            candidates = {(r['case_id'],r['scope_hash']) for r in db.execute('SELECT case_id,scope_hash FROM notification_candidates WHERE mode=? AND scenario=?',(self.mode,scenario))}
            allocated_ever = {(r['case_id'],r['scope_hash']) for r in db.execute('SELECT case_id,scope_hash FROM notification_allocations WHERE mode=? AND scenario=?',(self.mode,scenario))}
            allocated_today = {r['case_id'] for r in db.execute('SELECT case_id FROM notification_allocations WHERE mode=? AND scenario=? AND day=?',(self.mode,scenario,day))}
            used = Counter(r[0] for r in db.execute('SELECT company_id FROM notification_allocations WHERE mode=? AND scenario=? AND day=?',(self.mode,scenario,day)))
            selected = []
            for row in rows:
                key, company = (row['case_id'],row['notification_scope']), row['company_id']
                if key not in candidates or key in allocated_ever or row['case_id'] in allocated_today or used[company] >= budget or not self.targets(company):
                    continue
                db.execute('INSERT INTO notification_allocations VALUES(?,?,?,?,?,?)',(self.mode,day,scenario,company,row['case_id'],row['notification_scope']))
                used[company] += 1
                allocated_today.add(row['case_id'])
                selected.append(row)
                self._enqueue(db,scenario,company,'high_priority',digest(key),[row],now)
            # Weekly digests use the SAME daily allocation pool, so email and
            # Zalo, retries and digests do not multiply the case budget.
            week_key = weekly_date.isoformat()
            if now >= weekly_at:
                for company in sorted({r['company_id'] for r in rows}):
                    if db.execute("SELECT 1 FROM notification_outbox WHERE mode=? AND scenario=? AND company_id=? AND kind='weekly' AND event_key=?",(self.mode,scenario,company,week_key)).fetchone():
                        continue
                    company_rows = [r for r in rows if r['company_id'] == company]
                    digest_rows = []
                    for row in company_rows:
                        if row['case_id'] in allocated_today:
                            digest_rows.append(row)
                        elif used[company] < budget and self.targets(company):
                            db.execute('INSERT INTO notification_allocations VALUES(?,?,?,?,?,?)',(self.mode,day,scenario,company,row['case_id'],row['notification_scope']))
                            allocated_today.add(row['case_id'])
                            used[company] += 1
                            digest_rows.append(row)
                    self._enqueue(db,scenario,company,'weekly',week_key,digest_rows,now,total=len(company_rows))
        return dict(new_high_priority_cases=len(selected), daily_case_limit=budget, mode=self.mode)

    def dispatch(self, *, allow_live=False, limit=100):
        if not self.config['dry_run'] and not allow_live:
            raise PermissionError('Live sending is disabled in the UI; use the explicitly configured worker')
        now = self.store.clock().astimezone(TZ)
        with self.store.connection() as db:
            # A crashed in-flight send has an unknown outcome; do not auto-resend.
            db.execute("UPDATE notification_outbox SET status='uncertain',error_code='worker_interrupted' WHERE mode=? AND status='sending' AND claimed_at<?",(self.mode,(now-timedelta(minutes=5)).isoformat()))
        sent = 0
        for _ in range(limit):
            with self.store.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute("SELECT * FROM notification_outbox WHERE mode=? AND status='pending' AND next_at<=? ORDER BY created_at,job_id LIMIT 1",(self.mode,now.isoformat())).fetchone()
                if row is None:
                    break
                job = dict(row)
                if (job['channel'],job['recipient']) not in self.targets(job['company_id']):
                    db.execute("UPDATE notification_outbox SET status='cancelled',error_code='recipient_removed' WHERE job_id=?",(job['job_id'],))
                    continue
                current_rows = self.current(job['scenario'],now)
                current = {(r['case_id'],r['notification_scope']):r for r in current_rows}
                refs = json.loads(job['payload'])['case_refs']
                if job['kind'] == 'weekly':
                    # Refresh counts and remove closed/changed references without
                    # allocating extra cases or dropping the whole weekly digest.
                    remaining = [current[(r['case_id'],r['scope_hash'])] for r in refs if (r['case_id'],r['scope_hash']) in current]
                    total = sum(r['company_id']==job['company_id'] for r in current_rows)
                    job['payload'] = json.dumps(self._payload(job['scenario'],job['company_id'],'weekly',remaining,now,total),ensure_ascii=False)
                    db.execute('UPDATE notification_outbox SET payload=? WHERE job_id=?',(job['payload'],job['job_id']))
                elif any((r['case_id'],r['scope_hash']) not in current for r in refs):
                    db.execute("UPDATE notification_outbox SET status='cancelled',error_code='case_closed_or_changed' WHERE job_id=?",(job['job_id'],))
                    continue
                db.execute("UPDATE notification_outbox SET status='sending',attempts=attempts+1,claimed_at=? WHERE job_id=?",(now.isoformat(),job['job_id']))
            status, provider, error, delay = 'sent', '', '', 0
            try:
                if self.config['dry_run']:
                    status, provider = 'simulated', 'simulation:'+job['job_id']
                else:
                    provider = self.transports[job['channel']](dict(job,**json.loads(job['payload'])),self.config,now)
                sent += 1
            except DeliveryError as failure:
                error = failure.code
                status = 'uncertain' if failure.uncertain else 'pending' if failure.retryable and job['attempts']+1 < self.config['max_attempts'] else 'failed'
                delay = max(failure.retry_after, min(3600,60*2**job['attempts']))
            except Exception:
                status, error = 'uncertain', 'delivery_outcome_unknown'
            with self.store.connection() as db:
                db.execute('UPDATE notification_outbox SET status=?,provider_id=?,error_code=?,next_at=? WHERE job_id=?',
                    (status,provider,error,(now+timedelta(seconds=delay)).isoformat(),job['job_id']))
        return dict(processed=sent, mode=self.mode)

    def status(self, scenario):
        self.store.report(scenario)
        day = self.store.clock().astimezone(TZ).date().isoformat()
        with self.store.connection() as db:
            counts = dict(Counter(r[0] for r in db.execute('SELECT status FROM notification_outbox WHERE mode=? AND scenario=?',(self.mode,scenario))))
            used = dict(Counter(r[0] for r in db.execute('SELECT company_id FROM notification_allocations WHERE mode=? AND scenario=? AND day=?',(self.mode,scenario,day))))
            jobs = [dict(r) for r in db.execute('SELECT job_id,company_id,kind,channel,payload,status,attempts,error_code,created_at FROM notification_outbox WHERE mode=? AND scenario=? ORDER BY created_at DESC,job_id LIMIT 30',(self.mode,scenario))]
            receipts = dict(Counter(r[0] for r in db.execute('SELECT r.event_name FROM notification_receipts r JOIN notification_outbox o ON o.provider_id=r.provider_id WHERE o.mode=? AND o.scenario=?',(self.mode,scenario))))
        for job in jobs:
            job.update(json.loads(job.pop('payload')))
            self.preview_links(scenario, job)
        return dict(mode=self.mode, day=day, daily_case_limit=min(self.config['daily_budget'],self.store.budget()),
                    used_by_company=used, counts=counts, receipt_counts=receipts, items=jobs, weekly_weekday=self.config['weekly_weekday'],
                    weekly_hour=self.config['weekly_hour'], budget_scope='company_snapshot_local_day')

    def receive_zalo(self, content, signature):
        settings = self.config.get('zalo', {})
        secret = os.environ.get(settings.get('webhook_secret_env', 'SME_ZALO_WEBHOOK_SECRET'), '')
        app_id = settings.get('app_id', '')
        if not secret or not app_id:
            raise PermissionError('Zalo webhook is not configured')
        event = json.loads(content)
        if not isinstance(event,dict) or str(event.get('app_id','')) != str(app_id):
            raise PermissionError('Invalid Zalo application')
        stamp = str(event.get('timestamp',''))
        if not stamp.isdigit() or abs(self.store.clock().timestamp()-int(stamp)/1000) > 300:
            raise PermissionError('Expired webhook timestamp')
        expected = 'mac='+hashlib.sha256(str(app_id).encode()+content+stamp.encode()+secret.encode()).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise PermissionError('Invalid webhook signature')
        name = event.get('event_name')
        if name not in {'user_received_message', 'user_seen_message'}:
            return dict(accepted=True, matched=0)
        ids = event.get('message', {}).get('msg_ids', [])
        if not isinstance(ids,list) or len(ids) > 100 or any(not isinstance(i,str) for i in ids):
            raise ValueError('Invalid delivery receipt IDs')
        matched = 0
        with self.store.connection() as db:
            for provider in ids:
                exists = db.execute("SELECT 1 FROM notification_outbox WHERE mode='live' AND channel='zalo' AND provider_id=? AND status='sent'",(provider,)).fetchone()
                if exists:
                    inserted = db.execute('INSERT OR IGNORE INTO notification_receipts VALUES(?,?,?,?)',
                        (digest([provider,name]),provider,name,self.store.clock().isoformat()))
                    matched += inserted.rowcount
        return dict(accepted=True, matched=matched)
