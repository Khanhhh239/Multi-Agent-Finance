"""Verifier error injection and authored slot-carry conversations."""
import json,re,hashlib
from pathlib import Path
import duckdb
from agent4.engine.engine import ExecutionEngine
from agent4.engine.metrics import REGISTRY
from agent4.engine.formatting import fmt_vnd
from agent4.agent.constants import NOTICE
from agent4.agent.render import render_facts
from agent4.agent.trace import public_data
from .build_e1_e2 import ROOT,SPLITS,expected_value

KINDS=['digit_swap','scale_swap','period_swap','add_number','drop_caveat','sign_flip','swap_two','faithful']


def mutate_answer(block,source,other,kind,index=0):
    text=block.text;display=source['display']
    if kind=='digit_swap':
        changed=re.sub(r'\d',lambda m:str((int(m[0])+5)%10),display,count=1)
        return text.replace(display,changed,1)
    if kind=='scale_swap':
        if source['unit']=='VND':
            changed=display.replace('tỷ','triệu') if 'tỷ' in display else display.replace('triệu','tỷ') if 'triệu' in display else display.replace('đồng','tỷ đồng')
        else:changed=re.search(r'[-−+]?\d[\d.,]*',display)[0]+' tỷ đồng'
        return text.replace(display,changed,1)
    if kind=='period_swap':return text.replace(source['period_label'],'tháng 01/2039',1)
    if kind=='add_number':return text+' Ngoài ra có 987654321,123 tỷ đồng.'
    if kind=='drop_caveat':return text.replace(NOTICE,'').replace(source['data_status'],'')
    if kind=='sign_flip':return text.replace(display,display[1:] if display.startswith(('-','−')) else '-'+display,1)
    if kind=='swap_two':return text.replace(display,other['display'],1)
    if kind=='faithful':
        if source['unit']=='VND' and index%2:return text.replace(display,fmt_vnd(source['value'],exact=True),1)
        return 'Theo sổ sách được cung cấp:\n'+text
    raise ValueError(kind)


def e6(split,engine):
    sizes={'train':400,'val':100,'test':300};rows=[]
    source_rows=[json.loads(l) for l in (ROOT/'eval/data'/f'e2.{split}.jsonl').read_text(encoding='utf8').splitlines()]
    for i in range(sizes[split]):
        kind=KINDS[i%8];offset=0
        while True:
            call=source_rows[(i+offset)%len(source_rows)]['expected']['args']
            source=engine.query(**call)
            if source.get('value') and source.get('display'):break
            offset+=1
            if offset>len(source_rows):raise ValueError('No nonzero mutation fixture')
        other=engine.query('cash_and_equivalents' if source['metric_id']!='cash_and_equivalents' else 'net_revenue',call['period'])
        if other['display']==source['display']:other=engine.query('cogs','2026-Q2')
        block=render_facts([source,other],question='')
        answer=mutate_answer(block,source,other,kind,i)
        assert answer!=block.text
        rows.append({'id':f'e6.{split}.{i:04}','split':split,'template_id':f'e6.{split}.{kind}',
                     'capability':'faithfulness','difficulty':'hard','tags':[kind],
                     'question':f'Verifier fixture {split}/{i}', 'as_of':'2026-10-14',
                     'tool_results':public_data([source,other]),'answer':answer,'mutation':kind,
                     'expected_faithful':kind=='faithful','label_source':'deterministic_mutation_of_engine_fixture'})
    return rows


FIRST={
 'train':'Tôi muốn xem {metric} trong {period}, hồ sơ {n}.',
 'val':'Nhờ mở số liệu {metric} ứng với {period}, hồ sơ {n}.',
 'test':'Hồ sơ {n} cần kết quả {metric} thuộc {period}.',
}
FOLLOW={
 'train':['Còn kỳ {period} thì sao?','Vậy cũng chỉ số ấy trong {period}.','Chia theo chi nhánh cho kỳ đó.',
          'Giữ chỉ số này nhưng lấy {period}.','Không, tôi đang nói tới {period}.','Trong kỳ đó, phân theo chi nhánh.',
          'Kỳ ấy chia theo từng chi nhánh nhé.','Cùng khung này, chuyển về {period}.','Theo từng chi nhánh cho số vừa hỏi.',
          'Đổi sang {metric} cho {period}.'],
 'val':['Kỳ {period} của chỉ số vừa hỏi thì thế nào?','Số đang xem, thay kỳ bằng {period}.','Với số trước, lập bảng từng chi nhánh.',
        'Chỉ tiêu vừa nêu chuyển sang {period}.','Ý tôi cần sửa kỳ thành {period}.','Đối với kỳ đang xem, nhóm theo chi nhánh.',
        'Đưa kết quả kỳ ấy vào từng chi nhánh.','Dùng khung vừa chọn và kỳ {period}.','Từ số vừa tra, tách chi nhánh giúp.',
        'Thay chủ đề bằng {metric} trong {period}.'],
 'test':['Hãy áp dụng {period} cho phép tra vừa rồi.','Mục vừa báo cần kỳ {period} thay thế.','Tách số đang nói thành các chi nhánh.',
         'Vẫn mục đó, tôi cần {period}.','Tôi đính chính mốc thời gian: {period}.','Giữ kỳ hiện dùng, phân rã từng chi nhánh.',
         'Kết quả của kỳ đang dùng cần bảng chi nhánh.','Không đổi khung sổ, dùng {period}.','Phân bổ phần vừa trả theo các chi nhánh.',
         'Bây giờ yêu cầu {metric}, thời gian {period}.'],
}


def e7(split,con):
    metrics=['net_revenue','cogs','gross_profit','net_profit','operating_profit','operating_expenses','salary_expense','labor_cost','profit_before_tax','gross_margin_pct']
    tokens=['this_month','last_month','last_quarter','2026-Q2'];phrases=['tháng này','tháng trước','quý trước','quý 2/2026']
    rows=[]
    for i in range({'train':80,'val':30,'test':80}[split]):
        metric=metrics[i%10];period=tokens[(i//10)%4];phrase=phrases[(i//10)%4]
        call={'metric':metric,'period':period,'view':'mgmt'}
        turns=[{'user':FIRST[split].format(metric=REGISTRY[metric].label,period=phrase,n=i+1),
                'expected':{'tool':'query_metric','args':dict(call)},'gold':expected_value(con,call)}]
        for t in range(1,2+i%4):
            kind=(i+t-1)%10
            if kind not in (2,5,6,8):call['period']='last_quarter' if t%2 else 'last_month'
            else:call['group_by']='branch'
            if kind==9:call['metric']=metrics[(i+1)%10];call.pop('group_by',None)
            text=FOLLOW[split][kind].format(period='quý trước' if call['period']=='last_quarter' else 'tháng trước',metric=REGISTRY[call['metric']].label)
            turns.append({'user':text,'reference_type':kind,'expected':{'tool':'query_metric','args':dict(call)},'gold':expected_value(con,call)})
        rows.append({'id':f'e7.{split}.{i:03}','split':split,'template_id':f'e7.{split}.sequence{i%10}',
                     'capability':'multiturn','difficulty':'hard','tags':['carryover'],
                     'question':' / '.join(t['user'] for t in turns),'turns':turns,'as_of':'2026-10-14',
                     'warehouse_seed':SPLITS[split][0],'label_source':'authored_slots+independent_oracle'})
    return rows


def main():
    out=ROOT/'eval/data';target=out/'manifest_e6_e7.json'
    if target.exists():raise SystemExit('E6/E7 frozen')
    manifest={}
    for split,(_,warehouse,_) in SPLITS.items():
        with ExecutionEngine(ROOT/'data'/f'{warehouse}.duckdb') as engine,duckdb.connect(str(ROOT/'data'/f'{warehouse}.duckdb'),read_only=True) as con:
            for suite,rows in [('e6',e6(split,engine)),('e7',e7(split,con))]:
                payload=''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows)
                (out/f'{suite}.{split}.jsonl').write_text(payload,encoding='utf8')
                manifest[f'{suite}.{split}']={'n':len(rows),'sha256':hashlib.sha256(payload.encode()).hexdigest()}
    report={'report_notice':'formulas not accountant-approved','G0_7':'OPEN / CHƯA ĐẠT','datasets':manifest,
            'E6_note':'Engine fixtures are permitted for verifier mutation labels, never used as E1/E2 gold values.'}
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    (ROOT/'docs/5_handoff/measurements/t2_3_datasets.json').write_text(target.read_text(encoding='utf8'),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
