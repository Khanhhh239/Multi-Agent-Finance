"""Real committed snapshots, point-in-time builders and no crypto/fit on reject."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.import_files import ImportFailure,canonical,digest
from experiments.he_training.protocol import TrainingError,sign,verify,sha
from experiments.he_training.snapshot_adapter import prepare_snapshot_training,ReadOnlySnapshots,COLUMNS
from experiments.he_training.enterprise import Enterprise
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from training_snapshot_support import native,canonical_source,scope,commit,request


class TrainingSnapshotAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.store=SnapshotStore(self.root/'snapshots.sqlite3');self.scope=scope()

    def plan(self,data,authority=None):
        authority=authority or self.scope;snapshot=commit(self.store,data,authority,key='p-'+digest(canonical(data))[:10]);q=request(snapshot,data)
        return prepare_snapshot_training(ReadOnlySnapshots(self.store.path),authority,q),q

    def test_both_profiles_map_existing_binary_features_without_scaling(self):
        for source in (native(),canonical_source()):
            with self.subTest(contract=source['contract_version']):
                before=canonical(source);p,q=self.plan(source)
                self.assertEqual(p['status'],'ready',p['issues']);self.assertEqual(p['x'],[[1,1],[0,0],[1,0],[0,1]])
                self.assertEqual(p['mapping']['columns'],list(COLUMNS));self.assertFalse(p['labels_included']);self.assertEqual(before,canonical(source))

    def test_same_transaction_ids_in_companies_are_scoped(self):
        a,qa=self.plan(native('C001'));b,qb=self.plan(native('C002'),scope('C002'))
        self.assertEqual(a['row_ids'],b['row_ids']);self.assertNotEqual(a['plan_sha256'],b['plan_sha256'])
        with self.assertRaises(ImportFailure):prepare_snapshot_training(self.store,scope('C002'),qa)

    def test_readonly_export_does_not_modify_db_or_require_evidence_verify(self):
        data=native();sid=commit(self.store,data,self.scope);before=hashlib.sha256(self.store.path.read_bytes()).hexdigest()
        p=prepare_snapshot_training(ReadOnlySnapshots(self.store.path),scope(permissions={'data.import'}),request(sid,data))
        self.assertEqual(p['status'],'ready');self.assertEqual(hashlib.sha256(self.store.path.read_bytes()).hexdigest(),before)

    def test_future_row_and_nonexistent_revision_are_kept_as_issues_not_dropped(self):
        data=native();sid=commit(self.store,data,self.scope);q=request(sid,data);q['as_of']='2025-08-11T11:30:00+07:00';q['training_end']=q['as_of']
        p=prepare_snapshot_training(self.store,self.scope,q);self.assertEqual(p['row_count'],4);self.assertEqual(p['status'],'rejected');self.assertIsNone(p['x']);self.assertIn('ROW_NOT_AVAILABLE_AT_AS_OF',{i['code'] for i in p['issues']})
        q=request(sid,data);q['rows'][0]['revision']=99
        p=prepare_snapshot_training(self.store,self.scope,q);self.assertIsNone(p['x']);self.assertFalse(p['rows'][0]['available'])

    def test_no_first_four_padding_or_duplicate_transactions(self):
        data=native();sid=commit(self.store,data,self.scope);q=request(sid,data)
        for rows in (q['rows'][:3],q['rows']+[q['rows'][0]],q['rows'][:3]+[q['rows'][0]]):
            with self.assertRaises(TrainingError):prepare_snapshot_training(self.store,self.scope,dict(q,rows=rows))

    def test_window_and_explicit_row_order_preserved(self):
        p,q=self.plan(native());swapped=dict(q,rows=list(reversed(q['rows'])))
        reverse=prepare_snapshot_training(self.store,self.scope,swapped);self.assertEqual(reverse['x'],list(reversed(p['x'])));self.assertNotEqual(reverse['plan_sha256'],p['plan_sha256'])
        changed=dict(q,training_start='2025-08-11T10:00:00+07:00');bad=prepare_snapshot_training(self.store,self.scope,changed);self.assertIn('ROW_OUTSIDE_TRAINING_WINDOW',{i['code'] for i in bad['issues']});self.assertIsNone(bad['x'])

    def test_partial_source_and_missing_approver_never_imputed_zero(self):
        for field in ('coverage','approver'):
            data=native()
            if field=='coverage':data['source']['coverage']['transactions']['status']='partial'
            else:
                data['source']['tables']['transactions'][0]['approver_id']=''
                data['source']['coverage']['transactions']['records_sha256']=digest(canonical(data['source']['tables']['transactions']))
            p,_=self.plan(data);self.assertEqual(p['status'],'rejected');self.assertIsNone(p['x']);self.assertIn('FEATURE_MISSING',{i['code'] for i in p['issues']})

    def test_late_approval_does_not_change_past_feature(self):
        data=canonical_source();first,_=self.plan(data)
        late=deepcopy(data['approvals'][0]);late.update(record_id='APP_LATE',observed_at='2026-10-01T18:00:00+07:00',employee_ref=dict(record_id='E002',revision=1));data['approvals'].append(late)
        after,_=self.plan(data);self.assertEqual(first['x'],after['x']);self.assertEqual(first['x'][0],[1,1])

    def test_future_coverage_claim_cannot_enable_historical_training(self):
        p,q=self.plan(native());q['as_of']='2025-08-11T13:00:00+07:00';q['training_end']=q['as_of']
        result=prepare_snapshot_training(self.store,self.scope,q)
        self.assertIsNone(result['x']);self.assertIn('FEATURE_SOURCE_NOT_KNOWN_AT_AS_OF',{i['code'] for i in result['issues']})

    def test_out_of_domain_does_not_round_clip_or_recode(self):
        from experiments.he_training import snapshot_adapter as a
        p,q=self.plan(native());original=a.build_from_rule_snapshot
        def invalid(*args,**kwargs):
            frame=original(*args,**kwargs);frame['features'][0][frame['contract']['columns'].index('round_million')]=1.00001;return frame
        with patch.object(a,'build_from_rule_snapshot',side_effect=invalid):bad=a.prepare_snapshot_training(self.store,self.scope,q)
        self.assertIsNone(bad['x']);self.assertIn('FEATURE_OUT_OF_DOMAIN',{i['code'] for i in bad['issues']})

    def test_stale_preview_and_changed_auth_prevent_encryption(self):
        p,q=self.plan(native());node=Enterprise.__new__(Enterprise);node.scope=self.scope;node.recheck=None
        with patch.object(node,'prepare') as encrypt:
            with self.assertRaisesRegex(TrainingError,'TRAINING_PREVIEW_STALE'):node.prepare_snapshot(self.store,q,expected_plan_sha256='0'*64)
            encrypt.assert_not_called()
            node.prepare_snapshot(self.store,q,expected_plan_sha256=p['plan_sha256']);self.assertEqual(encrypt.call_args.kwargs['provenance']['plan_sha256'],p['plan_sha256'])
        with self.assertRaises(ImportFailure):prepare_snapshot_training(self.store,self.scope,q,recheck=lambda:scope('C002'))

    def test_missing_db_does_not_create_storage(self):
        absent=self.root/'not-there.sqlite3'
        with self.assertRaises(ImportFailure):ReadOnlySnapshots(absent)
        self.assertFalse(absent.exists())

    def test_real_and_simulated_source_modes_not_silently_mixed(self):
        data=canonical_source();data['transactions'][0]['source']['is_simulated']=False
        p,_=self.plan(data);self.assertEqual(p['status'],'rejected');self.assertIn('MIXED_SOURCE_MODES',{x['code'] for x in p['issues']})
        for table in ('transactions','employees','approvals'):
            for record in data[table]:record['source']['is_simulated']=False
        p,_=self.plan(data);self.assertEqual(p['status'],'ready');self.assertFalse(p['simulated'])

    def test_cli_preview_and_rejection_do_not_provision_keys(self):
        from experiments.he_training import cli
        p,q=self.plan(native());request_path=self.root/'request.json';request_path.write_bytes(canonical(q))
        config=self.root/'config.json';config.write_bytes(canonical(dict(auth_file='fixture-only',snapshot_db=str(self.store.path),company_id='C001',expected_plan_sha256='0'*64)))
        token=self.root/'token';token.write_text('synthetic-test-token',encoding='ascii');output=self.root/'output.json'
        args=['encrypted_training.py','preview-snapshot','--config',str(config),'--token-file',str(token),'--data',str(request_path),'--output',str(output)]
        with patch.object(cli,'FileAuthorizer') as auth,patch.object(cli,'Enterprise') as crypto:
            auth.return_value.authorize.return_value=self.scope
            with patch('sys.argv',args):cli.main()
            crypto.assert_not_called();self.assertEqual(json.loads(output.read_bytes())['status'],'ready')
            output.unlink();args[1]='prepare-snapshot'
            with patch('sys.argv',args),self.assertRaisesRegex(TrainingError,'TRAINING_PREVIEW_STALE'):cli.main()
            crypto.assert_not_called()


if __name__=='__main__':unittest.main()
