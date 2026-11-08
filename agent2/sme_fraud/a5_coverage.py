"""Transaction-time observability for A5; never a scoring or threshold policy."""
from collections import Counter, defaultdict
import json


VERSION = 'a5-transaction-coverage-v1'


def observation_summary(signal, evidence):
    parameter = evidence.get('selected_parameter', {})
    fields = ('company_id', 'account_code', 'measurement', 'family', 'as_of', 'window_days',
              'phase', 'phase_anchor', 'sample_count', 'minimum_samples', 'method',
              'history_sha256', 'parameter_id')
    return dict({key: parameter.get(key) for key in fields},
        observation_id=evidence.get('observation_id'), source_ref=evidence.get('source_ref'),
        status=evidence['status'], comparison_amount_vnd=evidence.get('comparison_amount_vnd'),
        threshold_vnd=evidence.get('threshold_vnd'), amount_signal=bool(signal),
        base_threshold_vnd=evidence.get('base_threshold_vnd'))


def transaction_record(row, signal, evidence, diagnostics, policy):
    observations = diagnostics['observations']
    ready = sum(item['threshold_vnd'] is not None for item in observations)
    count = len(observations)
    status = ('ready' if ready == count else 'partial_history') if ready else (
        'insufficient_history' if count else 'not_observed_at_cutoff'
        if diagnostics['bound_observation_count'] else 'not_applicable')
    gate = bool(int(row['is_financial_entry']) and int(row['amount_vnd']) % 1000 == 0)
    return dict(version=VERSION, company_id=row['company_id'], transaction_id=row['transaction_id'],
        posted_at=row['posted_at'], month=row['posted_at'][:7], status=status,
        financial=bool(int(row['is_financial_entry'])), round_thousand=int(row['amount_vnd']) % 1000 == 0,
        a5_gate=gate, eligible=bool(count), ready=bool(ready), fully_ready=bool(count and ready == count),
        bound_observation_count=diagnostics['bound_observation_count'], candidate_count=count,
        ready_candidate_count=ready, missing_candidate_count=count-ready,
        amount_signal=bool(signal), a5_predicate=bool(gate and signal),
        window_days=policy.window_days, method=policy.method, minimum_samples=policy.minimum_samples,
        selected=observation_summary(signal, evidence) if count else None, observations=observations,
        unavailable_reason=('observation_not_known_at_posting' if status == 'not_observed_at_cutoff'
                            else 'no_expense_or_verified_vnd_cash_outflow' if not count else ''))


def attach_hits(records, hits):
    a5 = {hit['transaction_id']: hit for hit in hits if hit['rule_id'] == 'A5'}
    for record in records:
        hit = a5.get(record['transaction_id'])
        record.update(hit_emitted=bool(hit), points=hit['points'] if hit else 0,
                      suppressed_reason=hit.get('suppressed_reason', '') if hit else '')


def counts(rows):
    rows = list(rows)
    total = len(rows)
    eligible = sum(row['eligible'] for row in rows)
    ready = sum(row['ready'] for row in rows)
    gate = [row for row in rows if row['a5_gate']]
    gate_eligible = sum(row['eligible'] for row in gate)
    gate_ready = sum(row['ready'] for row in gate)
    return dict(transactions=total, eligible_transactions=eligible, ready_transactions=ready,
        fully_ready_transactions=sum(row['fully_ready'] for row in rows),
        insufficient_transactions=sum(row['eligible'] and not row['ready'] for row in rows),
        partial_transactions=sum(row['status'] == 'partial_history' for row in rows),
        unavailable_transactions=total-eligible, status_counts=dict(Counter(row['status'] for row in rows)),
        ready_over_all=ready/total if total else None, ready_over_eligible=ready/eligible if eligible else None,
        a5_gate_transactions=len(gate), a5_gate_eligible_transactions=gate_eligible,
        a5_gate_ready_transactions=gate_ready,
        a5_gate_ready_over_all=gate_ready/len(gate) if gate else None,
        a5_gate_ready_over_eligible=gate_ready/gate_eligible if gate_eligible else None,
        selected_cycle_transactions=sum(bool(row['selected'] and row['selected']['phase'] != 'all_days') for row in rows),
        observations=sum(row['candidate_count'] for row in rows),
        ready_observations=sum(row['ready_candidate_count'] for row in rows),
        a5_hits=sum(row.get('hit_emitted', False) for row in rows),
        a5_scored_hits=sum(row.get('points', 0) > 0 for row in rows))


def coverage(records):
    groups, accounts = defaultdict(list), defaultdict(list)
    for row in records:
        for dimension, value in (('company', row['company_id']), ('month', row['month'])):
            groups[dimension, value].append(row)
        for obs in row['observations']:
            key = tuple(obs[field] for field in ('company_id', 'account_code', 'measurement', 'family'))
            accounts[key].append(obs)
    return dict(version=VERSION, available=True, reference_time='posted_at; history event_at and known_at strictly earlier',
        definition='Eligible: an observed expense measurement, otherwise verified VND cash outflow. '
                   'Ready: at least one preferred measurement has a threshold; fully_ready: all do. '
                   'A5 gate: financial entry and transaction amount divisible by 1000. No hit is not a clearance.',
        totals=counts(records),
        groups=[dict(dimension=dimension, value=value, **counts(rows)) for (dimension, value), rows in sorted(groups.items())],
        account_scopes=[dict(zip(('company_id','account_code','measurement','family'), key),
            observations=len(rows), ready_observations=sum(row['threshold_vnd'] is not None for row in rows),
            distinct_transactions_note='Observation counts can exceed transaction counts for multi-account documents')
            for key, rows in sorted(accounts.items())])


def write_coverage(output, result):
    if result.get('a5_evaluations') is None:
        return
    records = result['a5_evaluations']
    with (output/'a5_evaluations.jsonl').open('w', encoding='utf-8') as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False)+'\n')
    (output/'a5_coverage.json').write_text(json.dumps(coverage(records), ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    from .generate import write_csv
    flat = [{**{key: value for key, value in row.items() if key not in {'observations', 'selected'}},
             **{'selected_'+key: value for key, value in (row['selected'] or {}).items()}} for row in records]
    if flat:
        write_csv(output/'a5_evaluations.csv', flat, sorted({key for row in flat for key in row}))
