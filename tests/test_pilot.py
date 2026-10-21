import pandas as pd
from pilot.analysis import difference_in_differences


def test_did_removes_shared_time_change():
    rows=[]
    for i in range(6):
        treated=i<3
        rows.extend([dict(firm_id=str(i),treated=treated,period='pre',metric=10+i),
                     dict(firm_id=str(i),treated=treated,period='post',metric=10+i+3-(2 if treated else 0))])
    result=difference_in_differences(pd.DataFrame(rows),'metric')
    assert result['DiD']==-2 and result['ci_low']==-2 and result['ci_high']==-2
    assert result['meets_six_firm_design'] and not result['causal_claim']
