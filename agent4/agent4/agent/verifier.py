"""Typed source membership, rounding bounds, period and caveat verification."""
from __future__ import annotations
from dataclasses import dataclass,field
from datetime import date
import math,re
from agent4.engine.formatting import _NUM_RE,_SCALE,parse_vn_number
from agent4.engine.periods import strip_accents

UNITS={'VND':'money','%':'percent','days':'days','ratio':'ratio','count':'count'}
DATE_RE=re.compile(r'\b\d{4}-\d{2}(?:-\d{2})?\b|\b\d{1,2}/\d{1,2}/\d{4}\b|\b\d{1,2}/\d{4}\b')
PERIOD_RE=re.compile(r'\b(?:thang\s+\d{1,2}(?:/\d{4})?|quy\s+[1-4](?:/\d{4})?|nam\s+\d{4}|\d{4}-q[1-4])\b',re.I)

@dataclass(frozen=True)
class NumberEvidence:
    value: float
    unit: str
    source: str

@dataclass
class NumberSet:
    values: list[NumberEvidence] = field(default_factory=list)
    periods: set[str] = field(default_factory=set)
    labels: set[str] = field(default_factory=set)
    causal_level: int = 1
    primary: dict[str,NumberEvidence] = field(default_factory=dict)
    renderer_counts: set[tuple[int,int]] = field(default_factory=set)

@dataclass
class Violation:
    code: str
    text: str

@dataclass
class VerifyResult:
    ok: bool
    violations: list[Violation] = field(default_factory=list)

def _periods(text):
    t=strip_accents(str(text).lower())
    found=set()
    for pattern in (DATE_RE,PERIOD_RE):
        for m in pattern.finditer(t):
            value=m.group().strip()
            if re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}',value):
                d,mo,y=map(int,value.split('/'))
                try: value=date(y,mo,d).isoformat()
                except ValueError: pass
            found.add(value)
    return found

def mentions(text):
    # Dates and identifiers are verified separately, never treated as amounts.
    cleaned=DATE_RE.sub(' ',text)
    cleaned=re.sub(r'\b\d{4}-(?:[QH][1-4]|\d{2})\b|\bG\d+(?:\.\d+)+\b',' ',cleaned,flags=re.I)
    cleaned=re.sub(r'\b(?:[A-Za-z]+[-_]?\d|\d+[A-Za-z])[\w\-/]*\b',' ',cleaned)
    for m in _NUM_RE.finditer(cleaned):
        token,suffix=m.group(1),(m.group(2) or '').lower()
        value=parse_vn_number(token)
        tail=cleaned[m.end():m.end()+20].lower()
        scale=_SCALE.get(suffix,1)
        unit='money' if suffix and suffix!='%' else 'percent' if suffix=='%' else (
            'money' if re.match(r'\s*(?:đồng|đ\b|vnd)',tail) else
            'days' if re.match(r'\s*ngày',tail) else 'ratio' if re.match(r'\s*lần',tail) else 'count')
        if re.match(r'\s*điểm\s*%',tail): unit='percent'
        # VN grouped thousands do not represent decimal precision.
        decimal=token.split(',')[-1] if ',' in token else token.split('.')[-1] if '.' in token and not re.fullmatch(r'[-+−]?\d{1,3}(?:\.\d{3})+',token) else ''
        digits=len(decimal)
        yield NumberEvidence(value*scale,unit,m.group()),scale,digits

def allowed_numbers(results,question='',constants=None):
    allowed=NumberSet()
    skip={'description','label','metric_name','formula','partner_name','customer','item_name','name','notes','note',
          '_sql','_sql_params','accounts_involved','key','metric_id','lineage_id','data_version','filters','scope'}
    def add(value,unit,source):
        if isinstance(value,(float,int)) and not isinstance(value,bool) and math.isfinite(value):
            allowed.values.append(NumberEvidence(float(value),unit,source))
    def walk(value,unit,path='',key=''):
        if isinstance(value,dict):
            # A row's display can carry money even for an anomaly-count metric.
            display=value.get('display')
            inferred=next(iter(mentions(display)),None) if isinstance(display,str) else None
            ownunit=inferred[0].unit if inferred else unit
            for k,v in value.items():
                if k.startswith('_') or k in skip: continue
                childunit=('percent' if 'pct' in k or 'z_score'==k else 'days' if 'days' in k else
                           'count' if k in ('headcount','invoices','receipts','bills','rows_total','entry_count','invoice_count','customer_count','journals_checked','spike_count','lines','documents') else ownunit)
                walk(v,childunit,path+'.'+k,k)
        elif isinstance(value,list):
            for i,v in enumerate(value): walk(v,unit,f'{path}[{i}]',key)
        elif isinstance(value,(int,float)): add(value,unit,path)
        elif isinstance(value,str):
            if key.endswith('display') or key in ('amount','inflow','outflow','current','baseline_avg_3m','change_pct',
                'cash','cash_now','gap_vs_cash','avg_daily_outflow','total_inflow','total_outflow','collected',
                'gross_and_bonus','employer_contribution','pit_withheld','net_pay','actual','budget','avg_6m',
                'ar_begin','ar_end','credit_sales_incl_vat','ap_begin','ap_end','purchases_incl_vat','inventory_begin','inventory_end','cogs'):
                for number,_,_ in mentions(value): add(number.value,number.unit,path+'.display')
    for result in results:
        walk(result,UNITS.get(result.get('unit'),'count'))
        metadata=' '.join(str(result.get(k,'')) for k in ('period','period_label','data_status','data_through','comparison'))
        allowed.periods.update(_periods(metadata))
        for year in re.findall(r'\b(?:19|20)\d{2}\b',metadata): add(float(year),'count','period year')
        if result.get('value') is not None and result.get('metric_name'):
            allowed.primary[result['metric_name']+' '+result.get('period_label','')]=NumberEvidence(float(result['value']),UNITS.get(result.get('unit'),'count'),'primary')
        for account in result.get('audit_trail',{}).get('accounts_involved',[]):
            if str(account).isdigit(): add(float(account),'count','account code')
        if result.get('metric_id')=='ar_aging':
            from agent4.engine.custom import BUCKETS
            for label,_,_ in BUCKETS:
                for number,_,_ in mentions(label): add(number.value,number.unit,'engine aging bucket')
        if result.get('metric_id')=='cit_estimate': add(20,'percent','engine CIT assumption')
        if result.get('metric_id')=='mgmt_vs_tax_gap':
            from agent4.engine.custom2 import TAX_NOTES
            for text in TAX_NOTES.values():
                for number,_,_ in mentions(text): add(number.value,number.unit,'engine tax classification assumption')
        if result.get('metric_id')=='unusual_account_movements':
            for row in result.get('rows',[]):
                if match:=re.fullmatch(r'(\d{3,5})-(?:Nợ|Có)',str(row.get('key',''))):
                    add(float(match.group(1)),'count','engine movement account')
        if result.get('metric_id')=='upcoming_obligations':
            for row in result.get('rows',[]):
                if row.get('key')=='SALARY_EST':
                    for number,_,_ in mentions(row.get('label','')):
                        if number.unit=='count': add(number.value,'count','engine projected payroll periods')
                    allowed.periods.update(_periods(row.get('label','')))
        if result.get('group_by') in ('month','quarter','year'):
            for row in result.get('rows',[]): allowed.periods.update(_periods(str(row.get('label',''))))
        for row in result.get('rows',[]):
            if isinstance(row.get('label'),str): allowed.labels.add(strip_accents(row['label'].lower()))
    # Only temporal/count hints from the question; a user cannot mint money evidence.
    for number,_,_ in mentions(question):
        if number.unit in ('days','count'): allowed.values.append(number)
    for value in constants or []:
        allowed.values.append(value if isinstance(value,NumberEvidence) else NumberEvidence(float(value),'count','declared renderer constant'))
    return allowed

def _matches(number,scale,digits,evidence):
    if number.unit!=evidence.unit: return False
    if number.unit=='money':
        tolerance=abs(evidence.value)*.01 if scale>=1e6 and digits==0 else .5*scale*10**(-digits)
    elif number.unit=='percent': tolerance=.5 if digits==0 else .05
    elif number.unit=='days': tolerance=.5 if digits==0 else .05
    elif number.unit=='ratio': tolerance=.005
    else: tolerance=1e-9
    return abs(number.value-evidence.value)<=tolerance+1e-8

def verify(answer_text,allowed,required_labels=None):
    violations=[]
    # Row cardinalities are presentation metadata, not financial evidence.
    # Trust only an exact source-derived footer pair, never a global numeric
    # whitelist that could also admit an invented customer/amount claim.
    def footer(match):
        pair=tuple(map(int,match.groups()))
        if pair not in allowed.renderer_counts:violations.append(Violation('WRONG_RENDER_COUNT',match.group()))
        return 'hiển thị [số dòng đã kiểm tra] dòng'
    numeric_text=re.sub(r'hiển\s+thị\s+(\d+)/(\d+)\s+dòng',footer,answer_text,flags=re.I)
    for number,scale,digits in mentions(numeric_text):
        if not any(_matches(number,scale,digits,e) for e in allowed.values):
            violations.append(Violation('UNSUPPORTED_NUMBER',number.source))
    for period in _periods(answer_text)-allowed.periods:
        violations.append(Violation('WRONG_PERIOD',period))
    for label in required_labels or []:
        if label not in answer_text: violations.append(Violation('MISSING_LABEL',label))
    for line in answer_text.splitlines():
        for prefix,expected in allowed.primary.items():
            if line.startswith(prefix+':'):
                primary=next(iter(mentions(line.split(':',1)[1])),None)
                if primary and not _matches(*primary,expected):
                    violations.append(Violation('SWAPPED_PRIMARY',prefix))
    plain=strip_accents(answer_text.lower())
    if allowed.causal_level and re.search(r'tang do|giam do|nguyen nhan la|boi vi',plain):
        if allowed.causal_level>=2 or not any(label in plain for label in allowed.labels if len(label)>3):
            violations.append(Violation('UNSUPPORTED_CAUSE','Mệnh đề nguyên nhân chưa có chứng cứ.'))
    if re.search(r'cong thuc da (?:duyet|duoc duyet)|g0\.7\s*(?:da dat|da dong)',plain):
        violations.append(Violation('FALSE_APPROVAL','G0.7 chưa được duyệt.'))
    return VerifyResult(not violations,violations)

def repair_prompt(violations):
    return 'Use only source facts. Remove numbers and unsupported causes. Preserve required labels. Errors: '+','.join(v.code for v in violations)[:100]
