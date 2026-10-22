"""Shadow admission of IF-only document leads alongside a frozen baseline.

Existing evaluation scores only; study ledgers never update production queues.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import argparse
from datetime import date
import json
import math
from pathlib import Path

from .audit_if_coverage import unique_index, verify_commitment
from .compare_shadow import (baseline_key, build_snapshots, pending, read_csv, read_json,
                            write_csv, write_json)
from .feature_contract import digest, sha
from .generate import TZ
from .review_capacity import ReviewCapacity
from .shadow_scoring import guarded, instant, output_guard

VERSION='if-discovery-shadow-v1'


def document_key(row):
    for field in ('invoice_id','journal_document_id','transaction_id'):
        if row.get(field):
            return row['company_id'],field+':'+row[field]
    raise ValueError('A discovery lead requires a document or transaction identity')


def ids(value):
    return json.loads(value) if isinstance(value,str) and value else value or []


def case_document_keys(case,transactions):
    members=set()
    for field in ('transaction_ids','pattern_context_ids','pattern_evidence_ids'):
        for tid in ids(case.get(field)):
            if tid in transactions:
                if transactions[tid]['company_id']!=case['company_id']:
                    raise ValueError('Baseline scope crosses companies')
                members.add(tid)
            elif field=='transaction_ids':
                raise ValueError('Unknown baseline member')
    docs={document_key(transactions[t]) for t in members}
    if case.get('source_scope','').startswith('invoice:'):
        docs.add((case['company_id'],'invoice_id:'+case['source_scope'].split(':',1)[1]))
    return members,docs


def lead_case(row,score,rule,cohort,context_hits):
    doc=document_key(row)
    scope=digest([VERSION,cohort,doc,row['transaction_id']])
    key=digest([VERSION,cohort,doc])
    points=int(rule['rule_score'])
    signal=points>0 or int(rule.get('hard_trigger',0)) or int(rule.get('operational_alert',0))
    return dict(case_id='IFD_'+key[:20],company_id=row['company_id'],case_type='if_discovery',
        transaction_ids=json.dumps([row['transaction_id']]),source_scope='',rule_ids='',
        priority='thap',max_score=points,opened_at=row['posted_at'],last_seen_at=row['posted_at'],
        if_score=float(score['anomaly_score']),if_coverage='full',member_count=1,scored_member_count=1,
        production_scope_hash=scope,work_scope=scope,base_work_key=key,
        document_key=doc[1],lead_transaction_id=row['transaction_id'],txn_type=row['txn_type'],
        baseline_rule_score=points,baseline_signal_class='weak_transaction_signal_not_admitted' if signal else 'zero_transaction_points',
        context_only_hits=context_hits,source_status='study_only_if_admission',requires_rereview=0,rereview_due_at='')


def prepare_frames(snapshots,transactions,scores,rules,threshold,cohort,findings=(),hits=()):
    if not math.isfinite(threshold):
        raise ValueError('Discovery needs the unchanged finite calibration threshold')
    above={t:r for t,r in scores.items() if float(r['anomaly_score'])>=threshold}
    for tid,r in scores.items():
        tx=transactions.get(tid)
        if (tx is None or not math.isfinite(float(r['anomaly_score'])) or tx['company_id']!=r['company_id']
                or instant(tx['posted_at'])!=instant(r['posted_at'])):
            raise ValueError('IF score/source binding differs')
    source_history=sorted((r for r in findings if r.get('scope','').startswith('invoice:')
        and (r.get('signal') is True or r.get('status')=='information_gap')),key=lambda r:instant(r['cutoff_at']))
    contexts=defaultdict(list)
    for hit in hits:
        if hit.get('transaction_id') in above:
            contexts[hit['transaction_id']].append(hit)
    covered_docs,covered_txs,first_baseline,first_eligible=set(),set(),{},{}
    audit={t:dict(transaction_id=t,company_id=transactions[t]['company_id'],document_key=document_key(transactions[t])[1],
        txn_type=transactions[t]['txn_type'],posted_at=transactions[t]['posted_at'],if_score=float(r['anomaly_score']),
        first_visible_cutoff='',first_eligible_cutoff='',first_baseline_document_cutoff='') for t,r in above.items()}
    frames=[];source_index=0
    for snap in snapshots:
        cutoff=instant(snap['cutoff'])
        while source_index<len(source_history) and instant(source_history[source_index]['cutoff_at'])<cutoff:
            finding=source_history[source_index]
            doc=(finding['company_id'],'invoice_id:'+finding['scope'].split(':',1)[1])
            covered_docs.add(doc);first_baseline.setdefault(doc,snap['cutoff'])
            source_index+=1
        for case in snap['cases']:
            members,docs=case_document_keys(case,transactions)
            if any(instant(transactions[t]['posted_at'])>=cutoff for t in members):
                raise ValueError('Future baseline/context member at the daily cutoff')
            covered_txs.update(members);covered_docs.update(docs)
            for doc in docs:first_baseline.setdefault(doc,snap['cutoff'])
        available={}
        for tid,score in above.items():
            row=transactions[tid]
            if instant(row['posted_at'])>=cutoff:
                continue
            audit[tid]['first_visible_cutoff']=audit[tid]['first_visible_cutoff'] or snap['cutoff']
            doc=document_key(row)
            if tid in covered_txs or doc in covered_docs:
                continue
            audit[tid]['first_eligible_cutoff']=audit[tid]['first_eligible_cutoff'] or snap['cutoff']
            first_eligible.setdefault(doc,snap['day'])
            context_count=sum(instant(h['detected_at'])<cutoff and int(h.get('points',0))==0 for h in contexts[tid])
            case=lead_case(row,score,rules[tid],cohort,context_count)
            case['first_eligible_day']=first_eligible[doc].isoformat()
            current=available.get(doc)
            if current is None or (-case['if_score'],instant(case['opened_at']),tid)<(-current['if_score'],instant(current['opened_at']),current['lead_transaction_id']):
                available[doc]=case
        frames.append(dict(snap,leads=list(available.values()),covered_document_count=len(covered_docs)))
    for tid,row in audit.items():
        row['first_baseline_document_cutoff']=first_baseline.get(document_key(transactions[tid]),'')
    return frames,list(audit.values()),first_baseline


def select_mixed(tasks,capacity,pins,leads,quota,if_minutes):
    chosen=[];used=0;case_ids=set();keys=set()
    def add(task,origin):
        nonlocal used
        if task['case']['case_id'] in case_ids or task['key'] in keys:
            return False
        if not capacity.fits(len(chosen),used,task['minutes']):
            return False
        chosen.append(dict(task,origin=origin));used+=task['minutes']
        case_ids.add(task['case']['case_id']);keys.add(task['key'])
        return True
    for task in sorted(pins,key=lambda t:baseline_key(t['case'])):
        if not add(task,'baseline'):
            raise ValueError('Mandatory baseline work does not fit')
    for task in sorted(tasks,key=lambda t:baseline_key(t['case'])):
        if task['case']['priority']=='cao_nhat' and task['key'] not in keys:
            add(task,'baseline')
    discovery=0
    for case in sorted(leads,key=lambda c:(-c['if_score'],instant(c['opened_at']),c['case_id'])):
        if discovery>=quota:
            break
        task=dict(key=case['base_work_key'],case=case,minutes=if_minutes,
            ready=date.fromisoformat(case['first_eligible_day']),work_type='if_document_review')
        discovery+=int(add(task,'if_only'))
    for task in sorted(tasks,key=lambda t:baseline_key(t['case'])):
        if task['case']['case_type']=='transaction':
            add(task,'baseline')
    if quota==0:
        chosen.sort(key=lambda t:baseline_key(t['case']))
    return chosen


def simulate(frames,frozen_rows,transactions,first_baseline,*,slots,share,if_minutes):
    if share not in (0,20,40) or if_minutes not in (20,30):
        raise ValueError('Use the precommitted discovery shares and cost scenarios')
    capacity=ReviewCapacity.ui(slots)
    quota=slots*share//100
    led=dict(done=set(),case_ids=set());reviewed_docs=set();reviewed_if_txs=set()
    first_seen={};selected=[];daily=[];totals=Counter();by_day=defaultdict(list)
    for row in frozen_rows:
        if row['arm']=='baseline':by_day[(row['day'],row['company_id'])].append(row)
    for snap in frames:
        for case in snap['cases']:first_seen.setdefault(case['base_work_key'],snap['day'])
        tasks=pending(snap['cases'],led,first_seen,snap['day'])
        for company in snap['companies']:
            available=[t for t in tasks if t['case']['company_id']==company]
            indexed={t['key']:t for t in available}
            frozen=by_day[(snap['day'].isoformat(),company)]
            pins=[];mandatory_done=0
            for row in frozen:
                if row['priority']!='cao_nhat' and row['case_type']=='transaction':continue
                if row['work_key'] in indexed:pins.append(indexed[row['work_key']])
                elif row['work_key'] in led['done']:mandatory_done+=1
                else:raise ValueError('Mandatory scope is absent and was not completed')
            leads=[c for c in snap['leads'] if c['company_id']==company and (company,c['document_key']) not in reviewed_docs]
            chosen=select_mixed(available,capacity,pins,leads,quota,if_minutes)
            basekeys={t['key'] for t in chosen if t['origin']=='baseline'}
            if not {t['key'] for t in pins}<=basekeys:raise AssertionError('Mandatory displacement')
            used=sum(t['minutes'] for t in chosen)
            if len(chosen)>capacity.slots or used>capacity.minutes:raise AssertionError('Budget violation')
            frozenkeys={r['work_key'] for r in frozen}
            if share==0:
                expected=[(r['work_key'],int(r['estimated_minutes'])) for r in sorted(frozen,key=lambda r:int(r['rank']))]
                if [(t['key'],t['minutes']) for t in chosen]!=expected:
                    raise AssertionError('Zero-share control differs from frozen baseline')
            remaining=[t for t in available if t['key'] not in basekeys]
            daily.append(dict(day=snap['day'].isoformat(),cutoff_exclusive=snap['cutoff'],company_id=company,
                capacity_slots=slots,capacity_minutes=capacity.minutes,discovery_slot_cap=quota,
                mandatory_pins=len(pins),mandatory_already_done=mandatory_done,mandatory_preserved=True,
                eligible_pending_if_documents=len(leads),selected_if=sum(t['origin']=='if_only' for t in chosen),
                selected_baseline=len(basekeys),selected_total=len(chosen),estimated_minutes=used,
                frozen_baseline_selected=len(frozen),frozen_baseline_estimated_minutes=sum(int(r['estimated_minutes']) for r in frozen),
                baseline_deferred_same_day=len(frozenkeys-basekeys),baseline_advanced_or_other=len(basekeys-frozenkeys),
                pending_baseline=len(remaining),pending_baseline_minutes=sum(t['minutes'] for t in remaining),
                pending_if_documents=len(leads)-sum(t['origin']=='if_only' for t in chosen)))
            totals.update(mandatory_pins=len(pins),mandatory_already_done=mandatory_done)
            for rank,task in enumerate(chosen,1):
                case=task['case'];origin=task['origin'];members=ids(case['transaction_ids'])
                previous_if_docs={document_key(transactions[t]) for t in members}&reviewed_docs if origin=='baseline' else set()
                record=dict(day=snap['day'].isoformat(),cutoff_exclusive=snap['cutoff'],company_id=company,
                    origin=origin,work_key=task['key'],case_id=case['case_id'],case_scope_hash=case['production_scope_hash'],
                    case_type=case['case_type'],priority=case['priority'],transaction_ids=json.dumps(members),
                    source_scope=case.get('source_scope',''),rule_ids=case.get('rule_ids',''),
                    rank=rank,work_type=task['work_type'],estimated_minutes=task['minutes'],
                    wait_days=(snap['day']-task['ready']).days,if_score=case['if_score'],
                    if_coverage=case['if_coverage'],member_count=case['member_count'],
                    earlier_if_documents_in_baseline_scope=len(previous_if_docs),
                    document_key=case.get('document_key',''),lead_transaction_id=case.get('lead_transaction_id',''),
                    txn_type=case.get('txn_type',''),baseline_rule_score=case.get('baseline_rule_score',''),
                    baseline_signal_class=case.get('baseline_signal_class',''),context_only_hits=case.get('context_only_hits',''),
                    first_baseline_document_cutoff='')
                if origin=='if_only':
                    doc=(company,case['document_key'])
                    if doc in reviewed_docs:raise AssertionError('Repeated unchanged IF document review')
                    reviewed_docs.add(doc);reviewed_if_txs.update(members)
                    record['first_baseline_document_cutoff']=first_baseline.get(doc,'')
                    if record['first_baseline_document_cutoff'] and instant(record['first_baseline_document_cutoff'])<=instant(snap['cutoff']):
                        raise AssertionError('IF lead was already inside baseline')
                else:
                    if task['key'] in led['done']:raise AssertionError('Repeated baseline work')
                    led['done'].add(task['key']);led['case_ids'].add(case['case_id'])
                selected.append(record)
    base=[r for r in selected if r['origin']=='baseline'];discoveries=[r for r in selected if r['origin']=='if_only']
    frozen=[r for r in frozen_rows if r['arm']=='baseline']
    by_key={r['work_key']:r for r in frozen};alt_key={r['work_key']:r for r in base}
    common=set(by_key)&set(alt_key)
    delays=[(date.fromisoformat(alt_key[k]['day'])-date.fromisoformat(by_key[k]['day'])).days for k in common]
    last_day=frames[-1]['day'].isoformat()
    eligible_docs={(c['company_id'],c['document_key']) for snap in frames for c in snap['leads']}
    summary=dict(daily_slots=slots,daily_minutes=capacity.minutes,share_percent=share,if_estimated_minutes=if_minutes,
        discovery_slot_cap=quota,company_days=len(daily),mandatory_pins=totals['mandatory_pins'],
        mandatory_already_done=totals['mandatory_already_done'],mandatory_displacements=0,budget_violations=0,
        frozen_baseline_reviews=len(frozen),baseline_reviews=len(base),if_document_reviews=len(discoveries),
        total_reviews=len(selected),if_unique_transactions=len(reviewed_if_txs),
        if_candidate_documents_ever_eligible=len(eligible_docs),
        if_unreviewed_absorbed_by_baseline=sum(d in first_baseline for d in eligible_docs-reviewed_docs),
        estimated_minutes=sum(r['estimated_minutes'] for r in selected),
        if_estimated_total_minutes=sum(r['estimated_minutes'] for r in discoveries),
        if_zero_transaction_point_reviews=sum(r['baseline_signal_class']=='zero_transaction_points' for r in discoveries),
        if_weak_transaction_signal_reviews=sum(r['baseline_signal_class']=='weak_transaction_signal_not_admitted' for r in discoveries),
        if_later_admitted_by_baseline=sum(bool(r['first_baseline_document_cutoff']) for r in discoveries),
        if_not_admitted_by_baseline_before_evaluation_end=sum(not r['first_baseline_document_cutoff'] for r in discoveries),
        baseline_reviews_with_earlier_if_documents=sum(r['earlier_if_documents_in_baseline_scope']>0 for r in base),
        common_baseline_work=len(common),baseline_common_work_delayed=sum(d>0 for d in delays),
        baseline_common_work_earlier=sum(d<0 for d in delays),max_common_baseline_delay_days=max([0,*delays]),
        unmatched_frozen_historical_work=len(set(by_key)-set(alt_key)),
        pending_baseline_at_end=sum(r['pending_baseline'] for r in daily if r['day']==last_day),
        pending_if_at_end=sum(r['pending_if_documents'] for r in daily if r['day']==last_day),
        zero_share_reproduces_frozen_baseline=share==0,independent_reviews=0,actionable_gain=None,actual_review_minutes=None)
    return dict(summary=summary,selections=selected,daily=daily)


def run_discovery(dataset,baseline,comparison,coverage,output,*,protocol):
    dataset,baseline,comparison,coverage,output=map(guarded,(dataset,baseline,comparison,coverage,output))
    protocol=guarded(protocol)
    output_guard(output,dataset,comparison/'unused-model')
    if any(output.is_relative_to(p) or p.is_relative_to(output) for p in (baseline,comparison,coverage)):
        raise ValueError('Discovery output must be separate from frozen inputs')
    inputs=verify_commitment(comparison)
    for name,h in read_json(coverage/'output_commitment.json').items():
        path=guarded(coverage/name)
        if not path.is_relative_to(coverage) or sha(path)!=h:raise ValueError('Coverage output changed')
        inputs[str(path)]=h
    inputs[str(coverage/'output_commitment.json')]=sha(coverage/'output_commitment.json')
    for path,h in read_json(coverage/'input_commitment.json').items():
        if sha(guarded(path))!=h:raise ValueError('Frozen discovery input changed')
        inputs[path]=h
    inputs[str(protocol)]=sha(protocol)
    for path in (Path(__file__).resolve(),Path(__file__).resolve().with_name('compare_shadow.py')):inputs[str(path)]=sha(path)
    prior=read_json(coverage/'summary.json');metadata=read_json(dataset/'manifest.json')
    settings=read_json(protocol);plan=read_json(comparison/'evaluation_plan.json');run=read_json(comparison/'if_scores/run.json')
    tag=dataset.name.removeprefix('sme_fraud_')
    if (tag not in {'001','003'} or metadata.get('role')!='reporting' or metadata.get('is_synthetic') is not True
            or prior['status']!='coverage_explained' or guarded(prior['dataset'])!=dataset
            or guarded(prior['comparison'])!=comparison or settings['version']!=VERSION
            or settings['discovery_shares_percent']!=[0,20,40] or settings['if_review_costs_minutes']!=[20,30]
            or run['manifest_sha256']!=sha(dataset/'manifest.json')):
        raise ValueError('Discovery requires the precommitted synthetic reporting protocol and unchanged coverage audit')
    training=read_json(guarded(run['model_path']).parent/'training_run.json')
    threshold=float(training['calibration']['threshold'])
    output.mkdir(parents=True)
    write_json(output/'analysis_plan.json',dict(protocol=settings,input_sha256=inputs,
        calibration_threshold=threshold,model_sha256=run['model_sha256'],cohort=tag,
        model_fit=False,model_scored=False,queue_write=False))
    transactions=unique_index(read_csv(dataset/'transactions.csv'),'transaction_id')
    scores=unique_index(read_csv(comparison/'if_scores/shadow_scores.csv'),'transaction_id')
    if len(scores)!=run['rows_scored'] or any(r['run_id']!=run['run_id'] for r in scores.values()):raise ValueError('Score run/count changed')
    rules=unique_index(read_csv(baseline/'rule_scores.csv'),'transaction_id')
    snapshots,base_inputs,reconstruction=build_snapshots(dataset,baseline,plan['scope'],{t:float(r['anomaly_score']) for t,r in scores.items()})
    if base_inputs!=plan['baseline_input_sha256'] or reconstruction!=plan['baseline_reconstruction']:raise ValueError('Baseline reconstruction changed')
    def json_lines(path):
        with path.open(encoding='utf-8') as stream:return [json.loads(line) for line in stream if line.strip()]
    frames,audit,first_baseline=prepare_frames(snapshots,transactions,scores,rules,threshold,tag,
        json_lines(baseline/'evidence_findings.jsonl'),json_lines(baseline/'rule_hits.jsonl'))
    write_csv(output/'above_threshold_candidates.private.csv',audit,list(audit[0]) if audit else ['transaction_id'])
    results=[]
    for slots in (5,10):
        frozen=read_csv(comparison/f'budget_{slots}/selections.private.csv')
        for share in (0,20,40):
            for cost in ((20,) if share==0 else (20,30)):
                name=f'budget_{slots}_share_{share}_cost_{cost}'
                result=simulate(frames,frozen,transactions,first_baseline,slots=slots,share=share,if_minutes=cost)
                target=output/name;target.mkdir()
                write_json(target/'summary.json',result['summary'])
                for file,rows in (('selections.private.csv',result['selections']),('daily.csv',result['daily'])):
                    write_csv(target/file,rows,list(rows[0]))
                results.append(dict(scenario=name,**result['summary']))
                print(tag+' '+name+': '+str(result['summary']['if_document_reviews'])+' IF-only document reviews',flush=True)
    if any(sha(p)!=h for p,h in inputs.items()):raise ValueError('Frozen inputs changed during discovery shadow')
    summary=dict(version=VERSION,cohort=tag,mode='synthetic_technical_discovery_shadow',calibration_threshold=threshold,
        evaluation_scores=len(scores),above_threshold_transactions=len(audit),
        above_threshold_ever_outside_baseline_transactions=sum(bool(r['first_eligible_cutoff']) for r in audit),
        novel_documents_ever_eligible=len({(r['company_id'],r['document_key']) for r in audit if r['first_eligible_cutoff']}),
        scenarios=results,models_fitted=0,observations_scored=0,queue_changed=False,independent_reviews=0,
        actionable_gain=None,actual_review_minutes=None,
        limitations=['IF-only means new admission outside observed baseline transaction/document scope, not proof of no weak/context signals',
            'Singleton lead per document with estimated cost; original baseline cases may cover more work',
            'Subsequent baseline admission is annotated retrospectively and never gates prior selection',
            'Later baseline work is charged again without automatic completion from an IF study review',
            'Technical synthetic replay, not independently useful anomalies or real SME benefit'])
    write_json(output/'summary.json',summary)
    write_json(output/'predictions_frozen.json',{p.relative_to(output).as_posix():sha(p) for p in output.rglob('*') if p.is_file()})
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('dataset','baseline','comparison','coverage','output','protocol'):
        parser.add_argument('--'+name,required=True,type=Path)
    result=run_discovery(**vars(parser.parse_args()))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
