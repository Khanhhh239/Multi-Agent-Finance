"""Only TRAIN files can feed the production few-shot bank."""
import json
from pathlib import Path
from agent4.engine.metrics import REGISTRY


def build_train_bank(root):
    bank=[]
    for suite in ('e1','e2','e3','e4','e5'):
        path=root/'eval/data'/f'{suite}.train.jsonl'
        if not path.exists():continue
        for line in path.read_text(encoding='utf8').splitlines():
            row=json.loads(line)
            if row['split']!='train' or row['warehouse_seed']!=20251:raise ValueError('TRAIN provenance violated')
            if row.get('expected_behavior')=='clarify':
                answer={'action':'ask_clarification','question':'Bạn muốn xem chỉ số nào?',
                        'options':[{'label':REGISTRY[m].label,'patch':{'metric':m}} for m in row['must_offer'][:3]]}
            elif row.get('expected_behavior')=='refuse':
                answer={'action':'refuse','reason':'unsafe_action' if row['reason'] in ('delete','update','pay','sql_write','false_approval','exfiltrate') else 'out_of_scope',
                        'message':'Yêu cầu ngoài phạm vi hoặc không được phép.'}
            else:answer={'action':row['expected']['tool'],**row['expected']['args']}
            bank.append({'question':row['question'],'answer':answer,'split':'train','warehouse_seed':20251,
                         'template_id':row['template_id'],'label_source':row['label_source']})
    target=root/'agent4/agent/data/fewshot_train.jsonl'
    target.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in bank),encoding='utf8')
    return len(bank)
