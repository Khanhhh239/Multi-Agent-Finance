"""Operational document requests; separate from detector scores and conclusions."""
from datetime import datetime, timezone, timedelta
import json
import uuid

from .case_identity import digest, scope_hash

TZ=timezone(timedelta(hours=7))
ACTIVE={'open','received'}


def text(value, label, maximum):
    if not isinstance(value,str) or not value.strip() or len(value)>maximum:
        raise ValueError(f'{label}: nhập nội dung, tối đa {maximum} ký tự.')
    return value.strip()


def timestamp(value):
    try:
        result=datetime.fromisoformat(value)
        if result.utcoffset() is None:
            raise ValueError()
        return result.astimezone(TZ)
    except (TypeError,ValueError):
        raise ValueError('Hạn bổ sung phải là thời điểm ISO có múi giờ.') from None


class InformationRequests:
    def __init__(self,store):
        self.store=store
        with store.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS information_request_events(id INTEGER PRIMARY KEY,data TEXT NOT NULL,event_hash TEXT NOT NULL)')

    @staticmethod
    def history(db):
        previous=''
        result=[]
        for saved in db.execute('SELECT id,data,event_hash FROM information_request_events ORDER BY id'):
            event=json.loads(saved['data'])
            if event.get('id')!=saved['id'] or event.get('previous_hash')!=previous or digest(event)!=saved['event_hash']:
                raise ValueError('Nhật ký yêu cầu tài liệu đã thay đổi; kiểm tra bản lưu trước khi tiếp tục.')
            result.append(dict(event,event_hash=saved['event_hash']))
            previous=saved['event_hash']
        return result

    def view(self,scenario,case,db=None,history=None):
        if db is None and history is None:
            with self.store.connection() as connection:
                return self.view(scenario,case,connection)
        binding=scope_hash(case)
        if history is None:
            history=self.history(db)
        relevant=[e for e in history if e['scenario']==scenario and e['company_id']==case['company_id'] and
                  (e['case_id']==case['case_id'] or e['case_scope_hash']==binding)]
        latest={e['request_id']:e for e in relevant}
        now=self.store.clock().astimezone(TZ)
        rows=[]
        for event in latest.values():
            applies=event['case_scope_hash']==binding
            active=applies and event['status'] in ACTIVE
            rows.append(dict(event,applies_to_current_scope=applies,active=active,
                overdue=active and now>timestamp(event['due_at']),
                age_hours=max(0,round((now-timestamp(event['created_at'])).total_seconds()/3600,2)),
                due_in_hours=round((timestamp(event['due_at'])-now).total_seconds()/3600,2)))
        active=[r for r in rows if r['active']]
        return dict(scope_hash=binding,requests=rows,history=relevant,
            active_count=len(active),overdue_count=sum(r['overdue'] for r in active),
            ready_for_rereview=any(r['status']=='received' for r in active),
            next_due_at=min((r['due_at'] for r in active),default=None),
            owners=sorted({r['owner'] for r in active}),time_basis='request_created_at_operational_clock',
            now=now.isoformat(timespec='seconds'),audit_integrity='passed')

    def update(self,db,scenario,case,body):
        binding=scope_hash(case)
        if body.get('case_scope_hash')!=binding:
            raise RuntimeError('Phạm vi hồ sơ đã thay đổi. Tải lại trước khi cập nhật yêu cầu tài liệu.')
        actor=text(body.get('actor'),'Người thực hiện',100)
        reason=text(body.get('reason'),'Lý do',2000)
        action=body.get('action')
        if action not in {'create','assign','receive','review','reopen','cancel'}:
            raise ValueError('Thao tác yêu cầu tài liệu không hợp lệ.')
        history=self.history(db)
        now=self.store.clock().astimezone(TZ)
        if action=='create':
            if body.get('expected_hash')!='':
                raise RuntimeError('Yêu cầu mới không có phiên bản cũ.')
            event=dict(request_id='DR_'+uuid.uuid4().hex,scenario=scenario,company_id=case['company_id'],
                case_id=case['case_id'],case_scope_hash=binding,created_at=now.isoformat(timespec='seconds'),
                owner=text(body.get('owner'),'Người phụ trách',100),requested_documents=text(body.get('requested_documents'),'Tài liệu cần bổ sung',2000),
                due_at=timestamp(body.get('due_at')).isoformat(timespec='seconds'),status='open',evidence_refs=[])
        else:
            matches=[e for e in history if e['request_id']==body.get('request_id')]
            if not matches:
                raise KeyError('Không tìm thấy yêu cầu tài liệu.')
            old=matches[-1]
            if old['scenario']!=scenario or old['company_id']!=case['company_id'] or old['case_scope_hash']!=binding:
                raise RuntimeError('Yêu cầu thuộc snapshot/công ty/phạm vi khác; không tự chuyển trạng thái.')
            if body.get('expected_hash')!=old['event_hash']:
                raise RuntimeError('Yêu cầu vừa được cập nhật. Tải lại trước khi lưu.')
            if old['status'] in {'reviewed','cancelled'}:
                raise RuntimeError('Yêu cầu đã kết thúc; tạo yêu cầu mới nếu cần bổ sung tiếp.')
            event={k:v for k,v in old.items() if k not in {'event_hash','id','previous_hash','action','actor','reason','event_at'}}
            if action=='assign':
                event.update(owner=text(body.get('owner'),'Người phụ trách',100),due_at=timestamp(body.get('due_at')).isoformat(timespec='seconds'))
            elif action=='receive':
                if old['status']!='open':
                    raise RuntimeError('Chỉ ghi nhận tài liệu cho yêu cầu đang chờ bổ sung.')
                refs=body.get('evidence_refs')
                if not isinstance(refs,list) or not 1<=len(refs)<=20:
                    raise ValueError('Cần 1–20 tham chiếu chứng từ đã nhận.')
                event.update(status='received',evidence_refs=list(dict.fromkeys(text(r,'Tham chiếu chứng từ',300) for r in refs)))
            elif action=='review':
                if old['status']!='received':
                    raise RuntimeError('Cần ghi nhận tài liệu đã nhận trước khi rà lại.')
                event['status']='reviewed'
            elif action=='reopen':
                if old['status']!='received':
                    raise RuntimeError('Chỉ trả về bổ sung tiếp sau khi đã nhận tài liệu.')
                event['status']='open'
            elif action=='cancel':
                event['status']='cancelled'
        if action in {'create','assign'} and timestamp(event['due_at'])<=now:
            raise ValueError('Chọn hạn bổ sung sau thời điểm thao tác hiện tại; không lấy hạn lịch sử của snapshot.')
        event.update(id=history[-1]['id']+1 if history else 1,action=action,actor=actor,reason=reason,
            event_at=now.isoformat(timespec='seconds'),previous_hash=history[-1]['event_hash'] if history else '')
        checksum=digest(event)
        db.execute('INSERT INTO information_request_events VALUES(?,?,?)',(event['id'],json.dumps(event,ensure_ascii=False),checksum))
        return dict(event,event_hash=checksum)
