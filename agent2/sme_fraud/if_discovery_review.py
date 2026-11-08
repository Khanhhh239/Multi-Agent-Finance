"""Blind review material for frozen IF-discovery shadow differences and controls."""
from collections import Counter,defaultdict
import json
from pathlib import Path
import zipfile

from .compare_shadow import read_csv,read_json,write_csv,write_json
from .compare_if_discovery import case_document_keys,document_key
from .feature_contract import digest,sha
from .independent_ml_review import (PRIMARY_FIELDS,ADJ_FIELDS,evidence_for,card_markdown,load_tables,validate_reviews)
from .shadow_scoring import guarded,instant,output_guard


def key_for(row,cohort):
    return digest([cohort,row['case_id'],row['case_scope_hash'],instant(row['cutoff_exclusive']).isoformat()])


def scope_for(row,scope_index):
    exact=scope_index.get((row['case_id'],row['case_scope_hash']))
    if exact is not None:return exact
    # Frozen source work ignores overdue-clock drift. Its object identity remains
    # fixed while daily production_scope_hash may change; export at the row cutoff.
    options=[r for (cid,_),r in scope_index.items() if cid==row['case_id']]
    signatures={(r['source_scope'],r['rule_ids'],r['transaction_ids']) for r in options}
    if (row['case_type']!='source' or len(signatures)!=1 or not options
            or any(r['case_type']!='source' or json.loads(r['transaction_ids']) for r in options)):
        raise ValueError('Frozen selected scope has no unambiguous source-object mapping')
    return options[0]


def select_disagreements(original,experimental,cohort,scope_index,seed):
    chosen={};reservoir={};populations=Counter()
    originals=defaultdict(dict);alternates=defaultdict(dict)
    for row in original:
        if row['arm']=='baseline':originals[(row['day'],row['company_id'])][row['work_key']]=row
    for row in experimental:alternates[(row['day'],row['company_id'])][row['work_key']]=row
    def descriptor(row,group):
        key=key_for(row,cohort)
        case=dict(row)
        if 'transaction_ids' not in case:
            scope=scope_for(row,scope_index)
            case.update({f:scope[f] for f in ('transaction_ids','source_scope','rule_ids','case_type')})
        return key,dict(cohort=cohort,company_id=row['company_id'],case_id=row['case_id'],
            case_scope_hash=row['case_scope_hash'],cutoff_exclusive=row['cutoff_exclusive'],case=case,
            sample_group=group,selection_events=[row])
    for stamp in sorted(set(originals)|set(alternates)):
        left,right=originals[stamp],alternates[stamp]
        for work_key in set(left)^set(right):
            row=(left if work_key in left else right)[work_key]
            group='if_discovery_selected' if row.get('origin')=='if_only' else 'baseline_selection_disagreement'
            key,d=descriptor(row,group)
            if key in chosen:chosen[key]['selection_events'].append(row)
            else:chosen[key]=d
        for work_key in set(left)&set(right):
            key,d=descriptor(left[work_key],'reference_common_selected')
            stratum=(cohort,d['company_id'])
            populations[stratum]+=1
            rank=digest([seed,'common',stratum,key])
            if stratum not in reservoir or rank<reservoir[stratum][0]:reservoir[stratum]=(rank,key,d)
    for stratum,(_,key,d) in reservoir.items():
        if key in chosen:continue
        chosen[key]=dict(d,stratum_population=populations[stratum],inclusion_probability=1/populations[stratum])
    return chosen


def prepare_discovery_review(discovery_root,output,*,seed=20261022,comparison_root=None,source_root=None):
    discovery_root,output=guarded(discovery_root),guarded(output)
    output_guard(output,discovery_root,discovery_root/'unused-model')
    root=Path(__file__).resolve().parents[1]
    comparison_root=guarded(comparison_root or root/'reports/ml_shadow_comparison_20261022')
    source_root=guarded(source_root or root/'data/synthetic_sources_20261017_v2')
    inputs={};chosen={};tables={}
    for path in (Path(__file__).resolve(),Path(__file__).resolve().with_name('independent_ml_review.py')):
        inputs[str(path)]=sha(path)
    for tag in ('001','003'):
        cohort='sme_fraud_'+tag;target=discovery_root/cohort
        for name,h in read_json(target/'predictions_frozen.json').items():
            path=guarded(target/name)
            if not path.is_relative_to(target) or sha(path)!=h:raise ValueError('Discovery commitment changed')
            inputs[str(path)]=h
        inputs[str(target/'predictions_frozen.json')]=sha(target/'predictions_frozen.json')
        for path,h in read_json(target/'analysis_plan.json')['input_sha256'].items():
            if sha(guarded(path))!=h:raise ValueError('Source/comparison binding changed before review export')
            inputs[path]=h
        original_root=comparison_root/cohort
        original=read_csv(original_root/'budget_5/selections.private.csv')
        experimental=read_csv(target/'budget_5_share_20_cost_20/selections.private.csv')
        scope_rows=read_csv(original_root/'review_union.blind.csv')
        scope_index={(r['case_id'],r['case_scope_hash']):r for r in scope_rows}
        chosen.update(select_disagreements(original,experimental,tag,scope_index,seed))
        source=source_root/cohort
        tables[tag]=load_tables(source)
        tx={r['transaction_id']:r for r in tables[tag]['transactions']}
        reviewed_docs=set()
        for row in [r for r in original if r['arm']=='baseline']+experimental:
            case=row if 'transaction_ids' in row else scope_for(row,scope_index)
            case=dict(case,company_id=row['company_id'])
            _,docs=case_document_keys(case,tx);reviewed_docs.update(docs)
        end=read_json(original_root/'evaluation_plan.json')['scope']['end_at']
        pools=defaultdict(lambda:defaultdict(list))
        for row in read_csv(original_root/'if_scores/shadow_scores.csv'):
            source_row=tx[row['transaction_id']];doc=document_key(source_row)
            if doc not in reviewed_docs:pools[source_row['company_id']][doc].append(source_row)
        for company,docs in pools.items():
            doc=min(docs,key=lambda d:digest([seed,'unreviewed_document',tag,d]))
            row=min(docs[doc],key=lambda r:digest([seed,'representative',r['transaction_id']]))
            cid='REF_'+digest([tag,doc])[:20]
            scope=digest([tag,doc,row['transaction_id']])
            case=dict(case_id=cid,company_id=company,transaction_ids=json.dumps([row['transaction_id']]),
                source_scope='',rule_ids='',case_type='transaction')
            d=dict(cohort=tag,company_id=company,case_id=cid,case_scope_hash=scope,cutoff_exclusive=end,
                case=case,sample_group='reference_unreviewed_document_at_end',
                stratum_population=len(docs),inclusion_probability=1/len(docs),selection_events=[])
            chosen[digest([tag,cid,scope,end])]=d
    output.mkdir(parents=True)
    public=output/'public';private=output/'private';public.mkdir();private.mkdir()
    write_json(private/'selection_plan.json',dict(seed=seed,primary='budget_5_share_20_cost_20',
        forced='All same-day symmetric-difference case snapshots including new IF leads and baseline timing differences',
        random_common='One common-selected snapshot per cohort/company using seeded hash rank',
        random_unreviewed='One evaluation document per cohort/company unreviewed in both primary arms by end, at end cutoff',
        inference='Diagnostic census/stratified references; not a population benefit estimator',input_sha256=inputs))
    pairs=sorted({(r['cohort'],r['company_id']) for r in chosen.values()},key=lambda p:digest([seed,p]))
    aliases={p:'DN'+str(i+1).zfill(2) for i,p in enumerate(pairs)}
    units=[];mapping=[];readonly={}
    for key in sorted(chosen,key=lambda k:digest(['public_order',seed,k])):
        d=chosen[key];rid='DRV_'+digest([seed,key])[:16];alias=aliases[(d['cohort'],d['company_id'])]
        folder=public/'evidence'/rid;folder.mkdir(parents=True)
        evidence=evidence_for(d,tables[d['cohort']],alias)
        write_json(folder/'evidence.json',evidence)
        (folder/'review.md').write_text(card_markdown(rid,evidence),encoding='utf-8')
        for name in ('evidence.json','review.md'):readonly[(folder/name).relative_to(public).as_posix()]=sha(folder/name)
        units.append(dict(review_unit_id=rid,company_code=alias,cutoff_exclusive=d['cutoff_exclusive'],
            evidence_sha256=sha(folder/'evidence.json'),evidence_ref='evidence/'+rid+'/review.md'))
        mapping.append(dict(review_unit_id=rid,unit_key=key,**{k:v for k,v in d.items() if k!='case'}))
    write_csv(public/'primary_reviews.csv',units,PRIMARY_FIELDS)
    write_csv(public/'adjudications.csv',units,ADJ_FIELDS)
    old_readme=root/'reports/ml_independent_review_20261022/public/README.md'
    inputs[str(old_readme)]=sha(old_readme)
    (public/'README.md').write_bytes(old_readme.read_bytes())
    index=['# Danh sách phiếu rà','','| Mã | Công ty | Cutoff loại trừ | Bằng chứng |','|---|---|---|---|']
    index.extend(f"| {u['review_unit_id']} | {u['company_code']} | {u['cutoff_exclusive']} | [Mở]({u['evidence_ref']}) |" for u in units)
    (public/'REVIEW_INDEX.md').write_text('\n'.join(index)+'\n',encoding='utf-8')
    for name in ('README.md','REVIEW_INDEX.md'):readonly[name]=sha(public/name)
    write_json(public/'review_manifest.json',dict(version='independent-ml-review-v1',source_origin='synthetic_process_simulation',
        status='awaiting_human_independent_review',units=units,readonly_sha256=readonly,forms_mutable=True,independent_reviews=0))
    write_json(private/'unit_mapping.json',mapping)
    write_json(private/'reviewer_assignment.json',dict(status='unassigned',primary_reviewer_id=None,adjudicator_id=None))
    write_json(private/'prepared_commitment.json',dict(public_manifest_sha256=sha(public/'review_manifest.json'),
        mapping_sha256=sha(private/'unit_mapping.json'),input_sha256=inputs))
    if any(sha(p)!=h for p,h in inputs.items()):raise ValueError('Discovery review inputs changed')
    with zipfile.ZipFile(output/'reviewer_packet.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(public.rglob('*')):
            if path.is_file():archive.write(path,path.relative_to(public).as_posix())
    initial=validate_reviews(output,public/'primary_reviews.csv',public/'adjudications.csv',private/'initial_validation')
    assert initial['validated_independent_units']==0 and initial['pending_units']==len(units)
    summary=dict(units=len(units),sample_groups=dict(Counter(d['sample_group'] for d in chosen.values())),
        independent_reviews=0,actual_review_minutes=None,actionable_gain=None,
        reviewer_zip_sha256=sha(output/'reviewer_packet.zip'),status='prepared_awaiting_human_review')
    write_json(output/'summary.json',summary)
    return summary
