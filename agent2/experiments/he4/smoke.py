"""Actual FHE smoke test. Run with the isolated Linux Concrete environment."""
import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np
from concrete import fhe

from . import circuits


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    started=time.monotonic()
    compiler=fhe.Compiler(circuits.robust_z,{'z':'encrypted'})
    samples=[np.array([a,b]) for a in (-16383,-10240,-1,0,1,10240,16383)
             for b in (-16383,-10240,-1,0,1,10240,16383)]
    circuit=compiler.compile(samples)
    circuit.keygen()
    result={'profile':'he4-robust-z-2/0.1','simulation':False,'checks':[]}
    for plain in ([-16383,1],[-10241,10240],[0,0],[123,-456]):
        value=np.array(plain,dtype=np.int64)
        # Explicit server boundary: only ciphertext and public evaluation keys.
        encrypted=circuit.client.encrypt(value)
        public=fhe.EvaluationKeys.deserialize(circuit.client.evaluation_keys.serialize())
        cipher=fhe.Value.deserialize(encrypted.serialize())
        answer=circuit.server.run(cipher,evaluation_keys=public)
        got=int(circuit.client.decrypt(fhe.Value.deserialize(answer.serialize())))
        expected=int(circuits.robust_z(value))
        if got!=expected:raise RuntimeError(f'FHE mismatch: {got} != {expected}')
        result['checks'].append({'input':plain,'expected':expected,'actual':got})
    result['seconds']=time.monotonic()-started
    result['evaluation_key_bytes']=len(circuit.client.evaluation_keys.serialize())
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
