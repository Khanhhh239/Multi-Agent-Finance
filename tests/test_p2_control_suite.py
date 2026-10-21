"""Independent P2 scenario expectations, positive ledgers and immutable inputs."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sme_fraud.case_queue import review_queue
from sme_fraud.features import build_features
from sme_fraud.p2_control_cases import build_control, check_books, declarations
from sme_fraud.run_p2_controls import PROTECTED, evaluate, fresh, prepare, verify_sources
from sme_fraud.rules import score_rules


class P2ControlSuiteTest(unittest.TestCase):
    def spec(self, identity):
        return next(s for s in declarations() if s['control_id']==identity)

    def test_declared_controls_cover_all_requested_families(self):
        specs=declarations()
        self.assertEqual(len(specs),32)
        self.assertEqual(len({r['control_id'] for r in specs}),32)
        self.assertEqual({r['group'] for r in specs}, {'full_invoice','missing_documents','installments','refund_reversal','recurring','internal_limit'})

    def test_all_declared_outcomes_pass_through_real_rules_and_queue(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=prepare(root/'data')
            self.assertNotIn('expected',json.loads((source/'REFUND_FULL/tables.json').read_text(encoding='utf-8')))
            with patch('sme_fraud.run_p2_controls.fingerprints',return_value={}):
                result=evaluate(source,root/'report')
            self.assertTrue(result['successful'])
            self.assertEqual((result['controls'],result['observations'],result['mismatches']),(32,73,0))
            self.assertTrue(result['expected_joined_after_freeze'])

    def test_known_cash_receipt_does_not_create_a_new_cash_purchase_request(self):
        for identity in ('REFUND_FULL','RECEIPT_UNLINKED'):
            tables,config=build_control(self.spec(identity))
            result=score_rules(tables,config=config,features=build_features(tables))
            receipt=tables['transactions'][-1]
            self.assertEqual((receipt['debit_account'],receipt['credit_account']),('111','642'))
            self.assertFalse(any(h['rule_id']=='P2' and h['transaction_id']==receipt['transaction_id'] for h in result['hits']))
            cases,_=review_queue(result,tables)
            self.assertFalse(any(receipt['transaction_id'] in json.loads(c['transaction_ids']) for c in cases))

    def test_future_return_never_erases_the_original_as_of_flag(self):
        tables,config=build_control(self.spec('REFUND_FULL'))
        complete=score_rules(tables,config=config,features=build_features(tables))
        prefix=deepcopy(tables)
        first=prefix['transactions'][0]
        prefix['transactions']=[first]
        earlier=score_rules(prefix,config=config,features=build_features(prefix))
        def original(result):
            return next(h for h in result['hits'] if h['rule_id']=='P2' and h['transaction_id']==first['transaction_id'])
        self.assertEqual(original(complete),original(earlier))
        self.assertEqual(original(complete)['points'],8)

    def test_bad_return_link_and_unbalanced_journal_are_rejected(self):
        tables,_=build_control(self.spec('REFUND_FULL'))
        self.assertEqual(check_books(tables)['return_links'],1)
        broken=deepcopy(tables)
        broken['journal_lines'][-1]['credit_vnd']+=1
        with self.assertRaises(AssertionError): check_books(broken)
        broken=deepcopy(tables)
        link=next(r for r in broken['document_links'] if r['link_type']=='cash_return_of')
        link['observed_at']='2024-01-01T00:00:00+07:00'
        with self.assertRaises(AssertionError): check_books(broken)

    def test_source_checksum_and_existing_results_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source=prepare(root/'data')
            (source/'FULL_EQUAL/tables.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'hash'): verify_sources(source)
            output=root/'report';output.mkdir();(output/'keep.txt').write_text('keep')
            with self.assertRaises(FileExistsError): fresh(output)
            self.assertEqual((output/'keep.txt').read_text(),'keep')

    def test_frozen_roots_are_rejected_before_any_manifest_is_read(self):
        with tempfile.TemporaryDirectory() as temp,patch('sme_fraud.run_p2_controls.read',side_effect=AssertionError('Do not read frozen source')):
            for protected in PROTECTED:
                with self.assertRaises(ValueError): fresh(protected/'new')
                with self.assertRaises(ValueError): evaluate(protected/'sme_fraud_005',Path(temp)/'report')
