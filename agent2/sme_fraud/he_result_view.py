"""Accountant result allowlist; model/config internals stay server-side."""
from copy import deepcopy


def pick(value,fields):
    return {k:deepcopy(value[k]) for k in fields if k in value}


def review_result(value):
    if value.get('version')=='he-rule-snapshot-groups-result/1.0.0':
        result=pick(value,('version','contract_version','run_id','company_id','snapshot_id','snapshot_checksum','data_checksum','as_of','status','row_count','aggregation'))
        if isinstance(value.get('provenance'),dict):
            result['provenance']=pick(value['provenance'],('snapshot_id','snapshot_checksum','data_checksum','as_of','covered_he_rules','covered_rule_count','total_rule_count'))
        result['rows']=[]
        for row in value['rows']:
            public=pick(row,('record_id','transaction_id','revision','known_at_cutoff','txn_type','posted_at','observed_at','amount_vnd','currency','available','status','matched','reason','score','unsupported_summary'))
            if 'groups' in row:
                public['groups']={}
                for gk,gv in row['groups'].items():
                    safe=pick(gv,('rule_id','profile','available','status','applicable','matched','score','hard_trigger','scoring_role','scoring_family','intrinsic_points','overlap_kind','shared_fields','matched_employee_ids','ambiguous_employee_ids','disclosed','reason','explanation'))
                    if 'gaps' in gv:safe['gaps']=deepcopy(gv['gaps'])
                    if 'row_check' in gv:safe['row_check']=deepcopy(gv['row_check'])
                    if 'simultaneous_checks' in gv:safe['simultaneous_checks']=deepcopy(gv['simultaneous_checks'])
                    if 'details' in gv:safe['details']=deepcopy(gv['details'])
                    public['groups'][gk]=safe
            if 'branches' in row:
                public['branches']={}
                for bk,bv in row['branches'].items():
                    safe=pick(bv,('rule_id','profile','available','status','applicable','matched','score','hard_trigger','reason','message','explanation'))
                    if 'gaps' in bv:safe['gaps']=deepcopy(bv['gaps'])
                    if 'evidence_refs' in bv:safe['evidence_refs']=deepcopy(bv['evidence_refs'])
                    public['branches'][bk]=safe
            result['rows'].append(public)
        return result
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
