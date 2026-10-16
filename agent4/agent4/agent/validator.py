"""Validate model intent before any financial execution. Never accept model scope."""
from __future__ import annotations
from dataclasses import dataclass,field
import copy
from jsonschema import Draft202012Validator
from agent4.engine import periods as P
from agent4.engine.engine import EngineError,FilterError
from agent4.engine.scope import compile_scope
from .tools import build_union_schema,principal_access,Principal

@dataclass
class Issue:
    code: str
    message: str

@dataclass
class ValidationResult:
    ok: bool
    fixed_call: dict|None = None
    errors: list[Issue] = field(default_factory=list)
    action: str = 'proceed'

CUSTOM_FILTERS = {
    'ar_aging':{'customer','exclude_customers','exclude_top_customers'},
    'overdue_receivables':{'customer','exclude_customers','exclude_top_customers'},
    'dso_actual':{'customer','branch','salesperson','exclude_customers','exclude_top_customers'},
    'ap_due_soon':{'vendor'},'budget_vs_actual':{'branch'},
}
SQL_FILTER_CUSTOM={'dso','dpo','dio','cash_conversion_cycle','expense_spikes','mgmt_vs_tax_gap'}

def _result(code,message,action='repair'):
    return ValidationResult(False,errors=[Issue(code,message)],action=action)

def validate(call,*,hints,candidates,principal=None,engine):
    principal=principal or Principal()
    ids=[c.metric if hasattr(c,'metric') else c for c in candidates]
    if not isinstance(call,dict): return _result('SCHEMA','Chỉ trả một đối tượng JSON theo lược đồ.')
    action=call.get('action')
    cues=getattr(hints,'cues',set())
    if cues.intersection({'unsafe_action','jailbreak','out_of_scope'}) and action not in ('refuse','propose_action'):
        return _result('UNSAFE_REQUEST','Yêu cầu bị giới hạn bởi chính sách an toàn.','refuse')
    fixed=copy.deepcopy(call)
    metric=fixed.get('metric')
    if not principal_access(principal,metric if isinstance(metric,str) else None):
        return _result('NO_PERMISSION','Vai trò hoặc phạm vi không cho phép yêu cầu này.','refuse')
    # Check schema before correcting values: do not silently drop unknown fields.
    try:
        errors=list(Draft202012Validator(build_union_schema(ids)).iter_errors(fixed))
    except (ValueError,TypeError):
        return _result('CANDIDATES','Không có tập chỉ số hợp lệ.','clarify')
    if errors:
        return _result('SCHEMA','Trường hoặc giá trị không thuộc lược đồ; chọn chỉ số trong ứng viên.')
    if action not in ('query_metric','explain_metric'):
        if action=='propose_action' and principal.role not in ('owner','cfo'):
            return _result('NO_PERMISSION','Vai trò không được tạo đề xuất.','refuse')
        return ValidationResult(True,fixed)
    md=engine.get_definition(metric)
    if 'needs_clarification' in cues:
        return _result('AMBIGUOUS','Cần xác định rõ loại lợi nhuận hoặc ý nghĩa câu hỏi.','clarify')
    inherited=getattr(hints,'inherited',{}) or {}
    view_hint=getattr(hints,'view_hint',None) or inherited.get('view')
    view='tax' if view_hint=='tax' else 'mgmt'
    if view not in md.views:
        return _result('VIEW','Cần chọn chỉ số phù hợp với khung đang được hỏi.','clarify')
    fixed['view']=view
    hits=getattr(hints,'periods',[])
    if hits:
        hit=hits[0]
        period=getattr(hit,'period',None)
        if period is None and isinstance(hit,tuple): period=hit[1]
        if period is not None: fixed['period']=period.token
    elif inherited.get('period'):
        fixed['period']=inherited['period']
    elif not fixed.get('period'):
        default='today' if md.period_type=='snapshot' else md.params.get('period_default','this_month')
        fixed['period']=None if default=='all' else default
    try:
        per=engine.resolve(md,fixed.get('period'),md.params)
    except EngineError:
        return _result('PERIOD','Kỳ không giải được; dùng token hoặc cụm trong HINTS.')
    if md.period_type=='flow' and per.start>engine.as_of and metric!='upcoming_obligations':
        return _result('NO_DATA','Kỳ được hỏi chưa có dữ liệu.','refuse')
    if action=='query_metric':
        if getattr(hints,'compare',None): fixed['compare_to']=hints.compare
        if getattr(hints,'group_by',None): fixed['group_by']=hints.group_by
        elif inherited.get('group_by'): fixed['group_by']=inherited['group_by']
        if fixed.get('group_by') and fixed['group_by'] not in md.group_bys:
            return _result('GROUP','Chiều nhóm không hỗ trợ cho chỉ số này.')
        parameters={**(fixed.get('params') or {}),**(getattr(hints,'params',{}) or {})}
        if parameters: fixed['params']=parameters
    filters={**(inherited.get('filters') or {}),**(fixed.get('filters') or {})}
    for entity in getattr(hints,'entities',[]):
        kind,codes=getattr(entity,'kind',None),getattr(entity,'codes',[])
        if kind and len(codes)>1:
            return _result('ENTITY','Tên khớp nhiều đối tượng; cần chọn đúng mã.','clarify')
        if kind and codes: filters[kind]=codes[0]
    if md.kind=='custom' and metric not in SQL_FILTER_CUSTOM and set(filters)-CUSTOM_FILTERS.get(metric,set()):
        return _result('FILTER_UNSUPPORTED','Chỉ số này chưa hỗ trợ đầy đủ bộ lọc được yêu cầu.','refuse')
    try:
        for kind,values in filters.items():
            if kind=='exclude_top_customers': continue
            for value in values if isinstance(values,list) else [values]:
                engine.resolve_entity('customer' if kind=='exclude_customers' else kind,value)
        compile_scope(engine,md,principal.scope)
    except (EngineError,KeyError,TypeError) as exc:
        return _result('FILTER',str(exc) if isinstance(exc,EngineError) else 'Bộ lọc không hợp lệ.','clarify')
    if filters: fixed['filters']=filters
    # Repairs derived from hints must still satisfy the same schema.
    if not Draft202012Validator(build_union_schema(ids)).is_valid(fixed):
        return _result('SCHEMA','Tham số gợi ý chưa phù hợp với lược đồ của chỉ số.')
    return ValidationResult(True,fixed)

def repair_prompt(issues):
    codes=','.join(i.code for i in issues)[:40]
    return f'Fix JSON. Error: {codes}. Use schema, candidate metrics and HINTS.'
