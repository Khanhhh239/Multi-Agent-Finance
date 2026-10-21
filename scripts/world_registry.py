"""Đăng ký cấu hình/hash của dữ liệu hiện có, không sinh/mở miền tgt2 cuối cùng."""
import hashlib
import json
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent1.paths import SYNTH,ROOT
from agent1.data.contracts import validate_world


def main():
    rows=[]
    for path in sorted(SYNTH.glob('*/config.json')):
        cfg=json.loads(path.read_text(encoding='utf-8'))
        files=sorted(path.parent.glob('*.parquet'))
        digest=hashlib.sha256()
        for f in files:digest.update(hashlib.sha256(f.read_bytes()).digest())
        checks=validate_world(path.parent,raise_on_error=False)
        name=path.parent.name
        purpose='held_out' if name=='tgt' else 'stress' if name.startswith('hc_') else 'training_randomized' if name.startswith('dr_') else 'source_or_sensitivity'
        rows.append(dict(name=name,seed=cfg['seed'],config_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            tables_sha256=digest.hexdigest(),purpose=purpose,n_firms=cfg['n_firms'],
            all_contracts_pass=bool(checks.passed.all()),smoke=('smoke' in name)))
    pd.DataFrame(rows).to_csv(ROOT/'docs/02_Data/worlds_registry.csv',index=False)


if __name__=='__main__':main()
