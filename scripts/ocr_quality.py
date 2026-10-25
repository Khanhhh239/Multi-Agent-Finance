"""Seal, run and compare local OCR quality experiments on the capture pipeline."""
import argparse
import json
import mimetypes
import platform
import sys
import time
from datetime import date,datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'agent3_tax_compliance'
sys.path.insert(0,str(APP))
from src.quality.ocr_evaluation import (HEADER_FIELDS,ITEM_FIELDS,file_hash,seal_dataset,
    verify_dataset,score_record,summarize,compare_runs,local_file,fingerprint)

OUTPUT=APP/'data/ocr_quality'


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def fresh_directory(name):
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',name):raise ValueError('Use a plain run ID')
    path=OUTPUT/name
    path.mkdir(parents=True,exist_ok=False)
    return path


def execute_case(entry,out,config,render_dpi):
    """A separate DB per case makes all OCR observations fresh, never replayed."""
    from src.config import Settings
    from src.domain.taxpayer import AccessContext,TaxpayerMaster
    from src.ingestion.service import IngestionService
    from src.ingestion.upload import StagedUpload
    from src.jobs.service import CaptureJobs
    from src.adapters.ocr.bridge import OCRBridge,config_key
    from src.adapters.ocr.worker_client import WorkerClient
    from src.extraction.contracts import ExtractionProfile
    settings=Settings(database_path=out/'capture.sqlite3',staging_directory=out/'staging',render_dpi=render_dpi)
    ctx=AccessContext(actor_id='quality-runner',tenant_id='quality',taxpayer_ids=frozenset({'quality'}),permissions=frozenset({'READ','WRITE','ADMIN'}))
    jobs=CaptureJobs(settings);jobs.base.initialize()
    jobs.base.add_taxpayer(ctx,TaxpayerMaster(config_version='quality-v1',creator='quality-runner',stage='benchmark',
        tenant_id=ctx.tenant_id,taxpayer_id='quality',revision=1,tax_code='0000000000',effective_from=date(1900,1,1),provenance_reference='benchmark-only'))
    source=local_file(ROOT,entry['path']);timings=[]
    client=WorkerClient(model_id=config.model_id)
    inventory=client.inventory();write(out/'runtime.json',inventory)
    delegate=client.run_batch
    def measured(requests,run_config,**kwargs):
        start=time.perf_counter()
        responses=[]
        try:
            responses=delegate(requests,run_config,**kwargs)
            return responses
        finally:
            timings.append({'stage':'ocr_page','route':'OCR','elapsed_seconds':time.perf_counter()-start,
                            'page_index':requests[0].page_index,'worker_metrics':client.metrics_history[-1:],
                            'lifecycle':'NEW_WORKER_PER_PAGE','cached':False,
                            'model_load_ms':responses[0].result.load_time_ms if responses and responses[0].result else None,
                            'inference_ms':responses[0].result.inference_time_ms if responses and responses[0].result else None})
    client.run_batch=measured
    bridge=OCRBridge(settings,config,client)
    ingestion=IngestionService(settings)
    start=time.perf_counter()
    with StagedUpload(settings) as staged:
        with source.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):staged.write(chunk)
        view=ingestion.accept_staged(ctx,'quality',1,entry['case_id'],staged,mimetypes.guess_type(source.name)[0] or 'application/octet-stream',source.name)
    job=jobs.enqueue(ctx,'quality',view.ingestion_id)
    result=jobs.work_one(ctx,'quality',job['job_id'],bridge=bridge,profile=ExtractionProfile(number_locale=entry['number_locale']))
    elapsed=time.perf_counter()-start
    row={'case_id':entry['case_id'],'input_kind':entry['input_kind'],'sha256':entry['sha256'],
         'group_id':entry['group_id'],'derived_render':entry.get('derived_render',False),
         'state':result['state'],'error_code':result.get('error_code'),'elapsed_seconds':elapsed,'timings':timings}
    record=None
    if result.get('extraction_artifact_id'):
        artifact=jobs.extraction.get(ctx,'quality',result['extraction_artifact_id']);record=artifact.record
        write(out/'extraction.json',artifact.model_dump(mode='json'))
    if record:
        from src.recovery.policy import diagnose
        normalized=bridge.repository.get(ctx,'quality',view.ingestion_id,config_key(config,inventory['runtime_sha256']))['result']
        write(out/'normalized.json',normalized.model_dump(mode='json'))
        write(out/'diagnostics.json',diagnose(record,artifact,normalized))
        write(out/'error_inventory.json',error_inventory(record,artifact,normalized,entry['labels']))
        if normalized.status!='COMPLETE':row['state']='INCOMPLETE'
    try:
        document=ingestion.repository.document(ctx,'quality',view.ingestion_id)
        row['page_count']=len(document.pages);row['routes']=[p.route for p in document.pages]
        for timing in timings:timing['route']=document.pages[timing['page_index']].route
    except Exception:
        row['page_count']=None
    row['score']=score_record(record,entry['labels'])
    # Source text/crops stay in the local run DB and artifacts, never in the aggregate.
    return row


def error_inventory(record,artifact,normalized,labels):
    """Hypotheses only; detector versus recognizer requires a visual crop oracle."""
    from src.quality.ocr_evaluation import canonical
    score=score_record(record,labels);errors=[]
    blocks=[b for p in normalized.pages for b in p.blocks]
    for outcome in score['outcomes']:
        if outcome['outcome']=='CORRECT':continue
        path=outcome['field_path'];semantic=path.removeprefix('parties.')
        if path.startswith('items.'):
            index=int(path.split('.')[1])-1
            items=sorted(record.items,key=lambda item:item.line_number)
            semantic='items.'+items[index].item_id+'.'+path.rsplit('.',1)[-1] if index<len(items) else path
            expected=labels['items'][index].get(path.rsplit('.',1)[-1])
        else:expected=labels.get('fields',{}).get(path)
        matching=[b.block_id for b in blocks if expected is not None and str(canonical(expected,path)) in b.text_raw]
        issues=[i.model_dump(mode='json') for i in artifact.issues if i.field_path in (semantic,path)]
        hypothesis='FIELD_UNBOUND_OR_SOURCE_CONFLICT' if matching else 'TEXT_NOT_DETECTED_OR_MISREAD_OR_CROP'
        if any(i['code'].startswith('UNPARSEABLE') for i in issues):hypothesis='NORMALIZATION_OR_TEXT_REQUIRES_ORACLE'
        errors.append({**outcome,'hypothesis':hypothesis,'oracle_required':True,'matching_blocks':matching,
                       'issues':issues,'candidates':[c.model_dump(mode='json') for c in artifact.candidates if c.semantic_field==semantic]})
    return errors


def run(args):
    from src.adapters.ocr.registry import load_default_config
    from src.adapters.ocr.protocol import OCRConfig
    from src.extraction.service import implementation_sha
    manifest=read(args.manifest);verify_dataset(manifest,ROOT)
    selected=[row for row in manifest['entries'] if row['split']==args.split]
    if not selected:raise ValueError('Selected split has no inputs; provide real data first')
    if args.split=='test' and not args.open_test:raise ValueError('Use --open-test only after freezing the candidate; opening test for tuning consumes it')
    config=OCRConfig.model_validate(read(args.config)) if args.config else load_default_config()
    out=fresh_directory(args.run_id)
    write(out/'state.json',{'state':'RUNNING','split':args.split})
    implementation={str(p.relative_to(APP)):file_hash(p) for p in (APP/'src').rglob('*.py')}
    report={'version':'ocr-evaluation-v1','manifest_sha256':manifest['manifest_sha256'],'split':args.split,
            'run_state':'RUNNING','expected_cases':[entry['case_id'] for entry in selected],
            'created_at':datetime.now(timezone.utc).isoformat(),'machine':platform.platform(),'python':sys.version,
            'config':config.model_dump(mode='json'),'render_dpi':args.render_dpi,'extractor_sha256':implementation_sha(),
            'implementation_sha256':fingerprint(implementation),'runner_sha256':file_hash(Path(__file__)),
            'model_inference_calls':0,'fresh_database_per_case':True,'workload_controlled':args.dedicated_machine,'cases':[]}
    write(out/'manifest.json',manifest)
    for entry in selected:
        folder=out/entry['case_id'];folder.mkdir()
        try:row=execute_case(entry,folder,config,args.render_dpi)
        except Exception as error:
            # No invoice values or framework exception payloads in aggregate logs.
            import traceback
            (folder/'runner_error.txt').write_text(traceback.format_exc(),encoding='utf-8')
            row={'case_id':entry['case_id'],'sha256':entry['sha256'],'input_kind':entry['input_kind'],
                 'group_id':entry['group_id'],'derived_render':entry.get('derived_render',False),
                 'state':'RUNNER_ERROR','error_code':type(error).__name__,'score':score_record(None,entry['labels']),
                 'elapsed_seconds':None,'timings':[],'page_count':None}
        report['cases'].append(row);report['model_inference_calls']+=len(row['timings'])
        report['summary']=summarize(report['cases'],args.dedicated_machine);write(out/'report.json',report)
        print(json.dumps({'case_id':entry['case_id'],'state':row['state'],'labeled':row['score']['labeled'],'correct':row['score']['correct']}),flush=True)
    try:verify_dataset(manifest,ROOT)
    except ValueError:
        report.update(run_state='INVALIDATED',dataset_validated_at_end=False)
        write(out/'report.json',report);write(out/'state.json',{'state':'INVALIDATED','error_code':'DATASET_CHANGED'})
        return 1
    report.update(run_state='COMPLETED',dataset_validated_at_end=True)
    write(out/'report.json',report)
    write(out/'state.json',{'state':'COMPLETED','processing_failures':report['summary']['failed'],'release_approved':False})
    print(str(out/'report.json'))
    return int(bool(report['summary']['failed']))


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    seal=sub.add_parser('seal');seal.add_argument('--input',type=Path,required=True);seal.add_argument('--run-id',required=True)
    execute=sub.add_parser('run');execute.add_argument('--manifest',type=Path,required=True);execute.add_argument('--run-id',required=True)
    execute.add_argument('--split',choices=('dev','test'),default='dev');execute.add_argument('--open-test',action='store_true')
    execute.add_argument('--config',type=Path);execute.add_argument('--render-dpi',type=int,choices=(150,200,300),default=150)
    execute.add_argument('--dedicated-machine',action='store_true',help='Declare no competing tests/inference/workloads during latency measurement')
    compare=sub.add_parser('compare');compare.add_argument('--baseline',type=Path,required=True);compare.add_argument('--candidate',type=Path,required=True);compare.add_argument('--run-id',required=True)
    template=sub.add_parser('template');template.add_argument('--run-id',required=True)
    pilot=sub.add_parser('pilot-intake');pilot.add_argument('--run-id',required=True)
    args=parser.parse_args()
    if args.command=='run':return run(args)
    if args.command=='pilot-intake':
        from benchmark_public_invoices import CASES,SCAN_CASES,DATA
        labels=read(DATA/'labels.json');entries=[]
        for case in CASES:
            group=case.rsplit('-p',1)[0]
            for suffix,kind,derived in [('.pdf','pdf_text',False)]+([('.png','pdf_scan',True)] if case in SCAN_CASES else []):
                source=DATA/'cases'/(case+suffix)
                if not source.is_file():continue
                fields={k:v for k,v in labels.get(case,{}).get('fields',{}).items() if k in HEADER_FIELDS and v is not None}
                entries.append({'case_id':case+('-scan' if derived else '-native'),'path':str(source.relative_to(ROOT)),
                    'input_kind':kind,'group_id':case,'source_group':group,'layout_group':group,'derived_render':derived,
                    'split':'dev','number_locale':'VI','used_for_tuning':True,
                    'labels':{'review_status':'DRAFT','complete':False,'fields':fields,'items':[]}})
        out=fresh_directory(args.run_id);write(out/'intake.json',entries);print(str(out/'intake.json'));return 0
    if args.command=='template':
        out=fresh_directory(args.run_id)
        write(out/'intake.json',[{'case_id':'invoice-001','path':'data invoice/ocr_quality_inputs/invoice-001.pdf',
            'input_kind':'pdf_text','group_id':'invoice-group-001','source_group':'vendor-001','layout_group':'layout-001',
            'split':'dev','number_locale':'AUTO','used_for_tuning':False,
            'labels':{'review_status':'DRAFT','reviewer':None,'complete':False,'fields':{},'items':[]}}])
        write(out/'label_fields.json',{'header_fields':HEADER_FIELDS,'item_fields':ITEM_FIELDS,
            'instructions':'Use canonical strings; null means confirmed not printed, not unknown. Omit unreviewed fields. Only complete=true after every printed row/cell is labeled.'})
        print(str(out/'intake.json'));return 0
    if args.command=='seal':
        from benchmark_public_invoices import CASES
        used=set(CASES)|{'charity_2023','software_kct','cyber_construction','misa_public_filing','viettel_adjustment','accounting_training'}
        from benchmark_public_invoices import DATA
        used.update(file_hash(path) for case in CASES for suffix in ('.pdf','.png')
                    if (path:=DATA/'cases'/(case+suffix)).is_file())
        manifest=seal_dataset(read(args.input),ROOT,used)
        out=fresh_directory(args.run_id);write(out/'manifest.json',manifest);print(str(out/'manifest.json'));return 0
    result=compare_runs(read(args.baseline),read(args.candidate));out=fresh_directory(args.run_id)
    write(out/'comparison.json',result);print(json.dumps(result));return 0 if result['technical_gate_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
