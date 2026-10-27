"""Two review levels, bound to identities supplied by a trusted future login layer."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import json

from .case_identity import digest, scope_hash

VERSION='accountant-review-final-approval-v1'
SETTING='two_stage_review_policy'
LABELS={'accountant':'Kế toán viên','chief_accountant':'Kế toán trưởng','director':'Giám đốc'}
PERMISSIONS={
    'primary':frozenset({'accountant'}),
    'finalize':frozenset({'chief_accountant','director'}),
    'return':frozenset({'chief_accountant','director'}),
    'information_request':frozenset({'accountant'}),
    'budget':frozenset({'chief_accountant','director'}),
    'notification_preview':frozenset({'chief_accountant','director'}),
    'uat_note':frozenset(LABELS)}
_grant=ContextVar('trusted_review_finalization',default=None)


@dataclass(frozen=True)
class ReviewPrincipal:
    user_id:str
    person_id:str
    display_name:str
    role:str
    company_ids:tuple

    def __post_init__(self):
        if (any(not isinstance(v,str) or not v.strip() or len(v)>100 for v in
                (self.user_id,self.person_id,self.display_name)) or self.role not in LABELS
            or not isinstance(self.company_ids,tuple) or not self.company_ids
            or any(not isinstance(c,str) or not c.strip() or c=='*' for c in self.company_ids)):
            raise ValueError('Danh tính đăng nhập cần mã người dùng, mã người thật, vai trò và phạm vi công ty rõ ràng.')


def require_permission(principal,action,company=None):
    if not isinstance(principal,ReviewPrincipal):
        raise PermissionError('Đã cấu hình phân quyền; cần tài khoản từ luồng đăng nhập để ghi nhận hoặc duyệt hồ sơ.')
    if principal.role not in PERMISSIONS.get(action,()):
        raise PermissionError('Vai trò này không có quyền thực hiện bước rà soát được yêu cầu.')
    if company is not None and company not in principal.company_ids:
        raise PermissionError('Tài khoản không thuộc phạm vi công ty của hồ sơ.')
    return principal


def policy_status(principal=None):
    return dict(enabled=True,version=VERSION,primary_roles=['accountant'],final_roles=['chief_accountant','director'],
        role_labels=LABELS,same_person_finalization_allowed=False,
        identity_status='authenticated' if isinstance(principal,ReviewPrincipal) else 'awaiting_login_integration',
        principal=None if principal is None else dict(user_id=principal.user_id,display_name=principal.display_name,role=principal.role),
        independent_ml_review_automatically_confirmed=False)


def workflow_events(db):
    previous='';result=[]
    for row in db.execute('SELECT data FROM review_workflow_events ORDER BY sequence'):
        event=json.loads(row[0]);checksum=event.pop('event_hash')
        if event['previous_hash']!=previous or digest(event)!=checksum:
            raise ValueError('Nhật ký rà soát hai cấp không còn khớp; cần kiểm tra trước khi ghi thêm.')
        event['event_hash']=checksum;result.append(event);previous=checksum
    return result


@contextmanager
def finalization_context(database,event):
    token=_grant.set(dict(database=str(database.resolve()),event=event))
    try:yield
    finally:_grant.reset(token)


def check_finalization_grant(db,database,case,decision,reviewer):
    configured=db.execute('SELECT value FROM settings WHERE key=?',(SETTING,)).fetchone()
    if not configured:return None
    if configured[0]!=VERSION:raise ValueError('Phiên bản chính sách rà soát hai cấp không được hỗ trợ.')
    grant=_grant.get()
    if not grant or grant['database']!=str(database.resolve()):
        raise PermissionError('Kết luận cần được kế toán trưởng hoặc giám đốc chốt qua luồng rà soát hai cấp.')
    history=workflow_events(db);event=grant['event']
    relevant=[r for r in history if r['scenario']==event['scenario'] and r['case_id']==case['case_id']
              and r['case_scope_hash']==scope_hash(case)]
    if (not relevant or relevant[-1]!=event or event['kind']!='finalization_requested'
        or event['actor']['role'] not in PERMISSIONS['finalize'] or event['data']['decision']!=decision
        or event['actor']['display_name']!=reviewer):
        raise PermissionError('Quyền chốt kết luận không khớp người thực hiện hoặc phiên bản hồ sơ.')
    primary=next((r for r in reversed(relevant[:-1]) if r['kind']=='primary_submitted'),None)
    if (not primary or event['data']['primary_event_hash']!=primary['event_hash']
        or primary['actor']['role']!='accountant'
        or primary['actor']['person_id'].casefold()==event['actor']['person_id'].casefold()
        or primary['actor']['user_id']==event['actor']['user_id']):
        raise PermissionError('Người rà lần đầu và người chốt kết luận phải là hai người khác nhau.')
    return event['event_hash']


def validate_ml_review_pair(assignment,unit_id,primary_id,final_id):
    """Role assignment never substitutes for real identities or blind attestations."""
    if assignment.get('role_policy') is None:
        return (bool(assignment.get('primary_reviewer_id')) and bool(assignment.get('adjudicator_id'))
                and primary_id==assignment['primary_reviewer_id'] and final_id==assignment['adjudicator_id']
                and primary_id!=final_id)
    if assignment['role_policy']!=VERSION:raise ValueError('Unsupported reviewer role policy')
    people=assignment.get('people',{})
    primary,final=people.get(primary_id,{}),people.get(final_id,{})
    binding=assignment.get('units',{}).get(unit_id,assignment)
    return bool(primary_id!=final_id and primary.get('role')=='accountant'
        and final.get('role') in PERMISSIONS['finalize']
        and isinstance(primary.get('person_id'),str) and primary['person_id'].strip()
        and isinstance(final.get('person_id'),str) and final['person_id'].strip()
        and primary['person_id'].strip().casefold()!=final['person_id'].strip().casefold()
        and binding.get('primary_reviewer_id')==primary_id and binding.get('adjudicator_id')==final_id)
