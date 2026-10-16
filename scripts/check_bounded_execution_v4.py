"""Verify bounded execution against the registered P3 development result."""
import gc
import json
from pathlib import Path

import numpy as np

from agent2 import eval_v4
from agent2.sealed_v4 import compact_integer_storage, development_pool, run_bounded


def main():
    train, valid = development_pool([Path('work/data/w4_s411'), Path('work/data/w4_s412')], compact=True)
    target = compact_integer_storage(eval_v4.prepare(Path('work/data/w4_s413')))
    tr, va, te = (target[target.split == split].copy() for split in ('train', 'validation', 'test'))
    del target
    gc.collect()
    eval_v4.WORKERS = 3
    scores, reference, _ = run_bounded(train, valid, te, 1, history=[tr, va], ref_for_novelty=va)
    test = te.reset_index(drop=True)
    alerts, fused = eval_v4.alerts_for(test, scores, reference)
    actual = eval_v4.summarise(test, alerts, fused)
    expected = json.loads(Path('results/v4/method_study/w4_s413.json').read_text(encoding='utf-8'))['P3']
    checked = 0
    def compare(left, right):
        nonlocal checked
        assert set(left) == set(right)
        for key in left:
            if isinstance(left[key], dict):
                compare(left[key], right[key])
            else:
                np.testing.assert_allclose(left[key], right[key], rtol=0, atol=0, equal_nan=True)
                checked += 1
    compare(actual, expected)
    result = {'status': 'passed', 'target': 'w4_s413', 'protocol': 'P3', 'configurations': len(actual),
              'metrics_checked_exactly': checked, 'maximum_metric_difference': 0,
              'reference_max_concurrent_candidates': 3, 'bounded_max_concurrent_candidates': 1,
              'training_worlds': ['w4_s411', 'w4_s412'], 'parameters_or_features_changed': False, 'lossless_integer_compaction': True}
    result['integer_storage'] = {name: {'equivalent_int64_bytes': sum(len(frame) * 8 for col in frame.select_dtypes('integer')),
                                      'actual_bytes': sum(frame[col].to_numpy().nbytes for col in frame.select_dtypes('integer'))}
                                 for name, frame in [('training', train), ('validation', valid), ('test', test)]}
    Path('results/v4/bounded_execution_regression.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
