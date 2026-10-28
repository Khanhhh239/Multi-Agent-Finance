"""Prepare auditable error crops, run bounded recognizers, and check holdout intake."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import sys
import time
import unicodedata
from uuid import uuid4

import ocr_quality as q
from src.adapters.ocr.protocol import NormalizedDocumentExtraction,OCRConfig,OCRBridgeRequest,correlate
from src.adapters.ocr.worker_client import WorkerClient
from src.extraction.contracts import ExtractionArtifact
from src.recovery.regions import plan_regions,region_box,crop_box
from src.recovery.field_reads import text_read,typed_read,is_typed
from src.quality.ocr_evaluation import canonical,validate_labels,seal_dataset
from src.quality.completeness import flatten

SCOPES=('UNREVIEWED','ROW_PRINTED','DOCUMENT_PRINTED','NOT_PRINTED','UNREADABLE','INFERRED')


def edit_distance(a,b):
    previous=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        current=[i]
        for j,y in enumerate(b,1):current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(x!=y)))
        previous=current
    return previous[-1]


def audit_labels(audit,labels):
    """A reviewed sidecar changes evaluation scope, never extractor inputs."""
    if audit['labels_sha256']!=q.fingerprint(labels):raise ValueError('Audit/labels hash mismatch')
    seen=set()
    for row in audit['rows']:
        key=(row['case_id'],row['field_path'])
        if key in seen:raise ValueError('Duplicate audit field')
        seen.add(key)
        case=labels['cases'].get(row['case_id'])
        if not case or case['sha256']!=row['source_sha256']:raise ValueError('Audit/source mismatch')
        if row['scope'] not in SCOPES:raise ValueError('Unknown label scope')
        path=row['field_path'];parts=path.split('.')
        if path.startswith('items.'):
            if len(parts)!=3 or not parts[1].isdigit() or int(parts[1])<1:raise ValueError('Invalid row path')
            items=case['labels'].get('items',[]);index=int(parts[1])-1
            if index>=len(items) or parts[2] not in items[index]:raise ValueError('Unknown labeled row')
            expected=items[index][parts[2]]
        else:
            if path not in case['labels'].get('fields',{}):raise ValueError('Unknown labeled field')
            expected=case['labels']['fields'][path]
        if row['label_text']!=expected:raise ValueError('Audit must not silently replace labels')
        if row['review_status'] not in ('DRAFT','SELF_CHECK_NOT_INDEPENDENT','VERIFIED'):raise ValueError('Invalid audit review state')
        if row['review_status']!='DRAFT' and (row['scope']=='UNREVIEWED' or not row.get('reviewer') or not row.get('reason')):
            raise ValueError('Reviewed scope requires reviewer and source justification')
        if row['review_status']!='DRAFT' and row['scope'] in ('ROW_PRINTED','DOCUMENT_PRINTED') and expected is None:
            raise ValueError('A printed reference needs observed text, not an absence label')
    expected=sum(len(v['labels'].get('fields',{}))+sum(len(i) for i in v['labels'].get('items',[])) for v in labels['cases'].values())
    if len(seen)!=expected:raise ValueError('Audit coverage changed')
    return True


def scoped_score(report,audit,labels):
    audit_labels(audit,labels)
    decisions={(r['case_id'],r['field_path']):r for r in audit['rows']}
    counts=Counter();excluded=Counter()
    for case in report['cases']:
        for outcome in case['score']['outcomes']:
            row=decisions[(case['case_id'],outcome['field_path'])]
            if row['review_status']=='DRAFT' or row['scope'] not in ('ROW_PRINTED','DOCUMENT_PRINTED'):
                excluded[row['scope']]+=1;continue
            if outcome['field_path'].startswith('items.') and row['scope']!='ROW_PRINTED':
                excluded['DOCUMENT_LEVEL_NOT_ROW_PRINTED']+=1;continue
            counts[outcome['outcome']]+=1
    return {'included':sum(counts.values()),'outcomes':dict(counts),'excluded':dict(excluded),
            'release_approved':False,'independent_review':all(r['review_status']=='VERIFIED' for r in audit['rows'])}


def prepare(args):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',args.source_run):raise ValueError('Plain source run ID required')
    source=q.OUTPUT/args.source_run;report=q.read(source/'report.json');manifest=q.read(source/'manifest.json');labels=q.read(source/'labels.json')
    q.verify_dataset(manifest,q.ROOT)
    if report['run_state']!='COMPLETED' or not report['dataset_validated_at_end']:raise ValueError('Completed source run required')
    out=q.fresh_directory(args.run_id);entries={e['case_id']:e for e in manifest['entries']};rows=[];targets=[]
    for case in report['cases']:
        identifier=case['case_id'];entry=entries[identifier]
        if labels['cases'][identifier]['sha256']!=entry['sha256']:raise ValueError('Label/source mismatch')
        validate_labels(labels['cases'][identifier]['labels'])
        artifact=ExtractionArtifact.model_validate_json((source/identifier/'extraction.json').read_bytes())
        doc=NormalizedDocumentExtraction.model_validate_json((source/identifier/'normalized.json').read_bytes())
        if artifact.normalized_input_sha256!=q.fingerprint(doc.model_dump(mode='json')):
            # Canonicalization uses its own stable hash encoding.
            from src.canonicalization.derive import sha
            if artifact.normalized_input_sha256!=sha(doc.model_dump(mode='json')):raise ValueError('OCR observation changed')
        fields=flatten(artifact.record);items=sorted(artifact.record.items,key=lambda i:i.line_number)
        for outcome in case['score']['outcomes']:
            path=outcome['field_path'];semantic=path
            if path.startswith('items.'):
                _,index,name=path.split('.');expected=labels['cases'][identifier]['labels']['items'][int(index)-1][name]
                semantic='items.'+items[int(index)-1].item_id+'.'+name if int(index)<=len(items) else path
            else:expected=labels['cases'][identifier]['labels']['fields'][path]
            field=fields.get(semantic);refs=[e.model_dump(mode='json') for e in field.provenance.evidence] if field else []
            row={'case_id':identifier,'source_sha256':entry['sha256'],'field_path':path,'semantic_field':semantic,
                 'label_text':expected,'scope':'UNREVIEWED','review_status':'DRAFT','reviewer':None,'reason':None,
                 'outcome':outcome['outcome'],'evidence':refs,'region_state':'NOT_PREPARED'}
            rows.append(row)
            if outcome['outcome']!='CORRECT' and expected is not None:
                targets.append((row,artifact,doc,entry))
    audit={'version':'label-evidence-v1','source_run':args.source_run,'manifest_sha256':manifest['manifest_sha256'],
           'labels_sha256':q.fingerprint(labels),'rows':rows,'original_report_unchanged':True}
    audit_labels(audit,labels);q.write(out/'labels.json',labels);q.write(out/'source_report.json',report)
    targets.sort(key=lambda value:(value[0]['outcome']!='WRONG_PRESENT',not value[0]['field_path'].endswith('.name'),value[0]['case_id'],value[0]['field_path']))
    import pymupdf
    crops=[];selected=0
    for row,artifact,doc,entry in targets:
        try:_,regions=plan_regions(artifact.record,artifact,doc,row['semantic_field'])
        except Exception as error:
            row['region_state']=getattr(error,'code',type(error).__name__);continue
        row['region_state']='AVAILABLE';row['region_count']=len(regions)
        category=getattr(args,'category','all')
        numeric=is_typed(row['semantic_field'])
        if (category=='numeric' and not numeric) or (category=='text' and numeric):continue
        if selected>=args.limit:continue
        path=q.local_file(q.ROOT,entry['path'])
        if q.file_hash(path)!=entry['sha256']:raise ValueError('Source PDF changed')
        target={'target_id':f'target-{selected:03d}','case_id':row['case_id'],'field_path':row['field_path'],
                'semantic_field':row['semantic_field'],'expected':row['label_text'],'expected_status':'DRAFT_NOT_VERIFIED',
                'profile':artifact.profile.model_dump(mode='json'),'regions':[]}
        with pymupdf.open(path) as pdf:
            for index,(page,block) in enumerate(regions):
                source_page=pdf[page.page_index]
                if source_page.rotation:raise ValueError('Rotated source requires explicit coordinate mapping')
                box=region_box(block);region={'original_text':block.text_raw,'source_evidence':[b.evidence.model_dump(mode='json') for b in getattr(block,'source_blocks',(block,))],'images':{}}
                for dpi in (150,300):
                    x0,y0,x1,y1=box;rect=source_page.rect
                    clip=pymupdf.Rect(max(0,x0-.002)*rect.width,max(0,y0-.001)*rect.height,min(1,x1+.002)*rect.width,min(1,y1+.001)*rect.height)
                    image=source_page.get_pixmap(matrix=pymupdf.Matrix(dpi/72,dpi/72),clip=clip)
                    if image.width*image.height>1_000_000:raise ValueError('Crop pixel budget exceeded')
                    name=f'{target["target_id"]}-{index}-{dpi}.png';image.save(out/name)
                    region['images'][str(dpi)]={'path':name,'sha256':q.file_hash(out/name),'width':image.width,'height':image.height}
                target['regions'].append(region)
        crops.append(target);selected+=1
    q.write(out/'label_evidence.json',audit)
    q.write(out/'crops.json',{'version':'invoice-crop-experiment-v1','source_run':args.source_run,
                            'labels_status':'DRAFT_NOT_VERIFIED','source_manifest_sha256':manifest['manifest_sha256'],'targets':crops})
    q.write(out/'inventory.json',{'labeled':len(rows),'errors':sum(r['outcome']!='CORRECT' for r in rows),
             'region_states':dict(Counter(r['region_state'] for r in rows if r['outcome']!='CORRECT')),'crop_targets':selected,
             'scope_review':'PENDING','release_approved':False})
    print(str(out),flush=True)


def benchmark(args):
    folder=q.OUTPUT/args.run_id;manifest=q.read(folder/'crops.json');manifest_hash=q.file_hash(folder/'crops.json')
    destination=folder/('benchmark-'+args.arm+'.json')
    if destination.exists():raise ValueError('Frozen benchmark result exists')
    arms={'baseline':('round3_crop_base',150),'width':('round3_crop_wide',150),
          'beam':('round3_crop_beam',150),'pdf300':('round3_crop_base',300),'production':('vietocr_region_v1',150)}
    model,dpi=arms[args.arm];client=WorkerClient(model_id=model);runtime=client.inventory()['runtime_sha256']
    config=OCRConfig(version='crop-round3-v1',model_id=model,timeout_seconds=120,memory_mb=3072,max_attempts=1,max_output_bytes=262144)
    requests=[];bindings=[]
    for target in manifest['targets']:
        for region in target['regions']:
            image=region['images'][str(dpi)];path=q.local_file(folder,image['path'])
            if q.file_hash(path)!=image['sha256']:raise ValueError('Crop changed')
            evidence=region['source_evidence'][0]
            requests.append(OCRBridgeRequest(config_version=config.version,creator='crop-benchmark',stage='ocr',request_id='crop-'+uuid4().hex,
                source_id=evidence['source_id'],document_id=evidence['document_id'],page_id='benchmark-page',page_index=evidence['page_index'],
                image_hash=image['sha256'],image_path=str(path.resolve()),image_width=image['width'],image_height=image['height'],
                model_config_version=config.version,runtime_sha256=runtime,model_id=model,timeout_seconds=config.timeout_seconds))
            bindings.append(target['target_id'])
    started=time.perf_counter();responses=client.run_batch(requests,config);elapsed=time.perf_counter()-started
    if len(requests)!=len(responses):raise ValueError('Response count mismatch')
    grouped={};raw=[]
    for target,request,response in zip(bindings,requests,responses):
        correlate(request,response)
        text=response.result.document_text_raw if response.result else ''
        grouped.setdefault(target,[]).append(text);raw.append(response.model_dump(mode='json'))
    from src.extraction.contracts import ExtractionProfile
    outcomes=[]
    for target in manifest['targets']:
        texts=grouped[target['target_id']];path=target['semantic_field'];profile=ExtractionProfile.model_validate(target['profile'])
        value=typed_read(path,texts,profile) if is_typed(path) else text_read(path,texts)
        expected=target['expected'];actual='' if value is None else str(value)
        good=value is not None and canonical(value,target['field_path'])==canonical(expected,target['field_path'])
        a=unicodedata.normalize('NFC',actual);b=unicodedata.normalize('NFC',expected)
        outcomes.append({'target_id':target['target_id'],'value':value,'exact_match':good,'edits':edit_distance(a,b),'characters':len(b)})
    if q.file_hash(folder/'crops.json')!=manifest_hash:raise ValueError('Crop manifest changed during inference')
    q.write(destination,{'arm':args.arm,'model_id':model,'runtime_sha256':runtime,'manifest_sha256':manifest_hash,
            'profile_sha256':q.file_hash(q.APP/'configs/ocr/engines'/(model+'.json')),'dpi':dpi,'model_inference_calls':len(requests),
            'elapsed_seconds':elapsed,'worker_metrics':client.metrics_history,'raw_responses':raw,'outcomes':outcomes,
            'diagnostic_exact':sum(r['exact_match'] for r in outcomes),'targets':len(outcomes),
            'label_status':'DRAFT_NOT_VERIFIED','scope':'DEV crop diagnostic, not holdout or end-to-end latency','release_approved':False})
    print(args.arm,'finished',len(requests),'real crop reads',flush=True)


def holdout(args):
    if not re.fullmatch(r'[a-f0-9]{64}',args.candidate_sha):raise ValueError('Freeze a SHA-256 candidate identifier')
    from src.extraction.service import implementation_sha
    from src.recovery.regions import implementation_sha as recovery_sha
    if args.candidate_sha!=implementation_sha():raise ValueError('Freeze the current candidate before admitting test inputs')
    previous=q.read(q.OUTPUT/args.source_run/'manifest.json');supplied=q.read(args.input)
    used=set(previous.get('used_groups',()))
    for entry in previous['entries']:
        used.update(entry.get(k) for k in ('case_id','group_id','source_group','layout_group','sha256'))
        if entry.get('source_bundle_sha256'):used.add(entry['source_bundle_sha256'])
    if any(row.get('source_bundle_sha256') in used for row in supplied if row.get('source_bundle_sha256')):
        raise ValueError('A page from a development source bundle cannot become holdout')
    sealed=seal_dataset(supplied,q.ROOT,used)
    if any(row['split']!='test' for row in sealed['entries']):raise ValueError('Holdout intake requires test split')
    out=q.fresh_directory(args.run_id);q.write(out/'manifest.json',sealed)
    q.write(out/'candidate_snapshot.json',{'extractor_sha256':args.candidate_sha,'recovery_sha256':recovery_sha(),
          'render_dpi':getattr(args,'render_dpi',150),
          'ocr_config_sha256':{str(p.relative_to(q.APP)):q.file_hash(p) for p in sorted((q.APP/'configs/ocr').rglob('*.json'))},
          'release_approved':False})
    q.write(out/'readiness.json',{'state':'READY_FOR_LABEL_REVIEW' if sealed['entries'] else 'PENDING_UNSEEN_DATA',
            'cases':len(sealed['entries']),'candidate_frozen':args.candidate_sha,'release_approved':False})
    print(str(out),flush=True)


def evaluate_holdout(args):
    """Open a pinned unseen split once; retrying cannot silently change code."""
    from src.extraction.service import implementation_sha
    from src.recovery.regions import implementation_sha as recovery_sha
    from types import SimpleNamespace
    folder=q.OUTPUT/args.source_run;snapshot=q.read(folder/'candidate_snapshot.json');manifest=q.read(folder/'manifest.json')
    q.verify_dataset(manifest,q.ROOT)
    configs={str(p.relative_to(q.APP)):q.file_hash(p) for p in sorted((q.APP/'configs/ocr').rglob('*.json'))}
    if (snapshot['extractor_sha256'],snapshot['recovery_sha256'],snapshot['ocr_config_sha256'])!=(implementation_sha(),recovery_sha(),configs):
        raise ValueError('Candidate changed after holdout freeze')
    if not manifest['entries']:raise ValueError('PENDING_UNSEEN_DATA: supply new invoices before opening test')
    if any(e['split']!='test' or e['labels'].get('review_status')!='VERIFIED' or not e['labels'].get('complete') for e in manifest['entries']):
        raise ValueError('Holdout requires complete verified references before evaluation')
    q.write(folder/'test_consumed.json',{'candidate_sha256':snapshot['extractor_sha256'],'state':'OPENED_FOR_EVALUATION',
           'run_id':args.run_id,'created_at':datetime.now(timezone.utc).isoformat(),'must_not_use_for_tuning':True})
    return q.run(SimpleNamespace(manifest=folder/'manifest.json',run_id=args.run_id,split='test',open_test=True,
                                config=None,render_dpi=snapshot.get('render_dpi',150),dedicated_machine=args.dedicated_machine))


def export_labels(args):
    folder=q.OUTPUT/args.source_run;labels=q.read(folder/'labels.json');audit=q.read(args.audit)
    audit_labels(audit,labels);updated=json.loads(json.dumps(labels));changes=[]
    for row in audit['rows']:
        if 'proposed_label_text' not in row:continue
        if row['review_status']=='DRAFT' or row['scope'] in ('UNREVIEWED','INFERRED','UNREADABLE'):
            raise ValueError('A proposed label must have a checked visible source/scope')
        value=row['proposed_label_text']
        if value is not None and not isinstance(value,str):raise ValueError('Reference labels require strings or null')
        case=updated['cases'][row['case_id']]['labels'];path=row['field_path']
        if path.startswith('items.'):
            _,index,name=path.split('.');case['items'][int(index)-1][name]=value
        else:case['fields'][path]=value
        changes.append({'case_id':row['case_id'],'field_path':path,'before':row['label_text'],'after':value,
                        'review_status':row['review_status'],'reviewer':row['reviewer'],'reason':row['reason']})
    for case in updated['cases'].values():validate_labels(case['labels'])
    out=q.fresh_directory(args.run_id);q.write(out/'labels.json',updated)
    q.write(out/'label_changes.json',{'source_labels_sha256':q.fingerprint(labels),'revised_labels_sha256':q.fingerprint(updated),
              'changes':changes,'original_unchanged':True,'release_approved':False})
    print(str(out/'labels.json'),flush=True)


def compare_labels(args):
    labels=q.read(args.labels);label_hash=q.file_hash(args.labels);reports=[]
    for name in (args.baseline_run,args.candidate_run):
        folder=q.OUTPUT/name;report=q.read(folder/'report.json');manifest=q.read(folder/'manifest.json');q.verify_dataset(manifest,q.ROOT)
        if set(labels['cases'])!=set(report['expected_cases']):raise ValueError('Label coverage mismatch')
        cases=[]
        for case in report['cases']:
            annotation=labels['cases'][case['case_id']]
            if annotation['sha256']!=case['sha256']:raise ValueError('Label/source mismatch')
            artifact=ExtractionArtifact.model_validate_json((folder/case['case_id']/'extraction.json').read_bytes())
            if artifact.input_sha256!=annotation['sha256']:raise ValueError('Artifact/source mismatch')
            cases.append({**case,'score':q.score_record(artifact.record,annotation['labels'])})
        reports.append({**report,'cases':cases,'summary':q.summarize(cases,False)})
    if q.file_hash(args.labels)!=label_hash:raise ValueError('Reference labels changed')
    out=q.fresh_directory(args.run_id)
    for label,report in zip(('baseline','candidate'),reports):q.write(out/(label+'.json'),report)
    q.write(out/'comparison.json',{**q.compare_runs(*reports),'labels_sha256':label_hash,
               'protocol':'Both frozen artifacts rescored on the same revised labels; not a change in recognizer accuracy'})
    print(str(out/'comparison.json'),flush=True)


def score_audit(args):
    folder=q.OUTPUT/args.source_run;labels=q.read(folder/'labels.json');audit=q.read(args.audit)
    result=scoped_score(q.read(folder/'source_report.json'),audit,labels)
    out=q.fresh_directory(args.run_id);q.write(out/'scope_score.json',result);q.write(out/'label_evidence.json',audit)
    print(str(out/'scope_score.json'),flush=True)


def summarize_benchmark(args):
    """Score immutable raw predictions with a separate visually checked oracle."""
    folder=q.OUTPUT/args.source_run;manifest=q.read(folder/'crops.json');oracle=q.read(args.oracle)
    if oracle['manifest_sha256']!=q.file_hash(folder/'crops.json'):raise ValueError('Oracle/crop mismatch')
    from src.extraction.contracts import ExtractionProfile
    from src.recovery.regions import implementation_sha
    results=[]
    for arm in ('baseline','width','beam','pdf300','production'):
        path=folder/('benchmark-'+arm+'.json')
        if not path.exists():raise ValueError('Run every arm before drawing a comparison')
        report=q.read(path)
        if report['manifest_sha256']!=oracle['manifest_sha256']:raise ValueError('Benchmark/crop mismatch')
        index=0;rows=[]
        for target in manifest['targets']:
            count=len(target['regions']);responses=report['raw_responses'][index:index+count];index+=count
            checked=oracle['targets'].get(target['target_id'])
            if not checked or checked.get('review_status')!='SELF_CHECK_NOT_INDEPENDENT':continue
            texts=[r['result']['document_text_raw'] if r.get('result') else '' for r in responses]
            field=target['semantic_field'];profile=ExtractionProfile.model_validate(target['profile'])
            value=typed_read(field,texts,profile) if is_typed(field) else text_read(field,texts)
            expected=checked['expected'];actual='' if value is None else str(value)
            good=value is not None and canonical(value,target['field_path'])==canonical(expected,target['field_path'])
            rows.append({'target_id':target['target_id'],'exact':good,'edits':edit_distance(unicodedata.normalize('NFC',actual),unicodedata.normalize('NFC',expected)),
                         'characters':len(expected),'missing':value is None})
        results.append({'arm':arm,'checked_targets':len(rows),'exact':sum(r['exact'] for r in rows),'edits':sum(r['edits'] for r in rows),
                        'characters':sum(r['characters'] for r in rows),'elapsed_seconds':report['elapsed_seconds'],'model_inference_calls':report['model_inference_calls'],
                        'raw_result_sha256':q.file_hash(path),'rows':rows})
    out=q.fresh_directory(args.run_id)
    q.write(out/'benchmark_comparison.json',{'oracle_sha256':q.file_hash(args.oracle),'parser_sha256':implementation_sha(),'arms':results,
            'scope':'Visually checked DEV crop subset; no independent holdout or controlled end-to-end latency',
            'workload_controlled':False,'promotion_approved':False,'release_approved':False})
    print(str(out/'benchmark_comparison.json'),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--source-run',required=True);prep.add_argument('--run-id',required=True);prep.add_argument('--limit',type=int,default=12,choices=range(1,31))
    prep.add_argument('--category',choices=('all','numeric','text'),default='all')
    run=sub.add_parser('benchmark');run.add_argument('--run-id',required=True);run.add_argument('--arm',required=True,choices=('baseline','width','beam','pdf300','production'))
    intake=sub.add_parser('holdout');intake.add_argument('--source-run',required=True);intake.add_argument('--run-id',required=True);intake.add_argument('--input',type=Path,required=True);intake.add_argument('--candidate-sha',required=True)
    intake.add_argument('--render-dpi',type=int,choices=(150,200,300),default=150)
    evaluate=sub.add_parser('evaluate-holdout');evaluate.add_argument('--source-run',required=True);evaluate.add_argument('--run-id',required=True);evaluate.add_argument('--dedicated-machine',action='store_true')
    for command in ('export-labels','score-audit'):
        item=sub.add_parser(command);item.add_argument('--source-run',required=True);item.add_argument('--run-id',required=True);item.add_argument('--audit',type=Path,required=True)
    revised=sub.add_parser('compare-labels');revised.add_argument('--baseline-run',required=True);revised.add_argument('--candidate-run',required=True);revised.add_argument('--labels',type=Path,required=True);revised.add_argument('--run-id',required=True)
    summary=sub.add_parser('summarize-benchmark');summary.add_argument('--source-run',required=True);summary.add_argument('--run-id',required=True);summary.add_argument('--oracle',type=Path,required=True)
    args=parser.parse_args()
    for name in ('run_id','source_run','baseline_run','candidate_run'):
        if hasattr(args,name) and not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',getattr(args,name)):parser.error('Use plain run IDs')
    if args.command=='prepare':prepare(args)
    elif args.command=='benchmark':benchmark(args)
    elif args.command=='holdout':holdout(args)
    elif args.command=='evaluate-holdout':return evaluate_holdout(args)
    elif args.command=='export-labels':export_labels(args)
    elif args.command=='compare-labels':compare_labels(args)
    elif args.command=='summarize-benchmark':summarize_benchmark(args)
    else:score_audit(args)


if __name__=='__main__':raise SystemExit(main())
