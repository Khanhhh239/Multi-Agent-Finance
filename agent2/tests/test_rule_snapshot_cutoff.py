"""Candidate visibility must not abort or contaminate an analysis batch."""
from copy import deepcopy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from sme_fraud.analysis_resources import AnalysisResources
from sme_fraud.import_files import canonical, digest
from sme_fraud.native_rule_demo import scenario
from sme_fraud.review_server import make_server
from sme_fraud.rule_snapshot import validate
from sme_fraud.snapshot_analysis import analyze_snapshot
from sme_fraud.snapshot_features import feature_contract as canonical_contract
from sme_fraud.rule_snapshot_features import feature_contract as bridge_contract
from sme_fraud.snapshots import SnapshotStore
import sme_fraud.method_adapters as adapters
import test_rule_snapshot as helpers
import test_rule_snapshot_ml_bridge as ml_helpers


REASON = 'transaction_not_visible_at_as_of'


def rehash(data):
    for table, rows in data['source']['tables'].items():
        data['source']['coverage'][table].update(record_count=len(rows), records_sha256=digest(canonical(rows)))
    return data


def mixed(company='C001', *, only_future=False, no_visible_history=False):
    source, _ = scenario('B1', True, company)
    known = deepcopy(source['tables']['transactions'][-1])
    known['transaction_id'] = 'KNOWN'
    future = source['tables']['transactions'][-1]
    for field in ('observed_at', 'posted_at', 'created_at', 'approved_at'):
        future[field] = '2025-08-13T11:00:00+07:00'
    if not no_visible_history:
        source['tables']['transactions'].insert(0, known)
    candidates = [future['transaction_id']] if only_future else [future['transaction_id'], known['transaction_id']]
    return rehash(helpers.wrap(source, candidates))


class RuleSnapshotCutoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SnapshotStore(Path(self.temp.name) / 'snapshots.sqlite3')

    def analyze(self, data, *, technical=True, key='cutoff-check'):
        authority = helpers.scope(data['company_id'])
        saved, _, _ = helpers.save(self.store, data, authority, key)
        return analyze_snapshot(self.store, authority, saved['snapshot']['snapshot_id'], data['source']['as_of'], technical=technical)

    def assert_unavailable(self, row):
        self.assertFalse(row['availability']['available'])
        self.assertEqual(row['availability']['reason']['code'], REASON)
        self.assertTrue(all(r['status'] == 'unavailable' and r['matched'] is None and r['score'] is None
                            and r['reason'] == REASON and not r['hits'] for r in row['rule_coverage']['rules']))
        for result in row['methods'].values():
            self.assertFalse(result['available'])
            self.assertIsNone(result['raw_score'])
            self.assertIsNone(result['score'])
            self.assertEqual(result['reason']['code'], REASON)
            self.assertEqual(result['evidence_refs'], [])
        self.assertFalse(row['graph']['available'])
        self.assertEqual(row['feature_evidence']['records'], [])
        self.assertIsNone(row['feature_evidence']['signed_amount_vnd'])
        self.assertEqual(set(row['feature_missing_reasons'].values()), {REASON})
        self.assertTrue(all(b['status'] == 'unavailable' for b in row['branches'].values()))

    def test_mixed_batch_keeps_order_and_both_companies(self):
        for company in ('C001', 'C002'):
            with self.subTest(company=company):
                data = mixed(company)
                before = canonical(data)
                result = self.analyze(data, key='mixed-' + company)
                self.assertEqual(result['row_count'], 2)
                self.assertEqual([r['transaction_id'] for r in result['rows']], data['candidate_transaction_ids'])
                self.assert_unavailable(result['rows'][0])
                known = result['rows'][1]
                b1 = next(r for r in known['rule_coverage']['rules'] if r['rule_id'] == 'B1')
                self.assertEqual(b1['status'], 'evaluated_hit')
                self.assertEqual(result['summary']['unavailable_transactions'], 1)
                self.assertEqual(result['bridge_provenance']['candidate_transaction_ids'], ['KNOWN'])
                self.assertEqual(result['bridge_provenance']['requested_candidate_transaction_ids'], data['candidate_transaction_ids'])
                self.assertEqual(canonical(data), before)

    def test_future_only_candidates_do_not_invoke_predictor_or_replay_history(self):
        for no_history in (False, True):
            with self.subTest(no_visible_history=no_history), patch.object(adapters, 'score_batch', side_effect=AssertionError('No model scoring')):
                result = self.analyze(mixed(only_future=True, no_visible_history=no_history), key='all-future-' + str(no_history))
                self.assertEqual(result['row_count'], 1)
                self.assert_unavailable(result['rows'][0])
                self.assertEqual(result['bridge_provenance']['row_count'], 0)
                if no_history:
                    self.assertIsNone(result['native_reference_sha256'])
                    self.assertTrue(all(not r['available'] and r['matched'] is None for r in result['catalogue_results']))

    def test_review_future_row_is_not_a_no_signal_or_not_applicable_result(self):
        result = self.analyze(mixed(only_future=True, no_visible_history=True), technical=False)
        row = result['rows'][0]
        self.assertTrue(all(c['status'] == 'unavailable' and c['needs_review'] is None
                            and c['evidence_refs'] == [] and 'mốc phân tích' in c['reason']
                            for c in row['checks'].values()))
        self.assertNotIn('methods', row)
        self.assertNotIn('feature_contract', result)
        self.assertNotIn('native_reference_sha256', result)

    def test_cutoff_equality_is_visible_and_fictitious_ids_still_rejected(self):
        source, _ = scenario('B1', True)
        data = helpers.wrap(source)
        result = self.analyze(data)
        self.assertEqual(result['summary']['unavailable_transactions'], 0)
        self.assertTrue(any(r['available'] for r in result['rows'][0]['rule_coverage']['rules']))
        data['candidate_transaction_ids'] = ['DOES_NOT_EXIST']
        self.assertEqual(validate(data, helpers.scope())['status'], 'rejected')

    def test_known_observation_but_future_event_is_not_scored(self):
        data = mixed()
        tx = data['source']['tables']['transactions'][-1]
        for field in ('observed_at', 'created_at', 'approved_at'):
            tx[field] = data['source']['as_of']
        result = self.analyze(rehash(data))
        self.assert_unavailable(result['rows'][0])

    def test_real_model_scores_only_visible_candidates_and_preserves_scores(self):
        h = ml_helpers.RuleSnapshotMLBridgeTests()
        h.setUp()
        self.addCleanup(h.doCleanups)
        data = ml_helpers._make_native_history_and_candidates()
        sid = h._commit(data, key='fit-source')
        artifacts = h._fit_all_methods('C001', sid, methods=('robust_z', 'ecod'))
        resources = AnalysisResources(h.base / 'models.sqlite3', h._write_bindings({'C001': artifacts}))
        baseline = analyze_snapshot(h.snapshots, h._scope(), sid, data['source']['as_of'], technical=True, resources=resources)
        changed = deepcopy(data)
        future_id = changed['candidate_transaction_ids'][-1]
        tx = next(r for r in changed['source']['tables']['transactions'] if r['transaction_id'] == future_id)
        for field in ('observed_at', 'posted_at', 'created_at', 'approved_at'):
            tx[field] = '2026-10-07T11:00:00+07:00'
        rehash(changed)
        changed_sid = h._commit(changed, key='mixed-source')
        contracts = (canonical_contract()['fingerprint'], bridge_contract()['fingerprint'])
        with patch.object(adapters, 'score_batch', wraps=adapters.score_batch) as scorer:
            result = analyze_snapshot(h.snapshots, h._scope(), changed_sid, data['source']['as_of'], technical=True, resources=resources)
        self.assertEqual(result['row_count'], 5)
        frame = scorer.call_args.args[0]
        self.assertEqual([r['record_id'] for r in frame['rows']], data['candidate_transaction_ids'][:-1])
        for before, after in zip(baseline['rows'][:-1], result['rows'][:-1]):
            for method in ('robust_z', 'ecod'):
                self.assertTrue(after['methods'][method]['available'])
                self.assertEqual(after['methods'][method]['raw_score'], before['methods'][method]['raw_score'])
                self.assertEqual(after['methods'][method]['score'], before['methods'][method]['score'])
        self.assert_unavailable(result['rows'][-1])
        self.assertEqual(contracts, (canonical_contract()['fingerprint'], bridge_contract()['fingerprint']))

        # A real HTTP request retains the same five result rows and gate reasons.
        server = make_server(0, h.auth, h.snapshots, analysis_resources=resources)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=30)
            try:
                connection.request('POST', f'/api/v1/companies/C001/snapshots/{changed_sid}/analyze',
                                   canonical(dict(as_of=data['source']['as_of'], view='technical')),
                                   {'Authorization': h.director_header, 'Content-Type': 'application/json'})
                response = connection.getresponse()
                body = json.loads(response.read())
                self.assertEqual(response.status, 200, body)
                self.assertEqual(body['row_count'], 5)
                self.assert_unavailable(body['rows'][-1])
            finally:
                connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)
