import copy
from pathlib import Path
import sys
import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'scripts'))
import invoice_accuracy as runner


class InvoiceAccuracyAuditTests(unittest.TestCase):
    def fixture(self):
        labels={'cases':{'a':{'sha256':'a'*64,'labels':{'fields':{'parties.buyer.name':'A'},
                    'items':[{'vat_rate':'0.08','vat_treatment':'TAXABLE_RATE'}]}}}}
        audit={'labels_sha256':runner.q.fingerprint(labels),'rows':[
            {'case_id':'a','source_sha256':'a'*64,'field_path':path,'label_text':value,'scope':'DOCUMENT_PRINTED',
             'review_status':'SELF_CHECK_NOT_INDEPENDENT','reviewer':'test','reason':'synthetic source reviewed'}
            for path,value in [('parties.buyer.name','A'),('items.1.vat_rate','0.08'),('items.1.vat_treatment','TAXABLE_RATE')]]}
        report={'cases':[{'case_id':'a','score':{'outcomes':[{'field_path':r['field_path'],'outcome':'CORRECT'} for r in audit['rows']]}}]}
        return labels,audit,report

    def test_document_rate_is_excluded_from_row_ocr_not_counted_correct(self):
        labels,audit,report=self.fixture();result=runner.scoped_score(report,audit,labels)
        self.assertEqual(result['included'],1)
        self.assertEqual(result['excluded'],{'DOCUMENT_LEVEL_NOT_ROW_PRINTED':2})
        self.assertFalse(result['independent_review']);self.assertFalse(result['release_approved'])

    def test_label_source_coverage_and_review_binding_cannot_be_changed(self):
        labels,audit,_=self.fixture()
        for key,value in [('source_sha256','b'*64),('label_text','different'),('reviewer',None),('field_path','items.0.vat_rate')]:
            altered=copy.deepcopy(audit);altered['rows'][0][key]=value
            with self.assertRaises(ValueError):runner.audit_labels(altered,labels)
        altered=copy.deepcopy(audit);altered['rows'].append(altered['rows'][0])
        with self.assertRaises(ValueError):runner.audit_labels(altered,labels)

    def test_unreviewed_fields_are_excluded_not_turned_into_successes(self):
        labels,audit,report=self.fixture()
        for row in audit['rows']:row.update(scope='UNREVIEWED',review_status='DRAFT',reviewer=None)
        result=runner.scoped_score(report,audit,labels)
        self.assertEqual(result['included'],0);self.assertEqual(result['outcomes'],{})

    def test_edit_distance_is_character_sensitive(self):
        self.assertEqual(runner.edit_distance('8%','B%'),1)
        self.assertEqual(runner.edit_distance('abcd','abcd'),0)
        self.assertEqual(runner.edit_distance('abc','a'),2)

    def holdout_fixture(self):
        temp=tempfile.TemporaryDirectory(dir=runner.q.APP/'data');self.addCleanup(temp.cleanup)
        root=Path(temp.name);source=root/'dev';source.mkdir();output=root/'output';output.mkdir()
        original=root/'source.pdf';original.write_bytes(b'synthetic-old')
        entry={'case_id':'old','path':str(original.relative_to(runner.q.ROOT)),'input_kind':'pdf_text','split':'dev',
               'group_id':'old','source_group':'old-source','layout_group':'old-layout','source_bundle_sha256':'b'*64,'labels':{}}
        manifest=runner.q.seal_dataset([entry],runner.q.ROOT);runner.q.write(source/'manifest.json',manifest)
        candidate=output/'dev';candidate.mkdir();runner.q.write(candidate/'manifest.json',manifest)
        incoming=root/'new.json';runner.q.write(incoming,[])
        args=SimpleNamespace(source_run='dev',run_id='holdout',input=incoming,candidate_sha='a'*64,render_dpi=150)
        return root,output,args

    def test_empty_holdout_stays_pending_and_never_runs_inference(self):
        root,output,args=self.holdout_fixture()
        with patch.object(runner.q,'OUTPUT',output),patch('src.extraction.service.implementation_sha',return_value='a'*64),patch.object(runner.q,'run') as inference:
            runner.holdout(args)
            state=runner.q.read(output/'holdout/readiness.json');self.assertEqual(state['state'],'PENDING_UNSEEN_DATA')
            with self.assertRaisesRegex(ValueError,'PENDING_UNSEEN_DATA'):
                runner.evaluate_holdout(SimpleNamespace(source_run='holdout',run_id='evaluation',dedicated_machine=False))
            inference.assert_not_called()

    def test_stale_candidate_is_rejected_before_opening_holdout(self):
        root,output,args=self.holdout_fixture()
        with patch.object(runner.q,'OUTPUT',output),patch('src.extraction.service.implementation_sha',return_value='c'*64):
            with self.assertRaisesRegex(ValueError,'current candidate'):runner.holdout(args)
        self.assertFalse((output/'holdout').exists())

    def test_page_from_original_bundle_cannot_be_relabelled_holdout(self):
        root,output,args=self.holdout_fixture();fresh=root/'new.pdf';fresh.write_bytes(b'synthetic-new-page')
        row={'case_id':'new','path':str(fresh.relative_to(runner.q.ROOT)),'input_kind':'pdf_text','split':'test',
             'group_id':'new','source_group':'new-source','layout_group':'new-layout','source_bundle_sha256':'b'*64,'labels':{}}
        runner.q.write(args.input,[row])
        with patch.object(runner.q,'OUTPUT',output),patch('src.extraction.service.implementation_sha',return_value='a'*64):
            with self.assertRaisesRegex(ValueError,'development source bundle'):runner.holdout(args)
