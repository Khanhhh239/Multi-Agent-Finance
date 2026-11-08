"""Guard the holdout and frozen outputs of the reusable pipeline rehearsal."""
import json
from pathlib import Path
import tempfile
import unittest

from sme_fraud.run_pipeline_rehearsal import input_guard, source_comparison, score_cohort, assert_network_scope, graph_checks
from sme_fraud.entity_graph import EntityGraph


class PipelineRehearsalGuardsTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.data,self.baseline,self.output=(self.root/name for name in ('data','baseline','output'))
        for tag in ('001','003'):
            data=self.data/f'sme_fraud_{tag}'
            report=self.baseline/f'sme_fraud_{tag}'
            data.mkdir(parents=True);report.mkdir(parents=True)
            (data/'manifest.json').write_text(json.dumps(dict(role='reporting',is_synthetic=True)))
            (report/'review_packet.csv').write_text('review_id\n')

    def tearDown(self):
        self.temp.cleanup()

    def test_refuses_nested_or_nonempty_output_before_writes(self):
        for output in (self.data,self.data/'new',self.baseline/'new',self.root):
            with self.subTest(output=output),self.assertRaises(ValueError):
                input_guard(self.data,self.baseline,output)
        self.output.mkdir();(self.output/'keep.txt').write_text('existing result')
        with self.assertRaises(FileExistsError):input_guard(self.data,self.baseline,self.output)
        self.assertEqual((self.output/'keep.txt').read_text(),'existing result')

    def test_reporting_guard_does_not_need_or_load_holdout_manifest(self):
        # No 005 directory is provided. Only 001/003 manifests are inspected.
        result=input_guard(self.data,self.baseline,self.output)
        self.assertEqual(result[0],self.data.resolve())
        self.assertFalse(self.output.exists())
        (self.data/'sme_fraud_003'/'manifest.json').write_text(json.dumps(dict(role='blind_holdout_unscored',is_synthetic=True)))
        with self.assertRaises(ValueError):input_guard(self.data,self.baseline,self.output)

    def test_holdout_scoring_and_oracle_join_are_rejected_without_reading_sources(self):
        with self.assertRaisesRegex(ValueError,'001/003'):
            score_cohort(self.data,self.baseline,self.output,'005',{})
        with self.assertRaisesRegex(ValueError,'001/003'):
            source_comparison(self.baseline/'sme_fraud_005',self.output,[])
        self.assertFalse(self.output.exists())

    def test_oracle_cannot_be_read_before_freeze_or_after_detector_tampering(self):
        self.output.mkdir()
        prior=self.baseline/'sme_fraud_001'
        with self.assertRaisesRegex(ValueError,'Freeze'):
            source_comparison(prior,self.output,[])
        (self.output/'rule_hits.jsonl').write_text('tampered')
        (self.output/'predictions_frozen.json').write_text(json.dumps(dict(files={'rule_hits.jsonl':'incorrect_hash'})))
        with self.assertRaisesRegex(ValueError,'after freeze'):
            source_comparison(prior,self.output,[])

    def test_company_scope_uses_the_real_node_link_contract_and_rejects_foreign_nodes(self):
        from test_entity_graph import sources,CUTOFF
        tables=sources()
        network=EntityGraph(tables,'C001',CUTOFF).to_json(max_nodes=None)
        assert_network_scope(network,'C001',CUTOFF)
        result=graph_checks(tables,{'companies':{'C001':network}},CUTOFF)
        self.assertTrue(result['components_partition_nodes'])
        self.assertGreater(result['company_paths_checked'],0)
        other=EntityGraph(tables,'C002',CUTOFF).to_json(max_nodes=None)
        if other['nodes']:
            network['nodes'].append(other['nodes'][0])
        else:
            network['nodes'][0]['id']='employee:foreign_namespace'
        with self.assertRaises(AssertionError):
            assert_network_scope(network,'C001',CUTOFF)
