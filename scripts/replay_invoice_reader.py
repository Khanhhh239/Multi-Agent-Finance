"""Re-read PDFs and merge hash-bound frozen OCR, without recognition inference."""
import argparse
import hashlib
import re
import sqlite3
from pathlib import Path
import ocr_quality as q
from replay_invoice_extraction import frozen_inputs
from src.config import Settings
from src.ingestion.models import DocumentArtifact
from src.ingestion.pdf_reader import read_pdf
from src.adapters.ocr.normalizer import normalize
from src.adapters.ocr.layout_merge import merge
from src.adapters.ocr.protocol import NormalizedDocumentExtraction
from src.extraction.contracts import ExtractionArtifact
from src.extraction.service import extract,implementation_sha


def run(args):
    for name in (args.source_run,args.run_id,args.compare_run):
        if name is not None and not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',name):raise ValueError('Use plain run IDs')
    source=q.OUTPUT/args.source_run;original=q.read(source/'report.json');manifest=q.read(source/'manifest.json')
    if original['run_state']!='COMPLETED' or not original['dataset_validated_at_end']:raise ValueError('Completed source required')
    q.verify_dataset(manifest,q.ROOT)
    supplied=q.read(args.labels) if args.labels else None
    if supplied and supplied['run_id']!=args.source_run:raise ValueError('Labels belong to another source run')
    before={c['case_id']:c for c in original['cases']}
    out=q.fresh_directory(args.run_id)
    report={'run_state':'RUNNING','mode':'FROZEN_OCR_FRESH_PDF_READER','model_inference_calls':0,'latency_evaluated':False,
            'extractor_sha256':implementation_sha(),
            'runner_sha256':q.file_hash(__file__),
            'layout_source_sha256':{name:q.file_hash(q.APP/'src/adapters/ocr'/name) for name in ('normalizer.py','layout_merge.py')},
            'source_run':args.source_run,'manifest_sha256':manifest['manifest_sha256'],'cases':[],'failures':[],
            'reader_source_sha256':{str(p.relative_to(q.APP)):q.file_hash(p) for p in (q.APP/'src/ingestion').glob('*.py')},
            'release_approved':False}
    q.write(out/'manifest.json',manifest)
    for entry in manifest['entries']:
        name=entry['case_id'];folder=out/name;folder.mkdir()
        try:
            previous=ExtractionArtifact.model_validate_json((source/name/'extraction.json').read_bytes())
            old,master=frozen_inputs(source/name,previous)
            if old.status!='COMPLETE':raise ValueError('Incomplete frozen observations')
            with sqlite3.connect((source/name/'capture.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as db:
                row=db.execute('SELECT payload,sha256 FROM documents WHERE tenant_id=? AND taxpayer_id=? AND ingestion_id=?',
                               (old.tenant_id,old.taxpayer_id,old.ingestion_id)).fetchone()
            if not row or hashlib.sha256(row[0].encode()).hexdigest()!=row[1]:raise ValueError('Document integrity failure')
            document=DocumentArtifact.model_validate_json(row[0])
            if document.input_sha256!=entry['sha256'] or document.source_id!=old.source_id:raise ValueError('Source identity mismatch')
            pdf=q.local_file(q.ROOT,entry['path'])
            if q.file_hash(pdf)!=entry['sha256']:raise ValueError('Source changed')
            fresh=read_pdf(pdf,folder,dict(source_id=old.source_id,document_id=old.document_id,input_sha256=old.input_sha256),
                           Settings(render_dpi=original.get('render_dpi',150)))
            if len(fresh)!=len(old.pages):raise ValueError('Page count changed')
            pages=[]
            for page,cached in zip(fresh,old.pages):
                if (page.page_id,page.render_sha256,page.geometry)!=(cached.page_id,cached.image_hash,cached.geometry):
                    raise ValueError('Frozen OCR cannot be used for a changed render or transform')
                ocr=[]
                if page.route!='NATIVE_TEXT':
                    if len(cached.raw_responses)!=1:raise ValueError('Fresh OCR required for this page')
                    response=cached.raw_responses[0]
                    if (response.source_id,response.document_id,response.page_id,response.page_index,response.image_hash,response.runtime_sha256)!=(
                            old.source_id,old.document_id,page.page_id,page.page_index,page.render_sha256,old.runtime_sha256):
                        raise ValueError('Frozen response binding mismatch')
                    if response.issue or not response.result:raise ValueError('Incomplete frozen response')
                    if response.model_config_version!=old.ocr_config.version or response.result.model_id!=old.ocr_config.model_id:
                        raise ValueError('Frozen response model/config mismatch')
                    ocr=normalize(page,response)
                blocks=merge(page,ocr)
                pages.append(cached.model_copy(update={'route':page.route,'geometry':page.geometry,'blocks':blocks,
                              'table_candidates':tuple(b.block_id for b in blocks if b.evidence) if page.table_structure_present else ()}))
            new_doc=document.model_copy(update={'pages':tuple(fresh)})
            normalized=NormalizedDocumentExtraction.model_validate_json(old.model_copy(update={'pages':tuple(pages),
                'document_artifact_sha256':hashlib.sha256(new_doc.model_dump_json().encode()).hexdigest()}).model_dump_json())
            artifact=extract(normalized,'PDF',master,previous.profile)
            labels=supplied['cases'][name]['labels'] if supplied else entry['labels']
            if supplied and supplied['cases'][name]['sha256']!=entry['sha256']:raise ValueError('Label source mismatch')
            reference=previous
            if args.compare_run:
                reference=ExtractionArtifact.model_validate_json((q.OUTPUT/args.compare_run/name/'extraction.json').read_bytes())
                if (reference.input_sha256,reference.normalized_input_sha256)!=(previous.input_sha256,previous.normalized_input_sha256):
                    raise ValueError('Comparison observations differ')
            q.write(folder/'ingestion.json',new_doc.model_dump(mode='json'))
            q.write(folder/'normalized.json',normalized.model_dump(mode='json'))
            q.write(folder/'extraction.json',artifact.model_dump(mode='json'))
            old_score=q.score_record(reference.record,labels);score=q.score_record(artifact.record,labels)
            old_out={o['field_path']:o['outcome'] for o in old_score['outcomes']}
            row={'case_id':name,'sha256':entry['sha256'],'before':old_score,'score':score,'segmentation':artifact.segmentation.status,
                 'previously_correct_regressions':[o['field_path'] for o in score['outcomes'] if old_out.get(o['field_path'])=='CORRECT' and o['outcome']!='CORRECT']}
            report['cases'].append(row)
            print(name,score['correct'],'/',score['labeled'],row['segmentation'],flush=True)
        except Exception as exc:
            report['failures'].append({'case_id':name,'kind':type(exc).__name__,'reason':str(exc)[:200]})
        q.write(out/'report.json',report)
    q.verify_dataset(manifest,q.ROOT)
    if implementation_sha()!=report['extractor_sha256']:raise ValueError('Extractor changed during replay')
    if any(q.file_hash(q.APP/'src/adapters/ocr'/p)!=digest for p,digest in report['layout_source_sha256'].items()):
        raise ValueError('Layout implementation changed during replay')
    if any(q.file_hash(q.APP/p)!=digest for p,digest in report['reader_source_sha256'].items()):raise ValueError('Reader changed during replay')
    report.update(run_state='COMPLETED' if not report['failures'] else 'INCOMPLETE',dataset_validated_at_end=True)
    q.write(out/'report.json',report)
    return int(bool(report['failures']))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run',required=True);parser.add_argument('--run-id',required=True)
    parser.add_argument('--labels',type=Path);parser.add_argument('--compare-run')
    raise SystemExit(run(parser.parse_args()))
