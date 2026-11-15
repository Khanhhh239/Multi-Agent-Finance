"""Compile a public fixed training program, without customer data or keys."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from concrete import fhe
from . import VERSION, TARGET, PROFILE
from . import circuit as c


def build(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    values = c.samples()
    expected = [c.oracle(*v) for v in values]
    c.configure_fhe()
    started = time.monotonic()
    compiled = fhe.Compiler(c.update, {'x': 'encrypted', 'y': 'encrypted', 'weights': 'encrypted'}).compile(values, global_p_error=1e-9, composable=True)
    for v, wanted in zip(values, expected):
        if not np.array_equal(compiled.simulate(*v), wanted):
            raise ValueError('training simulation differs from scalar oracle')
    compiled.server.save(output / 'server.zip')
    specs = compiled.client.specs.serialize()
    (output / 'client.specs.json').write_bytes(specs if isinstance(specs, bytes) else specs.encode())
    manifest = dict(version=VERSION, profile=PROFILE, target=TARGET, rows=4, features=2,
        feature_scale=1, weight_scale=2, bias_scale=2, probability_scale=4,
        input_domain=[-1,1], weight_domain=[-2,2], bias_domain=[-4,4],
        learning_rate=1, batch_size=4, max_steps=4, all_inputs_encrypted=True, composable=True,
        secret_keys_in_bundle=False, concrete_version='2.11.0', seconds=time.monotonic()-started,
        source_sha256=hashlib.sha256(Path(c.__file__).read_bytes()).hexdigest(),
        files={name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in ('server.zip','client.specs.json')})
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='compiled',seconds=manifest['seconds'],simulation_cases=len(values))),flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.output)
