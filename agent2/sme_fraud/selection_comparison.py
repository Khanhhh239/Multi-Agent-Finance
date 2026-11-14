"""Frozen, retrospective selection experiment. Never changes operational routing.

The default trial preserves P1 alert groups and uses ML only for unused slots.
Feedback is read after selection and never influences the frozen lists.
"""
from copy import deepcopy
from datetime import datetime,timezone
import math

from .import_files import canonical,digest,fail
from .snapshot_features import utc

VERSION='selection-comparison/1.0.0'
POLICY='rules_first_fill/1.0.0'
BUDGET=5


def identity(value):return value['record_id'],value['revision']


def score(branch):
    value=branch.get('raw_score')
    return float(value) if branch.get('available') is True and type(value) in (int,float) and math.isfinite(value) and value>=0 else None


def select_records(records,groups,budget=BUDGET):
    """Shared budget policy only; caller binds source/model before selection."""
    by_key={identity(r):r for r in records}
    order=lambda key:(utc(by_key[key]['event_at']),key[0],key[1])
    components=[{identity(r)} for r in records if r['rule_state']=='alert']
    for members in groups.values():
        merged=set(members);remaining=[]
        for comp in components:
            if comp & members:merged.update(comp)
            else:remaining.append(comp)
        components=remaining+[merged]
    components.sort(key=lambda comp:min(order(k) for k in comp));baseline=[];deferred=[]
    for comp in components:
        target=baseline if len(baseline)+len(comp)<=budget else deferred
        target.extend(sorted(comp,key=order))
    candidates=sorted((r for r in records if r['rule_state']!='alert' and r['ml_available']),key=lambda r:(-r['ml_score'],utc(r['event_at']),r['record_id'],r['revision']))
    additions=[identity(r) for r in candidates[:budget-len(baseline)]]
    return baseline,deferred,additions,[sorted(comp,key=order) for comp in components]


def make_plan(result,cases,snapshot_manifest,model_pin):
    if result.get('version')!='he-four-branch-result/1.0.0':
        fail(409,'COMPARISON_FOUR_BRANCH_REQUIRED','Lượt này chưa có kết quả luật và ML để so sánh.','Chọn một lượt bốn nhánh đã hoàn tất.')
    rows={identity(r):r for r in result['rows']};lookup={identity(c):c for c in cases}
    if len(rows)!=len(result['rows']) or set(rows)!=set(lookup) or len(cases)!=result['row_count']:
        fail(503,'COMPARISON_ROW_BINDING','Kết quả và phiếu chưa khớp đủ giao dịch.','Kiểm tra nguồn và lần chạy trước khi so sánh.')
    records=[];groups={}
    for key,c in lookup.items():
        row=rows[key];branches=row.get('branches',{});rule=branches.get('rules',{});ml=branches.get('ml',{})
        group_hits=[g for g in rule.get('simultaneous_checks',[]) if g.get('matched') is True] if rule.get('available') is True else []
        hit=rule.get('available') is True and (rule.get('matched') is True or any(i.get('matched') is True for i in rule.get('invoice_checks',[])) or bool(group_hits))
        rule_state='alert' if hit else 'no_p1_hit' if rule.get('available') is True else 'not_applicable' if rule.get('status')=='not_applicable' else 'unavailable'
        record=dict(record_id=key[0],revision=key[1],case_id=c['case_id'],event_at=c['event_at'],rule_state=rule_state,ml_available=score(ml) is not None,ml_score=score(ml),ml_reason=ml.get('reason'))
        records.append(record)
        for group in group_hits:
            group_key=digest(canonical([utc(c['event_at']).isoformat(),group['obligation']]))
            groups.setdefault(group_key,set()).add(key)
    # Keep every known simultaneous P1 alert component together. One member
    # consumes one transaction slot; the group is never counted as two cases.
    baseline,deferred,additions,components=select_records(records,groups)
    start=min((utc(c['event_at']) for c in cases),default=None);end=max((utc(c['event_at']) for c in cases),default=None)
    simulated=any(e['simulated'] for c in cases for e in c['evidence'])
    return dict(version=VERSION,policy=POLICY,budget=BUDGET,run_id=result['run_id'],company_id=result['company_id'],snapshot_id=result['snapshot_id'],as_of=result['as_of'],
        snapshot_checksum=snapshot_manifest['checksum'],result_sha256=digest(canonical(result)),model_pin=deepcopy(model_pin),
        period_start=start.isoformat() if start else None,period_end=end.isoformat() if end else None,created_at=datetime.now(timezone.utc).isoformat(),
        prospective=False,design='retrospective_known_run',simulated_data=simulated,unit='transaction',reviews_present_before_lock=sum(c['review']['feedback'] is not None for c in cases),
        baseline=[list(k) for k in baseline],combined=[list(k) for k in baseline+additions],added=[list(k) for k in additions],removed=[],
        deferred_rule_alerts=[list(k) for k in deferred],rule_groups=[[list(k) for k in comp] for comp in components],records=records,
        ordering='P1 alert groups by event UTC then record ID/revision; ML descending raw score then event UTC and ID/revision; no weights or new threshold',
        selection_uses_feedback=False,mandatory_routing_approved=False,operational_queue_changed=False)


def arm_metrics(keys,cases):
    items=[cases[tuple(k)] for k in keys];reviews=[c['review'] for c in items];feedback=[r['feedback'] for r in reviews if r['feedback'] is not None]
    resolved=[f for f in feedback if f['outcome'] in ('confirmed_risk','legitimate')]
    problems=sum(f['outcome']=='confirmed_risk' for f in resolved);useful=[f for f in feedback if f['usefulness'] in ('yes','no')]
    useful_yes=sum(f['usefulness']=='yes' for f in useful)
    return dict(selected=len(items),budget=BUDGET,unused_slots=BUDGET-len(items),reviewed=len(feedback),pending=len(items)-len(feedback),
        resolved=len(resolved),inconclusive=sum(f['outcome']=='inconclusive' for f in feedback),declared_problem_transactions=problems if resolved else None,
        declared_precision_resolved=problems/len(resolved) if resolved else None,resolution_coverage=len(resolved)/len(items) if items else None,
        declared_precision_at_selected=problems/len(items) if items and len(resolved)==len(items) else None,
        usefulness_assessed=len(useful),declared_useful_transactions=useful_yes if useful else None,declared_useful_fraction=useful_yes/len(useful) if useful else None,
        saved_connected_seconds=round(sum(r['active_seconds'] for r in reviews if r['feedback'] is not None),3) if feedback else None,
        effort_complete=len(feedback)==len(items) and bool(items),accuracy=None,recall=None,pr_auc=None,confirmed_fraud_cases=None)


def report_for(plan,cases):
    lookup={identity(c):c for c in cases};records={identity(r):r for r in plan['records']}
    if set(lookup)!=set(records):fail(503,'COMPARISON_CASE_BINDING','Nguồn phiếu không còn khớp kế hoạch.','Mở đúng bản dữ liệu và lần chạy đã khóa.')
    def entries(keys):
        output=[]
        for key in keys:
            r=records[tuple(key)];c=lookup[tuple(key)];review=c['review'];f=review['feedback'] or {}
            output.append(dict(record_id=r['record_id'],revision=r['revision'],case_id=c['case_id'],amount_vnd=c['amount_vnd'],event_at=r['event_at'],rule_state=r['rule_state'],
                reason='rule_alert' if r['rule_state']=='alert' else 'ml_addition',review_revision=review['revision'],outcome=f.get('outcome'),usefulness=f.get('usefulness'),active_seconds=review['active_seconds'] if review['feedback'] is not None else None))
        return output
    baseline=arm_metrics(plan['baseline'],lookup);combined=arm_metrics(plan['combined'],lookup);added=arm_metrics(plan['added'],lookup);removed=arm_metrics(plan['removed'],lookup)
    delta_known=added['resolved']==added['selected'] and removed['resolved']==removed['selected']
    usefulness_known=added['usefulness_assessed']==added['selected'] and removed['usefulness_assessed']==removed['selected']
    pins=dict(version=plan['version'],policy=plan['policy'],budget=plan['budget'],run_id=plan['run_id'],company_id=plan['company_id'],snapshot_id=plan['snapshot_id'],snapshot_checksum=plan['snapshot_checksum'],result_sha256=plan['result_sha256'],model_context_pinned_by_run=True,as_of=plan['as_of'],
        period_start=plan['period_start'],period_end=plan['period_end'],created_at=plan['created_at'],simulated_data=plan['simulated_data'],design=plan['design'],reviews_present_before_lock=plan['reviews_present_before_lock'],prospective=False,unit='transaction',operational_queue_changed=False)
    value=dict(version=VERSION,status='technical_only',label_status='insufficient_verified_labels',plan=pins,baseline=dict(metrics=baseline,transactions=entries(plan['baseline'])),combined=dict(metrics=combined,transactions=entries(plan['combined'])),
        added=entries(plan['added']),removed=entries(plan['removed']),deferred_rule_alerts=entries(plan['deferred_rule_alerts']),
        delta=dict(declared_problem_transactions=(added['declared_problem_transactions'] or 0)-(removed['declared_problem_transactions'] or 0) if delta_known else None,
            declared_useful_transactions=(added['declared_useful_transactions'] or 0)-(removed['declared_useful_transactions'] or 0) if usefulness_known else None,
            attributed_connected_seconds=round(combined['saved_connected_seconds']-baseline['saved_connected_seconds'],3) if baseline['effort_complete'] and combined['effort_complete'] else None),
        coverage=dict(total_transactions=len(records),p1_available=sum(r['rule_state'] in ('alert','no_p1_hit') for r in records.values()),p1_unavailable=sum(r['rule_state']=='unavailable' for r in records.values()),
            p1_not_applicable=sum(r['rule_state']=='not_applicable' for r in records.values()),ml_available=sum(r['ml_available'] for r in records.values()),ml_unavailable=sum(not r['ml_available'] for r in records.values()),
            both_available=sum(r['ml_available'] and r['rule_state'] in ('alert','no_p1_hit') for r in records.values())),
        overlap=dict(shared=len(set(map(tuple,plan['baseline']))&set(map(tuple,plan['combined']))),added=len(plan['added']),removed=len(plan['removed']),known_p1_alert_groups=len(plan['rule_groups'])),
        feedback_revisions=[dict(case_id=c['case_id'],revision=c['review']['revision']) for c in cases],generated_at=datetime.now(timezone.utc).isoformat(),new_scoring_performed=False,model_fit_performed=False,
        limitations=['Synthetic/known-run trial does not establish fraud accuracy or generalization.','P1 is not the full rules catalog; missing/not-applicable is not no-hit.',
            'Budget is a cap of five transaction slots. Rules baseline may leave slots unused; no random padding.',
            'Known simultaneous alert groups stay together; transaction results are not counts of independent fraud cases.',
            'Usefulness and resolution are declared separately; no verified ground truth or training labels are created.',
            'Shared transactions reuse the same saved review. Connected time is attributed, not a blinded randomized timing experiment.'])
    common={k for k,r in records.items() if r['ml_available'] and r['rule_state'] in ('alert','no_p1_hit')}
    value['common_coverage']=dict(cohort_size=len(common),selection_recomputed=False,baseline=arm_metrics([k for k in plan['baseline'] if tuple(k) in common],lookup),combined=arm_metrics([k for k in plan['combined'] if tuple(k) in common],lookup))
    value['report_sha256']=digest(canonical(value));return value
