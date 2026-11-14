"""Persisted demo inputs, protected keys, no overwrite, and read-only reuse."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from finance_input import AccessScope
from experiments.he_inference.prepared_demo import prepare, check
from experiments.he_inference.protocol import read_json
from experiments.he_inference.registry_demo import database_dump
from experiments.he_inference.registry_export import ReadOnlySnapshots
from experiments.he_inference.key_manager import load_key, PROVIDER
from sme_fraud.import_files import digest


class PreparedCompanyDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='he prepared demo ')
        cls.root=Path(cls.temp.name)/'private packet'
        cls.manifest=prepare(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_each_company_has_five_evaluation_rows_and_own_model(self):
        self.assertEqual({i['company_id'] for i in self.manifest['companies']},{'C001','C002'})
        self.assertEqual(len({i['artifact_id'] for i in self.manifest['companies']}),2)
        for info in self.manifest['companies']:
            data=read_json(self.root/info['evaluation_file'])
            self.assertEqual(len(data['transactions']),5)
            self.assertEqual({t['record_id'] for t in data['transactions']},{'T0','T1','T2','T3','T4'})
            self.assertTrue(all(t['company_id']==info['company_id'] and t['source']['is_simulated'] for t in data['transactions']))

    def test_exported_bytes_match_the_immutable_source_upload(self):
        store=ReadOnlySnapshots(self.root/'enterprise/snapshots.sqlite3')
        for info in self.manifest['companies']:
            scope=AccessScope('demo',frozenset({info['company_id']}),'source-reader',frozenset({'data.import'}))
            for filename,snapshot in [('evaluation_file','evaluation_snapshot_id'),('history_file','training_snapshot_id')]:
                metadata=store.get_snapshot(scope,info[snapshot])
                self.assertEqual(metadata['source_hash'],digest((self.root/info[filename]).read_bytes()))

    def test_enterprise_keys_are_dpapi_and_no_standalone_credentials_remain(self):
        for purpose,name in [('node-signing','node-signing.dpapi.json'),('state-wrapping','state-wrapping.dpapi.json')]:
            key=load_key(self.root/'enterprise'/name,purpose=purpose,required_provider=PROVIDER)
            self.assertEqual(key.provider,PROVIDER)
            self.assertNotIn(key.material.hex().encode(),(self.root/'enterprise'/name).read_bytes())
        self.assertEqual(read_json(self.root/'enterprise/auth.json')['principals'],[])

    def test_prepare_again_refuses_and_preserves_existing_keys_and_models(self):
        files=[self.root/'enterprise/node-signing.dpapi.json',self.root/'enterprise/state-wrapping.dpapi.json',self.root/'enterprise/models.sqlite3']
        before=[p.read_bytes() for p in files]
        with self.assertRaises(FileExistsError):prepare(self.root)
        self.assertEqual(before,[p.read_bytes() for p in files])

    def test_opening_web_snapshot_store_keeps_locked_demo_valid(self):
        from sme_fraud.snapshots import SnapshotStore
        before=database_dump(self.root/'enterprise/snapshots.sqlite3')
        SnapshotStore(self.root/'enterprise/snapshots.sqlite3')
        self.assertEqual(before,database_dump(self.root/'enterprise/snapshots.sqlite3'))
        self.assertNotIn('enterprise/snapshots.sqlite3',self.manifest['source_sha256'])
        with patch('sme_fraud.unsupervised_statistics.ShrunkMahalanobis.fit',side_effect=AssertionError('no fit')):
            self.assertEqual(check(self.root)['status'],'passed')

    def test_checker_uses_separate_state_while_web_node_is_running(self):
        from experiments.he_inference.enterprise_server import load_node
        from experiments.he_inference.worker_store import WorkerStore
        from sme_fraud.auth import FileAuthorizer
        config=read_json(self.root/'enterprise/node.json')
        node=load_node(config,FileAuthorizer(config['auth_file']))
        worker=WorkerStore(self.root/'worker/state')
        before=database_dump(worker.path)
        try:
            self.assertEqual(check(self.root)['status'],'passed')
            self.assertEqual(database_dump(worker.path),before)
            self.assertTrue((self.root/'enterprise/check-state/jobs.sqlite3').exists())
            self.assertTrue((self.root/'worker/check-state/jobs.sqlite3').exists())
        finally:worker.close();node.jobs.close()

    def test_reopen_check_uses_saved_models_without_fit_and_keeps_job_ids(self):
        before={name:database_dump(self.root/'enterprise'/name) for name in ('models.sqlite3','snapshots.sqlite3')}
        with (patch('experiments.he_inference.prepared_demo.setup_demo',side_effect=AssertionError('no preparation while checking')),
              patch('sme_fraud.unsupervised_statistics.ShrunkMahalanobis.fit',side_effect=AssertionError('no fit while checking'))):
            first=check(self.root); second=check(self.root)
        self.assertEqual(first['status'],'passed');self.assertEqual(second['status'],'passed')
        self.assertEqual([c['run_id'] for c in first['companies']],[c['run_id'] for c in second['companies']])
        self.assertEqual(before,{name:database_dump(self.root/'enterprise'/name) for name in before})


if __name__=='__main__':unittest.main()
