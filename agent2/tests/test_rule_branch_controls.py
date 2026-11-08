"""Each declared source control runs through the engine, queue and SLA, two seeds."""
import json,tempfile,unittest
from collections import Counter
from pathlib import Path
from sme_fraud.rule_branch_controls import catalog,build_control,assess,namespace,run,RULES,SEEDS
from sme_fraud.features import build_features
from sme_fraud.rules import score_rules,load_inputs


class BranchControlTest(unittest.TestCase):
    pass


def control_test(spec):
    def test(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                tables,target,scope,config,future=build_control(spec,seed)
                if spec['expected']=='rejected':
                    with self.assertRaises(ValueError):score_rules(tables,features=build_features(tables),config=config)
                    continue
                result=score_rules(tables,features=build_features(tables),config=config)
                comparison=assess(result,tables,spec,target,scope,'C001')
                self.assertTrue(comparison['passed'],json.dumps(comparison,ensure_ascii=False))
                self.assertNotIn('labels',tables);self.assertNotIn('splits',tables)
                self.assertTrue(all(r['posted_at']<='2025-09-12T11:00:00+07:00' for r in tables['transactions']))
    return test


for spec in catalog():setattr(BranchControlTest,'test_'+spec['rule_id'].lower()+'_'+spec['variant'],control_test(spec))


class BranchExportTest(unittest.TestCase):
    def test_registry_is_unique_and_keeps_both_existing_and_new_details(self):
        specs=catalog();self.assertEqual(len({(s['rule_id'],s['variant']) for s in specs}),len(specs))
        self.assertEqual({s['rule_id'] for s in specs},set(RULES))
        self.assertTrue(all(any(s['rule_id']==code and s['new_detail_control'] for s in specs) for code in RULES))

    def test_namespace_keeps_linked_ids_and_distinguishes_controls(self):
        spec=next(s for s in catalog() if s['rule_id']=='F4' and s['variant']=='fully_paid')
        tables,target,scope,config,_=build_control(spec,SEEDS[0])
        a,mapping=namespace(tables,'SIM_A_');b,_=namespace(tables,'SIM_B_')
        self.assertFalse({e['employee_id'] for e in a['employees']} & {e['employee_id'] for e in b['employees']})
        self.assertEqual(a['receipt_allocations'][0]['receipt_transaction_id'],mapping[tables['receipt_allocations'][0]['receipt_transaction_id']])
        result=score_rules(a,features=build_features(a),config=config)
        comparison=assess(result,a,spec,mapping[target],'invoice:'+mapping['AR1'],mapping['C001'])
        self.assertTrue(comparison['passed'],comparison)

    def test_export_whitelist_contract_and_all_seeded_expectations_roundtrip(self):
        with tempfile.TemporaryDirectory() as location:
            root=Path(location);summary=run(root/'data',root/'reports',seeds=(SEEDS[0],))
            self.assertEqual(summary['matched'],summary['controls']);self.assertEqual(summary['mismatches'],[])
            for code in RULES:
                tables,features,manifest=load_inputs(root/'data'/code/'sme_fraud_003')
                self.assertNotIn('labels',tables);self.assertNotIn('splits',tables)
                self.assertTrue(manifest['is_synthetic']);self.assertEqual(len(features),len(tables['transactions']))
                self.assertFalse((root/'data'/code/'sme_fraud_003'/'labels.csv').exists())
            deferred=json.loads((root/'data/deferred_transactions.json').read_text(encoding='utf-8'))
            self.assertTrue(deferred);self.assertTrue(all(r['reason']=='posted_after_evaluation_cutoff' for r in deferred))
            with self.assertRaises(FileExistsError):run(root/'data',root/'reports',seeds=(SEEDS[0],))


if __name__=='__main__':unittest.main()
