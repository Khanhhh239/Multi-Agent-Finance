"""Role routing and current workflow reminders; no login or recipient discovery."""
import json
from datetime import datetime,timedelta
from .case_identity import digest,scope_hash
from .review_roles import SETTING,workflow_events,LABELS
from .information_requests import InformationRequests
from .review_store import TZ

VERSION='notification-roles-20261027-v1'
EVENTS={
    'high_priority':'Hồ sơ ưu tiên cao','weekly':'Tóm tắt tuần',
    'review_submitted':'Có kết quả chờ kiểm tra','review_returned':'Hồ sơ được trả lại',
    'review_finalized':'Đã kiểm tra kết quả','documents_received':'Tài liệu đã nhận, cần rà lại',
    'case_overdue':'Hồ sơ quá hạn rà soát','review_overdue':'Quá hạn kiểm tra kết quả',
    'rework_overdue':'Quá hạn rà bổ sung','documents_overdue':'Quá hạn bổ sung tài liệu'}
DEFAULT_REMINDERS=dict(review_due_hours=48,rework_due_hours=48,repeat_hours=24,escalate_after_hours=48)


def validate_roles(raw,reminders):
    if raw is not None:
        if not isinstance(raw,dict):raise ValueError('Role recipients must be scoped by company')
        for company,people in raw.items():
            if not isinstance(company,str) or not company.strip() or company=='*' or not isinstance(people,list) or len(people)>100:
                raise ValueError('Invalid role recipient company/list')
            users=set()
            for person in people:
                if not isinstance(person,dict) or set(person)-{'user_id','person_id','display_name','role','channels'}:
                    raise ValueError('Invalid role recipient')
                if person.get('role') not in LABELS:raise ValueError('Unknown notification role')
                for field in ('user_id','person_id'):
                    value=person.get(field)
                    if not isinstance(value,str) or not value.strip() or value!=value.strip() or len(value)>100:
                        raise ValueError('Role recipients need stable user and person IDs')
                if person['user_id'] in users:raise ValueError('Duplicate notification user within company')
                users.add(person['user_id'])
                name=person.get('display_name',person['user_id'])
                if not isinstance(name,str) or not name.strip() or len(name)>100:raise ValueError('Invalid recipient name')
                channels=person.get('channels')
                if not isinstance(channels,dict) or not channels or set(channels)-{'email','zalo'}:raise ValueError('Invalid role channels')
                if not any(channels.values()):raise ValueError('Role recipient needs a destination')
    if not isinstance(reminders,dict) or set(reminders)-set(DEFAULT_REMINDERS):raise ValueError('Unknown reminder policy')
    result=DEFAULT_REMINDERS|reminders
    if any(type(value) is not int or not 1<=value<=720 for value in result.values()):raise ValueError('Reminder hours must be integers from 1 to 720')
    return result


class BusinessNotifications:
    def __init__(self,owner,db):
        self.owner=owner;self.store=owner.store;self.config=owner.config
        self.enabled=self.config['role_recipients'] is not None or bool(db.execute('SELECT 1 FROM settings WHERE key=?',(SETTING,)).fetchone())
        db.executescript('''
            CREATE TABLE IF NOT EXISTS notification_business_runs(mode TEXT,scenario TEXT,company_id TEXT,PRIMARY KEY(mode,scenario,company_id));
            CREATE TABLE IF NOT EXISTS notification_business_seen(mode TEXT,scenario TEXT,event_key TEXT,eligible INTEGER,PRIMARY KEY(mode,scenario,event_key));
            CREATE TABLE IF NOT EXISTS notification_routing_gaps(mode TEXT,scenario TEXT,event_key TEXT,company_id TEXT,kind TEXT,case_id TEXT,
                reason TEXT,first_at TEXT,last_at TEXT,resolved_at TEXT DEFAULT '',PRIMARY KEY(mode,scenario,event_key));
        ''')

    def routes(self,company,kind,source=None):
        people=self.config['role_recipients'] or {};people=people.get(company,[]);source=source or {}
        primary=source.get('primary') or {};actor=source.get('actor') or {}
        same=lambda p,a:p['person_id'].strip().casefold()==str(a.get('person_id','')).strip().casefold()
        accountants=[p for p in people if p['role']=='accountant']
        checkers=[p for p in people if p['role']=='chief_accountant' and not same(p,primary)]
        directors=[p for p in people if p['role']=='director' and not same(p,primary)]
        original=[p for p in accountants if p['user_id']==primary.get('user_id') and same(p,primary)]
        if kind in {'review_submitted','review_overdue','weekly'}:selected=checkers or directors
        elif kind in {'review_returned','rework_overdue'}:selected=original
        elif kind=='review_finalized':
            selected=original
            if source.get('decision') in {'confirmed_suspicion','non_compliance','confirmed_fraud'}:
                selected=selected+[p for p in directors if not same(p,actor)]
        else:selected=accountants
        if source.get('escalated'):selected=selected+directors
        destinations={}
        for person in selected:
            for channel,values in person['channels'].items():
                for recipient in values:
                    canonical=recipient.casefold() if channel=='email' else recipient
                    target=destinations.setdefault((channel,canonical),dict(channel=channel,recipient=recipient,users=[]))
                    if person['user_id'] not in [p['user_id'] for p in target['users']]:
                        target['users'].append({k:person[k] for k in ('user_id','person_id','role')}|dict(display_name=person.get('display_name',person['user_id'])))
        return list(destinations.values())

    def missing_route(self,db,scenario,company,kind,event_key,case_id,now):
        key=digest([VERSION,company,kind,event_key])
        db.execute('INSERT INTO notification_routing_gaps VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(mode,scenario,event_key) DO UPDATE SET last_at=excluded.last_at,resolved_at=\'\'',
            (self.owner.mode,scenario,key,company,kind,case_id,'recipient_unassigned',now.isoformat(),now.isoformat(),''))

    def describe(self,scenario,now,db):
        cases={r['case_id']:r for r in (json.loads(row[0]) for row in db.execute('SELECT data FROM cases WHERE scenario=?',(scenario,)))}
        latest,_=self.store.feedback_state(scenario)
        all_events=workflow_events(db) if db.execute("SELECT 1 FROM sqlite_master WHERE name='review_workflow_events'").fetchone() else []
        requests=InformationRequests.history(db)
        sources={};policy=self.config['reminders']
        def emit(kind,case,key,**values):
            event_key=digest([VERSION,kind,case['case_id'],scope_hash(case),key])
            sources[event_key]=dict(kind=kind,case=case,key=event_key,**values)
        def reminder(kind,case,due,phase,**values):
            if now<=due:return
            bucket=int((now-due).total_seconds()//(3600*policy['repeat_hours']))
            emit(kind,case,[phase,due.isoformat(),bucket],due_at=due.isoformat(),
                 escalated=(now-due)>=timedelta(hours=policy['escalate_after_hours']),reminder=True,**values)
        for case in cases.values():
            if datetime.fromisoformat(case['last_seen_at']).astimezone(TZ)>now:continue
            scope=scope_hash(case)
            events=[e for e in all_events if e['scenario']==scenario and e['case_id']==case['case_id'] and e['case_scope_hash']==scope]
            primary=next((e for e in reversed(events) if e['kind']=='primary_submitted'),None)
            last=events[-1] if events else None
            feedback=latest.get(case['case_id']);closed=self.store.status(feedback)=='closed'
            final=last if last and last['kind']=='finalized' else None
            intent=(next((e for e in events if e['event_hash']==final['data']['intent_hash']),None) if final else
                    last if last and last['kind']=='finalization_requested' and feedback and feedback.get('workflow_approval_id')==last['event_hash'] else None)
            final_done=bool(intent)
            context=dict(primary=primary['actor'] if primary else {})
            if final_done:
                emit('review_finalized',case,intent['event_hash'],actor=intent['actor'],decision=intent['data']['decision'],**context)
            if closed:continue
            relevant={}
            for event in requests:
                if event['scenario']==scenario and event['company_id']==case['company_id'] and event['case_scope_hash']==scope:
                    relevant[event['request_id']]=event
            active=[e for e in relevant.values() if e['status'] in {'open','received'}]
            for request in active:
                if request['status']=='received':
                    emit('documents_received',case,request['event_hash'],request_id=request['request_id'],**context)
                reminder('documents_overdue',case,datetime.fromisoformat(request['due_at']),request['event_hash'],request_id=request['request_id'],**context)
            if last and last['kind']=='returned':
                emit('review_returned',case,last['event_hash'],actor=last['actor'],**context)
                reminder('rework_overdue',case,datetime.fromisoformat(last['event_at'])+timedelta(hours=policy['rework_due_hours']),last['event_hash'],**context)
            elif primary and not final_done:
                emit('review_submitted',case,primary['event_hash'],actor=primary['actor'],**context)
                reminder('review_overdue',case,datetime.fromisoformat(primary['event_at'])+timedelta(hours=policy['review_due_hours']),primary['event_hash'],**context)
            elif final_done and not active:
                reminder('rework_overdue',case,datetime.fromisoformat(intent['event_at'])+timedelta(hours=policy['rework_due_hours']),intent['event_hash'],**context)
            elif not active:
                due=case.get('sla_due_at')
                if due:reminder('case_overdue',case,datetime.fromisoformat(due),last['event_hash'] if last else scope,**context)
        return sources

    def plan(self,scenario,now,company_ids=None):
        if not self.enabled:return
        owner=self.owner;mode=owner.mode;day=now.date().isoformat()
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            sources=self.describe(scenario,now,db)
            sources={key:s for key,s in sources.items() if company_ids is None or s['case']['company_id'] in company_ids}
            companies={r[0] for r in db.execute('SELECT DISTINCT company_id FROM cases WHERE scenario=?',(scenario,)) if company_ids is None or r[0] in company_ids}
            initial={c:not db.execute('SELECT 1 FROM notification_business_runs WHERE mode=? AND scenario=? AND company_id=?',(mode,scenario,c)).fetchone() for c in companies}
            for key,source in sorted(sources.items(),key=lambda pair:(pair[1].get('reminder',False),pair[1]['case'].get('sla_due_at',''),pair[0])):
                case=source['case'];company=case['company_id'];kind=source['kind']
                if not source.get('reminder'):
                    db.execute('INSERT OR IGNORE INTO notification_business_seen VALUES(?,?,?,?)',
                               (mode,scenario,key,int(not initial[company] or self.config['replay_existing'])))
                    if not db.execute('SELECT eligible FROM notification_business_seen WHERE mode=? AND scenario=? AND event_key=?',(mode,scenario,key)).fetchone()[0]:continue
                routes=self.routes(company,kind,source)
                queued={(r['channel'],r['recipient'].casefold() if r['channel']=='email' else r['recipient']) for r in db.execute(
                    'SELECT channel,recipient FROM notification_outbox WHERE mode=? AND scenario=? AND event_key=?',(mode,scenario,key))}
                if routes and all((r['channel'],r['recipient'].casefold() if r['channel']=='email' else r['recipient']) in queued for r in routes):
                    db.execute('UPDATE notification_routing_gaps SET resolved_at=? WHERE mode=? AND scenario=? AND event_key=? AND resolved_at=\'\'',(now.isoformat(),mode,scenario,key));continue
                existing=db.execute('SELECT 1 FROM notification_allocations WHERE mode=? AND day=? AND scenario=? AND case_id=?',(mode,day,scenario,case['case_id'])).fetchone()
                used=db.execute('SELECT COUNT(*) FROM notification_allocations WHERE mode=? AND day=? AND scenario=? AND company_id=?',(mode,day,scenario,company)).fetchone()[0]
                reason='recipient_unassigned' if not routes else 'daily_budget' if not existing and used>=min(self.config['daily_budget'],self.store.budget()) else ''
                if reason:
                    db.execute('INSERT INTO notification_routing_gaps VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(mode,scenario,event_key) DO UPDATE SET reason=excluded.reason,last_at=excluded.last_at,resolved_at=\'\'',
                        (mode,scenario,key,company,kind,case['case_id'],reason,now.isoformat(),now.isoformat(),''));continue
                db.execute('UPDATE notification_routing_gaps SET resolved_at=? WHERE mode=? AND scenario=? AND event_key=? AND resolved_at=\'\'',(now.isoformat(),mode,scenario,key))
                if not existing:db.execute('INSERT INTO notification_allocations VALUES(?,?,?,?,?,?)',(mode,day,scenario,company,case['case_id'],scope_hash(case)))
                owner._enqueue(db,scenario,company,kind,key,[dict(case,notification_scope=scope_hash(case))],now,source=source)
            for company in companies:db.execute('INSERT OR IGNORE INTO notification_business_runs VALUES(?,?,?)',(mode,scenario,company))
            for row in db.execute('SELECT event_key,company_id FROM notification_routing_gaps WHERE mode=? AND scenario=? AND resolved_at=\'\'',(mode,scenario)).fetchall():
                if (company_ids is None or row['company_id'] in company_ids) and row['event_key'] not in sources:
                    db.execute('UPDATE notification_routing_gaps SET resolved_at=? WHERE mode=? AND scenario=? AND event_key=?',(now.isoformat(),mode,scenario,row['event_key']))

    def valid(self,job,now,db):
        payload=json.loads(job['payload']);kind=job['kind']
        source=None
        if kind not in {'high_priority','weekly'}:
            source=self.describe(job['scenario'],now,db).get(job['event_key'])
            if source is None:return False
        expected={(r['channel'],r['recipient'].casefold() if r['channel']=='email' else r['recipient']) for r in self.routes(job['company_id'],kind,source)}
        return (job['channel'],job['recipient'].casefold() if job['channel']=='email' else job['recipient']) in expected

    def payload(self,scenario,company,kind,cases,now,source):
        source=source or {};label=EVENTS[kind]
        body=[f'Công ty {company} · {label}.','Mở hồ sơ để đối chiếu bằng chứng và thực hiện bước tiếp theo.']
        if source.get('due_at'):body.append('Hạn xử lý: '+source['due_at']+' (giờ Việt Nam).')
        if source.get('escalated'):body.append('Đã đến mốc báo giám đốc theo chính sách nhắc quá hạn.')
        body.extend(row['case_id']+' · '+self.owner.case_link(scenario,row['case_id']) for row in cases)
        return dict(subject=('[GIẢ LẬP] ' if self.config['dry_run'] else '')+'Sổ Soát · '+company+' · '+label,
                    body='\n'.join(body),case_refs=[dict(case_id=r['case_id'],scope_hash=r['notification_scope']) for r in cases],
                    as_of=now.isoformat(),total_open=0,policy_version=VERSION,event_label=label,
                    due_at=source.get('due_at'),escalated=bool(source.get('escalated')))
