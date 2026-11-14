"""Training-only missing-data policies. Never mutate source values or refit at score."""
import math
import numpy as np

VERSION = 'frozen-feature-preprocess/1.0.0'
POLICIES = ('strict', 'median_flags')


def fit_preprocess(frame, selected_columns, policy):
    if policy not in POLICIES:
        raise ValueError('Unknown missing policy')
    selected = list(selected_columns)
    indexes = [frame['contract']['columns'].index(c) for c in selected]
    kept, dropped, medians = [], {}, {}
    for column, index in zip(selected, indexes):
        observed = [row[index] for row in frame['features'] if row[index] is not None]
        if policy == 'strict':
            if len(observed) != len(frame['rows']):
                raise ValueError('Training features missing under strict policy: '+column)
            kept.append(column)
        elif not observed:
            dropped[column] = 'no_observed_training_values'
        else:
            kept.append(column); medians[column] = float(np.median(observed))
    if not kept:
        raise ValueError('No observed training features')
    output = kept if policy == 'strict' else ['value:'+c for c in kept]+['missing:'+c for c in kept]
    result = dict(version=VERSION, policy=policy, selected_columns=selected,
                  kept_columns=kept, dropped_columns=dropped, medians=medians, output_columns=output)
    # No rows are silently removed from training or calibration.
    transform_frame(frame, result)
    return result


def validate_preprocess(frame, state):
    if state['version'] != VERSION or state['policy'] not in POLICIES:
        raise ValueError('Preprocess version/policy mismatch')
    selected, kept, dropped = state['selected_columns'], state['kept_columns'], state['dropped_columns']
    if not kept or len(set(selected)) != len(selected) or any(c not in frame['contract']['columns'] for c in selected):
        raise ValueError('Preprocess columns invalid')
    if kept != [c for c in selected if c not in dropped] or set(kept) & set(dropped) or set(kept) | set(dropped) != set(selected):
        raise ValueError('Preprocess selection changed')
    if state['policy'] == 'strict':
        if dropped or state['medians'] or state['output_columns'] != kept:
            raise ValueError('Strict preprocess must not impute')
    else:
        if set(state['medians']) != set(kept) or any(type(v) not in (float,int) or not math.isfinite(v) for v in state['medians'].values()):
            raise ValueError('Frozen medians invalid')
        if state['output_columns'] != ['value:'+c for c in kept]+['missing:'+c for c in kept]:
            raise ValueError('Preprocess output order changed')


def row_values(frame, values, state):
    indexes = [frame['contract']['columns'].index(c) for c in state['kept_columns']]
    raw = [values[i] for i in indexes]
    missing = [c for c,v in zip(state['kept_columns'],raw) if v is None]
    if state['policy'] == 'strict' and missing:
        return None, missing, 'features_missing'
    if len(missing) == len(raw):
        return None, missing, 'features_all_missing'
    prepared = [state['medians'][c] if v is None else v for c,v in zip(state['kept_columns'],raw)] if state['policy']=='median_flags' else raw
    if state['policy'] == 'median_flags':
        prepared += [int(v is None) for v in raw]
    return prepared, missing, None


def transform_frame(frame, state):
    validate_preprocess(frame, state)
    values = []
    for row in frame['features']:
        prepared, _, reason = row_values(frame, row, state)
        if reason:
            raise ValueError('History/reference row unavailable under missing policy: '+reason)
        values.append(prepared)
    if not values:
        raise ValueError('Empty history/reference')
    return np.asarray(values, dtype=float)
