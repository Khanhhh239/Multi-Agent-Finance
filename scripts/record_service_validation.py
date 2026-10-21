"""Gom bằng chứng chạy local từ kho demo mã hoá, chỉ xuất số tổng hợp."""
import argparse
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import OUT
from agent1_service.store import Store
from agent1_service.model_registry import load


def main():
    p=argparse.ArgumentParser();p.add_argument('--state',required=True);p.add_argument('--firm',required=True);args=p.parse_args()
    directory=Path(args.state);store=Store(directory/'agent1.db',(directory/'encryption.key').read_bytes())
    rows=[]
    try:
        for forecast in store.get(args.firm,'forecasts'):
            model,version=load(store,args.firm,forecast['cutoff'])
            rows.append(dict(check='stored_model_loaded_by_forecast',value=int(model is not None and version['id']==forecast.get('model_version')),
                cutoff=forecast['cutoff'],target_met=model is not None and version['id']==forecast.get('model_version')))
            rows.append(dict(check='forecast_seconds',value=forecast['seconds'],cutoff=forecast['cutoff'],target_met=forecast['seconds']<=300))
        for report in store.get(args.firm,'monitoring'):
            for row in report['coverage']:
                rows.append(dict(check='realized_coverage_single_company_demo',value=row['cov80'],cutoff=report['cutoff'],target_met=None))
        result=pd.DataFrame(rows);result['measurement_version']='service-local-synthetic-research-v1'
        result['limitation']='one_firm_demo_with_user_supplied_opening_balance;not_pilot_or_UAT_evidence'
        result.to_csv(OUT/'service/local_validation.csv',index=False)
    finally:store.connection.close()


if __name__=='__main__':main()
