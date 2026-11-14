"""Independent reconciliation of frozen R1 data; deliberately reports open defects.

This is a review tool, not a replacement acceptance baseline or business approval.
Expected values below are worked examples, not calls to the legacy feature engine.
"""
import argparse
import copy
import csv
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from finance_input import AccessScope
from sme_fraud.import_files import canonical, digest
from sme_fraud.imports import validate_input
from sme_fraud.snapshot_features import build_feature_rows, build_from_snapshot
from sme_fraud.feature_pipeline import export_artifact, read_artifact
from sme_fraud.snapshots import SnapshotStore

EARLY = '2026-10-10T11:00:00+07:00'
LATE = '2026-10-13T00:00:00+07:00'
FIXTURE = ROOT/'tests/fixtures/r1_feature_replay_v1.json'


def source(company=None):
    data = json.loads(FIXTURE.read_text('utf-8'))
    if company:
        for table, rows in data.items():
            if isinstance(rows, list):
                data[table] = [r for r in rows if r['company_id'] == company]
    return data


def scope(companies=('C001', 'C002'), verify=False):
    return AccessScope('demo', frozenset(companies), 'r1-review',
                       frozenset({'data.import', 'evidence.verify'} if verify else {'data.import'}))


def values(result, company, identity):
    row = next(r for r in result['rows'] if (r['company_id'], r['record_id']) == (company, identity))
    index = row['row_index']
    return dict(zip(result['contract']['columns'], result['features'][index])), result['evidence'][index]


def save(store, authority, data):
    draft = store.upload(authority, canonical(data), 'synthetic-review.json', 'review-upload')
    preview = store.preview(authority, draft['import_id'], 1)
    body = {k: preview[k] for k in ('preview_id', 'source_hash', 'mapping_hash', 'report_hash', 'context_hash')}
    body.update(expected_revision=1, acknowledge=True)
    return store.commit(authority, draft['import_id'], body, 'review-commit')['snapshot']['snapshot_id']


def expected(company, row):
    """Hand-worked expectations for every column in the frozen two-company example."""
    identity = row['record_id']
    history_counts = {'H0': 0, 'T001': 1, 'T002': 1, 'ADJ001': 0, 'Z0001': 3, 'NEXT01': 4}
    if company == 'C002':
        history_counts.update(T001=0, T002=0, Z0001=2, NEXT01=3)
    ratios = {'H0': .2, 'T001': .3, 'T002': .35, 'NEXT01': .4}
    prior_amounts = {'H0': 0, 'T001': 4000000, 'T002': 4000000, 'NEXT01': 17000000}
    prior_counts = {'H0': 0, 'T001': 1, 'T002': 1, 'NEXT01': 3}
    if company == 'C002':
        prior_amounts.update(T001=0, T002=0, NEXT01=13000000)
        prior_counts.update(T001=0, T002=0, NEXT01=2)
    amount = row['amount_vnd']
    event = datetime.fromisoformat(row['effective_at'])
    known_invoice = identity in ratios
    history_deviation = None
    if company == 'C001' and identity in ('T001', 'T002'):
        history_deviation = math.log1p(abs(amount)) - math.log1p(4000000)
    result = dict(
        log_abs_amount=math.log1p(abs(amount)), amount_negative=int(amount < 0),
        amount_zero=int(amount == 0), round_million=int(amount % 1000000 == 0),
        event_hour_sin=math.sin(2*math.pi*event.hour/24),
        event_hour_cos=math.cos(2*math.pi*event.hour/24),
        event_weekday_sin=math.sin(2*math.pi*event.weekday()/7),
        event_weekday_cos=math.cos(2*math.pi*event.weekday()/7),
        event_weekend=int(event.weekday() >= 5),
        prior_type_history_log_count=math.log1p(history_counts[identity]),
        log_abs_deviation_from_history=history_deviation, abs_amount_history_z=None,
        employee_bank_overlap_observed=1, graph_employee_count_observed=1,
        graph_vendor_count_observed=1, journal_line_count=2 if identity == 'T001' else None,
        journal_imbalance_abs_ratio=0 if identity == 'T001' else None,
        known_document_count=1 if identity == 'T001' else 0,
        verified_original_document_count=0, known_invoice_count=int(known_invoice),
        linked_invoice_log_abs_total=math.log1p(20000000) if known_invoice else None,
        allocation_to_invoice_face_ratio=ratios.get(identity),
        prior_invoice_payment_count=prior_counts.get(identity),
        prior_invoice_allocation_log_abs=math.log1p(prior_amounts[identity]) if known_invoice else None,
        prior_invoice_allocation_negative=0 if known_invoice else None,
        creator_equals_approver=1 if identity == 'T001' else None,
        observed_approval_limit_ratio=.6 if identity == 'T001' else None,
    )
    result.update({'kind_'+kind: int(row['kind'] == kind)
                   for kind in ('payment', 'receipt', 'payroll', 'transfer', 'adjustment', 'reversal')})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    checks, comparisons = [], []

    def check(identity, operation):
        try:
            detail = operation()
            checks.append(dict(id=identity, status='pass', detail=detail))
        except Exception as error:
            checks.append(dict(id=identity, status='fail', error_type=type(error).__name__,
                               error=str(error), traceback=traceback.format_exc()))

    data = source()
    result = build_feature_rows(data, scope(), LATE)
    early = build_feature_rows(data, scope(), EARLY)

    def reconcile():
        assert len(result['rows']) == 11 and len(early['rows']) == 5
        by_key = {(r['company_id'], r['record_id']): r for r in data['transactions']}
        for at, output in ((EARLY, early), (LATE, result)):
            for meta in output['rows']:
                key = (meta['company_id'], meta['record_id'])
                row = by_key[key]
                actual, evidence = values(output, *key)
                oracle = expected(key[0], row)
                assert set(actual) == set(oracle), 'Unreviewed feature column'
                for column, target in oracle.items():
                    observed = actual[column]
                    ok = observed is None if target is None else observed is not None and math.isclose(observed, target, rel_tol=0, abs_tol=1e-8)
                    comparisons.append(dict(as_of=at, company=key[0], record_id=key[1],
                                            column=column, expected=target, observed=observed, passed=ok))
                    assert ok, (key, column, target, observed)
                assert evidence['signed_amount_vnd'] == row['amount_vnd']
                assert set(evidence['missing_reasons']) == {k for k, v in actual.items() if v is None}
                for ref in evidence['records']:
                    matching = [r for r in data[ref['table']] if (r['company_id'], r['record_id'], r['revision']) == (*key[:1], ref['record_id'], ref['revision'])]
                    assert len(matching) == 1, ref
                    assert all(ref[k] == matching[0][k] for k in ('observed_at', 'effective_at'))
                    assert datetime.fromisoformat(ref['observed_at']) <= datetime.fromisoformat(meta['as_of'])
                    assert datetime.fromisoformat(ref['effective_at']) <= datetime.fromisoformat(meta['event_at'])
        return dict(rows_at_early=5, rows_at_late=11, numeric_or_null_cells=len(comparisons), tolerance_abs=1e-8)
    check('BR-01-all-33-columns-and-source-evidence', reconcile)

    def frozen():
        for meta in early['rows']:
            first, first_evidence = values(early, meta['company_id'], meta['record_id'])
            later, later_evidence = values(result, meta['company_id'], meta['record_id'])
            assert first == later
            # An artifact-local array index can shift when another company gains
            # rows. Compare provenance by company + logical ID, not array slot.
            assert {k: v for k, v in first_evidence.items() if k != 'row_index'} == {
                k: v for k, v in later_evidence.items() if k != 'row_index'}
        assert all(r['record_id'] != 'DOC_LATE' for e in result['evidence'] for r in e['records'])
        return 'All five old rows, missing reasons and evidence unchanged at later job cutoff.'
    check('BR-02-late-document-no-past-rewrite', frozen)

    def different_bank():
        changed = source('C001')
        changed['employees'][0]['bank_account'] = '99123456'
        output = build_feature_rows(changed, scope(('C001',)), EARLY)
        f, _ = values(output, 'C001', 'T001')
        assert f['employee_bank_overlap_observed'] == 0
        assert f['graph_employee_count_observed'] == 0
        assert f['graph_vendor_count_observed'] == 1
        return 'Different bank identity removes employee overlap/graph link; vendor self count remains one.'
    check('BR-03-bank-link-negative-control', different_bank)

    def ambiguous_limit():
        changed = source('C001')
        approval = copy.deepcopy(changed['approvals'][0])
        approval.update(record_id='AP_DIFFERENT_LIMIT', limit_vnd=5000000)
        changed['approvals'].append(approval)
        f, e = values(build_feature_rows(changed, scope(('C001',)), EARLY), 'C001', 'T001')
        assert f['observed_approval_limit_ratio'] is None
        assert 'observed_approval_limit_ratio' in e['missing_reasons']
        return 'Conflicting 10M/5M approved limits produce null; no arbitrary denominator.'
    check('BR-04-ambiguous-approval-limit', ambiguous_limit)

    def negative_allocation():
        changed = source('C001')
        correction = copy.deepcopy(next(a for a in changed['payment_allocations'] if a['record_id'] == 'A_H0'))
        correction.update(record_id='ALLOC_MINUS_1M', amount_vnd=-1000000, kind='adjustment',
                          observed_at='2026-10-09T10:00:00+07:00', effective_at='2026-10-09T10:00:00+07:00',
                          adjustment_reason='Synthetic reduction', adjusts_ref=dict(record_id='A_H0', revision=1))
        changed['payment_allocations'].append(correction)
        f, e = values(build_feature_rows(changed, scope(('C001',)), EARLY), 'C001', 'T001')
        assert e['prior_signed_allocation_vnd'] == 3000000
        assert math.isclose(f['prior_invoice_allocation_log_abs'], math.log1p(3000000), abs_tol=1e-8)
        assert f['prior_invoice_payment_count'] == 1
        return '4M + (-1M) = 3M; one payment identity, not two.'
    check('BR-05-signed-allocation-correction', negative_allocation)

    with tempfile.TemporaryDirectory(prefix='r1_business_review_') as tmp:
        def artifact():
            authority = scope(('C001',))
            store = SnapshotStore(Path(tmp)/'artifact.sqlite3')
            snapshot_id = save(store, authority, source('C001'))
            built = build_from_snapshot(store, authority, snapshot_id, EARLY)
            saved = export_artifact(built, out/'artifacts')
            reread = read_artifact(saved['directory'])
            assert reread['features'] == built['features']
            assert reread['manifest']['snapshot']['snapshot_id'] == snapshot_id
            assert export_artifact(built, out/'artifacts')['directory'] == saved['directory']
            (out/'demo_snapshot_manifest.json').write_bytes(canonical(store.get_snapshot(authority, snapshot_id)))
            return dict(snapshot_id=snapshot_id, artifact=saved['directory'], checksum=saved['manifest']['checksum'])
        check('BR-06-persisted-snapshot-and-artifact', artifact)

        def verified_reader():
            changed = source('C001')
            doc = next(d for d in changed['supporting_documents'] if d['record_id'] == 'DOC_KNOWN')
            doc.update(source_kind='original', verification_status='verified',
                       verification=dict(verified_by='synthetic-verifier', verified_at=doc['observed_at'],
                                         basis='Synthetic permission regression, not an authentic original document'))
            doc['source']['is_simulated'] = False
            writer, reader = scope(('C001',), verify=True), scope(('C001',))
            assert validate_input(changed, writer)['status'] != 'rejected'
            store = SnapshotStore(Path(tmp)/'verified.sqlite3')
            snapshot_id = save(store, writer, changed)
            assert store.get_snapshot(reader, snapshot_id)['snapshot_id'] == snapshot_id
            # Desired behavior: reading/deriving cannot re-confirm verification.
            output = build_from_snapshot(store, reader, snapshot_id, EARLY)
            assert values(output, 'C001', 'T001')[0]['verified_original_document_count'] == 1
            return 'Already authorized/committed verification can be read without permission to verify.'
        check('BR-07-verified-snapshot-reader-permission', verified_reader)

    def unknown_prior_invoice_revision():
        changed = source('C001')
        invoice = copy.deepcopy(changed['invoices'][0])
        invoice.update(revision=2, observed_at='2026-10-12T08:00:00+07:00')
        changed['invoices'].append(invoice)
        allocation = next(a for a in changed['payment_allocations'] if a['record_id'] == 'A_H0')
        allocation['invoice_ref']['revision'] = 2
        assert validate_input(changed, scope(('C001',)))['status'] != 'rejected'
        output = build_feature_rows(changed, scope(('C001',)), EARLY)
        f, e = values(output, 'C001', 'T001')
        # A known 4M allocation references a not-yet-known revision of the same
        # invoice. It cannot be used, nor can completeness be silently assumed.
        observed = {k: f[k] for k in ('prior_invoice_payment_count', 'prior_invoice_allocation_log_abs', 'prior_invoice_allocation_negative')}
        (out/'unknown_prior_invoice_observed.json').write_bytes(canonical(dict(
            observed=observed, missing_reasons=e['missing_reasons'], records=e['records'],
            prior_signed_allocation_vnd=e['prior_signed_allocation_vnd'],
            prior_invoice_history=e.get('prior_invoice_history'),
            validation_warnings=validate_input(changed, scope(('C001',)))['warnings'])))
        assert all(v is None for v in observed.values()), 'Incomplete prior link reported as known zero: '+repr(observed)
        assert all(e['missing_reasons'][k] == 'prior_invoice_history_incomplete' for k in observed)
        assert e['prior_signed_allocation_vnd'] is None
        coverage = e['prior_invoice_history']
        assert coverage['status'] == 'unavailable'
        assert any(item['source']['record_id'] == 'A_H0' and item['field'] == 'invoice_ref'
                   and item['reference'] == dict(table='invoices', record_id='I001', revision=2)
                   and item['message'] and item['action'] for item in coverage['unavailable_references'])
        assert any(r['table'] == 'payment_allocations' and r['record_id'] == 'A_H0' for r in e['records'])
        assert not any(r['table'] == 'invoices' and r['revision'] == 2 for r in e['records'])
        return 'Missing predictors/total, known allocation, unavailable source reference and action are explicit; no future revision is used.'
    check('BR-08-incomplete-prior-invoice-history', unknown_prior_invoice_revision)

    with (out/'feature_reconciliation.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(comparisons[0]))
        writer.writeheader(); writer.writerows(comparisons)
    report = dict(kind='business-data-review-on-synthetic-fixtures', run_at=datetime.now().astimezone().isoformat(),
                  fixture_sha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                  status='changes_required' if any(c['status'] == 'fail' for c in checks) else 'ready_for_human_review',
                  real_business_approval=False, checks=checks)
    (out/'review_checks.json').write_bytes(canonical(report))
    for c in checks:
        print(c['status'].upper()+': '+c['id']+(' -- '+c['error'] if c['status'] == 'fail' else ''))
    print('Reconciled cells:', len(comparisons), '| Passed:', sum(c['status'] == 'pass' for c in checks), '| Failed:', sum(c['status'] == 'fail' for c in checks))
    return 1 if report['status'] == 'changes_required' else 0


if __name__ == '__main__':
    raise SystemExit(main())
