"""Company-scoped blinded review forms and server-measured, pausable work time."""
from datetime import datetime, timezone
import hashlib
import io
import csv
import json
import secrets

from .feature_contract import digest
from .ml_review_packets import load_packet, review_metrics
from .company_ml_comparison import SOURCE_FIELDS, REVIEW_FIELDS
from .review_roles import require_permission

LEASE_SECONDS=30
MAX_MS=24*60*60*1000
FORM_FIELDS={'useful','business_action','rationale','evidence_refs'}


class MLReview:
    def __init__(self,store,roots=(),*,clock=None,qa=False):
        self.store,self.clock,self.qa=store,clock or (lambda:datetime.now(timezone.utc)),qa
        with store.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS ml_review_packets(packet_id TEXT PRIMARY KEY, metadata TEXT, report TEXT);
                CREATE TABLE IF NOT EXISTS ml_review_units(packet_id TEXT, review_id TEXT, company_id TEXT, data TEXT,
                    PRIMARY KEY(packet_id,review_id));
                CREATE TABLE IF NOT EXISTS ml_review_work(packet_id TEXT, review_id TEXT, data TEXT,
                    PRIMARY KEY(packet_id,review_id));
                CREATE TABLE IF NOT EXISTS ml_review_events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    packet_id TEXT, review_id TEXT, data TEXT);
                CREATE INDEX IF NOT EXISTS ml_review_event_unit ON ml_review_events(packet_id,review_id,sequence);
            ''')
        for root in roots:self.import_packet(root)

    def import_packet(self,root):
        packet=load_packet(root);pid=packet['packet_id'];report=packet['report'];plan=report['plan']
        metadata=dict(packet_id=pid,created_at=plan['created_at'],scenario=plan['scenario'],
            source_kind=plan['source_kind'],companies=plan['companies'],windows=plan['windows'],
            review_count=plan['review_count_per_company_model'],manifest_sha256=packet['manifest_sha256'],report_digest=digest(report))
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT metadata,report FROM ml_review_packets WHERE packet_id=?',(pid,)).fetchone()
            if existing:
                if json.loads(existing['metadata'])!=metadata or json.loads(existing['report'])!=report:
                    raise ValueError('Gói đã nhập không còn khớp bản đã khóa.')
                return pid
            db.execute('INSERT INTO ml_review_packets VALUES(?,?,?)',(pid,json.dumps(metadata),json.dumps(report)))
            for rid,unit in packet['units'].items():
                db.execute('INSERT INTO ml_review_units VALUES(?,?,?,?)',(pid,rid,unit['company_id'],json.dumps(unit)))
        return pid

    @staticmethod
    def _permission(principal,company=None):
        return require_permission(principal,'ml_review',company)

    def _packet(self,db,pid,principal):
        self._permission(principal)
        row=db.execute('SELECT * FROM ml_review_packets WHERE packet_id=?',(pid,)).fetchone()
        if not row:raise KeyError('Không tìm thấy gói phiếu rà.')
        meta=json.loads(row['metadata'])
        report=json.loads(row['report'])
        if digest(report)!=meta['report_digest']:raise ValueError('Kế hoạch phiếu đã thay đổi ngoài luồng đã khóa.')
        if not set(meta['companies'])&set(principal.company_ids):raise PermissionError('Gói phiếu ngoài phạm vi doanh nghiệp của tài khoản.')
        return meta,report

    def _unit(self,db,pid,rid,principal):
        self._packet(db,pid,principal)
        row=db.execute('SELECT data FROM ml_review_units WHERE packet_id=? AND review_id=?',(pid,rid)).fetchone()
        if not row:raise KeyError('Không tìm thấy phiếu rà trong gói đã khóa.')
        unit=json.loads(row['data']);self._permission(principal,unit['company_id'])
        if unit['evidence_sha256']!=digest(unit['evidence']):raise ValueError('Bằng chứng trong phiếu không còn khớp.')
        return unit

    def _work(self,db,pid,rid):
        row=db.execute('SELECT data FROM ml_review_work WHERE packet_id=? AND review_id=?',(pid,rid)).fetchone()
        if not row:return None
        state=json.loads(row['data'])
        last=db.execute('SELECT data FROM ml_review_events WHERE packet_id=? AND review_id=? ORDER BY sequence DESC LIMIT 1',(pid,rid)).fetchone()
        if not last:raise ValueError('Phiếu có dữ liệu nhưng thiếu nhật ký rà.')
        event=json.loads(last[0]);checksum=event.pop('event_hash')
        if digest(event)!=checksum or event['state_hash']!=digest(state):raise ValueError('Dữ liệu/nhật ký phiếu rà không còn khớp.')
        return state

    def _write(self,db,pid,rid,state,principal,action,credited_ms=0):
        last=db.execute('SELECT data FROM ml_review_events WHERE packet_id=? AND review_id=? ORDER BY sequence DESC LIMIT 1',(pid,rid)).fetchone()
        event=dict(action=action,actor=dict(user_id=principal.user_id,person_id=principal.person_id,role=principal.role),
            at=self.clock().isoformat(),revision=state['revision'],credited_ms=credited_ms,state_hash=digest(state),
            previous_hash=json.loads(last[0])['event_hash'] if last else '')
        if action in {'draft','submit'}:event['form']=state['form']
        event['event_hash']=digest(event)
        db.execute('INSERT OR REPLACE INTO ml_review_work VALUES(?,?,?)',(pid,rid,json.dumps(state)))
        db.execute('INSERT INTO ml_review_events(packet_id,review_id,data) VALUES(?,?,?)',(pid,rid,json.dumps(event)))

    def _view(self,state,principal):
        if not state:return dict(revision=0,status='unstarted',owner=None,can_edit=True,form={},timer=dict(running=False,elapsed_ms=0,confirmed_ms=0,expired=False))
        elapsed=max(0,(self.clock()-datetime.fromisoformat(state['last_tick'])).total_seconds()) if state.get('last_tick') else 0
        expired=bool(state['running'] and elapsed>LEASE_SECONDS)
        running=bool(state['running'] and not expired)
        return dict(revision=state['revision'],status=state['status'],owner=state['owner'],
            can_edit=(state['owner']['user_id'],state['owner']['person_id'])==(principal.user_id,principal.person_id),form=state['form'],submitted_at=state.get('submitted_at'),
            timer=dict(running=running,expired=expired,confirmed_ms=state['confirmed_ms'],
                       elapsed_ms=min(MAX_MS,state['confirmed_ms']+(int(elapsed*1000) if running else 0))))

    def overview(self,principal):
        self._permission(principal);packets=[]
        with self.store.connection() as db:
            db.execute('BEGIN')
            for row in db.execute('SELECT metadata FROM ml_review_packets ORDER BY rowid DESC'):
                meta=json.loads(row[0]);companies=sorted(set(meta['companies'])&set(principal.company_ids))
                if companies:packets.append({k:meta[k] for k in ('packet_id','created_at','source_kind','windows','review_count')}|dict(companies=companies))
        return dict(packets=packets,principal=dict(user_id=principal.user_id,display_name=principal.display_name,role=principal.role),
                    can_summarize=principal.role in {'chief_accountant','director'},qa=self.qa)

    def units(self,pid,principal,company=''):
        with self.store.connection() as db:
            db.execute('BEGIN')
            meta,_=self._packet(db,pid,principal)
            allowed=set(meta['companies'])&set(principal.company_ids)
            if company:
                self._permission(principal,company);allowed&={company}
            result=[]
            for row in db.execute('SELECT * FROM ml_review_units WHERE packet_id=? ORDER BY review_id',(pid,)):
                if row['company_id'] not in allowed:continue
                unit=json.loads(row['data']);view=self._view(self._work(db,pid,row['review_id']),principal)
                result.append(dict(review_id=unit['review_id'],company_id=unit['company_id'],transaction_id=unit['transaction_id'],
                                   status=view['status'],owner=view['owner'],confirmed_ms=view['timer']['confirmed_ms']))
        return dict(items=result,total=len(result),reviewed=sum(r['status']=='reviewed' for r in result))

    def detail(self,pid,rid,principal):
        with self.store.connection() as db:
            db.execute('BEGIN')
            unit=self._unit(db,pid,rid,principal);state=self._work(db,pid,rid)
        evidence=unit['evidence']
        # Expose only public transaction facts, never private selections/model names/scores.
        public={k:evidence.get(k) for k in ('review_cutoff_exclusive','source_kind','limitations')}
        public['source_record']={k:v for k,v in evidence['source_record'].items() if k in SOURCE_FIELDS}
        return dict(packet_id=pid,review_id=rid,company_id=unit['company_id'],transaction_id=unit['transaction_id'],
                    evidence_sha256=unit['evidence_sha256'],evidence=public,work=self._view(state,principal),qa=self.qa)

    def _edit(self,db,pid,rid,principal,expected_revision):
        self._unit(db,pid,rid,principal);state=self._work(db,pid,rid)
        if type(expected_revision) is not int or expected_revision<0:raise ValueError('Thiếu phiên bản phiếu hợp lệ.')
        if (state['revision'] if state else 0)!=expected_revision:raise RuntimeError('Phiếu vừa đổi ở phiên khác. Tải lại trước khi tiếp tục; bản nháp đang nhập được giữ trên màn hình.')
        if state and (state['owner']['user_id'],state['owner']['person_id'])!=(principal.user_id,principal.person_id):raise PermissionError('Phiếu đã được người khác nhận rà; không thể ghi đè.')
        return state

    def timer(self,pid,rid,principal,*,expected_revision,action,timer_token=''):
        if action not in {'start','pause','heartbeat','recover'}:raise ValueError('Thao tác đồng hồ không hợp lệ.')
        token=None;now=self.clock();notice=''
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE');state=self._edit(db,pid,rid,principal,expected_revision)
            if not state:
                if action!='start':raise ValueError('Bắt đầu đồng hồ trước khi thao tác.')
                state=dict(revision=0,status='draft',form={},owner=dict(user_id=principal.user_id,person_id=principal.person_id,
                    display_name=principal.display_name),confirmed_ms=0,running=False,last_tick=None,token_hash=None)
            elapsed=max(0,(now-datetime.fromisoformat(state['last_tick'])).total_seconds()) if state['last_tick'] else 0
            live=state['running'] and elapsed<=LEASE_SECONDS
            credited=0
            if action=='start':
                if state['confirmed_ms']>=MAX_MS:raise ValueError('Phiếu đã đạt giới hạn đo 24 giờ; cần kiểm tra lại phiên rà.')
                if live:raise RuntimeError('Đồng hồ đang chạy ở một phiên. Tạm dừng phiên đó hoặc chọn tiếp tục tại tab này.')
                token=secrets.token_urlsafe(32);state.update(running=True,last_tick=now.isoformat(),token_hash=hashlib.sha256(token.encode()).hexdigest(),status='draft',submitted_at=None)
            elif action=='recover':
                # An unconfirmed tail after losing the tab/network is never fabricated.
                state.update(running=False,last_tick=None,token_hash=None)
                notice='Đã dừng phiên cũ; chỉ giữ thời gian đã xác nhận. Bấm bắt đầu để tiếp tục.'
            else:
                if not isinstance(timer_token,str) or not state['token_hash'] or not secrets.compare_digest(hashlib.sha256(timer_token.encode()).hexdigest(),state['token_hash']):
                    raise PermissionError('Đồng hồ thuộc phiên khác. Dùng tiếp tục tại tab này để khôi phục.')
                if live:credited=min(MAX_MS-state['confirmed_ms'],int(elapsed*1000));state['confirmed_ms']+=credited
                if not live:notice='Phiên đo hết hạn; thời gian mất kết nối chưa xác nhận không được tính.'
                if action=='pause' or not live or state['confirmed_ms']>=MAX_MS:
                    state.update(running=False,last_tick=None,token_hash=None)
                else:state['last_tick']=now.isoformat()
            state['revision']+=1;self._write(db,pid,rid,state,principal,action,credited)
        return dict(work=self._view(state,principal),timer_token=token,notice=notice)

    @staticmethod
    def _form(value,complete):
        if not isinstance(value,dict) or set(value)-FORM_FIELDS:raise ValueError('Phiếu có trường không được hỗ trợ.')
        form={key:value.get(key,'') for key in FORM_FIELDS}
        if any(not isinstance(v,str) or len(v)>4000 for v in form.values()):raise ValueError('Mỗi ô nội dung cần là văn bản, tối đa 4.000 ký tự.')
        form={k:v.strip() for k,v in form.items()}
        if form['useful'] not in {'','yes','no','unknown'}:raise ValueError('Chọn hữu ích, không hữu ích hoặc chưa đủ căn cứ.')
        if complete and (not form['useful'] or not form['rationale'] or not form['evidence_refs'] or (form['useful']=='yes' and not form['business_action'])):
            raise ValueError('Cần kết quả, nhận xét/căn cứ, tham chiếu và hành động cụ thể khi đánh dấu hữu ích.')
        return form

    def save(self,pid,rid,principal,*,expected_revision,form,submit=False,acknowledge=False):
        if type(submit) is not bool or type(acknowledge) is not bool:raise ValueError('Trạng thái xác nhận không hợp lệ.')
        form=self._form(form,submit)
        if submit and not acknowledge:raise ValueError('Xác nhận đã trực tiếp rà và kiểm tra nội dung trước khi lưu kết quả.')
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE');state=self._edit(db,pid,rid,principal,expected_revision)
            if not state:raise ValueError('Bắt đầu đồng hồ để nhận phiếu và ghi nhận thời gian rà.')
            if state['running']:raise ValueError('Tạm dừng đồng hồ trước khi lưu phiếu.')
            if submit and state['confirmed_ms']<=0:raise ValueError('Cần thời gian kiểm tra đã đo trước khi xác nhận kết quả.')
            state.update(form=form,status='reviewed' if submit else 'draft',revision=state['revision']+1,
                         submitted_at=self.clock().isoformat() if submit else None)
            self._write(db,pid,rid,state,principal,'submit' if submit else 'draft')
        return dict(work=self._view(state,principal))

    def _results(self,db,pid,principal):
        meta,report=self._packet(db,pid,principal);entered={};all_units=[]
        for row in db.execute('SELECT * FROM ml_review_units WHERE packet_id=? ORDER BY review_id',(pid,)):
            if row['company_id'] not in principal.company_ids:continue
            unit=json.loads(row['data']);all_units.append(unit);state=self._work(db,pid,row['review_id'])
            if state and state['status']=='reviewed':
                entered[row['review_id']]=dict({k:unit[k] for k in ('review_id','company_id','transaction_id','evidence_sha256')},
                    **state['form'],active_review_minutes=state['confirmed_ms']/60000,timing_method='stopwatch',
                    reviewer_id=state['owner']['user_id'],reviewed_at=state['submitted_at'],human_verified='1')
        return meta,report,all_units,entered

    def summary(self,pid,principal):
        require_permission(principal,'ml_manage')
        with self.store.connection() as db:
            db.execute('BEGIN');meta,report,units,entered=self._results(db,pid,principal)
        complete=len(entered)==len(units)
        # Model identities are revealed only after the user's scoped review population is complete.
        metrics=review_metrics(report,entered,set(principal.company_ids)) if complete else []
        return dict(packet_id=pid,source_kind=meta['source_kind'],reviewed=len(entered),total=len(units),complete=complete,
                    metrics=metrics,total_unique_review_minutes=sum(r['active_review_minutes'] for r in entered.values()),
                    business_winner=None,reason='' if complete else 'Hoàn tất các phiếu trong phạm vi công ty trước khi xem tên model và bảng so sánh.')

    def export(self,pid,principal):
        require_permission(principal,'ml_manage')
        with self.store.connection() as db:
            db.execute('BEGIN');_,_,units,entered=self._results(db,pid,principal)
        stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=REVIEW_FIELDS);writer.writeheader()
        for unit in units:
            row=entered.get(unit['review_id']) or {k:unit[k] for k in ('review_id','company_id','transaction_id','evidence_sha256')}
            writer.writerow({k:("'"+str(row.get(k,'')) if str(row.get(k,'')).lstrip().startswith(('=','+','-','@')) else row.get(k,'')) for k in REVIEW_FIELDS})
        return '\ufeff'+stream.getvalue()
