"""Four-rule baseline scope, source/model pins and fixed-budget selection."""
from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from sme_fraud.snapshots import SnapshotStore
from sme_fraud.method_adapters import score_snapshot
from sme_fraud.expanded_selection import compare
from experiments.he4.p1_demo import source,scope,save_snapshot

AS_OF='2026-10-09T00:00:00+07:00'


def fixture():
    data=source('C001');data['contract_version']='1.2.0'
    for v in data['vendors']:v.update(phone='0902000001',address='SIMULATED ADDRESS',related_party_disclosed_at='')
    with tempfile.TemporaryDirectory() as d:
        store=SnapshotStore(Path(d)/'snapshot.sqlite3');sid=save_snapshot(store,'C001',data);local=score_snapshot(store,scope('C001'),sid,AS_OF,methods=())
    receipt=dict(snapshot=local['snapshot'],as_of=AS_OF,feature_contract_fingerprint=local['feature_contract_fingerprint'],company_id='C001',tenant_id='demo',artifact_id='pinned',model_version='version',reference_version='ref',fit_job_id='job',selected_columns=['a','b'],preprocess_sha256='hash',reference_end='2026-09-20T00:00:00+07:00')
    ml=dict(receipt=receipt,row_count=8,rows=[dict(record_id=r['record_id'],revision=r['revision'],available=r['record_id']!='P1_T08',raw_score=100 if r['record_id']=='P1_T04' else 90 if r['record_id']=='P1_T02' else 1) for r in local['rows']])
    return local,ml


class ExpandedSelection(unittest.TestCase):
    def setUp(self):self.local,self.ml=fixture()
    def compare(self):return compare(self.local,self.ml,AS_OF,simulated_only=True)
    def test_rules_first_preserves_groups_and_fills_only_unused_slots(self):
        p=self.compare();self.assertEqual([k[0] for k in p['baseline']],['P1_T03','P1_T06','P1_T07']);self.assertEqual([k[0] for k in p['added']],['P1_T04','P1_T02']);self.assertEqual(len(p['combined']),5);self.assertEqual(p['removed'],[])
        self.assertEqual(p['baseline_rule_ids'],['P1','E3','B5','E4']);self.assertEqual(p['transaction_priority_rule_ids'],['P1']);self.assertFalse(p['all_rule_evaluations_he']);self.assertEqual(p['not_yet_adapted_rule_count'],31)
    def test_master_hits_never_promote_or_double_count_transaction_alerts(self):
        before=self.compare()
        for row in self.local['rows']:
            for r in row['methods']['rules']['details']['rule_results']['rules']:
                if r['rule_id'] in ('B5','E4'):r.update(status='evaluated_hit',available=True,matched=True,score=0)
        after=self.compare();self.assertEqual(before['baseline'],after['baseline']);self.assertEqual(before['combined'],after['combined']);self.assertTrue(all(r['master_hits']==['B5','E4'] for r in after['records']))
    def test_unknown_accuracy_usefulness_and_time_remain_null(self):
        p=self.compare();self.assertTrue(all(v is None for v in p['metrics'].values()));self.assertFalse(p['operational_queue_changed']);self.assertFalse(p['selection_uses_feedback'])
    def test_snapshot_company_asof_feature_and_model_pin_mismatch_are_rejected(self):
        for field in ('snapshot','company_id','as_of','feature_contract_fingerprint','model_version'):
            local,ml=deepcopy(self.local),deepcopy(self.ml)
            if field=='snapshot':ml['receipt'][field]['snapshot_id']='other'
            elif field=='as_of':ml['receipt'][field]='2026-01-01T00:00:00+07:00'
            else:ml['receipt'][field]=None
            with self.subTest(field=field),self.assertRaises(ValueError):compare(local,ml,AS_OF)
    def test_missing_negative_or_duplicate_ml_rows_do_not_create_scores(self):
        for value in (None,True,-1):
            ml=deepcopy(self.ml)
            for row in ml['rows']:row['raw_score']=value
            p=compare(self.local,ml,AS_OF);self.assertEqual(p['baseline'],p['combined']);self.assertEqual(p['ml_unavailable'],8)
        self.ml['rows'].append(deepcopy(self.ml['rows'][0]))
        with self.assertRaises(ValueError):self.compare()
    def test_nonfinite_input_cannot_be_sealed_as_json(self):
        for value in (float('nan'),float('inf')):
            ml=deepcopy(self.ml);ml['rows'][0]['raw_score']=value
            with self.assertRaises(ValueError):compare(self.local,ml,AS_OF)
    def test_unavailable_p1_and_missing_ml_keep_all_rows(self):
        p=self.compare();self.assertEqual(len(p['records']),8);self.assertEqual(p['coverage']['P1']['unavailable'],1);self.assertEqual(p['coverage']['P1']['not_applicable'],1);self.assertEqual(p['ml_unavailable'],1)
        for r in p['records']:
            if r['record_id']=='P1_T08':self.assertEqual(r['rule_state'],'unavailable')
    def test_order_is_deterministic_and_inputs_are_not_mutated(self):
        local,ml=deepcopy(self.local),deepcopy(self.ml);first=self.compare();self.assertEqual(self.local,local);self.assertEqual(self.ml,ml)
        self.local['rows'].reverse();self.ml['rows'].reverse();other=self.compare()
        for field in ('baseline','combined','added','rule_groups'):self.assertEqual(first[field],other[field])
    def test_master_score_policy_cannot_be_silently_changed(self):
        r=next(r for r in self.local['rows'][0]['methods']['rules']['details']['rule_results']['rules'] if r['rule_id']=='B5');r['score']=3
        with self.assertRaises(ValueError):self.compare()


if __name__=='__main__':unittest.main()
