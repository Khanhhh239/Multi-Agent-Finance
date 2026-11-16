"""Synthetic chronological batches; shared by tests and isolated native demo."""
from datetime import datetime,timedelta,timezone
from sme_fraud.native_rule_demo import base,finish
from sme_fraud.rule_snapshot import CONTRACT
from experiments.he_training.batch_plan import VERSION


def native_batches(company='C001',tenant='batch-demo'):
    c=base();c.rows=[];start=datetime(2025,8,11,9,tzinfo=timezone(timedelta(hours=7)))
    for i in range(12):
        at=start+timedelta(hours=i if i<8 else 24+i-8)
        same=i<4 or i>=8 and i%2==0
        amount=1_000_000 if i<4 or i>=8 and i%2==0 else 1_000_001
        c.pay(at,amount,invoice_number='SIM_BATCH_INV_'+str(i),invoice_gross_vnd=amount,creator_id=c.maker['employee_id'],
              approver_id=c.maker['employee_id'] if same else c.director['employee_id'],approved_at=(at-timedelta(minutes=1)).isoformat(),observed_at=at.isoformat())
    source=finish(c,company);source['tenant_id']=tenant;source['as_of']='2025-08-13T00:00:00+07:00'
    for coverage in source['coverage'].values():coverage.update(observed_at=source['as_of'],covered_through=source['as_of'])
    data=dict(contract_version=CONTRACT,tenant_id=tenant,company_id=company,source=source,candidate_transaction_ids=[r['transaction_id'] for r in source['tables']['transactions']])
    ids=[dict(record_id=r['transaction_id'],revision=r.get('revision',1)) for r in source['tables']['transactions']]
    request=dict(version=VERSION,snapshot_id=None,as_of=source['as_of'],training_start='2025-08-11T00:00:00+07:00',training_end='2025-08-12T00:00:00+07:00',
        evaluation_start='2025-08-12T00:00:00+07:00',evaluation_end=source['as_of'],training_batches=[ids[:4],ids[4:8]],evaluation_batches=[ids[8:]])
    return data,request
