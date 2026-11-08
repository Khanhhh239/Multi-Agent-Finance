"""Measure detector coverage against native spans; no recognition accuracy claim."""
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance';sys.path.insert(0,str(APP))
from src.config import Settings
from src.ingestion.pdf_reader import read_pdf
from src.ingestion.preprocess import compose,inverse
from src.adapters.ocr.worker_client import WorkerClient
from src.adapters.ocr.protocol import OCRConfig,OCRBridgeResponse
from src.adapters.ocr.bridge import request_for
from src.adapters.ocr.normalizer import normalize
spec=importlib.util.spec_from_file_location('coverage_geometry',ROOT/'data invoice/ocr_e2e_workflow/src/adapters/coverage_geometry.py')
geometry=importlib.util.module_from_spec(spec);spec.loader.exec_module(geometry)


def main():
    case='charity_2023-p1';source=ROOT/'data invoice/real_invoice_pilot_v1/cases'/(case+'.pdf')
    out=APP/'data/ocr_coverage_v1/detection';out.mkdir(parents=True,exist_ok=True)
    page=read_pdf(source,out,dict(source_id=case,document_id=case,input_sha256=hashlib.sha256(source.read_bytes()).hexdigest()),Settings(render_dpi=200))[0]
    with Image.open(out/'page-0.png') as image:
        tilted,forward,_=geometry.rotation(image,2);tilted.save(out/'tilted.png');tilted.close()
    rows=[]
    for model,tilt in (('ppocrv6_detector_base',False),('ppocrv6_detector_base',True),('ppocrv6_detector_tiles',False),('ppocrv6_detector_deskew',True)):
        path=out/('tilted.png' if tilt else 'page-0.png')
        with Image.open(path) as image:w,h=image.size
        new_geometry=page.geometry
        if tilt:
            matrix=compose(page.geometry.original_to_render,forward)
            new_geometry=page.geometry.model_copy(update={'transform_id':page.geometry.transform_id+'-tilt',
                'original_to_render':matrix,'render_to_original':inverse(matrix)})
        input_page=page.model_copy(update={'render_width':w,'render_height':h,'render_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'geometry':new_geometry})
        client=WorkerClient(model_id=model);runtime=client.inventory()['runtime_sha256']
        config=OCRConfig(version='detector-coverage-v1',model_id=model,timeout_seconds=180,memory_mb=6144,max_attempts=1)
        started=time.perf_counter();cached=out/(model+'-'+runtime+'-'+input_page.render_sha256[:16]+'.private.json')
        try:
            legacy=out/(model+'-'+runtime+'.private.json')
            if cached.exists():response=OCRBridgeResponse.model_validate_json(cached.read_bytes())
            elif legacy.exists() and OCRBridgeResponse.model_validate_json(legacy.read_bytes()).image_hash==input_page.render_sha256:
                response=OCRBridgeResponse.model_validate_json(legacy.read_bytes())
            else:
                response=client.run_batch([request_for(input_page,path,config,runtime)],config)[0]
                cached.write_bytes(response.model_dump_json(indent=2).encode())
            blocks=normalize(input_page,response)  # Strict ownership/bounds/area checks.
            predicted=[geometry.bounds(d.polygon) for d in response.result.detections];covered=total=0
            for b in page.native_blocks:
                if not b.text.strip():continue
                x0,y0,x1,y1=b.evidence.bbox
                polygon=[[x0*page.render_width,y0*page.render_height],[x1*page.render_width,y0*page.render_height],
                    [x1*page.render_width,y1*page.render_height],[x0*page.render_width,y1*page.render_height]]
                if tilt:polygon=[geometry.point(forward,p) for p in polygon]
                a=geometry.bounds(polygon);area=max(1.,(a[2]-a[0])*(a[3]-a[1]));total+=1
                if any(max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))/area>=.6 for b in predicted):covered+=1
            row={'model_id':model,'status':'COMPLETE','tilted_derivative':tilt,'runtime_sha256':runtime,
                'input_sha256':input_page.render_sha256,'native_span_count':total,'covered_native_spans':covered,
                'detection_count':len(blocks),'geometry_normalization_passed':True,
                'load_ms':response.result.load_time_ms,'inference_ms':response.result.inference_time_ms,
                'coverage':response.result.metadata.get('coverage_detection'),'deskew':response.result.metadata.get('coverage_geometry')}
        except Exception as exc:
            import traceback
            (out/(model+'.failure.private.txt')).write_bytes(traceback.format_exc().encode())
            row={'model_id':model,'status':'FAILED','error_type':type(exc).__name__}
        row['elapsed_seconds']=time.perf_counter()-started;rows.append(row);print(json.dumps(row),flush=True)
    report={'scope':'One DEV PDF, synthetic rotation is same invoice. Native font spans as proxy, not manual detection GT; no CER/field accuracy or false positive estimate.',
        'rows':rows,'default_promoted':False}
    (out.parent/'detection_summary.json').write_bytes((json.dumps(report,indent=2)+'\n').encode())


if __name__=='__main__':main()
