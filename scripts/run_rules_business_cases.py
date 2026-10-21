"""Xuất hồi quy tình huống độc lập với giá trị đọc từ registry hiện hành."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import ROOT,OUT
from agent1.rules.regression_cases import cases,calculate,coverage


def main():
    rows=[]
    for case in cases():
        actual=calculate(case);expected=case['expected']
        passed=actual==expected if isinstance(expected,str) else bool(np.isclose(actual,expected,rtol=0,atol=1e-6))
        rows.append(dict(**{k:v for k,v in case.items() if k!='arguments'},
            arguments=json.dumps(case['arguments']),actual=actual,passed=passed,
            expert_verified=False,measurement_version='configured-rules-business-regression-v1'))
    directory=OUT/'rules';directory.mkdir(exist_ok=True)
    frame=pd.DataFrame(rows);counts=coverage()
    frame.to_csv(directory/'business_cases.csv',index=False)
    pd.DataFrame([dict(rule=rule,n_cases=n) for rule,n in counts.items()]).to_csv(directory/'business_case_coverage.csv',index=False)
    sources=['agent1/rules/regression_cases.py','agent1/rules/rules_history.json','agent1/rules/provisioning.py',
        'agent1/rules/__init__.py','agent1/calendar_vn.py','scripts/run_rules_business_cases.py']
    protocol=dict(complete=bool(frame.passed.all()),n_cases=len(frame),n_rule_versions=len(counts),
        minimum_cases_per_rule=min(counts.values()),expert_verified=False,
        scope='historical configured arithmetic/calendar regression; not legal-source or current-law verification',
        source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources})
    (directory/'business_case_protocol.json').write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    print(f'{int(frame.passed.sum())}/{len(frame)} business cases; {len(counts)} configured rule versions')
    if not protocol['complete']:raise ValueError('Hồi quy nghiệp vụ không khớp')


if __name__=='__main__':main()
