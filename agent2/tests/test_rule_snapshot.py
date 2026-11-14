"""All retained rules through real import/preview/commit/analyze dispatch."""
from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from finance_input import AccessScope
from sme_fraud.import_files import canonical,ImportFailure
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.native_rule_demo import scenario
from sme_fraud.native_rule_node import REQUIRED
from sme_fraud.rule_snapshot import CONTRACT,catalogue,validate
from sme_fraud.snapshot_analysis import analyze_snapshot
from sme_fraud.rules import RULE_NAMES,score_rules
from test_snapshots import commit_fields


def scope(company='C001',actor='rules-reader',verify=False):return AccessScope('native-demo',frozenset({company}),actor,frozenset({'data.import','evidence.verify'} if verify else {'data.import'}))
def wrap(source,ids=None):return dict(contract_version=CONTRACT,tenant_id=source['tenant_id'],company_id=source['company_id'],source=deepcopy(source),candidate_transaction_ids=ids or [source['tables']['transactions'][-1]['transaction_id']])
def save(store,data,authority=None,key='rule-demo'):
    authority=authority or scope();draft=store.upload(authority,canonical(data),'rule-source.json',key+'-upload');p=store.preview(authority,draft['import_id'],1)
    if p['status']=='rejected':raise AssertionError(p['errors'])
    return store.commit(authority,draft['import_id'],commit_fields(p),key+'-commit'),draft,p


class RuleSnapshots(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.store=SnapshotStore(Path(self.tmp.name)/'snapshot.sqlite3')
    def analyze(self,data,authority=None,technical=True,key='rule-demo'):
        saved,_,_=save(self.store,data,authority,key);return analyze_snapshot(self.store,authority or scope(),saved['snapshot']['snapshot_id'],data['source']['as_of'],technical=technical)
    def test_every_evaluator_is_registered_with_explicit_profile_sources_and_he_limits(self):
        c=catalogue();self.assertEqual(len(c),35);self.assertEqual({r['rule_id'] for r in c},set(RULE_NAMES));self.assertTrue(all(r['implemented'] and r['required_tables'] for r in c));self.assertTrue(all(r['he_supported'] is False for r in c))
    def test_all_non_statistical_rules_run_positive_control_in_snapshot_pipeline(self):
        for code in RULE_NAMES:
            if code.startswith('D'):continue
            for positive in (True,False):
                with self.subTest(rule=code,positive=positive):
                    b,_=scenario(code,positive);data=wrap(b);r=self.analyze(data,key=code+str(positive));entry=next(x for x in r['catalogue_results'] if x['rule_id']==code)
                    self.assertTrue(entry['available']);self.assertEqual(entry['matched'],positive);self.assertEqual(len(r['rows'][0]['rule_coverage']['rules']),35);self.assertFalse(r['he_execution']);self.assertIsNone(r['aggregate']['score'])
    def test_native_engine_result_hash_and_input_immutability_survive_the_snapshot_route(self):
        from sme_fraud.import_files import digest
        b,_=scenario('B1',True);data=wrap(b);before=canonical(data);r=self.analyze(data)
        self.assertEqual(r['native_reference_sha256'],digest(canonical(score_rules(b['tables']))));self.assertEqual(canonical(data),before)
    def test_missing_sources_are_unavailable_not_no_hit_for_every_rule(self):
        b,_=scenario('B1',True);b['coverage']={};r=self.analyze(wrap(b))
        self.assertTrue(all(x['status'] in ('unavailable','not_applicable') and x['matched'] is None for x in r['catalogue_results']))
        self.assertEqual(r['summary']['unavailable_checks'],33)
    def test_payroll_rules_on_payment_are_not_applicable_not_no_hit(self):
        b,_=scenario('B1',True);r=self.analyze(wrap(b))
        for code in ('E1','E2'):
            entry=next(x for x in r['rows'][0]['rule_coverage']['rules'] if x['rule_id']==code);self.assertEqual(entry['status'],'not_applicable');self.assertIsNone(entry['matched']);self.assertIsNone(entry['score'])
    def test_empty_authority_and_attendance_exports_do_not_enable_legacy_fallback(self):
        from sme_fraud.import_files import digest
        for code,tables in [('C2',('approval_authorities','approval_authority_coverage')),('E1',('attendance',))]:
            b,_=scenario(code,True)
            for name in tables:b['tables'][name]=[];b['coverage'][name].update(record_count=0,records_sha256=digest(canonical([])))
            result=self.analyze(wrap(b),key='empty-'+code);entry=next(r for r in result['catalogue_results'] if r['rule_id']==code)
            self.assertFalse(entry['available']);self.assertIsNone(entry['matched']);self.assertTrue(entry['gaps'])
    def test_authority_coverage_outside_action_time_is_not_an_approved_matrix(self):
        from sme_fraud.import_files import digest
        b,_=scenario('C2',True)
        for r in b['tables']['approval_authority_coverage']:r['covered_through']='2024-12-31'
        b['coverage']['approval_authority_coverage']['records_sha256']=digest(canonical(b['tables']['approval_authority_coverage']))
        result=self.analyze(wrap(b));entry=next(r for r in result['catalogue_results'] if r['rule_id']=='C2');self.assertFalse(entry['available']);self.assertIsNone(entry['matched'])
    def test_unknown_contact_and_invoice_identity_are_not_no_hit(self):
        from sme_fraud.import_files import digest
        for code,table,field,value in [('B5','vendors','phone',None),('P1','transactions','invoice_number','')]:
            b,_=scenario(code,False);b['tables'][table][-1][field]=value;b['coverage'][table]['records_sha256']=digest(canonical(b['tables'][table]))
            r=self.analyze(wrap(b),key='unknown-'+code);entry=next(x for x in r['catalogue_results'] if x['rule_id']==code);self.assertFalse(entry['available']);self.assertIsNone(entry['matched'])
    def test_five_candidates_are_preserved_without_history_becoming_candidates(self):
        b,_=scenario('A5',True);ids=[r['transaction_id'] for r in b['tables']['transactions'][-5:]];r=self.analyze(wrap(b,ids));self.assertEqual(r['row_count'],5);self.assertEqual([x['transaction_id'] for x in r['rows']],ids)
    def test_scope_diagnostics_are_separate_from_transaction_points(self):
        b,_=scenario('F4',True);r=self.analyze(wrap(b));f=next(x for x in r['scope_results'] if x['rule_id']=='F4');self.assertTrue(f['matched'])
        row=next(x for x in r['rows'][0]['rule_coverage']['rules'] if x['rule_id']=='F4');self.assertEqual(row['status'],'not_applicable');self.assertIsNone(row['score']);self.assertEqual(row['scope_result_ref'],'F4')
    def test_review_view_hides_catalogue_codes_scores_and_native_implementation(self):
        b,_=scenario('C2',True);r=self.analyze(wrap(b),technical=False);self.assertNotIn('catalogue',r);self.assertNotIn('catalogue_results',r);self.assertNotIn('native_reference_sha256',r)
        forbidden={'rule_id','points','intrinsic_points','score','hits','implementation','threshold','native_reference_sha256'}
        def walk(value):
            if isinstance(value,dict):
                self.assertFalse(forbidden&set(value))
                for child in value.values():walk(child)
            elif isinstance(value,list):
                for child in value:walk(child)
        walk(r);checks=list(r['rows'][0]['checks'].values());self.assertTrue(any(x['needs_review'] for x in checks));self.assertTrue(all(x['next_action'] for x in checks))
    def test_wrong_company_tenant_candidates_and_source_checksum_are_rejected(self):
        b,_=scenario('B1',True);original=wrap(b)
        for kind in ('company','tenant','candidate','checksum'):
            data=deepcopy(original)
            if kind=='company':data['source']['tables']['vendors'][0]['company_id']='C002'
            elif kind=='tenant':data['source']['tenant_id']='other'
            elif kind=='candidate':data['candidate_transaction_ids']=['missing']
            else:data['source']['tables']['transactions'][0]['amount_vnd']+=1
            self.assertEqual(validate(data,scope())['status'],'rejected')
    def test_foreign_currency_and_malformed_profile_are_rejected_without_scoring(self):
        from sme_fraud.import_files import digest
        b,_=scenario('B1',True);data=wrap(b);data['source']['tables']['transactions'][0]['currency']='USD';data['source']['coverage']['transactions']['records_sha256']=digest(canonical(data['source']['tables']['transactions']))
        self.assertEqual(validate(data,scope())['errors'][0]['code'],'RULE_CURRENCY_UNSUPPORTED')
        data=wrap(b);data['source']['coverage']['employees']['record_count']=1.0;self.assertEqual(validate(data,scope())['status'],'rejected')
        b,_=scenario('C2',True);data=wrap(b);data['source']['tables']['approval_authority_coverage'][0]['coverage_end']='2026-12-31'
        self.assertEqual(validate(data,scope())['status'],'rejected')
    def test_read_permission_does_not_reverify_already_committed_real_source(self):
        b,_=scenario('B7',False);b['is_simulated']=False;data=wrap(b);self.assertEqual(validate(data,scope())['status'],'rejected')
        saved,_,_=save(self.store,data,scope(actor='verifier',verify=True));r=analyze_snapshot(self.store,scope(),saved['snapshot']['snapshot_id'],b['as_of']);self.assertEqual(r['row_count'],1)
    def test_source_cutoff_is_pinned_and_foreign_snapshot_reads_fail(self):
        b,_=scenario('B1',True);saved,_,_=save(self.store,wrap(b));sid=saved['snapshot']['snapshot_id']
        with self.assertRaises(ImportFailure):analyze_snapshot(self.store,scope(),sid,'2026-01-01T00:00:00+07:00')
        with self.assertRaises(ImportFailure):analyze_snapshot(self.store,scope('C002'),sid,b['as_of'])
    def test_repeat_commit_keeps_one_snapshot_and_changed_file_cannot_use_preview(self):
        b,_=scenario('B1',True);data=wrap(b);saved,draft,p=save(self.store,data)
        self.assertEqual(self.store.commit(scope(),draft['import_id'],commit_fields(p),'second-commit')['snapshot']['snapshot_id'],saved['snapshot']['snapshot_id'])
        other=self.store.upload(scope(),canonical(data),'other.json','other-upload');preview=self.store.preview(scope(),other['import_id'],1);changed=deepcopy(data);changed['candidate_transaction_ids']=[]
        self.store.revise(scope(),other['import_id'],1,'replace-source',raw=canonical(changed),filename='other.json')
        with self.assertRaises(ImportFailure):self.store.commit(scope(),other['import_id'],commit_fields(preview),'stale-commit')
    def test_pipeline_never_fits_models_or_calls_cloud(self):
        b,_=scenario('B1',True)
        with patch('sme_fraud.unsupervised_statistics.ShrunkMahalanobis.fit',side_effect=AssertionError('fit')),patch('experiments.he_inference.http_common.post',side_effect=AssertionError('cloud')):
            r=self.analyze(wrap(b));self.assertFalse(r['he_execution'])


if __name__=='__main__':unittest.main()
