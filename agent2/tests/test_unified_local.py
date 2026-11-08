"""One-port profile, explicit demo identity and lossless atomic ML transfer."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from sme_fraud.company_ml import CompanyML
from sme_fraud.data_import import DataImport
from sme_fraud.ml_review_web import MLReview
from sme_fraud.ml_workspace_merge import TABLES,inventory,plan_merge,merge_workspace
from sme_fraud.review_roles import ReviewPrincipal
from sme_fraud.review_server import demo_ml_manager,main
from sme_fraud.review_store import ReviewStore
from company_ml_fixture import CHIEF,label_text
from test_data_import import import_fixture
from test_ml_review_web import packet_fixture
from start_review import configured_command


class UnifiedLocalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.shared.cleanup)
        root=Path(cls.shared.name);packet=packet_fixture(root)
        store=ReviewStore(root/'source/data',root/'source/reports',root/'source/review.sqlite3')
        store.prepare();ml=CompanyML(store)
        with store.connection() as db:revision,_,records,_,_=ml._data(db,'C001')
        state=ml.update_labels('003','C001',CHIEF,expected_revision=revision,labels_text=label_text(records[:1]))
        revision=state['data']['revision']
        state=ml.evaluate('003','C001',CHIEF,expected_revision=revision,algorithm='ecod',alert_budget=.1,**state['data']['suggested_windows'])
        state=ml.activate('003','C001',CHIEF,expected_revision=revision,expected_active=None,version_id=state['versions'][0]['version_id'])
        ml.score('003','C001',CHIEF,expected_revision=revision,expected_active=state['active_version'])
        service=MLReview(store,[packet]);pid=service.overview(CHIEF)['packets'][0]['packet_id']
        rid=service.units(pid,CHIEF)['items'][0]['review_id'];service.timer(pid,rid,CHIEF,action='start',expected_revision=0)
        cls.original=store.database

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.source=self.root/'source.sqlite3'
        with closing(sqlite3.connect(self.original)) as src,closing(sqlite3.connect(self.source)) as dest:src.backup(dest)
        self.store,_=import_fixture(self.root/'target');self.store.prepare()
        self.ml=CompanyML(self.store);DataImport(self.ml);MLReview(self.store)
        self.target=self.store.database
        with self.store.connection() as db:
            self.cases=[tuple(r) for r in db.execute('SELECT * FROM cases ORDER BY scenario,case_id')]
            self.other_tables={t:[tuple(r) for r in db.execute('SELECT * FROM "'+t+'" ORDER BY rowid')]
                for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'") if t not in TABLES and t!='sqlite_sequence'}
    def source_inventory(self):
        with closing(sqlite3.connect(self.source)) as db:return inventory(db)
    def assert_target_preserved(self):
        with self.store.connection() as db:
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM cases ORDER BY scenario,case_id')],self.cases)
            for t,rows in self.other_tables.items():self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM "'+t+'" ORDER BY rowid')],rows,t)

    def test_merge_preserves_snapshots_artifacts_audits_reviews_and_all_legacy_tables(self):
        plan=plan_merge(self.source,self.target);self.assertEqual(plan['action'],'copy')
        result=merge_workspace(self.source,self.target,expected_plan=plan)
        self.assertGreater(result['rows_copied'],0)
        with self.store.connection() as db:
            self.assertEqual(inventory(db),self.source_inventory())
            _,_,_,_,labels=self.ml._data(db,'C001');self.assertEqual(len(labels),1)
        self.assert_target_preserved()
        state=self.ml.status('003','C001',CHIEF);self.assertEqual(len(state['versions']),1)
        result=self.ml.readiness('003','C001',CHIEF,**state['data']['suggested_windows'])
        self.assertTrue(result['model']['can_score'])
        service=MLReview(self.store);pid=service.overview(CHIEF)['packets'][0]['packet_id']
        self.assertGreater(service.units(pid,CHIEF)['total'],0)

    def test_repeating_the_same_merge_does_not_duplicate_rows(self):
        merge_workspace(self.source,self.target,expected_plan=plan_merge(self.source,self.target))
        repeat=plan_merge(self.source,self.target);self.assertEqual(repeat['action'],'already_present')
        self.assertEqual(merge_workspace(self.source,self.target,expected_plan=repeat)['rows_copied'],0)
        self.assert_target_preserved()

    def test_nonempty_conflicting_target_is_never_overwritten(self):
        self.ml.update_data('003','C001',CHIEF,expected_revision=None)
        with self.assertRaisesRegex(ValueError,'đã có dữ liệu ML khác'):plan_merge(self.source,self.target)
        self.assert_target_preserved()

    def test_source_change_after_plan_is_rejected_before_copy(self):
        plan=plan_merge(self.source,self.target)
        with closing(sqlite3.connect(self.source)) as db,db:db.execute("UPDATE company_ml_runs SET scores='[]'")
        with self.assertRaises(RuntimeError):merge_workspace(self.source,self.target,expected_plan=plan)
        with self.store.connection() as db:self.assertTrue(all(t['rows']==0 for t in inventory(db).values()))
        self.assert_target_preserved()

    def test_mid_copy_database_failure_rolls_back_every_ml_table(self):
        with self.store.connection() as db:
            db.execute("CREATE TRIGGER fail_copy BEFORE INSERT ON company_ml_runs BEGIN SELECT RAISE(ABORT,'SIM COPY FAILURE'); END")
        plan=plan_merge(self.source,self.target)
        with self.assertRaises(sqlite3.DatabaseError):merge_workspace(self.source,self.target,expected_plan=plan)
        with self.store.connection() as db:self.assertTrue(all(t['rows']==0 for t in inventory(db).values()))
        self.assert_target_preserved()

    def test_missing_company_and_same_source_destination_are_rejected(self):
        with self.store.connection() as db:db.execute("DELETE FROM companies WHERE company_id='C002'")
        with self.assertRaisesRegex(ValueError,'ngoài phạm vi'):plan_merge(self.source,self.target)
        with self.assertRaises(ValueError):plan_merge(self.source,self.source)

    def test_demo_identity_is_explicit_qa_and_company_scoped(self):
        with self.assertRaises(ValueError):demo_ml_manager(self.store,qa=False)
        actor=demo_ml_manager(self.store,qa=True)
        self.assertIsInstance(actor,ReviewPrincipal);self.assertEqual(actor.role,'chief_accountant')
        self.assertEqual(actor.company_ids,('C001','C002'));self.assertIn('MÔ PHỎNG',actor.display_name)

    def test_demo_cli_cannot_enable_manager_without_qa(self):
        with patch.object(sys,'argv',['review_server','--demo-ml-manager']),patch('sme_fraud.review_server.ReviewStore') as store:
            with self.assertRaises(SystemExit) as error:main()
            self.assertEqual(error.exception.code,2);store.assert_not_called()

    def test_saved_profile_builds_one_runtime_and_all_routes_on_same_port(self):
        profile=self.root/'session.json'
        profile.write_text(json.dumps(dict(version='review-local-session-v1',python_executable=sys.executable,
            python_path=['libs','tests'],data_root='data',reports_root='reports',database='main.sqlite3',
            qa=True,demo_ml_manager=True,ml_review_comparison=['packet'])),encoding='utf-8')
        command,env,checksum,path=configured_command(self.root,8765,'SIM_INSTANCE',profile)
        self.assertEqual(command[command.index('--port')+1],'8765');self.assertIn('--demo-ml-manager',command)
        self.assertIn('--qa',command);self.assertIn('--ml-review-comparison',command)
        self.assertEqual(command[command.index('--database')+1],str(self.root/'main.sqlite3'))
        self.assertIn(str((self.root/'libs').resolve()),env['PYTHONPATH']);self.assertEqual(len(checksum),64)
        self.assertEqual(Path(path).resolve(),profile.resolve())

    def test_saved_profile_rejects_role_without_qa_and_unknown_settings(self):
        for value in (dict(version='review-local-session-v1',demo_ml_manager=True),
                      dict(version='review-local-session-v1',unknown=True)):
            profile=self.root/'invalid.json';profile.write_text(json.dumps(value),encoding='utf-8')
            with self.assertRaises(ValueError):configured_command(self.root,8765,'SIM_INSTANCE',profile)


if __name__=='__main__':unittest.main()
