"""Explicit synthetic invoice/payment export for P1 acceptance.

Expected outcomes are separate from source records and never enter features.
Coverage is a declaration from this controlled synthetic exporter, not a claim
that an unknown ERP's books have been externally verified.
"""
from copy import deepcopy
import json
from pathlib import Path

from finance_input import AccessScope
from sme_fraud.import_files import canonical,digest
from sme_fraud.p1_inputs import export_manifest
from sme_fraud.rule_sources import _resolve
from sme_fraud.rule_evaluation import _evaluate
from sme_fraud.snapshot_features import build_from_snapshot
from .snapshot_adapter import prepare_snapshot
from .inputs import decode_payment
from . import circuits

VERSION='he4-p1-source-demo/1.0.0'
AS_OF='2026-10-20T00:00:00+07:00'
ROOT=Path(__file__).resolve().parents[2]


def scope(company):
    if company not in ('C001','C002'):raise ValueError('explicit synthetic companies only')
    return AccessScope('demo',frozenset({company}),'p1-demo-setup-operator',frozenset({'data.import'}))


def source(company):
    scope(company);factor=1 if company=='C001' else 3
    template=json.loads((ROOT/'tests/fixtures/input_p1_v1_1.json').read_bytes())
    data={k:deepcopy(v) for k,v in template.items() if not isinstance(v,list)}
    for table in template:
        if isinstance(template[table],list):data[table]=[]
    for table in ('companies','vendors','employees'):
        data[table]=[deepcopy(template[table][0])]
    data['companies'][0].update(record_id=company,name='Doanh nghiệp mô phỏng '+company)
    invoice=deepcopy(template['invoices'][0])
    for identity,number,cap in [('P1_I_BASE','P1-BASE',10_000_000),('P1_I_GROUP','P1-GROUP',6_000_000),('P1_I_GAP','P1-GAP',10_000_000)]:
        data['invoices'].append(dict(deepcopy(invoice),record_id=identity,number=number,amount_vnd=cap*factor))
    rows=[('P1_T01',6_000_000,2,'P1_I_BASE'),
          ('P1_T02',3_000_000,3,'P1_I_BASE'),
          ('P1_T03',3_000_000,4,'P1_I_BASE'),
          ('P1_T04',-4_000_000,5,'P1_I_BASE'),
          ('P1_T05',1_000_000,6,'P1_I_BASE'),
          ('P1_T06',4_000_000,7,'P1_I_GROUP'),
          ('P1_T07',4_000_000,7,'P1_I_GROUP'),
          ('P1_T08',2_000_000,8,'P1_I_GAP')]
    for identity,amount,day,invoice_id in rows:
        at=f'2026-10-{day:02d}T08:00:00+07:00';amount*=factor
        tx=deepcopy(template['transactions'][1])
        tx.update(record_id=identity,effective_at=at,observed_at=at,amount_vnd=amount,
            description='Bản ghi mô phỏng '+identity+' theo hóa đơn '+invoice_id,
            kind='payment',payment_channel='bank',
            accounting_lines=[dict(account='331',debit_vnd=amount,credit_vnd=0),dict(account='112',debit_vnd=0,credit_vnd=amount)])
        allocation=deepcopy(template['payment_allocations'][0])
        allocation.update(record_id='P1_A_'+identity,effective_at=at,observed_at=at,amount_vnd=amount,
            kind='allocation',transaction_ref=dict(record_id=identity,revision=1),invoice_ref=dict(record_id=invoice_id,revision=1))
        if amount<0:
            tx.update(kind='adjustment',adjusts_ref=dict(record_id='P1_T01',revision=1),adjustment_reason='Điều chỉnh giảm khoản trả gốc theo nguồn mô phỏng')
            allocation.update(kind='adjustment',adjusts_ref=dict(record_id='P1_A_P1_T01',revision=1),adjustment_reason='Phân bổ điều chỉnh giảm có liên kết gốc')
        data['transactions'].append(tx);data['payment_allocations'].append(allocation)
    # The synthetic source certifies only these two obligations. GAP has an
    # invoice and allocation but deliberately no history coverage declaration.
    for index,at in enumerate(sorted({t['observed_at'] for t in data['transactions'] if t['record_id']!='P1_T08'})):
        claim=deepcopy(template['payment_history_coverage'][0])
        claim.update(record_id='P1_COV_'+str(index+1),observed_at=at,covered_through=at,
            invoice_refs=[dict(record_id=i,revision=1) for i in ('P1_I_BASE','P1_I_GROUP')],
            covered_from='2026-09-01T00:00:00+07:00',history_basis='since_inception',coverage_status='complete',export_id='P1_SYNTH_EXPORT_'+str(index+1))
        data['payment_history_coverage'].append(claim)
    for table,records in data.items():
        if isinstance(records,list):
            for record in records:
                record['tenant_id']='demo';record['company_id']=company
                record['source']=dict(system='p1-synthetic-export-v1',record_id=record['record_id'],is_simulated=True)
    for claim in data['payment_history_coverage']:claim['manifest']=export_manifest(data,claim)
    return data


def expected(company):
    scope(company);f=1 if company=='C001' else 3
    def result(prior,current,cap,matched,previous=False,group=None):
        row=dict(status='evaluated_hit' if matched else 'evaluated_no_hit',score=20 if matched else 0,matched=matched,
            prior_paid_vnd=prior*f,current_allocated_vnd=current*f,invoice_gross_vnd=cap*f,
            cumulative_paid_vnd=(prior+current)*f,excess_vnd=max(0,prior+current-cap)*f,previous_payment=previous)
        if group is not None:row['simultaneous']=dict(matched=True,points=20,cumulative_paid_vnd=group*f,excess_vnd=(group-cap)*f)
        return row
    return {'P1_T01':result(0,6_000_000,10_000_000,False),
            'P1_T02':result(6_000_000,3_000_000,10_000_000,False,True),
            'P1_T03':result(9_000_000,3_000_000,10_000_000,True,True),
            'P1_T04':dict(status='not_applicable',score=None,matched=None),
            'P1_T05':result(8_000_000,1_000_000,10_000_000,False,True),
            'P1_T06':result(0,4_000_000,6_000_000,False,group=8_000_000),
            'P1_T07':result(0,4_000_000,6_000_000,False,group=8_000_000),
            'P1_T08':dict(status='unavailable',score=None,matched=None)}


def save_snapshot(store,company,data):
    authority=scope(company);key='p1-source-demo-'+digest(canonical(data))[:48]
    draft=store.upload(authority,canonical(data),company+'_P1_5_ca_8_ban_ghi.json',key+'-upload')
    current=store.get_import(authority,draft['import_id'])
    if current['status']=='committed':
        manifest=store.get_snapshot(authority,current['snapshot_id'])
        if manifest['source_hash']!=digest(canonical(data)):raise AssertionError('saved source changed')
        return manifest['snapshot_id']
    preview=store.preview(authority,draft['import_id'],draft['revision'])
    if preview['status']=='rejected':raise ValueError(preview['errors'])
    body={k:preview[k] for k in ('preview_id','source_hash','mapping_hash','report_hash','context_hash')}
    body.update(expected_revision=draft['revision'],acknowledge=True)
    first=store.commit(authority,draft['import_id'],body,key+'-save')
    again=store.commit(authority,draft['import_id'],body,key+'-save')
    if first['snapshot']['snapshot_id']!=again['snapshot']['snapshot_id']:raise AssertionError('duplicate snapshot')
    return first['snapshot']['snapshot_id']


def inspect(store,company,snapshot,as_of=AS_OF):
    """Compare hand-calculated expectations, retained engine and HE input plan.

    circuits.p1 here is a plain reference, NOT evidence of actual HE execution.
    Actual native HE parity is performed by a separate HTTP acceptance runner.
    """
    import numpy as np
    authority=scope(company);frame=build_from_snapshot(store,authority,snapshot,as_of)
    data=json.loads(store.get_snapshot(authority,snapshot,data=True));private,public=_resolve(data,frame,authority)
    plan=prepare_snapshot(store,authority,snapshot,as_of)
    plans={(r['record_id'],r['revision']):r for r in plan['rows']};expectations=expected(company);output=[]
    if len(frame['rows'])!=8 or len(plans)!=8:raise AssertionError('source rows lost')
    for meta in frame['rows']:
        identity=meta['record_id'],meta['revision'];want=expectations[identity[0]]
        p1=next(r for r in _evaluate(private[identity],public[identity],authority,meta)['rules'] if r['rule_id']=='P1')
        for key in ('status','score','matched'):
            if p1[key]!=want[key]:raise AssertionError((company,identity,key,p1[key],want[key]))
        branch=plans[identity]['branches']['rules'];checks=[]
        if p1['status'].startswith('evaluated_'):
            check,=p1['details']['invoice_checks']
            for name in ('prior_paid_vnd','current_allocated_vnd','invoice_gross_vnd','cumulative_paid_vnd','excess_vnd','previous_payment'):
                if check[name]!=want[name]:raise AssertionError((identity,name))
            if not branch['available']:raise AssertionError(branch)
            for request in branch['requests']:
                values=[np.asarray(v,dtype=np.int64) for v in request['values']]
                actual=decode_payment(circuits.p1(*values))
                reference=check if request['role']=='row' else p1['details']['simultaneous_checks'][0]
                for key,value in actual.items():
                    if key=='current_allocated_vnd' and request['role']=='simultaneous_group':
                        if value!=reference['group_allocated_vnd']:raise AssertionError((identity,'group_allocated_vnd'))
                    if key in reference and value!=reference[key]:raise AssertionError((identity,request['role'],key,value,reference[key]))
                checks.append(dict(role=request['role'],**actual))
            if want.get('simultaneous'):
                group,=p1['details']['simultaneous_checks']
                for name,value in want['simultaneous'].items():
                    if group[name]!=value:raise AssertionError((identity,name))
        elif branch['requests']:raise AssertionError('unavailable/not-applicable source encrypted')
        if identity[0]=='P1_T08' and not any(g['code']=='p1_history_scope_missing' for g in p1['gaps']):raise AssertionError('missing coverage not explained')
        output.append(dict(record_id=identity[0],status=p1['status'],row_score=p1['score'],matched=p1['matched'],
            reason=p1['reason'],gaps=p1['gaps'],invoice_checks=p1['details'].get('invoice_checks',[]),
            simultaneous_checks=p1['details'].get('simultaneous_checks',[]),plain_circuit_checks=checks))
    return dict(version=VERSION,company_id=company,snapshot_id=snapshot,as_of=as_of,row_count=8,
        statuses={s:sum(r['status']==s for r in output) for s in sorted({r['status'] for r in output})},
        simulated_data=True,manual_expected_parity=True,retained_engine_parity=True,plain_circuit_parity=True,
        actual_fhe=False,model_fit_performed=False,rows=output),plan
