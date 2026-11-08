"""Small, labelled-as-synthetic source controls; expectations precede scoring.

Each control has its own synthetic company, so unrelated controls cannot supply
evidence for one another. This is a software test dataset, not a fraud sample.
"""
import argparse
from collections import Counter,defaultdict
import copy,json
from datetime import timedelta
from pathlib import Path

from .accounting import enrich_accounting
from .evidence_cases import prepare,decision
from .evidence_policy import SOURCES
from .features import build_features,FEATURE_DESCRIPTIONS
from .feature_contract import cache_contract,sha
from .generate import stamp,write_csv,parse
from .rules import DEFAULT_CONFIG,INPUT_TABLES,OPTIONAL_INPUT_TABLES,load_inputs,score_rules
from .case_queue import review_queue
from .synthetic_dataset import columns

VERSION='rule-branch-controls-20261027-v1'
RULES=('C4','E2','F2','F3','F4')
SEEDS=(2026102701,2026102702)
BASE={
 'C4':{'positive':True,'authorized':False,'late_source':False,'cancel_after_action':True,'end_boundary':False},
 'E2':{'positive':True,'final_payment':False,'missing_period':None,'rehire':False,'late_source':False},
 'F2':{'positive':True,'authorized':False,'completed':False,'missing_policy':None},
 'F3':{'positive':True,'duplicate':True,'cancelled_gap':False,'not_closed':None,'late_cancel':True,'missing_cancel_coverage':None},
 'F4':{'positive':True,'fully_paid':False,'partial':True,'explanation':False,'missing_coverage':None,'overallocated':None,'future_receipt':True}}

# These are acceptance inputs, never computed from a detector prediction.
EXTRA={
 'C4':[
  ('checker_on_leave','positive',True,'actor_binding'),
  ('both_actions_one_authorized','authorized',True,'mixed_events'),
  ('leave_start_at_action','positive',True,'boundary'),
  ('leave_starts_after_action','positive',False,'boundary'),
  ('permission_ends_at_action','authorized',True,'boundary'),
  ('permission_wrong_action','authorized',True,'actor_binding'),
  ('permission_revoked_before','authorized',True,'revision'),
  ('permission_revoked_after','authorized',False,'revision'),
  ('leave_revoked_before','positive',False,'revision'),
  ('missing_action_proof','positive',False,'missing_evidence'),
  ('wrong_action_actor','positive',False,'actor_binding'),
  ('permission_known_after_action','authorized',True,'late_evidence'),
  ('master_updated_after_action','positive',True,'master_change')],
 'E2':[
  ('approved_backpay','final_payment',False,'exception'),
  ('approved_severance','final_payment',False,'exception'),
  ('approved_bonus','final_payment',False,'exception'),
  ('bonus_for_later_service','final_payment',None,'missing_evidence'),
  ('final_amount_short_one','final_payment',None,'boundary'),
  ('settlement_wrong_employee','positive',None,'actor_binding'),
  ('settlement_wrong_period','positive',None,'actor_binding'),
  ('self_approved_settlement','positive',None,'exception'),
  ('termination_effective_today','positive',False,'boundary'),
  ('rehire_known_after_cutoff','rehire',True,'late_evidence'),
  ('termination_revoked_before','positive',False,'revision'),
  ('settlement_known_at_cutoff','positive',True,'boundary'),
  ('settlement_known_after_cutoff','positive',None,'late_evidence'),
  ('reversed_service_period','positive','rejected','input_rejection')],
 'F2':[
  ('control_not_required','positive',False,'exception'),
  ('override_wrong_role','authorized',True,'actor_binding'),
  ('role_promoted_after_action','positive',True,'master_change'),
  ('override_at_cap','authorized',False,'boundary'),
  ('override_above_cap_one','authorized',True,'boundary'),
  ('policy_known_at_action','authorized',False,'boundary'),
  ('policy_known_after_action','authorized',None,'late_evidence'),
  ('pending_override','positive',False,'not_applicable'),
  ('cancelled_override','positive',False,'revision'),
  ('expired_policy','positive',None,'boundary'),
  ('authorized_and_unauthorized','authorized',True,'mixed_events'),
  ('authorized_and_unknown','authorized',None,'mixed_events'),
  ('override_without_proof','positive',False,'missing_evidence')],
 'F3':[
  ('continuous_series','positive',False,'negative'),
  ('duplicate_log_same_document','duplicate',False,'identity'),
  ('cancelled_duplicate_document','duplicate',False,'exception'),
  ('draft_duplicate_peer','duplicate',False,'identity'),
  ('future_duplicate_peer','duplicate',False,'late_evidence'),
  ('duplicate_peer_other_series','duplicate',False,'scope'),
  ('cancellation_other_series','cancelled_gap',True,'scope'),
  ('revoked_cancellation','cancelled_gap',True,'revision'),
  ('register_known_at_cutoff','positive',False,'boundary'),
  ('register_known_after_cutoff','positive',True,'late_evidence'),
  ('inverted_series_range','positive','rejected','input_rejection'),
  ('oversize_series_range','positive','rejected','input_rejection')],
 'F4':[
  ('overdue_exactly_60_days','positive',False,'boundary'),
  ('overdue_61_days','positive',True,'boundary'),
  ('invoice_due_today','positive',False,'negative'),
  ('zero_invoice_amount','positive',None,'missing_evidence'),
  ('cancelled_invoice','positive',None,'not_applicable'),
  ('invoice_due_before_issue','positive','rejected','input_rejection'),
  ('receipt_wrong_customer','fully_paid',None,'scope'),
  ('allocation_other_invoice','fully_paid',True,'scope'),
  ('unverified_allocation','fully_paid',True,'missing_evidence'),
  ('receipt_nonfinancial','fully_paid',None,'invalid_linkage'),
  ('receipt_journal_only','fully_paid',None,'invalid_linkage'),
  ('verification_before_receipt','fully_paid',None,'late_evidence'),
  ('unknown_verifier','fully_paid',None,'actor_binding'),
  ('coverage_starts_too_late','positive',None,'missing_evidence'),
  ('coverage_known_after_cutoff','positive',None,'late_evidence'),
  ('expired_explanation','explanation',True,'boundary'),
  ('revoked_explanation','explanation',True,'revision'),
  ('explanation_expires_at_cutoff','explanation',False,'boundary'),
  ('allocation_id_binding_conflict','fully_paid','rejected','input_rejection')]}


def catalog():
    result=[]
    for code in RULES:
        items=[(v,v,e,'existing_control') for v,e in BASE[code].items()]+EXTRA[code]
        for variant,base,expected,dimension in items:
            scope='transaction' if code in {'C4','E2','F2'} or code=='F3' and base=='duplicate' else 'series:PAY_2025' if code=='F3' else 'invoice:AR1'
            finding_status=('none' if code=='F3' and base=='not_closed' or code=='F4' and variant=='cancelled_invoice' else
                            'information_gap' if expected is None else 'evaluated')
            result.append(dict(rule_id=code,variant=variant,base=base,expected=expected,dimension=dimension,scope=scope,
                existing_dimension_coverage='covered_in_previous_matrix',new_detail_control=dimension!='existing_control',finding_status=finding_status,
                interpretation='No signal without action/proof is not proof that the business condition was absent.' if variant in {'missing_action_proof','wrong_action_actor','override_without_proof','pending_override'} else 'Synthetic source-condition control; not a fraud conclusion.'))
    return result


def build_control(spec,seed):
    code,variant=spec['rule_id'],spec['variant']
    c,row,_,scope=prepare(code,spec['base'],seed)
    # Remove random preparation lag from the predicate under test.
    row['created_at']=stamp(c.at-timedelta(hours=1))
    for event in c.tables.get('system_actions',[]):
        if event['transaction_id']==row['transaction_id'] and event['action']=='maker':event['action_at']=row['created_at']
    for event in c.tables.get('override_events',[]):
        if event['transaction_id']==row['transaction_id']:event['operation_at']=row['created_at']
    if code=='C4':
        leave=c.tables['leave_periods'][0];action=c.tables['system_actions'][0]
        permissions=c.tables.get('leave_activity_authorizations',[]);permission=permissions[0] if permissions else None
        at=parse(row['created_at'])
        if variant=='end_boundary':leave['ends_at']=row['created_at']
        elif variant=='checker_on_leave':
            row['approver_id']=c.worker['employee_id'];leave['employee_id']=c.worker['employee_id']
            action.update(action='checker',employee_id=c.worker['employee_id'],action_at=row['approved_at'])
        elif variant=='both_actions_one_authorized':
            row['approver_id']=c.worker['employee_id']
            c.tables['leave_periods'].append(dict(leave,leave_id='CHECKER_LEAVE',employee_id=c.worker['employee_id']))
            c.tables['system_actions'].append(dict(action,action_id='CHECKER_ACTION',employee_id=c.worker['employee_id'],action='checker',action_at=row['approved_at']))
        elif variant=='leave_start_at_action':leave['starts_at']=row['created_at']
        elif variant=='leave_starts_after_action':leave['starts_at']=stamp(at+timedelta(seconds=1))
        elif variant=='permission_ends_at_action':permission['ends_at']=row['created_at']
        elif variant=='permission_wrong_action':permission['action']='checker'
        elif variant in {'permission_revoked_before','permission_revoked_after'}:
            c.tables['leave_activity_authorizations'].append(dict(permission,status='revoked',observed_at=stamp(at+timedelta(seconds=-1 if variant.endswith('before') else 1))))
        elif variant=='leave_revoked_before':c.tables['leave_periods'].append(dict(leave,status='revoked',observed_at=stamp(at-timedelta(seconds=1))))
        elif variant=='missing_action_proof':action['evidence_id']=''
        elif variant=='wrong_action_actor':action['employee_id']=c.worker['employee_id']
        elif variant=='permission_known_after_action':permission['observed_at']=stamp(at+timedelta(seconds=1))
        elif variant=='master_updated_after_action':c.tables['employees'].append(dict(c.maker,phone='SIM_UPDATED_PHONE',recorded_at=stamp(at+timedelta(seconds=1))))
    elif code=='E2':
        event=c.tables['employment_events'][0];settlements=c.tables.get('payroll_settlements',[]);settlement=settlements[0] if settlements else None
        if variant.startswith('approved_'):settlement['payment_kind']=variant.removeprefix('approved_')
        elif variant=='bonus_for_later_service':settlement.update(payment_kind='bonus',service_period_end='2025-09-01')
        elif variant=='final_amount_short_one':settlement['authorized_amount_vnd']=row['amount_vnd']-1
        elif variant=='settlement_wrong_employee':settlement['employee_id']=c.maker['employee_id']
        elif variant=='settlement_wrong_period':settlement['payroll_period']='2025-08'
        elif variant=='self_approved_settlement':settlement['approver_id']=c.worker['employee_id']
        elif variant=='termination_effective_today':event['effective_date']=c.at.date().isoformat()
        elif variant=='rehire_known_after_cutoff':c.tables['employment_events'][-1]['observed_at']=stamp(c.at+timedelta(seconds=1))
        elif variant=='termination_revoked_before':c.tables['employment_events'].append(dict(event,status='revoked',observed_at=stamp(c.at-timedelta(seconds=1))))
        elif variant=='settlement_known_at_cutoff':settlement['observed_at']=row['posted_at']
        elif variant=='settlement_known_after_cutoff':settlement['observed_at']=stamp(c.at+timedelta(seconds=1))
        elif variant=='reversed_service_period':settlement.update(service_period_start='2025-09-30',service_period_end='2025-09-01')
    elif code=='F2':
        policy=c.tables['workflow_policies'][0] if c.tables['workflow_policies'] else None;event=c.tables['override_events'][0];at=parse(event['operation_at'])
        if variant=='control_not_required':policy['required']=0
        elif variant=='override_wrong_role':policy['authorized_override_roles']='director'
        elif variant=='role_promoted_after_action':
            policy.update(allow_override=1,authorized_override_roles='director')
            c.tables['employees'].append(dict(c.maker,role='director',recorded_at=stamp(at+timedelta(seconds=1))))
        elif variant in {'override_at_cap','override_above_cap_one'}:row.update(amount_vnd=20_000_000+(variant=='override_above_cap_one'),invoice_gross_vnd=0)
        elif variant=='policy_known_at_action':policy['observed_at']=event['operation_at']
        elif variant=='policy_known_after_action':policy['observed_at']=stamp(at+timedelta(seconds=1))
        elif variant=='pending_override':event['status']='pending'
        elif variant=='cancelled_override':event['status']='cancelled'
        elif variant=='expired_policy':policy['effective_to']=stamp(at-timedelta(seconds=1))
        elif variant in {'authorized_and_unauthorized','authorized_and_unknown'}:
            other=dict(event,override_id='SECOND_OVERRIDE',control_id='SECOND_CONTROL');c.tables['override_events'].append(other)
            if variant=='authorized_and_unauthorized':c.tables['workflow_policies'].append(dict(policy,workflow_policy_id='SECOND_POLICY',control_id='SECOND_CONTROL',allow_override=0))
        elif variant=='override_without_proof':event['evidence_id']=''
    elif code=='F3':
        series=c.tables['document_series'][0];docs=c.tables['document_register'];peer=docs[-1]
        if variant in {'continuous_series','register_known_at_cutoff','register_known_after_cutoff'}:
            docs.append(dict(docs[0],register_id='FILL_GAP',document_id='DOC2',document_number=2,
                observed_at=stamp(c.at+timedelta(seconds=1)) if variant.endswith('after_cutoff') else row['posted_at'],transaction_id='CONTEXT_DOC2'))
        elif variant=='duplicate_log_same_document':peer['document_id']=docs[-2]['document_id']
        elif variant=='cancelled_duplicate_document':c.tables['document_cancellations']=[c.approved(cancellation_id='VOID_DUP',series_id='PAY_2025',document_id=peer['document_id'],document_number=3)]
        elif variant=='draft_duplicate_peer':peer['state']='draft'
        elif variant=='future_duplicate_peer':peer['observed_at']=stamp(c.at+timedelta(seconds=1))
        elif variant=='duplicate_peer_other_series':peer['series_id']='OTHER_SERIES'
        elif variant=='cancellation_other_series':c.tables['document_cancellations'][0]['series_id']='OTHER_SERIES'
        elif variant=='revoked_cancellation':c.tables['document_cancellations'][0]['status']='revoked'
        elif variant=='inverted_series_range':series.update(start_number=4,closed_through_number=3)
        elif variant=='oversize_series_range':series.update(start_number=1,closed_through_number=100002)
    elif code=='F4':
        invoice=c.tables['receivable_invoices'][0];allocations=c.tables.get('receipt_allocations',[])
        allocation=allocations[0] if allocations else None
        receipt=next((r for r in c.rows if r['txn_type']=='customer_receipt'),None)
        if variant in {'overdue_exactly_60_days','overdue_61_days','invoice_due_today'}:invoice['due_at']=stamp(c.at-timedelta(days={'overdue_exactly_60_days':60,'overdue_61_days':61,'invoice_due_today':0}[variant]))
        elif variant=='zero_invoice_amount':invoice['gross_vnd']=0
        elif variant=='cancelled_invoice':invoice['status']='cancelled'
        elif variant=='invoice_due_before_issue':invoice['due_at']='2025-04-30T11:00:00+07:00'
        elif variant=='receipt_wrong_customer':receipt['customer_id']=c.tables['customers'][1]['customer_id']
        elif variant=='allocation_other_invoice':allocation['invoice_id']='OTHER_INVOICE'
        elif variant=='unverified_allocation':allocation['status']='pending'
        elif variant=='receipt_nonfinancial':receipt['is_financial_entry']=0
        elif variant=='receipt_journal_only':receipt['payment_channel']='journal'
        elif variant=='verification_before_receipt':allocation['verified_at']=stamp(parse(receipt['posted_at'])-timedelta(seconds=1))
        elif variant=='unknown_verifier':allocation['verifier_id']='UNKNOWN_VERIFIER'
        elif variant=='coverage_starts_too_late':c.tables['receipt_coverage'][0]['covered_from']=stamp(parse(invoice['issued_at'])+timedelta(seconds=1))
        elif variant=='coverage_known_after_cutoff':c.tables['receipt_coverage'][0]['observed_at']=stamp(c.at+timedelta(seconds=1))
        elif variant=='expired_explanation':c.tables['receivable_explanations'][0]['expires_at']=stamp(c.at-timedelta(seconds=1))
        elif variant=='revoked_explanation':c.tables['receivable_explanations'][0]['status']='revoked'
        elif variant=='explanation_expires_at_cutoff':c.tables['receivable_explanations'][0]['expires_at']=row['posted_at']
        elif variant=='allocation_id_binding_conflict':allocations.append(dict(allocation,invoice_id='OTHER_INVOICE'))
    tables=copy.deepcopy(c.tables)
    future=[copy.deepcopy(r) for r in c.rows if parse(r['posted_at'])>c.at]
    tables['transactions']=[copy.deepcopy(r) for r in c.rows if parse(r['posted_at'])<=c.at]
    tables.pop('labels',None);tables.pop('splits',None)
    staff={e['employee_id'] for e in tables['employees']}
    tables['attendance']=[r for r in tables.get('attendance',[]) if r['employee_id'] in staff]
    enrich_accounting(tables,seed)
    # The accounting template normally turns customer receipts into bank rows.
    # Keep this intentionally contradictory source declaration for the F4 guard.
    if variant=='receipt_journal_only':
        receipt=next(r for r in tables['transactions'] if r['txn_type']=='customer_receipt')
        receipt.update(payment_channel='journal',recipient_account='')
    return tables,row['transaction_id'],scope,DEFAULT_CONFIG|c.config,future


def namespace(tables,prefix):
    identifiers={str(value) for rows in tables.values() for row in rows for key,value in row.items()
                 if isinstance(value,str) and value and (key.endswith('_id') or key in {'bank_account','recipient_account','old_account','new_account','phone','address'})}
    mapping={value:prefix+value for value in identifiers}
    return {name:[{key:mapping.get(value,value) if isinstance(value,str) else value for key,value in row.items()} for row in rows]
            for name,rows in tables.items()},mapping


def expected_route(spec):
    code,expected=spec['rule_id'],spec['expected']
    if expected=='rejected':return dict(queued=False,priority=None,sla_hours=None)
    if spec['scope']=='transaction':
        active=expected is True and code!='F3'
        return dict(queued=active,priority=('cao_nhat' if code=='E2' else 'trung_binh') if active else None,sla_hours=(24 if code=='E2' else 168) if active else None)
    active=expected is True or spec['finding_status']=='information_gap'
    return dict(queued=active,priority=('thap' if expected is None else 'trung_binh') if active else None,sla_hours=(336 if expected is None else 168) if active else None)


def assess(result,tables,spec,target,scope,company):
    row=next(r for r in tables['transactions'] if r['transaction_id']==target)
    actual=decision(result,spec['rule_id'],row,scope)
    queue,_=review_queue(result,tables)
    bound=[q for q in queue if q['company_id']==company and spec['rule_id'] in q['rule_ids'].split('|') and
           (target in json.loads(q['transaction_ids']) if scope=='transaction' else q.get('source_scope')==scope)]
    route=expected_route(spec)
    checks=dict(condition=actual is spec['expected'],queue=bool(bound)==route['queued'])
    if bound:
        checks['priority']=all(q['priority']==route['priority'] for q in bound)
        checks['sla']=all((parse(q['sla_due_at'])-parse(q['opened_at'])).total_seconds()==route['sla_hours']*3600 for q in bound) if route['sla_hours'] else False
    return dict(actual=actual,expected=spec['expected'],route_expected=route,queue=bound,checks=checks,passed=all(checks.values()))


def write_json(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def run(data_root,output,seeds=SEEDS):
    data_root,output=Path(data_root).resolve(),Path(output).resolve()
    if data_root.exists() or output.exists():raise FileExistsError('Use fresh synthetic data and output roots')
    if data_root==output or data_root.is_relative_to(output) or output.is_relative_to(data_root):raise ValueError('Data and report roots must be separate')
    if not seeds or len(set(seeds))!=len(seeds) or any(type(seed) is not int or seed<0 for seed in seeds):raise ValueError('Use nonempty distinct integer seeds')
    specs=catalog();data_root.mkdir(parents=True);output.mkdir(parents=True)
    plan=dict(version=VERSION,is_synthetic=True,seeds=list(seeds),scope='software/source-condition controls only',
        controls=specs,real_source_acceptance='awaiting_real_data',human_reviews=0,model_fit=False,model_score=False,
        expectation_policy='Declared before source generation/scoring; mismatches are retained, never relabelled.',
        isolation='One synthetic company per control/seed; not independent real companies.',
        evaluation_cutoff='2025-09-12T11:00:00+07:00',configuration=DEFAULT_CONFIG|dict(noise_policy='phase2',spec_policy='phase3',evidence_policy='phase4'),
        code_sha256={name:sha(Path(__file__).with_name(name)) for name in ('rule_branch_controls.py','evidence_policy.py','rules.py','case_queue.py','features.py')})
    write_json(output/'evaluation_plan.json',plan)
    groups={};registry=[];rejected=[];deferred=[]
    # Complete and commit sources + expectations for all groups before scoring.
    for code in RULES:
        merged=defaultdict(list);controls=[]
        for seed in seeds:
            for number,spec in enumerate([s for s in specs if s['rule_id']==code],1):
                tables,target,scope,config,future=build_control(spec,seed)
                identity=f'{code}_{seed}_{number:03}'
                tables,mapping=namespace(dict(tables,__future_transactions=future),'SIM_'+identity+'_')
                future=tables.pop('__future_transactions')
                deferred.extend(dict(control_id=identity,reason='posted_after_evaluation_cutoff',transaction=r) for r in future)
                target=mapping[target];scope=scope if scope=='transaction' else scope.split(':')[0]+':'+mapping[scope.split(':',1)[1]]
                control=dict(spec,control_id=identity,seed=seed,target_transaction_id=target,source_scope=scope,company_id=mapping['C001'])
                registry.append(control)
                if spec['expected']=='rejected':rejected.append(dict(control=control,tables=tables,config=config));continue
                for name,rows in tables.items():merged[name].extend(rows)
                controls.append(control)
        folder=data_root/code/'sme_fraud_003';folder.mkdir(parents=True)
        for name in (*INPUT_TABLES,*OPTIONAL_INPUT_TABLES):write_csv(folder/f'{name}.csv',merged.get(name,[]),columns(name,merged.get(name,[])))
        features=build_features(merged);write_csv(folder/'features.csv',features,['transaction_id',*FEATURE_DESCRIPTIONS])
        files={path.name:dict(sha256=sha(path),rows=len(features) if path.stem=='features' else len(merged.get(path.stem,[]))) for path in folder.glob('*.csv')}
        write_json(folder/'manifest.json',dict(version=VERSION,is_synthetic=True,data_origin='synthetic_branch_controls',seed_roles='all diagnostic reporting, no holdout',
            target_rule=code,files=files,feature_columns=list(FEATURE_DESCRIPTIONS),feature_contract=cache_contract(files),financial_fraud_labels_available=False))
        groups[code]=(folder,controls,config)
    write_json(data_root/'rejected_inputs.json',rejected)
    write_json(data_root/'deferred_transactions.json',deferred)
    write_json(output/'expectations.json',registry)
    commitment={str(path.relative_to(data_root)):sha(path) for path in data_root.rglob('*') if path.is_file()}
    write_json(output/'source_commitment.json',dict(source_files=commitment,expectations_sha256=sha(output/'expectations.json'),plan_sha256=sha(output/'evaluation_plan.json')))
    comparisons=[]
    for code,(folder,controls,config) in groups.items():
        tables,features,_=load_inputs(folder);result=score_rules(tables,features=features,config=config)
        directory=output/code/'sme_fraud_003';directory.mkdir(parents=True)
        from .run_rule_repairs import write_jsonl
        queue,events=review_queue(result,tables)
        write_csv(directory/'case_queue.csv',queue);write_csv(directory/'case_events.csv',events)
        write_jsonl(directory/'rule_hits.jsonl',result['hits']);write_jsonl(directory/'evidence_findings.jsonl',result['evidence_findings'])
        write_jsonl(directory/'batch_events.jsonl',result.get('batch_events',[]));write_json(directory/'rule_coverage.json',result['coverage'])
        write_csv(directory/'rule_scores.csv',result['scores'])
        write_json(directory/'rule_config.json',config)
        for spec in controls:
            comparison=assess(result,tables,spec,spec['target_transaction_id'],spec['source_scope'],spec['company_id'])
            comparisons.append(dict(control_id=spec['control_id'],rule_id=code,variant=spec['variant'],seed=spec['seed'],**comparison))
    for item in rejected:
        spec=item['control']
        try:score_rules(item['tables'],features=build_features(item['tables']),config=item['config'])
        except ValueError as failure:comparison=dict(passed=True,expected='rejected',actual='rejected',error=str(failure))
        else:comparison=dict(passed=False,expected='rejected',actual='accepted')
        comparisons.append(dict(control_id=spec['control_id'],rule_id=spec['rule_id'],variant=spec['variant'],seed=spec['seed'],**comparison))
    write_json(output/'comparisons.json',comparisons)
    assert all(sha(data_root/name)==expected for name,expected in commitment.items()),'Sources changed during scoring'
    summary=dict(version=VERSION,is_synthetic=True,seeds=list(seeds),variant_count=len(specs),controls=len(registry),
        transactions=sum(len(load_inputs(folder)[0]['transactions']) for folder,_,_ in groups.values()),
        matched=sum(c['passed'] for c in comparisons),mismatches=[c for c in comparisons if not c['passed']],
        by_rule={code:dict(variants=sum(s['rule_id']==code for s in specs),controls=sum(c['rule_id']==code for c in comparisons),matched=sum(c['passed'] for c in comparisons if c['rule_id']==code)) for code in RULES},
        rejected_source_controls=len(rejected),models_fitted_or_scored=0,independent_human_reviews=0,real_source_acceptance='awaiting_real_data')
    write_json(output/'summary.json',summary)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    options=parser.parse_args();result=run(options.data_root,options.output)
    print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(bool(result['mismatches']))
