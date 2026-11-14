"""Accountant result allowlist; model/config internals stay server-side."""
from copy import deepcopy


def pick(value,fields):
    return {k:deepcopy(value[k]) for k in fields if k in value}


def review_result(value):
    result=pick(value,('version','run_id','company_id','snapshot_id','as_of','status','row_count','aggregation'))
    result['rows']=[]
    for row in value['rows']:
        public=pick(row,('record_id','revision','available','status','reason','score','raw_score'))
        if 'branches' in row:
            public['branches']={}
            for name,branch in row['branches'].items():
                safe=pick(branch,('available','status','reason','matched','raw_score','probability'))
                if name=='rules':
                    for key in ('invoice_checks','simultaneous_checks'):
                        safe[key]=[pick(c,('obligation','prior_paid_vnd','current_allocated_vnd','invoice_gross_vnd','cumulative_paid_vnd','excess_vnd','matched','previous_payment')) for c in branch.get(key,[])]
                    safe['gaps']=[pick(g,('code','message','action')) for g in branch.get('gaps',[])]
                if name=='graph':safe.update(pick(branch,('entities','links_by_field','strong_reachability')))
                if 'evidence_refs' in branch:safe['evidence_refs']=[pick(r,('table','record_id','revision','observed_at','effective_at')) for r in branch['evidence_refs']]
                public['branches'][name]=safe
        result['rows'].append(public)
    return result
