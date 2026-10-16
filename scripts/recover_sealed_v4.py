"""Sequential recovery after an infrastructure-only failure, with explicit gates.

Never overwrites a sealed report or retries after metrics have been recorded.
Run only after the bounded development regression has passed.
"""
import json
from pathlib import Path
import subprocess
import sys
import argparse

ATTEMPT = ''


def state(stage, status, **extra):
    Path('work/recovery_state.json').write_text(json.dumps({'stage': stage, 'status': status, **extra}, indent=2), encoding='utf-8')


def step(stage, *arguments):
    state(stage, 'running', log=f'work/{ATTEMPT}{stage}.log', error=f'work/{ATTEMPT}{stage}.err')
    with Path(f'work/{ATTEMPT}{stage}.log').open('x', encoding='utf-8') as output, Path(f'work/{ATTEMPT}{stage}.err').open('x', encoding='utf-8') as error:
        result = subprocess.run([sys.executable, *arguments], stdout=output, stderr=error)
    if result.returncode:
        state(stage, 'failed', returncode=result.returncode)
        raise SystemExit(result.returncode)


def main():
    global ATTEMPT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', default='compact')
    args = parser.parse_args()
    if not args.attempt.isalnum():
        raise ValueError('attempt name must be alphanumeric')
    ATTEMPT = args.attempt + '_'
    regression = json.loads(Path('results/v4/bounded_execution_regression.json').read_text(encoding='utf-8'))
    assert regression['status'] == 'passed' and regression['maximum_metric_difference'] == 0 and regression.get('lossless_integer_compaction')
    if Path('work/results/sealed_v4.json').exists():
        raise FileExistsError('one-shot result already exists; recovery is forbidden')
    common = ['-m', 'agent2.sealed_v4', '--dev', 'work/data/w4_s411', 'work/data/w4_s412', 'work/data/w4_s413',
              '--frozen', 'work/results/v4_frozen.json', '--max-concurrent-candidates', '1']
    step('bounded_dryrun', *common, '--sealed', 'work/data/v4s_smoke', '--out', 'work/results/sealed_v4_bounded_dryrun.json')
    step('bounded_dryrun_verify', 'scripts/verify_dryrun_v4.py', '--report', 'work/results/sealed_v4_bounded_dryrun.json',
         '--out', 'results/v4/bounded_dryrun_verification.json')
    step('sealed_v4_bounded', *common, '--sealed', 'work/data/s4_s931', 'work/data/s4_s932', 'work/data/s4_s933',
         '--out', 'work/results/sealed_v4.json')
    step('sealed_report', 'scripts/report_sealed_v4.py')
    gates = json.loads(Path('results/v4/sealed_gates.json').read_text(encoding='utf-8'))
    if gates['global_stop_triggered']:
        step('tests_complete_v4', '-m', 'pytest', 'tests_agent2', 'tests_sme_fraud', '-q')
        state('M2', 'global_stop', reasons=gates['global_stop_reasons'])
        return
    step('train_pretrained_v4', '-m', 'agent2.train_pretrained_v4')
    step('pipeline_precision_v4', '-m', 'agent2.pipeline', '--data', 'work/data/w4_s413', '--out', 'work/results/precision_v4_C001_W40',
         '--company', 'C001', '--week', '2025-W40', '--config', 'configs/agent2_default.json')
    step('explanation_check_v4', 'scripts/check_explanations_v4.py')
    step('api_integration_v4', 'scripts/check_api_v4.py')
    step('tests_complete_v4', '-m', 'pytest', 'tests_agent2', 'tests_sme_fraud', '-q')
    state('A6_C1', 'complete', g5_passed=gates['g5_passed_macro_scenarios'])


if __name__ == '__main__':
    main()
