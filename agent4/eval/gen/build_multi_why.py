"""Separate authored multi-metric and causal-premise evaluation, <=3 calls."""
import json
import duckdb
from agent4.engine.metrics import REGISTRY
from .build_e1_e2 import ROOT,SPLITS,expected_value
from .prepare import save_dataset
from .split import assert_disjoint


def main():
    out=ROOT/'eval/data';target=out/'manifest_multi_why.json'
    if target.exists():raise SystemExit('Multi/why frozen')
    manifest={}
    groups=[['net_revenue','cogs','gross_profit'],['net_profit','net_revenue'],['ar_balance','ap_balance','cash_and_equivalents'],
            ['salary_expense','labor_cost'],['total_assets','total_liabilities','equity']]
    periods=['this_month','last_month','last_quarter','2026-Q2'];phrases=['tháng này','tháng trước','quý trước','quý 2/2026']
    for split,(_,warehouse,_) in SPLITS.items():
        with duckdb.connect(str(ROOT/'data'/f'{warehouse}.duckdb'),read_only=True) as con:
            for suite,count in [('multi',{'train':60,'val':20,'test':40}[split]),('why',{'train':30,'val':20,'test':30}[split])]:
                rows=[]
                for i in range(count):
                    token=periods[(i//5)%4];period=phrases[(i//5)%4]
                    metrics=groups[i%5] if suite=='multi' else [['net_revenue'],['gross_profit'],['net_profit'],['operating_profit'],['gross_margin_pct']][i%5]
                    calls=[{'metric':m,'period':token,'view':'mgmt',**({'compare_to':'previous_period'} if suite=='why' else {})} for m in metrics]
                    name=', '.join(REGISTRY[m].label for m in metrics)
                    if suite=='multi':q={'train':'Đối chiếu {name} trong {period}, hồ sơ {n}.','val':'Cho đồng thời số {name} ứng với {period}, hồ sơ {n}.','test':'Với hồ sơ {n} của {period}, tôi cần các chỉ số {name}.'}[split].format(name=name,period=period,n=i+1)
                    else:q={'train':'Vì sao {name} trong {period} giảm, hồ sơ {n}?','val':'Tại sao mức {name} của {period} đi xuống, hồ sơ {n}?','test':'Hồ sơ {n}: why {name} lại giảm vào {period}?'}[split].format(name=name,period=period,n=i+1)
                    rows.append({'id':f'{suite}.{split}.{i:03}','split':split,'template_id':f'{suite}.{split}.form{i%5}',
                                 'question':q,'capability':suite,'difficulty':'hard','tags':[suite],
                                 'expected_calls':calls,'gold_values':[expected_value(con,c) for c in calls],
                                 'expected_behavior':'answer','requires_causal_caveat':suite=='why',
                                 'label_source':'authored_slots+independent_oracle','warehouse_seed':SPLITS[split][0]})
                manifest[f'{suite}.{split}']=save_dataset(out,f'{suite}.{split}',rows)
    records={s:[] for s in SPLITS}
    for split in records:
        for path in out.glob(f'*.{split}.jsonl'):records[split]+=[json.loads(l) for l in path.read_text(encoding='utf8').splitlines()]
    assert_disjoint(records)
    report={'report_notice':'formulas not accountant-approved','G0_7':'OPEN / CHƯA ĐẠT','datasets':manifest,
            'why_note':'The question premise may be false; judge comparison and evidence limits, not fabricated causal explanations.'}
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    (ROOT/'docs/5_handoff/measurements/t2_5a_datasets.json').write_text(target.read_text(encoding='utf8'),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
