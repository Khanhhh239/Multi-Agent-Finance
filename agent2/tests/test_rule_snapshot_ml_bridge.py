"""Comprehensive acceptance & security tests for the 35-rule + 33-feature ML bridge."""
from contextlib import closing
import copy
from datetime import datetime, timedelta, timezone
import http.client
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from finance_input import AccessScope
import joblib

from sme_fraud.analysis_resources import AnalysisResources
from sme_fraud.auth import FileAuthorizer
from sme_fraud.import_files import canonical, digest, ImportFailure
from sme_fraud.method_adapters import LocalArtifact, fit_local_reference, score_batch
from sme_fraud.method_jobs import run_fit_job, run_score_job
from sme_fraud.method_store import MethodStore
from sme_fraud.ml_estimators import CompanyEstimator
from sme_fraud.native_rule_demo import scenario
from sme_fraud.review_server import make_server
from sme_fraud.rule_snapshot import CONTRACT, VERSION as RULE_ANALYSIS_VERSION, analyze as analyze_rule_snapshot, validate as validate_rule_snapshot
from sme_fraud.rule_snapshot_features import (
    UNMAPPED_COLUMNS,
    VERSION as BRIDGE_CONTRACT_VERSION,
    build_from_rule_snapshot,
    build_rule_feature_rows,
    feature_contract as rule_feature_contract,
)
from sme_fraud.snapshot_analysis import analyze_snapshot
from sme_fraud.snapshot_features import COLUMNS, build_feature_rows, feature_contract as canonical_feature_contract
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.unsupervised_statistics import RobustZ
from test_validation_backend import policy_for
from test_snapshots import commit_fields

TZ = timezone(timedelta(hours=7))


def _rehash(bundle):
    for table, rows in bundle['tables'].items():
        bundle['coverage'][table] = dict(
            bundle['coverage'][table],
            record_count=len(rows),
            records_sha256=digest(canonical(rows)),
        )
    return bundle


def _make_native_history_and_candidates(company='C001', *, amount_scale=1, overlap_candidate=False, reverse_order=False):
    """Build deterministic clean native-rule-source/1.0.0 bundle with history, reference, and 5 candidates."""
    bundle, _ = scenario('B1', False, company)
    bundle['tenant_id'] = 'demo'
    tables = bundle['tables']
    maker = tables['employees'][1]
    director = tables['employees'][0]
    worker = tables['employees'][2]
    vendor = copy.deepcopy(tables['vendors'][0])
    vendor['vendor_id'] = 'V_BRIDGE_01'
    vendor['name'] = 'Lotus Precision Engineering Co., Ltd'
    vendor['phone'] = '0909888777'
    vendor['address'] = '120 Le Loi, District 1, HCMC'
    vendor['tax_code'] = 'MST_BRIDGE_001'
    vendor['bank_account'] = worker['bank_account'] if overlap_candidate else 'BANK_CLEAN_8899'
    vendor['bank_code'] = 'SIMBANK'
    vendor['recorded_at'] = '2026-08-01T00:00:00+07:00'
    vendor['observed_at'] = '2026-08-01T00:00:00+07:00'
    # Replace clean vendors so unrelated generators cannot trigger name similarity.
    tx_template = copy.deepcopy(tables['transactions'][0])
    jl_template = copy.deepcopy(tables['journal_lines'][-1])
    tables['vendors'] = [vendor]
    tables['vendor_status_history'] = []
    tables['bank_account_changes'] = []
    tables['entity_links'] = []
    tables['transactions'] = []
    tables['journal_lines'] = []
    tables['transaction_documents'] = []

    def add_tx(tx_id, at, amount, *, doc=False, imbalance=0):
        ts = at.isoformat(timespec='seconds')
        tx = copy.deepcopy(tx_template)
        tx.update({
            'transaction_id': tx_id,
            'company_id': company,
            'txn_type': 'vendor_payment',
            'amount_vnd': int(amount),
            'currency': 'VND',
            'posted_at': ts,
            'observed_at': ts,
            'created_at': (at - timedelta(minutes=30)).isoformat(timespec='seconds'),
            'approved_at': ts,
            'effective_date': at.date().isoformat(),
            'creator_id': maker['employee_id'],
            'approver_id': director['employee_id'],
            'vendor_id': vendor['vendor_id'],
            'customer_id': '',
            'employee_id': '',
            'recipient_account': vendor['bank_account'],
            'recipient_bank_code': vendor['bank_code'],
            'counterparty_account': vendor['bank_account'],
            'payment_channel': 'bank',
            'support_doc_count': 2 if doc else 0,
            'goods_receipt_verified': 1,
            'invoice_issued_at': (at - timedelta(days=1)).isoformat(timespec='seconds'),
            'invoice_number': 'INV_' + tx_id,
            'invoice_gross_vnd': int(amount),
            'approval_limit_vnd': 50_000_000,
            'business_purpose': 'Synthetic bridge baseline ' + tx_id,
        })
        tables['transactions'].append(tx)
        jl1 = copy.deepcopy(jl_template)
        jl1.update(document_id='JD_' + tx_id, transaction_id=tx_id, company_id=company, posted_at=ts, observed_at=ts,
                   account_code='331', debit_vnd=int(amount), credit_vnd=0, vendor_id=vendor['vendor_id'], employee_id='', customer_id='')
        jl2 = copy.deepcopy(jl_template)
        jl2.update(document_id='JD_' + tx_id, transaction_id=tx_id, company_id=company, posted_at=ts, observed_at=ts,
                   account_code='112', debit_vnd=0, credit_vnd=int(amount) + int(imbalance), vendor_id=vendor['vendor_id'], employee_id='', customer_id='')
        tables['journal_lines'].extend([jl1, jl2])
        if doc:
            tables['transaction_documents'].append({
                'record_id': 'DOC_' + tx_id,
                'transaction_id': tx_id,
                'vendor_id': vendor['vendor_id'],
                'company_id': company,
                'document_type': 'invoice',
                'status': 'verified',
                'evidence_id': 'EV_' + tx_id,
                'verifier_id': director['employee_id'],
                'verified_at': ts,
                'observed_at': ts,
            })

    # History: 10 payments in Sept 1..10
    for i in range(10):
        add_tx(f'HIST_{i:02d}', datetime(2026, 9, 1 + i, 10, 0, tzinfo=TZ), (1_000_000 + i * 25_000) * amount_scale, doc=True)
    # Reference: 5 payments in Sept 15..19
    for i in range(5):
        add_tx(f'REF_{i:02d}', datetime(2026, 9, 15 + i, 10, 0, tzinfo=TZ), (1_020_000 + i * 20_000) * amount_scale, doc=True)
    # 5 Evaluation candidates in Oct 1..5 with identical IDs across companies; CAND_0..3 normal, CAND_4 magnitude anomaly.
    candidates = []
    cand_amounts = [1_050_000, 1_060_000, 1_075_000, 1_090_000, 95_000_000]
    for i, amt in enumerate(cand_amounts):
        cid = f'CAND_{i:02d}'
        candidates.append(cid)
        add_tx(cid, datetime(2026, 10, 1 + i, 11, 0, tzinfo=TZ), amt * amount_scale, doc=True, imbalance=(500_000 if i == 4 else 0))

    as_of = '2026-10-06T00:00:00+07:00'
    bundle['as_of'] = as_of
    for table, cov in bundle['coverage'].items():
        if isinstance(cov, dict):
            cov['status'] = 'complete'
            cov['observed_at'] = as_of
            if 'covered_from' in cov:
                cov['covered_from'] = '2023-01-01T00:00:00+07:00'
            if 'covered_through' in cov:
                cov['covered_through'] = as_of
            if 'history_basis' in cov:
                cov['history_basis'] = 'since_inception'
    if reverse_order:
        for tname in ('transactions', 'journal_lines', 'transaction_documents', 'vendors', 'employees'):
            tables[tname].reverse()
    _rehash(bundle)
    return dict(
        contract_version=CONTRACT,
        tenant_id='demo',
        company_id=company,
        source=bundle,
        candidate_transaction_ids=candidates,
    )


def _equivalent_canonical_from_native(wrapped):
    """Project mapped entities from a clean native bundle to an equivalent canonical 1.1.0 snapshot."""
    source = wrapped['source']
    tables = source['tables']
    company = wrapped['company_id']
    tenant = wrapped['tenant_id']
    kind_map = {'vendor_payment': 'payment', 'customer_receipt': 'receipt', 'payroll': 'payroll', 'adjustment': 'adjustment'}
    src_meta = dict(system='parity-test', record_id='SRC', is_simulated=bool(source.get('is_simulated', True)))

    jl_by_tx = {}
    for jl in tables['journal_lines']:
        tid = jl.get('transaction_id')
        if tid:
            jl_by_tx.setdefault(tid, []).append(dict(account=jl['account_code'], debit_vnd=jl['debit_vnd'], credit_vnd=jl['credit_vnd']))

    companies = [dict(
        tenant_id=tenant, company_id=company, record_id=company, revision=1,
        effective_at='2023-01-01T00:00:00+07:00', observed_at='2023-01-01T00:00:00+07:00',
        name='Parity DN ' + company, source=dict(src_meta, record_id=company),
    )]
    vendors = [dict(
        tenant_id=tenant, company_id=company, record_id=v['vendor_id'], revision=1,
        effective_at=v['recorded_at'], observed_at=v['observed_at'],
        name=v['name'], bank_account=v['bank_account'], bank_code=v['bank_code'],
        source=dict(src_meta, record_id=v['vendor_id']),
    ) for v in tables['vendors']]
    employees = [dict(
        tenant_id=tenant, company_id=company, record_id=e['employee_id'], revision=1,
        effective_at=e['recorded_at'], observed_at=e['observed_at'],
        name=e['full_name'], role=e['role'], bank_account=e['bank_account'], bank_code=e['bank_code'],
        source=dict(src_meta, record_id=e['employee_id']),
    ) for e in tables['employees']]
    transactions = []
    for tx in tables['transactions']:
        transactions.append(dict(
            tenant_id=tenant, company_id=company, record_id=tx['transaction_id'], revision=1,
            effective_at=tx['posted_at'], observed_at=tx['observed_at'],
            amount_vnd=tx['amount_vnd'], currency='VND', kind=kind_map[tx['txn_type']],
            description=tx.get('business_purpose', ''),
            vendor_ref=dict(record_id=tx['vendor_id'], revision=1),
            created_by_ref=dict(record_id=tx['creator_id'], revision=1),
            bank_account=tx.get('recipient_account', ''), bank_code=tx.get('recipient_bank_code', ''),
            accounting_lines=jl_by_tx.get(tx['transaction_id'], []),
            source=dict(src_meta, record_id=tx['transaction_id']),
        ))
    docs = [dict(
        tenant_id=tenant, company_id=company, record_id=(d.get('record_id') or d.get('document_id')), revision=1,
        effective_at=d['verified_at'], observed_at=d['observed_at'],
        subject_refs=[dict(table='transactions', record_id=d['transaction_id'], revision=1)],
        name='Doc ' + str(d.get('record_id') or d.get('document_id')),
        document_kind='invoice',
        verification_status='unverified',
        content_sha256=digest(canonical(d)),
        source_kind='simulated',
        source=dict(src_meta, record_id=(d.get('record_id') or d.get('document_id'))),
    ) for d in tables['transaction_documents']]
    return dict(
        contract_version='1.1.0', tenant_id=tenant,
        companies=companies, vendors=vendors, employees=employees,
        invoices=[], transactions=transactions, payment_allocations=[],
        approvals=[], supporting_documents=docs, vendor_bank_history=[],
    )


class RuleSnapshotMLBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.snapshots = SnapshotStore(self.base / 'snapshots.sqlite3')
        self.models = MethodStore(self.base / 'models.sqlite3')
        self.token = secrets.token_urlsafe(32)
        self.reader_token = secrets.token_urlsafe(32)
        self.policy = policy_for(self.token)
        owner = self.policy['principals'][0]
        owner['memberships'] = [
            dict(company_id=c, role='director', status='active', permissions=['data.import', 'model.fit'])
            for c in ('C001', 'C002')
        ]
        reader = copy.deepcopy(policy_for(self.reader_token)['principals'][0])
        reader['actor_id'] = 'accountant-reader'
        reader['tenant_id'] = 'demo'
        reader['memberships'] = [
            dict(company_id=c, role='accountant', status='active', permissions=['data.import'])
            for c in ('C001', 'C002')
        ]
        self.policy['principals'].append(reader)
        self.policy_file = self.base / 'policy.json'
        self._save_policy()
        self.auth = FileAuthorizer(self.policy_file)
        self.director_header = 'Bearer ' + self.token
        self.reader_header = 'Bearer ' + self.reader_token

    def _save_policy(self):
        self.policy_file.write_bytes(canonical(self.policy))

    def _scope(self, company='C001', *, reader=False):
        return self.auth.authorize(self.reader_header if reader else self.director_header, company)

    def _commit(self, data, company='C001', key='upload'):
        scope = self._scope(company)
        draft = self.snapshots.upload(scope, canonical(data), f'{key}.json', key + '-u')
        preview = self.snapshots.preview(scope, draft['import_id'], 1)
        self.assertNotEqual(preview['status'], 'rejected', preview.get('errors'))
        return self.snapshots.commit(scope, draft['import_id'], commit_fields(preview), key + '-c')['snapshot']['snapshot_id']

    def _fit_config(self, snapshot_id, method_id, *, missing_policy='median_flags'):
        return dict(
            version='company-fit-config/1.0.0',
            snapshot_id=snapshot_id,
            method_id=method_id,
            missing_policy=missing_policy,
            minimum_history=5,
            profile_id='sandbox-bridge-acceptance-only',
            evaluation_mode='backtest',
            history_start='2026-09-01T00:00:00+07:00',
            history_end='2026-09-12T00:00:00+07:00',
            reference_start='2026-09-15T00:00:00+07:00',
            reference_end='2026-09-20T00:00:00+07:00',
            evaluation_start='2026-10-01T00:00:00+07:00',
        )

    def _fit_all_methods(self, company, snapshot_id, methods=('robust_z', 'ecod', 'isolation_forest', 'lof', 'autoencoder'), prefix='fit'):
        artifacts = {}
        for m in methods:
            res = run_fit_job(
                self.snapshots, self.models, self.auth, self.director_header, company,
                self._fit_config(snapshot_id, m), f'{prefix}-{company}-{m}',
            )
            self.assertEqual(res['job']['status'], 'succeeded', res)
            artifacts[m] = res['job']['artifact_id']
        return artifacts

    def _write_bindings(self, bindings_by_company):
        path = self.base / 'bindings.json'
        rows = []
        for comp, arts in sorted(bindings_by_company.items()):
            ml_arts = {k: v for k, v in arts.items() if k != 'robust_z'}
            rows.append(dict(
                tenant_id='demo',
                company_id=comp,
                statistics_artifact_id=arts.get('robust_z'),
                ml_artifacts=ml_arts,
            ))
        path.write_bytes(canonical(dict(
            version='analysis-bindings/1.0.0',
            bindings=rows,
        )))
        return path

    # Acceptance 1, 2, 6(partial): C001/C002 5 candidates each, shared IDs, order-invariance, 0-rule-hit gets ML.
    def test_company_isolation_five_candidates_order_invariance_and_zero_rule_hit_ml(self):
        c1_data = _make_native_history_and_candidates('C001', amount_scale=1)
        c2_data = _make_native_history_and_candidates('C002', amount_scale=7, overlap_candidate=True)
        sid1 = self._commit(c1_data, 'C001', 'bridge-c1')
        sid2 = self._commit(c2_data, 'C002', 'bridge-c2')

        arts1 = self._fit_all_methods('C001', sid1, prefix='m1')
        arts2 = self._fit_all_methods('C002', sid2, prefix='m2')
        bindings = self._write_bindings({'C001': arts1, 'C002': arts2})
        resources = AnalysisResources(model_db=self.base / 'models.sqlite3', bindings_file=bindings)

        with (
            patch.object(CompanyEstimator, 'fit', side_effect=AssertionError('No fit during analyze')),
            patch.object(RobustZ, 'fit', side_effect=AssertionError('No fit during analyze')),
            patch.object(joblib, 'dump', side_effect=AssertionError('No write during analyze')),
        ):
            r1 = analyze_rule_snapshot(self.snapshots, self._scope('C001', reader=True), sid1, c1_data['source']['as_of'], technical=False, resources=resources)
            r2 = analyze_rule_snapshot(self.snapshots, self._scope('C002', reader=True), sid2, c2_data['source']['as_of'], technical=False, resources=resources)
            r1_tech = analyze_rule_snapshot(self.snapshots, self._scope('C001'), sid1, c1_data['source']['as_of'], technical=True, resources=resources)
            r2_tech = analyze_rule_snapshot(self.snapshots, self._scope('C002'), sid2, c2_data['source']['as_of'], technical=True, resources=resources)

        # Exactly 5 candidates preserved; history did not turn into candidates.
        self.assertEqual(r1['row_count'], 5)
        self.assertEqual(r2['row_count'], 5)
        self.assertEqual([r['transaction_id'] for r in r1['rows']], [f'CAND_{i:02d}' for i in range(5)])
        self.assertEqual([r['transaction_id'] for r in r2['rows']], [f'CAND_{i:02d}' for i in range(5)])

        # Zero-rule-hit transaction CAND_00 still receives ML and RobustZ scores.
        cand0_tech = r1_tech['rows'][0]
        self.assertEqual(cand0_tech['rule_coverage']['summary']['evaluated_hit'], 0)
        for m in ('robust_z', 'ecod', 'isolation_forest', 'lof', 'autoencoder'):
            self.assertTrue(cand0_tech['methods'][m]['available'], cand0_tech['methods'][m])
            self.assertIsNotNone(cand0_tech['methods'][m]['score'])
            self.assertIsNotNone(cand0_tech['methods'][m]['raw_score'])

        # Magnitude anomaly CAND_04 ranks strictly higher than normal CAND_00 under ECOD & RobustZ.
        cand4_tech = r1_tech['rows'][4]
        self.assertGreater(cand4_tech['methods']['ecod']['raw_score'], cand0_tech['methods']['ecod']['raw_score'])
        self.assertGreater(cand4_tech['methods']['robust_z']['raw_score'], cand0_tech['methods']['robust_z']['raw_score'])

        # Cross-company pin isolation & distinct values despite shared candidate IDs.
        self.assertEqual(r1_tech['rows'][0]['methods']['ecod']['artifact_id'], arts1['ecod'])
        self.assertEqual(r2_tech['rows'][0]['methods']['ecod']['artifact_id'], arts2['ecod'])
        self.assertNotEqual(r1_tech['rows'][0]['amount_vnd'], r2_tech['rows'][0]['amount_vnd'])
        self.assertEqual(r1_tech['branch_summary']['ml']['available'], 5)
        self.assertEqual(r1_tech['branch_summary']['statistics']['available'], 5)
        self.assertEqual(r1_tech['branch_summary']['graph']['available'] + r1_tech['branch_summary']['graph']['partial'], 5)
        self.assertEqual(r2['rows'][0]['branches']['graph']['findings'] != [], True)

        # Reversing source table order leaves features, missing masks, and scores unchanged.
        c1_rev = _make_native_history_and_candidates('C001', amount_scale=1, reverse_order=True)
        f_orig = build_rule_feature_rows(c1_data, self._scope('C001', reader=True), c1_data['source']['as_of'], candidates_only=True)
        f_rev = build_rule_feature_rows(c1_rev, self._scope('C001', reader=True), c1_rev['source']['as_of'], candidates_only=True)
        self.assertEqual(f_orig['features'], f_rev['features'])
        self.assertEqual(f_orig['missing'], f_rev['missing'])

    # Acceptance 3: Canonical vs full-source 33-col parity (no null->0), explicit gap/new contract incompatibility.
    def test_canonical_vs_full_source_33_col_parity_and_contract_gate(self):
        native_wrapped = _make_native_history_and_candidates('C001', amount_scale=1)
        canon_bundle = _equivalent_canonical_from_native(native_wrapped)
        as_of = native_wrapped['source']['as_of']

        native_frame = build_rule_feature_rows(native_wrapped, self._scope('C001'), as_of, candidates_only=False)
        canon_frame = build_feature_rows(canon_bundle, self._scope('C001'), as_of)
        self.assertEqual(native_frame['contract']['columns'], list(COLUMNS))
        self.assertEqual(canon_frame['contract']['columns'], list(COLUMNS))
        self.assertEqual(len(COLUMNS), 33)

        # Compare every mapped column on every aligned row (excluding columns where canonical & native structurally differ).
        canon_by_id = {r['record_id']: (r, f, m, e) for r, f, m, e in zip(canon_frame['rows'], canon_frame['features'], canon_frame['missing'], canon_frame['evidence'])}
        # creator_equals_approver in canonical requires approvals table (not creator_id/approver_id header); others map cleanly.
        structural_gap_cols = set(UNMAPPED_COLUMNS) | {'creator_equals_approver', 'known_invoice_count'}
        for nr, nf, nm, ne in zip(native_frame['rows'], native_frame['features'], native_frame['missing'], native_frame['evidence']):
            cr, cf, cm, ce = canon_by_id[nr['record_id']]
            self.assertEqual(nr['event_at'], cr['event_at'])
            self.assertEqual(nr['as_of'], cr['as_of'])
            self.assertEqual(ne['signed_amount_vnd'], ce['signed_amount_vnd'])
            for idx, col in enumerate(COLUMNS):
                if col in structural_gap_cols:
                    continue
                self.assertEqual(nm[idx], cm[idx], f'Mask mismatch on {nr["record_id"]}.{col}')
                if nf[idx] is not None:
                    self.assertAlmostEqual(nf[idx], cf[idx], places=7, msg=f'Value mismatch on {nr["record_id"]}.{col}')

        # Structurally absent columns stay None (never coerced to 0) with explicit reason.
        for nf, ne in zip(native_frame['features'], native_frame['evidence']):
            for col, reason in UNMAPPED_COLUMNS.items():
                idx = COLUMNS.index(col)
                self.assertIsNone(nf[idx])
                self.assertEqual(ne['missing_reasons'][col], reason)

        # Canonical model MUST be incompatible against rule-snapshot contract (no stale fingerprint copy).
        canon_sid = self._commit(canon_bundle, 'C001', 'canon-eq')
        native_sid = self._commit(native_wrapped, 'C001', 'native-eq')
        canon_fit = run_fit_job(self.snapshots, self.models, self.auth, self.director_header, 'C001', self._fit_config(canon_sid, 'ecod'), 'canon-fit')
        native_fit = run_fit_job(self.snapshots, self.models, self.auth, self.director_header, 'C001', self._fit_config(native_sid, 'ecod'), 'native-fit')
        self.assertEqual(canon_fit['job']['status'], 'succeeded')
        self.assertEqual(native_fit['job']['status'], 'succeeded')

        # Cross-contract scoring fails compatibility gate.
        canon_art = self.models.get_artifact(self._scope('C001'), canon_fit['job']['artifact_id'])
        native_cands = build_from_rule_snapshot(self.snapshots, self._scope('C001'), native_sid, as_of, candidates_only=True)
        cross_scored = score_batch(native_cands, self._scope('C001'), methods=('ecod',), artifacts={'ecod': canon_art})
        self.assertTrue(all(r['methods']['ecod']['reason']['code'] == 'artifact_incompatible' for r in cross_scored['rows']))

        # Same-business-source scoring via respective contract models ranks anomaly row equally high.
        res_native = run_score_job(self.snapshots, self.models, self.auth, self.reader_header, 'C001', native_sid, as_of, {'ecod': native_fit['job']['artifact_id']})
        res_canon = run_score_job(self.snapshots, self.models, self.auth, self.reader_header, 'C001', canon_sid, as_of, {'ecod': canon_fit['job']['artifact_id']})
        canon_scores = {r['record_id']: r['methods']['ecod']['raw_score'] for r in res_canon['rows'] if r['record_id'].startswith('CAND_')}
        native_scores = {r['record_id']: r['methods']['ecod']['raw_score'] for r in res_native['rows']}
        self.assertEqual(max(canon_scores, key=canon_scores.get), 'CAND_04')
        self.assertEqual(max(native_scores, key=native_scores.get), 'CAND_04')

    # Acceptance 4: Late documents, future master revisions, simultaneous batch, missing coverage/bank_code, signed/domain guards.
    def test_temporal_clocks_simultaneous_incomplete_coverage_and_domain_guards(self):
        base = _make_native_history_and_candidates('C001')
        as_of = '2026-10-08T00:00:00+07:00'
        base['source']['as_of'] = as_of
        for cov in base['source']['coverage'].values():
            if isinstance(cov, dict):
                cov['covered_through'] = as_of
                cov['observed_at'] = as_of
        _rehash(base['source'])
        baseline_frame = build_rule_feature_rows(base, self._scope(), as_of, candidates_only=True)

        # Late document + future vendor revision after CAND_00 cutoff do not change CAND_00 past features.
        mutated = copy.deepcopy(base)
        mutated['source']['tables']['transaction_documents'].append({
            'record_id': 'DOC_LATE', 'transaction_id': 'CAND_00', 'vendor_id': 'V_BRIDGE_01', 'company_id': 'C001',
            'document_type': 'invoice', 'status': 'verified', 'evidence_id': 'EV_LATE',
            'verifier_id': 'E0000001', 'verified_at': '2026-10-07T09:00:00+07:00', 'observed_at': '2026-10-07T09:00:00+07:00',
        })
        future_vendor = copy.deepcopy(mutated['source']['tables']['vendors'][0])
        future_vendor.update(bank_account='CHANGED_LATER', recorded_at='2026-10-07T10:00:00+07:00', observed_at='2026-10-07T10:00:00+07:00')
        mutated['source']['tables']['vendors'].append(future_vendor)
        _rehash(mutated['source'])
        after_late = build_rule_feature_rows(mutated, self._scope(), as_of, candidates_only=True)
        self.assertEqual(after_late['features'][0], baseline_frame['features'][0])

        # Simultaneous transactions on posted_at == observed_at do not see each other in history.
        sim = copy.deepcopy(base)
        sim['source']['tables']['transactions'] = [tx for tx in sim['source']['tables']['transactions'] if tx['transaction_id'] in ('CAND_00', 'CAND_01')]
        sim['candidate_transaction_ids'] = ['CAND_00', 'CAND_01']
        sim['source']['tables']['transactions'][0].update(posted_at='2026-10-02T11:00:00+07:00', observed_at='2026-10-02T11:00:00+07:00')
        sim['source']['tables']['transactions'][1].update(posted_at='2026-10-02T11:00:00+07:00', observed_at='2026-10-02T11:00:00+07:00')
        _rehash(sim['source'])
        sim_frame = build_rule_feature_rows(sim, self._scope(), as_of, candidates_only=True)
        idx_hist = COLUMNS.index('prior_type_history_log_count')
        self.assertEqual(sim_frame['features'][1][idx_hist], 0.0)

        # Missing bank_code on non-synthetic account must stay None (never default SIMBANK).
        nobank = copy.deepcopy(base)
        nobank['source']['tables']['vendors'][0]['bank_account'] = '00123456'
        nobank['source']['tables']['vendors'][0]['bank_code'] = ''
        for tx in nobank['source']['tables']['transactions']:
            tx['recipient_account'] = '00123456'
            tx['recipient_bank_code'] = ''
        _rehash(nobank['source'])
        nb_frame = build_rule_feature_rows(nobank, self._scope(), as_of, candidates_only=True)
        for col in ('employee_bank_overlap_observed', 'graph_employee_count_observed', 'graph_vendor_count_observed'):
            self.assertIsNone(nb_frame['features'][0][COLUMNS.index(col)])

        # Bounded history_basis keeps history columns None rather than 0.
        bounded = copy.deepcopy(base)
        bounded['source']['coverage']['transactions']['history_basis'] = 'bounded_period'
        _rehash(bounded['source'])
        b_frame = build_rule_feature_rows(bounded, self._scope(), as_of, candidates_only=True)
        for col in ('prior_type_history_log_count', 'log_abs_deviation_from_history', 'abs_amount_history_z'):
            self.assertIsNone(b_frame['features'][0][COLUMNS.index(col)])

        # Signed amounts keep their sign indicator and original evidence amount.
        zero_ok = copy.deepcopy(base)
        for tx in zero_ok['source']['tables']['transactions']:
            if tx['transaction_id'] == 'CAND_00':
                tx['amount_vnd'] = 0
                tx['txn_type'] = 'adjustment'
        _rehash(zero_ok['source'])
        z_frame = build_rule_feature_rows(zero_ok, self._scope(), as_of, candidates_only=True)
        self.assertEqual(z_frame['features'][0][COLUMNS.index('amount_zero')], 1)
        self.assertEqual(z_frame['features'][0][COLUMNS.index('log_abs_amount')], 0.0)
        self.assertIsNone(z_frame['features'][0][COLUMNS.index('journal_imbalance_abs_ratio')])

        neg = copy.deepcopy(base)
        neg['source']['tables']['transactions'][-1]['amount_vnd'] = -500_000
        _rehash(neg['source'])
        self.assertEqual(validate_rule_snapshot(neg, self._scope())['status'], 'accepted_with_warnings')
        negative_frame=build_rule_feature_rows(neg,self._scope(),as_of,candidates_only=True)
        negative_rows=[(f,e) for f,e in zip(negative_frame['features'],negative_frame['evidence']) if e['signed_amount_vnd']==-500_000]
        self.assertEqual(len(negative_rows),1)
        self.assertEqual(negative_rows[0][0][COLUMNS.index('amount_negative')],1)

    # Acceptance 5 & 6: Negative ML gates, strict/median_flags, batch outlier invariance, ID rename invariance.
    def test_negative_gates_strict_vs_median_flags_outlier_and_id_invariance(self):
        c1_data = _make_native_history_and_candidates('C001', amount_scale=1)
        c2_data = _make_native_history_and_candidates('C002', amount_scale=3)
        sid1 = self._commit(c1_data, 'C001', 'neg-c1')
        sid2 = self._commit(c2_data, 'C002', 'neg-c2')

        # Strict missing policy fails fit on native profile (because 8 unmapped columns are always None) with 0 artifacts written.
        strict_res = run_fit_job(self.snapshots, self.models, self.auth, self.director_header, 'C001', self._fit_config(sid1, 'ecod', missing_policy='strict'), 'strict-fit')
        self.assertEqual(strict_res['job']['status'], 'failed')
        self.assertEqual(strict_res['job']['failure_code'], 'FIT_DATA_INVALID')

        arts1 = self._fit_all_methods('C001', sid1, methods=('ecod', 'robust_z'), prefix='g1')
        arts2 = self._fit_all_methods('C002', sid2, methods=('ecod', 'robust_z'), prefix='g2')
        c1_frame = build_from_rule_snapshot(self.snapshots, self._scope('C001'), sid1, c1_data['source']['as_of'], candidates_only=True)

        # Wrong company artifact / unpinned / missing artifact -> unavailable.
        unpinned = analyze_rule_snapshot(self.snapshots, self._scope('C001'), sid1, c1_data['source']['as_of'], technical=True, resources=AnalysisResources())
        self.assertTrue(all(r['methods']['ecod']['reason']['code'] == 'binding_missing' for r in unpinned['rows']), unpinned['rows'][0]['methods']['ecod'])

        wrong_bindings = self._write_bindings({'C001': arts2})  # C002's artifact pinned under C001!
        wrong_res = analyze_rule_snapshot(self.snapshots, self._scope('C001'), sid1, c1_data['source']['as_of'], technical=True,
                                          resources=AnalysisResources(model_db=self.base / 'models.sqlite3', bindings_file=wrong_bindings))
        self.assertTrue(all(r['methods']['ecod']['reason']['code'] == 'artifact_missing' for r in wrong_res['rows']), wrong_res['rows'][0]['methods']['ecod'])

        # Reordered contract, future reference_end, training identity overlap, and corrupt payload.
        ecod_art = self.models.get_artifact(self._scope('C001'), arts1['ecod'])
        reordered = copy.deepcopy(c1_frame)
        reordered['contract']['columns'].reverse()
        unsigned = dict(reordered['contract']); unsigned.pop('fingerprint'); reordered['contract']['fingerprint'] = digest(canonical(unsigned))
        for row in reordered['features']:
            row.reverse()
        for row in reordered['missing']:
            row.reverse()
        future_m = json.loads(ecod_art.manifest); future_m['reference_end'] = '2026-10-06T00:00:00+07:00'
        future_art = LocalArtifact('mth_' + digest(canonical(future_m)), canonical(future_m), ecod_art.payload)

        with closing(sqlite3.connect(self.base / 'models.sqlite3')) as conn:
            with conn:
                conn.execute('DROP TRIGGER method_artifacts_update')
                conn.execute('UPDATE method_artifacts SET payload=? WHERE artifact_id=?', (b'corrupted', arts1['robust_z']))
        corrupt_art = None
        try:
            self.models.get_artifact(self._scope('C001'), arts1['robust_z'])
        except ImportFailure:
            pass
        bindings_ok = self._write_bindings({'C001': {'ecod': arts1['ecod'], 'robust_z': arts1['robust_z']}})
        res_corrupt = analyze_rule_snapshot(self.snapshots, self._scope('C001'), sid1, c1_data['source']['as_of'], technical=True,
                                            resources=AnalysisResources(model_db=self.base / 'models.sqlite3', bindings_file=bindings_ok))
        self.assertEqual(res_corrupt['rows'][0]['methods']['robust_z']['reason']['code'], 'artifact_invalid')

        with patch('sme_fraud.method_adapters.joblib.load', side_effect=AssertionError('Corrupt/incompatible model loaded')):
            bad_order = score_batch(reordered, self._scope('C001'), methods=('ecod',), artifacts={'ecod': ecod_art})
        bad_future = score_batch(c1_frame, self._scope('C001'), methods=('ecod',), artifacts={'ecod': future_art})
        overlap_frame = copy.deepcopy(c1_frame)
        overlap_frame['rows'][0]['record_id'] = 'HIST_00'
        bad_overlap = score_batch(overlap_frame, self._scope('C001'), methods=('ecod',), artifacts={'ecod': ecod_art})
        self.assertEqual(bad_order['rows'][0]['methods']['ecod']['reason']['code'], 'artifact_incompatible')
        self.assertEqual(bad_future['rows'][0]['methods']['ecod']['reason']['code'], 'artifact_from_future')
        self.assertEqual(bad_overlap['rows'][0]['methods']['ecod']['reason']['code'], 'artifact_training_overlap')

        # Adding a huge outlier candidate into batch never changes reference or scores of existing candidates.
        with_outlier = copy.deepcopy(c1_data)
        extra_tx = copy.deepcopy(with_outlier['source']['tables']['transactions'][-1])
        extra_tx['transaction_id'] = 'CAND_OUTLIER_EXTRA'
        extra_tx['amount_vnd'] = 900_000_000
        with_outlier['source']['tables']['transactions'].append(extra_tx)
        with_outlier['candidate_transaction_ids'].append('CAND_OUTLIER_EXTRA')
        _rehash(with_outlier['source'])
        sid_extra = self._commit(with_outlier, 'C001', 'with-extra-outlier')
        b_ecod_only = self._write_bindings({'C001': {'ecod': arts1['ecod']}})
        base_ecod = analyze_rule_snapshot(self.snapshots, self._scope('C001'), sid1, c1_data['source']['as_of'], technical=True,
                                          resources=AnalysisResources(model_db=self.base / 'models.sqlite3', bindings_file=b_ecod_only))
        extra_ecod = analyze_rule_snapshot(self.snapshots, self._scope('C001'), sid_extra, with_outlier['source']['as_of'], technical=True,
                                           resources=AnalysisResources(model_db=self.base / 'models.sqlite3', bindings_file=b_ecod_only))
        self.assertEqual(
            [r['methods']['ecod']['raw_score'] for r in base_ecod['rows']],
            [r['methods']['ecod']['raw_score'] for r in extra_ecod['rows'][:5]],
        )

        # Synchronous ID renaming preserves exact numeric features.
        renamed = copy.deepcopy(c1_data)
        id_map = {tx['transaction_id']: 'REN_' + tx['transaction_id'] for tx in renamed['source']['tables']['transactions']}
        for tx in renamed['source']['tables']['transactions']:
            tx['transaction_id'] = id_map[tx['transaction_id']]
        for jl in renamed['source']['tables']['journal_lines']:
            if jl.get('transaction_id') in id_map:
                jl['transaction_id'] = id_map[jl['transaction_id']]
        for doc in renamed['source']['tables']['transaction_documents']:
            if doc.get('transaction_id') in id_map:
                doc['transaction_id'] = id_map[doc['transaction_id']]
        renamed['candidate_transaction_ids'] = [id_map[cid] for cid in renamed['candidate_transaction_ids']]
        _rehash(renamed['source'])
        ren_frame = build_rule_feature_rows(renamed, self._scope('C001'), renamed['source']['as_of'], candidates_only=True)
        orig_frame = build_rule_feature_rows(c1_data, self._scope('C001'), c1_data['source']['as_of'], candidates_only=True)
        self.assertEqual(ren_frame['features'], orig_frame['features'])

    # Acceptance 7, 8, 9: 35-rule preservation, RBAC review redaction, retry/restart/binding change, revocation & HE boundary.
    def test_35_rule_preservation_rbac_retry_revocation_and_he_boundary(self):
        c1_data = _make_native_history_and_candidates('C001', overlap_candidate=True)
        sid = self._commit(c1_data, 'C001', 'preserve-c1')
        arts = self._fit_all_methods('C001', sid, methods=('ecod', 'robust_z'), prefix='p1')
        bindings = self._write_bindings({'C001': arts})
        res_with_ml = analyze_rule_snapshot(self.snapshots, self._scope('C001'), sid, c1_data['source']['as_of'], technical=True,
                                            resources=AnalysisResources(model_db=self.base / 'models.sqlite3', bindings_file=bindings))
        res_without_ml = analyze_rule_snapshot(self.snapshots, self._scope('C001'), sid, c1_data['source']['as_of'], technical=True,
                                               resources=AnalysisResources())

        # 35 rules identical before/after ML bridge.
        self.assertEqual(res_with_ml['native_reference_sha256'], res_without_ml['native_reference_sha256'])
        self.assertEqual(res_with_ml['catalogue_results'], res_without_ml['catalogue_results'])
        self.assertEqual([r['rule_coverage'] for r in res_with_ml['rows']], [r['rule_coverage'] for r in res_without_ml['rows']])
        self.assertEqual(res_with_ml['summary'], res_without_ml['summary'])

        # Pinning / changing bindings changes analysis_context_id and analysis_id; retry/restart preserves identical IDs.
        self.assertNotEqual(res_with_ml['analysis_id'], res_without_ml['analysis_id'])
        self.assertNotEqual(res_with_ml['analysis_context_id'], res_without_ml['analysis_context_id'])
        restarted_resources = AnalysisResources(model_db=self.base / 'models.sqlite3', bindings_file=bindings)
        retry_res = analyze_rule_snapshot(self.snapshots, self._scope('C001'), sid, c1_data['source']['as_of'], technical=True, resources=restarted_resources)
        self.assertEqual(retry_res['analysis_id'], res_with_ml['analysis_id'])
        self.assertEqual(retry_res['analysis_context_id'], res_with_ml['analysis_context_id'])

        # Accountant review view redacts raw scores, features, rule_ids, implementation even when ML available.
        review = analyze_rule_snapshot(self.snapshots, self._scope('C001', reader=True), sid, c1_data['source']['as_of'], technical=False, resources=restarted_resources)
        self.assertEqual(review['version'], RULE_ANALYSIS_VERSION)
        self.assertEqual(review['branch_summary']['ml']['available'], 5)
        forbidden = {'rule_id', 'points', 'intrinsic_points', 'score', 'raw_score', 'hits', 'implementation', 'threshold', 'native_reference_sha256', 'features', 'methods'}
        def walk(v):
            if isinstance(v, dict):
                self.assertFalse(forbidden & set(v), forbidden & set(v))
                for child in v.values():
                    walk(child)
            elif isinstance(v, list):
                for child in v:
                    walk(child)
        walk(review)

        # Mid-flight permission revocation & mid-flight binding change raise 409.
        calls = []
        def revoked_recheck():
            calls.append(1)
            return self._scope('C001') if len(calls) == 1 else self._scope('C002')
        with self.assertRaises(ImportFailure) as err_auth:
            analyze_rule_snapshot(self.snapshots, self._scope('C001'), sid, c1_data['source']['as_of'], recheck=revoked_recheck, resources=restarted_resources)
        self.assertEqual(err_auth.exception.status, 409)

        # HE boundary remains strictly separated (`he_execution=False`, and he_workbench rejects profile cleanly).
        self.assertFalse(res_with_ml['he_execution'])
        from sme_fraud.he_workbench import HEWorkbench
        from types import SimpleNamespace
        he_bindings = self.base / 'he_bindings.json'
        he_bindings.write_bytes(canonical(dict(
            version='he-ui-bindings/1.0.0',
            bindings=[dict(tenant_id='demo', company_id='C001', artifact_id='mth_' + ('a' * 64))],
        )))
        fake_node = SimpleNamespace(
            model_db=self.base / 'models.sqlite3',
            snapshot_db=self.base / 'snapshots.sqlite3',
            jobs=SimpleNamespace(submit=lambda *a, **k: (_ for _ in ()).throw(AssertionError('Must not submit HE'))),
        )
        backend = HEWorkbench(fake_node, he_bindings)
        with self.assertRaises(ImportFailure) as err_he:
            backend.submit(self._scope('C001'), lambda: self._scope('C001'), 'C001', self.director_header, 'he-boundary-test-key', dict(snapshot_id=sid))
        self.assertEqual(err_he.exception.status, 422)
        self.assertEqual(err_he.exception.code, 'HE_PROFILE_UNSUPPORTED')

    def test_http_endpoint_end_to_end_c001_c002_and_midflight_binding_change(self):
        import http.client
        import threading
        from sme_fraud.review_server import make_server

        c1_data = _make_native_history_and_candidates('C001', amount_scale=1)
        c2_data = _make_native_history_and_candidates('C002', amount_scale=5, overlap_candidate=True)
        sid1 = self._commit(c1_data, 'C001', 'http-bridge-c1')
        sid2 = self._commit(c2_data, 'C002', 'http-bridge-c2')
        arts1 = self._fit_all_methods('C001', sid1, prefix='http1')
        arts2 = self._fit_all_methods('C002', sid2, prefix='http2')
        bindings = self._write_bindings({'C001': arts1, 'C002': arts2})
        resources = AnalysisResources(model_db=self.base / 'models.sqlite3', bindings_file=bindings)

        server = make_server(0, authorizer=self.auth, snapshot_store=self.snapshots, analysis_resources=resources)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(timeout=2)))

        def post_json(path, token_header, payload):
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=30)
            try:
                conn.request(
                    'POST',
                    path,
                    body=canonical(payload),
                    headers={'Authorization': token_header, 'Content-Type': 'application/json'},
                )
                resp = conn.getresponse()
                return resp.status, json.loads(resp.read().decode('utf-8'))
            finally:
                conn.close()

        st_rev, body_rev = post_json(f'/api/v1/companies/C001/snapshots/{sid1}/analyze', self.reader_header, dict(as_of=c1_data['source']['as_of'], view='review'))
        self.assertEqual(st_rev, 200, body_rev)
        self.assertEqual(body_rev['row_count'], 5)
        self.assertEqual(body_rev['branch_summary']['ml']['available'], 5)
        self.assertNotIn('methods', body_rev['rows'][0])

        st_forbidden, _ = post_json(f'/api/v1/companies/C001/snapshots/{sid1}/analyze', self.reader_header, dict(as_of=c1_data['source']['as_of'], view='technical'))
        self.assertEqual(st_forbidden, 403)

        st_c1, body_c1 = post_json(f'/api/v1/companies/C001/snapshots/{sid1}/analyze', self.director_header, dict(as_of=c1_data['source']['as_of'], view='technical'))
        st_c2, body_c2 = post_json(f'/api/v1/companies/C002/snapshots/{sid2}/analyze', self.director_header, dict(as_of=c2_data['source']['as_of'], view='technical'))
        self.assertEqual(st_c1, 200, body_c1)
        self.assertEqual(st_c2, 200, body_c2)
        self.assertEqual([r['transaction_id'] for r in body_c1['rows']], [f'CAND_{i:02d}' for i in range(5)])
        self.assertEqual([r['transaction_id'] for r in body_c2['rows']], [f'CAND_{i:02d}' for i in range(5)])
        self.assertEqual(body_c1['rows'][0]['methods']['ecod']['artifact_id'], arts1['ecod'])
        self.assertEqual(body_c2['rows'][0]['methods']['ecod']['artifact_id'], arts2['ecod'])
        self.assertFalse(body_c1['he_execution'])
        self.assertFalse(body_c2['he_execution'])

        # Reload after changing pinned artifacts updates context & analysis IDs; mid-flight recheck raises 409.
        loaded = resources.load(self._scope('C001'))
        self._write_bindings({'C001': {'robust_z': arts1['robust_z'], 'ecod': arts1['ecod']}, 'C002': arts2})
        with self.assertRaises(ImportFailure) as err_bind:
            resources.recheck(self._scope('C001'), loaded)
        self.assertEqual(err_bind.exception.status, 409)
        st_c1_b, body_c1_b = post_json(f'/api/v1/companies/C001/snapshots/{sid1}/analyze', self.director_header, dict(as_of=c1_data['source']['as_of'], view='technical'))
        self.assertEqual(st_c1_b, 200)
        self.assertNotEqual(body_c1_b['analysis_context_id'], body_c1['analysis_context_id'])
        self.assertNotEqual(body_c1_b['analysis_id'], body_c1['analysis_id'])


if __name__ == '__main__':
    unittest.main()
