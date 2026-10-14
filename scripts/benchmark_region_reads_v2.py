"""Local region read experiment, not a production field correction.

Prepare with app Python; recognize with the pinned OCR Python. The recognizer
sees crops only, never field labels or expected invoice values from the manifest.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LOCAL=ROOT/'data invoice/ocr_extraction_v2'
TARGETS=[('charity_2023-p1',52,'parties.buyer.tax_id'),
         ('charity_2023-p1',64,'invoice.series'),
         ('software_kct-p1',106,'parties.seller.tax_id'),
         ('software_kct-p1',116,'invoice.issue_date')]


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    import re
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--mode',choices=('prepare','recognize'),required=True)
    parser.add_argument('--decode',choices=('greedy','beam'),default='greedy')
    parser.add_argument('--dpi',type=int,choices=(150,300,450))
    args=parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',args.run_id):parser.error('plain run-id required')
    out=LOCAL/args.run_id
    if args.mode=='prepare':
        if out.exists():parser.error('Frozen region run exists')
        out.mkdir(parents=True)
        import pymupdf
        rows=[]
        for case,index,field in TARGETS:
            source=LOCAL/'plan06_v21_split_full_01'/case/'scan.normalized.json'
            doc=json.loads(source.read_text(encoding='utf-8'))
            block=doc['pages'][0]['blocks'][index]
            pdf_path=ROOT/'data invoice/real_invoice_pilot_v1/cases'/(case+'.pdf')
            with pymupdf.open(pdf_path) as pdf:
                page=pdf[0]
                if page.rotation:raise ValueError('Experiment requires unrotated pilot pages')
                x0,y0,x1,y1=block['evidence']['bbox']
                rect=page.rect
                clip=pymupdf.Rect(rect.x0+x0*rect.width,rect.y0+y0*rect.height,
                                  rect.x0+x1*rect.width,rect.y0+y1*rect.height)
                for dpi in (150,300,450):
                    name=case+'-'+str(index)+'-'+str(dpi)+'.png'
                    page.get_pixmap(matrix=pymupdf.Matrix(dpi/72,dpi/72),clip=clip).save(out/name)
                    rows.append(dict(case=case,field=field,block_id=block['block_id'],dpi=dpi,
                        image=name,image_sha256=digest(out/name),input_sha256=digest(pdf_path),
                        normalized_input_sha256=digest(source),original_bbox=list(clip),
                        before_text=block['text_raw']))
        (out/'manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Prepared '+str(len(rows))+' regions; no full-page high-DPI raster needed',flush=True)
        return
    sys.path.insert(0,str(ROOT/'data invoice/ocr_e2e_workflow'))
    from src.adapters.vietocr_adapter import PPOCRV6VietOCRAdapter
    config=json.loads((ROOT/'agent3_tax_compliance/configs/ocr/engines/ppocrv6_vietocr.json').read_text())['adapter_config']
    config.update(model_id='region-read-vietocr-v2',recognition_only=True)
    config['recognizer']['beamsearch']=args.decode=='beam'
    result_name='results.json' if args.decode=='greedy' and args.dpi is None else 'results-'+args.decode+'-'+str(args.dpi or 'all')+'.json'
    if (out/result_name).exists():parser.error('Frozen recognition result exists')
    adapter=PPOCRV6VietOCRAdapter(config,args.run_id)
    rows=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    if args.dpi:rows=[r for r in rows if r['dpi']==args.dpi]
    results=[]
    for row in rows:
        image=out/row['image']
        if digest(image)!=row['image_sha256']:raise ValueError('crop changed')
        started=time.perf_counter()
        response=adapter.predict(image).to_dict()
        results.append(dict(image=row['image'],image_sha256=row['image_sha256'],
                            elapsed_seconds=time.perf_counter()-started,result=response))
        (out/(result_name+'.partial')).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(dict(image=row['image'],text=response['document_text_raw'],error=response['error']),ensure_ascii=True),flush=True)
    (out/result_name).write_text(json.dumps(dict(parent_plan='PLAN_06',decode=args.decode,model_load_ms=adapter.load_time_ms,
        weights_sha256=digest(ROOT/'data invoice/ocr_e2e_workflow/artifacts/models/vietocr/transformerocr.pth'),
        rows=results),ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__': main()
