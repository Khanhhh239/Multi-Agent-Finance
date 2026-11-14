"""Compile operator-owned public FHE circuits; no tenant input or secret keys."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from concrete import fhe
from . import circuits as c


def samples(profile):
    rng=np.random.default_rng(20261112)
    if profile=='statistics':
        return [np.array([a,b]) for a in (-16383,-10240,-1,0,1,10240,16383) for b in (-16383,-10240,-1,0,1,10240,16383)]
    if profile=='rules':
        rows=[]
        for _ in range(32):
            arrays=[rng.integers(0,16,(4,c.WORD_DIGITS),dtype=np.int64) for _ in range(3)]
            rows.append((*arrays,rng.integers(0,2,4),rng.integers(0,16,c.WORD_DIGITS),int(rng.integers(0,2))))
        rows.extend((*(np.full((4,c.WORD_DIGITS),v,dtype=np.int64) for _ in range(3)),np.full(4,k),np.full(c.WORD_DIGITS,v),k) for v in (0,15) for k in (0,1))
        return rows
    rows=[]
    for _ in range(16):
        tokens=rng.integers(0,16,(4,4,c.TOKEN_DIGITS),dtype=np.int64)
        known=rng.integers(0,2,(4,4),dtype=np.int64);active=rng.integers(0,2,4,dtype=np.int64)
        rows.append((tokens,known,active))
    rows.extend((np.full((4,4,c.TOKEN_DIGITS),v,dtype=np.int64),np.full((4,4),k,dtype=np.int64),np.full(4,k,dtype=np.int64)) for v in (0,15) for k in (0,1))
    return rows


def build(profile,output):
    if output.exists():raise ValueError('use a new immutable build directory')
    output.mkdir(parents=True)
    c.ARRAY=fhe.array
    function,fields={'rules':(c.p1,['prior','current','caps','kinds','tolerance','group_mode']),
                     'statistics':(c.robust_z,['z']),
                     'graph':(c.graph,['tokens','known','active'])}[profile]
    started=time.monotonic()
    compiler=fhe.Compiler(function,{name:'encrypted' for name in fields})
    circuit=compiler.compile(samples(profile),global_p_error=1e-9)
    from .native_check import inputs
    for values in inputs(profile):
        c.ARRAY=np.array
        expected=function(*values)
        c.ARRAY=fhe.array
        actual=circuit.simulate(*values)
        if not np.array_equal(actual,expected):raise ValueError('compiled circuit differs from reference')
    circuit.server.save(output/'server.zip')
    specs=circuit.client.specs.serialize()
    (output/'client.specs.json').write_bytes(specs if isinstance(specs,bytes) else specs.encode('utf-8'))
    manifest=dict(version='he4-circuit-build/0.1.0',profile=profile,concrete_version='2.11.0',
        seconds=time.monotonic()-started,source_sha256=hashlib.sha256(Path(c.__file__).read_bytes()).hexdigest(),
        files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()},
        scope=dict(money_source='signed int64; sums signed128',max_rows_per_sum=4,graph_nodes=4,statistics_columns=2,statistics_quantum=1024),
        all_inputs_encrypted=True,contains_secret_keys=False)
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--profile',choices=['rules','statistics','graph'],required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.profile,a.output)
