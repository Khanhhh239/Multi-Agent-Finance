"""Generate full split sizes, excluding every previously used tuning question.

Test rows are written sealed; only aggregate manifests are printed.
"""
import argparse,ast,hashlib,json,re,random
from collections import Counter
from datetime import date
from pathlib import Path
import duckdb
from agent4.engine.metrics import REGISTRY
from agent4.engine.periods import resolve_period,previous_period,comparable_partial
from eval.oracle import oracle
from .noise import perturb
from .period_phrases import PHRASES,AS_OF,check_phrases
from .synonyms import synonyms
from .split import question_hash,assert_disjoint

ROOT=Path(__file__).resolve().parents[2]
SPLITS={'train':(20251,'cfo_warehouse',600),'val':(71,'val',200),'test':(9001,'test',400)}
FORMS={
 'train':['Cho tôi tra {metric} {period}{suffix}.','{metric} cho {period}{suffix}, báo kết quả giúp tôi.'],
 'val':['Báo cáo giúp {metric} ứng với kỳ {period}{suffix}.','Đọc kết quả {metric} tại kỳ {period}{suffix}.'],
 'test':['Tôi cần tra cứu {metric} thuộc khoảng {period}{suffix}.','Vui lòng cung cấp {metric} đối với {period}{suffix}.'],
}


def tuning_hashes():
    questions=set(re.findall(r'^\d+\. (.+)$',(ROOT/'reference_v0/sample-questions.md').read_text(encoding='utf8'),re.M))
    paths=list((ROOT/'tests/data').glob('*.jsonl'))+[ROOT/'agent4/agent/data/fewshot_bank.jsonl']
    for path in paths:
        for line in path.read_text(encoding='utf8').splitlines():
            row=json.loads(line)
            if 'question' in row:questions.add(row['question'])
    for path in (ROOT/'tests').glob('test_*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf8'))):
            if isinstance(node,ast.Constant) and isinstance(node.value,str) and len(node.value)>4:
                questions.add(node.value)
    return {question_hash(q) for q in questions}


def expected_value(con,call):
    md=REGISTRY[call['metric']]
    per=resolve_period(call.get('period'),AS_OF,'today' if md.period_type=='snapshot' else 'this_month')
    value=oracle(con,md.id,per.start,per.end,call['view'],call.get('filters'))
    expected={'value':value,'start':per.start.isoformat(),'end':per.end.isoformat(),'view':call['view'],'unit':md.unit}
    if call.get('compare_to'):
        prior=comparable_partial(per,previous_period(per),AS_OF)
        expected['comparison_value']=oracle(con,md.id,prior.start,prior.end,call['view'],call.get('filters'))
        expected['comparison_start']=prior.start.isoformat();expected['comparison_end']=prior.end.isoformat()
    return expected


def make_cases(suite,split,con,excluded):
    seed,_,size=SPLITS[split];rng=random.Random(seed+len(suite));ids=list(REGISTRY)
    rows=[];attempt=0
    while len(rows)<size:
        i=len(rows);metric=ids[i%len(ids)];md=REGISTRY[metric];j=i//len(ids)+attempt
        form_index=(i//len(ids)+i)%2
        tokens=('today','last_month','last_quarter','2026-Q2','ytd') if md.period_type=='snapshot' else ('this_month','last_month','last_quarter','2026-Q2','ytd')
        token=tokens[j%len(tokens)]
        phrase=PHRASES[token][(j//len(tokens))%4]
        syn=synonyms(metric)[j%len(synonyms(metric))]
        call={'action':'query_metric','metric':metric,'period':token,'view':md.default_view}
        suffix=' theo khung thuế' if md.default_view=='tax' else ''
        tags=[]
        if suite=='e2':
            # Independent oracle supports filters for flow/ratio/snapshot;
            # unimplemented filtered customs are never mislabeled as supported.
            if j%3==0 and md.kind!='custom' and 'branch' in md.group_bys:
                branch=con.execute('SELECT branch_code,branch_name FROM dim_branch ORDER BY branch_code').fetchall()[j%3]
                call['filters']={'branch':branch[0]};suffix+=' tại '+branch[1];tags.append('entity')
            elif j%3==1 and md.kind!='custom' and 'customer' in md.group_bys:
                partner=con.execute("SELECT partner_code,partner_name FROM dim_partner WHERE partner_type='CUSTOMER' ORDER BY partner_code LIMIT 6").fetchall()[j%6]
                call['filters']={'customer':partner[0]};suffix+=' của khách hàng '+partner[1];tags.append('entity')
            elif md.group_bys:
                group=md.group_bys[j%len(md.group_bys)];call['group_by']=group
                labels={'month':'tháng','quarter':'quý','year':'năm','branch':'chi nhánh','product_line':'dòng sản phẩm','customer':'khách hàng','item':'mặt hàng','salesperson':'nhân viên','account':'tài khoản','department':'phòng ban','cost_category':'khoản mục','vendor':'nhà cung cấp'}
                suffix+=' theo '+labels[group];tags.append('group')
            if j%4==2 and md.kind=='flow':
                call['compare_to']='previous_period';suffix+=' so với kỳ trước';tags.append('compare')
        question=FORMS[split][form_index].format(metric=syn,period=phrase,suffix=suffix)
        if suite=='e2':question='Tra số chi tiết: '+question
        if i%4==0:
            question,noise=perturb(question,i//4);tags.append(noise)
        digest=question_hash(question)
        if digest in excluded:
            attempt+=1
            if attempt>50000:raise RuntimeError('Cannot produce disjoint examples')
            continue
        excluded.add(digest);attempt=0
        gold=expected_value(con,call)
        rows.append({'id':f'{suite}.{split}.{i:04}','split':split,'template_id':f'{suite}.{metric}.{split}.form{form_index}',
                     'template_family':f'{suite}.{split}.form{form_index}','capability':'tool' if suite=='e1' else 'args',
                     'difficulty':'hard' if len(tags)>1 else 'medium' if tags else 'easy','tags':tags,'as_of':AS_OF.isoformat(),
                     'question':question,'metric_synonym':syn,'expected':{'tool':'query_metric','args':{k:v for k,v in call.items() if k!='action'}},
                     'expected_behavior':'answer','gold':gold,'label_source':'independent_oracle','warehouse_seed':seed})
    return rows


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'eval/data');args=p.parse_args()
    if (args.out/'manifest_e1_e2.json').exists():raise SystemExit('Dataset already frozen; do not overwrite.')
    check_phrases();args.out.mkdir(parents=True,exist_ok=True)
    excluded=tuning_hashes();initial=len(excluded);all_records={s:[] for s in SPLITS};manifest={}
    for suite in ('e1','e2'):
        for split,(seed,warehouse,_) in SPLITS.items():
            with duckdb.connect(str(ROOT/'data'/f'{warehouse}.duckdb'),read_only=True) as con:rows=make_cases(suite,split,con,excluded)
            all_records[split]+=rows
            target=args.out/f'{suite}.{split}.jsonl'
            payload=''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows)
            target.write_text(payload,encoding='utf8')
            counts=Counter(r['expected']['args']['metric'] for r in rows)
            assert min(counts.values())>=3 and len(counts)==66
            assert all(len({r['template_id'] for r in rows if r['expected']['args']['metric']==metric})>=2 for metric in REGISTRY)
            synonym_min=min(len({r['metric_synonym'] for r in rows if r['expected']['args']['metric']==metric}) for metric in REGISTRY)
            assert synonym_min>=2
            manifest[f'{suite}.{split}']={'n':len(rows),'noise':sum(bool(set(r['tags'])&{'noaccent','colloquial','abbreviation','typo','ordinal'}) for r in rows),
                                         'metric_min':min(counts.values()),'metric_count':len(counts),'sha256':hashlib.sha256(payload.encode()).hexdigest(),
                                         'metric_distribution':dict(counts),'difficulty_distribution':dict(Counter(r['difficulty'] for r in rows)),
                                         'synonym_min':synonym_min,'noise_distribution':dict(Counter(t for r in rows for t in r['tags'] if t in {'noaccent','colloquial','abbreviation','typo','ordinal'})),
                                         'oracle_coverage':1.0,'warehouse_seed':seed}
    assert_disjoint(all_records)
    template_catalog=[{'id':f'{suite}.{metric}.{split}.form{i}','metric':metric,'split':split,'text':form}
                      for suite in ('e1','e2') for metric in REGISTRY for split,forms in FORMS.items() for i,form in enumerate(forms)]
    templates=Path(__file__).parent/'templates';templates.mkdir(exist_ok=True)
    (templates/'metrics.yaml').write_text(json.dumps(template_catalog,ensure_ascii=False,indent=2),encoding='utf8')
    manifest={'report_notice':'formulas not accountant-approved','G0_7':'OPEN / CHƯA ĐẠT','corpus_version':'p2-language-v2','tuning_questions_excluded':initial,
              'template_disjoint':True,'normalized_questions_disjoint':True,'datasets':manifest}
    (args.out/'manifest_e1_e2.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    (ROOT/'docs/5_handoff/measurements/t2_1_datasets_v2.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(manifest,ensure_ascii=False))


if __name__=='__main__':main()
