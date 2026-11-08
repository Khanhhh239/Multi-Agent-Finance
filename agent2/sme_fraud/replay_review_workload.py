"""Recalculate workload from frozen train/validation queues, without reading labels.

Keep prior report roots immutable. Research scenarios and actual UI capacities
are named separately; weekday-only scheduling is an explicit sensitivity case.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from .evidence_evaluation import budget_review
from .feature_contract import validate_cache
from .review_capacity import CAPACITY_VERSION, ReviewCalendar, workload_scenarios


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = (('before_split_admission', 'feature_model_sync_20261017', 'comparison_train_validation.json'),
             ('after_split_admission', 'split_pattern_admission_20261017_v2', 'comparison.json'))
PERIOD_ENDS = dict(train='2024-12-31', validation='2025-06-30')
CALENDARS = dict(calendar_days=ReviewCalendar(), weekdays_mon_fri=ReviewCalendar(tuple(range(5))))


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            value.update(block)
    return value.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def run(output):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('Use a new output root; frozen workload runs are not overwritten')
    protected = {}

    def protect(path, expected=None):
        path = Path(path).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError('Protected input is outside this workspace')
        value = protected.get(path) or sha(path)
        if expected is not None and value != expected:
            raise ValueError(f'Frozen input hash mismatch: {path}')
        protected[path] = value

    for tag in ('001', '003', '005'):
        data = ROOT/f'data/feature_model_sync_20261017/sme_fraud_{tag}'
        manifest = read(data/'manifest.json')
        validate_cache(manifest)
        for path in data.glob('*'):
            if path.is_file():
                protect(path)
        for name, expected in manifest['derivation']['source_sha256'].items():
            protect(ROOT/f'data/sme_fraud_{tag}'/name, expected)
        for _, folder, _ in SNAPSHOTS:
            for path in (ROOT/'reports'/folder/f'sme_fraud_{tag}').glob('*'):
                if path.is_file() and path.name != '.feedback.lock':
                    protect(path)
            database = ROOT/'reports'/folder/f'review_{tag}.sqlite3'
            if database.is_file():
                protect(database)
        after = ROOT/f'reports/split_pattern_admission_20261017_v2/sme_fraud_{tag}'
        for name, expected in read(after/'comparison.json')['protected_sha256'].items():
            protect(ROOT/name, expected)
        for name, expected in read(after/'predictions_frozen.json')['sha256'].items():
            protect(after/name, expected)
    production = ROOT/'.runtime/review/review.sqlite3'
    if production.is_file():
        protect(production)
    code_files = ('review_capacity.py', 'evidence_evaluation.py', 'review_store.py', 'replay_review_workload.py')
    source_hashes = {name: sha(ROOT/'sme_fraud'/name) for name in code_files}
    plan = dict(capacity_contract=CAPACITY_VERSION, period_ends=PERIOD_ENDS,
        profiles=[dict(name=name, kind=kind, slots=capacity.slots, minutes=capacity.minutes)
                  for name, kind, capacity in workload_scenarios()],
        calendars={name: calendar.as_dict() for name, calendar in CALENDARS.items()},
        labels_read=False, detector_scored=False, test_scored=False, model_refitted=False,
        rank_policy='opening_event_only', effort_policy='saved_final_snapshot_estimate',
        source_sha256=source_hashes)
    output.mkdir(parents=True)
    write(output/'evaluation_plan.json', plan)
    results, legacy_checks = [], 0
    for tag in ('001', '003', '005'):
        data = ROOT/f'data/feature_model_sync_20261017/sme_fraud_{tag}'
        transactions = {row['transaction_id']: row for row in rows(data/'transactions.csv')}
        partitions = {row['transaction_id']: row['split'] for row in rows(data/'splits.csv')}
        if len(transactions) != 75000 or set(partitions) != set(transactions) or set(partitions.values()) != {'train', 'validation'}:
            raise ValueError('Only the frozen 75,000 train/validation IDs are allowed per dataset')
        destination = output/f'sme_fraud_{tag}'
        destination.mkdir()
        measured = []
        for snapshot, folder, comparison_name in SNAPSHOTS:
            source = ROOT/'reports'/folder/f'sme_fraud_{tag}'
            cases, events = rows(source/'case_queue.csv'), rows(source/'case_events.csv')
            comparison = read(source/comparison_name)
            for period, cutoff in PERIOD_ENDS.items():
                selected = [case for case in cases if case['opened_at'].startswith('2024' if period == 'train' else '2025')]
                for calendar_name, calendar in CALENDARS.items():
                    for name, kind, capacity in workload_scenarios():
                        load = budget_review(selected, events, transactions, None, capacity.slots,
                            capacity_minutes=capacity.minutes, calendar=calendar, period_end=cutoff)
                        admissions = load.pop('admissions')
                        admissions_name = f'{snapshot}_{period}_{calendar_name}_{name}.jsonl'
                        with (destination/admissions_name).open('w', encoding='utf-8') as stream:
                            for item in admissions:
                                stream.write(json.dumps(item, ensure_ascii=False)+'\n')
                        if kind == 'research' and calendar_name == 'calendar_days':
                            old = next(row for row in comparison['workload'] if row['version'] == 'after'
                                and row['period'] == period and row['budget_per_company_day'] == capacity.slots)
                            for key in ('total_cases', 'total_work_items', 'total_demand_minutes',
                                        'carryover_work_items', 'peak_backlog_work_items', 'peak_backlog_minutes'):
                                if old[key] != load[key]:
                                    raise ValueError(f'Historical workload replay differs: {tag}/{snapshot}/{period}/{name}/{key}')
                            legacy_checks += 1
                        measured.append(dict(snapshot=snapshot, period=period, calendar_name=calendar_name,
                            capacity_profile=name, profile_kind=kind, admissions_file=admissions_name, **load))
        write(destination/'workload.json', measured)
        results.append(dict(tag=tag, workloads=measured))
        print(f'{tag}: {len(measured)} workload scenarios replayed from unchanged queues', flush=True)
    for path, expected in protected.items():
        if sha(path) != expected:
            raise ValueError(f'Protected input changed during workload replay: {path}')
    if any(sha(ROOT/'sme_fraud'/name) != expected for name, expected in source_hashes.items()):
        raise ValueError('Workload code changed during evaluation')
    summary = dict(successful=True, observations=225000, source_snapshots=6,
        labels_read=False, detector_scored=False, test_scored=False, model_refitted=False,
        historical_research_scenarios_replayed=legacy_checks, workload_scenarios=sum(len(r['workloads']) for r in results),
        protected_files_unchanged=True, protected_sha256={str(path.relative_to(ROOT)): value for path, value in protected.items()},
        plan=plan, results=results)
    write(output/'summary.json', summary)
    write(output/'output_hashes.json', {str(path.relative_to(output)): sha(path)
                                      for path in output.rglob('*') if path.is_file()})
    print(f'Complete: {legacy_checks} historical comparisons exact; inputs, queues, models and SQLite hashes unchanged.', flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('reports/review_capacity_20261017'))
    run(parser.parse_args().output)


if __name__ == '__main__':
    main()
