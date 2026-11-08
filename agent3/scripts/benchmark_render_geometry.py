"""Render ablation only; does not claim OCR recognition accuracy at higher DPI."""
import hashlib
import json
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/'agent3_tax_compliance';sys.path.insert(0,str(APP))
from src.config import Settings
from src.ingestion.pdf_reader import read_pdf
from src.ingestion.models import IngestionError


def main():
    source=ROOT/'data invoice/real_invoice_pilot_v1/cases/charity_2023-p1.pdf'
    out=APP/'data/ocr_coverage_v1/render';rows=[]
    identity=dict(source_id='render-ablation',document_id='render-ablation',input_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    baseline=None
    for dpi in (150,200,300):
        folder=out/str(dpi);folder.mkdir(parents=True,exist_ok=True);started=time.perf_counter()
        page=read_pdf(source,folder,identity,Settings(render_dpi=dpi,max_render_pixels=12_000_000))[0]
        boxes={b.block_id:b.evidence.bbox for b in page.native_blocks}
        if baseline is None:baseline=boxes
        delta=max((abs(a-b) for k,box in boxes.items() for a,b in zip(box,baseline[k])),default=0.)
        rows.append({'dpi':dpi,'width':page.render_width,'height':page.render_height,'pixels':page.render_width*page.render_height,
            'elapsed_seconds':time.perf_counter()-started,'native_blocks':len(boxes),'same_native_block_ids':boxes.keys()==baseline.keys(),
            'max_normalized_bbox_delta':delta,'render_sha256':page.render_sha256})
    # A4 300 DPI exceeds the unchanged 8M production page limit: prove rejection.
    rejected=False
    try:read_pdf(source,out/'300',identity,Settings(render_dpi=300))
    except IngestionError as exc:rejected=exc.issue.code=='LIMIT_EXCEEDED'
    report={'scope':'One PDF render geometry/resource DEV experiment; no OCR field accuracy claim','rows':rows,
        'default_300dpi_limit_enforced':rejected,'default_changed':False}
    (out.parent/'render_summary.json').write_bytes((json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps(report))


if __name__=='__main__':main()
