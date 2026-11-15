"""Synthetic input fixtures for snapshot->HE training adapter acceptance."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
from finance_input import AccessScope
from sme_fraud.import_files import canonical
from sme_fraud.native_rule_demo import base,finish
from sme_fraud.rule_snapshot import CONTRACT

ROOT=Path(__file__).resolve().parents[1]


def scope(company='C001',tenant='demo',permissions=None):
    return AccessScope(tenant,frozenset({company}),'snapshot-training-operator',frozenset(permissions or {'data.import','model.fit'}))


def native(company='C001',tenant='demo'):
    c=base();c.rows=[];start=datetime(2025,8,11,9,tzinfo=timezone(timedelta(hours=7)))
    for i,(amount,same) in enumerate([(1_000_000,True),(1_000_001,False),(2_000_000,False),(2_000_001,True)]):
        at=start+timedelta(hours=i)
        c.pay(at,amount,invoice_number='SIM_INV_'+str(i),invoice_gross_vnd=amount,creator_id=c.maker['employee_id'],approver_id=c.maker['employee_id'] if same else c.director['employee_id'],approved_at=(at-timedelta(minutes=1)).isoformat(),observed_at=at.isoformat())
    source=finish(c,company);source['tenant_id']=tenant;source['as_of']='2025-08-12T00:00:00+07:00'
    for coverage in source['coverage'].values():coverage.update(observed_at=source['as_of'],covered_through=source['as_of'])
    return dict(contract_version=CONTRACT,tenant_id=tenant,company_id=company,source=source,candidate_transaction_ids=[r['transaction_id'] for r in source['tables']['transactions']])


def canonical_source(company='C001',tenant='demo'):
    b=json.loads((ROOT/'sme_fraud/web/import-demo.json').read_bytes());b['tenant_id']=tenant
    for table,rows in b.items():
        if isinstance(rows,list):
            for row in rows:row['tenant_id']=tenant;row['company_id']=company
    tx=deepcopy(b['transactions'][0]);b['transactions']=[]
    for table in ('invoices','payment_allocations','supporting_documents','vendor_bank_history','payment_history_coverage','approvals'):b[table]=[]
    b['employees'].append(dict(deepcopy(b['employees'][0]),record_id='E002'))
    start=datetime(2026,10,1,9,tzinfo=timezone(timedelta(hours=7)))
    for i,(amount,same) in enumerate([(1_000_000,True),(1_000_001,False),(2_000_000,False),(2_000_001,True)]):
        at=(start+timedelta(hours=i)).isoformat();row=dict(deepcopy(tx),record_id='TRAIN_'+str(i),effective_at=at,observed_at=at,amount_vnd=amount)
        row['source']['record_id']=row['record_id'];b['transactions'].append(row)
        b['approvals'].append(dict(tenant_id=tenant,company_id=company,record_id='APP_'+str(i),revision=1,effective_at=at,observed_at=at,source=dict(system='snapshot-training-synthetic',record_id='APP_'+str(i),is_simulated=True),transaction_ref=dict(record_id=row['record_id'],revision=1),employee_ref=dict(record_id='E001' if same else 'E002',revision=1),decision='approved'))
    return b


def commit(store,data,authority,key='snapshot-training'):
    draft=store.upload(authority,canonical(data),'training-source.json',key+'-upload');report=store.preview(authority,draft['import_id'],1)
    if report['status']=='rejected':raise AssertionError([{k:e.get(k) for k in ('code','path','message')} for e in report['errors'][:2]])
    body={k:report[k] for k in ('preview_id','source_hash','mapping_hash','report_hash','context_hash')};body.update(expected_revision=report['revision'],acknowledge=True)
    return store.commit(authority,draft['import_id'],body,key+'-commit')['snapshot']['snapshot_id']


def request(snapshot,data):
    native_profile='source' in data
    rows=data['source']['tables']['transactions'] if native_profile else data['transactions']
    return dict(version='snapshot-he-training-adapter/0.1.0',snapshot_id=snapshot,as_of=data['source']['as_of'] if native_profile else '2026-10-02T00:00:00+07:00',training_start='2025-08-11T00:00:00+07:00' if native_profile else '2026-10-01T00:00:00+07:00',training_end='2025-08-12T00:00:00+07:00' if native_profile else '2026-10-02T00:00:00+07:00',rows=[dict(record_id=r['transaction_id'] if native_profile else r['record_id'],revision=r.get('revision',1)) for r in rows])
