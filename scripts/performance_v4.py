"""Measure synthetic 100k-row single-company weekly scoring on at most four CPUs."""
import os
for variable in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[variable] = '4'

import ctypes
import json
from pathlib import Path
import sys
import time


def cpu_limit():
    if sys.platform == 'win32':
        from ctypes import wintypes
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        process = kernel.GetCurrentProcess()
        kernel.GetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
        kernel.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
        allowed, system = ctypes.c_size_t(), ctypes.c_size_t()
        if not kernel.GetProcessAffinityMask(process, ctypes.byref(allowed), ctypes.byref(system)):
            raise ctypes.WinError()
        selected = [i for i in range(64) if allowed.value & (1 << i)][:4]
        mask = sum(1 << i for i in selected)
        if not kernel.SetProcessAffinityMask(process, mask):
            raise ctypes.WinError()
        return selected
    selected = sorted(os.sched_getaffinity(0))[:4]
    os.sched_setaffinity(0, selected)
    return selected


def main():
    cpus = cpu_limit()
    from agent2.pipeline_v4 import run
    from agent2.sealed_v4 import release_feature_caches, wait_for_memory
    from agent2.validate_v4 import validate_v4
    from agent2.world_v4 import generate_v4
    root = Path('work/performance_v4')
    root.mkdir(exist_ok=False)
    wait_for_memory(4)
    began = time.perf_counter()
    generate_v4(root / 'single_100k', n=100_000, rate=.004, seed=1481, companies=1)
    generation_seconds = time.perf_counter() - began
    began = time.perf_counter()
    validation = validate_v4(root / 'single_100k', run_shortcut=False)
    validation_seconds = time.perf_counter() - began
    release_feature_caches()
    config = json.loads(Path('configs/agent2_default.json').read_text(encoding='utf-8'))
    config['model_path'] = str(Path('models/pretrained_v2.joblib').resolve())
    config['input_data_kind'] = 'synthetic_performance_fixture'
    config_path = root / 'config.json'
    config_path.write_text(json.dumps(config, indent=2), encoding='utf-8')
    wait_for_memory(4)
    began = time.perf_counter()
    report, _ = run(root / 'single_100k', root / 'precision', config_path, '2025-W52', 'C001')
    seconds = time.perf_counter() - began
    result = {'data_kind': 'synthetic', 'source_rows': validation['rows'], 'companies': 1,
              'cpu_affinity_logical_ids': cpus, 'logical_cpus_used_at_most': len(cpus),
              'generation_seconds': generation_seconds, 'validation_seconds': validation_seconds,
              'weekly_scoring_seconds': seconds, 'target_seconds': 300, 'target_passed': seconds < 300,
              'rows_observed_history': report['rows_history'], 'rows_scored_week': report['rows_scored'],
              'timing_seconds': report['timing_seconds'], 'accuracy_measured': False,
              'limitations': ['single synthetic company; concurrent host workloads are uncontrolled',
                              'four logical CPUs, not a claim about four physical cores',
                              '200k and 1m full-workload benchmarks remain separate tasks']}
    Path('results/v4/performance_100k.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
