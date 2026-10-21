"""Export an explicitly synthetic, checksummed source world and causal cache."""
from collections import Counter, defaultdict
import copy
import json
from pathlib import Path
import statistics

from .synthetic_world import World, AS_OF, VARIANTS, raw_export, map_export
from .exception_validation import PROFILES, validated_tables, validated_record
from .features import build_features, FEATURE_DESCRIPTIONS
from .feature_contract import cache_contract, sha
from .generate import write_csv, parse
from .rules import INPUT_TABLES, OPTIONAL_INPUT_TABLES
from .real_source_acceptance import F1_COLUMNS, RULE_SOURCES, source_inventory
from .run_rule_repairs import write_jsonl


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def columns(name, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    required = F1_COLUMNS.get(name, PROFILES.get(name, {}).get('required', ()))
    return list(dict.fromkeys([*fields, *required])) or ['_empty']


def quarantine_probes(tables):
    """Malformed records never enter the canonical cache or detector."""
    probes = []
    for name, field, value in (
        ('payroll_entitlements', 'evidence_on_file', 2),
        ('workflow_policies', 'allow_override', 2),
        ('workflow_policies', 'required', -1),
        ('workflow_policies', 'override_max_vnd', 'NaN'),
        ('override_events', 'status', 'EXECUTED_TYPO'),
        ('system_actions', 'action_at', '2025-02-30T10:00:00+07:00'),
        ('leave_periods', 'observed_at', '2025-06-01T10:00:00'),
        ('receivable_invoices', 'gross_vnd', -1000),
    ):
        raw = dict(tables[name][0], **{field: value})
        try:
            validated_record(name, raw)
        except ValueError as exc:
            probes.append(dict(source=name, field=field, invalid_value=value,
                status='rejected', reason=str(exc), source_record=raw))
        else:
            raise AssertionError(f'Malformed {name}.{field} was accepted')
    first = raw_export(tables['transactions'][0])
    for field, value in (
        ('value_vnd', '-1,000'), ('value_vnd', '10,00'),
        ('booked_at_utc', '2025-01-01T00:00:00'),
        ('payment_kind', 'refund'), ('payment_kind', 'reversal'),
        ('payment_kind', 'cancelled_payment'), ('payment_kind', 'parallel_bank_account'),
        ('payment_kind', 'unknown_kind'),
    ):
        raw = dict(first, **{field: value})
        try:
            map_export(raw)
        except ValueError as exc:
            probes.append(dict(source='erp_payments_raw', field=field, invalid_value=value,
                status='rejected', reason=str(exc), source_record=raw))
        else:
            raise AssertionError('Unsafe ERP conversion')
    return probes


def diagnostics(tables, oracle, profiles):
    amounts = sorted(int(row['amount_vnd']) for row in tables['transactions'])
    batches = Counter((r['company_id'], r['posted_at']) for r in tables['transactions'])
    debit, credit = defaultdict(int), defaultdict(int)
    for line in tables['journal_lines']:
        debit[line['document_id']] += int(line['debit_vnd'])
        credit[line['document_id']] += int(line['credit_vnd'])
    unbalanced = [identity for identity in set(debit)|set(credit) if debit[identity] != credit[identity]]
    if unbalanced:
        raise AssertionError('Synthetic journal does not balance')
    return dict(is_synthetic=True, as_of=AS_OF, financial_fraud_labels_available=False,
        transactions=len(amounts), tables={name: len(rows) for name, rows in tables.items()},
        transaction_kinds=dict(Counter(r['txn_type'] for r in tables['transactions'])),
        companies=profiles, company_rows=dict(Counter(r['company_id'] for r in tables['transactions'])),
        amount_vnd=dict(min=min(amounts), median=statistics.median(amounts),
            p90=amounts[int(.9*(len(amounts)-1))], p99=amounts[int(.99*(len(amounts)-1))], max=max(amounts)),
        month_rows=dict(sorted(Counter(r['posted_at'][:7] for r in tables['transactions']).items())),
        same_timestamp_rows=sum(n for n in batches.values() if n > 1),
        weekend_rows=sum(parse(r['posted_at']).weekday() >= 5 for r in tables['transactions']),
        leading_zero_recipient_rows=sum(str(r['recipient_account']).startswith('0') for r in tables['transactions']),
        balanced_journal_documents=len(debit), unbalanced_journal_documents=len(unbalanced),
        enriched_process_controls=len(oracle),
        control_counts=dict(Counter(r['rule_id'] for r in oracle)),
        limitations=['Priors are illustrative assumptions, not fitted field distributions',
            'Enriched controls do not estimate financial-fraud prevalence or precision',
            'Bank identifiers are fictional; tax/accounting templates are illustrative',
            'No reviewer conclusions or production readiness are implied'])


def export_world(data, report, seed, *, role, companies=8, background_rows=12000, repetitions=2):
    data, report = Path(data), Path(report)
    if data.exists() or report.exists():
        raise FileExistsError('Synthetic snapshots must use fresh output directories')
    data.mkdir(parents=True)
    report.mkdir(parents=True)
    world = World(seed, companies, background_rows)
    tables, oracle = world.build(repetitions)
    # Commit source-defined expectations before feature extraction or scoring.
    sealed = report/'sealed_truth'
    sealed.mkdir()
    write_json(sealed/'oracle.json', oracle)
    write_json(sealed/'scenario_registry.json', VARIANTS)
    tables = validated_tables(tables)
    masters = {row.get('employee_id') or row.get('vendor_id'): row
               for row in [*tables['employees'], *tables['vendors']]}
    seen = Counter()
    for link in tables['entity_links']:
        master = masters[link['source_id']]
        kind = link['link_type']
        seen[(link['source_id'], kind)] += 1
        if (link['target_id'] != master[kind] or kind == 'bank_account'
                and link['bank_code'] != master['bank_code']):
            raise AssertionError('Contact mirror differs from decorated source master')
    if len(seen) != 2*len(masters) or any(count != 1 for count in seen.values()):
        raise AssertionError('Contact mirror is missing or duplicated')
    probes = quarantine_probes(tables)
    write_jsonl(report/'quarantine.jsonl', [*world.quarantine, *probes])
    raw = [raw_export(row) for row in tables['transactions']]
    for before, after in zip(tables['transactions'], map(map_export, raw)):
        if any(before[key] != value for key, value in after.items()):
            raise AssertionError('ERP mapping round-trip changed a value')
    write_jsonl(report/'erp_payments_raw.jsonl', raw)
    write_json(report/'mapping_contract.json', dict(data_origin='synthetic', timezone='Asia/Saigon',
        currency='VND', amount='nonnegative integer, grouped decimal string at ERP boundary',
        bank_identity='company + bank code + account text; preserve leading zeros',
        fields=dict(voucher_uid='transaction_id', org_code='company_id', booked_at_utc='posted_at',
            value_vnd='amount_vnd', recipient_number='recipient_account', recipient_bank='recipient_bank_code',
            maker_ref='creator_id', checker_ref='approver_id', payment_kind='txn_type'),
        round_trip_verified_rows=len(raw), rejected_probe_records=len(probes),
        future_transactions_quarantined=len(world.quarantine),
        erp_hr_cash_source_mapping={rule: list(names) for rule, names in RULE_SOURCES.items()},
        unsupported_semantics=['refund', 'reversal', 'cancelled_payment', 'parallel_bank_account']))
    for name in dict.fromkeys([*INPUT_TABLES, *OPTIONAL_INPUT_TABLES, *tables]):
        if name == 'labels':
            continue
        rows = tables.get(name, [])
        write_csv(data/f'{name}.csv', rows, columns(name, rows))
    features = build_features(tables)
    write_csv(data/'features.csv', features, ['transaction_id', *FEATURE_DESCRIPTIONS])
    files = {path.name: dict(sha256=sha(path)) for path in sorted(data.glob('*.csv'))}
    manifest = dict(version='synthetic-source-world-v1', is_synthetic=True,
        data_origin='synthetic_process_simulation', seed=seed, role=role, as_of=AS_OF,
        period_start='2024-01-01T00:00:00+07:00', companies=companies,
        background_random_rows=background_rows, control_repetitions=repetitions,
        financial_fraud_labels_available=False, files=files,
        feature_columns=list(FEATURE_DESCRIPTIONS), feature_contract=cache_contract(files))
    write_json(data/'manifest.json', manifest)
    write_json(report/'source_inventory.json', source_inventory(data, manifest))
    write_json(report/'diagnostics.json', diagnostics(tables, oracle, world.profiles))
    write_json(report/'source_commitment.json', dict(manifest_sha256=sha(data/'manifest.json'),
        oracle_sha256=sha(sealed/'oracle.json'), registry_sha256=sha(sealed/'scenario_registry.json'),
        role=role, predictions_created=False, source_origin='synthetic', human_reviewed_units=0))
    return manifest
