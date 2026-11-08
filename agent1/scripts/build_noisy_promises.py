"""Sinh lời hứa nhiễu với dòng RNG riêng; đối chiếu toàn bộ bảng tài chính với src."""
from pathlib import Path
import sys
import json
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.synth.world import WorldConfig,generate
from agent1.paths import SYNTH,OUT


def main():
    cfg=json.loads((SYNTH/'src/config.json').read_text(encoding='utf-8'))
    cfg.update(name='src_noisy_promises',promises_mode='noisy',write_xml=0)
    directory=SYNTH/cfg['name']
    if not (directory/'config.json').exists():generate(WorldConfig(**cfg))
    rows=[]
    for table in ['invoices','payments','bank_txns','outflows','daily_cash','firms','customers','macro','events']:
        a=pd.read_parquet(SYNTH/'src'/f'{table}.parquet');b=pd.read_parquet(directory/f'{table}.parquet')
        try:pd.testing.assert_frame_equal(a,b);same=True
        except AssertionError:same=False
        rows.append(dict(table=table,unchanged=same,n_rows=len(b)))
    output=OUT/'data';output.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(output/'noisy_promise_coupling.csv',index=False)
    if not all(r['unchanged'] for r in rows):raise ValueError('Bảng tài chính đổi; không được coi đây là ablation chỉ lời hứa')


if __name__=='__main__':main()
