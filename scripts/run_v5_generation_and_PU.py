"""Detached sequential controller; stops after locking PU, before new features."""
from pathlib import Path
import json
import subprocess
import sys
import time

from agent2.runtime_v5 import write_json

state=Path('results/v5/r2_controller.json')
smoke=Path('results/v5/development_smoke/verification.json')
failure=Path('results/v5/development_smoke/failure.json')
while not smoke.exists():
    if failure.exists():
        write_json(state,{'status':'stopped_on_smoke_failure','failure':str(failure),'data_origin':'dữ liệu tổng hợp'})
        raise SystemExit(1)
    write_json(state,{'status':'waiting_for_generator_smoke','data_origin':'dữ liệu tổng hợp'})
    time.sleep(30)
if json.loads(smoke.read_text(encoding='utf-8'))['status']!='passed':
    raise SystemExit('Generator smoke did not pass')
write_json(state,{'status':'running','step':'development_generation','data_origin':'dữ liệu tổng hợp'})
for seed in range(1001,1021):
    # A fresh worker releases Python arenas and native feature caches between
    # worlds. Every worker has the same six-GiB hard limit and full plan.
    completed=subprocess.run([sys.executable,'-m','agent2.world_v5_dev','--one-world',str(seed)],check=False)
    if completed.returncode:
        write_json(state,{'status':'failed','step':'development_generation','seed':seed,
                          'exit_code':completed.returncode,'data_origin':'dữ liệu tổng hợp'})
        raise SystemExit(completed.returncode)
checks=[json.loads(Path(f'results/v5/development/world_{seed}.json').read_text(encoding='utf-8'))
        for seed in range(1001,1021)]
assert all(item['status']=='validated' and all(v=='passed' for v in item['checks'].values()) for item in checks)
write_json(Path('results/v5/development/runtime.json'),{'status':'complete','worlds':20,'data_origin':'dữ liệu tổng hợp'})
for seed in range(1001,1021):
    write_json(state,{'status':'running','step':'base_feature_preparation','seed':seed,'data_origin':'dữ liệu tổng hợp'})
    completed=subprocess.run([sys.executable,'-m','agent2.base_v5','--prepare-world',str(seed)],check=False)
    if completed.returncode:
        write_json(state,{'status':'failed','step':'base_feature_preparation','seed':seed,
                          'exit_code':completed.returncode,'data_origin':'dữ liệu tổng hợp'})
        raise SystemExit(completed.returncode)
for step,arguments in [('PU_pilot',['-m','agent2.base_v5','--pilot-only']),
                       ('PU_screen',['-m','agent2.base_v5'])]:
    write_json(state,{'status':'running','step':step,'data_origin':'dữ liệu tổng hợp'})
    completed=subprocess.run([sys.executable,*arguments],check=False)
    if completed.returncode:
        write_json(state,{'status':'failed','step':step,'exit_code':completed.returncode,'data_origin':'dữ liệu tổng hợp'})
        raise SystemExit(completed.returncode)
    if step=='PU_pilot':
        assert Path('results/v5/PU_screen/runtime_estimate.json').exists()
write_json(state,{'status':'PU_phase_finished','PU_locked':Path('results/v5/PU_screen/PU_locked.json').exists(),
                  'data_origin':'dữ liệu tổng hợp','next':'implement change_detect and receivables only after inspecting PU lock'})
