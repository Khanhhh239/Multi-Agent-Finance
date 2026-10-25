import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('ocr_quality_runner',ROOT/'scripts/ocr_quality.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
from src.adapters.ocr.protocol import OCRConfig,OCRError
from src.quality.ocr_evaluation import file_hash


class NativeClient:
    def __init__(self,**kwargs):self.metrics_history=[]
    def inventory(self):return {'runtime_sha256':'a'*64,'engine_versions':{'test':'1'}}
    def run_batch(self,*args,**kwargs):raise AssertionError('Native input must not invoke inference')


class TimeoutClient(NativeClient):
    def run_batch(self,*args,**kwargs):raise OCRError('WORKER_TIMEOUT','Synthetic timeout',True)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        data=ROOT/'agent3_tax_compliance/data';data.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=data);self.addCleanup(self.temp.cleanup);self.out=Path(self.temp.name)

    def test_real_native_pipeline_is_isolated_and_does_not_infer(self):
        source=ROOT/'agent3_tax_compliance/tests/fixtures/ocr/functional_set_v1/syn-00-pdf_text.pdf'
        entry={'case_id':'native','path':str(source.relative_to(ROOT)),'input_kind':'pdf_text','group_id':'fixture',
               'sha256':file_hash(source),'number_locale':'VI','labels':{'fields':{'invoice.number':'DEMO/000'}}}
        with patch('src.adapters.ocr.worker_client.WorkerClient',NativeClient):
            row=runner.execute_case(entry,self.out,OCRConfig(),150)
        self.assertEqual(row['state'],'REVIEW');self.assertEqual(row['page_count'],1)
        self.assertEqual(row['timings'],[]);self.assertEqual(row['score']['labeled'],1)
        self.assertEqual(row['score']['correct'],1)
        self.assertTrue((self.out/'capture.sqlite3').is_file());self.assertTrue((self.out/'error_inventory.json').is_file())

    def test_timeout_stays_failed_and_labeled_cells_stay_in_denominator(self):
        from PIL import Image
        source=self.out/'scan.png'
        with Image.new('RGB',(400,200),'white') as image:image.save(source)
        entry={'case_id':'scan','path':str(source.relative_to(ROOT)),'input_kind':'pdf_scan','group_id':'fixture',
               'sha256':file_hash(source),'number_locale':'VI','labels':{'fields':{'invoice.number':'001'}}}
        with patch('src.adapters.ocr.worker_client.WorkerClient',TimeoutClient):
            row=runner.execute_case(entry,self.out,OCRConfig(),150)
        self.assertNotEqual(row['state'],'REVIEW');self.assertEqual(row['score']['labeled'],1)
        self.assertEqual(row['score']['correct'],0);self.assertEqual(len(row['timings']),1)


if __name__=='__main__':unittest.main()
