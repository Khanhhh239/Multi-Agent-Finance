"""Read-only investigation projection over frozen observations, never a scorer."""
from collections import Counter
from contextlib import closing
from copy import deepcopy
import math
import sqlite3
from datetime import datetime, timezone
from .import_files import canonical,digest
from .pipeline_release_store import ensure
from .snapshot_features import utc

VERSION='transaction-investigation/1.0.0'
RELATIONS={'vendor_id':('vendors','Nhà cung cấp'),'customer_id':('customers','Khách hàng'),
 'employee_id':('employees','Nhân viên'),'creator_id':('employees','Người lập'),
 'approver_id':('employees','Người phê duyệt')}
IDS={'transactions':'transaction_id','vendors':'vendor_id','employees':'employee_id',
 'customers':'customer_id','invoices':'invoice_id','payment_allocations':'allocation_id','transaction_documents':'document_id','approvals':'record_id'}
KINDS={'transactions':'Giao dịch','vendors':'Nhà cung cấp','employees':'Nhân viên','customers':'Khách hàng',
 'invoices':'Hóa đơn','transaction_documents':'Chứng từ','bank':'Tài khoản','phone':'Điện thoại','address':'Địa chỉ'}

def number(value):
    return value if type(value) in (int,float) and math.isfinite(value) else None

def public_record(row):
    fields={'transaction_id','record_id','revision','posted_at','effective_at','observed_at','recorded_at','occurred_at',
      'txn_type','kind','amount_vnd','currency','vendor_id','customer_id','employee_id','creator_id','approver_id',
      'name','full_name','legal_name','invoice_id','invoice_number','invoice_gross_vnd','invoice_issued_at',
      'business_purpose','description','bank_code','status','decision','gross_vnd','number','transaction_ref','employee_ref'}
    return {k:str(v) if k.endswith('_vnd') and type(v) is int else deepcopy(v) for k,v in row.items() if k in fields}

def known(row,cutoff):
    clocks=[row.get(k) for k in ('observed_at','recorded_at','effective_at','posted_at','occurred_at') if row.get(k)]
    try:return bool(clocks) and all(utc(v)<=utc(cutoff) for v in clocks)
    except (ValueError,TypeError):return False

def graph(scope,manifest,data,transaction_id,cutoff):
    """Identity comes from scoped source IDs, never a display name. No live master joins."""
    tables=data.get('source',{}).get('tables',{})
    nodes={};edges={};limits=[];owner=[scope.tenant_id,next(iter(scope.company_ids)),manifest['snapshot_id']]
    def node(table,identity,record=None):
        key='n_'+digest(canonical(owner+[table,str(identity)]))[:32]
        if key not in nodes:
            label=(record or {}).get('full_name') or (record or {}).get('name') or (record or {}).get('legal_name') or str(identity)
            if table=='bank':label='•••• '+str(identity).split(':')[-1][-4:]
            nodes[key]=dict(id=key,table=table,record_id=str(identity) if table!='bank' else label,label=label,
                kind=KINDS.get(table,table),record=public_record(record or {}))
        return key
    def link(a,b,label,table,record,context=False):
        source=dict(table=table,record_id=record.get(IDS.get(table,'record_id'),record.get('record_id')),
            revision=record.get('revision',1),sha256=digest(canonical(record)),snapshot_id=manifest['snapshot_id'],
            known_at=record.get('observed_at') or record.get('recorded_at'),original_verified=False,
            source_kind='simulated' if data.get('source',{}).get('is_simulated') else 'source_export')
        eid='e_'+digest(canonical([a,b,label,source]))[:32]
        edges[eid]=dict(id=eid,source=a,target=b,label=label,context_only=context,
            verification='source_record_only',evidence=source)
    visible={}
    for table,idfield in IDS.items():
        latest={}
        for row in tables.get(table,[]):
            identity=row.get(idfield,row.get('record_id'))
            if identity is None or not known(row,cutoff):continue
            if row.get('company_id') not in (None,next(iter(scope.company_ids))):continue
            previous=latest.get(str(identity))
            stamp=lambda r:(r.get('revision',1),r.get('observed_at') or r.get('recorded_at') or '')
            if previous is None or stamp(row)>stamp(previous):latest[str(identity)]=row
        visible[table]=latest
    size=sum(map(len,visible.values()))
    if size>10000:
        return dict(nodes=[],edges=[],root=None,truncated=True,limits=['Nguồn vượt giới hạn 10.000 bản ghi của lượt xem quan hệ; chọn kỳ dữ liệu nhỏ hơn.'],as_of=cutoff)
    for table in ('vendors','employees','customers'):
        for identity,row in visible[table].items():
            a=node(table,identity,row)
            for field,label,context in [('bank_account','Tài khoản trong hồ sơ',False),('phone','Cùng số điện thoại',False),('address','Cùng địa chỉ · bối cảnh',True)]:
                value=row.get(field)
                if not value:continue
                typ={'bank_account':'bank','phone':'phone','address':'address'}[field]
                normalized=''.join(str(value).split()).casefold()
                if typ=='bank':normalized=str(row.get('bank_code') or '?')+':'+normalized;context=not bool(row.get('bank_code'))
                b=node(typ,normalized);link(a,b,label,table,row,context)
    for identity,row in visible['transactions'].items():
        a=node('transactions',identity,row)
        for field,(table,label) in RELATIONS.items():
            ref=row.get(field)
            if ref in (None,''):continue
            source=visible[table].get(str(ref))
            b=node(table,ref,source);link(a,b,label,'transactions',row)
        if row.get('recipient_account'):
            account=str(row.get('recipient_bank_code') or row.get('bank_code') or '?')+':'+''.join(str(row['recipient_account']).split()).casefold()
            link(a,node('bank',account),'Tài khoản nhận','transactions',row,account.startswith('?:'))
        if row.get('invoice_number'):
            invoice_key=str(row.get('vendor_id') or row.get('customer_id') or '?')+':'+str(row['invoice_number'])
            b=node('invoices','number:'+invoice_key,{'number':row['invoice_number'],'name':row['invoice_number']})
            link(a,b,'Tham chiếu hóa đơn','transactions',row)
    for identity,row in visible['invoices'].items():node('invoices',identity,row)
    for identity,row in visible['payment_allocations'].items():
        tid=str(row.get('transaction_id',''));iid=str(row.get('invoice_id',''))
        if tid in visible['transactions'] and iid in visible['invoices']:
            link(node('transactions',tid),node('invoices',iid),'Phân bổ thanh toán','payment_allocations',row)
    for identity,row in visible['transaction_documents'].items():
        tid=str(row.get('transaction_id',''))
        if tid in visible['transactions']:
            b=node('transaction_documents',identity,row);link(node('transactions',tid),b,'Chứng từ liên quan','transaction_documents',row)
    for identity,row in visible['approvals'].items():
        tid=str(row.get('transaction_ref',row.get('transaction_id','')));eid=str(row.get('employee_ref',row.get('employee_id','')))
        if tid in visible['transactions'] and eid in visible['employees']:
            link(node('transactions',tid),node('employees',eid),'Bản ghi phê duyệt','approvals',row)
    root='n_'+digest(canonical(owner+['transactions',transaction_id]))[:32]
    if root not in nodes:limits.append('Giao dịch chưa có bản ghi khả dụng tại thời điểm chốt; không suy ra quan hệ.')
    # Return only the connected component. Unrelated objects never enter the graph view.
    adjacent={}
    for edge in edges.values():
        adjacent.setdefault(edge['source'],set()).add(edge['target']);adjacent.setdefault(edge['target'],set()).add(edge['source'])
    reached={root} if root in nodes else set();front=set(reached)
    while front:
        nxt=set().union(*(adjacent.get(k,set()) for k in front))-reached
        reached.update(nxt);front=nxt
    return dict(nodes=[nodes[k] for k in sorted(reached)],edges=[v for v in edges.values() if v['source'] in reached and v['target'] in reached],
        root=root if root in nodes else None,truncated=False,limits=limits,as_of=cutoff,source_kind='simulated' if data.get('source',{}).get('is_simulated') else 'source_export',
        limitation='Quan hệ từ bản dữ liệu đã khóa; chưa xác minh chứng từ gốc, không tự kết luận gian lận.')

class Investigation:
    def __init__(self,workspace):
        self.work=workspace
    def _connection(self):
        path=self.work.release.store.path.with_name(self.work.release.store.path.stem+'-investigation.sqlite3')
        conn=sqlite3.connect(path,timeout=30);conn.row_factory=sqlite3.Row
        conn.execute('CREATE TABLE IF NOT EXISTS events (owner TEXT, review TEXT, key TEXT, action TEXT, actor TEXT, at TEXT, PRIMARY KEY(owner,review,key))')
        return conn
    def events(self,scope,review):
        with closing(self._connection()) as c, c:
            return [dict(r) for r in c.execute('SELECT action,actor,at FROM events WHERE owner=? AND review=? ORDER BY rowid',(self.work.reviews.owner(scope),review))]
    def record(self,scope,review,key,action,recheck):
        with closing(self._connection()) as c, c:
            c.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?)',(self.work.reviews.owner(scope),review,key,action,scope.actor_id,datetime.now(timezone.utc).isoformat()))
            if recheck is not None and recheck()!=scope:
                c.rollback();ensure(False,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.',403)
    def _items(self,scope,run_id,recheck):
        observed,packet=self.work.packet(scope,run_id,recheck)
        result=observed['result'];pipe=result['pipeline'];cases={c['case_id']:c for c in pipe['cases']}
        rows={r.get('transaction_id',r.get('record_id')):r for r in result['rows']}
        decisions={d['case_id']:d for d in pipe['queue']['decisions']}
        output=[]
        for item in packet['cases']:
            raw=cases.get(item['case_id'],{});review=self.work.reviews.get(scope,item['review_id'])
            history=self.events(scope,item['review_id']);feedback=review.get('feedback')
            status=('waiting_evidence' if feedback['outcome']=='inconclusive' else 'concluded') if feedback else ('in_review' if history else 'new')
            breakdown=raw.get('score_breakdown',{}).get('per_candidate',[])
            for tid in item['candidate_ids']:
                row=rows.get(tid,{})
                score=next((b for b in breakdown if b.get('transaction_id')==tid),{})
                signals=[dict(rule_id=r['rule_id'],name=r.get('name',r['rule_id']),status=r['status'],points=r.get('score'),
                    context_only=all(h.get('scoring_role')=='context' for h in r.get('hits',[]))) for r in row.get('rule_coverage',{}).get('rules',[]) if r.get('matched')]
                names={r['rule_id']:r.get('name',r['rule_id']) for r in row.get('rule_coverage',{}).get('rules',[])}
                for rid in raw.get('actionable_rule_ids',[]):
                    if rid not in {s['rule_id'] for s in signals}:signals.append(dict(rule_id=rid,name=names.get(rid,rid),status='signal_from_frozen_case',points=None,context_only=False))
                value=number(score.get('candidate_score'))
                output.append(dict(transaction_id=tid,run_id=run_id,snapshot_id=packet['snapshot_id'],bundle_id=packet['bundle_id'],as_of=packet['as_of'],
                    case_id=item['case_id'],review_id=item['review_id'],amount_vnd=str(row['amount_vnd']) if row.get('amount_vnd') is not None else None,
                    event_at=row.get('event_at'),kind=row.get('kind'),description=row.get('description',''),score=value,
                    score_status='available' if value is not None else 'unavailable',score_scale='saved_candidate_score',status=status,
                    mandatory=decisions.get(item['case_id'],{}).get('decision')=='mandatory_route',signals=signals,
                    explanation=dict(basis='Điểm giao dịch đã lưu trong phiên bản phân tích; không phải xác suất gian lận.',
                        raw_components={k:number(score.get(k)) for k in ('rule_score','ml_score')},
                        weights=deepcopy(pipe.get('case_policy',{}).get('scoring',{})),
                        branches=[dict(name=k,status=v.get('status','unavailable'),message=v.get('message')) for k,v in row.get('branches',{}).items()],
                        question=item['question'],why=item['why'],limitations=item['source_limits']),
                    source_kind=item['source_kind'],queue_mode=packet.get('queue_mode','shadow'),review=review))
                output[-1]['model_trace']=[dict(method_id=k,artifact_id=m.get('artifact_id') or m.get('model_id'),model_version=m.get('model_version') or m.get('details',{}).get('model_version'),version_tag=m.get('model_version') or m.get('details',{}).get('version_tag') or pipe.get('model_version_tag'),circuit_version=m.get('circuit_version'),feature_contract=m.get('feature_contract_fingerprint') or m.get('feature_schema_version'),preprocess_version=m.get('preprocess_version'),raw_score=number(m.get('raw_score')),relative_rank=number(m.get('score')),probability=number(m.get('probability')),threshold=number(m.get('threshold')),prediction=m.get('prediction'),error_code=m.get('error_code'),top_contributing_features=deepcopy(m.get('details',{}).get('top_contributing_features') or []),status=m.get('status','available' if m.get('available') else 'unavailable')) for k,m in row.get('methods',{}).items()]
                ml_attrs=[]
                for mt in output[-1]['model_trace']:
                    if mt['method_id'] not in ('rules','robust_z','supervised_lr') and mt.get('top_contributing_features'):
                        ml_attrs=mt['top_contributing_features'];break
                output[-1]['explanation']['ml_attributions']=ml_attrs
                output[-1]['explanation']['model_version_tag']=pipe.get('model_version_tag')
                output[-1]['explanation']['lr_model_version']=pipe.get('lr_model_version')

                # R3 — Unified 5-method view (Rules, Statistics, Graph, Unsupervised ML, Supervised LR)
                five_assess=row.get('five_method_assessment')
                if not isinstance(five_assess,dict):
                    from .lr_inference import SupervisedLRAdapter,build_five_method_row_assessment
                    lr_m=(row.get('methods') or {}).get('supervised_lr')
                    if not isinstance(lr_m,dict):
                        lr_m=SupervisedLRAdapter._unavailable_method_dto(
                            error_code='LR_NOT_INCLUDED_IN_RUN',
                            message='Lần phân tích này chạy trước khi bật mô hình Logistic Regression được phê duyệt.',
                            model_version=None,circuit_version=None)
                    five_assess=build_five_method_row_assessment(row,unsup_method_id=None,unsup_version_tag=pipe.get('model_version_tag'),lr_dto=lr_m)
                lr_entry=next((m for m in five_assess.get('five_methods',[]) if m.get('method_id')=='supervised_lr'),None)
                output[-1]['explanation']['five_methods']=deepcopy(five_assess.get('five_methods',[]))
                output[-1]['explanation']['unavailable_methods']=deepcopy(five_assess.get('unavailable_methods',[]))
                output[-1]['explanation']['unavailable_treated_as_zero']=False
                output[-1]['explanation']['supervised_lr']=deepcopy(lr_entry)
                output[-1]['explanation']['scoring_config']=deepcopy(five_assess.get('scoring_config'))
                output[-1]['lr_probability']=number(lr_entry.get('probability')) if isinstance(lr_entry,dict) and lr_entry.get('status')=='available' else None
                output[-1]['lr_prediction']=lr_entry.get('prediction') if isinstance(lr_entry,dict) and lr_entry.get('status')=='available' else None
                output[-1]['lr_status']=lr_entry.get('status') if isinstance(lr_entry,dict) else 'unavailable'

                weights=pipe.get('case_policy',{}).get('scoring',{});parts=[]
                for key,label,weight in [('rule_score','Luật nghiệp vụ','rule_weight'),('ml_score','ML không giám sát','ml_weight')]:
                    val=number(score.get(key));w=number(weights.get(weight))
                    parts.append(dict(name=label,raw_score=val,weight=w,contribution=round(val*w,6) if val is not None and w is not None else None))
                lr_val=number(score.get('lr_score'));lr_w=number(weights.get('calibrated_weight'))
                if lr_val is not None and lr_w is not None and lr_w>0:
                    output[-1]['explanation']['raw_components']['lr_score']=lr_val
                    parts.append(dict(name='Logistic Regression có giám sát',raw_score=lr_val,weight=lr_w,contribution=round(lr_val*lr_w,6)))
                output[-1]['explanation']['contributions']=parts
                output[-1]['explanation']['components_reconcile']=value is not None and abs(sum(p['contribution'] or 0 for p in parts)-value)<1e-6
        return observed,packet,output
    def queue(self,scope,run_id=None,recheck=None):
        listing=self.work.list_runs(scope,recheck)
        runs=[r for r in listing['runs'] if r['status']=='completed']
        all_runs=deepcopy(runs);rows=[]
        if run_id is not None:
            observed,packet,rows=self._items(scope,run_id,recheck)
        else:
            # Never compare raw scores from different model/bundle/period scales.
            for r in runs[:50]:
                _,_,candidate_rows=self._items(scope,r['run_id'],recheck)
                run_id=r['run_id']
                if candidate_rows:
                    rows=candidate_rows;break
        # Latest immutable occurrence of a transaction/case; retain the source binding.
        unique={}
        for row in rows:unique.setdefault((row['transaction_id'],row['case_id']),row)
        rows=sorted(unique.values(),key=lambda r:(r['score'] is None,-(r['score'] or 0),not r['mandatory'],r['transaction_id'],r['case_id']))
        for index,row in enumerate(rows,1):row['rank']=index;row['priority']='Bắt buộc rà' if row['mandatory'] else 'Ưu tiên '+str(index)
        if recheck is not None:ensure(recheck()==scope,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.',403)
        return dict(version=VERSION,company_id=next(iter(scope.company_ids)),rows=rows,runs=all_runs,run_id=run_id,
            counts=dict(Counter(r['status'] for r in rows)),truncated=len(runs)>50,
            limitation='Giao dịch của một lần phân tích đã tiếp nhận; không so điểm thô khác phiên bản. Ngân sách vẫn tính theo vụ. Điểm không phải xác suất gian lận.')
    def resolve(self,scope,run_id,tid,recheck=None,review_id=None):
        _,_,items=self._items(scope,run_id,recheck)
        matches=[r for r in items if r['transaction_id']==tid and (review_id is None or r['review_id']==review_id)]
        ensure(bool(matches),'INVESTIGATION_NOT_FOUND','Giao dịch không thuộc phiếu đã tiếp nhận của lần phân tích này.',404)
        return matches[0]
    def detail(self,scope,run_id,tid,recheck=None,review_id=None):
        observed,packet,items=self._items(scope,run_id,recheck)
        matches=[r for r in items if r['transaction_id']==tid and (review_id is None or r['review_id']==review_id)]
        ensure(bool(matches),'INVESTIGATION_NOT_FOUND','Giao dịch không thuộc phiếu đã tiếp nhận của lần phân tích này.',404)
        item=matches[0];case=self.work.case(scope,run_id,item['review_id'],recheck)
        manifest,data=self.work.release._snapshot(scope,packet['snapshot_id'],recheck)
        ensure(manifest['checksum']==packet['snapshot_checksum'] and manifest['data_checksum']==packet['data_checksum'],'INVESTIGATION_SOURCE_CHANGED','Nguồn không khớp phiếu đã khóa.',503)
        cutoff=min(utc(packet['as_of']),utc(item['event_at'])) if item['event_at'] else utc(packet['as_of'])
        diagram=graph(scope,manifest,data,tid,cutoff.isoformat())
        result=dict(item,graph=diagram,evidence=case['evidence'],next_step=case['next_step'],
            transaction=next((n['record'] for n in diagram['nodes'] if n['id']==diagram['root']),{}),
            related_transactions=[dict(n['record'],graph_node=n['id']) for n in diagram['nodes'] if n['table']=='transactions' and n['record_id']!=tid],
            workflow_history=self.events(scope,item['review_id']),other_cases=[dict(case_id=r['case_id'],review_id=r['review_id']) for r in items if r['transaction_id']==tid],
            review_path='/api/v1/companies/'+next(iter(scope.company_ids))+'/pipeline-workspace/runs/'+run_id+'/reviews/'+item['review_id'])
        if recheck is not None:ensure(recheck()==scope,'AUTH_CONTEXT_CHANGED','Quyền đã thay đổi.',403)
        return result
