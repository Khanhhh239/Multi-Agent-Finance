"""Normalized method outputs against real retained rules/estimators/graph."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from finance_input import AccessScope
import jsonschema
import numpy as np

from sme_fraud.import_files import canonical, digest, ImportFailure
from sme_fraud.method_adapters import fit_local_reference, score_batch, native_inputs, score_snapshot, LocalArtifact, METHODS
from sme_fraud.ml_estimators import CompanyEstimator
from sme_fraud.unsupervised_statistics import RobustZ
from sme_fraud.rules import score_rules
from sme_fraud.rule_audit_cases import Case
from sme_fraud.entity_graph import EntityGraph
from sme_fraud.snapshots import SnapshotStore
from test_snapshot_features import bundle, scope, committed, AS_OF

ROOT = Path(__file__).resolve().parents[1]
FROZEN = json.loads((ROOT/'tests/fixtures/retained_parity.json').read_text('utf-8'))
SCHEMA = json.loads((ROOT/'sme_fraud/method_scores.schema.json').read_text('utf-8'))


def frame(values, start, prefix):
    contract = dict(version='frozen-numeric-parity/1.0.0', columns=['f'+str(i) for i in range(len(values[0]))], dtype='float64')
    contract['fingerprint'] = digest(canonical(contract))
    origin = datetime.fromisoformat(start)
    rows = [dict(row_index=i, tenant_id='demo', company_id='C001', record_id=prefix+str(i), revision=1,
                 event_at=(origin+timedelta(seconds=i)).isoformat(), as_of=(origin+timedelta(seconds=i)).isoformat()) for i in range(len(values))]
    return dict(as_of=rows[-1]['as_of'], contract=contract, features=copy.deepcopy(values),
                missing=[[False]*len(values[0]) for r in values], rows=rows,
                evidence=[dict(row_index=i, records=[], missing_reasons={}) for i in range(len(rows))])


def native_case(start, trigger=False):
    case = Case()
    # Generator's uniform vendor names legitimately trigger E3. Use a distinct
    # source name for the clean-row routing example; keep all rule thresholds.
    case.vendor['name'] = 'Orchid marine instruments'
    for i in range(5):
        at = start+timedelta(days=7*i)
        kw = dict(created_at=at.isoformat(), approved_at=(at+timedelta(minutes=5)).isoformat())
        if trigger and i == 0:
            kw['approver_id'] = case.maker['employee_id']
        case.pay(at, int(case.maker['self_approval_limit_vnd'])+1 if trigger and i == 0 else 500003+137*i,
                 transaction_id=f'NATIVE_{start:%Y%m%d}_{i}', **kw)
    case.score()
    return native_inputs(case.tables, scope(), config=case.config), case


class MethodAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.history = frame(FROZEN['train'], '2025-01-01T00:00:00+07:00', 'H')
        cls.reference = frame(FROZEN['test'], '2025-02-01T00:00:00+07:00', 'R')
        cls.test = frame(FROZEN['test'], '2025-03-01T00:00:00+07:00', 'T')
        cls.artifacts = {m:fit_local_reference(cls.history, cls.reference, scope(), m,
            selected_columns=cls.history['contract']['columns'], minimum_history=5,
            profile_id='r2-technical-parity-only-not-production') for m in METHODS}

    def validate(self, result):
        jsonschema.validate(result, SCHEMA)
        self.assertEqual(result['row_count'], len(result['rows']))

    def test_all_native_rule_scores_hits_and_exceptions_are_preserved(self):
        (features, rules, graphs), case = native_case(datetime(2025,8,12,11,tzinfo=timezone(timedelta(hours=7))), trigger=True)
        baseline = score_rules(case.tables, config=case.config)
        result = score_batch(features, scope(), methods=(), rule_output=rules, graphs=graphs)
        self.validate(result)
        by_id = {r['transaction_id']:r for r in baseline['scores']}
        for row in result['rows']:
            score = row['methods']['rules']
            self.assertEqual(score['score'], by_id[row['record_id']]['rule_score'])
            self.assertEqual(score['details']['native_score'], by_id[row['record_id']])
            self.assertEqual(score['details']['hits'], [h for h in baseline['hits'] if h['transaction_id'] == row['record_id']])
            graph=EntityGraph(case.tables,'C001',row['as_of'])
            raw=graph.to_json([graph.actor('vendor',case.vendor['vendor_id'])],depth=2,max_nodes=None)
            for field in ('nodes','links','findings','information_gaps'):
                self.assertEqual(row['graph'][field],raw[field])
        permitted=Case(); permitted.vendor['name']='Orchid marine instruments'
        permitted.pay(amount=int(permitted.maker['self_approval_limit_vnd']),approver_id=permitted.maker['employee_id'])
        original=permitted.score()
        f,r,g=native_inputs(permitted.tables,scope(),config=permitted.config)
        adapted=score_batch(f,scope(),methods=(),rule_output=r,graphs=g)
        self.assertTrue(any(h['rule_id']=='C2' and h['suppressed_reason'] for h in original['hits']))
        self.assertEqual(adapted['rows'][0]['methods']['rules']['details']['hits'],original['hits'])

    def test_float_parity_all_retained_ml_and_statistics(self):
        result = score_batch(self.test, scope(), artifacts=self.artifacts)
        self.validate(result)
        for method in METHODS:
            expected = FROZEN['statistics']['RobustZ'] if method == 'robust_z' else FROZEN['estimators'][method]['scores']
            actual = [r['methods'][method]['raw_score'] for r in result['rows']]
            np.testing.assert_allclose(actual, expected, atol=1e-8, rtol=1e-6)

    def test_no_hit_native_rows_still_receive_available_ml_scores(self):
        tz = timezone(timedelta(hours=7))
        (history, _, _), _ = native_case(datetime(2025,1,7,11,tzinfo=tz))
        (reference, _, _), _ = native_case(datetime(2025,6,3,11,tzinfo=tz))
        (test, rules, graphs), _ = native_case(datetime(2025,8,12,11,tzinfo=tz), trigger=True)
        artifact = fit_local_reference(history, reference, scope(), 'ecod',
            selected_columns=['log_amount','amount_limit_ratio','hour_sin'], minimum_history=5, profile_id='native-routing-demo-only')
        result = score_batch(test, scope(), methods=('ecod',), artifacts={'ecod':artifact}, rule_output=rules, graphs=graphs)
        self.validate(result)
        no_hit = [r for r in result['rows'] if r['methods']['rules']['score'] == 0]
        self.assertTrue(no_hit, 'Need an actual zero-point native rule result, not a mocked flag')
        self.assertTrue(all(r['methods']['ecod']['available'] for r in result['rows']))
        self.assertEqual(len(result['rows']), 5)

    def test_missing_artifact_is_null_and_inference_never_fits(self):
        with patch.object(CompanyEstimator, 'fit', side_effect=AssertionError('Inference fit')), patch.object(RobustZ, 'fit', side_effect=AssertionError('Inference fit')):
            missing = score_batch(self.test, scope())
            available = score_batch(self.test, scope(), artifacts=self.artifacts)
        self.validate(missing); self.validate(available)
        for row in missing['rows']:
            for method in METHODS:
                self.assertFalse(row['methods'][method]['available'])
                self.assertIsNone(row['methods'][method]['score'])
                self.assertEqual(row['methods'][method]['reason']['code'], 'artifact_missing')

    def test_extreme_batch_does_not_change_reference_or_prior_scores(self):
        normal = score_batch(self.test, scope(), artifacts=self.artifacts)
        extreme = copy.deepcopy(self.test)
        extreme['features'][-1] = [1e12]*len(extreme['contract']['columns'])
        snapshots = {m:(a.manifest,a.payload) for m,a in self.artifacts.items()}
        later = score_batch(extreme, scope(), artifacts=self.artifacts)
        for before, after in zip(normal['rows'][:-1], later['rows'][:-1]):
            self.assertEqual(before['methods'], after['methods'])
        self.assertTrue(all((a.manifest,a.payload)==snapshots[m] for m,a in self.artifacts.items()))

    def test_missing_selected_feature_keeps_every_row(self):
        changed = copy.deepcopy(self.test)
        changed['features'][0][0] = None; changed['missing'][0][0] = True
        changed['evidence'][0]['missing_reasons'] = {'f0':'source_unavailable'}
        result = score_batch(changed, scope(), artifacts=self.artifacts)
        self.validate(result)
        self.assertEqual(len(result['rows']), 5)
        for method in METHODS:
            first = result['rows'][0]['methods'][method]
            self.assertIsNone(first['raw_score']); self.assertIsNone(first['score'])
            self.assertEqual(first['missing_features'], ['f0'])
            self.assertEqual(first['reason']['code'], 'features_missing')
            self.assertTrue(all(r['methods'][method]['available'] for r in result['rows'][1:]))

    def test_every_requested_adapter_returns_five_rows_without_top_k(self):
        result = score_batch(self.test, scope(), artifacts=self.artifacts)
        self.assertEqual([r['record_id'] for r in result['rows']], ['T0','T1','T2','T3','T4'])
        for method in METHODS:
            self.assertEqual(sum(method in r['methods'] for r in result['rows']), 5)

    def test_future_or_incompatible_artifact_is_unavailable(self):
        future = score_batch(self.reference, scope(), artifacts=self.artifacts)
        for method in METHODS:
            self.assertTrue(all(r['methods'][method]['reason']['code']=='artifact_from_future' for r in future['rows']))
        changed = copy.deepcopy(self.test)
        changed['contract']['version'] = 'incompatible'
        unsigned = dict(changed['contract']); unsigned.pop('fingerprint')
        changed['contract']['fingerprint'] = digest(canonical(unsigned))
        bad = score_batch(changed, scope(), artifacts=self.artifacts)
        self.assertTrue(all(r['methods']['ecod']['reason']['code']=='artifact_incompatible' for r in bad['rows']))

    def test_fit_rejects_overlap_and_silent_imputation(self):
        args = dict(selected_columns=['f0'], minimum_history=5, profile_id='technical-only')
        with self.assertRaises(ValueError):fit_local_reference(self.history,self.history,scope(),'ecod',**args)
        missing = copy.deepcopy(self.history); missing['features'][0][0]=None; missing['missing'][0][0]=True
        with self.assertRaises(ValueError):fit_local_reference(missing,self.reference,scope(),'ecod',**args)
        overlap=copy.deepcopy(self.reference); overlap['rows'][0]['record_id']='H0'
        with self.assertRaises(ValueError):fit_local_reference(self.history,overlap,scope(),'ecod',**args)
        query=copy.deepcopy(self.test); query['rows'][0]['record_id']='H0'
        result=score_batch(query,scope(),methods=('ecod',),artifacts=self.artifacts)
        self.assertEqual(result['rows'][0]['methods']['ecod']['reason']['code'],'artifact_training_overlap')

    def test_wrong_scope_and_corrupt_artifact_do_not_return_scores(self):
        with self.assertRaises(ImportFailure):score_batch(self.test, scope('C002'), artifacts=self.artifacts)
        a = self.artifacts['ecod']; manifest = json.loads(a.manifest)
        manifest['company_id']='C002'
        foreign = LocalArtifact('mth_'+digest(canonical(manifest)),canonical(manifest),a.payload)
        with self.assertRaises(ImportFailure):score_batch(self.test,scope(),methods=('ecod',),artifacts={'ecod':foreign})
        corrupt = LocalArtifact(a.artifact_id,a.manifest,a.payload+b'corrupt')
        result = score_batch(self.test,scope(),methods=('ecod',),artifacts={'ecod':corrupt})
        self.assertTrue(all(r['methods']['ecod']['reason']['code']=='artifact_invalid' for r in result['rows']))
        foreign_graph=dict(available=True,reason=None,nodes=[],links=[],findings=[],information_gaps=[],evidence_refs=[],
                           scope=dict(company_id='C002',as_of=self.test['rows'][0]['as_of']))
        with self.assertRaises(ImportFailure):score_batch(self.test,scope(),methods=(),graphs={('T0',1):foreign_graph})
        future=copy.deepcopy(foreign_graph); future['scope'].update(company_id='C001',as_of='2027-01-01T00:00:00+07:00')
        with self.assertRaises(ValueError):score_batch(self.test,scope(),methods=(),graphs={('T0',1):future})

    def test_snapshot_graph_is_source_backed_and_unsupported_rules_are_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=SnapshotStore(Path(temporary)/'snapshot.sqlite3'); identity=committed(store)
            result=score_snapshot(store,scope(),identity,AS_OF,methods=('ecod',))
            self.validate(result)
            self.assertEqual(len(result['rows']),3)
            for row in result['rows']:
                self.assertFalse(row['methods']['rules']['available'])
                self.assertEqual(row['methods']['rules']['reason']['code'],'rules_incomplete')
                results=row['methods']['rules']['details']['rule_results']['rules']
                self.assertEqual(next(r for r in results if r['rule_id']=='C2')['reason']['code'],'rule_sources_unavailable')
                self.assertTrue(row['graph']['available'])
                self.assertTrue(row['graph']['links'])
                self.assertNotIn('score',row['graph'])
                self.assertTrue(all(datetime.fromisoformat(ref['observed_at'])<=datetime.fromisoformat(row['as_of']) for ref in row['graph']['evidence_refs']))

    def test_demo_scores_new_snapshot_rows_and_retains_unavailable_old_rows(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'output.json'
            p=subprocess.run([sys.executable,'-X','utf8','-B',str(ROOT/'scripts/demo_method_scores.py'),
                '--output',str(output),'--database',str(Path(temporary)/'snapshot.sqlite3')],capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            demo=json.loads(output.read_text('utf-8')); self.validate(demo['canonical']); self.validate(demo['native'])
            self.assertEqual(demo['canonical']['row_count'],20)
            new=[r for r in demo['canonical']['rows'] if r['record_id'].startswith('T')]
            self.assertEqual(len(new),5)
            self.assertTrue(all(r['methods']['ecod']['available'] for r in new))
            self.assertTrue(all(r['methods']['rules']['score'] is None for r in new))
            old=[r for r in demo['canonical']['rows'] if not r['record_id'].startswith('T')]
            self.assertTrue(all(r['methods']['ecod']['reason']['code']=='artifact_from_future' for r in old))

    def test_snapshot_revocation_before_return_blocks_all_scores(self):
        from sme_fraud.method_adapters import score_batch as actual
        with tempfile.TemporaryDirectory() as temporary:
            store=SnapshotStore(Path(temporary)/'snapshot.sqlite3'); identity=committed(store); revoked=[False]
            def check(): return scope('C002') if revoked[0] else scope()
            def revoke(*args,**kwargs):
                result=actual(*args,**kwargs); revoked[0]=True; return result
            with patch('sme_fraud.method_adapters.score_batch',side_effect=revoke),self.assertRaises(ImportFailure) as error:
                score_snapshot(store,scope(),identity,AS_OF,recheck=check)
            self.assertEqual(error.exception.code,'AUTH_CONTEXT_CHANGED')


if __name__=='__main__':unittest.main()
