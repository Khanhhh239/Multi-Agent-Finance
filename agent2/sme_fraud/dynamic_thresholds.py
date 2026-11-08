"""Causal account-level rolling distributions and monthly calendar contexts."""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import calendar
import hashlib
import json
import math
from pathlib import Path
import sys

# Match the repository's optional scientific runtime before importing NumPy.
# Loading a different NumPy first breaks later SciPy/sklearn imports.
_local_packages = Path(__file__).resolve().parents[1]/'.runtime'/'site-packages'
if _local_packages.exists() and str(_local_packages) not in sys.path:
    sys.path.insert(0, str(_local_packages))
import numpy as np


VERSION = 'rolling-account-v1'
VN = timezone(timedelta(hours=7))
METHODS = ('p95', 'p99', 'mean_std')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError('Dynamic thresholds require timezone-aware timestamps')
    return parsed.astimezone(VN).isoformat()


def integer(value, field, minimum=0):
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if type(value) is not int or not minimum <= value <= 9_000_000_000_000_000:
        raise ValueError(f'{field} requires an integer >= {minimum}')
    return value


@dataclass(frozen=True)
class ThresholdPolicy:
    window_days: int = 90
    method: str = 'p99'
    minimum_samples: int = 20
    sigma_k: float = 3.0
    cycle_enabled: bool = True
    cycle_radius_days: int = 2
    cycle_learning_days: int = 180
    minimum_cycle_months: int = 3

    def __post_init__(self):
        if type(self.window_days) is not int or self.window_days not in (30, 60, 90):
            raise ValueError('Dynamic window must be 30, 60 or 90 days')
        if self.method not in METHODS:
            raise ValueError('Dynamic method must be p95, p99 or mean_std')
        for field, low, high in (('minimum_samples', 2, 100000), ('cycle_radius_days', 0, 5),
                                 ('cycle_learning_days', 90, 730), ('minimum_cycle_months', 2, 24)):
            value = getattr(self, field)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f'Invalid dynamic {field}')
        if type(self.cycle_enabled) is not bool or type(self.sigma_k) not in (int, float) or not math.isfinite(self.sigma_k) or not 0 < self.sigma_k <= 100:
            raise ValueError('Invalid dynamic cycle flag or sigma coefficient')

    @classmethod
    def from_config(cls, config):
        return cls(window_days=config.get('dynamic_window_days', 90), method=config.get('dynamic_method', 'p99'),
                   minimum_samples=config.get('dynamic_min_samples', 20), sigma_k=config.get('dynamic_sigma_k', 3.),
                   cycle_enabled=config.get('dynamic_cycle_enabled', True),
                   cycle_radius_days=config.get('dynamic_cycle_radius_days', 2),
                   cycle_learning_days=config.get('dynamic_cycle_learning_days', 180),
                   minimum_cycle_months=config.get('dynamic_min_cycle_months', 3))

    def as_dict(self):
        return dict(version=VERSION, **self.__dict__, quantile_interpolation='linear', std_ddof=1,
                    windows=[30, 60, 90], comparison='strict_upper_tail', currency='VND')


def observation(record):
    result = {field: record.get(field, '') for field in ('observation_id', 'company_id', 'account_code',
        'measurement', 'family', 'event_at', 'source_transaction_id', 'source_ref')}
    for field in ('observation_id', 'company_id', 'account_code', 'measurement', 'family'):
        if not isinstance(result[field], str) or not result[field] or result[field] != result[field].strip():
            raise ValueError(f'Invalid dynamic observation {field}')
    if result['measurement'] not in {'expense_debit', 'cash_outflow', 'transaction_amount'}:
        raise ValueError('Unknown dynamic measurement; amounts with different meanings cannot be pooled')
    result['event_at'] = timestamp(result['event_at'])
    result['known_at'] = max(result['event_at'], timestamp(record.get('observed_at') or record.get('known_at') or result['event_at']))
    result['amount_vnd'] = integer(record['amount_vnd'], 'amount_vnd', 1)
    if record.get('currency', 'VND') != 'VND':
        raise ValueError('Dynamic thresholds require a verified VND measurement')
    event = datetime.fromisoformat(result['event_at'])
    result['_event'] = event
    result['_day'] = event.day
    result['_month'] = event.strftime('%Y-%m')
    result['_month_length'] = calendar.monthrange(event.year, event.month)[1]
    result['_end_offset'] = result['_month_length']-event.day
    return result


def key_of(record):
    return tuple(record[field] for field in ('company_id', 'account_code', 'measurement', 'family'))


class DynamicThresholds:
    def __init__(self, records, policy=None):
        self.policy = policy or ThresholdPolicy()
        unique = {}
        for raw in records:
            row = observation(raw)
            identity = row['observation_id']
            if identity in unique and unique[identity] != row:
                raise ValueError('Conflicting dynamic observation ID')
            unique[identity] = row
        self.pending = sorted(unique.values(), key=lambda r: (r['known_at'], r['event_at'], r['observation_id']))
        self.by_transaction = defaultdict(list)
        for row in self.pending:
            if row['source_transaction_id']:
                self.by_transaction[(row['company_id'], row['source_transaction_id'])].append(row)
        self.history = defaultdict(list)
        self.index, self.watermark, self.cycle_cache = 0, '', {}

    def advance(self, cutoff, *, inclusive=False):
        cutoff = timestamp(cutoff)
        if self.watermark and cutoff < self.watermark:
            raise ValueError('Dynamic stream cannot move backward; use a separate instance for historical replay')
        touched = set()
        while self.index < len(self.pending):
            row = self.pending[self.index]
            if row['known_at'] > cutoff or not inclusive and row['known_at'] == cutoff:
                break
            key = key_of(row)
            self.history[key].append(row)
            touched.add(key)
            self.index += 1
        lower = datetime.fromisoformat(cutoff[:10]+'T00:00:00+07:00')-timedelta(days=self.policy.cycle_learning_days)
        for key in touched:
            self.history[key] = [r for r in self.history[key] if r['_event'] >= lower]
        self.watermark = cutoff

    def _samples(self, key, cutoff, days, inclusive=False):
        upper = datetime.fromisoformat(cutoff)
        lower = upper-timedelta(days=days)
        return [r for r in self.history.get(key, []) if lower <= r['_event']
                and (r['event_at'] <= cutoff if inclusive else r['event_at'] < cutoff)
                and (r['known_at'] <= cutoff if inclusive else r['known_at'] < cutoff)]

    def _phase(self, rows, mode, anchor):
        if mode == 'all_days':
            return rows
        radius = self.policy.cycle_radius_days
        if mode == 'day_of_month':
            return [r for r in rows if abs(r['_day']-min(anchor, r['_month_length'])) <= radius]
        return [r for r in rows if abs(r['_end_offset']-anchor) <= radius]

    def _learning(self, key, cutoff):
        # Calendar support is frozen at midnight for the entire day. A late
        # arrival cannot rewrite a cycle decision made earlier on that day.
        day = cutoff[:10]
        cache_key = key, day
        if cache_key not in self.cycle_cache:
            midnight = day+'T00:00:00+07:00'
            rows = self._samples(key, midnight, self.policy.cycle_learning_days)
            support = {}
            for mode, anchors in (('day_of_month', range(1, 32)), ('month_end_offset', range(3))):
                for anchor in anchors:
                    selected = self._phase(rows, mode, anchor)
                    support[(mode, anchor)] = len(selected), len({r['_month'] for r in selected})
            # Keep only the current day for this scope, rather than growing
            # an unbounded cache during a multi-year replay.
            for old in [old for old in self.cycle_cache if old[0] == key]:
                del self.cycle_cache[old]
            self.cycle_cache[cache_key] = support
        return self.cycle_cache[cache_key]

    def _parameter(self, key, cutoff, days, rows, mode='all_days', anchor=0, learning=None):
        selected = self._phase(rows, mode, anchor)
        values = np.asarray([r['amount_vnd'] for r in selected], dtype=np.float64)
        count = len(values)
        mean = float(np.mean(values)) if count else None
        sd = float(np.std(values, ddof=1)) if count >= 2 else None
        # Suppress sub-micro-dong interpolation noise at an exact VND boundary.
        p95, p99 = ((round(float(v), 6) for v in np.quantile(values, [.95, .99], method='linear')) if count else (None, None))
        mean_std = mean+self.policy.sigma_k*sd if sd is not None else None
        cycle_n, months = (count, len({r['_month'] for r in selected})) if mode == 'all_days' else learning[(mode, anchor)]
        supported = mode == 'all_days' or self.policy.cycle_enabled and cycle_n >= self.policy.minimum_samples and months >= self.policy.minimum_cycle_months
        ready = count >= self.policy.minimum_samples and supported
        threshold = {'p95': p95, 'p99': p99, 'mean_std': mean_std}[self.policy.method] if ready else None
        source_hash = digest([(r['observation_id'], r['amount_vnd'], r['known_at']) for r in selected])
        result = dict(company_id=key[0], account_code=key[1], measurement=key[2], family=key[3], currency='VND',
            as_of=cutoff, window_days=days, window_start=(datetime.fromisoformat(cutoff)-timedelta(days=days)).isoformat(),
            phase=mode, phase_anchor=anchor, cycle_radius_days=self.policy.cycle_radius_days,
            sample_count=count, minimum_samples=self.policy.minimum_samples,
            mean_vnd=mean, std_vnd=sd, p95_vnd=p95, p99_vnd=p99, mean_plus_k_std_vnd=mean_std,
            sigma_k=self.policy.sigma_k, method=self.policy.method, threshold_vnd=threshold,
            status='ready' if ready else 'insufficient_history' if count < self.policy.minimum_samples else 'insufficient_cycle_history',
            cycle_learning_days=self.policy.cycle_learning_days, cycle_learning_samples=cycle_n,
            cycle_learning_months=months, minimum_cycle_months=self.policy.minimum_cycle_months,
            history_sha256=source_hash, policy_version=VERSION)
        result['parameter_id'] = digest(result)[:24]
        return result

    def parameters_for(self, key, cutoff, days, *, inclusive=False, all_phases=False, target_at=None):
        cutoff = timestamp(cutoff)
        rows = self._samples(key, cutoff, days, inclusive)
        base = self._parameter(key, cutoff, days, rows)
        result = [base]
        if self.policy.cycle_enabled:
            learning = self._learning(key, cutoff)
            when = datetime.fromisoformat(timestamp(target_at or cutoff))
            phases = ([('day_of_month', day) for day in range(1, 32)]+[('month_end_offset', day) for day in range(3)]
                      if all_phases else [('day_of_month', when.day)]+(
                          [('month_end_offset', calendar.monthrange(when.year, when.month)[1]-when.day)]
                          if calendar.monthrange(when.year, when.month)[1]-when.day <= 2 else []))
            for mode, anchor in phases:
                item = self._parameter(key, cutoff, days, rows, mode, anchor, learning)
                item['effective_threshold_vnd'] = item['threshold_vnd'] if item['status'] == 'ready' else base['threshold_vnd']
                item['fallback_basis'] = '' if item['status'] == 'ready' else 'all_days' if base['status'] == 'ready' else 'none'
                result.append(item)
        base['effective_threshold_vnd'], base['fallback_basis'] = base['threshold_vnd'], ''
        return result

    def evaluate(self, raw, cutoff=None):
        row = raw if '_event' in raw else observation(raw)
        cutoff = timestamp(cutoff or row['known_at'])
        self.advance(cutoff)
        if row['known_at'] > cutoff:
            return False, dict(method='rolling_account', status='not_observed_at_cutoff')
        parameters = self.parameters_for(key_of(row), cutoff, self.policy.window_days, target_at=row['event_at'])
        ready_cycles = [p for p in parameters[1:] if p['status'] == 'ready']
        # Select calendar context using historical support, never current amount
        # or fraud labels. Coverage wins; month-end wins an exact support tie.
        selected = max(ready_cycles, key=lambda p: (p['cycle_learning_months'], p['cycle_learning_samples'],
                                                    p['sample_count'], p['phase'] == 'month_end_offset')) if ready_cycles else parameters[0]
        threshold = selected['threshold_vnd']
        signal = threshold is not None and row['amount_vnd'] > threshold
        return signal, dict(method='rolling_account', status=selected['status'],
            comparison_amount_vnd=row['amount_vnd'], threshold_vnd=threshold,
            observation_id=row['observation_id'], source_ref=row['source_ref'],
            selected_parameter=selected, calendar_conditioned=bool(ready_cycles),
            base_threshold_vnd=parameters[0]['threshold_vnd'],
            reference_time_basis='known_at', threshold_inclusive=False)

    def evaluate_transaction(self, row, *, diagnostics=None):
        cutoff = timestamp(row['posted_at'])
        bound = self.by_transaction.get((row['company_id'], row['transaction_id']), [])
        candidates = [r for r in bound
                      if r['known_at'] <= cutoff]
        expenses = [r for r in candidates if r['measurement'] in {'expense_debit', 'transaction_amount'}]
        selected = expenses or [r for r in candidates if r['measurement'] == 'cash_outflow']
        if diagnostics is not None:
            diagnostics.update(bound_observation_count=len(bound), observations=[])
        if not selected:
            self.advance(cutoff)
            return False, dict(method='rolling_account', status='not_applicable', required_source='expense posting or verified VND cash outflow')
        results = [self.evaluate(r, cutoff) for r in sorted(selected, key=lambda r: r['observation_id'])]
        if diagnostics is not None:
            from .a5_coverage import observation_summary
            diagnostics['observations'] = [observation_summary(*pair) for pair in results]
        return max(results, key=lambda pair: (pair[0], pair[1].get('threshold_vnd') is not None,
            pair[1].get('comparison_amount_vnd', 0)/max(1., pair[1].get('threshold_vnd') or 1.)))

    def parameter_table(self, cutoff):
        cutoff = timestamp(cutoff)
        self.advance(cutoff, inclusive=True)
        result = []
        for key in sorted(self.history):
            for days in (30, 60, 90):
                result.extend(self.parameters_for(key, cutoff, days, inclusive=True, all_phases=True))
        return result
