"""Enterprise-local four-rule baseline vs freshly encrypted model inference.

Not an all-HE baseline: E3/B5/E4 have no encrypted evaluator. No reviewed
labels or operational queue changes enter this offline technical comparison.
"""
from copy import deepcopy
from .import_files import canonical,digest
from .selection_comparison import identity,score,select_records,BUDGET,POLICY
from .snapshot_features import utc

RULES=('P1','E3','B5','E4')
MASTER=('E3','B5','E4')


def compare(local,ml,as_of,*,simulated_only=None):
    # Pin exact JSON inputs. NaN/Infinity cannot enter a frozen experiment.
    local_hash=digest(canonical(local));ml_hash=digest(canonical(ml))
    receipt=ml['receipt'];snapshot=local['snapshot']
    if snapshot!=receipt['snapshot'] or utc(as_of)!=utc(receipt['as_of']) or local['feature_contract_fingerprint']!=receipt['feature_contract_fingerprint']:
        raise ValueError('Snapshot/as_of/feature binding mismatch')
    if receipt['company_id']!=snapshot['company_id'] or receipt['tenant_id']!=snapshot['tenant_id']:
        raise ValueError('Model company binding mismatch')
    if not all(receipt.get(k) for k in ('artifact_id','model_version','reference_version','fit_job_id')):raise ValueError('Model pin missing')
    left={identity(r):r for r in local['rows']};right={identity(r):r for r in ml['rows']}
    if (len(left)!=local['row_count'] or len(left)!=len(local['rows']) or
        len(right)!=ml['row_count'] or len(right)!=len(ml['rows']) or set(left)!=set(right)):
        raise ValueError('Comparison row binding mismatch')
    records=[];groups={};coverage={code:dict(evaluated_hit=0,evaluated_no_hit=0,unavailable=0,not_applicable=0) for code in RULES}
    for key,row in left.items():
        if (row['tenant_id'],row['company_id'])!=(snapshot['tenant_id'],snapshot['company_id']):raise ValueError('Foreign row')
        if utc(row['as_of'])>utc(as_of) or utc(row['event_at'])>utc(as_of):raise ValueError('Row after comparison ceiling')
        results=row['methods']['rules']['details']['rule_results']['rules'];by_code={r['rule_id']:r for r in results}
        if len(by_code)!=35 or not set(RULES)<=set(by_code):raise ValueError('Incomplete rule results')
        for code in RULES:
            r=by_code[code];coverage[code][r['status']]+=1
            if code in MASTER and r['available'] and r['score']!=0:raise ValueError('Master-quality contribution changed')
            if not r['available'] and (r['matched'] is not None or r['score'] is not None):raise ValueError('Unavailable is not zero')
        p1=by_code['P1'];group_hits=[g for g in p1['details'].get('simultaneous_checks',[]) if g.get('matched') is True] if p1['available'] else []
        hit=p1['available'] and (p1['matched'] or group_hits)
        state='alert' if hit else 'no_operational_rule_hit' if p1['available'] else 'not_applicable' if p1['status']=='not_applicable' else 'unavailable'
        value=score(right[key]);records.append(dict(record_id=key[0],revision=key[1],event_at=row['event_at'],rule_state=state,ml_available=value is not None,ml_score=value,ml_reason=right[key].get('reason'),
            rule_states={code:by_code[code]['status'] for code in RULES},master_hits=[code for code in MASTER if by_code[code]['available'] and by_code[code]['matched']]))
        for group in group_hits:
            members={identity(ref) for ref in group['transaction_refs']}
            if key not in members or not members<=set(left):raise ValueError('Group outside comparison cohort')
            groups.setdefault(group['group_id'],set()).update(members)
    baseline,deferred,added,components=select_records(records,groups)
    common={identity(r) for r in records if r['ml_available'] and r['rule_state'] in ('alert','no_operational_rule_hit')}
    result=dict(version='expanded-rule-selection/1.0.0',status='technical_only',policy=POLICY,budget=BUDGET,snapshot=deepcopy(snapshot),as_of=utc(as_of).isoformat(),
        source_execution='enterprise_local_rules_plus_ciphertext_worker_ml',all_rule_evaluations_he=False,
        baseline_rule_ids=list(RULES),transaction_priority_rule_ids=['P1'],master_quality_rule_ids=list(MASTER),not_yet_adapted_rule_count=31,
        model_pin={k:deepcopy(receipt[k]) for k in ('artifact_id','model_version','reference_version','fit_job_id','selected_columns','preprocess_sha256','reference_end','feature_contract_fingerprint')},
        local_result_sha256=local_hash,ml_result_sha256=ml_hash,
        baseline=[list(k) for k in baseline],combined=[list(k) for k in baseline+added],added=[list(k) for k in added],removed=[],deferred_rule_alerts=[list(k) for k in deferred],rule_groups=[[list(k) for k in c] for c in components],
        records=records,coverage=coverage,ml_available=sum(r['ml_available'] for r in records),ml_unavailable=sum(not r['ml_available'] for r in records),
        common_coverage=dict(cohort_size=len(common),selection_recomputed=False,baseline_selected=sum(k in common for k in baseline),combined_selected=sum(k in common for k in baseline+added)),
        simulated_only=simulated_only,prospective=False,selection_uses_feedback=False,model_fit_performed=False,operational_queue_changed=False,
        metrics=dict(accuracy=None,precision=None,recall=None,incremental_usefulness=None,review_seconds=None),
        limitations=['Four-rule local baseline; not 35 rules or fully homomorphic rules.','Master findings are retained separately, never promoted to transaction alerts.','Synthetic, retrospective, unreviewed data cannot establish fraud detection benefit.'])
    result['report_sha256']=digest(canonical(result));return result
