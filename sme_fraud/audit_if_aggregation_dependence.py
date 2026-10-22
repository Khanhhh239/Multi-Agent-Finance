"""Sensitivity to related member sets, using existing aggregation diagnostics."""
from collections import Counter, defaultdict
import json

from .audit_if_aggregation import size_correlation, stratified_correlation
from .shadow_scoring import instant


def dependence_profiles(rows):
    full=[r for r in rows if r['if_coverage']=='full']
    by_case=defaultdict(list)
    for r in full:
        by_case[(r['cohort'],r['company_id'],r['first_case_id'])].append(r)
    earliest=lambda r:(instant(r['first_cutoff_exclusive']),r['unit_id'])
    largest=lambda r:(r['member_count'],instant(r['first_cutoff_exclusive']),r['unit_id'])
    parent=list(range(len(full)))
    def find(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]]
            i=parent[i]
        return i
    owners={}
    for i,row in enumerate(full):
        for tid in json.loads(row['member_ids']):
            key=(row['cohort'],row['company_id'],tid)
            if key in owners:
                parent[find(i)]=find(owners[key])
            else:
                owners[key]=i
    components=defaultdict(list)
    for i,row in enumerate(full):
        components[find(i)].append(row)
    return dict(all_full_member_sets=full,
        first_full_set_per_case=[min(g,key=earliest) for g in by_case.values()],
        largest_full_set_per_case=[max(g,key=largest) for g in by_case.values()],
        largest_full_set_per_transaction_overlap_component=[max(g,key=largest) for g in components.values()],
        rerankable_first_appearance_sets=[r for r in full if r['first_priority']!='cao_nhat'])


def profile_statistics(name, rows):
    uses=Counter((r['cohort'],r['company_id'],t) for r in rows for t in json.loads(r['member_ids']))
    return dict(profile=name,units=len(rows),size_bins=dict(Counter(r['size_bin'] for r in rows)),
        unique_evaluation_members=len(uses),repeated_member_occurrences=sum(n-1 for n in uses.values()),
        size_max_spearman=size_correlation(rows),size_residual_spearman=size_correlation(rows,'actual_minus_reference'),
        within_company=stratified_correlation(rows,('company_id',)),
        within_company_type=stratified_correlation(rows,('company_id','txn_group')))
