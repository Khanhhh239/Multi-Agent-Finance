import json
from pathlib import Path
import tempfile
import unittest

from src.adapters.ocr.registry import EngineRegistry, adapter_config, load_default_config, CONFIG_ROOT, confined
from src.adapters.ocr.protocol import OCRConfig, OCRError, correlate
from src.adapters.ocr.worker_client import WorkerClient
from src.adapters.ocr.bridge import request_for
from src.adapters.ocr.normalizer import normalize
from src.ingestion.pdf_reader import read_image
from src.config import Settings
from src.persistence.repository import digest

PROJECT=Path(__file__).resolve().parents[2]
BENCH=PROJECT.parent/'data invoice/ocr_e2e_workflow'


class RegistryTests(unittest.TestCase):
    def test_experimental_split_is_opt_in_and_geometry_code_is_pinned(self):
        default=EngineRegistry().get(load_default_config().model_id)
        experimental=EngineRegistry().get('ppocrv6_vietocr_v2_split')
        self.assertFalse(default.adapter_config['recognizer'].get('split_long_lines',False))
        self.assertTrue(experimental.adapter_config['recognizer']['split_long_lines'])
        self.assertIn('src/adapters/recognition_crops.py',experimental.source_files)
        config=load_default_config().model_copy(update={'model_id':experimental.model_id})
        compiled=adapter_config(experimental,BENCH,config)
        self.assertEqual(compiled['model_id'],experimental.model_id)
        self.assertEqual(compiled['adapter'],'ppocrv6_vietocr')

    def test_default_is_hybrid_and_all_profiles_are_valid(self):
        config=load_default_config()
        self.assertEqual(config.model_id,'ppocrv6_vietocr')
        registry=EngineRegistry()
        for name in ('ppocrv6_vietocr','tesseract','ppocrv6_medium','easyocr'):
            profile=registry.get(name)
            self.assertEqual(profile.model_id,name)
        options=adapter_config(registry.get(config.model_id),BENCH,config)
        self.assertEqual(options['recognizer']['config_name'],'vgg_transformer')
        self.assertTrue(Path(options['recognizer']['weights']).is_absolute())
        self.assertFalse(options['detector']['use_doc_orientation_classify'])

    def test_engine_paths_cannot_escape_root(self):
        with self.assertRaises(OCRError): confined(BENCH,'../outside')
        with self.assertRaises(OCRError): EngineRegistry().get('unknown-engine')

    def test_unknown_parameter_rejected_and_profile_not_mutated(self):
        profile=EngineRegistry().get('ppocrv6_vietocr')
        before=profile.model_dump_json()
        adapter_config(profile,BENCH,load_default_config())
        self.assertEqual(profile.model_dump_json(),before)
        config=load_default_config().model_copy(update={'parameters':{'weights':'untrusted-path'}})
        with self.assertRaises(OCRError): adapter_config(profile,BENCH,config)

    def test_profile_can_select_same_adapter_under_new_model_without_app_edits(self):
        # Real worker call demonstrates that dispatch/correlation are not tied
        # to the literal model name "tesseract" in application code.
        with tempfile.TemporaryDirectory() as directory:
            profile=json.loads((CONFIG_ROOT/'engines/tesseract.json').read_text())
            profile['model_id']='custom-tesseract';profile['profile_version']='custom-runtime-v1'
            (Path(directory)/'custom-tesseract.json').write_text(json.dumps(profile),encoding='utf-8')
            client=WorkerClient(model_id='custom-tesseract',registry=EngineRegistry(directory))
            config=OCRConfig(model_id='custom-tesseract',version='custom-model-v1')
            image=PROJECT/'tests/fixtures/ocr/functional_set_v1/syn-00-image.png'
            page=read_image(image,Path(directory),dict(source_id='alias-source',document_id='alias-doc',
                input_sha256=digest(image.read_bytes())),Settings())[0]
            request=request_for(page,Path(directory)/'page-0.png',config,client.inventory()['runtime_sha256'])
            response=client.run_batch([request],config)[0]
            correlate(request,response)
            self.assertEqual(response.result.model_id,'custom-tesseract')
            self.assertGreater(len(normalize(page,response)),0)
            wrong=response.model_copy(update={'result':response.result.model_copy(update={'model_id':'other'})})
            with self.assertRaises(OCRError): correlate(request,wrong)

    def test_hybrid_scores_are_detection_scores(self):
        # Contract semantics test uses tiny data; real hybrid inference has
        # a separate smoke/e2e report, not a mock accuracy measurement.
        from test_ocr import response
        with tempfile.TemporaryDirectory() as directory:
            image=PROJECT/'tests/fixtures/ocr/functional_set_v1/syn-00-image.png'
            page=read_image(image,Path(directory),dict(source_id='score-source',document_id='score-doc',
                input_sha256=digest(image.read_bytes())),Settings())[0]
            req=request_for(page,Path(directory)/'page-0.png',load_default_config(),'a'*64)
            result=response(req)
            result=result.model_copy(update={'result':result.result.model_copy(update={'metadata':{
                'confidence_semantics':'DETECTION_SCORE_NOT_TEXT_CONFIDENCE'}})})
            block=normalize(page,result)[0]
            self.assertEqual(block.origins[0].score_kind,'DETECTION')
            self.assertEqual(block.origins[0].score_semantics,'ENGINE_HEURISTIC_NOT_CALIBRATED')


if __name__=='__main__': unittest.main()
