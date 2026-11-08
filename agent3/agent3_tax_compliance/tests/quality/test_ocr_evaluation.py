import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from src.quality.ocr_evaluation import (seal_dataset,verify_dataset,score_record,summarize,
    compare_runs,HEADER_FIELDS,ITEM_FIELDS,canonical)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        (self.root/'a.pdf').write_bytes(b'a');(self.root/'b.pdf').write_bytes(b'b')
        self.entry={'case_id':'a','path':'a.pdf','group_id':'a','source_group':'vendor-a','layout_group':'layout-a',
                    'input_kind':'pdf_text','split':'dev','labels':{}}

    def other(self,**changes):
        return {**self.entry,'case_id':'b','path':'b.pdf','group_id':'b','source_group':'vendor-b','layout_group':'layout-b','split':'test',**changes}

    def test_seal_hashes_inputs_and_labels_and_detects_tampering(self):
        manifest=seal_dataset([self.entry,self.other()],self.root)
        self.assertTrue(verify_dataset(manifest,self.root))
        altered=copy.deepcopy(manifest);altered['entries'][0]['labels']={'fields':{'invoice.number':'x'}}
        with self.assertRaises(ValueError):verify_dataset(altered,self.root)
        (self.root/'b.pdf').write_bytes(b'changed')
        with self.assertRaises(ValueError):verify_dataset(manifest,self.root)

    def test_split_leakage_aliases_duplicate_bytes_and_known_pilot_are_rejected(self):
        for other in (self.other(source_group='vendor-a'),self.other(layout_group='layout-a'),self.other(group_id='a'),self.other(path='a.pdf')):
            with self.assertRaises(ValueError):seal_dataset([self.entry,other],self.root)
        with self.assertRaises(ValueError):seal_dataset([self.other()],self.root,{'layout-b'})
        with self.assertRaises(ValueError):seal_dataset([self.other(used_for_tuning=True)],self.root)

    def test_no_path_escape_incomplete_labels_or_numeric_float_labels(self):
        for entry in ({**self.entry,'path':'../elsewhere'}, {**self.entry,'labels':{'complete':True}},
                      {**self.entry,'labels':{'fields':{'totals.gross':1.5}}},
                      {**self.entry,'labels':{'fields':{'totals.gross':'NaN'}}},
                      {**self.entry,'labels':{'review_status':'VERIFIED'}}):
            with self.assertRaises(ValueError):seal_dataset([entry],self.root)

    def test_exact_money_ignores_decimal_context_and_names_remain_case_sensitive(self):
        self.assertEqual(canonical('9007199254740993.00000000000000000001','totals.gross'),canonical('9007199254740993.000000000000000000010','totals.gross'))
        self.assertNotEqual(canonical('9007199254740993.00000000000000000001','totals.gross'),canonical('9007199254740993.00000000000000000002','totals.gross'))
        self.assertNotEqual(canonical('Công Ty A','parties.seller.name'),canonical('CÔNG TY A','parties.seller.name'))

    def test_missing_record_wrong_present_and_extra_rows_count_against_accuracy(self):
        labels={'fields':{path:None for path in HEADER_FIELDS},'items':[{key:None for key in ITEM_FIELDS}],
                'complete':True,'review_status':'DRAFT'}
        labels['fields']['invoice.number']='001'
        payload={'invoice':{'number':{'status':'PRESENT','value':'002'}},'items':[{'line_number':1},{'line_number':2}]}
        score=score_record(SimpleNamespace(model_dump=lambda **kw:payload),labels)
        self.assertEqual(score['wrong_present'],1);self.assertFalse(score['item_count_correct']);self.assertFalse(score['whole_invoice_correct'])
        self.assertFalse(score_record(None,labels)['whole_invoice_correct'])
        self.assertEqual(score_record(None,{})['labeled'],0)

    def test_timeout_and_small_sample_do_not_pass_latency_gate(self):
        def case(state='REVIEW',elapsed=10):
            return {'case_id':'a','input_kind':'photo','state':state,'elapsed_seconds':elapsed,'page_count':1,'score':score_record(None,{}),'timings':[]}
        self.assertEqual(summarize([case()])['latency_gate'],'PENDING_SAMPLE_SIZE')
        self.assertEqual(summarize([case('PROCESSING_ERROR')])['latency_gate'],'FAIL')
        self.assertEqual(summarize([case(elapsed=181)])['latency_gate'],'FAIL')
        self.assertEqual(summarize([case()]*20)['quality_acceptance'],'PENDING')
        self.assertEqual(summarize([case()]*20)['latency_gate'],'PENDING_SAMPLE_SIZE')

    def test_comparison_requires_same_dataset_and_checks_new_critical_errors(self):
        def report(outcome):
            return {'run_state':'COMPLETED','dataset_validated_at_end':True,'expected_cases':['a'],
                'manifest_sha256':'a','split':'dev','cases':[{'case_id':'a','score':{'outcomes':[
                {'field_path':'invoice.number','outcome':outcome,'critical':True}], 'item_count_correct':None}}],
                'summary':{'latency_gate':'PASS','failed':0,'quality_acceptance':'PENDING'}}
        result=compare_runs(report('MISSING_OR_AMBIGUOUS'),report('WRONG_PRESENT'))
        self.assertFalse(result['technical_gate_passed']);self.assertEqual(len(result['new_critical_wrong_present']),1)
        result=compare_runs(report('MISSING_OR_AMBIGUOUS'),report('CORRECT'))
        self.assertEqual(result['relative_error_reduction'],1);self.assertFalse(result['release_approved'])
        self.assertFalse(result['gates']['complete_label_coverage'])
        changed=report('CORRECT');changed['manifest_sha256']='b'
        with self.assertRaises(ValueError):compare_runs(report('CORRECT'),changed)
        for change in ({'run_state':'RUNNING'},{'dataset_validated_at_end':False},{'expected_cases':['a','b']}):
            with self.assertRaises(ValueError):compare_runs(report('CORRECT'),{**report('CORRECT'),**change})


if __name__=='__main__':unittest.main()
