"""200 ca cảnh báo bằng mẫu; không thay cho đánh giá tự nhiên bởi ba người."""
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.text.verbalize import verbalize,check_numbers
from agent1.paths import OUT


def main():
    rows=[]
    for i in range(200):
        table={'week':i%13+1,'balance_text':str((i-100)*1000000),'risk_text':f'{i%101}%'}
        text=verbalize(table)
        rows.append(dict(case=i,text=text,number_gate_pass=check_numbers(text,table),generator='template',human_naturalness_review=False))
    directory=OUT/'service';directory.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(directory/'alert_number_gate.csv',index=False)
    pd.DataFrame([dict(cases=len(rows),passed=sum(r['number_gate_pass'] for r in rows),
                      failed=sum(not r['number_gate_pass'] for r in rows),human_naturalness_review=False)]).to_csv(directory/'alert_gate_summary.csv',index=False)
    assert all(r['number_gate_pass'] for r in rows)


if __name__=='__main__':main()
