"""Append-only two-level review; no accounts, login or outcomes are fabricated."""
import json
import math

from .case_identity import digest,load_lineage,resolve,scope_hash,feedback_view
from .feedback import DECISIONS,feedback_lock,read_audit,_record_feedback
from .review_decision_gate import assert_binding
from .review_roles import (VERSION,SETTING,require_permission,policy_status,workflow_events,finalization_context)


class TwoStageReview:
    def __init__(self,store):
        self.store=store
        with store.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS review_workflow_events(sequence INTEGER PRIMARY KEY,data TEXT NOT NULL)')
            existing=db.execute('SELECT value FROM settings WHERE key=?',(SETTING,)).fetchone()
            if existing and existing[0]!=VERSION:raise ValueError('Unsupported review role policy')
            db.execute('INSERT OR IGNORE INTO settings VALUES(?,?)',(SETTING,VERSION))

    def policy(self,principal=None):return policy_status(principal)

    def _case(self,scenario,case_id):
        directory=self.store.report(scenario);lineage=load_lineage(directory)
        case_id=resolve(case_id,lineage['aliases'])
        with self.store.connection() as db:
            assert_binding(db,directory,self.store.database,scenario)
            saved=db.execute('SELECT data FROM cases WHERE scenario=? AND case_id=?',(scenario,case_id)).fetchone()
        if not saved:raise KeyError('Hồ sơ không còn hiện hành; lịch sử chỉ đọc.')
        return json.loads(saved[0])

    def _current(self,scenario,case):
        with self.store.connection() as db:history=workflow_events(db)
        events=[r for r in history if r['scenario']==scenario and r['case_id']==case['case_id'] and r['case_scope_hash']==scope_hash(case)]
        primary=next((r for r in reversed(events) if r['kind']=='primary_submitted'),None)
        last=events[-1] if events else None
        recovered=bool(last and last['kind']=='finalization_requested' and any(
            r.get('workflow_approval_id')==last['event_hash']
            for r in read_audit(self.store.report(scenario)/'feedback_audit.jsonl')))
        stage=('finalized' if last and (last['kind']=='finalized' or recovered) else
               'returned' if last and last['kind']=='returned' else 'pending_final' if primary else 'pending_review')
        return dict(stage=stage,case_scope_hash=scope_hash(case),latest_event_hash=last['event_hash'] if last else '',primary=primary,history=events)

    def state(self,scenario,case_id,principal=None):
        with feedback_lock(self.store.report(scenario)):
            case=self._case(scenario,case_id)
            if principal is not None and case['company_id'] not in principal.company_ids:
                raise PermissionError('Tài khoản không thuộc phạm vi công ty của hồ sơ.')
            result=self._current(scenario,case)
        return dict(result,policy=self.policy(principal))

    def _append(self,kind,scenario,case,principal,data):
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE');assert_binding(db,self.store.report(scenario),self.store.database,scenario)
            history=workflow_events(db)
            event=dict(version=VERSION,kind=kind,scenario=scenario,case_id=case['case_id'],company_id=case['company_id'],
                case_scope_hash=scope_hash(case),actor=dict(user_id=principal.user_id,person_id=principal.person_id,
                    display_name=principal.display_name,role=principal.role),
                event_at=self.store.clock().isoformat(timespec='seconds'),data=data,
                previous_hash=history[-1]['event_hash'] if history else '')
            event['event_hash']=digest(event)
            db.execute('INSERT INTO review_workflow_events(data) VALUES(?)',(json.dumps(event,ensure_ascii=False),))
        return event

    def _body(self,body,kind):
        allowed={'decision','reason','missing_evidence','active_minutes','timing_method','expected_event_hash','expected_scope_hash'}
        if not isinstance(body,dict) or set(body)-allowed:raise ValueError('Chỉ nhận nội dung rà; danh tính và vai trò lấy từ phiên đăng nhập.')
        reason=body.get('reason');minutes=body.get('active_minutes');missing=body.get('missing_evidence','')
        if not isinstance(reason,str) or not reason.strip() or len(reason)>2000:raise ValueError('Cần lý do đã đối chiếu, tối đa 2.000 ký tự.')
        if (type(minutes) not in (float,int) or not math.isfinite(minutes) or not 0<minutes<=1440
            or body.get('timing_method')!='measured_stopwatch'):
            raise ValueError('Ghi phút thực tế đo bằng đồng hồ; không dùng thời gian ước lượng.')
        if not isinstance(body.get('expected_event_hash'),str):raise ValueError('Cần phiên bản bước rà đã đọc.')
        if not isinstance(body.get('expected_scope_hash'),str):raise ValueError('Cần phiên bản bằng chứng đã đọc.')
        if not isinstance(missing,str) or len(missing)>2000:raise ValueError('Danh sách chứng từ thiếu không hợp lệ.')
        decision=body.get('decision')
        if kind!='return' and decision not in DECISIONS:raise ValueError('Chọn kết quả rà hợp lệ.')
        if decision=='information_gap' and not missing.strip():raise ValueError('Ghi rõ chứng từ hoặc bằng chứng cần bổ sung.')
        return dict(decision=decision if kind!='return' else None,reason=reason.strip(),missing_evidence=missing.strip(),
                    active_minutes=minutes,timing_method='measured_stopwatch')

    def _expected(self,current,body):
        if current['case_scope_hash']!=body['expected_scope_hash']:
            raise RuntimeError('Phạm vi hoặc bằng chứng hồ sơ đã đổi. Cần tải lại và rà lại.')
        if current['latest_event_hash']!=body['expected_event_hash']:
            raise RuntimeError('Bước rà đã được cập nhật. Tải lại hồ sơ trước khi ghi tiếp.')

    def _feedback_hash(self,scenario,case):
        directory=self.store.report(scenario);lineage=load_lineage(directory)
        latest,_=feedback_view(read_audit(directory/'feedback_audit.jsonl'),lineage['current'],lineage)
        return latest.get(case['case_id'],{}).get('event_hash','')

    def submit(self,scenario,case_id,principal,body):
        case=self._case(scenario,case_id);require_permission(principal,'primary',case['company_id'])
        values=self._body(body,'primary')
        with feedback_lock(self.store.report(scenario)):self._expected(self._current(scenario,case),body)
        self.store.admit(scenario,case['case_id'])
        with feedback_lock(self.store.report(scenario)):
            case=self._case(scenario,case_id);self._expected(self._current(scenario,case),body)
            values['feedback_hash']=self._feedback_hash(scenario,case)
            self._append('primary_submitted',scenario,case,principal,values)
        return self.state(scenario,case_id,principal)

    def final_action(self,scenario,case_id,principal,body,*,action='finalize'):
        case=self._case(scenario,case_id);require_permission(principal,action,case['company_id'])
        if action not in {'finalize','return'}:raise ValueError('Unknown final review action')
        values=self._body(body,action)
        with feedback_lock(self.store.report(scenario)):
            case=self._case(scenario,case_id);current=self._current(scenario,case);self._expected(current,body)
            primary=current['primary']
            if current['stage']!='pending_final' or not primary:
                raise RuntimeError('Cần kết quả rà của kế toán viên đang chờ kiểm tra cuối.')
            if (primary['actor']['person_id'].strip().casefold()==principal.person_id.strip().casefold()
                    or primary['actor']['user_id']==principal.user_id):
                raise PermissionError('Người kiểm tra cuối phải khác người đã rà lần đầu.')
            values['primary_event_hash']=primary['event_hash']
            if action=='return':self._append('returned',scenario,case,principal,values)
            else:
                if self._feedback_hash(scenario,case)!=primary['data']['feedback_hash']:
                    raise RuntimeError('Kết luận hoặc phạm vi đã đổi sau bước rà lần đầu. Cần rà lại.')
                intent=self._append('finalization_requested',scenario,case,principal,values)
                try:
                    with finalization_context(self.store.database,intent):
                        saved=_record_feedback(self.store.report(scenario),case['case_id'],values['decision'],principal.display_name,
                            values['reason'],self.store.clock().isoformat(timespec='seconds'),
                            expected_hash=primary['data']['feedback_hash'],expected_database=self.store.database)
                except Exception:
                    # The audit append may have succeeded before a derived CSV
                    # write failed. Recover that outcome instead of appending twice.
                    saved=next((r for r in read_audit(self.store.report(scenario)/'feedback_audit.jsonl')
                                if r.get('workflow_approval_id')==intent['event_hash']),None)
                    if not saved:
                        self._append('finalization_failed',scenario,case,principal,dict(intent_hash=intent['event_hash']))
                        raise
                self._append('finalized',scenario,case,principal,dict(primary_event_hash=primary['event_hash'],
                    intent_hash=intent['event_hash'],feedback_event_hash=saved['event_hash'],decision=values['decision']))
        return self.state(scenario,case_id,principal)
