"""Describe the existing max-member IF aggregate; do not change ranking or scores."""
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
import json
import math
from pathlib import Path

import numpy as np

from .audit_if_coverage import unique_index, verify_commitment
from .compare_shadow import build_snapshots, read_csv, read_json, write_csv, write_json
from .feature_contract import digest, sha
from .shadow_scoring import guarded, instant, output_guard

VERSION = 'if-max-member-audit-v1'
SIZE_BINS = ('1','2','3-4','5-8','9+')


def size_bin(n):
    return '1' if n==1 else '2' if n==2 else '3-4' if n<=4 else '5-8' if n<=8 else '9+'


def rank_average(values):
    values = np.asarray(values, dtype=float)
    if not np.isfinite(values).all():
        raise ValueError('Diagnostic ranks require finite values')
    _, inverse, counts = np.unique(values, return_inverse=True, return_counts=True)
    ends = np.cumsum(counts)
    return (ends-(counts-1)/2)[inverse]


def correlation(x, y):
    x, y = np.asarray(x,dtype=float), np.asarray(y,dtype=float)
    if len(x)<3 or np.ptp(x)==0 or np.ptp(y)==0:
        return None
    return float(np.corrcoef(x,y)[0,1])


def size_correlation(rows, value='if_max'):
    return correlation(rank_average([r['member_count'] for r in rows]), rank_average([r[value] for r in rows]))


def stratified_correlation(rows, fields, value='if_max'):
    groups = defaultdict(list)
    for r in rows:
        groups[tuple(r[f] for f in fields)].append(r)
    x, y, used = [], [], 0
    for group in groups.values():
        if len(group)<3:
            continue
        a = rank_average([r['member_count'] for r in group])
        b = rank_average([r[value] for r in group])
        if np.ptp(a)==0 or np.ptp(b)==0:
            continue
        x.extend((a-a.mean())/(len(group)-1))
        y.extend((b-b.mean())/(len(group)-1))
        used += 1
    return dict(strata=list(fields),rho=correlation(x,y),included_units=len(x),
                excluded_units=len(rows)-len(x),included_strata=used,total_strata=len(groups))


def describe_case(case, cutoff, cohort, transactions, score_rows):
    members = json.loads(case['transaction_ids']) if isinstance(case['transaction_ids'],str) else case['transaction_ids']
    if not isinstance(members,list) or not members or len(members)!=len(set(members)):
        raise ValueError('Transaction cases require unique nonempty members')
    types = Counter()
    values = []
    for tid in members:
        row = transactions.get(tid)
        if row is None or row['company_id']!=case['company_id'] or instant(row['posted_at'])>=instant(cutoff):
            raise ValueError('Unknown, cross-company or future member')
        if not row.get('txn_type'):
            raise ValueError('Business type is required')
        types[row['txn_type']] += 1
        if tid in score_rows:
            score = score_rows[tid]
            value = float(score['anomaly_score'])
            if (not math.isfinite(value) or score['company_id']!=row['company_id']
                    or instant(score['posted_at'])!=instant(row['posted_at'])):
                raise ValueError('Invalid member score/source binding')
            values.append(value)
    full = len(values)==len(members)
    maximum = max(values) if full else None
    if case['if_score'] != maximum or (case['if_coverage']=='full') != full:
        raise ValueError('Reconstructed aggregate differs from frozen max-member policy')
    winners = [transactions[t]['txn_type'] for t in members if full and float(score_rows[t]['anomaly_score'])==maximum]
    return dict(unit_id=digest([cohort,case['company_id'],sorted(members)]),cohort=cohort,
        company_id=case['company_id'],first_cutoff_exclusive=cutoff,first_month=case['opened_at'][:7],
        first_priority=case['priority'],first_case_id=case['case_id'],first_scope_hash=case['production_scope_hash'],
        member_ids=json.dumps(sorted(members)),member_count=len(members),size_bin=size_bin(len(members)),
        txn_group=next(iter(types)) if len(types)==1 else 'mixed',
        txn_type_signature='+'.join(sorted(types)),txn_type_counts=json.dumps(dict(sorted(types.items()))),
        type_count=len(types),if_coverage='full' if full else 'missing_or_partial',scored_members=len(values),
        if_max=maximum,member_mean=float(np.mean(values)) if full else None,
        member_median=float(np.median(values)) if full else None,
        max_minus_member_median=maximum-float(np.median(values)) if full else None,
        winner_type_signature='+'.join(sorted(set(winners))),winner_ties=len(winners))


def collect_units(snapshots, cohort, transactions, scores, selections):
    """Deduplicate by exact member set, before inspecting selection outcomes."""
    units, scopes, selected = {}, defaultdict(set), []
    by_day = defaultdict(list)
    for row in selections:
        by_day[row['day']].append(row)
    for snapshot in snapshots:
        descriptors = {}
        for case in snapshot['cases']:
            if case['case_type']!='transaction':
                continue
            descriptor = describe_case(case,snapshot['cutoff'],cohort,transactions,scores)
            key = descriptor['unit_id']
            if key not in units:
                descriptor['first_month'] = snapshot['day'].isoformat()[:7]
                units[key] = dict(descriptor,snapshot_occurrences=0)
            units[key]['snapshot_occurrences'] += 1
            scopes[key].add(case['production_scope_hash'])
            descriptors[(snapshot['day'].isoformat(),case['case_id'],case['production_scope_hash'])] = descriptor
        for row in by_day[snapshot['day'].isoformat()]:
            if row['case_type']!='transaction':
                continue
            d = descriptors.get((row['day'],row['case_id'],row['case_scope_hash']))
            if (d is None or row['company_id']!=d['company_id'] or row['if_coverage']!=d['if_coverage']
                    or int(row['member_count'])!=d['member_count']
                    or (row['if_score']=='')!=(d['if_max'] is None)
                    or (row['if_score'] and float(row['if_score'])!=d['if_max'])):
                raise ValueError('Frozen selected review differs from case reconstruction')
            selected.append(dict(d,budget=int(row['budget']),arm=row['arm'],day=row['day'],
                work_key=row['work_key'],selection_priority=row['priority']))
    if len(selected)!=sum(r['case_type']=='transaction' for r in selections):
        raise ValueError('Selected reviews were not completely reconstructed')
    for key, row in units.items():
        row['scope_variants'] = len(scopes[key])
    return list(units.values()), selected


def score_pools(transactions, scores):
    pools = defaultdict(list)
    for tid, score in scores.items():
        source = transactions[tid]
        pools[(source['company_id'],source['txn_type'])].append((instant(source['posted_at']),float(score['anomaly_score'])))
    return {key:(sorted(rows),[x[0] for x in sorted(rows)]) for key,rows in pools.items()}


def max_reference(unit, pools, *, repetitions, seed):
    """Composition-matched diagnostic draws; never a replacement case score.

    Sample without replacement within company/type, from evaluation scores strictly
    before this unit's first cutoff. The member set and type counts stay fixed.
    """
    if repetitions<100:
        raise ValueError('Use at least 100 descriptive reference draws')
    cutoff = instant(unit['first_cutoff_exclusive'])
    arrays, sizes = [], {}
    composition = json.loads(unit['txn_type_counts'])
    for txn_type, count in sorted(composition.items()):
        rows, times = pools[(unit['company_id'],txn_type)]
        available = np.asarray([v for _,v in rows[:bisect_left(times,cutoff)]],dtype=float)
        if len(available)<count or not np.isfinite(available).all():
            raise ValueError('Reference pool does not cover the causal type composition')
        arrays.append((available,count));sizes[txn_type]=len(available)
    single = sum(float(a.mean())*n for a,n in arrays)/unit['member_count']
    if unit['member_count']==1:
        expected, sd, se = single,0.,0.
    else:
        rng = np.random.default_rng(int(digest([seed,unit['unit_id']])[:16],16))
        draws = np.full(repetitions,-np.inf)
        for i in range(repetitions):
            draws[i] = max(float(rng.choice(a,size=n,replace=False).max()) for a,n in arrays)
        expected, sd = float(draws.mean()),float(draws.std(ddof=1))
        se = sd/math.sqrt(repetitions)
    return dict(reference_single_mean=single,reference_max_mean=expected,
        reference_max_uplift=expected-single,actual_minus_reference=unit['if_max']-expected,
        reference_max_simulation_se=se,reference_max_sd=sd,
        reference_pool_sizes=json.dumps(sizes,sort_keys=True),
        reference_pool_exhausted=any(sizes[t]==n for t,n in composition.items()),
        reference_all_pools_exhausted=all(sizes[t]==n for t,n in composition.items()))


def summarize_group(rows, cohort, dimension, group):
    scores = [r['if_max'] for r in rows]
    return dict(cohort=cohort,dimension=dimension,group=group,units=len(rows),
        member_count_mean=float(np.mean([r['member_count'] for r in rows])),
        max_mean=float(np.mean(scores)),max_p25=float(np.quantile(scores,.25)),
        max_median=float(np.median(scores)),max_p75=float(np.quantile(scores,.75)),
        member_mean=float(np.mean([r['member_mean'] for r in rows])),
        max_minus_member_median_mean=float(np.mean([r['max_minus_member_median'] for r in rows])),
        reference_max_mean=float(np.mean([r['reference_max_mean'] for r in rows])),
        reference_single_mean=float(np.mean([r['reference_single_mean'] for r in rows])),
        reference_max_uplift_mean=float(np.mean([r['reference_max_uplift'] for r in rows])),
        actual_minus_reference_mean=float(np.mean([r['actual_minus_reference'] for r in rows])),
        pool_exhausted_units=sum(r['reference_pool_exhausted'] for r in rows),
        size_max_spearman=size_correlation(rows),size_residual_spearman=size_correlation(rows,'actual_minus_reference'))


def analyze_units(units, transactions, scores, cohort, *, repetitions, seed):
    full = [r for r in units if r['if_coverage']=='full']
    pools = score_pools(transactions,scores)
    for row in full:
        row.update(max_reference(row,pools,repetitions=repetitions,seed=seed))
    groups=[]
    for fields in (('size_bin',),('company_id',),('txn_group',),('company_id','txn_group'),
                   ('first_month',),('first_priority',)):
        buckets=defaultdict(list)
        for row in full:
            buckets[tuple(row[f] for f in fields)].append(row)
        for key, rows in sorted(buckets.items()):
            groups.append(summarize_group(rows,cohort,'+'.join(fields),'|'.join(key)))
    controls=[('company_id',),('txn_group',),('company_id','txn_group'),
              ('company_id','txn_group','first_month','first_priority')]
    uses=Counter(t for r in full for t in json.loads(r['member_ids']))
    summary=dict(cohort=cohort,unique_member_sets=len(units),full_coverage_member_sets=len(full),
        excluded_missing_or_partial=len(units)-len(full),
        eligible_size_bins=dict(Counter(r['size_bin'] for r in full)),
        eligible_priorities=dict(Counter(r['first_priority'] for r in full)),
        unique_evaluation_members=len(uses),member_sets_sharing_transactions=sum(
            any(uses[t]>1 for t in json.loads(r['member_ids'])) for r in full),
        size_max_spearman=size_correlation(full),size_residual_spearman=size_correlation(full,'actual_minus_reference'),
        conditional_correlations=[stratified_correlation(full,f) for f in controls],
        conditional_residual_correlations=[stratified_correlation(full,f,'actual_minus_reference') for f in controls],
        reference_repetitions=repetitions,reference_seed=seed,
        reference_pool_exhausted_units=sum(r['reference_pool_exhausted'] for r in full),
        reference_all_pools_exhausted_units=sum(r['reference_all_pools_exhausted'] for r in full),
        reference_max_simulation_se_max=max(r['reference_max_simulation_se'] for r in full),
        rerankable_first_appearance_units=sum(r['first_priority']!='cao_nhat' for r in full))
    return summary, groups


def audit_aggregation(dataset, baseline, comparison, coverage, output, *, repetitions=1000, seed=20261022):
    if type(repetitions) is not int or repetitions<100 or type(seed) is not int or seed<0:
        raise ValueError('Reference requires an integer seed >=0 and at least 100 draws')
    dataset,baseline,comparison,coverage,output=map(guarded,(dataset,baseline,comparison,coverage,output))
    output_guard(output,dataset,comparison/'unused-model')
    if any(output.is_relative_to(p) or p.is_relative_to(output) for p in (baseline,comparison,coverage)):
        raise ValueError('Aggregation output must be separate from frozen inputs')
    inputs=verify_commitment(comparison)
    for name in ('audit_if_aggregation.py','audit_if_coverage.py'):
        path=Path(__file__).resolve().with_name(name)
        inputs[str(path)]=sha(path)
    inputs[str(coverage/'output_commitment.json')]=sha(coverage/'output_commitment.json')
    for name,h in read_json(coverage/'output_commitment.json').items():
        path=guarded(coverage/name)
        if not path.is_relative_to(coverage) or sha(path)!=h:
            raise ValueError('Coverage audit output changed')
        inputs[str(path)]=h
    for path,h in read_json(coverage/'input_commitment.json').items():
        if sha(guarded(path))!=h:
            raise ValueError('Coverage audit input changed')
        inputs[path]=h
    metadata=read_json(dataset/'manifest.json')
    prior=read_json(coverage/'summary.json')
    plan=read_json(comparison/'evaluation_plan.json')
    run=read_json(comparison/'if_scores/run.json')
    cohort=dataset.name.removeprefix('sme_fraud_')
    if (cohort not in {'001','003'} or metadata.get('role')!='reporting' or metadata.get('is_synthetic') is not True
            or prior['status']!='coverage_explained' or guarded(prior['dataset'])!=dataset
            or guarded(prior['comparison'])!=comparison or run['manifest_sha256']!=sha(dataset/'manifest.json')
            or not {str(dataset/'transactions.csv'),str(comparison/'evaluation_plan.json')}<=set(inputs)):
        raise ValueError('Requires unchanged reporting 001/003 coverage audit')
    frozen_plan=dict(version=VERSION,cohort=cohort,seed=seed,repetitions=repetitions,
        analysis_unit='Exact transaction member set per cohort/company, first causal appearance; repeated days/scopes deduplicated',
        universe='All admitted transaction cases seen in frozen daily reconstruction; not only reviewed cases',
        eligibility='All members have valid evaluation IF scores; history/partial remain excluded',
        business_type='Source txn_type; multiple types are mixed and exact composition is retained',
        reference='Within cohort/company/txn_type; sample without replacement before first cutoff, matching type counts',
        reference_interpretation='Descriptive max-size reference; not a replacement score, independent null or performance estimate',
        conditional_statistic='Pooled centered fractional ranks inside varying strata of >=3 member sets; report exclusions',
        inference='Descriptive only; overlapping member sets, sparse strata and case admission prevent significance or causal claims',
        production_changes=False,alternative_aggregation_tested=False,model_fit=False,model_scored=False,
        input_sha256=inputs)
    output.mkdir(parents=True)
    write_json(output/'analysis_plan.json',frozen_plan)
    transactions=unique_index(read_csv(dataset/'transactions.csv'),'transaction_id')
    scores=unique_index(read_csv(comparison/'if_scores/shadow_scores.csv'),'transaction_id')
    if len(scores)!=run['rows_scored'] or any(r['run_id']!=run['run_id'] for r in scores.values()):
        raise ValueError('Frozen score run/count differs')
    snapshots,baseline_inputs,reconstruction=build_snapshots(dataset,baseline,plan['scope'],
        {t:float(r['anomaly_score']) for t,r in scores.items()})
    if baseline_inputs!=plan['baseline_input_sha256'] or reconstruction!=plan['baseline_reconstruction']:
        raise ValueError('Frozen reconstruction changed')
    selections=[dict(r,budget=b) for b in (5,10) for r in read_csv(comparison/f'budget_{b}/selections.private.csv')]
    units,selected=collect_units(snapshots,cohort,transactions,scores,selections)
    summary,groups=analyze_units(units,transactions,scores,cohort,repetitions=repetitions,seed=seed)
    transaction_groups=[]
    for fields in (('company_id',),('txn_type',),('company_id','txn_type')):
        buckets=defaultdict(list)
        for t,r in scores.items():
            buckets[tuple(transactions[t][f] for f in fields)].append(float(r['anomaly_score']))
        for key,values in sorted(buckets.items()):
            transaction_groups.append(dict(cohort=cohort,dimension='+'.join(fields),group='|'.join(key),
                transactions=len(values),score_mean=float(np.mean(values)),score_median=float(np.median(values)),
                score_p95=float(np.quantile(values,.95))))
    selection_groups=[]
    for budget in (5,10):
        for arm in ('baseline','if_shadow'):
            rows=[r for r in selected if r['budget']==budget and r['arm']==arm]
            for group in SIZE_BINS:
                chosen=[r for r in rows if r['if_coverage']=='full' and r['size_bin']==group]
                selection_groups.append(dict(cohort=cohort,budget=budget,arm=arm,size_bin=group,
                    all_transaction_reviews=len(rows),full_if_reviews=sum(r['if_coverage']=='full' for r in rows),
                    selected_full_reviews=len(chosen),rerankable_selected_full_reviews=sum(r['selection_priority']!='cao_nhat' for r in chosen)))
    if any(sha(p)!=h for p,h in inputs.items()):
        raise ValueError('Frozen inputs changed during aggregation audit')
    for name,rows in (('member_sets.private.csv',units),('selected_reviews.private.csv',selected),
            ('group_statistics.csv',groups),('transaction_score_groups.csv',transaction_groups),
            ('selection_size_groups.csv',selection_groups)):
        fields=list(dict.fromkeys(k for r in rows for k in r))
        write_csv(output/name,rows,fields)
    write_json(output/'summary.json',dict(summary,version=VERSION,models_fitted=0,observations_scored=0,
        aggregation_changed=False,ranking_changed=False,independent_outcomes_added=0))
    write_json(output/'output_commitment.json',{p.name:sha(p) for p in output.iterdir() if p.is_file()})
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('dataset','baseline','comparison','coverage','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--repetitions',type=int,default=1000)
    parser.add_argument('--seed',type=int,default=20261022)
    print(json.dumps(audit_aggregation(**vars(parser.parse_args())),ensure_ascii=False))


if __name__=='__main__':
    main()
