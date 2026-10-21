"""Đo C2ST và kiểm định marginal độc lập; không dùng kết quả để điều chỉnh tgt."""
import json
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent1.data.real_loaders import customer_invoices, uk_ppr_stats
from agent1.synth.c2st import classifier_two_sample
from agent1.synth.fidelity import report
from agent1.paths import SYNTH, OUT


def main():
    directory=OUT/'data'; directory.mkdir(exist_ok=True)
    real=customer_invoices()
    rows=[]
    for world in ('src','sens_uk','sens_coface'):
        inv=pd.read_parquet(SYNTH/world/'invoices.parquet')
        metrics, importance=classifier_two_sample(real,inv)
        rows.append(dict(world=world,**metrics,measurement_version='structural-company-split-v1'))
        importance.to_csv(directory/f'c2st_features_{world}.csv',index=False)
    pd.DataFrame(rows).to_csv(directory/'c2st.csv',index=False)
    (directory/'independent_uk_ppr.json').write_text(json.dumps(uk_ppr_stats(),indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
