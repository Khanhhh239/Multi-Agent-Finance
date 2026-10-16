"""Read-only tool contract. A proposal is an in-memory draft, never a write."""
from __future__ import annotations
from dataclasses import dataclass,field
import copy
from agent4.engine.metrics import REGISTRY
from agent4.engine.engine import EngineError,FILTER_KEYS,COMPARE_MODES
from .constants import NOTICE,MUST,PILOT_NOTICE

PROPOSALS = ('record_payment_promise','set_credit_hold','flag_for_review')

@dataclass(frozen=True)
class Principal:
    user_id: str = 'local-experiment'
    role: str = 'owner'
    scope: dict = field(default_factory=dict)

@dataclass
class ToolResult:
    ok: bool
    data: dict = field(default_factory=dict)
    error: dict|None = None

def _object(properties,required=()):
    return {'type':'object','properties':properties,'required':list(required),'additionalProperties':False}

def _nullable(schema):
    return {'anyOf':[schema,{'type':'null'}]}

def build_union_schema(candidates):
    ids=list(dict.fromkeys(candidates))
    if not ids or any(m not in REGISTRY for m in ids): raise ValueError('Cần tập chỉ số hợp lệ.')
    views=sorted({v for m in ids for v in REGISTRY[m].views})
    groups=sorted({g for m in ids for g in REGISTRY[m].group_bys})
    filters={k:_nullable({'anyOf':[{'type':'string'},{'type':'array','items':{'type':'string'}}]}) for k in FILTER_KEYS if k!='exclude_top_customers'}
    filters['exclude_top_customers']=_nullable({'type':'integer','minimum':1,'maximum':20})
    period={'anyOf':[{'type':'string'},_object({'start_date':{'type':'string'},'end_date':{'type':'string'}},('start_date','end_date'))]}
    props={'metric':{'type':'string','enum':ids},'period':_nullable(period),
           'compare_to':_nullable({'type':'string','enum':list(COMPARE_MODES)}),
           'group_by':_nullable({'type':'string','enum':groups}) if groups else {'type':'null'},
           'view':_nullable({'type':'string','enum':views}),'filters':_nullable(_object(filters)),
           'top_k':_nullable({'type':'integer','minimum':1,'maximum':50}),
           'params':_nullable(_object({'min_days':{'type':'integer','minimum':0,'maximum':3650},
                                     'days':{'type':'integer','minimum':1,'maximum':365},
                                     'date_basis':{'type':'string','enum':['receipt','bank']},
                                     'line_type':{'type':'string','enum':['ALL','REVENUE','EXPENSE']}}))}
    branches=[]
    def add(action,fields,required=()):
        branches.append(_object({'action':{'const':action},**fields},('action',*required)))
    add('query_metric',props,('metric',))
    add('explain_metric',{k:v for k,v in props.items() if k in ('metric','period','view','filters')},('metric',))
    add('find_entity',{'kind':{'type':'string','enum':['customer','vendor','branch','item','cost_category','department','salesperson']},'text':{'type':'string','maxLength':160}},('kind','text'))
    add('list_metrics',{'category':{'type':'string','enum':sorted({m.category for m in REGISTRY.values()})}})
    patch=_object({'metric':{'type':'string','enum':ids},'period':period,'view':{'type':'string','enum':views}})
    add('ask_clarification',{'question':{'type':'string','maxLength':300},'options':{'type':'array','minItems':2,'maxItems':3,
        'items':_object({'label':{'type':'string','maxLength':100},'patch':patch},('label','patch'))}},('question','options'))
    add('refuse',{'reason':{'type':'string','enum':['out_of_scope','unsafe_action','no_permission','no_data']},
                  'message':{'type':'string','maxLength':300}},('reason','message'))
    add('propose_action',{'action_type':{'type':'string','enum':list(PROPOSALS)},
                          'rationale':{'type':'string','maxLength':300}},('action_type','rationale'))
    return {'$schema':'https://json-schema.org/draft/2020-12/schema','oneOf':branches}

def build_tool_specs(candidates):
    descriptions={'query_metric':'Tra chỉ số tài chính bằng engine; không tự tính số.',
        'explain_metric':'Xem nguồn và cách tính của chỉ số.', 'find_entity':'Tìm mã thực thể bằng tên hoặc mã.',
        'list_metrics':'Liệt kê chỉ số trong phạm vi quyền.', 'ask_clarification':'Hỏi lại khi nghĩa câu hỏi chưa rõ, kèm lựa chọn.',
        'refuse':'Từ chối yêu cầu ngoài phạm vi hoặc không được phép.',
        'propose_action':'Soạn đề xuất để người dùng xem; không lưu hoặc thực thi.'}
    out=[]
    for branch in build_union_schema(candidates)['oneOf']:
        schema=copy.deepcopy(branch)
        action=schema['properties'].pop('action')['const']
        schema['required'].remove('action')
        out.append({'type':'function','function':{'name':action,'description':descriptions[action],'parameters':schema}})
    return out

COMPANY_ONLY = {'cash_and_equivalents','term_deposits','debt_balance','total_assets','total_liabilities',
                'equity','payroll_summary','salary_expense','labor_cost','upcoming_obligations','cash_coverage_days'}
SALES_METRICS = {'net_revenue','gross_revenue','goods_revenue','service_revenue','ar_balance','ar_by_customer',
                 'ar_by_salesperson','overdue_receivables','ar_aging','dso','dso_actual'}

def principal_access(principal,metric=None):
    role=principal.role
    if role in ('owner','cfo'): return True
    if role not in ('branch_manager','sales'): return False
    required='branch' if role=='branch_manager' else 'salesperson'
    if not isinstance(principal.scope,dict) or not principal.scope.get(required): return False
    if metric in COMPANY_ONLY: return False
    return role!='sales' or metric is None or metric in SALES_METRICS

def execute(call,engine,principal=None):
    principal=principal or Principal()
    action=call.get('action')
    metric=call.get('metric')
    if not principal_access(principal,metric):
        return ToolResult(False,error={'code':'NO_PERMISSION','message':'Vai trò hoặc phạm vi không cho phép yêu cầu này.'})
    try:
        if action in ('query_metric','explain_metric'):
            # Schema is enforced here too; direct callers cannot inject scope/SQL.
            from jsonschema import Draft202012Validator
            Draft202012Validator(build_union_schema([metric] if metric in REGISTRY else list(REGISTRY))).validate(call)
            args={k:v for k,v in call.items() if k!='action' and v is not None}
            data=getattr(engine,'query' if action=='query_metric' else 'explain')(**args,scope=principal.scope)
        elif action=='list_metrics':
            data={'metrics':[m for m in engine.list_metrics() if principal_access(principal,m['id']) and (not call.get('category') or REGISTRY[m['id']].category==call['category'])]}
        elif action=='find_entity':
            if principal.role not in ('owner','cfo'):
                return ToolResult(False,error={'code':'NO_PERMISSION','message':'Tra danh mục toàn công ty chưa hỗ trợ vai trò giới hạn.'})
            codes=engine.resolve_entity(call['kind'],call['text'])
            data={'entities':codes}
        elif action=='propose_action' and call.get('action_type') in PROPOSALS:
            data={'status':'DRAFT_ONLY','action_type':call['action_type'],'requires_human_approval':True,
                  'message':'Đề xuất thử nghiệm; chưa lưu và chưa thực thi.'}
        elif action in ('ask_clarification','refuse'):
            data=copy.deepcopy(call)
        else:
            return ToolResult(False,error={'code':'UNKNOWN_TOOL','message':'Công cụ chưa được hỗ trợ trong P1.'})
        data['experimental_notice']=NOTICE
        if metric in MUST: data['pilot_status']=PILOT_NOTICE
        return ToolResult(True,data)
    except EngineError as exc:
        return ToolResult(False,error={'code':exc.code,'message':str(exc),'candidates':getattr(exc,'candidates',[])})
    except Exception as exc:
        # Never expose SQL or remote/internal exception text to a model.
        return ToolResult(False,error={'code':'INVALID_TOOL_CALL','message':'Lời gọi công cụ không hợp lệ.'})
