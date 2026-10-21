"""Huấn luyện/chấm lại DR từ snapshot đã kiểm hash, đối chiếu CSV và nguồn."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    directory=ROOT/'outputs/t1/DR'
    protocol=json.loads((directory/'protocol.json').read_text(encoding='utf-8'))
    if not protocol.get('complete'):raise ValueError('Cần lượt DR đầy đủ trước khi đối chiếu')
    paths=[directory/name for name in ['metrics.csv','decisions.csv']]
    before={p.name:digest(p) for p in paths}
    manifest=ROOT/'data/synthetic/dr_comparison_v1/manifest.json'
    input_sha=digest(manifest)
    with (ROOT/'outputs/implementation/DR-repeat.log').open('w',encoding='utf-8') as log:
        subprocess.run([sys.executable,'-u',str(ROOT/'scripts/run_dr_comparison.py')],
            cwd=ROOT,check=True,stdout=log,stderr=subprocess.STDOUT)
    current=json.loads((directory/'protocol.json').read_text(encoding='utf-8'))
    after={p.name:digest(p) for p in paths}
    same_source=input_sha==digest(manifest) and current['code_sha256']==protocol['code_sha256']
    result=dict(passed=before==after and same_source and current.get('complete',False),
        same_source=same_source,before_sha256=before,after_sha256=after,
        checked_at_utc=datetime.now(timezone.utc).isoformat(),
        scope='DR model refitting and all four target scores from prepared snapshots; not regeneration or independent source seeds')
    (directory/'reproducibility.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('DR refit repeat',result['passed'])
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
