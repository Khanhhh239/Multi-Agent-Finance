"""Budget, missingness, grouping, frozen choices and honest review metrics."""
from copy import deepcopy
from contextlib import closing
import json,sqlite3,tempfile,unittest
from pathlib import Path
from experiments.he4.p1_demo import scope
from sme_fraud.import_files import ImportFailure
from sme_fraud.selection_comparison import make_plan,report_for,score
from sme_fraud.comparison_store import ComparisonStore


def fixture():
    rows=[];cases=[]
    for i in range(1,8):
        rule=dict(available=i not in (5,6),status='not_applicable' if i==6 else 'unavailable' if i==5 else 'partial',matched=i==1,invoice_checks=[],simultaneous_checks=[])
        if i in (2,3):rule['simultaneous_checks']=[dict(matched=True,obligation=['V','I'])]
        rows.append(dict(record_id='T'+str(i),revision=1,branches=dict(rules=rule,ml=dict(available=True,raw_score={4:100,5:90,6:80}.get(i,10)))))
        cases.append(dict(record_id='T'+str(i),revision=1,case_id='case'+str(i),event_at='2026-10-03T08:00:00+07:00' if i in (2,3) else f'2026-10-{i+1:02d}T08:00:00+07:00',amount_vnd='1000000',evidence=[dict(simulated=True)],review=dict(revision=0,feedback=None,active_seconds=0)))
    return dict(version='he-four-branch-result/1.0.0',run_id='herun_'+'a'*32,company_id='C001',snapshot_id='snp_'+'a'*32,as_of='2026-11-01T00:00:00+07:00',row_count=len(rows),rows=rows),cases


def plan(result,cases):return make_plan(result,cases,dict(checksum='c'*64),dict(artifact_id='mth-private'))


class Selection(unittest.TestCase):
    def test_preserves_rule_alerts_including_group_and_uses_only_remaining_slots(self):
        result,cases=fixture();p=plan(result,cases)
        self.assertEqual([x[0] for x in p['baseline']],['T1','T2','T3'])
        self.assertEqual([x[0] for x in p['added']],['T4','T5']);self.assertEqual(len(p['combined']),5);self.assertEqual(p['removed'],[])
        self.assertEqual(len(p['rule_groups']),2);self.assertFalse(p['selection_uses_feedback']);self.assertFalse(p['operational_queue_changed'])
        r=report_for(p,cases);self.assertEqual(r['baseline']['metrics']['unused_slots'],2)
        self.assertEqual([e['rule_state'] for e in r['added']],['no_p1_hit','unavailable'])

    def test_no_reviews_are_not_zero_accuracy_or_zero_usefulness_or_zero_time(self):
        result,cases=fixture();r=report_for(plan(result,cases),cases)
        for name in ('baseline','combined'):
            m=r[name]['metrics'];self.assertIsNone(m['declared_precision_resolved']);self.assertIsNone(m['declared_precision_at_selected']);self.assertIsNone(m['declared_useful_transactions']);self.assertIsNone(m['saved_connected_seconds']);self.assertIsNone(m['accuracy']);self.assertIsNone(m['recall'])
        self.assertIsNone(r['delta']['declared_problem_transactions']);self.assertIsNone(r['delta']['declared_useful_transactions'])

    def test_feedback_changes_metrics_without_changing_plan_or_selection(self):
        result,cases=fixture();p=plan(result,cases);before=deepcopy(p)
        for i,c in enumerate(cases):
            c['review']=dict(revision=1,active_seconds=30,feedback=dict(outcome='confirmed_risk' if i==3 else 'legitimate',usefulness='yes' if i==3 else 'no'))
        r=report_for(p,cases)
        self.assertEqual(p,before);self.assertEqual(r['delta']['declared_problem_transactions'],1);self.assertEqual(r['delta']['declared_useful_transactions'],1)
        self.assertEqual(r['delta']['attributed_connected_seconds'],60)
        self.assertEqual(r['combined']['metrics']['declared_precision_at_selected'],.2)
        self.assertEqual(r['status'],'technical_only');self.assertEqual(r['label_status'],'insufficient_verified_labels');self.assertNotIn('mth-private',json.dumps(r))
        self.assertEqual(plan(result,cases)['baseline'],p['baseline']);self.assertEqual(plan(result,cases)['combined'],p['combined'])

    def test_inconclusive_is_reported_separately_and_does_not_become_false_alert(self):
        result,cases=fixture();p=plan(result,cases);cases[3]['review']=dict(revision=1,active_seconds=20,feedback=dict(outcome='inconclusive',usefulness='not_assessed'))
        m=report_for(p,cases)['combined']['metrics'];self.assertEqual(m['inconclusive'],1);self.assertEqual(m['resolved'],0);self.assertIsNone(m['declared_precision_resolved']);self.assertIsNone(m['declared_precision_at_selected'])

    def test_missing_and_bad_ml_scores_do_not_hide_rows_or_use_zero_fallback(self):
        result,cases=fixture()
        for row in result['rows']:row['branches']['ml']=dict(available=False,reason='artifact_missing',raw_score=None)
        p=plan(result,cases);self.assertEqual(p['baseline'],p['combined']);r=report_for(p,cases);self.assertEqual(r['coverage']['total_transactions'],7);self.assertEqual(r['coverage']['ml_unavailable'],7)
        for value in (True,float('nan'),float('inf'),-1,'20',None):self.assertIsNone(score(dict(available=True,raw_score=value)))
        self.assertEqual(score(dict(available=True,raw_score=0)),0)

    def test_ties_deterministic_and_changing_input_order_does_not_change_selection(self):
        result,cases=fixture()
        for row in result['rows']:row['branches']['ml']['raw_score']=10
        p=plan(result,cases);result['rows'].reverse();cases.reverse();other=plan(result,cases)
        self.assertEqual(p['baseline'],other['baseline']);self.assertEqual(p['combined'],other['combined'])

    def test_large_simultaneous_group_is_deferred_whole_not_sliced_to_budget(self):
        result,cases=fixture()
        for row,c in zip(result['rows'][:6],cases[:6]):
            row['branches']['rules']=dict(available=True,matched=False,simultaneous_checks=[dict(matched=True,obligation=['V','GIANT'])]);c['event_at']='2026-10-03T08:00:00+07:00'
        p=plan(result,cases);self.assertEqual(p['baseline'],[]);self.assertEqual(len(p['deferred_rule_alerts']),6);self.assertEqual([x[0] for x in p['combined']],['T7'])

    def test_duplicate_or_missing_rows_are_rejected(self):
        result,cases=fixture();cases.pop()
        with self.assertRaises(ImportFailure):plan(result,cases)


class Plans(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'plans.sqlite3';self.key=b'k'*32;self.store=ComparisonStore(self.path,self.key);self.result,self.cases=fixture();self.p=plan(self.result,self.cases)

    def test_idempotent_sealed_plan_survives_restart_and_feedback(self):
        first=self.store.put(scope('C001'),self.p);changed=deepcopy(self.p);changed['created_at']='later'
        self.assertEqual(first,self.store.put(scope('C001'),changed));self.assertEqual(first,ComparisonStore(self.path,self.key).get(scope('C001'),self.p['run_id']))
        self.assertNotIn(b'mth-private',self.path.read_bytes());self.assertIsNone(self.store.get(scope('C002'),self.p['run_id']))
        changed['combined']=[]
        with self.assertRaises(ImportFailure):self.store.put(scope('C001'),changed)
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM plans').fetchone()[0],1)
            with self.assertRaises(sqlite3.IntegrityError):conn.execute('DELETE FROM plans')

    def test_wrong_key_cannot_replace_store_and_owner_isolated(self):
        self.store.put(scope('C001'),self.p)
        with self.assertRaises(Exception):ComparisonStore(self.path,b'x'*32)
        self.assertIsNotNone(self.store.get(scope('C001'),self.p['run_id']))
        from dataclasses import replace
        self.assertIsNone(self.store.get(replace(scope('C001'),actor_id='other-reviewer'),self.p['run_id']))


if __name__=='__main__':unittest.main()
