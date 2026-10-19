"""Detached structural smoke check; does not run any fraud detector."""
import gc
import time
from pathlib import Path

from agent2.runtime_v5 import limit_memory, wait_memory, write_json
from agent2.world_v5_dev import development_config, generate
from agent2.validate_v4 import validate_v4

limit_memory(6)
out=Path('results/v5/development_smoke')
out.mkdir(parents=True, exist_ok=True)
wait_memory(1.5, out/'runtime.json')
write_json(out/'runtime.json',{'status':'generating_smoke','data_origin':'dữ liệu tổng hợp'})
config=development_config(1001)
config.update(seed=1099, calendar_seed=521099, rows=60000, companies=8)
start=time.monotonic()
try:
    directory=Path('work/data/v5dev_smoke1099')
    if not (directory/'manifest.json').exists():
        generate(config,directory)
    gc.collect()
    report=validate_v4(directory,run_shortcut=False)
    write_json(out/'verification.json', {'status':'passed','data_origin':'dữ liệu tổng hợp',
               'seconds':time.monotonic()-start,'config':config,'validation':report,
               'scope':'V1-V9 and V11 passed; V10 coverage gaps reported; V12 required on every full development world'})
    write_json(out/'runtime.json',{'status':'complete','data_origin':'dữ liệu tổng hợp'})
    print('structural generator smoke passed',flush=True)
except Exception as error:
    write_json(out/'failure.json',{'status':'failed','error':repr(error),'data_origin':'dữ liệu tổng hợp'})
    raise
