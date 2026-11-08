"""Source-only factual dossiers for assistant review; never independent outcomes.

No model/rule/branch inputs, no human signatures, and no imputed review minutes.
"""
from __future__ import annotations

from collections import Counter,defaultdict
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

CLOCKS=('observed_at','recorded_at','verified_at','approved_at','action_at','posted_at','issued_at','closed_at')
MEMBER_FIELDS=('transaction_id','posted_at','created_at','approved_at','effective_date','txn_type','amount_vnd','currency','payment_channel','account_pair',
    'journal_signature','accounting_framework','creator_id','approver_id','employee_id','vendor_id','customer_id',
    'recipient_account','recipient_bank_code','invoice_id','invoice_number','invoice_gross_vnd','support_doc_count',
    'goods_receipt_verified','evidence_on_file','self_approval_exception_id','approval_limit_vnd',
    'recognised_input_vat_vnd','recognised_output_vat_vnd','invoice_net_vnd','invoice_vat_vnd',
    'journal_document_id','linked_document_id','contract_id','payroll_period')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def instant(value):
    result=datetime.fromisoformat(value)
    if result.tzinfo is None:raise ValueError('Evidence clocks require a timezone')
    return result.astimezone(timezone.utc)


def integer(value):
    return int(value or 0)


def refs(rows,table,condition=lambda r:True):
    return [dict(ref=f'/tables/{table}/{i}',**row) for i,row in enumerate(rows) if condition(row)]


def factual_dossier(unit,evidence):
    cutoff=instant(unit['cutoff_exclusive']);tables=evidence['tables']
    if evidence['company_code']!=unit['company_code'] or instant(evidence['cutoff_exclusive'])!=cutoff:
        raise ValueError('Evidence identity/cutoff differs')
    for table,rows in tables.items():
        for row in rows:
            if row.get('company_id') and row['company_id']!=unit['company_code']:
                raise ValueError('Foreign-company evidence')
            clocks=[row[f] for f in CLOCKS if row.get(f)]
            if table!='calendar' and not clocks:raise ValueError('Unversioned evidence row')
            if any(instant(v)>=cutoff for v in clocks):raise ValueError('Future evidence row')
    members=tables['member_transactions'];related=tables['related_transactions']
    member_ids={r['transaction_id'] for r in members}
    if len(member_ids)!=len(members) or member_ids!=set(evidence['scope_transaction_ids']):
        raise ValueError('Member identity differs')
    rows=members+related;tx_ids={r['transaction_id'] for r in rows}
    people={r.get(k) for r in members for k in ('employee_id','creator_id','approver_id') if r.get(k)}
    vendor_ids={r['vendor_id'] for r in rows if r.get('vendor_id')}
    invoice_ids={r['invoice_id'] for r in rows if r.get('invoice_id')}
    if evidence.get('source_object','').startswith('invoice:'):invoice_ids.add(evidence['source_object'].split(':',1)[1])
    doc_ids={r.get(k) for r in rows for k in ('journal_document_id','linked_document_id') if r.get(k)}
    primary_docs={r.get('journal_document_id') for r in members if r.get('journal_document_id')}
    journals=[]
    for did in sorted(doc_ids):
        lines=refs(tables.get('journal_lines',[]),'journal_lines',lambda r:r['document_id']==did)
        if not lines:
            journals.append(dict(document_id=did,primary=did in primary_docs,lines=0,debit=None,credit=None,net=None,accounts=[]))
            continue
        debit=sum(integer(r['debit_vnd']) for r in lines);credit=sum(integer(r['credit_vnd']) for r in lines)
        journals.append(dict(document_id=did,primary=did in primary_docs,lines=len(lines),debit=debit,credit=credit,
            net=debit-credit,accounts=sorted({r['account_code'] for r in lines}),refs=[r['ref'] for r in lines]))
    invoices=refs(tables.get('invoices',[]),'invoices',lambda r:r['invoice_id'] in invoice_ids)
    statuses=refs(tables.get('vendor_status_history',[]),'vendor_status_history',lambda r:r['vendor_id'] in vendor_ids)
    vendor_master=refs(tables.get('vendors',[]),'vendors',lambda r:r['vendor_id'] in vendor_ids)
    mismatches=[]
    for r in members:
        masters=[m for m in vendor_master if m['vendor_id']==r.get('vendor_id') and instant(m['recorded_at'])<=instant(r['posted_at'])]
        master=max(masters,key=lambda m:instant(m['recorded_at'])) if masters else None
        if master and r.get('recipient_account') and master.get('bank_account') and r['recipient_account']!=master['bank_account']:
            mismatches.append(dict(transaction_id=r['transaction_id'],paid_account=r['recipient_account'],master_account=master['bank_account'],master_ref=master['ref']))
    duplicates=[];same=defaultdict(list)
    for r in rows:
        if r['txn_type']=='vendor_payment' and r.get('invoice_number'):
            same[(r.get('vendor_id'),r['invoice_number'],r['amount_vnd'],r.get('currency'))].append(r['transaction_id'])
    for key,tids in same.items():
        if len(set(tids))>1 and member_ids.intersection(tids):duplicates.append(dict(vendor_id=key[0],invoice_number=key[1],amount_vnd=key[2],transaction_ids=sorted(set(tids))))
    periods={r.get('payroll_period') for r in members if r.get('payroll_period')}
    employees=refs(tables.get('employees',[]),'employees',lambda r:r['employee_id'] in people)
    latest_employees={}
    for r in employees:
        if r['employee_id'] not in latest_employees or instant(r['recorded_at'])>instant(latest_employees[r['employee_id']]['recorded_at']):
            latest_employees[r['employee_id']]=r
    employee_bank_differences=[]
    for m in members:
        choices=[r for r in employees if r['employee_id']==m.get('employee_id') and instant(r['recorded_at'])<=instant(m['posted_at'])]
        historical=max(choices,key=lambda r:instant(r['recorded_at'])) if choices else None
        if historical and m.get('recipient_account') and historical.get('bank_account') and m['recipient_account']!=historical['bank_account']:
            employee_bank_differences.append(dict(transaction_id=m['transaction_id'],paid_account=m['recipient_account'],
                master_account=historical['bank_account'],master_ref=historical['ref']))
    nodes=people|vendor_ids|{r['customer_id'] for r in members if r.get('customer_id')}
    shared=defaultdict(list)
    for edge in refs(tables.get('entity_links',[]),'entity_links'):
        signature=(edge['link_type'],edge['target_id'],edge.get('bank_code','') if edge['link_type']=='bank_account' else '')
        shared[signature].append(edge)
    shared_attributes=[]
    for signature,edges in shared.items():
        sources={r['source_id'] for r in edges}
        if len(sources)>1 and sources&nodes:
            shared_attributes.append(dict(link_type=signature[0],value=signature[1],bank_code=signature[2],
                source_entities=sorted(sources),refs=[r['ref'] for r in edges]))
    employment=refs(tables.get('employment_events',[]),'employment_events',lambda r:r['employee_id'] in people)
    payroll=refs(tables.get('payroll_settlements',[]),'payroll_settlements',lambda r:r.get('transaction_id') in member_ids or
        (r['employee_id'] in people and r.get('payroll_period') in periods))
    attendance=refs(tables.get('attendance',[]),'attendance',lambda r:r['employee_id'] in people and r.get('payroll_period') in periods)
    entitlements=refs(tables.get('payroll_entitlements',[]),'payroll_entitlements',lambda r:r['employee_id'] in people and r.get('payroll_period') in periods)
    actions=refs(tables.get('system_actions',[]),'system_actions',lambda r:r.get('transaction_id') in member_ids)
    overrides=refs(tables.get('override_events',[]),'override_events',lambda r:r.get('transaction_id') in member_ids)
    leaves=refs(tables.get('leave_periods',[]),'leave_periods',lambda r:r['employee_id'] in people and any(
        instant(r['starts_at'])<=instant(m[k])<=instant(r['ends_at']) for m in members for k in ('posted_at','created_at','approved_at') if m.get(k)))
    authorizations=refs(tables.get('leave_activity_authorizations',[]),'leave_activity_authorizations',lambda r:r['employee_id'] in people)
    recurring=refs(tables.get('recurring_payments',[]),'recurring_payments',lambda r:any(
        (r.get('vendor_id') and r['vendor_id']==m.get('vendor_id')) or (r.get('employee_id') and r['employee_id']==m.get('employee_id')) or
        (r.get('contract_id') and r['contract_id']==m.get('contract_id')) for m in members))
    kinds={r['txn_type'] for r in members}
    policies=refs(tables.get('workflow_policies',[]),'workflow_policies',lambda r:r['txn_type'] in kinds|{'*','all',''})
    receivables=refs(tables.get('receivable_invoices',[]),'receivable_invoices',lambda r:r['invoice_id'] in invoice_ids)
    allocations=refs(tables.get('receipt_allocations',[]),'receipt_allocations',lambda r:r['invoice_id'] in invoice_ids)
    explanations=refs(tables.get('receivable_explanations',[]),'receivable_explanations',lambda r:r['invoice_id'] in invoice_ids)
    register=refs(tables.get('document_register',[]),'document_register',lambda r:r.get('transaction_id') in member_ids or r.get('document_id') in primary_docs)
    cancellations=refs(tables.get('document_cancellations',[]),'document_cancellations',lambda r:r.get('document_id') in primary_docs)
    audit=refs(tables.get('journal_audit_log',[]),'journal_audit_log',lambda r:r.get('transaction_id') in member_ids)
    compact_members=[dict(ref=f'/tables/member_transactions/{i}',**{f:r.get(f,'') for f in MEMBER_FIELDS}) for i,r in enumerate(members)]
    return dict(review_unit_id=unit['review_unit_id'],company_code=unit['company_code'],cutoff_exclusive=unit['cutoff_exclusive'],
        evidence_sha256=unit['evidence_sha256'],source_object=evidence.get('source_object',''),members=compact_members,
        related_transactions=refs(related,'related_transactions'),journals=journals,invoices=invoices,
        bank_master_differences=mismatches,employee_bank_master_differences=employee_bank_differences,
        shared_entity_attributes=shared_attributes,vendor_master=vendor_master,
        duplicate_payment_context=duplicates,vendor_status_history=statuses,
        employees=list(latest_employees.values()),employment_events=employment,payroll_settlements=payroll,
        attendance=attendance,payroll_entitlements=entitlements,leaves=leaves,leave_authorizations=authorizations,
        actions=actions,overrides=overrides,workflow_policies=policies,recurring_payments=recurring,
        receivables=receivables,receipt_allocations=allocations,receipt_coverage=refs(tables.get('receipt_coverage',[]),'receipt_coverage'),
        receivable_explanations=explanations,register=register,cancellations=cancellations,journal_audit=audit,
        closing_periods=refs(tables.get('closing_periods',[]),'closing_periods'),
        materiality_policies=refs(tables.get('materiality_policies',[]),'materiality_policies'),
        available_tables=sorted(tables),source_limitation='Synthetic attestations only; original scans are not included')


def build_dossiers(public,output):
    public,output=Path(public).resolve(),Path(output).resolve()
    if output.exists():raise FileExistsError('Use a fresh assistant review folder')
    if output.is_relative_to(public) or public.is_relative_to(output):raise ValueError('Preserve the human review packet')
    manifest_path=public/'review_manifest.json';manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    inputs={str(manifest_path):sha(manifest_path)}
    for name,h in manifest['readonly_sha256'].items():
        path=(public/name).resolve()
        if not path.is_relative_to(public) or sha(path)!=h:raise ValueError('Readonly evidence commitment changed')
        inputs[str(path)]=h
    output.mkdir(parents=True);(output/'dossiers').mkdir();index=[]
    for i,unit in enumerate(manifest['units'],1):
        path=public/'evidence'/unit['review_unit_id']/'evidence.json'
        if sha(path)!=unit['evidence_sha256']:raise ValueError('Evidence identity hash differs')
        dossier=factual_dossier(unit,json.loads(path.read_text(encoding='utf-8')))
        (output/'dossiers'/(unit['review_unit_id']+'.json')).write_text(json.dumps(dossier,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        index.append(dict(order=i,**unit,member_count=len(dossier['members'])))
    if any(sha(p)!=h for p,h in inputs.items()):raise ValueError('Input changed during dossier extraction')
    (output/'source_commitment.json').write_text(json.dumps(inputs,indent=2)+'\n',encoding='utf-8')
    (output/'index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return index
